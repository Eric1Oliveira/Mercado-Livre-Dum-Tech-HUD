"""Estrutura do banco local do DumTech Agenda (agenda.db)."""

from __future__ import annotations

from pathlib import Path

from ...core.database import Database, Migration

MIGRATIONS = (
    Migration(
        version=1,
        name="compromissos",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS compromissos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo      TEXT NOT NULL,
                cliente     TEXT NOT NULL DEFAULT '',
                inicio      TEXT NOT NULL,
                duracao_min INTEGER NOT NULL DEFAULT 60,
                local       TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'agendado',
                observacoes TEXT NOT NULL DEFAULT '',
                criado_em   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_compromissos_inicio ON compromissos(inicio);
            """,
        ),
    ),
    Migration(
        version=2,
        name="tipo, bloqueio e repeticao",
        statements=(
            # so colunas novas: nenhum tipo muda. Bloqueio (almoco, folga,
            # feriado) nao ganha tabela propria - e um compromisso de tipo
            # 'bloqueio', e assim ja ocupa a grade e entra no conflito.
            """
            ALTER TABLE compromissos ADD COLUMN tipo TEXT NOT NULL
                DEFAULT 'atendimento';
            ALTER TABLE compromissos ADD COLUMN grupo TEXT NOT NULL DEFAULT '';
            ALTER TABLE compromissos ADD COLUMN repeticao TEXT NOT NULL DEFAULT '';
            CREATE INDEX IF NOT EXISTS idx_compromissos_grupo ON compromissos(grupo);
            CREATE INDEX IF NOT EXISTS idx_compromissos_tipo ON compromissos(tipo);
            """,
        ),
    ),
    Migration(
        version=3,
        name="agendamento online",
        statements=(
            # so acrescimo: telefone serve a qualquer compromisso; origem e
            # reserva marcam o que veio do link. O indice unico impede a mesma
            # reserva de entrar duas vezes (a confirmacao pode se perder na
            # rede e o servidor manda de novo). `ajustes` guarda a configuracao
            # do link: ele e deste computador e vai no backup junto da agenda.
            """
            ALTER TABLE compromissos ADD COLUMN telefone TEXT NOT NULL DEFAULT '';
            ALTER TABLE compromissos ADD COLUMN origem TEXT NOT NULL DEFAULT '';
            ALTER TABLE compromissos ADD COLUMN reserva TEXT NOT NULL DEFAULT '';
            CREATE UNIQUE INDEX IF NOT EXISTS idx_compromissos_reserva
                ON compromissos(reserva) WHERE reserva <> '';
            CREATE TABLE IF NOT EXISTS ajustes (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            );
            """,
        ),
    ),
    Migration(
        version=4,
        name="profissional, sinal e documento gerado",
        statements=(
            """
            ALTER TABLE compromissos ADD COLUMN profissional TEXT NOT NULL DEFAULT '';
            ALTER TABLE compromissos ADD COLUMN sinal REAL NOT NULL DEFAULT 0;
            ALTER TABLE compromissos ADD COLUMN documento TEXT NOT NULL DEFAULT '';
            """,
        ),
    ),
)


def open_database(path: Path) -> Database:
    """Abre (criando se preciso) o banco local da Agenda."""
    database = Database(path, MIGRATIONS)
    database.connection  # forca a criacao do arquivo e das tabelas
    return database
