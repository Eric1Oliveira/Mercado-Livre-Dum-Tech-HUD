"""O sistema visual: a fonte em todo lugar e a navegacao que nao pula."""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication

from dumtech.ui import theme
from dumtech.ui.theme import MODO_CLARO, MODO_ESCURO, ThemeManager

_app: QApplication | None = None
_tema: ThemeManager | None = None


def setUpModule() -> None:
    global _app, _tema
    _app = QApplication.instance() or QApplication([])
    _tema = ThemeManager(_app, MODO_ESCURO)


class FonteTestCase(unittest.TestCase):
    def test_a_fonte_vem_junto_com_o_programa(self) -> None:
        """Nao depende do que estiver instalado no Windows do cliente."""
        self.assertEqual(theme.text_family(), "Plus Jakarta Sans")

    def test_a_fonte_chega_nas_classes_que_o_windows_guarda(self) -> None:
        """Celula de tabela, menu e dica ficavam no Segoe.

        E trocar de tema e justamente o que devolvia o Segoe: a folha de estilo
        nova faz o Qt reler as fontes do sistema para essas classes.
        """
        _tema.set_mode(MODO_CLARO)
        try:
            for classe in ("QAbstractItemView", "QMenu", "QTipLabel", "QMessageBox"):
                with self.subTest(classe=classe):
                    self.assertEqual(QApplication.font(classe).family(),
                                     theme.text_family())
        finally:
            _tema.set_mode(MODO_ESCURO)


class TrocaDeTemaTestCase(unittest.TestCase):
    def test_janela_escondida_troca_na_hora_sem_cortina(self) -> None:
        """Sem ninguem olhando nao ha o que animar: a troca e imediata."""
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QWidget

        from dumtech.ui import motion

        janela = QWidget()
        trocas: list[int] = []
        motion.revelar_tema(janela, QPointF(10, 10), lambda: trocas.append(1))
        self.assertEqual(trocas, [1])
        self.assertEqual(janela.findChildren(motion._Cortina), [])

    def test_o_icone_do_tema_termina_no_novo(self) -> None:
        from dumtech.ui.widgets.topbar import BotaoTema

        botao = BotaoTema()
        botao.set_icon_name("moon")
        self.assertEqual(botao.icon_name, "moon")


class IndicadorTestCase(unittest.TestCase):
    """A selecao que desliza entre as abas."""

    def _abas(self):
        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

        from dumtech.ui.widgets.indicador import PILULA, Indicador

        caixa = QWidget()
        caixa.resize(300, 40)
        linha = QHBoxLayout(caixa)
        a, b = QPushButton("A"), QPushButton("B")
        linha.addWidget(a)
        linha.addWidget(b)
        linha.activate()
        indicador = Indicador(caixa, forma=PILULA)
        indicador.registrar(a)
        indicador.registrar(b)
        return caixa, a, b, indicador

    def test_sem_janela_a_selecao_vai_direto_para_o_lugar(self) -> None:
        """Ninguem olhando: nada de andar, a selecao ja nasce na aba."""
        caixa, _a, b, indicador = self._abas()
        indicador.selecionar(b)
        self.assertEqual(indicador._sel.left(), b.geometry().left())
        self.assertEqual(indicador._sel.width(), b.geometry().width())

    def test_desmontado_pelo_coletor_nao_dispara_erro(self) -> None:
        """O defeito: o coletor de ciclos esvazia o indicador ANTES do Qt acabar.

        Quando a caixa e o indicador so se seguram um no outro, quem os
        desmonta e o coletor de ciclos do Python: ele esvazia os atributos dos
        dois e so depois o Qt destroi as abas - que ainda mandam eventos para o
        indicador (ele e o filtro delas). Sem atributos, cada evento virava um
        erro no `sys.excepthook`, que no programa e a janela de erro.
        """
        import contextlib
        import gc
        import io
        import sys

        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

        from dumtech.ui.widgets.indicador import PILULA, Indicador

        erros: list = []
        saida = io.StringIO()
        antigo = sys.excepthook
        sys.excepthook = lambda *dados: erros.append(str(dados[1]))
        try:
            with contextlib.redirect_stderr(saida):
                caixa = QWidget()
                linha = QHBoxLayout(caixa)
                a, b = QPushButton("A"), QPushButton("B")
                linha.addWidget(a)
                linha.addWidget(b)
                indicador = Indicador(caixa, forma=PILULA)
                indicador.registrar(a)
                indicador.registrar(b)
                caixa.indicador = indicador  # o ciclo: so o coletor desmonta
                del caixa, linha, a, b, indicador
                gc.collect()
        finally:
            sys.excepthook = antigo
        self.assertEqual(erros, [])
        self.assertNotIn("Error calling Python override", saida.getvalue())

    def test_aba_que_sai_leva_a_selecao_junto(self) -> None:
        """A licenca mudou e a aba sumiu: o indicador nao aponta para o nada."""
        caixa, _a, b, indicador = self._abas()
        indicador.selecionar(b)
        indicador.remover(b)
        self.assertIsNone(indicador._selecionado)


class JanelaSoltaTestCase(unittest.TestCase):
    """Nenhuma janelinha piscando enquanto o Hub prepara as telas.

    `setVisible` num widget que ainda nao entrou no layout nao esconde nem
    mostra coisa alguma: **abre uma janela de verdade**, que pisca no canto da
    tela ate o widget ganhar um pai. O Hub monta os aplicativos em segundo
    plano na abertura, entao um botao assim virava uma janelinha por aplicativo.
    """

    def setUp(self) -> None:
        from PySide6.QtCore import QEvent, QObject
        from PySide6.QtWidgets import QWidget

        self.soltas: list[str] = []

        class Olho(QObject):
            def eventFilter(interno, obj, evento):  # noqa: N805 (Qt)
                if (evento.type() == QEvent.Type.Show and isinstance(obj, QWidget)
                        and obj.isWindow() and obj.parent() is None):
                    texto = obj.text() if hasattr(obj, "text") else obj.windowTitle()
                    self.soltas.append(f"{type(obj).__name__} '{texto.strip()}'")
                return False

        self.olho = Olho()
        _app.installEventFilter(self.olho)
        self.addCleanup(lambda: _app.removeEventFilter(self.olho))

    def test_montar_os_aplicativos_nao_abre_janela_nenhuma(self) -> None:
        import tempfile
        from pathlib import Path as Caminho

        from dumtech.core.config import Settings
        from dumtech.hub.main_window import HubWindow

        settings = Settings(Caminho(tempfile.mkdtemp()) / "hub.json")
        hub = HubWindow(settings=settings, theme=_tema)
        hub.launcher.notify = lambda *args: None
        self.addCleanup(hub.deleteLater)
        self.addCleanup(hub.close)

        for entrada in hub.registry.available():
            casca = hub.launcher.preparar(entrada.app_id)
            self.assertIsNotNone(casca, entrada.app_id)
            hub.workspace.montar_escondido(casca)
        _app.processEvents()

        self.assertEqual(self.soltas, [],
                         "widget sem pai ficou visivel e virou janela solta")


class PreparoTestCase(unittest.TestCase):
    """Aplicativo montado de antemao: o primeiro clique so mostra."""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path

        from dumtech.core.config import Settings
        from dumtech.hub.main_window import HubWindow

        _tema.set_mode(MODO_ESCURO)
        settings = Settings(Path(tempfile.mkdtemp()) / "hub.json")
        self.hub = HubWindow(settings=settings, theme=_tema)
        self.hub.launcher.notify = lambda *args: None

    def tearDown(self) -> None:
        from PySide6.QtCore import QEvent

        self.hub.close()
        self.hub.deleteLater()
        _app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _preparar(self, app_id: str):
        casca = self.hub.launcher.preparar(app_id)
        self.hub.workspace.montar_escondido(casca)
        return casca

    def test_preparado_nao_conta_como_aberto(self) -> None:
        """Sem ponto na aba e fora do "mais usados" ate a pessoa abrir."""
        self._preparar("estoque")
        self.assertEqual(self.hub.launcher.open_apps, ())
        self.assertEqual(self.hub.launcher.preparados, ("estoque",))
        self.assertFalse(self.hub._app_items["estoque"].is_open)

    def test_abrir_o_preparado_reaproveita_a_mesma_casca(self) -> None:
        casca = self._preparar("estoque")
        self.assertTrue(self.hub.open_app("estoque"))
        self.assertIs(self.hub.launcher.get("estoque"), casca)
        self.assertEqual(self.hub.launcher.preparados, ())
        self.assertEqual(self.hub.workspace.current_app, "estoque")

    def test_fechar_tudo_solta_os_preparados(self) -> None:
        """Eles seguram o banco aberto: restaurar backup precisa deles fechados."""
        self._preparar("vendas")
        self.hub.launcher.close_all()
        self.assertEqual(self.hub.launcher.preparados, ())

    def test_janela_escondida_nao_prepara_nada(self) -> None:
        self.hub._preparar_proximo()
        self.assertEqual(self.hub.launcher.preparados, ())

    def test_fechar_app_e_janela_nao_dispara_erro_escondido(self) -> None:
        """Fechar um aplicativo e destruir a janela nao deixa erro para tras.

        Erro dentro de um filtro do Qt vai para o `sys.excepthook` - e o do
        programa abre a janela de erro para o cliente. Este teste percorre os
        caminhos de fechamento (o comum e o do aplicativo preparado); o defeito
        do coletor de ciclos em si esta em `IndicadorTestCase`.
        """
        import contextlib
        import gc
        import io
        import sys
        import tempfile
        from pathlib import Path

        from PySide6.QtCore import QEvent

        from dumtech.core.config import Settings
        from dumtech.hub.main_window import HubWindow

        erros: list = []
        saida = io.StringIO()
        antigo = sys.excepthook
        sys.excepthook = lambda *dados: erros.append(str(dados[1]))
        try:
            with contextlib.redirect_stderr(saida):
                # fechar um aplicativo aberto do jeito comum
                self.hub.open_app("estoque")
                self.hub.close_app("estoque", perguntar=False)
                _app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

                # o caminho que falhava: preparado, aberto, e a janela destruida
                outra = HubWindow(settings=Settings(Path(tempfile.mkdtemp()) / "hub.json"),
                                  theme=_tema)
                outra.launcher.notify = lambda *args: None
                casca = outra.launcher.preparar("vendas")
                outra.workspace.montar_escondido(casca)
                outra.open_app("vendas")
                outra.close()
                outra.deleteLater()
                del outra, casca
                _app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                gc.collect()
                _app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        finally:
            sys.excepthook = antigo
        self.assertEqual(erros, [])
        self.assertNotIn("Error calling Python override", saida.getvalue())

    def test_refazer_as_abas_com_um_app_na_frente_nao_derruba(self) -> None:
        """O defeito: a aba de antes ficava guardada depois de apagada.

        Refazer as abas (a licenca mudou) com um aplicativo na frente fazia a
        conta de direcao medir uma aba ja solta da janela - e o Qt fechava o
        programa com acesso invalido de memoria, sem excecao nenhuma.
        """
        self.hub.open_app("estoque")
        self.hub.refresh_rail()  # antes desta correcao: o processo morria aqui
        self.assertTrue(self.hub.open_app("vendas"))
        self.assertEqual(self.hub.workspace.current_app, "vendas")


class AbaDoTopoTestCase(unittest.TestCase):
    def test_abrir_o_aplicativo_nao_muda_a_largura_da_aba(self) -> None:
        """O ponto de "aberto" mora no respiro da aba: nada empurra as vizinhas."""
        from dumtech.ui.widgets.topbar import NavTab

        aba = NavTab("Financeiro", accent="#2E9E6B", closable=True)
        antes = aba.sizeHint()
        aba.set_open(True)
        self.assertEqual(aba.sizeHint(), antes)

    def test_as_iniciais_da_empresa_pulam_a_palavra_de_ligacao(self) -> None:
        from dumtech.ui.widgets.topbar import iniciais

        self.assertEqual(iniciais("Casa do Parafuso"), "CP")
        self.assertEqual(iniciais("Mercado"), "ME")
        self.assertEqual(iniciais(""), "DT")


if __name__ == "__main__":
    unittest.main()
