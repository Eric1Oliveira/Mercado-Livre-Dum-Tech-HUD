"""Configuracoes: tudo que o cliente ajusta sozinho, num lugar so.

A regra desta tela e a mesma do produto inteiro: **configuravel pelo cliente, e
util sem configurar**. Nada aqui e obrigatorio para o programa funcionar - mas
tudo que alguem teria vontade de mudar mora aqui, e nao no codigo.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ...ui.theme import Space
from ...ui.widgets.common import label, separator
from ...ui.widgets.pilha import Pilha
from ...ui.widgets.rail import RailItem, RailSection

LARGURA_MENU = 210


class ConfigView(QWidget):
    """Menu de secoes a esquerda, a secao escolhida a direita."""

    #: alguma configuracao mudou e os aplicativos abertos precisam saber
    alterada = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._itens: list[RailItem] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(34, 30, 34, 26)
        raiz.setSpacing(Space.lg)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Configuracoes", "display"))
        titulos.addWidget(
            label("Ajuste o programa do seu jeito - tudo ja funciona sem mexer",
                  "subtitle")
        )
        raiz.addLayout(titulos)

        corpo = QHBoxLayout()
        corpo.setSpacing(Space.xl)

        menu = QWidget()
        menu.setFixedWidth(LARGURA_MENU)
        self._menu = QVBoxLayout(menu)
        self._menu.setContentsMargins(0, 0, 0, 0)
        self._menu.setSpacing(Space.xs)
        self._secao = RailSection()
        self._menu.addWidget(self._secao)
        self._menu.addStretch(1)
        corpo.addWidget(menu)

        self.stack = Pilha()
        corpo.addWidget(self.stack, 1)
        raiz.addLayout(corpo, 1)

    # ------------------------------------------------------------------ secoes
    def add_secao(self, titulo: str, icone: str, widget: QWidget) -> QWidget:
        indice = self.stack.count()
        item = RailItem(titulo, icone)
        item.clicked.connect(lambda _=False, i=indice: self.mostrar(i))
        self._secao.add(item)
        self._itens.append(item)
        self.stack.addWidget(widget)
        if indice == 0:
            self.mostrar(0)
        return widget

    def mostrar(self, indice: int) -> None:
        if not 0 <= indice < self.stack.count():
            return
        self.stack.setCurrentIndex(indice)
        for posicao, item in enumerate(self._itens):
            item.setChecked(posicao == indice)
        self._secao.selecionar(self._itens[indice])

    @property
    def secao_atual(self) -> int:
        return self.stack.currentIndex()

    def refresh(self) -> None:
        for indice in range(self.stack.count()):
            atualizar = getattr(self.stack.widget(indice), "refresh", None)
            if callable(atualizar):
                atualizar()
