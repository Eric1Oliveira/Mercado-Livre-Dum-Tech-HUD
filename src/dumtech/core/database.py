"""Camada de banco de dados local (SQLite).

Cada banco (o do Hub e o de cada aplicativo) e um arquivo .db separado dentro da
pasta de dados do usuario. Nao existe servidor, nao existe internet: o SQLite ja
vem junto com o Python, entao o programa funciona 100% offline.

Cada banco tem sua propria lista de "migracoes" (mudancas de estrutura). A versao
aplicada fica gravada no proprio arquivo (PRAGMA user_version), o que permite
evoluir o esquema em versoes futuras sem perder os dados do cliente.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Sequence


@dataclass(frozen=True)
class Migration:
    """Um passo de evolucao do esquema do banco."""

    version: int
    name: str
    statements: Sequence[str] = field(default_factory=tuple)


class Database:
    """Conexao unica com um arquivo SQLite, com controle de versao de esquema."""

    def __init__(self, path: Path, migrations: Sequence[Migration] = ()) -> None:
        self.path = Path(path)
        self._migrations = tuple(sorted(migrations, key=lambda m: m.version))
        self._connection: sqlite3.Connection | None = None

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
            self._connection = conn
            self._apply_migrations(conn)
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    # ------------------------------------------------------------------ escrita
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Executa varias operacoes de forma atomica (tudo ou nada)."""
        conn = self.connection
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
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
        for migration in pending:
            for statement in migration.statements:
                conn.executescript(statement)
            conn.execute(f"PRAGMA user_version = {int(migration.version)}")
        conn.commit()
