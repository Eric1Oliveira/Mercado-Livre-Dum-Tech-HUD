"""Tela de movimentacoes: registrar entradas e saidas do estoque."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ....ui import format as fmt
from ....ui import icons
from ....ui.theme import palette_for
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, label, repolish
from ....ui.widgets.table import DIREITA, DataTable
from ..models import TIPO_ENTRADA, TIPO_SAIDA, EstoqueError, Movimentacao
from ..repository import EstoqueRepository

COLUNAS = ["Data", "Tipo", "Produto", "Quantidade", "Saldo", "Observacao"]


class MovimentacoesView(QWidget):
    """Entrada e saida de produtos, com historico completo."""

    data_changed = Signal()

    def __init__(self, repository: EstoqueRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 24)
        root.setSpacing(16)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Movimentacoes", "title"))
        titulos.addWidget(label("Registre entradas e saidas do seu estoque", "subtitle"))
        root.addLayout(titulos)

        root.addWidget(self._formulario())

        filtros = QHBoxLayout()
        filtros.setSpacing(10)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Pesquisar no historico...")
        self._acao_busca = self.busca.addAction(
            icons.icon("search", palette_for(self).text_dim, 16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.busca.setClearButtonEnabled(True)
        self.busca.textChanged.connect(self.refresh)
        filtros.addWidget(self.busca, 3)

        self.filtro_tipo = QComboBox()
        self.filtro_tipo.addItem("Todos os tipos", "")
        self.filtro_tipo.addItem("Somente entradas", TIPO_ENTRADA)
        self.filtro_tipo.addItem("Somente saidas", TIPO_SAIDA)
        self.filtro_tipo.currentIndexChanged.connect(self.refresh)
        filtros.addWidget(self.filtro_tipo, 1)
        root.addLayout(filtros)

        self.tabela = DataTable(COLUNAS)
        root.addWidget(self.tabela, 1)

        self.refresh()

    # -------------------------------------------------------------- formulario
    def _formulario(self) -> Card:
        card = Card()
        card.body.addWidget(label("Registrar movimentacao", "section"))

        linha = QHBoxLayout()
        linha.setSpacing(12)

        coluna_produto = QVBoxLayout()
        coluna_produto.setSpacing(4)
        coluna_produto.addWidget(label("PRODUTO", "dim"))
        self.combo_produto = QComboBox()
        self.combo_produto.setMinimumWidth(280)
        coluna_produto.addWidget(self.combo_produto)
        linha.addLayout(coluna_produto, 3)

        coluna_qtd = QVBoxLayout()
        coluna_qtd.setSpacing(4)
        coluna_qtd.addWidget(label("QUANTIDADE", "dim"))
        self.quantidade = QSpinBox()
        self.quantidade.setRange(1, 9_999_999)
        self.quantidade.setValue(1)
        self.quantidade.setMinimumWidth(120)
        coluna_qtd.addWidget(self.quantidade)
        linha.addLayout(coluna_qtd, 1)

        coluna_obs = QVBoxLayout()
        coluna_obs.setSpacing(4)
        coluna_obs.addWidget(label("OBSERVACAO (OPCIONAL)", "dim"))
        self.observacao = QLineEdit()
        self.observacao.setPlaceholderText("Ex.: compra do fornecedor, venda no balcao...")
        coluna_obs.addWidget(self.observacao)
        linha.addLayout(coluna_obs, 3)
        card.body.addLayout(linha)

        acoes = QHBoxLayout()
        acoes.setSpacing(10)
        self.aviso = label("", "muted")
        acoes.addWidget(self.aviso, 1)

        self.botao_entrada = Button("Registrar entrada", "in", "success")
        self.botao_entrada.clicked.connect(lambda: self._registrar(TIPO_ENTRADA))
        acoes.addWidget(self.botao_entrada)

        self.botao_saida = Button("Registrar saida", "out", "danger")
        self.botao_saida.clicked.connect(lambda: self._registrar(TIPO_SAIDA))
        acoes.addWidget(self.botao_saida)
        card.body.addLayout(acoes)
        return card

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        self._carregar_produtos()
        movimentacoes = self.repository.listar_movimentacoes(
            tipo=self.filtro_tipo.currentData() or "",
            busca=self.busca.text(),
        )
        self._preencher_tabela(movimentacoes)

    def _carregar_produtos(self) -> None:
        atual = self.combo_produto.currentData()
        produtos = self.repository.listar()
        self.combo_produto.blockSignals(True)
        self.combo_produto.clear()
        for produto in produtos:
            self.combo_produto.addItem(
                f"{produto.codigo}  -  {produto.nome}   (saldo: {produto.quantidade})",
                produto.id,
            )
        indice = self.combo_produto.findData(atual)
        if indice >= 0:
            self.combo_produto.setCurrentIndex(indice)
        self.combo_produto.blockSignals(False)

        tem_produtos = bool(produtos)
        self.botao_entrada.setEnabled(tem_produtos)
        self.botao_saida.setEnabled(tem_produtos)
        if not tem_produtos:
            self.aviso.setText("Cadastre um produto antes de movimentar o estoque.")
            self.aviso.setProperty("tone", "muted")
            repolish(self.aviso)

    def _preencher_tabela(self, movimentacoes: list[Movimentacao]) -> None:
        tons = {TIPO_ENTRADA: "success", TIPO_SAIDA: "danger"}
        linhas = []
        for item in movimentacoes:
            tom = tons.get(item.tipo, "text_muted")
            linhas.append([
                self.tabela.cell(fmt.data_hora(item.criado_em)),
                self.tabela.cell(item.tipo_label, tone=tom, bold=True),
                self.tabela.cell(f"{item.produto_codigo}   {item.produto_nome}"),
                self.tabela.cell(item.variacao, DIREITA, tom, bold=True),
                self.tabela.cell(fmt.numero(item.saldo_atual), DIREITA),
                self.tabela.cell(item.observacao or "-"),
            ])
        self.tabela.fill(linhas, {0: 150, 1: 100, 3: 110, 4: 90})

    # ------------------------------------------------------------------- acoes
    def _registrar(self, tipo: str) -> None:
        produto_id = self.combo_produto.currentData()
        if not produto_id:
            QMessageBox.warning(self, "Selecione um produto", "Escolha o produto da movimentacao.")
            return
        try:
            movimentacao = self.repository.movimentar(
                int(produto_id), tipo, self.quantidade.value(), self.observacao.text()
            )
        except EstoqueError as erro:
            QMessageBox.warning(self, "Movimentacao nao registrada", str(erro))
            return

        self.aviso.setText(
            f"{movimentacao.tipo_label} de {movimentacao.quantidade} registrada em "
            f"'{movimentacao.produto_nome}'. Saldo atual: {movimentacao.saldo_atual}."
        )
        self.aviso.setProperty("tone", "success" if tipo == TIPO_ENTRADA else "danger")
        repolish(self.aviso)
        self.quantidade.setValue(1)
        self.observacao.clear()
        self.refresh()
        self.data_changed.emit()

    def apply_theme(self, palette) -> None:
        self._acao_busca.setIcon(icons.icon("search", palette.text_dim, 16))
