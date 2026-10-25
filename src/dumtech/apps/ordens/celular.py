"""O DumTech Ordens de servico no celular: o quadro, o que atrasou e o que esta pronto.

Pronta e dinheiro parado na prateleira: a linha leva o botao que avisa o
cliente pelo WhatsApp, com a mensagem ja escrita.
"""

from __future__ import annotations

from ...core import celular as c
from ...ui import format as fmt


def _ordem(o, *, avisar: bool = False) -> dict:
    partes = [p for p in (o.numero, o.assunto) if p]
    acao = None
    if avisar:
        primeiro = (o.cliente or "").split(" ")[0]
        assunto = f" ({o.assunto})" if o.assunto else ""
        acao = c.whatsapp(o.telefone, (
            f"Olá{', ' + primeiro if primeiro else ''}! O serviço {o.numero}{assunto} está pronto. "
            "Pode vir buscar quando quiser."), "Avisar cliente")
    else:
        partes.append(o.status_label.replace("aprovacao", "aprovação"))
    return c.linha(o.cliente or "Sem cliente", " · ".join(partes),
                   fmt.moeda(o.total) if o.total else "", "perigo" if o.atrasada else "", acao=acao)


def _alertas(r) -> list[dict]:
    alertas = []
    if r.atrasadas:
        alertas.append(c.alerta(
            f"Resolver {fmt.contagem(r.atrasadas, 'ordem atrasada', 'ordens atrasadas')}", tom="perigo"))
    if r.prontas_total:
        alertas.append(c.alerta(
            f"Entregar {fmt.contagem(r.prontas_total, 'ordem pronta', 'ordens prontas')}", tom="aviso"))
    if r.aguardando:
        alertas.append(c.alerta(
            f"{fmt.contagem(r.aguardando, 'ordem espera', 'ordens esperam')} aprovação do cliente", tom="aviso"))
    return alertas


def secao(paths, manifesto) -> dict:
    from .database import open_database
    from .repository import OrdensRepository

    banco = open_database(paths.app_db(manifesto.app_id))
    try:
        r = OrdensRepository(banco).resumo(limite_listas=c.LIMITE_LISTA)
    finally:
        banco.close()

    em_aberto = r.abertas + r.aguardando + r.em_andamento
    return c.secao(
        manifesto.app_id, "Ordens de Serviço", peso=70,
        cartoes=[
            c.cartao("Em aberto", fmt.numero(em_aberto), f"{fmt.numero(r.aguardando)} aguardando aprovação"),
            c.cartao("Atrasadas", fmt.numero(r.atrasadas), "passaram do prazo", "perigo" if r.atrasadas else ""),
            c.cartao("Entregues no mês", fmt.numero(r.concluidas_mes), fmt.moeda(r.valor_mes)),
            c.cartao("Tempo médio", f"{fmt.numero(r.tempo_medio)} dias" if r.concluidas_mes else "—",
                     "da entrada à entrega"),
        ],
        graficos=[
            c.etapas("Quadro agora", [
                c.item("Aguardando aprovação", r.aguardando, fmt.numero(r.aguardando)),
                c.item("Na fila", r.abertas, fmt.numero(r.abertas)),
                c.item("Em andamento", r.em_andamento, fmt.numero(r.em_andamento)),
                c.item("Prontas", r.prontas_total, fmt.numero(r.prontas_total)),
            ], vazio="Nenhuma ordem em aberto."),
        ],
        listas=[
            c.lista("Prontas para entregar", [_ordem(o, avisar=True) for o in r.prontas],
                    "Nenhuma pronta agora."),
            c.lista("Na fila", [_ordem(o) for o in r.fila], "Fila vazia."),
        ],
        alertas=_alertas(r),
    )
