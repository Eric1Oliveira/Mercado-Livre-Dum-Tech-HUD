"""O DumTech Agenda respondendo a busca geral e a ficha do cliente."""

from __future__ import annotations

from pathlib import Path

from ...core.consulta import Achado
from .database import open_database
from .repository import AgendaRepository


class ConsultaAgenda:
    """Implementacao de `core.consulta.Consulta` em cima do banco da Agenda."""

    app_id = "agenda"

    def __init__(self, database) -> None:
        self.database = database
        self.repository = AgendaRepository(database)

    def _achado(self, compromisso) -> Achado:
        return Achado(
            app_id=self.app_id, tipo="Horário", titulo=compromisso.titulo,
            detalhe=compromisso.cliente, data=compromisso.inicio,
            situacao=compromisso.status_label, tom=compromisso.status_tom,
        )

    def buscar(self, termo: str, limite: int = 5) -> list[Achado]:
        return [self._achado(c) for c in self.repository.listar(busca=termo, limite=limite)]

    def do_cliente(self, nome: str, limite: int = 30) -> list[Achado]:
        lista = self.repository.listar(cliente=nome, limite=limite)
        return [self._achado(c) for c in sorted(lista, key=lambda c: c.inicio, reverse=True)]

    def renomear_cliente(self, antigo: str, novo: str) -> int:
        return self.database.execute(
            "UPDATE compromissos SET cliente = ? WHERE cliente = ? COLLATE NOCASE", (novo, antigo)
        ).rowcount

    def close(self) -> None:
        self.database.close()


def abrir_consulta(caminho: Path) -> ConsultaAgenda:
    return ConsultaAgenda(open_database(caminho))
