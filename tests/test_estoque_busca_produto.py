"""Achar o produto pelo nome em Entradas e em Movimentacoes.

Antes, Entradas so achava o produto com o codigo exato (ou um nome que batesse
com UM produto so), e Movimentacoes era uma caixa de selecao para rolar. Agora
os dois campos sugerem os produtos cadastrados enquanto se digita.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from dumtech.apps.estoque.database import open_database
from dumtech.apps.estoque.models import TIPO_ENTRADA, Produto
from dumtech.apps.estoque.repository import EstoqueRepository

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def _escolher_primeiro(busca) -> None:
    """Seta para baixo e Enter, como o usuario faria."""
    for tecla in (Qt.Key.Key_Down, Qt.Key.Key_Return):
        busca.tecla(QKeyEvent(QEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier))


class BuscaDeProdutoBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = open_database(Path(tempfile.mkdtemp()) / "estoque.db")
        self.addCleanup(self.db.close)
        self.repo = EstoqueRepository(self.db)
        for codigo, nome in (("C1", "Cabo HDMI 2m"), ("C2", "Cabo USB-C"), ("M1", "Mouse sem fio")):
            self.repo.criar(Produto(codigo=codigo, nome=nome, unidade="UN", quantidade=5))


class EntradasTestCase(BuscaDeProdutoBase):
    def setUp(self) -> None:
        super().setUp()
        from dumtech.apps.estoque.ui.entradas_view import EntradasView

        self.tela = EntradasView(self.repo)
        self.addCleanup(self.tela.deleteLater)

    def test_parte_do_nome_sugere_os_produtos_cadastrados(self) -> None:
        self.tela.busca.procurar("cabo")
        self.assertTrue(self.tela.busca.aberta)
        self.assertIn("Cabo HDMI 2m", self.tela.busca.linha_texto(0))

        _escolher_primeiro(self.tela.busca)
        self.assertEqual(self.tela._produto.codigo, "C1")
        self.assertTrue(self.tela.botao_adicionar.isEnabled())

    def test_enter_com_nome_ambiguo_mostra_a_lista_em_vez_de_dizer_que_nao_existe(self) -> None:
        self.tela.bipe.setText("cabo")
        self.tela._localizar()
        self.assertIsNone(self.tela._produto)
        self.assertTrue(self.tela.busca.aberta)
        self.assertIn("Escolha na lista", self.tela.aviso.text())

    def test_o_codigo_exato_continua_entrando_direto(self) -> None:
        self.tela.bipe.setText("M1")
        self.tela._localizar()
        self.assertEqual(self.tela._produto.nome, "Mouse sem fio")


class MovimentacoesTestCase(BuscaDeProdutoBase):
    def setUp(self) -> None:
        super().setUp()
        from dumtech.apps.estoque.ui.movimentacoes_view import MovimentacoesView

        self.tela = MovimentacoesView(self.repo)
        self.addCleanup(self.tela.deleteLater)

    def test_sem_produto_escolhido_nao_da_para_registrar(self) -> None:
        self.assertFalse(self.tela.botao_entrada.isEnabled())
        self.assertFalse(self.tela.botao_saida.isEnabled())

    def test_escreve_o_nome_escolhe_e_registra(self) -> None:
        self.tela.busca_produto.procurar("mouse")
        _escolher_primeiro(self.tela.busca_produto)
        self.assertEqual(self.tela.campo_produto.text(), "Mouse sem fio")
        self.assertTrue(self.tela.botao_entrada.isEnabled())

        self.tela.quantidade.setValue(3)
        self.tela._registrar(TIPO_ENTRADA)
        self.assertEqual(self.repo.buscar("M1").quantidade, 8)
        # o produto continua escolhido, com o saldo novo
        self.assertEqual(self.tela._produto.quantidade, 8)

    def test_mexer_no_nome_depois_de_escolher_desfaz_a_escolha(self) -> None:
        self.tela.campo_produto.setText("M1")
        self.tela._localizar()
        self.assertIsNotNone(self.tela._produto)

        self.tela.campo_produto.textEdited.emit("Mous")
        self.assertIsNone(self.tela._produto)
        self.assertFalse(self.tela.botao_saida.isEnabled())


if __name__ == "__main__":
    unittest.main()
