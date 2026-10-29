"""A sugestao de produto chegando nos tres lugares onde se digita item.

`test_busca_catalogo.py` prova o mecanismo. Aqui provamos a ligacao: que o
catalogo do Estoque atravessa a cadeia ate o campo, que escolher preenche os
campos certos de cada modulo, e que sem o Estoque na licenca nada muda.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from dumtech.apps.estoque.models import Produto
from dumtech.core.config import Settings
from dumtech.core.paths import DataPaths

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def _seta_baixo(busca) -> None:
    busca.tecla(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down,
                          Qt.KeyboardModifier.NoModifier))


class SugestaoNosModulosTestCase(unittest.TestCase):
    """Um Hub de verdade, com produto de verdade no Estoque."""

    def setUp(self) -> None:
        from dumtech.hub.main_window import HubWindow

        self.hub = HubWindow(settings=Settings(Path(tempfile.mkdtemp()) / "hub.json"))
        self.hub.launcher.notify = lambda *args: None
        self.addCleanup(self._fechar)

        # a pasta de dados dos testes e uma so para o arquivo inteiro: o
        # produto sobrevive de um teste para o outro, entao so criamos se
        # ainda nao existir
        self.assertTrue(self.hub.open_app("estoque"))
        estoque = self.hub.launcher.get("estoque")
        if estoque.repository.buscar("A1023") is None:
            estoque.repository.criar(Produto(
                codigo="A1023", nome="Cafe Torrado 500g", unidade="UN",
                quantidade=10, preco_venda=20.0,
            ))
        self.hub.close_app("estoque", perguntar=False)

    def _fechar(self) -> None:
        self.hub.close()
        self.hub.deleteLater()
        QApplication.instance().sendPostedEvents(None, QEvent.Type.DeferredDelete)

    # ------------------------------------------------------------------ balcao
    def test_o_balcao_sugere_e_preenche(self) -> None:
        self.assertTrue(self.hub.open_app("vendas"))
        balcao = self.hub.launcher.get("vendas").balcao_view
        self.assertIsNotNone(balcao.busca.catalogo, "o catalogo tem que atravessar")

        balcao.busca.procurar("cafe")
        self.assertTrue(balcao.busca.aberta)
        self.assertIn("A1023", balcao.busca.linha_texto(0))

        _seta_baixo(balcao.busca)
        balcao.busca.tecla(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                     Qt.KeyboardModifier.NoModifier))
        self.assertEqual(balcao.bipe.text(), "Cafe Torrado 500g")
        self.assertEqual(balcao.valor.value(), 20.0)
        self.assertIn("saldo", balcao.achado.text())
        self.assertFalse(balcao.busca.aberta)

    def test_o_enter_do_leitor_no_balcao_continua_sendo_o_de_sempre(self) -> None:
        """O caminho que o codigo de barras usa nao pode ter mudado."""
        self.assertTrue(self.hub.open_app("vendas"))
        balcao = self.hub.launcher.get("vendas").balcao_view

        balcao.bipe.setText("A1023")
        balcao.busca.procurar("A1023")      # a lista abriu, como abriria digitando
        balcao._localizar()                 # o Enter de sempre
        self.assertEqual(balcao.bipe.text(), "Cafe Torrado 500g")
        self.assertEqual(balcao.valor.value(), 20.0)

    # ----------------------------------------------------------- lancar venda
    def test_o_lancar_venda_sugere_e_guarda_o_produto(self) -> None:
        """A venda lancada a mao tambem enxerga o Estoque - e lembra qual e."""
        self.assertTrue(self.hub.open_app("vendas"))
        view = self.hub.launcher.get("vendas").vendas_view
        dialogo = view.abrir_dialogo(None)
        self.addCleanup(dialogo.deleteLater)
        editor = dialogo.itens
        self.assertIsNotNone(editor.busca.catalogo, "o catalogo tem que atravessar")

        editor.busca.procurar("cafe")
        self.assertTrue(editor.busca.aberta)
        _seta_baixo(editor.busca)
        editor.busca.tecla(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                     Qt.KeyboardModifier.NoModifier))
        self.assertEqual(editor.campo_descricao.text(), "Cafe Torrado 500g")
        self.assertEqual(editor.campo_valor.value(), 20.0)

        editor.adicionar()
        item = editor.items()[0]
        self.assertGreater(item["produto_id"], 0, "sem o vinculo, o estoque nao baixa")
        self.assertEqual(item["codigo"], "A1023")

    def test_o_lancar_venda_esquece_o_produto_se_a_descricao_mudou(self) -> None:
        self.assertTrue(self.hub.open_app("vendas"))
        view = self.hub.launcher.get("vendas").vendas_view
        dialogo = view.abrir_dialogo(None)
        self.addCleanup(dialogo.deleteLater)
        editor = dialogo.itens

        editor.busca.procurar("cafe")
        _seta_baixo(editor.busca)
        editor.busca.tecla(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                     Qt.KeyboardModifier.NoModifier))
        editor.campo_descricao.setText("Cafe da casa")
        editor.adicionar()
        self.assertEqual(editor.items()[0].get("produto_id", 0), 0)

    def test_a_venda_lancada_ja_paga_baixa_o_estoque_e_cai_no_financeiro(self) -> None:
        from dumtech.apps.vendas.models import CONCLUIDA

        self.assertTrue(self.hub.open_app("vendas"))
        view = self.hub.launcher.get("vendas").vendas_view
        catalogo = self.hub.launcher.catalog("vendas")
        antes = catalogo.buscar("A1023").saldo

        dialogo = view.abrir_dialogo(None)
        self.addCleanup(dialogo.deleteLater)
        dialogo.itens._usar_produto(catalogo.buscar("A1023"))
        dialogo.itens.adicionar()
        dialogo.status.setCurrentIndex(dialogo.status.findData(CONCLUIDA))
        dialogo.salvar()

        self.assertEqual(catalogo.buscar("A1023").saldo, antes - 1)
        contas = self.hub.launcher.contas("vendas")
        self.assertTrue(contas.ja_lancado(dialogo.venda.numero),
                        "toda venda cai no Financeiro, inclusive a lancada a mao")
        self.assertIn("Financeiro", dialogo.recado)

    # -------------------------------------------------------------- orcamentos
    def test_o_orcamento_sugere_e_traz_o_preco_do_estoque(self) -> None:
        self.assertTrue(self.hub.open_app("orcamentos"))
        view = self.hub.launcher.get("orcamentos").orcamentos_view
        dialogo = view.abrir_dialogo(None)
        self.addCleanup(dialogo.deleteLater)
        editor = dialogo.itens
        self.assertIsNotNone(editor.busca.catalogo)

        editor.busca.procurar("cafe")
        _seta_baixo(editor.busca)
        editor.busca.tecla(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                     Qt.KeyboardModifier.NoModifier))
        self.assertEqual(editor.descricao.text(), "Cafe Torrado 500g")
        self.assertEqual(editor.valor.value(), 20.0)
        self.assertEqual(editor.unidade.currentText(), "UN")

    # ------------------------------------------------------------------ ordens
    def test_a_ordem_sugere_e_marca_como_peca(self) -> None:
        from dumtech.apps.ordens.models import PECA

        self.assertTrue(self.hub.open_app("ordens"))
        view = self.hub.launcher.get("ordens").ordens_view
        dialogo = view.abrir_dialogo(None)
        self.addCleanup(dialogo.deleteLater)
        editor = dialogo.itens
        self.assertIsNotNone(editor.busca.catalogo)

        editor.busca.procurar("cafe")
        _seta_baixo(editor.busca)
        editor.busca.tecla(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                     Qt.KeyboardModifier.NoModifier))
        self.assertEqual(editor.descricao.text(), "Cafe Torrado 500g")
        self.assertEqual(editor.valor.value(), 20.0)
        self.assertEqual(editor.tipo.currentData(), PECA,
                         "produto que veio do Estoque e peca, nao servico")


class SemEstoqueTestCase(unittest.TestCase):
    """Sem o Estoque na licenca, os campos continuam texto livre."""

    def setUp(self) -> None:
        from dumtech.core.licensing import License, LicenseService, machine_id
        from dumtech.hub.main_window import HubWindow

        pasta = Path(tempfile.mkdtemp())
        servico = LicenseService(pasta / "license.json")
        servico.save(License(
            key="DUM1-2345-ABCD-6789", customer="Sem estoque",
            entitlements=("vendas", "orcamentos", "ordens"),
            machine=machine_id(), activated_at="2026-01-01T10:00:00",
        ))
        self.hub = HubWindow(settings=Settings(pasta / "hub.json"),
                             license_service=servico)
        self.hub.launcher.notify = lambda *args: None
        self.addCleanup(self._fechar)

    def _fechar(self) -> None:
        self.hub.close()
        self.hub.deleteLater()
        QApplication.instance().sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_o_balcao_funciona_sem_catalogo(self) -> None:
        self.assertTrue(self.hub.open_app("vendas"))
        balcao = self.hub.launcher.get("vendas").balcao_view
        self.assertIsNone(balcao.busca.catalogo)

        balcao.busca.procurar("cafe")
        self.assertFalse(balcao.busca.aberta)
        # e o Enter continua sendo de quem sempre foi
        self.assertFalse(balcao.busca.tecla(
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                      Qt.KeyboardModifier.NoModifier)
        ))

    def test_vender_avulso_continua_funcionando(self) -> None:
        self.assertTrue(self.hub.open_app("vendas"))
        balcao = self.hub.launcher.get("vendas").balcao_view
        balcao.bipe.setText("Servico avulso")
        balcao.quantidade.setValue(1)
        balcao.valor.setValue(35.0)
        balcao._adicionar()
        self.assertEqual(len(balcao.itens), 1)
        self.assertEqual(balcao.itens[0].descricao, "Servico avulso")


class EstoqueLiberadoDepoisTestCase(unittest.TestCase):
    """O Estoque entra na licenca com o Vendas ja montado (compra, teste gratis).

    O Vendas nascia sem catalogo e ficava sem ele ate o Hub ser reiniciado: o
    produto do Estoque nao aparecia em lugar nenhum da venda.
    """

    def setUp(self) -> None:
        from dumtech.core.licensing import License, LicenseService, machine_id
        from dumtech.hub.main_window import HubWindow

        pasta = Path(tempfile.mkdtemp())
        self.servico = LicenseService(pasta / "license.json")
        self.licenca = dict(
            key="DUM1-2345-ABCD-6789", customer="Cresceu",
            machine=machine_id(), activated_at="2026-01-01T10:00:00",
        )
        self.servico.save(License(entitlements=("vendas", "orcamentos"), **self.licenca))
        self.hub = HubWindow(settings=Settings(pasta / "hub.json"),
                             license_service=self.servico)
        self.hub.launcher.notify = lambda *args: None
        self.addCleanup(self._fechar)

    def _fechar(self) -> None:
        self.hub.close()
        self.hub.deleteLater()
        QApplication.instance().sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _ir_para_a_licenca(self) -> None:
        from dumtech.hub.main_window import PAGINA_LICENCA

        self.hub._go(PAGINA_LICENCA)  # quem libera modulo esta ali, nao no Vendas

    def _liberar_estoque(self) -> None:
        from dumtech.core.licensing import License

        self.servico.save(License(entitlements=("vendas", "orcamentos", "estoque"),
                                  **self.licenca))
        self.hub._on_license_changed()
        QApplication.instance().sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_o_vendas_aberto_passa_a_enxergar_o_estoque(self) -> None:
        self.assertTrue(self.hub.open_app("vendas"))
        self.assertIsNone(self.hub.launcher.get("vendas").balcao_view.busca.catalogo)
        self._ir_para_a_licenca()

        self._liberar_estoque()
        self.assertTrue(self.hub.open_app("vendas"))
        vendas = self.hub.launcher.get("vendas")
        self.assertIsNotNone(vendas.balcao_view.busca.catalogo)
        self.assertTrue(vendas.repository.tem_catalogo)

    def test_o_preparado_em_segundo_plano_tambem(self) -> None:
        surface = self.hub.launcher.preparar("orcamentos")
        self.hub.workspace.montar_escondido(surface)
        self.assertIsNone(surface.context.catalog)

        self._liberar_estoque()
        self.assertTrue(self.hub.open_app("orcamentos"))
        self.assertIsNotNone(self.hub.launcher.get("orcamentos").context.catalog)

    def test_venda_no_meio_do_balcao_nao_se_perde(self) -> None:
        self.assertTrue(self.hub.open_app("vendas"))
        balcao = self.hub.launcher.get("vendas").balcao_view
        balcao.bipe.setText("Servico avulso")
        balcao.valor.setValue(35.0)
        balcao._adicionar()
        self._ir_para_a_licenca()

        self._liberar_estoque()
        self.assertIs(self.hub.launcher.get("vendas").balcao_view, balcao,
                      "com item no carrinho, o Vendas fica como estava")
        self.assertEqual(len(balcao.itens), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
