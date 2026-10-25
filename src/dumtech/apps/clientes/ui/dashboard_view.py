"""Painel do DumTech Clientes.

Onde estao e de que tipo sao os clientes: duas perguntas de proporcao, dois
desenhos. Quem faz aniversario e uma lista de nomes para ligar hoje.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ....core.contacts import ContactsStore
from ....ui import format as fmt
from ....ui.graficos import GraficoBarras, GraficoRosca, fatias_de, maiores
from ....ui.theme import Space
from ....ui.widgets.common import FaixaDeNumeros, StatCard, label
from ....ui.widgets.panels import ChartPanel, ListPanel

MESES = (
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
SEM_SEGMENTO = "Sem segmento"


class DashboardView(QWidget):
    """Quem sao seus clientes e para quem ligar hoje."""

    def __init__(self, store: ContactsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Painel", "title"))
        titulos.addWidget(label("Sua carteira de clientes", "subtitle"))
        raiz.addLayout(titulos)

        cartoes = FaixaDeNumeros()
        self.card_total = StatCard("Clientes ativos", "0", "users", "accent")
        self.card_mes = StatCard("Novos neste mês", "0", "plus", "success")
        self.card_cidades = StatCard("Cidades atendidas", "0", "home", "warning")
        for cartao in (self.card_total, self.card_mes, self.card_cidades):
            cartoes.add(cartao)
        raiz.addWidget(cartoes)

        desenhos = QHBoxLayout()
        desenhos.setSpacing(Space.lg)
        self.grafico_cidades = GraficoBarras(largura_rotulo=150)
        self.grafico_cidades.vazio = "Sem cidades informadas no cadastro."
        self.painel_cidades = ChartPanel(
            "Onde estão os clientes", self.grafico_cidades
        )
        desenhos.addWidget(self.painel_cidades, 1)

        self.grafico_segmentos = GraficoRosca(titulo_centro="Ativos")
        self.grafico_segmentos.vazio = "Preencha o segmento no cadastro."
        self.painel_segmentos = ChartPanel(
            "De que tipo são", self.grafico_segmentos
        )
        desenhos.addWidget(self.painel_segmentos, 1)
        raiz.addLayout(desenhos, 3)

        listas = QHBoxLayout()
        listas.setSpacing(Space.lg)
        mes = MESES[date.today().month - 1]
        # aniversario e o motivo mais barato de ligar para um cliente antigo
        self.painel_aniversarios = ListPanel(
            f"Aniversariantes de {mes}",
            "Ninguém faz aniversário este mês. Preencha a data no cadastro.",
        )
        listas.addWidget(self.painel_aniversarios, 1)
        self.painel_recentes = ListPanel(
            "Últimos cadastros", "Nenhum cliente cadastrado ainda."
        )
        listas.addWidget(self.painel_recentes, 1)
        raiz.addLayout(listas, 2)

        self.refresh()

    def refresh(self) -> None:
        resumo = self.store.resumo(limite=4)
        hoje = date.today()

        self.card_total.set_value(
            fmt.numero(resumo.ativos),
            f"{resumo.total - resumo.ativos} inativo(s)"
            if resumo.total > resumo.ativos else "",
        )
        self.card_mes.set_value(fmt.numero(resumo.novos_mes))
        self.card_cidades.set_value(fmt.numero(resumo.cidades))

        self.grafico_cidades.set_fatias(fatias_de(
            [(cidade, quantidade, fmt.numero(quantidade))
             for cidade, quantidade in maiores(resumo.por_cidade, 6)],
            tons=["accent"] * 7,
        ))

        segmentos = Counter(
            (contato.segmento.strip() or SEM_SEGMENTO) for contato in self.store.listar()
        )
        self.grafico_segmentos.set_fatias(fatias_de(
            [(nome, quantidade, fmt.numero(quantidade))
             for nome, quantidade in maiores(segmentos.most_common(), 5)]
        ))
        self.grafico_segmentos.set_total(fmt.numero(resumo.ativos))

        self.painel_aniversarios.set_items([
            (
                contato.nome,
                f"{contato.idade_neste_ano} anos"
                if contato.idade_neste_ano is not None
                else "",
                self._dia_aniversario(contato, hoje),
                "success" if self._e_hoje(contato, hoje) else "accent",
            )
            for contato in resumo.aniversariantes
        ])

        self.painel_recentes.set_items([
            (c.nome, c.resumo or "sem contato informado", fmt.data(c.criado_em), "muted")
            for c in resumo.recentes
        ])

    @staticmethod
    def _e_hoje(contato, hoje: date) -> bool:
        aniversario = contato.aniversario
        return bool(aniversario and aniversario == (hoje.day, hoje.month))

    def _dia_aniversario(self, contato, hoje: date) -> str:
        aniversario = contato.aniversario
        if not aniversario:
            return "-"
        if self._e_hoje(contato, hoje):
            return "é hoje!"
        return f"dia {aniversario[0]:02d}"
