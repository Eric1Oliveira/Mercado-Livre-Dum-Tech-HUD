"""Janela do DumTech Vendas.

A ordem das telas comeca pelo Balcao, e nao pelo Painel como nos outros
modulos: quem abre o Vendas abre para vender.
"""

from __future__ import annotations

import logging

from ....ui.app_shell import AppWindow
from ....ui.widgets.recorrencias import RecorrenciasDialog, Textos
from .. import financeiro, recorrencias
from ..database import open_database
from ..repository import VendasRepository
from .balcao_view import BalcaoView
from .caixa_view import CaixaView
from .dashboard_view import DashboardView
from .resultado_view import ResultadoView
from .vendas_view import VendasView

logger = logging.getLogger(__name__)

TEXTOS_RECORRENCIA = Textos(
    documento="venda", documentos="vendas",
    exemplo="Ex.: Mensalidade do plano, fornecimento do mês",
    antecedencia=recorrencias.ANTECEDENCIA,
    onde="uma venda pendente",
)


class VendasWindow(AppWindow):
    def setup_data(self) -> None:
        self.database = open_database(self.context.db_path)
        # o catalogo so chega quando o cliente tem o DumTech Estoque liberado
        self.repository = VendasRepository(self.database, catalogo=self.context.catalog)
        self.clientes = self.context.contacts.nomes() if self.context.contacts else []
        self.recorrencias = recorrencias.repositorio(self.database)
        # a mensalidade que venceu com o programa fechado entra ao abrir
        self.gerar_recorrencias()
        financeiro.conciliar(self.repository, self.context.contas)

    def gerar_recorrencias(self) -> list[str]:
        """Cria as vendas devidas dos contratos. Nunca impede o Vendas de abrir."""
        try:
            return recorrencias.gerar(self.repository, self.context.contas)
        except Exception:  # noqa: BLE001 - recorrencia com defeito nao trava o balcao
            logger.exception("Falha ao gerar as vendas recorrentes")
            return []

    def refresh_all(self) -> None:
        # o Hub aberto de um dia para o outro tambem precisa gerar a vez de hoje
        self.gerar_recorrencias()
        super().refresh_all()

    def build_views(self) -> None:
        self.balcao_view = self.add_view(
            "Balcão", "cart", BalcaoView(self.repository, self.clientes,
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
            "Caixa", "money", CaixaView(self.repository, empresa=self.empresa,
                                        contas=self.context.contas)
        )

        self.resultado_view = self.add_view(
            "Resultado", "chart", ResultadoView(self.repository)
        )

        self.vendas_view.botao_recorrentes.clicked.connect(self.abrir_recorrentes)
        for tela in (self.balcao_view, self.vendas_view, self.caixa_view, self.resultado_view):
            tela.data_changed.connect(self.refresh_all)

    def dialogo_recorrentes(self) -> RecorrenciasDialog:
        return RecorrenciasDialog(
            self.recorrencias, TEXTOS_RECORRENCIA,
            gerar=self.gerar_recorrencias,
            contar=lambda contratos: recorrencias.contar_geradas(self.repository, contratos),
            clientes=self.clientes,
            catalogo=self.context.catalog,
            parent=self,
        )

    def abrir_recorrentes(self) -> None:
        self.dialogo_recorrentes().exec()
        self.refresh_all()

    def tem_trabalho_aberto(self) -> bool:
        # a venda do balcao so vai para o banco ao receber
        return bool(self.balcao_view.itens)

    def teardown(self) -> None:
        self.database.close()
