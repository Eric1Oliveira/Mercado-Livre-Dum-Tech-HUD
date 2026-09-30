"""Janela do DumTech Orcamentos.

Duas telas, e nao quatro: o Funil ja e o painel deste modulo. Criar um "Painel"
ao lado dele seria a mesma tela com dois nomes.
"""

from __future__ import annotations

from ....ui.app_shell import AppWindow
from ..database import open_database
from ..repository import OrcamentosRepository
from .funil_view import FunilView
from .orcamentos_view import OrcamentosView


class OrcamentosWindow(AppWindow):
    def setup_data(self) -> None:
        self.database = open_database(self.context.db_path)
        self.repository = OrcamentosRepository(self.database)
        self.clientes = self.context.contacts.nomes() if self.context.contacts else []

    def build_views(self) -> None:
        self.funil_view = self.add_view("Funil", "chart", FunilView(self.repository))
        self.orcamentos_view = self.add_view(
            "Orcamentos", "file", OrcamentosView(self.repository, self.clientes,
                                                 empresa=self.empresa,
                                                 paths=self.context.paths,
                                                 mensageiro=self.mensagens,
                                                 contatos=self.context.contacts,
                                                 destinos=self.context.destinos,
                                                 catalogo=self.context.catalog)
        )
        self.orcamentos_view.data_changed.connect(self.refresh_all)

    def teardown(self) -> None:
        self.database.close()
