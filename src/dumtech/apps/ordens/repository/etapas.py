"""A esteira do servico, e o historico que ela deixa.

    Aberta -> Aguardando aprovacao -> Em andamento -> Concluida -> Entregue

Cada passo grava uma linha com data e hora. O historico nunca e apagado: e ele
que responde "quando voces me entregaram?".
"""

from __future__ import annotations

from datetime import date

from ..models import (
    AGUARDANDO,
    ANDAMENTO,
    CANCELADA,
    CONCLUIDA,
    ENTREGUE,
    PROXIMO_PASSO,
    EventoOS,
    Ordem,
    OrdemError,
    STATUS_LABEL,
)
from ....ui import format as fmt
from .comum import agora


class EtapasMixin:
    """Parte do OrdensRepository que move a ordem de etapa."""

    # ---------------------------------------------------------------- historico
    def historico_de(self, ordem_id: int) -> list[EventoOS]:
        return [
            EventoOS.from_row(row)
            for row in self.db.query(
                "SELECT * FROM os_historico WHERE ordem_id = ? ORDER BY id DESC",
                (ordem_id,),
            )
        ]

    def registrar_evento(self, ordem_id: int, status: str, observacao: str = "") -> EventoOS:
        momento = agora()
        cursor = self.db.execute(
            """
            INSERT INTO os_historico (ordem_id, status, observacao, criado_em)
            VALUES (?, ?, ?, ?)
            """,
            (ordem_id, status, observacao.strip(), momento),
        )
        return EventoOS(
            id=int(cursor.lastrowid), ordem_id=ordem_id, status=status,
            observacao=observacao.strip(), criado_em=momento,
        )

    # ------------------------------------------------------------------- etapas
    def definir_status(self, ordem_id: int, status: str, observacao: str = "") -> Ordem:
        """Muda a etapa e deixa registro. Nao aplica as regras de cada passo."""
        ordem = self.obter(ordem_id)
        if ordem is None:
            raise OrdemError("Ordem não encontrada.")
        if status not in STATUS_LABEL:
            raise OrdemError("Etapa inválida.")

        hoje = date.today().isoformat()
        if status == CONCLUIDA:
            concluida, entregue = hoje, ""
        elif status == ENTREGUE:
            concluida, entregue = ordem.concluida_em or hoje, ordem.entregue_em or hoje
        elif status == CANCELADA:
            concluida, entregue = ordem.concluida_em, ordem.entregue_em
        else:
            # voltou para execucao: nem concluida nem entregue aconteceram
            concluida, entregue = None, ""

        self.db.execute(
            "UPDATE ordens SET status = ?, concluida_em = ?, entregue_em = ? WHERE id = ?",
            (status, concluida, entregue, ordem_id),
        )
        self.registrar_evento(ordem_id, status, observacao)
        return self.obter(ordem_id)

    def avancar(self, ordem_id: int, observacao: str = "") -> Ordem:
        """Leva a ordem ao proximo passo da esteira."""
        ordem = self.obter(ordem_id)
        if ordem is None:
            raise OrdemError("Ordem não encontrada.")

        proximo = PROXIMO_PASSO.get(ordem.status)
        if proximo is None:
            raise OrdemError(f"A ordem {ordem.numero} já foi finalizada.")

        # sair de "aguardando aprovacao" e uma decisao do cliente, nao do balcao
        if ordem.status == AGUARDANDO:
            raise OrdemError(
                "Registre quem aprovou o orçamento para começar o serviço."
            )
        if proximo == ENTREGUE:
            return self.entregar(ordem_id, observacao=observacao)
        return self.definir_status(ordem_id, proximo, observacao)

    def aprovar(self, ordem_id: int, quem: str, observacao: str = "") -> Ordem:
        """O cliente autorizou o orcamento: a ordem vai para execucao."""
        quem = quem.strip()
        if not quem:
            raise OrdemError("Informe quem aprovou o orçamento.")

        ordem = self.obter(ordem_id)
        if ordem is None:
            raise OrdemError("Ordem não encontrada.")
        if ordem.status in (ENTREGUE, CANCELADA):
            raise OrdemError(f"A ordem {ordem.numero} já foi finalizada.")

        self.db.execute(
            "UPDATE ordens SET aprovado_em = ?, aprovado_por = ? WHERE id = ?",
            (date.today().isoformat(), quem, ordem_id),
        )
        recado = f"Orçamento de {fmt.moeda(ordem.total)} aprovado por {quem}"
        if observacao.strip():
            recado = f"{recado}. {observacao.strip()}"
        return self.definir_status(ordem_id, ANDAMENTO, recado)

    def entregar(self, ordem_id: int, quem: str = "", observacao: str = "") -> Ordem:
        """Entrega o servico. E daqui que a garantia comeca a contar."""
        ordem = self.obter(ordem_id)
        if ordem is None:
            raise OrdemError("Ordem não encontrada.")
        if ordem.status != CONCLUIDA:
            raise OrdemError(
                f"A ordem {ordem.numero} não está concluída. "
                "Não se entrega o que ainda não ficou pronto."
            )

        hoje = date.today().isoformat()
        self.db.execute(
            "UPDATE ordens SET entregue_em = ?, status = ? WHERE id = ?",
            (hoje, ENTREGUE, ordem_id),
        )
        recado = f"Entregue para {quem.strip()}" if quem.strip() else "Entregue"
        if observacao.strip():
            recado = f"{recado}. {observacao.strip()}"
        self.registrar_evento(ordem_id, ENTREGUE, recado)

        entregue = self.obter(ordem_id)
        entregue.avisos = self._baixar_pecas(ordem)
        return entregue

    def _baixar_pecas(self, ordem: Ordem) -> list[str]:
        """Tira do Estoque os materiais que sairam com o servico.

        QUANDO: na entrega. Enquanto a ordem esta no quadro o material ainda e
        da casa; quando o servico e entregue, ele foi embora.

        NUNCA DERRUBA A ENTREGA: o servico ja foi entregue. Saldo errado
        no cadastro vira recado para conferir depois, nao motivo para segurar
        o cliente no balcao. E a marca `baixa_estoque` garante que entregar de
        novo (ou reabrir e entregar) nao tire a mesma peca duas vezes.
        """
        if self.catalogo is None:
            return []
        ja_feita = self.db.query_one(
            "SELECT baixa_estoque FROM ordens WHERE id = ?", (ordem.id,)
        )
        if ja_feita is not None and str(ja_feita["baixa_estoque"] or "").strip():
            return []

        avisos: list[str] = []
        baixou = False
        for item in ordem.itens:
            if not item.do_estoque:
                continue
            try:
                self.catalogo.baixar(
                    item.produto_id,
                    item.quantidade,
                    documento=ordem.numero,
                    motivo=f"Ordem {ordem.numero}",
                )
                baixou = True
            except Exception as erro:  # noqa: BLE001 - o estoque nao derruba a entrega
                avisos.append(f"{item.descricao}: não foi possível dar baixa ({erro})")
        if baixou:
            self.db.execute(
                "UPDATE ordens SET baixa_estoque = ? WHERE id = ?",
                (date.today().isoformat(), ordem.id),
            )
        return avisos

    def cancelar(self, ordem_id: int, motivo: str) -> Ordem:
        motivo = motivo.strip()
        if not motivo:
            raise OrdemError("Informe o motivo do cancelamento.")
        ordem = self.obter(ordem_id)
        if ordem is None:
            raise OrdemError("Ordem não encontrada.")
        if ordem.status == CANCELADA:
            raise OrdemError(f"A ordem {ordem.numero} já está cancelada.")
        return self.definir_status(ordem_id, CANCELADA, f"Cancelada: {motivo}")

    def reabrir(self, ordem_id: int, motivo: str = "") -> Ordem:
        """Cliente voltou: a ordem volta para o quadro, sem perder o passado."""
        ordem = self.obter(ordem_id)
        if ordem is None:
            raise OrdemError("Ordem não encontrada.")
        if ordem.aberta:
            raise OrdemError(f"A ordem {ordem.numero} já está em andamento.")
        recado = f"Reaberta: {motivo.strip()}" if motivo.strip() else "Reaberta"
        return self.definir_status(ordem_id, ANDAMENTO, recado)
