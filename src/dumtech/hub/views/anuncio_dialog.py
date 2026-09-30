"""O anuncio em pop-up: uma vez por anuncio, e so.

POR QUE EXISTE
    O bloco "DumTech para voce", no Inicio, e discreto de proposito - e por
    isso passava batido. Novidade que ninguem ve nao vende, e o cliente fica
    sabendo do modulo novo pelo WhatsApp, meses depois.

AS REGRAS (sao elas que separam anuncio de estorvo)
    * aparece **uma vez por anuncio**, nunca de novo (`core/comunicados.py`);
    * so quando o Hub ja esta aberto e na tela de Inicio - nunca por cima de
      alguem trabalhando dentro de um aplicativo;
    * um por vez, e no maximo um por abertura do programa;
    * fechar e de graca: "Agora nao" some e nao volta.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from ...ui.theme import Space, apply_window_theme, palette_for
from ...ui.widgets.buttons import Button
from ...ui.widgets.common import IconBadge, Pill, label, separator

LARGURA = 460


class AnuncioDialog(QDialog):
    """Um anuncio com cara de anuncio: etiqueta, titulo grande e um convite."""

    def __init__(self, comunicado, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.comunicado = comunicado
        self.setWindowTitle(comunicado.rotulo or "DumTech")
        self.setModal(True)
        self.setFixedWidth(LARGURA)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 24, 28, 22)
        raiz.setSpacing(Space.md)

        topo = QHBoxLayout()
        topo.setSpacing(Space.md)
        topo.addWidget(IconBadge("tag", "accent", size=40, radius=12), 0,
                       Qt.AlignmentFlag.AlignTop)
        marca = QVBoxLayout()
        marca.setSpacing(3)
        etiqueta = QHBoxLayout()
        etiqueta.setSpacing(Space.xs)
        # a etiqueta e a primeira coisa que o olho pega: "Oferta", "Novidade"
        etiqueta.addWidget(Pill(comunicado.rotulo.upper() or "NOVIDADE", "accent"))
        etiqueta.addStretch(1)
        marca.addLayout(etiqueta)
        marca.addWidget(label("DumTech para voce", "dim"))
        topo.addLayout(marca, 1)
        raiz.addLayout(topo)

        titulo = label(comunicado.titulo, "title")
        titulo.setWordWrap(True)
        raiz.addWidget(titulo)

        if comunicado.texto:
            corpo = label(comunicado.texto, "body")
            corpo.setWordWrap(True)
            raiz.addWidget(corpo)

        raiz.addSpacing(Space.xs)
        raiz.addWidget(separator())

        botoes = QHBoxLayout()
        botoes.setSpacing(Space.sm)
        depois = Button("Agora nao", "", "ghost")
        depois.setAutoDefault(False)
        depois.clicked.connect(self.reject)
        botoes.addWidget(depois)
        botoes.addStretch(1)
        self.botao_ver = Button("Quero ver", "external", "primary")
        self.botao_ver.setMinimumHeight(38)
        self.botao_ver.setDefault(True)
        self.botao_ver.clicked.connect(self.accept)
        botoes.addWidget(self.botao_ver)
        raiz.addLayout(botoes)

        apply_window_theme(self, palette_for(parent))
