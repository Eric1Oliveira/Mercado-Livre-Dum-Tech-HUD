"""A licenca acabou, os dados nao: da para ver e exportar, nunca para gravar."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dumtech.apps.vendas.database import open_database as abrir_vendas
from dumtech.apps.vendas.models import ItemVenda, Venda
from dumtech.apps.vendas import module as modulo_vendas
from dumtech.apps.vendas.module import MANIFEST as MANIFESTO_VENDAS
from dumtech.apps.vendas.repository import VendasRepository, pagamento_unico
from dumtech.core.database import SO_CONSULTA, Database, e_so_consulta
from dumtech.core.paths import DataPaths
from dumtech.hub.launcher import AppLauncher

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class Licenca:
    def __init__(self, *liberados: str) -> None:
        self.liberados = set(liberados)

    def allows(self, app_id: str) -> bool:
        return app_id in self.liberados


class Entrada:
    def __init__(self, manifesto) -> None:
        self.manifest = manifesto
        self.app_id = manifesto.app_id
        self.create_window = modulo_vendas.create_window


class Registro:
    def __init__(self, licenca: Licenca) -> None:
        self.license_service = licenca
        self.acesso = None
        self.entrada = Entrada(MANIFESTO_VENDAS)

    def get(self, app_id: str):
        return self.entrada if app_id == "vendas" else None

    def locked(self):
        return [] if self.license_service.allows("vendas") else [self.entrada]


class BancoSoLeitura(unittest.TestCase):
    def setUp(self) -> None:
        self.caminho = Path(tempfile.mkdtemp(prefix="dt_ro_")) / "vendas.db"
        banco = abrir_vendas(self.caminho)
        VendasRepository(banco).finalizar(
            Venda(itens=[ItemVenda(descricao="x", valor_unitario=10.0)]),
            [pagamento_unico("Pix", 10.0)],
        )
        banco.close()
        Database.so_leitura.add(self.caminho)
        self.addCleanup(Database.so_leitura.discard, self.caminho)
        self.banco = abrir_vendas(self.caminho)
        self.addCleanup(self.banco.close)
        self.repo = VendasRepository(self.banco)

    def test_le_tudo(self) -> None:
        self.assertEqual(len(self.repo.listar()), 1)
        self.assertEqual(self.repo.resumo().total_mes, 10.0)

    def test_nao_grava_nada(self) -> None:
        with self.assertRaises(sqlite3.OperationalError) as erro:
            self.repo.finalizar(Venda(itens=[ItemVenda(descricao="y", valor_unitario=5.0)]),
                                [pagamento_unico("Pix", 5.0)])
        self.assertTrue(e_so_consulta(erro.exception))
        self.assertEqual(len(self.repo.listar()), 1)

    def test_migracao_pendente_ainda_roda(self) -> None:
        self.assertEqual(self.banco.schema_version, self.banco._migrations[-1].version)


class AbrirEmConsulta(unittest.TestCase):
    def setUp(self) -> None:
        raiz = Path(tempfile.mkdtemp(prefix="dt_con_"))
        self.paths = DataPaths(root=raiz).ensure()
        fonte = mock.patch("dumtech.core.paths.get_paths", return_value=self.paths)
        fonte.start()
        self.addCleanup(fonte.stop)
        self.licenca = Licenca()
        hub_store = mock.Mock()
        self.launcher = AppLauncher(Registro(self.licenca), hub_store)
        self.launcher.notify = mock.Mock()
        self.addCleanup(self.launcher.close_all)

    def _com_dados(self) -> None:
        banco = abrir_vendas(self.paths.app_db("vendas"))
        VendasRepository(banco).finalizar(
            Venda(itens=[ItemVenda(descricao="x", valor_unitario=10.0)]),
            [pagamento_unico("Pix", 10.0)],
        )
        banco.close()

    def test_sem_dados_continua_bloqueado(self) -> None:
        self.assertFalse(self.launcher.consultavel("vendas"))
        self.assertIsNone(self.launcher.open("vendas"))
        self.launcher.notify.assert_called_once()

    def test_com_dados_abre_avisa_e_nao_grava(self) -> None:
        self._com_dados()
        self.assertEqual([e.app_id for e in self.launcher.consultaveis()], ["vendas"])
        casca = self.launcher.open("vendas")
        self.assertIsNotNone(casca)
        self.assertTrue(casca.context.so_consulta)
        self.assertTrue(self.launcher.em_consulta("vendas"))
        self.assertIsNone(casca.context.contas)
        self.assertTrue(casca.vendas_view.botao_novo.isHidden())
        with self.assertRaises(sqlite3.OperationalError):
            casca.repository.abrir_caixa(0.0)

    def test_renovar_fecha_a_consulta_e_destrava_o_banco(self) -> None:
        self._com_dados()
        self.launcher.open("vendas")
        self.licenca.liberados.add("vendas")
        self.launcher.close_blocked()
        self.assertFalse(self.launcher.em_consulta("vendas"))
        self.assertNotIn(self.paths.app_db("vendas"), Database.so_leitura)
        casca = self.launcher.open("vendas")
        casca.repository.abrir_caixa(0.0)
        self.assertIsNotNone(casca.repository.caixa_aberto())

    def test_consulta_nao_fecha_sozinha_com_a_licenca_igual(self) -> None:
        self._com_dados()
        self.launcher.open("vendas")
        self.launcher.close_blocked()
        self.assertIn("vendas", self.launcher.open_apps)


class Mensagem(unittest.TestCase):
    def test_recado_que_a_pessoa_entende(self) -> None:
        self.assertIn("modo consulta", SO_CONSULTA)
        self.assertFalse(e_so_consulta(ValueError("readonly")))


if __name__ == "__main__":
    unittest.main()
