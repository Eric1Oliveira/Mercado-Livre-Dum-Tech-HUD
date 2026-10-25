"""O DumTech Financeiro no celular: o saldo, para onde ele vai e o que atrasou.

O numero que importa nao e so o saldo de hoje - e o dia em que ele acaba. A
projecao e a mesma da tela de Fluxo do Hub (`repository/fluxo.py`): o que esta
em aberto, somado dia a dia; atrasado entra hoje.
"""

from __future__ import annotations

from datetime import date

from ...core import celular as c
from ...ui import format as fmt
from .models import ler_data


def _sinal(item) -> str:
    """Quem entra leva +, quem sai leva o sinal de menos: a direcao sem depender de cor."""
    return f"{'+' if item.e_receita else chr(0x2212)}{fmt.moeda(item.em_aberto)}"


def _atrasada(item, hoje: date) -> dict:
    vence = ler_data(item.vencimento) or hoje
    dias = (hoje - vence).days
    return c.linha(item.descricao_completa,
                   f"{'Receber' if item.e_receita else 'Pagar'} · {fmt.contagem(dias, 'dia', 'dias')} de atraso",
                   _sinal(item), "perigo", hora=c.data_curta(vence))


def _proxima(item, hoje: date) -> dict:
    vence = ler_data(item.vencimento) or hoje
    quem = item.cliente if getattr(item, "cliente", "") else ""
    detalhe = "Receber" if item.e_receita else "Pagar"
    if quem:
        detalhe += f" · {quem}"
    return c.linha(item.descricao_completa, detalhe, _sinal(item),
                   "aviso" if vence == hoje else "", hora="hoje" if vence == hoje else c.data_curta(vence))


def _destaque(projecao) -> dict:
    dias = [(date.fromisoformat(d.data), d) for d in projecao.dias]

    def dica(quando: date, dia) -> str:
        texto = f"{c.DIAS_CURTOS[quando.weekday()]}, {c.data_curta(quando)}"
        if dia.entradas:
            texto += f" · entra {fmt.moeda(dia.entradas)}"
        if dia.saidas:
            texto += f" · sai {fmt.moeda(dia.saidas)}"
        return texto

    vermelho = projecao.dia_no_vermelho
    if vermelho is not None:
        detalhe = f"Fica negativo em {c.data_curta(date.fromisoformat(vermelho.data))} se nada mudar"
    else:
        detalhe = f"Previsto em 30 dias: {fmt.moeda(projecao.saldo_final)}"
    return c.destaque([
        c.periodo("", "Saldo nas contas", fmt.moeda(projecao.saldo_inicial), projecao.saldo_inicial,
                  detalhe=detalhe,
                  grafico=c.linhas(
                      "Saldo previsto · 30 dias",
                      [c.data_curta(quando) for quando, _ in dias],
                      [c.serie("Saldo previsto", [dia.saldo for _, dia in dias], destaque=True)],
                      dicas=[dica(quando, dia) for quando, dia in dias],
                      zero=projecao.menor_saldo < 0,
                  )),
    ], tom="perigo" if vermelho is not None else "")


def _alertas(abertos, projecao, hoje: date) -> list[dict]:
    alertas = []
    atrasadas = [i for i in abertos if i.vencido]
    receber = [i for i in atrasadas if i.e_receita]
    pagar = [i for i in atrasadas if not i.e_receita]
    if receber:
        alertas.append(c.alerta(f"Cobrar {fmt.contagem(len(receber), 'conta atrasada', 'contas atrasadas')}",
                                fmt.moeda(sum(i.em_aberto for i in receber)), "perigo"))
    if pagar:
        alertas.append(c.alerta(f"Pagar {fmt.contagem(len(pagar), 'conta atrasada', 'contas atrasadas')}",
                                fmt.moeda(sum(i.em_aberto for i in pagar)), "perigo"))
    hoje_vence = [i for i in abertos if ler_data(i.vencimento) == hoje]
    if hoje_vence:
        texto = ("1 conta vence hoje" if len(hoje_vence) == 1
                 else f"{fmt.numero(len(hoje_vence))} contas vencem hoje")
        alertas.append(c.alerta(texto, fmt.moeda(sum(i.em_aberto for i in hoje_vence)), "aviso"))
    vermelho = projecao.dia_no_vermelho
    if vermelho is not None:
        alertas.append(c.alerta(
            f"Saldo fica negativo em {c.data_curta(date.fromisoformat(vermelho.data))}",
            fmt.moeda(projecao.menor_saldo), "perigo"))
    return alertas


def secao(paths, manifesto) -> dict:
    from .database import open_database
    from .repository import FinanceiroRepository
    from .repository.comum import SITUACAO_ABERTO

    banco = open_database(paths.app_db(manifesto.app_id))
    try:
        repositorio = FinanceiroRepository(banco)
        r = repositorio.resumo(limite_listas=c.LIMITE_LISTA)
        projecao = repositorio.projecao(30)
        abertos = repositorio.listar(situacao=SITUACAO_ABERTO, limite=5000)
    finally:
        banco.close()

    hoje = date.today()
    return c.secao(
        manifesto.app_id, "Financeiro", peso=80,
        destaque=_destaque(projecao),
        cartoes=[
            c.cartao("Saldo nas contas", fmt.moeda(r.saldo_contas), papel="destaque"),
            c.cartao("A receber · 30 dias", fmt.moeda(r.a_receber_mes),
                     f"{fmt.moeda(r.recebido_mes)} recebido no mês"),
            c.cartao("A pagar · 30 dias", fmt.moeda(r.a_pagar_mes), f"{fmt.moeda(r.pago_mes)} pago no mês"),
            c.cartao("Atrasado", fmt.moeda(r.vencidos_valor),
                     fmt.contagem(r.vencidos_quantidade, "conta", "contas"),
                     "perigo" if r.vencidos_quantidade else ""),
        ],
        graficos=[
            c.ranking("Gastos do mês por categoria",
                      [c.item(categoria, valor, fmt.moeda(valor)) for categoria, valor in r.por_categoria],
                      parte_do_todo=True) if r.por_categoria else None,
        ],
        listas=[
            c.lista("Atrasadas", [_atrasada(i, hoje) for i in r.atrasados], "Nada atrasado."),
            c.lista("Próximos vencimentos", [_proxima(i, hoje) for i in r.proximos], "Nada vencendo."),
        ],
        alertas=_alertas(abertos, projecao, hoje),
    )
