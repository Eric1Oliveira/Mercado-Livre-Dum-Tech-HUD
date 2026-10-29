"""Venda recorrente: cada vez do contrato vira uma venda pendente.

Pendente, e nao concluida, pela mesma razao da venda que vem da proposta:
o cliente ainda nao pagou. Quando ele paga, o "Receber" da lista de Vendas
fecha a venda, quita a conta no Financeiro e baixa o estoque - tudo pelo
caminho que ja existia.

A venda nasce com antecedencia (`ANTECEDENCIA`): a mensalidade do mes que
vem ja aparece no Financeiro como conta a receber.
"""

from __future__ import annotations

from datetime import date

from ...core import recorrencia
from . import financeiro
from .models import PENDENTE, ItemVenda, Venda

#: quantos dias antes da data a venda ja aparece (e vai ao Financeiro)
ANTECEDENCIA = 30
#: o numero do contrato; vai parar no Financeiro ao lado do das Ordens
PREFIXO = "VREC"


def repositorio(database) -> recorrencia.RecorrenciasRepository:
    return recorrencia.RecorrenciasRepository(database, PREFIXO)


def gerar(vendas, contas=None, hoje: date | None = None) -> list[str]:
    """Cria as vendas devidas e leva cada uma ao Financeiro. Devolve os numeros."""
    contratos = repositorio(vendas.db)

    def criar(rec: recorrencia.Recorrencia, quando: date) -> str:
        ja = vendas.db.query_one(
            "SELECT numero FROM vendas WHERE recorrencia = ? AND data = ?",
            (rec.numero, quando.isoformat()),
        )
        if ja is not None:
            return ""  # gerada numa rodada que caiu antes de anotar o avanco
        venda = vendas.salvar(Venda(
            numero=vendas.proximo_numero(),
            cliente=rec.cliente,
            data=quando.isoformat(),
            status=PENDENTE,
            desconto=rec.desconto,
            observacoes="\n".join(parte for parte in (
                f"{rec.descricao} · {rec.frequencia_label.lower()} ({rec.numero})",
                rec.observacoes,
            ) if parte),
            recorrencia=rec.numero,
            itens=[_item(item) for item in rec.itens],
        ))
        financeiro.registrar(contas, venda)
        return venda.numero

    return recorrencia.gerar(contratos, criar, hoje=hoje, antecedencia=ANTECEDENCIA)


def contar_geradas(vendas, contratos: list[recorrencia.Recorrencia]) -> None:
    """Preenche `gerados` de cada contrato (para a lista mostrar)."""
    contagem = {
        row["recorrencia"]: int(row["quantas"])
        for row in vendas.db.query(
            "SELECT recorrencia, COUNT(*) AS quantas FROM vendas"
            " WHERE recorrencia <> '' GROUP BY recorrencia"
        )
    }
    for rec in contratos:
        rec.gerados = contagem.get(rec.numero, 0)


def _item(item: dict) -> ItemVenda:
    return ItemVenda(
        descricao=str(item.get("descricao") or ""),
        quantidade=float(item.get("quantidade") or 1),
        valor_unitario=float(item.get("valor_unitario") or 0),
        produto_id=int(item.get("produto_id") or 0),
        codigo=str(item.get("codigo") or ""),
        unidade=str(item.get("unidade") or "UN"),
        casas=int(item.get("casas") or 0),
    )
