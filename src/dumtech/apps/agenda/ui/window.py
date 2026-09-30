"""Janela do DumTech Agenda.

Duas telas: a grade e a lista. A grade ja e o painel deste modulo - um cartao
dizendo "3 hoje" ao lado de uma tela que mostra os tres seria repeticao.
"""

from __future__ import annotations

from PySide6.QtCore import QDateTime, Qt

from ....ui.app_shell import AppWindow
from ..database import open_database
from ..repository import AgendaRepository
from .agenda_view import AgendaView
from .compromisso_dialog import CompromissoDialog
from .compromissos_view import CompromissosView


class AgendaWindow(AppWindow):
    def setup_data(self) -> None:
        self.database = open_database(self.context.db_path)
        self.repository = AgendaRepository(self.database)
        self.clientes = self.context.contacts.nomes() if self.context.contacts else []

    def build_views(self) -> None:
        self.agenda_view = self.add_view(
            "Agenda", "calendar", AgendaView(self.repository, prefs=self.prefs)
        )
        self.compromissos_view = self.add_view(
            "Compromissos", "list", CompromissosView(self.repository, self.clientes,
                             mensageiro=self.mensagens,
                             contatos=self.context.contacts)
        )

        self.agenda_view.abrir_ficha.connect(self.abrir_ficha)
        self.agenda_view.novo_em.connect(self.marcar_em)
        for tela in (self.agenda_view, self.compromissos_view):
            tela.data_changed.connect(self.refresh_all)

    def abrir_ficha(self, compromisso_id: int) -> None:
        """A ficha precisa da agenda de clientes, que so a janela conhece."""
        compromisso = self.repository.obter(compromisso_id) if compromisso_id else None
        self._abrir(CompromissoDialog(
            self.repository, compromisso, self.clientes, self.agenda_view
        ))

    def marcar_em(self, momento: str) -> None:
        """Clicou num horario vago: o formulario ja abre naquele dia e hora."""
        dialogo = CompromissoDialog(
            self.repository, None, self.clientes, self.agenda_view
        )
        lido = QDateTime.fromString(momento, Qt.DateFormat.ISODate)
        if lido.isValid():
            dialogo.inicio.setDateTime(lido)
        self._abrir(dialogo)

    def _abrir(self, dialogo: CompromissoDialog) -> None:
        if dialogo.exec():
            self.refresh_all()

    def teardown(self) -> None:
        self.database.close()
