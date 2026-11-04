"""O dinheiro e o estoque atravessando os modulos, nos dois sentidos."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dumtech.apps.agenda.database import open_database as abrir_agenda
from dumtech.apps.agenda.models import AGENDADO, Compromisso
from dumtech.apps.agenda.repository import AgendaRepository
from dumtech.apps.estoque.catalog import CatalogoEstoque
from dumtech.apps.estoque.database import open_database as abrir_estoque
from dumtech.apps.estoque.models import Produto
from dumtech.apps.estoque.repository import EstoqueRepository
from dumtech.apps.estoque.repository.planilha import _numero
from dumtech.apps.financeiro.contas import abrir_contas
from dumtech.apps.financeiro.models import DESPESA, RECEITA, Conta, Lancamento
from dumtech.apps.orcamentos.database import open_database as abrir_orcamentos
from dumtech.apps.orcamentos.models import APROVADO, ItemOrcamento, Orcamento
from dumtech.apps.orcamentos.repository import OrcamentosRepository
from dumtech.apps.ordens import financeiro as financeiro_os
from dumtech.apps.ordens.database import open_database as abrir_ordens
from dumtech.apps.ordens.models import CONCLUIDA, PECA, ItemOS, Ordem
from dumtech.apps.ordens.pedidos import DestinoOrdens
from dumtech.apps.ordens.repository import OrdensRepository
from dumtech.apps.vendas import financeiro
from dumtech.apps.vendas.database import open_database as abrir_vendas
from dumtech.apps.vendas.pedidos import DestinoVendas
from dumtech.apps.vendas.repository import VendasRepository
from dumtech.core.contas import AReceber, APagar, vencimento_padrao
from dumtech.core.pedidos import ItemPedido, Pedido

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = Path(tempfile.mkdtemp(prefix="dt_int_"))
        self.contas = abrir_contas(self.pasta / "financeiro.db")
        self.addCleanup(self.contas.close)
        self.financeiro = self.contas.repository
        banco = abrir_estoque(self.pasta / "estoque.db")
        self.addCleanup(banco.close)
        self.estoque = EstoqueRepository(banco)
        self.catalogo = CatalogoEstoque(banco)

    def conta(self, tipo: str, nome: str) -> Conta:
        return self.financeiro.criar_conta(Conta(nome=nome, tipo=tipo))


class FinanceiroTestCase(Base):
    def test_lista_nao_esconde_a_conta_de_hoje(self) -> None:
        hoje = date.today()
        self.financeiro.criar(Lancamento(tipo=RECEITA, descricao="Hoje", valor=10.0,
                                         vencimento=hoje.isoformat()))
        for dias in range(1, 621):
            self.financeiro.criar(Lancamento(
                tipo=RECEITA, descricao=f"Futura {dias}", valor=1.0,
                vencimento=(hoje + timedelta(days=dias)).isoformat(),
            ))
        lista = self.financeiro.listar()
        self.assertEqual(len(lista), 500)
        self.assertIn("Hoje", [item.descricao for item in lista])
        # continua do mais recente para o mais antigo
        datas = [item.vencimento for item in lista]
        self.assertEqual(datas, sorted(datas, reverse=True))

    def test_quitar_sem_conta_definida_soma_no_saldo(self) -> None:
        self.conta("caixa", "Caixa")
        item = self.financeiro.criar(Lancamento(tipo=RECEITA, descricao="Manual", valor=100.0))
        self.financeiro.alternar_pagamento(item.id)
        self.assertEqual(self.financeiro.saldo_total(), 100.0)

    def test_quitar_sem_nenhuma_conta_cadastrada_continua_funcionando(self) -> None:
        item = self.financeiro.criar(Lancamento(tipo=RECEITA, descricao="Manual", valor=100.0))
        self.financeiro.alternar_pagamento(item.id)
        self.assertTrue(self.financeiro.obter(item.id).pago)

    def test_compra_em_boletos_a_cada_30_dias(self) -> None:
        inicio = date.today()
        criados = self.contas.lancar_pagamento_parcelado(APagar(
            descricao="Compra NF 10", valor=900.0, vencimento=inicio.isoformat(),
            fornecedor="Atacado", documento="NF 10",
        ), 3)
        self.assertEqual(criados, 3)
        boletos = sorted(self.financeiro.listar(tipo=DESPESA), key=lambda b: b.vencimento)
        self.assertEqual([b.valor for b in boletos], [300.0, 300.0, 300.0])
        self.assertEqual([b.vencimento for b in boletos],
                         [(inicio + timedelta(days=d)).isoformat() for d in (0, 30, 60)])
        self.assertTrue(self.contas.ja_lancado("NF 10"))

    def test_situacao_de_um_documento(self) -> None:
        self.assertFalse(self.contas.situacao("OS-1").lancado)
        self.contas.lancar(AReceber(descricao="OS", valor=100.0, vencimento="2026-01-01",
                                    documento="OS-1"))
        self.assertEqual(self.contas.situacao("OS-1").em_aberto, 100.0)
        self.contas.quitar("OS-1", forma="Pix")
        situacao = self.contas.situacao("OS-1")
        self.assertTrue(situacao.quitado)
        self.assertEqual(situacao.forma, "Pix")


class CaixaNoFinanceiroTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        banco = abrir_vendas(self.pasta / "vendas.db")
        self.addCleanup(banco.close)
        self.vendas = VendasRepository(banco)
        self.vendas.abrir_caixa(100.0)

    def test_sangria_que_pagou_despesa_vira_despesa(self) -> None:
        self.conta("caixa", "Caixa")
        movimento = self.vendas.sangria(30.0, "Conta de luz")
        financeiro.movimento_de_caixa(self.contas, movimento, "despesa")
        despesa = self.financeiro.listar(tipo=DESPESA)[0]
        self.assertEqual((despesa.descricao, despesa.valor, despesa.pago), ("Conta de luz", 30.0, True))
        self.assertEqual(despesa.categoria, "Despesas de caixa")

    def test_sangria_para_o_banco_e_transferencia_e_nao_gasto(self) -> None:
        caixa, banco = self.conta("caixa", "Caixa"), self.conta("banco", "Banco")
        financeiro.movimento_de_caixa(self.contas, self.vendas.sangria(30.0, "Depósito"), "retirada")
        self.assertEqual(self.financeiro.listar(tipo=DESPESA), [])
        contas = {c.nome: c.saldo for c in self.financeiro.listar_contas()}
        self.assertEqual(contas, {"Caixa": -30.0, "Banco": 30.0})
        self.assertTrue(caixa.id and banco.id)

    def test_sangria_sem_banco_cadastrado_fica_fora_do_resultado(self) -> None:
        self.conta("caixa", "Caixa")
        financeiro.movimento_de_caixa(self.contas, self.vendas.sangria(30.0, "Cofre"), "retirada")
        self.assertEqual(self.financeiro.listar(tipo=DESPESA)[0].categoria, "Sangria de caixa")

    def test_suprimento(self) -> None:
        self.conta("caixa", "Caixa")
        financeiro.movimento_de_caixa(self.contas, self.vendas.suprimento(50.0, "Troco"))
        self.assertEqual(self.financeiro.saldo_total(), 50.0)

    def test_quebra_e_sobra_no_fechamento(self) -> None:
        self.conta("caixa", "Caixa")
        fechado = self.vendas.fechar_caixa(90.0)
        financeiro.fechamento(self.contas, fechado)
        quebra = self.financeiro.listar(tipo=DESPESA)[0]
        self.assertEqual((quebra.categoria, quebra.valor), ("Quebra de caixa", 10.0))
        # o mesmo fechamento de novo nao dobra
        financeiro.fechamento(self.contas, fechado)
        self.assertEqual(len(self.financeiro.listar(tipo=DESPESA)), 1)

    def test_caixa_que_bateu_nao_lanca_nada(self) -> None:
        financeiro.fechamento(self.contas, self.vendas.fechar_caixa(100.0))
        self.assertEqual(self.financeiro.listar(), [])

    def test_tela_de_sangria_pergunta_para_onde_foi_so_com_financeiro(self) -> None:
        from dumtech.apps.vendas.ui.caixa_dialogs import MovimentoCaixaDialog

        com = MovimentoCaixaDialog(self.vendas, "sangria", contas=self.contas)
        sem = MovimentoCaixaDialog(self.vendas, "sangria")
        self.addCleanup(com.deleteLater)
        self.addCleanup(sem.deleteLater)
        self.assertIsNotNone(com.form.labelForField(com.destino))
        self.assertIsNone(sem.form.labelForField(sem.destino))


class OrdemTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        banco = abrir_ordens(self.pasta / "ordens.db")
        self.addCleanup(banco.close)
        self.ordens = OrdensRepository(banco, catalogo=self.catalogo)
        self.produto = self.estoque.criar(Produto(codigo="P1", nome="Tela", quantidade=5,
                                                  preco_venda=100.0))

    def ordem(self, pecas: float = 2.0) -> Ordem:
        return self.ordens.salvar(Ordem(
            numero=self.ordens.proximo_numero(), cliente="Ana", equipamento="Celular",
            itens=[ItemOS(tipo=PECA, descricao="Tela", quantidade=pecas, valor_unitario=75.0,
                          produto_id=self.produto.id)],
        ))

    def entregue(self, pecas: float = 2.0) -> Ordem:
        ordem = self.ordem(pecas)
        self.ordens.definir_status(ordem.id, CONCLUIDA)
        return self.ordens.entregar(ordem.id)

    def saldo(self) -> float:
        return self.estoque.obter(self.produto.id).quantidade

    def test_cancelar_entregue_devolve_as_pecas(self) -> None:
        ordem = self.entregue()
        self.assertEqual(self.saldo(), 3.0)
        self.ordens.cancelar(ordem.id, "desistiu")
        self.assertEqual(self.saldo(), 5.0)

    def test_cancelar_a_que_nao_foi_entregue_nao_inventa_estoque(self) -> None:
        self.ordens.cancelar(self.ordem().id, "desistiu")
        self.assertEqual(self.saldo(), 5.0)

    def test_baixa_recusada_nao_volta(self) -> None:
        ordem = self.entregue(pecas=9.0)
        self.assertTrue(ordem.avisos)
        self.ordens.cancelar(ordem.id, "desistiu")
        self.assertEqual(self.saldo(), 5.0)

    def test_reabrir_e_entregar_de_novo_tira_as_pecas_de_novo(self) -> None:
        ordem = self.entregue()
        self.ordens.cancelar(ordem.id, "engano")
        self.ordens.reabrir(ordem.id)
        self.ordens.definir_status(ordem.id, CONCLUIDA)
        self.ordens.entregar(ordem.id)
        self.assertEqual(self.saldo(), 3.0)

    def test_cancelar_tira_a_conta_do_financeiro(self) -> None:
        ordem = self.entregue()
        self.contas.lancar(AReceber(descricao="OS", valor=150.0, vencimento="2026-01-01",
                                    documento=ordem.numero))
        cancelada = self.ordens.cancelar(ordem.id, "desistiu")
        self.assertIn("cancelada", financeiro_os.cancelar(self.contas, cancelada, "desistiu"))
        self.assertEqual(self.financeiro.listar(), [])

    def test_mudar_o_valor_acompanha_a_conta(self) -> None:
        ordem = self.ordem()
        financeiro_os.da_proposta(self.contas, ordem)
        ordem.itens[0].valor_unitario = 100.0
        self.ordens.salvar(ordem)
        financeiro_os.ajustar(self.contas, ordem)
        self.assertEqual(self.financeiro.listar()[0].valor, 200.0)

    def test_dinheiro_na_entrega_vai_para_a_gaveta(self) -> None:
        from dumtech.apps.ordens.ui.dialogos import EntregaDialog

        banco = abrir_vendas(self.pasta / "vendas.db")
        gaveta = DestinoVendas(banco)
        self.addCleanup(gaveta.close)
        gaveta.repository.abrir_caixa(0.0)

        ordem = self.ordem()
        self.ordens.definir_status(ordem.id, CONCLUIDA)
        dialogo = EntregaDialog(self.ordens, self.ordens.obter(ordem.id),
                                contas=self.contas, gaveta=gaveta)
        self.addCleanup(dialogo.deleteLater)
        dialogo.forma.setCurrentIndex(dialogo.forma.findData("Dinheiro"))
        dialogo.salvar()
        self.assertEqual(gaveta.repository.conferencia().recebimentos, 150.0)
        self.assertTrue(self.contas.situacao(ordem.numero).quitado)
        self.assertEqual(self.contas.situacao(ordem.numero).forma, "Dinheiro")

    def test_pix_na_entrega_nao_entra_na_gaveta(self) -> None:
        from dumtech.apps.ordens.ui.dialogos import EntregaDialog

        banco = abrir_vendas(self.pasta / "vendas.db")
        gaveta = DestinoVendas(banco)
        self.addCleanup(gaveta.close)
        gaveta.repository.abrir_caixa(0.0)

        ordem = self.ordem()
        self.ordens.definir_status(ordem.id, CONCLUIDA)
        dialogo = EntregaDialog(self.ordens, self.ordens.obter(ordem.id),
                                contas=self.contas, gaveta=gaveta)
        self.addCleanup(dialogo.deleteLater)
        dialogo.salvar()
        self.assertEqual(gaveta.repository.conferencia().recebimentos, 0.0)


class PropostaTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        banco = abrir_orcamentos(self.pasta / "orcamentos.db")
        self.addCleanup(banco.close)
        self.orcamentos = OrcamentosRepository(banco)

    def proposta(self) -> Orcamento:
        return self.orcamentos.salvar(Orcamento(
            numero=self.orcamentos.proximo_numero(), cliente="Ana",
            itens=[ItemOrcamento(descricao="Tela", quantidade=2, valor_unitario=50.0,
                                 produto_id=7, codigo="P7")],
        ))

    def test_duplicar_nao_perde_o_produto(self) -> None:
        copia = self.orcamentos.duplicar(self.proposta().id)
        self.assertEqual((copia.itens[0].produto_id, copia.itens[0].codigo), (7, "P7"))
        self.assertEqual(copia.gerado, "")

    def test_marca_em_que_a_proposta_virou(self) -> None:
        proposta = self.proposta()
        self.orcamentos.marcar_gerado(proposta.id, "VEN-2026-0001")
        self.assertEqual(self.orcamentos.obter(proposta.id).gerado, "VEN-2026-0001")

    def test_venda_da_proposta_ja_nasce_como_conta(self) -> None:
        banco = abrir_vendas(self.pasta / "vendas.db")
        destino = DestinoVendas(banco)
        self.addCleanup(destino.close)
        destino.contas = self.contas
        numero = destino.abrir(Pedido(cliente="Ana", origem="ORC-1", itens=[
            ItemPedido(descricao="x", quantidade=1, valor_unitario=80.0)]))
        conta = self.financeiro.listar()[0]
        self.assertEqual((conta.valor, conta.cliente), (80.0, "Ana"))
        self.assertTrue(self.contas.ja_lancado(numero))

    def test_ordem_da_proposta_ja_nasce_como_conta(self) -> None:
        banco = abrir_ordens(self.pasta / "ordens.db")
        destino = DestinoOrdens(banco)
        self.addCleanup(destino.close)
        destino.contas = self.contas
        numero = destino.abrir(Pedido(cliente="Ana", origem="ORC-1", itens=[
            ItemPedido(descricao="Serviço", quantidade=1, valor_unitario=80.0)]))
        self.assertEqual(self.contas.situacao(numero).em_aberto, 80.0)

    def _tela(self, destinos=()):
        from dumtech.apps.orcamentos.ui.orcamentos_view import OrcamentosView

        tela = OrcamentosView(self.orcamentos, destinos=list(destinos), contas=self.contas)
        self.addCleanup(tela.deleteLater)
        tela.refresh()
        tela.tabela.selectRow(0)
        return tela

    def test_sem_vendas_nem_ordens_aprovar_lanca_a_conta(self) -> None:
        proposta = self.proposta()
        tela = self._tela()
        tela._aprovar()
        self.assertEqual(self.orcamentos.obter(proposta.id).status, APROVADO)
        self.assertEqual(self.financeiro.listar()[0].valor, 100.0)
        tela._lancar_na_aprovacao(proposta)
        self.assertEqual(len(self.financeiro.listar()), 1)

    def test_com_destino_aprovar_nao_lanca(self) -> None:
        self.proposta()
        tela = self._tela(destinos=[object()])
        tela._aprovar()
        self.assertEqual(self.financeiro.listar(), [])


class AgendaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        banco = abrir_agenda(Path(tempfile.mkdtemp(prefix="dt_ag_")) / "agenda.db")
        self.addCleanup(banco.close)
        self.agenda = AgendaRepository(banco)
        conn = banco.connection
        for n in range(2100):
            conn.execute(
                "INSERT INTO compromissos (titulo, inicio, duracao_min, status, tipo, criado_em)"
                " VALUES (?, ?, 30, 'concluido', 'atendimento', '2020-01-01')",
                (f"Velho {n}", f"2020-01-{(n % 28) + 1:02d}T10:00"),
            )
        conn.commit()
        amanha = (date.today() + timedelta(days=1)).isoformat()
        self.hoje = self.agenda.salvar(Compromisso(
            titulo="De hoje", inicio=f"{date.today().isoformat()}T23:59", status=AGENDADO))
        self.agenda.salvar(Compromisso(titulo="De amanhã", inicio=f"{amanha}T10:00",
                                       status=AGENDADO))

    def test_painel_ve_o_dia_de_hoje_com_agenda_cheia(self) -> None:
        resumo = self.agenda.resumo()
        self.assertEqual(resumo.hoje, 1)
        self.assertIn("De amanhã", [c.titulo for c in resumo.proximos])

    def test_abertos_trazem_o_de_hoje(self) -> None:
        self.assertIn("De hoje", [c.titulo for c in self.agenda.abertos()])

    def test_lista_sem_filtro_mostra_o_que_esta_perto(self) -> None:
        lista = self.agenda.listar()
        self.assertEqual(len(lista), 500)
        self.assertIn("De hoje", [c.titulo for c in lista])


class PlanilhaTestCase(Base):
    def test_numeros_como_vem_das_planilhas(self) -> None:
        casos = {
            "1.500": 1500.0, "12.000": 12000.0, "R$ 2.350": 2350.0, "1.234.567": 1234567.0,
            "1.500,00": 1500.0, "1,234.56": 1234.56, "1234.56": 1234.56, "1,5": 1.5,
            "12,345": 12.345, "0.5": 0.5, "1.5": 1.5, "1,500,000": 1500000.0, "": 0.0,
        }
        for texto, esperado in casos.items():
            self.assertEqual(_numero(texto), esperado, texto)

    def test_o_que_sai_daqui_volta_igual(self) -> None:
        self.estoque.criar(Produto(codigo="A", nome="Queijo", unidade="KG", quantidade=12.345,
                                   preco_custo=1500.0, preco_venda=2350.5))
        previa = self.estoque.prever_importacao(self.estoque.exportar_produtos_csv())
        produto = previa.atualizar[0]
        self.assertEqual((produto.quantidade, produto.preco_custo, produto.preco_venda),
                         (12.345, 1500.0, 2350.5))

    def test_importacao_e_tudo_ou_nada(self) -> None:
        planilha = "codigo;nome\nA;Um\nB;Dois\n"
        original = self.estoque.criar
        chamadas = []

        def falha(produto):
            chamadas.append(produto.codigo)
            if len(chamadas) == 2:
                raise RuntimeError("disco cheio")
            return original(produto)

        self.estoque.criar = falha
        with self.assertRaises(RuntimeError):
            self.estoque.importar(planilha)
        self.estoque.criar = original
        self.assertEqual(self.estoque.listar(), [])

    def test_prazo_padrao(self) -> None:
        self.assertGreater(vencimento_padrao(), date.today().isoformat())


if __name__ == "__main__":
    unittest.main()
