"""Janela do DumTech Ordem de Servico.

A ordem comeca pelo Quadro: quem abre o programa de manha quer ver o que esta
em andamento hoje, nao quantas ordens existem no banco.
"""

from __future__ import annotations

import logging

from ....ui.app_shell import AppWindow
from ....ui.widgets.recorrencias import RecorrenciasDialog, Textos
from .. import recorrencias
from ..database import open_database
from ..repository import OrdensRepository
from .bancada_view import BancadaView
from .dashboard_view import DashboardView
from .ordem_dialog import OrdemDialog
from .ordens_view import OrdensView

logger = logging.getLogger(__name__)

TEXTOS_RECORRENCIA = Textos(
    documento="ordem", documentos="ordens",
    exemplo="Ex.: Manutenção preventiva do ar-condicionado",
    antecedencia=recorrencias.ANTECEDENCIA,
    onde="uma ordem aberta no Quadro",
)


class OrdensWindow(AppWindow):
    def setup_data(self) -> None:
        self.database = open_database(self.context.db_path)
        # com o Estoque liberado, a peca usada no servico sai do saldo
        # quando a ordem e entregue
        self.repository = OrdensRepository(self.database,
                                           catalogo=self.context.catalog)
        self.clientes = self.context.contacts.nomes() if self.context.contacts else []
        self.recorrencias = recorrencias.repositorio(self.database)
        # a preventiva que chegou com o programa fechado entra ao abrir
        self.gerar_recorrencias()

    def gerar_recorrencias(self) -> list[str]:
        """Abre as ordens devidas dos contratos. Nunca impede as Ordens de abrir."""
        try:
            return recorrencias.gerar(self.repository, self.context.contas,
                                      self.context.contacts)
        except Exception:  # noqa: BLE001 - recorrencia com defeito nao trava o Quadro
            logger.exception("Falha ao gerar as ordens recorrentes")
            return []

    def refresh_all(self) -> None:
        # o Hub aberto de um dia para o outro tambem precisa abrir a de hoje
        self.gerar_recorrencias()
        super().refresh_all()

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
        self.ordens_view.botao_recorrentes.clicked.connect(self.abrir_recorrentes)
        for tela in (self.bancada_view, self.ordens_view):
            tela.data_changed.connect(self.refresh_all)

    def abrir_ficha(self, ordem_id: int) -> None:
        """A ficha precisa da agenda de clientes, que so a janela conhece."""
        ordem = self.repository.obter(ordem_id) if ordem_id else None
        dialogo = OrdemDialog(self.repository, ordem, self.clientes,
                              self.bancada_view, catalogo=self.context.catalog,
                              contas=self.context.contas)
        if dialogo.exec():
            self.refresh_all()

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

    def teardown(self) -> None:
        self.database.close()
