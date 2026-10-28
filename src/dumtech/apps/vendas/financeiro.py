"""Toda venda cai no Financeiro - a prazo como conta, a vista como recebida.

Antes so a venda pendente atravessava: o dinheiro que entrava na gaveta nunca
aparecia no Financeiro, e o dono via o mes "vazio" com o caixa cheio. A regra
mora aqui, uma vez so, para o Balcao e a lista de Vendas falarem a mesma coisa.

O documento (numero da venda) e a chave: a mesma venda nunca vira duas contas.
"""

from __future__ import annotations

import logging

from ...core.contas import AReceber
from .models import CONCLUIDA, PENDENTE

logger = logging.getLogger(__name__)


def registrar(contas, venda) -> str:
    """Leva a venda ao Financeiro e devolve o recado para a tela ("" = nada).

    Nunca levanta: a venda ja esta gravada, e a ponte nao pode desfaze-la.
    """
    if contas is None or venda.status not in (PENDENTE, CONCLUIDA):
        return ""
    try:
        if not contas.ja_lancado(venda.numero):
            contas.lancar(AReceber(
                descricao=f"Venda {venda.numero}",
                valor=venda.total, vencimento=venda.data,
                cliente=venda.cliente, categoria="Vendas",
                documento=venda.numero,
            ))
            if venda.status == PENDENTE:
                return "  Conta a receber criada no Financeiro."
        elif venda.status == PENDENTE:
            return ""
        contas.quitar(venda.numero, forma=venda.resumo_pagamento)
    except Exception:  # noqa: BLE001 - a venda ja esta gravada; a ponte nao
        logger.exception("Nao foi possivel lancar a venda no Financeiro")
        return "  Não consegui lançar no Financeiro - lance na mão."
    return "  Recebimento lançado no Financeiro."
