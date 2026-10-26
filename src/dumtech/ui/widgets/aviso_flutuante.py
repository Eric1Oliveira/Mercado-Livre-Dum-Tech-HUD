"""O aviso que aparece no canto do Hub quando algo chega sozinho.

Hoje: o cliente marcou (ou cancelou) um horario pelo link de agendamento. O
dono pode estar no Balcao, vendendo - o aviso aparece no canto de baixo, diz o
que chegou e some sozinho em alguns segundos. "Ver" leva ao aplicativo.

Nao e um dialogo de proposito: nao rouba o foco, nao exige clique e nao para
ninguem no meio de uma venda. Com o mouse em cima, ele espera.

O cartao e a sombra sao pintados aqui, e nao com QGraphicsDropShadowEffect: o
efeito some em parte das capturas (os videos do Passo a passo) e briga com o
efeito de entrada das telas (`ui/motion.py`).
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ..theme import Palette, palette_for
from .buttons import Button
from .common import IconBadge, label

#: folga em volta do cartao para a sombra (esquerda, cima, direita, baixo)
SOMBRA = (14, 10, 14, 20)
RAIO = 14


class AvisoFlutuante(QFrame):
    """Um cartao so, no canto inferior direito da janela que o recebe."""

    MARGEM = 12
    LARGURA = 420
    DURACAO_MS = 9000

    def __init__(self, janela: QWidget) -> None:
        super().__init__(janela)
        self._palette = palette_for(janela)
        self.setFixedWidth(self.LARGURA)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._acao: Callable[[], None] | None = None

        esquerda, topo, direita, baixo = SOMBRA
        linha = QHBoxLayout(self)
        linha.setContentsMargins(esquerda + 16, topo + 14, direita + 12, baixo + 14)
        linha.setSpacing(12)
        self.icone = IconBadge("link", "accent", size=36, radius=11)
        linha.addWidget(self.icone, 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        self.titulo = label("", "caption")
        self.texto = label("", "strong")
        self.texto.setWordWrap(True)
        textos.addWidget(self.titulo)
        textos.addWidget(self.texto)
        linha.addLayout(textos, 1)

        self.botao_ver = Button("Ver", "", "ghost")
        self.botao_ver.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_ver.clicked.connect(self._ver)
        linha.addWidget(self.botao_ver, 0, Qt.AlignmentFlag.AlignVCenter)

        self._relogio = QTimer(self)
        self._relogio.setSingleShot(True)
        self._relogio.setInterval(self.DURACAO_MS)
        self._relogio.timeout.connect(self.hide)
        self.hide()
        janela.installEventFilter(self)

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def mostrar(self, texto: str, titulo: str = "", icone: str = "link", cor: str = "accent",
                acao: Callable[[], None] | None = None) -> None:
        self.titulo.setText(titulo)
        self.titulo.setVisible(bool(titulo))
        self.texto.setText(texto)
        self.icone.set_icon_name(icone)
        self.icone.set_color(cor)
        self._acao = acao
        self.botao_ver.setVisible(acao is not None)
        self.adjustSize()
        self._posicionar()
        self.raise_()
        self.show()
        self._relogio.start()

    def _posicionar(self) -> None:
        janela = self.parentWidget()
        if janela is not None:
            self.move(janela.width() - self.width() - self.MARGEM,
                      janela.height() - self.height() - self.MARGEM)

    def _ver(self) -> None:
        self.hide()
        if self._acao is not None:
            self._acao()

    # ------------------------------------------------------------------ desenho
    def paintEvent(self, event) -> None:  # noqa: N802
        p = self._palette
        esquerda, topo, direita, baixo = SOMBRA
        cartao = QRectF(self.rect()).adjusted(esquerda, topo, -direita, -baixo)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # a sombra: camadas cada vez maiores e mais fracas, puxadas para baixo
        for passo in range(10, 0, -1):
            sombra = QPainterPath()
            folga = passo * 1.2
            sombra.addRoundedRect(cartao.adjusted(-folga, -folga + 4, folga, folga + 6),
                                  RAIO + folga, RAIO + folga)
            pintor.fillPath(sombra, QColor(0, 0, 0, 5 if p.is_dark else 4))
        caixa = QPainterPath()
        caixa.addRoundedRect(cartao, RAIO, RAIO)
        pintor.fillPath(caixa, QColor(p.surface))
        pintor.setPen(QPen(QColor(p.border), 1))
        pintor.drawPath(caixa)
        pintor.end()

    # ------------------------------------------------------------------ eventos
    def eventFilter(self, objeto, evento) -> bool:  # noqa: N802
        if objeto is self.parentWidget() and evento.type() == QEvent.Type.Resize and self.isVisible():
            self._posicionar()
        return False

    def enterEvent(self, evento) -> None:  # noqa: N802
        self._relogio.stop()          # lendo: nao some na cara de ninguem
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:  # noqa: N802
        self._relogio.start()
        super().leaveEvent(evento)

    def mousePressEvent(self, evento) -> None:  # noqa: N802
        self.hide()                   # clicou no cartao: entendido
