"""Painel do DumTech Ordem de Servico: os servicos em numeros.

Quantas ordens em cada etapa e quanto do faturamento foi peca ou mao de obra
sao perguntas de tamanho - viram desenho. O que espera resposta do cliente e
o que espera retirada sao filas com nome e telefone, e continuam listas.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.graficos import Fatia, GraficoColunas, GraficoRosca
from ....ui.theme import Space
from ....ui.widgets.common import FaixaDeNumeros, StatCard, label
from ....ui.widgets.panels import ChartPanel, ListPanel
from ..models import STATUS_LABEL, STATUS_TOM
from ..repository import OrdensRepository


class DashboardView(QWidget):
    def __init__(self, repository: OrdensRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Painel", "title"))
        titulos.addWidget(label("Como estão os serviços", "subtitle"))
        raiz.addLayout(titulos)

        cartoes = FaixaDeNumeros()
        self.card_oficina = StatCard("Em andamento", "0", "wrench", "accent")
        self.card_aguardando = StatCard("Esperando o cliente", "0", "clock", "warning")
        self.card_atrasadas = StatCard("Passaram do prazo", "0", "alert", "danger")
        self.card_faturado = StatCard("Entregue no mês", "R$ 0,00", "money", "success")
        for cartao in (self.card_oficina, self.card_aguardando, self.card_atrasadas,
                       self.card_faturado):
            cartoes.add(cartao)
        raiz.addWidget(cartoes)

        desenhos = QHBoxLayout()
        desenhos.setSpacing(Space.lg)
        self.grafico_etapas = GraficoColunas()
        self.grafico_etapas.vazio = "Nenhuma ordem em andamento agora."
        self.painel_etapas = ChartPanel(
            "O quadro por etapa", self.grafico_etapas, "ordens em aberto"
        )
        desenhos.addWidget(self.painel_etapas, 3)

        self.grafico_composicao = GraficoRosca(titulo_centro="Entregue no mês")
        self.grafico_composicao.vazio = "Nenhuma entrega neste mês."
        self.painel_composicao = ChartPanel(
            "Material ou mão de obra", self.grafico_composicao
        )
        desenhos.addWidget(self.painel_composicao, 2)
        raiz.addLayout(desenhos, 3)

        listas = QHBoxLayout()
        listas.setSpacing(Space.lg)
        # esperando resposta na frente: e a fila que so anda com um telefonema
        self.painel_aguardando = ListPanel(
            "Esperando aprovação", "Nenhum orçamento parado esperando o cliente."
        )
        listas.addWidget(self.painel_aguardando, 1)
        self.painel_prontas = ListPanel(
            "Prontas para retirar", "Nada aguardando retirada."
        )
        listas.addWidget(self.painel_prontas, 1)
        raiz.addLayout(listas, 2)

        self.refresh()

    def refresh(self) -> None:
        resumo = self.repository.resumo(limite_listas=4)

        self.card_oficina.set_value(
            fmt.numero(resumo.abertas + resumo.aguardando + resumo.em_andamento),
            f"{resumo.em_andamento} em serviço  ·  {resumo.abertas} na entrada",
        )
        self.card_aguardando.set_value(fmt.numero(resumo.aguardando))
        self.card_atrasadas.set_value(fmt.numero(resumo.atrasadas))
        self.card_faturado.set_value(
            fmt.moeda(resumo.valor_mes), self._composicao(resumo)
        )

        faixas = self.repository.por_etapa()
        self.grafico_etapas.set_fatias([
            Fatia(STATUS_LABEL.get(status, status), len(ordens),
                  STATUS_TOM.get(status, "accent"), str(len(ordens)))
            for status, ordens in faixas.items() if ordens
        ])
        self.painel_etapas.set_nota(
            fmt.contagem(sum(len(o) for o in faixas.values()), "ordem", "ordens")
        )

        self.grafico_composicao.set_fatias([
            Fatia("Materiais", resumo.pecas_mes, "accent", fmt.moeda(resumo.pecas_mes)),
            Fatia("Mão de obra", resumo.servicos_mes, "success",
                  fmt.moeda(resumo.servicos_mes)),
        ] if resumo.valor_mes else [])
        self.grafico_composicao.set_total(fmt.moeda(resumo.valor_mes))

        self.painel_aguardando.set_items([
            (
                ordem.assunto,
                f"{ordem.cliente}  ·  {ordem.numero}",
                fmt.moeda(ordem.total),
                "warning",
            )
            for ordem in resumo.aguardando_lista
        ])

        self.painel_prontas.set_items([
            (ordem.assunto, ordem.cliente, fmt.moeda(ordem.total), "success")
            for ordem in resumo.prontas
        ])

    @staticmethod
    def _prazo(ordem) -> str:
        if ordem.prazo:
            return fmt.prazo_texto(ordem.prazo)
        dias = ordem.dias_em_aberto
        return "entrou hoje" if dias == 0 else f"há {fmt.dias(dias)}"

    @staticmethod
    def _composicao(resumo) -> str:
        """Material e mao de obra separados: a conta que diz se valeu a pena."""
        if not resumo.concluidas_mes:
            return "nenhuma entrega neste mês"
        partes = [fmt.contagem(resumo.concluidas_mes, "entrega")]
        if resumo.pecas_mes or resumo.servicos_mes:
            partes.append(
                f"{fmt.moeda(resumo.pecas_mes)} em material, "
                f"{fmt.moeda(resumo.servicos_mes)} em serviço"
            )
        return "  ·  ".join(partes)
