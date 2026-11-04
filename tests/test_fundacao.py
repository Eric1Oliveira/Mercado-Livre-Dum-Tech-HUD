"""O que sustenta o resto: migracao tudo ou nada, transacao aninhada, um Hub so."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication

from dumtech.core.database import Database, MigracaoError, Migration
from dumtech.main import travar_instancia

BASE = Migration(1, "base", ("CREATE TABLE a (id INTEGER PRIMARY KEY, nome TEXT);",))


class MigracaoTudoOuNada(unittest.TestCase):
    def setUp(self) -> None:
        self.arquivo = Path(tempfile.mkdtemp(prefix="dt_mig_")) / "x.db"

    def _abrir(self, *migracoes) -> Database:
        banco = Database(self.arquivo, migracoes)
        self.addCleanup(banco.close)
        banco.connection
        return banco

    def test_falha_no_meio_nao_deixa_nada_e_a_corrigida_passa(self) -> None:
        banco = self._abrir(BASE)
        banco.execute("INSERT INTO a (nome) VALUES ('Ana')")
        banco.close()

        com_defeito = Migration(2, "nova", (
            "CREATE TABLE b (id INTEGER); ALTER TABLE a ADD COLUMN extra TEXT;",
            "INSERT INTO tabela_que_nao_existe VALUES (1);",
        ))
        with self.assertRaises(MigracaoError) as erro:
            Database(self.arquivo, (BASE, com_defeito)).connection
        self.assertIn("Nada foi perdido", str(erro.exception))

        corrigida = Migration(2, "nova", (
            "CREATE TABLE b (id INTEGER); ALTER TABLE a ADD COLUMN extra TEXT;",
        ))
        banco = self._abrir(BASE, corrigida)
        self.assertEqual(banco.schema_version, 2)
        self.assertEqual(banco.scalar("SELECT nome FROM a"), "Ana")

    def test_falha_nao_entrega_banco_sem_atualizar(self) -> None:
        self._abrir(BASE).close()
        banco = Database(self.arquivo, (BASE, Migration(2, "x", ("isso nao e sql",))))
        for _ in range(2):
            with self.assertRaises(MigracaoError):
                banco.connection

    def test_reconstruir_tabela_nao_apaga_as_filhas(self) -> None:
        filhas = Migration(1, "base", ("""
            CREATE TABLE pai (id INTEGER PRIMARY KEY, nome TEXT);
            CREATE TABLE filha (id INTEGER PRIMARY KEY,
                                pai_id INTEGER REFERENCES pai(id) ON DELETE CASCADE);
        """,))
        banco = self._abrir(filhas)
        banco.execute("INSERT INTO pai VALUES (1, 'x')")
        banco.execute("INSERT INTO filha VALUES (1, 1)")
        banco.close()
        refazer = Migration(2, "refaz", ("""
            CREATE TABLE pai_v2 (id INTEGER PRIMARY KEY, nome TEXT, extra TEXT);
            INSERT INTO pai_v2 (id, nome) SELECT id, nome FROM pai;
            DROP TABLE pai;
            ALTER TABLE pai_v2 RENAME TO pai;
        """,))
        banco = self._abrir(filhas, refazer)
        self.assertEqual(banco.scalar("SELECT COUNT(*) FROM filha"), 1)

    def test_guarda_copia_antes_e_so_a_ultima(self) -> None:
        self._abrir(BASE).close()
        v2 = Migration(2, "dois", ("CREATE TABLE b (id INTEGER);",))
        self._abrir(BASE, v2).close()
        self.assertTrue(self.arquivo.with_name("x.db.antes-v1.bak").exists())
        v3 = Migration(3, "tres", ("CREATE TABLE c (id INTEGER);",))
        self._abrir(BASE, v2, v3).close()
        copias = sorted(p.name for p in self.arquivo.parent.glob("*.bak"))
        self.assertEqual(copias, ["x.db.antes-v2.bak"])

    def test_banco_novo_nao_gera_copia(self) -> None:
        self._abrir(BASE).close()
        self.assertEqual(list(self.arquivo.parent.glob("*.bak")), [])


class TransacaoAninhada(unittest.TestCase):
    def setUp(self) -> None:
        arquivo = Path(tempfile.mkdtemp(prefix="dt_tx_")) / "x.db"
        self.banco = Database(arquivo, (BASE,))
        self.addCleanup(self.banco.close)
        self.espiao = None

    def _no_disco(self) -> int:
        conn = sqlite3.connect(self.banco.path)
        try:
            return conn.execute("SELECT COUNT(*) FROM a").fetchone()[0]
        finally:
            conn.close()

    def test_o_bloco_de_dentro_nao_grava_sozinho(self) -> None:
        with self.banco.transaction():
            self.banco.execute("INSERT INTO a (nome) VALUES ('1')")
            self.assertEqual(self._no_disco(), 0)
        self.assertEqual(self._no_disco(), 1)

    def test_erro_desfaz_tudo(self) -> None:
        with self.assertRaises(ValueError):
            with self.banco.transaction():
                self.banco.execute("INSERT INTO a (nome) VALUES ('1')")
                raise ValueError
        self.assertEqual(self.banco.scalar("SELECT COUNT(*) FROM a"), 0)
        # e a contagem volta ao normal: a proxima escrita grava
        self.banco.execute("INSERT INTO a (nome) VALUES ('2')")
        self.assertEqual(self._no_disco(), 1)


class UmHubSo(unittest.TestCase):
    def test_o_segundo_nao_abre_e_depois_de_fechar_abre(self) -> None:
        QCoreApplication.instance() or QCoreApplication([])
        pasta = Path(tempfile.mkdtemp(prefix="dt_trava_"))
        primeira = travar_instancia(pasta, espera_ms=50)
        self.assertIsNotNone(primeira)
        self.assertIsNone(travar_instancia(pasta, espera_ms=50))
        primeira.unlock()
        segunda = travar_instancia(pasta, espera_ms=50)
        self.assertIsNotNone(segunda)
        segunda.unlock()


if __name__ == "__main__":
    unittest.main()
