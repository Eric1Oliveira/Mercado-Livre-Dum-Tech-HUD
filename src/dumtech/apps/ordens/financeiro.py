"""O que acontece com a ordem acontece com a conta dela.

A conta nasce em tres lugares (entrega, botao Financeiro e contrato recorrente).
Daqui so saem os caminhos de volta: sem isto, a ordem cancelada seguia cobrando o
cliente, e a ordem editada cobrava o valor velho. Como em
`apps/vendas/financeiro.py`, nada aqui levanta: a ordem ja esta gravada.
"""

from __future__ import annotations

import logging

from ...core.contas import AReceber, vencimento_padrao

logger = logging.getLogger(__name__)


def cancelar(contas, ordem, motivo: str) -> str:
    """Tira a ordem das contas; a baixa que existia e desfeita junto."""
    if contas is None:
        return ""
    try:
        saiu = contas.cancelar(ordem.numero, motivo)
    except Exception:  # noqa: BLE001
        logger.exception("Nao foi possivel cancelar a ordem no Financeiro")
        return "  Não consegui cancelar no Financeiro - ajuste na mão."
    return "  Conta cancelada no Financeiro." if saiu else ""


def ajustar(contas, ordem) -> str:
    """O valor ou o cliente mudou depois de a ordem virar conta."""
    if contas is None or not ordem.numero:
        return ""
    try:
        mudou = contas.ajustar(ordem.numero, valor=ordem.total, cliente=ordem.cliente)
    except Exception:  # noqa: BLE001
        logger.exception("Nao foi possivel ajustar a ordem no Financeiro")
        return "  Não consegui ajustar no Financeiro - confira a conta."
    return "  Conta ajustada no Financeiro." if mudou else ""


def da_proposta(contas, ordem) -> None:
    """A proposta aprovada ja e dinheiro combinado: nasce a conta a receber."""
    if contas is None or ordem.total <= 0 or contas.ja_lancado(ordem.numero):
        return
    contas.lancar(AReceber(
        descricao=f"Ordem {ordem.numero}" + (f" - {ordem.assunto}" if ordem.assunto else ""),
        valor=ordem.total, vencimento=vencimento_padrao(),
        cliente=ordem.cliente, categoria="Serviços", documento=ordem.numero,
    ))
