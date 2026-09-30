"""Erro inesperado: o relatorio que o suporte recebe e a caixa que o cliente ve."""

from __future__ import annotations

import logging
import sys
import unittest

from dumtech.core.diagnostico import onde, relatorio, resumo


def _estourar(mensagem: str = "coisa ruim") -> BaseException:
    """Levanta e devolve o erro ja com traceback de verdade."""
    try:
        raise ValueError(mensagem)
    except ValueError as erro:
        return erro


class RelatorioTestCase(unittest.TestCase):
    def test_o_resumo_e_uma_linha(self) -> None:
        self.assertEqual(resumo(_estourar()), "ValueError: coisa ruim")
        self.assertEqual(
            resumo(_estourar("primeira linha\nsegunda linha")),
            "ValueError: primeira linha",
        )

    def test_resumo_de_erro_sem_mensagem(self) -> None:
        try:
            raise RuntimeError
        except RuntimeError as erro:
            self.assertEqual(resumo(erro), "RuntimeError")

    def test_diz_o_arquivo_e_a_linha(self) -> None:
        """E a primeira coisa que o suporte pergunta."""
        local = onde(_estourar())
        self.assertIn("test_erros.py", local)
        self.assertIn("linha", local)
        self.assertIn("_estourar()", local)

    def test_erro_sem_traceback_nao_quebra(self) -> None:
        self.assertEqual(onde(ValueError("solto")), "origem desconhecida")

    def test_o_relatorio_tem_o_que_o_suporte_precisa(self) -> None:
        texto = relatorio(_estourar(), versao="2.0.0", contexto="abrindo o Estoque")

        self.assertIn("DumTech Hub - relatorio de erro", texto)
        self.assertIn("2.0.0", texto)
        self.assertIn("abrindo o Estoque", texto)
        self.assertIn("ValueError: coisa ruim", texto)
        self.assertIn("test_erros.py", texto)
        self.assertIn("Traceback (most recent call last)", texto)

    def test_o_relatorio_funciona_sem_versao(self) -> None:
        self.assertIn("desconhecida", relatorio(_estourar()))


class GanchoTestCase(unittest.TestCase):
    """O gancho instalado em `sys.excepthook`."""

    def setUp(self) -> None:
        self.anterior = sys.excepthook
        self.addCleanup(lambda: setattr(sys, "excepthook", self.anterior))

    def test_instalar_troca_o_excepthook(self) -> None:
        from dumtech.ui import erros

        erros.instalar("1.0")
        self.assertIsNot(sys.excepthook, self.anterior)

    def _sem_abrir_caixa(self) -> list:
        """Troca a caixa de erro por um espiao.

        Sem isto o teste so passa enquanto nao existir uma QApplication viva -
        e no dia em que existir, `exec()` abre a janela e a suite trava. O que
        interessa aqui e o que foi registrado, nao a janela.
        """
        from dumtech.ui import erros

        mostradas = []

        class Espia:
            def __init__(self, *args) -> None:
                mostradas.append(args)

            def exec(self) -> int:
                return 0

        original = erros.ErroDialog
        erros.ErroDialog = Espia
        self.addCleanup(lambda: setattr(erros, "ErroDialog", original))
        return mostradas

    def test_com_janela_viva_o_erro_vira_caixa(self) -> None:
        """Sem QApplication so resta o log; com ela, o usuario ve o que houve."""
        from PySide6.QtWidgets import QApplication

        from dumtech.ui import erros

        QApplication.instance() or QApplication([])
        mostradas = self._sem_abrir_caixa()

        erros.tratar(_estourar("falhou feio"), versao="2.0.0")
        self.assertEqual(len(mostradas), 1)

    def test_o_erro_vai_para_o_log(self) -> None:
        from dumtech.ui import erros

        self._sem_abrir_caixa()
        with self.assertLogs("dumtech.ui.erros", level=logging.ERROR) as capturado:
            texto = erros.tratar(_estourar("falhou feio"), versao="2.0.0")

        registro = "\n".join(capturado.output)
        self.assertIn("Erro nao tratado", registro)
        self.assertIn("falhou feio", registro)
        self.assertIn("falhou feio", texto)

    def test_ctrl_c_continua_encerrando_o_programa(self) -> None:
        """KeyboardInterrupt nao e bug: nao pode virar caixa de erro."""
        from dumtech.ui import erros

        recebidos = []
        sys.excepthook = lambda *args: recebidos.append(args[0])
        erros.instalar("1.0")

        sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
        self.assertEqual(recebidos, [KeyboardInterrupt])

    def test_sem_janela_o_erro_so_e_registrado(self) -> None:
        """Erro antes da tela existir nao pode tentar abrir caixa nenhuma."""
        from dumtech.ui import erros

        # a ausencia de aplicacao tem que ser encenada: outros arquivos da suite
        # deixam uma QApplication viva, e ai a caixa abriria de verdade
        class SemAplicacao:
            @staticmethod
            def instance():
                return None

        original = erros.QApplication
        erros.QApplication = SemAplicacao
        self.addCleanup(lambda: setattr(erros, "QApplication", original))
        espia = self._sem_abrir_caixa()

        with self.assertLogs("dumtech.ui.erros", level=logging.ERROR):
            texto = erros.tratar(_estourar("na abertura"))
        self.assertIn("na abertura", texto)
        self.assertEqual(espia, [])  # nenhuma caixa foi montada

    def test_um_erro_em_cascata_nao_vira_vinte_janelas(self) -> None:
        from dumtech.ui import erros

        erros._mostrando = True
        self.addCleanup(setattr, erros, "_mostrando", False)
        with self.assertLogs("dumtech.ui.erros", level=logging.ERROR):
            erros.tratar(_estourar("o segundo erro"))
        # registrado, mas sem tentar abrir outra caixa por cima


if __name__ == "__main__":
    unittest.main()
