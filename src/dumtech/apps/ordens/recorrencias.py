"""Servico recorrente: cada vez do contrato abre uma ordem no Quadro.

A preventiva do ar-condicionado a cada tres meses, a limpeza mensal da
piscina: a ordem aparece sozinha na coluna "Aberta" alguns dias antes
(`ANTECEDENCIA`), com o prazo na data combinada - o tecnico ve o que vem pela
frente e a ordem fica atrasada se a data passar.

A conta a receber nasce junto, no Financeiro, com vencimento na data: e o
dinheiro do contrato que o dono quer enxergar. Na entrega, se o cliente paga
na hora, e essa mesma conta que fecha (`dialogos.EntregaDialog`).
"""

from __future__ import annotations

import logging
from datetime import date

from ...core import recorrencia
from ...core.contas import AReceber
from .models import ABERTA, PECA, SERVICO, ItemOS, Ordem

logger = logging.getLogger(__name__)

#: quantos dias antes a ordem entra no Quadro. Menos que no Vendas: ordem e
#: trabalho na tela do tecnico, e um mes de antecedencia lotaria a coluna
ANTECEDENCIA = 7
PREFIXO = "OSREC"


def repositorio(database) -> recorrencia.RecorrenciasRepository:
    return recorrencia.RecorrenciasRepository(database, PREFIXO)


def gerar(ordens, contas=None, contatos=None, hoje: date | None = None) -> list[str]:
    """Abre as ordens devidas e leva cada uma ao Financeiro. Devolve os numeros."""
    contratos = repositorio(ordens.db)
    hoje = hoje or date.today()

    def criar(rec: recorrencia.Recorrencia, quando: date) -> str:
        ja = ordens.db.query_one(
            "SELECT numero FROM ordens WHERE recorrencia = ? AND prazo = ?",
            (rec.numero, quando.isoformat()),
        )
        if ja is not None:
            return ""  # aberta numa rodada que caiu antes de anotar o avanco
        ordem = ordens.salvar(Ordem(
            numero=ordens.proximo_numero(),
            cliente=rec.cliente,
            telefone=_telefone(contatos, rec.cliente),
            equipamento=rec.descricao,
            defeito=rec.observacoes or f"Serviço recorrente ({rec.frequencia_label.lower()})",
            status=ABERTA,
            aberta_em=min(hoje, quando).isoformat(),
            prazo=quando.isoformat(),
            desconto=rec.desconto,
            observacoes=f"Gerada do contrato recorrente {rec.numero}",
            recorrencia=rec.numero,
            itens=[_item(item) for item in rec.itens],
        ))
        lancar(contas, ordem, rec)
        return ordem.numero

    return recorrencia.gerar(contratos, criar, hoje=hoje, antecedencia=ANTECEDENCIA)


def contrato(
    contratos: recorrencia.RecorrenciasRepository, ordem: Ordem, frequencia: str, fim: str = "",
) -> recorrencia.Recorrencia:
    """O contrato que repete a ordem: ela e a primeira vez, as proximas vem dele.

    Ordem sem itens vale o que foi digitado, e o contrato precisa de uma linha
    para cobrar esse valor.
    """
    itens = [
        {
            "descricao": item.descricao,
            "quantidade": item.quantidade,
            "valor_unitario": item.valor_unitario,
            "produto_id": item.produto_id,
            "codigo": item.codigo,
        }
        for item in ordem.itens
    ] or [{"descricao": ordem.assunto, "quantidade": 1, "valor_unitario": ordem.subtotal}]
    return recorrencia.Recorrencia(
        numero=contratos.proximo_numero(),
        cliente=ordem.cliente,
        descricao=ordem.assunto,
        frequencia=frequencia,
        inicio=ordem.prazo,
        fim=fim,
        indice=1,
        desconto=ordem.desconto,
        observacoes=ordem.defeito,
        itens=itens,
    )


def contar_geradas(ordens, contratos: list[recorrencia.Recorrencia]) -> None:
    contagem = {
        row["recorrencia"]: int(row["quantas"])
        for row in ordens.db.query(
            "SELECT recorrencia, COUNT(*) AS quantas FROM ordens"
            " WHERE recorrencia <> '' GROUP BY recorrencia"
        )
    }
    for rec in contratos:
        rec.gerados = contagem.get(rec.numero, 0)


def lancar(contas, ordem: Ordem, rec: recorrencia.Recorrencia) -> None:
    """A conta do contrato. Nunca desfaz a ordem: sem Financeiro, segue sem."""
    if contas is None or ordem.total <= 0:
        return
    try:
        if not contas.ja_lancado(ordem.numero):
            contas.lancar(AReceber(
                descricao=f"Ordem {ordem.numero} · recorrente {rec.numero}",
                valor=ordem.total,
                vencimento=ordem.prazo,
                cliente=ordem.cliente,
                categoria="Serviços recorrentes",
                documento=ordem.numero,
                recorrencia=rec.numero,
            ))
    except Exception:  # noqa: BLE001 - a ordem ja existe; a conta sai na entrega
        logger.exception("Nao foi possivel lancar a ordem %s no Financeiro", ordem.numero)


def _telefone(contatos, cliente: str) -> str:
    if contatos is None or not cliente:
        return ""
    try:
        contato = contatos.por_nome(cliente)
    except Exception:  # noqa: BLE001 - sem agenda, a ordem sai sem telefone
        return ""
    return getattr(contato, "telefone", "") or "" if contato else ""


def _item(item: dict) -> ItemOS:
    produto_id = int(item.get("produto_id") or 0)
    return ItemOS(
        # produto do Estoque e material (sai do saldo na entrega); o resto e servico
        tipo=PECA if produto_id else SERVICO,
        descricao=str(item.get("descricao") or ""),
        quantidade=float(item.get("quantidade") or 1),
        valor_unitario=float(item.get("valor_unitario") or 0),
        produto_id=produto_id,
        codigo=str(item.get("codigo") or ""),
    )
