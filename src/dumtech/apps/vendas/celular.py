"""O DumTech Vendas no celular: o ritmo do dia, a tendencia e o que mais sai.

A pergunta do dono e uma so - "estou vendendo bem?" - e numero sozinho nao
responde. Cada numero aqui vai com a comparacao justa (ver
`repository/indicadores.py`) e o grafico que mostra o caminho ate ele.
"""

from __future__ import annotations

from datetime import date, timedelta

from ...core import celular as c
from ...ui import format as fmt
from .models import PENDENTE, quantidade_texto


def _ritmo(ind, base_nome: str) -> dict:
    """Hoje contra o mesmo dia da semana passada, somando hora a hora.

    A marca "10h" e tudo o que foi vendido antes das 10:00. A linha de hoje
    para na ultima hora cheia e termina no minuto de agora (`agora`).
    """
    agora = ind.agora
    com_venda = [h for h in range(24) if ind.horas_hoje[h] or ind.horas_base[h]]
    inicio = min([agora.hour, 8, *com_venda])
    fim = min(max([agora.hour + 1, 18, *(h + 1 for h in com_venda)]), 24)
    marcas = range(inicio, fim + 1)

    def acumulado(horas, ultima: int = 24) -> list:
        return [round(sum(horas[:h]), 2) if h <= ultima else None for h in marcas]

    return c.linhas(
        "Ritmo do dia",
        [f"{h}h" for h in marcas],
        [c.serie("Hoje", acumulado(ind.horas_hoje, agora.hour), destaque=True),
         c.serie(base_nome[:1].upper() + base_nome[1:], acumulado(ind.horas_base))],
        dicas=[f"até {h}h" for h in marcas],
        agora={"posicao": round(agora.hour - inicio + agora.minute / 60, 3),
               "valores": [ind.total_hoje, ind.base_ate_agora],
               "rotulo": f"agora, {agora:%H:%M}"},
    )


def _dias(ind, quantos: int) -> dict:
    """Uma coluna por dia; a de hoje (pela metade) e a que se destaca."""
    dias = [ind.hoje - timedelta(days=n) for n in range(quantos - 1, -1, -1)]
    curtos = quantos <= 7
    return c.colunas(
        f"Últimos {quantos} dias",
        [c.DIAS_CURTOS[d.weekday()] if curtos else str(d.day) for d in dias],
        [ind.dia(d).total for d in dias],
        destaque=len(dias) - 1,
        dicas=[f"{c.DIAS_CURTOS[d.weekday()]}, {c.data_curta(d)}" + (" · até agora" if d == ind.hoje else "")
               for d in dias],
    )


def _periodo_de_dias(ind, quantos: int) -> dict:
    total = ind.janela(quantos)
    vendas = sum(ind.dia(ind.hoje - timedelta(days=n)).vendas for n in range(quantos))
    return c.periodo(
        f"{quantos} dias", f"Vendido em {quantos} dias", fmt.moeda(total), total,
        detalhe=f"{fmt.contagem(vendas, 'venda', 'vendas')} · {fmt.moeda(total / quantos)} por dia em média",
        variacao=c.variacao(total, ind.janela_anterior(quantos), f"os {quantos} dias anteriores"),
        grafico=_dias(ind, quantos),
    )


def _destaque(ind) -> dict:
    base_nome = c.dia_passado(ind.base)
    hoje = (f"{fmt.contagem(ind.vendas_hoje, 'venda', 'vendas')} · ticket médio {fmt.moeda(ind.ticket_hoje)}"
            if ind.vendas_hoje else "Nenhuma venda ainda hoje")
    return c.destaque([
        c.periodo("Hoje", "Vendido hoje", fmt.moeda(ind.total_hoje), ind.total_hoje, detalhe=hoje,
                  variacao=c.variacao(ind.total_hoje, ind.base_ate_agora,
                                      f"{base_nome} até {ind.agora:%H:%M}"),
                  grafico=_ritmo(ind, base_nome)),
        _periodo_de_dias(ind, 7),
        _periodo_de_dias(ind, 30),
    ])


def _dia(texto: str) -> date | None:
    """A data que veio do banco - ou None, se alguem gravou coisa torta."""
    try:
        return date.fromisoformat((texto or "")[:10])
    except ValueError:
        return None


def _caixa(caixa, gaveta: float, hoje: date) -> tuple[dict, list[dict]]:
    if caixa is None:
        return c.cartao("Caixa", "Fechado", "abra no balcão para vender"), []
    aberto = (caixa.aberto_em or "")[:16].replace("T", " ")
    if aberto[:10] == hoje.isoformat():
        return c.cartao("Na gaveta", fmt.moeda(gaveta), f"caixa aberto às {aberto[11:16]}"), []
    dia = _dia(aberto) or hoje
    return (c.cartao("Na gaveta", fmt.moeda(gaveta), f"caixa aberto desde {c.data_curta(dia)}", "aviso"),
            [c.alerta(f"Fechar o caixa aberto desde {c.data_curta(dia)}", tom="aviso")])


def _ultima(venda, hoje: date) -> dict:
    formas = " + ".join(c.nome_da_forma(f.strip()) for f in (venda.resumo_pagamento or "").split("+") if f.strip())
    pendente = venda.status == PENDENTE
    criado = venda.criado_em or ""
    hora = criado[11:16] if venda.data == hoje.isoformat() and criado[:10] == venda.data else ""
    if not hora and _dia(venda.data):
        hora = c.data_curta(_dia(venda.data))
    return c.linha(venda.cliente or "Consumidor",
                   f"{venda.numero} · {'a receber' if pendente else formas or 'sem pagamento'}",
                   fmt.moeda(venda.total_liquido), "aviso" if pendente else "", hora=hora)


def secao(paths, manifesto) -> dict:
    from .database import open_database
    from .repository import VendasRepository

    banco = open_database(paths.app_db(manifesto.app_id))
    try:
        repositorio = VendasRepository(banco)
        ind = repositorio.indicadores()
        caixa = repositorio.caixa_aberto()
        gaveta = repositorio.conferencia(caixa.id).esperado if caixa else 0.0
        ultimas = [v for v in repositorio.listar(limite=c.LIMITE_LISTA * 2) if v.conta][:c.LIMITE_LISTA]
    finally:
        banco.close()

    ultimo_do_mes_passado = ind.hoje.replace(day=1) - timedelta(days=1)
    mes_passado = c.MESES[ultimo_do_mes_passado.month - 1]
    # "1 a 17/09": o pedaco do mes passado que vale a comparacao, dito curto
    pedaco = f"1 a {min(ind.hoje.day, ultimo_do_mes_passado.day)}/{ultimo_do_mes_passado.month:02d}"
    cartao_caixa, alertas = _caixa(caixa, gaveta, ind.hoje)
    cartoes = [
        # o celular antigo abre com este; o novo ja mostra o destaque
        c.cartao("Vendido hoje", fmt.moeda(ind.total_hoje), f"{fmt.moeda(ind.mes)} no mês", papel="destaque"),
        c.cartao("No mês", fmt.moeda(ind.mes), fmt.contagem(ind.vendas_mes, "venda", "vendas"),
                 variacao=c.variacao(ind.mes, ind.mes_anterior, pedaco)),
        c.cartao("Ticket médio", fmt.moeda(ind.ticket_mes), "por venda no mês",
                 variacao=c.variacao(ind.ticket_mes, ind.ticket_mes_anterior, mes_passado)),
        cartao_caixa,
    ]
    if ind.vendas_pendentes:
        cartoes.append(c.cartao("Vendas a prazo", fmt.moeda(ind.pendentes),
                                f"{fmt.contagem(ind.vendas_pendentes, 'venda', 'vendas')} a receber"))

    return c.secao(
        manifesto.app_id, "Vendas", peso=90, cartoes=cartoes,
        destaque=_destaque(ind),
        graficos=[
            c.ranking("Mais vendidos no mês", [
                c.item(m.descricao, m.valor, fmt.moeda(m.valor),
                       quantidade_texto(m.quantidade, m.unidade, m.casas))
                for m in ind.mais_vendidos], vazio="Nenhuma venda no mês ainda."),
            c.ranking("Como pagaram no mês", [
                c.item(c.nome_da_forma(forma), valor, fmt.moeda(valor)) for forma, valor in ind.por_forma
            ], parte_do_todo=True) if ind.por_forma else None,
        ],
        listas=[c.lista("Últimas vendas", [_ultima(v, ind.hoje) for v in ultimas], "Nenhuma venda ainda.")],
        alertas=alertas,
    )
