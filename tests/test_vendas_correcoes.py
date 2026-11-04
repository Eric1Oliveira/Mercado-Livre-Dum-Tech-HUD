"""Os erros de dinheiro e estoque que a auditoria provou, cada um com a sua conta."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dumtech.apps.estoque.catalog import CatalogoEstoque
from dumtech.apps.estoque.database import open_database as abrir_estoque
from dumtech.apps.estoque.models import Produto
from dumtech.apps.estoque.repository import EstoqueRepository
from dumtech.apps.financeiro.contas import abrir_contas, ligar_modulos
from dumtech.apps.financeiro.database import open_database as abrir_financeiro
from dumtech.apps.financeiro.repository import FinanceiroRepository
from dumtech.apps.vendas import financeiro
from dumtech.apps.vendas.database import MIGRATIONS, open_database
from dumtech.apps.vendas.models import (
    CONCLUIDA,
    PENDENTE,
    ItemVenda,
    Pagamento,
    Venda,
    VendaError,
)
from dumtech.apps.vendas.pedidos import DestinoVendas
from dumtech.apps.vendas.repository import VendasRepository, pagamento_unico
from dumtech.core.database import Database
from dumtech.core.pedidos import ItemPedido, Pedido, precos_fechados

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class Base(unittest.TestCase):
    def setUp(self) -> None:
        pasta = Path(tempfile.mkdtemp(prefix="dt_vc_"))
        self.pasta = pasta
        self.banco = open_database(pasta / "vendas.db")
        self.addCleanup(self.banco.close)
        banco_estoque = abrir_estoque(pasta / "estoque.db")
        self.addCleanup(banco_estoque.close)
        self.estoque = EstoqueRepository(banco_estoque)
        self.catalogo = CatalogoEstoque(banco_estoque)
        self.repo = VendasRepository(self.banco, catalogo=self.catalogo)
        self.contas = abrir_contas(pasta / "financeiro.db")
        self.addCleanup(self.contas.close)

    def produto(self, saldo: float = 10.0, preco: float = 50.0) -> Produto:
        return self.estoque.criar(Produto(
            codigo=f"P{self.estoque.db.scalar('SELECT COUNT(*) FROM produtos') + 1}",
            nome="Produto", quantidade=saldo, preco_venda=preco,
        ))

    def item(self, produto: Produto, quantidade: float = 1.0) -> ItemVenda:
        return ItemVenda(descricao=produto.nome, quantidade=quantidade,
                         valor_unitario=produto.preco_venda, produto_id=produto.id)

    def saldo(self, produto: Produto) -> float:
        return self.estoque.obter(produto.id).quantidade


class CaixaTestCase(Base):
    def test_troco_nao_e_descontado_duas_vezes(self) -> None:
        self.repo.abrir_caixa(100.0)
        self.repo.finalizar(
            Venda(itens=[ItemVenda(descricao="x", valor_unitario=50.0)]),
            [Pagamento(forma="Dinheiro", valor=50.0, recebido=100.0)],
        )
        # entrou a nota de 100 e saiu 50 de troco: a gaveta tem 150
        self.assertEqual(self.repo.conferencia().esperado, 150.0)
        fechado = self.repo.fechar_caixa(150.0)
        self.assertEqual(fechado.caixa.diferenca, 0.0)

    def test_venda_lancada_hoje_entra_na_gaveta(self) -> None:
        self.repo.abrir_caixa(0.0)
        self.repo.lancar(Venda(
            numero="V1", itens=[ItemVenda(descricao="x", valor_unitario=80.0)],
            pagamentos=[pagamento_unico("Dinheiro", 80.0)],
        ))
        self.assertEqual(self.repo.conferencia().esperado, 80.0)

    def test_venda_lancada_com_data_passada_nao_entra(self) -> None:
        self.repo.abrir_caixa(0.0)
        ontem = (date.today() - timedelta(days=1)).isoformat()
        self.repo.lancar(Venda(
            numero="V1", data=ontem, itens=[ItemVenda(descricao="x", valor_unitario=80.0)],
            pagamentos=[pagamento_unico("Dinheiro", 80.0)],
        ))
        self.assertEqual(self.repo.conferencia().esperado, 0.0)

    def test_devolucao_de_venda_no_pix_nao_tira_da_gaveta(self) -> None:
        self.repo.abrir_caixa(0.0)
        venda = self.repo.finalizar(
            Venda(itens=[ItemVenda(descricao="x", valor_unitario=50.0)]),
            [pagamento_unico("Pix", 50.0)],
        )
        self.repo.devolver(venda.id, [(venda.itens[0].id, 1)])
        self.assertEqual(self.repo.conferencia().esperado, 0.0)

    def test_devolucao_de_venda_mista_tira_so_o_que_entrou_em_dinheiro(self) -> None:
        self.repo.abrir_caixa(0.0)
        venda = self.repo.finalizar(
            Venda(itens=[ItemVenda(descricao="x", quantidade=2, valor_unitario=50.0)]),
            [pagamento_unico("Dinheiro", 30.0), pagamento_unico("Pix", 70.0)],
        )
        self.repo.devolver(venda.id, [(venda.itens[0].id, 2)])
        # entraram 30 em especie; os outros 70 voltam por fora da gaveta
        self.assertEqual(self.repo.conferencia().esperado, 0.0)

    def test_recebimento_de_fora_entra_e_sai_da_gaveta(self) -> None:
        self.assertFalse(self.repo.receber_na_gaveta(10.0, "OS", "OS-1"))
        self.repo.abrir_caixa(0.0)
        self.assertTrue(self.repo.receber_na_gaveta(40.0, "OS paga", "OS-1"))
        self.assertEqual(self.repo.conferencia().recebimentos, 40.0)
        self.assertEqual(self.repo.conferencia().esperado, 40.0)
        self.assertTrue(self.repo.desfazer_recebimento(40.0, "OS-1"))
        self.assertEqual(self.repo.conferencia().esperado, 0.0)

    def test_receber_sem_caixa_aberto_nao_cai_no_caixa_fechado(self) -> None:
        self.repo.abrir_caixa(0.0)
        venda = self.repo.finalizar(
            Venda(cliente="Ana", itens=[ItemVenda(descricao="x", valor_unitario=50.0)]),
            [pagamento_unico("Prazo", 50.0)],
        )
        fechado = self.repo.fechar_caixa(0.0).caixa
        self.repo.receber_pendente(venda.id, [pagamento_unico("Dinheiro", 50.0)])
        self.assertEqual(self.repo.conferencia(fechado.id).vendas_dinheiro, 0.0)


class TotaisTestCase(Base):
    def test_painel_soma_todas_as_vendas_do_mes(self) -> None:
        hoje = date.today().isoformat()
        conn = self.banco.connection
        for n in range(620):
            cursor = conn.execute(
                "INSERT INTO vendas (numero, cliente, data, forma_pagamento, status, desconto,"
                " observacoes, criado_em) VALUES (?, '', ?, 'Pix', 'concluida', 0, '', ?)",
                (f"V{n}", hoje, hoje),
            )
            conn.execute(
                "INSERT INTO venda_itens (venda_id, descricao, quantidade, valor_unitario)"
                " VALUES (?, 'x', 1, 10)", (cursor.lastrowid,),
            )
        conn.commit()
        resumo = self.repo.resumo()
        self.assertEqual(resumo.vendas_mes, 620)
        self.assertEqual(resumo.total_mes, 6200.0)
        self.assertEqual(len(resumo.ultimas), 6)

    def test_ultimas_vendas_aparecem_no_dia_primeiro(self) -> None:
        antiga = (date.today().replace(day=1) - timedelta(days=3)).isoformat()
        self.repo.lancar(Venda(numero="V1", data=antiga, cliente="Ana",
                               itens=[ItemVenda(descricao="x", valor_unitario=10.0)],
                               pagamentos=[pagamento_unico("Pix", 10.0)]))
        self.assertEqual([v.numero for v in self.repo.resumo().ultimas], ["V1"])


class EstoqueTestCase(Base):
    def test_cancelar_venda_sem_saldo_nao_inventa_estoque(self) -> None:
        produto = self.produto(saldo=3.0)
        venda = self.repo.finalizar(Venda(itens=[self.item(produto, 5)]),
                                    [pagamento_unico("Dinheiro", 250.0)])
        self.assertTrue(venda.avisos)
        self.assertEqual(self.saldo(produto), 3.0)
        self.repo.cancelar(venda.id, "desistiu")
        self.assertEqual(self.saldo(produto), 3.0)

    def test_cancelar_devolve_so_a_linha_que_saiu(self) -> None:
        tem, falta = self.produto(saldo=5.0), self.produto(saldo=0.0)
        venda = self.repo.finalizar(
            Venda(itens=[self.item(tem, 2), self.item(falta, 1)]),
            [pagamento_unico("Dinheiro", 150.0)],
        )
        self.assertEqual(self.saldo(tem), 3.0)
        self.repo.cancelar(venda.id, "desistiu")
        self.assertEqual(self.saldo(tem), 5.0)
        self.assertEqual(self.saldo(falta), 0.0)

    def test_devolucao_de_item_que_nao_saiu_nao_aumenta_o_saldo(self) -> None:
        produto = self.produto(saldo=0.0)
        venda = self.repo.finalizar(Venda(itens=[self.item(produto, 1)]),
                                    [pagamento_unico("Dinheiro", 50.0)])
        self.repo.devolver(venda.id, [(venda.itens[0].id, 1)])
        self.assertEqual(self.saldo(produto), 0.0)

    def test_devolver_e_depois_cancelar_nao_devolve_duas_vezes(self) -> None:
        produto = self.produto(saldo=5.0)
        venda = self.repo.finalizar(Venda(itens=[self.item(produto, 3)]),
                                    [pagamento_unico("Dinheiro", 150.0)])
        self.repo.devolver(venda.id, [(venda.itens[0].id, 1)])
        self.repo.cancelar(venda.id, "desistiu")
        self.assertEqual(self.saldo(produto), 5.0)


class EdicaoTestCase(Base):
    def test_venda_pendente_que_ja_saiu_do_estoque_acompanha_a_edicao(self) -> None:
        produto = self.produto(saldo=10.0)
        venda = self.repo.finalizar(Venda(cliente="Ana", itens=[self.item(produto, 1)]),
                                    [pagamento_unico("Prazo", 50.0)])
        financeiro.registrar(self.contas, venda)
        self.assertEqual(self.saldo(produto), 9.0)

        venda.itens = [self.item(produto, 3)]
        salva = self.repo.alterar_pendente(venda)
        self.assertEqual(self.saldo(produto), 7.0)
        self.assertEqual(salva.itens[0].baixado, 3.0)

        financeiro.ajustar(self.contas, salva)
        self.assertEqual(self.contas.repository.listar()[0].valor, 150.0)

        self.repo.cancelar(salva.id, "desistiu")
        self.assertEqual(self.saldo(produto), 10.0)

    def test_tirar_o_item_devolve_ao_estoque(self) -> None:
        produto, outro = self.produto(saldo=10.0), self.produto(saldo=10.0)
        venda = self.repo.finalizar(
            Venda(cliente="Ana", itens=[self.item(produto, 2)]),
            [pagamento_unico("Prazo", 100.0)],
        )
        venda.itens = [self.item(outro, 1)]
        self.repo.alterar_pendente(venda)
        self.assertEqual(self.saldo(produto), 10.0)
        self.assertEqual(self.saldo(outro), 9.0)

    def test_venda_paga_nao_muda_de_itens(self) -> None:
        produto = self.produto()
        venda = self.repo.finalizar(Venda(itens=[self.item(produto, 1)]),
                                    [pagamento_unico("Dinheiro", 50.0)])
        with self.assertRaises(VendaError):
            self.repo.alterar_pendente(venda)

    def test_tela_de_venda_paga_so_muda_cliente_e_observacoes(self) -> None:
        from dumtech.apps.vendas.ui.venda_dialog import VendaDialog

        produto = self.produto(saldo=10.0)
        self.repo.abrir_caixa(0.0)
        venda = self.repo.finalizar(
            Venda(cliente="Ana", itens=[self.item(produto, 2)]),
            [pagamento_unico("Dinheiro", 20.0), pagamento_unico("Pix", 80.0)],
        )
        financeiro.registrar(self.contas, venda)

        dialogo = VendaDialog(self.repo, self.repo.obter(venda.id), contas=self.contas)
        self.addCleanup(dialogo.deleteLater)
        self.assertFalse(dialogo.itens.isEnabled())
        self.assertFalse(dialogo.forma.isEnabled())
        dialogo.cliente.setText("Ana Maria")
        dialogo.salvar()

        lida = self.repo.obter(venda.id)
        self.assertEqual(lida.cliente, "Ana Maria")
        self.assertEqual([p.forma for p in lida.pagamentos], ["Dinheiro", "Pix"])
        self.assertEqual(self.repo.conferencia().esperado, 20.0)
        self.assertEqual(self.saldo(produto), 8.0)
        self.assertEqual(self.contas.repository.listar()[0].cliente, "Ana Maria")


class VencimentoTestCase(Base):
    def test_venda_a_prazo_vence_na_data_escolhida(self) -> None:
        data = (date.today() + timedelta(days=45)).isoformat()
        venda = self.repo.finalizar(
            Venda(cliente="Ana", vencimento=data,
                  itens=[ItemVenda(descricao="x", valor_unitario=50.0)]),
            [pagamento_unico("Prazo", 50.0)],
        )
        financeiro.registrar(self.contas, venda)
        self.assertEqual(self.contas.repository.listar()[0].vencimento, data)
        self.assertEqual(self.repo.obter(venda.id).vencimento, data)

    def test_primeira_parcela_vence_na_data_escolhida(self) -> None:
        data = (date.today() + timedelta(days=10)).isoformat()
        venda = self.repo.finalizar(
            Venda(cliente="Ana", vencimento=data,
                  itens=[ItemVenda(descricao="x", valor_unitario=300.0)]),
            [Pagamento(forma="Parcelado", valor=300.0, recebido=300.0, parcelas=3)],
        )
        financeiro.registrar(self.contas, venda)
        datas = sorted(item.vencimento for item in self.contas.repository.listar())
        self.assertEqual(datas[0], data)

    def test_pendente_exige_cliente(self) -> None:
        with self.assertRaises(VendaError):
            self.repo.finalizar(Venda(itens=[ItemVenda(descricao="x", valor_unitario=50.0)]),
                                [pagamento_unico("Prazo", 50.0)])

    def test_dialogo_nao_aceita_prazo_sem_cliente(self) -> None:
        from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

        dialogo = PagamentoDialog(50.0, conferir=self.repo.conferir_pagamento)
        self.addCleanup(dialogo.deleteLater)
        dialogo.forma.setCurrentText("Prazo")
        dialogo._lancar()
        self.assertEqual(dialogo.pagamentos, [])

    def test_dialogo_devolve_a_data_de_quem_ficou_devendo(self) -> None:
        from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

        dialogo = PagamentoDialog(50.0, conferir=self.repo.conferir_pagamento, cliente="Ana")
        self.addCleanup(dialogo.deleteLater)
        self.assertEqual(dialogo.vencimento_iso, "")
        dialogo.forma.setCurrentText("Prazo")
        self.assertFalse(dialogo.campo_vencimento.isHidden())
        dialogo._lancar()
        self.assertTrue(dialogo.vencimento_iso)


class CentavosTestCase(unittest.TestCase):
    def _total(self, pedido: Pedido) -> float:
        unitarios, desconto = precos_fechados(pedido)
        bruto = sum(round(i.quantidade * u, 2) for i, u in zip(pedido.itens, unitarios))
        return round(bruto - desconto, 2)

    def test_desconto_por_linha_fecha_no_centavo(self) -> None:
        pedido = Pedido(itens=[ItemPedido(descricao="x", quantidade=3, valor_unitario=10.0,
                                          desconto=0.10)])
        self.assertEqual(self._total(pedido), 29.90)

    def test_desconto_do_documento_continua_valendo(self) -> None:
        pedido = Pedido(desconto=5.0, itens=[
            ItemPedido(descricao="a", quantidade=7, valor_unitario=3.33, desconto=0.05),
            ItemPedido(descricao="b", quantidade=1.5, valor_unitario=9.90),
        ])
        self.assertEqual(self._total(pedido), 33.11)

    def test_sem_desconto_nao_inventa_nada(self) -> None:
        pedido = Pedido(itens=[ItemPedido(descricao="x", quantidade=2, valor_unitario=19.90)])
        self.assertEqual(precos_fechados(pedido), ([19.90], 0.0))


class VoltaDoFinanceiroTestCase(Base):
    """Receber na tela de contas fecha a venda."""

    def setUp(self) -> None:
        super().setUp()
        self.destino = DestinoVendas(self.banco)
        self.destino.repository.catalogo = self.catalogo
        self.tela = FinanceiroRepository(abrir_financeiro(self.pasta / "financeiro.db"))
        self.addCleanup(self.tela.db.close)
        ligar_modulos(self.tela, [self.destino], gaveta=self.destino)

    def pendente(self, produto: Produto | None = None) -> Venda:
        produto = produto or self.produto()
        venda = self.repo.lancar(Venda(
            numero=self.repo.proximo_numero(), cliente="Ana", status=PENDENTE,
            itens=[self.item(produto, 1)],
        ))
        financeiro.registrar(self.contas, venda)
        return venda

    def test_receber_no_financeiro_fecha_a_venda_e_baixa_o_estoque(self) -> None:
        produto = self.produto(saldo=10.0)
        venda = self.pendente(produto)
        conta = self.tela.listar()[0]
        self.tela.baixar(conta.id, forma="Pix")

        lida = self.repo.obter(venda.id)
        self.assertEqual(lida.status, CONCLUIDA)
        self.assertEqual(lida.forma_pagamento, "Pix")
        self.assertEqual(self.saldo(produto), 9.0)

    def test_em_dinheiro_com_caixa_aberto_entra_uma_vez_so_na_gaveta(self) -> None:
        self.repo.abrir_caixa(0.0)
        self.pendente()
        self.tela.baixar(self.tela.listar()[0].id, forma="Dinheiro")
        conferencia = self.repo.conferencia()
        self.assertEqual(conferencia.esperado, 50.0)
        self.assertEqual(conferencia.recebimentos, 0.0)

    def test_baixa_parcial_nao_fecha_a_venda(self) -> None:
        venda = self.pendente()
        self.tela.baixar(self.tela.listar()[0].id, valor=10.0, forma="Pix")
        self.assertEqual(self.repo.obter(venda.id).status, PENDENTE)

    def test_desfazer_a_baixa_reabre_a_venda(self) -> None:
        venda = self.pendente()
        conta = self.tela.listar()[0]
        self.tela.alternar_pagamento(conta.id)
        self.assertEqual(self.repo.obter(venda.id).status, CONCLUIDA)
        self.tela.alternar_pagamento(conta.id)
        lida = self.repo.obter(venda.id)
        self.assertEqual(lida.status, PENDENTE)
        self.assertEqual(lida.pagamentos, [])

    def test_venda_paga_no_balcao_nao_reabre(self) -> None:
        venda = self.repo.finalizar(
            Venda(cliente="Ana", itens=[ItemVenda(descricao="x", valor_unitario=50.0)]),
            [pagamento_unico("Dinheiro", 50.0)],
        )
        financeiro.registrar(self.contas, venda)
        self.tela.alternar_pagamento(self.tela.listar()[0].id)
        self.assertEqual(self.repo.obter(venda.id).status, CONCLUIDA)

    def test_conta_que_nao_e_de_venda_recebida_em_dinheiro_vai_para_a_gaveta(self) -> None:
        from dumtech.apps.financeiro.models import RECEITA, Lancamento

        self.repo.abrir_caixa(0.0)
        conta = self.tela.criar(Lancamento(tipo=RECEITA, descricao="Aluguel da sala",
                                           valor=70.0, forma_pagamento="Dinheiro"))
        self.tela.baixar(conta.id)
        self.assertEqual(self.repo.conferencia().recebimentos, 70.0)
        self.tela.estornar_tudo(conta.id)
        self.assertEqual(self.repo.conferencia().recebimentos, 0.0)

    def test_conciliar_fecha_o_que_ficou_para_tras_sem_mexer_na_gaveta(self) -> None:
        venda = self.pendente()
        self.repo.abrir_caixa(0.0)
        # a baixa foi feita antes de a volta existir: a ponte nao tem ganchos
        self.contas.quitar(venda.numero, forma="Dinheiro")
        financeiro.conciliar(self.repo, self.contas)
        lida = self.repo.obter(venda.id)
        self.assertEqual(lida.status, CONCLUIDA)
        self.assertEqual(lida.caixa_id, 0)
        self.assertEqual(self.repo.conferencia().esperado, 0.0)


class MigracaoTestCase(unittest.TestCase):
    def test_banco_antigo_mantem_a_historia(self) -> None:
        caminho = Path(tempfile.mkdtemp(prefix="dt_vm_")) / "vendas.db"
        antigo = Database(caminho, MIGRATIONS[:5])
        antigo.connection
        conn = antigo.connection
        cur = conn.execute(
            "INSERT INTO vendas (numero, data, criado_em, baixa_estoque) "
            "VALUES ('V1', '2026-01-01', '2026-01-01', 'antes')"
        )
        item = conn.execute(
            "INSERT INTO venda_itens (venda_id, descricao, quantidade, valor_unitario, produto_id)"
            " VALUES (?, 'x', 2, 10, 1)", (cur.lastrowid,),
        )
        conn.execute(
            "INSERT INTO devolucoes (venda_id, data, valor, criado_em) "
            "VALUES (?, '2026-01-02', 10, '2026-01-02')", (cur.lastrowid,),
        )
        caixa = conn.execute("INSERT INTO caixas (aberto_em) VALUES ('2026-01-01')")
        conn.execute(
            "INSERT INTO caixa_movimentos (caixa_id, tipo, valor, motivo, criado_em)"
            " VALUES (?, 'sangria', 5, 'banco', '2026-01-01')", (caixa.lastrowid,),
        )
        conn.commit()
        item_id = item.lastrowid
        antigo.close()

        novo = open_database(caminho)
        self.addCleanup(novo.close)
        repo = VendasRepository(novo)
        self.assertEqual(novo.schema_version, MIGRATIONS[-1].version)
        self.assertEqual(novo.scalar("SELECT baixado FROM venda_itens WHERE id = ?", (item_id,)), 2)
        self.assertEqual(novo.scalar("SELECT em_dinheiro FROM devolucoes"), 10)
        self.assertEqual(repo.movimentos_de(1)[0].motivo, "banco")


if __name__ == "__main__":
    unittest.main()
