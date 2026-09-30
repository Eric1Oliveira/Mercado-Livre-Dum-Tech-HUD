"""Janela do DumTech Estoque (aberta pelo Hub)."""

from __future__ import annotations

from ....ui.app_shell import AppWindow
from ..database import open_database
from ..repository import EstoqueRepository
from .contagem_view import ContagemView
from .dashboard_view import DashboardView
from .entradas_view import EntradasView
from .movimentacoes_view import MovimentacoesView
from .produtos_view import ProdutosView


class EstoqueWindow(AppWindow):
    """Painel, produtos, entradas, movimentacoes e contagem."""

    def setup_data(self) -> None:
        self.database = open_database(self.context.db_path)
        self.repository = EstoqueRepository(self.database)

    def build_views(self) -> None:
        self.dashboard_view = self.add_view("Painel", "dashboard", DashboardView(self.repository))
        self.produtos_view = self.add_view("Produtos", "box", ProdutosView(self.repository))
        self.entradas_view = self.add_view(
            "Entradas", "in",
            # a ponte do Financeiro chega aqui para a nota de compra virar
            # conta a pagar sem ninguem digitar de novo
            EntradasView(self.repository, contas=self.context.contas),
        )
        self.movimentacoes_view = self.add_view(
            "Movimentacoes", "swap", MovimentacoesView(self.repository)
        )
        self.contagem_view = self.add_view("Contagem", "list", ContagemView(self.repository))

        for tela in (
            self.produtos_view,
            self.entradas_view,
            self.movimentacoes_view,
            self.contagem_view,
        ):
            tela.data_changed.connect(self.refresh_all)

    def teardown(self) -> None:
        self.database.close()
