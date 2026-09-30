"""Desenha um QR Code como QPixmap.

Mesmo desenho de `ui/icons.py`: a biblioteca `qrcode` devolve a matriz e quem
pinta e o QPainter. Sem PIL - a matriz basta, e uma dependencia de imagem
inteira para preencher quadradinhos nao se justifica.

**O QR sai sempre preto no branco, inclusive no tema escuro.** E a unica coisa
da plataforma que ignora o tema, e ignora de proposito: leitor de celular
espera modulo escuro em fundo claro, e QR invertido falha em muito aparelho.
Falhar aqui e o cliente parado no balcao sem conseguir pagar - vale mais que a
tela fique com um retangulo branco no meio do escuro.
"""

from __future__ import annotations

import qrcode
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

#: correcao media: sobra folga para reflexo e tela suja sem inchar o codigo
CORRECAO = qrcode.constants.ERROR_CORRECT_M

#: a margem clara que o leitor precisa para achar o codigo (em modulos)
MARGEM = 4

PRETO = "#000000"
BRANCO = "#FFFFFF"


def matriz(texto: str) -> list[list[bool]]:
    """Os modulos do QR, com a margem clara ja em volta."""
    codigo = qrcode.QRCode(error_correction=CORRECAO, border=MARGEM)
    codigo.add_data(texto)
    codigo.make(fit=True)
    return codigo.get_matrix()


def pixmap(texto: str, lado: int = 190) -> QPixmap:
    """O QR num quadrado de `lado` pixels, pronto para um QLabel.

    O lado real e arredondado para um multiplo do numero de modulos: modulo com
    tamanho quebrado vira linha borrada, e borrado o leitor perde.
    """
    modulos = matriz(texto)
    total = len(modulos)
    escala = max(1, round(lado / total))
    tamanho = total * escala

    imagem = QPixmap(tamanho, tamanho)
    imagem.fill(QColor(BRANCO))

    painter = QPainter(imagem)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(PRETO))
    for linha, colunas in enumerate(modulos):
        for coluna, aceso in enumerate(colunas):
            if aceso:
                painter.drawRect(coluna * escala, linha * escala, escala, escala)
    painter.end()
    return imagem
