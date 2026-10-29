"""Estrutura do banco local do DumTech Vendas (vendas.db)."""

from __future__ import annotations

from pathlib import Path

from ...core.database import Database, Migration
from ...core.recorrencia import TABELA as TABELA_RECORRENCIAS

MIGRATIONS = (
    Migration(
        version=1,
        name="vendas e itens",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS vendas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                numero          TEXT NOT NULL UNIQUE,
                cliente         TEXT NOT NULL DEFAULT '',
                data            TEXT NOT NULL,
                forma_pagamento TEXT NOT NULL DEFAULT '',
                status          TEXT NOT NULL DEFAULT 'concluida',
                desconto        REAL NOT NULL DEFAULT 0,
                observacoes     TEXT NOT NULL DEFAULT '',
                criado_em       TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS venda_itens (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                venda_id       INTEGER NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
                descricao      TEXT NOT NULL,
                quantidade     INTEGER NOT NULL DEFAULT 1,
                valor_unitario REAL NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_venda_itens ON venda_itens(venda_id);
            CREATE INDEX IF NOT EXISTS idx_vendas_data ON vendas(data);
            """,
        ),
    ),
    Migration(
        version=2,
        name="pagamento, caixa do dia e devolucao",
        statements=(
            # `vendas` so ganha colunas: ALTER TABLE resolve, sem reconstruir.
            # `venda_itens` precisa ser reconstruida porque a quantidade vira
            # REAL - balcao de padaria e acougue vende por quilo, e o catalogo
            # do Estoque ja trabalha com casas decimais.
            """
            PRAGMA foreign_keys = OFF;

            ALTER TABLE vendas ADD COLUMN caixa_id INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE vendas ADD COLUMN troco REAL NOT NULL DEFAULT 0;
            ALTER TABLE vendas ADD COLUMN cancelada_em TEXT NOT NULL DEFAULT '';
            ALTER TABLE vendas ADD COLUMN motivo_cancelamento TEXT NOT NULL DEFAULT '';

            CREATE TABLE venda_itens_v2 (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                venda_id       INTEGER NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
                descricao      TEXT    NOT NULL,
                quantidade     REAL    NOT NULL DEFAULT 1,
                valor_unitario REAL    NOT NULL DEFAULT 0,
                produto_id     INTEGER NOT NULL DEFAULT 0,
                codigo         TEXT    NOT NULL DEFAULT '',
                unidade        TEXT    NOT NULL DEFAULT 'UN',
                casas          INTEGER NOT NULL DEFAULT 0
            );

            INSERT INTO venda_itens_v2 (id, venda_id, descricao, quantidade, valor_unitario)
            SELECT id, venda_id, descricao, quantidade, valor_unitario FROM venda_itens;

            DROP TABLE venda_itens;
            ALTER TABLE venda_itens_v2 RENAME TO venda_itens;
            CREATE INDEX IF NOT EXISTS idx_venda_itens ON venda_itens(venda_id);

            -- uma venda pode ser paga em varias formas ao mesmo tempo
            CREATE TABLE IF NOT EXISTS pagamentos (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                venda_id  INTEGER NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
                forma     TEXT    NOT NULL,
                valor     REAL    NOT NULL DEFAULT 0,
                recebido  REAL    NOT NULL DEFAULT 0,
                criado_em TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pagamentos_venda ON pagamentos(venda_id);

            CREATE TABLE IF NOT EXISTS caixas (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                aberto_em      TEXT NOT NULL,
                fechado_em     TEXT NOT NULL DEFAULT '',
                valor_abertura REAL NOT NULL DEFAULT 0,
                contado        REAL NOT NULL DEFAULT 0,
                diferenca      REAL NOT NULL DEFAULT 0,
                observacoes    TEXT NOT NULL DEFAULT '',
                status         TEXT NOT NULL DEFAULT 'aberto'
                               CHECK (status IN ('aberto', 'fechado'))
            );

            CREATE TABLE IF NOT EXISTS caixa_movimentos (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                caixa_id  INTEGER NOT NULL REFERENCES caixas(id) ON DELETE CASCADE,
                tipo      TEXT    NOT NULL CHECK (tipo IN ('sangria', 'suprimento')),
                valor     REAL    NOT NULL DEFAULT 0,
                motivo    TEXT    NOT NULL DEFAULT '',
                criado_em TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_caixa_mov ON caixa_movimentos(caixa_id);

            CREATE TABLE IF NOT EXISTS devolucoes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                venda_id  INTEGER NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
                data      TEXT    NOT NULL,
                motivo    TEXT    NOT NULL DEFAULT '',
                valor     REAL    NOT NULL DEFAULT 0,
                caixa_id  INTEGER NOT NULL DEFAULT 0,
                criado_em TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_devolucoes_venda ON devolucoes(venda_id);
            CREATE INDEX IF NOT EXISTS idx_devolucoes_data ON devolucoes(data);

            CREATE TABLE IF NOT EXISTS devolucao_itens (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                devolucao_id   INTEGER NOT NULL
                               REFERENCES devolucoes(id) ON DELETE CASCADE,
                venda_item_id  INTEGER NOT NULL
                               REFERENCES venda_itens(id) ON DELETE CASCADE,
                quantidade     REAL    NOT NULL DEFAULT 0,
                valor_unitario REAL    NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_devolucao_itens
                ON devolucao_itens(devolucao_id);
            CREATE INDEX IF NOT EXISTS idx_devolucao_item_venda
                ON devolucao_itens(venda_item_id);

            PRAGMA foreign_keys = ON;
            """,
        ),
    ),
    Migration(
        version=3,
        name="baixa de estoque marcada na venda",
        statements=(
            # A venda que nasce do Orcamento chega pendente e so e paga depois:
            # e no recebimento que a mercadoria sai do estoque. Para isso a
            # venda passa a anotar SE ja deu baixa - a venda a prazo do balcao
            # baixou na hora e nao pode baixar de novo quando for recebida.
            # O que ja existia fica marcado como "antes": nunca rebaixa.
            """
            ALTER TABLE vendas ADD COLUMN baixa_estoque TEXT NOT NULL DEFAULT '';
            UPDATE vendas SET baixa_estoque = 'antes';
            """,
        ),
    ),
    Migration(
        version=4,
        name="venda recorrente",
        statements=(
            # O contrato (mensalidade, fornecimento do mes) e cada venda que
            # ele gera, marcada com o numero dele: e por ela que se sabe que
            # a vez ja foi gerada e que ela vai ao Financeiro como recorrente.
            TABELA_RECORRENCIAS,
            """
            ALTER TABLE vendas ADD COLUMN recorrencia TEXT NOT NULL DEFAULT '';
            CREATE INDEX IF NOT EXISTS idx_vendas_recorrencia ON vendas(recorrencia, data);
            """,
        ),
    ),
)


def open_database(path: Path) -> Database:
    """Abre (criando se preciso) o banco local do Vendas."""
    database = Database(path, MIGRATIONS)
    database.connection  # forca a criacao do arquivo e das tabelas
    return database
