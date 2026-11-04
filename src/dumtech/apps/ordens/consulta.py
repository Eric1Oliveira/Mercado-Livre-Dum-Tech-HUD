"""O DumTech Ordem de Servico respondendo a busca geral e a ficha do cliente."""

from __future__ import annotations

from pathlib import Path

from ...core.consulta import Achado
from .database import open_database
from .repository import OrdensRepository


class ConsultaOrdens:
    """Implementacao de `core.consulta.Consulta` em cima do banco das Ordens."""

    app_id = "ordens"

    def __init__(self, database) -> None:
        self.database = database
        self.repository = OrdensRepository(database)

    def _achado(self, ordem) -> Achado:
        return Achado(
            app_id=self.app_id, tipo="OS", titulo=ordem.numero,
            detalhe=" · ".join(p for p in (ordem.cliente, ordem.assunto) if p),
            data=ordem.aberta_em, valor=ordem.total,
            situacao=ordem.status_label, tom=ordem.status_tom,
        )

    def buscar(self, termo: str, limite: int = 5) -> list[Achado]:
        return [self._achado(o) for o in self.repository.listar(busca=termo, limite=limite)]

    def do_cliente(self, nome: str, limite: int = 30) -> list[Achado]:
        return [self._achado(o) for o in self.repository.listar(cliente=nome, limite=limite)]

    def renomear_cliente(self, antigo: str, novo: str) -> int:
        with self.database.transaction() as conn:
            mudou = conn.execute("UPDATE ordens SET cliente = ? WHERE cliente = ? COLLATE NOCASE",
                                 (novo, antigo)).rowcount
            conn.execute("UPDATE recorrencias SET cliente = ? WHERE cliente = ? COLLATE NOCASE",
                         (novo, antigo))
        return mudou

    def close(self) -> None:
        self.database.close()


def abrir_consulta(caminho: Path) -> ConsultaOrdens:
    return ConsultaOrdens(open_database(caminho))
