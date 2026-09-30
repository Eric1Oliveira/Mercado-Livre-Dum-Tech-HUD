"""Pecas usadas por todas as partes das regras do Estoque."""

from __future__ import annotations

from datetime import datetime

#: quantidade e dinheiro sao guardados arredondados; comparar float cru
#: ("0.1 + 0.2 == 0.3" e falso) daria erro de saldo na cara do usuario.
CASAS_QUANTIDADE = 3
EPSILON = 1e-6


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def quantidade(valor) -> float:
    """Normaliza uma quantidade vinda da interface ou de uma planilha."""
    return round(float(valor or 0), CASAS_QUANTIDADE)


def dinheiro(valor) -> float:
    return round(float(valor or 0), 2)


def maior_que(a: float, b: float) -> bool:
    """a > b levando em conta o erro do ponto flutuante."""
    return (a - b) > EPSILON


def igual(a: float, b: float) -> bool:
    return abs(a - b) <= EPSILON
