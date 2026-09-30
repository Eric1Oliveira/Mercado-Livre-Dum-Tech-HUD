"""Regras do DumTech Financeiro.

Toda a logica fica aqui, fora da interface. O arquivo unico virou um pacote
quando o modulo deixou de ser uma lista de contas e virou um controle de fluxo
de caixa.

    lancamentos.py  contas a pagar/receber, parcelamento e recorrencia
    baixas.py       o momento em que o dinheiro andou (total ou parcial)
    contas.py       onde o dinheiro esta e transferencia entre contas
    fluxo.py        a projecao de 30 dias e os numeros do painel
"""

from __future__ import annotations

from ....core.database import Database
from ..models import Baixa, Conta, Lancamento, Projecao, ResumoFinanceiro, Transferencia
from .baixas import BaixasMixin
from .comum import (
    SITUACAO_ABERTO,
    SITUACAO_PAGO,
    SITUACAO_PARCIAL,
    SITUACAO_VENCIDO,
)
from .contas import ContasMixin
from .fluxo import HORIZONTE, FluxoMixin
from .lancamentos import LancamentosMixin, dividir, proximo_vencimento

__all__ = [
    "FinanceiroRepository",
    "Baixa",
    "Conta",
    "Lancamento",
    "Projecao",
    "ResumoFinanceiro",
    "Transferencia",
    "SITUACAO_ABERTO",
    "SITUACAO_PAGO",
    "SITUACAO_PARCIAL",
    "SITUACAO_VENCIDO",
    "HORIZONTE",
    "dividir",
    "proximo_vencimento",
]


class FinanceiroRepository(LancamentosMixin, BaixasMixin, ContasMixin, FluxoMixin):
    """Tudo que o DumTech Financeiro sabe fazer."""

    def __init__(self, database: Database) -> None:
        self.db = database
