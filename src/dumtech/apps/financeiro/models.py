"""Estruturas de dados do DumTech Financeiro."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from sqlite3 import Row

from ...core.errors import RegraError

RECEITA = "receita"
DESPESA = "despesa"

TIPOS_LABEL = {RECEITA: "Receita", DESPESA: "Despesa"}

#: tipos de conta onde o dinheiro fica
CAIXA = "caixa"
BANCO = "banco"
CARTAO = "cartao"

CONTA_LABEL = {CAIXA: "Caixa", BANCO: "Banco", CARTAO: "Cartão"}
CONTA_ICONE = {CAIXA: "money", BANCO: "home", CARTAO: "tag"}
CONTA_OPCOES = [(rotulo, chave) for chave, rotulo in CONTA_LABEL.items()]

#: series: varios lancamentos que nasceram juntos
PARCELAMENTO = "parcelamento"
RECORRENCIA = "recorrencia"

#: com que frequencia uma despesa se repete
MENSAL = "mensal"
SEMANAL = "semanal"
QUINZENAL = "quinzenal"
ANUAL = "anual"

FREQUENCIAS = ((MENSAL, "Todo mês"), (SEMANAL, "Toda semana"),
               (QUINZENAL, "A cada 15 dias"), (ANUAL, "Todo ano"))
FREQUENCIA_LABEL = dict(FREQUENCIAS)

#: meio centavo: abaixo disso, dois valores sao o mesmo dinheiro
CENTAVO = 0.005


class FinanceiroError(RegraError):
    """Erro de regra de negocio (mensagem pronta para o usuario)."""


def hoje_iso() -> str:
    return date.today().isoformat()


def ler_data(texto: str | None) -> date | None:
    try:
        return datetime.fromisoformat(texto).date() if texto else None
    except ValueError:
        return None


def somar_meses(quando: date, meses: int) -> date:
    """Mesma data N meses depois; mes curto usa o ultimo dia (31 -> 30/28)."""
    indice = quando.month - 1 + meses
    ano = quando.year + indice // 12
    mes = indice % 12 + 1
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(quando.day, ultimo))


@dataclass
class Conta:
    """Onde o dinheiro fica: o caixa da loja, a conta do banco, o cartao."""

    id: int | None = None
    nome: str = ""
    tipo: str = BANCO
    saldo_inicial: float = 0.0
    observacoes: str = ""
    ativo: bool = True
    criado_em: str = ""
    #: calculado na leitura
    saldo: float = 0.0

    @property
    def tipo_label(self) -> str:
        return CONTA_LABEL.get(self.tipo, self.tipo)

    @property
    def icone(self) -> str:
        return CONTA_ICONE.get(self.tipo, "money")

    @classmethod
    def from_row(cls, row: Row) -> "Conta":
        campos = row.keys()
        return cls(
            id=row["id"],
            nome=row["nome"],
            tipo=row["tipo"],
            saldo_inicial=float(row["saldo_inicial"]),
            observacoes=row["observacoes"] or "",
            ativo=bool(row["ativo"]),
            criado_em=row["criado_em"],
            saldo=float(row["saldo"]) if "saldo" in campos else 0.0,
        )


@dataclass
class Baixa:
    """Um pagamento (ou recebimento) de um lancamento. Pode ser parcial."""

    id: int | None = None
    lancamento_id: int = 0
    data: str = field(default_factory=hoje_iso)
    valor: float = 0.0
    conta_id: int = 0
    forma: str = ""
    observacao: str = ""
    criado_em: str = ""
    #: preenchido nas consultas que juntam a conta
    conta_nome: str = ""

    @classmethod
    def from_row(cls, row: Row) -> "Baixa":
        campos = row.keys()
        return cls(
            id=row["id"],
            lancamento_id=row["lancamento_id"],
            data=row["data"],
            valor=float(row["valor"]),
            conta_id=int(row["conta_id"] or 0),
            forma=row["forma"] or "",
            observacao=row["observacao"] or "",
            criado_em=row["criado_em"],
            conta_nome=row["conta_nome"] if "conta_nome" in campos else "",
        )


@dataclass
class Transferencia:
    """Dinheiro mudando de conta. Nao e receita nem despesa."""

    id: int | None = None
    origem_id: int = 0
    destino_id: int = 0
    data: str = field(default_factory=hoje_iso)
    valor: float = 0.0
    observacao: str = ""
    criado_em: str = ""
    origem_nome: str = ""
    destino_nome: str = ""

    @classmethod
    def from_row(cls, row: Row) -> "Transferencia":
        campos = row.keys()
        return cls(
            id=row["id"],
            origem_id=row["origem_id"],
            destino_id=row["destino_id"],
            data=row["data"],
            valor=float(row["valor"]),
            observacao=row["observacao"] or "",
            criado_em=row["criado_em"],
            origem_nome=row["origem_nome"] if "origem_nome" in campos else "",
            destino_nome=row["destino_nome"] if "destino_nome" in campos else "",
        )


@dataclass
class Lancamento:
    id: int | None = None
    tipo: str = RECEITA
    descricao: str = ""
    categoria: str = ""
    cliente: str = ""
    valor: float = 0.0
    vencimento: str = field(default_factory=hoje_iso)
    pago_em: str | None = None
    forma_pagamento: str = ""
    observacoes: str = ""
    criado_em: str = ""
    #: conta prevista para receber ou pagar
    conta_id: int = 0
    #: lancamentos que nasceram juntos (parcelamento ou recorrencia)
    grupo: str = ""
    parcela: int = 0
    parcelas: int = 0
    serie: str = ""
    #: despesa que se repete todo mes (aluguel, internet); so vale para despesa
    fixa: bool = False
    #: quanto ja foi baixado (somado na leitura, nao gravado)
    baixado: float = 0.0

    @property
    def pago(self) -> bool:
        return bool(self.pago_em)

    @property
    def em_aberto(self) -> float:
        """Quanto ainda falta receber ou pagar."""
        return round(max(self.valor - self.baixado, 0.0), 2)

    @property
    def parcial(self) -> bool:
        return not self.pago and self.baixado > CENTAVO

    @property
    def e_receita(self) -> bool:
        return self.tipo == RECEITA

    @property
    def tipo_label(self) -> str:
        return TIPOS_LABEL.get(self.tipo, self.tipo)

    @property
    def rotulo_parcela(self) -> str:
        return f"{self.parcela}/{self.parcelas}" if self.parcelas > 1 else ""

    @property
    def descricao_completa(self) -> str:
        rotulo = self.rotulo_parcela
        return f"{self.descricao} ({rotulo})" if rotulo else self.descricao

    @property
    def vencido(self) -> bool:
        if self.pago:
            return False
        quando = ler_data(self.vencimento)
        return quando is not None and quando < date.today()

    @property
    def dias_para_vencer(self) -> int | None:
        quando = ler_data(self.vencimento)
        return (quando - date.today()).days if quando else None

    @property
    def situacao(self) -> str:
        if self.pago:
            return "Recebido" if self.e_receita else "Pago"
        if self.parcial:
            return "Parcial"
        return "Vencido" if self.vencido else "Em aberto"

    @property
    def tom(self) -> str:
        if self.pago:
            return "success"
        if self.vencido:
            return "danger"
        return "warning"

    @property
    def valor_com_sinal(self) -> float:
        return self.valor if self.e_receita else -self.valor

    @classmethod
    def from_row(cls, row: Row) -> "Lancamento":
        # a consulta pode trazer colunas de join (baixado, nome da conta): so o
        # que e campo da classe entra no construtor
        proprios = {campo.name for campo in fields(cls)} - {"baixado"}
        campos = set(row.keys())
        dados = {chave: row[chave] for chave in campos & proprios}
        dados["conta_id"] = int(dados.get("conta_id") or 0)
        dados["grupo"] = dados.get("grupo") or ""
        dados["parcela"] = int(dados.get("parcela") or 0)
        dados["parcelas"] = int(dados.get("parcelas") or 0)
        dados["serie"] = dados.get("serie") or ""
        dados["fixa"] = bool(dados.get("fixa") or 0)
        lancamento = cls(**dados)
        if "baixado" in campos:
            lancamento.baixado = round(float(row["baixado"] or 0), 2)
        return lancamento


@dataclass
class DiaDoFluxo:
    """Um dia da projecao: o que entra, o que sai e como fica o saldo."""

    data: str
    entradas: float = 0.0
    saidas: float = 0.0
    saldo: float = 0.0
    atrasado: bool = False
    lancamentos: list[Lancamento] = field(default_factory=list)

    @property
    def movimento(self) -> float:
        return round(self.entradas - self.saidas, 2)

    @property
    def tem_movimento(self) -> bool:
        return abs(self.entradas) > CENTAVO or abs(self.saidas) > CENTAVO


@dataclass
class Projecao:
    """A resposta de 'vou ter dinheiro no dia 12?'."""

    saldo_inicial: float = 0.0
    dias: list[DiaDoFluxo] = field(default_factory=list)
    entradas: float = 0.0
    saidas: float = 0.0
    atrasado_receber: float = 0.0
    atrasado_pagar: float = 0.0

    @property
    def saldo_final(self) -> float:
        return self.dias[-1].saldo if self.dias else self.saldo_inicial

    @property
    def dia_no_vermelho(self) -> DiaDoFluxo | None:
        """O primeiro dia em que o saldo fica negativo - o aviso da tela."""
        for dia in self.dias:
            if dia.saldo < -CENTAVO:
                return dia
        return None

    @property
    def menor_saldo(self) -> float:
        return min((dia.saldo for dia in self.dias), default=self.saldo_inicial)


@dataclass
class ResumoFinanceiro:
    #: tudo que esta em aberto, sem limite de data
    a_receber: float = 0.0
    a_pagar: float = 0.0
    #: so o que vence nos proximos 30 dias - com recorrencia gerada para o ano
    #: inteiro, o total em aberto vira um numero que nao ajuda a decidir nada
    a_receber_mes: float = 0.0
    a_pagar_mes: float = 0.0
    vencidos_valor: float = 0.0
    vencidos_quantidade: int = 0
    recebido_mes: float = 0.0
    pago_mes: float = 0.0
    #: o pago no mes separado entre o que e fixo e o que varia
    pago_fixas_mes: float = 0.0
    pago_variaveis_mes: float = 0.0
    saldo_contas: float = 0.0
    proximos: list[Lancamento] = field(default_factory=list)
    atrasados: list[Lancamento] = field(default_factory=list)
    contas: list[Conta] = field(default_factory=list)
    por_categoria: list[tuple[str, float]] = field(default_factory=list)

    @property
    def saldo_mes(self) -> float:
        return round(self.recebido_mes - self.pago_mes, 2)
