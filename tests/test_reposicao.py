"""Estoque: produtos para reposicao, valor por produto e o Painel novo."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dumtech.apps.estoque.database import open_database
from dumtech.apps.estoque.models import TIPO_ENTRADA, TIPO_SAIDA, Produto
from dumtech.apps.estoque.repository import EstoqueRepository


class BaseReposicao(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        arquivo = Path(tempfile.mkdtemp()) / "estoque.db"
        self.repo = EstoqueRepository(open_database(arquivo))
        self.addCleanup(self.repo.db.close)

    def _produto(self, codigo: str, **campos) -> Produto:
        dados = dict(codigo=codigo, nome=campos.pop("nome", f"Produto {codigo}"))
        dados.update(campos)
        return self.repo.criar(Produto(**dados))

    def _widget(self, widget):
        self.addCleanup(widget.deleteLater)
        return widget


class ReposicaoRegrasTestCase(BaseReposicao):
    def test_zerado_vem_antes_de_baixo(self) -> None:
        """Baixo e longe do minimo continua vendendo; zerado nao vende hoje."""
        self._produto("BAIXO", quantidade=2, estoque_minimo=20)
        self._produto("ZERADO", quantidade=0, estoque_minimo=1)
        self._produto("OK", quantidade=50, estoque_minimo=5)
        self.assertEqual([p.codigo for p in self.repo.a_comprar()], ["ZERADO", "BAIXO"])

    def test_ultima_entrada_de_cada_produto(self) -> None:
        produto = self._produto("A", quantidade=5)
        nunca = self._produto("B")              # sem saldo inicial, sem entrada
        self.repo.movimentar(produto.id, TIPO_ENTRADA, 3)
        self.repo.movimentar(produto.id, TIPO_SAIDA, 1)    # saida nao e reposicao

        ultimas = self.repo.ultimas_entradas()
        self.assertIn(produto.id, ultimas)
        self.assertNotIn(nunca.id, ultimas)

    def test_entrada_ja_vem_com_a_quantidade_sugerida(self) -> None:
        from dumtech.apps.estoque.ui.movimento_dialog import MovimentoDialog

        produto = self._produto("A", quantidade=2, estoque_minimo=5, estoque_maximo=20)
        dialogo = self._widget(MovimentoDialog(
            self.repo, produto, TIPO_ENTRADA, quantidade_inicial=produto.sugestao_compra,
            observacao="Reposição de estoque",
        ))
        self.assertEqual(dialogo.quantidade.value(), 18)
        self.assertEqual(dialogo.observacao.text(), "Reposição de estoque")
        dialogo.salvar()
        self.assertEqual(self.repo.obter(produto.id).quantidade, 20)


class ReposicaoTelaTestCase(BaseReposicao):
    def test_lista_com_situacao_sugestao_e_fornecedor(self) -> None:
        from dumtech.apps.estoque.ui.reposicao_dialog import ReposicaoDialog

        self._produto("Z", nome="Zerado", quantidade=0, estoque_minimo=2,
                      estoque_maximo=10, fornecedor="Distribuidora X")
        self._produto("B", nome="Baixo", quantidade=1, estoque_minimo=3)

        dialogo = self._widget(ReposicaoDialog(self.repo))
        tabela = dialogo.tabela
        self.assertEqual(tabela.rowCount(), 2)
        self.assertEqual(tabela.item(0, 0).text(), "Zerado")
        self.assertEqual(tabela.item(0, 1).text(), "Zerado")
        self.assertEqual(tabela.item(0, 4).text(), "+10 UN")
        self.assertEqual(tabela.item(0, 5).text(), "Distribuidora X")
        self.assertEqual(tabela.item(0, 6).text(), "Nunca")
        self.assertEqual(tabela.item(1, 1).text(), "Baixo")
        # o mais urgente ja vem escolhido para registrar
        self.assertEqual(dialogo.selecionado().nome, "Zerado")
        self.assertTrue(dialogo.botao_registrar.isEnabled())

        dialogo.filtro.setCurrentIndex(dialogo.filtro.findData("baixos"))
        self.assertEqual(tabela.rowCount(), 1)
        self.assertEqual(tabela.item(0, 0).text(), "Baixo")

    def test_painel_mostra_os_cinco_mais_criticos_e_ver_todos(self) -> None:
        from dumtech.apps.estoque.ui.dashboard_view import CRITICOS, DashboardView

        for numero in range(CRITICOS + 2):
            self._produto(f"P{numero}", quantidade=0 if numero < 2 else 1, estoque_minimo=3)
        painel = self._widget(DashboardView(self.repo))

        self.assertEqual(painel.painel_reposicao.linhas, CRITICOS)
        self.assertIn(f"Ver todos ({CRITICOS + 2})", painel.botao_ver_todos.text())
        self.assertFalse(painel.botao_ver_todos.isHidden())
        self.assertEqual(painel.card_reposicao.value_label.text(), str(CRITICOS + 2))
        self.assertIn("2 zerados", painel.card_reposicao.hint_label.text())
        self.assertIn("5 abaixo do mínimo", painel.card_reposicao.hint_label.text())

    def test_poucos_produtos_lista_compacta_sem_ver_todos(self) -> None:
        from dumtech.apps.estoque.ui.dashboard_view import DashboardView

        self._produto("A", quantidade=1, estoque_minimo=3)
        painel = self._widget(DashboardView(self.repo))
        self.assertEqual(painel.painel_reposicao.linhas, 1)
        self.assertIn("Registrar reposição", painel.botao_ver_todos.text())

        self.repo.movimentar(self.repo.buscar_por_codigo("A").id, TIPO_ENTRADA, 10)
        painel.refresh()
        self.assertEqual(painel.painel_reposicao.linhas, 0)
        self.assertTrue(painel.botao_ver_todos.isHidden())
        self.assertIn("Nenhum produto", painel.card_reposicao.hint_label.text())

    def test_valor_por_produto_soma_cem_por_cento(self) -> None:
        from dumtech.apps.estoque.ui.dashboard_view import MAIORES, DashboardView

        for numero in range(MAIORES + 3):
            self._produto(f"V{numero}", quantidade=10, preco_custo=10.0 + numero)
        painel = self._widget(DashboardView(self.repo))

        # os maiores com nome, o resto numa linha "Outros produtos"
        self.assertEqual(painel.painel_valor.linhas, MAIORES + 1)
        self.assertIn("unidades em estoque", painel.card_produtos.hint_label.text())
        self.assertEqual(painel.card_valor.title_label.text(), "Valor investido em estoque")
        participacoes = []
        grade = painel.painel_valor.grade
        for linha in range(grade.rowCount()):
            item = grade.itemAtPosition(linha, 2)
            texto = getattr(item.widget(), "text", lambda: "")() if item else ""
            if texto.endswith("%"):
                participacoes.append(float(texto[:-1].replace(",", ".")))
        self.assertAlmostEqual(sum(participacoes), 100.0, delta=0.5)

    def test_movimentacoes_recentes_com_colunas(self) -> None:
        from dumtech.apps.estoque.ui.dashboard_view import DashboardView

        produto = self._produto("M", nome="Mouse", quantidade=5)
        self.repo.movimentar(produto.id, TIPO_SAIDA, 2)
        painel = self._widget(DashboardView(self.repo))

        grade = painel.painel_movimentacoes.grade
        cabecalhos = [grade.itemAtPosition(0, c).widget().text() for c in range(4)]
        self.assertEqual(cabecalhos, ["Produto", "Tipo de movimentação", "Quantidade",
                                      "Data e hora"])
        linha = [grade.itemAtPosition(2, c).widget().text() for c in range(1, 4)]
        self.assertEqual(linha[0], "Saída")
        self.assertEqual(linha[1], "-2 UN")
        self.assertTrue(linha[2].startswith("Hoje"))

    def test_cartao_de_reposicao_e_clicavel(self) -> None:
        from dumtech.apps.estoque.ui.dashboard_view import DashboardView

        painel = self._widget(DashboardView(self.repo))
        abertos = []
        painel.abrir_reposicao = lambda: abertos.append(True)
        painel.card_reposicao.clicado.disconnect()
        painel.card_reposicao.clicado.connect(painel.abrir_reposicao)

        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest

        QTest.mouseClick(painel.card_reposicao, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
        self.assertEqual(abertos, [True])


if __name__ == "__main__":
    unittest.main()
