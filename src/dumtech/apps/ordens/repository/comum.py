"""Pedacos usados por todas as regras da Ordem de Servico."""

from __future__ import annotations

from datetime import datetime


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def dinheiro(valor) -> float:
    return round(float(valor or 0), 2)


def quantidade(valor) -> float:
    return round(float(valor or 0), 3)
