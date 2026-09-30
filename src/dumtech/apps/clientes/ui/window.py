"""Janela do DumTech Clientes."""

from __future__ import annotations

from ....core.contacts import ContactsStore
from ....ui.app_shell import AppWindow
from .clientes_view import ClientesView
from .dashboard_view import DashboardView


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
        self.clientes_view = self.add_view("Clientes", "users", ClientesView(self.store, mensageiro=self.mensagens))
        self.clientes_view.data_changed.connect(self.refresh_all)

    def teardown(self) -> None:
        if self._store_proprio:
            self.store.close()
