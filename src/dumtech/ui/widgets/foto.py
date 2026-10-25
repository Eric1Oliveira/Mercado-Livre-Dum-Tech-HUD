"""Foto de produto: quadrado arredondado que recorta a imagem para caber.

Usada no cadastro do Estoque (clicavel: escolhe a imagem) e no balcao do
Vendas. Sem imagem, desenha um espaco vazio com o icone - nunca um X quebrado.
A imagem chega em bytes (JPEG/PNG), do jeito que o banco guarda.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .. import icons
from ..theme import Palette, Radius, current_palette, palette_for


def imagem_de(dados: bytes | None) -> QImage | None:
    """Bytes do banco -> QImage. Lixo ou vazio vira None, sem excecao."""
    if not dados:
        return None
    imagem = QImage.fromData(dados)
    return None if imagem.isNull() else imagem


def miniatura(dados: bytes | None, tamanho: int, raio: float = Radius.sm,
              escala: float = 2.0) -> QPixmap | None:
    """Quadrado arredondado com a imagem recortada no centro (para listas)."""
    imagem = imagem_de(dados)
    if imagem is None:
        return None
    lado = int(tamanho * escala)
    pix = QPixmap(lado, lado)
    pix.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(pix)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    caminho = QPainterPath()
    caminho.addRoundedRect(QRectF(0, 0, lado, lado), raio * escala, raio * escala)
    pintor.setClipPath(caminho)
    _cobrir(pintor, imagem, QRectF(0, 0, lado, lado))
    pintor.end()
    pix.setDevicePixelRatio(escala)
    return pix


def miniatura_vazia(tamanho: int, palette: Palette, raio: float = Radius.sm,
                    escala: float = 2.0) -> QPixmap:
    """O lugar da foto quando o produto ainda nao tem: discreto, nao alarme."""
    lado = int(tamanho * escala)
    pix = QPixmap(lado, lado)
    pix.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(pix)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    caminho = QPainterPath()
    caminho.addRoundedRect(QRectF(escala / 2, escala / 2, lado - escala, lado - escala),
                           raio * escala, raio * escala)
    pintor.fillPath(caminho, QColor(palette.surface_alt))
    pintor.setPen(QPen(QColor(palette.border_soft), escala))
    pintor.drawPath(caminho)
    glifo = int(lado * 0.5)
    pintor.drawPixmap((lado - glifo) // 2, (lado - glifo) // 2,
                      icons.pixmap("image", palette.text_dim, glifo, width=1.6))
    pintor.end()
    pix.setDevicePixelRatio(escala)
    return pix


def _cobrir(pintor: QPainter, imagem: QImage, alvo: QRectF) -> None:
    """Desenha a imagem preenchendo `alvo` inteiro, cortando o que sobra."""
    escala = max(alvo.width() / imagem.width(), alvo.height() / imagem.height())
    largura, altura = imagem.width() * escala, imagem.height() * escala
    destino = QRectF(
        alvo.x() + (alvo.width() - largura) / 2,
        alvo.y() + (alvo.height() - altura) / 2,
        largura, altura,
    )
    pintor.drawImage(destino, imagem)


class FotoProduto(QWidget):
    """Espaco quadrado da foto. `clicavel` mostra a mao e emite `clicado`."""

    clicado = Signal()

    def __init__(self, tamanho: int = 78, clicavel: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._imagem: QImage | None = None
        self._clicavel = clicavel
        self._palette = palette_for(parent) if parent else current_palette()
        self.setFixedSize(tamanho, tamanho)
        if clicavel:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    @property
    def tem_imagem(self) -> bool:
        return self._imagem is not None

    def set_imagem(self, dados: bytes | None) -> bool:
        """Troca a foto. Devolve False quando nao havia imagem valida."""
        self._imagem = imagem_de(dados)
        self.update()
        return self._imagem is not None

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (assinatura do Qt)
        if self._clicavel and event.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 (assinatura do Qt)
        p = self._palette
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        caminho = QPainterPath()
        caminho.addRoundedRect(rect, Radius.md, Radius.md)

        if self._imagem is not None:
            pintor.save()
            pintor.setClipPath(caminho)
            pintor.fillPath(caminho, QColor("#FFFFFF"))
            _cobrir(pintor, self._imagem, rect)
            pintor.restore()
            pintor.setPen(QPen(QColor(p.border_soft), 1))
            pintor.drawPath(caminho)
        else:
            pintor.fillPath(caminho, QColor(p.surface_alt))
            caneta = QPen(QColor(p.border), 1)
            if self._clicavel:  # "solte uma foto aqui": tracejado convida
                caneta.setStyle(Qt.PenStyle.DashLine)
            pintor.setPen(caneta)
            pintor.drawPath(caminho)
            glifo = max(16, int(self.width() * 0.34))
            pintor.drawPixmap(
                int((self.width() - glifo) / 2), int((self.height() - glifo) / 2),
                icons.pixmap("image", p.text_dim, glifo, width=1.7),
            )
        pintor.end()
