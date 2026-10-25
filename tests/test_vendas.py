"""Regras do PDV: pagamento, troco, caixa do dia, devolucao e a ponte do estoque."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from dumtech.apps.vendas.database import MIGRATIONS, open_database
from dumtech.apps.vendas.models import (
    CANCELADA,
    CONCLUIDA,
    DEVOLVIDA,
    PENDENTE,
    ItemVenda,
    Pagamento,
    Venda,
    VendaError,
)
from dumtech.apps.vendas.repository import VendasRepository, pagamento_unico
from dumtech.core.errors import RegraError


def _arquivo(nome: str) -> Path:
    return Path(tempfile.mkdtemp()) / nome


class CatalogoFake:
    """Um estoque de mentira, para provar o que a venda pede a ele."""

    def __init__(self, saldos: dict[int, float] | None = None) -> None:
        self.saldos = saldos or {}
        self.chamadas: list[tuple[str, int, float]] = []

    def buscar(self, termo: str):
        return None

    def procurar(self, termo: str, limite: int = 20):
        return []

    def baixar(self, produto_id, quantidade, documento="", motivo="") -> None:
        saldo = self.saldos.get(produto_id, 0.0)
        if quantidade > saldo:
            raise RegraError(f"Estoque insuficiente (saldo {saldo}).")
        self.saldos[produto_id] = saldo - quantidade
        self.chamadas.append(("baixar", produto_id, quantidade))

    def devolver(self, produto_id, quantidade, documento="", motivo="") -> None:
        self.saldos[produto_id] = self.saldos.get(produto_id, 0.0) + quantidade
        self.chamadas.append(("devolver", produto_id, quantidade))


class VendasBase(unittest.TestCase):
    catalogo = None

    def setUp(self) -> None:
        self.db = open_database(_arquivo("vendas.db"))
        self.repo = VendasRepository(self.db, catalogo=self.catalogo)

    def tearDown(self) -> None:
        self.db.close()

    def _itens(self, *linhas) -> list[ItemVenda]:
        """(descricao, quantidade, valor) ou (descricao, quantidade, valor, produto_id)."""
        itens = []
        for linha in linhas:
            descricao, qtd, valor = linha[:3]
            produto_id = linha[3] if len(linha) > 3 else 0
            itens.append(
                ItemVenda(
                    descricao=descricao,
                    quantidade=qtd,
                    valor_unitario=valor,
                    produto_id=produto_id,
                )
            )
        return itens

    def _vender(self, itens=None, pagamentos=None, desconto=0.0, **campos) -> Venda:
        venda = Venda(
            itens=itens or self._itens(("Produto", 2, 25.0)),
            desconto=desconto,
            **campos,
        )
        return self.repo.finalizar(
            venda, pagamentos or [pagamento_unico("Dinheiro", venda.total)]
        )


class PagamentoTestCase(VendasBase):
    def test_venda_simples_em_dinheiro(self) -> None:
        venda = self._vender()
        self.assertEqual(venda.total, 50.0)
        self.assertEqual(venda.status, CONCLUIDA)
        self.assertEqual(venda.numero, "VEN-2026-0001")
        self.assertEqual(self.repo.obter(venda.id).pago, 50.0)

    def test_troco_sai_do_que_a_pessoa_entregou(self) -> None:
        venda = self._vender(
            pagamentos=[Pagamento(forma="Dinheiro", valor=50.0, recebido=100.0)]
        )
        self.assertEqual(venda.troco, 50.0)
        self.assertEqual(self.repo.obter(venda.id).troco, 50.0)

    def test_duas_formas_na_mesma_venda(self) -> None:
        venda = self._vender(
            pagamentos=[
                Pagamento(forma="Pix", valor=30.0),
                Pagamento(forma="Dinheiro", valor=20.0, recebido=20.0),
            ]
        )
        salva = self.repo.obter(venda.id)
        self.assertEqual(len(salva.pagamentos), 2)
        self.assertEqual(salva.pago, 50.0)
        self.assertEqual(salva.troco, 0.0)
        # a lista mostra as duas formas sem precisar abrir a venda
        self.assertEqual(salva.forma_pagamento, "Pix + Dinheiro")

    def test_pagamento_que_nao_cobre_e_recusado(self) -> None:
        with self.assertRaises(VendaError) as erro:
            self._vender(pagamentos=[pagamento_unico("Pix", 30.0)])
        self.assertIn("Falta receber", str(erro.exception))

    def test_pagar_a_mais_no_cartao_nao_e_troco(self) -> None:
        with self.assertRaises(VendaError) as erro:
            self._vender(pagamentos=[pagamento_unico("Pix", 80.0)])
        self.assertIn("passou do total", str(erro.exception))

    def test_venda_sem_pagamento_e_recusada(self) -> None:
        with self.assertRaises(VendaError):
            self.repo.finalizar(Venda(itens=self._itens(("Produto", 1, 10.0))), [])

    def test_valor_quebrado_fecha_no_centavo(self) -> None:
        """3 x 3,333 da 9,999: o cliente paga 10,00 e a venda fecha."""
        venda = Venda(itens=self._itens(("Item", 3, 3.333)))
        self.assertEqual(venda.total, 10.0)
        finalizada = self.repo.finalizar(venda, [pagamento_unico("Pix", 10.0)])
        self.assertEqual(finalizada.status, CONCLUIDA)

    def test_venda_a_prazo_fica_pendente_ate_o_cliente_pagar(self) -> None:
        venda = self._vender(pagamentos=[pagamento_unico("Prazo", 50.0)])
        self.assertEqual(venda.status, PENDENTE)

        paga = self.repo.receber_pendente(
            venda.id, [Pagamento(forma="Dinheiro", valor=50.0, recebido=50.0)]
        )
        self.assertEqual(paga.status, CONCLUIDA)
        self.assertEqual(paga.forma_pagamento, "Dinheiro")

    def test_numero_continua_da_maior_numeracao(self) -> None:
        self._vender()
        self._vender()
        self.assertEqual(self.repo.proximo_numero(), "VEN-2026-0003")


class CancelamentoTestCase(VendasBase):
    def test_cancelamento_exige_motivo(self) -> None:
        venda = self._vender()
        with self.assertRaises(VendaError):
            self.repo.cancelar(venda.id, "   ")

    def test_cancelamento_guarda_o_motivo_e_sai_das_contas(self) -> None:
        venda = self._vender()
        self.repo.cancelar(venda.id, "Cliente desistiu")

        salva = self.repo.obter(venda.id)
        self.assertEqual(salva.status, CANCELADA)
        self.assertEqual(salva.motivo_cancelamento, "Cliente desistiu")
        self.assertTrue(salva.cancelada_em)
        self.assertFalse(salva.conta)
        self.assertEqual(self.repo.resumo().vendas_mes, 0)

    def test_nao_cancela_duas_vezes(self) -> None:
        venda = self._vender()
        self.repo.cancelar(venda.id, "Erro de operacao")
        with self.assertRaises(VendaError):
            self.repo.cancelar(venda.id, "De novo")

    def test_venda_concluida_nao_pode_ser_apagada(self) -> None:
        venda = self._vender()
        with self.assertRaises(VendaError):
            self.repo.excluir(venda.id)

        self.repo.cancelar(venda.id, "Erro de operacao")
        self.repo.excluir(venda.id)  # cancelada, ai sim
        self.assertIsNone(self.repo.obter(venda.id))


class DevolucaoTestCase(VendasBase):
    def _venda_com_dois_itens(self) -> Venda:
        return self._vender(
            itens=self._itens(("Camisa", 2, 50.0), ("Meia", 1, 10.0)),
            pagamentos=[pagamento_unico("Dinheiro", 110.0)],
        )

    def test_devolucao_parcial_nao_muda_a_venda_original(self) -> None:
        venda = self._venda_com_dois_itens()
        camisa = venda.itens[0]

        devolucao = self.repo.devolver(venda.id, [(camisa.id, 1)], "Tamanho errado")
        self.assertEqual(devolucao.valor, 50.0)

        salva = self.repo.obter(venda.id)
        self.assertEqual(salva.total, 110.0)          # o que foi vendido nao muda
        self.assertEqual(salva.devolvido, 50.0)
        self.assertEqual(salva.total_liquido, 60.0)
        self.assertEqual(salva.status, CONCLUIDA)     # ainda tem mercadoria com o cliente
        self.assertEqual(salva.itens[0].restante, 1.0)

    def test_devolver_tudo_marca_a_venda_como_devolvida(self) -> None:
        venda = self._venda_com_dois_itens()
        linhas = [(item.id, item.quantidade) for item in venda.itens]
        self.repo.devolver(venda.id, linhas, "Cliente desistiu")
        self.assertEqual(self.repo.obter(venda.id).status, DEVOLVIDA)

    def test_nao_devolve_mais_do_que_foi_vendido(self) -> None:
        venda = self._venda_com_dois_itens()
        camisa = venda.itens[0]
        self.repo.devolver(venda.id, [(camisa.id, 1)])
        with self.assertRaises(VendaError) as erro:
            self.repo.devolver(venda.id, [(camisa.id, 2)])
        self.assertIn("só restam", str(erro.exception))

    def test_devolucao_devolve_o_que_o_cliente_pagou_nao_o_preco_cheio(self) -> None:
        """Venda de 100 com 10 de desconto: devolver metade volta 45, nao 50."""
        venda = self._vender(
            itens=self._itens(("Item", 2, 50.0)),
            desconto=10.0,
            pagamentos=[pagamento_unico("Dinheiro", 90.0)],
        )
        devolucao = self.repo.devolver(venda.id, [(venda.itens[0].id, 1)])
        self.assertEqual(devolucao.valor, 45.0)

    def test_devolucao_vazia_e_recusada(self) -> None:
        venda = self._venda_com_dois_itens()
        with self.assertRaises(VendaError):
            self.repo.devolver(venda.id, [(venda.itens[0].id, 0)])

    def test_venda_com_devolucao_nao_pode_mais_ser_editada(self) -> None:
        venda = self._venda_com_dois_itens()
        self.repo.devolver(venda.id, [(venda.itens[0].id, 1)])

        salva = self.repo.obter(venda.id)
        salva.cliente = "Outro nome"
        with self.assertRaises(VendaError):
            self.repo.salvar(salva)


class CaixaTestCase(VendasBase):
    def test_venda_sem_caixa_aberto_e_permitida(self) -> None:
        venda = self._vender()
        self.assertEqual(venda.caixa_id, 0)
        self.assertIsNone(self.repo.caixa_aberto())

    def test_nao_abre_dois_caixas(self) -> None:
        self.repo.abrir_caixa(200.0)
        with self.assertRaises(VendaError):
            self.repo.abrir_caixa(100.0)

    def test_venda_entra_no_caixa_aberto(self) -> None:
        caixa = self.repo.abrir_caixa(100.0)
        venda = self._vender()
        self.assertEqual(venda.caixa_id, caixa.id)
        self.assertEqual(self.repo.conferencia().quantidade_vendas, 1)

    def test_sangria_exige_motivo_e_caixa_aberto(self) -> None:
        with self.assertRaises(VendaError):
            self.repo.sangria(50.0, "Pagamento de entrega")  # sem caixa aberto

        self.repo.abrir_caixa(100.0)
        with self.assertRaises(VendaError):
            self.repo.sangria(50.0, "  ")
        with self.assertRaises(VendaError):
            self.repo.sangria(0, "Motivo valido")

    def test_a_conta_da_gaveta(self) -> None:
        self.repo.abrir_caixa(100.0)
        # 50 em dinheiro, cliente deu 100 -> 50 de troco
        self._vender(pagamentos=[Pagamento(forma="Dinheiro", valor=50.0, recebido=100.0)])
        # 50 no Pix: nao encosta na gaveta
        self._vender(pagamentos=[pagamento_unico("Pix", 50.0)])
        self.repo.sangria(30.0, "Deposito no banco")
        self.repo.suprimento(20.0, "Troco extra")

        conferencia = self.repo.conferencia()
        self.assertEqual(conferencia.abertura, 100.0)
        self.assertEqual(conferencia.vendas_dinheiro, 50.0)
        self.assertEqual(conferencia.trocos, 50.0)
        self.assertEqual(conferencia.sangrias, 30.0)
        self.assertEqual(conferencia.suprimentos, 20.0)
        self.assertEqual(conferencia.total_vendido, 100.0)
        # 100 + 50 - 50 + 20 - 30
        self.assertEqual(conferencia.esperado, 90.0)
        self.assertEqual(dict(conferencia.por_forma), {"Dinheiro": 50.0, "Pix": 50.0})

    def test_venda_cancelada_sai_da_conta_do_caixa(self) -> None:
        self.repo.abrir_caixa(0.0)
        venda = self._vender(pagamentos=[pagamento_unico("Dinheiro", 50.0)])
        self.assertEqual(self.repo.conferencia().esperado, 50.0)

        self.repo.cancelar(venda.id, "Erro de operacao")
        conferencia = self.repo.conferencia()
        self.assertEqual(conferencia.quantidade_vendas, 0)
        self.assertEqual(conferencia.esperado, 0.0)

    def test_devolucao_tira_dinheiro_da_gaveta(self) -> None:
        self.repo.abrir_caixa(0.0)
        venda = self._vender(pagamentos=[pagamento_unico("Dinheiro", 50.0)])
        self.repo.devolver(venda.id, [(venda.itens[0].id, 1)], "Defeito")
        self.assertEqual(self.repo.conferencia().esperado, 25.0)

    def test_fechamento_grava_a_diferenca(self) -> None:
        self.repo.abrir_caixa(100.0)
        self._vender(pagamentos=[pagamento_unico("Dinheiro", 50.0)])

        conferencia = self.repo.fechar_caixa(148.0, "Faltaram 2 reais")
        self.assertEqual(conferencia.esperado, 150.0)
        self.assertEqual(conferencia.caixa.diferenca, -2.0)
        self.assertFalse(conferencia.caixa.aberto)
        self.assertIsNone(self.repo.caixa_aberto())

        # com o caixa fechado da para abrir outro
        self.repo.abrir_caixa(50.0)
        self.assertIsNotNone(self.repo.caixa_aberto())

    def test_fechar_sem_caixa_aberto_avisa(self) -> None:
        with self.assertRaises(VendaError):
            self.repo.fechar_caixa(100.0)


class PonteDoEstoqueTestCase(VendasBase):
    """A venda so mexe no estoque quando o item veio do catalogo."""

    def setUp(self) -> None:
        super().setUp()
        self.catalogo = CatalogoFake({7: 10.0})
        self.repo.catalogo = self.catalogo

    def test_sem_catalogo_a_venda_funciona_igual(self) -> None:
        self.repo.catalogo = None
        venda = self._vender(itens=self._itens(("Texto livre", 1, 10.0)))
        self.assertEqual(venda.status, CONCLUIDA)
        self.assertEqual(venda.avisos, [])

    def test_item_do_catalogo_da_baixa(self) -> None:
        self._vender(itens=self._itens(("Produto do estoque", 3, 10.0, 7)))
        self.assertEqual(self.catalogo.saldos[7], 7.0)
        self.assertEqual(self.catalogo.chamadas, [("baixar", 7, 3.0)])

    def test_item_de_texto_livre_nao_encosta_no_estoque(self) -> None:
        self._vender(itens=self._itens(("Servico de instalacao", 1, 30.0)))
        self.assertEqual(self.catalogo.chamadas, [])

    def test_estoque_errado_nao_faz_perder_a_venda(self) -> None:
        """O cliente esta com o dinheiro na mao: quem esta errado e o cadastro."""
        venda = self._vender(
            itens=self._itens(("Produto do estoque", 99, 1.0, 7)),
            pagamentos=[pagamento_unico("Dinheiro", 99.0)],
        )
        self.assertEqual(venda.status, CONCLUIDA)
        self.assertIsNotNone(self.repo.obter(venda.id))
        self.assertEqual(len(venda.avisos), 1)
        self.assertIn("Estoque insuficiente", venda.avisos[0])

    def test_cancelamento_devolve_ao_estoque(self) -> None:
        venda = self._vender(itens=self._itens(("Produto do estoque", 3, 10.0, 7)))
        self.repo.cancelar(venda.id, "Cliente desistiu")
        self.assertEqual(self.catalogo.saldos[7], 10.0)

    def test_devolucao_devolve_so_o_que_voltou(self) -> None:
        venda = self._vender(itens=self._itens(("Produto do estoque", 3, 10.0, 7)))
        self.repo.devolver(venda.id, [(venda.itens[0].id, 1)], "Defeito")
        self.assertEqual(self.catalogo.saldos[7], 8.0)

    def test_cancelar_depois_da_devolucao_nao_devolve_em_dobro(self) -> None:
        venda = self._vender(itens=self._itens(("Produto do estoque", 3, 10.0, 7)))
        self.repo.devolver(venda.id, [(venda.itens[0].id, 1)], "Defeito")
        self.repo.cancelar(venda.id, "Cliente desistiu do resto")
        self.assertEqual(self.catalogo.saldos[7], 10.0)


class CatalogoEstoqueTestCase(unittest.TestCase):
    """A ponte de verdade, contra o banco do DumTech Estoque."""

    def setUp(self) -> None:
        from dumtech.apps.estoque.catalog import abrir_catalogo
        from dumtech.apps.estoque.models import Produto

        self.catalogo = abrir_catalogo(_arquivo("estoque.db"))
        self.produto = self.catalogo.repository.criar(
            Produto(
                codigo="CAM-01",
                nome="Camisa polo",
                quantidade=10,
                preco_venda=79.9,
                codigo_barras="7890000000123",
                unidade="UN",
            )
        )
        self.db = open_database(_arquivo("vendas.db"))
        self.repo = VendasRepository(self.db, catalogo=self.catalogo)

    def tearDown(self) -> None:
        self.db.close()
        self.catalogo.close()

    def test_bipar_o_codigo_de_barras_traz_o_produto(self) -> None:
        item = self.catalogo.buscar("7890000000123")
        self.assertEqual(item.produto_id, self.produto.id)
        self.assertEqual(item.nome, "Camisa polo")
        self.assertEqual(item.preco, 79.9)
        self.assertEqual(item.saldo, 10.0)
        self.assertEqual(item.rotulo, "CAM-01 - Camisa polo")

    def test_vender_baixa_o_estoque_de_verdade(self) -> None:
        item = self.catalogo.buscar("CAM-01")
        venda = Venda(
            itens=[
                ItemVenda(
                    descricao=item.nome,
                    quantidade=2,
                    valor_unitario=item.preco,
                    produto_id=item.produto_id,
                    codigo=item.codigo,
                    unidade=item.unidade,
                    casas=item.casas,
                )
            ]
        )
        venda = self.repo.finalizar(venda, [pagamento_unico("Dinheiro", venda.total)])

        self.assertEqual(venda.avisos, [])
        self.assertEqual(self.catalogo.buscar("CAM-01").saldo, 8.0)

        # a baixa deixou historico no Estoque, com o numero da venda
        movimento = self.catalogo.repository.listar_movimentacoes(limite=1)[0]
        self.assertEqual(movimento.tipo, "saida")
        self.assertEqual(movimento.documento, venda.numero)

    def test_produto_por_quilo_vende_com_casas_decimais(self) -> None:
        from dumtech.apps.estoque.models import Produto

        self.catalogo.repository.criar(
            Produto(codigo="CAR-01", nome="Carne", quantidade=20, unidade="KG",
                    preco_venda=40.0)
        )
        item = self.catalogo.buscar("CAR-01")
        self.assertEqual(item.casas, 3)

        venda = Venda(
            itens=[
                ItemVenda(
                    descricao=item.nome, quantidade=1.25, valor_unitario=item.preco,
                    produto_id=item.produto_id, unidade="KG", casas=3,
                )
            ]
        )
        venda = self.repo.finalizar(venda, [pagamento_unico("Dinheiro", 50.0)])
        self.assertEqual(venda.total, 50.0)
        self.assertEqual(self.repo.obter(venda.id).itens[0].quantidade_texto, "1,250 KG")
        self.assertEqual(self.catalogo.buscar("CAR-01").saldo, 18.75)


class MigracaoTestCase(unittest.TestCase):
    """Quem ja vendia na versao 1 nao pode perder venda nenhuma."""

    def test_v1_vira_v2_mantendo_as_vendas(self) -> None:
        arquivo = _arquivo("vendas.db")
        conn = sqlite3.connect(arquivo)
        conn.executescript(MIGRATIONS[0].statements[0])
        hoje = date.today().isoformat()
        conn.execute(
            "INSERT INTO vendas (id, numero, cliente, data, forma_pagamento, status,"
            " desconto, observacoes, criado_em) VALUES (1, 'VEN-2025-0001', 'Maria',"
            f" '{hoje}', 'Pix', 'concluida', 5.0, 'Venda antiga', '{hoje}T10:00:00')"
        )
        conn.execute(
            "INSERT INTO venda_itens (id, venda_id, descricao, quantidade, valor_unitario)"
            " VALUES (1, 1, 'Produto antigo', 3, 20.0)"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        db = open_database(arquivo)
        self.addCleanup(db.close)
        repo = VendasRepository(db)
        self.assertEqual(db.schema_version, MIGRATIONS[-1].version)

        venda = repo.obter(1)
        self.assertEqual(venda.numero, "VEN-2025-0001")
        self.assertEqual(venda.cliente, "Maria")
        self.assertEqual(venda.subtotal, 60.0)
        self.assertEqual(venda.total, 55.0)
        self.assertEqual(venda.observacoes, "Venda antiga")
        # campos novos chegam com padrao util
        self.assertEqual(venda.caixa_id, 0)
        self.assertEqual(venda.troco, 0.0)
        self.assertEqual(venda.pagamentos, [])
        self.assertEqual(venda.itens[0].unidade, "UN")
        self.assertEqual(venda.itens[0].produto_id, 0)
        # a venda antiga ainda aparece nos totais, pela forma gravada nela
        self.assertEqual(dict(repo.resumo().por_forma), {"Pix": 55.0})

        # e o banco migrado continua vendendo
        nova = repo.finalizar(
            Venda(itens=[ItemVenda(descricao="Novo", quantidade=1, valor_unitario=10.0)]),
            [pagamento_unico("Dinheiro", 10.0)],
        )
        self.assertEqual(nova.status, CONCLUIDA)


if __name__ == "__main__":
    unittest.main()
