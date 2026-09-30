"""Registro do aplicativo DumTech Vendas na plataforma."""

from __future__ import annotations

from ...core.app_module import AppContext, AppManifest

MANIFEST = AppManifest(
    app_id="vendas",
    name="DumTech Vendas",
    short_name="Vendas",
    description="PDV de balcao: bipe, receba em varias formas e feche o caixa.",
    version="2.0.0",
    icon="cart",
    accent="#D8574F",
    category="Vendas",
)


def create_window(context: AppContext):
    from .ui.window import VendasWindow

    return VendasWindow(context)


def avisos(paths, config):
    """Venda fechada que ainda nao foi paga."""
    from ...core.avisos import Aviso
    from ...ui import format as fmt
    from .database import open_database
    from .models import PENDENTE
    from .repository import VendasRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        pendentes = VendasRepository(banco).listar(status=PENDENTE)
    finally:
        banco.close()

    if not pendentes:
        return []
    total = sum(venda.total_liquido for venda in pendentes)
    return [Aviso(
        app_id=MANIFEST.app_id, tipo="venda_a_receber",
        titulo=f"{fmt.contagem(len(pendentes), 'venda')} aguardando pagamento",
        detalhe=f"{fmt.moeda(total)} no total",
        tom="warning", urgencia=45, icone="cart", quantidade=len(pendentes),
    )]


def indicadores(paths):
    """O sinal vital do balcao: quanto entrou hoje."""
    from ...core.indicadores import Indicador
    from ...ui import format as fmt
    from .database import open_database
    from .repository import VendasRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        resumo = VendasRepository(banco).resumo(limite_listas=1)
    finally:
        banco.close()

    return [Indicador(
        app_id=MANIFEST.app_id, rotulo="Vendido hoje",
        valor=fmt.moeda(resumo.total_hoje),
        detalhe=(f"{fmt.moeda(resumo.total_mes)} no mes"
                 if resumo.total_mes else "nenhuma venda no mes"),
        tom="accent", icone="cart", peso=90,
    )]


def celular(paths):
    """No celular: quanto entrou hoje, o caixa e as ultimas vendas."""
    from ...core import celular as c
    from ...ui import format as fmt
    from .database import open_database
    from .repository import VendasRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        repositorio = VendasRepository(banco)
        r = repositorio.resumo(limite_listas=c.LIMITE_LISTA)
        caixa = repositorio.caixa_aberto()
    finally:
        banco.close()
    return c.secao(MANIFEST.app_id, "Vendas", peso=90, cartoes=[
        c.cartao("Vendido hoje", fmt.moeda(r.total_hoje), f"{fmt.moeda(r.total_mes)} no mês"),
        c.cartao("Caixa", "Aberto" if caixa else "Fechado",
                 f"desde {fmt.data_hora_curta(caixa.aberto_em)}" if caixa else "",
                 "ok" if caixa else ""),
        c.cartao("Ticket médio", fmt.moeda(r.ticket_medio),
                 fmt.contagem(r.vendas_mes, "venda", "vendas") + " no mês"),
    ], listas=[
        c.lista("Como pagaram no mês", [c.linha(forma, valor=fmt.moeda(valor)) for forma, valor in r.por_forma]),
        c.lista("Últimas vendas", [
            c.linha(v.cliente or "Consumidor", f"{v.numero} · {fmt.data(v.data)}", fmt.moeda(v.total_liquido),
                    "aviso" if v.status == "pendente" else "")
            for v in r.ultimas], "Nenhuma venda ainda."),
    ])
