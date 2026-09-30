"""Pecas visuais reutilizadas pelo Hub e por todos os aplicativos.

Todo widget que desenha cor propria expoe `apply_theme(palette)`: quando o tema
muda, a plataforma percorre a janela chamando esse metodo.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..theme import (
    Metrics,
    Palette,
    Radius,
    Space,
    apply_type,
    current_palette,
    palette_for,
    tom_visivel,
)


def label(text: str, role: str = "", parent: QWidget | None = None) -> QLabel:
    """QLabel com um papel do sistema visual (title, section, overline...).

    O papel define a cor pela folha de estilo e o tamanho/peso/tracking pelo
    QFont - Qt nao aceita `letter-spacing` em folha de estilo, entao a
    tipografia mora em `theme.TYPE`.
    """
    item = QLabel(text, parent)
    if role:
        item.setProperty("role", role)
        apply_type(item, role)
    return item


def overline(text: str, parent: QWidget | None = None) -> QLabel:
    """Titulo de secao de uma pagina.

    Um titulo de secao precisa ter presenca de titulo, senao ele nao organiza
    nada. Para o rotulo pequeno que vive DENTRO de um cartao ou de um campo,
    use `label(texto, "field")`: sao coisas diferentes.
    """
    return label(text, "section", parent)


def tone_label(text: str, tone: str = "text", role: str = "") -> QLabel:
    """QLabel colorido por token do tema (success, danger, warning...)."""
    item = label(text, role)
    item.setProperty("tone", tone)
    return item


def repolish(widget: QWidget) -> None:
    """Reaplica a folha de estilo depois de trocar uma propriedade dinamica."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def separator(sentido: str = "h", tracejado: bool = False) -> QFrame:
    """Fio de um pixel. `"v"` para o fio vertical que separa colunas.

    `tracejado` e o fio entre as linhas de uma lista dentro de um cartao: ele
    separa sem cortar - um fio cheio ali parecia uma tabela.
    """
    line = QFrame()
    line.setProperty("role", "dash" if tracejado else "separator")
    if sentido == "v":
        line.setFixedWidth(1)
    else:
        line.setFixedHeight(1)
    return line


def menu_arredondado(parent: QWidget | None = None) -> QMenu:
    """QMenu com os cantos redondos de verdade.

    A folha de estilo arredonda a borda, mas a janela do menu continua
    quadrada: sem fundo transparente, os quatro cantos apareciam como pontas
    de outra cor por fora da curva.
    """
    menu = QMenu(parent)
    menu.setWindowFlags(
        menu.windowFlags()
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.NoDropShadowWindowHint
    )
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    return menu


class Card(QFrame):
    """Caixa arredondada padrao da plataforma (branca, com fio)."""

    def __init__(self, parent: QWidget | None = None, padding: int = Metrics.padding) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(12)


class IconBadge(QWidget):
    """Quadrado arredondado com um icone no centro.

    A cor pode ser um #hex fixo (ex.: a cor do aplicativo) ou o nome de um token
    do tema (ex.: "accent", "warning"), que acompanha a troca de tema.

    Quatro jeitos de pintar (`estilo`):

    * ``tint``  - fundo tingido da cor, icone na cor (identidade, urgencia);
    * ``solid`` - fundo cheio da cor, icone branco (a marca do Hub);
    * ``chip``  - fundo branco com fio, icone neutro (rotulo de um numero);
    * ``glass`` - vidro claro sobre o degrade violeta do Inicio.
    """

    def __init__(
        self,
        icon_name: str,
        color: str = "accent",
        size: int = 56,
        radius: int = 16,
        parent: QWidget | None = None,
        estilo: str = "tint",
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._token = color
        self._estilo = estilo
        self._palette = palette_for(parent) if parent else current_palette()
        self._radius = radius
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_color(self, color: str) -> None:
        self._token = color
        self.update()

    def set_icon_name(self, icon_name: str) -> None:
        self._icon_name = icon_name
        self.update()

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (assinatura do Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        p = self._palette
        cor = p.resolve(self._token)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)

        if self._estilo == "solid":
            painter.fillPath(path, QColor(cor))
            glifo_cor = "#FFFFFF"
        elif self._estilo == "glass":
            vidro = QColor("#FFFFFF")
            vidro.setAlpha(46)
            painter.fillPath(path, vidro)
            borda = QColor("#FFFFFF")
            borda.setAlpha(70)
            painter.setPen(QPen(borda, 1))
            painter.drawPath(path)
            glifo_cor = "#FFFFFF"
        elif self._estilo == "chip":
            painter.fillPath(path, QColor(p.surface_hover if p.is_dark else p.surface))
            painter.setPen(QPen(QColor(p.border_soft), 1))
            painter.drawPath(path)
            glifo_cor = cor
        else:
            fundo = QColor(cor)
            fundo.setAlpha(46 if p.is_dark else 28)
            painter.fillPath(path, fundo)
            glifo_cor = cor

        glifo = max(14, int(self.width() * 0.46))
        painter.drawPixmap(
            int((self.width() - glifo) / 2),
            int((self.height() - glifo) / 2),
            icons.pixmap(self._icon_name, glifo_cor, glifo, width=1.9),
        )
        painter.end()


class Pill(QLabel):
    """Etiqueta pequena de status (Disponivel, Estoque baixo, Pago...)."""

    def __init__(self, text: str, tone: str = "muted", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self.setProperty("pill", tone)
        repolish(self)


class StatCard(QFrame):
    """Um numero de painel: chip com icone e rotulo, numero grande, apoio.

    E um bloco cinza sem fio, e nao um cartao branco com moldura: quatro
    molduras lado a lado competiam entre si, e o bloco cinza agrupa sem
    desenhar borda nenhuma. O icone fica num chip neutro - ele ajuda a achar
    o numero de longe, mas nao grita.

    O tom passa por `tom_visivel`: o numero so fica colorido quando ele pede
    acao. Ver a regra em `ui/theme.py`.
    """

    def __init__(
        self,
        title: str,
        value: str = "0",
        icon_name: str = "box",
        tone: str = "accent",
        hint: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tone = tone
        self.setProperty("role", "tile")
        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(Space.lg, Space.lg - 2, Space.lg, Space.lg - 2)
        coluna.setSpacing(2)

        topo = QHBoxLayout()
        topo.setSpacing(10)
        self.icone = IconBadge(icon_name, "text_muted", size=28, radius=8, estilo="chip")
        topo.addWidget(self.icone)
        self.title_label = label(title, "field")
        topo.addWidget(self.title_label, 1)
        coluna.addLayout(topo)
        coluna.addSpacing(Space.sm)

        self.value_label = tone_label(value, tom_visivel(tone), "metric")
        coluna.addWidget(self.value_label)

        self.hint_label = label(hint, "dim")
        self.hint_label.setWordWrap(True)
        # no layout primeiro: `setVisible` sem pai abriria uma janela solta
        coluna.addWidget(self.hint_label)
        self.hint_label.setVisible(bool(hint))
        coluna.addStretch(1)

    def set_value(self, value: str, hint: str = "") -> None:
        self.value_label.setText(value)
        self.hint_label.setText(hint)
        self.hint_label.setVisible(bool(hint))

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        self.value_label.setProperty("tone", tom_visivel(tone))
        repolish(self.value_label)


class FaixaDeNumeros(Card):
    """Os numeros de um painel lado a lado, cada um no seu bloco cinza.

    E a mesma peca do Inicio do Hub, e e ela que faz a plataforma inteira
    parecer um produto so: a fileira tem sempre o mesmo ritmo - blocos do
    mesmo tamanho, o mesmo respiro entre eles.
    """

    def __init__(self, *cartoes: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=0)
        self.setProperty("role", "plain")
        self.linha = QHBoxLayout()
        self.linha.setContentsMargins(0, 0, 0, 0)
        self.linha.setSpacing(Space.md)
        self.body.addLayout(self.linha)
        for cartao in cartoes:
            self.add(cartao)

    def add(self, cartao: QWidget, peso: int = 1) -> QWidget:
        self.linha.addWidget(cartao, peso)
        return cartao


class EmptyState(QWidget):
    """Mensagem amigavel quando ainda nao existem dados."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        icon_name: str = "box",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        holder = QHBoxLayout()
        holder.addStretch(1)
        holder.addWidget(IconBadge(icon_name, "accent", size=56, radius=Radius.lg + 2))
        holder.addStretch(1)
        layout.addLayout(holder)
        layout.addSpacing(Space.xs)

        titulo = label(title, "section")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        if subtitle:
            sub = label(subtitle, "muted")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setWordWrap(True)
            layout.addWidget(sub)
