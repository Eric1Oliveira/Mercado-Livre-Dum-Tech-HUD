"""A porta de entrada do cliente: boas-vindas, anuncio em pop-up e loja.

Nenhum teste acessa a internet: o servidor e substituido por um cliente falso e
o gateway de licenca por um de mentira.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from dumtech.ui.widgets.buttons import Button

from dumtech.core import comunicados, loja
from dumtech.core.comunicados import Comunicado, ComunicadosService
from dumtech.hub.views import anuncio_dialog
from dumtech.core.config import Settings
from dumtech.core.conta import Conta, ContaService
from dumtech.core.empresa import Empresa
from dumtech.core.licensing import ORIGEM_SUPABASE, License, LicenseService
from dumtech.core.uso import UsoService
from dumtech.hub.main_window import PAGINA_BOAS_VINDAS, PAGINA_INICIO, HubWindow
from dumtech.hub.views.boas_vindas_view import PASSO_CADASTRO, PASSO_CHAVE, BoasVindasView
from dumtech.ui.theme import MODO_ESCURO, ThemeManager

from .assinante import assinar_licenca, licenca_de_teste

CHAVE = "DEMO-2026-TEST-0001"


def pasta() -> Path:
    return Path(tempfile.mkdtemp(prefix="dumtech_porta_"))


def sem_modo_local():
    """Fora do modo de desenvolvimento - e com a loja num endereco de mentira.

    Sem fixar a loja, o caminho de erro de `abrir_loja` chamaria `url_compra()`
    e levantaria um servidor local de verdade no meio da suite.
    """
    return mock.patch.dict(os.environ, {
        "DUMTECH_LICENCA_LOCAL": "0",
        "DUMTECH_URL_LOJA": "https://loja.teste/comprar",
    })


class LinkDoAnuncioTestCase(unittest.TestCase):
    """O codigo de identificacao so entra em link NOSSO."""

    def setUp(self) -> None:
        self.enterContext(sem_modo_local())

    def test_reconhece_o_endereco_da_propria_loja(self) -> None:
        self.assertTrue(loja.e_da_loja("https://loja.teste/comprar"))
        self.assertTrue(loja.e_da_loja("https://LOJA.teste/comprar/novidades?x=1"))
        self.assertFalse(loja.e_da_loja("https://loja.teste.golpe.example/comprar"))
        self.assertFalse(loja.e_da_loja("https://outrolugar.example/promo"))
        self.assertFalse(loja.e_da_loja("javascript:alert(1)"))
        self.assertFalse(loja.e_da_loja(""))

    def test_o_codigo_entra_sem_atrapalhar_o_resto_do_link(self) -> None:
        pronto = loja.com_token("https://loja.teste/comprar/novidades?kit=vendas#topo", "ABC")
        self.assertEqual(pronto, "https://loja.teste/comprar/novidades?kit=vendas&t=ABC#topo")

    def test_codigo_velho_no_link_e_trocado(self) -> None:
        self.assertEqual(loja.com_token("https://loja.teste/comprar?t=VELHO", "NOVO"),
                         "https://loja.teste/comprar?t=NOVO")

    def test_link_de_fora_nunca_recebe_o_codigo(self) -> None:
        self.assertEqual(loja.com_token("https://outrolugar.example/promo", "ABC"),
                         "https://outrolugar.example/promo")

    def test_sem_codigo_o_link_sai_como_veio(self) -> None:
        self.assertEqual(loja.com_token("https://loja.teste/comprar", ""),
                         "https://loja.teste/comprar")

    def test_servico_pede_o_codigo_com_a_licenca(self) -> None:
        cliente = ClienteFalso({"ok": True, "token": "ABC"})
        licenca = mock.Mock(ativa=True, key=CHAVE, machine="MAQ", entitlements=("vendas",))
        pronto = loja.LojaService(cliente).link_do_anuncio(
            "https://loja.teste/comprar/novidades", licenca)
        self.assertEqual(pronto, "https://loja.teste/comprar/novidades?t=ABC")
        self.assertEqual(cliente.chamadas[0][1]["p_chave"], CHAVE)

    def test_servico_nao_fala_com_o_servidor_por_link_de_fora(self) -> None:
        cliente = ClienteFalso({"ok": True, "token": "ABC"})
        pronto = loja.LojaService(cliente).link_do_anuncio(
            "https://outrolugar.example/promo", mock.Mock(ativa=True, key=CHAVE, machine="M"))
        self.assertEqual(pronto, "https://outrolugar.example/promo")
        self.assertEqual(cliente.chamadas, [])

    def test_sem_link_cai_na_loja_de_sempre(self) -> None:
        cliente = ClienteFalso({"ok": True, "token": "ABC"})
        pronto = loja.LojaService(cliente).link_do_anuncio("", nome="Ana", email="a@b.com")
        self.assertEqual(pronto, "https://loja.teste/comprar?t=ABC")


class ClienteFalso:
    """Servidor de mentira: guarda o que foi chamado."""

    def __init__(self, resposta=None, excecao: Exception | None = None) -> None:
        self.resposta = resposta if resposta is not None else {"ok": True}
        self.excecao = excecao
        self.chamadas: list[tuple[str, dict]] = []

    def rpc(self, funcao: str, params: dict | None = None):
        self.chamadas.append((funcao, params or {}))
        if self.excecao is not None:
            raise self.excecao
        return self.resposta


class GatewayFalso:
    """Servidor de licencas de mentira."""

    def __init__(self, apps: tuple[str, ...] = ("estoque",)) -> None:
        self.apps = apps

    def fetch(self, key: str, machine: str) -> License:
        agora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return assinar_licenca(License(
            key=key, customer="Joao da Silva", entitlements=self.apps, machine=machine,
            activated_at=agora, last_check=agora, source=ORIGEM_SUPABASE,
            max_machines=1, used_machines=1, tipo="vitalicia",
        ))

    def verify(self, key: str, machine: str) -> License:
        return self.fetch(key, machine)

    def release(self, key: str, machine: str) -> None:
        return None


def esperar_tarefas(app: QApplication) -> None:
    """As chamadas de rede rodam em segundo plano: deixa terminarem."""
    QThreadPool.globalInstance().waitForDone(8000)
    app.processEvents()


class LinkDeOfertaTestCase(unittest.TestCase):
    """O link da oferta vem do servidor e abre no computador do cliente."""

    def test_so_https_passa(self) -> None:
        self.assertEqual(
            Comunicado.de_dict({"titulo": "x", "link": " https://dumtech.com.br/oferta?a=1 "}).link,
            "https://dumtech.com.br/oferta?a=1",
        )
        for perigoso in ("file:///C:/Users/Public/x.exe", r"\\servidor\pasta\x.exe",
                         "javascript:alert(1)", "http://dumtech.com.br", "ms-settings:",
                         "https://ok.com/ com espaco", "https://x.com\\..\\y", None, 42):
            with self.subTest(link=perigoso):
                self.assertEqual(Comunicado.de_dict({"titulo": "x", "link": perigoso}).link, "")

    def test_abrir_endereco_recusa_o_que_nao_e_web(self) -> None:
        with mock.patch("dumtech.hub.main_window.QDesktopServices.openUrl") as abrir:
            HubWindow._abrir_endereco("file:///C:/Windows/System32/calc.exe")
            HubWindow._abrir_endereco(r"\\servidor\x.exe")
            HubWindow._abrir_endereco("")
            abrir.assert_not_called()
            HubWindow._abrir_endereco("http://127.0.0.1:5173/?t=abc")
            HubWindow._abrir_endereco("https://dumtech.com.br")
            self.assertEqual(abrir.call_count, 2)


class BoasVindasTestCase(unittest.TestCase):
    """A tela dos dois passos, sozinha."""

    def setUp(self) -> None:
        for patch in (sem_modo_local(), licenca_de_teste()):
            patch.__enter__()
            self.addCleanup(patch.__exit__, None, None, None)

        self.app = QApplication.instance() or QApplication([])
        self.settings = Settings(pasta() / "hub.json")
        self.license_service = LicenseService(pasta() / "license.json", GatewayFalso())
        self.cliente = ClienteFalso()
        self.conta_service = ContaService(self.settings, self.cliente)
        self.tela = BoasVindasView(self.settings, self.license_service, self.conta_service)
        self.addCleanup(self.tela.deleteLater)

    def test_comeca_pedindo_quem_e_voce(self) -> None:
        self.assertEqual(self.tela.passos.currentIndex(), PASSO_CADASTRO)

    def test_cadastro_guarda_a_identidade_e_avanca(self) -> None:
        self.tela.campo_nome.setText("Loja do Joao")
        self.tela.campo_email.setText("joao@exemplo.com")
        self.tela.campo_telefone.setText("(63) 99999-0000")
        self.tela.continuar()
        esperar_tarefas(self.app)

        self.assertEqual(self.tela.passos.currentIndex(), PASSO_CHAVE,
                         "depois do cadastro vem a chave")

        # a mesma identidade que assina os comprovantes
        empresa = Empresa.carregar(Settings(self.settings.file_path))
        self.assertEqual(empresa.nome, "Loja do Joao")
        self.assertEqual(empresa.email, "joao@exemplo.com")
        self.assertTrue(empresa.telefone, "o telefone digitado precisa ser guardado")

        conta = Conta.carregar(Settings(self.settings.file_path))
        self.assertTrue(conta.concluido)
        self.assertTrue(conta.registrada)
        self.assertEqual(self.cliente.chamadas[0][0], "dumtech_identificar_cliente")

    def test_dados_errados_nao_avancam_nem_chamam_o_servidor(self) -> None:
        self.tela.campo_nome.setText("Joao")
        self.tela.campo_email.setText("isso-nao-e-email")
        self.tela.continuar()

        self.assertEqual(self.tela.passos.currentIndex(), PASSO_CADASTRO)
        self.assertEqual(self.cliente.chamadas, [])

    def test_sem_internet_o_cadastro_fica_pendente_mas_avanca(self) -> None:
        from dumtech.core.supabase import SemConexao

        tela = BoasVindasView(
            self.settings, self.license_service,
            ContaService(self.settings, ClienteFalso(excecao=SemConexao("sem rede"))),
        )
        self.addCleanup(tela.deleteLater)
        tela.campo_nome.setText("Loja do Joao")
        tela.campo_email.setText("joao@exemplo.com")
        tela.continuar()
        esperar_tarefas(self.app)

        self.assertEqual(tela.passos.currentIndex(), PASSO_CHAVE)
        conta = Conta.carregar(Settings(self.settings.file_path))
        self.assertTrue(conta.concluido, "o cliente entra mesmo sem internet")
        self.assertTrue(conta.pendente)

    def test_ainda_nao_tenho_chave_termina_o_primeiro_acesso(self) -> None:
        avisos = []
        self.tela.concluido.connect(lambda: avisos.append(True))
        self.tela.pular()
        self.assertEqual(avisos, [True])

    def test_ativar_a_chave_no_primeiro_acesso(self) -> None:
        concluido, licenca_alterada = [], []
        self.tela.concluido.connect(lambda: concluido.append(True))
        self.tela.licenca_alterada.connect(lambda: licenca_alterada.append(True))

        self.tela.campo_chave.setText(CHAVE)
        self.tela.ativar()
        esperar_tarefas(self.app)

        self.assertTrue(self.license_service.ativada)
        self.assertEqual(concluido, [True])
        self.assertEqual(licenca_alterada, [True])

    def test_chave_vazia_nem_tenta(self) -> None:
        self.tela.campo_chave.setText("")
        self.tela.ativar()
        esperar_tarefas(self.app)
        self.assertFalse(self.license_service.ativada)


class HubPortaDeEntradaTestCase(unittest.TestCase):
    """Onde o Hub abre, e o que ele mostra."""

    def setUp(self) -> None:
        for patch in (sem_modo_local(), licenca_de_teste()):
            patch.__enter__()
            self.addCleanup(patch.__exit__, None, None, None)
        self.app = QApplication.instance() or QApplication([])
        self.settings = Settings(pasta() / "hub.json")
        self.license_service = LicenseService(pasta() / "license.json", GatewayFalso())

    def montar(self) -> HubWindow:
        hub = HubWindow(
            settings=self.settings,
            license_service=self.license_service,
            theme=ThemeManager(self.app, MODO_ESCURO),
        )
        hub.launcher.notify = lambda *args: None
        # nada de rede nos testes, venha de onde vier o pedido
        hub.conta_service = ContaService(self.settings, ClienteFalso())
        hub.comunicados_service = ComunicadosService(
            client=ClienteFalso({"ok": True, "comunicados": []}),
            arquivo=pasta() / "comunicados.json",
        )
        hub.uso_service = UsoService(hub.hub_store, ClienteFalso({"ok": True, "gravados": 0}))
        hub.loja = mock.Mock(link=mock.Mock(return_value="https://loja.teste/comprar?t=ABC"))
        self.addCleanup(hub.close)
        return hub

    def test_cliente_novo_abre_nas_boas_vindas(self) -> None:
        hub = self.montar()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_BOAS_VINDAS)

    def test_quem_ja_se_apresentou_abre_no_inicio(self) -> None:
        Conta(concluido=True, email="joao@exemplo.com").salvar(self.settings)
        hub = self.montar()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_INICIO)

    def test_quem_ja_tem_licenca_nao_ve_as_boas_vindas(self) -> None:
        self.license_service.activate(CHAVE)
        hub = self.montar()

        self.assertEqual(hub.stack.currentIndex(), PAGINA_INICIO)
        self.assertTrue(Conta.carregar(self.settings).concluido,
                        "instalacao antiga nao tem nada a contar de novo")

    def test_terminar_o_primeiro_acesso_leva_ao_inicio(self) -> None:
        hub = self.montar()
        hub.boas_vindas_view.pular()
        esperar_tarefas(self.app)
        self.assertEqual(hub.stack.currentIndex(), PAGINA_INICIO)

    def test_o_inicio_nao_vira_mural_de_anuncio(self) -> None:
        """Anuncio chega por pop-up, e so. O Inicio e do trabalho do cliente.

        Antes havia um bloco fixo "DumTech para voce" no meio da tela, que
        competia com o pop-up e mostrava a mesma oferta para sempre.
        """
        hub = self.montar()
        # o servico tem oferta para dar; o Inicio nao pode mostra-la
        hub.comunicados_service.listar = lambda: [
            Comunicado(id="1", titulo="Leve o Vendas", texto="Balcao mais rapido",
                       rotulo="Oferta")
        ]
        hub.home_view.refresh()

        textos = [w.text() for w in hub.home_view.corpo.findChildren(QLabel)]
        self.assertNotIn("DumTech para voce", textos)
        self.assertNotIn("Leve o Vendas", textos,
                         "a oferta vazou para o Inicio: o canal e o pop-up")

    def test_a_loja_continua_a_um_clique_sem_o_bloco(self) -> None:
        """Tirar o bloco nao pode tirar o caminho para comprar.

        O botao morava em tres lugares, e um deles era o bloco removido. Quem
        NAO tem licenca e o caso critico: para ele o bloco vinha antes do
        `return` e era a unica saida na tela. A saida de verdade e o botao do
        estado vazio, que emite o mesmo sinal.
        """
        hub = self.montar()
        hub.home_view.refresh()

        # sem licenca: o estado vazio e quem leva para a loja
        # o texto do Button vem com o espaco do icone na frente
        botoes = [b.text().strip() for b in hub.home_view.findChildren(Button)]
        self.assertIn("Conhecer os modulos", botoes,
                      "sem o bloco, quem nao comprou ficou sem caminho para a loja")

        # e o sinal e mesmo o da loja, nao so um botao com nome parecido
        abriu: list[bool] = []
        hub.home_view.adquirir.connect(lambda: abriu.append(True))
        for botao in hub.home_view.findChildren(Button):
            if botao.text().strip() == "Conhecer os modulos":
                botao.click()
        self.assertTrue(abriu, "o botao nao abre a loja")

    # ------------------------------------------------------------- pop-up
    def _com_anuncio(self, hub, titulo: str = "Leve o Vendas", link: str = ""):
        item = Comunicado(id="a1", titulo=titulo, texto="Balcao mais rapido",
                          rotulo="Oferta", link=link)
        hub.comunicados_service.listar = lambda *a, **k: [item]
        hub.show()
        hub.activateWindow()     # o pop-up so entra com o Hub na frente
        hub.raise_()
        hub._go(PAGINA_INICIO)
        self.app.processEvents()
        return item

    def test_o_anuncio_aparece_uma_vez_e_nunca_mais(self) -> None:
        hub = self.montar()
        self._com_anuncio(hub)
        with mock.patch.object(anuncio_dialog.AnuncioDialog, "exec", return_value=0) as abriu:
            hub._talvez_anunciar()
            hub._anunciou = False          # como se fosse outra abertura do Hub
            hub._talvez_anunciar()

        self.assertEqual(abriu.call_count, 1, "anuncio repetido vira estorvo")
        self.assertEqual(comunicados.vistos(self.settings), ["a1"])

    def test_anuncio_so_aparece_no_inicio(self) -> None:
        """Fora do Inicio a pessoa esta fazendo alguma coisa - anuncio ali e estorvo."""
        hub = self.montar()
        self._com_anuncio(hub)
        hub._ir_para_config(hub.empresa_view)
        self.app.processEvents()
        self.assertNotEqual(hub.stack.currentIndex(), PAGINA_INICIO)

        with mock.patch.object(anuncio_dialog.AnuncioDialog, "exec", return_value=0) as abriu:
            hub._talvez_anunciar()

        self.assertFalse(abriu.called, "pop-up por cima de quem trabalha, nunca")
        self.assertEqual(comunicados.vistos(self.settings), [],
                         "nao mostrou: entao nao pode contar como visto")

    def test_quero_ver_abre_o_link_do_anuncio(self) -> None:
        hub = self.montar()
        self._com_anuncio(hub, link="https://loja.teste/comprar/novidades")
        abertos: list[str] = []
        hub.abrir_anuncio = abertos.append
        with mock.patch.object(anuncio_dialog.AnuncioDialog, "exec",
                               return_value=QDialog.DialogCode.Accepted):
            hub._talvez_anunciar()
        self.assertEqual(abertos, ["https://loja.teste/comprar/novidades"])

    def test_anuncio_sem_link_leva_para_a_loja(self) -> None:
        hub = self.montar()
        self._com_anuncio(hub)
        chamou: list[bool] = []
        hub.abrir_loja = lambda: chamou.append(True)
        with mock.patch.object(anuncio_dialog.AnuncioDialog, "exec",
                               return_value=QDialog.DialogCode.Accepted):
            hub._talvez_anunciar()
        self.assertEqual(chamou, [True])

    def test_anuncio_para_a_nossa_loja_leva_o_codigo_do_cliente(self) -> None:
        """O anuncio manda para a loja - e a loja tem que saber quem chegou."""
        hub = self.montar()
        hub.loja = mock.Mock(link_do_anuncio=mock.Mock(
            return_value="https://loja.teste/comprar/novidades?t=ABC"))
        abertos: list[str] = []
        hub._abrir_endereco = abertos.append

        hub.home_view.abrir_link.emit("https://loja.teste/comprar/novidades")
        esperar_tarefas(self.app)

        self.assertEqual(abertos, ["https://loja.teste/comprar/novidades?t=ABC"])
        self.assertEqual(hub.loja.link_do_anuncio.call_args[0][0],
                         "https://loja.teste/comprar/novidades")

    def test_anuncio_para_fora_abre_sem_pedir_codigo(self) -> None:
        """Codigo do cliente nunca sai para o site de outra pessoa."""
        hub = self.montar()
        hub.loja = mock.Mock()
        abertos: list[str] = []
        hub._abrir_endereco = abertos.append

        hub.home_view.abrir_link.emit("https://outrolugar.example/promo")
        esperar_tarefas(self.app)

        self.assertEqual(abertos, ["https://outrolugar.example/promo"])
        self.assertFalse(hub.loja.link_do_anuncio.called, "nem chegou a pedir codigo")

    def test_anuncio_abre_mesmo_sem_internet(self) -> None:
        hub = self.montar()
        hub.loja = mock.Mock(link_do_anuncio=mock.Mock(side_effect=RuntimeError("sem rede")))
        abertos: list[str] = []
        hub._abrir_endereco = abertos.append

        hub.abrir_anuncio("https://loja.teste/comprar/novidades")
        esperar_tarefas(self.app)

        self.assertEqual(abertos, ["https://loja.teste/comprar/novidades"],
                         "sem codigo o anuncio abre igual - so nao reconhece")

    def test_adquirir_abre_a_loja_com_o_link_do_servidor(self) -> None:
        hub = self.montar()
        abertos: list[str] = []
        hub._abrir_endereco = abertos.append

        hub.home_view.adquirir.emit()
        esperar_tarefas(self.app)

        self.assertEqual(abertos, ["https://loja.teste/comprar?t=ABC"])
        self.assertTrue(hub.loja.link.called)

    def test_loja_abre_mesmo_quando_o_servidor_falha(self) -> None:
        hub = self.montar()
        hub.loja = mock.Mock(link=mock.Mock(side_effect=RuntimeError("sem rede")))
        abertos: list[str] = []
        hub._abrir_endereco = abertos.append

        hub.abrir_loja()
        esperar_tarefas(self.app)

        self.assertEqual(len(abertos), 1)
        self.assertIn("origem=hub", abertos[0])

    def test_voltar_da_loja_traz_o_modulo_comprado(self) -> None:
        """Comprou no site e voltou: o modulo aparece sem clicar em nada."""
        self.license_service.activate(CHAVE)
        hub = self.montar()
        self.assertEqual([e.app_id for e in hub.registry.available()], ["estoque"])

        # a DumTech aprovou o pedido e liberou o Financeiro naquela licenca
        self.license_service.gateway.apps = ("estoque", "financeiro")
        hub._conferir_apos_a_loja()
        esperar_tarefas(self.app)

        self.assertIn("financeiro", [e.app_id for e in hub.registry.available()],
                      "o modulo comprado precisa aparecer sozinho na volta")

    def test_sem_licenca_a_volta_da_loja_nao_consulta_nada(self) -> None:
        hub = self.montar()
        hub.loja.link.reset_mock()
        hub._conferir_apos_a_loja()
        esperar_tarefas(self.app)
        self.assertFalse(self.license_service.ativada)

    def test_abrir_a_loja_marca_a_viagem(self) -> None:
        hub = self.montar()
        self.assertFalse(getattr(hub, "_volta_da_loja", False))
        hub.abrir_loja()
        esperar_tarefas(self.app)
        self.assertTrue(hub._volta_da_loja,
                        "o Hub precisa lembrar que a pessoa saiu para comprar")

    def test_a_tela_licenca_mostra_a_conta(self) -> None:
        Conta(concluido=True, email="joao@exemplo.com").salvar(self.settings)
        hub = self.montar()
        hub.license_view.refresh()

        textos = [w.text() for w in hub.license_view.findChildren(QLabel)]
        self.assertIn("joao@exemplo.com", textos)


if __name__ == "__main__":
    unittest.main()
