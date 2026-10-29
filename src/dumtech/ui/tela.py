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
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize
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


def caber_na_tela(janela: QWidget, centralizar: bool = False) -> None:
    """Encolhe o que passa da tela e traz a janela inteira para dentro dela.

    Janela que ja cabe fica exatamente como estava. Se precisou encolher, ela
    volta a ficar centrada sobre o Hub (ou no monitor, sem Hub).
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
    por_fora_l = largura + MOLDURA_LARGURA
    por_fora_a = altura + MOLDURA_ALTURA
    if centralizar:
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
