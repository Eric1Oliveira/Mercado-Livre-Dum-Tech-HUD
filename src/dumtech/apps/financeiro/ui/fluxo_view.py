"""Fluxo de caixa: a resposta de 'vou ter dinheiro no dia 12?'.

O eixo deste modulo e o tempo, entao a tela principal nao e uma lista nem um
painel de cartoes: e o saldo de hoje, a linha dos proximos 30 dias e, se ela
cruzar o zero, a data em letras grandes.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.theme import Space
from ....ui.widgets.common import Card, FaixaDeNumeros, StatCard, label, repolish, separator, tone_label
from ....ui.widgets.table import DIREITA, DataTable
from ..models import CENTAVO, Projecao
from ..repository import FinanceiroRepository
from ....ui.graficos import GraficoLinha

COLUNAS = ["Dia", "Descrição", "Valor", "Saldo projetado"]

HORIZONTES = (("Próximos 15 dias", 15), ("Próximos 30 dias", 30),
              ("Próximos 60 dias", 60), ("Próximos 90 dias", 90))


class FluxoView(QWidget):
    """Saldo de hoje, projecao e o dia em que o dinheiro acaba."""

    data_changed = Signal()

    def __init__(self, repository: FinanceiroRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.projecao = Projecao()

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        raiz.addLayout(self._cabecalho())
        raiz.addWidget(self._cartoes())
        raiz.addWidget(self._card_grafico())

        colunas = QHBoxLayout()
        colunas.setSpacing(Space.lg)
        colunas.addWidget(self._card_dias(), 4)
        colunas.addWidget(self._card_contas(), 1)
        raiz.addLayout(colunas, 1)

        self.refresh()

    # -------------------------------------------------------------- cabecalho
    def _cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Fluxo de caixa", "title"))
        titulos.addWidget(label("O que entra, o que sai e como fica o saldo", "subtitle"))
        linha.addLayout(titulos)
        linha.addStretch(1)

        self.horizonte = QComboBox()
        for rotulo, dias in HORIZONTES:
            self.horizonte.addItem(rotulo, dias)
        self.horizonte.setCurrentIndex(1)
        self.horizonte.currentIndexChanged.connect(self.refresh)
        linha.addWidget(self.horizonte, 0, Qt.AlignmentFlag.AlignVCenter)
        return linha

    def _cartoes(self) -> FaixaDeNumeros:
        linha = FaixaDeNumeros()
        self.card_hoje = StatCard("Saldo atual", "R$ 0,00", "money", "accent")
        self.card_entradas = StatCard("Entradas previstas", "R$ 0,00", "in", "success")
        self.card_saidas = StatCard("Saídas previstas", "R$ 0,00", "out", "danger")
        self.card_final = StatCard("Saldo futuro", "R$ 0,00", "chart", "accent")
        for cartao in (self.card_hoje, self.card_entradas, self.card_saidas,
                       self.card_final):
            linha.add(cartao)
        return linha

    def _card_grafico(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.setSpacing(Space.sm)

        topo = QHBoxLayout()
        topo.addWidget(label("Saldo projetado", "section"))
        topo.addStretch(1)
        self.recado = tone_label("", "muted", "strong")
        self.recado.setAlignment(DIREITA)
        topo.addWidget(self.recado)
        card.body.addLayout(topo)

        self.grafico = GraficoLinha()
        self.grafico.setMinimumHeight(190)
        self.grafico.formatar = fmt.moeda
        card.body.addWidget(self.grafico, 1)

        self.atrasados = label("", "dim")
        card.body.addWidget(self.atrasados)
        return card

    def _card_dias(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Dia a dia", "section"))
        self.tabela = DataTable(COLUNAS)
        self.tabela.set_empty_message(
            "Nenhum vencimento no período. O saldo segue como está hoje."
        )
        card.body.addWidget(self.tabela, 1)
        return card

    def _card_contas(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Onde o dinheiro está", "section"))
        self._contas = QVBoxLayout()
        self._contas.setSpacing(0)
        card.body.addLayout(self._contas)
        card.body.addStretch(1)
        return card

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        dias = self.horizonte.currentData() or 30
        self.projecao = self.repository.projecao(dias)

        self.card_hoje.set_value(fmt.moeda(self.projecao.saldo_inicial))
        self.card_entradas.set_value(fmt.moeda(self.projecao.entradas))
        self.card_saidas.set_value(fmt.moeda(self.projecao.saidas))
        negativo = self.projecao.saldo_final < -CENTAVO
        self.card_final.set_tone("danger" if negativo else "success")
        self.card_final.set_value(
            fmt.moeda(self.projecao.saldo_final), f"daqui a {dias} dias"
        )

        self._desenhar_grafico()
        self._dizer_o_recado()
        self._preencher_dias()
        self._preencher_contas()

    def _desenhar_grafico(self) -> None:
        """O saldo dia a dia, com o dia do aperto marcado na linha."""
        dias = self.projecao.dias
        vermelho = self.projecao.dia_no_vermelho
        marca = dias.index(vermelho) if vermelho is not None else None
        self.grafico.set_serie(
            [dia.saldo for dia in dias],
            [fmt.data(dia.data)[:5] for dia in dias],
            marca=marca,
            marca_texto=(f"{fmt.data(vermelho.data)[:5]}  {fmt.moeda(vermelho.saldo)}"
                         if vermelho is not None else ""),
        )

    def _dizer_o_recado(self) -> None:
        """A frase mais importante do modulo inteiro."""
        vermelho = self.projecao.dia_no_vermelho
        if vermelho is None:
            self.recado.setText("O saldo não fica negativo no período.")
            self.recado.setProperty("tone", "success")
        else:
            self.recado.setText(
                f"Saldo negativo em {fmt.data(vermelho.data)}  "
                f"({fmt.moeda(vermelho.saldo)})"
            )
            self.recado.setProperty("tone", "danger")
        repolish(self.recado)

        atrasado = self.projecao.atrasado_receber + self.projecao.atrasado_pagar
        if atrasado > CENTAVO:
            self.atrasados.setText(
                f"Vencidos entram no dia de hoje: "
                f"{fmt.moeda(self.projecao.atrasado_receber)} a receber e "
                f"{fmt.moeda(self.projecao.atrasado_pagar)} a pagar. "
                "Receber atrasado é uma aposta - confira antes de contar com ele."
            )
        else:
            self.atrasados.setText("")

    def _preencher_dias(self) -> None:
        linhas = []
        for dia in self.projecao.dias:
            if not dia.tem_movimento:
                continue
            linhas.append([
                self.tabela.cell(self._rotulo_dia(dia), bold=True),
                self.tabela.cell(self._resumo_dia(dia)),
                self._celula_valor(dia),
                self.tabela.cell(
                    fmt.moeda(dia.saldo), DIREITA,
                    "danger" if dia.saldo < -CENTAVO else "accent", bold=True,
                ),
            ])
        self.tabela.fill(linhas, {0: 110, 2: 130, 3: 140})

    def _celula_valor(self, dia):
        """Uma coluna so: o quanto o dia mexe no saldo, com sinal e cor."""
        movimento = dia.movimento
        if abs(movimento) <= CENTAVO:
            return self.tabela.cell(fmt.moeda(0), DIREITA, "text_muted")
        sinal, tom = ("+", "success") if movimento > 0 else ("-", "danger")
        return self.tabela.cell(f"{sinal} {fmt.moeda(abs(movimento))}", DIREITA, tom, True)

    @staticmethod
    def _rotulo_dia(dia) -> str:
        texto = fmt.data(dia.data)[:5]
        return f"{texto}  (hoje)" if dia.data == date.today().isoformat() else texto

    @staticmethod
    def _resumo_dia(dia) -> str:
        """Quem sao os lancamentos do dia, sem virar uma parede de texto."""
        nomes = [item.descricao_completa for item in dia.lancamentos]
        if len(nomes) <= 2:
            return "  ·  ".join(nomes)
        return f"{nomes[0]}  ·  {nomes[1]}  e mais {len(nomes) - 2}"

    def _preencher_contas(self) -> None:
        while self._contas.count():
            item = self._contas.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        contas = self.repository.listar_contas()
        if not contas:
            self._contas.addWidget(
                label("Cadastre uma conta na tela Contas para ver o saldo aqui.", "muted")
            )
            return

        for conta in contas:
            self._contas.addWidget(self._linha_conta(conta.nome, conta.saldo, conta.tipo_label))
        self._contas.addWidget(separator())
        self._contas.addWidget(
            self._linha_conta("Total", self.projecao.saldo_inicial, "", forte=True)
        )

    @staticmethod
    def _linha_conta(nome: str, saldo: float, detalhe: str, forte: bool = False) -> QWidget:
        linha = QWidget()
        layout = QHBoxLayout(linha)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(Space.sm)

        texto = QVBoxLayout()
        texto.setSpacing(0)
        texto.addWidget(label(nome, "strong" if forte else "body"))
        if detalhe:
            texto.addWidget(label(detalhe, "dim"))
        layout.addLayout(texto, 1)

        tom = "danger" if saldo < -CENTAVO else ("accent" if forte else "text")
        valor = tone_label(fmt.moeda(saldo), tom, "cardTitle" if forte else "strong")
        valor.setAlignment(DIREITA)
        layout.addWidget(valor)
        return linha
