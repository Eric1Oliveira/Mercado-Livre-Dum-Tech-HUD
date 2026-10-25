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
from ....ui.widgets.busca_catalogo import BuscaCatalogo
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, label, repolish
from ....ui.widgets.table import DIREITA, DataTable
from ..catalog import CatalogoEstoque
from ..models import (
    TIPO_ENTRADA,
    TIPO_SAIDA,
    EstoqueError,
    Movimentacao,
    Produto,
    quantidade_texto,
)
from ..repository import EstoqueRepository

COLUNAS = ["Data", "Tipo", "Produto", "Quantidade", "Saldo", "Observação"]


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
        titulos.addWidget(label("Movimentações", "title"))
        titulos.addWidget(label("Registre entradas e saídas do seu estoque", "subtitle"))
        root.addLayout(titulos)

        root.addWidget(self._formulario())

        filtros = QHBoxLayout()
        filtros.setSpacing(10)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Pesquisar no histórico...")
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
        self.filtro_tipo.addItem("Somente saídas", TIPO_SAIDA)
        self.filtro_tipo.currentIndexChanged.connect(self.refresh)
        filtros.addWidget(self.filtro_tipo, 1)
        root.addLayout(filtros)

        self.tabela = DataTable(COLUNAS)
        root.addWidget(self.tabela, 1)

        self.refresh()

    # -------------------------------------------------------------- formulario
    def _formulario(self) -> Card:
        card = Card()
        card.body.addWidget(label("Registrar movimentação", "section"))

        linha = QHBoxLayout()
        linha.setSpacing(12)

        coluna_produto = QVBoxLayout()
        coluna_produto.setSpacing(4)
        coluna_produto.addWidget(label("PRODUTO", "dim"))
        # digitar o nome (ou o codigo) e escolher na lista: com centenas de
        # produtos, rolar uma caixa de selecao nao era busca
        self.campo_produto = QLineEdit()
        self.campo_produto.setPlaceholderText("Digite o nome ou o código, ou bipe o código de barras...")
        self.campo_produto.setMinimumWidth(280)
        self.campo_produto.setClearButtonEnabled(True)
        self.campo_produto.returnPressed.connect(self._localizar)
        self.campo_produto.textEdited.connect(self._digitou)
        coluna_produto.addWidget(self.campo_produto)
        self.busca_produto = BuscaCatalogo(
            self.campo_produto, CatalogoEstoque(self.repository.db)
        )
        self.busca_produto.escolhido.connect(self._escolhido)
        self._produto: Produto | None = None
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
        coluna_obs.addWidget(label("OBSERVAÇÃO (OPCIONAL)", "dim"))
        self.observacao = QLineEdit()
        self.observacao.setPlaceholderText("Ex.: compra do fornecedor, venda no balcão...")
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

        self.botao_saida = Button("Registrar saída", "out", "danger")
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
        # o produto escolhido volta do banco: o saldo mostrado e o de agora
        if self._produto is not None:
            self._selecionar(self.repository.obter(self._produto.id))

        tem_produtos = bool(self.repository.listar())
        self.campo_produto.setEnabled(tem_produtos)
        if not tem_produtos:
            self._dizer("Cadastre um produto antes de movimentar o estoque.")
        self._atualizar_botoes()

    def _atualizar_botoes(self) -> None:
        escolhido = self._produto is not None
        self.botao_entrada.setEnabled(escolhido)
        self.botao_saida.setEnabled(escolhido)

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ----------------------------------------------------------------- produto
    def _digitou(self, _texto: str) -> None:
        # mexeu no nome depois de escolher: o produto so volta a valer escolhido de novo
        if self._produto is not None:
            self._selecionar(None)
            self._dizer("")

    def _localizar(self) -> None:
        termo = self.campo_produto.text().strip()
        if not termo or self._produto is not None:
            return
        produto = self.repository.buscar(termo)
        if produto is not None:
            self._usar(produto)
            return
        if self.repository.listar(busca=termo):
            # o nome bate com mais de um produto: a lista mostra quais
            self.busca_produto.procurar(termo)
            self._dizer(f"Mais de um produto com '{termo}'. Escolha na lista.")
        else:
            self._dizer(f"Nenhum produto encontrado para '{termo}'.", "danger")

    def _escolhido(self, item) -> None:
        """Produto escolhido na lista de sugestões."""
        produto = self.repository.obter(item.produto_id)
        if produto is not None:
            self._usar(produto)

    def _usar(self, produto: Produto) -> None:
        self._selecionar(produto)
        self.quantidade.setFocus()
        self.quantidade.selectAll()

    def _selecionar(self, produto: Produto | None) -> None:
        self._produto = produto
        if produto is not None:
            saldo = quantidade_texto(produto.quantidade, produto.unidade, com_unidade=True)
            self.campo_produto.setText(produto.nome)
            self._dizer(f"{produto.codigo}  -  {produto.nome}   (saldo atual: {saldo})")
        self._atualizar_botoes()

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
        if self._produto is None:
            QMessageBox.warning(self, "Selecione um produto", "Escolha o produto da movimentação.")
            return
        try:
            movimentacao = self.repository.movimentar(
                int(self._produto.id), tipo, self.quantidade.value(), self.observacao.text()
            )
        except EstoqueError as erro:
            QMessageBox.warning(self, "Movimentação não registrada", str(erro))
            return

        self.quantidade.setValue(1)
        self.observacao.clear()
        self.refresh()
        self._dizer(
            f"{movimentacao.tipo_label} de {movimentacao.quantidade} registrada em "
            f"'{movimentacao.produto_nome}'. Saldo atual: {movimentacao.saldo_atual}.",
            "success" if tipo == TIPO_ENTRADA else "danger",
        )
        self.data_changed.emit()

    def apply_theme(self, palette) -> None:
        self._acao_busca.setIcon(icons.icon("search", palette.text_dim, 16))
