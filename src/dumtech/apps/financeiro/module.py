"""Registro do aplicativo DumTech Financeiro na plataforma."""

from __future__ import annotations

from ...core.app_module import AppContext, AppManifest

MANIFEST = AppManifest(
    app_id="financeiro",
    name="DumTech Financeiro",
    short_name="Financeiro",
    description="Fluxo de caixa: projecao, parcelamento, baixa parcial e contas.",
    version="2.0.0",
    icon="money",
    accent="#2E9E6B",
    category="Gestao",
)


def create_window(context: AppContext):
    from .ui.window import FinanceiroWindow

    return FinanceiroWindow(context)


def avisos(paths, config):
    """O que vence, e o que ja venceu e continua em aberto."""
    from ...core.avisos import Aviso
    from ...ui import format as fmt
    from .database import open_database
    from .repository import FinanceiroRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        resumo = FinanceiroRepository(banco).resumo()
    finally:
        banco.close()

    encontrados = []
    if resumo.vencidos_quantidade:
        atrasado = resumo.atrasados[0] if resumo.atrasados else None
        encontrados.append(Aviso(
            app_id=MANIFEST.app_id, tipo="conta_vencida",
            titulo=f"{fmt.contagem(resumo.vencidos_quantidade, 'conta')} "
                   f"vencida{'s' if resumo.vencidos_quantidade > 1 else ''}",
            detalhe=(f"{fmt.moeda(resumo.vencidos_valor)} em aberto"
                     + (f" - a mais antiga: {atrasado.descricao}" if atrasado else "")),
            tom="danger", urgencia=90, icone="money",
            quantidade=resumo.vencidos_quantidade,
        ))

    prazo = config.dias("conta_vencendo")
    proximos = [
        lancamento for lancamento in resumo.proximos
        if (lancamento.dias_para_vencer or 0) >= 0
        and (lancamento.dias_para_vencer or 0) <= prazo
    ]
    if proximos:
        primeiro = proximos[0]
        total = sum(l.em_aberto or l.valor for l in proximos)
        encontrados.append(Aviso(
            app_id=MANIFEST.app_id, tipo="conta_vencendo",
            titulo=f"{fmt.contagem(len(proximos), 'conta')} "
                   f"vence{'m' if len(proximos) > 1 else ''} em ate "
                   f"{fmt.dias(prazo)}",
            detalhe=f"{fmt.moeda(total)} - a proxima: {primeiro.descricao}, "
                    f"{fmt.data(primeiro.vencimento)}",
            tom="warning", urgencia=60, icone="money", quantidade=len(proximos),
        ))
    return encontrados


def indicadores(paths):
    """O sinal vital do dinheiro: quanto ha em conta agora."""
    from ...core.indicadores import Indicador
    from ...ui import format as fmt
    from .database import open_database
    from .models import CENTAVO
    from .repository import FinanceiroRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        resumo = FinanceiroRepository(banco).resumo(limite_listas=1)
    finally:
        banco.close()

    saldo = resumo.saldo_contas
    return [Indicador(
        app_id=MANIFEST.app_id, rotulo="Em caixa e banco",
        valor=fmt.moeda(saldo),
        detalhe=(f"{fmt.moeda(resumo.a_receber_mes)} a receber em 30 dias"
                 if resumo.a_receber_mes else "sem contas a receber"),
        tom="danger" if saldo < -CENTAVO else "success",
        icone="money", peso=100,
    )]


def celular(paths):
    """No celular: o que vence, o que atrasou e o saldo."""
    from ...core import celular as c
    from ...ui import format as fmt
    from .database import open_database
    from .repository import FinanceiroRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        r = FinanceiroRepository(banco).resumo(limite_listas=c.LIMITE_LISTA)
    finally:
        banco.close()

    def conta(item):
        return c.linha(item.descricao_completa,
                       f"{'Receber' if item.e_receita else 'Pagar'} · vence {fmt.data(item.vencimento)}",
                       fmt.moeda(item.em_aberto), "ok" if item.e_receita else "")
    return c.secao(MANIFEST.app_id, "Financeiro", peso=80, cartoes=[
        c.cartao("Saldo nas contas", fmt.moeda(r.saldo_contas)),
        c.cartao("A receber no mês", fmt.moeda(r.a_receber_mes), f"{fmt.moeda(r.recebido_mes)} já recebido", "ok"),
        c.cartao("A pagar no mês", fmt.moeda(r.a_pagar_mes), f"{fmt.moeda(r.pago_mes)} já pago"),
        c.cartao("Atrasado", fmt.moeda(r.vencidos_valor),
                 fmt.contagem(r.vencidos_quantidade, "conta", "contas"),
                 "perigo" if r.vencidos_quantidade else ""),
    ], listas=[
        c.lista("Atrasadas", [conta(item) for item in r.atrasados], "Nada atrasado."),
        c.lista("Próximos vencimentos", [conta(item) for item in r.proximos], "Nada vencendo."),
    ])
