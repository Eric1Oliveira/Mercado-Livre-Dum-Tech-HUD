"""O dinheiro que anda precisa aparecer no Financeiro, para os dois lados.

Tres buracos da mesma familia: venda recebida que nao entrava no saldo,
devolucao que o Financeiro nunca ficava sabendo e cancelamento que mexia no
estoque sem ter por que. O que se protege aqui: o numero que o dono le bate com
o que aconteceu, e a data do dinheiro continua sendo a do dia em que ele andou.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from PySide6.QtWidgets import QApplication

from dumtech.apps.estoque.catalog import CatalogoEstoque
from dumtech.apps.estoque.database import open_database as abrir_estoque
from dumtech.apps.estoque.models import Produto
from dumtech.apps.estoque.repository import EstoqueRepository
from dumtech.apps.financeiro.models import CAIXA, DESPESA, Conta
from dumtech.apps.vendas import financeiro
from dumtech.apps.vendas.database import open_database as abrir_vendas
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
from dumtech.apps.vendas.repository import VendasRepository

from .test_venda_cancelada import VendaCanceladaBase

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class FinanceiroBase(VendaCanceladaBase):
    def setUp(self) -> None:
        super().setUp()
        self.conta = self.contas.repository.criar_conta(Conta(nome="Caixa da loja", tipo=CAIXA))

    def vender_duas(self) -> Venda:
        """Duas pecas de R$ 50 pagas no Pix."""
        venda = Venda(cliente="Ana", itens=[
            ItemVenda(descricao="Capa", quantidade=2, valor_unitario=50.0)])
        venda = self.repo.finalizar(venda, [Pagamento(forma="Pix", valor=100.0, recebido=100.0)])
        financeiro.registrar(self.contas, venda)
        return self.repo.obter(venda.id)

    def devolver(self, venda: Venda, quantas: int = 1, data: str = "") -> str:
        devolucao = self.repo.devolver(venda.id, [(venda.itens[0].id, quantas)], "Defeito", data)
        return financeiro.devolver(self.contas, self.repo.obter(venda.id), devolucao)

    def despesas(self):
        return [item for item in self.lancamentos() if item.tipo == DESPESA]


class SaldoTestCase(FinanceiroBase):
    def test_venda_recebida_entra_no_saldo(self) -> None:
        self.vender()
        self.assertEqual(self.contas.repository.saldo_total(), 30.0)

    def test_cancelar_tira_do_saldo(self) -> None:
        self.cancelar(self.vender())
        self.assertEqual(self.contas.repository.saldo_total(), 0.0)

    def test_receber_venda_a_prazo_entra_no_saldo(self) -> None:
        venda = self.vender(pagamentos=[Pagamento(forma="Prazo", valor=30.0, recebido=30.0)])
        self.assertEqual(self.contas.repository.saldo_total(), 0.0, "ainda nao pagou")

        recebida = self.repo.receber_pendente(
            venda.id, [Pagamento(forma="Pix", valor=30.0, recebido=30.0)])
        financeiro.registrar(self.contas, recebida)

        self.assertEqual(self.contas.repository.saldo_total(), 30.0)

    def test_conta_apagada_depois_cai_na_conta_padrao(self) -> None:
        """A conta prevista sumiu: a venda ainda tem que ser recebida."""
        repositorio = self.contas.repository
        venda = self.vender(pagamentos=[Pagamento(forma="Prazo", valor=30.0, recebido=30.0)])
        repositorio.excluir_conta(self.conta.id)
        nova = repositorio.criar_conta(Conta(nome="Banco", tipo="banco"))

        recebida = self.repo.receber_pendente(
            venda.id, [Pagamento(forma="Pix", valor=30.0, recebido=30.0)])
        recado = financeiro.registrar(self.contas, recebida)

        self.assertIn("Recebimento", recado)
        self.assertEqual(repositorio.obter_conta(nova.id).saldo, 30.0)


class SemContaCadastradaTestCase(VendaCanceladaBase):
    def test_quem_nao_tem_conta_continua_recebendo(self) -> None:
        self.vender()
        resumo = self.contas.repository.resumo()
        self.assertEqual(resumo.recebido_mes, 30.0)
        self.assertEqual(resumo.saldo_contas, 0.0)


class DevolucaoNoFinanceiroTestCase(FinanceiroBase):
    def test_devolucao_parcial_sai_como_despesa(self) -> None:
        recado = self.devolver(self.vender_duas())

        resumo = self.contas.repository.resumo()
        self.assertEqual(resumo.recebido_mes, 100.0, "a venda aconteceu")
        self.assertEqual(resumo.pago_mes, 50.0, "e o dinheiro voltou")
        self.assertEqual(resumo.saldo_contas, 50.0)
        self.assertIn("Financeiro", recado)

        despesa = self.despesas()[0]
        self.assertTrue(despesa.pago)
        self.assertEqual(despesa.categoria, "Devoluções")
        self.assertEqual(despesa.cliente, "Ana")
        self.assertIn("Devolução da venda", despesa.descricao)
        self.assertIn("Defeito", despesa.observacoes)

    def test_devolver_tudo_zera_o_resultado(self) -> None:
        venda = self.vender_duas()
        self.devolver(venda, 2)

        self.assertEqual(self.repo.obter(venda.id).status, DEVOLVIDA)
        resumo = self.contas.repository.resumo()
        self.assertEqual(resumo.saldo_mes, 0.0)
        self.assertEqual(resumo.saldo_contas, 0.0)

    def test_o_dinheiro_sai_no_dia_da_devolucao(self) -> None:
        """O mes da venda nao muda: e no dia da devolucao que o dinheiro saiu."""
        ontem = (date.today() - timedelta(days=1)).isoformat()
        self.devolver(self.vender_duas(), data=ontem)
        despesa = self.despesas()[0]
        self.assertEqual(despesa.pago_em, ontem)
        self.assertEqual(despesa.vencimento, ontem)

    def test_sai_pela_conta_por_onde_entrou(self) -> None:
        repositorio = self.contas.repository
        outra = repositorio.criar_conta(Conta(nome="Outra", tipo="banco"))
        venda = self.vender_duas()

        self.devolver(venda)

        self.assertEqual(repositorio.obter_conta(self.conta.id).saldo, 50.0)
        self.assertEqual(repositorio.obter_conta(outra.id).saldo, 0.0)

    def test_baixa_antiga_sem_conta_nao_tira_do_saldo(self) -> None:
        """Venda de antes da correcao nunca somou no saldo: nao pode subtrair."""
        venda = self.vender_duas()
        self.contas.database.execute("UPDATE baixas SET conta_id = 0")

        self.devolver(venda)

        self.assertEqual(self.contas.repository.saldo_total(), 0.0)

    def test_conta_em_aberto_so_deixa_de_ser_cobrada(self) -> None:
        """Quem nao recebeu nao devolve dinheiro: a conta e que encolhe."""
        venda = self.vender_duas()
        receita = self.lancamentos()[0]
        self.contas.repository.estornar_tudo(receita.id)

        self.devolver(venda)

        lancamento = self.contas.repository.obter(receita.id)
        self.assertEqual(lancamento.valor, 50.0)
        self.assertEqual(lancamento.em_aberto, 50.0)
        self.assertEqual(self.despesas(), [])
        self.assertIn("Devolução de R$ 50,00: Defeito", lancamento.observacoes,
                      "o valor mudou: precisa dizer por que")

    def test_conta_em_aberto_devolvida_inteira_e_cancelada(self) -> None:
        venda = self.vender_duas()
        receita = self.lancamentos()[0]
        self.contas.repository.estornar_tudo(receita.id)

        self.devolver(venda, 2)

        self.assertEqual(self.contas.repository.obter(receita.id).situacao, "Cancelado")
        self.assertEqual(self.contas.repository.resumo().a_receber, 0.0)

    def test_parte_recebida_e_parte_em_aberto(self) -> None:
        """Recebeu 70 de 100 e voltaram 50: 30 somem da conta e 20 saem do caixa."""
        venda = self.vender_duas()
        repositorio = self.contas.repository
        receita = self.lancamentos()[0]
        repositorio.estornar_tudo(receita.id)
        repositorio.baixar(receita.id, 70.0, conta_id=self.conta.id)

        self.devolver(venda)

        lancamento = repositorio.obter(receita.id)
        self.assertEqual(lancamento.valor, 70.0)
        self.assertTrue(lancamento.pago, "o que sobrou da conta ja estava pago")
        self.assertEqual(self.despesas()[0].valor, 20.0)
        self.assertEqual(repositorio.saldo_total(), 50.0)

    def test_venda_que_nunca_entrou_no_financeiro_nao_gera_despesa(self) -> None:
        """Antes da 1.5.4 a venda a vista nao atravessava: nao ha o que desfazer."""
        venda = self.repo.finalizar(
            Venda(cliente="Ana", itens=[
                ItemVenda(descricao="Capa", quantidade=2, valor_unitario=50.0)]),
            [Pagamento(forma="Pix", valor=100.0, recebido=100.0)],
        )
        self.assertEqual(self.devolver(self.repo.obter(venda.id)), "")
        self.assertEqual(self.lancamentos(), [])

    def test_cancelar_depois_de_devolver_nao_conta_duas_vezes(self) -> None:
        venda = self.vender_duas()
        self.devolver(venda)

        self.cancelar(venda, "Desistiu do resto")

        resumo = self.contas.repository.resumo()
        self.assertEqual(resumo.recebido_mes, 0.0)
        self.assertEqual(resumo.pago_mes, 0.0)
        self.assertEqual(resumo.saldo_contas, 0.0)
        self.assertEqual({item.situacao for item in self.lancamentos()}, {"Cancelado"})

    def test_duas_devolucoes_da_mesma_venda(self) -> None:
        venda = self.vender_duas()
        self.devolver(venda)
        self.devolver(self.repo.obter(venda.id))

        self.assertEqual(len(self.despesas()), 2)
        self.assertEqual(self.contas.repository.saldo_total(), 0.0)

    def test_a_ponte_com_defeito_nao_desfaz_a_devolucao(self) -> None:
        class Quebrada:
            def devolver(self, *_args, **_kwargs):
                raise RuntimeError("banco trancado")

        venda = self.vender_duas()
        devolucao = self.repo.devolver(venda.id, [(venda.itens[0].id, 1)])
        with self.assertLogs("dumtech.apps.vendas.financeiro", "ERROR"):
            self.assertIn("na mão", financeiro.devolver(Quebrada(), venda, devolucao))

    def test_sem_financeiro_na_licenca_nada_muda(self) -> None:
        venda = self.vender_duas()
        devolucao = self.repo.devolver(venda.id, [(venda.itens[0].id, 1)])
        self.assertEqual(financeiro.devolver(None, venda, devolucao), "")

    def test_devolver_pela_lista_avisa_o_financeiro(self) -> None:
        from dumtech.apps.vendas.ui import vendas_view

        venda = self.vender_duas()
        view = vendas_view.VendasView(self.repo, contas=self.contas)
        self.addCleanup(view.deleteLater)
        view.refresh()
        view.tabela.selectRow(0)

        dialogo = mock.Mock(devolucao=self.repo.devolver(venda.id, [(venda.itens[0].id, 1)]))
        dialogo.exec.return_value = True
        with mock.patch.object(vendas_view, "DevolucaoDialog", return_value=dialogo):
            view._devolver()

        self.assertEqual(self.contas.repository.resumo().pago_mes, 50.0)
        self.assertIn("Financeiro", view.aviso.text())


class VendaPendenteTestCase(FinanceiroBase):
    """A pendente nao recebeu nada: devolver nao tem o que devolver."""

    def _pendente(self) -> Venda:
        return self.repo.obter(self.vender(
            pagamentos=[Pagamento(forma="Prazo", valor=30.0, recebido=30.0)]).id)

    def test_devolucao_e_recusada(self) -> None:
        venda = self._pendente()
        with self.assertRaisesRegex(VendaError, "cancele"):
            self.repo.devolver(venda.id, [(venda.itens[0].id, 1)])

    def test_o_botao_nao_acende(self) -> None:
        from dumtech.apps.vendas.ui.vendas_view import VendasView

        self._pendente()
        view = VendasView(self.repo, contas=self.contas)
        self.addCleanup(view.deleteLater)
        view.refresh()
        view.tabela.selectRow(0)
        self.assertFalse(view.botao_devolver.isEnabled())
        self.assertTrue(view.botao_cancelar.isEnabled(), "cancelar e o caminho")


class SituacaoAoEditarTestCase(VendaCanceladaBase):
    """Cancelar tem botao proprio: e la que motivo, estoque e Financeiro andam juntos."""

    def _situacoes(self, venda=None) -> list[str]:
        from dumtech.apps.vendas.ui.venda_dialog import VendaDialog

        dialogo = VendaDialog(self.repo, venda, contas=self.contas)
        self.addCleanup(dialogo.deleteLater)
        return [dialogo.status.itemData(i) for i in range(dialogo.status.count())]

    def test_lancar_venda_nao_oferece_cancelada_nem_devolvida(self) -> None:
        self.assertEqual(self._situacoes(), [CONCLUIDA, PENDENTE])

    def test_editar_nao_oferece_cancelada(self) -> None:
        venda = self.vender()
        self.assertNotIn(CANCELADA, self._situacoes(self.repo.obter(venda.id)))

    def test_situacao_antiga_continua_na_lista(self) -> None:
        """Sem ela, o campo cairia em Concluida e salvar mudaria a venda calado."""
        venda = self.vender()
        self.repo.definir_status(venda.id, DEVOLVIDA)
        self.assertIn(DEVOLVIDA, self._situacoes(self.repo.obter(venda.id)))


class EstoqueAoCancelarTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pasta = Path(tempfile.mkdtemp())
        self.banco_estoque = abrir_estoque(pasta / "estoque.db")
        self.addCleanup(self.banco_estoque.close)
        self.produto = EstoqueRepository(self.banco_estoque).criar(Produto(
            codigo="A1", nome="Cafe", unidade="UN", quantidade=10, preco_venda=20.0))
        self.catalogo = CatalogoEstoque(self.banco_estoque)
        self.banco = abrir_vendas(pasta / "vendas.db")
        self.addCleanup(self.banco.close)
        self.repo = VendasRepository(self.banco, catalogo=self.catalogo)

    def _venda(self, **campos) -> Venda:
        return Venda(cliente="Ana", itens=[ItemVenda(
            descricao="Cafe", quantidade=3, valor_unitario=20.0,
            produto_id=self.produto.id, codigo="A1")], **campos)

    def test_pendente_que_nunca_saiu_nao_inventa_saldo(self) -> None:
        venda = self.repo.lancar(self._venda(numero="VEN-1", status=PENDENTE))
        self.assertEqual(self.catalogo.buscar("A1").saldo, 10.0)

        self.repo.cancelar(venda.id, "Desistiu")

        self.assertEqual(self.catalogo.buscar("A1").saldo, 10.0)

    def test_a_prazo_do_balcao_que_saiu_volta(self) -> None:
        venda = self.repo.finalizar(
            self._venda(), [Pagamento(forma="Prazo", valor=60.0, recebido=60.0)])
        self.assertEqual(self.catalogo.buscar("A1").saldo, 7.0)

        self.repo.cancelar(venda.id, "Desistiu")

        self.assertEqual(self.catalogo.buscar("A1").saldo, 10.0)

    def test_paga_volta_inteira(self) -> None:
        venda = self.repo.finalizar(
            self._venda(), [Pagamento(forma="Pix", valor=60.0, recebido=60.0)])
        self.repo.cancelar(venda.id, "Desistiu")
        self.assertEqual(self.catalogo.buscar("A1").saldo, 10.0)


if __name__ == "__main__":
    unittest.main()
