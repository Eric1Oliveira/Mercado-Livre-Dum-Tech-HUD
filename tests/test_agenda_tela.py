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
from dumtech.apps.agenda.ui.grade import GradeWidget
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


class ClienteNoBlocoTestCase(unittest.TestCase):
    """O nome da cliente aparece no compromisso - pequeno, embaixo do titulo.

    Pedido de cliente: quem bate o olho na agenda tem de saber para quem e o
    horario sem precisar abrir a ficha.
    """

    def setUp(self) -> None:
        self.grade = GradeWidget()
        self.addCleanup(self.grade.deleteLater)
        quando = datetime.combine(date.today(), time(9, 0)).isoformat(timespec="minutes")
        self.compromisso = Compromisso(id=1, titulo="Corte e escova",
                                       cliente="Maria Souza", inicio=quando)

    def _textos(self, altura: float, compromisso=None):
        return self.grade._textos(QRectF(0, 0, 180, altura), compromisso or self.compromisso)

    def test_bloco_alto_mostra_a_cliente_embaixo_do_titulo(self) -> None:
        textos = self._textos(90)
        titulo = next(t for t in textos if t[2] == "Corte e escova")
        cliente = next(t for t in textos if t[3])

        self.assertEqual(cliente[2], "Maria Souza")
        self.assertEqual(cliente[1], "caption", "o nome vai pequeno")
        self.assertGreaterEqual(cliente[0].top(), titulo[0].bottom(),
                                "a cliente vem embaixo do titulo")
        self.assertLessEqual(cliente[0].bottom(), 90, "e dentro do bloco")

    def test_bloco_medio_leva_a_cliente_ao_lado_do_horario(self) -> None:
        textos = self._textos(32)
        hora = textos[0]
        cliente = next(t for t in textos if t[3])
        self.assertIn("Maria Souza", cliente[2])
        self.assertEqual(cliente[0].top(), hora[0].top(), "mesma linha do horario")

    def test_bloco_baixo_poe_tudo_numa_linha(self) -> None:
        textos = self._textos(20)
        self.assertEqual(len(textos), 1)
        self.assertIn("Corte e escova", textos[0][2])
        self.assertIn("Maria Souza", textos[0][2])

    def test_sem_cliente_nao_sobra_linha_vazia(self) -> None:
        sem = Compromisso(id=2, titulo="Almoco", inicio=self.compromisso.inicio)
        textos = self._textos(90, sem)
        self.assertFalse(any(t[3] for t in textos))
        self.assertNotIn("·", " ".join(t[2] for t in self._textos(20, sem)))

    def test_a_grade_desenha_com_a_cliente(self) -> None:
        """Pintar de verdade nao pode quebrar (fonte, tema, recorte)."""
        db = open_database(Path(tempfile.mkdtemp()) / "agenda.db")
        self.addCleanup(db.close)
        repo = AgendaRepository(db)
        repo.salvar(Compromisso(titulo="Corte e escova", cliente="Maria Souza",
                                inicio=self.compromisso.inicio, duracao_min=90))
        tela = AgendaView(repo)
        self.addCleanup(tela.deleteLater)
        tela.refresh()
        tela.grade.resize(900, 700)
        tela.grade.grab()
        self.assertTrue(tela.grade._blocos)


if __name__ == "__main__":
    unittest.main()
