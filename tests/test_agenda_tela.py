"""A grade da agenda por dentro: navegacao, botao direito e exclusao."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication

from dumtech.apps.agenda.database import open_database
from dumtech.apps.agenda.models import CANCELADO, Compromisso
from dumtech.apps.agenda.repository import AgendaRepository
from dumtech.apps.agenda.ui.agenda_view import AgendaView
from dumtech.core import confirmacoes
from dumtech.core.config import Settings

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class GradeTelaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = open_database(Path(tempfile.mkdtemp()) / "agenda.db")
        self.repo = AgendaRepository(self.db)
        quando = datetime.combine(date.today(), time(9, 0)).isoformat(timespec="minutes")
        self.compromisso = self.repo.salvar(Compromisso(
            titulo="Troca de oleo", cliente="Mercado Central",
            inicio=quando, duracao_min=60,
        ))
        self.tela = AgendaView(self.repo)
        self.tela.refresh()
        # sem janela de confirmacao: o teste nao pode parar esperando clique
        confirmacoes.usar(Settings(Path(tempfile.mkdtemp()) / "config.json"))
        confirmacoes.nunca_mais(confirmacoes.EXCLUIR)

    def tearDown(self) -> None:
        self.tela.deleteLater()
        self.db.close()
        confirmacoes.voltar_a_perguntar()

    def _ponto_do_bloco(self) -> QPoint:
        """O centro do retangulo que a grade desenhou para o compromisso."""
        self.tela.grade.resize(900, 700)
        self.tela.grade.grab()          # forca o paintEvent a registrar os blocos
        self.assertTrue(self.tela.grade._blocos, "a grade nao desenhou o bloco")
        rect: QRectF = self.tela.grade._blocos[0][0]
        return rect.center().toPoint()

    # ------------------------------------------------------------ navegacao
    def test_as_duas_setas_do_periodo_sao_do_mesmo_par(self) -> None:
        """A seta de avancar era o icone de abrir link fora do programa."""
        self.assertEqual(self.tela.botao_antes._icon_name, "back")
        self.assertEqual(self.tela.botao_depois._icon_name, "forward")
        self.assertTrue(self.tela.botao_antes.toolTip())
        self.assertTrue(self.tela.botao_depois.toolTip())

    def test_as_setas_andam_o_periodo_da_tela(self) -> None:
        primeiro = self.tela.primeiro_dia
        dias = self.tela.modo.currentData()
        self.tela._navegar(1)
        self.assertEqual(self.tela.primeiro_dia, primeiro + timedelta(days=dias))
        self.tela._navegar(-1)
        self.assertEqual(self.tela.primeiro_dia, primeiro)

    # --------------------------------------------------------- botao direito
    def test_botao_direito_em_cima_do_compromisso_pede_o_menu(self) -> None:
        pedidos = []
        self.tela.grade.menu_pedido.connect(lambda i, _p: pedidos.append(i))
        ponto = self._ponto_do_bloco()
        self.tela.grade.contextMenuEvent(QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, ponto, self.tela.grade.mapToGlobal(ponto)))
        self.assertEqual(pedidos, [self.compromisso.id])
        self.assertEqual(self.tela.grade.selecao, self.compromisso.id)

    def test_botao_direito_no_vazio_nao_abre_menu(self) -> None:
        """Menu de compromisso sem compromisso embaixo nao quer dizer nada."""
        pedidos = []
        self.tela.grade.menu_pedido.connect(lambda i, _p: pedidos.append(i))
        vazio = QPoint(5, 5)
        self.tela.grade.contextMenuEvent(QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, vazio, self.tela.grade.mapToGlobal(vazio)))
        self.assertEqual(pedidos, [])

    def test_o_menu_traz_excluir(self) -> None:
        self.tela._menu_do_compromisso(self.compromisso.id, QPoint(0, 0))
        menu = self.tela._menu_aberto
        rotulos = [acao.text() for acao in menu.actions() if not acao.isSeparator()]
        menu.close()
        self.assertIn("Excluir", rotulos)
        self.assertIn("Abrir", rotulos)
        self.assertIn("Concluir", rotulos)

    # ---------------------------------------------------------------- acoes
    def test_excluir_tira_o_compromisso_da_agenda(self) -> None:
        avisos = []
        self.tela.data_changed.connect(lambda: avisos.append(1))
        self.tela._selecionar(self.compromisso.id)
        self.tela._excluir(self.compromisso)
        self.assertIsNone(self.repo.obter(self.compromisso.id))
        self.assertIsNone(self.tela.selecionado)
        self.assertEqual(avisos, [1])

    def test_cancelar_pelo_menu_mantem_o_registro(self) -> None:
        """Cancelar nao e excluir: o historico do dia continua contando."""
        self.tela._mudar_status(self.compromisso, CANCELADO, "cancelado")
        atual = self.repo.obter(self.compromisso.id)
        self.assertIsNotNone(atual)
        self.assertEqual(atual.status, CANCELADO)


if __name__ == "__main__":
    unittest.main()
