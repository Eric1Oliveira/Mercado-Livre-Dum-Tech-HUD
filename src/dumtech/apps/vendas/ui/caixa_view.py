"""O caixa do dia: abrir, acompanhar e fechar conferindo a gaveta.

A pergunta que esta tela responde e uma so: **quanto deveria ter na gaveta
agora, e por que?** Por isso a conta aparece linha a linha, e nao como um
numero solto que ninguem consegue conferir.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.theme import Space
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, FaixaDeNumeros, StatCard, label, repolish, separator, tone_label
from ....ui.widgets.comprovante import ComprovanteDialog
from ....ui.widgets.table import DIREITA, DataTable
from ..models import TIPO_SANGRIA, TIPO_SUPRIMENTO, VendaError
from ..recibo import fechamento
from ..repository import VendasRepository
from .caixa_dialogs import AbrirCaixaDialog, FecharCaixaDialog, MovimentoCaixaDialog


class CaixaView(QWidget):
    """Abertura, sangria, suprimento e fechamento do dia."""

    data_changed = Signal()

    def __init__(self, repository: VendasRepository, parent: QWidget | None = None,
                 empresa=None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.empresa = empresa

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        raiz.addLayout(self._cabecalho())
        raiz.addWidget(self._cartoes())

        colunas = QHBoxLayout()
        colunas.setSpacing(Space.lg)
        colunas.addWidget(self._card_conferencia(), 2)
        colunas.addWidget(self._card_movimentos(), 3)
        raiz.addLayout(colunas, 1)

        raiz.addWidget(self._card_historico(), 1)
        self.refresh()

    # -------------------------------------------------------------- cabecalho
    def _cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Caixa", "title"))
        self.subtitulo = label("", "subtitle")
        titulos.addWidget(self.subtitulo)
        linha.addLayout(titulos)
        linha.addStretch(1)

        self.botao_sangria = Button("Sangria", "out")
        self.botao_sangria.clicked.connect(lambda: self._movimento(TIPO_SANGRIA))
        linha.addWidget(self.botao_sangria)

        self.botao_suprimento = Button("Suprimento", "in")
        self.botao_suprimento.clicked.connect(lambda: self._movimento(TIPO_SUPRIMENTO))
        linha.addWidget(self.botao_suprimento)

        self.botao_comprovante = Button("Comprovante", "file")
        self.botao_comprovante.clicked.connect(self._comprovante)
        linha.addWidget(self.botao_comprovante)

        self.botao_principal = Button("Abrir caixa", "money", "primary")
        self.botao_principal.setMinimumHeight(38)
        self.botao_principal.clicked.connect(self._abrir_ou_fechar)
        linha.addWidget(self.botao_principal)
        return linha

    def _cartoes(self) -> FaixaDeNumeros:
        linha = FaixaDeNumeros()
        self.card_gaveta = StatCard("Esperado na gaveta", "R$ 0,00", "money", "accent")
        self.card_vendido = StatCard("Vendido no caixa", "R$ 0,00", "cart", "success")
        self.card_vendas = StatCard("Vendas", "0", "list", "warning")
        for cartao in (self.card_gaveta, self.card_vendido, self.card_vendas):
            linha.add(cartao)
        return linha

    # ---------------------------------------------------------------- paineis
    def _card_conferencia(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Dinheiro na gaveta", "section"))

        self._contas = QVBoxLayout()
        self._contas.setSpacing(0)
        card.body.addLayout(self._contas)
        card.body.addStretch(1)
        return card

    def _card_movimentos(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Sangrias e suprimentos", "section"))
        self.tabela_movimentos = DataTable(["Hora", "Tipo", "Motivo", "Valor"])
        self.tabela_movimentos.set_empty_message(
            "Nenhuma sangria ou suprimento neste caixa."
        )
        card.body.addWidget(self.tabela_movimentos, 1)
        return card

    def _card_historico(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Fechamentos anteriores", "section"))
        self.tabela_caixas = DataTable(
            ["Abertura", "Fechamento", "Abertura R$", "Contado", "Diferença"]
        )
        self.tabela_caixas.set_empty_message("Nenhum caixa fechado ainda.")
        self.tabela_caixas.setMaximumHeight(190)
        card.body.addWidget(self.tabela_caixas)
        return card

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        self.conferencia = self.repository.conferencia()
        caixa = self.conferencia.caixa
        aberto = caixa is not None

        if aberto:
            self.subtitulo.setText(f"Aberto em {fmt.data_hora(caixa.aberto_em)}")
            self.botao_principal.setText("Fechar caixa")
            self.botao_principal.set_icon_name("check")
        else:
            self.subtitulo.setText("Nenhum caixa aberto no momento")
            self.botao_principal.setText("Abrir caixa")
            self.botao_principal.set_icon_name("money")

        for botao in (self.botao_sangria, self.botao_suprimento, self.botao_comprovante):
            botao.setEnabled(aberto)

        self.card_gaveta.set_value(fmt.moeda(self.conferencia.esperado))
        self.card_vendido.set_value(fmt.moeda(self.conferencia.total_vendido))
        self.card_vendas.set_value(
            fmt.numero(self.conferencia.quantidade_vendas),
            self._resumo_formas(),
        )

        self._preencher_contas()
        self._preencher_movimentos()
        self._preencher_historico()

    def _resumo_formas(self) -> str:
        return "   ".join(
            f"{forma}: {fmt.moeda(valor)}" for forma, valor in self.conferencia.por_forma[:2]
        )

    def _preencher_contas(self) -> None:
        while self._contas.count():
            item = self._contas.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        if self.conferencia.caixa is None:
            self._contas.addWidget(
                label("Abra o caixa para acompanhar o dinheiro do dia.", "muted")
            )
            return

        conta = self.conferencia
        linhas = [
            ("Abertura", conta.abertura, "muted"),
            ("Vendas em dinheiro", conta.vendas_dinheiro, "success"),
            ("Trocos", -conta.trocos, "muted"),
            ("Suprimentos", conta.suprimentos, "success"),
            ("Sangrias", -conta.sangrias, "danger"),
        ]
        if conta.devolucoes_dinheiro:
            linhas.append(("Devoluções", -conta.devolucoes_dinheiro, "danger"))

        for titulo, valor, tom in linhas:
            self._contas.addWidget(self._conta(titulo, valor, tom))
        self._contas.addWidget(separator())
        self._contas.addWidget(self._conta("Esperado", conta.esperado, "accent", forte=True))

    @staticmethod
    def _conta(titulo: str, valor: float, tom: str, forte: bool = False) -> QWidget:
        linha = QWidget()
        layout = QHBoxLayout(linha)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.addWidget(label(titulo, "strong" if forte else "body"), 1)
        etiqueta = tone_label(fmt.moeda(valor), tom, "cardTitle" if forte else "strong")
        etiqueta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(etiqueta)
        return linha

    def _preencher_movimentos(self) -> None:
        self.tabela_movimentos.fill(
            [
                [
                    self.tabela_movimentos.cell(fmt.data_hora_curta(m.criado_em)),
                    self.tabela_movimentos.cell(
                        m.tipo_label,
                        tone="danger" if m.tipo == TIPO_SANGRIA else "success",
                    ),
                    self.tabela_movimentos.cell(m.motivo or "-"),
                    self.tabela_movimentos.cell(fmt.moeda(m.valor), DIREITA, bold=True),
                ]
                for m in reversed(self.conferencia.movimentos)
            ],
            {0: 110, 1: 110, 3: 130},
        )

    def _preencher_historico(self) -> None:
        fechados = [c for c in self.repository.listar_caixas(limite=20) if not c.aberto]
        self.tabela_caixas.fill(
            [
                [
                    self.tabela_caixas.cell(fmt.data_hora(c.aberto_em)),
                    self.tabela_caixas.cell(fmt.data_hora(c.fechado_em)),
                    self.tabela_caixas.cell(fmt.moeda(c.valor_abertura), DIREITA),
                    self.tabela_caixas.cell(fmt.moeda(c.contado), DIREITA),
                    self.tabela_caixas.cell(
                        fmt.moeda(c.diferenca),
                        DIREITA,
                        "success" if abs(c.diferenca) < 0.005 else "danger",
                        bold=True,
                    ),
                ]
                for c in fechados
            ],
            {2: 140, 3: 140, 4: 140},
        )

    # ------------------------------------------------------------------- acoes
    def _abrir_ou_fechar(self) -> None:
        if self.conferencia.caixa is None:
            dialogo = AbrirCaixaDialog(self.repository, self)
            if dialogo.exec():
                self.refresh()
                self.data_changed.emit()
            return

        dialogo = FecharCaixaDialog(self.repository, self.conferencia, self)
        if not dialogo.exec():
            return
        resultado = dialogo.resultado
        self.refresh()
        self.data_changed.emit()
        if resultado is not None:
            ComprovanteDialog(
                fechamento(resultado, self.empresa), "Fechamento de caixa", self
            ).exec()

    def _movimento(self, tipo: str) -> None:
        dialogo = MovimentoCaixaDialog(self.repository, tipo, self)
        if dialogo.exec():
            self.refresh()
            self.data_changed.emit()

    def _comprovante(self) -> None:
        try:
            texto = fechamento(self.repository.conferencia(), self.empresa)
        except VendaError as erro:
            self.subtitulo.setText(str(erro))
            repolish(self.subtitulo)
            return
        ComprovanteDialog(texto, "Conferência do caixa", self).exec()
