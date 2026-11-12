"""Toda janela cabe no monitor - inteira, com os botoes de baixo a vista.

O PROBLEMA

Num notebook de 1366x768 com o Windows em 125% (o padrao de fabrica), o Qt
enxerga uma tela de 1093x614 - e, tirando a barra de tarefas, sobram uns 576
pixels de altura. Os cadastros pediam de 580 a 770: a janela nascia maior que
a area util e o rodape, com o Salvar, ficava atras da barra de tarefas.

A SAIDA

`caber_na_tela` roda no instante em que a janela aparece (o vigia de
`motion.acompanhar`, por onde toda janela da plataforma passa): se ela nao cabe,
encolhe ate caber e volta para dentro da area util. Quem tem muito conteudo
(o `FormDialog`) rola o miolo - cabecalho e botoes ficam sempre parados.

DEPOIS DE ABERTA

O conteudo muda com a janela na tela: escolher Pix no Receber abre o QR
Code, escolher Parcelado abre as parcelas. O Qt crescia a janela so para
baixo, com o topo parado, e o Receber ia parar atras da barra de tarefas.
`vigiar` liga o `reajustar`: a janela acompanha o conteudo - cresce, ou volta
ao tamanho com que abriu -, continua centrada sobre o Hub e nunca passa da
tela (o que nao couber, o miolo rola).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

#: o que o Windows desenha POR FORA da geometria do widget: bordas dos lados e
#: barra de titulo + borda de baixo
MOLDURA_LARGURA = 16
MOLDURA_ALTURA = 40

#: respiro entre a janela e a borda da area util
FOLGA = 8


def area_util(janela: QWidget) -> QRect:
    """A area util do monitor onde a janela vai aparecer (o do Hub, se houver)."""
    pai = janela.parentWidget()
    tela = (pai.window().screen() if pai is not None else None) or janela.screen() \
        or QGuiApplication.primaryScreen()
    return tela.availableGeometry()


def tamanho_maximo(janela: QWidget) -> QSize:
    """O maior tamanho de janela que cabe inteiro, moldura incluida."""
    util = area_util(janela)
    return QSize(util.width() - MOLDURA_LARGURA - 2 * FOLGA,
                 util.height() - MOLDURA_ALTURA - 2 * FOLGA)


def moldura_real(janela: QWidget) -> tuple[int, int]:
    """A moldura medida de uma janela que ja esta na tela.

    Com a estimativa (`MOLDURA_*`), cada reajuste errava o centro por alguns
    pixels - e alternar Pix e Dinheiro fazia a janela andar pela tela.
    """
    fora, dentro = janela.frameGeometry(), janela.geometry()
    return fora.width() - dentro.width(), fora.height() - dentro.height()


def caber_na_tela(janela: QWidget, centralizar: bool = False,
                  centro: QPoint | None = None) -> None:
    """Encolhe o que passa da tela e traz a janela inteira para dentro dela.

    Janela que ja cabe fica exatamente como estava. Se precisou encolher, ela
    volta a ficar centrada sobre o Hub (ou no monitor, sem Hub). `centro`
    centraliza num ponto dado - o da propria janela, quando ela cresce: ai ela
    ja esta na tela, e a moldura e medida em vez de estimada.
    """
    maximo = tamanho_maximo(janela)
    # o minimo pedido pela propria janela tambem cede: senao o resize nao encolhe
    if janela.minimumWidth() > maximo.width():
        janela.setMinimumWidth(maximo.width())
    if janela.minimumHeight() > maximo.height():
        janela.setMinimumHeight(maximo.height())
    largura = min(janela.width(), maximo.width())
    altura = min(janela.height(), maximo.height())
    if (largura, altura) != (janela.width(), janela.height()):
        janela.resize(largura, altura)
        centralizar = True

    util = area_util(janela)
    moldura_l, moldura_a = (moldura_real(janela) if centro is not None
                            else (MOLDURA_LARGURA, MOLDURA_ALTURA))
    por_fora_l = largura + moldura_l
    por_fora_a = altura + moldura_a
    if centralizar or centro is not None:
        if centro is None:
            pai = janela.parentWidget()
            centro = pai.window().frameGeometry().center() if pai is not None else util.center()
        x, y = centro.x() - por_fora_l // 2, centro.y() - por_fora_a // 2
    else:
        x, y = janela.x(), janela.y()
    # a barra de titulo nunca acima do topo; o rodape nunca abaixo da barra de tarefas
    x = max(util.left(), min(x, util.right() + 1 - por_fora_l))
    y = max(util.top(), min(y, util.bottom() + 1 - por_fora_a))
    if (x, y) != (janela.x(), janela.y()):
        janela.move(x, y)


# ------------------------------------------------------------- reajuste ---
def natural_com_miolo(janela: QWidget, interno: QWidget, area: QWidget,
                      largura: int = 0) -> QSize:
    """O tamanho de uma janela cujo miolo (`interno`) rola dentro de `area`.

    A area de rolagem nao serve de regua: o Qt limita o "tamanho ideal" dela
    a algumas linhas, e a janela nascia apertada. A conta e feita com o
    conteudo de verdade, na largura em que ele vai ficar.
    """
    margens = janela.layout().contentsMargins()
    lados = margens.left() + margens.right()
    # a largura de sempre; so cresce se o conteudo nao couber nela
    largura = max(largura, janela.minimumWidth(), interno.minimumSizeHint().width() + lados)
    miolo = interno.layout()
    altura = (miolo.totalHeightForWidth(largura - lados) if miolo.hasHeightForWidth()
              else interno.sizeHint().height())
    moldura = janela.layout().sizeHint().height() - area.sizeHint().height()
    # a margem extra evita uma barra de rolagem por arredondamento
    natural = QSize(largura, altura + moldura + 2)
    if natural.height() > tamanho_maximo(janela).height():
        # vai rolar: a barra de rolagem come a largura do miolo, que sem isto
        # ganhava uma segunda barra, de lado, e cortava o que fica na direita
        natural.setWidth(largura + area.verticalScrollBar().sizeHint().width())
    return natural


def tamanho_natural(janela: QWidget) -> QSize:
    """O tamanho em que tudo aparece sem rolar.

    Quem rola o miolo sabe medir a si mesmo (`tamanho_natural`): a area de
    rolagem nao serve de regua, o Qt limita o tamanho ideal dela.
    """
    medir = getattr(janela, "tamanho_natural", None)
    natural = medir() if callable(medir) else janela.sizeHint()
    return natural.expandedTo(janela.minimumSizeHint())


def reajustar(janela: QWidget) -> None:
    """O conteudo mudou: a janela acompanha, sem sair do centro nem da tela.

    Cresce (ou volta) em volta do proprio centro: abriu centrada sobre o Hub,
    continua centrada; quem a arrastou para o lado nao a ve pular de volta.
    Nunca fica menor que a base - o tamanho com que abriu, ou o que a pessoa
    escolheu puxando a borda: quem abriu grande de proposito (a folha A4, o
    comprovante) nao encolhe por causa de um aviso.
    """
    filtro = getattr(janela, "_dt_reajuste", None)
    base = filtro.base if filtro is not None else None
    if base is None or not janela.isVisible() or janela.isMaximized():
        return
    natural = tamanho_natural(janela)
    maximo = tamanho_maximo(janela)
    largura = min(max(base.width(), natural.width()), maximo.width())
    altura = min(max(base.height(), natural.height()), maximo.height())
    if abs(largura - janela.width()) <= 1 and abs(altura - janela.height()) <= 1:
        return
    centro = janela.frameGeometry().center()
    filtro.pedir(QSize(largura, altura))
    janela.resize(largura, altura)
    caber_na_tela(janela, centro=centro)


class _Reajuste(QObject):
    """Ouve o conteudo mudar e reajusta a janela uma vez, depois da mudanca.

    Varias mudancas seguidas (esconder uma linha e mostrar outra) viram um
    reajuste so: ele roda quando o Qt termina de processar a rodada.
    """

    def __init__(self, janela: QWidget) -> None:
        super().__init__(janela)
        self._janela = janela
        #: o tamanho com que a janela abriu; None ate ela aparecer
        self.base: QSize | None = None
        #: os ultimos tamanhos que o reajuste pediu: o resto e escolha da pessoa
        self._pedidos: list[QSize] = []
        self._marcado = False

    def pedir(self, tamanho: QSize) -> None:
        self._pedidos = (self._pedidos + [tamanho])[-6:]

    def anotar_base(self) -> None:
        """Depois que a janela aparece e se arruma: e dali que ela parte."""
        QTimer.singleShot(0, self, self._anotar)

    def _anotar(self) -> None:
        if self._janela.isVisible():
            self.base = self._janela.size()

    def eventFilter(self, obj, evento) -> bool:  # noqa: N802 (Qt)
        tipo = evento.type()
        if tipo == QEvent.Type.Resize and obj is self._janela and self.base is not None:
            self._redimensionou(evento.size(), evento.oldSize())
        elif tipo == QEvent.Type.LayoutRequest and self.base is not None and not self._marcado:
            self._marcado = True
            QTimer.singleShot(0, self, self._rodar)
        return False

    def _redimensionou(self, novo: QSize, velho: QSize) -> None:
        """Quem mudou o tamanho: o reajuste, o Qt ou a pessoa?

        O Qt cresce a janela sem miolo rolavel ate o minimo novo, na hora em
        que o conteudo aparece - com o topo parado, para baixo. Esse volta ao
        centro antes de pintar. O resto e a pessoa puxando a borda: o tamanho
        que ela escolheu passa a ser a base. (O Windows pode avisar o tamanho
        pedido depois do pedido; por isso a lista, e nao so o ultimo.)
        """
        if novo in self._pedidos or not velho.isValid():
            return
        janela = self._janela
        cresceu = ((novo.height() > velho.height() and novo.height() == janela.minimumHeight())
                   or (novo.width() > velho.width() and novo.width() == janela.minimumWidth()))
        if cresceu:
            janela.move(janela.x() - (novo.width() - velho.width()) // 2,
                        janela.y() - (novo.height() - velho.height()) // 2)
            caber_na_tela(janela)
            return
        self.base = novo

    def _rodar(self) -> None:
        self._marcado = False
        reajustar(self._janela)


def vigiar(janela: QWidget, *conteudos: QWidget) -> _Reajuste:
    """Liga o reajuste na janela - e no miolo que rola, quando ha um.

    O miolo dentro de uma area de rolagem muda sem a janela ficar sabendo:
    por isso ele e vigiado tambem. Chamar de novo nao duplica nada.
    """
    filtro = getattr(janela, "_dt_reajuste", None)
    if filtro is None:
        filtro = _Reajuste(janela)
        janela._dt_reajuste = filtro
        janela.installEventFilter(filtro)
    for conteudo in conteudos:
        conteudo.installEventFilter(filtro)
    return filtro
