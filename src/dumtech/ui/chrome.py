"""A barra de titulo do Windows na cor do programa.

Sem isto, a janela clara ganha uma barra de titulo cinza do sistema por cima
da barra branca do Hub - duas faixas onde deveria haver uma. O Windows 11
aceita a cor da barra, do texto e da borda por janela (DWM); no Windows 10 o
pedido e ignorado sem erro, e fica a barra do sistema.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QWidget

_MODO_ESCURO = 20   # DWMWA_USE_IMMERSIVE_DARK_MODE
_COR_BORDA = 34     # DWMWA_BORDER_COLOR
_COR_BARRA = 35     # DWMWA_CAPTION_COLOR
_COR_TEXTO = 36     # DWMWA_TEXT_COLOR


def _colorref(hex_color: str) -> int:
    cor = QColor(hex_color)
    return cor.red() | (cor.green() << 8) | (cor.blue() << 16)


def pintar(janela: QWidget | None, paleta) -> None:
    """Pinta a barra de titulo de uma janela ja criada pelo sistema.

    Janela que ainda nao existe no Windows fica para o momento em que aparece
    (`motion._Vigia` chama de novo no Show): pedir o identificador antes
    obrigaria o Qt a criar a janela nativa fora de hora.
    """
    if sys.platform != "win32" or janela is None or not janela.isWindow():
        return
    if not janela.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
        return
    try:
        import ctypes

        hwnd = ctypes.c_void_p(int(janela.winId()))
        dwm = ctypes.windll.dwmapi

        def definir(atributo: int, valor: int) -> None:
            dado = ctypes.c_int(valor)
            dwm.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(dado),
                                      ctypes.sizeof(dado))

        definir(_MODO_ESCURO, 1 if paleta.is_dark else 0)
        definir(_COR_BARRA, _colorref(paleta.surface))
        definir(_COR_TEXTO, _colorref(paleta.text))
        definir(_COR_BORDA, _colorref(paleta.border))
    except Exception:  # noqa: BLE001 - cor da barra nunca derruba o programa
        pass


def pintar_abertas() -> None:
    """O tema mudou: repinta a barra de toda janela que esta na tela."""
    from .theme import palette_for

    app = QApplication.instance()
    if app is None:
        return
    for janela in app.topLevelWidgets():
        if janela.isVisible():
            pintar(janela, palette_for(janela))
