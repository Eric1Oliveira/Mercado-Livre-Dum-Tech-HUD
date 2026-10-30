"""A projecao: 'vou ter dinheiro no dia 12?'.

Comeca no saldo de hoje e soma, dia a dia, o que esta em aberto. Atrasado entra
no dia de hoje - e a tela diz isso e mostra quanto e, porque receber atrasado e
uma aposta e quem decide e o dono, nao o programa.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..models import RECORRENCIA, DiaDoFluxo, Projecao, ResumoFinanceiro, ler_data
from .comum import SITUACAO_ABERTO, dinheiro

#: quantos dias a tela mostra por padrao
HORIZONTE = 30


class FluxoMixin:
    """Parte do FinanceiroRepository que olha para a frente."""

    def projecao(self, dias: int = HORIZONTE) -> Projecao:
        hoje = date.today()
        fim = hoje + timedelta(days=int(dias))

        agenda = {
            (hoje + timedelta(days=passo)): DiaDoFluxo(
                data=(hoje + timedelta(days=passo)).isoformat()
            )
            for passo in range(int(dias) + 1)
        }

        atrasado_receber = atrasado_pagar = 0.0
        for lancamento in self.listar(situacao=SITUACAO_ABERTO, limite=5000):
            vence = ler_data(lancamento.vencimento)
            if vence is None or vence > fim:
                continue

            valor = lancamento.em_aberto
            if valor <= 0:
                continue

            if vence < hoje:
                # atrasado nao some do fluxo: entra hoje, e a tela avisa
                vence = hoje
                if lancamento.e_receita:
                    atrasado_receber += valor
                else:
                    atrasado_pagar += valor

            dia = agenda[vence]
            if vence == hoje and lancamento.vencido:
                dia.atrasado = True
            if lancamento.e_receita:
                dia.entradas += valor
            else:
                dia.saidas += valor
            dia.lancamentos.append(lancamento)

        saldo = self.saldo_total()
        ordenados = [agenda[chave] for chave in sorted(agenda)]
        for dia in ordenados:
            dia.entradas = dinheiro(dia.entradas)
            dia.saidas = dinheiro(dia.saidas)
            saldo = dinheiro(saldo + dia.movimento)
            dia.saldo = saldo

        return Projecao(
            saldo_inicial=self.saldo_total(),
            dias=ordenados,
            entradas=dinheiro(sum(dia.entradas for dia in ordenados)),
            saidas=dinheiro(sum(dia.saidas for dia in ordenados)),
            atrasado_receber=dinheiro(atrasado_receber),
            atrasado_pagar=dinheiro(atrasado_pagar),
        )

    # ------------------------------------------------------------------- painel
    def resumo(self, limite_listas: int = 6) -> ResumoFinanceiro:
        hoje = date.today().isoformat()
        mes = date.today().strftime("%Y-%m")
        abertos = self.listar(situacao=SITUACAO_ABERTO, limite=5000)
        vencidos = [item for item in abertos if item.vencido]
        limite = (date.today() + timedelta(days=HORIZONTE)).isoformat()
        proximos_30 = [i for i in abertos if i.vencimento <= limite]

        return ResumoFinanceiro(
            a_receber=dinheiro(sum(i.em_aberto for i in abertos if i.e_receita)),
            a_pagar=dinheiro(sum(i.em_aberto for i in abertos if not i.e_receita)),
            a_receber_mes=dinheiro(sum(i.em_aberto for i in proximos_30 if i.e_receita)),
            a_pagar_mes=dinheiro(sum(i.em_aberto for i in proximos_30 if not i.e_receita)),
            recorrente_mes=dinheiro(sum(i.em_aberto for i in proximos_30
                                        if i.e_receita and i.serie == RECORRENCIA)),
            vencidos_valor=dinheiro(sum(i.em_aberto for i in vencidos)),
            vencidos_quantidade=len(vencidos),
            # o mes conta pela data da BAIXA: e quando o dinheiro andou
            recebido_mes=self._movimentado_no_mes(mes, "receita"),
            pago_mes=self._movimentado_no_mes(mes, "despesa"),
            pago_fixas_mes=self._movimentado_no_mes(mes, "despesa", fixa=True),
            pago_variaveis_mes=self._movimentado_no_mes(mes, "despesa", fixa=False),
            saldo_contas=self.saldo_total(),
            proximos=sorted(
                (i for i in abertos if not i.vencido), key=lambda i: i.vencimento
            )[:limite_listas],
            atrasados=sorted(vencidos, key=lambda i: i.vencimento)[:limite_listas],
            contas=self.listar_contas(),
            por_categoria=self._despesas_por_categoria(mes, limite_listas),
        )

    def realizado_no_mes(self, mes: str = "") -> tuple[float, float]:
        """(entrou, saiu) no mes, pela data da baixa: so o dinheiro que ja andou."""
        mes = mes or date.today().strftime("%Y-%m")
        return (self._movimentado_no_mes(mes, "receita"),
                self._movimentado_no_mes(mes, "despesa"))

    def _movimentado_no_mes(self, mes: str, tipo: str, fixa: bool | None = None) -> float:
        sql = ("SELECT COALESCE(SUM(b.valor), 0) FROM baixas b"
               " JOIN lancamentos l ON l.id = b.lancamento_id"
               " WHERE l.tipo = ? AND b.data LIKE ?")
        params: list = [tipo, f"{mes}%"]
        if fixa is not None:
            sql += " AND l.fixa = ?"
            params.append(int(fixa))
        return dinheiro(self.db.scalar(sql, params, default=0.0))

    def _despesas_por_categoria(self, mes: str, limite: int) -> list[tuple[str, float]]:
        """As despesas pagas neste mes, por categoria."""
        linhas = self.db.query(
            "SELECT COALESCE(NULLIF(TRIM(l.categoria), ''), 'Sem categoria') AS categoria,"
            " SUM(b.valor) AS total"
            " FROM baixas b JOIN lancamentos l ON l.id = b.lancamento_id"
            " WHERE l.tipo = 'despesa' AND b.data LIKE ?"
            " GROUP BY categoria ORDER BY total DESC LIMIT ?",
            (f"{mes}%", int(limite)),
        )
        return [(row["categoria"], dinheiro(row["total"])) for row in linhas]

    def previsto_hoje(self) -> tuple[float, float]:
        """(entra, sai) hoje - o que a barra do topo mostra."""
        projecao = self.projecao(dias=0)
        dia = projecao.dias[0] if projecao.dias else None
        return (dia.entradas, dia.saidas) if dia else (0.0, 0.0)
