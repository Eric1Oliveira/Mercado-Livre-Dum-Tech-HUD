"""Um modulo escreve, o outro fica sabendo na hora.

As pontes de `test_pontes.py` provam que o dado atravessa. Estes testes provam
a outra metade: quem estava aberto do outro lado descobre que o dado mudou sem
precisar ser fechado e aberto de novo.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QWidget

from dumtech.core import eventos
from dumtech.core.app_module import AppContext, AppManifest
from dumtech.core.contacts import Contato, ContactsStore
from dumtech.core.contas import AReceber
from dumtech.core.paths import DataPaths
from dumtech.core.pedidos import ItemPedido, Pedido
from dumtech.ui.app_shell import AppWindow

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class Escuta:
    """Guarda o que o barramento anunciou enquanto o teste roda."""

    def __init__(self) -> None:
        self.avisos: list[str] = []
        eventos.ouvir(self.avisos.append)

    def parar(self) -> None:
        eventos.parar_de_ouvir(self.avisos.append)


class BarramentoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.recebidos: list[str] = []
        eventos.ouvir(self._anotar)
        self.addCleanup(eventos.parar_de_ouvir, self._anotar)

    def _anotar(self, app_id: str) -> None:
        self.recebidos.append(app_id)

    def test_quem_ouve_recebe_o_aviso(self) -> None:
        eventos.avisar("financeiro")
        self.assertEqual(self.recebidos, ["financeiro"])

    def test_quem_parou_de_ouvir_nao_recebe_mais(self) -> None:
        eventos.parar_de_ouvir(self._anotar)
        eventos.avisar("financeiro")
        self.assertEqual(self.recebidos, [])

    def test_ouvinte_com_defeito_nao_derruba_os_outros(self) -> None:
        def quebrado(_app_id: str) -> None:
            raise RuntimeError("boom")

        eventos.ouvir(quebrado)
        self.addCleanup(eventos.parar_de_ouvir, quebrado)
        eventos.avisar("estoque")  # nao pode levantar
        self.assertEqual(self.recebidos, ["estoque"])

    def test_o_mesmo_ouvinte_nao_entra_duas_vezes(self) -> None:
        eventos.ouvir(self._anotar)
        eventos.avisar("vendas")
        self.assertEqual(self.recebidos, ["vendas"])


class PonteAvisaTestCase(unittest.TestCase):
    """Toda porta entre modulos anuncia de quem e o dado que acabou de mudar."""

    def setUp(self) -> None:
        self.paths = DataPaths(root=Path(tempfile.mkdtemp())).ensure()
        self.abertos: list = []
        self.escuta = Escuta()
        self.addCleanup(self.escuta.parar)

    def tearDown(self) -> None:
        for aberto in self.abertos:
            aberto.close()

    def _abrir(self, modulo: str, funcao: str, app_id: str):
        from importlib import import_module

        ponte = getattr(import_module(modulo), funcao)(self.paths.app_db(app_id))
        self.abertos.append(ponte)
        return ponte

    def test_lancar_conta_avisa_o_financeiro(self) -> None:
        ponte = self._abrir("dumtech.apps.financeiro.contas", "abrir_contas", "financeiro")
        ponte.lancar(AReceber(descricao="Venda VEN-1", valor=100.0,
                              vencimento=date.today().isoformat(),
                              documento="VEN-1"))
        self.assertIn("financeiro", self.escuta.avisos)

    def test_quitar_avisa_o_financeiro(self) -> None:
        ponte = self._abrir("dumtech.apps.financeiro.contas", "abrir_contas", "financeiro")
        ponte.lancar(AReceber(descricao="Venda VEN-2", valor=100.0,
                              vencimento=date.today().isoformat(),
                              documento="VEN-2"))
        self.escuta.avisos.clear()
        self.assertTrue(ponte.quitar("VEN-2"))
        self.assertIn("financeiro", self.escuta.avisos)

    def test_quitar_o_que_nao_existe_nao_avisa(self) -> None:
        ponte = self._abrir("dumtech.apps.financeiro.contas", "abrir_contas", "financeiro")
        self.escuta.avisos.clear()
        self.assertFalse(ponte.quitar("NAO-EXISTE"))
        self.assertEqual(self.escuta.avisos, [])

    def test_baixar_do_catalogo_avisa_o_estoque(self) -> None:
        from dumtech.apps.estoque.models import Produto

        catalogo = self._abrir("dumtech.apps.estoque.catalog", "abrir_catalogo", "estoque")
        produto = catalogo.repository.criar(
            Produto(codigo="A1", nome="Cafe", quantidade=10, preco_venda=20.0)
        )
        self.escuta.avisos.clear()
        catalogo.baixar(produto.id, 2, documento="VEN-1")
        self.assertIn("estoque", self.escuta.avisos)

        self.escuta.avisos.clear()
        catalogo.devolver(produto.id, 2, documento="VEN-1")
        self.assertIn("estoque", self.escuta.avisos)

    def test_proposta_que_vira_venda_avisa_o_vendas(self) -> None:
        destino = self._abrir("dumtech.apps.vendas.pedidos", "abrir_destino", "vendas")
        destino.abrir(Pedido(cliente="Ana", origem="ORC-1",
                             itens=[ItemPedido(descricao="Servico", valor_unitario=50.0)]))
        self.assertIn("vendas", self.escuta.avisos)

    def test_proposta_que_vira_ordem_avisa_as_ordens(self) -> None:
        destino = self._abrir("dumtech.apps.ordens.pedidos", "abrir_destino", "ordens")
        destino.abrir(Pedido(cliente="Ana", origem="ORC-1",
                             itens=[ItemPedido(descricao="Servico", valor_unitario=50.0)]))
        self.assertIn("ordens", self.escuta.avisos)

    def test_mexer_na_agenda_de_clientes_avisa_a_plataforma(self) -> None:
        store = ContactsStore(self.paths.platform_db)
        self.abertos.append(store)
        criado = store.criar(Contato(nome="Ana Souza"))
        self.assertIn("clientes", self.escuta.avisos)

        self.escuta.avisos.clear()
        store.atualizar(Contato(id=criado.id, nome="Ana S. Souza"))
        self.assertIn("clientes", self.escuta.avisos)

        self.escuta.avisos.clear()
        store.inativar(criado.id)
        self.assertIn("clientes", self.escuta.avisos)


class CascaFalsa(AppWindow):
    """Um aplicativo minimo: uma tela que conta quantas vezes recarregou."""

    def setup_data(self) -> None:
        self.clientes: list[str] = []
        if self.context.contacts is not None:
            self.clientes = self.context.contacts.nomes()

    def build_views(self) -> None:
        tela = QWidget()
        tela.recargas = 0
        tela.clientes = self.clientes
        tela.refresh = lambda: setattr(tela, "recargas", tela.recargas + 1)
        self.tela = self.add_view("Painel", "dashboard", tela)


def _casca(paths: DataPaths, app_id: str, contacts=None) -> CascaFalsa:
    manifest = AppManifest(app_id=app_id, name=app_id, short_name=app_id,
                           description="teste")
    return CascaFalsa(AppContext(manifest=manifest, paths=paths, contacts=contacts))


class WorkspaceTestCase(unittest.TestCase):
    """O aplicativo que ficou para tras recarrega quando volta a aparecer."""

    def setUp(self) -> None:
        from dumtech.hub.workspace import Workspace

        self.paths = DataPaths(root=Path(tempfile.mkdtemp())).ensure()
        self.workspace = Workspace()
        self.addCleanup(self.workspace.deleteLater)

    def test_a_casca_escondida_recarrega_quando_volta(self) -> None:
        financeiro = _casca(self.paths, "financeiro")
        vendas = _casca(self.paths, "vendas")
        self.workspace.mount(financeiro)
        self.workspace.mount(vendas)  # o Vendas fica na frente
        recargas = financeiro.tela.recargas

        self.workspace.invalidar("financeiro")
        self.assertEqual(financeiro.tela.recargas, recargas,
                         "escondido, nao gasta leitura de banco")

        self.workspace.show_app("financeiro")
        self.assertEqual(financeiro.tela.recargas, recargas + 1)

    def test_voltar_de_novo_nao_recarrega_a_toa(self) -> None:
        financeiro = _casca(self.paths, "financeiro")
        vendas = _casca(self.paths, "vendas")
        self.workspace.mount(financeiro)
        self.workspace.mount(vendas)

        self.workspace.invalidar("financeiro")
        self.workspace.show_app("financeiro")
        recargas = financeiro.tela.recargas
        self.workspace.show_app("vendas")
        self.workspace.show_app("financeiro")
        self.assertEqual(financeiro.tela.recargas, recargas)

    def test_a_casca_visivel_recarrega_na_hora(self) -> None:
        vendas = _casca(self.paths, "vendas")
        self.workspace.mount(vendas)
        recargas = vendas.tela.recargas
        self.workspace.invalidar("vendas")
        self.workspace.atualizar_visivel()
        self.assertEqual(vendas.tela.recargas, recargas + 1)

    def test_aplicativo_fechado_nao_guarda_sujeira(self) -> None:
        vendas = _casca(self.paths, "vendas")
        self.workspace.mount(vendas)
        self.workspace.invalidar("vendas")
        self.workspace.unmount("vendas")
        self.assertEqual(self.workspace.sujos, ())

    def test_invalidar_tudo_atinge_todos_os_montados(self) -> None:
        self.workspace.mount(_casca(self.paths, "financeiro"))
        self.workspace.mount(_casca(self.paths, "vendas"))
        self.workspace.invalidar_tudo()
        self.assertEqual(set(self.workspace.sujos), {"financeiro", "vendas"})


class ClientesNaCascaTestCase(unittest.TestCase):
    """Cliente cadastrado agora aparece na sugestao de quem ja estava aberto."""

    def setUp(self) -> None:
        self.paths = DataPaths(root=Path(tempfile.mkdtemp())).ensure()
        self.store = ContactsStore(self.paths.platform_db)
        self.addCleanup(self.store.close)

    def test_refresh_all_rele_a_agenda_da_plataforma(self) -> None:
        self.store.criar(Contato(nome="Ana"))
        casca = _casca(self.paths, "vendas", contacts=self.store)
        self.addCleanup(casca.deleteLater)
        self.assertEqual(casca.tela.clientes, ["Ana"])

        self.store.criar(Contato(nome="Bruno"))
        casca.refresh_all()
        self.assertEqual(casca.clientes, ["Ana", "Bruno"])
        self.assertEqual(casca.tela.clientes, ["Ana", "Bruno"],
                         "a tela guarda a propria copia - ela tambem precisa saber")

    def test_agenda_fechada_nao_derruba_o_refresh(self) -> None:
        casca = _casca(self.paths, "vendas", contacts=self.store)
        self.addCleanup(casca.deleteLater)
        self.store.close()
        casca.refresh_all()  # nao pode levantar


class HubTestCase(unittest.TestCase):
    """De ponta a ponta, com o Hub de verdade: vender mexe no Estoque aberto."""

    def setUp(self) -> None:
        from dumtech.core.config import Settings
        from dumtech.hub.main_window import PAGINA_APP, HubWindow

        self.PAGINA_APP = PAGINA_APP
        pasta = Path(tempfile.mkdtemp())
        self.hub = HubWindow(settings=Settings(pasta / "hub.json"))
        self.hub.launcher.notify = lambda *args: None

    def tearDown(self) -> None:
        self.hub.close()
        self.hub.deleteLater()
        QApplication.instance().sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _girar(self) -> None:
        """O Hub adia a releitura para o proximo giro do laco - da o giro."""
        QApplication.instance().processEvents()

    def test_a_venda_marca_o_estoque_aberto_como_desatualizado(self) -> None:
        from dumtech.apps.estoque.models import Produto

        self.assertTrue(self.hub.open_app("estoque"))
        estoque = self.hub.launcher.get("estoque")
        produto = estoque.repository.criar(
            Produto(codigo="A1", nome="Cafe", quantidade=10, preco_venda=20.0)
        )
        self.assertTrue(self.hub.open_app("vendas"))  # o Estoque fica atras

        catalogo = self.hub.launcher.catalog("vendas")
        self.assertIsNotNone(catalogo, "com o Estoque na licenca, a ponte existe")
        catalogo.baixar(produto.id, 3, documento="VEN-1")
        self._girar()

        self.assertIn("estoque", self.hub.workspace.sujos,
                      "o Estoque escondido precisa saber que o saldo mudou")
        self.hub.open_app("estoque")
        self.assertEqual(self.hub.workspace.sujos, (),
                         "ao voltar, ele ja recarregou")
        self.assertEqual(estoque.repository.obter(produto.id).quantidade, 7)

    def test_a_ordem_entregue_atualiza_o_financeiro_aberto(self) -> None:
        self.assertTrue(self.hub.open_app("financeiro"))
        self.assertTrue(self.hub.open_app("ordens"))

        contas = self.hub.launcher.contas("ordens")
        self.assertIsNotNone(contas)
        contas.lancar(AReceber(descricao="OS-1", valor=300.0,
                               vencimento=date.today().isoformat(),
                               documento="OS-1"))
        self._girar()
        self.assertIn("financeiro", self.hub.workspace.sujos)

    def test_o_cliente_novo_chega_em_todos_os_modulos_abertos(self) -> None:
        self.assertTrue(self.hub.open_app("vendas"))
        self.assertTrue(self.hub.open_app("ordens"))
        vendas = self.hub.launcher.get("vendas")

        self.hub.contacts.criar(Contato(nome="Cliente Novo"))
        self._girar()

        self.hub.open_app("vendas")
        self.assertIn("Cliente Novo", vendas.clientes)
        self.assertIn("Cliente Novo", vendas.balcao_view.clientes,
                      "a sugestao do balcao e que o vendedor ve")

    def test_o_aplicativo_da_frente_recarrega_sem_precisar_trocar_de_tela(self) -> None:
        self.assertTrue(self.hub.open_app("financeiro"))
        financeiro = self.hub.launcher.get("financeiro")
        lancamentos = financeiro.lancamentos_view
        antes = len(lancamentos._registros)

        contas = self.hub.launcher.contas("vendas")
        contas.lancar(AReceber(descricao="VEN-9", valor=50.0,
                               vencimento=date.today().isoformat(),
                               documento="VEN-9"))
        self._girar()
        self.assertEqual(self.hub.workspace.sujos, (),
                         "quem esta na frente ja recarregou, nao fica devendo")
        self.assertGreater(len(lancamentos._registros), antes)

    def test_rajada_de_avisos_vira_uma_releitura_so(self) -> None:
        """A venda baixa cinco itens do estoque: isso e uma recarga, nao cinco."""
        self.assertTrue(self.hub.open_app("financeiro"))
        financeiro = self.hub.launcher.get("financeiro")
        recargas = []
        original = financeiro.refresh_all
        financeiro.refresh_all = lambda: (recargas.append(1), original())

        for numero in range(5):
            eventos.avisar("financeiro")
        self.assertEqual(len(recargas), 0, "nada acontece antes do giro do laco")
        self._girar()
        self.assertEqual(len(recargas), 1)

    def test_fechar_o_hub_solta_o_barramento(self) -> None:
        self.hub.close()
        self.assertNotIn(self.hub._dados_alterados, eventos._ouvintes)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
