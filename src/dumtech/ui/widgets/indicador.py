"""O indicador que desliza entre as abas - e o realce que segue o mouse.

A selecao nao pula de uma aba para a outra: ela anda. A ponta que vai na
frente sai um pouco antes e a de tras acompanha, entao o indicador estica no
caminho e assenta com uma mola curta. E isso que faz a navegacao parecer uma
peca so, e nao um monte de botoes que acendem e apagam.

O indicador mora ATRAS das abas (`lower()`): as abas so escrevem o proprio
texto, e quem pinta a selecao e o realce e ele. Por isso ele e um widget do
recipiente, e nao um desenho dentro de cada aba - so assim da para o mesmo
traco atravessar de uma aba para a outra.

Uma aba pode dizer onde quer o indicador (`area_indicador()`) e o realce
(`area_realce()`); sem isso, vale o retangulo inteiro dela.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .. import motion
from ..theme import Palette, Radius, mix, palette_for

#: um traco fino embaixo da aba (a barra do topo)
TRACO = "traco"
#: uma pilula clara por tras da aba (seletor de telas, menu lateral)
PILULA = "pilula"


def _entre(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class Indicador(QWidget):
    """Selecao (e, se pedido, realce do mouse) que anda entre as abas."""

    DURACAO = 300
    DURACAO_REALCE = 160

    def __init__(
        self,
        recipiente: QWidget,
        forma: str = PILULA,
        raio: float = Radius.md,
        realce: bool = False,
    ) -> None:
        super().__init__(recipiente)
        self._recipiente = recipiente
        self._forma = forma
        self._raio = raio
        self._com_realce = realce
        self._palette = palette_for(recipiente)
        self._alvos: list[QWidget] = []

        self._selecionado: QWidget | None = None
        self._cor_token = "text"
        self._sel = QRectF()
        self._cor = QColor(self._palette.text)
        self._sel_alfa = 0.0
        # de onde para onde a selecao esta andando agora
        self._de, self._para = QRectF(), QRectF()
        self._cor_de, self._cor_para = self._cor, self._cor

        self._hover = QRectF()
        self._hover_alfa = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setGeometry(recipiente.rect())
        self.lower()

        # mola curta: passa um pouquinho do lugar e volta, sem quicar
        self._mola = QEasingCurve(QEasingCurve.Type.OutBack)
        self._mola.setOvershoot(0.7)

        self._anim_sel = self._animacao(self.DURACAO, QEasingCurve.Type.Linear, self._andar)
        self._anim_alfa = self._animacao(motion.MEDIO, QEasingCurve.Type.OutCubic,
                                         self._mudar_alfa_sel)
        self._anim_hover = self._animacao(self.DURACAO_REALCE, QEasingCurve.Type.OutCubic,
                                          self._mover_hover)
        self._anim_hover_alfa = self._animacao(motion.RAPIDO + 30, QEasingCurve.Type.OutCubic,
                                               self._mudar_alfa_hover)

        # o layout assenta depois: recalcula quando o recipiente ou a aba mexem
        self._assentar = QTimer(self)
        self._assentar.setSingleShot(True)
        self._assentar.setInterval(0)
        self._assentar.timeout.connect(self._reposicionar)
        # sair de uma aba e entrar na vizinha nao pode apagar o realce no meio
        self._saida = QTimer(self)
        self._saida.setSingleShot(True)
        self._saida.setInterval(40)
        self._saida.timeout.connect(self._conferir_saida)

        recipiente.installEventFilter(self)
        self.show()

    def _vivo(self) -> bool:
        """O lado Python ainda esta montado?

        Quando a caixa e o indicador so se seguram um no outro, quem os
        desmonta e o coletor de ciclos: ele esvazia os atributos ANTES de o Qt
        terminar de destruir as abas, e as abas ainda mandam eventos para o
        indicador, que e o filtro delas. Sem esta conferencia, cada evento
        virava erro no `sys.excepthook` - a janela de erro do programa.
        """
        return self.__dict__.get("_recipiente") is not None

    def _animacao(self, duracao: int, curva: QEasingCurve.Type, passo) -> QVariantAnimation:
        animacao = QVariantAnimation(self)
        animacao.setDuration(duracao)
        animacao.setEasingCurve(curva)
        animacao.valueChanged.connect(passo)
        return animacao

    # ------------------------------------------------------------------ abas
    def registrar(self, alvo: QWidget) -> None:
        if alvo in self._alvos:
            return
        self._alvos.append(alvo)
        alvo.installEventFilter(self)

    def remover(self, alvo: QWidget) -> None:
        if alvo in self._alvos:
            self._alvos.remove(alvo)
            try:
                alvo.removeEventFilter(self)
            except RuntimeError:
                pass
        if self._selecionado is alvo:
            self._selecionado = None
        if getattr(self, "_pairando", None) is alvo:
            self._pairando = None

    def apply_theme(self, palette: Palette) -> None:
        if not self._vivo():
            return
        self._palette = palette
        self._cor = QColor(palette.resolve(self._cor_token))
        self._cor_de = self._cor_para = self._cor
        self.update()

    # --------------------------------------------------------------- selecao
    def selecionar(self, alvo: QWidget | None, cor: str = "text", animar: bool = True) -> None:
        """Leva a selecao ate `alvo` (None: a selecao some devagar)."""
        self._selecionado = alvo
        self._cor_token = cor
        if alvo is None:
            self._ir_alfa(0.0, animar)
            return
        destino = self._retangulo(alvo, selecao=True)
        destino_cor = QColor(self._palette.resolve(cor))
        if destino is None:
            return  # ainda sem geometria: `_reposicionar` termina quando assentar

        visivel = self._sel_alfa > 0.01 and not self._sel.isNull()
        if visivel and animar and self._animavel() and destino != self._sel:
            self._anim_sel.stop()
            self._de, self._para = QRectF(self._sel), destino
            self._cor_de, self._cor_para = QColor(self._cor), destino_cor
            self._anim_sel.setStartValue(0.0)
            self._anim_sel.setEndValue(1.0)
            self._anim_sel.start()
        else:
            # aparecendo do nada: nasce no lugar certo e so acende
            self._anim_sel.stop()
            self._sel, self._cor = destino, destino_cor
        self._ir_alfa(1.0, animar and not visivel)
        self.update()

    def _andar(self, valor) -> None:
        """Um passo da selecao: a ponta da frente corre, a de tras acompanha."""
        if not self._vivo():
            return
        t = float(valor)
        rapido = self._mola.valueForProgress(min(1.0, t * 1.2))
        lento = self._mola.valueForProgress(max(0.0, (t - 0.14) / 0.86))
        de, para = self._de, self._para
        if abs(para.center().x() - de.center().x()) >= abs(para.center().y() - de.center().y()):
            frente_direita = para.center().x() >= de.center().x()
            esquerda = _entre(de.left(), para.left(), lento if frente_direita else rapido)
            direita = _entre(de.right(), para.right(), rapido if frente_direita else lento)
            topo = _entre(de.top(), para.top(), rapido)
            base = _entre(de.bottom(), para.bottom(), rapido)
        else:
            frente_baixo = para.center().y() >= de.center().y()
            topo = _entre(de.top(), para.top(), lento if frente_baixo else rapido)
            base = _entre(de.bottom(), para.bottom(), rapido if frente_baixo else lento)
            esquerda = _entre(de.left(), para.left(), rapido)
            direita = _entre(de.right(), para.right(), rapido)
        self._sel = QRectF(esquerda, topo, max(0.0, direita - esquerda), max(0.0, base - topo))
        self._cor = QColor(mix(self._cor_de.name(), self._cor_para.name(), min(1.0, t * 1.3)))
        self.update()

    def _ir_alfa(self, alvo: float, animar: bool) -> None:
        if animar and self._animavel():
            self._anim_alfa.stop()
            self._anim_alfa.setStartValue(self._sel_alfa)
            self._anim_alfa.setEndValue(alvo)
            self._anim_alfa.start()
        else:
            self._anim_alfa.stop()
            self._sel_alfa = alvo
            self.update()

    def _mudar_alfa_sel(self, valor) -> None:
        if not self._vivo():
            return
        self._sel_alfa = float(valor)
        self.update()

    # ---------------------------------------------------------------- realce
    def _pairar(self, alvo: QWidget) -> None:
        self._saida.stop()
        destino = self._retangulo(alvo, selecao=False)
        if destino is None:
            return
        self._pairando = alvo
        if self._hover_alfa <= 0.01 or not self._animavel():
            self._anim_hover.stop()
            self._hover = destino
        else:
            self._anim_hover.stop()
            self._anim_hover.setStartValue(QRectF(self._hover))
            self._anim_hover.setEndValue(destino)
            self._anim_hover.start()
        self._acender_realce(1.0)

    def _conferir_saida(self) -> None:
        if not self._vivo():
            return
        for alvo in list(self._alvos):
            try:
                if alvo.underMouse():
                    return
            except RuntimeError:
                continue
        self._pairando = None
        self._acender_realce(0.0)

    def _acender_realce(self, alvo: float) -> None:
        if not self._animavel():
            self._hover_alfa = alvo
            self.update()
            return
        self._anim_hover_alfa.stop()
        self._anim_hover_alfa.setStartValue(self._hover_alfa)
        self._anim_hover_alfa.setEndValue(alvo)
        self._anim_hover_alfa.start()

    def _mover_hover(self, valor) -> None:
        if not self._vivo():
            return
        self._hover = QRectF(valor)
        self.update()

    def _mudar_alfa_hover(self, valor) -> None:
        if not self._vivo():
            return
        self._hover_alfa = float(valor)
        self.update()

    # ------------------------------------------------------------ geometria
    def _animavel(self) -> bool:
        return motion.habilitado() and self.isVisible()

    def _retangulo(self, alvo: QWidget, selecao: bool) -> QRectF | None:
        try:
            if alvo.width() <= 0 or alvo.height() <= 0:
                return None
            canto = alvo.mapTo(self._recipiente, QPoint(0, 0))
        except RuntimeError:
            return None  # a aba foi embora
        area = getattr(alvo, "area_indicador" if selecao else "area_realce", None)
        local = area() if callable(area) else QRectF(alvo.rect())
        return local.translated(canto.x(), canto.y())

    def _reposicionar(self) -> None:
        """O layout mexeu: a selecao vai direto para o lugar novo, sem andar."""
        if not self._vivo():
            return
        self.setGeometry(self._recipiente.rect())
        if self._anim_sel.state() != QVariantAnimation.State.Running and self._selecionado:
            destino = self._retangulo(self._selecionado, selecao=True)
            if destino is not None:
                self._sel = destino
                self._cor = QColor(self._palette.resolve(self._cor_token))
                if self._sel_alfa <= 0.01 and self._anim_alfa.state() != QVariantAnimation.State.Running:
                    self._sel_alfa = 1.0
        pairando = getattr(self, "_pairando", None)
        if pairando is not None and self._anim_hover.state() != QVariantAnimation.State.Running:
            destino = self._retangulo(pairando, selecao=False)
            if destino is not None:
                self._hover = destino
        self.update()

    def eventFilter(self, obj, evento) -> bool:  # noqa: N802 (Qt)
        if not self._vivo():
            return False
        tipo = evento.type()
        if obj is self._recipiente:
            if tipo in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.LayoutRequest):
                self._assentar.start()
        elif obj in self._alvos:
            if tipo == QEvent.Type.Enter and self._com_realce:
                self._pairar(obj)
            elif tipo == QEvent.Type.Leave and self._com_realce:
                self._saida.start()
            elif tipo in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show):
                self._assentar.start()
        return False

    # --------------------------------------------------------------- desenho
    def paintEvent(self, evento) -> None:  # noqa: N802 (Qt)
        if not self._vivo():
            return
        p = self._palette
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._com_realce and self._hover_alfa > 0.01 and not self._hover.isNull():
            fundo = QColor(p.surface_alt)
            fundo.setAlphaF(self._hover_alfa)
            forma = QPainterPath()
            forma.addRoundedRect(self._hover, Radius.md, Radius.md)
            pintor.fillPath(forma, fundo)

        if self._sel_alfa > 0.01 and not self._sel.isNull():
            forma = QPainterPath()
            if self._forma == TRACO:
                raio = self._sel.height() / 2
                forma.addRoundedRect(self._sel, raio, raio)
                cor = QColor(self._cor)
                cor.setAlphaF(self._sel_alfa)
                pintor.fillPath(forma, cor)
            else:
                forma.addRoundedRect(self._sel.adjusted(0.5, 0.5, -0.5, -0.5),
                                     self._raio, self._raio)
                fundo = QColor(p.surface_hover if p.is_dark else p.surface)
                fundo.setAlphaF(self._sel_alfa)
                pintor.fillPath(forma, fundo)
                borda = QColor(p.border_soft)
                borda.setAlphaF(self._sel_alfa)
                pintor.setPen(QPen(borda, 1))
                pintor.drawPath(forma)
        pintor.end()
