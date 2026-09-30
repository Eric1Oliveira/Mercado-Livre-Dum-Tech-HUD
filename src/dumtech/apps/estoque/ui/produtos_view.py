"""Tela de produtos: cadastrar, pesquisar e movimentar sem sair da lista."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QWidget,
)

from ....ui import format as fmt
from ....ui import icons
from ....ui.theme import palette_for
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import menu_arredondado
from ....ui.widgets.crud_view import CrudView
from ....ui.widgets.table import DIREITA
from ..models import TIPO_ENTRADA, TIPO_SAIDA, Produto, quantidade_texto
from ..repository import EstoqueRepository


class ProdutosView(CrudView):
    """Lista de produtos: e daqui que o dia a dia acontece."""

    titulo = "Produtos"
    nome_registro = "produto"
    nome_plural = "produtos"
    rotulo_novo = "Novo produto"
    dica_pesquisa = "Pesquisar por codigo, nome, categoria, local ou codigo de barras..."
    colunas = [
        "Codigo", "Produto", "Categoria", "Local",
        "Qtd.", "Custo", "Venda", "Margem", "Situacao",
    ]
    larguras = {0: 110, 3: 100, 4: 110, 5: 105, 6: 105, 7: 85, 8: 120}

    def __init__(self, repository: EstoqueRepository, parent: QWidget | None = None) -> None:
        self.repository = repository
        super().__init__(parent)
        self._montar_bipe()
        self._montar_atalhos()

    # ------------------------------------------------------------------ filtros
    def build_filters(self, layout: QHBoxLayout) -> None:
        self.filtro_categoria = QComboBox()
        self.filtro_categoria.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_categoria, 1)

        self.somente_baixo = QCheckBox("Somente estoque baixo")
        self.somente_baixo.stateChanged.connect(self.refresh)
        layout.addWidget(self.somente_baixo)

        self.mostrar_inativos = QCheckBox("Mostrar inativos")
        self.mostrar_inativos.stateChanged.connect(self.refresh)
        layout.addWidget(self.mostrar_inativos)

    def build_actions(self, layout: QHBoxLayout) -> None:
        self.botao_entrada = Button("Entrada", "in", "success")
        self.botao_entrada.setToolTip("Registra uma entrada do produto selecionado (E)")
        self.botao_entrada.clicked.connect(lambda: self._movimentar(TIPO_ENTRADA))
        layout.insertWidget(1, self.botao_entrada)

        self.botao_saida = Button("Saida", "out", "danger")
        self.botao_saida.setToolTip("Registra uma saida do produto selecionado (S)")
        self.botao_saida.clicked.connect(lambda: self._movimentar(TIPO_SAIDA))
        layout.insertWidget(2, self.botao_saida)

        self.botao_ativar = Button("Inativar", "close")
        self.botao_ativar.setToolTip(
            "Tira o produto das listas mantendo todo o historico dele"
        )
        self.botao_ativar.clicked.connect(self._alternar_ativo)
        layout.addWidget(self.botao_ativar)

        self.botao_planilha = Button("Planilha", "file")
        self.botao_planilha.setToolTip("Importar ou exportar em CSV")
        self.botao_planilha.setMenu(self._menu_planilha())
        layout.addWidget(self.botao_planilha)

    def _menu_planilha(self) -> QMenu:
        from . import planilha_dialog as planilha

        menu = menu_arredondado(self)
        acao = menu.addAction("Importar produtos de um CSV...")
        acao.triggered.connect(self._importar)
        menu.addSeparator()
        menu.addAction("Exportar produtos...").triggered.connect(
            lambda: planilha.exportar(self, self.repository)
        )
        menu.addAction("Exportar movimentacoes...").triggered.connect(
            lambda: planilha.exportar(self, self.repository, movimentacoes=True)
        )
        return menu

    def _importar(self) -> None:
        from . import planilha_dialog as planilha

        if planilha.importar(self, self.repository):
            self.refresh()
            self.data_changed.emit()

    def _montar_bipe(self) -> None:
        """O leitor USB digita o codigo e da Enter: e so escutar o Enter."""
        caixa = QHBoxLayout()
        caixa.setSpacing(10)
        self.bipe = QLineEdit()
        self.bipe.setPlaceholderText(
            "Bipe o codigo de barras ou digite o codigo e tecle Enter..."
        )
        self.bipe.setClearButtonEnabled(True)
        self._acao_bipe = self.bipe.addAction(
            icons.icon("tag", palette_for(self).accent, 16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.bipe.returnPressed.connect(self._bipou)
        caixa.addWidget(self.bipe, 1)

        self.tipo_bipe = QComboBox()
        self.tipo_bipe.addItem("Bipar da saida", TIPO_SAIDA)
        self.tipo_bipe.addItem("Bipar da entrada", TIPO_ENTRADA)
        self.tipo_bipe.setToolTip("O que fazer com o produto lido")
        caixa.addWidget(self.tipo_bipe)

        # entra logo abaixo do cabecalho, antes da pesquisa
        self.layout().insertLayout(1, caixa)

    def _montar_atalhos(self) -> None:
        for tecla, tipo in (("E", TIPO_ENTRADA), ("S", TIPO_SAIDA)):
            atalho = QShortcut(QKeySequence(tecla), self)
            atalho.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            atalho.activated.connect(lambda t=tipo: self._movimentar(t))
        foco = QShortcut(QKeySequence("Ctrl+B"), self)
        foco.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        foco.activated.connect(self.bipe.setFocus)

    # ------------------------------------------------------------------- dados
    def carregar(self) -> list[Produto]:
        self._preencher_categorias()
        return self.repository.listar(
            busca=self.busca.text(),
            categoria=self.filtro_categoria.currentData() or "",
            apenas_baixo=self.somente_baixo.isChecked(),
            incluir_inativos=self.mostrar_inativos.isChecked(),
        )

    def montar_linha(self, produto: Produto) -> list:
        if not produto.ativo:
            situacao, tom = "Inativo", "muted"
        elif produto.sem_estoque:
            situacao, tom = "Sem estoque", "danger"
        elif produto.estoque_baixo:
            situacao, tom = "Estoque baixo", "warning"
        else:
            situacao, tom = "Normal", "success"

        margem = produto.margem
        return [
            self.tabela.cell(produto.codigo, data=produto.id),
            self.tabela.cell(produto.nome, bold=True),
            self.tabela.cell(produto.categoria or "-"),
            self.tabela.cell(produto.localizacao or "-"),
            self.tabela.cell(
                quantidade_texto(produto.quantidade, produto.unidade, com_unidade=True),
                DIREITA,
                tom,
                bold=True,
            ),
            self.tabela.cell(fmt.moeda(produto.preco_custo), DIREITA),
            self.tabela.cell(fmt.moeda(produto.preco_venda), DIREITA),
            self.tabela.cell(
                f"{margem:.0f}%" if margem is not None else "-",
                DIREITA,
                "success" if margem and margem >= 30 else "muted",
            ),
            self.tabela.cell(situacao, tone=tom),
        ]

    def _preencher_categorias(self) -> None:
        atual = self.filtro_categoria.currentData() or ""
        self.filtro_categoria.blockSignals(True)
        self.filtro_categoria.clear()
        self.filtro_categoria.addItem("Todas as categorias", "")
        for categoria in self.repository.categorias():
            self.filtro_categoria.addItem(categoria, categoria)
        indice = self.filtro_categoria.findData(atual)
        self.filtro_categoria.setCurrentIndex(max(indice, 0))
        self.filtro_categoria.blockSignals(False)

    def _atualizar_acoes(self) -> None:
        super()._atualizar_acoes()
        produto = self.registro_selecionado()
        tem = produto is not None
        for botao in (self.botao_entrada, self.botao_saida, self.botao_ativar):
            botao.setEnabled(tem)
        if tem:
            self.botao_saida.setEnabled(produto.quantidade > 0)
            self.botao_ativar.setText("  Reativar" if not produto.ativo else "  Inativar")
            self.botao_ativar.set_icon_name("check" if not produto.ativo else "close")

    # ------------------------------------------------------------------- acoes
    def _bipou(self) -> None:
        termo = self.bipe.text().strip()
        if not termo:
            return
        produto = self.repository.buscar(termo)
        self.bipe.clear()
        if produto is None:
            self.busca.setText(termo)  # nao achou: vira pesquisa, sem beco sem saida
            self.mostrar_aviso(f"Nenhum produto encontrado para '{termo}'.")
            return
        self._abrir_movimento(produto, self.tipo_bipe.currentData())

    def _movimentar(self, tipo: str) -> None:
        produto = self.registro_selecionado()
        if produto is not None:
            self._abrir_movimento(produto, tipo)

    def _abrir_movimento(self, produto: Produto, tipo: str) -> None:
        from .movimento_dialog import MovimentoDialog

        if not produto.ativo:
            self.mostrar_aviso(f"'{produto.nome}' esta inativo. Reative para movimentar.")
            return
        if tipo == TIPO_SAIDA and produto.quantidade <= 0:
            self.mostrar_aviso(f"'{produto.nome}' esta sem estoque.")
            return

        dialogo = MovimentoDialog(self.repository, produto, tipo, self)
        if not dialogo.exec():
            return
        movimento = dialogo.movimentacao
        self.refresh()  # antes do aviso: recarregar limpa a linha de recado
        self.mostrar_aviso(
            f"{movimento.tipo_label} de "
            f"{quantidade_texto(movimento.quantidade, produto.unidade)} em "
            f"'{movimento.produto_nome}'. Saldo: "
            f"{quantidade_texto(movimento.saldo_atual, produto.unidade, True)}.",
            "success" if tipo == TIPO_ENTRADA else "danger",
        )
        self.data_changed.emit()

    def _alternar_ativo(self) -> None:
        produto = self.registro_selecionado()
        if produto is None:
            return
        if produto.ativo:
            self.repository.inativar(produto.id)
        else:
            self.repository.reativar(produto.id)
        self.refresh()
        self.data_changed.emit()

    # ------------------------------------------------------------------ ganchos
    def abrir_dialogo(self, produto: Produto | None):
        from .produto_dialog import ProdutoDialog

        return ProdutoDialog(self.repository, produto, self)

    def excluir(self, produto: Produto) -> None:
        self.repository.excluir(produto.id)

    def descricao(self, produto: Produto) -> str:
        return produto.nome

    def apply_theme(self, palette) -> None:
        super().apply_theme(palette)
        self._acao_bipe.setIcon(icons.icon("tag", palette.accent, 16))
