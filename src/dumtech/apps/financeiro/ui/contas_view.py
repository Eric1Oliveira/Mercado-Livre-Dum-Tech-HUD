"""Contas: onde o dinheiro esta, e como ele anda de uma para outra."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.theme import Space
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, IconBadge, label, repolish, tone_label
from ....ui.widgets.table import DIREITA, DataTable
from ..models import CENTAVO, Conta, FinanceiroError
from ..repository import FinanceiroRepository
from .dialogos import ContaDialog, TransferenciaDialog


class ContasView(QWidget):
    """Cadastro de contas, saldo de cada uma e transferencias."""

    data_changed = Signal()

    def __init__(self, repository: FinanceiroRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.contas: list[Conta] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        raiz.addLayout(self._cabecalho())
        raiz.addWidget(self._card_total())

        self.tabela = DataTable(["Conta", "Tipo", "Saldo inicial", "Saldo atual"])
        self.tabela.set_empty_message(
            "Cadastre a conta do banco e o caixa da loja para acompanhar o saldo."
        )
        self.tabela.itemSelectionChanged.connect(self._atualizar_acoes)
        self.tabela.doubleClicked.connect(self._editar)
        raiz.addWidget(self.tabela, 1)

        raiz.addLayout(self._acoes())
        raiz.addWidget(self._card_transferencias(), 1)

        self.refresh()

    # -------------------------------------------------------------- cabecalho
    def _cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Contas bancárias", "title"))
        self.subtitulo = label("", "subtitle")
        titulos.addWidget(self.subtitulo)
        linha.addLayout(titulos)
        linha.addStretch(1)

        self.mostrar_inativas = QCheckBox("Mostrar inativas")
        self.mostrar_inativas.stateChanged.connect(self.refresh)
        linha.addWidget(self.mostrar_inativas, 0, Qt.AlignmentFlag.AlignVCenter)

        self.botao_transferir = Button("Transferência", "swap")
        self.botao_transferir.clicked.connect(self._transferir)
        linha.addWidget(self.botao_transferir)

        self.botao_nova = Button("Nova conta", "plus", "primary")
        self.botao_nova.setMinimumHeight(38)
        self.botao_nova.clicked.connect(self._nova)
        linha.addWidget(self.botao_nova)
        return linha

    def _card_total(self) -> Card:
        card = Card(padding=Space.lg)
        linha = QHBoxLayout()
        linha.setSpacing(Space.md)
        linha.addWidget(IconBadge("money", "accent", size=44, radius=13))

        texto = QVBoxLayout()
        texto.setSpacing(0)
        texto.addWidget(label("Dinheiro disponível", "muted"))
        texto.addWidget(label("Somando todas as contas ativas", "dim"))
        linha.addLayout(texto, 1)

        self.total = tone_label(fmt.moeda(0), "accent", "metric")
        self.total.setAlignment(DIREITA)
        linha.addWidget(self.total)
        card.body.addLayout(linha)
        return card

    def _acoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        linha.addWidget(self.aviso, 1)

        self.botao_editar = Button("Editar", "edit")
        self.botao_editar.clicked.connect(self._editar)
        linha.addWidget(self.botao_editar)

        self.botao_ativar = Button("Inativar", "close")
        self.botao_ativar.clicked.connect(self._alternar_ativa)
        linha.addWidget(self.botao_ativar)

        self.botao_excluir = Button("Excluir", "trash", "danger")
        self.botao_excluir.clicked.connect(self._excluir)
        linha.addWidget(self.botao_excluir)
        return linha

    def _card_transferencias(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Transferências recentes", "section"))
        self.tabela_transferencias = DataTable(["Data", "De", "Para", "Motivo", "Valor"])
        self.tabela_transferencias.set_empty_message(
            "Nenhuma transferência registrada."
        )
        card.body.addWidget(self.tabela_transferencias)
        return card

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        self.contas = self.repository.listar_contas(
            incluir_inativas=self.mostrar_inativas.isChecked()
        )
        self.tabela.fill(
            [
                [
                    self.tabela.cell(
                        c.nome if c.ativo else f"{c.nome}  (inativa)", bold=True, data=c.id
                    ),
                    self.tabela.cell(c.tipo_label),
                    self.tabela.cell(fmt.moeda(c.saldo_inicial), DIREITA),
                    self.tabela.cell(
                        fmt.moeda(c.saldo), DIREITA,
                        "danger" if c.saldo < -CENTAVO else "accent", bold=True,
                    ),
                ]
                for c in self.contas
            ],
            {1: 120, 2: 160, 3: 170},
        )

        total = self.repository.saldo_total()
        self.total.setText(fmt.moeda(total))
        self.total.setProperty("tone", "danger" if total < -CENTAVO else "accent")
        repolish(self.total)

        ativas = sum(1 for c in self.contas if c.ativo)
        self.subtitulo.setText(
            "Nenhuma conta cadastrada" if not ativas
            else f"{ativas} conta ativa" if ativas == 1
            else f"{ativas} contas ativas"
        )
        self._preencher_transferencias()
        self._atualizar_acoes()

    def _preencher_transferencias(self) -> None:
        tabela = self.tabela_transferencias
        tabela.fill(
            [
                [
                    tabela.cell(fmt.data(t.data)),
                    tabela.cell(t.origem_nome or "-"),
                    tabela.cell(t.destino_nome or "-"),
                    tabela.cell(t.observacao or "-"),
                    tabela.cell(fmt.moeda(t.valor), DIREITA, bold=True),
                ]
                for t in self.repository.listar_transferencias(limite=20)
            ],
            {0: 120, 4: 140},
        )

    def selecionada(self) -> Conta | None:
        linha = self.tabela.currentRow()
        return self.contas[linha] if 0 <= linha < len(self.contas) else None

    def _atualizar_acoes(self) -> None:
        conta = self.selecionada()
        tem = conta is not None
        self.botao_editar.setEnabled(tem)
        self.botao_ativar.setEnabled(tem)
        self.botao_excluir.setEnabled(tem)
        self.botao_transferir.setEnabled(len(self.repository.listar_contas()) >= 2)
        self.botao_ativar.setText("  Reativar" if tem and not conta.ativo else "  Inativar")

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------- acoes
    def _abrir(self, dialogo) -> None:
        if dialogo.exec():
            self.refresh()
            self.data_changed.emit()

    def _nova(self) -> None:
        self._abrir(ContaDialog(self.repository, None, self))

    def _editar(self) -> None:
        conta = self.selecionada()
        if conta is not None:
            self._abrir(ContaDialog(self.repository, conta, self))

    def _alternar_ativa(self) -> None:
        conta = self.selecionada()
        if conta is None:
            return
        if conta.ativo:
            self.repository.inativar_conta(conta.id)
            recado = f"'{conta.nome}' saiu da lista. O histórico continua guardado."
        else:
            self.repository.reativar_conta(conta.id)
            recado = f"'{conta.nome}' voltou para a lista."
        self.refresh()
        self._dizer(recado)
        self.data_changed.emit()

    def _excluir(self) -> None:
        conta = self.selecionada()
        if conta is None:
            return
        try:
            self.repository.excluir_conta(conta.id)
        except FinanceiroError as erro:
            self.refresh()
            self._dizer(str(erro), "danger")
            return
        self.refresh()
        self._dizer(f"Conta '{conta.nome}' apagada.")
        self.data_changed.emit()

    def _transferir(self) -> None:
        try:
            dialogo = TransferenciaDialog(self.repository, self)
        except FinanceiroError as erro:
            self._dizer(str(erro), "danger")
            return
        self._abrir(dialogo)
