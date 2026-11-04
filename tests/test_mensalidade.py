"""Mensalidade no Hub: o que o cliente do plano mensal ve - e o vitalicio nunca ve.

Regra de ouro (pedido do Eric): licenca vitalicia nao mostra aviso de pagamento,
vencimento nem modo consulta da mensalidade. Os testes de vitalicia aqui sao os
que nao podem quebrar.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dumtech.core import mensalidade
from dumtech.core.licensing import ORIGEM_SUPABASE, License, LicenseService, machine_id

from .test_assinatura import CHAVE, chaves_de_teste, neste_computador, pacote

#: o dia como o servidor conta (UTC): e por ele que o prazo vence
HOJE = datetime.now(timezone.utc).date()


def licenca(tipo: str = "vitalicia", cobranca: dict | None = None, expira: str | None = None,
            bloqueio: str = "", mensagem: str = "") -> License:
    extras = {"bloqueio": bloqueio, "mensagem": mensagem} if bloqueio else {}
    return License(key=CHAVE, customer="Padaria", entitlements=("vendas",), machine="M",
                   activated_at="", source=ORIGEM_SUPABASE, tipo=tipo, expires_at=expira,
                   cobranca=cobranca or {}, extras=extras)


def daqui(dias: int) -> str:
    return (HOJE + timedelta(days=dias)).isoformat()


class VitalicioNuncaVeCobrancaTestCase(unittest.TestCase):
    def test_vitalicia_nao_tem_faixa_nem_texto(self) -> None:
        for lic in (licenca(), licenca(bloqueio="inativa", mensagem="Suspensa."),
                    licenca(cobranca={"situacao": "pendente", "ate": "2026-11-05"})):
            self.assertFalse(lic.mensal)
            self.assertEqual(lic.situacao_cobranca, "")
            self.assertIsNone(mensalidade.faixa(lic, HOJE))
            self.assertIsNone(mensalidade.texto_consulta(lic))
            self.assertIsNone(mensalidade.linha_do_plano(lic, HOJE))

    def test_licenca_sem_tipo_de_servidor_antigo_tambem_nao(self) -> None:
        self.assertIsNone(mensalidade.faixa(licenca(tipo=""), HOJE))


class SituacaoTestCase(unittest.TestCase):
    def test_teste_conta_os_dias(self) -> None:
        f = mensalidade.faixa(licenca("teste", {"situacao": "teste", "ate": daqui(4)}, daqui(4)), HOJE)
        self.assertEqual(f.situacao, "teste")
        self.assertIn("5 dias", f.titulo)
        self.assertEqual(f.acao, "assinar")

        amanha = mensalidade.faixa(licenca("teste", {"situacao": "teste", "ate": daqui(1)}, daqui(1)), HOJE)
        self.assertIn("amanhã", amanha.titulo)
        self.assertEqual(amanha.tom, "warning")

        hoje = mensalidade.faixa(licenca("teste", {"situacao": "teste", "ate": daqui(0)}, daqui(0)), HOJE)
        self.assertIn("último dia", hoje.titulo)

    def test_em_dia_nao_incomoda(self) -> None:
        self.assertIsNone(mensalidade.faixa(licenca("assinatura", {"situacao": "em_dia"}), HOJE))
        self.assertIn("em dia", mensalidade.linha_do_plano(licenca("assinatura", {"situacao": "em_dia"}), HOJE))

    def test_pendente_e_gentil_e_diz_ate_quando(self) -> None:
        f = mensalidade.faixa(licenca("assinatura", {"situacao": "pendente", "ate": daqui(7),
                                                     "motivo": "falhou"}, daqui(7)), HOJE)
        self.assertEqual(f.situacao, "pendente")
        self.assertIn((HOJE + timedelta(days=7)).strftime("%d/%m/%Y"), f.texto)
        self.assertEqual(f.acao, "whatsapp")

    def test_cancelou_oferece_voltar(self) -> None:
        f = mensalidade.faixa(licenca("assinatura", {"situacao": "pendente", "ate": daqui(7),
                                                     "motivo": "cancelou"}, daqui(7)), HOJE)
        self.assertIn("encerrada", f.titulo)
        self.assertEqual(f.acao, "assinar")

    def test_vencida_vira_consulta_com_texto_da_mensalidade(self) -> None:
        teste = licenca("teste", {"situacao": "teste", "ate": daqui(-2)}, daqui(-2),
                        bloqueio="expirada", mensagem="Seu teste grátis terminou.")
        self.assertEqual(teste.situacao_cobranca, "consulta")
        f = mensalidade.faixa(teste, HOJE)
        self.assertEqual(f.situacao, "consulta")
        self.assertIn("teste grátis terminou", f.titulo)
        self.assertIn("teste grátis terminou", mensalidade.texto_consulta(teste))

        falhou = licenca("assinatura", {"situacao": "pendente", "ate": daqui(-1), "motivo": "falhou"}, daqui(-1))
        self.assertEqual(falhou.situacao_cobranca, "consulta", "vencida offline tambem e consulta")
        self.assertIn("pagamento for confirmado", mensalidade.texto_consulta(falhou))

    def test_textos_sem_termo_tecnico(self) -> None:
        casos = [
            licenca("teste", {"situacao": "teste", "ate": daqui(4)}, daqui(4)),
            licenca("assinatura", {"situacao": "pendente", "ate": daqui(7), "motivo": "falhou"}, daqui(7)),
            licenca("assinatura", {"situacao": "pendente", "ate": daqui(-1), "motivo": "cancelou"}, daqui(-1)),
        ]
        for lic in casos:
            f = mensalidade.faixa(lic, HOJE)
            for texto in (f.titulo, f.texto, f.botao):
                self.assertNotRegex(texto, r"licen[cç]a_|None|expirad|bloque|null")


class PrazoDoUltimoDiaTestCase(unittest.TestCase):
    def test_data_sem_hora_vale_o_dia_inteiro(self) -> None:
        """'Ate 10/11' e o dia 10 inteiro, como no banco - nao a meia-noite que o comeca."""
        self.assertFalse(licenca("teste", expira=daqui(0)).is_expired)
        self.assertTrue(licenca("teste", expira=daqui(-1)).is_expired)
        agora = datetime.now(timezone.utc)
        self.assertTrue(licenca("teste", expira=(agora - timedelta(minutes=1)).isoformat()).is_expired)


class CobrancaSoValeAssinadaTestCase(unittest.TestCase):
    """O license.json pode ser editado: a cobranca que vale e a que a DumTech assinou."""

    def setUp(self) -> None:
        for patch in (mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "0"}),
                      chaves_de_teste(), neste_computador()):
            patch.start()
            self.addCleanup(patch.stop)
        self.arquivo = Path(tempfile.mkdtemp(prefix="dumtech_mensal_")) / "license.json"

    def _abrir(self, no_arquivo: dict, assinada: dict | None, tipo: str = "teste") -> License:
        agora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        extra = {"cobranca": assinada} if assinada is not None else {}
        dados = License(
            key=CHAVE, customer="Padaria", entitlements=("estoque", "vendas"), machine=machine_id(),
            activated_at=agora, last_check=agora, source=ORIGEM_SUPABASE, max_machines=2, tipo=tipo,
            expires_at=daqui(5), cobranca=no_arquivo,
            assinado=pacote(tipo=tipo, expira_em=daqui(5), **extra),
        ).to_dict()
        self.arquivo.write_text(json.dumps(dados), encoding="utf-8")
        return LicenseService(file_path=self.arquivo).current

    def test_vale_a_assinada(self) -> None:
        lic = self._abrir({"situacao": "em_dia"}, {"situacao": "teste", "ate": daqui(5)})
        self.assertEqual(lic.situacao_cobranca, "teste")

    def test_inventada_no_arquivo_nao_vale(self) -> None:
        lic = self._abrir({"situacao": "em_dia"}, None, tipo="vitalicia")
        self.assertEqual(lic.cobranca, {})

    def test_ida_e_volta_no_arquivo(self) -> None:
        lic = licenca("assinatura", {"situacao": "em_dia", "ate": None, "motivo": None, "desde": "2026-11-01"})
        self.assertEqual(License.from_dict(lic.to_dict()).cobranca, lic.cobranca)


if __name__ == "__main__":
    unittest.main()


class TelasDaMensalidadeTestCase(unittest.TestCase):
    """O Inicio e a tela de Licenca: com faixa so para o plano mensal."""

    def setUp(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from dumtech.core.config import Settings
        from dumtech.hub.main_window import HubWindow
        from dumtech.ui.theme import MODO_ESCURO, ThemeManager

        from .test_licenciamento import GatewayFalso, arquivo_licenca

        self.app = QApplication.instance() or QApplication([])
        self.service = LicenseService(arquivo_licenca(), GatewayFalso(apps=("estoque",)))
        self.hub = HubWindow(
            settings=Settings(Path(tempfile.mkdtemp()) / "hub.json"),
            license_service=self.service,
            theme=ThemeManager(self.app, MODO_ESCURO),
        )
        self.hub.launcher.notify = lambda *args: None
        self.addCleanup(self.hub.close)

    def _com(self, lic: License):
        return mock.patch.object(LicenseService, "current", new_callable=mock.PropertyMock, return_value=lic)

    def test_inicio_do_vitalicio_nao_tem_faixa(self) -> None:
        with self._com(licenca()):
            self.hub.home_view.refresh()
        self.assertIsNone(self.hub.home_view.faixa_mensal)

    def test_inicio_do_teste_tem_faixa_e_o_assinar_abre_a_loja(self) -> None:
        from dumtech.ui.widgets.buttons import Button

        with self._com(licenca("teste", {"situacao": "teste", "ate": daqui(4)}, daqui(4))):
            self.hub.home_view.refresh()
        faixa = self.hub.home_view.faixa_mensal
        self.assertIsNotNone(faixa)
        pedidos = []
        self.hub.home_view.adquirir.disconnect()      # sem abrir navegador no teste
        self.hub.home_view.adquirir.connect(lambda: pedidos.append("loja"))
        [botao] = [b for b in faixa.findChildren(Button) if b.text().strip() == "Assinar"]
        botao.click()
        self.assertEqual(pedidos, ["loja"])

    def test_licenca_do_teste_encerrado_mostra_o_plano_e_nao_pede_outra_chave(self) -> None:
        tela = self.hub.license_view
        vencida = licenca("teste", {"situacao": "teste", "ate": daqui(-2)}, daqui(-2),
                          bloqueio="expirada", mensagem="Seu teste grátis terminou.")
        with self._com(vencida), mock.patch.object(LicenseService, "reload", return_value=vencida):
            tela.refresh()
        self.assertTrue(tela.card_dados.isVisibleTo(tela))
        self.assertFalse(tela.card_ativacao.isVisibleTo(tela))
        self.assertIn("teste grátis terminou", tela.subtitulo.text())
