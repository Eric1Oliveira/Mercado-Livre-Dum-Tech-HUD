"""Teste gratis de 7 dias: libera no prazo, bloqueia sozinho, nao estica.

O fim do teste vem DENTRO da licenca assinada. O arquivo license.json so
pode tirar teste - nunca por nem esticar - e o Hub bloqueia no dia certo
mesmo sem internet.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dumtech.core.licensing import (
    ORIGEM_SUPABASE,
    License,
    LicenseError,
    LicenseService,
    machine_id,
)

from .test_assinatura import AQUI, CHAVE, chaves_de_teste, neste_computador, pacote


def _quando(dias: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=dias)).replace(microsecond=0).isoformat()


class LicencaComTesteTestCase(unittest.TestCase):
    def _licenca(self, testes: dict) -> License:
        return License(key=CHAVE, customer="X", entitlements=("vendas",), machine="M",
                       activated_at="", source=ORIGEM_SUPABASE, testes=testes)

    def test_modulo_em_teste_abre(self) -> None:
        licenca = self._licenca({"agenda": _quando(5)})
        self.assertTrue(licenca.allows("agenda"))
        self.assertTrue(licenca.teste_ativo("agenda"))
        self.assertEqual(licenca.dias_de_teste("agenda"), 5)
        self.assertEqual(licenca.em_teste, ("agenda",))

    def test_teste_que_acabou_fecha_sozinho(self) -> None:
        licenca = self._licenca({"agenda": _quando(-0.01)})
        self.assertFalse(licenca.allows("agenda"))
        self.assertTrue(licenca.teste_acabou("agenda"))
        self.assertEqual(licenca.em_teste, ())

    def test_modulo_comprado_nao_conta_como_teste(self) -> None:
        licenca = self._licenca({"vendas": _quando(3)})
        self.assertTrue(licenca.allows("vendas"))
        self.assertFalse(licenca.teste_ativo("vendas"))

    def test_data_estranha_nao_libera(self) -> None:
        self.assertFalse(self._licenca({"agenda": "amanha"}).allows("agenda"))

    def test_ida_e_volta_no_arquivo(self) -> None:
        licenca = self._licenca({"agenda": _quando(2)})
        self.assertEqual(License.from_dict(licenca.to_dict()).testes, licenca.testes)


class AssinaturaDoTesteTestCase(unittest.TestCase):
    """O arquivo so pode TIRAR teste. Vale o que a DumTech assinou."""

    def setUp(self) -> None:
        for patch in (mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "0"}),
                      chaves_de_teste(), neste_computador()):
            patch.start()
            self.addCleanup(patch.stop)
        self.arquivo = Path(tempfile.mkdtemp(prefix="dumtech_teste_")) / "license.json"

    def _abrir(self, testes_no_arquivo: dict, testes_assinados: dict) -> License:
        agora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        dados = License(
            key=CHAVE, customer="Padaria", entitlements=("estoque", "vendas"),
            machine=machine_id(), activated_at=agora, last_check=agora, source=ORIGEM_SUPABASE,
            max_machines=2, assinado=pacote(testes=testes_assinados), testes=testes_no_arquivo,
        ).to_dict()
        self.arquivo.write_text(json.dumps(dados), encoding="utf-8")
        return LicenseService(file_path=self.arquivo).current

    def test_teste_assinado_vale(self) -> None:
        fim = _quando(6)
        licenca = self._abrir({"agenda": fim}, {"AGENDA": fim})
        self.assertTrue(licenca.allows("agenda"))

    def test_esticar_o_prazo_no_arquivo_nao_adianta(self) -> None:
        """Alguem troca a data no license.json: vale a data assinada."""
        licenca = self._abrir({"agenda": _quando(300)}, {"AGENDA": _quando(-1)})
        self.assertFalse(licenca.allows("agenda"))

    def test_inventar_teste_no_arquivo_nao_adianta(self) -> None:
        licenca = self._abrir({"ordens": _quando(5)}, {})
        self.assertFalse(licenca.allows("ordens"))
        self.assertEqual(licenca.testes, {})


class IniciarTesteTestCase(unittest.TestCase):
    """O botao do Hub: pede ao servidor e ja traz a licenca com o teste."""

    def test_pede_ao_servidor_e_reconfere(self) -> None:
        pedidos = []

        class Gateway:
            def iniciar_teste(self, key, machine, produto):
                pedidos.append(produto)
                return {"ok": True}

            def verify(self, key, machine):
                return License(key=key, customer="X", entitlements=("vendas",), machine=machine,
                               activated_at="", source=ORIGEM_SUPABASE,
                               testes={"agenda": _quando(7)})

        arquivo = Path(tempfile.mkdtemp()) / "license.json"
        servico = LicenseService(file_path=arquivo, gateway=Gateway())
        servico.save(License(key=CHAVE, customer="X", entitlements=("vendas",), machine="M",
                             activated_at="", source=ORIGEM_SUPABASE))
        with mock.patch("dumtech.core.licensing.LicenseService._conferir_assinatura",
                        side_effect=lambda licenca: licenca):
            licenca = servico.iniciar_teste("agenda")
        self.assertEqual(pedidos, ["agenda"])
        self.assertTrue(licenca.teste_ativo("agenda"))

    def test_sem_licenca_nao_pede_nada(self) -> None:
        gateway = mock.Mock()
        with mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "0"}):
            servico = LicenseService(file_path=Path(tempfile.mkdtemp()) / "license.json",
                                     gateway=gateway)
            with self.assertRaises(LicenseError):
                servico.iniciar_teste("agenda")
        gateway.iniciar_teste.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class TesteNaTelaTestCase(unittest.TestCase):
    """O cliente ve o teste: na barra do modulo e na tela de licenca."""

    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_selo_e_comprar_na_barra_do_modulo(self) -> None:
        from dumtech.core.app_module import AppManifest
        from dumtech.hub.workspace import ContextBar

        manifest = AppManifest(app_id="agenda", name="DumTech Agenda", short_name="Agenda",
                               description="", icon="calendar", accent="#7353F6")
        barra = ContextBar(manifest)
        self.addCleanup(barra.deleteLater)
        barra.show()
        barra.mostrar_teste(None)                      # comprado: nada aparece
        self.assertFalse(barra.botao_comprar.isVisible())
        barra.mostrar_teste(5)
        self.assertTrue(barra.botao_comprar.isVisible())
        self.assertIn("5 dias", barra.selo_teste.text())
        barra.mostrar_teste(1)
        self.assertIn("ultimo dia", barra.selo_teste.text())

    def test_comprar_abre_a_loja_com_o_modulo_no_carrinho(self) -> None:
        from dumtech.core.loja import url_compra
        self.assertIn("kit=agenda", url_compra("TOKEN", marcar=("AGENDA",)))
        self.assertIn("kit=agenda", url_compra("", ("vendas",), ("AGENDA",)))
