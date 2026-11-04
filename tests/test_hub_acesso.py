"""O Hub inteiro com contas: quem abre, o que ve, e o que nao pode sumir.

O que estes testes protegem: loja sem conta segue igual; funcionario nao chega em
tela de dono por caminho nenhum; o celular continua recebendo a loja inteira; e
ninguem perde venda no meio por causa de uma conta.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtWidgets import QApplication

from dumtech.core import acesso as nucleo_acesso
from dumtech.core.config import Settings
from dumtech.core.licensing import License, LicenseService
from dumtech.core.paths import ENV_DATA_DIR
from dumtech.hub import main_window
from dumtech.hub.main_window import (
    PAGINA_APP, PAGINA_ASSISTENTE, PAGINA_CONFIG, PAGINA_INICIO, PAGINA_LICENCA, PAGINA_LOGIN, HubWindow,
)

from .assinante import licenca_de_teste, pacote, pacote_acesso, pacote_lembranca
from .test_acesso import ADM, CHAVE, MAQUINA, MARIA, ServidorFalso, conta, maria

_app: QApplication | None = None

MODULOS = ("agenda", "clientes", "estoque", "financeiro", "vendas")


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class BaseHub(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = Path(tempfile.mkdtemp(prefix="dumtech_hub_acesso_"))
        ambiente = mock.patch.dict(os.environ, {ENV_DATA_DIR: str(self.pasta)})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        os.environ.pop("DUMTECH_LICENCA_LOCAL", None)
        from dumtech.core import paths
        if hasattr(paths.get_paths, "cache_clear"):
            paths.get_paths.cache_clear()
            self.addCleanup(paths.get_paths.cache_clear)
        contexto = licenca_de_teste()
        contexto.__enter__()
        self.addCleanup(contexto.__exit__, None, None, None)
        rapido = mock.patch.object(nucleo_acesso, "ITERACOES_LOCAIS", 1000)
        rapido.start()
        self.addCleanup(rapido.stop)
        self.licencas = LicenseService(file_path=self.pasta / "license.json", gateway=mock.Mock())
        self.settings = Settings(self.pasta / "hub.json")
        self.settings.set("conta", "concluido", True)
        self.hub: HubWindow | None = None

    def licenca(self, usuarios=(), exigir_conta=False, documento=True) -> None:
        self.licencas.save(License(
            key=CHAVE, customer="Loja", entitlements=MODULOS, machine=MAQUINA,
            activated_at="2026-11-01T10:00:00+00:00", source="supabase", last_check=None,
            assinado=pacote(CHAVE, MAQUINA, MODULOS, contas=bool(usuarios)),
            acesso=pacote_acesso(usuarios, exigir_conta=exigir_conta) if documento else {},
        ))
        self.licencas.reload()

    def lembrar(self, usuario: dict) -> None:
        arquivo = self.pasta / "config" / "acesso.json"
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps({
            "lembrado": usuario["id"], "recentes": [usuario["id"]],
            "locais": {usuario["id"]: {"lembranca": pacote_lembranca(usuario["id"], usuario["senha_versao"])}},
        }), encoding="utf-8")

    def abrir(self) -> HubWindow:
        self.hub = HubWindow(settings=self.settings, license_service=self.licencas)
        self.addCleanup(self.fechar)
        return self.hub

    def fechar(self) -> None:
        if self.hub is not None:
            self.hub.close()
            self.hub.deleteLater()
            self.hub = None
            QApplication.processEvents()

    def abas(self) -> list[str]:
        return sorted(self.hub._app_items)

    def comandos(self) -> list[str]:
        return [comando.title for comando in self.hub.build_commands()]


class LojaSemConta(BaseHub):
    def test_abre_no_inicio_com_tudo_e_convida_uma_vez(self) -> None:
        self.licenca()
        hub = self.abrir()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_ASSISTENTE, "convite ao abrir")
        hub.assistente_view.botao_agora_nao.click()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_INICIO)
        self.assertEqual(self.abas(), sorted(MODULOS))
        hub._go(PAGINA_LICENCA)
        hub._go(PAGINA_INICIO)
        self.assertEqual(hub.stack.currentIndex(), PAGINA_INICIO, "uma vez por abertura")

    def test_exigir_conta_tira_o_agora_nao(self) -> None:
        self.licenca(exigir_conta=True)
        hub = self.abrir()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_ASSISTENTE)
        self.assertTrue(hub.assistente_view.botao_agora_nao.isHidden())

    def test_sem_saber_das_contas_nao_incomoda(self) -> None:
        self.licenca(documento=False)
        hub = self.abrir()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_INICIO)
        self.assertEqual(self.abas(), sorted(MODULOS))

    def test_menu_igual_ao_de_sempre(self) -> None:
        self.licenca(documento=False)
        hub = self.abrir()
        hub._ajustar_menu()
        self.assertTrue(hub.item_licenca.isVisible())
        self.assertTrue(hub.item_celular.isVisible())
        self.assertFalse(hub.item_sair.isVisible(), "sem conta nao ha de onde sair")


class ComContas(BaseHub):
    def test_abre_no_login_sem_barra_e_sem_nada(self) -> None:
        self.licenca([conta(), maria()])
        hub = self.abrir()
        hub.show()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_LOGIN)
        self.assertFalse(hub.topo.isVisible())
        self.assertEqual(self.abas(), [])
        hub._go(PAGINA_INICIO)
        self.assertEqual(hub.stack.currentIndex(), PAGINA_LOGIN, "atalho nao pula a porta")
        hub.open_palette()
        self.assertFalse(hub.palette_dialog.isVisible())

    def test_lembrado_abre_direto(self) -> None:
        self.licenca([conta(), maria()])
        self.lembrar(conta())
        hub = self.abrir()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_INICIO)
        self.assertEqual(self.abas(), sorted(MODULOS))

    def test_entrar_monta_as_abas_da_pessoa(self) -> None:
        self.licenca([conta(), maria()])
        hub = self.abrir()
        hub.acesso.client = servidor = ServidorFalso()
        servidor.respostas["entrar"] = {
            "ok": True, "sessao": "s", "usuario": maria(), "acesso_assinado": pacote_acesso([conta(), maria()])}
        hub.login_view.campo_login.setText("maria")
        hub.login_view.campo_senha.setText("cavalo-azul")
        with mock.patch("dumtech.hub.views.login_view.tasks.executar",
                        lambda _p, f, ok, _e: ok(f())):
            hub.login_view.entrar()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_INICIO)
        self.assertTrue(hub.topo.isVisibleTo(hub))
        self.assertEqual(self.abas(), ["vendas"])


class Funcionario(BaseHub):
    def setUp(self) -> None:
        super().setUp()
        self.licenca([conta(), maria()])
        self.lembrar(maria())
        self.abrir()

    def test_so_as_abas_dele(self) -> None:
        self.assertEqual(self.abas(), ["vendas"])
        self.assertEqual(self.hub.perfil._sub, "Maria")

    def test_nao_abre_modulo_nao_marcado(self) -> None:
        with mock.patch.object(self.hub.launcher, "_error") as recusa:
            self.assertFalse(self.hub.open_app("financeiro"))
        self.assertIn("não tem acesso", recusa.call_args.args[2])
        self.assertEqual(self.hub.launcher.preparar("financeiro"), None)

    def test_menu_so_tem_o_que_e_dele(self) -> None:
        self.hub._ajustar_menu()
        for item in (self.hub.item_empresa, self.hub.item_licenca, self.hub.item_config,
                     self.hub.item_usuarios, self.hub.item_backup, self.hub.item_celular):
            self.assertFalse(item.isVisible(), item.text())
        for item in (self.hub.item_minha_conta, self.hub.item_trocar, self.hub.item_sair):
            self.assertTrue(item.isVisible(), item.text())

    def test_paleta_nao_leva_a_tela_de_dono(self) -> None:
        titulos = self.comandos()
        for proibido in ("Licença", "Configurações", "Minha empresa", "Usuários e acessos",
                         "Pagamentos e chave Pix", "Backup"):
            self.assertNotIn(proibido, titulos)
        self.assertIn("Minha conta", titulos)
        self.assertFalse(any(t.startswith("Financeiro") for t in titulos))

    def test_nenhum_caminho_chega_em_tela_de_dono(self) -> None:
        self.hub._go(PAGINA_LICENCA)
        self.hub._go(PAGINA_CONFIG)
        self.hub._ir_para_config(self.hub.backup_view)
        self.assertEqual(self.hub.stack.currentIndex(), PAGINA_INICIO)

    def test_celular_e_loja_nao_abrem(self) -> None:
        with mock.patch.object(main_window, "CelularDialog") as celular, \
             mock.patch.object(self.hub.loja, "link") as loja:
            self.hub.abrir_celular()
            self.hub.abrir_loja()
        celular.assert_not_called()
        loja.assert_not_called()

    def test_resumo_do_celular_continua_com_a_loja_inteira(self) -> None:
        self.settings.set("celular", "pareados", 1)
        with mock.patch.object(main_window.nucleo_celular, "montar", return_value={"secoes": []}) as montar, \
             mock.patch.object(main_window.tasks, "executar"):
            self.hub.publicar_no_celular(forcar=True)
        self.assertEqual(sorted(e.app_id for e in montar.call_args.args[0]), sorted(MODULOS))

    def test_aviso_de_outro_modulo_nao_aparece(self) -> None:
        marcado = mock.Mock(tipo="estoque_baixo")
        outro = mock.Mock(tipo="conta_vencida")
        with mock.patch("dumtech.hub.views.home_view.nucleo_avisos.coletar", return_value=[marcado, outro]), \
             mock.patch("dumtech.hub.views.home_view.nucleo_avisos.ordenar", side_effect=list):
            avisos = self.hub.home_view._avisos(self.hub.registry.visiveis())
        self.assertEqual(avisos, [marcado])

    def test_sem_oferta_de_modulo(self) -> None:
        self.assertIsNone(self.hub.home_view._botao_adquirir())

    def test_trocar_de_usuario_volta_para_a_porta_e_nao_abre_sozinho(self) -> None:
        self.hub.trocar_de_usuario()
        self.assertEqual(self.hub.stack.currentIndex(), PAGINA_LOGIN)
        self.assertEqual(self.abas(), [])
        guardado = json.loads((self.pasta / "config" / "acesso.json").read_text(encoding="utf-8"))
        self.assertEqual(guardado["lembrado"], "", "reabrir o Hub nao devolve a conta sem senha")
        self.assertIn(MARIA, guardado["recentes"], "mas ela continua na lista do login")

    def test_sair_esquece(self) -> None:
        self.hub.sair_da_conta()
        self.assertEqual(self.hub.stack.currentIndex(), PAGINA_LOGIN)
        guardado = json.loads((self.pasta / "config" / "acesso.json").read_text(encoding="utf-8"))
        self.assertEqual(guardado["lembrado"], "")

    def test_sair_com_venda_aberta_pergunta(self) -> None:
        self.hub.open_app("vendas")
        with mock.patch.object(self.hub.launcher.get("vendas"), "tem_trabalho_aberto", return_value=True), \
             mock.patch.object(main_window, "confirmar", return_value=False) as pergunta:
            self.hub.sair_da_conta()
        pergunta.assert_called_once()
        self.assertEqual(self.hub.stack.currentIndex(), PAGINA_APP, "cancelou: continua vendendo")

    def test_permissao_nova_aparece_sem_sair(self) -> None:
        self.licencas.guardar_acesso(pacote_acesso([conta(), maria(modulos=["vendas", "estoque"])]))
        self.hub._acesso_mudou()
        self.assertEqual(self.abas(), ["estoque", "vendas"])
        self.assertEqual(self.hub.stack.currentIndex(), PAGINA_INICIO)

    def test_permissao_tirada_fecha_o_modulo(self) -> None:
        self.hub.open_app("vendas")
        self.licencas.guardar_acesso(pacote_acesso([conta(), maria(modulos=[])]))
        self.hub._acesso_mudou()
        self.assertEqual(self.abas(), [])
        self.assertEqual(self.hub.stack.currentIndex(), PAGINA_INICIO)

    def test_permissao_tirada_nao_derruba_venda_em_andamento(self) -> None:
        self.hub.open_app("vendas")
        self.licencas.guardar_acesso(pacote_acesso([conta(), maria(modulos=[])]))
        with mock.patch.object(self.hub.launcher.get("vendas"), "tem_trabalho_aberto", return_value=True):
            self.hub._acesso_mudou()
            self.assertIn("vendas", self.hub.workspace.mounted)

    def test_conta_bloqueada_sai_e_diz_por_que(self) -> None:
        self.licencas.guardar_acesso(pacote_acesso([conta(), maria(ativo=False)]))
        self.hub._acesso_mudou()
        self.assertEqual(self.hub.stack.currentIndex(), PAGINA_LOGIN)
        self.assertIn("mudou", self.hub.login_view.aviso_entrar.text())

    def test_conta_bloqueada_espera_a_venda_acabar(self) -> None:
        self.hub.open_app("vendas")
        self.licencas.guardar_acesso(pacote_acesso([conta(), maria(ativo=False)]))
        superficie = self.hub.launcher.get("vendas")
        with mock.patch.object(superficie, "tem_trabalho_aberto", return_value=True):
            self.hub._acesso_mudou()
            self.hub._conferir_saida_pendente()
            self.assertEqual(self.hub.stack.currentIndex(), PAGINA_APP)
        self.hub._conferir_saida_pendente()
        self.assertEqual(self.hub.stack.currentIndex(), PAGINA_LOGIN)


class ComputadorFora(BaseHub):
    def test_computador_solto_nao_fica_preso_no_login(self) -> None:
        self.licenca([conta(), maria()])
        hub = self.abrir()
        self.licencas._bloquear("Ative de novo", "maquina_nao_ativada")
        hub._on_license_changed()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_LOGIN, "fica na porta, com a saida")
        self.assertFalse(hub.login_view.link_licenca.isHidden())
        hub.login_view.link_licenca.click()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_LICENCA)

    def test_reativar_volta_para_o_login(self) -> None:
        self.licenca([conta(), maria()])
        self.licencas._bloquear("Ative de novo", "maquina_nao_ativada")
        hub = self.abrir()
        hub._go(PAGINA_LICENCA)
        self.licenca([conta(), maria()])
        hub._on_license_changed()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_LOGIN)


class Administrador(BaseHub):
    def test_rebaixado_com_a_tela_de_dono_aberta_sai_dela(self) -> None:
        self.licenca([conta(), maria()])
        self.lembrar(conta())
        hub = self.abrir()
        hub._go(PAGINA_CONFIG)
        rebaixada = conta(papel="funcionario", modulos=["vendas"])
        self.licencas.guardar_acesso(pacote_acesso([rebaixada, maria()]))
        hub._acesso_mudou()
        self.assertEqual(hub.stack.currentIndex(), PAGINA_INICIO)

    def test_novidade_nao_e_gasta_pelo_primeiro_funcionario(self) -> None:
        self.licenca([conta(), maria()])
        self.lembrar(maria())
        hub = self.abrir()
        hub.isActiveWindow = lambda: True
        with mock.patch.object(hub, "_contar_novidades") as contar:
            hub._talvez_anunciar()
        contar.assert_not_called()

    def test_hub_aberto_antes_das_contas_pede_a_senha_para_o_celular(self) -> None:
        self.licenca()
        hub = self.abrir()
        self.licencas.guardar_acesso(pacote_acesso([conta()]))
        confirmacao = mock.Mock()
        confirmacao.return_value.exec.return_value = False
        with mock.patch.object(main_window, "ConfirmarSenhaDialog", confirmacao):
            hub.abrir_celular()
        confirmacao.assert_called_once()

    def test_adm_ve_tudo_e_tem_a_conta_no_menu(self) -> None:
        self.licenca([conta(), maria()])
        self.lembrar(conta())
        hub = self.abrir()
        hub._ajustar_menu()
        self.assertTrue(hub.item_usuarios.isVisible())
        self.assertTrue(hub.item_sair.isVisible())
        self.assertIn("Usuários e acessos", self.comandos())

    def test_adm_lembrado_confirma_a_senha_para_o_celular(self) -> None:
        self.licenca([conta()])
        self.lembrar(conta())
        hub = self.abrir()
        confirmacao = mock.Mock()
        confirmacao.return_value.exec.return_value = False
        with mock.patch.object(main_window, "ConfirmarSenhaDialog", confirmacao), \
             mock.patch.object(main_window, "CelularDialog") as celular:
            hub.abrir_celular()
        confirmacao.assert_called_once()
        celular.assert_not_called()

    def test_liberar_este_computador_tira_a_licenca(self) -> None:
        self.licenca([conta()])
        self.lembrar(conta())
        hub = self.abrir()
        hub._licenca_saiu_daqui()
        self.assertFalse(self.licencas.current.key)
        self.assertFalse((self.pasta / "config" / "acesso.json").exists())
        self.assertFalse(hub.acesso.precisa_login())


if __name__ == "__main__":
    unittest.main()
