"""Camada de banco de dados local (SQLite).

Cada banco (o do Hub e o de cada aplicativo) e um arquivo .db separado dentro da
pasta de dados do usuario. Nao existe servidor, nao existe internet: o SQLite ja
vem junto com o Python, entao o programa funciona 100% offline.

Cada banco tem sua propria lista de "migracoes" (mudancas de estrutura). A versao
aplicada fica gravada no proprio arquivo (PRAGMA user_version), o que permite
evoluir o esquema em versoes futuras sem perder os dados do cliente.

Migracao e tudo ou nada: uma que falha no meio volta o banco para como estava,
e o programa pode tentar de novo depois de corrigida. Sem isso, a primeira falha
deixava tabela criada pela metade e travava o modulo para sempre.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Sequence

logger = logging.getLogger(__name__)


#: o que a pessoa le quando tenta gravar num modulo fora da licenca
SO_CONSULTA = (
    "Este módulo está em modo consulta porque saiu da licença: dá para ver e "
    "exportar, mas não para gravar. Renove a licença para voltar a lançar."
)


def aviso_so_consulta() -> str:
    """O que le quem tenta gravar em modo consulta. A mensalidade troca o motivo
    (`hub/launcher.py`); o resto continua com o texto de sempre."""
    return Database.aviso_consulta or SO_CONSULTA


def e_so_consulta(erro: BaseException) -> bool:
    """Foi o banco recusando escrita porque o modulo esta so para consulta?"""
    return isinstance(erro, sqlite3.OperationalError) and "readonly" in str(erro)


class MigracaoError(Exception):
    """A atualizacao de um banco falhou (mensagem pronta para o usuario)."""


@dataclass(frozen=True)
class Migration:
    """Um passo de evolucao do esquema do banco."""

    version: int
    name: str
    statements: Sequence[str] = field(default_factory=tuple)


class Database:
    """Conexao unica com um arquivo SQLite, com controle de versao de esquema."""

    #: bancos que abrem so para leitura: os do modulo que saiu da licenca. A
    #: trava fica aqui, e nao nos botoes: nenhuma tela precisa lembrar dela
    so_leitura: set[Path] = set()
    #: o motivo do modo consulta, quando nao e o de sempre (a mensalidade)
    aviso_consulta: str = ""

    def __init__(self, path: Path, migrations: Sequence[Migration] = ()) -> None:
        self.path = Path(path)
        self._migrations = tuple(sorted(migrations, key=lambda m: m.version))
        self._connection: sqlite3.Connection | None = None
        #: blocos `transaction` abertos agora: quem fecha o ultimo e quem grava
        self._aninhamento = 0

    # ------------------------------------------------------------------ conexao
    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            try:
                self._apply_migrations(conn)
            except Exception:
                # guardar esta conexao entregaria um banco sem atualizar a quem
                # pedisse de novo
                conn.close()
                raise
            if self.path in Database.so_leitura:
                conn.execute("PRAGMA query_only = ON")
            self._connection = conn
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    # ------------------------------------------------------------------ escrita
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Executa varias operacoes de forma atomica (tudo ou nada).

        Pode ser aberta dentro de outra: quem grava e o bloco de fora, e e isso
        que permite juntar operacoes que ja tem transacao propria.
        """
        conn = self.connection
        self._aninhamento += 1
        try:
            yield conn
        except Exception:
            self._aninhamento -= 1
            if not self._aninhamento:
                conn.rollback()
            raise
        else:
            self._aninhamento -= 1
            if not self._aninhamento:
                conn.commit()

    def execute(self, sql: str, params: Sequence | dict = ()) -> sqlite3.Cursor:
        with self.transaction() as conn:
            return conn.execute(sql, params)

    # ------------------------------------------------------------------ leitura
    def query(self, sql: str, params: Sequence | dict = ()) -> list[sqlite3.Row]:
        return list(self.connection.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: Sequence | dict = ()) -> sqlite3.Row | None:
        return self.connection.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: Sequence | dict = (), default=0):
        row = self.query_one(sql, params)
        if row is None or row[0] is None:
            return default
        return row[0]

    # --------------------------------------------------------------- migracoes
    @property
    def schema_version(self) -> int:
        return int(self.connection.execute("PRAGMA user_version").fetchone()[0])

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        pending = [m for m in self._migrations if m.version > current]
        if not pending:
            return
        if current > 0:
            self._copiar_antes(conn, current)
        for migration in pending:
            self._aplicar(conn, migration)

    def _aplicar(self, conn: sqlite3.Connection, migration: Migration) -> None:
        """Um passo inteiro numa transacao so.

        As chaves estrangeiras desligam antes do BEGIN porque la dentro o
        SQLite ignora o pedido, e reconstruir uma tabela com elas ligadas
        apagaria em cascata as linhas das tabelas filhas. Quebra que ja existia
        antes do passo nao o impede: so nao pode aparecer quebra nova.
        """
        script = ";\n".join(migration.statements)
        conn.commit()
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            quebras = len(conn.execute("PRAGMA foreign_key_check").fetchall())
            conn.executescript(
                f"BEGIN IMMEDIATE;\n{script}\n;"
                f"PRAGMA user_version = {int(migration.version)};"
            )
            if len(conn.execute("PRAGMA foreign_key_check").fetchall()) > quebras:
                raise sqlite3.IntegrityError("referencia quebrada")
            conn.commit()
        except sqlite3.Error as erro:
            conn.rollback()
            logger.exception("Falha na migracao %s de %s", migration.version, self.path.name)
            raise MigracaoError(
                f"Não foi possível atualizar os dados de '{self.path.stem}' "
                f"(passo {migration.version}: {migration.name}). Nada foi perdido: "
                "os dados continuam como estavam. Fale com o suporte."
            ) from erro
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    def _copiar_antes(self, conn: sqlite3.Connection, versao: int) -> None:
        """Guarda o banco como estava: um dado mal convertido nao levanta erro.

        A transacao protege da falha, nao de uma migracao que roda ate o fim e
        grava errado. Fica so a ultima copia. Falhar aqui nao impede a
        atualizacao, porque a transacao continua valendo.
        """
        destino = self.path.with_name(f"{self.path.name}.antes-v{versao}.bak")
        try:
            alvo = sqlite3.connect(destino)
            try:
                conn.backup(alvo)
            finally:
                alvo.close()
            for velha in self.path.parent.glob(f"{self.path.name}.antes-v*.bak"):
                if velha != destino:
                    velha.unlink(missing_ok=True)
        except (sqlite3.Error, OSError):
            logger.exception("Sem copia de %s antes de migrar", self.path.name)
