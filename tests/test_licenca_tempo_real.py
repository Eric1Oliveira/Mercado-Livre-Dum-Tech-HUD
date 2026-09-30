"""Mudanca feita no painel chega em minutos: a impressao digital da licenca.

A consulta leve de 2 em 2 minutos traz um md5 do estado da licenca. O Hub so
faz a conferencia pesada (assinada) quando esse md5 muda - e so aceita o md5
novo como "conhecido" depois que a conferencia der certo.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

_app: QApplication | None = None

MARCA_A = "a" * 32
MARCA_B = "b" * 32


def setUpModule() -> None:
    global _app
    os.environ.setdefault("DUMTECH_DATA_DIR", tempfile.mkdtemp())
    os.environ["DUMTECH_LICENCA_LOCAL"] = "1"
    _app = QApplication.instance() or QApplication([])


class ImpressaoDaLicencaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from dumtech.core.config import Settings
        from dumtech.hub.main_window import HubWindow

        # arquivo proprio por teste: a marca guardada num nao pode vazar no outro
        self.settings = Settings(Path(tempfile.mkdtemp()) / "config.json")
        self.settings.set("conta", "concluido", True)
        self.hub = HubWindow(settings=self.settings)
        self.addCleanup(self.hub.close)
        self.pedidos: list[dict] = []
        self.hub._tarefas_de_rede = lambda **kw: self.pedidos.append(kw)

    def test_impressao_nova_pede_conferencia_na_hora(self) -> None:
        self.hub._licenca_talvez_mudou({"ok": True, "licenca": MARCA_A})
        self.assertEqual(self.pedidos, [{"forcar_licenca": True}])

    def test_impressao_igual_nao_gasta_nada(self) -> None:
        self.settings.set("licenca", "marca", MARCA_A)
        self.hub._licenca_talvez_mudou({"ok": True, "licenca": MARCA_A})
        self.assertEqual(self.pedidos, [])

    def test_sem_impressao_nao_faz_nada(self) -> None:
        """Hub sem ativacao, ou servidor antigo sem o campo."""
        self.hub._licenca_talvez_mudou({"ok": True, "versao": "1.2.3"})
        self.hub._licenca_talvez_mudou(None)
        self.assertEqual(self.pedidos, [])

    def test_so_vira_conhecida_depois_de_conferir(self) -> None:
        """Conferencia que falhou (sem internet) tem de ser tentada de novo."""
        self.hub._licenca_talvez_mudou({"licenca": MARCA_A})
        self.assertNotEqual(self.settings.get("licenca", "marca", ""), MARCA_A)
        # a conferencia falhou: na proxima consulta, pede de novo
        self.hub._licenca_talvez_mudou({"licenca": MARCA_A})
        self.assertEqual(len(self.pedidos), 2)
        # agora deu certo
        self.hub._guardar_marca_da_licenca()
        self.assertEqual(self.settings.get("licenca", "marca", ""), MARCA_A)
        self.hub._licenca_talvez_mudou({"licenca": MARCA_A})
        self.assertEqual(len(self.pedidos), 2)

    def test_mudou_de_novo_confere_de_novo(self) -> None:
        self.settings.set("licenca", "marca", MARCA_A)
        self.hub._licenca_talvez_mudou({"licenca": MARCA_B})
        self.assertEqual(self.pedidos, [{"forcar_licenca": True}])


if __name__ == "__main__":
    unittest.main()
