"""O DumTech Agenda no celular: quem vem agora, o dia em linha do tempo e a semana.

O dono olha a agenda pelo telefone para saber uma coisa antes de todas: quem
e o proximo. Depois, como o dia esta andando (o que ja passou fica apagado) e
quanto da semana ja esta tomado.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ...core import celular as c
from ...ui import format as fmt


def _quem(x) -> str:
    return x.cliente or x.tipo_label


def _proximo(r, agora: datetime) -> dict:
    proximo = r.proximos[0] if r.proximos else None
    if proximo is None or proximo.inicio_dt is None:
        return c.cartao("Próximo", "—", "Nada marcado daqui para frente", largo=True)
    inicio = proximo.inicio_dt
    if inicio.date() == agora.date():
        quando = f"{inicio:%H:%M}"
    elif inicio.date() == agora.date() + timedelta(days=1):
        quando = f"Amanhã, {inicio:%H:%M}"
    else:
        quando = f"{c.DIAS_CURTOS[inicio.weekday()]} {c.data_curta(inicio)}, {inicio:%H:%M}"
    return c.cartao("Próximo", quando, f"{proximo.titulo} · {_quem(proximo)}", largo=True)


def _do_dia(x, agora: datetime) -> dict:
    inicio, fim = x.inicio_dt, x.fim_dt
    estado = ""
    if inicio and fim:
        estado = "passou" if fim <= agora else ("agora" if inicio <= agora else "")
    detalhe = "Bloqueio" if x.e_bloqueio else _quem(x)
    return c.linha(x.titulo, detalhe, x.duracao_texto, hora=f"{inicio:%H:%M}" if inicio else "",
                   estado=estado)


def _depois(x) -> dict:
    inicio = x.inicio_dt
    return c.linha(x.titulo, f"{inicio:%H:%M} · {_quem(x)}" if inicio else _quem(x), x.duracao_texto,
                   hora=f"{c.DIAS_CURTOS[inicio.weekday()]} {c.data_curta(inicio)}" if inicio else "")


def secao(paths, manifesto) -> dict:
    from .database import open_database
    from .repository import AgendaRepository

    banco = open_database(paths.app_db(manifesto.app_id))
    try:
        repositorio = AgendaRepository(banco)
        r = repositorio.resumo(limite_listas=c.LIMITE_LISTA)
        do_link = len(repositorio.do_link_para_confirmar())
    finally:
        banco.close()

    agora = datetime.now()
    hoje = agora.date()
    segunda = hoje - timedelta(days=hoje.weekday())
    do_dia = sorted(r.do_dia, key=lambda x: x.inicio or "")
    ja_listados = {x.id for x in do_dia}  # o de hoje ja esta na linha do tempo
    alertas = []
    if do_link:
        alertas.append(c.alerta(
            f"Confirmar {fmt.contagem(do_link, 'agendamento feito pelo link', 'agendamentos feitos pelo link')}",
            tom="aviso"))
    if r.atrasados:
        alertas.append(c.alerta(
            f"Fechar {fmt.contagem(r.atrasados, 'compromisso que já passou', 'compromissos que já passaram')}",
            tom="aviso"))

    return c.secao(
        manifesto.app_id, "Agenda", peso=50,
        cartoes=[
            _proximo(r, agora),
            c.cartao("Hoje", fmt.numero(r.hoje), f"{r.semana} na semana"),
            c.cartao("Sem fechar", fmt.numero(r.atrasados), "compromissos que já passaram",
                     "aviso" if r.atrasados else ""),
        ],
        graficos=[
            c.colunas("Esta semana", list(c.DIAS_CURTOS), r.por_dia_semana, "numero",
                      destaque=hoje.weekday(),
                      dicas=[f"{c.DIAS_CURTOS[n]}, {c.data_curta(segunda + timedelta(days=n))}"
                             for n in range(7)]),
        ],
        listas=[
            c.lista("Hoje", [_do_dia(x, agora) for x in do_dia], "Nada marcado para hoje."),
            c.lista("Próximos dias", [_depois(x) for x in r.proximos if x.id not in ja_listados]),
        ],
        alertas=alertas,
    )
