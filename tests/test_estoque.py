"""Testes das regras do DumTech Estoque."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dumtech.apps.estoque.database import open_database
from dumtech.apps.estoque.models import EstoqueError, Produto
from dumtech.apps.estoque.repository import EstoqueRepository


class EstoqueTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.arquivo = Path(tempfile.mkdtemp()) / "estoque.db"
        self.db = open_database(self.arquivo)
        self.repo = EstoqueRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _produto(self, codigo="MOU-001", nome="Mouse USB", quantidade=10, minimo=3) -> Produto:
        return self.repo.criar(
            Produto(
                codigo=codigo,
                nome=nome,
                categoria="Perifericos",
                quantidade=quantidade,
                estoque_minimo=minimo,
                preco_custo=25.0,
                preco_venda=50.0,
            )
        )

    # ------------------------------------------------------------- cadastro
    def test_cadastra_produto_e_guarda_estoque_inicial(self) -> None:
        produto = self._produto()
        self.assertIsNotNone(produto.id)
        self.assertEqual(self.repo.obter(produto.id).quantidade, 10)
        movimentacoes = self.repo.listar_movimentacoes()
        self.assertEqual(len(movimentacoes), 1)
        self.assertEqual(movimentacoes[0].tipo, "entrada")

    def test_nao_aceita_codigo_repetido(self) -> None:
        self._produto()
        with self.assertRaises(EstoqueError):
            self._produto(nome="Outro mouse")

    def test_nao_aceita_produto_sem_nome(self) -> None:
        with self.assertRaises(EstoqueError):
            self.repo.criar(Produto(codigo="X-1", nome="  "))

    def test_editar_quantidade_gera_ajuste(self) -> None:
        produto = self._produto()
        produto.quantidade = 25
        self.repo.atualizar(produto)
        ajustes = [m for m in self.repo.listar_movimentacoes() if m.tipo == "ajuste"]
        self.assertEqual(len(ajustes), 1)
        self.assertEqual(ajustes[0].saldo_atual, 25)

    def test_excluir_produto_com_historico_e_recusado(self) -> None:
        """Apagar levaria junto o historico: o caminho e inativar."""
        produto = self._produto()  # o cadastro com saldo ja gera uma entrada
        with self.assertRaises(EstoqueError):
            self.repo.excluir(produto.id)
        self.assertIsNotNone(self.repo.obter(produto.id))

    def test_excluir_produto_que_nunca_se_movimentou(self) -> None:
        produto = self._produto(codigo="NOVO-1", quantidade=0)
        self.repo.excluir(produto.id)
        self.assertIsNone(self.repo.obter(produto.id))

    def test_inativar_some_da_lista_e_mantem_o_historico(self) -> None:
        produto = self._produto()
        self.repo.inativar(produto.id)
        self.assertEqual(self.repo.listar(), [])
        self.assertEqual(len(self.repo.listar(incluir_inativos=True)), 1)
        self.assertEqual(len(self.repo.listar_movimentacoes()), 1)

        self.repo.reativar(produto.id)
        self.assertEqual(len(self.repo.listar()), 1)

    # --------------------------------------------------------- movimentacao
    def test_entrada_aumenta_o_estoque(self) -> None:
        produto = self._produto()
        self.repo.registrar_entrada(produto.id, 5, "Compra")
        self.assertEqual(self.repo.obter(produto.id).quantidade, 15)

    def test_saida_diminui_o_estoque(self) -> None:
        produto = self._produto()
        self.repo.registrar_saida(produto.id, 4, "Venda")
        self.assertEqual(self.repo.obter(produto.id).quantidade, 6)

    def test_saida_maior_que_o_estoque_e_recusada(self) -> None:
        produto = self._produto(quantidade=2)
        with self.assertRaises(EstoqueError):
            self.repo.registrar_saida(produto.id, 3)
        self.assertEqual(self.repo.obter(produto.id).quantidade, 2)

    def test_quantidade_zero_e_recusada(self) -> None:
        produto = self._produto()
        with self.assertRaises(EstoqueError):
            self.repo.registrar_entrada(produto.id, 0)

    # ---------------------------------------------------------- consultas
    def test_pesquisa_por_nome_codigo_e_categoria(self) -> None:
        self._produto()
        self._produto(codigo="TEC-002", nome="Teclado ABNT2")
        self.assertEqual(len(self.repo.listar(busca="teclado")), 1)
        self.assertEqual(len(self.repo.listar(busca="MOU")), 1)
        self.assertEqual(len(self.repo.listar(categoria="Perifericos")), 2)
        self.assertEqual(len(self.repo.listar(busca="inexistente")), 0)

    def test_resumo_do_painel(self) -> None:
        self._produto(quantidade=10, minimo=3)
        self._produto(codigo="TEC-002", nome="Teclado", quantidade=1, minimo=5)
        resumo = self.repo.resumo()
        self.assertEqual(resumo.total_produtos, 2)
        self.assertEqual(resumo.total_itens, 11)
        self.assertEqual(resumo.produtos_baixo, 1)
        self.assertEqual(len(resumo.ultimas), 2)

    # -------------------------------------------------------- persistencia
    def test_dados_continuam_apos_fechar_e_abrir(self) -> None:
        produto = self._produto()
        self.repo.registrar_entrada(produto.id, 7, "Compra")
        self.db.close()

        db2 = open_database(self.arquivo)
        repo2 = EstoqueRepository(db2)
        self.assertEqual(repo2.obter(produto.id).quantidade, 17)
        self.assertEqual(len(repo2.listar_movimentacoes()), 2)
        db2.close()


if __name__ == "__main__":
    unittest.main()
