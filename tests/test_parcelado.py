"""Venda parcelada: uma venda so, uma conta a receber por mes.

O pedido veio de quem vende login com mensalidade: sem isso, doze meses eram
doze lancamentos feitos a mao. O que se protege aqui: a venda nasce uma vez, o
Financeiro cobra cada parcela em separado, e a opcao so aparece onde a parcela
tem para onde ir.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from PySide6.QtWidgets import QApplication

from dumtech.apps.financeiro.contas import abrir_contas
from dumtech.apps.financeiro.models import somar_meses
from dumtech.apps.vendas import financeiro
from dumtech.apps.vendas.database import open_database
from dumtech.apps.vendas.models import (
    CONCLUIDA,
    ItemVenda,
    Pagamento,
    Venda,
    VendaError,
)
from dumtech.apps.vendas.recibo import comprovante
from dumtech.apps.vendas.repository import VendasRepository
from dumtech.core.pagamentos import FORMAS, PARCELADO, formas_do_balcao

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class ParceladoBase(unittest.TestCase):
    def setUp(self) -> None:
        pasta = Path(tempfile.mkdtemp())
        self.banco = open_database(pasta / "vendas.db")
        self.repo = VendasRepository(self.banco)
        self.contas = abrir_contas(pasta / "financeiro.db")
        self.addCleanup(self.banco.close)
        self.addCleanup(self.contas.close)

    def vender(self, total: float = 360.0, pagamentos=None) -> Venda:
        venda = Venda(cliente="Ana", itens=[
            ItemVenda(descricao="Login", quantidade=1, valor_unitario=total)])
        pagamentos = pagamentos or [
            Pagamento(forma=PARCELADO, valor=total, recebido=total, parcelas=12)]
        venda = self.repo.finalizar(venda, pagamentos)
        self.recado = financeiro.registrar(self.contas, venda)
        return venda

    def parcelas(self):
        return [item for item in self.contas.repository.listar(cancelados=True)
                if item.parcelas]


class VendaParceladaTestCase(ParceladoBase):
    def test_doze_meses_viram_doze_contas(self) -> None:
        venda = self.vender()

        parcelas = sorted(self.parcelas(), key=lambda item: item.parcela)
        self.assertEqual(len(parcelas), 12)
        self.assertTrue(all(item.valor == 30.0 for item in parcelas))
        self.assertTrue(all(item.cliente == "Ana" for item in parcelas))
        self.assertFalse(any(item.pago for item in parcelas), "ninguem pagou ainda")
        self.assertEqual(parcelas[0].descricao_completa, f"Venda {venda.numero} (1/12)")
        self.assertEqual(self.recado.strip(), "12 parcelas lançadas no Financeiro.")

    def test_a_primeira_vence_na_data_da_venda_e_as_outras_todo_mes(self) -> None:
        self.vender()
        parcelas = sorted(self.parcelas(), key=lambda item: item.parcela)
        hoje = date.today()
        self.assertEqual([item.vencimento for item in parcelas],
                         [somar_meses(hoje, n).isoformat() for n in range(12)])

    def test_centavos_nao_somem_na_divisao(self) -> None:
        self.vender(100.0, [Pagamento(forma=PARCELADO, valor=100.0, recebido=100.0, parcelas=3)])
        self.assertEqual(round(sum(item.valor for item in self.parcelas()), 2), 100.0)

    def test_a_venda_conclui_e_a_cobranca_mora_no_financeiro(self) -> None:
        venda = self.vender()

        self.assertEqual(venda.status, CONCLUIDA)
        lida = self.repo.obter(venda.id)
        self.assertEqual(lida.forma_pagamento, "Parcelado 12x")
        self.assertEqual(lida.parcelamento.parcelas, 12)
        self.assertEqual(self.repo.resumo().total_mes, 360.0)
        self.assertEqual(self.repo.resumo().por_forma, [("Parcelado", 360.0)])

    def test_entrada_na_hora_e_o_resto_parcelado(self) -> None:
        self.vender(pagamentos=[
            Pagamento(forma="Pix", valor=30.0, recebido=30.0),
            Pagamento(forma=PARCELADO, valor=330.0, recebido=330.0, parcelas=11),
        ])
        repositorio = self.contas.repository

        self.assertEqual(repositorio.resumo().recebido_mes, 30.0, "a entrada ja entrou")
        self.assertEqual(repositorio.resumo().a_receber, 330.0)
        self.assertEqual(len(self.parcelas()), 11)

    def test_registrar_de_novo_nao_recebe_parcela_sozinho(self) -> None:
        venda = self.vender()
        self.assertEqual(financeiro.registrar(self.contas, self.repo.obter(venda.id)), "")
        self.assertFalse(any(item.pago for item in self.parcelas()))
        self.assertEqual(len(self.parcelas()), 12)

    def test_duas_linhas_parceladas_nao_fecham(self) -> None:
        with self.assertRaises(VendaError):
            self.repo.conferir_pagamento(100.0, [
                Pagamento(forma=PARCELADO, valor=50.0, recebido=50.0, parcelas=2),
                Pagamento(forma=PARCELADO, valor=50.0, recebido=50.0, parcelas=3),
            ])

    def test_parcelado_nao_se_mistura_com_prazo(self) -> None:
        """A sobra do parcelado entra como recebida: prazo ninguem pagou."""
        with self.assertRaises(VendaError):
            self.repo.conferir_pagamento(100.0, [
                Pagamento(forma="Prazo", valor=40.0, recebido=40.0),
                Pagamento(forma=PARCELADO, valor=60.0, recebido=60.0, parcelas=3),
            ])

    def test_sem_cliente_nao_ha_de_quem_cobrar(self) -> None:
        venda = Venda(itens=[ItemVenda(descricao="Login", quantidade=1, valor_unitario=360.0)])
        with self.assertRaisesRegex(VendaError, "cliente"):
            self.repo.finalizar(venda, [
                Pagamento(forma=PARCELADO, valor=360.0, recebido=360.0, parcelas=12)])
        self.assertEqual(self.repo.listar(), [], "nada foi gravado")

    def test_valor_que_nao_cobre_as_parcelas_nao_passa(self) -> None:
        """R$ 0,05 em 12x daria onze parcelas de zero, e a serie ficaria pela metade."""
        venda = Venda(cliente="Ana", itens=[
            ItemVenda(descricao="Login", quantidade=1, valor_unitario=0.05)])
        with self.assertRaisesRegex(VendaError, "parcelas"):
            self.repo.finalizar(venda, [
                Pagamento(forma=PARCELADO, valor=0.05, recebido=0.05, parcelas=12)])
        self.assertEqual(self.parcelas(), [])

    def test_devolucao_nao_serve_para_venda_parcelada(self) -> None:
        """Devolver deixaria as parcelas cobrando e tiraria dinheiro da gaveta."""
        venda = self.repo.obter(self.vender().id)
        with self.assertRaisesRegex(VendaError, "cancele"):
            self.repo.devolver(venda.id, [(venda.itens[0].id, 1)])

    def test_parcelado_sem_quantidade_e_recusado(self) -> None:
        """Digitado onde nao e oferecido, viraria pagamento a vista calado."""
        with self.assertRaisesRegex(VendaError, "parcelas"):
            self.repo.conferir_pagamento(100.0, [
                Pagamento(forma="parcelado", valor=100.0, recebido=100.0)])

    def test_o_comprovante_diz_em_quantas_vezes(self) -> None:
        venda = self.vender()
        self.assertIn("Parcelado 12x", comprovante(self.repo.obter(venda.id)))

    def test_a_forma_antiga_continua_igual(self) -> None:
        venda = self.vender(30.0, [Pagamento(forma="Pix", valor=30.0, recebido=30.0)])
        self.assertIsNone(self.repo.obter(venda.id).parcelamento)
        self.assertEqual(self.repo.obter(venda.id).forma_pagamento, "Pix")


class CancelarParceladaTestCase(ParceladoBase):
    def _receber_parcelas(self, quantas: int) -> None:
        ordenadas = sorted(self.parcelas(), key=lambda item: item.parcela)
        for parcela in ordenadas[:quantas]:
            self.contas.repository.quitar(parcela.id)

    def test_cancela_o_que_falta_e_o_que_entrou_fica(self) -> None:
        venda = self.vender()
        self._receber_parcelas(3)

        recado = financeiro.registrar(self.contas, self.repo.cancelar(venda.id, "Parou de pagar"))

        repositorio = self.contas.repository
        self.assertEqual(repositorio.resumo().recebido_mes, 90.0)
        self.assertEqual(repositorio.resumo().a_receber, 0.0)
        self.assertEqual(sorted({item.situacao for item in self.parcelas()}),
                         ["Cancelado", "Recebido"])
        self.assertIn("9 parcela(s)", recado)

    def test_parcela_recebida_em_parte_nao_perde_o_que_entrou(self) -> None:
        venda = self.vender()
        parcela = sorted(self.parcelas(), key=lambda item: item.parcela)[1]
        self.contas.repository.baixar(parcela.id, 10.0)

        financeiro.registrar(self.contas, self.repo.cancelar(venda.id, "Parou de pagar"))

        resumo = self.contas.repository.resumo()
        self.assertEqual(resumo.recebido_mes, 10.0)
        self.assertEqual(resumo.a_receber, 0.0, "a venda acabou: o resto nao e mais cobrado")
        lancamento = self.contas.repository.obter(parcela.id)
        self.assertTrue(lancamento.pago)
        self.assertEqual(lancamento.valor, 10.0)
        self.assertIn("Parou de pagar", lancamento.observacoes)

    def test_a_entrada_tambem_fica(self) -> None:
        venda = self.vender(pagamentos=[
            Pagamento(forma="Pix", valor=30.0, recebido=30.0),
            Pagamento(forma=PARCELADO, valor=330.0, recebido=330.0, parcelas=11),
        ])
        financeiro.registrar(self.contas, self.repo.cancelar(venda.id, "Parou de pagar"))
        self.assertEqual(self.contas.repository.resumo().recebido_mes, 30.0)

    def test_acertar_ao_abrir_nao_estorna_parcela_paga(self) -> None:
        """O acerto roda a cada abertura: nao pode desfazer dinheiro que entrou."""
        venda = self.vender()
        self._receber_parcelas(2)
        financeiro.registrar(self.contas, self.repo.cancelar(venda.id, "Parou de pagar"))

        financeiro.conciliar(self.repo, self.contas)

        self.assertEqual(self.contas.repository.resumo().recebido_mes, 60.0)


class FormasTestCase(unittest.TestCase):
    def test_parcelado_e_uma_forma_que_a_loja_pode_esconder(self) -> None:
        self.assertIn(PARCELADO, FORMAS)
        self.assertNotIn(PARCELADO, formas_do_balcao((PARCELADO,), parcelavel=True))

    def test_so_aparece_onde_a_parcela_tem_para_onde_ir(self) -> None:
        self.assertNotIn(PARCELADO, formas_do_balcao())
        self.assertIn(PARCELADO, formas_do_balcao(parcelavel=True))


class ReceberParceladoTestCase(unittest.TestCase):
    def _dialogo(self, total: float = 360.0, parcelavel: bool = True, cliente: str = "Ana"):
        from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

        dialogo = PagamentoDialog(total, "teste", parcelavel=parcelavel, cliente=cliente)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def _formas(self, dialogo) -> list[str]:
        return [dialogo.forma.itemText(i) for i in range(dialogo.forma.count())]

    def test_nao_oferece_quando_nao_da_para_parcelar(self) -> None:
        self.assertNotIn(PARCELADO, self._formas(self._dialogo(parcelavel=False)))
        self.assertIn(PARCELADO, self._formas(self._dialogo()))

    def test_escolher_parcelado_troca_o_recebido_pelas_parcelas(self) -> None:
        dialogo = self._dialogo()
        self.assertFalse(dialogo.campo_parcelas.isVisibleTo(dialogo))

        dialogo.forma.setCurrentText(PARCELADO)

        self.assertTrue(dialogo.campo_parcelas.isVisibleTo(dialogo))
        self.assertFalse(dialogo.campo_recebido.isVisibleTo(dialogo))
        self.assertIn("12x de R$ 30,00", dialogo.nota_parcelas.text())

    def test_a_nota_acompanha_a_quantidade(self) -> None:
        dialogo = self._dialogo()
        dialogo.forma.setCurrentText(PARCELADO)
        dialogo.parcelas.setValue(6)
        self.assertIn("6x de R$ 60,00", dialogo.nota_parcelas.text())

    def test_voltar_para_outra_forma_devolve_o_recebido(self) -> None:
        dialogo = self._dialogo()
        dialogo.forma.setCurrentText(PARCELADO)
        dialogo.forma.setCurrentText("Dinheiro")
        self.assertTrue(dialogo.campo_recebido.isVisibleTo(dialogo))
        self.assertFalse(dialogo.campo_parcelas.isVisibleTo(dialogo))
        self.assertFalse(dialogo.nota_parcelas.isVisibleTo(dialogo))

    def test_lancar_grava_a_quantidade_na_linha(self) -> None:
        dialogo = self._dialogo()
        dialogo.forma.setCurrentText(PARCELADO)
        dialogo._lancar()

        self.assertEqual(dialogo.pagamentos[0].parcelas, 12)
        self.assertEqual(dialogo.pagamentos[0].rotulo, "Parcelado 12x")
        self.assertTrue(dialogo.botao_receber.isEnabled())

    def test_sem_cliente_avisa_antes_de_cobrar_o_resto(self) -> None:
        """No Balcao o Pix ja pode ter sido pago: recusar depois perderia tudo."""
        dialogo = self._dialogo(cliente="")
        dialogo.forma.setCurrentText(PARCELADO)
        dialogo._lancar()
        self.assertEqual(dialogo.pagamentos, [])
        self.assertIn("cliente", dialogo.aviso.text())

    def test_a_segunda_linha_parcelada_e_recusada_na_hora(self) -> None:
        dialogo = self._dialogo()
        dialogo.forma.setCurrentText(PARCELADO)
        dialogo.valor.setValue(100.0)
        dialogo._lancar()
        dialogo.forma.setCurrentText(PARCELADO)
        dialogo.valor.setValue(100.0)
        dialogo._lancar()
        self.assertEqual(len(dialogo.pagamentos), 1)

    def test_o_fluxo_do_dinheiro_continua_igual(self) -> None:
        dialogo = self._dialogo(50.0)
        dialogo.recebido.setValue(100.0)
        dialogo._lancar()
        self.assertEqual(dialogo.pagamentos[0].parcelas, 0)
        self.assertEqual(dialogo.troco, 50.0)


class TelasDeVendaTestCase(ParceladoBase):
    def _dialogo(self, venda=None, contas="padrao"):
        from dumtech.apps.vendas.ui.venda_dialog import VendaDialog

        dialogo = VendaDialog(self.repo, venda,
                              contas=self.contas if contas == "padrao" else contas)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def _formas(self, dialogo) -> list[str]:
        return [dialogo.forma.itemText(i) for i in range(dialogo.forma.count())]

    def _preencher(self, dialogo) -> None:
        dialogo.itens.set_items([{"descricao": "Login", "quantidade": 1,
                                  "valor_unitario": 360.0}])

    def test_lancar_venda_parcelada_a_mao(self) -> None:
        dialogo = self._dialogo()
        self._preencher(dialogo)
        dialogo.cliente.setText("Ana")
        dialogo.forma.setCurrentText(PARCELADO)
        self.assertFalse(dialogo.status.isEnabled(), "parcelada conclui: quem cobra e o Financeiro")
        dialogo.parcelas.setValue(12)

        dialogo.salvar()

        self.assertEqual(dialogo.venda.status, CONCLUIDA)
        self.assertEqual(len(self.parcelas()), 12)
        self.assertIn("12 parcelas", dialogo.recado)

    def test_sem_financeiro_nao_oferece_parcelado(self) -> None:
        self.assertNotIn(PARCELADO, self._formas(self._dialogo(contas=None)))

    def test_editar_venda_nao_oferece_parcelado(self) -> None:
        venda = self.vender(30.0, [Pagamento(forma="Pix", valor=30.0, recebido=30.0)])
        self.assertNotIn(PARCELADO, self._formas(self._dialogo(self.repo.obter(venda.id))))

    def test_a_lista_nao_edita_venda_parcelada(self) -> None:
        """Mudar o total depois deixaria as parcelas do Financeiro erradas."""
        from dumtech.apps.vendas.ui.vendas_view import VendasView

        self.vender()
        view = VendasView(self.repo, contas=self.contas)
        self.addCleanup(view.deleteLater)
        view.refresh()
        view.tabela.selectRow(0)

        self.assertFalse(view.botao_editar.isEnabled())
        self.assertFalse(view.botao_devolver.isEnabled(), "cancelar e que encerra as parcelas")
        with mock.patch.object(view, "_lancar") as abrir:
            view.editar()  # o duplo clique cai aqui
        abrir.assert_not_called()

    def test_o_balcao_so_oferece_com_financeiro(self) -> None:
        from dumtech.apps.vendas.ui import balcao_view

        for contas, esperado in ((self.contas, True), (None, False)):
            view = balcao_view.BalcaoView(self.repo, contas=contas)
            self.addCleanup(view.deleteLater)
            view.itens.append(ItemVenda(descricao="Login", quantidade=1, valor_unitario=30.0))
            with mock.patch.object(balcao_view, "PagamentoDialog") as dialogo:
                dialogo.return_value.exec.return_value = False
                view.receber()
            self.assertEqual(dialogo.call_args.kwargs["parcelavel"], esperado)

    def test_o_balcao_lanca_as_parcelas(self) -> None:
        from dumtech.apps.vendas.ui import balcao_view

        view = balcao_view.BalcaoView(self.repo, contas=self.contas)
        self.addCleanup(view.deleteLater)
        view.itens.append(ItemVenda(descricao="Login", quantidade=1, valor_unitario=360.0))
        view.cliente.setText("Ana")
        pagamentos = [Pagamento(forma=PARCELADO, valor=360.0, recebido=360.0, parcelas=12)]
        with mock.patch.object(balcao_view, "PagamentoDialog") as dialogo:
            dialogo.return_value.exec.return_value = True
            dialogo.return_value.pagamentos = pagamentos
            dialogo.return_value.vencimento_iso = ""
            view.receber()

        self.assertEqual(len(self.parcelas()), 12)

    def test_ordens_e_financeiro_nao_ganham_a_forma(self) -> None:
        self.assertNotIn(PARCELADO, self.contas.repository.formas())


if __name__ == "__main__":
    unittest.main()
