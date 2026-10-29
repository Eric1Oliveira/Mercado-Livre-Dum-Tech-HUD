"""Venda e servico que se repetem: mensalidade, contrato de manutencao.

Quem vende assinatura, fornece todo mes para o mesmo cliente ou faz a
manutencao preventiva do ar-condicionado a cada tres meses cadastrava a mesma
venda (ou a mesma ordem) de novo a cada vez - e era sempre a do mes que ele
esquecia de cobrar.

Aqui mora a parte que nao muda entre o Vendas e as Ordens: o cadastro do
contrato, as datas e quais vezes ja estao devidas. Quem transforma uma vez
devida em documento de verdade (a venda pendente, a ordem aberta) e o proprio
modulo, em `apps/<modulo>/recorrencias.py`, porque so ele sabe o que e uma
venda ou uma ordem.

De proposito sem Qt, como `core/eventos.py`: o motor e testado e usado sem
interface nenhuma.

AS REGRAS
    * A vez e gerada com antecedencia (`gerar(..., antecedencia)`): a venda do
      mes que vem ja aparece como conta a receber no Financeiro, que e onde o
      dono olha para saber quanto vai entrar.
    * Frequencia e inicio so mudam enquanto nada foi gerado - mexer depois
      seria refazer a serie, a mesma regra da recorrencia do Financeiro.
    * Pausar para de gerar; retomar NAO cobra o que ficou para tras.
    * Gerar e idempotente: o modulo confere se a vez ja virou documento antes
      de criar outro, e uma vez que falhou fica para a proxima rodada.
"""

from __future__ import annotations

import calendar
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from sqlite3 import Row
from typing import Callable

from .errors import RegraError

logger = logging.getLogger(__name__)

SEMANAL = "semanal"
QUINZENAL = "quinzenal"
MENSAL = "mensal"
BIMESTRAL = "bimestral"
TRIMESTRAL = "trimestral"
SEMESTRAL = "semestral"
ANUAL = "anual"

FREQUENCIAS = (
    (MENSAL, "Todo mês"),
    (SEMANAL, "Toda semana"),
    (QUINZENAL, "A cada 15 dias"),
    (BIMESTRAL, "A cada 2 meses"),
    (TRIMESTRAL, "A cada 3 meses"),
    (SEMESTRAL, "A cada 6 meses"),
    (ANUAL, "Todo ano"),
)
FREQUENCIA_LABEL = dict(FREQUENCIAS)

#: passo de cada frequencia: (dias, meses)
_PASSO = {
    SEMANAL: (7, 0),
    QUINZENAL: (15, 0),
    MENSAL: (0, 1),
    BIMESTRAL: (0, 2),
    TRIMESTRAL: (0, 3),
    SEMESTRAL: (0, 6),
    ANUAL: (0, 12),
}

#: teto de vezes geradas por contrato numa rodada. Contrato semanal com inicio
#: esquecido la atras nao pode despejar duzentas vendas de uma vez.
LIMITE_POR_RODADA = 24

ATIVA = "ativa"
PAUSADA = "pausada"
ENCERRADA = "encerrada"
SITUACAO_LABEL = {ATIVA: "Ativa", PAUSADA: "Pausada", ENCERRADA: "Encerrada"}
SITUACAO_TOM = {ATIVA: "success", PAUSADA: "warning", ENCERRADA: "muted"}

#: a tabela e a mesma nos dois bancos (vendas.db e ordens.db)
TABELA = """
CREATE TABLE IF NOT EXISTS recorrencias (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    numero      TEXT    NOT NULL UNIQUE,
    cliente     TEXT    NOT NULL DEFAULT '',
    descricao   TEXT    NOT NULL DEFAULT '',
    frequencia  TEXT    NOT NULL DEFAULT 'mensal',
    inicio      TEXT    NOT NULL,
    fim         TEXT    NOT NULL DEFAULT '',
    -- qual vez vem a seguir (0 = a do inicio)
    indice      INTEGER NOT NULL DEFAULT 0,
    ativa       INTEGER NOT NULL DEFAULT 1,
    desconto    REAL    NOT NULL DEFAULT 0,
    observacoes TEXT    NOT NULL DEFAULT '',
    -- os itens de cada vez, em JSON: descricao, quantidade, valor_unitario e
    -- a ligacao com o Estoque (produto_id, codigo, unidade, casas)
    itens       TEXT    NOT NULL DEFAULT '[]',
    criado_em   TEXT    NOT NULL
);
"""


class RecorrenciaError(RegraError):
    """Erro de regra de negocio (mensagem pronta para o usuario)."""


def ler_data(texto: str | None) -> date | None:
    try:
        return datetime.fromisoformat(texto).date() if texto else None
    except ValueError:
        return None


def data_da_vez(inicio: date, frequencia: str, indice: int) -> date:
    """A data da vez `indice`, contada sempre do inicio.

    Contar do inicio, e nao da vez anterior, e o que segura o dia: um contrato
    do dia 31 cai em 28/02 e volta para 31/03, em vez de ficar preso no 28.
    """
    dias, meses = _PASSO.get(frequencia, _PASSO[MENSAL])
    if meses:
        total = inicio.month - 1 + meses * indice
        ano, mes = inicio.year + total // 12, total % 12 + 1
        return date(ano, mes, min(inicio.day, calendar.monthrange(ano, mes)[1]))
    return inicio + timedelta(days=dias * indice)


@dataclass
class Recorrencia:
    id: int | None = None
    numero: str = ""
    cliente: str = ""
    descricao: str = ""
    frequencia: str = MENSAL
    inicio: str = field(default_factory=lambda: date.today().isoformat())
    #: ultima data que ainda pode gerar; vazio = ate alguem pausar
    fim: str = ""
    indice: int = 0
    ativa: bool = True
    desconto: float = 0.0
    observacoes: str = ""
    itens: list[dict] = field(default_factory=list)
    criado_em: str = ""
    #: quantas vezes ja viraram documento (contado na leitura pelo modulo)
    gerados: int = 0

    # ---------------------------------------------------------------- valores
    @property
    def subtotal(self) -> float:
        return round(sum(float(i.get("quantidade") or 0) * float(i.get("valor_unitario") or 0)
                         for i in self.itens), 2)

    @property
    def valor(self) -> float:
        """O que cada vez vale."""
        return round(max(self.subtotal - float(self.desconto or 0), 0.0), 2)

    # ------------------------------------------------------------------ datas
    @property
    def proxima(self) -> str:
        """Data da proxima vez; vazio quando o contrato ja acabou."""
        inicio = ler_data(self.inicio)
        if inicio is None:
            return ""
        quando = data_da_vez(inicio, self.frequencia, self.indice)
        fim = ler_data(self.fim)
        return "" if fim is not None and quando > fim else quando.isoformat()

    @property
    def situacao(self) -> str:
        if not self.proxima:
            return ENCERRADA
        return ATIVA if self.ativa else PAUSADA

    @property
    def situacao_label(self) -> str:
        return SITUACAO_LABEL[self.situacao]

    @property
    def situacao_tom(self) -> str:
        return SITUACAO_TOM[self.situacao]

    @property
    def frequencia_label(self) -> str:
        return FREQUENCIA_LABEL.get(self.frequencia, self.frequencia)

    @property
    def pode_mudar_serie(self) -> bool:
        """Inicio e frequencia so mudam antes da primeira vez gerada."""
        return self.indice == 0

    @classmethod
    def from_row(cls, row: Row) -> "Recorrencia":
        try:
            itens = json.loads(row["itens"] or "[]")
        except ValueError:
            logger.warning("Itens ilegiveis na recorrencia %s", row["numero"])
            itens = []
        return cls(
            id=row["id"],
            numero=row["numero"],
            cliente=row["cliente"] or "",
            descricao=row["descricao"] or "",
            frequencia=row["frequencia"] or MENSAL,
            inicio=row["inicio"],
            fim=row["fim"] or "",
            indice=int(row["indice"] or 0),
            ativa=bool(row["ativa"]),
            desconto=float(row["desconto"] or 0),
            observacoes=row["observacoes"] or "",
            itens=itens if isinstance(itens, list) else [],
            criado_em=row["criado_em"] or "",
        )


class RecorrenciasRepository:
    """Cadastro dos contratos, no banco do modulo que os usa."""

    def __init__(self, database, prefixo: str) -> None:
        self.db = database
        #: VREC (Vendas) ou OSREC (Ordens): o numero vai parar no Financeiro,
        #: e la os dois modulos dividem a mesma lista
        self.prefixo = prefixo

    # ---------------------------------------------------------------- leitura
    def listar(self, busca: str = "") -> list[Recorrencia]:
        sql = "SELECT * FROM recorrencias"
        params: list = []
        if busca.strip():
            sql += " WHERE numero LIKE ? OR cliente LIKE ? OR descricao LIKE ?"
            alvo = f"%{busca.strip()}%"
            params = [alvo, alvo, alvo]
        sql += " ORDER BY ativa DESC, cliente COLLATE NOCASE, id"
        return [Recorrencia.from_row(row) for row in self.db.query(sql, params)]

    def obter(self, recorrencia_id: int) -> Recorrencia | None:
        row = self.db.query_one("SELECT * FROM recorrencias WHERE id = ?", (recorrencia_id,))
        return Recorrencia.from_row(row) if row else None

    def proximo_numero(self) -> str:
        ano = date.today().year
        prefixo = f"{self.prefixo}-{ano}-"
        maior = 0
        for row in self.db.query(
            "SELECT numero FROM recorrencias WHERE numero LIKE ?", (f"{prefixo}%",)
        ):
            sufixo = str(row["numero"])[len(prefixo):]
            if sufixo.isdigit():
                maior = max(maior, int(sufixo))
        return f"{prefixo}{maior + 1:04d}"

    # ---------------------------------------------------------------- escrita
    def salvar(self, rec: Recorrencia) -> Recorrencia:
        self._validar(rec)
        valores = (
            rec.numero.strip(), rec.cliente.strip(), rec.descricao.strip(),
            rec.frequencia, rec.inicio, rec.fim or "", int(rec.indice),
            int(bool(rec.ativa)), round(float(rec.desconto or 0), 2),
            rec.observacoes.strip(), json.dumps(rec.itens, ensure_ascii=False),
        )
        if rec.id is None:
            rec.criado_em = datetime.now().isoformat(timespec="seconds")
            cursor = self.db.execute(
                """
                INSERT INTO recorrencias (numero, cliente, descricao, frequencia, inicio,
                                          fim, indice, ativa, desconto, observacoes,
                                          itens, criado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                valores + (rec.criado_em,),
            )
            rec.id = int(cursor.lastrowid)
        else:
            antes = self.obter(rec.id)
            if antes is not None and not antes.pode_mudar_serie and (
                antes.inicio != rec.inicio or antes.frequencia != rec.frequencia
            ):
                raise RecorrenciaError(
                    "Início e frequência não mudam depois que a primeira vez foi gerada. "
                    "Encerre este cadastro e crie outro."
                )
            # `indice` e `ativa` NAO entram: quem anda com eles e o gerador e o
            # pausar/retomar. Regravar o que o dialogo leu ao abrir desfaria
            # uma vez gerada enquanto a pessoa editava.
            numero, cliente, descricao, frequencia, inicio, fim, _, _, *resto = valores
            self.db.execute(
                """
                UPDATE recorrencias SET numero = ?, cliente = ?, descricao = ?,
                       frequencia = ?, inicio = ?, fim = ?,
                       desconto = ?, observacoes = ?, itens = ?
                WHERE id = ?
                """,
                (numero, cliente, descricao, frequencia, inicio, fim, *resto, rec.id),
            )
        return rec

    def excluir(self, recorrencia_id: int) -> None:
        """Apaga o cadastro. O que ja foi gerado continua - e historico."""
        self.db.execute("DELETE FROM recorrencias WHERE id = ?", (recorrencia_id,))

    def pausar(self, recorrencia_id: int) -> None:
        self.db.execute("UPDATE recorrencias SET ativa = 0 WHERE id = ?", (recorrencia_id,))

    def retomar(self, recorrencia_id: int, hoje: date | None = None) -> None:
        """Volta a gerar a partir de hoje: o que ficou parado nao vira cobranca."""
        rec = self.obter(recorrencia_id)
        if rec is None:
            return
        hoje = hoje or date.today()
        inicio = ler_data(rec.inicio)
        indice = rec.indice
        if inicio is not None:
            while data_da_vez(inicio, rec.frequencia, indice) < hoje:
                indice += 1
        self.db.execute("UPDATE recorrencias SET ativa = 1, indice = ? WHERE id = ?",
                        (indice, recorrencia_id))

    def _avancar(self, recorrencia_id: int, indice: int) -> None:
        self.db.execute("UPDATE recorrencias SET indice = ? WHERE id = ?",
                        (indice, recorrencia_id))

    # ----------------------------------------------------------------- regras
    def _validar(self, rec: Recorrencia) -> None:
        if not rec.numero.strip():
            rec.numero = self.proximo_numero()
        if not rec.cliente.strip():
            raise RecorrenciaError("Informe o cliente: cobrança recorrente é sempre de alguém.")
        if rec.frequencia not in FREQUENCIA_LABEL:
            raise RecorrenciaError("Escolha de quanto em quanto tempo se repete.")
        inicio = ler_data(rec.inicio)
        if inicio is None:
            raise RecorrenciaError("Informe a data da primeira vez.")
        if rec.fim:
            fim = ler_data(rec.fim)
            if fim is None:
                raise RecorrenciaError("Data final inválida. Use dd/mm/aaaa ou deixe em branco.")
            if fim < inicio:
                raise RecorrenciaError("A data final não pode ser antes da primeira vez.")
        if not rec.itens:
            raise RecorrenciaError("Adicione pelo menos um item.")
        if float(rec.desconto or 0) > rec.subtotal:
            raise RecorrenciaError("O desconto não pode ser maior que o total dos itens.")
        repetido = self.db.query_one(
            "SELECT id FROM recorrencias WHERE numero = ? AND id IS NOT ?",
            (rec.numero.strip(), rec.id),
        )
        if repetido is not None:
            raise RecorrenciaError(f"Já existe um cadastro com o número {rec.numero}.")


def gerar(
    repositorio: RecorrenciasRepository,
    criar: Callable[[Recorrencia, date], str],
    hoje: date | None = None,
    antecedencia: int = 0,
) -> list[str]:
    """Transforma em documento cada vez que ja esta devida.

    Devida = data ate `hoje + antecedencia`. `criar(rec, data)` e do modulo:
    ele cria a venda (ou a ordem) e devolve o numero, e precisa conferir se a
    vez ja existe antes de criar. Uma vez que falha nao derruba as outras -
    nem as dos outros contratos: fica no log e e tentada na proxima rodada.
    """
    hoje = hoje or date.today()
    limite = hoje + timedelta(days=max(int(antecedencia), 0))
    criados: list[str] = []
    for rec in repositorio.listar():
        if not rec.ativa:
            continue
        inicio = ler_data(rec.inicio)
        if inicio is None:
            continue
        fim = ler_data(rec.fim)
        indice = rec.indice
        for _ in range(LIMITE_POR_RODADA):
            quando = data_da_vez(inicio, rec.frequencia, indice)
            if quando > limite or (fim is not None and quando > fim):
                break
            try:
                numero = criar(rec, quando)
            except Exception:  # noqa: BLE001 - um contrato com defeito nao trava os outros
                logger.exception("Nao foi possivel gerar %s de %s", rec.numero, quando)
                break
            if numero:
                criados.append(numero)
            indice += 1
            repositorio._avancar(rec.id, indice)
    return criados
