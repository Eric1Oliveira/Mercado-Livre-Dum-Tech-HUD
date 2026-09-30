"""O autocompletar: casa no meio da palavra e nao briga com acento."""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication

from dumtech.ui.widgets import form

_app: QApplication | None = None

NOMES = [
    "Mercado Sao Joao",
    "Padaria Sao Jose",
    "Acougue Central",
    "Teclado e mouse sem fio",
    "Joao da Silva",
]


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def _casam(sugestoes: form.Sugestoes, termo: str) -> list[str]:
    sugestoes.filtro.procurar(termo)
    modelo = sugestoes.filtro
    return [modelo.index(linha, 0).data() for linha in range(modelo.rowCount())]


class SugestoesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.sugestoes = form.Sugestoes(NOMES)

    def test_casa_no_meio_da_palavra(self) -> None:
        """"mouse" tem de achar "Teclado e mouse sem fio" - nao so o comeco."""
        self.assertEqual(_casam(self.sugestoes, "mouse"), ["Teclado e mouse sem fio"])

    def test_ignora_maiuscula(self) -> None:
        self.assertEqual(_casam(self.sugestoes, "PADARIA"), ["Padaria Sao Jose"])

    def test_ignora_acento_dos_dois_lados(self) -> None:
        sugestoes = form.Sugestoes(["Açougue Central", "João da Silva"])
        self.assertEqual(_casam(sugestoes, "acougue"), ["Açougue Central"])
        self.assertEqual(_casam(sugestoes, "joao"), ["João da Silva"])
        self.assertEqual(_casam(sugestoes, "JOÃO"), ["João da Silva"])

    def test_sem_nada_digitado_mostra_tudo(self) -> None:
        self.assertEqual(len(_casam(self.sugestoes, "")), len(NOMES))

    def test_o_que_nao_existe_nao_sugere(self) -> None:
        self.assertEqual(_casam(self.sugestoes, "zzz"), [])

    def test_a_lista_pode_mudar_com_a_janela_aberta(self) -> None:
        """Cliente cadastrado agora aparece sem fechar e reabrir a tela."""
        self.sugestoes.definir(["Cliente novo"])
        self.assertEqual(_casam(self.sugestoes, "novo"), ["Cliente novo"])

    def test_campo_de_texto_nasce_com_o_autocompletar(self) -> None:
        campo = form.sugestao("", "Cliente", NOMES)
        self.assertIsInstance(campo.completer(), form.Sugestoes)

    def test_campo_sem_opcoes_nao_quebra(self) -> None:
        campo = form.sugestao("", "Cliente", [])
        self.assertEqual(_casam(campo.completer(), "qualquer"), [])

    def test_combo_aceita_digitar_e_sugere(self) -> None:
        combo = form.combo_sugestao("Perifericos", ["Perifericos", "Papelaria"], "Ex.")
        self.assertTrue(combo.isEditable())
        self.assertEqual(combo.currentText(), "Perifericos")
        self.assertEqual(_casam(combo.completer(), "pap"), ["Papelaria"])

    def test_combo_nao_cria_item_sozinho_ao_digitar(self) -> None:
        """Digitar uma categoria nova nao pode empurrar item na lista do banco."""
        combo = form.combo_sugestao("", ["Papelaria"], "Ex.")
        antes = combo.count()
        combo.setCurrentText("Categoria inedita")
        self.assertEqual(combo.count(), antes)
        self.assertEqual(combo.currentText(), "Categoria inedita")


class CampoDataTestCase(unittest.TestCase):
    def test_escreve_as_barras_sozinho(self) -> None:
        campo = form.data_opcional()
        campo._pontuar("31121999")
        self.assertEqual(campo.text(), "31/12/1999")
        self.assertEqual(campo.iso(), "1999-12-31")

    def test_aceita_data_incompleta_sem_atrapalhar(self) -> None:
        campo = form.data_opcional()
        campo._pontuar("3112")
        self.assertEqual(campo.text(), "31/12")
        self.assertEqual(campo.iso(), "31/12")   # quem valida reclama, nao aqui

    def test_vazio_continua_vazio(self) -> None:
        self.assertEqual(form.data_opcional("").iso(), "")


if __name__ == "__main__":
    unittest.main()
