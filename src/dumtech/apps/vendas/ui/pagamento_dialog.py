"""Recebimento: uma ou varias formas na mesma venda, e o troco.

Este dialogo e o unico lugar do sistema onde alguem esta com a fila esperando.
Ele abre com a linha em dinheiro ja preenchida com o total e o foco em
"Recebido": digitar 200 e apertar Enter duas vezes fecha a venda.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ....core.pagamentos import formas_do_balcao
from ....ui import format as fmt
from ....ui.theme import Space, apply_window_theme, palette_for
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, label, repolish, separator, tone_label
from ....ui.widgets.painel_pix import PainelPix, destino_pix
from ....ui.widgets.table import DIREITA, DataTable
from ..models import DINHEIRO, PIX, Pagamento, VendaError
from ..repository.comum import CENTAVO, dinheiro

#: lado do QR na tela. Cabe no dialogo e o celular le a 40cm sem esforco.


class PagamentoDialog(QDialog):
    """Recebe o pagamento de uma venda ja montada."""

    def __init__(
        self,
        total: float,
        titulo: str = "",
        conferir=None,
        parent: QWidget | None = None,
        empresa=None,
    ) -> None:
        super().__init__(parent)
        self.total = dinheiro(total)
        #: quem valida (o repositorio); injetado para o dialogo nao conhecer regra
        self._conferir = conferir
        #: de onde sai a chave Pix; None quando o dialogo roda sem Hub
        self.empresa = empresa
        self.pagamentos: list[Pagamento] = []

        self.setWindowTitle("Receber")
        self.setModal(True)
        self.setMinimumWidth(560)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)

        cabecalho = QVBoxLayout()
        cabecalho.setSpacing(2)
        cabecalho.addWidget(label("Receber", "section"))
        cabecalho.addWidget(label(titulo or "Pagamento da venda", "muted"))
        raiz.addLayout(cabecalho)

        raiz.addWidget(self._painel_total())
        raiz.addWidget(separator())
        raiz.addWidget(self._linha_lancamento())

        raiz.addWidget(self._painel_pix())

        self.tabela = DataTable(["Forma", "Valor", "Recebido"])
        self.tabela.setMaximumHeight(150)
        self.tabela.itemSelectionChanged.connect(self._atualizar_acoes)
        raiz.addWidget(self.tabela)

        raiz.addLayout(self._rodape())
        raiz.addWidget(separator())
        raiz.addLayout(self._botoes())

        apply_window_theme(self, palette_for(parent))
        self._atualizar()
        self.recebido.setFocus()
        self.recebido.selectAll()

    # ------------------------------------------------------------------ pedacos
    def _painel_total(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.addWidget(label("Total da venda", "muted"))
        linha.addStretch(1)
        self.rotulo_total = tone_label(fmt.moeda(self.total), "accent", "metric")
        linha.addWidget(self.rotulo_total)
        return caixa

    def _linha_lancamento(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(Space.md)

        self.forma = QComboBox()
        self.forma.setEditable(True)
        # so as formas liberadas em Configuracoes > Pagamentos
        self.forma.addItems(formas_do_balcao(getattr(self.empresa, "formas_ocultas", ())))
        self.forma.setCurrentText(DINHEIRO)
        self.forma.currentTextChanged.connect(self._forma_mudou)
        linha.addWidget(form.campo("Forma", self.forma), 3)

        self.valor = form.dinheiro(self.total)
        self.valor.valueChanged.connect(self._valor_mudou)
        linha.addWidget(form.campo("Valor", self.valor), 2)

        self.recebido = form.dinheiro(self.total)
        linha.addWidget(form.campo("Recebido", self.recebido), 2)

        self.botao_lancar = Button("Lançar", "plus")
        self.botao_lancar.clicked.connect(self._lancar)
        linha.addWidget(form.campo(" ", self.botao_lancar), 1)
        return caixa

    def _rodape(self) -> QHBoxLayout:
        rodape = QHBoxLayout()
        rodape.setSpacing(Space.xl)

        faltando = QVBoxLayout()
        faltando.setSpacing(1)
        faltando.addWidget(label("Falta receber", "field"))
        self.rotulo_falta = tone_label(fmt.moeda(self.total), "warning", "cardTitle")
        faltando.addWidget(self.rotulo_falta)
        rodape.addLayout(faltando)

        troco = QVBoxLayout()
        troco.setSpacing(1)
        troco.addWidget(label("Troco", "field"))
        self.rotulo_troco = tone_label(fmt.moeda(0), "success", "cardTitle")
        troco.addWidget(self.rotulo_troco)
        rodape.addLayout(troco)

        rodape.addStretch(1)
        self.botao_remover = Button("Remover linha", "trash", "ghost")
        self.botao_remover.clicked.connect(self._remover)
        rodape.addWidget(self.botao_remover)
        return rodape

    def _botoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        linha.addWidget(self.aviso, 1)

        cancelar = Button("Cancelar")
        cancelar.setAutoDefault(False)
        cancelar.clicked.connect(self.reject)
        linha.addWidget(cancelar)

        self.botao_receber = Button("Receber", "check", "success")
        self.botao_receber.setMinimumHeight(38)
        self.botao_receber.setDefault(True)
        self.botao_receber.clicked.connect(self._confirmar)
        linha.addWidget(self.botao_receber)
        return linha

    def _painel_pix(self) -> QWidget:
        """O QR Code que o cliente aponta o celular.

        Fica escondido ate alguem escolher Pix: e uma forma entre seis, e o
        dialogo do balcao nao pode ficar maior por causa de quem paga em
        dinheiro. O desenho em si e o painel da plataforma, o mesmo que o
        Financeiro e as Ordens usam.
        """
        self.painel_pix = PainelPix(self.empresa)
        # nomes antigos, mesma coisa: o resto do dialogo (e os testes) leem daqui
        self.imagem_pix = self.painel_pix.imagem
        self.texto_pix = self.painel_pix.texto
        self.botao_copiar_pix = self.painel_pix.botao_copiar
        self.recado_pix = self.painel_pix.recado
        self.painel_pix.setVisible(False)
        return self.painel_pix

    @property
    def payload_pix(self) -> str:
        """O copia e cola de agora - vazio quando nao ha o que cobrar."""
        return self.painel_pix.payload

    def _atualizar_pix(self) -> None:
        """Refaz o QR para o valor que esta no campo agora."""
        if not self._em_pix():
            self.painel_pix.setVisible(False)
            return
        self.painel_pix.setVisible(True)
        self.painel_pix.atualizar(self.valor.value())

    def _copiar_pix(self) -> None:
        if self.painel_pix.copiar():
            self._dizer("Código Pix copiado - cole no aplicativo do cliente.", "success")

    def _em_pix(self) -> bool:
        return self.forma.currentText().strip().casefold() == PIX.casefold()

    # -------------------------------------------------------------------- conta
    @property
    def pago(self) -> float:
        return dinheiro(sum(p.valor for p in self.pagamentos))

    @property
    def falta(self) -> float:
        return dinheiro(max(self.total - self.pago, 0.0))

    @property
    def troco(self) -> float:
        return dinheiro(
            sum(max(p.recebido - p.valor, 0.0) for p in self.pagamentos if p.em_dinheiro)
        )

    def _em_dinheiro(self) -> bool:
        return self.forma.currentText().strip() == DINHEIRO

    # ------------------------------------------------------------------- acoes
    def _forma_mudou(self, _texto: str = "") -> None:
        # so dinheiro tem troco: nas outras formas o recebido acompanha o valor
        self.recebido.setEnabled(self._em_dinheiro())
        if not self._em_dinheiro():
            self.recebido.setValue(self.valor.value())
        self._atualizar_pix()

    def _valor_mudou(self, valor: float) -> None:
        if not self._em_dinheiro() or self.recebido.value() < valor:
            self.recebido.setValue(valor)
        self._atualizar_pix()

    def _lancar(self) -> None:
        valor = dinheiro(self.valor.value())
        if valor <= 0:
            self._dizer("Informe um valor maior que zero.", "danger")
            return
        recebido = dinheiro(self.recebido.value()) if self._em_dinheiro() else valor
        if recebido < valor:
            self._dizer("O recebido não cobre o valor lançado.", "danger")
            return

        self.pagamentos.append(
            Pagamento(forma=self.forma.currentText().strip(), valor=valor, recebido=recebido)
        )
        self._atualizar()

    def _remover(self) -> None:
        linha = self.tabela.currentRow()
        if 0 <= linha < len(self.pagamentos):
            self.pagamentos.pop(linha)
            self._atualizar()

    def _confirmar(self) -> None:
        try:
            if self._conferir is not None:
                self._conferir(self.total, self.pagamentos)
        except VendaError as erro:
            self._dizer(str(erro), "danger")
            return
        self.accept()

    # ------------------------------------------------------------------- tela
    def _atualizar(self) -> None:
        self.tabela.fill(
            [
                [
                    self.tabela.cell(p.forma),
                    self.tabela.cell(fmt.moeda(p.valor), DIREITA, bold=True),
                    self.tabela.cell(
                        fmt.moeda(p.recebido) if p.em_dinheiro else "-", DIREITA
                    ),
                ]
                for p in self.pagamentos
            ],
            {1: 140, 2: 140},
        )
        self.rotulo_falta.setText(fmt.moeda(self.falta))
        self.rotulo_falta.setProperty("tone", "warning" if self.falta > CENTAVO else "muted")
        repolish(self.rotulo_falta)
        self.rotulo_troco.setText(fmt.moeda(self.troco))

        # a proxima linha ja vem preenchida com o que ainda falta
        self.valor.setValue(self.falta)
        self._forma_mudou()
        self._dizer("")
        self._atualizar_acoes()

    def _atualizar_acoes(self) -> None:
        fechou = self.falta <= CENTAVO
        self.botao_receber.setEnabled(fechou and bool(self.pagamentos))
        self.botao_lancar.setEnabled(not fechou)
        self.botao_remover.setEnabled(0 <= self.tabela.currentRow() < len(self.pagamentos))

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ---------------------------------------------------------------- teclado
    def keyPressEvent(self, event) -> None:  # noqa: N802 (assinatura do Qt)
        """Enter lanca a linha enquanto falta dinheiro; depois disso, recebe."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.falta > CENTAVO:
                self._lancar()
                return
        super().keyPressEvent(event)


