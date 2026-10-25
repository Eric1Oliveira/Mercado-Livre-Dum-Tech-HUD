"""Regras que o DumTech Estoque ganhou na versao 2 do banco.

Unidade e quantidade decimal, custo medio, busca por codigo de barras, entrada
em lote, contagem (balanco), reposicao e planilhas. Tudo sem abrir janela.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dumtech.apps.estoque.database import open_database
from dumtech.apps.estoque.models import EstoqueError, ItemEntrada, Produto
from dumtech.apps.estoque.repository import EstoqueRepository


def _novo_repo() -> tuple[EstoqueRepository, Path]:
    arquivo = Path(tempfile.mkdtemp()) / "estoque.db"
    return EstoqueRepository(open_database(arquivo)), arquivo


class BaseEstoque(unittest.TestCase):
    def setUp(self) -> None:
        self.repo, self.arquivo = _novo_repo()

    def tearDown(self) -> None:
        self.repo.db.close()

    def _produto(self, codigo: str, **campos) -> Produto:
        dados = dict(codigo=codigo, nome=campos.pop("nome", f"Produto {codigo}"))
        dados.update(campos)
        return self.repo.criar(Produto(**dados))


class UnidadeDecimalTestCase(BaseEstoque):
    def test_quantidade_decimal_sobrevive_ao_banco(self) -> None:
        produto = self._produto("CAB-01", nome="Cabo por metro", unidade="M", quantidade=2.5)
        self.assertEqual(self.repo.obter(produto.id).quantidade, 2.5)

        self.repo.registrar_saida(produto.id, 0.75, "Venda no balcao")
        self.assertEqual(self.repo.obter(produto.id).quantidade, 1.75)

    def test_saida_igual_ao_saldo_decimal_e_permitida(self) -> None:
        """0.1 + 0.2 != 0.3 no float: isso nao pode virar 'estoque insuficiente'."""
        produto = self._produto("KG-01", nome="Farinha", unidade="KG", quantidade=0.1)
        self.repo.registrar_entrada(produto.id, 0.2)
        self.repo.registrar_saida(produto.id, 0.3)
        self.assertEqual(self.repo.obter(produto.id).quantidade, 0.0)

    def test_unidade_desconhecida_e_recusada(self) -> None:
        with self.assertRaises(EstoqueError):
            self._produto("X-1", unidade="DUZIA")

    def test_unidade_define_as_casas_decimais(self) -> None:
        from dumtech.apps.estoque.models import quantidade_texto

        self.assertEqual(quantidade_texto(2, "UN"), "2")
        self.assertEqual(quantidade_texto(1.5, "KG"), "1,500")
        self.assertEqual(quantidade_texto(1500.5, "M", com_unidade=True), "1.500,500 M")


class CustoMedioTestCase(BaseEstoque):
    def test_media_ponderada_das_entradas(self) -> None:
        produto = self._produto("SSD-1", quantidade=10, preco_custo=200.0)
        # 10 a 200 + 10 a 300 = 20 a 250
        self.repo.registrar_entrada(produto.id, 10, "Compra", custo_unitario=300.0)
        self.assertEqual(self.repo.obter(produto.id).preco_custo, 250.0)

    def test_entrada_sem_custo_nao_mexe_no_custo_medio(self) -> None:
        produto = self._produto("SSD-2", quantidade=10, preco_custo=200.0)
        self.repo.registrar_entrada(produto.id, 5, "Devolucao de cliente")
        self.assertEqual(self.repo.obter(produto.id).preco_custo, 200.0)

    def test_saida_nao_mexe_no_custo_medio(self) -> None:
        produto = self._produto("SSD-3", quantidade=10, preco_custo=200.0)
        self.repo.registrar_saida(produto.id, 4)
        self.assertEqual(self.repo.obter(produto.id).preco_custo, 200.0)

    def test_primeira_entrada_define_o_custo(self) -> None:
        produto = self._produto("SSD-4", quantidade=0)
        self.repo.registrar_entrada(produto.id, 5, custo_unitario=90.0)
        self.assertEqual(self.repo.obter(produto.id).preco_custo, 90.0)


class BuscaTestCase(BaseEstoque):
    def test_acha_por_barras_codigo_e_nome(self) -> None:
        produto = self._produto("MOU-9", nome="Mouse gamer", codigo_barras="7891234567895")
        self.assertEqual(self.repo.buscar("7891234567895").id, produto.id)
        self.assertEqual(self.repo.buscar("MOU-9").id, produto.id)
        self.assertEqual(self.repo.buscar("gamer").id, produto.id)
        self.assertIsNone(self.repo.buscar("nao existe"))

    def test_nome_ambiguo_nao_chuta_um_produto(self) -> None:
        self._produto("A-1", nome="Cabo HDMI")
        self._produto("A-2", nome="Cabo USB")
        self.assertIsNone(self.repo.buscar("Cabo"))

    def test_codigo_de_barras_repetido_e_recusado(self) -> None:
        self._produto("B-1", codigo_barras="789")
        with self.assertRaises(EstoqueError):
            self._produto("B-2", codigo_barras="789")

    def test_varios_produtos_podem_ficar_sem_codigo_de_barras(self) -> None:
        self._produto("C-1")
        self._produto("C-2")
        self.assertEqual(len(self.repo.listar()), 2)


class EntradaEmLoteTestCase(BaseEstoque):
    def test_grava_a_nota_inteira_de_uma_vez(self) -> None:
        a = self._produto("L-1")
        b = self._produto("L-2")
        self.repo.entrada_em_lote(
            [ItemEntrada(a.id, 10, 5.0), ItemEntrada(b.id, 3, 20.0)],
            fornecedor="Tech Distribuidora",
            documento="NF 1234",
        )
        self.assertEqual(self.repo.obter(a.id).quantidade, 10)
        self.assertEqual(self.repo.obter(b.id).quantidade, 3)
        self.assertEqual(self.repo.obter(a.id).preco_custo, 5.0)

        historico = self.repo.listar_movimentacoes(fornecedor="Tech Distribuidora")
        self.assertEqual(len(historico), 2)
        self.assertEqual(historico[0].documento, "NF 1234")

    def test_linha_invalida_nao_grava_nada(self) -> None:
        a = self._produto("L-3")
        with self.assertRaises(EstoqueError):
            self.repo.entrada_em_lote(
                [ItemEntrada(a.id, 10, 5.0), ItemEntrada(9999, 1, 1.0)]
            )
        self.assertEqual(self.repo.obter(a.id).quantidade, 0)

    def test_entrada_vazia_e_recusada(self) -> None:
        with self.assertRaises(EstoqueError):
            self.repo.entrada_em_lote([])

    def test_fornecedor_da_entrada_entra_no_autocompletar(self) -> None:
        a = self._produto("L-4")
        self.repo.entrada_em_lote([ItemEntrada(a.id, 1, 1.0)], fornecedor="Distribuidora Sul")
        self.assertIn("Distribuidora Sul", self.repo.fornecedores())


class ContagemTestCase(BaseEstoque):
    def test_ajusta_so_o_que_divergiu(self) -> None:
        certo = self._produto("CT-1", quantidade=10)
        errado = self._produto("CT-2", quantidade=10)

        self.repo.contar(certo.id, 10)   # confere
        self.repo.contar(errado.id, 7)   # faltaram 3
        self.assertEqual(self.repo.resumo_contagem(), (2, 1))

        ajustados = self.repo.aplicar_contagem("Balanco de agosto")
        self.assertEqual(ajustados, 1)
        self.assertEqual(self.repo.obter(certo.id).quantidade, 10)
        self.assertEqual(self.repo.obter(errado.id).quantidade, 7)
        self.assertFalse(self.repo.contagem_em_andamento())

        ajuste = self.repo.listar_movimentacoes(tipo="ajuste")[0]
        self.assertEqual(ajuste.observacao, "Balanco de agosto")
        self.assertEqual(ajuste.saldo_anterior, 10)
        self.assertEqual(ajuste.saldo_atual, 7)

    def test_contar_de_novo_substitui_o_valor(self) -> None:
        produto = self._produto("CT-4", quantidade=10)
        self.repo.contar(produto.id, 3)
        self.repo.contar(produto.id, 8)
        self.assertEqual(self.repo.contagem()[0].contado, 8)

    def test_cancelar_nao_mexe_no_saldo(self) -> None:
        produto = self._produto("CT-3", quantidade=10)
        self.repo.contar(produto.id, 2)
        self.repo.cancelar_contagem()
        self.assertEqual(self.repo.obter(produto.id).quantidade, 10)
        self.assertFalse(self.repo.contagem_em_andamento())

    def test_aplicar_folha_vazia_e_recusado(self) -> None:
        with self.assertRaises(EstoqueError):
            self.repo.aplicar_contagem()


class ReposicaoTestCase(BaseEstoque):
    def test_sugere_quanto_falta_para_o_maximo(self) -> None:
        self._produto("RE-1", quantidade=2, estoque_minimo=5, estoque_maximo=20)
        self._produto("RE-2", quantidade=1, estoque_minimo=4)
        por_codigo = {p.codigo: p for p in self.repo.a_comprar()}
        self.assertEqual(por_codigo["RE-1"].sugestao_compra, 18)  # 20 - 2
        self.assertEqual(por_codigo["RE-2"].sugestao_compra, 3)   # 4 - 1

    def test_maximo_menor_que_o_minimo_e_recusado(self) -> None:
        with self.assertRaises(EstoqueError):
            self._produto("RE-3", estoque_minimo=10, estoque_maximo=2)

    def test_inativo_fica_fora_da_reposicao(self) -> None:
        produto = self._produto("RE-4", quantidade=0, estoque_minimo=5)
        self.assertEqual(len(self.repo.a_comprar()), 1)
        self.repo.inativar(produto.id)
        self.assertEqual(self.repo.a_comprar(), [])

    def test_margem_e_valor_parado(self) -> None:
        produto = self._produto("MG-1", quantidade=4, preco_custo=60.0, preco_venda=100.0)
        self.assertEqual(produto.margem, 40.0)
        self.assertEqual(produto.valor_em_estoque, 240.0)

    def test_margem_desconhecida_quando_falta_preco(self) -> None:
        self.assertIsNone(self._produto("MG-2", preco_venda=100.0).margem)


class PlanilhaTestCase(BaseEstoque):
    def test_exportar_e_importar_de_volta(self) -> None:
        self._produto("EX-1", nome="Mouse", quantidade=4)
        texto = self.repo.exportar_produtos_csv()
        self.assertIn("EX-1", texto)

        outro, _ = _novo_repo()
        self.assertEqual(outro.importar(texto), (1, 0))
        self.assertEqual(outro.buscar_por_codigo("EX-1").nome, "Mouse")
        outro.db.close()

    def test_previa_conta_antes_de_gravar(self) -> None:
        antigo = self._produto("MOU-001", nome="Mouse antigo")
        planilha = (
            "codigo;nome;quantidade;preco_venda\n"
            "MOU-001;Mouse novo;5;59,90\n"   # atualiza
            "TEC-002;Teclado;2;120,00\n"     # cria
            ";Sem codigo;1;10,00\n"          # recusa: sem codigo
            "TEC-002;Repetido;1;10,00\n"     # recusa: repetido no arquivo
        )
        previa = self.repo.prever_importacao(planilha)
        self.assertEqual(len(previa.criar), 1)
        self.assertEqual(len(previa.atualizar), 1)
        self.assertEqual(len(previa.recusados), 2)
        self.assertEqual(self.repo.obter(antigo.id).nome, "Mouse antigo")

    def test_le_numero_brasileiro(self) -> None:
        self.repo.importar("codigo;nome;preco_venda\nP-1;Produto;1.234,56\n")
        self.assertEqual(self.repo.buscar_por_codigo("P-1").preco_venda, 1234.56)

    def test_aceita_o_cabecalho_que_o_cliente_tem(self) -> None:
        self.repo.importar("SKU;Produto;EAN;Qtd\nP-9;Cadeira;789123;7\n")
        produto = self.repo.buscar_por_codigo("P-9")
        self.assertEqual(produto.nome, "Cadeira")
        self.assertEqual(produto.codigo_barras, "789123")
        self.assertEqual(produto.quantidade, 7)

    def test_planilha_sem_as_colunas_obrigatorias_e_recusada(self) -> None:
        with self.assertRaises(EstoqueError):
            self.repo.prever_importacao("nome;preco\nMouse;10\n")

    def test_nao_sobrescreve_o_saldo_de_quem_ja_existe(self) -> None:
        """Quem manda no saldo e o historico de movimentacoes, nao um arquivo."""
        produto = self._produto("SD-1", nome="Mouse USB", quantidade=10)
        self.repo.importar("codigo;nome;quantidade\nSD-1;Mouse USB;999\n")
        self.assertEqual(self.repo.obter(produto.id).quantidade, 10)


class MigracaoTestCase(unittest.TestCase):
    """O banco de um cliente que ja usava a versao 1 nao pode perder nada."""

    def _banco_v1(self) -> Path:
        import sqlite3

        from dumtech.apps.estoque.database import MIGRATIONS

        arquivo = Path(tempfile.mkdtemp()) / "estoque.db"
        conn = sqlite3.connect(arquivo)
        conn.executescript(MIGRATIONS[0].statements[0])
        conn.execute(
            "INSERT INTO produtos (id, codigo, nome, descricao, categoria, quantidade,"
            " estoque_minimo, preco_custo, preco_venda, criado_em, atualizado_em)"
            " VALUES (1, 'MOU-001', 'Mouse USB', 'Sem fio', 'Perifericos', 12, 3,"
            " 25.9, 59.9, '2026-01-10T09:00:00', '2026-01-10T09:00:00')"
        )
        conn.execute(
            "INSERT INTO movimentacoes (id, produto_id, produto_codigo, produto_nome,"
            " tipo, quantidade, saldo_anterior, saldo_atual, observacao, criado_em)"
            " VALUES (1, 1, 'MOU-001', 'Mouse USB', 'entrada', 12, 0, 12,"
            " 'Estoque inicial', '2026-01-10T09:00:00')"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()
        return arquivo

    def test_v1_vira_v2_sem_perder_dados(self) -> None:
        arquivo = self._banco_v1()
        db = open_database(arquivo)
        self.addCleanup(db.close)
        from dumtech.apps.estoque.database import MIGRATIONS

        self.assertEqual(db.schema_version, MIGRATIONS[-1].version)  # v1 sobe ate a atual

        repo = EstoqueRepository(db)
        produto = repo.buscar_por_codigo("MOU-001")
        self.assertIsNotNone(produto)
        self.assertEqual(produto.id, 1)
        self.assertEqual(produto.nome, "Mouse USB")
        self.assertEqual(produto.descricao, "Sem fio")
        self.assertEqual(produto.categoria, "Perifericos")
        self.assertEqual(produto.quantidade, 12)
        self.assertEqual(produto.estoque_minimo, 3)
        self.assertEqual(produto.preco_custo, 25.9)
        self.assertEqual(produto.preco_venda, 59.9)
        self.assertEqual(produto.criado_em, "2026-01-10T09:00:00")

        # os campos novos chegam com padrao util, nao vazios
        self.assertEqual(produto.unidade, "UN")
        self.assertTrue(produto.ativo)
        self.assertEqual(produto.codigo_barras, "")

        # o historico continua ligado ao produto certo
        movimentacoes = repo.listar_movimentacoes()
        self.assertEqual(len(movimentacoes), 1)
        self.assertEqual(movimentacoes[0].produto_id, 1)
        self.assertEqual(movimentacoes[0].quantidade, 12)
        self.assertEqual(movimentacoes[0].observacao, "Estoque inicial")

    def test_banco_migrado_continua_funcionando(self) -> None:
        db = open_database(self._banco_v1())
        self.addCleanup(db.close)
        repo = EstoqueRepository(db)

        repo.registrar_saida(1, 2, "Venda")
        self.assertEqual(repo.obter(1).quantidade, 10)
        self.assertEqual(len(repo.listar_movimentacoes()), 2)


if __name__ == "__main__":
    unittest.main()
