"""Pagamento da venda: varias formas na mesma compra, e o troco.

Regra do balcao: a soma dos pagamentos tem que fechar o total da venda, nem
mais nem menos. Troco nao e pagamento a mais - e a diferenca entre o que a
pessoa entregou em dinheiro (`recebido`) e o que aquela linha vale (`valor`).
Cartao e Pix nao dao troco.

Regra da venda pendente: o cliente volta e paga tudo ou so uma parte. Cada
parte e uma linha, com a sua forma e o caixa do dia em que entrou; o que
falta fica numa linha "Prazo" ate ele voltar de novo.
"""

from __future__ import annotations

from ....core.pagamentos import forma_canonica
from ....ui import format as fmt
from ..models import (
    CANCELADA,
    CONCLUIDA,
    DINHEIRO,
    PARCELADO,
    PENDENTE,
    PRAZO,
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

    def pagamentos_do_caixa(self, caixa_id: int) -> list[Pagamento]:
        """O dinheiro que entrou neste caixa - de venda que vale (cancelada nao)."""
        return [
            Pagamento.from_row(row)
            for row in self.db.query(
                "SELECT p.* FROM pagamentos p JOIN vendas v ON v.id = p.venda_id"
                " WHERE p.caixa_id = ? AND v.status <> ? ORDER BY p.id",
                (caixa_id, CANCELADA),
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
        if any(p.parcelado for p in linhas) and any(p.a_prazo for p in linhas):
            raise VendaError("Parcelado não combina com Prazo: inclua o valor nas parcelas.")

        for pagamento in linhas:
            PagamentosMixin._conferir_linha(pagamento)

        pago = dinheiro(sum(p.valor for p in linhas))
        total = dinheiro(total)
        if pago + CENTAVO < total:
            raise VendaError(f"Falta receber {fmt.moeda(total - pago)}.")
        if pago > total + CENTAVO:
            raise VendaError(
                f"O pagamento passou do total em {fmt.moeda(pago - total)}. "
                "Troco sai do campo Recebido, não do valor da forma."
            )

    @staticmethod
    def conferir_recebimento(em_aberto: float, pagamentos: list[Pagamento]) -> None:
        """O cliente voltou para pagar: tudo ou uma parte, nunca mais do que deve.

        Levanta VendaError se nao der. O que faltar nao precisa de linha: fica
        em aberto sozinho, na venda e no Financeiro.
        """
        linhas = [p for p in pagamentos if dinheiro(p.valor) > 0]
        if not linhas:
            raise VendaError("Informe quanto o cliente pagou agora.")
        for pagamento in linhas:
            if (pagamento.a_prazo or pagamento.parcelado
                    or pagamento.forma.strip().casefold() == PARCELADO.casefold()):
                raise VendaError(
                    "Aqui entra só o que o cliente pagou agora: o que faltar continua em aberto."
                )
            PagamentosMixin._conferir_linha(pagamento)

        pago = dinheiro(sum(p.valor for p in linhas))
        em_aberto = dinheiro(em_aberto)
        if pago > em_aberto + CENTAVO:
            raise VendaError(
                f"O pagamento passou do que falta ({fmt.moeda(em_aberto)}) em "
                f"{fmt.moeda(pago - em_aberto)}. Troco sai do campo Recebido, não do valor da forma."
            )

    @staticmethod
    def _conferir_linha(pagamento: Pagamento) -> None:
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

    # ------------------------------------------------------------------ escrita
    def gravar_pagamentos(self, venda_id: int, pagamentos: list[Pagamento],
                          caixa_id: int = 0) -> None:
        """Regrava as linhas. A que nao diz o caixa (None) e do caixa da venda."""
        momento = agora()
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM pagamentos WHERE venda_id = ?", (venda_id,))
            for pagamento in pagamentos:
                if dinheiro(pagamento.valor) <= 0:
                    continue
                caixa = int((caixa_id if pagamento.caixa_id is None else pagamento.caixa_id) or 0)
                criado = pagamento.criado_em or momento
                cursor = conn.execute(
                    """
                    INSERT INTO pagamentos (venda_id, forma, valor, recebido, parcelas,
                                            caixa_id, recebido_em, criado_em)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        venda_id,
                        pagamento.forma.strip(),
                        dinheiro(pagamento.valor),
                        dinheiro(pagamento.recebido),
                        int(pagamento.parcelas or 0),
                        caixa,
                        pagamento.recebido_em or "",
                        criado,
                    ),
                )
                # a memoria fica igual ao banco: salvar de novo nao muda de caixa
                pagamento.id = int(cursor.lastrowid)
                pagamento.caixa_id = caixa
                pagamento.criado_em = criado

    def finalizar(self, venda: Venda, pagamentos: list[Pagamento]) -> Venda:
        """O caminho do balcao: fecha a venda, recebe e da baixa no estoque.

        Devolve a venda gravada. Se o estoque recusar alguma baixa, a venda
        continua gravada e o recado fica em `venda.avisos`.
        """
        if not venda.numero.strip():
            venda.numero = self.proximo_numero()
        # "dinheiro" digitado no campo e o Dinheiro: conta na gaveta e da troco
        for pagamento in pagamentos:
            pagamento.forma = forma_canonica(pagamento.forma)
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
        gaveta: bool = True, quitada_por: str = "", quando: str = "",
    ) -> Venda:
        """Cliente voltou para pagar a venda a prazo - tudo ou so uma parte.

        Cada forma vira uma linha no caixa aberto agora: o Pix fica como Pix e
        so o dinheiro conta na gaveta. `gaveta=False` e para acerto de conta
        que ja foi recebida faz tempo: o dinheiro nao esta entrando agora,
        entao o caixa de hoje nao o conta. O que faltar continua pendente,
        numa linha "Prazo". Quitando tudo, a venda conclui.
        """
        venda = self.obter(venda_id)
        if venda is None:
            raise VendaError("Venda não encontrada.")
        if venda.status != PENDENTE:
            raise VendaError(f"A venda {venda.numero} não está pendente.")

        novas = [p for p in pagamentos if dinheiro(p.valor) > 0]
        for pagamento in novas:
            pagamento.forma = forma_canonica(pagamento.forma)
        self.conferir_recebimento(venda.em_aberto, novas)
        # sem caixa aberto, fica sem caixa: o da venda ja pode ter sido fechado
        caixa = self.caixa_aberto() if gaveta else None
        caixa_id = caixa.id if caixa is not None else 0
        dia = (quando or hoje_iso())[:10]
        for pagamento in novas:
            pagamento.caixa_id = caixa_id
            pagamento.recebido_em = dia

        falta = dinheiro(venda.em_aberto - sum(p.valor for p in novas))
        prazo = next((p for p in venda.pagamentos if p.a_prazo), None)
        venda.pagamentos = [p for p in venda.pagamentos if not p.a_prazo] + novas
        if falta > CENTAVO:
            venda.pagamentos.append(self._linha_prazo(venda, falta, prazo))
        else:
            venda.status = CONCLUIDA
            venda.quitada_por = quitada_por
            # a venda fica no caixa em que foi feita (o fechamento dele nao muda
            # depois); a que nasceu fora de caixa (proposta) entra no de agora
            if not venda.caixa_id:
                venda.caixa_id = caixa_id
        venda.troco = self.troco_de(venda.pagamentos)
        salva = self.salvar(venda)
        # a venda que veio do Orcamento ainda nao tirou nada do estoque: sai
        # quando fecha. A do balcao a prazo ja tirou e nao repete.
        salva.avisos = self._baixar_uma_vez(salva) if salva.status == CONCLUIDA else []
        return salva

    def estornar_recebimento(self, venda_id: int, forma: str, valor: float,
                             data: str = "") -> Venda | None:
        """Uma parte recebida foi desfeita no Financeiro: volta a ser devida.

        So mexe no que foi pago DEPOIS da venda (`recebido_em`), e no dia da
        baixa desfeita: o que entrou no balcao, junto com a venda, nao se
        desfaz por la - nem uma parte paga outro dia que tenha o mesmo valor.
        Devolve None quando nao acha a parte.
        """
        venda = self.obter(venda_id)
        if venda is None or venda.status not in (PENDENTE, CONCLUIDA):
            return None
        valor, forma = dinheiro(valor), forma_canonica(forma).casefold()
        depois = [p for p in reversed(venda.pagamentos) if p.recebido_em and not p.a_prazo
                  and (not data or p.recebido_em == data[:10])]
        mesmo_valor = [p for p in depois if abs(dinheiro(p.valor) - valor) < CENTAVO]
        alvo = next((p for p in mesmo_valor if p.forma.casefold() == forma),
                    mesmo_valor[0] if mesmo_valor else None)
        if alvo is None:
            return None

        prazo = next((p for p in venda.pagamentos if p.a_prazo), None)
        venda.pagamentos = [p for p in venda.pagamentos if p is not alvo and not p.a_prazo]
        venda.status = PENDENTE
        venda.quitada_por = ""
        # venda que chegou sem linha nenhuma volta sem linha nenhuma
        if venda.pagamentos or prazo is not None:
            venda.pagamentos.append(self._linha_prazo(venda, venda.em_aberto, prazo))
        venda.troco = self.troco_de(venda.pagamentos)
        return self.salvar(venda)

    @staticmethod
    def _linha_prazo(venda: Venda, valor: float, antes: Pagamento | None) -> Pagamento:
        """O que falta pagar, no caixa onde a venda a prazo foi feita."""
        return Pagamento(
            forma=PRAZO, valor=dinheiro(valor), recebido=dinheiro(valor),
            caixa_id=antes.caixa_id if antes is not None else venda.caixa_id,
            criado_em=antes.criado_em if antes is not None else "",
        )

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
