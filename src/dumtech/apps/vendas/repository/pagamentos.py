"""Pagamento da venda: varias formas na mesma compra, e o troco.

Regra do balcao: a soma dos pagamentos tem que fechar o total da venda, nem
mais nem menos. Troco nao e pagamento a mais - e a diferenca entre o que a
pessoa entregou em dinheiro (`recebido`) e o que aquela linha vale (`valor`).
Cartao e Pix nao dao troco.
"""

from __future__ import annotations

from ....ui import format as fmt
from ..models import (
    CONCLUIDA,
    DINHEIRO,
    PARCELADO,
    PENDENTE,
    QUITADA_NO_FINANCEIRO,
    Pagamento,
    Venda,
    VendaError,
    hoje_iso,
)
from .comum import CENTAVO, agora, dinheiro


class PagamentosMixin:
    """Parte do VendasRepository que recebe o dinheiro."""

    # ------------------------------------------------------------------ leitura
    def pagamentos_de(self, venda_id: int) -> list[Pagamento]:
        return [
            Pagamento.from_row(row)
            for row in self.db.query(
                "SELECT * FROM pagamentos WHERE venda_id = ? ORDER BY id", (venda_id,)
            )
        ]

    # -------------------------------------------------------------------- conta
    @staticmethod
    def troco_de(pagamentos: list[Pagamento]) -> float:
        """O que volta para o cliente: so sai das linhas em dinheiro."""
        return dinheiro(
            sum(max(p.recebido - p.valor, 0.0) for p in pagamentos if p.em_dinheiro)
        )

    @staticmethod
    def conferir_pagamento(total: float, pagamentos: list[Pagamento]) -> None:
        """Levanta VendaError se o pagamento nao fecha a conta."""
        linhas = [p for p in pagamentos if dinheiro(p.valor) > 0]
        if not linhas:
            raise VendaError("Informe como esta venda foi paga.")
        if sum(p.parcelado for p in linhas) > 1:
            raise VendaError("Uma venda só pode ter uma linha parcelada.")
        # a parte que sobra do parcelado entra como paga na hora: prazo nao foi
        if any(p.parcelado for p in linhas) and any(
            p.forma.strip().lower() == "prazo" for p in linhas
        ):
            raise VendaError("Parcelado não combina com Prazo: inclua o valor nas parcelas.")

        for pagamento in linhas:
            if not pagamento.forma.strip():
                raise VendaError("Toda linha de pagamento precisa de uma forma.")
            # digitado onde a forma nao e oferecida, viraria pagamento a vista
            if (pagamento.forma.strip().casefold() == PARCELADO.casefold()
                    and not pagamento.parcelado):
                raise VendaError(
                    "Parcelado é escolhido ao lançar a venda, com o número de parcelas."
                )
            if not pagamento.em_dinheiro and pagamento.recebido > pagamento.valor + CENTAVO:
                raise VendaError(
                    f"{pagamento.forma} não dá troco: o valor recebido não pode "
                    "passar do valor pago."
                )
            if pagamento.em_dinheiro and pagamento.recebido + CENTAVO < pagamento.valor:
                raise VendaError(
                    "O dinheiro recebido não cobre o valor lançado em dinheiro."
                )

        pago = dinheiro(sum(p.valor for p in linhas))
        total = dinheiro(total)
        if pago + CENTAVO < total:
            raise VendaError(f"Falta receber {fmt.moeda(total - pago)}.")
        if pago > total + CENTAVO:
            raise VendaError(
                f"O pagamento passou do total em {fmt.moeda(pago - total)}. "
                "Troco sai do campo Recebido, não do valor da forma."
            )

    # ------------------------------------------------------------------ escrita
    def gravar_pagamentos(self, venda_id: int, pagamentos: list[Pagamento]) -> None:
        momento = agora()
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM pagamentos WHERE venda_id = ?", (venda_id,))
            for pagamento in pagamentos:
                if dinheiro(pagamento.valor) <= 0:
                    continue
                conn.execute(
                    """
                    INSERT INTO pagamentos (venda_id, forma, valor, recebido, parcelas,
                                            criado_em)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        venda_id,
                        pagamento.forma.strip(),
                        dinheiro(pagamento.valor),
                        dinheiro(pagamento.recebido),
                        int(pagamento.parcelas or 0),
                        momento,
                    ),
                )

    def finalizar(self, venda: Venda, pagamentos: list[Pagamento]) -> Venda:
        """O caminho do balcao: fecha a venda, recebe e da baixa no estoque.

        Devolve a venda gravada. Se o estoque recusar alguma baixa, a venda
        continua gravada e o recado fica em `venda.avisos`.
        """
        if not venda.numero.strip():
            venda.numero = self.proximo_numero()
        self.conferir_pagamento(venda.total, pagamentos)

        venda.pagamentos = [p for p in pagamentos if dinheiro(p.valor) > 0]
        venda.troco = self.troco_de(venda.pagamentos)
        # venda a prazo nao entrou na gaveta: fica pendente ate o cliente pagar
        venda.status = PENDENTE if venda.a_prazo else CONCLUIDA

        caixa = self.caixa_aberto()
        venda.caixa_id = caixa.id if caixa is not None else 0

        self.salvar(venda)
        venda.avisos = self._baixar_uma_vez(venda)
        return venda

    def receber_pendente(
        self, venda_id: int, pagamentos: list[Pagamento],
        gaveta: bool = True, quitada_por: str = "",
    ) -> Venda:
        """Cliente voltou para pagar a venda a prazo.

        `gaveta=False` e para acerto de conta que ja foi recebida faz tempo: o
        dinheiro nao esta entrando agora, entao o caixa de hoje nao o conta.
        """
        venda = self.obter(venda_id)
        if venda is None:
            raise VendaError("Venda não encontrada.")
        if venda.status != PENDENTE:
            raise VendaError(f"A venda {venda.numero} não está pendente.")

        self.conferir_pagamento(venda.total, pagamentos)
        venda.pagamentos = [p for p in pagamentos if dinheiro(p.valor) > 0]
        venda.troco = self.troco_de(venda.pagamentos)
        venda.status = CONCLUIDA
        venda.quitada_por = quitada_por
        # sem caixa aberto, fica sem caixa: o da venda ja pode ter sido fechado
        caixa = self.caixa_aberto() if gaveta else None
        venda.caixa_id = caixa.id if caixa is not None else 0
        salva = self.salvar(venda)
        # a venda que veio do Orcamento ainda nao tirou nada do estoque: sai
        # agora. A do balcao a prazo ja tirou e nao repete.
        salva.avisos = self._baixar_uma_vez(salva)
        return salva

    def lancar(self, venda: Venda) -> Venda:
        """O caminho do "Lancar venda": grava e, se ja esta paga, baixa o estoque.

        Venda pendente nao tira nada agora - sai quando o cliente pagar, em
        `receber_pendente`, igual a que vem da proposta. Salvar de novo a mesma
        venda nao baixa outra vez. A venda paga hoje com caixa aberto entra
        nele, como a do balcao; a lancada com data passada nao passou por ele.
        """
        if venda.status == CONCLUIDA and not venda.caixa_id and venda.data == hoje_iso():
            caixa = self.caixa_aberto()
            venda.caixa_id = caixa.id if caixa is not None else 0
        salva = self.salvar(venda)
        salva.avisos = self._baixar_uma_vez(salva) if salva.status == CONCLUIDA else []
        return salva

    def alterar_pendente(self, venda: Venda) -> Venda:
        """Venda ainda nao paga pode mudar; o que ja saiu do estoque acompanha."""
        antes = self.obter(venda.id)
        if antes is None:
            raise VendaError("Venda não encontrada.")
        if antes.status != PENDENTE:
            raise VendaError(f"A venda {antes.numero} já foi paga e não pode mudar de itens.")
        ja_saiu = self._deu_baixa(venda.id)
        salva = self.lancar(venda)
        if ja_saiu:
            salva.avisos = self._acertar_estoque(antes, salva)
        return salva

    def desfazer_quitacao(self, venda_id: int) -> Venda | None:
        """A baixa foi desfeita no Financeiro: a venda volta a esperar pagamento.

        So a que foi fechada por la. A que foi paga no balcao teve o dinheiro na
        gaveta, e o que se desfaz na conta nao tira nota nenhuma de la. O
        estoque fica como esta: a mercadoria ja foi embora.
        """
        venda = self.obter(venda_id)
        if venda is None or venda.quitada_por != QUITADA_NO_FINANCEIRO:
            return None
        venda.status = PENDENTE
        venda.quitada_por = ""
        venda.caixa_id = 0
        venda.troco = 0.0
        venda.pagamentos = []
        return self.salvar(venda)

    def _baixar_uma_vez(self, venda: Venda) -> list[str]:
        """Da baixa no estoque se esta venda ainda nao deu. Anota que deu."""
        if self._deu_baixa(venda.id):
            return []
        avisos = self._baixar_do_estoque(venda)
        if self.catalogo is not None:
            self.db.execute("UPDATE vendas SET baixa_estoque = ? WHERE id = ?",
                            (agora(), venda.id))
        return avisos


#: usado pela interface para montar a linha padrao (tudo em dinheiro)
def pagamento_unico(
    forma: str, valor: float, recebido: float = 0.0, parcelas: int = 0
) -> Pagamento:
    return Pagamento(
        forma=forma or DINHEIRO,
        valor=dinheiro(valor),
        recebido=dinheiro(recebido or valor),
        parcelas=parcelas,
    )
