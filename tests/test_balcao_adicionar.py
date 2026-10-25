"""O botao Adicionar do Balcao acende enquanto a pessoa digita.

Defeito relatado por cliente: digitava o produto e o valor, e o Adicionar
continuava apagado - so acendia depois de ir ao Painel e voltar. O campo de
dinheiro so assume o valor digitado quando perde o foco (`keyboardTracking`
desligado), e ninguem olhava para ele enquanto se digitava.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dumtech.apps.vendas.database import open_database
from dumtech.apps.vendas.repository import VendasRepository
from dumtech.apps.vendas.ui.balcao_view import BalcaoView

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class _SemEsseProduto:
    """Estoque que nao tem o que foi digitado: a venda sai avulsa."""

    def buscar(self, termo: str):
        return None

    def procurar(self, termo: str, limite: int = 20):
        return []


class AdicionarAcendeTestCase(unittest.TestCase):
    def _tela(self, catalogo=None) -> BalcaoView:
        db = open_database(Path(tempfile.mkdtemp()) / "vendas.db")
        self.addCleanup(db.close)
        tela = BalcaoView(VendasRepository(db, catalogo=catalogo))
        self.addCleanup(tela.deleteLater)
        tela.show()
        return tela

    def _digitar_valor(self, tela: BalcaoView, texto: str) -> None:
        """Como a pessoa faz: clica no valor e digita, sem sair do campo."""
        tela.valor.setFocus()
        tela.valor.lineEdit().selectAll()
        QTest.keyClicks(tela.valor.lineEdit(), texto)

    def test_sem_estoque_acende_ao_digitar_o_valor(self) -> None:
        tela = self._tela()
        QTest.keyClicks(tela.bipe, "Corte de cabelo")
        self.assertFalse(tela.botao_adicionar.isEnabled(), "sem valor ainda nao da")

        self._digitar_valor(tela, "45")

        self.assertTrue(tela.botao_adicionar.isEnabled(),
                        "digitou produto e valor: o Adicionar tem de acender na hora")

    def test_produto_fora_do_estoque_acende_ao_digitar_o_valor(self) -> None:
        tela = self._tela(_SemEsseProduto())
        QTest.keyClicks(tela.bipe, "Brinde")
        QTest.keyClick(tela.bipe, Qt.Key.Key_Return)   # nao achou: vai para o valor

        self._digitar_valor(tela, "12,50")

        self.assertTrue(tela.botao_adicionar.isEnabled())

    def test_apagar_o_valor_apaga_o_botao(self) -> None:
        tela = self._tela()
        QTest.keyClicks(tela.bipe, "Corte de cabelo")
        self._digitar_valor(tela, "45")
        self._digitar_valor(tela, "0")
        self.assertFalse(tela.botao_adicionar.isEnabled())

    def test_clicar_logo_apos_digitar_usa_o_valor_digitado(self) -> None:
        """O clique vem antes de o campo largar o foco: nao pode sair R$ 0,00."""
        tela = self._tela()
        QTest.keyClicks(tela.bipe, "Corte de cabelo")
        self._digitar_valor(tela, "45")

        tela.botao_adicionar.click()

        self.assertEqual(len(tela.itens), 1)
        self.assertEqual(tela.itens[0].valor_unitario, 45.0)
        self.assertEqual(tela.itens[0].descricao, "Corte de cabelo")


if __name__ == "__main__":
    unittest.main()
