"""Lista de compromissos: procurar, confirmar, concluir e cancelar."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.widgets.buttons import Button
from ....ui.widgets.crud_view import CrudView
from ....ui.widgets.mensagem import mandar
from ..models import (
    CANCELADO,
    CONCLUIDO,
    CONFIRMADO,
    STATUS_LABEL,
    TIPO_LABEL,
    Compromisso,
)
from ..repository import (
    PERIODO_ATRASADOS,
    PERIODO_HOJE,
    PERIODO_MES,
    PERIODO_SEMANA,
    AgendaRepository,
)
from .compromisso_dialog import CompromissoDialog

PERIODOS = (
    ("Todos os periodos", ""),
    ("Hoje", PERIODO_HOJE),
    ("Esta semana", PERIODO_SEMANA),
    ("Este mes", PERIODO_MES),
    ("Sem fechar", PERIODO_ATRASADOS),
)


class CompromissosView(CrudView):
    titulo = "Compromissos"
    nome_registro = "compromisso"
    nome_plural = "compromissos"
    rotulo_novo = "Novo compromisso"
    dica_pesquisa = "Pesquisar por titulo, cliente, local ou anotacao..."
    colunas = ["Quando", "Horario", "Titulo", "Cliente", "Tipo", "Local", "Situacao"]
    larguras = {0: 130, 1: 140, 4: 130, 6: 150}

    def __init__(
        self,
        repository: AgendaRepository,
        clientes: list[str] | None = None,
        parent: QWidget | None = None,
        mensageiro=None,
        contatos=None,
    ) -> None:
        self.repository = repository
        self.clientes = clientes or []
        self.mensageiro = mensageiro
        self.contatos = contatos
        super().__init__(parent)

    def build_filters(self, layout: QHBoxLayout) -> None:
        self.filtro_periodo = QComboBox()
        for rotulo, chave in PERIODOS:
            self.filtro_periodo.addItem(rotulo, chave)
        # a semana e o horizonte de quem trabalha com agenda
        self.filtro_periodo.setCurrentIndex(2)
        self.filtro_periodo.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_periodo, 1)

        self.filtro_tipo = QComboBox()
        self.filtro_tipo.addItem("Todos os tipos", "")
        for chave, rotulo in TIPO_LABEL.items():
            self.filtro_tipo.addItem(rotulo, chave)
        self.filtro_tipo.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_tipo, 1)

        self.filtro_status = QComboBox()
        self.filtro_status.addItem("Todas as situacoes", "")
        for chave, rotulo in STATUS_LABEL.items():
            self.filtro_status.addItem(rotulo, chave)
        self.filtro_status.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_status, 1)

    def build_actions(self, layout: QHBoxLayout) -> None:
        self.botao_confirmar = Button("Confirmar", "check")
        self.botao_confirmar.clicked.connect(
            lambda: self._status(CONFIRMADO, "confirmado")
        )
        layout.insertWidget(1, self.botao_confirmar)

        self.botao_concluir = Button("Concluir", "check", "success")
        self.botao_concluir.clicked.connect(lambda: self._status(CONCLUIDO, "concluido"))
        layout.insertWidget(2, self.botao_concluir)

        self.botao_whatsapp = Button("WhatsApp", "chat")
        self.botao_whatsapp.setToolTip("Confirma o horario com o cliente")
        self.botao_whatsapp.clicked.connect(self._whatsapp)
        layout.insertWidget(3, self.botao_whatsapp)

        self.botao_cancelar = Button("Cancelar", "close", "danger")
        self.botao_cancelar.clicked.connect(lambda: self._status(CANCELADO, "cancelado"))
        layout.insertWidget(4, self.botao_cancelar)

    # ------------------------------------------------------------------- dados
    def carregar(self) -> list[Compromisso]:
        return self.repository.listar(
            busca=self.busca.text(),
            status=self.filtro_status.currentData() or "",
            tipo=self.filtro_tipo.currentData() or "",
            periodo=self.filtro_periodo.currentData() or "",
        )

    def montar_linha(self, compromisso: Compromisso) -> list:
        return [
            self.tabela.cell(
                fmt.data(compromisso.inicio), data=compromisso.id,
                tone="danger" if compromisso.atrasado else "",
            ),
            self.tabela.cell(compromisso.horario),
            self.tabela.cell(compromisso.titulo, bold=True),
            self.tabela.cell(compromisso.cliente or "-"),
            self.tabela.cell(compromisso.tipo_label, tone=compromisso.tom),
            self.tabela.cell(compromisso.local or "-"),
            self.tabela.cell(self._situacao(compromisso), tone=self._tom(compromisso)),
        ]

    @staticmethod
    def _situacao(compromisso: Compromisso) -> str:
        """A situacao sozinha nao diz que a hora passou e ninguem fechou."""
        if compromisso.atrasado:
            return f"{compromisso.status_label} · sem fechar"
        return compromisso.status_label

    @staticmethod
    def _tom(compromisso: Compromisso) -> str:
        return "danger" if compromisso.atrasado else compromisso.status_tom

    def _atualizar_acoes(self) -> None:
        super()._atualizar_acoes()
        compromisso = self.registro_selecionado()
        aberto = compromisso is not None and compromisso.em_aberto
        self.botao_confirmar.setEnabled(aberto and compromisso.status != CONFIRMADO)
        self.botao_concluir.setEnabled(aberto)
        self.botao_whatsapp.setEnabled(
            compromisso is not None and bool(compromisso.cliente)
        )
        self.botao_cancelar.setEnabled(
            compromisso is not None and compromisso.status != CANCELADO
        )

    # ------------------------------------------------------------------- acoes
    def _whatsapp(self) -> None:
        compromisso = self.registro_selecionado()
        if compromisso is None:
            return
        mandar(self, self.mensageiro, "compromisso", {
            "cliente": compromisso.cliente,
            "titulo": compromisso.titulo,
            "data": fmt.data(compromisso.inicio),
            "hora": compromisso.horario,
        }, contatos=self.contatos)

    def _status(self, status: str, recado: str) -> None:
        compromisso = self.registro_selecionado()
        if compromisso is None:
            return
        self.repository.definir_status(compromisso.id, status)
        self.refresh()
        self.mostrar_aviso(f"'{compromisso.titulo}' {recado}.", "success")
        self.data_changed.emit()

    def abrir_dialogo(self, compromisso: Compromisso | None):
        return CompromissoDialog(self.repository, compromisso, self.clientes, self)

    def excluir(self, compromisso: Compromisso) -> None:
        self.repository.excluir(compromisso.id)

    def descricao(self, compromisso: Compromisso) -> str:
        return f"{compromisso.titulo} ({fmt.data(compromisso.inicio)})"
