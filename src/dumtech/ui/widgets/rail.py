"""Menu lateral de secoes (Configuracoes).

O item e desenhado a mao porque precisa de tres coisas que a folha de estilo
do Qt nao entrega: o realce que acende aos poucos sob o mouse, o ponto de
"aberto" e o X de fechar que so aparece sob o mouse. O selecionado vira uma
pilula branca com fio - a mesma linguagem do seletor de telas dos aplicativos.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QVBoxLayout, QWidget

from .. import icons
from ..motion import Realce
from ..theme import Palette, Radius, Space, current_palette, font_for, mix, palette_for
from .common import label
from .indicador import PILULA, Indicador

ROW_HEIGHT = 38
ICON_SIZE = 16
CLOSE_SIZE = 15


class RailItem(QAbstractButton):
    """Uma linha do menu: uma secao das Configuracoes."""

    close_requested = Signal()

    def __init__(
        self,
        text: str,
        icon_name: str,
        accent: str = "accent",
        closable: bool = False,
        toggle: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._accent = accent
        self._closable = closable
        self._open = False
        self._hover = False
        #: anel de foco so aparece para quem navega pelo teclado; com o mouse
        #: ele competiria com o item realmente selecionado.
        self._kb_focus = False
        self._palette = palette_for(parent) if parent else current_palette()
        self._realce = Realce(self)

        self.setText(text)
        self.setCheckable(toggle)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(ROW_HEIGHT)
        self.setFont(font_for("tab"))

    # ------------------------------------------------------------------ estado
    def set_open(self, value: bool) -> None:
        """Aplicativo carregado na memoria (ganha o ponto na cor dele)."""
        if self._open != value:
            self._open = value
            self.update()

    @property
    def is_open(self) -> bool:
        return self._open

    def set_icon_name(self, icon_name: str) -> None:
        self._icon_name = icon_name
        self.update()

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(180, ROW_HEIGHT)

    # ------------------------------------------------------------------ desenho
    def _close_rect(self) -> QRect:
        y = (self.height() - CLOSE_SIZE) // 2
        return QRect(self.width() - Space.md - CLOSE_SIZE, y, CLOSE_SIZE, CLOSE_SIZE)

    def _accent_color(self) -> str:
        return self._palette.resolve(self._accent)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, Radius.md, Radius.md)
        realce = self._realce.valor
        # a pilula do item escolhido e do `Indicador` da secao, que desliza de
        # um item para o outro; aqui so o realce do mouse nos outros
        if not self.isChecked() and realce > 0.01:
            fundo = QColor(p.surface_hover)
            fundo.setAlphaF(realce * 0.7)
            painter.fillPath(path, fundo)

        if self._kb_focus and self.hasFocus():
            painter.setPen(QPen(QColor(p.accent), 1.2))
            painter.drawPath(path)

        acesa = 1.0 if self.isChecked() else realce
        cor_icone = self._accent_color() if self.isChecked() else mix(p.text_muted, p.text, realce)
        painter.drawPixmap(
            QPoint(Space.md, (self.height() - ICON_SIZE) // 2),
            icons.pixmap(self._icon_name, cor_icone, ICON_SIZE, width=1.8),
        )

        direita = Space.md + CLOSE_SIZE if (self._closable and self._hover) else Space.xl
        painter.setPen(QColor(mix(p.text_muted, p.text, acesa)))
        painter.setFont(font_for("strong" if self.isChecked() else "tab"))
        texto_rect = QRect(
            Space.md + ICON_SIZE + 10,
            0,
            max(0, self.width() - (Space.md + ICON_SIZE + 10) - direita),
            self.height(),
        )
        painter.drawText(
            texto_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            painter.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, texto_rect.width()),
        )

        if self._closable and self._hover:
            painter.drawPixmap(
                self._close_rect().topLeft(),
                icons.pixmap("close", p.text_muted, CLOSE_SIZE, width=1.8),
            )
        elif self._open and not self.isChecked():
            ponto = QRectF(self.width() - Space.md - 6, self.height() / 2 - 3, 6, 6)
            painter.setBrush(QColor(self._accent_color()))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(ponto)

        painter.end()

    # ------------------------------------------------------------------ eventos
    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self._realce.entrar()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._realce.sair()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._kb_focus = event.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._kb_focus = False
        self.update()
        super().focusOutEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if (
            self._closable
            and event.button() == Qt.MouseButton.LeftButton
            and self._close_rect().contains(event.position().toPoint())
        ):
            self.close_requested.emit()
            return
        super().mousePressEvent(event)


class RailSection(QWidget):
    """Um grupo do menu: rotulo + itens. Some quando esta vazio."""

    def __init__(self, titulo: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(2)

        self.header = label(titulo, "overline") if titulo else None
        if self.header is not None:
            self.header.setContentsMargins(Space.md, Space.md, 0, Space.xs)
            coluna.addWidget(self.header)

        self.items = QVBoxLayout()
        self.items.setContentsMargins(0, 0, 0, 0)
        self.items.setSpacing(2)
        coluna.addLayout(self.items)

        self.indicador = Indicador(self, forma=PILULA, raio=Radius.md)

    def add(self, item: RailItem) -> RailItem:
        self.items.addWidget(item)
        self.indicador.registrar(item)
        return item

    def selecionar(self, item: RailItem | None) -> None:
        """Leva a pilula ate o item escolhido, deslizando."""
        self.indicador.selecionar(item)

    def clear(self) -> None:
        while self.items.count():
            entrada = self.items.takeAt(0)
            widget = entrada.widget() if entrada else None
            if widget is not None:
                self.indicador.remover(widget)
                widget.setParent(None)
                widget.deleteLater()

    def set_empty(self, empty: bool) -> None:
        self.setVisible(not empty)
