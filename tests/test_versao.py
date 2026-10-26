"""As pecinhas do aviso de versao: comparar numero e confiar no endereco.

O caminho completo (baixar, conferir a assinatura e instalar) esta em
tests/test_atualizacao.py.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dumtech.core.config import Settings
from dumtech.core.versao import (
    dispensar,
    endereco_confiavel,
    foi_dispensada,
    mais_nova,
    numeros,
)


def _settings() -> Settings:
    return Settings(Path(tempfile.mkdtemp(prefix="dumtech_versao_")) / "hub.json")


class ComparacaoTestCase(unittest.TestCase):
    def test_versao_e_numero_nao_texto(self) -> None:
        """"1.10.0" e maior que "1.9.0" - no alfabeto seria o contrario."""
        self.assertTrue(mais_nova("1.10.0", "1.9.0"))
        self.assertFalse(mais_nova("1.9.0", "1.10.0"))
        self.assertTrue(mais_nova("2.0", "1.9.9"))
        self.assertFalse(mais_nova("1.1.0", "1.1.0"), "igual nao e novidade")
        self.assertFalse(mais_nova("1.0.0", "1.1.0"), "servidor atras do cliente")

    def test_tamanhos_diferentes(self) -> None:
        self.assertTrue(mais_nova("1.1.1", "1.1"))
        self.assertFalse(mais_nova("1.1", "1.1.0"))

    def test_lixo_nunca_vira_aviso(self) -> None:
        for texto in ("", "nova", None, "v?", "..."):
            self.assertEqual(numeros(texto), ())
            self.assertFalse(mais_nova(texto, "1.0.0"))
            self.assertFalse(mais_nova("1.0.0", texto))


class EnderecoTestCase(unittest.TestCase):
    """O endereco de atualizacao vem do servidor - e so o nosso vale.

    Achado do pentest de 17/09/2026: painel invadido + link para um instalador
    falso = o cliente instala o golpe confiando no proprio programa.
    """

    def setUp(self) -> None:
        self.enterContext(mock.patch.dict(
            os.environ, {"DUMTECH_URL_LOJA": "https://dumtechsolution.com"}))

    def test_endereco_da_loja_passa(self) -> None:
        for bom in ("https://dumtechsolution.com/baixar/",
                    "https://DUMTECHSOLUTION.com/baixar/DumTech-Hub-Setup.exe"):
            self.assertEqual(endereco_confiavel(bom), bom)

    def test_qualquer_outro_endereco_cai_no_padrao(self) -> None:
        for golpe in ("https://dumtechsolution.com.golpe.com/x.exe",
                      "http://dumtechsolution.com/baixar/",   # sem https
                      "https://mega.nz/instalador.exe",
                      "javascript:alert(1)", "", None):
            self.assertEqual(endereco_confiavel(golpe, "PADRAO"), "PADRAO", golpe)

    def test_servidor_local_so_fora_do_programa_instalado(self) -> None:
        """Em desenvolvimento da para apontar para 127.0.0.1; no .exe, nunca."""
        import sys

        local = "http://127.0.0.1:8123/DumTech-Hub-Setup.exe"
        self.assertEqual(endereco_confiavel(local), local)

        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertEqual(endereco_confiavel(local, "PADRAO"), "PADRAO")


class DispensarTestCase(unittest.TestCase):
    def test_cala_so_a_versao_dispensada(self) -> None:
        settings = _settings()
        self.assertFalse(foi_dispensada(settings, "1.3.0"))

        dispensar(settings, "1.3.0")
        self.assertTrue(foi_dispensada(settings, "1.3.0"))
        self.assertFalse(foi_dispensada(settings, "1.4.0"), "a proxima volta a avisar")

    def test_lembrar_em_3_dias(self) -> None:
        from datetime import date, timedelta

        settings = _settings()
        hoje = date(2026, 10, 26)
        dispensar(settings, "1.5.0", hoje=hoje)
        self.assertTrue(foi_dispensada(settings, "1.5.0", hoje=hoje + timedelta(days=2)))
        self.assertFalse(foi_dispensada(settings, "1.5.0", hoje=hoje + timedelta(days=3)),
                         "depois de 3 dias a faixa volta")

    def test_adiada_para_sempre_antes_da_1_5_volta_a_lembrar(self) -> None:
        settings = _settings()
        settings.set("versao", "dispensada", "1.4.5")  # sem a data: o jeito antigo
        self.assertFalse(foi_dispensada(settings, "1.4.5"))


if __name__ == "__main__":
    unittest.main()
