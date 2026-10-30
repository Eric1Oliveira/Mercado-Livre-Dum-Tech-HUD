"""As perguntas que a esteira faz: quem aprovou, quem retirou, e por que parou."""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import QWidget

from ....core.pagamentos import PIX, formas_do_balcao
from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.form import FormDialog
from ....ui.widgets.painel_pix import PainelPix
from ..models import Ordem, OrdemError
from ..repository import OrdensRepository


class AprovacaoDialog(FormDialog):
    """Sair de 'aguardando aprovacao' e uma decisao do cliente, nao do balcao."""

    def __init__(
        self,
        repository: OrdensRepository,
        ordem: Ordem,
        parent: QWidget | None = None,
    ) -> None:
        self.repository = repository
        self.ordem = ordem
        super().__init__(
            f"Aprovação da {ordem.numero}",
            "  ·  ".join(p for p in (ordem.assunto, ordem.cliente) if p),
            parent,
            largura=500,
        )

        self.quem = form.sugestao(ordem.cliente, "Quem autorizou o serviço", [ordem.cliente])
        self.add_row("Aprovado por", self.quem)

        self.observacao = form.texto("", "Ex.: autorizou por telefone")
        self.add_row("Observação", self.observacao)

        self.add_note(
            f"Orçamento de {fmt.moeda(ordem.total)}. A aprovação fica gravada com a "
            "data e sai no comprovante de entrega."
        )
        self.quem.setFocus()
        self.quem.selectAll()

    def salvar(self) -> None:
        self.repository.aprovar(self.ordem.id, self.quem.text(), self.observacao.text())


class EntregaDialog(FormDialog):
    """Entrega o servico - e registra o pagamento na mesma janela.

    Antes, entregar e lancar no Financeiro eram dois cliques em lugares
    diferentes, e o segundo era esquecido. Agora, com o Financeiro na casa, a
    entrega pergunta como o cliente pagou:

        pagou agora        -> entra no caixa como recebido (conta ja quitada)
        vai pagar depois   -> nasce conta a receber com o vencimento escolhido

    Sem o Financeiro a janela e a de sempre. E daqui que a garantia comeca.
    """

    PAGOU = "agora"
    DEPOIS = "depois"

    def __init__(
        self,
        repository: OrdensRepository,
        ordem: Ordem,
        parent: QWidget | None = None,
        empresa=None,
        contas=None,
    ) -> None:
        self.repository = repository
        self.ordem = ordem
        #: chave Pix da loja: a hora de entregar e a hora de receber
        self.empresa = empresa
        #: ponte com o Financeiro; None quando a licenca nao o libera
        self.contas = contas
        #: o que aconteceu com o dinheiro, para a tela contar depois
        self.recado_financeiro = ""
        super().__init__(
            f"Entrega da {ordem.numero}",
            "  ·  ".join(p for p in (ordem.assunto, ordem.cliente) if p),
            parent,
            largura=520,
        )

        self.quem = form.sugestao(ordem.cliente, "Quem está retirando", [ordem.cliente])
        self.add_row("Retirado por", self.quem)

        self.observacao = form.texto("", "Opcional")
        self.add_row("Observação", self.observacao)

        # --- o dinheiro (so faz sentido com valor e com o Financeiro ligado)
        self.cobrar = ordem.total > 0 and contas is not None
        self.situacao = self.forma = self.vencimento = None
        if self.cobrar:
            self.situacao = form.escolha(
                [("Pagou agora", self.PAGOU), ("Paga depois", self.DEPOIS)], self.PAGOU)
            self.forma = form.escolha(
                [(f, f) for f in formas_do_balcao() if f.lower() != "prazo"], PIX
            )
            self.rotulo_forma = form.linha(self.forma)
            self.add_row("Pagamento", self.situacao)
            self.add_row("Forma", self.rotulo_forma)
            self.vencimento = form.data()
            self.linha_vencimento = form.linha(self.vencimento)
            self.add_row("Vencimento", self.linha_vencimento)
            self.situacao.currentIndexChanged.connect(self._pagamento_mudou)
            self.forma.currentIndexChanged.connect(self._pagamento_mudou)

        garantia = (
            f"Garantia de {ordem.garantia_dias} dias a partir de hoje."
            if ordem.garantia_dias
            else "Este serviço sai sem garantia."
        )
        self.add_note(f"Total do serviço: {fmt.moeda(ordem.total)}. {garantia}")

        # o cliente esta na sua frente recebendo o servico: e agora que paga
        self.painel_pix = None
        if ordem.total > 0:
            self.painel_pix = PainelPix(self.empresa)
            self.painel_pix.atualizar(ordem.total)
            self.extras.addWidget(self.painel_pix)
        self._pagamento_mudou()

        self.quem.setFocus()
        self.quem.selectAll()

    def _pagamento_mudou(self) -> None:
        """Vencimento so para quem vai pagar depois; QR so para quem paga em Pix agora."""
        if not self.cobrar:
            return
        pagou = self.situacao.currentData() == self.PAGOU
        # uma linha ou outra: forma para quem pagou, vencimento para quem vai pagar
        for campo, mostrar in ((self.linha_vencimento, not pagou), (self.rotulo_forma, pagou)):
            rotulo = self.form.labelForField(campo)
            for widget in (campo, rotulo):
                if widget is not None:
                    widget.setVisible(mostrar)
        if self.painel_pix is not None:
            self.painel_pix.setVisible(pagou and self.forma.currentData() == PIX)

    def salvar(self) -> None:
        self.repository.entregar(self.ordem.id, self.quem.text(), self.observacao.text())
        if self.cobrar:
            self.recado_financeiro = self._lancar()

    def _lancar(self) -> str:
        """Leva o valor ao Financeiro. Nunca desfaz a entrega se falhar."""
        from ....core.contas import AReceber

        pagou = self.situacao.currentData() == self.PAGOU
        if self.contas.ja_lancado(self.ordem.numero):
            # a ordem de contrato recorrente ja nasce com a conta: pagou na
            # entrega, e essa conta que fecha - senao o Financeiro seguia cobrando
            if pagou:
                try:
                    if self.contas.quitar(self.ordem.numero, forma=self.forma.currentText()):
                        return (f"  Recebido em {self.forma.currentText()}: "
                                "a conta do Financeiro foi quitada.")
                except Exception as erro:  # noqa: BLE001 - o aparelho ja saiu pela porta
                    return f"  Não consegui quitar no Financeiro ({erro}) - quite por lá."
            return "  A conta desta ordem já existia no Financeiro."
        hoje = date.today().isoformat()
        try:
            self.contas.lancar(AReceber(
                descricao=f"Ordem {self.ordem.numero} - {self.ordem.equipamento or self.ordem.cliente}",
                valor=self.ordem.total,
                vencimento=hoje if pagou else form.iso_da_data(self.vencimento),
                cliente=self.ordem.cliente, categoria="Serviços",
                documento=self.ordem.numero,
            ))
            if pagou:
                self.contas.quitar(self.ordem.numero)
        except Exception as erro:  # noqa: BLE001 - o aparelho ja saiu pela porta
            return f"  Não consegui lançar no Financeiro ({erro}) - use o botão Financeiro."
        if pagou:
            return f"  Recebido em {self.forma.currentText()}: já entrou no caixa do Financeiro."
        return f"  Conta a receber criada para {fmt.data(form.iso_da_data(self.vencimento))}."


class MotivoDialog(FormDialog):
    """Pergunta o porque de algo que nao pode acontecer em silencio."""

    def __init__(
        self,
        titulo: str,
        subtitulo: str = "",
        dica: str = "",
        parent: QWidget | None = None,
    ) -> None:
        self.motivo = ""
        super().__init__(titulo, subtitulo, parent, largura=480)
        self.campo = form.texto("", dica)
        self.add_row("Motivo", self.campo)
        self.campo.setFocus()

    def salvar(self) -> None:
        texto = self.campo.text().strip()
        if not texto:
            raise OrdemError("Informe o motivo.")
        self.motivo = texto
