"""Registro do aplicativo DumTech Vendas na plataforma."""

from __future__ import annotations

from ...core.app_module import AppContext, AppManifest

MANIFEST = AppManifest(
    app_id="vendas",
    name="DumTech Vendas",
    short_name="Vendas",
    description="PDV de balcão: bipe, receba em várias formas e feche o caixa.",
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
        detalhe=(f"{fmt.moeda(resumo.total_mes)} no mês"
                 if resumo.total_mes else "nenhuma venda no mês"),
        tom="accent", icone="cart", peso=90,
    )]


def celular(paths):
    """No celular: o ritmo do dia, a tendencia, o caixa e o que mais sai."""
    from .celular import secao

    return secao(paths, MANIFEST)
