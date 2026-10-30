"""Produtos para reposicao: a lista inteira, do mais urgente para o menos.

Abre pelo cartao do Painel e pelo "Ver todos". Zerado vem antes de baixo,
porque produto zerado e venda perdida hoje. Cada linha diz quanto comprar para
chegar ao estoque maximo, de quem se compra e quando foi a ultima reposicao - e
a reposicao e registrada daqui mesmo, sem cacar o produto em outra tela.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.theme import Space, apply_window_theme, palette_for
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Pill, label, repolish
from ....ui.widgets.table import DIREITA, DataTable
from ..models import TIPO_ENTRADA, Produto, quantidade_texto
from ..repository import EstoqueRepository

COLUNAS = ["Produto", "Situação", "Em estoque", "Mínimo", "Sugerido", "Fornecedor",
           "Última reposição"]

TODOS, ZERADOS, BAIXOS = "todos", "zerados", "baixos"
FILTROS = (("Todos", TODOS), ("Só zerados", ZERADOS), ("Só abaixo do mínimo", BAIXOS))


class ReposicaoDialog(QDialog):
    """Os produtos no estoque minimo, com a quantidade sugerida e a reposicao."""

    def __init__(self, repository: EstoqueRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.houve_mudanca = False
        self._produtos: list[Produto] = []

        self.setWindowTitle("Produtos para reposição")
        self.setModal(True)
        self.setMinimumSize(880, 520)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)

        topo = QHBoxLayout()
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Produtos para reposição", "cardTitle"))
        titulos.addWidget(label("Quantidade sugerida para atingir o estoque máximo.", "muted"))
        topo.addLayout(titulos, 1)
        self.filtro = QComboBox()
        for rotulo, valor in FILTROS:
            self.filtro.addItem(rotulo, valor)
        self.filtro.currentIndexChanged.connect(self._preencher)
        topo.addWidget(self.filtro)
        raiz.addLayout(topo)

        # o tamanho de cada grupo antes da lista: decide por onde comecar
        contagem = QHBoxLayout()
        contagem.setSpacing(Space.sm)
        self.pill_zerados = Pill("", "danger")
        self.pill_baixos = Pill("", "warning")
        contagem.addWidget(self.pill_zerados)
        contagem.addWidget(self.pill_baixos)
        contagem.addStretch(1)
        raiz.addLayout(contagem)

        self.tabela = DataTable(COLUNAS)
        self.tabela.set_empty_message("Nenhum produto precisa de reposição. Estoque em dia.")
        self.tabela.doubleClicked.connect(self.registrar)
        self.tabela.itemSelectionChanged.connect(self._atualizar_acoes)
        raiz.addWidget(self.tabela, 1)

        rodape = QHBoxLayout()
        rodape.setSpacing(Space.sm + 2)
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        rodape.addWidget(self.aviso, 1)
        fechar = Button("Fechar")
        fechar.setMinimumHeight(38)
        fechar.clicked.connect(self.accept)
        rodape.addWidget(fechar)
        self.botao_registrar = Button("Registrar reposição", "in", "primary")
        self.botao_registrar.setMinimumHeight(38)
        self.botao_registrar.setToolTip("Dá entrada no produto selecionado (duplo clique)")
        self.botao_registrar.clicked.connect(self.registrar)
        rodape.addWidget(self.botao_registrar)
        raiz.addLayout(rodape)

        apply_window_theme(self, palette_for(parent))
        self.refresh()

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        self._todos = self.repository.a_comprar()
        self._ultimas = self.repository.ultimas_entradas()
        zerados = sum(1 for p in self._todos if p.sem_estoque)
        baixos = len(self._todos) - zerados
        self.pill_zerados.setText(fmt.contagem(zerados, "zerado"))
        self.pill_zerados.setVisible(bool(zerados))
        self.pill_baixos.setText(f"{fmt.numero(baixos)} abaixo do mínimo")
        self.pill_baixos.setVisible(bool(baixos))
        self._preencher()

    def _preencher(self) -> None:
        filtro = self.filtro.currentData()
        self._produtos = [
            p for p in self._todos
            if filtro == TODOS or (filtro == ZERADOS) == p.sem_estoque
        ]
        self.tabela.fill([self._linha(p) for p in self._produtos],
                         {1: 80, 2: 90, 3: 70, 4: 90, 5: 140, 6: 120})
        if self._produtos:
            self.tabela.selectRow(0)    # o mais urgente ja vem escolhido
        self._atualizar_acoes()

    def _linha(self, produto: Produto) -> list:
        cell = self.tabela.cell
        u = produto.unidade
        sugestao = produto.sugestao_compra
        ultima = self._ultimas.get(produto.id)
        return [
            cell(produto.nome, bold=True, data=produto.id),
            cell("Zerado", tone="danger", bold=True) if produto.sem_estoque
            else cell("Baixo", tone="warning", bold=True),
            cell(quantidade_texto(produto.quantidade, u, True), DIREITA),
            cell(quantidade_texto(produto.estoque_minimo, u), DIREITA),
            # sem estoque maximo nem minimo nao ha alvo: melhor um traco que um zero
            cell(f"+{quantidade_texto(sugestao, u, True)}" if sugestao > 0 else "-",
                 DIREITA, bold=sugestao > 0),
            cell(produto.fornecedor or "-"),
            cell(fmt.data(ultima) if ultima else "Nunca", tone="" if ultima else "text_muted"),
        ]

    def selecionado(self) -> Produto | None:
        linha = self.tabela.currentRow()
        if 0 <= linha < len(self._produtos):
            return self._produtos[linha]
        return None

    def _atualizar_acoes(self) -> None:
        self.botao_registrar.setEnabled(self.selecionado() is not None)

    # ------------------------------------------------------------------- acoes
    def registrar(self) -> None:
        from .movimento_dialog import MovimentoDialog

        produto = self.selecionado()
        if produto is None:
            return
        dialogo = MovimentoDialog(
            self.repository, produto, TIPO_ENTRADA, self,
            quantidade_inicial=produto.sugestao_compra or None,
            observacao="Reposição de estoque",
        )
        if not dialogo.exec():
            return
        movimento = dialogo.movimentacao
        self.houve_mudanca = True
        self.refresh()
        self.aviso.setText(
            f"Reposição de {quantidade_texto(movimento.quantidade, produto.unidade, True)} "
            f"em '{movimento.produto_nome}'. Saldo: "
            f"{quantidade_texto(movimento.saldo_atual, produto.unidade, True)}."
        )
        self.aviso.setProperty("tone", "success")
        repolish(self.aviso)
