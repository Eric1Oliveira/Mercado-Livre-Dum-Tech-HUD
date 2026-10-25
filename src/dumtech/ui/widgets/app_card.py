"""Cartoes de aplicativo da tela Inicio.

O cartao inteiro e o botao - nao existe um "Abrir" repetido sete vezes. O fundo,
a borda e o realce sao pintados aqui porque dependem da cor do aplicativo, que
vem do manifesto e nao da paleta do tema.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ...core.app_module import AppManifest
from ..motion import Realce
from ..theme import Palette, Radius, Space, current_palette, mix, palette_for
from .common import IconBadge, label

CARD_WIDTH = 284
CARD_HEIGHT = 150
ROW_HEIGHT = 56


class _CardBase(QWidget):
    """Superficie clicavel que acende na cor do aplicativo sob o mouse.

    `moldura=False` e a linha que mora dentro de outro cartao (o "Continuar"):
    ela nao desenha borda propria, so o realce - cartao dentro de cartao com
    duas molduras e ruido.
    """

    clicked = Signal(str)

    def __init__(self, manifest: AppManifest, parent: QWidget | None = None,
                 moldura: bool = True) -> None:
        super().__init__(parent)
        self.manifest = manifest
        self._moldura = moldura
        self._palette = palette_for(parent) if parent else current_palette()
        self._realce = Realce(self)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    # ------------------------------------------------------------------ desenho
    def paintEvent(self, event) -> None:  # noqa: N802
        p = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        realce = 1.0 if self.hasFocus() else self._realce.valor
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        corpo = QPainterPath()
        raio = Radius.lg if self._moldura else Radius.md
        corpo.addRoundedRect(rect, raio, raio)

        if self._moldura:
            painter.fillPath(corpo, QColor(p.surface))
            # a cor do aplicativo so aparece no fio, e so sob o mouse: parado,
            # o cartao e tao quieto quanto os outros
            borda = mix(p.border_soft, self.manifest.accent, realce * 0.85)
            painter.setPen(QPen(QColor(borda), 1.2 if realce > 0.5 else 1.0))
            painter.drawPath(corpo)
        elif realce > 0.01:
            fundo = QColor(p.surface_alt)
            fundo.setAlphaF(realce)
            painter.fillPath(corpo, fundo)
            if self.hasFocus():
                painter.setPen(QPen(QColor(p.accent), 1.2))
                painter.drawPath(corpo)
        painter.end()

    # ------------------------------------------------------------------ eventos
    def enterEvent(self, event) -> None:  # noqa: N802
        self._realce.entrar()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._realce.sair()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().focusOutEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit(self.manifest.app_id)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(self.manifest.app_id)
            return
        super().keyPressEvent(event)


class AppCard(_CardBase):
    """Cartao do catalogo: emblema, nome, o que o aplicativo faz e o ultimo uso."""

    def __init__(
        self,
        manifest: AppManifest,
        last_opened: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(manifest, parent)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)

        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(Space.lg + 2, Space.lg, Space.lg + 2, Space.md + 2)
        coluna.setSpacing(0)

        topo = QHBoxLayout()
        topo.setSpacing(Space.sm)
        topo.addWidget(IconBadge(manifest.icon, manifest.accent, size=40, radius=12))
        topo.addStretch(1)
        topo.addWidget(IconBadge("arrow-up-right", "text_muted", size=26, radius=8,
                                 estilo="chip"), 0, Qt.AlignmentFlag.AlignTop)
        coluna.addLayout(topo)
        coluna.addSpacing(Space.md + 2)

        coluna.addWidget(label(manifest.short_name, "cardTitle"))
        coluna.addSpacing(3)
        descricao = label(manifest.description, "caption")
        descricao.setWordWrap(True)
        descricao.setAlignment(Qt.AlignmentFlag.AlignTop)
        coluna.addWidget(descricao, 1)

        coluna.addWidget(label(last_opened or f"Versão {manifest.version}", "dim"))


class ContinueCard(_CardBase):
    """Atalho para o aplicativo que voce estava usando.

    E uma linha dentro do cartao "Continuar", nao um cartao solto: tres caixas
    do mesmo tamanho em fila e o jeito mais rapido de fazer uma tela parecer
    template - e "continuar" e atalho, nao noticia.
    """

    def __init__(
        self,
        manifest: AppManifest,
        hint: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(manifest, parent, moldura=False)
        self.setFixedHeight(ROW_HEIGHT)
        self.setMinimumWidth(230)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(Space.sm, Space.xs, Space.md, Space.xs)
        linha.setSpacing(Space.md)
        linha.addWidget(IconBadge(manifest.icon, manifest.accent, size=36, radius=10))

        texto = QVBoxLayout()
        texto.setSpacing(1)
        texto.addWidget(label(manifest.short_name, "strong"))
        # o "quando" e consulta, nao chamada: fica no tom mais baixo
        if hint:
            texto.addWidget(label(hint, "dim"))
        linha.addLayout(texto, 1)
        linha.addWidget(IconBadge("arrow-up-right", "text_muted", size=26, radius=8,
                                  estilo="chip"))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(240, ROW_HEIGHT)
