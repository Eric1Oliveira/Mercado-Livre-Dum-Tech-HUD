"""Quanto a loja ganhou de verdade, e com o que e com quem."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ....core import exportar
from ....ui import format as fmt
from ....ui.theme import Space, apply_window_theme, palette_for
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import label, repolish, tone_label
from ....ui.widgets.table import DIREITA, DataTable
from ..models import VendaError
from ..repository import VendasRepository

PERIODOS = (("Este mês", "mes"), ("Mês passado", "passado"), ("Este ano", "ano"))


def periodo(chave: str, hoje: date | None = None) -> tuple[str, str]:
    hoje = hoje or date.today()
    if chave == "ano":
        return hoje.replace(month=1, day=1).isoformat(), hoje.isoformat()
    primeiro = hoje.replace(day=1)
    if chave == "passado":
        ultimo = primeiro - timedelta(days=1)
        return ultimo.replace(day=1).isoformat(), ultimo.isoformat()
    return primeiro.isoformat(), hoje.isoformat()


def _porcento(valor: float) -> str:
    return f"{valor:.1f}%".replace(".", ",")


class VendedoresDialog(QDialog):
    """Quem vende aqui, e quanto ganha de comissao."""

    def __init__(self, repository: VendasRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.setWindowTitle("Vendedores")
        self.setModal(True)
        self.setMinimumSize(480, 420)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)
        raiz.addWidget(label("Vendedores", "section"))

        linha = QHBoxLayout()
        self.nome = QLineEdit()
        self.nome.setPlaceholderText("Nome")
        linha.addWidget(self.nome, 3)
        self.comissao = form.percentual(0.0)
        linha.addWidget(self.comissao, 1)
        adicionar = Button("Salvar", "plus", "primary")
        adicionar.clicked.connect(self._salvar)
        linha.addWidget(adicionar)
        raiz.addLayout(linha)

        self.tabela = DataTable(["Vendedor", "Comissão"])
        self.tabela.set_empty_message("Nenhum vendedor cadastrado.")
        raiz.addWidget(self.tabela, 1)

        rodape = QHBoxLayout()
        self.aviso = label("", "muted")
        rodape.addWidget(self.aviso, 1)
        tirar = Button("Tirar da lista", "close")
        tirar.clicked.connect(self._tirar)
        rodape.addWidget(tirar)
        fechar = Button("Fechar", "check", "primary")
        fechar.clicked.connect(self.accept)
        rodape.addWidget(fechar)
        raiz.addLayout(rodape)

        apply_window_theme(self, palette_for(parent))
        self.carregar()

    def carregar(self) -> None:
        self.lista = self.repository.vendedores()
        self.tabela.fill(
            [[self.tabela.cell(v.nome, bold=True),
              self.tabela.cell(_porcento(v.comissao), DIREITA)] for v in self.lista],
            {1: 110},
        )

    def _salvar(self) -> None:
        try:
            self.repository.salvar_vendedor(self.nome.text(), self.comissao.value())
        except VendaError as erro:
            self.aviso.setText(str(erro))
            self.aviso.setProperty("tone", "danger")
            repolish(self.aviso)
            return
        self.nome.clear()
        self.comissao.setValue(0.0)
        self.carregar()

    def _tirar(self) -> None:
        linha = self.tabela.currentRow()
        if 0 <= linha < len(self.lista):
            self.repository.inativar_vendedor(self.lista[linha].nome)
            self.carregar()


class ResultadoView(QWidget):
    data_changed = Signal()

    def __init__(self, repository: VendasRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.resultado = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.md)

        topo = QHBoxLayout()
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Resultado", "title"))
        titulos.addWidget(label("Lucro, margem e comissão do período", "subtitle"))
        topo.addLayout(titulos, 1)
        self.periodo = QComboBox()
        for rotulo, chave in PERIODOS:
            self.periodo.addItem(rotulo, chave)
        self.periodo.currentIndexChanged.connect(self.refresh)
        topo.addWidget(self.periodo)
        self.botao_vendedores = Button("Vendedores", "users")
        self.botao_vendedores.clicked.connect(self._vendedores)
        topo.addWidget(self.botao_vendedores)
        self.botao_exportar = Button("Exportar", "file")
        self.botao_exportar.clicked.connect(self.exportar)
        topo.addWidget(self.botao_exportar)
        raiz.addLayout(topo)

        self.numeros = tone_label("", "accent", "cardTitle")
        self.numeros.setWordWrap(True)
        raiz.addWidget(self.numeros)
        self.alerta = label("", "muted")
        self.alerta.setWordWrap(True)
        raiz.addWidget(self.alerta)

        raiz.addWidget(label("Os produtos que mais deram lucro", "section"))
        self.tabela_produtos = DataTable(["Produto", "Quantidade", "Receita", "Lucro", "Margem"])
        self.tabela_produtos.set_empty_message("Nenhuma venda neste período.")
        raiz.addWidget(self.tabela_produtos, 2)

        raiz.addWidget(label("Vendedores", "section"))
        self.tabela_vendedores = DataTable(["Vendedor", "Vendas", "Vendido", "Lucro", "Comissão"])
        self.tabela_vendedores.set_empty_message(
            "Nenhuma venda com vendedor. Cadastre em Vendedores e escolha no balcão."
        )
        raiz.addWidget(self.tabela_vendedores, 1)

    def refresh(self) -> None:
        inicio, fim = periodo(self.periodo.currentData())
        r = self.resultado = self.repository.resultado(inicio, fim)
        self.numeros.setText(
            f"Vendeu {fmt.moeda(r.receita)}   ·   Custo {fmt.moeda(r.custo)}   ·   "
            f"Lucro {fmt.moeda(r.lucro)}   ·   Margem {_porcento(r.margem)}"
        )
        self.alerta.setText(
            f"{r.itens_sem_custo} item(ns) sem custo conhecido: o lucro real é menor que "
            "este. Informe o custo nas entradas do Estoque." if r.itens_sem_custo else ""
        )
        self.tabela_produtos.fill(
            [[self.tabela_produtos.cell(l.nome, bold=True),
              self.tabela_produtos.cell(fmt.numero(l.quantidade), DIREITA),
              self.tabela_produtos.cell(fmt.moeda(l.receita), DIREITA),
              self.tabela_produtos.cell(fmt.moeda(l.lucro), DIREITA, "accent", bold=True),
              self.tabela_produtos.cell(_porcento(l.margem), DIREITA)]
             for l in r.produtos],
            {1: 110, 2: 130, 3: 130, 4: 100},
        )
        self.tabela_vendedores.fill(
            [[self.tabela_vendedores.cell(l.nome, bold=True),
              self.tabela_vendedores.cell(fmt.numero(l.quantidade), DIREITA),
              self.tabela_vendedores.cell(fmt.moeda(l.receita), DIREITA),
              self.tabela_vendedores.cell(fmt.moeda(l.lucro), DIREITA),
              self.tabela_vendedores.cell(fmt.moeda(l.comissao), DIREITA, "accent", bold=True)]
             for l in r.vendedores],
            {1: 90, 2: 130, 3: 130, 4: 120},
        )

    def _vendedores(self) -> None:
        VendedoresDialog(self.repository, self).exec()
        self.refresh()
        self.data_changed.emit()

    def exportar(self) -> None:
        caminho, _ = QFileDialog.getSaveFileName(self, "Exportar resultado", "Resultado.csv",
                                                 "Planilha CSV (*.csv)")
        if not caminho:
            return
        exportar.gravar(caminho, exportar.csv_de(
            ["Produto", "Quantidade", "Receita", "Custo", "Lucro"],
            [[l.nome, fmt.numero(l.quantidade), fmt.moeda(l.receita), fmt.moeda(l.custo),
              fmt.moeda(l.lucro)] for l in self.resultado.produtos],
        ))
