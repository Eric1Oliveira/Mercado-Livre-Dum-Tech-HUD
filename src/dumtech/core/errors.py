"""Erros de regra de negocio da plataforma.

Um `RegraError` carrega uma mensagem ja escrita para o usuario final: a tela
so precisa mostra-la. Serve para separar "o programa quebrou" (bug, vai para o
log) de "isso nao pode ser feito" (regra, vai para a tela).
"""

from __future__ import annotations


class RegraError(Exception):
    """Operacao recusada por uma regra do aplicativo."""
