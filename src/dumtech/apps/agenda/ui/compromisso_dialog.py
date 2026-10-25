"""Formulario de compromisso, com aviso de conflito e repeticao."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QWidget

from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.common import repolish
from ....ui.widgets.form import FormDialog
from ..models import (
    BLOQUEIO,
    DURACOES,
    REPETICOES,
    STATUS_OPCOES,
    TIPO_OPCOES,
    Compromisso,
)
from ..repository import AgendaRepository

SEM_REPETICAO = ""


class CompromissoDialog(FormDialog):
    """O conflito avisa e pede confirmacao - nao trava."""

    def __init__(
        self,
        repository: AgendaRepository,
        compromisso: Compromisso | None = None,
        clientes: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self.repository = repository
        self.compromisso = compromisso or Compromisso()
        self.editando = compromisso is not None
        self.criados: list[Compromisso] = []
        #: o usuario ja viu o aviso de conflito e clicou de novo
        self._conflito_aceito = False
        super().__init__(
            "Editar compromisso" if self.editando else "Novo compromisso",
            "Data, horário e com quem é o atendimento",
            parent,
            largura=620,
        )

        self.titulo = form.sugestao(
            self.compromisso.titulo, "Ex.: Visita técnica",
            self.repository.titulos(),
        )
        self.add_row("Título", self.titulo)

        self.tipo = form.escolha(TIPO_OPCOES, self.compromisso.tipo)
        self.tipo.currentIndexChanged.connect(self._tipo_mudou)
        self.add_row("Tipo", self.tipo)

        self.cliente = form.sugestao(
            self.compromisso.cliente, "Cliente (opcional)", clientes or []
        )
        self.add_row("Cliente", self.cliente)

        self.inicio = form.data_hora(self.compromisso.inicio)
        self.inicio.dateTimeChanged.connect(self._conferir_conflito)
        self.duracao = QComboBox()
        for minutos, rotulo in DURACOES:
            self.duracao.addItem(rotulo, minutos)
        indice = self.duracao.findData(self.compromisso.duracao_min or 60)
        if indice < 0:
            self.duracao.addItem(f"{self.compromisso.duracao_min} min",
                                 self.compromisso.duracao_min)
            indice = self.duracao.count() - 1
        self.duracao.setCurrentIndex(indice)
        self.duracao.currentIndexChanged.connect(self._conferir_conflito)
        self.add_row("Início", form.linha(self.inicio, "Duração", self.duracao))

        self.local = form.sugestao(
            self.compromisso.local, "Ex.: Loja, casa do cliente, online",
            repository.locais(),
        )
        self.add_row("Local", self.local)

        self.status = form.escolha(STATUS_OPCOES, self.compromisso.status)
        self.add_row("Situação", self.status)

        # repetir so no cadastro: mexer nisso depois seria refazer a serie
        if not self.editando:
            self.repeticao = QComboBox()
            self.repeticao.addItem("Não se repete", SEM_REPETICAO)
            for chave, rotulo in REPETICOES:
                self.repeticao.addItem(rotulo, chave)
            self.repeticao.currentIndexChanged.connect(self._repeticao_mudou)
            self.vezes = form.inteiro(4, minimo=2, maximo=60)
            self.vezes.setSuffix(" vezes")
            self.add_row("Repetir", form.linha(self.repeticao, self.vezes))

        self.observacoes = form.area(
            self.compromisso.observacoes, "Anotações do atendimento", 60
        )
        self.add_row("Observações", self.observacoes)

        self.add_note("")
        self._nota = self.extras.itemAt(self.extras.count() - 1).widget()
        self._nota.setWordWrap(True)

        if not self.editando:
            self._repeticao_mudou()
        self._tipo_mudou()
        self._conferir_conflito()
        self.titulo.setFocus()

    # -------------------------------------------------------------------- tela
    @property
    def em_serie(self) -> bool:
        return not self.editando and bool(self.repeticao.currentData())

    def _tipo_mudou(self) -> None:
        """Bloqueio nao tem cliente: e almoco, folga, feriado."""
        bloqueio = self.tipo.currentData() == BLOQUEIO
        self.cliente.setEnabled(not bloqueio)
        if bloqueio:
            self.cliente.clear()
            if not self.titulo.text().strip():
                self.titulo.setPlaceholderText("Ex.: Almoço, folga, feriado")
        self._conferir_conflito()

    def _repeticao_mudou(self) -> None:
        self.vezes.setVisible(self.em_serie)
        self._conferir_conflito()

    def _montar(self) -> Compromisso:
        provisorio = Compromisso(
            id=self.compromisso.id,
            titulo=self.titulo.text(),
            inicio=form.iso_da_data_hora(self.inicio),
            duracao_min=self.duracao.currentData() or 60,
            status=self.status.currentData(),
            tipo=self.tipo.currentData(),
        )
        return provisorio

    def _conferir_conflito(self) -> None:
        """Mostra o choque antes de salvar - e pede um segundo clique."""
        self._conflito_aceito = False
        conflitos = self.repository.conflitos(self._montar())
        if not conflitos:
            self._nota.setText(
                f"{fmt.contagem(self.vezes.value(), 'data')} nesta série."
                if self.em_serie else "Horário livre."
            )
            self._nota.setProperty("tone", "muted")
        else:
            nomes = ", ".join(
                f"{c.titulo} ({c.horario})" for c in conflitos[:3]
            )
            self._nota.setText(
                f"Já existe algo neste horário: {nomes}. "
                "Salvar de novo confirma a marcação em cima."
            )
            self._nota.setProperty("tone", "warning")
        repolish(self._nota)
        self._conflitos = conflitos

    # ------------------------------------------------------------------ gravar
    def salvar(self):
        # o primeiro clique so avisa; o segundo confirma
        if getattr(self, "_conflitos", None) and not self._conflito_aceito:
            self._conflito_aceito = True
            self._nota.setText(
                f"{self._nota.text()}  Clique em Salvar de novo para confirmar."
            )
            return False

        self.compromisso.titulo = self.titulo.text()
        self.compromisso.cliente = self.cliente.text()
        self.compromisso.inicio = form.iso_da_data_hora(self.inicio)
        self.compromisso.duracao_min = self.duracao.currentData() or 60
        self.compromisso.local = self.local.text()
        self.compromisso.status = self.status.currentData()
        self.compromisso.tipo = self.tipo.currentData()
        self.compromisso.observacoes = self.observacoes.toPlainText()

        if self.em_serie:
            self.criados = self.repository.repetir(
                self.compromisso, self.vezes.value(), self.repeticao.currentData()
            )
            return None
        self.repository.salvar(self.compromisso)
        return None
