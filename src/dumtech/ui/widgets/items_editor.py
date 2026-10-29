"""Editor de itens usado pelo Vendas ("Lancar venda").

Uma tabela simples com descricao, quantidade e valor unitario, mais os botoes
de adicionar e remover. Devolve os itens como lista de dicionarios.

Com o catalogo do Estoque, o campo de descricao sugere produto enquanto se
digita (o mesmo `BuscaCatalogo` do balcao) e o item escolhido guarda QUAL
produto e - e isso que faz a venda baixar o saldo. Sem catalogo, segue texto
livre como sempre foi.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .. import format as fmt
from .busca_catalogo import BuscaCatalogo
from .buttons import Button
from .common import label
from .form import dinheiro, quantidade, texto
from .table import DIREITA, DataTable


class ItemsEditor(QWidget):
    """Lista de itens de um documento (orcamento, venda...)."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None, catalogo=None) -> None:
        super().__init__(parent)
        self._itens: list[dict[str, Any]] = []
        #: ultimo produto escolhido no catalogo, esperando virar item
        self._produto = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(8)

        entrada = QHBoxLayout()
        entrada.setSpacing(8)
        self.campo_descricao = texto(
            dica="Produto ou descrição" if catalogo else "Descrição do item"
        )
        entrada.addWidget(self.campo_descricao, 3)
        # as casas acompanham a unidade do produto escolhido (KG vende 1,250)
        self.campo_quantidade = quantidade(1)
        self.campo_quantidade.setMinimumWidth(80)
        entrada.addWidget(self.campo_quantidade, 1)
        self.campo_valor = dinheiro(0)
        entrada.addWidget(self.campo_valor, 1)
        adicionar = Button("Adicionar", "plus")
        adicionar.clicked.connect(self.adicionar)
        entrada.addWidget(adicionar)
        raiz.addLayout(entrada)

        # sugestao de produto do Estoque; sem catalogo o campo segue texto livre
        self.busca = BuscaCatalogo(self.campo_descricao, catalogo)
        self.busca.escolhido.connect(self._usar_produto)

        self.tabela = DataTable(["Item", "Qtd.", "Valor unit.", "Total"])
        self.tabela.setMinimumHeight(160)
        raiz.addWidget(self.tabela)

        rodape = QHBoxLayout()
        self.resumo = label("Nenhum item adicionado", "muted")
        rodape.addWidget(self.resumo, 1)
        remover = Button("Remover item", "trash", "danger")
        remover.clicked.connect(self.remover)
        rodape.addWidget(remover)
        raiz.addLayout(rodape)

        self.campo_descricao.returnPressed.connect(self.adicionar)

    def _usar_produto(self, produto) -> None:
        """O item sai com o nome e o preco do Estoque, e nao de cabeca."""
        self._produto = produto
        self.campo_descricao.setText(produto.nome)
        self.campo_quantidade.setDecimals(int(produto.casas or 0))
        self.campo_quantidade.setValue(1)
        self.campo_valor.setValue(float(produto.preco or 0))
        self.campo_quantidade.setFocus()
        self.campo_quantidade.selectAll()

    # ------------------------------------------------------------------ dados
    def set_items(self, itens: list[dict[str, Any]]) -> None:
        self._itens = [dict(item) for item in itens]
        self._redesenhar()

    def items(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._itens]

    @property
    def total(self) -> float:
        return sum(i["quantidade"] * i["valor_unitario"] for i in self._itens)

    # ------------------------------------------------------------------ acoes
    def adicionar(self) -> None:
        descricao = self.campo_descricao.text().strip()
        if not descricao or self.campo_quantidade.value() <= 0:
            return
        item = {
            "descricao": descricao,
            "quantidade": self.campo_quantidade.value(),
            "valor_unitario": round(self.campo_valor.value(), 2),
        }
        # o vinculo com o Estoque so vale se a descricao continuou a do
        # produto escolhido: reescreveu o campo, virou outra coisa
        produto = self._produto
        if produto is not None and produto.nome.strip() == descricao:
            item.update(
                produto_id=int(produto.produto_id or 0),
                codigo=produto.codigo or "",
                unidade=produto.unidade or "UN",
                casas=int(produto.casas or 0),
            )
        self._itens.append(item)
        self._produto = None
        self.campo_descricao.clear()
        self.campo_quantidade.setDecimals(0)
        self.campo_quantidade.setValue(1)
        self.campo_valor.setValue(0)
        self.campo_descricao.setFocus()
        self._redesenhar()

    def remover(self) -> None:
        linha = self.tabela.currentRow()
        if 0 <= linha < len(self._itens):
            self._itens.pop(linha)
            self._redesenhar()

    def _redesenhar(self) -> None:
        linhas = []
        for item in self._itens:
            total = item["quantidade"] * item["valor_unitario"]
            linhas.append([
                self.tabela.cell(item["descricao"]),
                self.tabela.cell(fmt.numero(item["quantidade"]), DIREITA),
                self.tabela.cell(fmt.moeda(item["valor_unitario"]), DIREITA),
                self.tabela.cell(fmt.moeda(total), DIREITA, "accent", bold=True),
            ])
        self.tabela.fill(linhas, {1: 80, 2: 130, 3: 130})
        quantidade = len(self._itens)
        if quantidade:
            rotulo = "item" if quantidade == 1 else "itens"
            self.resumo.setText(f"{quantidade} {rotulo}   -   Total: {fmt.moeda(self.total)}")
        else:
            self.resumo.setText("Nenhum item adicionado")
        self.changed.emit()
