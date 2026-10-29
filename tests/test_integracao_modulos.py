"""Os modulos conversando: o que nasce num lugar aparece no outro.

Quem compra o Hub inteiro espera que vender baixe o estoque, que a ordem
entregue vire dinheiro a receber e que a nota de compra vire dinheiro a pagar.
Cada teste aqui e uma dessas conversas.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from dumtech.apps.estoque.catalog import CatalogoEstoque
from dumtech.apps.estoque.database import open_database as abrir_estoque
from dumtech.apps.estoque.models import Produto
from dumtech.apps.estoque.repository import EstoqueRepository
from dumtech.apps.financeiro.contas import ContasFinanceiro
from dumtech.apps.financeiro.database import open_database as abrir_financeiro
from dumtech.apps.financeiro.models import DESPESA, RECEITA
from dumtech.apps.ordens.database import open_database as abrir_ordens
from dumtech.apps.ordens.models import CONCLUIDA, PECA, SERVICO, ItemOS, Ordem
from dumtech.apps.ordens.repository import OrdensRepository
from dumtech.core.contas import APagar, AReceber


def _pasta() -> Path:
    return Path(tempfile.mkdtemp())


class PonteBase(unittest.TestCase):
    def setUp(self) -> None:
        pasta = _pasta()
        self.db_estoque = abrir_estoque(pasta / "estoque.db")
        self.estoque = EstoqueRepository(self.db_estoque)
        self.catalogo = CatalogoEstoque(self.db_estoque)
        self.db_financeiro = abrir_financeiro(pasta / "financeiro.db")
        self.contas = ContasFinanceiro(self.db_financeiro)

    def tearDown(self) -> None:
        self.db_estoque.close()
        self.db_financeiro.close()

    def _produto(self, saldo: float = 10.0) -> Produto:
        return self.estoque.criar(Produto(
            codigo="FON-001", nome="Fonte 19V", quantidade=saldo,
            preco_custo=60.0, preco_venda=150.0,
        ))

    def _saldo(self, produto_id: int) -> float:
        return self.estoque.obter(produto_id).quantidade


class OrdemBaixaEstoqueTestCase(PonteBase):
    """Peca usada no conserto sai do estoque quando o aparelho e entregue."""

    def setUp(self) -> None:
        super().setUp()
        self.db_ordens = abrir_ordens(_pasta() / "ordens.db")
        self.ordens = OrdensRepository(self.db_ordens, catalogo=self.catalogo)

    def tearDown(self) -> None:
        self.db_ordens.close()
        super().tearDown()

    def _ordem_com_peca(self, produto, quantidade: float = 2.0) -> Ordem:
        return self.ordens.salvar(Ordem(
            numero=self.ordens.proximo_numero(), cliente="Maria",
            equipamento="Notebook", status=CONCLUIDA,
            itens=[
                ItemOS(tipo=PECA, descricao=produto.nome, quantidade=quantidade,
                       valor_unitario=150.0, produto_id=produto.id,
                       codigo=produto.codigo),
                ItemOS(tipo=SERVICO, descricao="Mao de obra", quantidade=1,
                       valor_unitario=80.0),
            ],
        ))

    def test_entregar_tira_a_peca_do_saldo(self) -> None:
        produto = self._produto(saldo=10)
        ordem = self._ordem_com_peca(produto, quantidade=2)
        self.ordens.entregar(ordem.id, "Maria")
        self.assertEqual(self._saldo(produto.id), 8)

    def test_o_servico_nao_mexe_no_estoque(self) -> None:
        """Mao de obra nao tem saldo para baixar."""
        produto = self._produto(saldo=10)
        ordem = self.ordens.salvar(Ordem(
            numero=self.ordens.proximo_numero(), cliente="Maria",
            equipamento="Notebook", status=CONCLUIDA,
            itens=[ItemOS(tipo=SERVICO, descricao="Limpeza", quantidade=1,
                          valor_unitario=80.0)],
        ))
        self.ordens.entregar(ordem.id, "Maria")
        self.assertEqual(self._saldo(produto.id), 10)

    def test_peca_digitada_a_mao_nao_baixa_nada(self) -> None:
        """Sem produto do catalogo, nao da para saber de qual saldo tirar."""
        produto = self._produto(saldo=10)
        ordem = self.ordens.salvar(Ordem(
            numero=self.ordens.proximo_numero(), cliente="Maria",
            equipamento="Notebook", status=CONCLUIDA,
            itens=[ItemOS(tipo=PECA, descricao="Parafuso avulso", quantidade=3,
                          valor_unitario=2.0)],
        ))
        self.ordens.entregar(ordem.id, "Maria")
        self.assertEqual(self._saldo(produto.id), 10)

    def test_a_baixa_nao_acontece_duas_vezes(self) -> None:
        """Reabrir e entregar de novo nao pode tirar a mesma peca outra vez."""
        produto = self._produto(saldo=10)
        ordem = self._ordem_com_peca(produto, quantidade=2)
        self.ordens.entregar(ordem.id, "Maria")
        self.db_ordens.execute("UPDATE ordens SET status = ? WHERE id = ?",
                               (CONCLUIDA, ordem.id))
        self.ordens.entregar(ordem.id, "Maria")
        self.assertEqual(self._saldo(produto.id), 8)

    def test_sem_estoque_a_entrega_acontece_igual(self) -> None:
        """Quem nao comprou o Estoque continua entregando ordens."""
        ordens = OrdensRepository(self.db_ordens, catalogo=None)
        ordem = ordens.salvar(Ordem(
            numero=ordens.proximo_numero(), cliente="Maria", equipamento="TV",
            status=CONCLUIDA,
            itens=[ItemOS(tipo=PECA, descricao="Placa", quantidade=1,
                          valor_unitario=300.0, produto_id=99)],
        ))
        entregue = ordens.entregar(ordem.id, "Maria")
        self.assertEqual(entregue.status, "entregue")
        self.assertEqual(entregue.avisos, [])

    def test_saldo_insuficiente_nao_segura_o_cliente(self) -> None:
        """O aparelho ja saiu pela porta: o erro vira recado, nao bloqueio."""
        produto = self._produto(saldo=1)
        ordem = self._ordem_com_peca(produto, quantidade=5)
        entregue = self.ordens.entregar(ordem.id, "Maria")
        self.assertEqual(entregue.status, "entregue")
        self.assertTrue(entregue.avisos)


class CompraViraContaAPagarTestCase(PonteBase):
    """A nota que entra no Estoque e dinheiro que vai sair do caixa."""

    def test_lancar_pagamento_cria_despesa(self) -> None:
        self.contas.lancar_pagamento(APagar(
            descricao="Compra NF 1234", valor=850.0,
            vencimento=date.today().isoformat(),
            fornecedor="Distribuidora Sul", documento="NF 1234",
        ))
        lancamentos = self.contas.repository.listar()
        self.assertEqual(len(lancamentos), 1)
        conta = lancamentos[0]
        self.assertEqual(conta.tipo, DESPESA)
        self.assertEqual(conta.valor, 850.0)
        self.assertEqual(conta.cliente, "Distribuidora Sul")
        self.assertEqual(conta.categoria, "Fornecedores")

    def test_a_mesma_nota_nao_vira_duas_dividas(self) -> None:
        self.contas.lancar_pagamento(APagar(
            descricao="Compra NF 77", valor=100.0,
            vencimento=date.today().isoformat(), documento="NF 77",
        ))
        self.assertTrue(self.contas.ja_lancado("NF 77"))

    def test_receber_e_pagar_convivem_na_mesma_ponte(self) -> None:
        self.contas.lancar(AReceber(descricao="Venda VEN-1", valor=50.0,
                                    vencimento=date.today().isoformat(),
                                    documento="VEN-1"))
        self.contas.lancar_pagamento(APagar(descricao="Compra NF 9", valor=30.0,
                                            vencimento=date.today().isoformat(),
                                            documento="NF 9"))
        tipos = sorted(lanc.tipo for lanc in self.contas.repository.listar())
        self.assertEqual(tipos, sorted([RECEITA, DESPESA]))


if __name__ == "__main__":
    unittest.main()


class OrcamentoLevaOProdutoTestCase(PonteBase):
    """Proposta aprovada vira venda ou ordem - e o estoque baixa de verdade.

    Era o furo achado no teste de cliente: a proposta guardava so o nome do
    produto, e nem a venda nem a ordem que nasciam dela davam baixa.
    """

    def setUp(self) -> None:
        super().setUp()
        from dumtech.apps.vendas.database import open_database as abrir_vendas
        from dumtech.apps.vendas.pedidos import DestinoVendas
        from dumtech.apps.vendas.repository import VendasRepository
        from dumtech.apps.ordens.pedidos import DestinoOrdens

        self.db_vendas = abrir_vendas(_pasta() / "vendas.db")
        self.destino_vendas = DestinoVendas(self.db_vendas)
        # o Vendas do cliente abre o proprio banco COM o catalogo
        self.vendas = VendasRepository(self.db_vendas, catalogo=self.catalogo)
        self.db_ordens = abrir_ordens(_pasta() / "ordens.db")
        self.destino_ordens = DestinoOrdens(self.db_ordens)
        self.ordens = OrdensRepository(self.db_ordens, catalogo=self.catalogo)
        self.fonte = self._produto(saldo=10)

    def tearDown(self) -> None:
        self.db_vendas.close()
        self.db_ordens.close()
        super().tearDown()

    def _pedido(self):
        from dumtech.core.pedidos import ItemPedido, Pedido
        return Pedido(cliente="Maria", origem="ORC-2026-0001", itens=[
            ItemPedido(descricao="Fonte 19V", quantidade=2, valor_unitario=150,
                       produto_id=self.fonte.id, codigo=self.fonte.codigo),
            ItemPedido(descricao="Mao de obra", quantidade=1, valor_unitario=80),
        ])

    def test_a_linha_da_proposta_guarda_o_produto(self) -> None:
        from dumtech.apps.orcamentos.database import open_database as abrir_orc
        from dumtech.apps.orcamentos.models import ItemOrcamento, Orcamento
        from dumtech.apps.orcamentos.repository import OrcamentosRepository
        db = abrir_orc(_pasta() / "orc.db")
        self.addCleanup(db.close)
        repo = OrcamentosRepository(db)
        salvo = repo.salvar(Orcamento(numero=repo.proximo_numero(), cliente="Maria", itens=[
            ItemOrcamento(descricao="Fonte 19V", quantidade=1, valor_unitario=150,
                          produto_id=self.fonte.id, codigo="FON-001")]))
        item = repo.obter(salvo.id).itens[0]
        self.assertEqual((item.produto_id, item.codigo), (self.fonte.id, "FON-001"))

    def test_proposta_vira_venda_e_o_recebimento_baixa_o_estoque(self) -> None:
        from dumtech.apps.vendas.models import Pagamento
        numero = self.destino_vendas.abrir(self._pedido())
        venda = [v for v in self.vendas.listar() if v.numero == numero][0]
        self.assertEqual(self._saldo(self.fonte.id), 10)          # pendente: ainda nao saiu
        self.vendas.receber_pendente(venda.id, [Pagamento(forma="Pix", valor=venda.total)])
        self.assertEqual(self._saldo(self.fonte.id), 8)

    def test_venda_a_prazo_do_balcao_nao_baixa_duas_vezes(self) -> None:
        from dumtech.apps.vendas.models import ItemVenda, Pagamento, Venda
        venda = self.vendas.finalizar(Venda(cliente="Joao", itens=[
            ItemVenda(descricao="Fonte 19V", quantidade=1, valor_unitario=150,
                      produto_id=self.fonte.id, codigo=self.fonte.codigo)]),
            [Pagamento(forma="Prazo", valor=150)])
        self.assertEqual(self._saldo(self.fonte.id), 9)           # saiu no balcao
        self.vendas.receber_pendente(venda.id, [Pagamento(forma="Dinheiro", valor=150, recebido=150)])
        self.assertEqual(self._saldo(self.fonte.id), 9)           # e nao sai de novo

    def test_venda_lancada_a_mao_ja_paga_baixa_o_estoque(self) -> None:
        from dumtech.apps.vendas.models import CONCLUIDA as PAGA
        from dumtech.apps.vendas.models import ItemVenda, Venda
        venda = self.vendas.lancar(Venda(
            numero=self.vendas.proximo_numero(), cliente="Joao", status=PAGA,
            itens=[ItemVenda(descricao="Fonte 19V", quantidade=2, valor_unitario=150,
                             produto_id=self.fonte.id, codigo=self.fonte.codigo)]))
        self.assertEqual(self._saldo(self.fonte.id), 8)
        # salvar de novo (editar a observacao, por exemplo) nao tira outra vez
        self.vendas.lancar(venda)
        self.assertEqual(self._saldo(self.fonte.id), 8)
        # e cancelar devolve exatamente o que saiu
        self.vendas.cancelar(venda.id, "teste")
        self.assertEqual(self._saldo(self.fonte.id), 10)

    def test_venda_lancada_a_mao_pendente_so_baixa_ao_receber(self) -> None:
        from dumtech.apps.vendas.models import PENDENTE, ItemVenda, Pagamento, Venda
        venda = self.vendas.lancar(Venda(
            numero=self.vendas.proximo_numero(), cliente="Joao", status=PENDENTE,
            itens=[ItemVenda(descricao="Fonte 19V", quantidade=1, valor_unitario=150,
                             produto_id=self.fonte.id, codigo=self.fonte.codigo)]))
        self.assertEqual(self._saldo(self.fonte.id), 10)
        self.vendas.receber_pendente(venda.id, [Pagamento(forma="Pix", valor=150)])
        self.assertEqual(self._saldo(self.fonte.id), 9)

    def test_proposta_vira_ordem_com_a_peca_do_estoque(self) -> None:
        numero = self.destino_ordens.abrir(self._pedido())
        ordem = [o for o in self.ordens.listar() if o.numero == numero][0]
        fonte = [i for i in ordem.itens if i.descricao == "Fonte 19V"][0]
        mao = [i for i in ordem.itens if i.descricao == "Mao de obra"][0]
        self.assertTrue(fonte.e_peca and fonte.produto_id == self.fonte.id)
        self.assertFalse(mao.e_peca)
        self.ordens.definir_status(ordem.id, CONCLUIDA)
        self.ordens.entregar(ordem.id, "Maria")
        self.assertEqual(self._saldo(self.fonte.id), 8)


class EntregaRegistraPagamentoTestCase(PonteBase):
    """Entregar a ordem ja resolve o dinheiro - sem segundo botao."""

    def setUp(self) -> None:
        super().setUp()
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        self.db_ordens = abrir_ordens(_pasta() / "ordens.db")
        self.ordens = OrdensRepository(self.db_ordens)
        self.ordem = self.ordens.salvar(Ordem(
            numero=self.ordens.proximo_numero(), cliente="Maria", equipamento="Notebook",
            status=CONCLUIDA, valor=300.0))

    def tearDown(self) -> None:
        self.db_ordens.close()
        super().tearDown()

    def _janela(self, contas):
        from dumtech.apps.ordens.ui.dialogos import EntregaDialog
        janela = EntregaDialog(self.ordens, self.ordem, contas=contas)
        self.addCleanup(janela.deleteLater)
        return janela

    def _conta(self):
        contas = [l for l in self.contas.repository.listar() if self.ordem.numero in l.descricao]
        self.assertEqual(len(contas), 1)
        return contas[0]

    def test_pagou_agora_entra_no_caixa_ja_recebido(self) -> None:
        janela = self._janela(self.contas)
        janela.situacao.setCurrentIndex(janela.situacao.findData(janela.PAGOU))
        janela.salvar()
        conta = self._conta()
        self.assertEqual(conta.tipo, RECEITA)
        self.assertEqual(conta.valor, 300.0)
        self.assertTrue(conta.pago)
        self.assertIn("caixa", janela.recado_financeiro)

    def test_vai_pagar_depois_vira_conta_a_receber(self) -> None:
        from PySide6.QtCore import QDate
        janela = self._janela(self.contas)
        janela.situacao.setCurrentIndex(janela.situacao.findData(janela.DEPOIS))
        janela.vencimento.setDate(QDate.currentDate().addDays(15))
        janela.salvar()
        conta = self._conta()
        self.assertFalse(conta.pago)
        self.assertEqual(conta.vencimento, QDate.currentDate().addDays(15).toString("yyyy-MM-dd"))

    def test_o_qr_so_aparece_para_quem_paga_em_pix_agora(self) -> None:
        janela = self._janela(self.contas)
        janela.show()
        janela.situacao.setCurrentIndex(janela.situacao.findData(janela.PAGOU))
        janela.forma.setCurrentIndex(janela.forma.findData("Pix"))
        self.assertTrue(janela.painel_pix.isVisible())
        janela.forma.setCurrentIndex(janela.forma.findData("Dinheiro"))
        self.assertFalse(janela.painel_pix.isVisible())
        janela.situacao.setCurrentIndex(janela.situacao.findData(janela.DEPOIS))
        self.assertFalse(janela.painel_pix.isVisible())

    def test_entregar_de_novo_nao_duplica_a_conta(self) -> None:
        janela = self._janela(self.contas)
        janela.salvar()
        self.db_ordens.execute("UPDATE ordens SET status = ? WHERE id = ?", (CONCLUIDA, self.ordem.id))
        self._janela(self.contas).salvar()
        self._conta()

    def test_sem_financeiro_a_entrega_e_a_de_sempre(self) -> None:
        janela = self._janela(None)
        self.assertIsNone(janela.situacao)
        janela.salvar()
        self.assertEqual(self.ordens.obter(self.ordem.id).status, "entregue")
