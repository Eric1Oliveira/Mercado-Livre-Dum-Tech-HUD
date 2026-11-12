"""Todo dialogo cabe no monitor - com o Salvar a vista.

Na 1.6.0 um cliente com notebook (1366x768, Windows em 125%) abria qualquer
cadastro e nao achava o botao de salvar: a janela nascia mais alta que a area
util e o rodape ficava atras da barra de tarefas. Desde a 1.6.1 o miolo do
formulario rola e toda janela e aparada pela tela (`ui/tela.py`).

Os testes trocam a area util do monitor pela do notebook: o Qt de teste tem
uma tela so, e o tamanho dela nao muda depois de criado.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QRect, QSize
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QScrollArea

_app: QApplication | None = None

#: 1366x768 em 125% = 1093x614, menos a barra de tarefas
NOTEBOOK = QRect(0, 0, 1093, 576)
MONITOR = QRect(0, 0, 1920, 1040)


def setUpModule() -> None:
    global _app
    os.environ.setdefault("DUMTECH_DATA_DIR", tempfile.mkdtemp())
    os.environ["DUMTECH_LICENCA_LOCAL"] = "1"
    _app = QApplication.instance() or QApplication([])


def _na_tela(area: QRect):
    return mock.patch("dumtech.ui.tela.area_util", return_value=area)


def _dentro_de_rolagem(widget, dialogo: QDialog) -> bool:
    pai = widget.parentWidget()
    while pai is not None and pai is not dialogo:
        if isinstance(pai, QScrollArea):
            return True
        pai = pai.parentWidget()
    return False


def _problemas(dialogo: QDialog, area: QRect) -> list[str]:
    """O que impede a pessoa de usar o dialogo inteiro nesta tela."""
    from dumtech.ui.tela import MOLDURA_ALTURA, MOLDURA_LARGURA

    ruins = []
    por_fora = QRect(dialogo.x(), dialogo.y(),
                     dialogo.width() + MOLDURA_LARGURA, dialogo.height() + MOLDURA_ALTURA)
    if not area.contains(por_fora):
        ruins.append(f"janela {por_fora.getRect()} fora da area {area.getRect()}")
    for botao in dialogo.findChildren(QPushButton):
        # o que esta dentro de uma area de rolagem se alcanca rolando; o que
        # nao pode sumir e o que fica fora dela (o rodape com o Salvar)
        if botao.isVisibleTo(dialogo) and not _dentro_de_rolagem(botao, dialogo):
            fim = botao.mapTo(dialogo, botao.rect().bottomLeft()).y()
            if fim > dialogo.height():
                ruins.append(f"botao {botao.text().strip()!r} cortado ({fim} > {dialogo.height()})")
    for rotulo in dialogo.findChildren(QLabel):
        if rotulo.isVisibleTo(dialogo) and rotulo.text().strip() \
                and rotulo.height() + 1 < rotulo.minimumSizeHint().height():
            ruins.append(f"texto amassado {rotulo.text()[:25]!r}")
    return ruins


class CadastrosTestCase(unittest.TestCase):
    """O "Novo" de cada tela de cadastro, aberto no notebook e no monitor."""

    @classmethod
    def setUpClass(cls) -> None:
        from dumtech.core.config import Settings
        from dumtech.hub.main_window import HubWindow
        from dumtech.ui.widgets.crud_view import CrudView

        settings = Settings()
        settings.set("conta", "concluido", True)
        cls.hub = HubWindow(settings=settings)
        cls.hub.show()
        QTest.qWait(150)
        cls.telas = []
        for app_id in ("vendas", "estoque", "financeiro", "ordens",
                       "orcamentos", "clientes", "agenda"):
            if cls.hub.open_app(app_id):
                QTest.qWait(80)
                cls.telas += [(app_id, tela) for tela in
                              cls.hub.launcher.get(app_id).findChildren(CrudView)]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.hub.close()

    def _abrir(self, tela, area: QRect) -> QDialog | None:
        with _na_tela(area):
            dialogo = tela.abrir_dialogo(None)
            if dialogo is None:
                return None
            self.addCleanup(dialogo.deleteLater)
            self.addCleanup(dialogo.close)
            dialogo.show()
            QTest.qWait(40)
        return dialogo

    def test_ha_cadastros_para_conferir(self) -> None:
        self.assertGreaterEqual(len(self.telas), 8)

    def test_no_notebook_tudo_cabe_e_o_salvar_aparece(self) -> None:
        for app_id, tela in self.telas:
            dialogo = self._abrir(tela, NOTEBOOK)
            if dialogo is None:
                continue
            with self.subTest(dialogo=f"{app_id}/{type(dialogo).__name__}"):
                self.assertEqual(_problemas(dialogo, NOTEBOOK), [])
                self.assertTrue(dialogo.botao_salvar.isVisible())

    def test_no_monitor_grande_formulario_curto_nao_rola(self) -> None:
        for app_id, tela in self.telas:
            if app_id not in ("financeiro", "agenda", "estoque"):
                continue
            dialogo = self._abrir(tela, MONITOR)
            if dialogo is None:
                continue
            with self.subTest(dialogo=f"{app_id}/{type(dialogo).__name__}"):
                self.assertEqual(_problemas(dialogo, MONITOR), [])
                self.assertEqual(dialogo._area.verticalScrollBar().maximum(), 0)
                # a largura de sempre: nao encolhe nem estica por causa da rolagem
                self.assertGreaterEqual(dialogo.width(), dialogo._largura)


class OutrosDialogosTestCase(unittest.TestCase):
    """Os dialogos que nao sao formulario passam pela mesma regua."""

    def _conferir(self, dialogo: QDialog) -> list[str]:
        self.addCleanup(dialogo.deleteLater)
        self.addCleanup(dialogo.close)
        with _na_tela(NOTEBOOK):
            dialogo.show()
            QTest.qWait(40)
        return _problemas(dialogo, NOTEBOOK)

    def test_pagamento_do_balcao(self) -> None:
        from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

        self.assertEqual(self._conferir(PagamentoDialog(150.0, "Venda")), [])

    def test_novidades_de_varias_versoes_rolam(self) -> None:
        from dumtech.core import novidades
        from dumtech.hub.views.novidades_dialog import NovidadesDialog

        todas = [n for versao in novidades.VERSOES.values() for n in versao]
        self.assertEqual(self._conferir(NovidadesDialog(todas, "1.6.1")), [])

    def test_atualizacao_com_nota_comprida(self) -> None:
        from dumtech.core.atualizacao import Atualizacao
        from dumtech.hub.views.atualizacao_dialog import AtualizacaoDialog

        nota = "\n".join(f"Mudanca numero {i} desta versao" for i in range(60))
        aviso = Atualizacao("9.9.9", "https://dumtechsolution.com/x.exe", notas=nota)
        self.assertEqual(self._conferir(AtualizacaoDialog(aviso, "1.6.0", None)), [])

    def test_janela_com_minimo_maior_que_a_tela_cede(self) -> None:
        from dumtech.ui.widgets.comprovante import ComprovanteDialog

        texto = "\n".join(f"Linha {i}" for i in range(80))
        self.assertEqual(self._conferir(ComprovanteDialog(texto)), [])

    def test_pix_no_receber_nao_esconde_os_botoes_no_notebook(self) -> None:
        """O caso da cliente: escolher Pix abria o QR e o Receber sumia."""
        from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

        dialogo = PagamentoDialog(150.0, "Venda")
        self.addCleanup(dialogo.deleteLater)
        self.addCleanup(dialogo.close)
        with _na_tela(NOTEBOOK):
            dialogo.show()
            QTest.qWait(40)
            dialogo.forma.setCurrentText("Pix")
            QTest.qWait(60)
            self.assertTrue(dialogo.painel_pix.isVisible())
            self.assertEqual(_problemas(dialogo, NOTEBOOK), [])
            self.assertTrue(dialogo.botao_receber.isVisible())

    def _centro(self, dialogo) -> tuple[int, int]:
        centro = dialogo.geometry().center()
        return centro.x(), centro.y()

    def test_janela_cresce_e_volta_sem_sair_do_centro(self) -> None:
        from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

        dialogo = PagamentoDialog(150.0, "Venda")
        self.addCleanup(dialogo.deleteLater)
        self.addCleanup(dialogo.close)
        with _na_tela(MONITOR):
            dialogo.show()
            QTest.qWait(40)
            altura, centro = dialogo.height(), self._centro(dialogo)

            dialogo.forma.setCurrentText("Pix")
            QTest.qWait(60)
            self.assertGreater(dialogo.height(), altura + 150, "o QR inteiro a vista")
            self.assertEqual(dialogo._area.verticalScrollBar().maximum(), 0)
            x, y = self._centro(dialogo)
            self.assertLessEqual(abs(x - centro[0]) + abs(y - centro[1]), 4,
                                 "cresce para os dois lados, nao so para baixo")

            dialogo.forma.setCurrentText("Dinheiro")
            QTest.qWait(60)
            self.assertEqual(dialogo.height(), altura)
            self.assertEqual(_problemas(dialogo, MONITOR), [])

    def test_formulario_que_ganha_campo_cresce_centrado(self) -> None:
        from dumtech.ui.widgets import form

        class Formulario(form.FormDialog):
            def __init__(self) -> None:
                super().__init__("Teste", "", None, largura=480)
                self.add_row("Nome", form.texto("", ""))
                self.extra = QLabel("campo que aparece depois")
                self.extra.setFixedHeight(220)
                self.extra.setVisible(False)
                self.extras.addWidget(self.extra)

            def salvar(self) -> None:
                return None

        dialogo = Formulario()
        self.addCleanup(dialogo.deleteLater)
        self.addCleanup(dialogo.close)
        with _na_tela(MONITOR):
            dialogo.show()
            QTest.qWait(40)
            altura, centro = dialogo.height(), self._centro(dialogo)
            dialogo.extra.setVisible(True)
            QTest.qWait(60)
            self.assertGreaterEqual(dialogo.height(), altura + 200)
            x, y = self._centro(dialogo)
            self.assertLessEqual(abs(x - centro[0]) + abs(y - centro[1]), 4)
            dialogo.extra.setVisible(False)
            QTest.qWait(60)
            self.assertEqual(dialogo.height(), altura)

    def test_tamanho_escolhido_pela_pessoa_fica(self) -> None:
        """Quem puxou a borda nao ve a janela voltar sozinha ao tamanho de antes."""
        from dumtech.ui.widgets import form

        class Formulario(form.FormDialog):
            def __init__(self) -> None:
                super().__init__("Teste", "", None, largura=480)
                self.add_row("Nome", form.texto("", ""))
                self.aviso = QLabel("")
                self.extras.addWidget(self.aviso)

            def salvar(self) -> None:
                return None

        dialogo = Formulario()
        self.addCleanup(dialogo.deleteLater)
        self.addCleanup(dialogo.close)
        with _na_tela(MONITOR):
            dialogo.show()
            QTest.qWait(40)
            escolhido = dialogo.size() + QSize(120, 160)
            dialogo.resize(escolhido)
            QTest.qWait(40)
            dialogo.aviso.setText("Algo mudou\nem duas linhas")
            QTest.qWait(60)
            self.assertEqual(dialogo.size(), escolhido)

    def test_dialogo_sem_rolagem_tambem_cresce_centrado(self) -> None:
        from PySide6.QtWidgets import QVBoxLayout

        from dumtech.ui.theme import apply_window_theme, palette_for

        dialogo = QDialog()
        self.addCleanup(dialogo.deleteLater)
        self.addCleanup(dialogo.close)
        coluna = QVBoxLayout(dialogo)
        coluna.addWidget(QLabel("Sempre aqui"))
        extra = QLabel("aparece depois")
        extra.setFixedHeight(240)
        extra.setVisible(False)
        coluna.addWidget(extra)
        apply_window_theme(dialogo, palette_for(None))
        with _na_tela(MONITOR):
            dialogo.show()
            QTest.qWait(40)
            # no meio da tela, como sobre o Hub: colada na borda, crescer em
            # volta do centro a jogaria para fora - e ai caber vem primeiro
            dialogo.move(800, 400)
            QTest.qWait(20)
            centro = self._centro(dialogo)
            extra.setVisible(True)
            QTest.qWait(60)
            self.assertGreaterEqual(dialogo.height(), 240)
            x, y = self._centro(dialogo)
            self.assertLessEqual(abs(x - centro[0]) + abs(y - centro[1]), 4)

    def test_aviso_nao_encolhe_janela_que_abriu_grande(self) -> None:
        from dumtech.ui.widgets.comprovante import ComprovanteDialog

        dialogo = ComprovanteDialog("Linha")
        self.addCleanup(dialogo.deleteLater)
        self.addCleanup(dialogo.close)
        with _na_tela(MONITOR):
            dialogo.resize(700, 800)
            dialogo.show()
            QTest.qWait(40)
            tamanho = dialogo.size()
            dialogo._dizer("Comprovante copiado.", "success")
            QTest.qWait(60)
            self.assertEqual(dialogo.size(), tamanho)

    def test_janela_que_ja_cabe_fica_onde_estava(self) -> None:
        from dumtech.ui.tela import caber_na_tela
        from dumtech.ui.widgets.confirmar import ConfirmarDialog

        dialogo = ConfirmarDialog("Excluir?", "Tem certeza?")
        self.addCleanup(dialogo.deleteLater)
        dialogo.resize(430, 160)
        dialogo.move(200, 150)
        with _na_tela(NOTEBOOK):
            caber_na_tela(dialogo)
        self.assertEqual((dialogo.x(), dialogo.y(), dialogo.width(), dialogo.height()),
                         (200, 150, 430, 160))


class InstaladorTestCase(unittest.TestCase):
    """A atualizacao pelo Hub so mexe nos arquivos depois que ele os soltou.

    Sem a espera, o instalador apagava _internal com o Hub ainda fechando - e
    o programa nao abria mais ("Failed to load Python DLL"). O teste de verdade
    foi feito instalando por cima de uma copia em uso; aqui fica a guarda de
    que a espera continua no script.
    """

    def setUp(self) -> None:
        raiz = Path(__file__).resolve().parents[1]
        self.script = (raiz / "build" / "instalador.iss").read_text(encoding="utf-8")

    def test_espera_o_hub_soltar_antes_de_instalar(self) -> None:
        self.assertIn("function PrepareToInstall", self.script)
        self.assertIn("EsperarSoltar(ESPERA_MAXIMA)", self.script)
        self.assertIn("python311.dll", self.script)

    def test_so_encerra_o_hub_desta_pasta(self) -> None:
        self.assertNotIn("/IM", self.script)
        self.assertIn("$_.Path -eq", self.script)

    def test_mostra_que_esta_atualizando_e_guarda_log(self) -> None:
        self.assertIn("Atualizando o DumTech Hub", self.script)
        self.assertIn("SetupLogging=yes", self.script)


if __name__ == "__main__":
    unittest.main()
