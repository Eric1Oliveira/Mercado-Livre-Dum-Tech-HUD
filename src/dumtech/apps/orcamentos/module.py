"""Registro do aplicativo DumTech Orcamentos na plataforma."""

from __future__ import annotations

from ...core.app_module import AppContext, AppManifest

MANIFEST = AppManifest(
    app_id="orcamentos",
    name="DumTech Orçamentos",
    short_name="Orçamentos",
    description="Proposta comercial: condições, documento e taxa de conversão.",
    version="2.0.0",
    icon="file",
    accent="#E0902F",
    category="Vendas",
)


def create_window(context: AppContext):
    from .ui.window import OrcamentosWindow

    return OrcamentosWindow(context)


def avisos(paths, config):
    """Proposta parada e proposta vencendo - dinheiro que some por silencio."""
    from datetime import date, timedelta

    from ...core.avisos import Aviso
    from ...ui import format as fmt
    from .database import open_database
    from .repository import OrcamentosRepository

    espera = config.dias("proposta_parada")
    validade = config.dias("proposta_vencendo")

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        repositorio = OrcamentosRepository(banco)
        paradas = repositorio.esperando_ha_mais_de(espera)
        resumo = repositorio.resumo()
    finally:
        banco.close()

    encontrados = []
    if paradas:
        primeira = paradas[0]
        total = sum(o.total for o in paradas)
        encontrados.append(Aviso(
            app_id=MANIFEST.app_id, tipo="proposta_parada",
            titulo=f"{fmt.contagem(len(paradas), 'proposta')} sem resposta "
                   f"há mais de {fmt.dias(espera)}",
            detalhe=f"{fmt.moeda(total)} parados - a mais antiga: "
                    f"{primeira.numero}, {primeira.cliente}",
            tom="warning", urgencia=55, icone="file", quantidade=len(paradas),
        ))

    limite = (date.today() + timedelta(days=validade)).isoformat()
    vencendo = [o for o in resumo.vencendo if o.vale_ate and o.vale_ate <= limite]
    if vencendo:
        primeira = vencendo[0]
        encontrados.append(Aviso(
            app_id=MANIFEST.app_id, tipo="proposta_vencendo",
            titulo=f"{fmt.contagem(len(vencendo), 'proposta')} "
                   f"perde{'m' if len(vencendo) > 1 else ''} a validade em breve",
            detalhe=f"{primeira.numero} ({primeira.cliente}) vale até "
                    f"{fmt.data(primeira.vale_ate)}",
            tom="warning", urgencia=35, icone="file", quantidade=len(vencendo),
        ))
    return encontrados


def indicadores(paths):
    """O sinal vital do funil: quanto esta em negociacao."""
    from ...core.indicadores import Indicador
    from ...ui import format as fmt
    from .database import open_database
    from .repository import OrcamentosRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        resumo = OrcamentosRepository(banco).resumo(limite_listas=1)
    finally:
        banco.close()

    return [Indicador(
        app_id=MANIFEST.app_id, rotulo="Em negociação",
        valor=fmt.moeda(resumo.valor_em_aberto),
        detalhe=(f"{fmt.contagem(resumo.abertos, 'proposta')} em aberto"
                 if resumo.abertos else "nenhuma proposta em aberto"),
        tom="warning", icone="file", peso=80,
    )]


def celular(paths):
    """No celular: o que espera resposta, o que vence e quanto vira venda."""
    from datetime import date

    from ...core import celular as c
    from ...ui import format as fmt
    from .database import open_database
    from .models import ler_data
    from .repository import OrcamentosRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        r = OrcamentosRepository(banco).resumo(limite_listas=c.LIMITE_LISTA)
    finally:
        banco.close()

    def vale(o) -> str:
        quando = ler_data(o.vale_ate)
        return "" if quando is None else ("hoje" if quando == date.today() else c.data_curta(quando))

    vencendo = {o.id for o in r.vencendo}  # ja aparece na lista de cima
    alertas = []
    if r.vencendo:
        alertas.append(c.alerta(
            f"Cobrar resposta de {fmt.contagem(len(r.vencendo), 'proposta que vence', 'propostas que vencem')} "
            "em 7 dias", fmt.moeda(sum(o.total for o in r.vencendo)), "aviso"))
    return c.secao(MANIFEST.app_id, "Orçamentos", peso=40, cartoes=[
        c.cartao("Esperando resposta", fmt.numero(r.abertos), fmt.moeda(r.valor_em_aberto)),
        c.cartao("Aprovados no mês", fmt.numero(r.aprovados_mes), fmt.moeda(r.valor_aprovado_mes), "ok"),
        c.cartao("Conversão", f"{round(r.conversao)}%",
                 f"{fmt.contagem(r.respondidos, 'proposta respondida', 'propostas respondidas')}",
                 medidor=c.medidor(r.conversao, 100) if r.respondidos else None, largo=True),
    ], listas=[
        c.lista("Vencendo", [c.linha(o.cliente, o.numero, fmt.moeda(o.total), "aviso", hora=vale(o))
                             for o in r.vencendo],
                "Nenhuma proposta vencendo."),
        c.lista("Esperando resposta", [
            c.linha(o.cliente, f"{o.numero} · há {fmt.contagem(o.dias_esperando, 'dia', 'dias')}", fmt.moeda(o.total))
            for o in r.aguardando if o.id not in vencendo]),
    ], alertas=alertas)
