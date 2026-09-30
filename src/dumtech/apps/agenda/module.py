"""Registro do aplicativo DumTech Agenda na plataforma."""

from __future__ import annotations

from ...core.app_module import AppContext, AppManifest

MANIFEST = AppManifest(
    app_id="agenda",
    name="DumTech Agenda",
    short_name="Agenda",
    description="Grade da semana, conflito de horario, bloqueio e repeticao.",
    version="2.0.0",
    icon="calendar",
    accent="#C05FD4",
    category="Servicos",
)


def create_window(context: AppContext):
    from .ui.window import AgendaWindow

    return AgendaWindow(context)


def avisos(paths, config):
    """Os compromissos de hoje - a pergunta que a agenda responde melhor."""
    from ...core.avisos import Aviso
    from .database import open_database
    from .repository import AgendaRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        resumo = AgendaRepository(banco).resumo()
    finally:
        banco.close()

    encontrados = []
    if resumo.do_dia:
        proximo = resumo.do_dia[0]
        encontrados.append(Aviso(
            app_id=MANIFEST.app_id, tipo="compromisso_hoje",
            titulo=_contagem(len(resumo.do_dia), "compromisso", "compromissos")
                   + " hoje",
            detalhe=f"{proximo.horario} - {proximo.titulo}"
                    + (f" ({proximo.cliente})" if proximo.cliente else ""),
            tom="accent", urgencia=40, icone="calendar",
            quantidade=len(resumo.do_dia),
        ))
    return encontrados


def _contagem(quantidade: int, singular: str, plural: str) -> str:
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def indicadores(paths):
    """O sinal vital do dia: quantos compromissos ainda faltam."""
    from ...core.indicadores import Indicador
    from ...ui import format as fmt
    from .database import open_database
    from .repository import AgendaRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        resumo = AgendaRepository(banco).resumo(limite_listas=1)
    finally:
        banco.close()

    proximo = resumo.do_dia[0] if resumo.do_dia else None
    return [Indicador(
        app_id=MANIFEST.app_id, rotulo="Compromissos hoje",
        valor=fmt.numero(resumo.hoje),
        detalhe=(f"o proximo as {proximo.horario}" if proximo
                 else "nenhum compromisso hoje"),
        tom="accent", icone="calendar", peso=50,
    )]


def celular(paths):
    """No celular: o dia de hoje e o que vem depois."""
    from ...core import celular as c
    from ...ui import format as fmt
    from .database import open_database
    from .repository import AgendaRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        r = AgendaRepository(banco).resumo(limite_listas=c.LIMITE_LISTA)
    finally:
        banco.close()
    hoje = {x.id for x in r.do_dia}  # o de hoje ja esta na lista de cima
    return c.secao(MANIFEST.app_id, "Agenda", peso=50, cartoes=[
        c.cartao("Hoje", fmt.numero(r.hoje), f"{r.semana} na semana"),
        c.cartao("Sem fechar", fmt.numero(r.atrasados), "compromissos que já passaram",
                 "aviso" if r.atrasados else ""),
    ], listas=[
        c.lista("Hoje", [c.linha(x.titulo, x.cliente or x.tipo_label, x.horario) for x in r.do_dia],
                "Nada marcado para hoje."),
        c.lista("Próximos", [c.linha(x.titulo, f"{fmt.data(x.inicio)} · {x.cliente or x.tipo_label}", x.horario)
                             for x in r.proximos if x.id not in hoje]),
    ])
