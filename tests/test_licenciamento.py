"""Testes do licenciamento: ativacao, licenca invalida, app nao comprado e offline.

Nenhum teste acessa a internet: o servidor de licencas e substituido por
gateways falsos controlados pelo proprio teste.
"""

from __future__ import annotations

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
    SemInternet,
    SupabaseLicenseGateway,
    is_valid_key_format,
    machine_id,
    normalize_key,
)
from dumtech.core.supabase import SemConexao, ServicoIndisponivel, SupabaseClient

from .assinante import assinar_licenca, licenca_de_teste

CHAVE = "DEMO-2026-TEST-0001"


def arquivo_licenca() -> Path:
    return Path(tempfile.mkdtemp(prefix="dumtech_lic_")) / "license.json"


def sem_modo_local():
    """Desliga a licenca local de desenvolvimento durante o teste."""
    return mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "0"})


class LicencaBase(unittest.TestCase):
    """Base: modo local desligado e o Hub confiando na chave de teste.

    Os servidores de mentira assinam as licencas (tests/assinante.py): a
    assinatura e obrigatoria, entao os testes passam pelo caminho de verdade.
    """

    def setUp(self) -> None:
        for patch in (sem_modo_local(), licenca_de_teste()):
            patch.__enter__()
            self.addCleanup(patch.__exit__, None, None, None)


class GatewayFalso:
    """Servidor de licencas de mentira, controlado pelo teste."""

    def __init__(
        self,
        apps: tuple[str, ...] = ("estoque",),
        cliente: str = "Joao da Silva",
        erro: Exception | None = None,
        expira_em: str | None = None,
        max_machines: int = 1,
    ) -> None:
        self.apps = apps
        self.cliente = cliente
        self.erro = erro
        self.expira_em = expira_em
        self.max_machines = max_machines
        self.chamadas_fetch = 0
        self.chamadas_verify = 0
        self.liberou: list[tuple[str, str]] = []

    def _licenca(self, key: str, machine: str) -> License:
        if self.erro is not None:
            raise self.erro
        agora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return assinar_licenca(License(
            key=key,
            customer=self.cliente,
            entitlements=tuple(self.apps),
            machine=machine,
            activated_at=agora,
            last_check=agora,
            expires_at=self.expira_em,
            source=ORIGEM_SUPABASE,
            max_machines=self.max_machines,
            used_machines=1,
        ))

    def fetch(self, key: str, machine: str) -> License:
        self.chamadas_fetch += 1
        return self._licenca(key, machine)

    def verify(self, key: str, machine: str) -> License:
        self.chamadas_verify += 1
        return self._licenca(key, machine)

    def release(self, key: str, machine: str) -> None:
        if self.erro is not None:
            raise self.erro
        self.liberou.append((key, machine))


class ChaveTestCase(unittest.TestCase):
    def test_formata_a_chave_digitada(self) -> None:
        self.assertEqual(normalize_key("demo2026test0001"), CHAVE)
        self.assertEqual(normalize_key("demo 2026 test 0001"), CHAVE)
        self.assertEqual(normalize_key("DEMO-2026"), "DEMO-2026")

    def test_valida_o_formato(self) -> None:
        self.assertTrue(is_valid_key_format(CHAVE))
        self.assertFalse(is_valid_key_format("DEMO-2026"))
        self.assertFalse(is_valid_key_format(""))

    def test_identificador_do_computador_e_estavel(self) -> None:
        self.assertEqual(machine_id(), machine_id())
        self.assertTrue(is_valid_key_format(machine_id()))


class AtivacaoTestCase(LicencaBase):
    def setUp(self) -> None:
        super().setUp()
        self.arquivo = arquivo_licenca()
        self.gateway = GatewayFalso(apps=("estoque", "clientes"))
        self.service = LicenseService(self.arquivo, self.gateway)

    # ------------------------------------------------------------ licenca ok --
    def test_ativacao_com_chave_valida(self) -> None:
        with sem_modo_local():
            licenca = self.service.activate("demo2026test0001")

        self.assertEqual(licenca.key, CHAVE)
        self.assertEqual(licenca.customer, "Joao da Silva")
        self.assertEqual(self.gateway.chamadas_fetch, 1)
        self.assertTrue(self.service.ativada)
        self.assertTrue(self.arquivo.exists(), "a licenca precisa ficar gravada no computador")

    def test_ativacao_libera_somente_o_que_foi_comprado(self) -> None:
        with sem_modo_local():
            self.service.activate(CHAVE)
        self.assertTrue(self.service.allows("estoque"))
        self.assertTrue(self.service.allows("clientes"))
        self.assertFalse(self.service.allows("financeiro"))
        self.assertFalse(self.service.allows("vendas"))

    # -------------------------------------------------------- licenca invalida
    def test_chave_incompleta_nem_chega_no_servidor(self) -> None:
        with sem_modo_local(), self.assertRaises(LicenseError) as caso:
            self.service.activate("DEMO-2026")
        self.assertEqual(caso.exception.codigo, "formato")
        self.assertEqual(self.gateway.chamadas_fetch, 0)
        self.assertFalse(self.arquivo.exists())

    def test_chave_inexistente(self) -> None:
        self.gateway.erro = LicenseError("Chave nao encontrada.", "nao_encontrada")
        with sem_modo_local(), self.assertRaises(LicenseError) as caso:
            self.service.activate(CHAVE)
        self.assertEqual(caso.exception.codigo, "nao_encontrada")
        self.assertFalse(self.arquivo.exists())

    def test_licenca_suspensa(self) -> None:
        self.gateway.erro = LicenseError("Esta licenca esta suspensa.", "inativa")
        with sem_modo_local(), self.assertRaises(LicenseError) as caso:
            self.service.activate(CHAVE)
        self.assertEqual(caso.exception.codigo, "inativa")

    def test_limite_de_computadores(self) -> None:
        self.gateway.erro = LicenseError("Limite de computadores atingido.", "limite_maquinas")
        with sem_modo_local(), self.assertRaises(LicenseError) as caso:
            self.service.activate(CHAVE)
        self.assertEqual(caso.exception.codigo, "limite_maquinas")
        self.assertFalse(self.service.ativada)

    def test_sem_internet_na_ativacao(self) -> None:
        self.gateway.erro = SemInternet("Sem conexao com a internet.")
        with sem_modo_local(), self.assertRaises(SemInternet):
            self.service.activate(CHAVE)
        self.assertFalse(self.service.ativada)

    def test_licenca_vencida_nao_libera_nada(self) -> None:
        ontem = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.gateway.expira_em = ontem
        with sem_modo_local():
            licenca = self.service.activate(CHAVE)
        self.assertTrue(licenca.is_expired)
        self.assertFalse(self.service.allows("estoque"))
        self.assertFalse(self.service.ativada)


class OfflineTestCase(LicencaBase):
    """Depois de ativada, a licenca precisa funcionar sem internet."""

    def setUp(self) -> None:
        super().setUp()
        self.arquivo = arquivo_licenca()
        self.gateway = GatewayFalso(apps=("estoque", "vendas"))
        with sem_modo_local():
            LicenseService(self.arquivo, self.gateway).activate(CHAVE)

    def test_continua_liberado_sem_internet(self) -> None:
        offline = GatewayFalso(erro=SemInternet("Sem internet."))
        with sem_modo_local():
            servico = LicenseService(self.arquivo, offline)
            self.assertTrue(servico.ativada)
            self.assertTrue(servico.allows("estoque"))
            self.assertTrue(servico.allows("vendas"))
            self.assertFalse(servico.allows("financeiro"))
        self.assertEqual(offline.chamadas_fetch, 0, "nao pode consultar o servidor no dia a dia")
        self.assertEqual(offline.chamadas_verify, 0)

    def test_verificar_sem_internet_mantem_a_licenca(self) -> None:
        offline = GatewayFalso(erro=SemInternet("Sem internet."))
        with sem_modo_local():
            servico = LicenseService(self.arquivo, offline)
            with self.assertRaises(SemInternet):
                servico.verify()
            self.assertTrue(servico.reload().ativa)
            self.assertTrue(servico.allows("estoque"))

    def test_licenca_de_desenvolvimento_nao_vale_no_cliente(self) -> None:
        """Um license.json de teste (source=local) nao pode liberar nada em producao."""
        from dumtech.core.licensing import LOCAL_KEY, LocalLicenseGateway

        arquivo = arquivo_licenca()
        LicenseService(arquivo, LocalLicenseGateway()).save(
            LocalLicenseGateway().fetch(LOCAL_KEY, machine_id())
        )
        servico = LicenseService(arquivo, GatewayFalso())
        self.assertFalse(servico.ativada)
        self.assertFalse(servico.allows("estoque"))

    def test_arquivo_corrompido_nao_derruba_o_hub(self) -> None:
        self.arquivo.write_text("{isso nao e json", encoding="utf-8")
        with sem_modo_local():
            servico = LicenseService(self.arquivo, GatewayFalso())
            self.assertFalse(servico.ativada)
            self.assertFalse(servico.allows("estoque"))


class VerificacaoTestCase(LicencaBase):
    """Cliente comprou outro aplicativo: 'Verificar licenca' traz o novo."""

    def setUp(self) -> None:
        super().setUp()
        self.arquivo = arquivo_licenca()
        self.gateway = GatewayFalso(apps=("estoque",))
        with sem_modo_local():
            self.service = LicenseService(self.arquivo, self.gateway)
            self.service.activate(CHAVE)

    def test_novo_aplicativo_aparece_apos_verificar(self) -> None:
        self.assertFalse(self.service.allows("financeiro"))
        self.gateway.apps = ("estoque", "financeiro")  # o cliente comprou mais um

        with sem_modo_local():
            licenca = self.service.verify()

        self.assertEqual(self.gateway.chamadas_verify, 1)
        self.assertTrue(self.service.allows("financeiro"))
        self.assertEqual(len(licenca.entitlements), 2)

    def test_verificacao_e_gravada_para_uso_offline(self) -> None:
        self.gateway.apps = ("estoque", "financeiro")
        with sem_modo_local():
            self.service.verify()
            outro = LicenseService(self.arquivo, GatewayFalso(erro=SemInternet("Sem internet.")))
            self.assertTrue(outro.allows("financeiro"))

    def test_verificar_sem_licenca_avisa(self) -> None:
        with sem_modo_local():
            vazio = LicenseService(arquivo_licenca(), self.gateway)
            with self.assertRaises(LicenseError) as caso:
                vazio.verify()
        self.assertEqual(caso.exception.codigo, "sem_licenca")

    def test_remover_licenca_libera_a_vaga(self) -> None:
        with sem_modo_local():
            self.service.deactivate()
        self.assertEqual(self.gateway.liberou, [(CHAVE, machine_id())])
        self.assertFalse(self.arquivo.exists())
        with sem_modo_local():
            self.assertFalse(self.service.reload().ativa)


class ConferenciaTestCase(LicencaBase):
    """O que a DumTech muda no painel chega ao Hub sem ninguem clicar em nada."""

    def setUp(self) -> None:
        super().setUp()
        self.arquivo = arquivo_licenca()
        self.gateway = GatewayFalso(apps=("estoque", "vendas"))
        self.service = LicenseService(self.arquivo, self.gateway)
        self.service.activate(CHAVE)

    def _envelhecer(self, horas: float) -> None:
        antiga = (datetime.now(timezone.utc) - timedelta(hours=horas)).replace(microsecond=0)
        from dataclasses import replace as trocar
        self.service.save(trocar(self.service.current, last_check=antiga.isoformat()))

    def test_so_confere_quando_passou_o_intervalo(self) -> None:
        self.assertFalse(self.service.precisa_conferir(), "acabou de ativar: nao precisa")
        self._envelhecer(7)
        self.assertTrue(self.service.precisa_conferir())

    def test_sem_licenca_ou_licenca_local_nao_confere(self) -> None:
        self.assertFalse(LicenseService(arquivo_licenca(), self.gateway).precisa_conferir())

    def test_modulo_novo_chega_sozinho(self) -> None:
        self.gateway.apps = ("estoque", "vendas", "financeiro")
        licenca = self.service.conferir()
        self.assertTrue(self.service.allows("financeiro"))
        self.assertEqual(licenca.bloqueio, "")

    def test_licenca_suspensa_no_painel_para_de_abrir(self) -> None:
        for codigo in ("inativa", "expirada", "nao_encontrada", "maquina_nao_ativada"):
            with self.subTest(codigo=codigo):
                self.gateway.erro = LicenseError("Esta licenca esta suspensa.", codigo)
                licenca = self.service.conferir()
                self.assertFalse(self.service.allows("estoque"))
                self.assertEqual(licenca.bloqueio, codigo)
                # a chave fica: reativar no painel nao pode exigir digitar de novo
                self.assertEqual(LicenseService(self.arquivo, self.gateway).current.key, CHAVE)

    def test_computador_trocado_pede_para_ativar_de_novo(self) -> None:
        """Reinstalou o Windows (ou copiaram o license.json): a saida e ativar aqui.

        O servidor prende a licenca ao computador na primeira assinatura
        (pentest de 17/09/2026). Sem tratar isto, o cliente ficaria semanas
        vendo "conecte a internet" - e conectar nao resolveria.
        """
        recado = ("Esta licenca ja esta em uso em outro computador. "
                  "Use o botao Ativar licenca neste computador.")
        self.gateway.erro = LicenseError(recado, "outro_computador")
        licenca = self.service.conferir()

        self.assertFalse(self.service.allows("estoque"))
        self.assertEqual(licenca.bloqueio, "outro_computador")
        self.assertIn("Ativar licenca", licenca.extras.get("mensagem", ""),
                      "a tela precisa dizer o que fazer")
        self.assertEqual(LicenseService(self.arquivo, self.gateway).current.key, CHAVE,
                         "a chave fica guardada: ativar de novo nao pode exigir digitar tudo")

    def test_reativada_no_painel_volta_sozinha(self) -> None:
        self.gateway.erro = LicenseError("Esta licenca esta suspensa.", "inativa")
        self.service.conferir()
        self.assertFalse(self.service.allows("vendas"))

        self.gateway.erro = None  # a DumTech reativou
        licenca = self.service.conferir()
        self.assertTrue(self.service.allows("vendas"))
        self.assertEqual(licenca.bloqueio, "")

    def test_sem_internet_ou_servidor_fora_nao_bloqueia(self) -> None:
        for erro in (SemInternet("Sem internet."),
                     LicenseError("Muitas tentativas.", "muitas_tentativas"),
                     LicenseError("Erro 500.", "servidor"),
                     RuntimeError("inesperado")):
            with self.subTest(erro=type(erro).__name__):
                self.gateway.erro = erro
                self.service.conferir()
                self.assertTrue(self.service.allows("estoque"))
                self.assertEqual(self.service.current.bloqueio, "")


class GatewaySupabaseTestCase(unittest.TestCase):
    """Traducao entre a resposta do Supabase e a licenca local."""

    class ClienteFalso:
        def __init__(self, resposta=None, excecao: Exception | None = None) -> None:
            self.resposta = resposta
            self.excecao = excecao
            self.chamadas: list[tuple[str, dict]] = []

        def rpc(self, funcao: str, params: dict):
            self.chamadas.append((funcao, params))
            if self.excecao is not None:
                raise self.excecao
            return self.resposta

    def test_resposta_ok_vira_licenca(self) -> None:
        cliente = self.ClienteFalso({
            "ok": True,
            "chave": CHAVE,
            "cliente": "Maria Souza",
            "aplicativos": ["ESTOQUE", "VENDAS"],
            "expira_em": None,
            "max_computadores": 3,
            "computadores_usados": 2,
        })
        gateway = SupabaseLicenseGateway(cliente)
        licenca = gateway.fetch(CHAVE, "MAQ-1")

        self.assertEqual(cliente.chamadas[0][0], "dumtech_ativar_licenca")
        self.assertEqual(cliente.chamadas[0][1]["p_chave"], CHAVE)
        self.assertEqual(licenca.entitlements, ("estoque", "vendas"))
        self.assertEqual(licenca.customer, "Maria Souza")
        self.assertEqual(licenca.max_machines, 3)
        self.assertEqual(licenca.source, ORIGEM_SUPABASE)
        self.assertTrue(licenca.allows("vendas"))
        self.assertFalse(licenca.allows("agenda"))

    def test_resposta_com_produtos_e_tipo(self) -> None:
        """Formato atual do servidor: campo 'produtos' e o tipo da licenca."""
        cliente = self.ClienteFalso({
            "ok": True,
            "chave": CHAVE,
            "cliente": "Maria Souza",
            "tipo": "assinatura",
            "produtos": ["ESTOQUE", "AGENDA"],
            "aplicativos": ["ESTOQUE", "AGENDA"],
            "expira_em": "2027-12-31",
            "max_computadores": 1,
            "computadores_usados": 1,
        })
        licenca = SupabaseLicenseGateway(cliente).fetch(CHAVE, "MAQ-1")

        self.assertEqual(licenca.entitlements, ("agenda", "estoque"))
        self.assertEqual(licenca.tipo, "assinatura")
        self.assertEqual(licenca.expires_at, "2027-12-31")

    def test_servidor_antigo_ainda_e_entendido(self) -> None:
        """Sem o campo 'produtos', vale o nome antigo ('aplicativos')."""
        cliente = self.ClienteFalso({
            "ok": True, "chave": CHAVE, "cliente": "Joao", "aplicativos": ["VENDAS"],
        })
        licenca = SupabaseLicenseGateway(cliente).fetch(CHAVE, "MAQ-1")

        self.assertEqual(licenca.entitlements, ("vendas",))
        self.assertEqual(licenca.tipo, "", "servidor antigo nao manda tipo")

    def test_tipo_sobrevive_ao_arquivo_local(self) -> None:
        arquivo = arquivo_licenca()
        cliente = self.ClienteFalso({
            "ok": True, "chave": CHAVE, "cliente": "Joao",
            "produtos": ["VENDAS"], "tipo": "teste", "expira_em": "2030-01-01",
        })
        with sem_modo_local():
            servico = LicenseService(arquivo, SupabaseLicenseGateway(cliente))
            servico.activate(CHAVE)
            self.assertEqual(LicenseService(arquivo, cliente).current.tipo, "teste")

    def test_resposta_de_erro_vira_mensagem(self) -> None:
        cliente = self.ClienteFalso({
            "ok": False, "erro": "nao_encontrada", "mensagem": "Chave nao encontrada.",
        })
        with self.assertRaises(LicenseError) as caso:
            SupabaseLicenseGateway(cliente).fetch(CHAVE, "MAQ-1")
        self.assertEqual(caso.exception.codigo, "nao_encontrada")
        self.assertIn("nao encontrada", str(caso.exception).lower())

    def test_sem_conexao_vira_sem_internet(self) -> None:
        cliente = self.ClienteFalso(excecao=SemConexao("Sem internet."))
        with self.assertRaises(SemInternet):
            SupabaseLicenseGateway(cliente).verify(CHAVE, "MAQ-1")

    def test_servidor_com_problema_vira_erro_de_licenca(self) -> None:
        cliente = self.ClienteFalso(excecao=ServicoIndisponivel("Servidor sem as funcoes."))
        with self.assertRaises(LicenseError) as caso:
            SupabaseLicenseGateway(cliente).fetch(CHAVE, "MAQ-1")
        self.assertEqual(caso.exception.codigo, "servidor")

    def test_verificar_usa_a_funcao_certa(self) -> None:
        cliente = self.ClienteFalso({"ok": True, "chave": CHAVE, "cliente": "X", "aplicativos": []})
        SupabaseLicenseGateway(cliente).verify(CHAVE, "MAQ-1")
        self.assertEqual(cliente.chamadas[0][0], "dumtech_verificar_licenca")

    def test_endereco_e_chave_podem_vir_do_ambiente(self) -> None:
        with mock.patch.dict(os.environ, {
            "DUMTECH_SUPABASE_URL": "https://exemplo.supabase.co/rest/v1/",
            "DUMTECH_SUPABASE_KEY": "chave-de-teste",
        }):
            cliente = SupabaseClient()
        self.assertEqual(cliente.url, "https://exemplo.supabase.co/rest/v1")
        self.assertEqual(cliente.anon_key, "chave-de-teste")


class HubLicenciadoTestCase(LicencaBase):
    """O Hub so mostra (e so abre) o que a licenca liberar."""

    def setUp(self) -> None:
        super().setUp()
        from PySide6.QtWidgets import QApplication

        from dumtech.core.config import Settings
        from dumtech.hub.main_window import HubWindow
        from dumtech.ui.theme import MODO_ESCURO, ThemeManager

        self.app = QApplication.instance() or QApplication([])
        self.gateway = GatewayFalso(apps=("estoque",))
        self.service = LicenseService(arquivo_licenca(), self.gateway)
        self.hub = HubWindow(
            settings=Settings(Path(tempfile.mkdtemp()) / "hub.json"),
            license_service=self.service,
            theme=ThemeManager(self.app, MODO_ESCURO),
        )
        self.hub.launcher.notify = lambda *args: None
        self.addCleanup(self.hub.close)

    def test_sem_licenca_nada_e_liberado(self) -> None:
        self.assertFalse(self.service.ativada)
        self.assertEqual(self.hub.registry.available(), [])
        self.assertEqual(len(self.hub.registry.locked()), 7)
        self.assertFalse(self.hub.launcher.open("estoque", self.hub))
        self.assertTrue(self.hub.license_view.card_ativacao.isVisibleTo(self.hub.license_view))

    def test_apos_ativar_o_hub_mostra_so_o_que_foi_comprado(self) -> None:
        licenca = self.service.activate(CHAVE)
        self.hub.license_view._ativacao_concluida(licenca)  # callback real da tela

        self.assertEqual([e.app_id for e in self.hub.registry.available()], ["estoque"])
        self.assertEqual(len(self.hub.registry.locked()), 6)
        self.assertTrue(self.hub.launcher.open("estoque", self.hub))
        self.assertFalse(self.hub.launcher.open("financeiro", self.hub))

    def test_a_central_mostra_somente_os_aplicativos_comprados(self) -> None:
        from dumtech.ui.widgets.app_card import AppCard

        self.hub.license_view._ativacao_concluida(self.service.activate(CHAVE))
        cartoes = self.hub.home_view.corpo.findChildren(AppCard)
        self.assertEqual([c.manifest.app_id for c in cartoes], ["estoque"])
        # e o trilho da esquerda mostra exatamente os mesmos
        self.assertEqual(list(self.hub._app_items), ["estoque"])

    def test_comprar_outro_aplicativo_e_verificar(self) -> None:
        self.hub.license_view._ativacao_concluida(self.service.activate(CHAVE))
        self.gateway.apps = ("estoque", "agenda")

        self.hub.license_view._verificacao_concluida(self.service.verify())
        self.assertEqual(
            {e.app_id for e in self.hub.registry.available()}, {"estoque", "agenda"}
        )
        self.assertTrue(self.hub.launcher.open("agenda", self.hub))

    def test_perder_o_aplicativo_fecha_a_janela_aberta(self) -> None:
        self.hub.license_view._ativacao_concluida(self.service.activate(CHAVE))
        self.assertTrue(self.hub.launcher.open("estoque", self.hub))

        self.gateway.apps = ()  # a DumTech tirou o aplicativo da licenca
        self.hub.license_view._verificacao_concluida(self.service.verify())
        self.assertEqual(self.hub.launcher.open_apps, ())

    def test_ativacao_pela_tela_em_segundo_plano(self) -> None:
        from PySide6.QtCore import QThreadPool

        tela = self.hub.license_view
        tela.campo_chave.setText(CHAVE)
        tela.ativar()
        QThreadPool.globalInstance().waitForDone(8000)
        self.app.processEvents()

        self.assertTrue(self.service.ativada)
        self.assertEqual(self.gateway.chamadas_fetch, 1)
        self.assertTrue(tela.botao_ativar.isEnabled(), "a tela precisa voltar a responder")


if __name__ == "__main__":
    unittest.main()
