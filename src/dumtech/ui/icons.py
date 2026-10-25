"""Icones da plataforma, desenhados em SVG dentro do proprio codigo.

Vantagem: nao existe pasta de imagens para se perder no empacotamento, os
icones acompanham a cor do tema e ficam nitidos em qualquer resolucao.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import current_palette

#: Desenhos (traco) em uma area de 24x24.
PATHS: dict[str, str] = {
    "box": "M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z M3 7.5 12 12l9-4.5 M12 12v9",
    "grid": "M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z",
    "key": "M8 19a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M11 12l9-9 M17 6l3 3 M14 9l3 3",
    "info": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v6 M12 7.6h.01",
    "plus": "M12 5v14 M5 12h14",
    "minus": "M5 12h14",
    "edit": "M4 20h4l10-10a2.83 2.83 0 0 0-4-4L4 16v4z M13.5 6.5l4 4",
    "trash": "M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13 M10 11v6 M14 11v6",
    "search": "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z M21 21l-4.35-4.35",
    "in": "M12 4v13 M6 12l6 6 6-6",
    "out": "M12 20V7 M6 12l6-6 6 6",
    "alert": "M12 3.5 22 20H2L12 3.5z M12 9.5v5 M12 17.4h.01",
    "refresh": "M20.5 12a8.5 8.5 0 1 1-2.8-6.3 M20.5 3.5v5h-5",
    "back": "M14.5 5.5 8 12l6.5 6.5",
    "forward": "M9.5 5.5 16 12l-6.5 6.5",
    "close": "M6 6l12 12 M18 6 6 18",
    "dashboard": "M4 4h16v16H4z M4 10h16 M10 10v10",
    "list": "M8 6h13 M8 12h13 M8 18h13 M3.6 6h.01 M3.6 12h.01 M3.6 18h.01",
    "swap": "M4 8h13 M14 5l3 3-3 3 M20 16H7 M10 13l-3 3 3 3",
    "external": "M14 4h6v6 M20 4l-8.5 8.5 M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
    "check": "M5 12.5 10 17.5 19.5 7",
    "home": "M4 10.5 12 4l8 6.5V20h-5v-6h-6v6H4z",
    "tag": "M3 12V4h8l9 9-8 8-9-9z M7.5 7.6h.01",
    "shield": "M12 3.2 20 6v6c0 4.4-3.2 7.6-8 8.8C7.2 19.6 4 16.4 4 12V6l8-2.8z",
    "sun": "M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9z M12 2.6v2.2 M12 19.2v2.2 M4.2 4.2l1.6 1.6 M18.2 18.2l1.6 1.6 M2.6 12h2.2 M19.2 12h2.2 M4.2 19.8l1.6-1.6 M18.2 5.8l1.6-1.6",
    "moon": "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z",
    "money": "M3 6h18v12H3z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M6.5 9.5h.01 M17.5 14.5h.01",
    "users": "M9 11.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M2.5 20a6.5 6.5 0 0 1 13 0 M17 5.2a3.5 3.5 0 0 1 0 6.6 M18 14.4a6.5 6.5 0 0 1 3.5 5.6",
    "file": "M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7l-4-4z M14 3v4h4 M9 12.5h6 M9 16.5h6",
    "calendar": "M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M4 10h16 M8.5 3v4 M15.5 3v4 M8 14h.01 M12 14h.01 M16 14h.01",
    "wrench": "M20.5 6.2a5.5 5.5 0 0 1-7.3 7.3L6 20.7a2 2 0 0 1-2.8-2.8l7.2-7.2a5.5 5.5 0 0 1 7.3-7.3l-3.2 3.2 2.8 2.8 3.2-3.2z",
    "cart": "M3 4h2.2l2.3 11.2a1.5 1.5 0 0 0 1.5 1.2h8.4a1.5 1.5 0 0 0 1.5-1.2L21 8H6 M9.5 20.5h.01 M17.5 20.5h.01",
    "clock": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7.5V12l3 2",
    "chat": "M5 5h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H9.5L5 19.5V6a1 1 0 0 1 1-1z M8.5 9.5h.01 M12 9.5h.01 M15.5 9.5h.01",
    "chart": "M4 20V10 M10 20V4 M16 20v-7 M21 20H3",
    "caret-down": "M6 9.5 12 15.5 18 9.5",
    "caret-up": "M6 14.5 12 8.5 18 14.5",
    "arrow-up-right": "M7 17 17 7 M8.5 7H17v8.5",
    "user": "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4.5 20.5a7.5 7.5 0 0 1 15 0",
    "logout": "M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3 M10 16l4-4-4-4 M14 12H4",
    "phone": "M8 2.5h8a2 2 0 0 1 2 2v15a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-15a2 2 0 0 1 2-2z M11 18.5h2",
    "lock": "M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z M8.5 11V8a3.5 3.5 0 0 1 7 0v3 M12 15v2",
    "image": "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z M9 10.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z M20 15l-4.5-4.5L6 20",
}

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
    'stroke-linejoin="round">{shapes}</svg>'
)


def _svg(name: str, color: str, width: float) -> bytes:
    shapes = "".join(f'<path d="{part}"/>' for part in [PATHS.get(name, PATHS["box"])])
    return _TEMPLATE.format(color=color, width=width, shapes=shapes).encode("utf-8")


@lru_cache(maxsize=256)
def pixmap(name: str, color: str = "", size: int = 20, width: float = 1.8) -> QPixmap:
    color = color or current_palette().text
    renderer = QSvgRenderer(QByteArray(_svg(name, color, width)))
    scale = 2  # renderiza no dobro para ficar nitido em telas HiDPI
    pix = QPixmap(size * scale, size * scale)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    pix.setDevicePixelRatio(scale)
    return pix


@lru_cache(maxsize=256)
def icon(name: str, color: str = "", size: int = 20, width: float = 1.8) -> QIcon:
    return QIcon(pixmap(name, color, size, width))


def asset(name: str, color: str = "", size: int = 14, width: float = 2.2) -> str:
    color = color or current_palette().text_muted
    """Grava o icone como arquivo .svg e devolve o caminho para uso em QSS.

    A folha de estilo do Qt so aceita imagem vinda de arquivo; por isso os
    icones usados em setas de combo/spin sao gravados uma vez na pasta de
    cache do usuario.
    """
    from ..core.paths import get_paths

    cache = get_paths().root / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    arquivo = cache / f"{name}_{color.lstrip('#')}_{size}.svg"
    if not arquivo.exists():
        arquivo.write_bytes(_svg(name, color, width))
    return arquivo.as_posix()
