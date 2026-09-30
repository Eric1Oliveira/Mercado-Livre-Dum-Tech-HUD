"""Paineis de lista e de grafico usados no painel inicial de cada aplicativo.

Os dois tem a mesma cabeca: o titulo a esquerda e uma nota curta a direita,
sem fio embaixo - o espaco ja separa o titulo do conteudo.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..theme import Space
from .common import Card, label, separator, tone_label

PADDING = Space.lg + 4


def cabeca_de_painel(titulo: str, nota: str = ""):
    """Titulo de cartao a esquerda, nota curta a direita - sem fio embaixo.

    Publica: cartao montado a mao num modulo usa a mesma cabeca dos paineis,
    senao cada modulo inventa a sua (e um deles vinha com fio cheio).
    """
    topo = QHBoxLayout()
    topo.setSpacing(Space.sm)
    topo.addWidget(label(titulo, "section"))
    topo.addStretch(1)
    rotulo_nota = label(nota, "dim")
    topo.addWidget(rotulo_nota, 0, Qt.AlignmentFlag.AlignVCenter)
    return topo, rotulo_nota


class ListPanel(Card):
    """Cartao com titulo e uma lista simples de linhas.

    Cada item e uma tupla: (titulo, detalhe, valor, tom_do_valor).
    """

    def __init__(
        self,
        titulo: str,
        vazio: str = "Nada por aqui ainda.",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, padding=PADDING)
        self._vazio = vazio
        self.body.setSpacing(Space.sm)
        topo, self.nota = cabeca_de_painel(titulo)
        self.body.addLayout(topo)
        self.lista = QVBoxLayout()
        self.lista.setSpacing(0)
        self.body.addLayout(self.lista)
        self.body.addStretch(1)

    def set_nota(self, texto: str) -> None:
        self.nota.setText(texto)

    def set_items(self, itens: list[tuple[str, str, str, str]]) -> None:
        while self.lista.count():
            item = self.lista.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)   # tira da tela na hora
                widget.deleteLater()

        if not itens:
            vazio = label(self._vazio, "muted")
            vazio.setContentsMargins(0, Space.sm, 0, 0)
            self.lista.addWidget(vazio)
            return

        for posicao, (titulo, detalhe, valor, tom) in enumerate(itens):
            if posicao:
                self.lista.addWidget(separator(tracejado=True))
            self.lista.addWidget(_linha(titulo, detalhe, valor, tom))


def _linha(titulo: str, detalhe: str, valor: str, tom: str) -> QWidget:
    linha = QWidget()
    layout = QHBoxLayout(linha)
    layout.setContentsMargins(0, 10, 0, 10)
    layout.setSpacing(10)

    texto = QVBoxLayout()
    texto.setSpacing(2)
    texto.addWidget(label(titulo, "strong"))
    if detalhe:
        texto.addWidget(label(detalhe, "caption"))
    layout.addLayout(texto, 1)

    if valor:
        etiqueta = tone_label(valor, tom or "muted", "strong")
        etiqueta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        etiqueta.setMinimumWidth(80)
        layout.addWidget(etiqueta)
    return linha


class ChartPanel(Card):
    """Cartao com titulo e um grafico dentro.

    Existe para o painel nao virar uma pilha de listas: onde a pergunta e
    "quanto de cada", o desenho responde antes da leitura.
    """

    def __init__(
        self,
        titulo: str,
        grafico,
        subtitulo: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, padding=PADDING)
        self.grafico = grafico
        self.body.setSpacing(Space.md + 2)
        topo, self.nota = cabeca_de_painel(titulo, subtitulo)
        self.body.addLayout(topo)
        self.body.addWidget(grafico, 1)

    def set_nota(self, texto: str) -> None:
        self.nota.setText(texto)
