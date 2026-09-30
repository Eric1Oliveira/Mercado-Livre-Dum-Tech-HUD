"""Painel inicial do DumTech Estoque.

Responde as duas perguntas que o dono faz todo dia: o que preciso comprar e
quanto tenho parado em dinheiro. As duas sao de tamanho - por isso sao barras,
e nao colunas de numeros para comparar de cabeca.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.graficos import GraficoBarras, fatias_de
from ....ui.theme import Space
from ....ui.widgets.common import FaixaDeNumeros, StatCard, label
from ....ui.widgets.panels import ChartPanel, ListPanel
from ..models import TIPO_ENTRADA, TIPO_SAIDA, quantidade_texto
from ..repository import EstoqueRepository


class DashboardView(QWidget):
    """Resumo do estoque: numeros, o que comprar e onde esta o dinheiro."""

    def __init__(self, repository: EstoqueRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Painel", "title"))
        titulos.addWidget(label("Situacao atual do seu estoque", "subtitle"))
        raiz.addLayout(titulos)

        cartoes = FaixaDeNumeros()
        self.card_produtos = StatCard("Produtos ativos", "0", "box", "accent")
        self.card_valor = StatCard("Parado em estoque", "R$ 0,00", "money", "success")
        self.card_baixo = StatCard("Precisa comprar", "0", "alert", "warning")
        for cartao in (self.card_produtos, self.card_valor, self.card_baixo):
            cartoes.add(cartao)
        raiz.addWidget(cartoes)

        desenhos = QHBoxLayout()
        desenhos.setSpacing(Space.lg)
        self.grafico_comprar = GraficoBarras(largura_rotulo=170)
        self.grafico_comprar.vazio = "Nenhum produto no minimo. Estoque em dia."
        self.painel_comprar = ChartPanel(
            "O que precisa comprar", self.grafico_comprar, "quanto falta ate o maximo"
        )
        desenhos.addWidget(self.painel_comprar, 1)

        self.grafico_valor = GraficoBarras(largura_rotulo=170)
        self.grafico_valor.vazio = "Sem produtos com saldo para valorizar."
        self.painel_valor = ChartPanel(
            "Onde o dinheiro esta parado", self.grafico_valor
        )
        desenhos.addWidget(self.painel_valor, 1)
        raiz.addLayout(desenhos, 3)

        self.painel_movimentacoes = ListPanel(
            "Ultimas movimentacoes", "Nenhuma movimentacao registrada ainda."
        )
        raiz.addWidget(self.painel_movimentacoes, 2)

        self.refresh()

    def refresh(self) -> None:
        resumo = self.repository.resumo(limite_listas=4)

        self.card_produtos.set_value(
            fmt.numero(resumo.total_produtos),
            f"{quantidade_texto(resumo.total_itens)} itens somando todas as unidades",
        )
        self.card_valor.set_value(
            fmt.moeda(resumo.valor_custo), "Pelo custo medio dos produtos ativos"
        )
        self.card_baixo.set_value(
            fmt.numero(resumo.produtos_baixo),
            "Nenhum produto no minimo"
            if not resumo.produtos_baixo
            else "Produtos no minimo ou abaixo dele",
        )

        # o que comprar: a barra mede QUANTO comprar, nao o saldo que sobrou
        self.grafico_comprar.set_fatias(fatias_de(
            [
                (
                    produto.nome,
                    produto.sugestao_compra,
                    f"+{quantidade_texto(produto.sugestao_compra, produto.unidade)}",
                )
                for produto in resumo.a_comprar
            ],
            tons=["danger" if p.sem_estoque else "warning" for p in resumo.a_comprar],
        ))

        self.grafico_valor.set_fatias(fatias_de(
            [(produto.nome, produto.valor_em_estoque,
              fmt.moeda(produto.valor_em_estoque))
             for produto in resumo.maior_valor],
            tons=["success"] * len(resumo.maior_valor),
        ))
        self.painel_valor.set_nota(fmt.moeda(resumo.valor_custo))

        tons = {TIPO_ENTRADA: "success", TIPO_SAIDA: "danger"}
        self.painel_movimentacoes.set_items([
            (
                movimentacao.produto_nome,
                fmt.data_hora_curta(movimentacao.criado_em),
                movimentacao.variacao,
                tons.get(movimentacao.tipo, "muted"),
            )
            for movimentacao in resumo.ultimas
        ])
