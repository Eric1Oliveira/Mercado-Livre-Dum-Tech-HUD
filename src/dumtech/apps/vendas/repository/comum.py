"""Arredondamento e comparacao de dinheiro, usados por todas as regras."""

from __future__ import annotations

from datetime import datetime

#: meio centavo: abaixo disso, dois valores sao o mesmo dinheiro
CENTAVO = 0.005


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def dinheiro(valor) -> float:
    return round(float(valor or 0), 2)


def quantidade(valor) -> float:
    return round(float(valor or 0), 3)


def maior_que(a: float, b: float) -> bool:
    """`a` e maior que `b` de verdade (nao por arredondamento)."""
    return (a - b) > CENTAVO


def sobrou(a: float, b: float) -> float:
    """Quanto falta de `a` para `b`, nunca negativo."""
    return dinheiro(max(a - b, 0.0))
