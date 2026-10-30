"""Toda venda cai no Financeiro - a prazo como conta, a vista como recebida.

Antes so a venda pendente atravessava: o dinheiro que entrava na gaveta nunca
aparecia no Financeiro, e o dono via o mes "vazio" com o caixa cheio. A regra
mora aqui, uma vez so, para o Balcao e a lista de Vendas falarem a mesma coisa.

O documento (numero da venda) e a chave: a mesma venda nunca vira duas contas.
A venda parcelada vira uma conta por mes, todas com o mesmo documento, e a
cancelada sai das contas pelo mesmo caminho.
"""

from __future__ import annotations

import logging

from ...core.contas import AReceber
from .models import CANCELADA, CONCLUIDA, PENDENTE
from .repository.comum import dinheiro

logger = logging.getLogger(__name__)


def registrar(contas, venda) -> str:
    """Leva a venda ao Financeiro e devolve o recado para a tela ("" = nada).

    Nunca levanta: a venda ja esta gravada, e a ponte nao pode desfaze-la.
    """
    if contas is None:
        return ""
    if venda.status == CANCELADA:
        return _cancelar(contas, venda)
    if venda.status not in (PENDENTE, CONCLUIDA):
        return ""
    try:
        if not contas.ja_lancado(venda.numero):
            if venda.parcelamento is not None:
                return _parcelar(contas, venda)
            contas.lancar(_conta(venda, venda.total))
            if venda.status == PENDENTE:
                return "  Conta a receber criada no Financeiro."
        elif venda.status == PENDENTE or venda.parcelamento is not None:
            # quitar aqui receberia uma parcela que ninguem pagou
            return ""
        contas.quitar(venda.numero, forma=venda.resumo_pagamento)
    except Exception:  # noqa: BLE001 - a venda ja esta gravada; a ponte nao
        logger.exception("Nao foi possivel lancar a venda no Financeiro")
        return "  Não consegui lançar no Financeiro - lance na mão."
    return "  Recebimento lançado no Financeiro."


def devolver(contas, venda, devolucao) -> str:
    """Leva a devolucao ao Financeiro. Como `registrar`, nunca levanta."""
    if contas is None:
        return ""
    try:
        levou = contas.devolver(venda.numero, devolucao.valor, devolucao.data,
                                motivo=devolucao.motivo, cliente=venda.cliente)
    except Exception:  # noqa: BLE001 - a devolucao ja esta gravada; a ponte nao desfaz
        logger.exception("Nao foi possivel lancar a devolucao no Financeiro")
        return "  Não consegui lançar no Financeiro - lance na mão."
    return "  Lançada também no Financeiro." if levou else ""


def conciliar(vendas, contas) -> None:
    """Acerta no Financeiro o que foi cancelado sem a ponte ficar sabendo.

    Cobre quem cancelou antes de a ponte saber cancelar e o cancelamento que
    nao atravessou (Financeiro indisponivel na hora). Repetir nao muda nada,
    entao roda toda vez que o Vendas abre.
    """
    if contas is None:
        return
    try:
        for venda in vendas.listar(status=CANCELADA):
            registrar(contas, venda)
    except Exception:  # noqa: BLE001 - acerto com defeito nao trava o balcao
        logger.exception("Nao foi possivel acertar as vendas canceladas no Financeiro")


def _conta(venda, valor: float) -> AReceber:
    recorrente = bool(venda.recorrencia)
    return AReceber(
        descricao=f"Venda {venda.numero}"
                  + (f" · recorrente {venda.recorrencia}" if recorrente else ""),
        valor=valor, vencimento=venda.data,
        cliente=venda.cliente,
        categoria="Vendas recorrentes" if recorrente else "Vendas",
        documento=venda.numero,
        recorrencia=venda.recorrencia,
    )


def _parcelar(contas, venda) -> str:
    """Uma conta por mes; o que foi pago na hora entra ja recebido."""
    parcelado = venda.parcelamento
    entrada = dinheiro(venda.total - parcelado.valor)
    if entrada > 0:
        contas.lancar(_conta(venda, entrada))
        contas.quitar(venda.numero, forma=" + ".join(
            p.rotulo for p in venda.pagamentos if not p.parcelado
        ))
    contas.lancar_parcelado(_conta(venda, parcelado.valor), parcelado.parcelas)
    return f"  {parcelado.parcelas} parcelas lançadas no Financeiro."


def _cancelar(contas, venda) -> str:
    """Tira a venda das contas. Da parcelada, so o que ainda nao entrou."""
    parcelada = venda.parcelamento is not None
    try:
        canceladas = contas.cancelar(
            venda.numero, venda.motivo_cancelamento,
            # a tela antiga de edicao nao gravava a data: fica a da venda, senao
            # um cancelamento de meses atras cairia todo no mes de agora
            manter_pagos=parcelada, quando=venda.cancelada_em or venda.data,
        )
    except Exception:  # noqa: BLE001 - a venda ja foi cancelada; a ponte nao desfaz
        logger.exception("Nao foi possivel cancelar a venda no Financeiro")
        return "  Não consegui cancelar no Financeiro - ajuste na mão."
    if not canceladas:
        return ""
    if parcelada:
        return (f"  {canceladas} parcela(s) em aberto cancelada(s) no Financeiro; "
                "o que já foi recebido continua lá.")
    return "  Cancelada também no Financeiro."
