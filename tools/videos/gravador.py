"""Grava o Hub de verdade em MP4: cursor, cliques, digitacao e legendas.

COMO FUNCIONA
    O Hub roda de verdade (sem janela na tela, QT_QPA_PLATFORM=offscreen). Um
    relogio fotografa a janela ~25 vezes por segundo, cola por cima o que
    estiver aberto (dialogo, menu, lista de sugestoes), desenha o cursor e a
    legenda, e manda o quadro cru para o ffmpeg.

O ROTEIRO E UM GERADOR
    Cada passo devolve (yield) quantos milissegundos esperar. Clique e tecla
    vao por `QTimer.singleShot(0, ...)`: um clique que abre `dialog.exec()`
    trava quem clicou ate o dialogo fechar - e o roteiro precisa continuar
    rodando la dentro para preencher o dialogo.

TEMPO REAL
    O quadro e escrito pelo relogio de verdade: se uma foto atrasar, o
    ultimo quadro se repete - o video fica na velocidade em que o Hub andou.
"""

from __future__ import annotations

import math
import os
import subprocess
import time
import unicodedata

from PySide6.QtCore import QByteArray, QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

VIOLETA = QColor("#7353F6")
FONTE = "Plus Jakarta Sans"


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto or "")
    # "Receber  (F12)" -> "receber": o que vem depois de dois espacos e atalho
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower().strip().split("  ")[0].strip()


def _igual(a: str, b: str) -> bool:
    return " ".join(_sem_acento(a).split()) == " ".join(_sem_acento(b).split())


def _tecla_de_texto(alvo: QWidget, letra: str) -> None:
    """Digita uma letra. O QTest so conhece ASCII: com "ç" ou "ã" ele derruba o
    processo (qFatal) - entao acento vai como evento de tecla com o texto pronto."""
    if letra.isascii():
        QTest.keyClicks(alvo, letra)
        return
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    for tipo in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(alvo, QKeyEvent(tipo, 0, Qt.KeyboardModifier.NoModifier, letra))


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class Gravador:
    """Fotografa `janela` + o que estiver por cima e manda para o ffmpeg."""

    def __init__(self, janela: QWidget, saida: str, ffmpeg: str, fps: int = 25) -> None:
        self.janela = janela
        self.fps = fps
        self.largura, self.altura = janela.width(), janela.height()
        self.proc = subprocess.Popen(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra",
             "-s", f"{self.largura}x{self.altura}", "-r", str(fps), "-i", "-",
             # grava no tamanho de um notebook (tudo maior na tela) e entrega em Full HD
             "-vf", "scale=1920:1080:flags=lanczos",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", saida],
            stdin=subprocess.PIPE)
        self.escritos = 0
        self.inicio = time.monotonic()
        self.ultimo: bytes | None = None
        # cursor
        self.cursor = QPointF(self.largura * 0.6, self.altura * 0.55)
        self._de = self._para = self.cursor
        self._t0 = 0.0
        self._dur = 0.0
        self._clique: tuple[float, QPointF] | None = None
        self.cursor_visivel = True
        # legenda e cartao de abertura
        self.legenda = ""
        self._legenda_t = 0.0
        self.cartao = None  # funcao(painter, agora) que desenha o quadro inteiro
        self.relogio = QTimer()
        self.relogio.setInterval(int(1000 / fps))
        self.relogio.timeout.connect(self._tick)

    # ---------------------------------------------------------------- tempo --
    def agora(self) -> float:
        return time.monotonic() - self.inicio

    def comecar(self) -> None:
        self.inicio = time.monotonic()
        self.relogio.start()

    def terminar(self) -> None:
        self.relogio.stop()
        self._tick()
        self.proc.stdin.close()
        self.proc.wait()

    def _tick(self) -> None:
        devidos = int(self.agora() * self.fps) + 1
        if devidos <= self.escritos:
            return
        quadro = self._quadro()
        faltam = devidos - self.escritos
        for _ in range(faltam):
            self.proc.stdin.write(quadro)
        self.escritos = devidos

    # --------------------------------------------------------------- cursor --
    def mover_para(self, ponto: QPointF, dur: float) -> None:
        self._de = self._cursor_agora()
        self._para = QPointF(ponto)
        self._t0 = self.agora()
        self._dur = max(0.01, dur)

    def _cursor_agora(self) -> QPointF:
        t = _ease((self.agora() - self._t0) / self._dur) if self._dur else 1.0
        return self._de + (self._para - self._de) * t

    def marcar_clique(self) -> None:
        self._clique = (self.agora(), self._cursor_agora())

    def dizer(self, texto: str) -> None:
        if texto != self.legenda:
            self.legenda = texto
            self._legenda_t = self.agora()

    # --------------------------------------------------------------- quadro --
    def _quadro(self) -> bytes:
        img = QImage(self.largura, self.altura, QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        agora = self.agora()
        if self.cartao is not None:
            self.cartao(p, agora)
        else:
            p.drawPixmap(0, 0, self.janela.grab())
            self._por_cima(p)
            self._desenhar_legenda(p, agora)
            if self.cursor_visivel:
                self._desenhar_clique(p, agora)
                self._desenhar_cursor(p, self._cursor_agora())
        p.end()
        return bytes(img.constBits())

    def _por_cima(self, p: QPainter) -> None:
        """Dialogos, menus e listas de sugestao: sao janelas proprias."""
        origem = self.janela.mapToGlobal(QPoint(0, 0))
        for w in QApplication.topLevelWidgets():
            if w is self.janela or not w.isVisible() or w.width() < 8:
                continue
            if w.windowType() == Qt.WindowType.ToolTip:  # dica de mouse parado: so polui o video
                continue
            pos = w.mapToGlobal(QPoint(0, 0)) - origem
            if isinstance(w, QDialog):
                # o dialogo fica no meio da janela, com o fundo escurecido - e
                # encolhido se for mais alto que a tela (a do video e de notebook)
                caixa, _ = self.lugar_do_dialogo(w)
                p.fillRect(0, 0, self.largura, self.altura, QColor(15, 12, 30, 110))
                sombra = QPainterPath()
                sombra.addRoundedRect(caixa.adjusted(-2, 6, 2, 12), 16, 16)
                p.fillPath(sombra, QColor(0, 0, 0, 60))
                caminho = QPainterPath()
                caminho.addRoundedRect(caixa, 14, 14)
                p.save()
                p.setClipPath(caminho)
                p.drawPixmap(caixa.toRect(), w.grab())
                p.restore()
            else:
                p.drawPixmap(pos, w.grab())

    def lugar_do_dialogo(self, w: QWidget) -> tuple[QRectF, float]:
        """Onde o dialogo aparece no video (e em que escala)."""
        margem = 14
        escala = min(1.0, (self.altura - 2 * margem) / max(1, w.height()),
                     (self.largura - 2 * margem) / max(1, w.width()))
        largura, altura = w.width() * escala, w.height() * escala
        return QRectF((self.largura - largura) / 2, max(margem, (self.altura - altura) / 2),
                      largura, altura), escala

    def _desenhar_cursor(self, p: QPainter, c: QPointF) -> None:
        seta = QPolygonF([QPointF(0, 0), QPointF(0, 22), QPointF(6, 17), QPointF(10.5, 26),
                          QPointF(14, 24.5), QPointF(9.8, 15.8), QPointF(17, 15.5)])
        seta.translate(c)
        p.setPen(QPen(QColor(255, 255, 255), 2.2))
        p.setBrush(QColor(20, 20, 28))
        p.drawPolygon(seta)

    def _desenhar_clique(self, p: QPainter, agora: float) -> None:
        if not self._clique:
            return
        t0, ponto = self._clique
        t = (agora - t0) / 0.45
        if t > 1:
            return
        raio = 8 + 26 * _ease(t)
        cor = QColor(VIOLETA)
        cor.setAlphaF(0.55 * (1 - t))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(cor)
        p.drawEllipse(ponto, raio, raio)

    def _desenhar_legenda(self, p: QPainter, agora: float) -> None:
        if not self.legenda:
            return
        aparecer = _ease((agora - self._legenda_t) / 0.3)
        fonte = QFont(FONTE, 17)
        fonte.setWeight(QFont.Weight.DemiBold)
        p.setFont(fonte)
        metrica = p.fontMetrics()
        largura = min(self.largura - 160, metrica.horizontalAdvance(self.legenda) + 64)
        altura = 58
        x = (self.largura - largura) / 2
        y = self.altura - altura - 34 + (1 - aparecer) * 14
        p.setOpacity(aparecer)
        caixa = QPainterPath()
        caixa.addRoundedRect(QRectF(x, y, largura, altura), 18, 18)
        p.fillPath(caixa, QColor(23, 23, 31, 232))
        p.fillRect(QRectF(x + 22, y + altura / 2 - 5, 10, 10), VIOLETA)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(x + 42, y, largura - 60, altura), Qt.AlignmentFlag.AlignVCenter, self.legenda)
        p.setOpacity(1)


# ============================================================ cartoes (abertura)
def icone_svg(caminho: str, cor: str, lado: int, traco: float = 1.8) -> QImage:
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='{cor}' "
           f"stroke-width='{traco}' stroke-linecap='round' stroke-linejoin='round'><path d='{caminho}'/></svg>")
    img = QImage(lado, lado, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    return img


GRADE = "M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z"


def cartao_de_titulo(largura: int, altura: int, sobre: str, titulo: str, texto: str,
                     icone: str = GRADE, cor: str = "#7353F6", duracao: float = 3.2,
                     sair: bool = True):
    """`sair`: some no fim (abertura); o encerramento fica ate o video acabar."""
    """Abertura/encerramento: fundo violeta, icone do modulo, titulo grande."""
    marca = icone_svg(GRADE, "#ffffff", 30, 2)
    simbolo = icone_svg(icone, "#ffffff", 72, 1.7)
    fundo = icone_svg(GRADE, "#ffffff", int(altura * 0.9), 0.9)

    def desenhar(p: QPainter, agora: float, t0: list = []) -> None:  # noqa: B006 - guarda o inicio
        if not t0:
            t0.append(agora)
        t = agora - t0[0]
        # desenhado em 1600x900 e ajustado ao tamanho real do quadro
        escala = p.device().width() / largura
        p.save()
        p.scale(escala, escala)
        g = QLinearGradient(0, 0, largura, altura)
        g.setColorAt(0, QColor("#6a48f2"))
        g.setColorAt(0.6, QColor("#7c5cf7"))
        g.setColorAt(1, QColor("#9d86fb"))
        p.fillRect(0, 0, largura, altura, g)
        p.setOpacity(0.10)
        p.drawImage(int(largura * 0.58), int(altura * 0.05) - int(t * 6), fundo)
        p.setOpacity(1)
        entra = _ease(t / 0.6)
        dy = (1 - entra) * 24
        p.setOpacity(entra)
        # marca
        selo = QPainterPath()
        selo.addRoundedRect(QRectF(96, 80, 52, 52), 15, 15)
        p.fillPath(selo, QColor(255, 255, 255, 46))
        p.drawImage(107, 91, marca)
        p.setPen(QColor("#ffffff"))
        f = QFont(FONTE, 20)
        f.setWeight(QFont.Weight.ExtraBold)
        p.setFont(f)
        p.drawText(QRectF(164, 80, 600, 52), Qt.AlignmentFlag.AlignVCenter, "DumTech Hub")
        # icone do modulo
        caixa = QPainterPath()
        caixa.addRoundedRect(QRectF(96, altura * 0.36 + dy, 116, 116), 32, 32)
        p.fillPath(caixa, QColor(cor))
        p.setPen(QPen(QColor(255, 255, 255, 90), 2))
        p.drawPath(caixa)
        p.drawImage(118, int(altura * 0.36 + dy) + 22, simbolo)
        # textos
        f = QFont(FONTE, 15)
        f.setWeight(QFont.Weight.ExtraBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 215))
        p.drawText(QRectF(244, altura * 0.36 + dy, largura - 300, 36), Qt.AlignmentFlag.AlignVCenter, sobre.upper())
        f = QFont(FONTE, 54)
        f.setWeight(QFont.Weight.ExtraBold)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 97)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(240, altura * 0.36 + 30 + dy, largura - 300, 100), Qt.AlignmentFlag.AlignVCenter, titulo)
        f = QFont(FONTE, 19)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 225))
        p.drawText(QRectF(96, altura * 0.36 + 160 + dy, largura * 0.62, 120),
                   Qt.TextFlag.TextWordWrap, texto)
        p.setOpacity(1)
        # sai em fade para branco no fim
        sai = _ease((t - (duracao - 0.35)) / 0.35)
        if sair and sai > 0:
            p.fillRect(0, 0, largura, altura, QColor(246, 246, 249, int(255 * sai)))
        p.restore()

    return desenhar


# ================================================================== diretor
class Diretor:
    """Os gestos do roteiro: achar, apontar, clicar, digitar, legendar."""

    def __init__(self, gravador: Gravador) -> None:
        self.g = gravador

    # -------------------------------------------------------------- achar --
    def _janelas(self) -> list[QWidget]:
        modal = QApplication.activeModalWidget()
        if modal is not None:
            return [modal]
        return [w for w in QApplication.topLevelWidgets() if w.isVisible()]

    def _visivel(self, w: QWidget) -> bool:
        return w.isVisible() and w.width() > 2 and w.height() > 2 and w.window().isVisible()

    def botao(self, texto: str, dentro: QWidget | None = None, indice: int = 0) -> QAbstractButton:
        achados = []
        for raiz in ([dentro] if dentro else self._janelas()):
            for b in raiz.findChildren(QAbstractButton):
                if self._visivel(b) and _igual(b.text(), texto):
                    achados.append(b)
        if not achados:
            raise LookupError(f"botao nao encontrado: {texto!r}\n{self.o_que_tem()}")
        return achados[indice]

    def campo(self, rotulo: str, dentro: QWidget | None = None, indice: int = 0) -> QWidget:
        """O campo que vem logo depois do rotulo (QFormLayout ou rotulo em cima)."""
        entradas = (QLineEdit, QAbstractSpinBox, QComboBox, QTextEdit, QPlainTextEdit)
        achados = []
        for raiz in ([dentro] if dentro else self._janelas()):
            for lab in raiz.findChildren(QLabel):
                if not (self._visivel(lab) and _igual(lab.text().rstrip(" *:"), rotulo)):
                    continue
                if lab.buddy() is not None:
                    achados.append(lab.buddy())
                    continue
                pai = lab.parentWidget()
                achado = self._vizinho(pai.layout() if pai else None, lab, entradas)
                if achado is not None:
                    achados.append(achado)
        achados = [a for a in achados if a is not None]
        if not achados:
            raise LookupError(f"campo nao encontrado: {rotulo!r}\n{self.o_que_tem()}")
        return achados[indice]

    def _vizinho(self, layout, lab: QLabel, entradas) -> QWidget | None:
        """Procura o rotulo em todos os layouts aninhados e devolve o campo dele."""
        if layout is None:
            return None
        if isinstance(layout, QFormLayout):
            for linha in range(layout.rowCount()):
                item = layout.itemAt(linha, QFormLayout.ItemRole.LabelRole)
                if item and item.widget() is lab:
                    campo = layout.itemAt(linha, QFormLayout.ItemRole.FieldRole)
                    alvo = campo.widget() if campo.widget() else None
                    if alvo is None and campo.layout():
                        alvo = next((campo.layout().itemAt(i).widget() for i in range(campo.layout().count())
                                     if campo.layout().itemAt(i).widget()), None)
                    return self._primeira_entrada(alvo, entradas) if alvo else None
        depois = False
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget()
            if w is lab:
                depois = True
            elif depois and w is not None:
                return self._primeira_entrada(w, entradas)
            if item.layout() is not None:
                achado = self._vizinho(item.layout(), lab, entradas)
                if achado is not None:
                    return achado
        return None

    @staticmethod
    def _primeira_entrada(w: QWidget, tipos) -> QWidget | None:
        if isinstance(w, tipos):
            return w
        for filho in w.findChildren(QWidget):
            if isinstance(filho, tipos) and filho.isVisible():
                return filho
        return None

    def por_dica(self, dica: str) -> QLineEdit:
        """Campo pelo texto de exemplo (placeholder)."""
        for raiz in self._janelas():
            for c in raiz.findChildren(QLineEdit):
                if self._visivel(c) and _sem_acento(dica) in _sem_acento(c.placeholderText()):
                    return c
        raise LookupError(f"campo com dica {dica!r} nao encontrado\n{self.o_que_tem()}")

    def o_que_tem(self) -> str:
        """Para consertar roteiro: o que esta visivel agora."""
        linhas = []
        for raiz in self._janelas():
            linhas.append(f"[{type(raiz).__name__}]")
            linhas.append(" botoes: " + " | ".join(b.text().strip() for b in raiz.findChildren(QAbstractButton)
                                                    if self._visivel(b) and b.text().strip()))
            linhas.append(" rotulos: " + " | ".join(l.text().strip()[:30] for l in raiz.findChildren(QLabel)
                                                     if self._visivel(l) and l.text().strip())[:1500])
            linhas.append(" dicas: " + " | ".join(c.placeholderText() for c in raiz.findChildren(QLineEdit)
                                                   if self._visivel(c) and c.placeholderText()))
        return "\n".join(linhas)

    # ------------------------------------------------------------ gestos --
    def centro(self, w: QWidget, ancora: QPoint | None = None) -> QPointF:
        origem = self.g.janela.mapToGlobal(QPoint(0, 0))
        ponto = ancora if ancora is not None else w.rect().center()
        pos = w.mapToGlobal(ponto) - origem
        dialogo = w.window()
        if isinstance(dialogo, QDialog):
            # o gravador desenha o dialogo centralizado (e as vezes menor): o cursor segue
            caixa, escala = self.g.lugar_do_dialogo(dialogo)
            dentro = w.mapTo(dialogo, ponto)
            return QPointF(caixa.x() + dentro.x() * escala, caixa.y() + dentro.y() * escala)
        return QPointF(pos)

    def rotulo(self, texto: str) -> QLabel:
        """Um texto visivel na tela (para clicar num cartao, por exemplo)."""
        for raiz in self._janelas():
            for lab in raiz.findChildren(QLabel):
                if self._visivel(lab) and _igual(lab.text(), texto):
                    return lab
        raise LookupError(f"texto {texto!r} nao encontrado\n" + self.o_que_tem())

    def apontar(self, w: QWidget, ancora: QPoint | None = None, dur: float = 0.7):
        alvo = self.centro(w, ancora)
        distancia = math.hypot(alvo.x() - self.g.cursor.x(), alvo.y() - self.g.cursor.y())
        dur = min(dur, 0.25 + distancia / 1400)
        self.g.mover_para(alvo, dur)
        self.g.cursor = alvo
        yield int(dur * 1000) + 120

    def clicar(self, w: QWidget, ancora: QPoint | None = None, espera: int = 650, direito: bool = False):
        yield from self.apontar(w, ancora)
        self.g.marcar_clique()
        botao = Qt.MouseButton.RightButton if direito else Qt.MouseButton.LeftButton
        ponto = ancora if ancora is not None else w.rect().center()
        QTimer.singleShot(0, lambda: QTest.mouseClick(w, botao, Qt.KeyboardModifier.NoModifier, ponto))
        yield espera

    def digitar(self, w: QWidget, texto: str, por_segundo: float = 16, limpar: bool = True, espera: int = 350):
        yield from self.clicar(w, espera=250)
        if limpar:
            if isinstance(w, QAbstractSpinBox):
                QTimer.singleShot(0, w.selectAll)
            elif hasattr(w, "clear") and not isinstance(w, QComboBox):
                QTimer.singleShot(0, w.clear)
            yield 60
        # combo editavel recebe no campo de texto dele; spinbox repassa sozinho
        alvo = w.lineEdit() if isinstance(w, QComboBox) and w.isEditable() else w
        for letra in texto:
            QTimer.singleShot(0, lambda c=letra: _tecla_de_texto(alvo, c))
            yield int(1000 / por_segundo)
        yield espera

    def tecla(self, w: QWidget, tecla, espera: int = 500):
        QTimer.singleShot(0, lambda: QTest.keyClick(w, tecla))
        yield espera

    def dizer(self, texto: str) -> None:
        self.g.dizer(texto)

    def clicar_sugestao(self, linha: int = 0, espera: int = 900):
        """Clica numa linha da lista de sugestao (a do catalogo ou a do autocompletar)."""
        from PySide6.QtWidgets import QAbstractItemView
        candidatas = [w for raiz in self._janelas() for w in raiz.findChildren(QAbstractItemView)
                      if w.objectName() == "BuscaCatalogo" and self._visivel(w)]
        candidatas += [w for w in QApplication.topLevelWidgets() if isinstance(w, QAbstractItemView) and w.isVisible()]
        if not candidatas:
            raise LookupError("nenhuma lista de sugestao aberta\n" + self.o_que_tem())
        lista = candidatas[0]
        ponto = lista.visualRect(lista.model().index(linha, 0)).center()
        yield from self.clicar(lista.viewport(), ponto, espera=espera)

    def tem_dialogo(self) -> bool:
        return QApplication.activeModalWidget() is not None

    def fechar_dialogo(self, aceitar: bool = False):
        modal = QApplication.activeModalWidget()
        if modal is not None:
            QTimer.singleShot(0, modal.accept if aceitar else modal.reject)
        yield 700

    def dialogo(self) -> QWidget:
        """O formulario aberto agora (para usar os campos dele pelo nome)."""
        modal = QApplication.activeModalWidget()
        if modal is None:
            raise LookupError("nenhum dialogo aberto\n" + self.o_que_tem())
        return modal

    def escolher(self, combo: QComboBox, texto: str, espera: int = 500):
        """Abre a lista, mostra, e escolhe a opcao."""
        indice = next((i for i in range(combo.count()) if _igual(combo.itemText(i), texto)), -1)
        if indice < 0:
            raise LookupError(f"opcao {texto!r} nao existe: {[combo.itemText(i) for i in range(combo.count())]}")
        yield from self.clicar(combo, espera=900)

        def escolhe() -> None:
            combo.setCurrentIndex(indice)
            combo.hidePopup()
        QTimer.singleShot(0, escolhe)
        yield espera

    def linha_da_tabela(self, texto: str):
        """(viewport, ponto) da primeira linha visivel que tem `texto`."""
        from PySide6.QtCore import QModelIndex
        from PySide6.QtWidgets import QAbstractItemView
        for raiz in self._janelas():
            for vista in raiz.findChildren(QAbstractItemView):
                modelo = vista.model()
                if not self._visivel(vista) or modelo is None:
                    continue
                for linha in range(modelo.rowCount(QModelIndex())):
                    for coluna in range(modelo.columnCount(QModelIndex())):
                        indice = modelo.index(linha, coluna)
                        if _sem_acento(texto) in _sem_acento(str(modelo.data(indice) or "")):
                            vista.scrollTo(indice)
                            return vista.viewport(), vista.visualRect(indice).center()
        raise LookupError(f"linha {texto!r} nao encontrada\n" + self.o_que_tem())

    def clicar_linha(self, texto: str, espera: int = 700, duplo: bool = False, direito: bool = False):
        vista, ponto = self.linha_da_tabela(texto)
        yield from self.clicar(vista, ponto, espera=150 if duplo else espera, direito=direito)
        if duplo:
            QTimer.singleShot(0, lambda: QTest.mouseDClick(vista, Qt.MouseButton.LeftButton,
                                                           Qt.KeyboardModifier.NoModifier, ponto))
            yield espera

    def clicar_acao(self, menu: QMenu, texto: str, espera: int = 800):
        """Clica num item de menu (menu de contexto ou menu da empresa)."""
        acao = next((a for a in menu.actions() if _igual(a.text(), texto)), None)
        if acao is None:
            raise LookupError(f"menu sem {texto!r}: {[a.text() for a in menu.actions()]}")
        ponto = menu.actionGeometry(acao).center()
        yield from self.apontar(menu, ponto)
        self.g.marcar_clique()
        QTimer.singleShot(0, acao.trigger)
        QTimer.singleShot(0, menu.close)
        yield espera

    def menu_aberto(self) -> QMenu:
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMenu) and w.isVisible():
                return w
        raise LookupError("nenhum menu aberto")

    def rolar_ate(self, w: QWidget):
        """Garante que o widget esteja na tela (dentro de area de rolagem)."""
        from PySide6.QtWidgets import QScrollArea
        pai = w.parentWidget()
        while pai is not None:
            if isinstance(pai, QScrollArea):
                QTimer.singleShot(0, lambda a=pai: a.ensureWidgetVisible(w, 40, 80))
                break
            pai = pai.parentWidget()
        yield 300

    def cartao(self, desenhar, duracao: float, manter: bool = False):
        """Tela cheia por `duracao`. `manter`: fica ate o fim (o encerramento)."""
        self.g.cartao = desenhar
        yield int(duracao * 1000)
        if not manter:
            self.g.cartao = None


def rodar(roteiro, gravador: Gravador, app: QApplication) -> None:
    """Toca o gerador passo a passo, sem nunca reentrar nele."""
    erros: list[BaseException] = []

    def passo() -> None:
        try:
            espera = next(roteiro)
        except StopIteration:
            QTimer.singleShot(400, fim)
            return
        except BaseException as erro:  # noqa: BLE001 - o video fecha e o erro aparece
            erros.append(erro)
            QTimer.singleShot(0, fim)
            return
        if os.environ.get("VIDEO_PASSOS"):  # para achar onde um roteiro para
            gen, cadeia = roteiro, []
            while gen is not None and hasattr(gen, "gi_frame"):
                cadeia.append(f"{gen.gi_code.co_name}:{gen.gi_frame.f_lineno if gen.gi_frame else '?'}")
                gen = getattr(gen, "gi_yieldfrom", None)
            print("passo " + " > ".join(cadeia), flush=True)
        QTimer.singleShot(int(espera or 0), passo)

    def fim() -> None:
        gravador.terminar()
        # fecha dialogos que tenham ficado abertos (o exec() deles segura o laco)
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible():
                w.reject()
        app.exit(0)

    gravador.comecar()
    QTimer.singleShot(0, passo)
    app.exec()
    if erros:
        raise erros[0]
