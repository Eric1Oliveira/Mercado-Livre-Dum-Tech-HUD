"""Comprovante em texto de 40 colunas - a largura da bobina termica comum.

O mesmo texto vai para a tela e para a impressora: o que se ve e o que sai.
Nao e documento fiscal, e o comprovante do balcao, e o rodape diz isso.
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
from .models import CANCELADA, ConferenciaCaixa, Venda


def comprovante(venda: Venda, empresa=None) -> str:
    """O papel que o cliente leva."""
    linhas = [
        *cabecalho_empresa(empresa),
        centro("COMPROVANTE DE VENDA"),
        linha("="),
        lado_a_lado(venda.numero, fmt.data(venda.data)),
    ]
    if venda.cliente:
        linhas += quebrar(f"Cliente: {venda.cliente}")
    linhas.append(linha())

    for item in venda.itens:
        linhas += quebrar(item.descricao)
        quantidade = f"{item.quantidade_texto} x {fmt.moeda(item.valor_unitario)}"
        linhas.append(lado_a_lado(f"  {quantidade}", fmt.moeda(item.total)))

    linhas.append(linha())
    if venda.desconto:
        linhas.append(lado_a_lado("Subtotal", fmt.moeda(venda.subtotal)))
        linhas.append(lado_a_lado("Desconto", f"-{fmt.moeda(venda.desconto)}"))
    linhas.append(lado_a_lado("TOTAL", fmt.moeda(venda.total)))
    linhas.append("")

    for pagamento in venda.pagamentos:
        linhas.append(lado_a_lado(pagamento.forma, fmt.moeda(pagamento.valor)))
        if pagamento.em_dinheiro and pagamento.recebido > pagamento.valor:
            linhas.append(lado_a_lado("  Recebido", fmt.moeda(pagamento.recebido)))
    if venda.troco:
        linhas.append(lado_a_lado("TROCO", fmt.moeda(venda.troco)))

    if venda.devolvido:
        linhas.append(linha())
        linhas.append(lado_a_lado("Devolvido", f"-{fmt.moeda(venda.devolvido)}"))
        linhas.append(lado_a_lado("Valor liquido", fmt.moeda(venda.total_liquido)))

    if venda.status == CANCELADA:
        linhas += ["", centro("*** VENDA CANCELADA ***")]
        linhas += quebrar(f"Motivo: {venda.motivo_cancelamento}")

    if venda.observacoes:
        linhas.append(linha())
        linhas += quebrar(venda.observacoes)

    linhas += [
        linha("="),
        *rodape_empresa(empresa),
        centro("Documento sem valor fiscal"),
        centro(fmt.data_hora(venda.criado_em)),
    ]
    return "\n".join(linhas)


def fechamento(conferencia: ConferenciaCaixa, empresa=None) -> str:
    """O papel que fica com quem fecha o caixa."""
    caixa = conferencia.caixa
    if caixa is None:
        return centro("Nenhum caixa aberto.")

    linhas = [
        *cabecalho_empresa(empresa),
        centro("FECHAMENTO DE CAIXA"),
        linha("="),
        lado_a_lado("Abertura", fmt.data_hora(caixa.aberto_em)),
    ]
    if caixa.fechado_em:
        linhas.append(lado_a_lado("Fechamento", fmt.data_hora(caixa.fechado_em)))
    linhas += [
        linha(),
        lado_a_lado("Vendas", str(conferencia.quantidade_vendas)),
        lado_a_lado("Total vendido", fmt.moeda(conferencia.total_vendido)),
        linha(),
    ]

    for forma, valor in conferencia.por_forma:
        linhas.append(lado_a_lado(f"  {forma}", fmt.moeda(valor)))

    linhas += [
        linha(),
        centro("DINHEIRO NA GAVETA"),
        lado_a_lado("Abertura", fmt.moeda(conferencia.abertura)),
        lado_a_lado("Vendas em dinheiro", fmt.moeda(conferencia.vendas_dinheiro)),
        lado_a_lado("Trocos", f"-{fmt.moeda(conferencia.trocos)}"),
        lado_a_lado("Suprimentos", fmt.moeda(conferencia.suprimentos)),
        lado_a_lado("Sangrias", f"-{fmt.moeda(conferencia.sangrias)}"),
    ]
    if conferencia.devolucoes_dinheiro:
        linhas.append(
            lado_a_lado("Devolucoes", f"-{fmt.moeda(conferencia.devolucoes_dinheiro)}")
        )
    linhas.append(lado_a_lado("ESPERADO", fmt.moeda(conferencia.esperado)))

    if not caixa.aberto:
        linhas += [
            "",
            lado_a_lado("Contado", fmt.moeda(caixa.contado)),
            lado_a_lado("Diferenca", fmt.moeda(caixa.diferenca)),
        ]
        if caixa.observacoes:
            linhas += quebrar(caixa.observacoes)

    linhas += [linha("="), *rodape_empresa(empresa),
               centro("Documento sem valor fiscal")]
    return "\n".join(linhas)
