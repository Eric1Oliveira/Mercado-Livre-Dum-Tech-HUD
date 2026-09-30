"""Registro do aplicativo DumTech Clientes na plataforma."""

from __future__ import annotations

from ...core.app_module import AppContext, AppManifest

MANIFEST = AppManifest(
    app_id="clientes",
    name="DumTech Clientes",
    short_name="Clientes",
    description="Ficha do cliente com documento, endereco, anotacoes e aniversarios.",
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
        titulo=(f"{primeiro.nome} faz aniversario hoje"
                if len(aniversariantes) == 1
                else f"{len(aniversariantes)} clientes fazem aniversario hoje"),
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
        detalhe=(f"{fmt.contagem(resumo.novos_mes, 'novo', 'novos')} neste mes"
                 if resumo.novos_mes else "nenhum novo neste mes"),
        tom="success", icone="users", peso=40,
    )]


def celular(paths):
    """No celular: os aniversariantes (motivo para mandar mensagem hoje)."""
    from ...core import celular as c
    from ...core.contacts import ContactsStore
    from ...ui import format as fmt

    loja = ContactsStore(paths.platform_db)
    try:
        r = loja.resumo(limite=c.LIMITE_LISTA)
    finally:
        loja.close()
    return c.secao(MANIFEST.app_id, "Clientes", peso=30, cartoes=[
        c.cartao("Clientes ativos", fmt.numero(r.ativos), f"{r.novos_mes} novos no mês"),
    ], listas=[
        c.lista("Aniversariantes do mês", [c.linha(x.nome, x.aniversario, x.telefone_formatado)
                                           for x in r.aniversariantes],
                "Ninguém faz aniversário este mês."),
    ])
