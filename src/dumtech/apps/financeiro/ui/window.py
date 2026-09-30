"""Janela do DumTech Financeiro.

A ordem comeca pelo Fluxo: quem abre o Financeiro quer saber se vai ter
dinheiro, nao quantos lancamentos existem.
"""

from __future__ import annotations

from ....ui.app_shell import AppWindow
from ..database import open_database
from ..repository import FinanceiroRepository
from .contas_view import ContasView
from .dashboard_view import DashboardView
from .fluxo_view import FluxoView
from .lancamentos_view import LancamentosView


class FinanceiroWindow(AppWindow):
    def setup_data(self) -> None:
        self.database = open_database(self.context.db_path)
        self.repository = FinanceiroRepository(self.database)
        self.clientes = self.context.contacts.nomes() if self.context.contacts else []

    def build_views(self) -> None:
        self.fluxo_view = self.add_view("Fluxo", "chart", FluxoView(self.repository))
        self.dashboard_view = self.add_view(
            "Painel", "dashboard", DashboardView(self.repository)
        )
        self.lancamentos_view = self.add_view(
            "Lancamentos", "money", LancamentosView(self.repository, self.clientes,
                            mensageiro=self.mensagens,
                            contatos=self.context.contacts,
                            empresa=self.empresa)
        )
        self.contas_view = self.add_view("Contas", "home", ContasView(self.repository))

        for tela in (self.lancamentos_view, self.contas_view):
            tela.data_changed.connect(self.refresh_all)

    def teardown(self) -> None:
        self.database.close()
