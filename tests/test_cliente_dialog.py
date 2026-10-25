"""O cadastro de cliente por dentro: data em dd/mm/aaaa e CEP que preenche."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from dumtech.apps.clientes.ui.cliente_dialog import ClienteDialog
from dumtech.core import cep as nucleo_cep
from dumtech.core.contacts import Contato, ContactsStore

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class ClienteDialogTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.store = ContactsStore(Path(tempfile.mkdtemp()) / "plataforma.db")
        nucleo_cep.esquecer()

    def tearDown(self) -> None:
        self.store.close()

    def _dialogo(self, contato: Contato | None = None) -> ClienteDialog:
        dialogo = ClienteDialog(self.store, contato)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    # ------------------------------------------------------------ nascimento
    def test_o_aniversario_e_escrito_como_todo_mundo_escreve(self) -> None:
        dialogo = self._dialogo()
        dialogo.nascimento.setText("")
        dialogo.nascimento._pontuar("07031990")
        self.assertEqual(dialogo.nascimento.text(), "07/03/1990")
        self.assertEqual(dialogo.nascimento.iso(), "1990-03-07")

    def test_o_que_estava_guardado_aparece_em_dd_mm_aaaa(self) -> None:
        contato = self.store.criar(Contato(nome="Joao", nascimento="1990-03-07"))
        dialogo = self._dialogo(contato)
        self.assertEqual(dialogo.nascimento.text(), "07/03/1990")

    def test_sem_aniversario_continua_sem_aniversario(self) -> None:
        """Um QDateEdit inventaria 'hoje'; em branco tem de sair em branco."""
        dialogo = self._dialogo()
        self.assertEqual(dialogo.nascimento.text(), "")
        self.assertEqual(dialogo.nascimento.iso(), "")
        dialogo.nome.setText("Sem aniversario")
        dialogo.salvar()
        self.assertEqual(self.store.listar()[0].nascimento, "")

    def test_a_data_digitada_chega_no_banco_como_iso(self) -> None:
        dialogo = self._dialogo()
        dialogo.nome.setText("Joao da Silva")
        dialogo.nascimento._pontuar("07031990")
        dialogo.salvar()
        self.assertEqual(self.store.listar()[0].nascimento, "1990-03-07")

    # -------------------------------------------------------------------- CEP
    def test_o_cep_se_formata_sozinho_e_busca_ao_fechar(self) -> None:
        dialogo = self._dialogo()
        procurados = []
        with mock.patch.object(nucleo_cep, "buscar",
                               side_effect=lambda c: procurados.append(c)):
            dialogo.cep.setText("01001")
            dialogo._cep_mudou("01001")
            self.assertEqual(dialogo.cep.text(), "01001")
            self.assertEqual(procurados, [])      # ainda nao fechou oito digitos

            dialogo.cep.setText("01001000")
            dialogo._cep_mudou("01001000")
            self.assertEqual(dialogo.cep.text(), "01001-000")
            QThreadPool.globalInstance().waitForDone(2000)
            QApplication.processEvents()
        self.assertEqual(procurados, ["01001-000"])

    def test_o_endereco_chega_pelo_cep(self) -> None:
        dialogo = self._dialogo()
        dialogo._preencher_endereco(nucleo_cep.Endereco(
            cep="01001-000", logradouro="Praca da Se", bairro="Se",
            cidade="Sao Paulo", uf="SP"))
        self.assertEqual(dialogo.endereco.text(), "Praca da Se")
        self.assertEqual(dialogo.bairro.text(), "Se")
        self.assertEqual(dialogo.cidade.currentText(), "Sao Paulo")
        self.assertEqual(dialogo.uf.currentData(), "SP")

    def test_cep_nao_encontrado_so_avisa(self) -> None:
        dialogo = self._dialogo()
        dialogo._preencher_endereco(None)
        self.assertIn("Não achei", dialogo.dica_cep.text())
        self.assertEqual(dialogo.endereco.text(), "")


if __name__ == "__main__":
    unittest.main()
