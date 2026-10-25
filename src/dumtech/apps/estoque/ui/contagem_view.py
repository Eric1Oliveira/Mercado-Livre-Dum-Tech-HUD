"""Contagem fisica do estoque (balanco).

Voce percorre a loja bipando e anotando o que existe de verdade. A folha fica
salva enquanto isso - da para parar no meio e continuar depois. So no fim, em
"Aplicar ajustes", os saldos mudam, e cada divergencia vira um ajuste no
historico.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ....ui import icons
from ....ui.theme import Space, palette_for
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, label, repolish
from ....ui.widgets.table import DIREITA, DataTable
from ..models import EstoqueError, Produto, quantidade_texto
from ..repository import EstoqueRepository

COLUNAS = ["Código", "Produto", "Sistema", "Contado", "Diferença"]


class ContagemView(QWidget):
    """A folha de contagem e o botao que a transforma em ajustes."""

    data_changed = Signal()

    def __init__(self, repository: EstoqueRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self._produto: Produto | None = None
        self._itens = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Contagem", "title"))
        titulos.addWidget(
            label("Confira o estoque real e corrija o que estiver diferente", "subtitle")
        )
        raiz.addLayout(titulos)

        raiz.addWidget(self._formulario())

        self.tabela = DataTable(COLUNAS)
        self.tabela.itemSelectionChanged.connect(self._atualizar_acoes)
        raiz.addWidget(self.tabela, 1)
        raiz.addLayout(self._rodape())

        self.refresh()

    # -------------------------------------------------------------- formulario
    def _formulario(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.setSpacing(Space.sm)
        card.body.addWidget(label("Contar produto", "section"))

        linha = QHBoxLayout()
        linha.setSpacing(Space.md)

        self.bipe = QLineEdit()
        self.bipe.setPlaceholderText("Bipe o código de barras ou digite o código...")
        self._acao_bipe = self.bipe.addAction(
            icons.icon("tag", palette_for(self).accent, 16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.bipe.returnPressed.connect(self._localizar)
        linha.addWidget(form.campo("Produto", self.bipe), 4)

        self.contado = QDoubleSpinBox()
        self.contado.setRange(0, 9_999_999)
        self.contado.setDecimals(0)
        self.contado.setMinimumWidth(120)
        linha.addWidget(form.campo("Quantidade contada", self.contado), 1)

        self.botao_anotar = Button("Anotar", "check", "primary")
        self.botao_anotar.clicked.connect(self._anotar)
        self.botao_anotar.setEnabled(False)
        linha.addWidget(form.campo(" ", self.botao_anotar), 1)
        card.body.addLayout(linha)

        self.encontrado = label("Nenhum produto selecionado", "dim")
        card.body.addWidget(self.encontrado)
        return card


    def _rodape(self) -> QHBoxLayout:
        rodape = QHBoxLayout()
        rodape.setSpacing(Space.md)
        self.aviso = label("", "muted")
        rodape.addWidget(self.aviso, 1)

        self.resumo = label("", "section")
        rodape.addWidget(self.resumo)

        self.botao_remover = Button("Tirar da folha", "trash")
        self.botao_remover.clicked.connect(self._remover)
        rodape.addWidget(self.botao_remover)

        self.botao_cancelar = Button("Cancelar contagem", "close", "ghost")
        self.botao_cancelar.clicked.connect(self._cancelar)
        rodape.addWidget(self.botao_cancelar)

        self.botao_aplicar = Button("Aplicar ajustes", "swap", "success")
        self.botao_aplicar.setMinimumHeight(38)
        self.botao_aplicar.clicked.connect(self._aplicar)
        rodape.addWidget(self.botao_aplicar)
        return rodape

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        itens = self.repository.contagem()
        linhas = []
        for item in itens:
            diferenca = item.diferenca
            if item.confere:
                texto, tom = "confere", "success"
            else:
                sinal = "+" if diferenca > 0 else "-"
                texto = f"{sinal}{quantidade_texto(abs(diferenca), item.unidade)}"
                tom = "warning" if diferenca > 0 else "danger"
            linhas.append([
                self.tabela.cell(item.produto_codigo),
                self.tabela.cell(item.produto_nome, bold=True),
                self.tabela.cell(
                    quantidade_texto(item.saldo_sistema, item.unidade, com_unidade=True),
                    DIREITA,
                ),
                self.tabela.cell(
                    quantidade_texto(item.contado, item.unidade, com_unidade=True),
                    DIREITA,
                    bold=True,
                ),
                self.tabela.cell(texto, DIREITA, tom, bold=True),
            ])
        self._itens = itens
        self.tabela.fill(linhas, {0: 130, 2: 140, 3: 140, 4: 130})

        contados, divergentes = len(itens), sum(1 for i in itens if not i.confere)
        if contados:
            plural = "produto contado" if contados == 1 else "produtos contados"
            self.resumo.setText(f"{contados} {plural}   ·   {divergentes} com diferença")
        else:
            self.resumo.setText("")
        self._atualizar_acoes()

    def _atualizar_acoes(self) -> None:
        tem_folha = bool(self._itens)
        self.botao_aplicar.setEnabled(tem_folha)
        self.botao_cancelar.setEnabled(tem_folha)
        self.botao_remover.setEnabled(0 <= self.tabela.currentRow() < len(self._itens))
        self.botao_anotar.setEnabled(self._produto is not None)

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------- acoes
    def _localizar(self) -> None:
        termo = self.bipe.text().strip()
        if not termo:
            return
        produto = self.repository.buscar(termo)
        if produto is None:
            self._selecionar(None)
            self._dizer(f"Nenhum produto encontrado para '{termo}'.", "danger")
            return
        self._selecionar(produto)
        self._dizer("")
        self.contado.setFocus()
        self.contado.selectAll()

    def _selecionar(self, produto: Produto | None) -> None:
        self._produto = produto
        if produto is None:
            self.encontrado.setText("Nenhum produto selecionado")
        else:
            saldo = quantidade_texto(produto.quantidade, produto.unidade, com_unidade=True)
            self.encontrado.setText(
                f"{produto.codigo}  -  {produto.nome}   (o sistema diz: {saldo})"
            )
            self.contado.setDecimals(produto.casas)
            # comeca no saldo do sistema: o caso comum e conferir, nao corrigir
            self.contado.setValue(produto.quantidade)
        self._atualizar_acoes()

    def _anotar(self) -> None:
        if self._produto is None:
            return
        try:
            self.repository.contar(self._produto.id, self.contado.value())
        except EstoqueError as erro:
            self._dizer(str(erro), "danger")
            return
        nome = self._produto.nome
        self.bipe.clear()
        self._selecionar(None)
        self.refresh()
        self._dizer(f"'{nome}' anotado na folha.", "success")
        self.bipe.setFocus()

    def _remover(self) -> None:
        linha = self.tabela.currentRow()
        if 0 <= linha < len(self._itens):
            item = self._itens[linha]
            self.repository.remover_da_contagem(item.produto_id)
            self.refresh()
            self._dizer(f"'{item.produto_nome}' saiu da folha.")

    def _cancelar(self) -> None:
        resposta = QMessageBox.question(
            self,
            "Cancelar contagem",
            "Descartar a folha de contagem? Nenhum saldo será alterado.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        self.repository.cancelar_contagem()
        self.refresh()
        self._dizer("Contagem descartada. Nenhum saldo foi alterado.")

    def _aplicar(self) -> None:
        divergentes = sum(1 for item in self._itens if not item.confere)
        if divergentes == 0:
            self.repository.cancelar_contagem()
            self.refresh()
            self._dizer("Tudo conferia: nenhum ajuste foi necessário.", "success")
            self.data_changed.emit()
            return

        plural = "saldo" if divergentes == 1 else "saldos"
        resposta = QMessageBox.question(
            self,
            "Aplicar ajustes",
            f"Corrigir {divergentes} {plural} para a quantidade contada?\n"
            "Cada correção entra no histórico como um ajuste.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        try:
            ajustados = self.repository.aplicar_contagem()
        except EstoqueError as erro:
            self._dizer(str(erro), "danger")
            return
        self.refresh()
        plural = "saldo corrigido" if ajustados == 1 else "saldos corrigidos"
        self._dizer(f"Contagem aplicada: {ajustados} {plural}.", "success")
        self.data_changed.emit()

    def apply_theme(self, palette) -> None:
        self._acao_bipe.setIcon(icons.icon("tag", palette.accent, 16))
