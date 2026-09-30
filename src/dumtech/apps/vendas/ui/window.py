"""Janela do DumTech Vendas.

A ordem das telas comeca pelo Balcao, e nao pelo Painel como nos outros
modulos: quem abre o Vendas abre para vender.
"""

from __future__ import annotations

from ....ui.app_shell import AppWindow
from ..database import open_database
from ..repository import VendasRepository
from .balcao_view import BalcaoView
from .caixa_view import CaixaView
from .dashboard_view import DashboardView
from .vendas_view import VendasView


class VendasWindow(AppWindow):
    def setup_data(self) -> None:
        self.database = open_database(self.context.db_path)
        # o catalogo so chega quando o cliente tem o DumTech Estoque liberado
        self.repository = VendasRepository(self.database, catalogo=self.context.catalog)
        self.clientes = self.context.contacts.nomes() if self.context.contacts else []

    def build_views(self) -> None:
        self.balcao_view = self.add_view(
            "Balcao", "cart", BalcaoView(self.repository, self.clientes,
                       contas=self.context.contas, empresa=self.empresa)
        )
        self.dashboard_view = self.add_view("Painel", "dashboard", DashboardView(self.repository))
        self.vendas_view = self.add_view(
            "Vendas", "list", VendasView(self.repository, self.clientes,
                                         empresa=self.empresa,
                                         mensageiro=self.mensagens,
                                         contatos=self.context.contacts,
                                         contas=self.context.contas)
        )
        self.caixa_view = self.add_view(
            "Caixa", "money", CaixaView(self.repository, empresa=self.empresa)
        )

        for tela in (self.balcao_view, self.vendas_view, self.caixa_view):
            tela.data_changed.connect(self.refresh_all)

    def teardown(self) -> None:
        self.database.close()
