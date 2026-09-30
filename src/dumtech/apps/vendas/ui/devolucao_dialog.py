"""Devolucao: o cliente voltou com parte (ou tudo) da compra.

Cada item da venda tem o seu campo "devolver". O que ja voltou antes aparece,
para ninguem devolver duas vezes a mesma peca.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from ....ui import format as fmt
from ....ui.theme import Space, apply_window_theme, palette_for
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import label, repolish, separator, tone_label
from ....ui.widgets.table import DIREITA, DataTable

from ..models import Devolucao, Venda, VendaError, quantidade_texto
from ..repository import VendasRepository

COLUNAS = ["Item", "Vendido", "Ja devolvido", "Devolver"]


class DevolucaoDialog(QDialog):
    """Escolhe o que volta e quanto o cliente recebe de volta."""

    def __init__(
        self,
        repository: VendasRepository,
        venda: Venda,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.venda = venda
        self.devolucao: Devolucao | None = None
        self._campos: list[tuple[int, QDoubleSpinBox, float]] = []

        self.setWindowTitle("Devolucao")
        self.setModal(True)
        self.setMinimumWidth(640)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)

        cabecalho = QVBoxLayout()
        cabecalho.setSpacing(2)
        cabecalho.addWidget(label(f"Devolucao da venda {venda.numero}", "section"))
        cabecalho.addWidget(
            label(
                f"{venda.cliente or 'Consumidor'}  ·  {fmt.data(venda.data)}"
                f"  ·  total {fmt.moeda(venda.total)}",
                "muted",
            )
        )
        raiz.addLayout(cabecalho)
        raiz.addWidget(separator())

        self.tabela = DataTable(COLUNAS)
        raiz.addWidget(self.tabela, 1)
        self._montar_itens()

        self.motivo = form.texto("", "Ex.: produto com defeito")
        raiz.addWidget(form.campo("Motivo", self.motivo))

        rodape = QHBoxLayout()
        rodape.addWidget(label("Valor a devolver", "field"))
        rodape.addStretch(1)
        self.total = tone_label(fmt.moeda(0), "warning", "cardTitle")
        rodape.addWidget(self.total)
        raiz.addLayout(rodape)

        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        raiz.addWidget(self.aviso)
        raiz.addLayout(self._botoes())

        apply_window_theme(self, palette_for(parent))
        self._recalcular()

    # ------------------------------------------------------------------ tela
    def _montar_itens(self) -> None:
        linhas = []
        for item in self.venda.itens:
            linhas.append([
                self.tabela.cell(item.descricao, bold=True),
                self.tabela.cell(item.quantidade_texto, DIREITA),
                self.tabela.cell(
                    quantidade_texto(item.devolvido, item.unidade, item.casas), DIREITA
                ),
                self.tabela.cell(""),
            ])
        self.tabela.fill(linhas, {1: 130, 2: 130, 3: 130})

        for indice, item in enumerate(self.venda.itens):
            campo = QDoubleSpinBox()
            campo.setDecimals(item.casas)
            campo.setRange(0, item.restante)
            campo.setValue(0)
            campo.setEnabled(item.restante > 0)
            campo.valueChanged.connect(self._recalcular)
            self.tabela.setCellWidget(indice, 3, campo)
            self._campos.append((item.id, campo, item.valor_unitario))

    def _botoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.addStretch(1)

        tudo = Button("Devolver tudo", "refresh", "ghost")
        tudo.clicked.connect(self._marcar_tudo)
        linha.addWidget(tudo)

        cancelar = Button("Cancelar")
        cancelar.clicked.connect(self.reject)
        linha.addWidget(cancelar)

        self.botao_confirmar = Button("Confirmar devolucao", "check", "primary")
        self.botao_confirmar.setDefault(True)
        self.botao_confirmar.clicked.connect(self._confirmar)
        linha.addWidget(self.botao_confirmar)
        return linha

    def _marcar_tudo(self) -> None:
        for _, campo, _ in self._campos:
            campo.setValue(campo.maximum())

    def _recalcular(self) -> None:
        bruto = sum(campo.value() * valor for _, campo, valor in self._campos)
        # o desconto da venda vale para o que volta tambem
        fator = (self.venda.total / self.venda.subtotal) if self.venda.subtotal else 1.0
        self._total = round(bruto * fator, 2)
        self.total.setText(fmt.moeda(self._total))
        self.botao_confirmar.setEnabled(self._total > 0)

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------ acao
    def _confirmar(self) -> None:
        linhas = [(item_id, campo.value()) for item_id, campo, _ in self._campos]
        try:
            self.devolucao = self.repository.devolver(
                self.venda.id, linhas, self.motivo.text()
            )
        except VendaError as erro:
            self._dizer(str(erro), "danger")
            return
        self.accept()
