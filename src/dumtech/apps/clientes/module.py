"""Registro do aplicativo DumTech Clientes na plataforma."""

from __future__ import annotations

from ...core.app_module import AppContext, AppManifest

MANIFEST = AppManifest(
    app_id="clientes",
    name="DumTech Clientes",
    short_name="Clientes",
    description="Ficha do cliente com documento, endereço, anotações e aniversários.",
    version="2.0.0",
    icon="users",
    accent="#2FB6A6",
    category="Cadastros",
)


def create_window(context: AppContext):
    from .ui.window import ClientesWindow

    return ClientesWindow(context)


def avisos(paths, config):
    """Quem faz aniversario hoje. Motivo de ligacao que gera venda."""
    from datetime import date

    from ...core.avisos import Aviso
    from ...core.contacts import ContactsStore

    hoje = date.today()
    loja = ContactsStore(paths.platform_db)
    try:
        aniversariantes = [
            c for c in loja.aniversariantes(hoje.month)
            if c.aniversario == (hoje.day, hoje.month)
        ]
    finally:
        loja.close()

    if not aniversariantes:
        return []
    primeiro = aniversariantes[0]
    idade = primeiro.idade_neste_ano
    return [Aviso(
        app_id=MANIFEST.app_id, tipo="aniversario_hoje",
        titulo=(f"{primeiro.nome} faz aniversário hoje"
                if len(aniversariantes) == 1
                else f"{len(aniversariantes)} clientes fazem aniversário hoje"),
        detalhe=(f"{idade} anos" if idade and len(aniversariantes) == 1
                 else ", ".join(c.nome for c in aniversariantes[:4])),
        tom="success", urgencia=20, icone="users",
        quantidade=len(aniversariantes),
    )]


def indicadores(paths):
    """O sinal vital da carteira: quantos clientes a loja tem."""
    from ...core.contacts import ContactsStore
    from ...core.indicadores import Indicador
    from ...ui import format as fmt

    loja = ContactsStore(paths.platform_db)
    try:
        resumo = loja.resumo(limite=1)
    finally:
        loja.close()

    return [Indicador(
        app_id=MANIFEST.app_id, rotulo="Clientes",
        valor=fmt.numero(resumo.ativos),
        detalhe=(f"{fmt.contagem(resumo.novos_mes, 'novo', 'novos')} neste mês"
                 if resumo.novos_mes else "nenhum novo neste mês"),
        tom="success", icone="users", peso=40,
    )]


def celular(paths):
    """No celular: os aniversariantes - e o botao que manda os parabens."""
    from datetime import date

    from ...core import celular as c
    from ...core.contacts import ContactsStore
    from ...ui import format as fmt

    loja = ContactsStore(paths.platform_db)
    try:
        r = loja.resumo(limite=31)
    finally:
        loja.close()

    hoje = date.today()

    def aniversariante(x) -> dict:
        dia, _mes = x.aniversario or (0, 0)
        primeiro = (x.nome or "").split(" ")[0]
        acao = c.whatsapp(x.whatsapp or x.telefone,
                          f"Feliz aniversário, {primeiro}! Muita saúde e um ótimo dia. Um abraço!",
                          "Mandar parabéns") if dia >= hoje.day else None
        if dia == hoje.day:
            return c.linha(x.nome, "Faz aniversário hoje", "", "ok", hora="hoje", acao=acao)
        return c.linha(x.nome, x.telefone_formatado or "sem telefone", "",
                       hora=f"{dia:02d}/{hoje.month:02d}", estado="passou" if dia < hoje.day else "", acao=acao)

    # quem ainda vai fazer aniversario vem antes de quem ja fez
    ordem = sorted(r.aniversariantes, key=lambda x: ((x.aniversario or (0, 0))[0] < hoje.day,
                                                      (x.aniversario or (0, 0))[0]))
    hoje_tem = [x for x in r.aniversariantes if (x.aniversario or (0, 0))[0] == hoje.day]
    alertas = []
    if len(hoje_tem) == 1:
        alertas.append(c.alerta(f"Dar parabéns a {hoje_tem[0].nome}", tom="ok", detalhe="aniversário hoje"))
    elif hoje_tem:
        alertas.append(c.alerta(f"Dar parabéns a {fmt.numero(len(hoje_tem))} clientes", tom="ok",
                                detalhe="aniversário hoje"))
    return c.secao(MANIFEST.app_id, "Clientes", peso=30, cartoes=[
        c.cartao("Clientes ativos", fmt.numero(r.ativos), f"{r.novos_mes} novos no mês"),
        c.cartao("Aniversariantes", fmt.numero(len(r.aniversariantes)), "neste mês",
                 "ok" if hoje_tem else ""),
    ], listas=[
        c.lista("Aniversariantes do mês", [aniversariante(x) for x in ordem],
                "Ninguém faz aniversário este mês."),
    ], alertas=alertas)
