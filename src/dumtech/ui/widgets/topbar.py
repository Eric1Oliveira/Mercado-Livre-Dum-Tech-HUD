"""A barra do topo do Hub: abas, busca e a empresa.

Tudo aqui e pintado a mao porque cada peca precisa de algo que a folha de
estilo do Qt nao faz: o traco da aba que cresce do centro, o ponto de
aplicativo aberto que vira X sob o mouse, a tecla de atalho desenhada dentro
da busca e o avatar redondo com o logotipo da empresa.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QSizePolicy, QWidget

from .. import icons
from ..motion import Progresso, Realce
from ..theme import Palette, Radius, current_palette, font_for, mix, palette_for

ALTURA = 64
#: respiro de cada lado do texto da aba. O ponto e o X moram dentro dele, e
#: nao num espaco a mais: assim o vao entre as abas e sempre o mesmo, com o
#: aplicativo aberto ou fechado
PAD = 17


class _Pintado(QAbstractButton):
    """O que as pecas da barra tem em comum: tema, realce e foco de teclado."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette_for(parent) if parent else current_palette()
        self._realce = Realce(self)
        self._hover = False
        #: anel de foco so para quem chegou pelo teclado; com o mouse ele
        #: competiria com o item realmente selecionado
        self._kb_focus = False
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

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

    def _anel(self) -> bool:
        return self._kb_focus and self.hasFocus()


class NavTab(_Pintado):
    """Uma aba do topo: Inicio ou um aplicativo.

    O traco embaixo mostra onde voce esta - na cor do aplicativo, que e o que
    diferencia estar no Vendas de estar no Estoque. Ele (e a pilula que segue
    o mouse) e pintado pelo `Indicador` da barra, que anda de uma aba para a
    outra; a aba diz onde ele assenta (`area_indicador`, `area_realce`).
    Aplicativo aberto em segundo plano ganha um ponto na mesma cor embaixo do
    nome, como no dock; sob o mouse aparece um X pequeno no canto do nome.
    """

    close_requested = Signal()

    def __init__(
        self,
        text: str,
        accent: str = "text",
        closable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._accent = accent
        self._closable = closable
        self._open = False
        self.setText(text)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(ALTURA - 1)
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
        """Mantido pela API do trilho antigo: a aba do topo nao tem icone."""

    def _largura_texto(self) -> float:
        return QFontMetricsF(font_for("tab")).horizontalAdvance(self.text())

    def sizeHint(self) -> QSize:  # noqa: N802
        largura = PAD * 2 + self._largura_texto()
        return QSize(int(largura + 0.99), ALTURA - 1)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def _botao_fechar(self) -> QRectF:
        return QRectF(PAD + self._largura_texto() + 1, self.height() / 2 - 16, 13, 13)

    def _close_rect(self) -> QRect:
        # a area de clique e maior que o desenho: X de 13px e alvo dificil
        return self._botao_fechar().adjusted(-3, -3, 3, 3).toRect()

    @property
    def accent(self) -> str:
        return self._accent

    def area_indicador(self) -> QRectF:
        """Onde o traco da selecao assenta: embaixo do texto, um pouco mais largo."""
        return QRectF(PAD - 5, self.height() - 3, self._largura_texto() + 10, 3)

    def area_realce(self) -> QRectF:
        """Onde a pilula do mouse assenta: a aba inteira, com folga nas pontas."""
        return QRectF(4, self.height() / 2 - 17, self.width() - 8, 34)

    # ------------------------------------------------------------------ desenho
    def paintEvent(self, event) -> None:  # noqa: N802
        p = self._palette
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fonte = font_for("tab")
        pintor.setFont(fonte)
        largura_texto = self._largura_texto()
        altura = self.height()

        acesa = 1.0 if self.isChecked() else self._realce.valor
        pintor.setPen(QColor(mix(p.text_muted, p.text, acesa)))
        pintor.drawText(
            QRectF(PAD, 0, largura_texto + 2, altura),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self.text(),
        )

        # o traco da selecao e o realce do mouse nao sao desenhados aqui: quem
        # pinta e o `Indicador` da barra, que anda de uma aba para a outra

        if self._closable and self._open:
            if self._hover:
                # fechar e raro e trocar e comum: o X e pequeno e fica no canto
                caixa = self._botao_fechar()
                pintor.setPen(QPen(QColor(p.border), 1))
                pintor.setBrush(QColor(p.surface_alt))
                pintor.drawEllipse(caixa)
                pintor.drawPixmap(
                    QPoint(int(caixa.x() + 2.5), int(caixa.y() + 2.5)),
                    icons.pixmap("close", p.text_muted, 8, width=2.8),
                )
            elif not self.isChecked():
                pintor.setPen(Qt.PenStyle.NoPen)
                pintor.setBrush(QColor(p.resolve(self._accent)))
                pintor.drawEllipse(QRectF(PAD + largura_texto / 2 - 2.5, altura - 12, 5, 5))

        if self._anel():
            pintor.setPen(QPen(QColor(p.accent), 1.2))
            pintor.setBrush(Qt.BrushStyle.NoBrush)
            pintor.drawRoundedRect(QRectF(3.5, altura / 2 - 15, self.width() - 7, 30),
                                   Radius.sm, Radius.sm)
        pintor.end()

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if (
            self._closable
            and self._open
            and event.button() == Qt.MouseButton.LeftButton
            and self._close_rect().contains(event.position().toPoint())
        ):
            self.close_requested.emit()
            return
        super().mousePressEvent(event)


class BotaoTema(_Pintado):
    """O botao de tema: o sol e a lua trocam de lugar girando.

    E daqui que nasce o circulo da troca de tema (`motion.revelar_tema`), e o
    icone girando no centro dele e o que diz "a troca comecou aqui".
    """

    LADO = 38

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icone = "sun"
        self._anterior = ""
        self._giro = Progresso(self, 380)
        self.setFixedSize(self.LADO, self.LADO)

    def set_icon_name(self, icon_name: str) -> None:
        if icon_name == self._icone:
            return
        self._anterior, self._icone = self._icone, icon_name
        self._giro.reiniciar()

    @property
    def icon_name(self) -> str:
        return self._icone

    def paintEvent(self, event) -> None:  # noqa: N802
        p = self._palette
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        realce = self._realce.valor
        caixa = QPainterPath()
        caixa.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1),
                             Radius.md, Radius.md)
        pintor.fillPath(caixa, QColor(mix(p.surface, p.surface_alt, realce)))
        borda = p.accent if self._anel() else mix(p.border, p.border_strong, realce)
        pintor.setPen(QPen(QColor(borda), 1))
        pintor.drawPath(caixa)

        # cor fixa por estado (e nao misturada quadro a quadro): o icone vem de
        # um cache, e cada tom intermediario seria um desenho novo guardado
        cor = p.text if realce > 0.5 else p.text_muted
        passo = self._giro.valor
        if self._anterior and passo < 1.0:
            self._glifo(pintor, self._anterior, cor, 90 * passo, 1 - 0.5 * passo,
                        max(0.0, 1 - passo * 1.8))
        entrada = min(1.0, passo * 1.6) if self._anterior else 1.0
        self._glifo(pintor, self._icone, cor, -90 * (1 - passo), 0.5 + 0.5 * passo, entrada)
        pintor.end()

    def _glifo(self, pintor: QPainter, nome: str, cor: str, giro: float,
               escala: float, opacidade: float) -> None:
        if opacidade <= 0.01:
            return
        pintor.save()
        pintor.setOpacity(opacidade)
        pintor.translate(self.width() / 2, self.height() / 2)
        pintor.rotate(giro)
        pintor.scale(escala, escala)
        pintor.drawPixmap(QPointF(-8, -8), icons.pixmap(nome, cor, 16, width=1.9))
        pintor.restore()


class TabStrip(QWidget):
    """Uma fileira de abas. Some quando nao ha nenhuma."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.linha = QHBoxLayout(self)
        self.linha.setContentsMargins(0, 0, 0, 0)
        self.linha.setSpacing(2)

    def add(self, item: QWidget) -> QWidget:
        self.linha.addWidget(item)
        return item

    def clear(self) -> None:
        while self.linha.count():
            entrada = self.linha.takeAt(0)
            widget = entrada.widget() if entrada else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def set_empty(self, empty: bool) -> None:
        self.setVisible(not empty)


class SearchPill(_Pintado):
    """A busca do topo: parece um campo, abre a paleta de comandos.

    Nao e um campo de verdade de proposito - o que se procura aqui (um
    aplicativo, uma tela, uma configuracao) ja tem lugar pronto na paleta, com
    teclado e busca sem acento. A tecla de atalho fica escrita dentro, para
    ensinar o caminho mais curto sem manual.
    """

    LARGURA = 220
    ALTURA = 38

    def __init__(self, texto: str = "Buscar no Hub...", atalho: str = "Ctrl K",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._texto = texto
        self._atalho = atalho
        self._compacto = False
        self.setText(texto)
        self.setFixedSize(self.LARGURA, self.ALTURA)

    @property
    def compacto(self) -> bool:
        return self._compacto

    def set_compacto(self, sim: bool) -> None:
        """Janela estreita: so a lupa, e a busca continua a um clique."""
        if sim == self._compacto:
            return
        self._compacto = sim
        self.setFixedSize(self.ALTURA if sim else self.LARGURA, self.ALTURA)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = self._palette
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        caixa = QPainterPath()
        caixa.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1),
                             Radius.md, Radius.md)
        pintor.fillPath(caixa, QColor(mix(p.bg_soft, p.surface_alt, self._realce.valor * 0.6)))
        borda = p.accent if self._anel() else mix(p.border, p.border_strong, self._realce.valor)
        pintor.setPen(QPen(QColor(borda), 1))
        pintor.drawPath(caixa)

        lupa = 16
        x_lupa = (self.width() - lupa) // 2 if self._compacto else 13
        pintor.drawPixmap(QPoint(x_lupa, (self.height() - lupa) // 2),
                          icons.pixmap("search", p.text_muted, lupa, width=2.0))
        if self._compacto:
            pintor.end()
            return

        fonte_tecla = font_for("kbd")
        largura_tecla = QFontMetricsF(fonte_tecla).horizontalAdvance(self._atalho) + 12
        tecla = QRectF(self.width() - largura_tecla - 9, (self.height() - 20) / 2,
                       largura_tecla, 20)

        pintor.setFont(font_for("body"))
        pintor.setPen(QColor(p.text_dim))
        pintor.drawText(
            QRectF(38, 0, tecla.left() - 44, self.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._texto,
        )

        molde = QPainterPath()
        molde.addRoundedRect(tecla, 5, 5)
        pintor.fillPath(molde, QColor(p.surface_alt))
        pintor.setPen(QPen(QColor(p.border_soft), 1))
        pintor.drawPath(molde)
        pintor.setFont(fonte_tecla)
        pintor.setPen(QColor(p.text_muted))
        pintor.drawText(tecla, int(Qt.AlignmentFlag.AlignCenter), self._atalho)
        pintor.end()


def iniciais(nome: str) -> str:
    """"Casa do Parafuso" -> "CP". Palavra de ligacao nao entra na conta."""
    palavras = [
        palavra for palavra in nome.split()
        if palavra[:1].isalnum() and not (palavra.islower() and len(palavra) <= 3)
    ]
    if not palavras:
        return "DT"
    if len(palavras) == 1:
        return palavras[0][:2].upper()
    return (palavras[0][0] + palavras[1][0]).upper()


class ProfileButton(_Pintado):
    """A empresa no canto: logotipo (ou iniciais), nome e o que esta liberado.

    O clique abre o menu com Licenca, Configuracoes e Sobre - o lugar onde o
    dono espera achar "a conta", e nao espalhado pelo meio da navegacao.
    """

    AVATAR = 36
    ALTURA = 44
    MAX_TEXTO = 180

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._nome = "Sua empresa"
        self._sub = ""
        self._logo: QPixmap | None = None
        self._compacto = False
        self._ativo = False
        self.setFixedHeight(self.ALTURA)
        self.setFixedWidth(self.largura(False))

    # ------------------------------------------------------------------ estado
    def set_empresa(self, nome: str, sub: str = "", logo: QPixmap | None = None) -> None:
        self._nome = nome or "Sua empresa"
        self._sub = sub
        self._logo = logo if logo is not None and not logo.isNull() else None
        self.setText(self._nome)
        self.setFixedWidth(self.largura(self._compacto))
        self.update()

    def set_ativo(self, ativo: bool) -> None:
        """Voce esta numa das telas do menu (Licenca, Configuracoes, Sobre)."""
        if ativo != self._ativo:
            self._ativo = ativo
            self.update()

    @property
    def compacto(self) -> bool:
        return self._compacto

    def set_compacto(self, sim: bool) -> None:
        if sim != self._compacto:
            self._compacto = sim
            self.setFixedWidth(self.largura(sim))

    def _largura_texto(self) -> float:
        nome = QFontMetricsF(font_for("strong")).horizontalAdvance(self._nome)
        sub = QFontMetricsF(font_for("caption")).horizontalAdvance(self._sub)
        return min(max(nome, sub), self.MAX_TEXTO)

    def largura(self, compacto: bool) -> int:
        base = 4 + self.AVATAR + 8 + 14 + 8
        if compacto:
            return base
        return int(base + 4 + self._largura_texto() + 0.99)

    # ------------------------------------------------------------------ desenho
    def paintEvent(self, event) -> None:  # noqa: N802
        p = self._palette
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        fundo = 1.0 if self._ativo else self._realce.valor
        if fundo > 0.01:
            caixa = QPainterPath()
            caixa.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 12, 12)
            cor = QColor(p.surface_alt)
            cor.setAlphaF(fundo)
            pintor.fillPath(caixa, cor)
        if self._anel():
            pintor.setPen(QPen(QColor(p.accent), 1.2))
            pintor.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 12, 12)

        self._avatar(pintor, p)

        if not self._compacto:
            x = 4 + self.AVATAR + 10
            largura = self._largura_texto()
            meio = self.height() / 2
            pintor.setFont(font_for("strong"))
            pintor.setPen(QColor(p.text))
            nome = QFontMetricsF(font_for("strong")).elidedText(
                self._nome, Qt.TextElideMode.ElideRight, largura)
            pintor.drawText(QRectF(x, meio - 17, largura + 2, 18),
                            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), nome)
            if self._sub:
                pintor.setFont(font_for("caption"))
                pintor.setPen(QColor(p.text_muted))
                pintor.drawText(QRectF(x, meio + 1, largura + 2, 16),
                                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                                self._sub)

        pintor.drawPixmap(QPoint(self.width() - 8 - 14, (self.height() - 14) // 2),
                          icons.pixmap("caret-down", p.text_muted, 14, width=2.0))
        pintor.end()

    def _avatar(self, pintor: QPainter, p: Palette) -> None:
        area = QRectF(4, (self.height() - self.AVATAR) / 2, self.AVATAR, self.AVATAR)
        circulo = QPainterPath()
        circulo.addEllipse(area)
        if self._logo is not None:
            pintor.fillPath(circulo, QColor(p.surface))
            pintor.save()
            pintor.setClipPath(circulo)
            imagem = self._logo.scaled(
                QSize(self.AVATAR * 2, self.AVATAR * 2),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            imagem.setDevicePixelRatio(2)
            largura, altura = imagem.width() / 2, imagem.height() / 2
            pintor.drawPixmap(
                QRectF(area.center().x() - largura / 2, area.center().y() - altura / 2,
                       largura, altura),
                imagem, QRectF(imagem.rect()),
            )
            pintor.restore()
            pintor.setPen(QPen(QColor(p.border), 1))
            pintor.drawEllipse(area.adjusted(0.5, 0.5, -0.5, -0.5))
            return
        pintor.fillPath(circulo, QColor(p.accent_soft))
        fonte = font_for("strong")
        fonte.setPointSizeF(10.0)
        fonte.setWeight(fonte.Weight(800))
        pintor.setFont(fonte)
        pintor.setPen(QColor(p.accent))
        pintor.drawText(area, int(Qt.AlignmentFlag.AlignCenter), iniciais(self._nome))
