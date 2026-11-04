"""A copia de seguranca: o que protege o cliente de perder um ano de trabalho."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from dumtech.core import backup
from dumtech.core.backup import Backup, BackupError
from dumtech.core.paths import DataPaths


class BackupBase(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = DataPaths(root=Path(tempfile.mkdtemp(prefix="dt_bkp_"))).ensure()
        self.destino = Path(tempfile.mkdtemp(prefix="dt_dest_"))

    def _banco(self, caminho: Path, linhas: int = 3) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(caminho)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS coisas (id INTEGER, nome TEXT)")
        conn.executemany(
            "INSERT INTO coisas VALUES (?, ?)",
            [(i, f"linha {i}") for i in range(linhas)],
        )
        conn.commit()
        conn.close()

    def _plataforma(self) -> None:
        """Um Hub com dados: o banco do Hub, o compartilhado e dois aplicativos."""
        self._banco(self.paths.hub_db)
        self._banco(self.paths.platform_db)
        self._banco(self.paths.app_db("estoque"), linhas=5)
        self._banco(self.paths.app_db("vendas"), linhas=7)
        self.paths.settings_file.write_text('{"hub": {}}', encoding="utf-8")

    def _contar(self, caminho: Path) -> int:
        conn = sqlite3.connect(caminho)
        try:
            return conn.execute("SELECT COUNT(*) FROM coisas").fetchone()[0]
        finally:
            conn.close()


class CriarTestCase(BackupBase):
    def test_o_zip_leva_todos_os_bancos_e_a_configuracao(self) -> None:
        self._plataforma()
        copia = backup.criar(self.destino, self.paths, versao="1.0.0")

        self.assertTrue(copia.arquivo.exists())
        self.assertGreater(copia.tamanho, 0)
        with zipfile.ZipFile(copia.arquivo) as pacote:
            dentro = set(pacote.namelist())
        self.assertEqual(
            dentro,
            {
                "backup.json",
                "data/hub.db",
                "data/plataforma.db",
                "data/estoque.db",
                "data/vendas.db",
                "config/hub.json",
            },
        )

    def test_a_licenca_nao_vai_junto(self) -> None:
        """Licenca e amarrada a maquina: restaurar em outro PC so confunde."""
        self._plataforma()
        self.paths.license_file.write_text('{"key": "ABC"}', encoding="utf-8")

        copia = backup.criar(self.destino, self.paths)
        with zipfile.ZipFile(copia.arquivo) as pacote:
            self.assertNotIn("config/license.json", pacote.namelist())

    def test_copia_o_que_esta_no_wal_e_nao_so_no_arquivo(self) -> None:
        """O teste que justifica usar a API do SQLite em vez de copiar o .db."""
        banco = self.paths.app_db("estoque")
        self._banco(banco, linhas=2)

        # conexao aberta, sem checkpoint: as linhas novas vivem no -wal
        conn = sqlite3.connect(banco)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executemany(
            "INSERT INTO coisas VALUES (?, ?)", [(90 + i, "no wal") for i in range(4)]
        )
        conn.commit()
        try:
            self.assertTrue(Path(f"{banco}-wal").exists(), "o teste precisa de um WAL")
            copia = backup.criar(self.destino, self.paths)
        finally:
            conn.close()

        restaurado = Path(tempfile.mkdtemp()) / "estoque.db"
        with zipfile.ZipFile(copia.arquivo) as pacote, open(restaurado, "wb") as saida:
            saida.write(pacote.read("data/estoque.db"))
        self.assertEqual(self._contar(restaurado), 6)

    def test_sem_dado_nenhum_avisa_em_vez_de_gravar_zip_vazio(self) -> None:
        with self.assertRaises(BackupError):
            backup.criar(self.destino, self.paths)

    def test_o_manifesto_diz_o_que_tem_dentro(self) -> None:
        self._plataforma()
        copia = backup.criar(self.destino, self.paths, automatico=True, versao="2.0")

        lido = backup.ler_manifesto(copia.arquivo)
        self.assertTrue(lido.automatico)
        self.assertEqual(lido.versao, "2.0")
        self.assertIn("estoque.db", lido.bancos)
        self.assertIsNotNone(lido.momento)

    def test_arquivo_que_nao_e_backup_e_recusado(self) -> None:
        intruso = self.destino / "dumtech-backup-falso.zip"
        intruso.write_bytes(b"nao sou um zip")
        with self.assertRaises(BackupError):
            backup.ler_manifesto(intruso)


class CopiaDeForaTestCase(BackupBase):
    """A copia que sobrevive ao computador: nuvem, pendrive, HD externo.

    A regra que nao pode ser quebrada: falhar aqui **nunca** estraga o backup
    local. O pendrive pode estar fora, a pasta da nuvem pode ter sumido - o que
    importa ja foi gravado antes desta funcao rodar.
    """

    def _copia(self) -> Backup:
        self._plataforma()
        return backup.criar(self.destino, self.paths)

    def test_o_zip_aparece_igualzinho_na_pasta_de_fora(self) -> None:
        copia = self._copia()
        fora = Path(tempfile.mkdtemp(prefix="dt_nuvem_"))

        destino = backup.copiar_para_fora(copia, fora)

        self.assertTrue(destino.exists())
        self.assertEqual(destino.name, copia.arquivo.name)
        self.assertEqual(destino.read_bytes(), copia.arquivo.read_bytes())
        # e continua sendo um backup de verdade, restauravel
        self.assertEqual(backup.ler_manifesto(destino).bancos, copia.bancos)

    def test_pasta_que_nao_da_para_usar_avisa_e_nao_apaga_nada(self) -> None:
        copia = self._copia()
        arquivo = self.destino / "isto-e-um-arquivo.txt"
        arquivo.write_text("nao sou pasta", encoding="utf-8")

        with self.assertRaises(BackupError) as erro:
            backup.copiar_para_fora(copia, arquivo)

        self.assertIn("computador foi feito normalmente", str(erro.exception))
        self.assertTrue(copia.arquivo.exists(), "o backup local tem que continuar la")

    def test_a_pasta_de_fora_tambem_nao_cresce_para_sempre(self) -> None:
        copia = self._copia()
        fora = Path(tempfile.mkdtemp(prefix="dt_nuvem_"))
        for dia in range(1, 6):
            (fora / f"{backup.PREFIXO}2026-09-0{dia}-1200.zip").write_bytes(b"velho")

        backup.copiar_para_fora(copia, fora, manter=3)

        sobraram = sorted(a.name for a in fora.glob(f"{backup.PREFIXO}*.zip"))
        self.assertEqual(len(sobraram), 3)
        self.assertIn(copia.arquivo.name, sobraram, "a mais nova nunca pode sumir")

    def test_nuvens_encontradas_so_devolve_pasta_que_existe(self) -> None:
        for caminho in backup.nuvens_encontradas():
            self.assertTrue(caminho.is_dir(), caminho)


class ListarTestCase(BackupBase):
    def test_lista_do_mais_novo_para_o_mais_velho(self) -> None:
        self._plataforma()
        primeiro = backup.criar(self.destino, self.paths)
        # o nome tem segundos: forcar dois momentos diferentes
        segundo = backup.criar(self.destino, self.paths)
        segundo.arquivo.rename(self.destino / "dumtech-backup-2099-01-01_000000.zip")

        achados = backup.listar(self.destino)
        self.assertEqual(len(achados), 2)
        self.assertGreaterEqual(achados[0].criado_em, achados[1].criado_em)
        del primeiro

    def test_arquivo_estranho_na_pasta_nao_quebra_a_lista(self) -> None:
        self._plataforma()
        backup.criar(self.destino, self.paths)
        (self.destino / "dumtech-backup-lixo.zip").write_bytes(b"lixo")
        (self.destino / "outra-coisa.txt").write_text("oi", encoding="utf-8")

        self.assertEqual(len(backup.listar(self.destino)), 1)

    def test_pasta_que_nao_existe_devolve_lista_vazia(self) -> None:
        self.assertEqual(backup.listar(self.destino / "nao-existe"), [])


class LimpezaTestCase(BackupBase):
    def _falsos(self, quantidade: int, automatico: bool) -> None:
        self._plataforma()
        for indice in range(quantidade):
            copia = backup.criar(self.destino, self.paths, automatico=automatico)
            sufixo = "-auto" if automatico else ""
            copia.arquivo.rename(
                self.destino / f"dumtech-backup-2026-01-{indice + 1:02d}_120000{sufixo}.zip"
            )

    def test_guarda_as_ultimas_e_apaga_as_velhas(self) -> None:
        self._falsos(6, automatico=True)
        apagados = backup.limpar_antigos(self.destino, manter=3)
        self.assertEqual(apagados, 3)
        self.assertEqual(len(backup.listar(self.destino)), 3)

    def test_backup_feito_a_mao_nunca_e_apagado(self) -> None:
        """Quem clicou em 'fazer backup' quis guardar aquilo."""
        self._falsos(4, automatico=False)
        self.assertEqual(backup.limpar_antigos(self.destino, manter=1), 0)
        self.assertEqual(len(backup.listar(self.destino)), 4)


class RestaurarTestCase(BackupBase):
    def test_restaurar_devolve_os_dados_do_dia_da_copia(self) -> None:
        self._plataforma()
        copia = backup.criar(self.destino, self.paths)

        # depois do backup, o cliente mexe (ou perde) tudo
        estoque = self.paths.app_db("estoque")
        conn = sqlite3.connect(estoque)
        conn.execute("DELETE FROM coisas")
        conn.commit()
        conn.close()
        self.assertEqual(self._contar(estoque), 0)

        restaurados = backup.restaurar(copia.arquivo, self.paths)
        self.assertEqual(self._contar(estoque), 5)
        self.assertIn("estoque.db", restaurados)
        self.assertIn("hub.db", restaurados)

    def test_cada_banco_volta_para_a_sua_pasta(self) -> None:
        self._plataforma()
        copia = backup.criar(self.destino, self.paths)
        for caminho in (self.paths.hub_db, self.paths.app_db("vendas")):
            caminho.unlink()

        backup.restaurar(copia.arquivo, self.paths)
        self.assertTrue(self.paths.hub_db.exists())          # data/
        self.assertTrue(self.paths.app_db("vendas").exists())  # data/apps/
        self.assertEqual(self._contar(self.paths.app_db("vendas")), 7)

    def test_restaurar_apaga_o_wal_velho(self) -> None:
        """O WAL do banco antigo nao vale para o banco restaurado."""
        self._plataforma()
        copia = backup.criar(self.destino, self.paths)
        sobra = Path(f"{self.paths.app_db('estoque')}-wal")
        sobra.write_bytes(b"wal velho")

        backup.restaurar(copia.arquivo, self.paths)
        self.assertFalse(sobra.exists())

    def test_zip_invalido_nao_mexe_em_nada(self) -> None:
        self._plataforma()
        antes = self._contar(self.paths.app_db("estoque"))
        intruso = self.destino / "dumtech-backup-falso.zip"
        intruso.write_bytes(b"nao sou zip")

        with self.assertRaises(BackupError):
            backup.restaurar(intruso, self.paths)
        self.assertEqual(self._contar(self.paths.app_db("estoque")), antes)

    def test_backup_de_uma_versao_futura_e_recusado(self) -> None:
        self._plataforma()
        copia = backup.criar(self.destino, self.paths)
        futuro = self.destino / "dumtech-backup-2099-01-01_000000.zip"
        with zipfile.ZipFile(copia.arquivo) as origem, \
                zipfile.ZipFile(futuro, "w") as saida:
            for nome in origem.namelist():
                dados = origem.read(nome)
                if nome == backup.MANIFESTO:
                    dados = dados.replace(b'"formato": 1', b'"formato": 99')
                saida.writestr(nome, dados)

        with self.assertRaises(BackupError) as erro:
            backup.restaurar(futuro, self.paths)
        self.assertIn("versão mais nova", str(erro.exception))


class IdaEVoltaTestCase(BackupBase):
    def test_o_caminho_completo_com_dados_de_verdade(self) -> None:
        """Copia de um Hub com dados reais, apaga tudo e restaura."""
        from dumtech.apps.estoque.database import open_database
        from dumtech.apps.estoque.models import Produto
        from dumtech.apps.estoque.repository import EstoqueRepository

        banco = open_database(self.paths.app_db("estoque"))
        repo = EstoqueRepository(banco)
        repo.criar(Produto(codigo="P-1", nome="Produto real", quantidade=12,
                           preco_venda=49.9))
        self._banco(self.paths.hub_db)

        # backup com o banco ainda ABERTO, como acontece no uso real
        copia = backup.criar(self.destino, self.paths, versao="2.0.0")
        banco.close()

        self.paths.app_db("estoque").unlink()
        backup.restaurar(copia.arquivo, self.paths)

        banco = open_database(self.paths.app_db("estoque"))
        self.addCleanup(banco.close)
        produto = EstoqueRepository(banco).buscar_por_codigo("P-1")
        self.assertIsNotNone(produto)
        self.assertEqual(produto.nome, "Produto real")
        self.assertEqual(produto.quantidade, 12)


if __name__ == "__main__":
    unittest.main()


class RestaurarInteiro(BackupBase):
    """Restaurar e tudo ou nada, e traz a empresa de volta."""

    def setUp(self) -> None:
        super().setUp()
        self._plataforma()
        self.paths.settings_file.write_text(json.dumps({
            "empresa": {"nome": "Loja da Ana"},
            "app:vendas": {"tema": "claro"},
            "backup": {"pasta": "D:/velha"},
            "licenca": {"chave": "OUTRA"},
        }), encoding="utf-8")
        self.copia = backup.criar(self.destino, self.paths)

    def _linhas(self, caminho: Path) -> int:
        conn = sqlite3.connect(caminho)
        try:
            return conn.execute("SELECT COUNT(*) FROM coisas").fetchone()[0]
        finally:
            conn.close()

    def test_a_empresa_volta_e_o_que_e_da_maquina_fica(self) -> None:
        self.paths.settings_file.write_text(json.dumps({
            "backup": {"pasta": "E:/nova"}, "licenca": {"chave": "MINHA"},
        }), encoding="utf-8")
        backup.restaurar(self.copia.arquivo, self.paths)
        config = json.loads(self.paths.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(config["empresa"]["nome"], "Loja da Ana")
        self.assertEqual(config["app:vendas"]["tema"], "claro")
        self.assertEqual(config["backup"]["pasta"], "E:/nova")
        self.assertEqual(config["licenca"]["chave"], "MINHA")

    def test_banco_em_uso_nao_troca_nada(self) -> None:
        banco = self.paths.app_db("vendas")
        aberto = sqlite3.connect(banco)
        self.addCleanup(aberto.close)
        aberto.execute("PRAGMA journal_mode = WAL")
        aberto.execute("INSERT INTO coisas VALUES (99, 'depois do backup')")
        aberto.commit()
        with self.assertRaises(BackupError):
            backup.restaurar(self.copia.arquivo, self.paths)
        self.assertEqual(aberto.execute("SELECT COUNT(*) FROM coisas").fetchone()[0], 8)
        self.assertEqual(self._linhas(self.paths.app_db("estoque")), 5)
        self.assertTrue(self.paths.hub_db.exists())

    def test_banco_estragado_no_zip_para_antes_de_mexer(self) -> None:
        estragado = self.destino / "dumtech-backup-estragado.zip"
        with zipfile.ZipFile(self.copia.arquivo) as origem, zipfile.ZipFile(estragado, "w") as saida:
            for nome in origem.namelist():
                dados = origem.read(nome)
                saida.writestr(nome, b"lixo" * 500 if nome.endswith("vendas.db") else dados)
        with self.assertRaises(BackupError) as erro:
            backup.restaurar(estragado, self.paths)
        self.assertIn("danificado", str(erro.exception))
        self.assertEqual(self._linhas(self.paths.app_db("vendas")), 7)

    def test_sem_dados_e_um_erro_que_se_reconhece(self) -> None:
        vazio = DataPaths(root=Path(tempfile.mkdtemp(prefix="dt_vazio_"))).ensure()
        with self.assertRaises(backup.SemDados):
            backup.criar(self.destino, vazio)
