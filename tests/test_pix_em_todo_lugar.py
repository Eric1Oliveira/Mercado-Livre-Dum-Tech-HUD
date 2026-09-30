"""A chave Pix cadastrada tem de valer em TODO lugar que recebe dinheiro.

Ja aconteceu de um caminho abrir o Receber sem passar a empresa: a chave
estava cadastrada, e mesmo assim o quadrado do QR Code nascia em branco.
Estes testes cobrem cada porta por onde se recebe.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from dumtech.apps.vendas.database import open_database
from dumtech.apps.vendas.models import ItemVenda, Venda
from dumtech.apps.vendas.repository import VendasRepository
from dumtech.apps.vendas.ui import vendas_view as vendas_view_mod
from dumtech.apps.vendas.ui import balcao_view as balcao_view_mod
from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog
from dumtech.core.empresa import Empresa
from dumtech.core.pagamentos import PIX

_app: QApplication | None = None

CHAVE = "contato@dumtech.com.br"


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def _empresa() -> Empresa:
    return Empresa(nome="Padaria Pao de Ouro", cidade="Limeira", pix_chave=CHAVE)


class QrDoBalcaoTestCase(unittest.TestCase):
    """O quadrado do QR so pode ficar vazio quando nao ha chave."""

    def _dialogo(self, empresa) -> PagamentoDialog:
        dialogo = PagamentoDialog(100.0, "Venda 1", empresa=empresa)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def test_com_chave_o_qr_aparece(self) -> None:
        dialogo = self._dialogo(_empresa())
        dialogo.forma.setCurrentText(PIX)
        self.assertTrue(dialogo.payload_pix.startswith("000201"))
        self.assertIn(CHAVE, dialogo.payload_pix)
        self.assertFalse(dialogo.imagem_pix.pixmap().isNull())
        self.assertTrue(dialogo.texto_pix.text())
        self.assertTrue(dialogo.botao_copiar_pix.isEnabled())

    def test_o_qr_acompanha_o_valor_digitado(self) -> None:
        """Trocar o valor tem de refazer o codigo - senao cobra errado."""
        dialogo = self._dialogo(_empresa())
        dialogo.forma.setCurrentText(PIX)
        primeiro = dialogo.payload_pix
        dialogo.valor.setValue(42.50)
        self.assertNotEqual(dialogo.payload_pix, primeiro)
        self.assertIn("42.50", dialogo.payload_pix)

    def test_sem_chave_avisa_onde_cadastrar(self) -> None:
        dialogo = self._dialogo(Empresa(nome="Loja", cidade="Limeira"))
        dialogo.forma.setCurrentText(PIX)
        self.assertEqual(dialogo.payload_pix, "")
        self.assertIn("Configuracoes", dialogo.recado_pix.text())

    def test_sem_empresa_nenhuma_nao_quebra(self) -> None:
        """O dialogo tambem roda fora do Hub (teste, script): nao pode explodir."""
        dialogo = self._dialogo(None)
        dialogo.forma.setCurrentText(PIX)
        self.assertEqual(dialogo.payload_pix, "")


class TodasAsPortasTestCase(unittest.TestCase):
    """Todo caminho que abre o Receber leva a empresa junto."""

    def setUp(self) -> None:
        self.db = open_database(Path(tempfile.mkdtemp()) / "vendas.db")
        self.repo = VendasRepository(self.db)
        self.empresa = _empresa()
        self.abertos: list[dict] = []

    def tearDown(self) -> None:
        self.db.close()

    def _espionar(self, modulo) -> None:
        """Troca o dialogo por um espiao que so anota como foi chamado."""
        espiao = self

        class Espiao:
            def __init__(self, *args, **kwargs) -> None:
                espiao.abertos.append(kwargs)

            def exec(self) -> int:
                return 0

        original = modulo.PagamentoDialog
        modulo.PagamentoDialog = Espiao
        self.addCleanup(lambda: setattr(modulo, "PagamentoDialog", original))

    def _venda_pendente(self) -> Venda:
        venda = Venda(numero=self.repo.proximo_numero(), cliente="Joao", itens=[
            ItemVenda(descricao="Pao", quantidade=2, valor_unitario=5.0),
        ])
        return self.repo.salvar(venda)

    def test_receber_venda_pendente_leva_a_empresa(self) -> None:
        """Foi exatamente aqui que o QR nascia em branco."""
        self._espionar(vendas_view_mod)
        tela = vendas_view_mod.VendasView(self.repo, empresa=self.empresa)
        self.addCleanup(tela.deleteLater)
        venda = self._venda_pendente()
        tela.refresh()
        tela.registro_selecionado = lambda: venda
        tela._receber()
        self.assertEqual(len(self.abertos), 1)
        self.assertIs(self.abertos[0].get("empresa"), self.empresa)

    def test_receber_no_balcao_leva_a_empresa(self) -> None:
        self._espionar(balcao_view_mod)
        tela = balcao_view_mod.BalcaoView(self.repo, empresa=self.empresa)
        self.addCleanup(tela.deleteLater)
        tela.itens = [ItemVenda(descricao="Pao", quantidade=1, valor_unitario=5.0)]
        tela.receber()
        self.assertEqual(len(self.abertos), 1)
        self.assertIs(self.abertos[0].get("empresa"), self.empresa)


class FinanceiroRecebeComPixTestCase(unittest.TestCase):
    """Receber uma conta em Pix mostra o QR - pagar uma conta, nao."""

    def setUp(self) -> None:
        from dumtech.apps.financeiro.database import open_database as abrir_fin
        from dumtech.apps.financeiro.models import DESPESA, Lancamento
        from dumtech.apps.financeiro.repository import FinanceiroRepository
        from dumtech.apps.financeiro.ui.dialogos import BaixaDialog

        self.Lancamento, self.DESPESA, self.BaixaDialog = Lancamento, DESPESA, BaixaDialog
        self.db = abrir_fin(Path(tempfile.mkdtemp()) / "financeiro.db")
        self.repo = FinanceiroRepository(self.db)
        self.empresa = _empresa()

    def tearDown(self) -> None:
        self.db.close()

    def _dialogo(self, tipo=None):
        dados = dict(descricao="Servico de instalacao", valor=250.0,
                     vencimento="2026-09-30")
        if tipo:
            dados["tipo"] = tipo
        lancamento = self.repo.criar(self.Lancamento(**dados))
        dialogo = self.BaixaDialog(self.repo, lancamento, empresa=self.empresa)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def test_ao_receber_em_pix_o_qr_aparece(self) -> None:
        dialogo = self._dialogo()
        dialogo.forma.setCurrentText(PIX)
        self.assertTrue(dialogo.painel_pix.isVisibleTo(dialogo))
        self.assertTrue(dialogo.painel_pix.tem_qr)
        self.assertIn(CHAVE, dialogo.painel_pix.payload)

    def test_em_outra_forma_o_qr_fica_fora_do_caminho(self) -> None:
        dialogo = self._dialogo()
        dialogo.forma.setCurrentText("Dinheiro")
        self.assertFalse(dialogo.painel_pix.isVisibleTo(dialogo))

    def test_conta_a_pagar_nao_mostra_qr(self) -> None:
        """Quem cobra e o fornecedor: exibir a MINHA chave ali seria errado."""
        dialogo = self._dialogo(tipo=self.DESPESA)
        self.assertIsNone(dialogo.painel_pix)


class OrdemEntregaComPixTestCase(unittest.TestCase):
    """Na entrega da ordem o cliente paga - o QR tem de estar ali."""

    def setUp(self) -> None:
        from dumtech.apps.ordens.database import open_database as abrir_os
        from dumtech.apps.ordens.models import Ordem
        from dumtech.apps.ordens.repository import OrdensRepository
        from dumtech.apps.ordens.ui.dialogos import EntregaDialog

        self.Ordem, self.EntregaDialog = Ordem, EntregaDialog
        self.db = abrir_os(Path(tempfile.mkdtemp()) / "ordens.db")
        self.repo = OrdensRepository(self.db)
        self.empresa = _empresa()

    def tearDown(self) -> None:
        self.db.close()

    def _ordem(self, valor: float):
        return self.repo.salvar(self.Ordem(
            numero=self.repo.proximo_numero(), cliente="Joao",
            equipamento="Notebook", valor=valor,
        ))

    def test_a_entrega_mostra_o_qr_do_total(self) -> None:
        dialogo = self.EntregaDialog(self.repo, self._ordem(350.0), empresa=self.empresa)
        self.addCleanup(dialogo.deleteLater)
        self.assertIsNotNone(dialogo.painel_pix)
        self.assertTrue(dialogo.painel_pix.tem_qr)
        self.assertIn("350.00", dialogo.painel_pix.payload)

    def test_ordem_sem_valor_nao_mostra_cobranca(self) -> None:
        """Servico de cortesia nao tem o que cobrar."""
        dialogo = self.EntregaDialog(self.repo, self._ordem(0.0), empresa=self.empresa)
        self.addCleanup(dialogo.deleteLater)
        self.assertIsNone(dialogo.painel_pix)


if __name__ == "__main__":
    unittest.main()
