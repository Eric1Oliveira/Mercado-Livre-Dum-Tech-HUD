"""Lucro, DRE, exportacao, OS completa e estoque avancado."""

from __future__ import annotations

import csv
import io
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dumtech.apps.estoque.catalog import CatalogoEstoque
from dumtech.apps.estoque.database import MIGRATIONS as MIGRACOES_ESTOQUE
from dumtech.apps.estoque.database import open_database as abrir_estoque
from dumtech.apps.estoque.models import (
    EstoqueError,
    Fornecedor,
    ItemEntrada,
    ItemPedidoCompra,
    PedidoCompra,
    Produto,
)
from dumtech.apps.estoque.repository import EstoqueRepository
from dumtech.apps.financeiro.contas import abrir_contas
from dumtech.apps.financeiro.models import DESPESA, RECEITA, Lancamento
from dumtech.apps.financeiro.ui.dre_view import MES_PASSADO, DreView, periodo
from dumtech.apps.ordens.database import open_database as abrir_ordens
from dumtech.apps.ordens.documento import entrega_a4
from dumtech.apps.ordens.models import Ordem
from dumtech.apps.ordens.repository import OrdensRepository
from dumtech.apps.ordens.ui.anexos_dialog import AnexosDialog, preparar_foto
from dumtech.apps.vendas.database import open_database as abrir_vendas
from dumtech.apps.vendas.models import ItemVenda, Venda, VendaError
from dumtech.apps.vendas.repository import VendasRepository, pagamento_unico
from dumtech.apps.vendas.ui.resultado_view import ResultadoView
from dumtech.core import exportar
from dumtech.core.contas import AReceber, APagar, MovimentoDeCaixa
from dumtech.core.database import Database

_app: QApplication | None = None
HOJE = date.today().isoformat()


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = Path(tempfile.mkdtemp(prefix="dt_mel_"))
        banco = abrir_estoque(self.pasta / "estoque.db")
        self.addCleanup(banco.close)
        self.estoque = EstoqueRepository(banco)
        self.catalogo = CatalogoEstoque(banco)
        banco_vendas = abrir_vendas(self.pasta / "vendas.db")
        self.addCleanup(banco_vendas.close)
        self.vendas = VendasRepository(banco_vendas, catalogo=self.catalogo)

    def produto(self, custo: float = 30.0, preco: float = 100.0, saldo: float = 50.0,
                codigo: str = "P1", **campos) -> Produto:
        return self.estoque.criar(Produto(codigo=codigo, nome=f"Produto {codigo}", quantidade=saldo,
                                          preco_custo=custo, preco_venda=preco, **campos))

    def vender(self, produto: Produto, quantidade: float = 1.0, **campos) -> Venda:
        venda = Venda(itens=[ItemVenda(descricao=produto.nome, quantidade=quantidade,
                                       valor_unitario=produto.preco_venda,
                                       produto_id=produto.id)], **campos)
        return self.vendas.finalizar(venda, [pagamento_unico("Pix", venda.total)])


class LucroTestCase(Base):
    def test_custo_fica_gravado_na_venda(self) -> None:
        produto = self.produto()
        venda = self.vender(produto, 2)
        self.assertEqual(venda.itens[0].custo_unitario, 30.0)
        # o custo medio mudou depois: a venda antiga continua com o dela
        self.estoque.registrar_entrada(produto.id, 50, custo_unitario=90.0)
        self.assertEqual(self.vendas.obter(venda.id).itens[0].custo_unitario, 30.0)

    def test_lucro_margem_e_ticket(self) -> None:
        self.vender(self.produto(), 2)
        r = self.vendas.resultado(HOJE, HOJE)
        self.assertEqual((r.receita, r.custo, r.lucro, r.margem), (200.0, 60.0, 140.0, 70.0))
        self.assertEqual(r.ticket_medio, 200.0)

    def test_desconto_e_devolucao_entram_na_conta(self) -> None:
        produto = self.produto()
        venda = self.vender(produto, 2, desconto=20.0)
        self.vendas.devolver(venda.id, [(venda.itens[0].id, 1)])
        r = self.vendas.resultado(HOJE, HOJE)
        self.assertEqual((r.receita, r.custo), (90.0, 30.0))

    def test_cancelada_nao_conta(self) -> None:
        venda = self.vender(self.produto())
        self.vendas.cancelar(venda.id, "desistiu")
        self.assertEqual(self.vendas.resultado(HOJE, HOJE).receita, 0.0)

    def test_item_sem_custo_e_avisado(self) -> None:
        self.vendas.finalizar(Venda(itens=[ItemVenda(descricao="Serviço", valor_unitario=50.0)]),
                              [pagamento_unico("Pix", 50.0)])
        self.assertEqual(self.vendas.resultado(HOJE, HOJE).itens_sem_custo, 1)

    def test_comissao_do_vendedor(self) -> None:
        self.vendas.salvar_vendedor("Bia", 5.0)
        self.vender(self.produto(), 2, vendedor="Bia")
        r = self.vendas.resultado(HOJE, HOJE)
        self.assertEqual((r.vendedores[0].nome, r.vendedores[0].comissao), ("Bia", 10.0))
        self.assertEqual(r.comissoes, 10.0)

    def test_vendedor_que_saiu_some_da_lista_e_nao_do_resultado(self) -> None:
        self.vendas.salvar_vendedor("Bia", 5.0)
        self.vender(self.produto(), vendedor="Bia")
        self.vendas.inativar_vendedor("Bia")
        self.assertEqual(self.vendas.vendedores(), [])
        self.assertEqual(self.vendas.resultado(HOJE, HOJE).vendedores[0].comissao, 5.0)

    def test_comissao_invalida(self) -> None:
        with self.assertRaises(VendaError):
            self.vendas.salvar_vendedor("Bia", 120.0)

    def test_tela_de_resultado_abre(self) -> None:
        self.vender(self.produto(), 2)
        tela = ResultadoView(self.vendas)
        self.addCleanup(tela.deleteLater)
        tela.refresh()
        self.assertIn("Lucro R$", tela.numeros.text().replace("\xa0", " "))
        self.assertEqual(tela.tabela_produtos.rowCount(), 1)


class DreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.contas = abrir_contas(Path(tempfile.mkdtemp(prefix="dt_dre_")) / "financeiro.db")
        self.addCleanup(self.contas.close)
        self.repo = self.contas.repository

    def pago(self, tipo: str, categoria: str, valor: float, fixa: bool = False) -> None:
        self.repo.criar(Lancamento(tipo=tipo, descricao=categoria, categoria=categoria,
                                   valor=valor, vencimento=HOJE, pago_em=HOJE, fixa=fixa))

    def test_receita_menos_fixas_menos_variaveis(self) -> None:
        self.pago(RECEITA, "Vendas", 1000.0)
        self.pago(DESPESA, "Aluguel", 300.0, fixa=True)
        self.pago(DESPESA, "Frete", 100.0)
        dre = self.repo.dre(HOJE, HOJE)
        self.assertEqual((dre.total_receitas, dre.total_fixas, dre.total_variaveis),
                         (1000.0, 300.0, 100.0))
        self.assertEqual((dre.resultado, dre.margem), (600.0, 60.0))

    def test_conta_em_aberto_nao_entra(self) -> None:
        self.repo.criar(Lancamento(tipo=RECEITA, descricao="x", valor=500.0, vencimento=HOJE))
        self.assertEqual(self.repo.dre(HOJE, HOJE).total_receitas, 0.0)

    def test_sangria_nao_e_gasto(self) -> None:
        self.contas.movimento_de_caixa(MovimentoDeCaixa("retirada", 50.0, "Cofre", HOJE, "C-1"))
        self.contas.movimento_de_caixa(MovimentoDeCaixa("despesa", 30.0, "Luz", HOJE, "C-2"))
        self.assertEqual(self.repo.dre(HOJE, HOJE).total_variaveis, 30.0)

    def test_cancelado_nao_entra(self) -> None:
        self.contas.lancar(AReceber(descricao="x", valor=80.0, vencimento=HOJE, documento="D"))
        self.contas.quitar("D")
        self.contas.cancelar("D", "erro")
        self.assertEqual(self.repo.dre(HOJE, HOJE).total_receitas, 0.0)

    def test_tela_mostra_o_resultado(self) -> None:
        self.pago(RECEITA, "Vendas", 1000.0)
        tela = DreView(self.repo)
        self.addCleanup(tela.deleteLater)
        tela.refresh()
        self.assertIn("Sobrou", tela.resultado.text())
        self.assertEqual(tela.linhas()[0], ("Receitas", 1000.0, True))

    def test_periodo_do_mes_passado(self) -> None:
        self.assertEqual(periodo(MES_PASSADO, date(2026, 3, 15)), ("2026-02-01", "2026-02-28"))


class ExportarTestCase(Base):
    def test_excel_nao_executa_o_que_veio_do_cadastro(self) -> None:
        texto = exportar.csv_de(["a"], [["=1+1"], ["@x"], ["Normal"]])
        self.assertEqual(texto.splitlines()[1:], ["'=1+1", "'@x", "Normal"])

    def test_abre_no_excel_brasileiro(self) -> None:
        arquivo = self.pasta / "x.csv"
        exportar.gravar(arquivo, exportar.csv_de(["Número", "Valor"], [["1", "R$ 10,00"]]))
        self.assertTrue(arquivo.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_exporta_a_lista_inteira_e_nao_so_a_tela(self) -> None:
        from dumtech.apps.vendas.ui.vendas_view import VendasView

        conn = self.vendas.db.connection
        for n in range(510):
            conn.execute(
                "INSERT INTO vendas (numero, cliente, data, forma_pagamento, status, desconto,"
                " observacoes, criado_em) VALUES (?, '', ?, 'Pix', 'concluida', 0, '', ?)",
                (f"V{n}", HOJE, HOJE),
            )
        conn.commit()
        tela = VendasView(self.vendas)
        self.addCleanup(tela.deleteLater)
        tela.refresh()
        self.assertEqual(tela.tabela.rowCount(), 500)
        self.assertIn("Mostrando só 500", tela.subtitulo.text())
        self.assertEqual(len(tela.linhas_para_exportar()), 510)

        arquivo = self.pasta / "vendas.csv"
        with mock.patch("dumtech.ui.widgets.crud_view.QFileDialog.getSaveFileName",
                        return_value=(str(arquivo), "")):
            tela.exportar()
        linhas = list(csv.reader(io.StringIO(arquivo.read_text(encoding="utf-8-sig")),
                                 delimiter=";"))
        self.assertEqual(len(linhas), 511)
        self.assertEqual(linhas[0][0], "Número")

    def test_todo_modulo_com_lista_tem_o_botao(self) -> None:
        from dumtech.apps.agenda.ui.compromissos_view import CompromissosView
        from dumtech.apps.financeiro.ui.lancamentos_view import LancamentosView
        from dumtech.apps.orcamentos.ui.orcamentos_view import OrcamentosView
        from dumtech.apps.ordens.ui.ordens_view import OrdensView
        from dumtech.apps.vendas.ui.vendas_view import VendasView

        for tela in (VendasView, LancamentosView, OrdensView, OrcamentosView, CompromissosView):
            self.assertTrue(tela.exportavel, tela.__name__)


class OrdemCompletaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = Path(tempfile.mkdtemp(prefix="dt_oc_"))
        banco = abrir_ordens(self.pasta / "ordens.db")
        self.addCleanup(banco.close)
        self.ordens = OrdensRepository(banco)
        self.ordem = self.ordens.salvar(Ordem(numero="OS-1", cliente="Ana", equipamento="Celular"))
        self.dialogo = AnexosDialog(self.ordens, self.ordem)
        self.addCleanup(self.dialogo.deleteLater)

    def test_checklist(self) -> None:
        self.dialogo.nova_tarefa.setText("Testar a tela")
        self.dialogo._adicionar_tarefa()
        item = self.dialogo.lista.item(0)
        item.setCheckState(Qt.CheckState.Checked)
        self.assertTrue(self.ordens.checklist_de(self.ordem.id)[0].feito)
        self.assertEqual(self.ordens.tarefas_usadas(), ["Testar a tela"])

    def test_tarefa_vazia_avisa(self) -> None:
        self.dialogo._adicionar_tarefa()
        self.assertIn("Escreva", self.dialogo.aviso.text())

    def test_foto_grande_e_reduzida_e_vai_para_o_banco(self) -> None:
        arquivo = self.pasta / "foto.png"
        imagem = QImage(3000, 2000, QImage.Format.Format_RGB32)
        imagem.fill(Qt.GlobalColor.red)
        imagem.save(str(arquivo))
        self.dialogo.adicionar_foto(str(arquivo))
        self.assertEqual(self.dialogo.fotos.count(), 1)
        guardada = QImage.fromData(self.ordens.fotos_de(self.ordem.id)[0].imagem)
        self.assertEqual(guardada.width(), 1280)

    def test_arquivo_que_nao_e_imagem(self) -> None:
        arquivo = self.pasta / "x.png"
        arquivo.write_text("nao sou imagem")
        self.dialogo.adicionar_foto(str(arquivo))
        self.assertEqual(self.ordens.fotos_de(self.ordem.id), [])

    def test_fotos_somem_com_a_ordem(self) -> None:
        self.ordens.adicionar_foto(self.ordem.id, b"x")
        self.ordens.excluir(self.ordem.id)
        self.assertEqual(self.ordens.db.scalar("SELECT COUNT(*) FROM os_fotos"), 0)

    def test_assinatura_precisa_de_traco_e_sai_no_comprovante(self) -> None:
        self.dialogo.guardar_assinatura()
        self.assertIn("Assine", self.dialogo.aviso.text())

        papel = self.dialogo.papel
        papel.resize(300, 190)
        QTest.mousePress(papel, Qt.MouseButton.LeftButton, pos=QPointF(10, 10).toPoint())
        QTest.mouseMove(papel, QPointF(120, 80).toPoint())
        QTest.mouseRelease(papel, Qt.MouseButton.LeftButton, pos=QPointF(120, 80).toPoint())
        self.assertFalse(papel.vazio)
        self.dialogo.guardar_assinatura()

        assinatura = self.ordens.assinatura_de(self.ordem.id)
        self.assertTrue(assinatura.startswith(b"\x89PNG"))
        documento = entrega_a4(self.ordens.obter(self.ordem.id), None, None, assinatura)
        self.assertIn("data:image/png;base64,", documento)

    def test_comprovante_sem_assinatura_continua_com_a_linha(self) -> None:
        documento = entrega_a4(self.ordens.obter(self.ordem.id))
        self.assertNotIn("data:image/png", documento)
        self.assertIn("Recebi o serviço", documento)

    def test_lista_mostra_o_pagamento(self) -> None:
        from dumtech.apps.ordens.ui.ordens_view import OrdensView

        contas = abrir_contas(self.pasta / "financeiro.db")
        self.addCleanup(contas.close)
        tela = OrdensView(self.ordens, contas=contas)
        self.addCleanup(tela.deleteLater)
        self.assertEqual(tela._pagamento(self.ordem), ("-",))
        contas.lancar(AReceber(descricao="OS", valor=100.0, vencimento=HOJE, documento="OS-1"))
        self.assertEqual(tela._pagamento(self.ordem)[0], "Em aberto")
        contas.quitar("OS-1")
        self.assertEqual(tela._pagamento(self.ordem)[0], "Recebido")


class EstoqueAvancadoTestCase(Base):
    def test_variacoes_sao_produtos_de_verdade(self) -> None:
        base = self.produto(codigo="CAM", saldo=0.0)
        criadas = self.estoque.criar_variacoes(base, ["P", "M"], ["Azul", "Preto"])
        self.assertEqual(len(criadas), 4)
        self.assertEqual(criadas[0].codigo, "CAM-P-AZUL")
        self.assertEqual(criadas[0].nome, "Produto CAM P Azul")
        self.assertEqual((criadas[0].tamanho, criadas[0].cor, criadas[0].quantidade), ("P", "Azul", 0))
        self.assertEqual(len(self.estoque.variacoes_de("CAM")), 4)

    def test_variacao_duplicada_nao_deixa_metade(self) -> None:
        base = self.produto(codigo="CAM", saldo=0.0)
        self.estoque.criar_variacoes(base, ["M"], [])
        with self.assertRaises(EstoqueError):
            self.estoque.criar_variacoes(base, ["P", "M"], [])
        self.assertEqual(len(self.estoque.variacoes_de("CAM")), 1)

    def test_variacao_sem_dado(self) -> None:
        with self.assertRaises(EstoqueError):
            self.estoque.criar_variacoes(self.produto(), [" "], [])

    def test_sai_primeiro_o_que_vence_primeiro(self) -> None:
        produto = self.produto(saldo=0.0)
        hoje = date.today()
        self.estoque.entrada_em_lote([
            ItemEntrada(produto.id, 10, 5.0, lote="B", validade=(hoje + timedelta(days=90)).isoformat()),
            ItemEntrada(produto.id, 10, 5.0, lote="A", validade=(hoje + timedelta(days=10)).isoformat()),
            ItemEntrada(produto.id, 10, 5.0, lote="SEM"),
        ])
        self.assertEqual(self.estoque.obter(produto.id).quantidade, 30)
        self.estoque.registrar_saida(produto.id, 12)
        lotes = {l.codigo: l.quantidade for l in self.estoque.lotes_de(produto.id)}
        self.assertEqual(lotes, {"B": 8.0, "SEM": 10.0})

    def test_vencendo_aparece_no_painel_e_no_aviso(self) -> None:
        from dumtech.apps.estoque import module
        from dumtech.core.avisos import Config

        produto = self.produto(saldo=0.0)
        validade = (date.today() + timedelta(days=5)).isoformat()
        self.estoque.entrada_em_lote([ItemEntrada(produto.id, 3, 5.0, lote="A", validade=validade)])
        self.assertEqual(self.estoque.resumo().vencendo[0].validade, validade)

        caminhos = mock.Mock()
        caminhos.app_db.return_value = self.estoque.db.path
        avisos = module.avisos(caminhos, Config())
        self.assertIn("lote_vencendo", [a.tipo for a in avisos])

    def test_longe_da_validade_nao_avisa(self) -> None:
        produto = self.produto(saldo=0.0)
        self.estoque.entrada_em_lote([ItemEntrada(
            produto.id, 3, lote="A", validade=(date.today() + timedelta(days=200)).isoformat())])
        self.assertEqual(self.estoque.vencendo(), [])

    def test_fornecedor_antigo_vira_cadastro(self) -> None:
        caminho = self.pasta / "antigo.db"
        antigo = Database(caminho, MIGRACOES_ESTOQUE[:3])
        antigo.connection.execute(
            "INSERT INTO produtos (codigo, nome, fornecedor, criado_em, atualizado_em)"
            " VALUES ('A', 'Um', 'Atacado', '2026-01-01', '2026-01-01')")
        antigo.connection.commit()
        antigo.close()
        novo = abrir_estoque(caminho)
        self.addCleanup(novo.close)
        nomes = [f.nome for f in EstoqueRepository(novo).listar_fornecedores()]
        self.assertEqual(nomes, ["Atacado"])

    def test_fornecedor_repetido_avisa(self) -> None:
        self.estoque.salvar_fornecedor(Fornecedor(nome="Atacado"))
        with self.assertRaises(EstoqueError):
            self.estoque.salvar_fornecedor(Fornecedor(nome="atacado"))

    def test_pedido_recebido_vira_entrada_uma_vez(self) -> None:
        produto = self.produto(custo=10.0, saldo=0.0)
        pedido = self.estoque.salvar_pedido(PedidoCompra(
            fornecedor="Atacado", itens=[ItemPedidoCompra(produto.id, 5, 12.0)]))
        self.assertEqual(pedido.total, 60.0)
        self.assertEqual(self.estoque.obter(produto.id).quantidade, 0)

        self.estoque.receber_pedido(pedido.id)
        lido = self.estoque.obter(produto.id)
        self.assertEqual((lido.quantidade, lido.preco_custo), (5, 12.0))
        with self.assertRaises(EstoqueError):
            self.estoque.receber_pedido(pedido.id)
        self.assertEqual(self.estoque.obter(produto.id).quantidade, 5)

    def test_pedido_recebido_nao_cancela_nem_apaga(self) -> None:
        produto = self.produto()
        pedido = self.estoque.salvar_pedido(PedidoCompra(itens=[ItemPedidoCompra(produto.id, 1)]))
        self.estoque.receber_pedido(pedido.id)
        with self.assertRaises(EstoqueError):
            self.estoque.cancelar_pedido(pedido.id)
        with self.assertRaises(EstoqueError):
            self.estoque.excluir_pedido(pedido.id)

    def test_reposicao_pede_o_que_falta(self) -> None:
        produto = self.produto(saldo=1.0, estoque_minimo=5.0, estoque_maximo=20.0)
        pedido = self.estoque.gerar_pedido_de_reposicao()
        self.assertEqual(pedido.itens[0].produto_id, produto.id)
        self.assertEqual(pedido.itens[0].quantidade, 19.0)

    def test_nada_a_repor(self) -> None:
        with self.assertRaises(EstoqueError):
            self.estoque.gerar_pedido_de_reposicao()

    def test_receber_na_tela_lanca_a_conta_a_pagar(self) -> None:
        from dumtech.apps.estoque.ui.pedidos_view import PedidosView

        contas = abrir_contas(self.pasta / "financeiro.db")
        self.addCleanup(contas.close)
        produto = self.produto()
        self.estoque.salvar_pedido(PedidoCompra(
            fornecedor="Atacado", itens=[ItemPedidoCompra(produto.id, 2, 10.0)]))
        tela = PedidosView(self.estoque, contas=contas)
        self.addCleanup(tela.deleteLater)
        tela.refresh()
        tela.tabela.selectRow(0)
        tela.botao_receber.click()
        conta = contas.repository.listar(tipo=DESPESA)[0]
        self.assertEqual((conta.valor, conta.cliente), (20.0, "Atacado"))
        self.assertIn("recebido", tela.aviso.text())

    def test_tela_de_entrada_guarda_lote_e_validade(self) -> None:
        from dumtech.apps.estoque.ui.entradas_view import EntradasView

        produto = self.produto(saldo=0.0)
        tela = EntradasView(self.estoque)
        self.addCleanup(tela.deleteLater)
        tela._produto = produto
        tela.quantidade.setValue(4)
        tela.lote.setText("L1")
        tela.validade.definir_iso("2030-01-01")
        tela._adicionar()
        tela._confirmar()
        self.assertEqual(self.estoque.lotes_de(produto.id)[0].codigo, "L1")

    def test_dialogo_de_variacoes(self) -> None:
        from dumtech.apps.estoque.ui.variacoes_dialog import VariacoesDialog

        dialogo = VariacoesDialog(self.estoque, self.produto(codigo="CAM"))
        self.addCleanup(dialogo.deleteLater)
        dialogo.tamanhos.setText("P, M")
        dialogo.cores.setText("Azul")
        self.assertIn("2 produtos", dialogo._nota.text())
        dialogo.salvar()
        self.assertEqual(len(dialogo.criadas), 2)


if __name__ == "__main__":
    unittest.main()
