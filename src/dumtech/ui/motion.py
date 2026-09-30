"""Movimento da plataforma: pouco, curto e sempre com motivo.

Quatro usos, e so quatro:

* **chegar** - a tela nova surge em vez de trocar num estalo, e o dialogo
  abre com uma entrada curta;
* **realce** - o que esta sob o mouse muda de cor aos poucos, nao pisca;
* **crescer** - o grafico se desenha quando o numero muda, e o olho segue a
  mudanca em vez de procurar a diferenca;
* **revelar** - o tema novo se abre num circulo a partir do botao de tema,
  em vez de a janela inteira trocar de cor de uma vez.

Tudo respeita a opcao "Efeitos de animacao" do Windows (Acessibilidade): quem
desligou la nao ve movimento aqui. `DUMTECH_SEM_ANIMACAO=1` desliga tambem.
"""

from __future__ import annotations

import math
import os
import sys
import time
from functools import lru_cache
from typing import Callable

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QDialog, QGraphicsEffect, QWidget

#: Duracoes curtas de proposito: animacao tambem e espera - a tela so parece
#: pronta quando o movimento termina. Estas estao na faixa dos sistemas
#: rapidos (Windows 11, macOS): o olho acompanha, mas ninguem fica esperando.
RAPIDO = 110
MEDIO = 140
LENTO = 420

#: SPI_GETCLIENTAREAANIMATION: "Mostrar animacoes no Windows"
_SPI_ANIMACOES = 0x1042


@lru_cache(maxsize=1)
def habilitado() -> bool:
    """O movimento esta ligado para esta pessoa?"""
    if os.environ.get("DUMTECH_SEM_ANIMACAO"):
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            ligado = ctypes.c_int(1)
            if ctypes.windll.user32.SystemParametersInfoW(
                _SPI_ANIMACOES, 0, ctypes.byref(ligado), 0
            ):
                return bool(ligado.value)
        except Exception:  # noqa: BLE001 - sem a consulta, segue o padrao
            pass
    return True


#: quanto a tela anda ao chegar: de lado quando veio de uma aba, de baixo
#: quando nao tem lado (Licenca, Configuracoes)
DESLIZE_LATERAL = 22.0
DESLIZE_VERTICAL = 10.0


class _Entrada(QGraphicsEffect):
    """Esmaecer e deslizar numa passada so.

    O desenho do widget vem pronto do Qt (`sourcePixmap`) e e colado
    deslocado. Transladar o pintor e chamar `drawSource` nao funciona: para um
    widget, o Qt desenha a fonte ignorando a translacao - foi medido.

    A foto da tela e reaproveitada entre os quadros e so e refeita a cada
    `REFRESCO` segundos: tirar a foto de uma pagina inteira custa ~7 ms, e
    tira-la a cada quadro ocupava o processador a animacao inteira. Refazer de
    vez em quando mantem vivo o que se mexe por dentro (um grafico crescendo).
    """

    REFRESCO = 0.07

    def __init__(self, deslocamento: QPointF, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._deslocamento = QPointF(deslocamento)
        self.progresso = 0.0
        self._imagem: QPixmap | None = None
        self._origem = QPoint(0, 0)
        self._quando = 0.0

    def avancar(self, valor) -> None:
        self.progresso = float(valor)
        self.update()

    def _foto(self):
        agora = time.monotonic()
        if self._imagem is None or agora - self._quando >= self.REFRESCO:
            resultado = self.sourcePixmap(Qt.CoordinateSystem.LogicalCoordinates)
            if isinstance(resultado, tuple):
                self._imagem, self._origem = resultado[0], resultado[1]
            else:
                self._imagem, self._origem = resultado, QPoint(0, 0)
            self._quando = agora
        return self._imagem, self._origem

    def draw(self, pintor: QPainter) -> None:  # noqa: D401 (Qt)
        imagem, origem = self._foto()
        falta = 1.0 - self.progresso
        pintor.save()
        pintor.setOpacity(pintor.opacity() * self.progresso)
        pintor.drawPixmap(QPointF(origem) + self._deslocamento * falta, imagem)
        pintor.restore()


def surgir(widget: QWidget | None, direcao: int = 0, duracao: int = MEDIO + 10) -> None:
    """A tela chega esmaecendo e deslizando um pouco, em vez de trocar num estalo.

    `direcao` e o lado da aba nova em relacao a antiga (+1 direita, -1
    esquerda): o conteudo anda no mesmo sentido que o traco das abas. Sem
    lado (0), a tela so sobe um pouquinho.

    O efeito sai assim que termina: ele custa uma pintura extra por quadro, e
    ninguem precisa pagar isso depois que a tela ja chegou. Widget que ja tem
    efeito proprio fica como esta - efeito dentro de efeito faz o Qt reclamar
    de dois pintores no mesmo lugar.
    """
    if widget is None or not habilitado() or not widget.isVisible():
        return
    if widget.graphicsEffect() is not None:
        return
    deslocamento = (QPointF(DESLIZE_LATERAL * direcao, 0.0) if direcao
                    else QPointF(0.0, DESLIZE_VERTICAL))
    efeito = _Entrada(deslocamento, widget)
    widget.setGraphicsEffect(efeito)

    animacao = QVariantAnimation(widget)
    animacao.setDuration(duracao)
    animacao.setStartValue(0.0)
    animacao.setEndValue(1.0)
    animacao.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _passo(valor) -> None:
        try:
            efeito.avancar(valor)
        except RuntimeError:
            animacao.stop()  # alguem trocou o efeito da tela no meio do caminho

    def _terminou() -> None:
        try:
            if widget.graphicsEffect() is efeito:
                widget.setGraphicsEffect(None)
        except RuntimeError:
            pass  # a tela foi embora antes do fim

    animacao.valueChanged.connect(_passo)
    animacao.finished.connect(_terminou)
    animacao.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


class _Curva(QObject):
    """Um numero de 0 a 1 que anda com o tempo e repinta o dono a cada passo."""

    def __init__(self, widget: QWidget, duracao: int, inicial: float,
                 curva: QEasingCurve.Type) -> None:
        super().__init__(widget)
        self._widget = widget
        self.valor = inicial
        self._animacao = QVariantAnimation(self)
        self._animacao.setDuration(duracao)
        self._animacao.setEasingCurve(curva)
        self._animacao.valueChanged.connect(self._andou)

    def _andou(self, valor) -> None:
        self.valor = float(valor)
        self._widget.update()

    def ir(self, alvo: float, de: float | None = None) -> None:
        alvo = float(alvo)
        if not habilitado() or not self._widget.isVisible():
            self._animacao.stop()
            self.valor = alvo
            self._widget.update()
            return
        self._animacao.stop()
        self._animacao.setStartValue(self.valor if de is None else float(de))
        self._animacao.setEndValue(alvo)
        self._animacao.start()


class Realce(_Curva):
    """0 = parado, 1 = sob o mouse. O widget pinta misturando as duas pontas."""

    def __init__(self, widget: QWidget, duracao: int = RAPIDO) -> None:
        super().__init__(widget, duracao, 0.0, QEasingCurve.Type.OutCubic)

    def entrar(self) -> None:
        self.ir(1.0)

    def sair(self) -> None:
        self.ir(0.0)


class Progresso(_Curva):
    """De 0 a 1 quando o dado muda: o grafico cresce ate o tamanho certo.

    Tela escondida nao anima - ela ja nasce pronta, e ninguem fica olhando
    para um grafico vazio esperando o movimento que nao viu comecar.
    """

    def __init__(self, widget: QWidget, duracao: int = LENTO) -> None:
        super().__init__(widget, duracao, 1.0, QEasingCurve.Type.OutCubic)

    def reiniciar(self) -> None:
        self.ir(1.0, de=0.0)


# --------------------------------------------------------------- janelas ---
class _Vigia(QObject):
    """Olha a hora em que cada janela aparece - e so as janelas da plataforma.

    Um filtro na aplicacao inteira receberia todo evento de todo widget; aqui
    ele fica pendurado em cada janela, e o custo e zero no resto do tempo.
    """

    def eventFilter(self, obj, evento) -> bool:  # noqa: N802 (Qt)
        if evento.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
            from . import chrome
            from .theme import palette_for

            chrome.pintar(obj, palette_for(obj))
            if isinstance(obj, QDialog):
                abrir_janela(obj)
        return False


_vigia: _Vigia | None = None


def acompanhar(janela: QWidget) -> None:
    """Liga a entrada suave e a barra de titulo pintada numa janela."""
    global _vigia
    if getattr(janela, "_dt_vigiada", False):
        return
    app = QApplication.instance()
    if app is None:
        return
    if _vigia is None:
        _vigia = _Vigia(app)
    janela.installEventFilter(_vigia)
    janela._dt_vigiada = True


# ---------------------------------------------------------- troca de tema ---
class _Cortina(QWidget):
    """A foto do tema antigo por cima da janela, com um furo que cresce.

    Por baixo o tema novo ja esta aplicado; o furo circular, aberto a partir do
    botao que pediu a troca, vai mostrando o novo ate a foto sumir. Nada de
    brilho nem cor extra: so uma sombra curta na borda do circulo, para o olho
    acompanhar o movimento sem que ele chame mais atencao que a propria tela.
    """

    SOMBRA = 18

    def __init__(self, janela: QWidget, foto: QPixmap, origem: QPointF, duracao: int) -> None:
        super().__init__(janela)
        self._foto = foto
        self._origem = QPointF(origem)
        self._raio = 0.0
        # durante a troca o clique ja vai para a tela nova, que esta por baixo
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setGeometry(janela.rect())
        fim = max(math.hypot(x - origem.x(), y - origem.y())
                  for x in (0, self.width()) for y in (0, self.height()))
        self._animacao = QVariantAnimation(self)
        self._animacao.setDuration(duracao)
        self._animacao.setStartValue(0.0)
        self._animacao.setEndValue(fim + self.SOMBRA)
        self._animacao.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animacao.valueChanged.connect(self._abrir)
        self._animacao.finished.connect(self._terminar)
        self.show()
        self.raise_()

    def comecar(self) -> None:
        self.raise_()
        self._animacao.start()

    def _abrir(self, valor) -> None:
        self._raio = float(valor)
        self.update()

    def _terminar(self) -> None:
        self.hide()
        self.deleteLater()

    def paintEvent(self, evento) -> None:  # noqa: N802 (Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(self.rect())
        fora = QPainterPath()
        fora.addRect(area)
        if self._raio > 0:
            furo = QPainterPath()
            furo.addEllipse(self._origem, self._raio, self._raio)
            fora = fora.subtracted(furo)
        pintor.setClipPath(fora)
        pintor.drawPixmap(QPointF(0, 0), self._foto)
        if self._raio > 0:
            externo = self._raio + self.SOMBRA
            sombra = QRadialGradient(self._origem, externo)
            sombra.setColorAt(self._raio / externo, QColor(0, 0, 0, 34))
            sombra.setColorAt(1.0, QColor(0, 0, 0, 0))
            pintor.fillRect(area, sombra)
        pintor.end()


def revelar_tema(janela: QWidget, origem: QPointF, trocar: Callable[[], None],
                 duracao: int = 420) -> None:
    """Troca o tema com um circulo que se abre a partir de `origem`.

    A ordem importa: a foto e tirada ANTES da troca, a cortina com a foto
    entra por cima, e so entao o tema muda por baixo dela - assim nao existe
    nenhum quadro com a tela piscando no tema novo antes da hora. Janela
    escondida (testes) ou movimento desligado: troca na hora, sem cortina.
    """
    if not habilitado() or not janela.isVisible():
        trocar()
        return
    cortina = _Cortina(janela, janela.grab(), origem, duracao)
    try:
        trocar()
    finally:
        cortina.comecar()


def abrir_janela(janela: QWidget) -> None:
    """A janela aparece com um esmaecer curto (dialogos e a paleta de comandos)."""
    if not habilitado():
        return
    janela.setWindowOpacity(0.0)
    animacao = QPropertyAnimation(janela, b"windowOpacity", janela)
    animacao.setDuration(MEDIO)
    animacao.setStartValue(0.0)
    animacao.setEndValue(1.0)
    animacao.setEasingCurve(QEasingCurve.Type.OutCubic)
    animacao.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
