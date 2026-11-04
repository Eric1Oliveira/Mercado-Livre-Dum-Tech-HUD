"""Estrutura do banco local do DumTech Ordem de Servico (ordens.db)."""

from __future__ import annotations

from pathlib import Path

from ...core.database import Database, Migration
from ...core.recorrencia import TABELA as TABELA_RECORRENCIAS

MIGRATIONS = (
    Migration(
        version=1,
        name="ordens de servico",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS ordens (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                numero       TEXT NOT NULL UNIQUE,
                cliente      TEXT NOT NULL DEFAULT '',
                telefone     TEXT NOT NULL DEFAULT '',
                equipamento  TEXT NOT NULL DEFAULT '',
                defeito      TEXT NOT NULL DEFAULT '',
                diagnostico  TEXT NOT NULL DEFAULT '',
                servico      TEXT NOT NULL DEFAULT '',
                valor        REAL NOT NULL DEFAULT 0,
                status       TEXT NOT NULL DEFAULT 'aberta',
                tecnico      TEXT NOT NULL DEFAULT '',
                aberta_em    TEXT NOT NULL,
                prazo        TEXT NOT NULL DEFAULT '',
                concluida_em TEXT,
                observacoes  TEXT NOT NULL DEFAULT '',
                criado_em    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ordens_status ON ordens(status);
            CREATE INDEX IF NOT EXISTS idx_ordens_data ON ordens(aberta_em);
            """,
        ),
    ),
    Migration(
        version=2,
        name="itens, historico, aprovacao e garantia",
        statements=(
            # `ordens` so ganha colunas: nenhum tipo muda, ALTER TABLE resolve.
            """
            ALTER TABLE ordens ADD COLUMN acessorios TEXT NOT NULL DEFAULT '';
            ALTER TABLE ordens ADD COLUMN condicao TEXT NOT NULL DEFAULT '';
            ALTER TABLE ordens ADD COLUMN senha TEXT NOT NULL DEFAULT '';
            ALTER TABLE ordens ADD COLUMN aprovado_em TEXT NOT NULL DEFAULT '';
            ALTER TABLE ordens ADD COLUMN aprovado_por TEXT NOT NULL DEFAULT '';
            ALTER TABLE ordens ADD COLUMN entregue_em TEXT NOT NULL DEFAULT '';
            ALTER TABLE ordens ADD COLUMN garantia_dias INTEGER NOT NULL DEFAULT 90;
            ALTER TABLE ordens ADD COLUMN desconto REAL NOT NULL DEFAULT 0;

            -- separar peca de servico responde "quanto foi material e quanto
            -- foi mao de obra", que e a conta que o dono do negocio precisa
            CREATE TABLE IF NOT EXISTS os_itens (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                ordem_id       INTEGER NOT NULL REFERENCES ordens(id) ON DELETE CASCADE,
                tipo           TEXT    NOT NULL DEFAULT 'servico'
                               CHECK (tipo IN ('peca', 'servico')),
                descricao      TEXT    NOT NULL,
                quantidade     REAL    NOT NULL DEFAULT 1,
                valor_unitario REAL    NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_os_itens ON os_itens(ordem_id);

            -- cada mudanca de etapa com data e hora: e o que responde
            -- "quando voces me entregaram?"
            CREATE TABLE IF NOT EXISTS os_historico (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ordem_id   INTEGER NOT NULL REFERENCES ordens(id) ON DELETE CASCADE,
                status     TEXT    NOT NULL,
                observacao TEXT    NOT NULL DEFAULT '',
                criado_em  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_os_hist ON os_historico(ordem_id);

            -- a ordem que ja existia ganha a primeira linha do historico, para
            -- nao nascer sem passado
            INSERT INTO os_historico (ordem_id, status, observacao, criado_em)
            SELECT id, status, 'Situacao anterior a atualizacao do sistema', criado_em
            FROM ordens;

            -- e a que ja estava entregue passa a ter a data da entrega
            UPDATE ordens SET entregue_em = COALESCE(concluida_em, aberta_em)
            WHERE status = 'entregue';
            """,
        ),
    ),
    Migration(
        version=3,
        name="peca ligada ao produto do Estoque",
        statements=(
            # Sem isto a peca da ordem era so um texto: o tecnico trocava a
            # fonte do notebook e o saldo do Estoque continuava o mesmo. Com o
            # produto identificado, entregar a ordem da baixa igual a venda.
            """
            ALTER TABLE os_itens ADD COLUMN produto_id INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE os_itens ADD COLUMN codigo TEXT NOT NULL DEFAULT '';
            ALTER TABLE ordens ADD COLUMN baixa_estoque TEXT NOT NULL DEFAULT '';
            """,
        ),
    ),
    Migration(
        version=4,
        name="servico recorrente",
        statements=(
            # O contrato de manutencao (a preventiva a cada tres meses) e cada
            # ordem que ele abre, marcada com o numero dele.
            TABELA_RECORRENCIAS,
            """
            ALTER TABLE ordens ADD COLUMN recorrencia TEXT NOT NULL DEFAULT '';
            CREATE INDEX IF NOT EXISTS idx_ordens_recorrencia ON ordens(recorrencia, prazo);
            """,
        ),
    ),
    Migration(
        version=5,
        name="estoque por linha",
        statements=(
            # O que ja deu baixa conta como saido por inteiro: e o que sempre
            # se supos. Sem isto, cancelar nao sabia o que devolver.
            """
            ALTER TABLE os_itens ADD COLUMN baixado REAL NOT NULL DEFAULT 0;
            UPDATE os_itens SET baixado = quantidade
                WHERE tipo = 'peca' AND produto_id > 0 AND ordem_id IN
                    (SELECT id FROM ordens WHERE TRIM(baixa_estoque) <> '');
            """,
        ),
    ),
    Migration(
        version=6,
        name="checklist, fotos e assinatura",
        statements=(
            # as fotos ficam no banco, e nao numa pasta: assim vao junto no backup
            """
            CREATE TABLE IF NOT EXISTS os_checklist (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ordem_id INTEGER NOT NULL REFERENCES ordens(id) ON DELETE CASCADE,
                texto    TEXT    NOT NULL,
                feito    INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_os_checklist ON os_checklist(ordem_id);

            CREATE TABLE IF NOT EXISTS os_fotos (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ordem_id  INTEGER NOT NULL REFERENCES ordens(id) ON DELETE CASCADE,
                imagem    BLOB    NOT NULL,
                criado_em TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_os_fotos ON os_fotos(ordem_id);

            ALTER TABLE ordens ADD COLUMN assinatura BLOB;
            ALTER TABLE ordens ADD COLUMN assinado_em TEXT NOT NULL DEFAULT '';
            """,
        ),
    ),
)


def open_database(path: Path) -> Database:
    """Abre (criando se preciso) o banco local da Ordem de Servico."""
    database = Database(path, MIGRATIONS)
    database.connection  # forca a criacao do arquivo e das tabelas
    return database
