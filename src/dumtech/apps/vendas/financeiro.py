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

from ...core.contas import AReceber, MovimentoDeCaixa
from ...ui import format as fmt
from .models import (
    CANCELADA,
    CONCLUIDA,
    PENDENTE,
    QUITADA_NO_FINANCEIRO,
    RECEBIDO_NO_FINANCEIRO,
    TIPO_SANGRIA,
    TOLERANCIA,
)
from .repository import pagamento_unico
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
            contas.lancar(_conta(venda, venda.total, venda.vencimento))
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


def ajustar(contas, venda) -> str:
    """A venda mudou depois de virar conta. Como `registrar`, nunca levanta."""
    if contas is None:
        return ""
    pendente = venda.status == PENDENTE
    try:
        mudou = contas.ajustar(
            venda.numero,
            valor=venda.total if pendente else None,
            cliente=venda.cliente,
            vencimento=venda.vencimento if pendente else "",
        )
    except Exception:  # noqa: BLE001 - a venda ja esta gravada; a ponte nao desfaz
        logger.exception("Nao foi possivel ajustar a venda no Financeiro")
        return "  Não consegui ajustar no Financeiro - confira a conta."
    return "  Conta ajustada no Financeiro." if mudou else ""


def conciliar(vendas, contas) -> None:
    """Acerta o que aconteceu sem a ponte ficar sabendo.

    Cobre quem cancelou antes de a ponte saber cancelar, o cancelamento que nao
    atravessou (Financeiro indisponivel na hora) e a venda pendente cuja conta
    ja foi recebida: e o que ficou para tras de quando o Financeiro nao avisava.
    Repetir nao muda nada, entao roda toda vez que o Vendas abre.
    """
    if contas is None:
        return
    try:
        for venda in vendas.listar(status=CANCELADA, limite=-1):
            registrar(contas, venda)
        for venda in vendas.listar(status=PENDENTE, limite=-1):
            situacao = contas.situacao(venda.numero)
            if situacao.quitado:
                vendas.receber_pendente(
                    venda.id,
                    [pagamento_unico(situacao.forma or RECEBIDO_NO_FINANCEIRO, venda.total)],
                    # o dinheiro entrou la atras: o caixa de hoje nao o viu
                    gaveta=False, quitada_por=QUITADA_NO_FINANCEIRO,
                )
    except Exception:  # noqa: BLE001 - acerto com defeito nao trava o balcao
        logger.exception("Nao foi possivel acertar as vendas no Financeiro")


def movimento_de_caixa(contas, movimento, destino: str = "retirada") -> str:
    """Sangria e suprimento chegam ao Financeiro. Como `registrar`, nunca levanta.

    `destino` diz o que a sangria virou: "despesa" (pagou algo com o dinheiro
    da gaveta) ou "retirada" (foi para o banco ou para o cofre).
    """
    sangria = movimento.tipo == TIPO_SANGRIA
    return _levar(contas, MovimentoDeCaixa(
        tipo=destino if sangria else "suprimento",
        valor=movimento.valor,
        descricao=movimento.motivo or movimento.tipo_label,
        data=(movimento.criado_em or "")[:10],
        documento=f"CAIXA-{movimento.caixa_id}-M{movimento.id}",
    ))


def fechamento(contas, conferencia) -> str:
    """O que sobrou ou faltou na gaveta e dinheiro de verdade: vira lancamento."""
    caixa = conferencia.caixa
    if caixa is None or abs(caixa.diferenca) < TOLERANCIA:
        return ""
    sobrou = caixa.diferenca > 0
    return _levar(contas, MovimentoDeCaixa(
        tipo="sobra" if sobrou else "quebra",
        valor=abs(caixa.diferenca),
        descricao=f"{'Sobra' if sobrou else 'Quebra'} do caixa de {fmt.data(caixa.aberto_em)}",
        data=(caixa.fechado_em or "")[:10],
        documento=f"CAIXA-{caixa.id}",
    ))


def _levar(contas, movimento: MovimentoDeCaixa) -> str:
    if contas is None:
        return ""
    try:
        contas.movimento_de_caixa(movimento)
    except Exception:  # noqa: BLE001 - o caixa ja gravou; a ponte nao desfaz
        logger.exception("Nao foi possivel levar o movimento de caixa ao Financeiro")
        return "  Não consegui lançar no Financeiro - lance na mão."
    return "  Lançado também no Financeiro."


def _conta(venda, valor: float, vencimento: str = "") -> AReceber:
    recorrente = bool(venda.recorrencia)
    return AReceber(
        descricao=f"Venda {venda.numero}"
                  + (f" · recorrente {venda.recorrencia}" if recorrente else ""),
        valor=valor, vencimento=vencimento or venda.data,
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
    contas.lancar_parcelado(_conta(venda, parcelado.valor, venda.vencimento),
                            parcelado.parcelas)
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
