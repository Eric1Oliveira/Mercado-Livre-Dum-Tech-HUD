"""A pilha de telas da plataforma: um QStackedWidget que nao faz conta a toa.

Quando a tela da frente tem altura que depende da largura (um rotulo que
quebra linha, a barra de acoes que quebra em duas), o QStackedWidget de
fabrica passa a perguntar essa altura para TODAS as telas da pilha - inclusive
as escondidas. Com sete aplicativos abertos isso virava milhares de contas por
troca de tela: cada lista escondida redistribuindo a propria barra de acoes em
Python, cada rotulo escondido medindo o proprio texto de novo. Medido: trocar
de tela caia de 169 ms para 19 ms so com esta classe.

A pilha sempre ocupa todo o espaco que recebe, entao essa altura nao serve
para nada aqui. A tela da frente continua se organizando sozinha dentro do
espaco dela - so a pergunta para cima deixa de existir.
"""

from __future__ import annotations

from PySide6.QtWidgets import QStackedWidget


class Pilha(QStackedWidget):
    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt)
        return False
