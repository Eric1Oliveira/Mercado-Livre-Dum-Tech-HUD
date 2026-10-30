"""Pedacos usados por todas as regras do Financeiro."""

from __future__ import annotations

import uuid
from datetime import datetime

from ..models import CENTAVO

#: filtros de situacao usados pela lista
SITUACAO_ABERTO = "aberto"
SITUACAO_PAGO = "pago"
SITUACAO_VENCIDO = "vencido"
SITUACAO_PARCIAL = "parcial"
SITUACAO_CANCELADO = "cancelado"

#: soma o que ja foi baixado de cada lancamento, sem gravar isso duas vezes
BAIXADO = """
    COALESCE((SELECT SUM(b.valor) FROM baixas b WHERE b.lancamento_id = l.id), 0)
"""

SELECT_LANCAMENTO = f"SELECT l.*, {BAIXADO} AS baixado FROM lancamentos l"


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def dinheiro(valor) -> float:
    return round(float(valor or 0), 2)


def maior_que(a: float, b: float) -> bool:
    """`a` e maior que `b` de verdade (nao por arredondamento)."""
    return (a - b) > CENTAVO


def novo_grupo() -> str:
    """Identificador dos lancamentos que nasceram juntos."""
    return uuid.uuid4().hex[:12]
