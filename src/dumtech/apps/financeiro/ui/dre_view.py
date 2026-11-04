"""DRE: o que a loja ganhou de verdade no periodo.

A lista de lancamentos responde "o que vence"; esta tela responde a pergunta do
fim do mes: entrou mais do que saiu?
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from ....core import exportar
from ....ui import format as fmt
from ....ui.theme import Space
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import label, tone_label
from ....ui.widgets.table import DIREITA, DataTable
from ..repository import FinanceiroRepository

ESTE_MES, MES_PASSADO, ESTE_ANO = "mes", "passado", "ano"
PERIODOS = (("Este mês", ESTE_MES), ("Mês passado", MES_PASSADO), ("Este ano", ESTE_ANO))


def periodo(chave: str, hoje: date | None = None) -> tuple[str, str]:
    hoje = hoje or date.today()
    if chave == ESTE_ANO:
        return hoje.replace(month=1, day=1).isoformat(), hoje.isoformat()
    primeiro = hoje.replace(day=1)
    if chave == MES_PASSADO:
        ultimo = primeiro - timedelta(days=1)
        return ultimo.replace(day=1).isoformat(), ultimo.isoformat()
    return primeiro.isoformat(), hoje.isoformat()


class DreView(QWidget):
    data_changed = Signal()

    def __init__(self, repository: FinanceiroRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.dre = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.md)

        topo = QHBoxLayout()
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Resultado do período", "title"))
        titulos.addWidget(label("O dinheiro que entrou e saiu, por categoria", "subtitle"))
        topo.addLayout(titulos, 1)
        self.periodo = QComboBox()
        for rotulo, chave in PERIODOS:
            self.periodo.addItem(rotulo, chave)
        self.periodo.currentIndexChanged.connect(self.refresh)
        topo.addWidget(self.periodo)
        self.botao_exportar = Button("Exportar", "file")
        self.botao_exportar.clicked.connect(self.exportar)
        topo.addWidget(self.botao_exportar)
        raiz.addLayout(topo)

        self.tabela = DataTable(["Conta", "Valor", "% da receita"])
        self.tabela.set_empty_message("Nenhum dinheiro andou neste período.")
        raiz.addWidget(self.tabela, 1)

        self.resultado = tone_label("", "accent", "cardTitle")
        raiz.addWidget(self.resultado)

    def linhas(self) -> list[tuple[str, float, bool]]:
        """(nome, valor, e_total), na ordem em que se le um DRE."""
        dre = self.dre
        saida: list[tuple[str, float, bool]] = [("Receitas", dre.total_receitas, True)]
        saida += [(f"   {i.categoria}", i.valor, False) for i in dre.receitas]
        saida.append(("Despesas fixas", -dre.total_fixas, True))
        saida += [(f"   {i.categoria}", -i.valor, False) for i in dre.fixas]
        saida.append(("Despesas variáveis", -dre.total_variaveis, True))
        saida += [(f"   {i.categoria}", -i.valor, False) for i in dre.variaveis]
        saida.append(("Resultado", dre.resultado, True))
        return saida

    def _parte(self, valor: float) -> str:
        receita = self.dre.total_receitas
        return f"{abs(valor) / receita * 100:.1f}%".replace(".", ",") if receita else "-"

    def refresh(self) -> None:
        inicio, fim = periodo(self.periodo.currentData())
        self.dre = self.repository.dre(inicio, fim)
        self.tabela.fill(
            [
                [
                    self.tabela.cell(nome, bold=total),
                    self.tabela.cell(fmt.moeda(valor), DIREITA, bold=total),
                    self.tabela.cell(self._parte(valor), DIREITA),
                ]
                for nome, valor, total in self.linhas()
            ],
            {1: 150, 2: 120},
        )
        tom = "success" if self.dre.resultado >= 0 else "danger"
        self.resultado.setProperty("tone", tom)
        self.resultado.setText(
            f"{'Sobrou' if self.dre.resultado >= 0 else 'Faltou'} "
            f"{fmt.moeda(abs(self.dre.resultado))}  ·  margem de "
            f"{str(self.dre.margem).replace('.', ',')}%"
        )

    def exportar(self) -> None:
        caminho, _ = QFileDialog.getSaveFileName(self, "Exportar DRE", "DRE.csv",
                                                 "Planilha CSV (*.csv)")
        if not caminho:
            return
        exportar.gravar(caminho, exportar.csv_de(
            ["Conta", "Valor", "% da receita"],
            [[nome.strip(), fmt.moeda(valor), self._parte(valor)]
             for nome, valor, _ in self.linhas()],
        ))
