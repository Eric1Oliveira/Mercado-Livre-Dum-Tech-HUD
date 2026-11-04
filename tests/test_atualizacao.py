"""Atualizar o Hub pelo proprio Hub: baixar, conferir e instalar.

Este e o caminho mais perigoso do programa - ele baixa um executavel e manda o
Windows roda-lo. Os testes aqui existem para provar que **nada** passa sem:

* assinatura da DumTech no manifesto (versao + endereco + sha256);
* endereco no dominio da loja, por https;
* impressao digital batendo, antes de baixar virar instalacao.

O download e testado de verdade, contra um servidor levantado aqui.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import unittest
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from PySide6.QtWidgets import QApplication

from dumtech.core import atualizacao as nucleo
from dumtech.core.atualizacao import (
    Atualizacao,
    AtualizacaoError,
    AtualizacaoService,
    DIAS_EM_SILENCIO,
    abrir_manifesto,
    disponivel,
    em_silencio,
    para_avisar,
)
from dumtech.core.config import Settings
from dumtech.core.paths import DataPaths
from dumtech.core.supabase import SemConexao
from dumtech.core.versao import dispensar

from .assinante import licenca_de_teste, pacote_atualizacao

_app: QApplication | None = None

INSTALADOR = b"MZ" + b"instalador de mentira" * 500


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


class Servidor:
    """Serve um "instalador" em 127.0.0.1 - com defeito, quando pedido."""

    def __init__(self, corpo: bytes = INSTALADOR) -> None:
        self.corpo = corpo

        class Entregador(BaseHTTPRequestHandler):
            def do_GET(interno) -> None:  # noqa: N802
                interno.send_response(200)
                interno.send_header("Content-Length", str(len(self.corpo)))
                interno.end_headers()
                interno.wfile.write(self.corpo)

            def log_message(interno, *args) -> None:
                pass

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Entregador)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.servidor.server_port}/DumTech-Hub-Setup.exe"

    def parar(self) -> None:
        self.servidor.shutdown()


class Cliente:
    def __init__(self, resposta=None, excecao: Exception | None = None) -> None:
        self.resposta = resposta
        self.excecao = excecao
        self.chamadas: list[tuple[str, dict]] = []

    def funcao(self, nome: str, corpo: dict):
        self.chamadas.append((nome, corpo))
        if self.excecao is not None:
            raise self.excecao
        return self.resposta


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(licenca_de_teste())
        self.enterContext(mock.patch.dict(
            os.environ, {"DUMTECH_URL_LOJA": "https://dumtechsolution.com"}))
        self.raiz = Path(tempfile.mkdtemp(prefix="dumtech_atu_"))
        self.paths = DataPaths(root=self.raiz).ensure()
        self.settings = Settings(self.raiz / "hub.json")

    def servico(self, cliente: Cliente | None = None, instalada: str = "1.2.1") -> AtualizacaoService:
        self.cliente = cliente or Cliente()
        return AtualizacaoService(self.settings, instalada, self.cliente, self.paths)


# =========================================================== o manifesto ====
class ManifestoTestCase(Base):
    URL = "https://dumtechsolution.com/baixar/DumTech-Hub-Setup.exe"

    def test_manifesto_assinado_e_aceito(self) -> None:
        aviso = abrir_manifesto(pacote_atualizacao("1.3.0", self.URL, sha(INSTALADOR),
                                                  notas="Novidades", tamanho=12345))
        self.assertEqual(aviso.versao, "1.3.0")
        self.assertEqual(aviso.sha256, sha(INSTALADOR))
        self.assertTrue(aviso.automatica)
        self.assertEqual(aviso.tamanho_texto, "0,0 MB")

    def test_sem_assinatura_nao_existe_atualizacao(self) -> None:
        for pacote in (None, {}, {"versao": "9.9.9", "url": self.URL}, "texto"):
            self.assertIsNone(abrir_manifesto(pacote), pacote)

    def test_conteudo_mexido_depois_de_assinado_nao_passa(self) -> None:
        import base64

        from .assinante import b64

        pacote = pacote_atualizacao("1.3.0", self.URL, sha(INSTALADOR))
        conteudo = json.loads(base64.urlsafe_b64decode(pacote["licenca"] + "=="))
        conteudo["url"] = "https://golpe.example/instalador.exe"
        pacote["licenca"] = b64(json.dumps(conteudo).encode())
        self.assertIsNone(abrir_manifesto(pacote))

    def test_endereco_de_fora_nao_vira_atualizacao(self) -> None:
        self.assertIsNone(abrir_manifesto(
            pacote_atualizacao("1.3.0", "https://golpe.example/x.exe", sha(INSTALADOR))))
        self.assertIsNone(abrir_manifesto(
            pacote_atualizacao("1.3.0", "https://dumtechsolution.com.golpe.com/x.exe",
                               sha(INSTALADOR))))

    def test_licenca_assinada_nao_vira_atualizacao(self) -> None:
        """Documento assinado para outro uso nao serve aqui (e vice-versa)."""
        self.assertIsNone(abrir_manifesto(
            pacote_atualizacao("1.3.0", self.URL, sha(INSTALADOR), uso="licenca")))

    def test_sem_impressao_digital_so_avisa(self) -> None:
        aviso = abrir_manifesto(pacote_atualizacao("1.3.0", self.URL, ""))
        self.assertIsNotNone(aviso)
        self.assertFalse(aviso.automatica, "sem sha256 o botao de instalar nao aparece")
        self.assertEqual(aviso.sha256, "")

    def test_sha256_estranho_desliga_a_instalacao(self) -> None:
        for ruim in ("abc", "z" * 64, sha(INSTALADOR).upper() + "00"):
            aviso = abrir_manifesto(pacote_atualizacao("1.3.0", self.URL, ruim))
            self.assertFalse(aviso.automatica, ruim)


# ===================================================== o que a tela mostra ==
class AvisoTestCase(Base):
    URL = "https://dumtechsolution.com/baixar/DumTech-Hub-Setup.exe"

    def guardar(self, versao: str, **extras) -> None:
        self.settings.set("versao", "assinado",
                          pacote_atualizacao(versao, self.URL, sha(INSTALADOR), **extras))
        self.settings.save()

    def test_versao_nova_aparece(self) -> None:
        self.guardar("1.3.0")
        self.assertEqual(disponivel(self.settings, "1.2.1").versao, "1.3.0")

    def test_versao_igual_ou_mais_velha_nao_aparece(self) -> None:
        for versao in ("1.2.1", "1.2.0", "0.9"):
            self.guardar(versao)
            self.assertIsNone(disponivel(self.settings, "1.2.1"), versao)

    def test_agora_nao_cala_ate_a_proxima(self) -> None:
        self.guardar("1.3.0")
        dispensar(self.settings, "1.3.0")
        self.assertIsNone(para_avisar(self.settings, "1.2.1"))
        self.assertIsNotNone(disponivel(self.settings, "1.2.1"),
                             "dispensar esconde o aviso, nao a atualizacao")

        self.guardar("1.4.0")
        self.assertIsNotNone(para_avisar(self.settings, "1.2.1"))

    def test_obrigatoria_nao_se_cala(self) -> None:
        self.guardar("1.3.0", obrigatoria=True)
        dispensar(self.settings, "1.3.0")
        self.assertIsNotNone(para_avisar(self.settings, "1.2.1"))


# ================================================== a versao silenciosa ====
class SilenciosaTestCase(Base):
    URL = "https://dumtechsolution.com/baixar/DumTech-Hub-Setup.exe"

    def setUp(self) -> None:
        super().setUp()
        # so o programa instalado se instala sozinho: aqui, finge que e ele
        self.enterContext(mock.patch.object(nucleo, "pode_atualizar_aqui", return_value=True))

    def guardar(self, versao: str = "1.3.0", **extras):
        return self.servico().guardar({"ok": True, "assinado": pacote_atualizacao(
            versao, self.URL, sha(INSTALADOR), **extras)})

    def test_so_e_silenciosa_quando_o_hub_consegue_instalar(self) -> None:
        self.assertTrue(abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.URL, sha(INSTALADOR), silenciosa=True)).silenciosa)
        self.assertFalse(abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.URL, "", silenciosa=True)).silenciosa,
            "sem sha256 o Hub nao instala: o cliente tem de ser avisado")
        self.assertFalse(abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.URL, sha(INSTALADOR))).silenciosa)

    def test_nao_aparece_na_tela_mas_continua_disponivel(self) -> None:
        self.guardar(silenciosa=True)
        self.assertIsNone(para_avisar(self.settings, "1.2.1"))
        self.assertIsNotNone(disponivel(self.settings, "1.2.1"))

    def test_quem_nunca_fecha_o_hub_ve_o_aviso_depois_do_prazo(self) -> None:
        self.guardar(silenciosa=True)
        aviso = disponivel(self.settings, "1.2.1")
        hoje = date.today()
        self.assertTrue(em_silencio(self.settings, aviso, hoje + timedelta(DIAS_EM_SILENCIO - 1)))
        self.assertFalse(em_silencio(self.settings, aviso, hoje + timedelta(DIAS_EM_SILENCIO)))

    def test_o_prazo_conta_de_quando_a_versao_chegou(self) -> None:
        self.guardar(silenciosa=True)
        primeira = self.settings.get("versao", "silenciosa")
        self.settings.set("versao", "silenciosa", {**primeira, "desde": "2020-01-01"})
        self.guardar(silenciosa=True)            # a mesma versao, 2 minutos depois
        self.assertEqual(self.settings.get("versao", "silenciosa")["desde"], "2020-01-01")

        self.guardar("1.4.0", silenciosa=True)   # versao nova, prazo novo
        self.assertEqual(self.settings.get("versao", "silenciosa"),
                         {"versao": "1.4.0", "desde": date.today().isoformat()})

    def test_em_desenvolvimento_avisa_como_sempre(self) -> None:
        self.guardar(silenciosa=True)
        with mock.patch.object(nucleo, "pode_atualizar_aqui", return_value=False):
            self.assertIsNotNone(para_avisar(self.settings, "1.2.1"))


# ============================================================== o servico ===
class ServicoTestCase(Base):
    URL = "https://dumtechsolution.com/baixar/DumTech-Hub-Setup.exe"

    def test_pergunta_ao_servidor_dizendo_a_versao_instalada(self) -> None:
        servico = self.servico(Cliente({"ok": True, "versao": "1.3.0"}))
        servico.buscar("CHAVE", "MAQ")
        nome, corpo = self.cliente.chamadas[0]
        self.assertEqual(nome, "versao")
        self.assertEqual(corpo["versao"], "1.2.1")

    def test_so_guarda_manifesto_assinado(self) -> None:
        servico = self.servico()
        self.assertIsNone(servico.guardar({"ok": True, "versao": "9.9.9", "url": self.URL}))
        self.assertIsNone(self.settings.get("versao", "assinado"))

        guardado = servico.guardar({"ok": True, "assinado": pacote_atualizacao(
            "1.3.0", self.URL, sha(INSTALADOR))})
        self.assertEqual(guardado.versao, "1.3.0")

    def test_sem_internet_e_silencio(self) -> None:
        servico = self.servico(Cliente(excecao=SemConexao("x")))
        self.assertIsNone(servico.buscar("CHAVE", "MAQ"))
        self.assertIsNone(servico.guardar(None))


# ============================================================ o download ====
class DownloadTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        self.servidor = Servidor()
        self.addCleanup(self.servidor.parar)

    def aviso(self, corpo: bytes = INSTALADOR, **extras) -> Atualizacao:
        return abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.servidor.url, sha(corpo), tamanho=len(corpo), **extras))

    def test_baixa_confere_e_guarda_na_pasta_do_programa(self) -> None:
        servico = self.servico()
        andou: list[tuple[int, int]] = []

        caminho = servico.baixar(self.aviso(), progresso=lambda b, t: andou.append((b, t)))

        self.assertTrue(caminho.is_file())
        self.assertEqual(caminho.read_bytes(), INSTALADOR)
        self.assertEqual(caminho.parent, self.raiz / "atualizacoes")
        self.assertTrue(andou, "a barra de progresso precisa de numeros")
        self.assertEqual(andou[-1][0], len(INSTALADOR))

    def test_arquivo_diferente_do_assinado_nao_vira_instalador(self) -> None:
        """O servidor entrega outra coisa: nada e gravado, nada e executado."""
        servico = self.servico()
        aviso = self.aviso()
        self.servidor.corpo = b"MZ" + b"virus" * 100   # trocaram o arquivo

        with self.assertRaises(AtualizacaoError) as erro:
            servico.baixar(aviso)

        self.assertEqual(erro.exception.codigo, "impressao_digital")
        self.assertEqual(list((self.raiz / "atualizacoes").glob("*")), [],
                         "nem o arquivo pela metade pode ficar para tras")

    def test_download_interrompido_nao_deixa_lixo(self) -> None:
        servico = self.servico()
        with self.assertRaises(AtualizacaoError) as erro:
            servico.baixar(self.aviso(), parar=lambda: True)
        self.assertEqual(erro.exception.codigo, "cancelado")
        self.assertEqual(list((self.raiz / "atualizacoes").glob("*")), [])

    def test_baixar_de_novo_reaproveita_o_arquivo_intacto(self) -> None:
        servico = self.servico()
        primeiro = servico.baixar(self.aviso())
        antes = primeiro.stat().st_mtime_ns
        segundo = servico.baixar(self.aviso())
        self.assertEqual(primeiro, segundo)
        self.assertEqual(segundo.stat().st_mtime_ns, antes, "nao baixou de novo a toa")

    def test_sem_impressao_digital_nao_baixa(self) -> None:
        servico = self.servico()
        aviso = abrir_manifesto(pacote_atualizacao("1.3.0", self.servidor.url, ""))
        with self.assertRaises(AtualizacaoError) as erro:
            servico.baixar(aviso)
        self.assertEqual(erro.exception.codigo, "sem_assinatura")


# ============================================================= instalar =====
class InstalarTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        self.servidor = Servidor()
        self.addCleanup(self.servidor.parar)
        self.servico_ = self.servico()
        self.aviso = abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.servidor.url, sha(INSTALADOR), tamanho=len(INSTALADOR)))
        self.caminho = self.servico_.baixar(self.aviso)

    def test_chama_o_instalador_em_silencio_e_pedindo_para_reabrir(self) -> None:
        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            self.servico_.instalar(self.caminho, self.aviso)

        argumentos = popen.call_args[0][0]
        self.assertEqual(argumentos[0], str(self.caminho))
        self.assertIn("/VERYSILENT", argumentos)
        self.assertIn("/reabrir=1", argumentos)
        self.assertIn("/NORESTART", argumentos)

    def test_silenciosa_instala_sem_reabrir_o_hub(self) -> None:
        """A pessoa fechou o Hub porque quis: ele nao reaparece sozinho."""
        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            self.servico_.instalar(self.caminho, self.aviso, reabrir=False)

        argumentos = popen.call_args[0][0]
        self.assertIn("/VERYSILENT", argumentos)
        self.assertNotIn("/reabrir=1", argumentos)

    def test_arquivo_trocado_depois_do_download_nao_executa(self) -> None:
        """A janela entre baixar e abrir tambem e conferida."""
        self.caminho.write_bytes(b"MZ" + b"outro programa" * 50)

        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            with self.assertRaises(AtualizacaoError) as erro:
                self.servico_.instalar(self.caminho, self.aviso)

        self.assertEqual(erro.exception.codigo, "impressao_digital")
        self.assertFalse(popen.called, "nada pode ser executado")
        self.assertFalse(self.caminho.exists(), "o arquivo suspeito e apagado")

    def test_instalador_de_fora_da_pasta_nao_executa(self) -> None:
        estranho = self.raiz / "DumTech-Hub-Setup.exe"
        estranho.write_bytes(INSTALADOR)
        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            with self.assertRaises(AtualizacaoError) as erro:
                self.servico_.instalar(estranho, self.aviso)
        self.assertEqual(erro.exception.codigo, "lugar")
        self.assertFalse(popen.called)

    def test_limpar_tira_os_instaladores_velhos(self) -> None:
        velho = self.caminho.parent / "DumTech-Hub-Setup-1.0.0.exe"
        velho.write_bytes(b"velho")
        self.servico_.limpar(manter=self.caminho.name)
        self.assertFalse(velho.exists())
        self.assertTrue(self.caminho.exists())


# ================================================================ a tela ====
class JanelaTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        self.servidor = Servidor()
        self.addCleanup(self.servidor.parar)
        self.servico_ = self.servico()
        self.aviso = abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.servidor.url, sha(INSTALADOR), notas="Pagamentos protegidos",
            tamanho=len(INSTALADOR)))

    def janela(self, aviso=None):
        from dumtech.hub.views.atualizacao_dialog import AtualizacaoDialog

        dialogo = AtualizacaoDialog(aviso or self.aviso, "1.2.1", self.servico_)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def _textos(self, dialogo) -> list[str]:
        from PySide6.QtWidgets import QLabel

        return [w.text() for w in dialogo.findChildren(QLabel)]

    def test_diz_as_duas_versoes_e_o_que_mudou(self) -> None:
        dialogo = self.janela()
        textos = " | ".join(self._textos(dialogo))
        self.assertIn("1.2.1", textos)
        self.assertIn("1.3.0", textos)
        self.assertIn("Pagamentos protegidos", textos)

    def test_fora_do_programa_instalado_manda_para_o_site(self) -> None:
        """Rodando pelo codigo nao ha o que instalar: a acao principal e o site."""
        dialogo = self.janela()
        self.assertIn("site", dialogo.botao_instalar.text().lower())
        self.assertIn("site", dialogo.explica.text())

    def test_no_programa_instalado_o_botao_aparece(self) -> None:
        with mock.patch.object(nucleo, "pode_atualizar_aqui", return_value=True):
            dialogo = self.janela()
        self.assertTrue(dialogo.botao_instalar.isVisibleTo(dialogo))
        self.assertIn("instalar", dialogo.botao_instalar.text().lower())
        self.assertIn("sozinho", dialogo.explica.text())

    def test_no_maximo_dois_botoes(self) -> None:
        """Tres botoes numa janela de 480 px cortavam o texto do do meio."""
        from PySide6.QtWidgets import QPushButton

        with mock.patch.object(nucleo, "pode_atualizar_aqui", return_value=True):
            dialogo = self.janela()
        botoes = [b for b in dialogo.findChildren(QPushButton) if b.isVisibleTo(dialogo)]
        self.assertLessEqual(len(botoes), 2)

    def test_o_site_so_aparece_depois_de_um_erro(self) -> None:
        with mock.patch.object(nucleo, "pode_atualizar_aqui", return_value=True):
            dialogo = self.janela()
        self.assertFalse(dialogo.link_site.isVisibleTo(dialogo))
        dialogo._falhou(AtualizacaoError("O arquivo baixado nao e o oficial.", "impressao_digital"))
        self.assertTrue(dialogo.link_site.isVisibleTo(dialogo))
        self.assertIn("de novo", dialogo.botao_instalar.text())

    def test_baixar_e_instalar_avisa_quem_precisa_fechar_o_hub(self) -> None:
        with mock.patch.object(nucleo, "pode_atualizar_aqui", return_value=True):
            dialogo = self.janela()
        avisou: list[bool] = []
        dialogo.instalando.connect(lambda: avisou.append(True))

        from PySide6.QtTest import QTest

        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            dialogo._baixar()
            for _ in range(200):
                if avisou:
                    break
                QTest.qWait(20)

        self.assertTrue(avisou, "a janela precisa avisar para o Hub fechar")
        self.assertTrue(popen.called)

    def test_atualizacao_obrigatoria_nao_oferece_dispensar(self) -> None:
        aviso = abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.servidor.url, sha(INSTALADOR), obrigatoria=True))
        dialogo = self.janela(aviso)
        self.assertIn("Fechar", dialogo.botao_depois.text())
        self.assertIn("importante", " | ".join(self._textos(dialogo)).lower())


class RelogioNoHubTestCase(Base):
    """O aviso de versao nao pode esperar a conferencia da licenca (1 h)."""

    def hub(self):
        from dumtech.core.config import Settings
        from dumtech.hub.main_window import HubWindow

        settings = Settings(self.raiz / "hub-janela.json")
        janela = HubWindow(settings=settings)
        janela.launcher.notify = lambda *args: None
        self.addCleanup(janela.deleteLater)
        self.addCleanup(janela.close)
        return janela

    def test_a_versao_tem_relogio_proprio_e_curto(self) -> None:
        from dumtech.hub.main_window import HubWindow

        self.assertLessEqual(HubWindow.VERSAO_INTERVALO_MS, 5 * 60 * 1000,
                             "esperar mais que isso nao e aviso, e arqueologia")
        self.assertLess(HubWindow.VERSAO_INTERVALO_MS, HubWindow.REDE_INTERVALO_MS)

    def test_conferir_versao_pergunta_ao_servidor(self) -> None:
        hub = self.hub()
        hub.atualizacao_service = mock.Mock(
            buscar=mock.Mock(return_value=None), guardar=mock.Mock(return_value=None))
        with mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "0"}):
            hub.conferir_versao(True)
            from .test_porta_entrada import esperar_tarefas

            esperar_tarefas(_app)
        self.assertTrue(hub.atualizacao_service.buscar.called)

    def test_nao_repete_a_toa(self) -> None:
        """Voltar para a janela varias vezes nao vira enxurrada de pedidos."""
        hub = self.hub()
        hub.atualizacao_service = mock.Mock(
            buscar=mock.Mock(return_value=None), guardar=mock.Mock(return_value=None))
        with mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "0"}):
            hub.conferir_versao(True)
            for _ in range(5):
                hub.conferir_versao()
            from .test_porta_entrada import esperar_tarefas

            esperar_tarefas(_app)
        self.assertEqual(hub.atualizacao_service.buscar.call_count, 1)

    def test_em_desenvolvimento_nao_pergunta(self) -> None:
        hub = self.hub()
        hub.atualizacao_service = mock.Mock(buscar=mock.Mock(return_value=None))
        hub.conferir_versao(True)          # DUMTECH_LICENCA_LOCAL=1 nos testes
        self.assertFalse(hub.atualizacao_service.buscar.called)


class SilenciosaNoHubTestCase(Base):
    """Versao silenciosa: nada na tela, baixa sozinha e instala ao fechar."""

    def setUp(self) -> None:
        super().setUp()
        self.servidor = Servidor()
        self.addCleanup(self.servidor.parar)
        self.enterContext(mock.patch.object(nucleo, "pode_atualizar_aqui", return_value=True))

    def hub(self, **extras):
        from dumtech.hub.main_window import HubWindow

        from .test_porta_entrada import esperar_tarefas

        settings = Settings(self.raiz / "hub-janela.json")
        settings.set("versao", "assinado", pacote_atualizacao(
            "9.9.0", self.servidor.url, sha(INSTALADOR), tamanho=len(INSTALADOR), **extras))
        janela = HubWindow(settings=settings)
        janela.launcher.notify = lambda *args: None
        janela.atualizacao_service.paths = self.paths
        self.addCleanup(janela.deleteLater)
        janela._atualizar_botao_versao()
        esperar_tarefas(_app)
        return janela

    def test_nao_mostra_nada_e_instala_ao_fechar_sem_reabrir(self) -> None:
        hub = self.hub(silenciosa=True)
        self.assertTrue(hub.botao_atualizar.isHidden(), "versao silenciosa nao chama ninguem")
        self.assertIsNotNone(hub._silenciosa, "o instalador ja devia estar baixado")

        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            hub.close()

        argumentos = popen.call_args[0][0]
        self.assertEqual(argumentos[0], str(hub._silenciosa[0]))
        self.assertNotIn("/reabrir=1", argumentos)

    def test_deixar_de_ser_silenciosa_aparece_e_ainda_instala_ao_fechar(self) -> None:
        """Hub 1.5.1 a 1.9.0 forcado: e o que o servidor faz depois dos primeiros minutos."""
        hub = self.hub(silenciosa=True, obrigatoria=True)
        self.assertTrue(hub.botao_atualizar.isHidden())

        hub.settings.set("versao", "assinado", pacote_atualizacao(
            "9.9.0", self.servidor.url, sha(INSTALADOR), tamanho=len(INSTALADOR), obrigatoria=True))
        hub._atualizar_botao_versao()
        self.assertFalse(hub.botao_atualizar.isHidden(), "o aviso tem que aparecer")
        self.assertIsNotNone(nucleo.para_avisar(hub.settings, "1.0.0"), "e nao se dispensa")

        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            hub.close()
        self.assertNotIn("/reabrir=1", popen.call_args[0][0], "o que ja baixou instala ao fechar")

    def test_com_o_windows_desligando_nao_instala(self) -> None:
        hub = self.hub(silenciosa=True)
        hub._windows_desligando(None)
        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            hub.close()
        self.assertFalse(popen.called, "instalador cortado no meio estraga o programa")

    def test_versao_normal_continua_com_o_botao(self) -> None:
        hub = self.hub()
        self.assertFalse(hub.botao_atualizar.isHidden())
        self.assertIsNone(hub._silenciosa)
        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            hub.close()
        self.assertFalse(popen.called, "versao normal so instala com o clique")


class ForcadaTestCase(Base):
    """O painel mandou instalar: conferencias iguais, sem esperar o clique."""

    URL = "https://dumtechsolution.com/baixar/DumTech-Hub-Setup.exe"

    def test_vem_do_manifesto_assinado(self) -> None:
        aviso = nucleo.abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.URL, sha(INSTALADOR), forcada=True))
        self.assertTrue(aviso.forcada)
        self.assertFalse(nucleo.abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.URL, sha(INSTALADOR))).forcada, "so forca quem manda forcar")

    def test_sem_impressao_digital_nao_forca_nada(self) -> None:
        self.assertFalse(nucleo.abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.URL, "", forcada=True)).forcada)

    def test_endereco_de_fora_nao_passa_nem_forcado(self) -> None:
        self.assertIsNone(nucleo.abrir_manifesto(pacote_atualizacao(
            "1.3.0", "https://golpe.example/hub.exe", sha(INSTALADOR), forcada=True)))

    def test_forcada_nunca_e_silenciosa(self) -> None:
        aviso = nucleo.abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.URL, sha(INSTALADOR), forcada=True, silenciosa=True))
        with mock.patch.object(nucleo, "pode_atualizar_aqui", return_value=True):
            self.assertFalse(nucleo.em_silencio(self.settings, aviso))
            self.assertTrue(nucleo.forcada_aqui(aviso))

    def test_rodando_do_codigo_nao_tenta_instalar(self) -> None:
        aviso = nucleo.abrir_manifesto(pacote_atualizacao(
            "1.3.0", self.URL, sha(INSTALADOR), forcada=True))
        with mock.patch.object(nucleo, "pode_atualizar_aqui", return_value=False):
            self.assertFalse(nucleo.forcada_aqui(aviso))


class ForcadaNoHubTestCase(Base):
    """Baixa sozinha, conta o prazo por cima de tudo, instala e reabre."""

    def setUp(self) -> None:
        super().setUp()
        self.servidor = Servidor()
        self.addCleanup(self.servidor.parar)
        self.enterContext(mock.patch.object(nucleo, "pode_atualizar_aqui", return_value=True))

    def hub(self, **extras):
        from dumtech.hub.main_window import HubWindow

        from .test_porta_entrada import esperar_tarefas

        settings = Settings(self.raiz / "hub-janela.json")
        settings.set("versao", "assinado", pacote_atualizacao(
            "9.9.0", self.servidor.url, sha(INSTALADOR), tamanho=len(INSTALADOR),
            obrigatoria=True, silenciosa=True, forcada=True, **extras))
        janela = HubWindow(settings=settings)
        janela.launcher.notify = lambda *args: None
        janela.atualizacao_service.paths = self.paths
        self.addCleanup(janela.deleteLater)
        self.addCleanup(self._fechar, janela)
        janela._atualizar_botao_versao()
        esperar_tarefas(_app)
        return janela

    @staticmethod
    def _fechar(janela) -> None:
        """Fechar tira a janela dos eventos; sem isto, o proximo teste esbarra nela morta."""
        janela._silenciosa = None       # e nao roda o instalador de mentira ao sair
        janela.close()

    def test_baixa_avisa_e_mostra_o_prazo(self) -> None:
        hub = self.hub()
        self.assertIsNotNone(hub._silenciosa, "o instalador ja devia estar baixado")
        aviso = hub._aviso_forcada
        self.assertIsNotNone(aviso, "a contagem devia ter comecado")
        self.assertTrue(aviso.isVisible())
        self.assertEqual(aviso.restam, nucleo.PRAZO_FORCADA_S)
        self.assertIn("5:00", aviso.contagem.text())
        self.assertFalse(hub.botao_atualizar.isHidden(), "o caminho para atualizar fica a vista")

    def test_conferir_de_novo_nao_reinicia_o_prazo(self) -> None:
        hub = self.hub()
        aviso = hub._aviso_forcada
        aviso.restam = 37
        hub._atualizar_botao_versao()
        self.assertIs(hub._aviso_forcada, aviso)
        self.assertEqual(aviso.restam, 37)

    def test_o_aviso_nao_se_fecha(self) -> None:
        hub = self.hub()
        hub._aviso_forcada.close()
        self.assertTrue(hub._aviso_forcada.isVisible())

    def test_o_prazo_acaba_instala_e_reabre(self) -> None:
        hub = self.hub()
        aviso = hub._aviso_forcada
        aviso.restam = 1
        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            aviso._passo()
        argumentos = popen.call_args[0][0]
        self.assertEqual(argumentos[0], str(hub._silenciosa[0]))
        self.assertIn("/reabrir=1", argumentos)
        self.assertTrue(hub._atualizando)
        self.assertIsNone(hub._aviso_forcada)

    def test_instalar_agora_nao_espera_o_prazo(self) -> None:
        hub = self.hub()
        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            hub._aviso_forcada.botao_instalar.click()
        self.assertTrue(popen.called)

    def test_janela_aberta_nao_segura_o_programa(self) -> None:
        from PySide6.QtWidgets import QDialog

        hub = self.hub()
        dialogo = QDialog(hub)
        dialogo.show()
        with mock.patch.object(nucleo.subprocess, "Popen"):
            hub._aviso_forcada.botao_instalar.click()
        self.assertFalse(dialogo.isVisible(), "dialogo aberto deixaria o Hub no ar")

    def test_windows_recusar_nao_derruba_o_hub(self) -> None:
        hub = self.hub()
        with mock.patch.object(nucleo.subprocess, "Popen", side_effect=OSError("negado")):
            hub._aviso_forcada.botao_instalar.click()
        self.assertFalse(getattr(hub, "_atualizando", False), "o Hub tem que continuar aberto")
        self.assertIsNone(hub._aviso_forcada)
        self.assertIsNone(hub._silenciosa, "a proxima conferencia baixa de novo")

    def _ordem_nova(self, hub, versao="9.9.0", **extras) -> None:
        """A proxima conferencia de versao trouxe outro manifesto."""
        hub.settings.set("versao", "assinado", pacote_atualizacao(
            versao, self.servidor.url, sha(INSTALADOR), tamanho=len(INSTALADOR), **extras))
        hub._atualizar_botao_versao()

    def test_recolher_no_meio_do_prazo_para_a_instalacao(self) -> None:
        hub = self.hub()
        aviso = hub._aviso_forcada
        self._ordem_nova(hub, "0.0.1")          # voltou para uma versao mais velha
        self.assertIsNone(hub._aviso_forcada, "a contagem tinha que parar")
        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            aviso._acabou()
        self.assertFalse(popen.called, "versao recolhida nao pode instalar")

    def test_a_conferencia_de_rotina_traz_o_recolhimento(self) -> None:
        from .test_porta_entrada import esperar_tarefas

        hub = self.hub()
        pacote = pacote_atualizacao("0.0.1", self.servidor.url, sha(INSTALADOR))
        hub.atualizacao_service.buscar = lambda *_: {"ok": True, "assinado": pacote}
        with mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "0"}):
            hub.conferir_versao(forcar=True)
            esperar_tarefas(_app)
        self.assertIsNone(hub._aviso_forcada, "versao que nao e mais nova tambem tem que parar a contagem")
        self.assertTrue(hub.botao_atualizar.isHidden())

    def test_sem_internet_a_contagem_continua(self) -> None:
        from .test_porta_entrada import esperar_tarefas

        hub = self.hub()
        aviso = hub._aviso_forcada
        hub.atualizacao_service.buscar = mock.Mock(return_value=None)
        with mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "0"}):
            hub.conferir_versao(forcar=True)
            esperar_tarefas(_app)
        self.assertTrue(hub.atualizacao_service.buscar.called)
        self.assertIs(hub._aviso_forcada, aviso)

    def test_cancelar_a_obrigacao_para_a_contagem(self) -> None:
        hub = self.hub()
        self._ordem_nova(hub)                   # a mesma versao, sem forcar
        self.assertIsNone(hub._aviso_forcada)
        self.assertFalse(hub.botao_atualizar.isHidden(), "continua disponivel, sem obrigar")

    def test_fechar_depois_de_recolher_nao_instala(self) -> None:
        hub = self.hub()
        self._ordem_nova(hub, "0.0.1")
        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            hub.close()
        self.assertFalse(popen.called)

    def test_fechar_durante_o_prazo_instala_sem_reabrir(self) -> None:
        hub = self.hub()
        with mock.patch.object(nucleo.subprocess, "Popen") as popen:
            hub.close()
        self.assertNotIn("/reabrir=1", popen.call_args[0][0])
        self.assertIsNone(hub._aviso_forcada)


if __name__ == "__main__":
    unittest.main()
