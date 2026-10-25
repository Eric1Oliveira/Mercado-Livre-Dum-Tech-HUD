"""Janela do DumTech Ordem de Servico.

A ordem comeca pelo Quadro: quem abre o programa de manha quer ver o que esta
em andamento hoje, nao quantas ordens existem no banco.
"""

from __future__ import annotations

from ....ui.app_shell import AppWindow
from ..database import open_database
from ..repository import OrdensRepository
from .bancada_view import BancadaView
from .dashboard_view import DashboardView
from .ordem_dialog import OrdemDialog
from .ordens_view import OrdensView


class OrdensWindow(AppWindow):
    def setup_data(self) -> None:
        self.database = open_database(self.context.db_path)
        # com o Estoque liberado, a peca usada no servico sai do saldo
        # quando a ordem e entregue
        self.repository = OrdensRepository(self.database,
                                           catalogo=self.context.catalog)
        self.clientes = self.context.contacts.nomes() if self.context.contacts else []

    def build_views(self) -> None:
        self.bancada_view = self.add_view(
            "Quadro", "wrench",
            BancadaView(self.repository, empresa=self.empresa, contas=self.context.contas)
        )
        self.dashboard_view = self.add_view(
            "Painel", "dashboard", DashboardView(self.repository)
        )
        self.ordens_view = self.add_view(
            "Ordens de Serviço", "list", OrdensView(self.repository, self.clientes,
                                         empresa=self.empresa,
                                         paths=self.context.paths,
                                         mensageiro=self.mensagens,
                                         contatos=self.context.contacts,
                                         contas=self.context.contas,
                                         catalogo=self.context.catalog)
        )

        self.bancada_view.abrir_ficha.connect(self.abrir_ficha)
        for tela in (self.bancada_view, self.ordens_view):
            tela.data_changed.connect(self.refresh_all)

    def abrir_ficha(self, ordem_id: int) -> None:
        """A ficha precisa da agenda de clientes, que so a janela conhece."""
        ordem = self.repository.obter(ordem_id) if ordem_id else None
        dialogo = OrdemDialog(self.repository, ordem, self.clientes,
                              self.bancada_view, catalogo=self.context.catalog)
        if dialogo.exec():
            self.refresh_all()

    def teardown(self) -> None:
        self.database.close()
