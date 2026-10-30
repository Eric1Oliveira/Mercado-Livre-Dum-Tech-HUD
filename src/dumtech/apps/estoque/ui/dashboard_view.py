"""Painel inicial do DumTech Estoque.

Responde as duas perguntas que o dono faz todo dia: o que preciso repor e
quanto tenho investido em mercadoria. As duas viram tabela curta, e nao barra:
cada linha tem mais de um numero para ler (quanto tem, quanto comprar; quanto
vale, que parte do todo).

A cor so aparece onde ha o que fazer - zerado e baixo. O resto fica na cor do
texto: se tudo tem destaque, nada tem.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.theme import Space
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import FaixaDeNumeros, StatCard, label
from ....ui.widgets.panels import TablePanel
from ....ui.widgets.table import DIREITA, ESQUERDA
from ..models import quantidade_texto
from ..repository import EstoqueRepository

#: quantos produtos para repor cabem no Painel; passou disso, "Ver todos"
CRITICOS = 5
#: produtos com nome na tabela de valor; o resto vira uma linha "Outros"
MAIORES = 6


class DashboardView(QWidget):
    """Resumo do estoque: numeros, o que repor e quanto vale cada produto."""

    data_changed = Signal()

    def __init__(self, repository: EstoqueRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Painel", "title"))
        titulos.addWidget(label("Situação atual do seu estoque", "subtitle"))
        raiz.addLayout(titulos)

        cartoes = FaixaDeNumeros()
        self.card_produtos = StatCard("Produtos ativos", "0", "box", "accent")
        self.card_valor = StatCard("Valor investido em estoque", "R$ 0,00", "money", "accent")
        self.card_reposicao = StatCard("Produtos para reposição", "0", "alert", "warning")
        self.card_reposicao.tornar_clicavel("Ver os produtos para repor e registrar a reposição")
        self.card_reposicao.clicado.connect(self.abrir_reposicao)
        for cartao in (self.card_produtos, self.card_valor, self.card_reposicao):
            cartoes.add(cartao)
        raiz.addWidget(cartoes)

        tabelas = QHBoxLayout()
        tabelas.setSpacing(Space.lg)
        self.painel_reposicao = TablePanel(
            "Produtos para reposição",
            [("Produto", ESQUERDA), ("Situação", ESQUERDA),
             ("Em estoque", DIREITA), ("Sugerido", DIREITA)],
            vazio="Nenhum produto no estoque mínimo. Estoque em dia.",
            apoio="Quantidade sugerida para atingir o estoque máximo.",
        )
        self.botao_ver_todos = Button("Ver todos", "list")
        self.botao_ver_todos.clicked.connect(self.abrir_reposicao)
        self.painel_reposicao.body.addWidget(self.botao_ver_todos, 0, Qt.AlignmentFlag.AlignLeft)
        tabelas.addWidget(self.painel_reposicao, 1)

        self.painel_valor = TablePanel(
            "Valor do estoque por produto",
            [("Produto", ESQUERDA), ("Valor", DIREITA), ("Participação", DIREITA)],
            vazio="Sem produtos com saldo para valorizar.",
            apoio="Distribuição do custo das mercadorias em estoque.",
        )
        tabelas.addWidget(self.painel_valor, 1)
        raiz.addLayout(tabelas, 3)

        self.painel_movimentacoes = TablePanel(
            "Movimentações recentes",
            [("Produto", ESQUERDA), ("Tipo de movimentação", ESQUERDA),
             ("Quantidade", DIREITA), ("Data e hora", DIREITA)],
            vazio="Nenhuma movimentação registrada ainda.",
        )
        raiz.addWidget(self.painel_movimentacoes, 2)

        self.refresh()

    def refresh(self) -> None:
        resumo = self.repository.resumo(limite_listas=MAIORES)

        self.card_produtos.set_value(
            fmt.numero(resumo.total_produtos),
            f"{quantidade_texto(resumo.total_itens)} unidades em estoque",
        )
        self.card_valor.set_value(
            fmt.moeda(resumo.valor_custo), "Pelo custo médio dos produtos ativos"
        )
        self._mostrar_reposicao(resumo)
        self._mostrar_valor(resumo)

        self.painel_movimentacoes.set_linhas([
            [
                movimentacao.produto_nome,
                movimentacao.tipo_label,
                f"{movimentacao.variacao} {movimentacao.unidade}",
                fmt.data_hora_curta(movimentacao.criado_em),
            ]
            for movimentacao in resumo.ultimas
        ])

    def _mostrar_reposicao(self, resumo) -> None:
        total = resumo.produtos_baixo
        zerados = min(resumo.sem_estoque, total)
        baixos = total - zerados

        partes = []
        if zerados:
            partes.append(fmt.contagem(zerados, "zerado"))
        if baixos:
            partes.append(f"{fmt.numero(baixos)} abaixo do mínimo")
        self.card_reposicao.set_tone("danger" if zerados else ("warning" if total else "accent"))
        self.card_reposicao.set_value(
            fmt.numero(total),
            "  ·  ".join(partes) if partes else "Nenhum produto no estoque mínimo",
        )

        # poucos: a lista inteira, compacta; muitos: os mais criticos e "Ver todos"
        self.painel_reposicao.set_linhas([
            [
                produto.nome,
                ("Zerado", "danger") if produto.sem_estoque else ("Baixo", "warning"),
                quantidade_texto(produto.quantidade, produto.unidade, True),
                f"+{quantidade_texto(produto.sugestao_compra, produto.unidade)}"
                if produto.sugestao_compra > 0 else "-",
            ]
            for produto in resumo.a_comprar[:CRITICOS]
        ])
        self.painel_reposicao.set_nota(fmt.contagem(total, "produto") if total else "")
        muitos = total > CRITICOS
        self.botao_ver_todos.setText(
            f"  Ver todos ({fmt.numero(total)})" if muitos else "  Registrar reposição"
        )
        self.botao_ver_todos.set_icon_name("list" if muitos else "in")
        self.botao_ver_todos.setVisible(bool(total))

    def _mostrar_valor(self, resumo) -> None:
        total = resumo.valor_custo
        linhas = [(produto.nome, produto.valor_em_estoque) for produto in resumo.maior_valor]
        outros = total - sum(valor for _nome, valor in linhas)
        if outros > 0.005:
            linhas.append(("Outros produtos", outros))

        self.painel_valor.set_linhas([
            [nome, fmt.moeda(valor), _participacao(valor, total)]
            for nome, valor in linhas
        ])
        self.painel_valor.set_nota(fmt.moeda(total) if linhas else "")

    # ------------------------------------------------------------------- acoes
    def abrir_reposicao(self) -> None:
        from .reposicao_dialog import ReposicaoDialog

        dialogo = ReposicaoDialog(self.repository, self)
        dialogo.exec()
        if dialogo.houve_mudanca:
            self.data_changed.emit()


def _participacao(valor: float, total: float) -> str:
    """A parte do todo, com uma casa: "12,5%"."""
    if total <= 0:
        return "-"
    return f"{valor / total * 100:.1f}%".replace(".", ",")
