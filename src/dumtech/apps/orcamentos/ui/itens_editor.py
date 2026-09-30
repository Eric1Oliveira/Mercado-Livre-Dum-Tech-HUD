"""Itens da proposta, com desconto por linha.

Negociacao de verdade e "tiro 10% nessa peca", nao um abatimento no rodape -
por isso o desconto mora na linha, e o documento mostra os dois.
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
from ..models import ItemOrcamento


#: o que cabe num orcamento de qualquer ramo - servico, obra, peca ou hora
UNIDADES_COMUNS = ("un", "pc", "cx", "kg", "g", "L", "m", "m2", "m3", "h", "dia", "sv")


class ItensEditor(QWidget):
    """Descricao, quantidade, unidade, valor e desconto de cada linha."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None, catalogo=None) -> None:
        super().__init__(parent)
        self._itens: list[ItemOrcamento] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(Space.sm)

        entrada = QHBoxLayout()
        entrada.setSpacing(Space.sm)
        self.descricao = form.texto(dica="O que esta sendo cotado")
        self.descricao.returnPressed.connect(self.adicionar)
        entrada.addWidget(self.descricao, 4)
        # a largura minima padrao dos campos de dinheiro somaria mais que o
        # dialogo inteiro: aqui eles dividem a linha com mais quatro widgets
        self.quantidade = form.quantidade(1, casas=2)
        self.quantidade.setMinimumWidth(95)
        entrada.addWidget(self.quantidade, 1)
        self.unidade = form.combo_sugestao("", UNIDADES_COMUNS, "un")
        self.unidade.setMaximumWidth(84)
        entrada.addWidget(self.unidade)
        self.valor = form.dinheiro(0)
        self.valor.setMinimumWidth(110)
        entrada.addWidget(self.valor, 1)
        self.desconto = form.dinheiro(0)
        self.desconto.setMinimumWidth(110)
        entrada.addWidget(self.desconto, 1)
        adicionar = Button("Adicionar", "plus")
        adicionar.clicked.connect(self.adicionar)
        entrada.addWidget(adicionar)
        raiz.addLayout(entrada)

        # sugestao de produto do Estoque; sem catalogo o campo segue texto livre
        self.busca = BuscaCatalogo(self.descricao, catalogo)
        self.busca.escolhido.connect(self._usar_produto)

        self.tabela = DataTable(
            ["Descricao", "Qtd.", "Valor unit.", "Desconto", "Total"]
        )
        self.tabela.setMinimumHeight(160)
        self.tabela.set_empty_message("Adicione o que esta sendo cotado.")
        raiz.addWidget(self.tabela)

        rodape = QHBoxLayout()
        self.resumo = label("Nenhum item na proposta", "muted")
        rodape.addWidget(self.resumo, 1)
        remover = Button("Remover item", "trash", "danger")
        remover.clicked.connect(self.remover)
        rodape.addWidget(remover)
        raiz.addLayout(rodape)

    def _usar_produto(self, produto) -> None:
        """A proposta sai com o preco do Estoque, e nao com o de cabeca.

        E guarda QUAL produto e: aprovada, a proposta vira venda ou ordem e
        e isso que faz o estoque baixar.
        """
        self._produto = produto
        self.descricao.setText(produto.nome)
        if produto.unidade:
            self.unidade.setCurrentText(produto.unidade)
        self.valor.setValue(float(produto.preco or 0))
        self.quantidade.setFocus()
        self.quantidade.selectAll()

    # ------------------------------------------------------------------ dados
    def set_items(self, itens: list[ItemOrcamento]) -> None:
        self._itens = [
            ItemOrcamento(descricao=i.descricao, quantidade=i.quantidade,
                          valor_unitario=i.valor_unitario, desconto=i.desconto,
                          unidade=i.unidade, produto_id=i.produto_id, codigo=i.codigo)
            for i in itens
        ]
        self._redesenhar()

    def items(self) -> list[ItemOrcamento]:
        return list(self._itens)

    @property
    def subtotal(self) -> float:
        return round(sum(item.total for item in self._itens), 2)

    @property
    def descontos(self) -> float:
        return round(sum(item.desconto for item in self._itens), 2)

    # ------------------------------------------------------------------ acoes
    def adicionar(self) -> None:
        descricao = self.descricao.text().strip()
        if not descricao or self.quantidade.value() <= 0:
            return
        # o vinculo com o Estoque so vale se a descricao continuou a do
        # produto escolhido: reescreveu o campo, virou outra coisa
        produto = getattr(self, "_produto", None)
        do_catalogo = produto is not None and produto.nome.strip() == descricao
        self._itens.append(ItemOrcamento(
            descricao=descricao,
            quantidade=self.quantidade.value(),
            valor_unitario=round(self.valor.value(), 2),
            desconto=round(self.desconto.value(), 2),
            unidade=self.unidade.currentText().strip(),
            produto_id=int(getattr(produto, "produto_id", 0) or 0) if do_catalogo else 0,
            codigo=(getattr(produto, "codigo", "") or "") if do_catalogo else "",
        ))
        self._produto = None
        self.descricao.clear()
        self.quantidade.setValue(1)
        self.valor.setValue(0)
        self.desconto.setValue(0)
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
                    self.tabela.cell(item.descricao, bold=True),
                    self.tabela.cell(item.quantidade_texto, DIREITA),
                    self.tabela.cell(fmt.moeda(item.valor_unitario), DIREITA),
                    self.tabela.cell(
                        f"-{fmt.moeda(item.desconto)}" if item.desconto else "-",
                        DIREITA, "danger" if item.desconto else "",
                    ),
                    self.tabela.cell(fmt.moeda(item.total), DIREITA, "accent", bold=True),
                ]
                for item in self._itens
            ],
            {1: 110, 2: 130, 3: 120, 4: 130},
        )

        if self._itens:
            texto = (f"{fmt.contagem(len(self._itens), 'item', 'itens')}"
                     f"   -   {fmt.moeda(self.subtotal)}")
            if self.descontos:
                texto += f"   (ja com {fmt.moeda(self.descontos)} de desconto nas linhas)"
            self.resumo.setText(texto)
        else:
            self.resumo.setText("Nenhum item na proposta")
        self.changed.emit()
