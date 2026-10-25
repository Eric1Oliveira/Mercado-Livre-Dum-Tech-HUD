"""A proposta comercial em A4 - a versao que vai por e-mail.

A bobina de 40 colunas (`recibo.py`) continua existindo para quem imprime no
balcao. Esta e para quando o cliente vai receber o arquivo e decidir olhando
para ele: mesma informacao, forma de documento.
"""

from __future__ import annotations

from ...ui import documento as doc
from ...ui import format as fmt
from .models import APROVADO, RECUSADO, Orcamento


def proposta_a4(orcamento: Orcamento, empresa=None, paths=None) -> str:
    itens = [
        [
            item.descricao,
            item.quantidade_texto,
            fmt.moeda(item.valor_unitario),
            f"-{fmt.moeda(item.desconto)}" if item.desconto else "",
            fmt.moeda(item.total),
        ]
        for item in orcamento.itens
    ]

    resumo = []
    if orcamento.desconto_total:
        resumo.append(("Valor dos itens", fmt.moeda(orcamento.bruto)))
        if orcamento.descontos_dos_itens:
            resumo.append(
                ("Descontos por item", f"-{fmt.moeda(orcamento.descontos_dos_itens)}")
            )
        if orcamento.desconto:
            resumo.append(("Desconto na proposta", f"-{fmt.moeda(orcamento.desconto)}"))

    if orcamento.vale_ate:
        validade = fmt.data(orcamento.vale_ate)
    elif orcamento.validade_dias:
        validade = f"{fmt.dias(orcamento.validade_dias)} após o envio"
    else:
        validade = ""

    return doc.pagina([
        doc.cabecalho(empresa, doc.tem_logo(empresa, paths)),
        doc.titulo("Proposta comercial", orcamento.numero, fmt.data(orcamento.data)),
        doc.campos([
            ("Cliente", orcamento.cliente),
            ("Proposta válida até", validade),
            ("Condição de pagamento", orcamento.condicao_pagamento),
            ("Prazo de entrega", orcamento.prazo_entrega),
        ]),
        doc.tabela(
            ["Descrição", "Qtd.", "Valor unit.", "Desconto", "Total"],
            itens,
            alinhamentos=[doc.ESQUERDA, doc.DIREITA, doc.DIREITA, doc.DIREITA,
                          doc.DIREITA],
            larguras=["46%", "10%", "14%", "14%", "16%"],
        ),
        doc.totais(resumo, ("Total da proposta", fmt.moeda(orcamento.total))),
        _selo(orcamento),
        doc.secao("Observações", orcamento.observacoes),
        doc.rodape(empresa, "Documento sem valor fiscal"),
    ])


def _selo(orcamento: Orcamento) -> str:
    if orcamento.status == APROVADO:
        return doc.destaque("Proposta aprovada pelo cliente")
    if orcamento.status == RECUSADO:
        return doc.destaque("Proposta não aprovada")
    return ""
