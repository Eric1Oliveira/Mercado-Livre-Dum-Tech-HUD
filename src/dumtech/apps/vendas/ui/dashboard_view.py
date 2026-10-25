"""Painel do DumTech Vendas: como foi o dia e o que ficou em aberto.

Como o cliente paga e quanto cada venda rendeu sao perguntas de tamanho - viram
desenho. O que ficou a prazo e uma lista de nomes para cobrar, e continua lista.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.graficos import GraficoBarras, GraficoRosca, fatias_de, maiores
from ....ui.theme import Space
from ....ui.widgets.common import FaixaDeNumeros, StatCard, label
from ....ui.widgets.panels import ChartPanel, ListPanel
from ..models import PENDENTE
from ..repository import VendasRepository


class DashboardView(QWidget):
    def __init__(self, repository: VendasRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Painel", "title"))
        titulos.addWidget(label("Como estão as vendas", "subtitle"))
        raiz.addLayout(titulos)

        cartoes = FaixaDeNumeros()
        self.card_hoje = StatCard("Vendido hoje", "R$ 0,00", "cart", "accent")
        self.card_caixa = StatCard("Caixa", "Fechado", "money", "muted")
        self.card_mes = StatCard("Vendido no mês", "R$ 0,00", "chart", "success")
        self.card_ticket = StatCard("Ticket médio", "R$ 0,00", "list", "warning")
        for cartao in (self.card_hoje, self.card_caixa, self.card_mes, self.card_ticket):
            cartoes.add(cartao)
        raiz.addWidget(cartoes)

        desenhos = QHBoxLayout()
        desenhos.setSpacing(Space.lg)
        self.grafico_formas = GraficoRosca(titulo_centro="No mês")
        self.painel_formas = ChartPanel(
            "Como o cliente paga", self.grafico_formas, "vendas do mês"
        )
        desenhos.addWidget(self.painel_formas, 3)

        self.grafico_ultimas = GraficoBarras(largura_rotulo=170)
        self.painel_ultimas = ChartPanel("Últimas vendas", self.grafico_ultimas)
        desenhos.addWidget(self.painel_ultimas, 2)
        raiz.addLayout(desenhos, 3)

        # venda a prazo e a que mais se perde: fica na frente do dono
        self.painel_pendentes = ListPanel(
            "A receber", "Nenhuma venda a prazo em aberto."
        )
        raiz.addWidget(self.painel_pendentes, 2)

        self.refresh()

    def refresh(self) -> None:
        resumo = self.repository.resumo(limite_listas=5)

        self.card_hoje.set_value(fmt.moeda(resumo.total_hoje))
        self._preencher_caixa(resumo)
        self.card_mes.set_value(
            fmt.moeda(resumo.total_mes),
            f"{resumo.vendas_mes} venda(s)"
            + (f"  ·  {fmt.moeda(resumo.devolvido_mes)} devolvido"
               if resumo.devolvido_mes else ""),
        )
        self.card_ticket.set_value(fmt.moeda(resumo.ticket_medio), "por venda no mês")

        formas = maiores(resumo.por_forma, 5)
        self.grafico_formas.set_fatias(fatias_de(
            [(forma, valor, fmt.moeda(valor)) for forma, valor in formas]
        ))
        self.grafico_formas.set_total(fmt.moeda(resumo.total_mes))

        self.grafico_ultimas.set_fatias(fatias_de(
            [(venda.cliente or "Consumidor", venda.total, fmt.moeda(venda.total))
             for venda in resumo.ultimas],
            tons=[venda.status_tom for venda in resumo.ultimas],
        ))
        self.painel_ultimas.set_nota(
            f"{len(resumo.ultimas)} mais recentes" if resumo.ultimas else ""
        )

        pendentes = self.repository.listar(status=PENDENTE, limite=5)
        self.painel_pendentes.set_items([
            (
                venda.cliente or "Consumidor",
                f"{venda.numero}  ·  {fmt.data(venda.data)}",
                fmt.moeda(venda.total),
                "warning",
            )
            for venda in pendentes
        ])

    def _preencher_caixa(self, resumo) -> None:
        if resumo.caixa is None:
            self.card_caixa.set_tone("muted")
            self.card_caixa.set_value("Fechado", "abra o caixa para conferir a gaveta")
            return
        conferencia = self.repository.conferencia(resumo.caixa.id)
        self.card_caixa.set_tone("success")
        self.card_caixa.set_value(
            fmt.moeda(conferencia.esperado),
            f"aberto desde {fmt.data_hora_curta(resumo.caixa.aberto_em)}",
        )
