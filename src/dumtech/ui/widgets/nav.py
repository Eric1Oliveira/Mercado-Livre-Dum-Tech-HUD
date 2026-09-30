"""Botao do menu lateral usado pelo Hub e pelos aplicativos."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QPushButton, QWidget

from .. import icons
from ..theme import Control, Palette, current_palette, palette_for


class NavButton(QPushButton):
    """Item de menu: icone + texto, com estado selecionado.

    O visual vem da folha de estilo global (regras `NavButton`), entao ele
    acompanha a troca de tema sozinho; aqui so o icone precisa ser recolorido.
    """

    def __init__(self, text: str, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._icon_name = icon_name
        self._palette = palette_for(parent) if parent else current_palette()
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(Control.default + 2)
        self.toggled.connect(lambda _: self._refresh_icon())
        self._refresh_icon()

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        cor = self._palette.accent if self.isChecked() else self._palette.text_muted
        self.setIcon(icons.icon(self._icon_name, cor, 18))
