"""Botoes da plataforma, com icone que acompanha o tema."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import QPushButton, QWidget

from .. import icons
from ..theme import Control, Palette, current_palette, palette_for

#: cor do icone conforme o tipo do botao
TOKEN_POR_VARIANTE = {
    "primary": "on_accent",
    "success": "on_success",
    "danger": "danger",
    "ghost": "text_muted",
    "": "text",
}


class Button(QPushButton):
    """QPushButton padrao: variante + icone recolorido pelo tema."""

    def __init__(
        self,
        text: str = "",
        icon_name: str = "",
        variant: str = "",
        icon_token: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"  {text}" if (text and icon_name) else text, parent)
        self._icon_name = icon_name
        self._token = icon_token or TOKEN_POR_VARIANTE.get(variant, "text")
        self._palette = palette_for(parent) if parent else current_palette()
        if variant:
            self.setProperty("variant", variant)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setIconSize(QSize(16, 16))
        self.setMinimumHeight(Control.default)
        self._refresh_icon()

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self._refresh_icon()

    def set_icon_name(self, icon_name: str) -> None:
        self._icon_name = icon_name
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        if not self._icon_name:
            return
        icone = QIcon()
        icone.addPixmap(icons.pixmap(self._icon_name, self._palette.resolve(self._token), 16),
                        QIcon.Mode.Normal)
        # desligado, o icone apaga junto com o texto. O cinza que o Qt inventa
        # a partir do icone branco do botao primario sumia no fundo claro do
        # botao desligado, e o botao parecia nao ter icone nenhum
        icone.addPixmap(icons.pixmap(self._icon_name, self._palette.text_dim, 16),
                        QIcon.Mode.Disabled)
        self.setIcon(icone)
