"""Cancelar a venda tem que chegar ao Financeiro.

O relato que originou estes testes: duas vendas de R$ 30, uma cancelada. O
Painel de Vendas dizia R$ 30, o Financeiro dizia R$ 60 e o cancelamento nao
aparecia em lugar nenhum. O que se protege aqui: o dinheiro sai das contas, o
registro continua a vista, e quem ja tinha cancelado antes da correcao tambem
fica certo.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from PySide6.QtWidgets import QApplication

from dumtech.apps.financeiro.contas import abrir_contas
from dumtech.apps.financeiro.models import CAIXA, Conta, FinanceiroError, Lancamento
from dumtech.apps.financeiro.repository import (
    SITUACAO_ABERTO,
    SITUACAO_CANCELADO,
    FinanceiroRepository,
)
from dumtech.apps.vendas import financeiro
from dumtech.apps.vendas.database import open_database
from dumtech.apps.vendas.models import ItemVenda, Pagamento, Venda
from dumtech.apps.vendas.repository import VendasRepository
from dumtech.core.config import Settings
from dumtech.core.contas import APagar
from dumtech.core.database import Database

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class VendaCanceladaBase(unittest.TestCase):
    def setUp(self) -> None:
        pasta = Path(tempfile.mkdtemp())
        self.banco = open_database(pasta / "vendas.db")
        self.repo = VendasRepository(self.banco)
        self.contas = abrir_contas(pasta / "financeiro.db")
        self.addCleanup(self.banco.close)
        self.addCleanup(self.contas.close)

    def vender(self, valor: float = 30.0, pagamentos=None, numero: str = "") -> Venda:
        venda = Venda(numero=numero, cliente="Ana", itens=[
            ItemVenda(descricao="Login", quantidade=1, valor_unitario=valor)])
        venda = self.repo.finalizar(
            venda, pagamentos or [Pagamento(forma="Pix", valor=valor, recebido=valor)])
        financeiro.registrar(self.contas, venda)
        return venda

    def cancelar(self, venda: Venda, motivo: str = "Era teste") -> str:
        return financeiro.registrar(self.contas, self.repo.cancelar(venda.id, motivo))

    def lancamentos(self) -> list[Lancamento]:
        return self.contas.repository.listar(cancelados=True)


class CancelamentoNoFinanceiroTestCase(VendaCanceladaBase):
    def test_o_relato_da_cliente_duas_de_30_e_uma_cancelada(self) -> None:
        primeira = self.vender()
        self.vender()

        recado = self.cancelar(primeira)

        resumo = self.contas.repository.resumo()
        self.assertEqual(resumo.recebido_mes, 30.0, "o dinheiro cancelado nao ficou")
        self.assertEqual(resumo.cancelado_mes, 30.0, "e o cancelamento precisa constar")
        self.assertIn("Financeiro", recado)

        por_situacao = sorted(item.situacao for item in self.lancamentos())
        self.assertEqual(por_situacao, ["Cancelado", "Recebido"])

    def test_o_saldo_da_conta_tambem_volta(self) -> None:
        repositorio = self.contas.repository
        conta = repositorio.criar_conta(Conta(nome="Caixa da loja", tipo=CAIXA))
        venda = self.vender(pagamentos=[Pagamento(forma="Prazo", valor=30.0, recebido=30.0)])
        repositorio.baixar(self.lancamentos()[0].id, conta_id=conta.id)
        self.assertEqual(repositorio.saldo_total(), 30.0)

        self.cancelar(venda)

        self.assertEqual(repositorio.saldo_total(), 0.0)
        self.assertEqual(repositorio.baixas_do_periodo("2000-01-01", "2100-01-01"), [])

    def test_venda_a_prazo_cancelada_para_de_ser_cobrada(self) -> None:
        venda = self.vender(pagamentos=[Pagamento(forma="Prazo", valor=30.0, recebido=30.0)])
        self.assertEqual(self.contas.repository.resumo().a_receber, 30.0)

        self.cancelar(venda)

        resumo = self.contas.repository.resumo()
        self.assertEqual(resumo.a_receber, 0.0)
        self.assertEqual(resumo.vencidos_quantidade, 0)
        self.assertEqual(self.contas.repository.projecao().entradas, 0.0)

    def test_so_cancela_o_documento_exato(self) -> None:
        """Numero de venda e editavel: VEN-1 nao pode levar junto o VEN-10."""
        curta = self.vender(numero="VEN-1")
        self.vender(numero="VEN-10")

        self.cancelar(curta)

        situacoes = {item.descricao: item.situacao for item in self.lancamentos()}
        self.assertEqual(situacoes["Venda VEN-1"], "Cancelado")
        self.assertEqual(situacoes["Venda VEN-10"], "Recebido")

    def test_a_conta_do_fornecedor_com_o_mesmo_numero_nao_vai_junto(self) -> None:
        """Numero de venda e editavel e pode bater com o de uma nota de compra."""
        venda = self.vender(numero="1234")
        self.contas.lancar_pagamento(APagar(
            descricao="Compra NF 1234", valor=50.0, vencimento=date.today().isoformat(),
            fornecedor="Atacado", documento="1234",
        ))

        self.cancelar(venda)

        situacoes = {item.descricao: item.situacao for item in self.lancamentos()}
        self.assertEqual(situacoes["Venda 1234"], "Cancelado")
        self.assertEqual(situacoes["Compra NF 1234"], "Em aberto")

    def test_barra_e_ponto_tambem_mudam_o_numero(self) -> None:
        self.vender(numero="VEN-1/2")
        self.vender(numero="VEN-1.2")
        self.assertFalse(self.contas.ja_lancado("VEN-1"))

    def test_cem_nao_e_confundido_com_mil(self) -> None:
        self.vender(numero="1000")
        self.assertFalse(self.contas.ja_lancado("100"))

    def test_anotar_na_mesma_linha_nao_perde_a_conta(self) -> None:
        """Observacao e texto livre: perder a marca lancaria a venda em dobro."""
        venda = self.vender(numero="VEN-1")
        lancamento = self.lancamentos()[0]
        lancamento.observacoes += " ligar dia 5"
        self.contas.repository.atualizar(lancamento)

        self.assertTrue(self.contas.ja_lancado("VEN-1"))
        self.cancelar(venda)
        self.assertEqual(self.lancamentos()[0].situacao, "Cancelado")

    def test_o_numero_reaproveitado_entra_de_novo(self) -> None:
        """Vender, cancelar, apagar e vender de novo: e o que quem testa faz."""
        primeira = self.vender()
        self.cancelar(primeira)
        self.repo.excluir(primeira.id)

        segunda = self.vender()

        self.assertEqual(segunda.numero, primeira.numero)
        self.assertEqual(self.contas.repository.resumo().recebido_mes, 30.0)
        self.assertEqual(sorted(item.situacao for item in self.lancamentos()),
                         ["Cancelado", "Recebido"])

    def test_o_motivo_fica_no_lancamento(self) -> None:
        self.cancelar(self.vender(), "Cliente desistiu")
        lancamento = self.lancamentos()[0]
        self.assertIn("Cliente desistiu", lancamento.observacoes)
        self.assertIn("Origem: ", lancamento.observacoes, "a marca de origem continua la")

    def test_cancelar_duas_vezes_nao_muda_nada(self) -> None:
        venda = self.vender()
        self.cancelar(venda)
        cancelada = self.repo.obter(venda.id)
        self.assertEqual(financeiro.registrar(self.contas, cancelada), "")
        self.assertEqual(len(self.lancamentos()), 1)

    def test_sem_financeiro_na_licenca_nada_muda(self) -> None:
        venda = self.vender()
        cancelada = self.repo.cancelar(venda.id, "Era teste")
        self.assertEqual(financeiro.registrar(None, cancelada), "")

    def test_a_ponte_com_defeito_nao_derruba_o_cancelamento(self) -> None:
        class Quebrada:
            def cancelar(self, *_args, **_kwargs):
                raise RuntimeError("banco trancado")

        venda = self.vender()
        cancelada = self.repo.cancelar(venda.id, "Era teste")
        with self.assertLogs("dumtech.apps.vendas.financeiro", "ERROR"):
            self.assertIn("na mão", financeiro.registrar(Quebrada(), cancelada))


class LancamentoCanceladoTestCase(VendaCanceladaBase):
    def setUp(self) -> None:
        super().setUp()
        self.venda = self.vender()
        self.cancelar(self.venda)
        self.lancamento = self.lancamentos()[0]

    def test_fica_fora_das_contas_e_dentro_do_filtro(self) -> None:
        repositorio = self.contas.repository
        self.assertEqual(repositorio.listar(), [], "quem soma nao pode enxergar")
        self.assertEqual(repositorio.listar(situacao=SITUACAO_ABERTO), [])
        self.assertEqual(len(repositorio.listar(situacao=SITUACAO_CANCELADO)), 1)

    def test_nao_recebe_nem_conta_como_vencido(self) -> None:
        self.assertEqual(self.lancamento.em_aberto, 0.0)
        self.assertFalse(self.lancamento.vencido)
        self.assertEqual(self.lancamento.tom, "muted")
        with self.assertRaises(FinanceiroError):
            self.contas.repository.baixar(self.lancamento.id)

    def test_cai_para_o_fim_da_lista(self) -> None:
        repositorio = self.contas.repository
        repositorio.criar(Lancamento(descricao="Conta nova", valor=10.0,
                                     vencimento=date.today().isoformat()))
        self.assertEqual(self.lancamentos()[-1].descricao, self.lancamento.descricao)


class VendasAntigasTestCase(VendaCanceladaBase):
    """Quem cancelou antes da correcao nao pode continuar vendo R$ 60."""

    def test_ao_abrir_acerta_o_que_ja_estava_cancelado(self) -> None:
        primeira = self.vender()
        self.vender()
        self.repo.cancelar(primeira.id, "Era teste")  # como era: a ponte nao ouvia
        self.assertEqual(self.contas.repository.resumo().recebido_mes, 60.0)

        financeiro.conciliar(self.repo, self.contas)

        resumo = self.contas.repository.resumo()
        self.assertEqual(resumo.recebido_mes, 30.0)
        self.assertEqual(resumo.cancelado_mes, 30.0)

    def test_o_acerto_guarda_a_data_em_que_cancelou_de_verdade(self) -> None:
        """Cancelamento de meses atras nao pode cair todo no "cancelado neste mes"."""
        venda = self.vender()
        self.repo.cancelar(venda.id, "Era teste")
        self.banco.execute("UPDATE vendas SET cancelada_em = ? WHERE id = ?",
                           ("2025-03-10T10:00:00", venda.id))

        financeiro.conciliar(self.repo, self.contas)

        self.assertEqual(self.contas.repository.resumo().cancelado_mes, 0.0)
        self.assertEqual(self.lancamentos()[0].cancelado_em[:7], "2025-03")

    def test_venda_cancelada_na_tela_antiga_cai_no_mes_da_venda(self) -> None:
        """A edicao antiga nao gravava a data: nao pode pesar no mes de agora."""
        venda = self.vender()
        self.repo.cancelar(venda.id, "Era teste")
        self.banco.execute("UPDATE vendas SET cancelada_em = '', data = ? WHERE id = ?",
                           ("2025-03-10", venda.id))

        financeiro.conciliar(self.repo, self.contas)

        self.assertEqual(self.contas.repository.resumo().cancelado_mes, 0.0)
        self.assertEqual(self.lancamentos()[0].cancelado_em[:7], "2025-03")

    def test_acertar_de_novo_nao_muda_nada(self) -> None:
        self.repo.cancelar(self.vender().id, "Era teste")
        financeiro.conciliar(self.repo, self.contas)
        financeiro.conciliar(self.repo, self.contas)
        self.assertEqual(self.contas.repository.resumo().cancelado_mes, 30.0)

    def test_sem_financeiro_nao_faz_nada(self) -> None:
        self.repo.cancelar(self.vender().id, "Era teste")
        financeiro.conciliar(self.repo, None)  # nao levanta


class CanceladoNaTelaTestCase(VendaCanceladaBase):
    def _view(self):
        from dumtech.apps.financeiro.ui.lancamentos_view import LancamentosView

        view = LancamentosView(self.contas.repository)
        self.addCleanup(view.deleteLater)
        view.refresh()
        return view

    def test_a_lista_mostra_o_cancelado_e_trava_as_acoes(self) -> None:
        self.cancelar(self.vender())
        view = self._view()
        view.tabela.selectRow(0)

        self.assertEqual(view.registro_selecionado().situacao, "Cancelado")
        for botao in (view.botao_baixar, view.botao_quitar, view.botao_editar,
                      view.botao_parcelar, view.botao_repetir, view.botao_whatsapp):
            self.assertFalse(botao.isEnabled())
        self.assertIsNone(view.abrir_dialogo(view.registro_selecionado()),
                          "o duplo clique nao pode reabrir o lancamento")

    def test_o_filtro_de_cancelados(self) -> None:
        self.cancelar(self.vender())
        self.vender()
        view = self._view()
        self.assertEqual(view.tabela.rowCount(), 2)

        view.filtro_situacao.setCurrentIndex(view.filtro_situacao.findData(SITUACAO_CANCELADO))
        self.assertEqual(view.tabela.rowCount(), 1)

    def test_o_painel_do_financeiro_diz_quanto_foi_cancelado(self) -> None:
        from dumtech.apps.financeiro.ui.dashboard_view import DashboardView

        self.cancelar(self.vender())
        painel = DashboardView(self.contas.repository)
        self.addCleanup(painel.deleteLater)
        self.assertIn("R$ 30,00 cancelado", painel.painel_resultado.nota.text())

    def test_o_painel_de_vendas_diz_quanto_foi_cancelado(self) -> None:
        from dumtech.apps.vendas.ui.dashboard_view import DashboardView

        primeira = self.vender()
        self.vender()
        self.cancelar(primeira)

        painel = DashboardView(self.repo)
        self.addCleanup(painel.deleteLater)
        self.assertEqual(painel.card_hoje.value_label.text(), "R$ 30,00")
        self.assertIn("R$ 30,00 cancelado", painel.card_hoje.hint_label.text())
        self.assertIn("R$ 30,00 cancelado", painel.card_mes.hint_label.text())

    def test_cancelar_pela_lista_de_vendas_avisa_o_financeiro(self) -> None:
        from unittest import mock

        from dumtech.apps.vendas.ui import vendas_view

        self.vender()
        view = vendas_view.VendasView(self.repo, contas=self.contas)
        self.addCleanup(view.deleteLater)
        view.refresh()
        view.tabela.selectRow(0)

        dialogo = mock.Mock(motivo="Era teste")
        dialogo.exec.return_value = True
        with mock.patch.object(vendas_view, "MotivoDialog", return_value=dialogo):
            view._cancelar()

        self.assertEqual(self.contas.repository.resumo().recebido_mes, 0.0)
        self.assertEqual(self.lancamentos()[0].situacao, "Cancelado")


class AtualizacaoTestCase(unittest.TestCase):
    """O cliente atualiza com o banco que ja tem: nada pode se perder."""

    def test_o_banco_do_financeiro_ganha_a_coluna(self) -> None:
        from dumtech.apps.financeiro import database as banco_financeiro

        caminho = Path(tempfile.mkdtemp()) / "financeiro.db"
        antigo = Database(caminho, banco_financeiro.MIGRATIONS[:3])
        antigo.execute(
            "INSERT INTO lancamentos (tipo, descricao, valor, vencimento, criado_em)"
            " VALUES ('receita', 'Antiga', 10, '2026-01-01', '2026-01-01T10:00:00')"
        )
        antigo.close()

        novo = banco_financeiro.open_database(caminho)
        self.addCleanup(novo.close)
        lancamento = FinanceiroRepository(novo).listar()[0]
        self.assertEqual(lancamento.descricao, "Antiga")
        self.assertFalse(lancamento.cancelado)

    def test_o_banco_do_vendas_ganha_a_coluna(self) -> None:
        from dumtech.apps.vendas import database as banco_vendas

        caminho = Path(tempfile.mkdtemp()) / "vendas.db"
        antigo = Database(caminho, banco_vendas.MIGRATIONS[:4])
        antigo.execute(
            "INSERT INTO vendas (numero, data, criado_em)"
            " VALUES ('VEN-2026-0001', '2026-01-01', '2026-01-01T10:00:00')"
        )
        antigo.execute(
            "INSERT INTO pagamentos (venda_id, forma, valor, recebido, criado_em)"
            " VALUES (1, 'Pix', 10, 10, '2026-01-01T10:00:00')"
        )
        antigo.close()

        novo = banco_vendas.open_database(caminho)
        self.addCleanup(novo.close)
        venda = VendasRepository(novo).listar()[0]
        self.assertEqual(venda.pagamentos[0].forma, "Pix")
        self.assertIsNone(venda.parcelamento)


class AbrirOVendasTestCase(unittest.TestCase):
    """Um Hub de verdade: o acerto precisa acontecer sem ninguem pedir."""

    def setUp(self) -> None:
        from dumtech.hub.main_window import HubWindow

        self.hub = HubWindow(settings=Settings(Path(tempfile.mkdtemp()) / "hub.json"))
        self.hub.launcher.notify = lambda *args: None
        self.addCleanup(self.hub.close)

    def test_abrir_o_vendas_acerta_o_que_estava_errado(self) -> None:
        self.assertTrue(self.hub.open_app("vendas"))
        janela = self.hub.launcher.get("vendas")
        contas = self.hub.launcher.contas("vendas")
        venda = janela.repository.finalizar(
            Venda(cliente="Antes da correcao", itens=[
                ItemVenda(descricao="Login", quantidade=1, valor_unitario=30.0)]),
            [Pagamento(forma="Pix", valor=30.0, recebido=30.0)],
        )
        financeiro.registrar(contas, venda)
        janela.repository.cancelar(venda.id, "Era teste")  # como era: a ponte nao ouvia
        self.assertEqual(contas._do_documento(venda.numero)[0].situacao, "Recebido")
        self.hub.close_app("vendas", perguntar=False)

        self.assertTrue(self.hub.open_app("vendas"))

        contas = self.hub.launcher.contas("vendas")
        self.assertEqual(contas._do_documento(venda.numero)[0].situacao, "Cancelado")


if __name__ == "__main__":
    unittest.main()
