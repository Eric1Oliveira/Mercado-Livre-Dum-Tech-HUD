"""Quando a tela e maior que o monitor, a pagina rola - nao corta.

O QUE ESTE ARQUIVO RESOLVE

Um painel com quatro cartoes, um grafico e uma lista pede cerca de 610 pixels
de altura para existir. Num monitor de 1280x720 sobram, depois da barra de
titulo do Windows, da barra de tarefas, da barra do topo do Hub e da barra do
aplicativo, por volta de 520. O Qt nao encolhe abaixo do minimo de quem esta
dentro: ele deixa a janela maior que a area util, e o resto fica embaixo da
barra de tarefas - foi o que cortava os botoes do Balcao.

`Rolagem` e a saida honesta: em monitor grande ela desaparece (a tela recebe
todo o espaco, exatamente como antes) e em monitor pequeno aparece uma barra
de rolagem fina em vez de um pedaco faltando.

POR QUE ISSO DESTRAVA A JANELA

A area de rolagem nao repassa para cima o minimo de quem esta dentro dela.
Sem isso, cada aplicativo aberto empurrava a altura minima do Hub para mais de
760 pixels, e nenhum ajuste de janela conseguia baixar disso.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QWidget


class Rolagem(QScrollArea):
    """Embrulha uma tela: rola so quando o espaco nao da."""

    def __init__(self, tela: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tela = tela
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        # o conteudo acompanha a largura da janela; a altura so cresce alem do
        # visivel quando a tela realmente precisa de mais
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.viewport().setAutoFillBackground(False)
        self.setWidget(tela)


def rolavel(tela: QWidget) -> Rolagem:
    """Atalho: `rolavel(minha_tela)` no lugar de montar a area na mao."""
    return Rolagem(tela)
