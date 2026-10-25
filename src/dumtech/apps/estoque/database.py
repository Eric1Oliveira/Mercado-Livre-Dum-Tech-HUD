"""Estrutura do banco local do DumTech Estoque (arquivo estoque.db)."""

from __future__ import annotations

from pathlib import Path

from ...core.database import Database, Migration

MIGRATIONS = (
    Migration(
        version=1,
        name="produtos e movimentacoes",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS produtos (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                nome           TEXT    NOT NULL,
                descricao      TEXT    NOT NULL DEFAULT '',
                categoria      TEXT    NOT NULL DEFAULT '',
                quantidade     INTEGER NOT NULL DEFAULT 0,
                estoque_minimo INTEGER NOT NULL DEFAULT 0,
                preco_custo    REAL    NOT NULL DEFAULT 0,
                preco_venda    REAL    NOT NULL DEFAULT 0,
                criado_em      TEXT    NOT NULL,
                atualizado_em  TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_produtos_nome ON produtos(nome);
            CREATE INDEX IF NOT EXISTS idx_produtos_categoria ON produtos(categoria);

            CREATE TABLE IF NOT EXISTS movimentacoes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                produto_id     INTEGER REFERENCES produtos(id) ON DELETE SET NULL,
                produto_codigo TEXT    NOT NULL,
                produto_nome   TEXT    NOT NULL,
                tipo           TEXT    NOT NULL
                               CHECK (tipo IN ('entrada', 'saida', 'ajuste')),
                quantidade     INTEGER NOT NULL,
                saldo_anterior INTEGER NOT NULL DEFAULT 0,
                saldo_atual    INTEGER NOT NULL DEFAULT 0,
                observacao     TEXT    NOT NULL DEFAULT '',
                criado_em      TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_mov_data ON movimentacoes(criado_em);
            CREATE INDEX IF NOT EXISTS idx_mov_produto ON movimentacoes(produto_id);
            """,
        ),
    ),
    Migration(
        version=2,
        name="unidade, codigo de barras, custo medio e contagem",
        statements=(
            # SQLite nao muda o tipo de uma coluna: as duas tabelas sao
            # reconstruidas com quantidade REAL e os dados sao copiados. O
            # `INSERT ... SELECT` preserva id, para o historico continuar ligado
            # ao produto certo.
            """
            PRAGMA foreign_keys = OFF;

            CREATE TABLE produtos_v2 (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                nome           TEXT    NOT NULL,
                descricao      TEXT    NOT NULL DEFAULT '',
                categoria      TEXT    NOT NULL DEFAULT '',
                unidade        TEXT    NOT NULL DEFAULT 'UN',
                codigo_barras  TEXT    NOT NULL DEFAULT '',
                fornecedor     TEXT    NOT NULL DEFAULT '',
                localizacao    TEXT    NOT NULL DEFAULT '',
                quantidade     REAL    NOT NULL DEFAULT 0,
                estoque_minimo REAL    NOT NULL DEFAULT 0,
                estoque_maximo REAL    NOT NULL DEFAULT 0,
                preco_custo    REAL    NOT NULL DEFAULT 0,
                preco_venda    REAL    NOT NULL DEFAULT 0,
                ativo          INTEGER NOT NULL DEFAULT 1,
                criado_em      TEXT    NOT NULL,
                atualizado_em  TEXT    NOT NULL
            );

            INSERT INTO produtos_v2 (
                id, codigo, nome, descricao, categoria, quantidade,
                estoque_minimo, preco_custo, preco_venda, criado_em, atualizado_em
            )
            SELECT id, codigo, nome, descricao, categoria, quantidade,
                   estoque_minimo, preco_custo, preco_venda, criado_em, atualizado_em
            FROM produtos;

            DROP TABLE produtos;
            ALTER TABLE produtos_v2 RENAME TO produtos;

            CREATE INDEX IF NOT EXISTS idx_produtos_nome ON produtos(nome);
            CREATE INDEX IF NOT EXISTS idx_produtos_categoria ON produtos(categoria);
            CREATE INDEX IF NOT EXISTS idx_produtos_ativo ON produtos(ativo);
            -- varios produtos podem ficar sem codigo de barras; dois nao podem
            -- repetir o mesmo codigo
            CREATE UNIQUE INDEX IF NOT EXISTS idx_produtos_barras
                ON produtos(codigo_barras) WHERE codigo_barras <> '';

            CREATE TABLE movimentacoes_v2 (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                produto_id     INTEGER REFERENCES produtos(id) ON DELETE SET NULL,
                produto_codigo TEXT    NOT NULL,
                produto_nome   TEXT    NOT NULL,
                tipo           TEXT    NOT NULL
                               CHECK (tipo IN ('entrada', 'saida', 'ajuste')),
                quantidade     REAL    NOT NULL,
                saldo_anterior REAL    NOT NULL DEFAULT 0,
                saldo_atual    REAL    NOT NULL DEFAULT 0,
                custo_unitario REAL    NOT NULL DEFAULT 0,
                fornecedor     TEXT    NOT NULL DEFAULT '',
                documento      TEXT    NOT NULL DEFAULT '',
                observacao     TEXT    NOT NULL DEFAULT '',
                criado_em      TEXT    NOT NULL
            );

            INSERT INTO movimentacoes_v2 (
                id, produto_id, produto_codigo, produto_nome, tipo, quantidade,
                saldo_anterior, saldo_atual, observacao, criado_em
            )
            SELECT id, produto_id, produto_codigo, produto_nome, tipo, quantidade,
                   saldo_anterior, saldo_atual, observacao, criado_em
            FROM movimentacoes;

            DROP TABLE movimentacoes;
            ALTER TABLE movimentacoes_v2 RENAME TO movimentacoes;

            CREATE INDEX IF NOT EXISTS idx_mov_data ON movimentacoes(criado_em);
            CREATE INDEX IF NOT EXISTS idx_mov_produto ON movimentacoes(produto_id);

            -- folha de contagem: uma por vez, e o que o balanco precisa
            CREATE TABLE IF NOT EXISTS contagem_itens (
                produto_id    INTEGER PRIMARY KEY
                              REFERENCES produtos(id) ON DELETE CASCADE,
                contado       REAL NOT NULL,
                atualizado_em TEXT NOT NULL
            );

            PRAGMA foreign_keys = ON;
            """,
        ),
    ),
    Migration(
        version=3,
        name="imagem do produto",
        statements=(
            # tabela a parte: a lista de produtos (SELECT * FROM produtos) nao
            # carrega imagem nenhuma. Dentro do banco, a imagem entra no backup
            # e volta na restauracao sem nenhuma pasta extra para se perder.
            # A miniatura (96 px, poucos KB) e o que as listas desenham: abrir a
            # foto inteira de cada produto travaria a tela de Produtos.
            """
            CREATE TABLE IF NOT EXISTS produto_imagens (
                produto_id    INTEGER PRIMARY KEY
                              REFERENCES produtos(id) ON DELETE CASCADE,
                imagem        BLOB NOT NULL,
                miniatura     BLOB NOT NULL,
                atualizado_em TEXT NOT NULL
            );
            """,
        ),
    ),
)


def open_database(path: Path) -> Database:
    """Abre (criando se preciso) o banco local do Estoque."""
    database = Database(path, MIGRATIONS)
    database.connection  # forca a criacao do arquivo e das tabelas
    return database
