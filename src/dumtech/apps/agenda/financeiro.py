"""O dinheiro da Agenda: o sinal que segura o horario.

O sinal entra na hora: o cliente pagou para reservar. Vai para o Financeiro ja
recebido e, quando o atendimento vira venda, sai do total. Como nas outras
pontes, nada aqui levanta: o compromisso ja esta gravado.
"""

from __future__ import annotations

import logging
from datetime import date

from ...core.contas import AReceber

logger = logging.getLogger(__name__)


def lancar_sinal(contas, compromisso) -> str:
    """Leva o sinal ao Financeiro. O numero do compromisso impede lancar duas vezes."""
    if contas is None or compromisso.sinal <= 0 or compromisso.id is None:
        return ""
    documento = f"AG-{compromisso.id}"
    try:
        if contas.ja_lancado(documento):
            return ""
        contas.lancar(AReceber(
            descricao=f"Sinal - {compromisso.titulo}", valor=compromisso.sinal,
            vencimento=date.today().isoformat(), cliente=compromisso.cliente,
            categoria="Sinais", documento=documento,
        ))
        contas.quitar(documento)
    except Exception:  # noqa: BLE001 - o compromisso ja esta gravado
        logger.exception("Nao foi possivel lancar o sinal no Financeiro")
        return "Não consegui lançar o sinal no Financeiro - lance na mão."
    return "Sinal lançado no Financeiro."
