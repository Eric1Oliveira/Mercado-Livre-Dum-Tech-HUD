"""Janela pequena rola - nunca amassa.

Na 1.2.2 a tela de Licenca, com a janela restaurada (fora do maximizado),
empilhava as linhas umas por cima das outras: o Hub travava um tamanho minimo
"a forca" e, quando o conteudo nao cabia, o Qt espremia os textos abaixo da
altura em que eles conseguem ser desenhados. Desde a 1.2.3 toda pagina fica
dentro de uma area de rolagem.

Este teste abre cada pagina do Hub e cada tela dos aplicativos no MENOR
tamanho de janela permitido e reprova qualquer texto visivel mais baixo do
que ele precisa para aparecer inteiro.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    os.environ.setdefault("DUMTECH_DATA_DIR", tempfile.mkdtemp())
    os.environ["DUMTECH_LICENCA_LOCAL"] = "1"
    _app = QApplication.instance() or QApplication([])


def _amassados(raiz: QWidget) -> list[str]:
    """Textos visiveis mais baixos do que precisam para aparecer."""
    ruins = []
    for rotulo in raiz.findChildren(QLabel):
        if not rotulo.isVisibleTo(raiz) or not rotulo.text().strip():
            continue
        precisa = rotulo.minimumSizeHint().height()
        if rotulo.height() + 1 < precisa:
            ruins.append(f"{rotulo.text()[:30]!r}: {rotulo.height()}px de {precisa}px")
    return ruins


class JanelaPequenaTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from dumtech.core.config import Settings
        from dumtech.hub.main_window import HubWindow

        settings = Settings()
        settings.set("conta", "concluido", True)
        cls.hub = HubWindow(settings=settings)
        cls.hub.show()
        # o menor tamanho que o proprio Hub aceita
        cls.hub.resize(cls.hub.minimumSize())
        QTest.qWait(300)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.hub.close()

    def test_paginas_do_hub(self) -> None:
        from dumtech.hub.main_window import (
            PAGINA_CONFIG,
            PAGINA_INICIO,
            PAGINA_LICENCA,
            PAGINA_SOBRE,
        )

        for pagina in (PAGINA_INICIO, PAGINA_LICENCA, PAGINA_CONFIG, PAGINA_SOBRE):
            with self.subTest(pagina=pagina):
                self.hub._go(pagina)
                QTest.qWait(150)
                tela = self.hub.stack.currentWidget()
                self.assertEqual(_amassados(tela), [])

    def test_telas_de_configuracoes(self) -> None:
        cfg = self.hub.config_view
        for indice in range(cfg.stack.count()):
            tela = cfg.stack.widget(indice)
            with self.subTest(tela=type(tela).__name__):
                self.hub._ir_para_config(tela)
                QTest.qWait(150)
                self.assertEqual(_amassados(tela), [])

    def test_telas_dos_aplicativos(self) -> None:
        for app_id in ("vendas", "estoque", "financeiro", "ordens",
                       "orcamentos", "clientes", "agenda"):
            if not self.hub.open_app(app_id):
                continue
            QTest.qWait(150)
            surface = self.hub.launcher.get(app_id)
            for indice in range(surface.stack.count()):
                surface.show_view(indice)
                QTest.qWait(120)
                tela = surface.stack.widget(indice)
                with self.subTest(app=app_id, tela=indice):
                    self.assertEqual(_amassados(tela), [])


if __name__ == "__main__":
    unittest.main()
