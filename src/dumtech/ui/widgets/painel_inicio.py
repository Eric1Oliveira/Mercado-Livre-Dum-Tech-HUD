"""As pecas do Inicio: a empresa, os sinais vitais e o que pede atencao.

O Inicio nao e um mural de avisos - e a primeira coisa que o dono ve de manha,
e por isso ele abre com o nome da propria empresa, nao com o nome do programa.
Depois vem a linha de sinais vitais, que cresce conforme os modulos: um so ja
faz sentido, e sete formam o retrato do negocio.

A regra que sustenta essa sensacao de completude: **nenhum bloco fica com
buraco**. Sem empresa preenchida, o cabecalho convida a preencher; sem aviso
nenhum, aparece o cartao de "tudo em dia"; com um modulo so, a linha de sinais
tem um numero e continua parecendo proposital.
"""

from __future__ import annotations

import math
from datetime import date

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import format as fmt
from ..motion import Realce
from ..theme import LIGHT, Palette, Radius, Space, current_palette, font_for, mix, palette_for
from .buttons import Button
from .common import Card, IconBadge, Pill, label, repolish, separator, tone_label

DIAS = ("segunda-feira", "terca-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sabado", "domingo")
MESES = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")

ALTURA_LOGO = 44
#: a grade mantem sempre o mesmo numero de colunas: assim um sinal sozinho
#: ocupa um quarto da largura, como ocupara quando os outros chegarem - e nao
#: uma faixa esticada que parece caixa vazia
COLUNAS_SINAIS = 4

#: Quieto por padrao, alto so quando ha problema.
#:
#: O modulo diz o tom do indicador, mas quem decide como isso vira cor na tela
#: e o Inicio. Verde em "voce tem dinheiro em caixa" e azul em "vendeu hoje"
#: sao enfeite: sao fatos normais, e pintar fato normal faz o arco-iris em que
#: nada se destaca. Vermelho em "venceu" e ambar em "no minimo" sao aviso.
TONS_DE_ALARME = ("danger", "warning")


def tom_na_tela(tom: str) -> str:
    return tom if tom in TONS_DE_ALARME else "text"


def data_por_extenso(quando: date | None = None) -> str:
    quando = quando or date.today()
    return f"{DIAS[quando.weekday()]}, {quando.day} de {MESES[quando.month - 1]}"


def data_curta(quando: date | None = None) -> str:
    quando = quando or date.today()
    return f"{quando.day} de {MESES[quando.month - 1]}"


def saudacao(agora: date | None = None) -> str:
    """A frase do topo. Muda com a hora - e o que faz a tela parecer viva."""
    from datetime import datetime

    hora = datetime.now().hour
    if hora < 12:
        return "Bom dia"
    if hora < 18:
        return "Boa tarde"
    return "Boa noite"


def _no_degrade(rotulo: QLabel, tom: str = "1") -> QLabel:
    """Texto que mora sobre o violeta: branco ("1") ou branco suave ("soft")."""
    rotulo.setProperty("onhero", tom)
    return rotulo


def cabecalho_de_cartao(titulo: str, extra: QWidget | None = None,
                        nota: str = "") -> QHBoxLayout:
    """Titulo de um cartao do Inicio, com etiqueta e nota do lado direito."""
    linha = QHBoxLayout()
    linha.setSpacing(Space.sm)
    linha.addWidget(label(titulo, "section"))
    if extra is not None:
        linha.addWidget(extra, 0, Qt.AlignmentFlag.AlignVCenter)
    linha.addStretch(1)
    if nota:
        linha.addWidget(label(nota, "dim"), 0, Qt.AlignmentFlag.AlignVCenter)
    return linha


class CabecalhoEmpresa(QFrame):
    """A faixa de abertura: quem e a empresa, o dia de hoje e como ele esta.

    E o pedaco que transforma "um programa aberto" em "a minha empresa". O
    violeta e a unica superficie colorida da plataforma inteira - e por isso
    ela e reservada para uma coisa so: dizer de quem e este programa.

    A onda do lado direito e o desenho do dia, e o balao em cima dela diz o
    que interessa: tudo em dia, ou quantos avisos esperam. Sem os dados da
    empresa preenchidos o cabecalho nao fica vazio: convida a preencher, e o
    convite e clicavel.
    """

    configurar = Signal()
    buscar = Signal()

    ALTURA = 218

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette_for(parent) if parent else current_palette()
        self._preenchida = True
        #: (rotulo, valor) do balao sobre a onda
        self._balao = ("", "")
        self.setMinimumHeight(self.ALTURA)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(Space.xxl - 2, Space.xl + 2, Space.xxl - 2, Space.xl)
        linha.setSpacing(Space.xl)

        esquerda = QVBoxLayout()
        esquerda.setSpacing(0)

        topo = QHBoxLayout()
        topo.setSpacing(Space.md)
        self.marca = label("")
        self.marca.setFixedSize(ALTURA_LOGO, ALTURA_LOGO)
        self.marca.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.emblema = IconBadge("home", "#FFFFFF", size=ALTURA_LOGO, radius=12,
                                 estilo="glass")
        topo.addWidget(self.marca)
        topo.addWidget(self.emblema)
        saudar = QVBoxLayout()
        saudar.setSpacing(1)
        self.dia = _no_degrade(label("", "strong"))
        saudar.addWidget(self.dia)
        self.sistemas = _no_degrade(label("", "caption"), "soft")
        saudar.addWidget(self.sistemas)
        topo.addLayout(saudar)
        topo.addStretch(1)
        esquerda.addLayout(topo)
        esquerda.addSpacing(Space.lg + 2)

        # o nome da loja e a primeira coisa que ele ve de manha: tamanho de
        # manchete, nao de titulo de cartao
        self.nome = _no_degrade(label("", "hero"))
        self.nome.setWordWrap(True)
        esquerda.addWidget(self.nome)
        esquerda.addSpacing(Space.xs)
        # endereco e e-mail sao consulta, nao noticia: ficam no branco suave
        self.detalhe = _no_degrade(label("", "body"), "soft")
        self.detalhe.setWordWrap(True)
        esquerda.addWidget(self.detalhe)
        esquerda.addStretch(1)
        esquerda.addSpacing(Space.lg)

        botoes = QHBoxLayout()
        botoes.setSpacing(Space.sm)
        self.botao_empresa = Button("Minha empresa", "edit", "hero", icon_token="#FFFFFF")
        self.botao_empresa.clicked.connect(self.configurar.emit)
        botoes.addWidget(self.botao_empresa)
        self.botao_buscar = Button("Buscar   Ctrl K", "search", "heroLink",
                                   icon_token="#FFFFFF")
        self.botao_buscar.setToolTip("Abre a paleta de comandos")
        self.botao_buscar.clicked.connect(self.buscar.emit)
        botoes.addWidget(self.botao_buscar)
        botoes.addStretch(1)
        esquerda.addLayout(botoes)

        linha.addLayout(esquerda, 11)
        linha.addStretch(9)  # o lugar da onda

    # ------------------------------------------------------------------ dados
    def preencher(self, empresa, paths, sistemas: int, avisos: int | None = None) -> None:
        preenchida = empresa is not None and empresa.preenchida
        self.nome.setText(empresa.nome if preenchida else "Sua empresa")

        if preenchida:
            partes = [p for p in (empresa.endereco_completo, empresa.contato) if p]
            self.detalhe.setText("  ·  ".join(partes) or empresa.tipo_documento)
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        else:
            self.detalhe.setText(
                "Configurações > Minha empresa: o nome da loja passa a assinar "
                "os documentos e as mensagens."
            )
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.botao_empresa.setText(
            "  Minha empresa" if preenchida else "  Preencher dados da empresa"
        )

        self._mostrar_marca(empresa, paths, preenchida)
        self.dia.setText(f"{saudacao()}  ·  {data_por_extenso()}")
        self.sistemas.setText(
            "nenhum sistema liberado" if not sistemas
            else f"{sistemas} sistema{'s' if sistemas > 1 else ''} em uso"
        )
        if avisos is None:
            self._balao = (f"Hoje, {data_curta()}", "")
        else:
            self._balao = (
                f"Hoje, {data_curta()}",
                "Tudo em dia" if not avisos else f"{fmt.contagem(avisos, 'aviso')} para ver",
            )
        self._preenchida = preenchida
        self.update()

    def _mostrar_marca(self, empresa, paths, preenchida: bool) -> None:
        caminho = empresa.caminho_logo(paths) if preenchida else None
        if caminho is not None:
            imagem = QPixmap(str(caminho))
            if not imagem.isNull():
                self.marca.setPixmap(imagem.scaled(
                    QSize(ALTURA_LOGO, ALTURA_LOGO),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                self.marca.setVisible(True)
                self.emblema.setVisible(False)
                return
        self.marca.setVisible(False)
        self.emblema.setVisible(True)

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    # ---------------------------------------------------------------- desenho
    def paintEvent(self, evento) -> None:  # noqa: N802 (Qt)
        p = self._palette
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(self.rect())
        forma = QPainterPath()
        forma.addRoundedRect(area, Radius.xl, Radius.xl)

        degrade = QLinearGradient(area.topLeft(), area.bottomRight())
        degrade.setColorAt(0.0, QColor(p.hero_a))
        degrade.setColorAt(1.0, QColor(p.hero_b))
        pintor.fillPath(forma, degrade)

        pintor.save()
        pintor.setClipPath(forma)
        brilho = QRadialGradient(QPointF(area.width() * 0.86, -area.height() * 0.25),
                                 area.width() * 0.55)
        brilho.setColorAt(0.0, QColor(255, 255, 255, 58))
        brilho.setColorAt(1.0, QColor(255, 255, 255, 0))
        pintor.fillRect(area, brilho)
        self._onda(pintor, area)
        pintor.restore()
        pintor.end()

    def _onda(self, pintor: QPainter, area: QRectF) -> None:
        """A curva do dia, a malha de pontos embaixo dela e o balao."""
        esquerda = area.width() * 0.47
        largura = area.width() - esquerda
        base = area.height()
        topo = area.height() * 0.30
        amostras = 64

        def altura(t: float) -> float:
            forma = (0.54 - 0.19 * math.sin(t * math.pi * 1.7 + 0.5)
                     - 0.24 * t + 0.05 * math.sin(t * math.pi * 5.3))
            return topo + (base - topo) * forma

        pontos = [QPointF(esquerda + largura * i / (amostras - 1),
                          altura(i / (amostras - 1))) for i in range(amostras)]

        # malha: cada coluna de pontos desce da curva e some aos poucos
        pintor.setPen(Qt.PenStyle.NoPen)
        for coluna in range(0, amostras, 2):
            ponto = pontos[coluna]
            peso_coluna = 0.25 + 0.75 * coluna / (amostras - 1)
            for fileira in range(1, 10):
                y = ponto.y() + fileira * 10
                if y > base - 2:
                    break
                alfa = int(78 * (1 - fileira / 10) * peso_coluna)
                pintor.setBrush(QColor(255, 255, 255, alfa))
                pintor.drawEllipse(QPointF(ponto.x(), y), 1.15, 1.15)

        caminho = QPainterPath(pontos[0])
        for ponto in pontos[1:]:
            caminho.lineTo(ponto)
        # a curva nasce do nada na esquerda, em vez de comecar com um corte
        tinta = QLinearGradient(esquerda, 0, esquerda + largura * 0.3, 0)
        tinta.setColorAt(0.0, QColor(255, 255, 255, 0))
        tinta.setColorAt(1.0, QColor(255, 255, 255, 235))
        caneta = QPen(QBrush(tinta), 2.4)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawPath(caminho)

        rotulo, valor = self._balao
        if not rotulo:
            return
        alvo = pontos[int(0.58 * (amostras - 1))]
        guia = QPen(QColor(255, 255, 255, 95), 1)
        guia.setStyle(Qt.PenStyle.DashLine)
        pintor.setPen(guia)
        pintor.drawLine(QPointF(alvo.x(), alvo.y() + 6), QPointF(alvo.x(), base))
        pintor.setPen(QPen(QColor(self._palette.hero_a), 2.6))
        pintor.setBrush(QColor("#FFFFFF"))
        pintor.drawEllipse(alvo, 5.5, 5.5)

        fonte_rotulo, fonte_valor = font_for("caption"), font_for("strong")
        largura_balao = max(QFontMetricsF(fonte_rotulo).horizontalAdvance(rotulo),
                            QFontMetricsF(fonte_valor).horizontalAdvance(valor)) + 26
        altura_balao = 48 if valor else 30
        x = min(max(alvo.x() - largura_balao / 2, esquerda), area.right() - largura_balao - 16)
        y = alvo.y() - altura_balao - 16
        if y < 14:
            y = alvo.y() + 16
        caixa = QRectF(x, y, largura_balao, altura_balao)

        sombra = QPainterPath()
        sombra.addRoundedRect(caixa.translated(0, 5), 11, 11)
        pintor.fillPath(sombra, QColor(24, 12, 70, 46))
        fundo = QPainterPath()
        fundo.addRoundedRect(caixa, 11, 11)
        pintor.fillPath(fundo, QColor("#FFFFFF"))

        # o balao e sempre branco, entao o texto dele e sempre o do tema claro
        pintor.setFont(fonte_rotulo)
        pintor.setPen(QColor(LIGHT.text_muted))
        pintor.drawText(QRectF(x + 13, y + 7, largura_balao - 26, 16),
                        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), rotulo)
        if valor:
            pintor.setFont(fonte_valor)
            pintor.setPen(QColor(LIGHT.text))
            pintor.drawText(QRectF(x + 13, y + 24, largura_balao - 26, 18),
                            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), valor)

    def mouseReleaseEvent(self, evento) -> None:  # noqa: N802 (Qt)
        if not getattr(self, "_preenchida", True):
            self.configurar.emit()
        super().mouseReleaseEvent(evento)


class SinalVital(QWidget):
    """Um numero da vitrine: o que o modulo responde sobre o negocio agora.

    Um bloco cinza sem fio, com o icone num chip neutro. A informacao e o
    numero; o bloco so agrupa. A cor sobrou so onde ela quer dizer alguma
    coisa (prazo estourado, estoque no minimo), e nunca como enfeite.
    """

    clicado = Signal(str)

    def __init__(self, indicador, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.indicador = indicador
        self._palette = palette_for(parent) if parent else current_palette()
        self._realce = Realce(self)
        self.setMinimumHeight(122)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(Space.lg, Space.lg - 2, Space.lg, Space.md + 2)
        coluna.setSpacing(2)

        topo = QHBoxLayout()
        topo.setSpacing(10)
        topo.addWidget(IconBadge(getattr(indicador, "icone", "") or "chart", "text_muted",
                                 size=28, radius=8, estilo="chip"))
        rotulo = label(indicador.rotulo, "field")
        topo.addWidget(rotulo, 1)
        coluna.addLayout(topo)
        coluna.addSpacing(Space.sm)

        coluna.addWidget(
            tone_label(indicador.valor, tom_na_tela(indicador.tom), "metric")
        )
        detalhe = label(indicador.detalhe, "dim")
        detalhe.setWordWrap(True)
        coluna.addWidget(detalhe)
        coluna.addStretch(1)

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, evento) -> None:  # noqa: N802 (Qt)
        p = self._palette
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        forma = QPainterPath()
        forma.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1),
                             Radius.lg, Radius.lg)
        pintor.fillPath(forma, QColor(mix(p.surface_alt, p.surface_hover, self._realce.valor)))
        if self.hasFocus():
            pintor.setPen(QPen(QColor(p.accent), 1.2))
            pintor.drawPath(forma)
        pintor.end()

    def enterEvent(self, evento) -> None:  # noqa: N802
        self._realce.entrar()
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:  # noqa: N802
        self._realce.sair()
        super().leaveEvent(evento)

    def mouseReleaseEvent(self, evento) -> None:  # noqa: N802
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit(self.indicador.app_id)
        super().mouseReleaseEvent(evento)

    def keyPressEvent(self, evento) -> None:  # noqa: N802
        if evento.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicado.emit(self.indicador.app_id)
            return
        super().keyPressEvent(evento)


class VitrineDeSinais(QWidget):
    """Os sinais vitais em blocos do mesmo tamanho, sempre no mesmo ritmo."""

    abrir = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.grade = QGridLayout(self)
        self.grade.setContentsMargins(0, 0, 0, 0)
        self.grade.setHorizontalSpacing(Space.md)
        self.grade.setVerticalSpacing(Space.md)

    @staticmethod
    def colunas_para(quantidade: int) -> int:
        """Quantas colunas deixam as linhas equilibradas.

        Seis sinais em quatro colunas viram 4+2, que parece sobra; em tres
        colunas viram 3+3, que parece proposital - e a sensacao de completude
        vem justamente disso.
        """
        if quantidade <= COLUNAS_SINAIS:
            return max(quantidade, 1)
        linhas = -(-quantidade // COLUNAS_SINAIS)
        return -(-quantidade // linhas)

    def preencher(self, indicadores) -> None:
        while self.grade.count():
            widget = self.grade.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        if not indicadores:
            return
        colunas = self.colunas_para(len(indicadores))
        for posicao, indicador in enumerate(indicadores):
            linha, coluna = divmod(posicao, colunas)
            sinal = SinalVital(indicador, self)
            sinal.clicado.connect(self.abrir.emit)
            self.grade.addWidget(sinal, linha, coluna)
        for coluna in range(colunas):
            self.grade.setColumnStretch(coluna, 1)


class LinhaDeAviso(QWidget):
    """Um assunto que pede atencao, como linha de uma lista.

    Lista se le de cima para baixo, na ordem de urgencia; grade de cartoes
    obriga o olho a varrer em zigue-zague e faz todos parecerem igualmente
    importantes.
    """

    clicado = Signal(str)

    def __init__(self, aviso, aplicativo: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.aviso = aviso
        self._palette = palette_for(parent) if parent else current_palette()
        self._realce = Realce(self)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(Space.sm, Space.md - 2, Space.md, Space.md - 2)
        linha.setSpacing(Space.md)
        linha.addWidget(IconBadge(aviso.icone, aviso.tom, size=36, radius=10),
                        0, Qt.AlignmentFlag.AlignTop)

        texto = QVBoxLayout()
        texto.setSpacing(2)
        # o icone ja carrega a urgencia em cor; so o que e grave acende tambem
        # no titulo, senao cinco ambares na mesma tela nao avisam nada
        titulo = tone_label(
            aviso.titulo, aviso.tom if aviso.tom == "danger" else "text", "strong"
        )
        titulo.setWordWrap(True)
        texto.addWidget(titulo)
        if aviso.detalhe:
            detalhe = label(aviso.detalhe, "caption")
            detalhe.setWordWrap(True)
            texto.addWidget(detalhe)
        linha.addLayout(texto, 1)

        if aplicativo:
            nome = label(aplicativo, "dim")
            nome.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            linha.addWidget(nome, 0, Qt.AlignmentFlag.AlignTop)

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, evento) -> None:  # noqa: N802 (Qt)
        realce = self._realce.valor
        if realce <= 0.01 and not self.hasFocus():
            return
        p = self._palette
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        forma = QPainterPath()
        forma.addRoundedRect(QRectF(0.5, 1.5, self.width() - 1, self.height() - 3),
                             Radius.md, Radius.md)
        fundo = QColor(p.surface_alt)
        fundo.setAlphaF(max(realce, 0.0))
        pintor.fillPath(forma, fundo)
        if self.hasFocus():
            pintor.setPen(QPen(QColor(p.accent), 1.2))
            pintor.drawPath(forma)
        pintor.end()

    def enterEvent(self, evento) -> None:  # noqa: N802
        self._realce.entrar()
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:  # noqa: N802
        self._realce.sair()
        super().leaveEvent(evento)

    def focusInEvent(self, evento) -> None:  # noqa: N802
        self.update()
        super().focusInEvent(evento)

    def focusOutEvent(self, evento) -> None:  # noqa: N802
        self.update()
        super().focusOutEvent(evento)

    def mouseReleaseEvent(self, evento) -> None:  # noqa: N802
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit(self.aviso.app_id)
        super().mouseReleaseEvent(evento)

    def keyPressEvent(self, evento) -> None:  # noqa: N802
        if evento.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicado.emit(self.aviso.app_id)
            return
        super().keyPressEvent(evento)


class PainelDeAvisos(Card):
    """Tudo que pede atencao hoje, num cartao so, na ordem da urgencia.

    E o unico cartao do Inicio que se pinta com a cor da urgencia - faixa na
    lateral, fio e fundo tingidos, titulo na mesma cor. Se todos chamassem
    atencao, nenhum chamaria; este so existe quando ha o que fazer.
    """

    abrir = Signal(str)
    TITULO = "Atenção"
    #: largura da faixa colorida da lateral
    FAIXA = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=Space.lg + 2)
        self._palette = palette_for(parent) if parent else current_palette()
        self._tom = "warning"
        self.body.setContentsMargins(Space.lg + 2 + self.FAIXA, Space.lg + 2,
                                     Space.lg + 2, Space.lg + 2)
        self.body.setSpacing(Space.sm)
        self.contagem = Pill("", "warning")
        self.nota = label("", "dim")

        topo = QHBoxLayout()
        topo.setSpacing(Space.sm + 2)
        self.icone = IconBadge("alert", self._tom, size=30, radius=9)
        topo.addWidget(self.icone, 0, Qt.AlignmentFlag.AlignVCenter)
        self.titulo = tone_label(self.TITULO, self._tom, "cardTitle")
        topo.addWidget(self.titulo, 0, Qt.AlignmentFlag.AlignVCenter)
        topo.addWidget(self.contagem, 0, Qt.AlignmentFlag.AlignVCenter)
        topo.addStretch(1)
        topo.addWidget(self.nota, 0, Qt.AlignmentFlag.AlignVCenter)
        self.body.addLayout(topo)

        self.linhas = QVBoxLayout()
        self.linhas.setContentsMargins(0, 0, 0, 0)
        self.linhas.setSpacing(0)
        self.body.addLayout(self.linhas)
        self.body.addStretch(1)

    def preencher(self, avisos, nomes: dict, sobrando: int = 0) -> None:
        while self.linhas.count():
            item = self.linhas.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        total = len(avisos) + max(sobrando, 0)
        self.contagem.setText(str(total))
        self._tom = "danger" if any(a.tom == "danger" for a in avisos) else "warning"
        self.contagem.set_tone(self._tom)
        self.icone.set_color(self._tom)
        self.titulo.setProperty("tone", self._tom)
        repolish(self.titulo)
        self.update()
        self.nota.setText(
            f"e mais {fmt.contagem(sobrando, 'assunto')} dentro dos aplicativos"
            if sobrando > 0 else ""
        )
        for posicao, aviso in enumerate(avisos):
            if posicao:
                self.linhas.addWidget(separator(tracejado=True))
            linha = LinhaDeAviso(aviso, nomes.get(aviso.app_id, ""), self)
            linha.clicado.connect(self.abrir.emit)
            self.linhas.addWidget(linha)

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, evento) -> None:  # noqa: N802 (Qt)
        super().paintEvent(evento)  # o cartao de sempre, pelo QSS
        cor = QColor(self._palette.resolve(self._tom))
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        forma = QPainterPath()
        forma.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1),
                             Radius.lg, Radius.lg)
        fundo = QColor(cor)
        fundo.setAlphaF(0.06)
        pintor.fillPath(forma, fundo)
        fio = QColor(cor)
        fio.setAlphaF(0.55)
        pintor.setPen(QPen(fio, 1))
        pintor.drawPath(forma)
        # a faixa acompanha a curva do cartao: recortada pela propria forma
        pintor.setClipPath(forma)
        pintor.fillRect(QRectF(0, 0, self.FAIXA, self.height()), cor)
        pintor.end()


class TudoEmDia(Card):
    """O lugar dos avisos quando nao ha aviso nenhum.

    Um espaco vazio aqui pareceria defeito; esta frase e a resposta certa para
    um dia em que nao ha nada pegando fogo.
    """

    def __init__(self, sistemas: int, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=Space.lg + 2)
        self.body.setSpacing(Space.md)
        self.body.addLayout(cabecalho_de_cartao(PainelDeAvisos.TITULO))

        linha = QHBoxLayout()
        linha.setSpacing(Space.md)
        linha.addWidget(IconBadge("check", "success", size=42, radius=12))

        texto = QVBoxLayout()
        texto.setSpacing(2)
        texto.addWidget(tone_label("Tudo em dia", "success", "cardTitle"))
        texto.addWidget(label(
            "Nada vencido, nada atrasado e nada no mínimo."
            if sistemas else
            "Ative a sua licença para o Início começar a acompanhar o negócio.",
            "muted",
        ))
        linha.addLayout(texto, 1)
        self.body.addLayout(linha)
        self.body.addStretch(1)


class PainelContinuar(Card):
    """Os aplicativos que voce usou por ultimo, um por linha."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=Space.lg + 2)
        self.body.setSpacing(Space.sm)
        self.body.addLayout(cabecalho_de_cartao("Continuar de onde parou"))
        self.linhas = QVBoxLayout()
        self.linhas.setContentsMargins(0, 0, 0, 0)
        self.linhas.setSpacing(2)
        self.body.addLayout(self.linhas)
        self.body.addStretch(1)

    def adicionar(self, cartao: QWidget) -> QWidget:
        self.linhas.addWidget(cartao)
        return cartao
