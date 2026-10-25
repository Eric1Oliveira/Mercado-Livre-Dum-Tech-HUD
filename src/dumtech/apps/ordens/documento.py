"""O comprovante de entrega em A4 - o papel que fica com o cliente.

A bobina serve para a entrada, no balcao, na hora. A entrega e outra conversa:
e o documento da garantia, o cliente guarda numa gaveta e volta com ele meses
depois. Por isso este sai em folha, com o prazo em destaque e a linha de
assinatura.

As palavras nao sao de nenhum ramo: quem le e o cliente da assistencia, o da
oficina mecanica, o da lavanderia e o da grafica. `doc.campos` e `doc.secao`
ja somem com o que esta em branco, entao o papel de quem so preenche cliente e
servico sai sem buraco nenhum.
"""

from __future__ import annotations

from ...ui import documento as doc
from ...ui import format as fmt
from .models import CANCELADA, Ordem

GARANTIA_COBRE = (
    "A garantia cobre o serviço executado e os materiais aplicados nesta "
    "ordem. Não cobre mau uso, dano acidental nem intervenção de terceiros."
)


def entrega_a4(ordem: Ordem, empresa=None, paths=None) -> str:
    itens = [
        [
            item.descricao,
            item.tipo_label,
            fmt.numero(item.quantidade),
            fmt.moeda(item.valor_unitario),
            fmt.moeda(item.total),
        ]
        for item in ordem.itens
    ]

    resumo = []
    if ordem.itens:
        resumo.append(("Materiais", fmt.moeda(ordem.total_pecas)))
        resumo.append(("Serviços", fmt.moeda(ordem.total_servicos)))
    if ordem.desconto:
        resumo.append(("Desconto", f"-{fmt.moeda(ordem.desconto)}"))

    return doc.pagina([
        doc.cabecalho(empresa, doc.tem_logo(empresa, paths)),
        doc.titulo("Comprovante de entrega", ordem.numero,
                   fmt.data(ordem.entregue_em or ordem.aberta_em)),
        doc.campos([
            ("Cliente", ordem.cliente),
            ("Telefone", fmt.telefone(ordem.telefone)),
            ("Item ou local", ordem.equipamento),
            ("Responsável", ordem.tecnico),
        ]),
        doc.secao("O que foi pedido", ordem.defeito),
        doc.secao("O que foi feito", ordem.diagnostico or ordem.servico),
        doc.tabela(
            ["Descrição", "Tipo", "Qtd.", "Valor unit.", "Total"],
            itens,
            alinhamentos=[doc.ESQUERDA, doc.ESQUERDA, doc.DIREITA, doc.DIREITA,
                          doc.DIREITA],
            larguras=["42%", "14%", "10%", "16%", "18%"],
        ),
        doc.totais(resumo, ("Total do serviço", fmt.moeda(ordem.total))),
        _garantia(ordem),
        doc.secao("Observações", ordem.observacoes),
        doc.destaque("Ordem cancelada") if ordem.status == CANCELADA else "",
        doc.assinatura("Recebi o serviço nas condições acima"),
        doc.rodape(empresa, "Documento sem valor fiscal"),
    ])


def _garantia(ordem: Ordem) -> str:
    if not ordem.garantia_ate:
        return doc.secao("Garantia", "Este serviço foi entregue sem garantia.")
    return doc.secao(
        f"Garantia de {fmt.dias(ordem.garantia_dias)} - até "
        f"{fmt.data(ordem.garantia_ate)}",
        GARANTIA_COBRE,
    )
