"""Janela do DumTech Clientes."""

from __future__ import annotations

from ....core.contacts import ContactsStore
from ....ui.app_shell import AppWindow
from .clientes_view import ClientesView
from .dashboard_view import DashboardView
from .parceiros_view import ParceirosView


class ClientesWindow(AppWindow):
    """Cadastro de clientes da plataforma.

    Os dados ficam na agenda compartilhada (data/plataforma.db): os outros
    aplicativos usam essa lista para sugerir nomes, sem depender deste app.
    """

    def setup_data(self) -> None:
        self.store: ContactsStore = self.context.contacts or ContactsStore()
        self._store_proprio = self.context.contacts is None

    def build_views(self) -> None:
        self.dashboard_view = self.add_view("Painel", "dashboard", DashboardView(self.store))
        self.clientes_view = self.add_view("Clientes", "users", ClientesView(self.store, mensageiro=self.mensagens,
                                               consultas=self.context.consultas,
                                               contas=self.context.contas))
        self.parceiros_view = self.add_view(
            "Parceiros", "link", ParceirosView(self.store, consultas=self.context.consultas,
                                               contas=self.context.contas))
        for tela in (self.clientes_view, self.parceiros_view):
            tela.data_changed.connect(self.refresh_all)

    def teardown(self) -> None:
        if self._store_proprio:
            self.store.close()
