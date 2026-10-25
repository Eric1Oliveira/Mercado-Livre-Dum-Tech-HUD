"""Editor de itens usado por Orcamentos e Vendas.

Uma tabela simples com descricao, quantidade e valor unitario, mais os botoes
de adicionar e remover. Devolve os itens como lista de dicionarios.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .. import format as fmt
from .buttons import Button
from .common import label
from .form import dinheiro, inteiro, texto
from .table import DIREITA, DataTable


class ItemsEditor(QWidget):
    """Lista de itens de um documento (orcamento, venda...)."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._itens: list[dict[str, Any]] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(8)

        entrada = QHBoxLayout()
        entrada.setSpacing(8)
        self.campo_descricao = texto(dica="Descrição do item")
        entrada.addWidget(self.campo_descricao, 3)
        self.campo_quantidade = inteiro(1, minimo=1)
        self.campo_quantidade.setMinimumWidth(80)
        entrada.addWidget(self.campo_quantidade, 1)
        self.campo_valor = dinheiro(0)
        entrada.addWidget(self.campo_valor, 1)
        adicionar = Button("Adicionar", "plus")
        adicionar.clicked.connect(self.adicionar)
        entrada.addWidget(adicionar)
        raiz.addLayout(entrada)

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
        if not descricao:
            return
        self._itens.append({
            "descricao": descricao,
            "quantidade": self.campo_quantidade.value(),
            "valor_unitario": round(self.campo_valor.value(), 2),
        })
        self.campo_descricao.clear()
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
                self.tabela.cell(str(item["quantidade"]), DIREITA),
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
