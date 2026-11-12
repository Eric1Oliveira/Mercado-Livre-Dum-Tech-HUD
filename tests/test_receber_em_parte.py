"""Venda a prazo paga aos poucos, entrada no parcelado e o Pix fora da gaveta.

Pedidos de uma cliente (11/2026), nas palavras dela:

* "tenho uma conta de 150, ela nao vai pagar tudo hoje, vai dar 100 e o resto
  fica para outro dia" - o Receber so aceitava o valor inteiro;
* "se a pessoa da uma entrada de 300 hoje e mais tres de 350, eu nao consigo";
* "entra no caixa como dinheiro, e e Pix" - a conta recebida em partes ia
  inteira para a gaveta, com a forma da ULTIMA parte.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from PySide6.QtWidgets import QApplication

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
from dumtech.apps.vendas.repository import VendasRepository
from dumtech.core.database import Database
from dumtech.core.pagamentos import FORMAS as FORMAS_TODAS
from dumtech.core.pagamentos import PARCELADO, PRAZO, forma_canonica

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = Path(tempfile.mkdtemp(prefix="dt_parte_"))
        self.banco = open_database(self.pasta / "vendas.db")
        self.addCleanup(self.banco.close)
        self.repo = VendasRepository(self.banco)
        self.contas = abrir_contas(self.pasta / "financeiro.db")
        self.addCleanup(self.contas.close)

    def a_prazo(self, total: float = 150.0, entrada: list[Pagamento] | None = None) -> Venda:
        """A conta do balcao: o cliente leva e fica devendo."""
        pagos = entrada or []
        devendo = total - sum(p.valor for p in pagos)
        venda = self.repo.finalizar(
            Venda(cliente="Nena", itens=[ItemVenda(descricao="Tecido", valor_unitario=total)]),
            pagos + [Pagamento(forma=PRAZO, valor=devendo, recebido=devendo)],
        )
        financeiro.registrar(self.contas, venda)
        return venda

    def conta(self, venda: Venda):
        return self.contas._achar(venda.numero)

    def receber(self, venda: Venda, *linhas: Pagamento) -> Venda:
        recebida = self.repo.receber_pendente(venda.id, list(linhas))
        self.recado = financeiro.receber(self.contas, recebida, list(linhas))
        return recebida


def pix(valor: float) -> Pagamento:
    return Pagamento(forma="Pix", valor=valor, recebido=valor)


def dinheiro(valor: float, entregue: float = 0.0) -> Pagamento:
    return Pagamento(forma="Dinheiro", valor=valor, recebido=entregue or valor)


class ReceberEmParteTestCase(Base):
    def test_da_100_dos_150_e_o_resto_fica_em_aberto(self) -> None:
        venda = self.receber(self.a_prazo(), dinheiro(100.0))

        self.assertEqual(venda.status, PENDENTE)
        self.assertEqual(venda.em_aberto, 50.0)
        self.assertEqual([(p.forma, p.valor) for p in venda.pagamentos],
                         [("Dinheiro", 100.0), (PRAZO, 50.0)])
        self.assertIn("R$ 50,00", self.recado)

    def test_o_financeiro_cobra_so_o_que_falta(self) -> None:
        venda = self.receber(self.a_prazo(), pix(100.0))
        conta = self.conta(venda)
        self.assertFalse(conta.pago)
        self.assertEqual(conta.em_aberto, 50.0)
        self.assertEqual(self.contas.repository.baixas_de(conta.id)[0].forma, "Pix")

    def test_a_segunda_parte_quita_a_venda_e_a_conta(self) -> None:
        venda = self.receber(self.a_prazo(), pix(100.0))
        venda = self.receber(venda, dinheiro(50.0))

        self.assertEqual(venda.status, CONCLUIDA)
        self.assertEqual(venda.em_aberto, 0.0)
        self.assertEqual(venda.resumo_pagamento, "Pix + Dinheiro")
        conta = self.conta(venda)
        self.assertTrue(conta.pago)
        self.assertEqual(sorted(b.forma for b in self.contas.repository.baixas_de(conta.id)),
                         ["Dinheiro", "Pix"])

    def test_nao_recebe_mais_do_que_deve(self) -> None:
        venda = self.a_prazo()
        with self.assertRaises(VendaError):
            self.repo.receber_pendente(venda.id, [dinheiro(200.0)])
        self.assertEqual(self.repo.obter(venda.id).em_aberto, 150.0)

    def test_receber_nao_vira_prazo_nem_parcela_de_novo(self) -> None:
        venda = self.a_prazo()
        for linha in (Pagamento(forma=PRAZO, valor=50.0, recebido=50.0),
                      Pagamento(forma=PARCELADO, valor=50.0, recebido=50.0, parcelas=2)):
            with self.subTest(linha=linha.forma), self.assertRaises(VendaError):
                self.repo.receber_pendente(venda.id, [linha])

    def test_entrada_no_balcao_ja_entra_recebida_no_financeiro(self) -> None:
        """Antes a conta nascia com o valor cheio e cobrava a entrada de novo."""
        venda = self.a_prazo(150.0, [dinheiro(50.0)])
        self.assertEqual(venda.em_aberto, 100.0)
        self.assertEqual(self.conta(venda).em_aberto, 100.0)

    def test_venda_antiga_sem_conta_quita_com_a_entrada_junto(self) -> None:
        """Venda a prazo de antes da ponte: a conta nasce na hora de quitar."""
        venda = self.repo.finalizar(
            Venda(cliente="Nena", itens=[ItemVenda(descricao="x", valor_unitario=150.0)]),
            [dinheiro(50.0), Pagamento(forma=PRAZO, valor=100.0, recebido=100.0)],
        )  # sem registrar: o Financeiro nao sabe dela
        venda = self.receber(venda, pix(100.0))
        self.assertEqual(venda.status, CONCLUIDA)
        self.assertTrue(self.conta(venda).pago, "a entrada do balcao entra junto")

    def test_dinheiro_digitado_em_minuscula_da_troco(self) -> None:
        self.repo.abrir_caixa(0.0)
        venda = self.repo.receber_pendente(
            self.a_prazo().id, [Pagamento(forma="dinheiro", valor=100.0, recebido=120.0)])
        self.assertEqual(venda.pagamentos[0].forma, "Dinheiro")
        self.assertEqual(self.repo.conferencia().esperado, 100.0)

    def test_quitada_fica_no_caixa_em_que_foi_vendida(self) -> None:
        """O fechamento de um caixa nao muda depois que o cliente paga."""
        self.repo.abrir_caixa(0.0)
        venda = self.a_prazo()
        caixa_da_venda = venda.caixa_id
        self.repo.fechar_caixa(0.0)
        self.repo.abrir_caixa(0.0)
        quitada = self.receber(venda, pix(150.0))
        self.assertEqual(quitada.caixa_id, caixa_da_venda)
        self.assertEqual(self.repo.conferencia(caixa_da_venda).total_vendido, 150.0)

    def test_venda_sem_caixa_entra_no_caixa_em_que_quitou(self) -> None:
        venda = self.repo.lancar(Venda(numero=self.repo.proximo_numero(), cliente="Nena",
                                       status=PENDENTE,
                                       itens=[ItemVenda(descricao="x", valor_unitario=80.0)]))
        caixa = self.repo.abrir_caixa(0.0)
        self.assertEqual(self.receber(venda, pix(80.0)).caixa_id, caixa.id)

    def test_venda_da_proposta_sem_conta_ganha_a_conta_com_o_que_entrou(self) -> None:
        venda = self.repo.lancar(Venda(numero=self.repo.proximo_numero(), cliente="Nena",
                                       status=PENDENTE,
                                       itens=[ItemVenda(descricao="x", valor_unitario=150.0)]))
        venda = self.receber(venda, pix(100.0))
        self.assertEqual(self.conta(venda).em_aberto, 50.0)


class GavetaTestCase(Base):
    """So o dinheiro em especie conta na gaveta - em qualquer caixa que ele entre."""

    def test_pix_nao_entra_na_gaveta_como_dinheiro(self) -> None:
        venda = self.a_prazo()
        self.repo.abrir_caixa(20.0)
        self.receber(venda, pix(100.0))

        conferencia = self.repo.conferencia()
        self.assertEqual(conferencia.esperado, 20.0)
        self.assertIn(("Pix", 100.0), conferencia.por_forma)

    def test_cada_parte_entra_no_caixa_do_dia_em_que_chegou(self) -> None:
        self.repo.abrir_caixa(0.0)
        venda = self.a_prazo()
        primeiro = self.repo.caixa_aberto()
        self.repo.fechar_caixa(0.0)

        self.repo.abrir_caixa(10.0)
        self.receber(venda, pix(100.0), dinheiro(30.0, entregue=50.0))

        hoje = self.repo.conferencia()
        self.assertEqual(hoje.vendas_dinheiro, 50.0)
        self.assertEqual(hoje.trocos, 20.0)
        self.assertEqual(hoje.esperado, 40.0)  # 10 de abertura + 30 da conta
        self.assertEqual(dict(hoje.por_forma), {"Pix": 100.0, "Dinheiro": 30.0})
        antes = self.repo.conferencia(primeiro.id)
        self.assertEqual(antes.vendas_dinheiro, 0.0, "o caixa fechado nao ganha o dinheiro de hoje")

    def test_venda_comum_continua_contando_igual(self) -> None:
        self.repo.abrir_caixa(0.0)
        self.repo.finalizar(Venda(itens=[ItemVenda(descricao="x", valor_unitario=80.0)]),
                            [dinheiro(50.0, entregue=60.0), pix(30.0)])
        conferencia = self.repo.conferencia()
        self.assertEqual(conferencia.esperado, 50.0)
        self.assertEqual(conferencia.trocos, 10.0)
        self.assertEqual(conferencia.total_vendido, 80.0)


class FinanceiroNaTelaTestCase(Base):
    """A baixa feita na tela de contas chega a venda - parte por parte."""

    def setUp(self) -> None:
        super().setUp()
        self.destino = DestinoVendas(self.banco)
        self.tela = FinanceiroRepository(abrir_financeiro(self.pasta / "financeiro.db"))
        self.addCleanup(self.tela.db.close)
        ligar_modulos(self.tela, [self.destino], gaveta=self.destino)

    def test_ultima_parte_nao_fala_pelas_outras(self) -> None:
        """O caso da cliente: 100 no Pix, 50 em dinheiro - a gaveta espera 50."""
        self.repo.abrir_caixa(0.0)
        venda = self.a_prazo()
        conta = self.conta(venda)

        self.tela.baixar(conta.id, valor=100.0, forma="Pix")
        self.assertEqual(self.repo.obter(venda.id).em_aberto, 50.0)
        self.tela.baixar(conta.id, valor=50.0, forma="Dinheiro")

        lida = self.repo.obter(venda.id)
        self.assertEqual(lida.status, CONCLUIDA)
        self.assertEqual(lida.resumo_pagamento, "Pix + Dinheiro")
        self.assertEqual(self.repo.conferencia().esperado, 50.0)

    def test_forma_digitada_em_minuscula_tambem_e_dinheiro(self) -> None:
        self.repo.abrir_caixa(0.0)
        venda = self.a_prazo()
        self.tela.baixar(self.conta(venda).id, valor=40.0, forma="dinheiro")
        self.assertEqual(self.repo.conferencia().esperado, 40.0)

    def test_baixa_com_data_de_outro_dia_nao_entra_na_gaveta_de_hoje(self) -> None:
        self.repo.abrir_caixa(0.0)
        venda = self.a_prazo()
        ontem = (date.today() - timedelta(days=1)).isoformat()
        self.tela.baixar(self.conta(venda).id, valor=40.0, forma="Dinheiro", data=ontem)

        self.assertEqual(self.repo.obter(venda.id).em_aberto, 110.0)
        self.assertEqual(self.repo.conferencia().esperado, 0.0)

    def test_estornar_uma_parte_devolve_so_ela(self) -> None:
        venda = self.a_prazo()
        conta = self.conta(venda)
        self.tela.baixar(conta.id, valor=100.0, forma="Pix")
        self.tela.baixar(conta.id, valor=20.0, forma="Dinheiro")

        pix_baixa = next(b for b in self.tela.baixas_de(conta.id) if b.forma == "Pix")
        self.tela.estornar(pix_baixa.id)

        lida = self.repo.obter(venda.id)
        self.assertEqual(lida.em_aberto, 130.0)
        self.assertEqual([p.forma for p in lida.pagamentos], ["Dinheiro", PRAZO])

    def test_estornar_a_quitacao_reabre_a_venda(self) -> None:
        venda = self.a_prazo()
        conta = self.conta(venda)
        self.tela.baixar(conta.id, forma="Pix")
        self.assertEqual(self.repo.obter(venda.id).status, CONCLUIDA)

        self.tela.estornar(self.tela.baixas_de(conta.id)[0].id)
        lida = self.repo.obter(venda.id)
        self.assertEqual(lida.status, PENDENTE)
        self.assertEqual(lida.em_aberto, 150.0)

    def test_entrada_paga_no_balcao_nao_reabre(self) -> None:
        venda = self.a_prazo(150.0, [dinheiro(50.0)])
        conta = self.conta(venda)
        entrada = self.tela.baixas_de(conta.id)[0]
        self.tela.estornar(entrada.id)
        self.assertEqual(self.repo.obter(venda.id).em_aberto, 100.0)

    def test_desfazer_a_entrada_depois_de_quitar_nao_apaga_a_venda(self) -> None:
        """A revisao achou: caia no caminho antigo, que zerava todas as linhas."""
        ontem = (date.today() - timedelta(days=1)).isoformat()
        venda = self.repo.finalizar(
            Venda(cliente="Nena", data=ontem,
                  itens=[ItemVenda(descricao="x", valor_unitario=150.0)]),
            [dinheiro(50.0), Pagamento(forma=PRAZO, valor=100.0, recebido=100.0)],
        )
        financeiro.registrar(self.contas, venda)
        conta = self.conta(venda)
        # hoje ele paga 50 no Pix e mais 50 no Pix: uma parte tem o valor da entrada
        self.tela.baixar(conta.id, valor=50.0, forma="Pix")
        self.tela.baixar(conta.id, valor=50.0, forma="Pix")
        self.assertEqual(self.repo.obter(venda.id).status, CONCLUIDA)

        entrada = next(b for b in self.tela.baixas_de(conta.id) if b.data == ontem)
        self.tela.estornar(entrada.id)

        lida = self.repo.obter(venda.id)
        self.assertEqual(lida.status, CONCLUIDA)
        self.assertEqual([(p.forma, p.valor) for p in lida.pagamentos],
                         [("Dinheiro", 50.0), ("Pix", 50.0), ("Pix", 50.0)])


class MigracaoTestCase(unittest.TestCase):
    def test_pagamento_antigo_fica_no_caixa_da_propria_venda(self) -> None:
        caminho = Path(tempfile.mkdtemp(prefix="dt_parte_m_")) / "vendas.db"
        antigo = Database(caminho, MIGRATIONS[:7])
        conn = antigo.connection
        caixa = conn.execute("INSERT INTO caixas (aberto_em, valor_abertura) "
                             "VALUES ('2026-11-01T08:00:00', 10)").lastrowid
        venda = conn.execute(
            "INSERT INTO vendas (numero, data, criado_em, caixa_id, troco) "
            "VALUES ('V1', '2026-11-01', '2026-11-01', ?, 5)", (caixa,)).lastrowid
        conn.execute("INSERT INTO venda_itens (venda_id, descricao, quantidade, valor_unitario)"
                     " VALUES (?, 'x', 1, 45)", (venda,))
        conn.execute("INSERT INTO pagamentos (venda_id, forma, valor, recebido, criado_em)"
                     " VALUES (?, 'Dinheiro', 45, 50, '2026-11-01')", (venda,))
        conn.commit()
        antigo.close()

        novo = open_database(caminho)
        self.addCleanup(novo.close)
        conferencia = VendasRepository(novo).conferencia(caixa)
        self.assertEqual(novo.scalar("SELECT caixa_id FROM pagamentos"), caixa)
        self.assertEqual(conferencia.vendas_dinheiro, 50.0)
        self.assertEqual(conferencia.trocos, 5.0)
        self.assertEqual(conferencia.esperado, 55.0)


class FormaTestCase(unittest.TestCase):
    def test_forma_digitada_vira_a_do_balcao(self) -> None:
        self.assertEqual(forma_canonica(" dinheiro "), "Dinheiro")
        self.assertEqual(forma_canonica("PIX"), "Pix")
        self.assertEqual(forma_canonica("Vale do patrão"), "Vale do patrão")

    def test_formas_a_vista_respeitam_as_escondidas(self) -> None:
        from dumtech.core.pagamentos import formas_a_vista

        formas = formas_a_vista(("Boleto",))
        self.assertNotIn("Boleto", formas)
        self.assertNotIn(PRAZO, formas)
        self.assertNotIn(PARCELADO, formas)
        self.assertEqual(formas_a_vista(tuple(f for f in FORMAS_TODAS)), ["Dinheiro"])

    def test_entrada_do_balcao_nao_oferece_forma_escondida(self) -> None:
        from types import SimpleNamespace

        from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

        dialogo = PagamentoDialog(100.0, "x", parcelavel=True, cliente="Nena",
                                  empresa=SimpleNamespace(formas_ocultas=("Boleto",)))
        self.addCleanup(dialogo.deleteLater)
        entrada = [dialogo.forma_entrada.itemText(i) for i in range(dialogo.forma_entrada.count())]
        self.assertNotIn("Boleto", entrada)
        self.assertNotIn(PRAZO, entrada)


# ======================================================================= telas
class DialogoParcialTestCase(unittest.TestCase):
    """O Receber da venda pendente."""

    def _dialogo(self, em_aberto: float = 150.0):
        from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

        dialogo = PagamentoDialog(em_aberto, "Venda", conferir=VendasRepository.conferir_recebimento,
                                  parcial=True)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def _formas(self, dialogo) -> list[str]:
        return [dialogo.forma.itemText(i) for i in range(dialogo.forma.count())]

    def test_nao_oferece_prazo_nem_parcelado(self) -> None:
        formas = self._formas(self._dialogo())
        self.assertNotIn(PRAZO, formas)
        self.assertNotIn(PARCELADO, formas)

    def test_digita_100_e_recebe_a_parte_num_clique(self) -> None:
        dialogo = self._dialogo()
        dialogo.valor.setValue(100.0)

        self.assertTrue(dialogo.botao_receber.isEnabled())
        self.assertIn("Receber parte", dialogo.botao_receber.text())
        with mock.patch.object(dialogo, "accept") as aceitar:
            dialogo._confirmar()
        aceitar.assert_called_once()
        self.assertEqual([(p.forma, p.valor) for p in dialogo.pagamentos], [("Dinheiro", 100.0)])

    def test_valor_acima_do_que_falta_explica_em_vez_de_travar(self) -> None:
        dialogo = self._dialogo()
        dialogo.valor.setValue(200.0)
        self.assertTrue(dialogo.botao_receber.isEnabled())
        with mock.patch.object(dialogo, "accept") as aceitar:
            dialogo._confirmar()
        aceitar.assert_not_called()
        self.assertIn("passou do que falta", dialogo.aviso.text())

    def test_baixar_o_valor_nao_inventa_troco(self) -> None:
        dialogo = self._dialogo()
        dialogo.valor.setValue(100.0)
        dialogo._lancar()
        self.assertEqual(dialogo.troco, 0.0)
        self.assertEqual(dialogo.pagamentos[0].recebido, 100.0)

    def test_o_segundo_enter_recebe_a_parte_e_nao_quita_tudo(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        dialogo = self._dialogo()
        dialogo.valor.setValue(100.0)
        dialogo._lancar()
        with mock.patch.object(dialogo, "accept") as aceitar:
            QTest.keyClick(dialogo, Qt.Key.Key_Return)
        aceitar.assert_called_once()
        self.assertEqual(dialogo.pago, 100.0)

    def test_pix_e_dinheiro_na_mesma_vez(self) -> None:
        dialogo = self._dialogo()
        dialogo.forma.setCurrentText("Pix")
        dialogo.valor.setValue(100.0)
        dialogo._lancar()
        dialogo.forma.setCurrentText("Dinheiro")
        dialogo._lancar()  # o resto, 50, ja vem preenchido
        self.assertEqual([(p.forma, p.valor) for p in dialogo.pagamentos],
                         [("Pix", 100.0), ("Dinheiro", 50.0)])
        self.assertEqual(dialogo.botao_receber.text().strip(), "Receber")


class EntradaNoParceladoTestCase(Base):
    """ "Entrada de 300 hoje e mais tres de 350." """

    def _dialogo(self, total: float = 1350.0):
        from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

        dialogo = PagamentoDialog(total, "Venda", conferir=self.repo.conferir_pagamento,
                                  parcelavel=True, cliente="Nena")
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def parcelas(self):
        return sorted((item for item in self.contas.repository.listar(cancelados=True)
                       if item.parcelas), key=lambda item: item.parcela)

    def test_no_balcao(self) -> None:
        dialogo = self._dialogo()
        dialogo.forma.setCurrentText(PARCELADO)
        self.assertTrue(dialogo.campo_entrada.isVisibleTo(dialogo))
        dialogo.entrada.setValue(300.0)
        dialogo.parcelas.setValue(3)
        self.assertIn("Entrada de R$ 300,00 hoje em Dinheiro + 3x de R$ 350,00",
                      dialogo.nota_parcelas.text())

        dialogo._lancar()

        self.assertEqual([(p.rotulo, p.valor) for p in dialogo.pagamentos],
                         [("Dinheiro", 300.0), ("Parcelado 3x", 1050.0)])
        self.assertTrue(dialogo.botao_receber.isEnabled())
        venda = self.repo.finalizar(
            Venda(cliente="Nena", itens=[ItemVenda(descricao="Sofá", valor_unitario=1350.0)]),
            dialogo.pagamentos,
        )
        financeiro.registrar(self.contas, venda)
        self.assertEqual([item.valor for item in self.parcelas()], [350.0, 350.0, 350.0])
        entrada = next(item for item in self.contas.repository.listar() if not item.parcelas)
        self.assertTrue(entrada.pago)
        self.assertEqual(entrada.valor, 300.0)

    def test_entrada_maior_que_o_valor_e_recusada(self) -> None:
        dialogo = self._dialogo(100.0)
        dialogo.forma.setCurrentText(PARCELADO)
        dialogo.entrada.setValue(100.0)
        dialogo._lancar()
        self.assertEqual(dialogo.pagamentos, [])
        self.assertIn("entrada", dialogo.aviso.text().lower())

    def test_no_lancar_venda(self) -> None:
        from dumtech.apps.vendas.ui.venda_dialog import VendaDialog

        dialogo = VendaDialog(self.repo, contas=self.contas)
        self.addCleanup(dialogo.deleteLater)
        dialogo.itens.set_items([{"descricao": "Sofá", "quantidade": 1, "valor_unitario": 1350.0}])
        dialogo.cliente.setText("Nena")
        dialogo.forma.setCurrentText(PARCELADO)
        dialogo.entrada.setValue(300.0)
        dialogo.forma_entrada.setCurrentText("Pix")
        dialogo.parcelas.setValue(3)

        dialogo.salvar()

        self.assertEqual([(p.rotulo, p.valor) for p in dialogo.venda.pagamentos],
                         [("Pix", 300.0), ("Parcelado 3x", 1050.0)])
        self.assertEqual([item.valor for item in self.parcelas()], [350.0, 350.0, 350.0])


class EditarPendenteTestCase(Base):
    def test_concluir_pelo_editar_poe_o_resto_no_caixa_de_hoje(self) -> None:
        from dumtech.apps.vendas.ui.venda_dialog import VendaDialog

        self.repo.abrir_caixa(0.0)
        venda = self.a_prazo()
        antigo = venda.caixa_id
        self.repo.fechar_caixa(0.0)
        hoje = self.repo.abrir_caixa(0.0)

        dialogo = VendaDialog(self.repo, self.repo.obter(venda.id), contas=self.contas)
        self.addCleanup(dialogo.deleteLater)
        dialogo.forma.setCurrentText("Dinheiro")
        dialogo.status.setCurrentIndex(dialogo.status.findData(CONCLUIDA))
        dialogo.salvar()

        self.assertEqual(self.repo.conferencia(hoje.id).esperado, 150.0)
        self.assertEqual(self.repo.conferencia(antigo).vendas_dinheiro, 0.0,
                         "o caixa que ja fechou nao ganha dinheiro depois")

    def test_editar_nao_apaga_o_que_ja_entrou(self) -> None:
        from dumtech.apps.vendas.ui.venda_dialog import VendaDialog

        venda = self.receber(self.a_prazo(), pix(100.0))
        dialogo = VendaDialog(self.repo, self.repo.obter(venda.id), contas=self.contas)
        self.addCleanup(dialogo.deleteLater)
        dialogo.observacoes.setPlainText("Pagou 100 no Pix")
        dialogo.salvar()

        lida = self.repo.obter(venda.id)
        self.assertEqual(lida.em_aberto, 50.0)
        self.assertEqual([(p.forma, p.valor) for p in lida.pagamentos],
                         [("Pix", 100.0), (PRAZO, 50.0)])


class TelaDeVendasTestCase(Base):
    def test_receber_da_lista_aceita_uma_parte(self) -> None:
        from dumtech.apps.vendas.ui import vendas_view

        venda = self.a_prazo()
        view = vendas_view.VendasView(self.repo, contas=self.contas)
        self.addCleanup(view.deleteLater)
        view.refresh()
        view.tabela.selectRow(0)
        with mock.patch.object(vendas_view, "PagamentoDialog") as dialogo:
            dialogo.return_value.exec.return_value = True
            dialogo.return_value.pagamentos = [pix(100.0)]
            view._receber()

        self.assertTrue(dialogo.call_args.kwargs["parcial"])
        self.assertEqual(dialogo.call_args.args[0], 150.0)
        self.assertEqual(self.repo.obter(venda.id).em_aberto, 50.0)
        self.assertEqual(self.conta(venda).em_aberto, 50.0)
        view.refresh()
        view.tabela.selectRow(0)
        self.assertIn("falta R$ 50,00", view.tabela.item(0, 6).text())
        self.assertTrue(view.botao_receber.isEnabled(), "ainda da para receber o resto")


if __name__ == "__main__":
    unittest.main()
