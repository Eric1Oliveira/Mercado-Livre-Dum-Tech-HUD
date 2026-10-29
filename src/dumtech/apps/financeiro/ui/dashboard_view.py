"""Painel do DumTech Financeiro: o retrato de agora.

Tres perguntas, nesta ordem: quanto eu tenho, para onde o dinheiro esta indo e
o que precisa de telefonema hoje. As duas primeiras sao de proporcao, e por isso
sao desenho; a terceira e uma lista de nomes, e por isso continua lista.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.graficos import GraficoBarras, GraficoRosca, fatias_de, maiores
from ....ui.theme import Space
from ....ui.widgets.common import FaixaDeNumeros, StatCard, label
from ....ui.widgets.panels import ChartPanel, ListPanel
from ..models import CENTAVO
from ..repository import FinanceiroRepository


NOTA_CATEGORIAS = "despesas pagas no mês"


class DashboardView(QWidget):
    def __init__(self, repository: FinanceiroRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Painel", "title"))
        titulos.addWidget(label("Contas a receber, a pagar e o resultado do mês",
                                "subtitle"))
        raiz.addLayout(titulos)

        cartoes = FaixaDeNumeros()
        self.card_saldo = StatCard("Dinheiro em conta", "R$ 0,00", "money", "accent")
        self.card_receber = StatCard("A receber (30 dias)", "R$ 0,00", "in", "success")
        self.card_pagar = StatCard("A pagar (30 dias)", "R$ 0,00", "out", "danger")
        self.card_vencidos = StatCard("Vencidos", "R$ 0,00", "alert", "warning")
        for cartao in (self.card_saldo, self.card_receber, self.card_pagar,
                       self.card_vencidos):
            cartoes.add(cartao)
        raiz.addWidget(cartoes)

        desenhos = QHBoxLayout()
        desenhos.setSpacing(Space.lg)
        self.grafico_categorias = GraficoRosca(titulo_centro="Pago no mês")
        self.painel_categorias = ChartPanel(
            "Categoria de despesas", self.grafico_categorias, NOTA_CATEGORIAS
        )
        desenhos.addWidget(self.painel_categorias, 3)

        self.grafico_contas = GraficoBarras(largura_rotulo=130)
        self.painel_contas = ChartPanel("Onde o dinheiro está", self.grafico_contas)
        desenhos.addWidget(self.painel_contas, 2)
        raiz.addLayout(desenhos, 3)

        listas = QHBoxLayout()
        listas.setSpacing(Space.lg)
        # a única lista do painel: é a que vira telefonema hoje
        self.painel_atrasados = ListPanel("Vencidos", "Nada vencido. Contas em dia.")
        listas.addWidget(self.painel_atrasados, 1)
        self.painel_proximos = ListPanel("Próximos vencimentos",
                                         "Nenhum vencimento à vista.")
        listas.addWidget(self.painel_proximos, 1)
        raiz.addLayout(listas, 2)

        self.refresh()

    def refresh(self) -> None:
        resumo = self.repository.resumo(limite_listas=4)

        self.card_saldo.set_tone("danger" if resumo.saldo_contas < -CENTAVO else "accent")
        self.card_saldo.set_value(
            fmt.moeda(resumo.saldo_contas), self._resumo_contas(resumo)
        )
        # o cartao mostra os proximos 30 dias; o total em aberto vai na dica,
        # senao a recorrencia do ano inteiro engole o numero que interessa
        dica = self._total(resumo.a_receber)
        if resumo.recorrente_mes > CENTAVO:
            # mensalidade e contrato: o pedaco do numero que se repete todo mes
            dica = f"{fmt.moeda(resumo.recorrente_mes)} recorrente  ·  {dica}"
        self.card_receber.set_value(fmt.moeda(resumo.a_receber_mes), dica)
        self.card_pagar.set_value(
            fmt.moeda(resumo.a_pagar_mes), self._total(resumo.a_pagar)
        )
        self.card_vencidos.set_value(
            fmt.moeda(resumo.vencidos_valor),
            f"{resumo.vencidos_quantidade} conta(s)" if resumo.vencidos_quantidade else "",
        )

        categorias = maiores(resumo.por_categoria, 5)
        self.grafico_categorias.set_fatias(fatias_de(
            [(nome, valor, fmt.moeda(valor)) for nome, valor in categorias]
        ))
        self.grafico_categorias.set_total(fmt.moeda(resumo.pago_mes))
        # fixa e variavel na mesma linha: o quanto do mes ja estava comprometido
        self.painel_categorias.set_nota(
            f"fixas {fmt.moeda(resumo.pago_fixas_mes)}  ·  "
            f"variáveis {fmt.moeda(resumo.pago_variaveis_mes)}"
            if resumo.pago_mes > CENTAVO else NOTA_CATEGORIAS
        )

        self.grafico_contas.set_fatias(fatias_de(
            [(conta.nome, conta.saldo, fmt.moeda(conta.saldo))
             for conta in resumo.contas],
            tons=["accent"] * len(resumo.contas),
        ))
        self.painel_contas.set_nota(fmt.moeda(resumo.saldo_contas))

        self.painel_atrasados.set_items([
            (
                item.descricao_completa,
                f"{item.cliente or item.categoria or item.tipo_label}"
                f"  ·  {fmt.prazo_texto(item.vencimento)}",
                fmt.moeda(item.em_aberto),
                "danger",
            )
            for item in resumo.atrasados
        ])

        self.painel_proximos.set_items([
            (
                item.descricao_completa,
                f"{fmt.data(item.vencimento)}  ·  {fmt.prazo_texto(item.vencimento)}",
                fmt.moeda(item.em_aberto),
                "success" if item.e_receita else "warning",
            )
            for item in resumo.proximos
        ])

    @staticmethod
    def _total(valor: float) -> str:
        return f"em aberto no total: {fmt.moeda(valor)}"

    @staticmethod
    def _resumo_contas(resumo) -> str:
        """O saldo do mes explica o numero grande sem precisar de outro cartao."""
        saldo = resumo.saldo_mes
        sinal = "+" if saldo >= 0 else "-"
        return (
            f"no mês: {sinal} {fmt.moeda(abs(saldo))}"
            f"  ({fmt.moeda(resumo.recebido_mes)} entrou, "
            f"{fmt.moeda(resumo.pago_mes)} saiu)"
        )
