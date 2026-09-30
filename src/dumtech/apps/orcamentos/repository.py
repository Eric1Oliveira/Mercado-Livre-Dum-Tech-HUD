"""Regras do DumTech Orcamentos.

Uma proposta sai da loja e volta com um sim ou um nao. Quase tudo aqui existe
para conseguir dizer, no fim do mes, **quantas voltaram com sim e por que as
outras nao voltaram**.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ...core.database import Database
from .models import (
    APROVADO,
    ENVIADO,
    FUNIL,
    MOTIVOS_LABEL,
    RASCUNHO,
    RECUSADO,
    EtapaFunil,
    ItemOrcamento,
    Orcamento,
    OrcamentoError,
    ResumoOrcamentos,
)

CAMPOS = """
    numero, cliente, data, validade, status, desconto, observacoes,
    condicao_pagamento, prazo_entrega, validade_dias, enviado_em,
    respondido_em, motivo_recusa, total
"""

#: quantos dias sem resposta ja pedem um telefonema
ESPERA_LONGA = 5


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def dinheiro(valor) -> float:
    return round(float(valor or 0), 2)


class OrcamentosRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    # ------------------------------------------------------------------ leitura
    def listar(
        self,
        busca: str = "",
        status: str = "",
        em_aberto: bool = False,
        limite: int = 500,
    ) -> list[Orcamento]:
        sql = "SELECT * FROM orcamentos WHERE 1 = 1"
        params: list = []
        if busca.strip():
            sql += " AND (numero LIKE ? OR cliente LIKE ? OR observacoes LIKE ?)"
            alvo = f"%{busca.strip()}%"
            params += [alvo, alvo, alvo]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if em_aberto:
            sql += " AND status IN (?, ?)"
            params += [RASCUNHO, ENVIADO]
        sql += " ORDER BY date(data) DESC, id DESC LIMIT ?"
        params.append(int(limite))

        orcamentos = [Orcamento.from_row(row) for row in self.db.query(sql, params)]
        for orcamento in orcamentos:
            orcamento.itens = self.itens_de(orcamento.id)
        return orcamentos

    def obter(self, orcamento_id: int) -> Orcamento | None:
        row = self.db.query_one("SELECT * FROM orcamentos WHERE id = ?", (orcamento_id,))
        if row is None:
            return None
        orcamento = Orcamento.from_row(row)
        orcamento.itens = self.itens_de(orcamento.id)
        return orcamento

    def itens_de(self, orcamento_id: int) -> list[ItemOrcamento]:
        return [
            ItemOrcamento.from_row(row)
            for row in self.db.query(
                "SELECT * FROM orcamento_itens WHERE orcamento_id = ? ORDER BY id",
                (orcamento_id,),
            )
        ]

    def proximo_numero(self) -> str:
        """ORC-2026-0001. Continua da maior numeracao ja usada no ano."""
        ano = date.today().year
        prefixo = f"ORC-{ano}-"
        maior = 0
        for row in self.db.query(
            "SELECT numero FROM orcamentos WHERE numero LIKE ?", (f"{prefixo}%",)
        ):
            sufixo = str(row["numero"])[len(prefixo):]
            if sufixo.isdigit():
                maior = max(maior, int(sufixo))
        return f"{prefixo}{maior + 1:04d}"

    def condicoes_usadas(self) -> list[str]:
        return [row["condicao_pagamento"] for row in self.db.query(
            "SELECT DISTINCT condicao_pagamento FROM orcamentos"
            " WHERE TRIM(condicao_pagamento) <> '' ORDER BY condicao_pagamento"
        )]

    # ------------------------------------------------------------------ escrita
    def salvar(self, orcamento: Orcamento) -> Orcamento:
        """Cria ou atualiza a proposta junto com os itens."""
        self._validar(orcamento)
        momento = agora()
        valores = (
            orcamento.numero.strip(),
            orcamento.cliente.strip(),
            orcamento.data,
            orcamento.validade or "",
            orcamento.status,
            dinheiro(orcamento.desconto),
            orcamento.observacoes.strip(),
            orcamento.condicao_pagamento.strip(),
            orcamento.prazo_entrega.strip(),
            int(orcamento.validade_dias or 0),
            orcamento.enviado_em,
            orcamento.respondido_em,
            orcamento.motivo_recusa,
            orcamento.total,
        )
        if orcamento.id is None:
            colunas = ", ".join(campo.strip() for campo in CAMPOS.split(","))
            marcadores = ", ".join("?" for _ in valores)
            cursor = self.db.execute(
                f"INSERT INTO orcamentos ({colunas}, criado_em)"
                f" VALUES ({marcadores}, ?)",
                valores + (momento,),
            )
            orcamento.id = int(cursor.lastrowid)
            orcamento.criado_em = momento
        else:
            atribuicoes = ", ".join(f"{campo.strip()} = ?" for campo in CAMPOS.split(","))
            self.db.execute(
                f"UPDATE orcamentos SET {atribuicoes} WHERE id = ?",
                valores + (orcamento.id,),
            )
        self._gravar_itens(orcamento)
        orcamento.total_gravado = orcamento.total
        return orcamento

    def duplicar(self, orcamento_id: int) -> Orcamento:
        """Copia tudo menos a historia: numero, datas e resposta comecam limpos."""
        origem = self.obter(orcamento_id)
        if origem is None:
            raise OrcamentoError("Orcamento nao encontrado.")

        copia = Orcamento(
            numero=self.proximo_numero(),
            cliente=origem.cliente,
            data=date.today().isoformat(),
            status=RASCUNHO,
            desconto=origem.desconto,
            observacoes=origem.observacoes,
            condicao_pagamento=origem.condicao_pagamento,
            prazo_entrega=origem.prazo_entrega,
            validade_dias=origem.validade_dias,
            itens=[
                ItemOrcamento(
                    descricao=item.descricao, quantidade=item.quantidade,
                    valor_unitario=item.valor_unitario, desconto=item.desconto,
                    unidade=item.unidade,
                )
                for item in origem.itens
            ],
        )
        return self.salvar(copia)

    # -------------------------------------------------------------------- etapas
    def enviar(self, orcamento_id: int, quando: str = "") -> Orcamento:
        """Sair de rascunho marca a data: e dali que conta a espera e a validade."""
        orcamento = self._exigir(orcamento_id)
        if not orcamento.itens:
            raise OrcamentoError("Adicione pelo menos um item antes de enviar.")

        orcamento.status = ENVIADO
        orcamento.enviado_em = quando or date.today().isoformat()
        orcamento.respondido_em = ""
        orcamento.motivo_recusa = ""
        return self.salvar(orcamento)

    def aprovar(self, orcamento_id: int, quando: str = "") -> Orcamento:
        orcamento = self._exigir(orcamento_id)
        orcamento.status = APROVADO
        orcamento.enviado_em = orcamento.enviado_em or date.today().isoformat()
        orcamento.respondido_em = quando or date.today().isoformat()
        orcamento.motivo_recusa = ""
        return self.salvar(orcamento)

    def recusar(self, orcamento_id: int, motivo: str, quando: str = "") -> Orcamento:
        """Perder sem motivo nao vira licao nenhuma."""
        if motivo not in MOTIVOS_LABEL:
            raise OrcamentoError("Escolha por que o orcamento nao foi aprovado.")

        orcamento = self._exigir(orcamento_id)
        orcamento.status = RECUSADO
        orcamento.enviado_em = orcamento.enviado_em or date.today().isoformat()
        orcamento.respondido_em = quando or date.today().isoformat()
        orcamento.motivo_recusa = motivo
        return self.salvar(orcamento)

    def reabrir(self, orcamento_id: int) -> Orcamento:
        """Cliente voltou atras: a proposta volta a esperar resposta."""
        orcamento = self._exigir(orcamento_id)
        orcamento.status = ENVIADO if orcamento.enviado_em else RASCUNHO
        orcamento.respondido_em = ""
        orcamento.motivo_recusa = ""
        return self.salvar(orcamento)

    def excluir(self, orcamento_id: int) -> None:
        self.db.execute("DELETE FROM orcamentos WHERE id = ?", (orcamento_id,))

    # ------------------------------------------------------------------ interno
    def _exigir(self, orcamento_id: int) -> Orcamento:
        orcamento = self.obter(orcamento_id)
        if orcamento is None:
            raise OrcamentoError("Orcamento nao encontrado.")
        return orcamento

    def _gravar_itens(self, orcamento: Orcamento) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM orcamento_itens WHERE orcamento_id = ?", (orcamento.id,)
            )
            for item in orcamento.itens:
                conn.execute(
                    """
                    INSERT INTO orcamento_itens (orcamento_id, descricao, quantidade,
                                                 valor_unitario, desconto, unidade,
                                                 produto_id, codigo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        orcamento.id,
                        item.descricao.strip(),
                        round(float(item.quantidade), 3),
                        dinheiro(item.valor_unitario),
                        dinheiro(item.desconto),
                        item.unidade.strip(),
                        int(item.produto_id or 0),
                        (item.codigo or "").strip(),
                    ),
                )
        orcamento.itens = self.itens_de(orcamento.id)

    def _validar(self, orcamento: Orcamento) -> None:
        if not orcamento.numero.strip():
            raise OrcamentoError("Informe o numero do orcamento.")
        if not orcamento.cliente.strip():
            raise OrcamentoError("Informe o cliente do orcamento.")
        if not orcamento.itens:
            raise OrcamentoError("Adicione pelo menos um item ao orcamento.")
        for item in orcamento.itens:
            if not item.descricao.strip():
                raise OrcamentoError("Todo item precisa de uma descricao.")
            if float(item.quantidade) <= 0:
                raise OrcamentoError(
                    f"A quantidade de '{item.descricao}' precisa ser maior que zero."
                )
            if dinheiro(item.desconto) > item.bruto:
                raise OrcamentoError(
                    f"O desconto de '{item.descricao}' passou do valor da linha."
                )
        if dinheiro(orcamento.desconto) > orcamento.subtotal:
            raise OrcamentoError("O desconto nao pode ser maior que o total dos itens.")
        if int(orcamento.validade_dias or 0) < 0:
            raise OrcamentoError("A validade nao pode ser negativa.")
        repetido = self.db.query_one(
            "SELECT id FROM orcamentos WHERE numero = ? AND id IS NOT ?",
            (orcamento.numero.strip(), orcamento.id),
        )
        if repetido is not None:
            raise OrcamentoError(f"Ja existe um orcamento com o numero {orcamento.numero}.")

    # ------------------------------------------------------------------- funil
    def resumo(self, limite_listas: int = 6) -> ResumoOrcamentos:
        mes = date.today().strftime("%Y-%m")
        todos = self.listar(limite=2000)
        abertos = [o for o in todos if o.em_aberto]
        respondidos = [o for o in todos if o.respondido]
        aprovados = [o for o in respondidos if o.status == APROVADO]
        aprovados_mes = [o for o in aprovados if (o.respondido_em or "")[:7] == mes]

        etapas = [
            EtapaFunil(
                status=status,
                quantidade=len([o for o in todos if o.status == status]),
                valor=dinheiro(sum(o.total for o in todos if o.status == status)),
            )
            for status in FUNIL
        ]

        esperando = sorted(
            (o for o in todos if o.status == ENVIADO),
            key=lambda o: o.enviado_em or o.data,
        )
        limite_vencimento = (date.today() + timedelta(days=7)).isoformat()
        vencendo = sorted(
            (o for o in abertos
             if o.vale_ate and o.vale_ate <= limite_vencimento),
            key=lambda o: o.vale_ate,
        )

        return ResumoOrcamentos(
            total=len(todos),
            abertos=len(abertos),
            aprovados_mes=len(aprovados_mes),
            valor_aprovado_mes=dinheiro(sum(o.total for o in aprovados_mes)),
            valor_em_aberto=dinheiro(sum(o.total for o in abertos)),
            conversao=round(len(aprovados) / len(respondidos) * 100, 1)
            if respondidos else 0.0,
            respondidos=len(respondidos),
            ticket_medio=dinheiro(
                sum(o.total for o in aprovados) / len(aprovados)
            ) if aprovados else 0.0,
            etapas=etapas,
            recentes=todos[:limite_listas],
            aguardando=esperando[:limite_listas],
            vencendo=vencendo[:limite_listas],
            motivos=self._motivos(todos, limite_listas),
        )

    @staticmethod
    def _motivos(todos: list[Orcamento], limite: int) -> list[tuple[str, int, float]]:
        """Por que voce perde - a pergunta que nenhum outro modulo faz."""
        contagem: dict[str, list[float]] = {}
        for orcamento in todos:
            if orcamento.status != RECUSADO:
                continue
            chave = orcamento.motivo_recusa or "sem_resposta"
            contagem.setdefault(chave, []).append(orcamento.total)
        linhas = [
            (MOTIVOS_LABEL.get(chave, chave), len(valores), dinheiro(sum(valores)))
            for chave, valores in contagem.items()
        ]
        return sorted(linhas, key=lambda linha: -linha[1])[:limite]

    def esperando_ha_mais_de(self, dias: int = ESPERA_LONGA) -> list[Orcamento]:
        """Propostas paradas tempo demais: sao elas que pedem um telefonema."""
        return [
            o for o in self.listar(status=ENVIADO, limite=2000)
            if (o.dias_esperando or 0) >= dias
        ]


__all__ = [
    "OrcamentosRepository",
    "ESPERA_LONGA",
    "ItemOrcamento",
    "Orcamento",
    "ResumoOrcamentos",
]
