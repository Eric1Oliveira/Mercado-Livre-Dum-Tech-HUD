"""A proposta em 40 colunas: o documento que sai da loja.

O cliente precisa ver onde o desconto entrou - por isso o desconto de cada
linha aparece junto dela, e nao so somado no rodape.
"""

from __future__ import annotations

from ...ui import format as fmt
from ...ui.recibo import (
    cabecalho_empresa,
    centro,
    lado_a_lado,
    linha,
    quebrar,
    rodape_empresa,
)
from .models import APROVADO, RECUSADO, Orcamento


def proposta(orcamento: Orcamento, empresa=None) -> str:
    linhas = [
        *cabecalho_empresa(empresa),
        centro("PROPOSTA COMERCIAL"),
        linha("="),
        lado_a_lado(orcamento.numero, fmt.data(orcamento.data)),
    ]
    linhas += quebrar(f"Cliente: {orcamento.cliente}")
    linhas.append(linha())

    for item in orcamento.itens:
        linhas += quebrar(item.descricao)
        detalhe = f"  {item.quantidade_texto} x {fmt.moeda(item.valor_unitario)}"
        linhas.append(lado_a_lado(detalhe, fmt.moeda(item.bruto)))
        if item.desconto:
            linhas.append(
                lado_a_lado("  desconto nesta linha", f"-{fmt.moeda(item.desconto)}")
            )

    linhas.append(linha())
    if orcamento.desconto_total:
        linhas.append(lado_a_lado("Valor dos itens", fmt.moeda(orcamento.bruto)))
        if orcamento.descontos_dos_itens:
            linhas.append(lado_a_lado(
                "Descontos por item", f"-{fmt.moeda(orcamento.descontos_dos_itens)}"
            ))
        if orcamento.desconto:
            linhas.append(lado_a_lado(
                "Desconto na proposta", f"-{fmt.moeda(orcamento.desconto)}"
            ))
    linhas.append(lado_a_lado("TOTAL", fmt.moeda(orcamento.total)))

    condicoes = []
    if orcamento.condicao_pagamento:
        condicoes.append(("Pagamento", orcamento.condicao_pagamento))
    if orcamento.prazo_entrega:
        condicoes.append(("Prazo de entrega", orcamento.prazo_entrega))
    if condicoes:
        linhas.append(linha())
        for rotulo, valor in condicoes:
            linhas.append(f"{rotulo}:")
            linhas += quebrar(valor, recuo=2)

    linhas.append(linha())
    if orcamento.vale_ate:
        linhas.append(lado_a_lado("Proposta valida ate", fmt.data(orcamento.vale_ate)))
    elif orcamento.validade_dias:
        linhas.append(
            lado_a_lado("Validade", f"{orcamento.validade_dias} dias apos o envio")
        )

    if orcamento.status == APROVADO:
        linhas.append(centro("*** APROVADA ***"))
    elif orcamento.status == RECUSADO:
        linhas.append(centro("*** NAO APROVADA ***"))

    if orcamento.observacoes:
        linhas.append(linha())
        linhas += quebrar(orcamento.observacoes)

    linhas += [linha("="), *rodape_empresa(empresa),
               centro("Documento sem valor fiscal")]
    return "\n".join(linhas)
