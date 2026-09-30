"""Gera os icones .ico/.png usados pelo executavel e pelo instalador.

    python tools/gerar_icones.py

Os desenhos vem de dumtech/ui/icons.py, entao o icone do programa e sempre o
mesmo que aparece dentro da interface.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dumtech.ui import icons  # noqa: E402

DESTINO = RAIZ / "assets"
TAMANHOS = (16, 24, 32, 48, 64, 128, 256)


def desenhar(nome_icone: str, fundo: str, tamanho: int) -> QPixmap:
    pix = QPixmap(tamanho, tamanho)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    caminho = QPainterPath()
    caminho.addRoundedRect(QRectF(0, 0, tamanho, tamanho), tamanho * 0.22, tamanho * 0.22)
    painter.fillPath(caminho, QColor(fundo))

    glifo = int(tamanho * 0.56)
    desenho = icons.pixmap(nome_icone, "#FFFFFF", glifo, width=2.0)
    painter.drawPixmap(int((tamanho - glifo) / 2), int((tamanho - glifo) / 2), desenho)
    painter.end()
    return pix


def gerar(nome_arquivo: str, nome_icone: str, fundo: str) -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    maior = desenhar(nome_icone, fundo, 256)
    maior.save(str(DESTINO / f"{nome_arquivo}.png"))
    desenhar(nome_icone, fundo, 256).save(str(DESTINO / f"{nome_arquivo}.ico"))
    print("gerado:", DESTINO / f"{nome_arquivo}.ico")


if __name__ == "__main__":
    app = QApplication([])
    gerar("dumtech_hub", "grid", "#2F6BE0")
    gerar("dumtech_estoque", "box", "#7A68F0")
