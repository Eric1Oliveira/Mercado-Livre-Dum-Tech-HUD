"""Tela Sobre: informacoes da plataforma e onde ficam os dados."""

from __future__ import annotations

import sys

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ... import __version__
from ...core.loja import URL_GUIA, WHATSAPP_SUPORTE
from ...core.paths import get_paths
from ...ui.widgets.buttons import Button
from ...ui.widgets.rolagem import Rolagem
from ...ui.widgets.common import Card, IconBadge, label


class AboutView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        paths = get_paths()

        # a pagina inteira rola: em monitor pequeno isto vira uma barra
        # de rolagem fina em vez de um pedaco da tela faltando
        fora = QVBoxLayout(self)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.setSpacing(0)
        corpo = QWidget()
        fora.addWidget(Rolagem(corpo), 1)
        root = QVBoxLayout(corpo)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(18)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Sobre", "title"))
        titles.addWidget(label("Informações da plataforma DumTech", "subtitle"))
        root.addLayout(titles)

        root.addWidget(self._identity_card())
        root.addWidget(self._suporte_card())
        root.addWidget(self._offline_card())
        root.addWidget(self._data_card(paths))
        root.addStretch(1)
        root.addWidget(
            label(f"Python {sys.version.split()[0]}   ·   PySide6 {pyside_version}", "dim")
        )

    def _identity_card(self) -> Card:
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(IconBadge("grid", "accent", size=56, radius=16))
        text = QVBoxLayout()
        text.setSpacing(3)
        name = label("DumTech Hub", "cardTitle")
        text.addWidget(name)
        text.addWidget(label(f"Versão {__version__}", "muted"))
        description = label(
            "Plataforma que reúne os aplicativos DumTech em um único lugar. Cada "
            "aplicativo é vendido separadamente e aparece aqui quando liberado.",
            "muted",
        )
        description.setWordWrap(True)
        text.addWidget(description)
        row.addLayout(text, 1)
        card.body.addLayout(row)
        return card

    def _suporte_card(self) -> Card:
        card = Card()
        card.body.addWidget(label("Precisa de ajuda?", "section"))
        texto = label(
            "Fale com a DumTech pelo WhatsApp ou abra o guia com a instalação, a ativação "
            "e os primeiros passos.",
            "muted",
        )
        texto.setWordWrap(True)
        card.body.addWidget(texto)

        acoes = QHBoxLayout()
        whatsapp = Button("Falar no WhatsApp", "external")
        whatsapp.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(f"https://wa.me/{WHATSAPP_SUPORTE}"))
        )
        acoes.addWidget(whatsapp)
        guia = Button("Guia de instalação", "external", "ghost")
        guia.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_GUIA)))
        acoes.addWidget(guia)
        acoes.addStretch(1)
        card.body.addLayout(acoes)
        return card

    def _offline_card(self) -> Card:
        card = Card()
        card.body.addWidget(label("Funciona sem internet", "section"))
        text = label(
            "Os aplicativos guardam tudo no próprio computador, em bancos de dados "
            "locais. Nenhuma conexão é necessária para cadastrar produtos, movimentar "
            "estoque ou consultar informações.",
            "muted",
        )
        text.setWordWrap(True)
        card.body.addWidget(text)
        return card

    def _data_card(self, paths) -> Card:
        # sem o caminho e sem o botao de abrir: a pasta e do programa, e mexer
        # nos arquivos dela a mao e o jeito mais rapido de perder dado
        card = Card()
        card.body.addWidget(label("Onde ficam os seus dados", "section"))
        texto = label(
            "Numa pasta protegida deste computador, cuidada pelo próprio DumTech Hub. "
            "Para guardar uma cópia ou levar os dados para outro computador, use "
            "Configurações > Backup.",
            "muted",
        )
        texto.setWordWrap(True)
        card.body.addWidget(texto)
        return card
