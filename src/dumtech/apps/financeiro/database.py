"""Estrutura do banco local do DumTech Financeiro (financeiro.db)."""

from __future__ import annotations

from pathlib import Path

from ...core.database import Database, Migration

MIGRATIONS = (
    Migration(
        version=1,
        name="lancamentos",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS lancamentos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo            TEXT NOT NULL CHECK (tipo IN ('receita', 'despesa')),
                descricao       TEXT NOT NULL,
                categoria       TEXT NOT NULL DEFAULT '',
                cliente         TEXT NOT NULL DEFAULT '',
                valor           REAL NOT NULL DEFAULT 0,
                vencimento      TEXT NOT NULL,
                pago_em         TEXT,
                forma_pagamento TEXT NOT NULL DEFAULT '',
                observacoes     TEXT NOT NULL DEFAULT '',
                criado_em       TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_lanc_venc ON lancamentos(vencimento);
            CREATE INDEX IF NOT EXISTS idx_lanc_tipo ON lancamentos(tipo);
            """,
        ),
    ),
    Migration(
        version=2,
        name="contas, baixas, transferencias e series",
        statements=(
            # `lancamentos` so ganha colunas: nenhum tipo muda, entao ALTER TABLE
            # resolve e a tabela nao precisa ser reconstruida.
            """
            ALTER TABLE lancamentos ADD COLUMN conta_id INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE lancamentos ADD COLUMN grupo TEXT NOT NULL DEFAULT '';
            ALTER TABLE lancamentos ADD COLUMN parcela INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE lancamentos ADD COLUMN parcelas INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE lancamentos ADD COLUMN serie TEXT NOT NULL DEFAULT '';
            CREATE INDEX IF NOT EXISTS idx_lanc_grupo ON lancamentos(grupo);

            CREATE TABLE IF NOT EXISTS contas (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                nome          TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                tipo          TEXT    NOT NULL DEFAULT 'banco'
                              CHECK (tipo IN ('caixa', 'banco', 'cartao')),
                saldo_inicial REAL    NOT NULL DEFAULT 0,
                observacoes   TEXT    NOT NULL DEFAULT '',
                ativo         INTEGER NOT NULL DEFAULT 1,
                criado_em     TEXT    NOT NULL
            );

            -- um lancamento tem N baixas: e daqui que sai o recebimento parcial
            -- e a resposta "quando o dinheiro entrou de verdade"
            CREATE TABLE IF NOT EXISTS baixas (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                lancamento_id INTEGER NOT NULL
                              REFERENCES lancamentos(id) ON DELETE CASCADE,
                data          TEXT    NOT NULL,
                valor         REAL    NOT NULL DEFAULT 0,
                conta_id      INTEGER NOT NULL DEFAULT 0,
                forma         TEXT    NOT NULL DEFAULT '',
                observacao    TEXT    NOT NULL DEFAULT '',
                criado_em     TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_baixas_lanc ON baixas(lancamento_id);
            CREATE INDEX IF NOT EXISTS idx_baixas_data ON baixas(data);
            CREATE INDEX IF NOT EXISTS idx_baixas_conta ON baixas(conta_id);

            -- dinheiro mudando de conta nao e receita nem despesa
            CREATE TABLE IF NOT EXISTS transferencias (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                origem_id  INTEGER NOT NULL REFERENCES contas(id) ON DELETE CASCADE,
                destino_id INTEGER NOT NULL REFERENCES contas(id) ON DELETE CASCADE,
                data       TEXT    NOT NULL,
                valor      REAL    NOT NULL DEFAULT 0,
                observacao TEXT    NOT NULL DEFAULT '',
                criado_em  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_transf_data ON transferencias(data);

            -- quem ja estava pago vira uma baixa do valor cheio na data do
            -- pagamento: ninguem perde historico ao atualizar
            INSERT INTO baixas (lancamento_id, data, valor, conta_id, forma,
                                observacao, criado_em)
            SELECT id, pago_em, valor, 0, forma_pagamento, '', criado_em
            FROM lancamentos WHERE pago_em IS NOT NULL AND TRIM(pago_em) <> '';
            """,
        ),
    ),
)


def open_database(path: Path) -> Database:
    """Abre (criando se preciso) o banco local do Financeiro."""
    database = Database(path, MIGRATIONS)
    database.connection  # forca a criacao do arquivo e das tabelas
    return database
