"""O campo de dinheiro.

A reclamacao que originou isto: "nao quero ter que apagar o R$ 0,00 para
escrever o valor, e se eu escrever 1000 tem que virar R$ 1.000,00".
"""

from __future__ import annotations

import unittest

from dumtech.ui import format as fmt

_app = None


def setUpModule() -> None:
    global _app
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])


class LeituraTestCase(unittest.TestCase):
    """`fmt.para_numero` - texto puro, sem Qt."""

    def test_o_jeito_brasileiro_de_escrever(self) -> None:
        casos = {
            "1000": 1000.0,
            "1.000": 1000.0,
            "1.000,50": 1000.5,
            "1000,5": 1000.5,
            "R$ 1.234,56": 1234.56,
            "R$ 0,00": 0.0,
            "12": 12.0,
            "1.234.567,89": 1234567.89,
        }
        for texto, esperado in casos.items():
            with self.subTest(texto):
                self.assertEqual(fmt.para_numero(texto), esperado)

    def test_ponto_com_tres_casas_e_milhar(self) -> None:
        """"1.000" e mil - a duvida classica de quem digita numero."""
        self.assertEqual(fmt.para_numero("1.000"), 1000.0)
        self.assertEqual(fmt.para_numero("1.50"), 1.5)

    def test_o_ultimo_separador_manda(self) -> None:
        self.assertEqual(fmt.para_numero("1.234,56"), 1234.56)
        self.assertEqual(fmt.para_numero("1,234.56"), 1234.56)

    def test_negativo_e_lixo(self) -> None:
        self.assertEqual(fmt.para_numero("-250,10"), -250.1)
        self.assertEqual(fmt.para_numero("abc"), 0.0)
        self.assertEqual(fmt.para_numero(""), 0.0)
        self.assertEqual(fmt.para_numero(None), 0.0)

    def test_o_que_sai_volta_igual(self) -> None:
        """O texto que o programa escreve, o programa le de volta."""
        for valor in (0.0, 12.0, 1000.0, 1234.56, 1234567.89):
            with self.subTest(valor):
                self.assertEqual(fmt.para_numero(fmt.moeda(valor)), valor)


class CampoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from dumtech.ui.widgets import form

        self.campo = form.dinheiro()

    def digitar(self, texto: str) -> float:
        """Como quem digita por cima do que estava la."""
        self.campo.lineEdit().setText(texto)
        self.campo.interpretText()
        return self.campo.value()

    def test_comeca_formatado(self) -> None:
        self.assertEqual(self.campo.text(), "R$ 0,00")

    def test_mil_vira_mil_reais(self) -> None:
        self.assertEqual(self.digitar("1000"), 1000.0)
        self.assertEqual(self.campo.text(), "R$ 1.000,00")

    def test_aceita_o_valor_ja_formatado(self) -> None:
        """Colar "R$ 1.000,50" no campo tem que funcionar."""
        self.assertEqual(self.digitar("R$ 1.000,50"), 1000.5)
        self.assertEqual(self.campo.text(), "R$ 1.000,50")

    def test_escrever_por_cima_sem_apagar(self) -> None:
        """Campo com R$ 250,00: seleciona tudo, digita 3000, e sao 3 mil reais."""
        self.campo.setValue(250.0)
        self.assertEqual(self.digitar("R$ 3000"), 3000.0)
        self.assertEqual(self.campo.text(), "R$ 3.000,00")

    def test_milhar_com_separador_na_exibicao(self) -> None:
        self.campo.setValue(1234567.89)
        self.assertEqual(self.campo.text(), "R$ 1.234.567,89")

    def test_o_foco_seleciona_tudo(self) -> None:
        """E o que dispensa apagar antes de digitar."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFocusEvent

        self.campo.setValue(90.0)
        self.campo.focusInEvent(QFocusEvent(QFocusEvent.Type.FocusIn,
                                            Qt.FocusReason.MouseFocusReason))
        _app.processEvents()
        self.assertTrue(self.campo.lineEdit().hasSelectedText())

    def test_quantidade_tambem_aceita_digitar_por_cima(self) -> None:
        from dumtech.ui.widgets import form

        campo = form.quantidade(1, casas=3)
        campo.lineEdit().setText("2,5")
        campo.interpretText()
        self.assertEqual(campo.value(), 2.5)


if __name__ == "__main__":
    unittest.main()
