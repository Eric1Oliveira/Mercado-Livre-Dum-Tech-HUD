"""O aviso "o que mudou": uma vez, e so para quem usa o modulo que mudou.

Quem so tem a Agenda nao precisa saber do Balcao - e quem nao tem nada a ver
com a versao nova nao e interrompido por ela.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtWidgets import QApplication, QLabel

from dumtech import __version__
from dumtech.core import novidades
from dumtech.core.config import Settings
from dumtech.core.conta import Conta, ContaService
from dumtech.core.comunicados import Comunicado, ComunicadosService
from dumtech.core.licensing import LicenseService
from dumtech.core.registry import AppRegistry
from dumtech.core.uso import UsoService
from dumtech.core.versao import mais_nova
from dumtech.hub.main_window import PAGINA_INICIO, HubWindow
from dumtech.hub.views import anuncio_dialog
from dumtech.hub.views.novidades_dialog import NovidadesDialog
from dumtech.ui.theme import MODO_ESCURO, ThemeManager

from .assinante import licenca_de_teste
from .test_porta_entrada import CHAVE, ClienteFalso, GatewayFalso, pasta, sem_modo_local

N = novidades.Novidade

VERSOES = {
    "1.0.0": (N("vendas", "Antiga do Balcao"),),
    "1.1.0": (N("vendas", "Balcao novo"), N("agenda", "Agenda nova"), N("", "Para todos")),
    "1.2.0": (N("estoque", "Estoque futuro"),),
}


def _settings() -> Settings:
    return Settings(pasta() / "hub.json")


class PendentesTestCase(unittest.TestCase):
    def _titulos(self, settings, instalada, modulos) -> list[str]:
        return [n.titulo for n in novidades.pendentes(settings, instalada, modulos, VERSOES)]

    def test_so_o_que_e_dos_modulos_da_pessoa(self) -> None:
        self.assertEqual(self._titulos(_settings(), "1.1.0", ["agenda"]),
                         ["Agenda nova", "Para todos"])
        self.assertEqual(self._titulos(_settings(), "1.1.0", ["vendas", "agenda"]),
                         ["Balcao novo", "Agenda nova", "Para todos"])

    def test_sem_modulo_afetado_nao_ha_aviso(self) -> None:
        so_dos_modulos = {"1.1.0": VERSOES["1.1.0"][:2]}
        self.assertEqual(
            novidades.pendentes(_settings(), "1.1.0", ["clientes"], so_dos_modulos), [])

    def test_sem_marca_conta_so_a_versao_instalada(self) -> None:
        """Primeira abertura com o recurso: nada de despejar o historico inteiro."""
        self.assertNotIn("Antiga do Balcao", self._titulos(_settings(), "1.1.0", ["vendas"]))

    def test_quem_pulou_versoes_ve_o_que_perdeu(self) -> None:
        settings = _settings()
        settings.set(novidades.SECAO, "vista", "0.9.0")
        self.assertEqual(self._titulos(settings, "1.1.0", ["vendas"]),
                         ["Balcao novo", "Para todos", "Antiga do Balcao"])

    def test_texto_de_versao_que_nao_chegou_nao_aparece(self) -> None:
        self.assertNotIn("Estoque futuro", self._titulos(_settings(), "1.1.0", ["estoque"]))

    def test_visto_nao_volta(self) -> None:
        settings = _settings()
        novidades.marcar_vista(settings, "1.1.0")
        self.assertEqual(self._titulos(settings, "1.1.0", ["vendas", "agenda"]), [])

    def test_a_marca_so_anda_para_a_frente(self) -> None:
        settings = _settings()
        novidades.marcar_vista(settings, "1.1.0")
        novidades.marcar_vista(settings, "1.0.0")
        self.assertEqual(settings.get(novidades.SECAO, "vista"), "1.1.0")


class TextoDasVersoesTestCase(unittest.TestCase):
    """O que esta escrito em `VERSOES` - erro de digitacao some com o aviso."""

    def test_todo_modulo_citado_existe(self) -> None:
        existentes = {e.app_id for e in AppRegistry().entries}
        for versao, itens in novidades.VERSOES.items():
            for item in itens:
                with self.subTest(versao=versao, titulo=item.titulo):
                    self.assertTrue(not item.app_id or item.app_id in existentes,
                                    f"modulo '{item.app_id}' nao existe: ninguem veria o aviso")
                    self.assertTrue(item.titulo.strip())

    def test_nenhuma_nota_de_versao_futura(self) -> None:
        for versao in novidades.VERSOES:
            self.assertFalse(mais_nova(versao, __version__),
                             f"nota da {versao} numa versao {__version__}")


class NovidadesNoHubTestCase(unittest.TestCase):
    """Na hora boa do anuncio (Inicio, Hub na frente), e no lugar dele."""

    def setUp(self) -> None:
        for patch in (sem_modo_local(), licenca_de_teste(),
                      mock.patch.object(novidades, "VERSOES", {__version__: (
                          N("vendas", "Balcao: Adicionar na hora"),
                          N("agenda", "Agenda: nome da cliente"),
                      )})):
            patch.__enter__()
            self.addCleanup(patch.__exit__, None, None, None)
        self.app = QApplication.instance() or QApplication([])
        self.settings = _settings()

    def _hub(self, apps: tuple[str, ...]) -> HubWindow:
        license_service = LicenseService(pasta() / "license.json", GatewayFalso(apps))
        license_service.activate(CHAVE)
        Conta(concluido=True, email="joao@exemplo.com").salvar(self.settings)
        hub = HubWindow(settings=self.settings, license_service=license_service,
                        theme=ThemeManager(self.app, MODO_ESCURO))
        hub.launcher.notify = lambda *args: None
        hub.conta_service = ContaService(self.settings, ClienteFalso())
        hub.comunicados_service = ComunicadosService(
            client=ClienteFalso({"ok": True, "comunicados": []}),
            arquivo=pasta() / "comunicados.json",
        )
        hub.uso_service = UsoService(hub.hub_store, ClienteFalso({"ok": True, "gravados": 0}))
        self.addCleanup(hub.close)
        hub.show()
        hub.activateWindow()
        hub.raise_()
        hub._go(PAGINA_INICIO)
        self.app.processEvents()
        return hub

    def test_mostra_so_o_que_mudou_no_modulo_da_pessoa(self) -> None:
        hub = self._hub(("agenda", "clientes"))
        with mock.patch("dumtech.hub.main_window.NovidadesDialog") as janela:
            hub._talvez_anunciar()
        janela.assert_called_once()
        itens = janela.call_args.args[0]
        self.assertEqual([n.titulo for n in itens], ["Agenda: nome da cliente"],
                         "quem nao tem o Vendas nao precisa saber do Balcao")

    def test_aparece_uma_vez_e_nunca_mais(self) -> None:
        hub = self._hub(("vendas",))
        with mock.patch("dumtech.hub.main_window.NovidadesDialog") as janela:
            hub._talvez_anunciar()
            hub._anunciou = False           # como se fosse outra abertura do Hub
            hub._talvez_anunciar()
        self.assertEqual(janela.call_count, 1)

    def test_quem_nao_tem_modulo_afetado_nao_ve_nada(self) -> None:
        hub = self._hub(("financeiro",))
        with mock.patch("dumtech.hub.main_window.NovidadesDialog") as janela:
            hub._talvez_anunciar()
        janela.assert_not_called()
        self.assertEqual(self.settings.get(novidades.SECAO, "vista"), __version__,
                         "nada a contar: a versao conta como vista")

    def test_novidade_vem_antes_do_anuncio_e_ele_espera(self) -> None:
        hub = self._hub(("vendas",))
        hub.comunicados_service.listar = lambda *a, **k: [
            Comunicado(id="a1", titulo="Leve o Estoque", rotulo="Oferta")]
        with mock.patch("dumtech.hub.main_window.NovidadesDialog") as janela, \
             mock.patch.object(anuncio_dialog.AnuncioDialog, "exec", return_value=0) as anuncio:
            hub._talvez_anunciar()
        janela.assert_called_once()
        anuncio.assert_not_called()

    def test_quem_acabou_de_instalar_nao_ve_novidade(self) -> None:
        license_service = LicenseService(pasta() / "license.json", GatewayFalso(("vendas",)))
        hub = HubWindow(settings=self.settings, license_service=license_service,
                        theme=ThemeManager(self.app, MODO_ESCURO))
        self.addCleanup(hub.close)
        self.assertEqual(self.settings.get(novidades.SECAO, "vista"), __version__)


class NovidadesDialogTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])

    def test_lista_o_que_mudou_e_tem_ok(self) -> None:
        manifesto = AppRegistry().get("agenda").manifest
        janela = NovidadesDialog([N("agenda", "Agenda: nome da cliente", "Bateu o olho.")],
                                 "1.4.2", {"agenda": manifesto})
        self.addCleanup(janela.deleteLater)
        textos = [w.text() for w in janela.findChildren(QLabel)]
        self.assertIn("Agenda: nome da cliente", textos)
        self.assertIn("Bateu o olho.", textos)
        self.assertEqual(janela.botao_ok.text().strip(), "OK, entendi")
        janela.botao_ok.click()
        self.assertEqual(janela.result(), NovidadesDialog.DialogCode.Accepted)


if __name__ == "__main__":
    unittest.main()
