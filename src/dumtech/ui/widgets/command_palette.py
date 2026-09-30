"""Paleta de comandos: Ctrl+K em qualquer lugar do Hub.

Abre um aplicativo, pula direto para uma tela dele, troca o tema. E o caminho
mais curto entre saber o que voce quer e chegar la - sem passar pelo mouse.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from .. import icons, motion
from ..theme import Palette, Radius, Space, current_palette, font_for
from .common import separator

#: a caixa em si. A janela e maior: a sombra precisa de espaco em volta
LARGURA = 580

#: folga para a sombra caber INTEIRA dentro da janela. Sem isto ela e cortada
#: na borda, e o corte aparece como um risco escuro a direita e embaixo - foi
#: exatamente o que acontecia com margem de 16 e desfoque de 56.
FOLGA = 44
FOLGA_BAIXO = 64
ALTURA_LISTA = 340
LINHA = 44
PAPEL_COMANDO = int(Qt.ItemDataRole.UserRole)


@dataclass(frozen=True)
class Command:
    """Uma coisa que da para fazer daqui."""

    title: str
    hint: str = ""
    icon: str = "grid"
    accent: str = "accent"
    run: Callable[[], None] = field(default=lambda: None)


def _simples(texto: str) -> str:
    """Sem acento e em minusculas: quem digita "orcamento" acha "Orcamentos"."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


def _pontos(titulo: str, busca: str) -> int | None:
    """Menor e melhor. None quando o comando nao serve para a busca."""
    if not busca:
        return 3
    alvo, termo = _simples(titulo), _simples(busca)
    if alvo.startswith(termo):
        return 0
    if any(palavra.startswith(termo) for palavra in alvo.replace(">", " ").split()):
        return 1
    if termo in alvo:
        return 2
    # subsequencia: "vnd" encontra "Vendas"
    resto = iter(alvo)
    if all(letra in resto for letra in termo):
        return 4
    return None


def filtrar(comandos: list[Command], busca: str) -> list[Command]:
    marcados = ((_pontos(c.title, busca), i, c) for i, c in enumerate(comandos))
    validos = [(p, i, c) for p, i, c in marcados if p is not None]
    return [c for _, _, c in sorted(validos, key=lambda t: (t[0], t[1]))]


class _Delegate(QStyledItemDelegate):
    """Uma linha: icone na cor do aplicativo, titulo e o tipo do comando."""

    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette_ = palette

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), LINHA)

    def paint(self, painter: QPainter, option, index) -> None:
        comando: Command = index.data(PAPEL_COMANDO)
        p = self.palette_
        rect: QRect = option.rect
        selecionado = bool(option.state & QStyle.StateFlag.State_Selected)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        if selecionado:
            painter.setBrush(QColor(p.surface_alt))
            painter.drawRoundedRect(QRectF(rect.adjusted(6, 1, -6, -1)), Radius.md, Radius.md)

        # o icone mora num chip tingido da cor do aplicativo, como no Inicio
        cor = p.resolve(comando.accent)
        chip = QRectF(rect.left() + 14, rect.top() + (LINHA - 28) / 2, 28, 28)
        fundo = QColor(cor)
        fundo.setAlpha(46 if p.is_dark else 28)
        painter.setBrush(fundo)
        painter.drawRoundedRect(chip, 8, 8)
        painter.drawPixmap(
            int(chip.x() + 6), int(chip.y() + 6),
            icons.pixmap(comando.icon, cor, 16, width=1.8),
        )

        painter.setFont(font_for("tab"))
        painter.setPen(QColor(p.text))
        painter.drawText(
            QRect(rect.left() + 54, rect.top(), rect.width() - 190, LINHA),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            comando.title,
        )

        if comando.hint:
            painter.setFont(font_for("dim"))
            painter.setPen(QColor(p.text_dim))
            painter.drawText(
                QRect(rect.right() - 160, rect.top(), 136, LINHA),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                comando.hint,
            )
        painter.restore()


class CommandPalette(QDialog):
    """A caixa que abre no meio da janela."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # a janela leva a caixa MAIS a folga da sombra dos dois lados
        self.setFixedWidth(LARGURA + 2 * FOLGA)

        fora = QVBoxLayout(self)
        fora.setContentsMargins(FOLGA, FOLGA, FOLGA, FOLGA_BAIXO)

        self.caixa = QFrame()
        self.caixa.setObjectName("CommandPalette")
        self.sombra = QGraphicsDropShadowEffect(self)
        self.sombra.setBlurRadius(48)
        self.sombra.setOffset(0, 14)
        self.sombra.setColor(QColor(0, 0, 0, 140))
        self.caixa.setGraphicsEffect(self.sombra)
        fora.addWidget(self.caixa)

        dentro = QVBoxLayout(self.caixa)
        dentro.setContentsMargins(0, 0, 0, Space.sm)
        dentro.setSpacing(0)

        self.busca = QLineEdit()
        self.busca.setObjectName("CommandSearch")
        self.busca.setPlaceholderText("Buscar aplicativo, tela ou comando...")
        self.busca.setFont(font_for("subtitle"))
        self._lupa = self.busca.addAction(
            icons.icon("search", current_palette().text_muted, 18),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.busca.textChanged.connect(self._filtrar)
        dentro.addWidget(self.busca)
        dentro.addWidget(separator())

        self.lista = QListWidget()
        self.lista.setObjectName("CommandList")
        self.lista.setFrameShape(QFrame.Shape.NoFrame)
        self.lista.setUniformItemSizes(True)
        self.lista.setMaximumHeight(ALTURA_LISTA)
        self.lista.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lista.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.lista.itemActivated.connect(self._executar)
        self.lista.itemClicked.connect(self._executar)
        dentro.addWidget(self.lista)

        self._comandos: list[Command] = []
        self.busca.installEventFilter(self)

    # ------------------------------------------------------------------ abrir
    def show_for(self, comandos: list[Command], palette: Palette) -> None:
        self._comandos = comandos
        self.lista.setItemDelegate(_Delegate(palette, self.lista))
        self._aplicar_estilo(palette)
        self.busca.clear()
        self._filtrar("")

        pai = self.parentWidget()
        if pai is not None:
            centro = pai.mapToGlobal(pai.rect().center())
            self.adjustSize()
            self.move(centro.x() - self.width() // 2, pai.mapToGlobal(pai.rect().topLeft()).y() + 88)
        self.show()
        motion.abrir_janela(self)
        self.busca.setFocus()

    def _aplicar_estilo(self, p: Palette) -> None:
        # sombra de papel no claro, sombra funda no escuro: a mesma sombra
        # preta nos dois deixava a caixa clara com um halo sujo
        self.sombra.setColor(QColor(0, 0, 0, 150) if p.is_dark else QColor(28, 20, 70, 56))
        self._lupa.setIcon(icons.icon("search", p.text_muted, 18))
        self.caixa.setStyleSheet(
            f"""
            #CommandPalette {{
                background-color: {p.surface};
                border: 1px solid {p.border};
                border-radius: {Radius.xl}px;
            }}
            #CommandSearch {{
                background: transparent;
                border: none;
                border-radius: 0px;
                padding: {Space.lg}px {Space.lg + 2}px {Space.lg}px {Space.sm}px;
                min-height: 26px;
                color: {p.text};
            }}
            #CommandList {{
                background: transparent;
                border: none;
                padding: {Space.sm - 2}px 2px;
            }}
            #CommandList::item {{ border: none; padding: 0px; background: transparent; }}
            """
        )

    # ---------------------------------------------------------------- filtrar
    def _filtrar(self, texto: str) -> None:
        self.lista.clear()
        for comando in filtrar(self._comandos, texto):
            item = QListWidgetItem()
            item.setData(PAPEL_COMANDO, comando)
            item.setSizeHint(QSize(self.lista.viewport().width(), LINHA))
            self.lista.addItem(item)
        if self.lista.count():
            self.lista.setCurrentRow(0)

    def _executar(self, item: QListWidgetItem) -> None:
        comando: Command = item.data(PAPEL_COMANDO)
        self.accept()
        comando.run()

    # ----------------------------------------------------------------- teclado
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.busca and event.type() == event.Type.KeyPress:
            tecla = event.key()
            if tecla in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                total = self.lista.count()
                if total:
                    passo = 1 if tecla == Qt.Key.Key_Down else -1
                    self.lista.setCurrentRow((self.lista.currentRow() + passo) % total)
                return True
            if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self.lista.currentItem()
                if item is not None:
                    self._executar(item)
                return True
        return super().eventFilter(obj, event)
