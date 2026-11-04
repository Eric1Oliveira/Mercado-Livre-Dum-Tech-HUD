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
from .online_view import OnlineView
from .servicos_view import ServicosView


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
                             contatos=self.context.contacts,
                             destinos=self.context.destinos,
                             contas=self.context.contas)
        )
        self.servicos_view = self.add_view(
            "Serviços", "tag", ServicosView(self.repository)
        )
        self.online_view = self.add_view(
            "Online", "link", OnlineView(self.repository, servidor=self.context.servidor,
                                         empresa=self.empresa, paths=self.context.paths)
        )

        self.agenda_view.abrir_ficha.connect(self.abrir_ficha)
        self.agenda_view.novo_em.connect(self.marcar_em)
        # a aba Servicos publica pela Online, que ja conversa com o servidor
        self.servicos_view.pedir_publicacao.connect(self.online_view.publicar)
        self.online_view.publicacao.connect(self.servicos_view.mostrar_publicacao)
        for tela in (self.agenda_view, self.compromissos_view, self.servicos_view, self.online_view):
            tela.data_changed.connect(self.refresh_all)

    def abrir_ficha(self, compromisso_id: int) -> None:
        """A ficha precisa da agenda de clientes, que so a janela conhece."""
        compromisso = self.repository.obter(compromisso_id) if compromisso_id else None
        self._abrir(CompromissoDialog(
            self.repository, compromisso, self.clientes, self.agenda_view,
            contas=self.context.contas,
        ))

    def marcar_em(self, momento: str) -> None:
        """Clicou num horario vago: o formulario ja abre naquele dia e hora."""
        dialogo = CompromissoDialog(
            self.repository, None, self.clientes, self.agenda_view,
            contas=self.context.contas,
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
