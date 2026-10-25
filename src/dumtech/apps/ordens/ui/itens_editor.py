"""Pecas e servicos da ordem.

O editor de itens da plataforma nao serve aqui: a ordem precisa dizer se a
linha e **peca** ou **servico**, porque essa separacao e a conta que responde
se o conserto valeu a pena.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.theme import Space
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....ui.widgets.busca_catalogo import BuscaCatalogo
from ....ui.widgets.common import label
from ....ui.widgets.table import DIREITA, DataTable
from ..models import PECA, SERVICO, TIPO_ITEM_OPCOES, ItemOS


class ItensEditor(QWidget):
    """Lista de materiais e servicos, com o total de cada lado."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None, catalogo=None) -> None:
        super().__init__(parent)
        self._itens: list[ItemOS] = []
        #: ultimo produto escolhido no catalogo, esperando virar item
        self._produto = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(Space.sm)

        entrada = QHBoxLayout()
        entrada.setSpacing(Space.sm)
        self.tipo = form.escolha(TIPO_ITEM_OPCOES, SERVICO)
        entrada.addWidget(self.tipo, 1)
        self.descricao = form.texto(dica="Material aplicado ou serviço feito")
        self.descricao.returnPressed.connect(self.adicionar)
        entrada.addWidget(self.descricao, 3)
        self.quantidade = form.quantidade(1, casas=0)
        entrada.addWidget(self.quantidade, 1)
        self.valor = form.dinheiro(0)
        entrada.addWidget(self.valor, 1)
        adicionar = Button("Adicionar", "plus")
        adicionar.clicked.connect(self.adicionar)
        entrada.addWidget(adicionar)
        raiz.addLayout(entrada)

        # sugestao de produto do Estoque; sem catalogo o campo segue texto livre
        self.busca = BuscaCatalogo(self.descricao, catalogo)
        self.busca.escolhido.connect(self._usar_produto)

        self.tabela = DataTable(["Tipo", "Descrição", "Qtd.", "Valor unit.", "Total"])
        # baixa de proposito: a lista costuma ter duas ou tres linhas, e cada
        # pixel gasto aqui empurra os blocos de detalhe para fora da tela
        self.tabela.setMinimumHeight(104)
        self.tabela.set_empty_message("Sem itens: vale o valor digitado acima.")
        raiz.addWidget(self.tabela)

        rodape = QHBoxLayout()
        self.resumo = label("Nenhum item lançado", "muted")
        rodape.addWidget(self.resumo, 1)
        remover = Button("Remover item", "trash", "danger")
        remover.clicked.connect(self.remover)
        rodape.addWidget(remover)
        raiz.addLayout(rodape)

    def _usar_produto(self, produto) -> None:
        """Produto que veio do Estoque e material, nao servico - e assim que se cobra.

        Guardar QUAL produto e (e nao so o nome) e o que permite a peca sair
        do saldo do Estoque quando a ordem for entregue.
        """
        self._produto = produto
        self.descricao.setText(produto.nome)
        self.valor.setValue(float(produto.preco or 0))
        indice = self.tipo.findData(PECA)
        if indice >= 0:
            self.tipo.setCurrentIndex(indice)
        self.quantidade.setFocus()
        self.quantidade.selectAll()

    # ------------------------------------------------------------------ dados
    def set_items(self, itens: list[ItemOS]) -> None:
        self._itens = [
            ItemOS(tipo=i.tipo, descricao=i.descricao, quantidade=i.quantidade,
                   valor_unitario=i.valor_unitario,
                   produto_id=i.produto_id, codigo=i.codigo)
            for i in itens
        ]
        self._redesenhar()

    def items(self) -> list[ItemOS]:
        return list(self._itens)

    @property
    def total(self) -> float:
        return round(sum(item.total for item in self._itens), 2)

    # ------------------------------------------------------------------ acoes
    def adicionar(self) -> None:
        descricao = self.descricao.text().strip()
        if not descricao or self.quantidade.value() <= 0:
            return
        # o vinculo com o Estoque so vale se a descricao continuou sendo a do
        # produto escolhido: se alguem reescreveu o campo, virou outra coisa
        produto = self._produto
        do_catalogo = produto is not None and produto.nome.strip() == descricao
        self._itens.append(ItemOS(
            tipo=self.tipo.currentData(),
            descricao=descricao,
            quantidade=self.quantidade.value(),
            valor_unitario=round(self.valor.value(), 2),
            produto_id=int(getattr(produto, "produto_id", 0) or 0) if do_catalogo else 0,
            codigo=(getattr(produto, "codigo", "") or "") if do_catalogo else "",
        ))
        self._produto = None
        self.descricao.clear()
        self.quantidade.setValue(1)
        self.valor.setValue(0)
        self.descricao.setFocus()
        self._redesenhar()

    def remover(self) -> None:
        linha = self.tabela.currentRow()
        if 0 <= linha < len(self._itens):
            self._itens.pop(linha)
            self._redesenhar()

    def _redesenhar(self) -> None:
        self.tabela.fill(
            [
                [
                    self.tabela.cell(item.tipo_label,
                                     tone="warning" if item.e_peca else "accent"),
                    self.tabela.cell(item.descricao, bold=True),
                    self.tabela.cell(fmt.numero(item.quantidade), DIREITA),
                    self.tabela.cell(fmt.moeda(item.valor_unitario), DIREITA),
                    self.tabela.cell(fmt.moeda(item.total), DIREITA, "accent", bold=True),
                ]
                for item in self._itens
            ],
            {0: 100, 2: 80, 3: 120, 4: 120},
        )

        if self._itens:
            pecas = sum(i.total for i in self._itens if i.tipo == PECA)
            servicos = sum(i.total for i in self._itens if i.tipo == SERVICO)
            self.resumo.setText(
                f"Materiais: {fmt.moeda(pecas)}     Serviços: {fmt.moeda(servicos)}"
                f"     Total: {fmt.moeda(self.total)}"
            )
        else:
            self.resumo.setText("Nenhum item lançado")
        self.changed.emit()
