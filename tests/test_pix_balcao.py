"""O QR Code do Pix dentro do dialogo de Receber.

O que estes testes protegem e o comportamento no balcao, nao o desenho: o QR
aparece quando a forma e Pix, acompanha o valor digitado, some quando a forma
muda, e - o mais importante - o dialogo continua recebendo normalmente quando
nao ha chave Pix cadastrada. Ninguem pode ficar impedido de vender por causa de
um campo em branco nas configuracoes.
"""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication

from dumtech.core.empresa import Empresa
from dumtech.core.pix import campos
from dumtech.apps.vendas.models import DINHEIRO
from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

_app: QApplication | None = None

PIX = "Pix"
CHAVE = "11144477735"


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def _empresa(chave: str = CHAVE) -> Empresa:
    return Empresa(nome="Loja Teste", cidade="Sao Paulo", pix_chave=chave)


class PixNoBalcaoTestCase(unittest.TestCase):
    def _dialogo(self, total: float = 150.0, empresa=None) -> PagamentoDialog:
        dialogo = PagamentoDialog(total, "teste", empresa=empresa)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    # ------------------------------------------------------------- aparecer
    def test_o_painel_fica_escondido_em_dinheiro(self) -> None:
        dialogo = self._dialogo(empresa=_empresa())
        self.assertFalse(dialogo.painel_pix.isVisibleTo(dialogo))

    def test_escolher_pix_mostra_o_qr_com_o_valor_da_venda(self) -> None:
        dialogo = self._dialogo(150.0, empresa=_empresa())
        dialogo.forma.setCurrentText(PIX)
        self.assertTrue(dialogo.painel_pix.isVisibleTo(dialogo))
        self.assertFalse(dialogo.imagem_pix.pixmap().isNull())
        self.assertEqual(campos(dialogo.payload_pix)["54"], "150.00")

    def test_voltar_para_dinheiro_esconde_o_painel(self) -> None:
        dialogo = self._dialogo(empresa=_empresa())
        dialogo.forma.setCurrentText(PIX)
        dialogo.forma.setCurrentText(DINHEIRO)
        self.assertFalse(dialogo.painel_pix.isVisibleTo(dialogo))

    # -------------------------------------------------------------- o valor
    def test_o_qr_acompanha_o_valor_digitado(self) -> None:
        """Pagamento parcial em Pix: o QR tem que cobrar so a parte do Pix."""
        dialogo = self._dialogo(150.0, empresa=_empresa())
        dialogo.forma.setCurrentText(PIX)
        dialogo.valor.setValue(60.0)
        self.assertEqual(campos(dialogo.payload_pix)["54"], "60.00")

    def test_o_numero_da_venda_ainda_nao_existe_entao_o_txid_e_coringa(self) -> None:
        dialogo = self._dialogo(empresa=_empresa())
        dialogo.forma.setCurrentText(PIX)
        self.assertIn("***", campos(dialogo.payload_pix)["62"])

    def test_o_copia_e_cola_e_o_mesmo_texto_do_qr(self) -> None:
        dialogo = self._dialogo(empresa=_empresa())
        dialogo.forma.setCurrentText(PIX)
        self.assertEqual(dialogo.texto_pix.text().strip(), dialogo.payload_pix)

    def test_copiar_leva_o_payload_para_a_area_de_transferencia(self) -> None:
        dialogo = self._dialogo(empresa=_empresa())
        dialogo.forma.setCurrentText(PIX)
        dialogo._copiar_pix()
        self.assertEqual(QApplication.clipboard().text(), dialogo.payload_pix)

    # ----------------------------------------------------- sem chave, sem QR
    def test_sem_chave_cadastrada_o_dialogo_avisa_e_nao_quebra(self) -> None:
        dialogo = self._dialogo(empresa=_empresa(chave=""))
        dialogo.forma.setCurrentText(PIX)
        self.assertTrue(dialogo.painel_pix.isVisibleTo(dialogo))
        self.assertEqual(dialogo.payload_pix, "")
        self.assertIn("Pagamentos", dialogo.recado_pix.text())

    def test_sem_empresa_nenhuma_o_pix_continua_sendo_forma_de_pagamento(self) -> None:
        """Rodando sem Hub (teste, modo avulso) nada pode explodir."""
        dialogo = self._dialogo(empresa=None)
        dialogo.forma.setCurrentText(PIX)
        self.assertEqual(dialogo.payload_pix, "")

    def test_receber_em_pix_funciona_sem_chave(self) -> None:
        """A venda nao pode depender do QR: o cliente pode ter pago por fora."""
        dialogo = self._dialogo(150.0, empresa=_empresa(chave=""))
        dialogo.forma.setCurrentText(PIX)
        dialogo._lancar()
        self.assertEqual(len(dialogo.pagamentos), 1)
        self.assertEqual(dialogo.pagamentos[0].forma, PIX)
        self.assertEqual(dialogo.pagamentos[0].valor, 150.0)

    # ------------------------------------------------------------- honestidade
    def test_o_aviso_diz_que_o_sistema_nao_confirma_o_pagamento(self) -> None:
        dialogo = self._dialogo(empresa=_empresa())
        dialogo.forma.setCurrentText(PIX)
        self.assertIn("confira", dialogo.recado_pix.text().lower())


class ChaveNovaNoVendasAbertoTestCase(unittest.TestCase):
    """Cadastrar a chave Pix vale no Vendas que ja esta aberto, sem reabrir."""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path

        from dumtech.core.config import Settings
        from dumtech.hub.main_window import HubWindow

        self.hub = HubWindow(settings=Settings(Path(tempfile.mkdtemp()) / "hub.json"))
        self.hub.launcher.notify = lambda *args: None

    def tearDown(self) -> None:
        from PySide6.QtCore import QEvent

        self.hub.close()
        self.hub.deleteLater()
        QApplication.instance().sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_a_chave_cadastrada_agora_chega_no_balcao_aberto(self) -> None:
        self.assertTrue(self.hub.open_app("vendas"))
        balcao = self.hub.launcher.get("vendas").balcao_view
        self.assertFalse(getattr(balcao.empresa, "tem_pix", False))

        # o lojista entra em Configuracoes > Pagamentos e o servidor devolve a chave assinada
        from .assinante import licenca_de_teste, pacote_pix

        with licenca_de_teste():
            self.hub.settings.set("pagamentos", "assinado", pacote_pix(CHAVE))
            self.hub.launcher.atualizar_empresa()
            self.assertTrue(balcao.empresa.tem_pix,
                            "sem isto, so apareceria depois de fechar e abrir o Vendas")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
