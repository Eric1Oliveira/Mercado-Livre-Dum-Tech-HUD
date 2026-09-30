"""Estrutura do banco local do DumTech Orcamentos (orcamentos.db)."""

from __future__ import annotations

from pathlib import Path

from ...core.database import Database, Migration

MIGRATIONS = (
    Migration(
        version=1,
        name="orcamentos e itens",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS orcamentos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                numero      TEXT NOT NULL UNIQUE,
                cliente     TEXT NOT NULL DEFAULT '',
                data        TEXT NOT NULL,
                validade    TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'rascunho',
                desconto    REAL NOT NULL DEFAULT 0,
                observacoes TEXT NOT NULL DEFAULT '',
                criado_em   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orcamento_itens (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                orcamento_id   INTEGER NOT NULL
                               REFERENCES orcamentos(id) ON DELETE CASCADE,
                descricao      TEXT NOT NULL,
                quantidade     INTEGER NOT NULL DEFAULT 1,
                valor_unitario REAL NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_orc_itens ON orcamento_itens(orcamento_id);
            CREATE INDEX IF NOT EXISTS idx_orc_status ON orcamentos(status);
            """,
        ),
    ),
    Migration(
        version=2,
        name="condicoes, desconto por item e acompanhamento",
        statements=(
            # `orcamentos` so ganha colunas; `orcamento_itens` precisa ser
            # reconstruida porque a quantidade vira REAL - proposta cota metro
            # quadrado, quilo e hora.
            """
            PRAGMA foreign_keys = OFF;

            ALTER TABLE orcamentos ADD COLUMN condicao_pagamento TEXT NOT NULL DEFAULT '';
            ALTER TABLE orcamentos ADD COLUMN prazo_entrega TEXT NOT NULL DEFAULT '';
            ALTER TABLE orcamentos ADD COLUMN validade_dias INTEGER NOT NULL DEFAULT 15;
            ALTER TABLE orcamentos ADD COLUMN enviado_em TEXT NOT NULL DEFAULT '';
            ALTER TABLE orcamentos ADD COLUMN respondido_em TEXT NOT NULL DEFAULT '';
            ALTER TABLE orcamentos ADD COLUMN motivo_recusa TEXT NOT NULL DEFAULT '';
            ALTER TABLE orcamentos ADD COLUMN total REAL NOT NULL DEFAULT 0;

            CREATE TABLE orcamento_itens_v2 (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                orcamento_id   INTEGER NOT NULL
                               REFERENCES orcamentos(id) ON DELETE CASCADE,
                descricao      TEXT NOT NULL,
                quantidade     REAL NOT NULL DEFAULT 1,
                valor_unitario REAL NOT NULL DEFAULT 0,
                desconto       REAL NOT NULL DEFAULT 0,
                unidade        TEXT NOT NULL DEFAULT ''
            );

            INSERT INTO orcamento_itens_v2 (id, orcamento_id, descricao, quantidade,
                                            valor_unitario)
            SELECT id, orcamento_id, descricao, quantidade, valor_unitario
            FROM orcamento_itens;

            DROP TABLE orcamento_itens;
            ALTER TABLE orcamento_itens_v2 RENAME TO orcamento_itens;
            CREATE INDEX IF NOT EXISTS idx_orc_itens ON orcamento_itens(orcamento_id);

            -- o total virou coluna: quem ja tinha orcamento nao pode aparecer
            -- zerado na lista nem no funil
            UPDATE orcamentos SET total = MAX(0, COALESCE((
                SELECT SUM(i.quantidade * i.valor_unitario)
                FROM orcamento_itens i WHERE i.orcamento_id = orcamentos.id
            ), 0) - desconto);

            -- o que ja saiu da loja ganha a data de saida, senao o funil nao
            -- consegue dizer ha quantos dias a proposta esta parada
            UPDATE orcamentos SET enviado_em = data
            WHERE status IN ('enviado', 'aprovado', 'recusado');
            UPDATE orcamentos SET respondido_em = data
            WHERE status IN ('aprovado', 'recusado');

            PRAGMA foreign_keys = ON;
            """,
        ),
    ),
    Migration(
        version=3,
        name="linha ligada ao produto do Estoque",
        statements=(
            # Sem isto a proposta guardava so o nome do produto: quando virava
            # venda ou ordem de servico, ninguem sabia de qual prateleira ele
            # saia, e o estoque nunca baixava.
            """
            ALTER TABLE orcamento_itens ADD COLUMN produto_id INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE orcamento_itens ADD COLUMN codigo TEXT NOT NULL DEFAULT '';
            """,
        ),
    ),
)


def open_database(path: Path) -> Database:
    """Abre (criando se preciso) o banco local do Orcamentos."""
    database = Database(path, MIGRATIONS)
    database.connection  # forca a criacao do arquivo e das tabelas
    return database
