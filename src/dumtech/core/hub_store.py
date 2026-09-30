"""Banco de dados do proprio Hub (hub.db).

Guarda apenas informacoes da plataforma - hoje, quando cada aplicativo foi
aberto pela ultima vez. Os dados de cada aplicativo ficam em bancos separados.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .database import Database, Migration
from .paths import get_paths

MIGRATIONS = (
    Migration(
        version=1,
        name="uso dos aplicativos",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS app_usage (
                app_id       TEXT PRIMARY KEY,
                last_opened  TEXT,
                open_count   INTEGER NOT NULL DEFAULT 0
            );
            """,
        ),
    ),
    Migration(
        version=2,
        name="uso por dia (resumo que o Hub manda para a DumTech)",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS uso_diario (
                dia       TEXT NOT NULL,
                app_id    TEXT NOT NULL,
                aberturas INTEGER NOT NULL DEFAULT 0,
                enviado   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (dia, app_id)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_uso_pendente ON uso_diario(enviado, dia);",
        ),
    ),
)


class HubStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db = Database(db_path or get_paths().hub_db, MIGRATIONS)

    def register_open(self, app_id: str) -> None:
        agora = datetime.now()
        self.db.execute(
            """
            INSERT INTO app_usage (app_id, last_opened, open_count)
            VALUES (?, ?, 1)
            ON CONFLICT(app_id) DO UPDATE SET
                last_opened = excluded.last_opened,
                open_count  = app_usage.open_count + 1
            """,
            (app_id, agora.isoformat(timespec="seconds")),
        )
        # o mesmo clique entra no resumo do dia. E so uma contagem por dia e por
        # modulo - sem hora, sem sequencia, sem o que foi feito la dentro.
        self.db.execute(
            """
            INSERT INTO uso_diario (dia, app_id, aberturas, enviado)
            VALUES (?, ?, 1, 0)
            ON CONFLICT(dia, app_id) DO UPDATE SET
                aberturas = uso_diario.aberturas + 1,
                enviado   = 0
            """,
            (agora.date().isoformat(), app_id),
        )

    # ------------------------------------------------------- resumo para enviar
    def uso_pendente(self, limite: int = 200) -> list[dict]:
        """Dias que a DumTech ainda nao recebeu, do mais antigo para o mais novo."""
        linhas = self.db.query(
            """
            SELECT dia, app_id, aberturas FROM uso_diario
             WHERE enviado = 0 AND aberturas > 0
             ORDER BY dia
             LIMIT ?
            """,
            (limite,),
        )
        return [
            {
                "dia": linha["dia"],
                "produto": str(linha["app_id"]).upper(),  # no servidor o codigo e maiusculo
                "aberturas": int(linha["aberturas"] or 0),
            }
            for linha in linhas
        ]

    def marcar_uso_enviado(self, linhas: list[dict]) -> None:
        for item in linhas:
            self.db.execute(
                "UPDATE uso_diario SET enviado = 1 WHERE dia = ? AND app_id = ?",
                (item["dia"], str(item["produto"]).lower()),
            )

    def recent(self, limit: int = 3) -> list[str]:
        """Aplicativos usados por ultimo, do mais recente para o mais antigo."""
        linhas = self.db.query(
            """
            SELECT app_id FROM app_usage
            WHERE last_opened IS NOT NULL
            ORDER BY last_opened DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [linha["app_id"] for linha in linhas]

    def usage(self) -> dict[str, int]:
        """Quantas vezes cada aplicativo foi aberto (ordena o trilho)."""
        linhas = self.db.query("SELECT app_id, open_count FROM app_usage")
        return {linha["app_id"]: int(linha["open_count"] or 0) for linha in linhas}

    def last_opened(self, app_id: str) -> str | None:
        row = self.db.query_one("SELECT last_opened FROM app_usage WHERE app_id = ?", (app_id,))
        return row["last_opened"] if row else None

    def close(self) -> None:
        self.db.close()
