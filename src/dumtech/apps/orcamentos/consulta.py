"""O DumTech Orcamentos respondendo a busca geral e a ficha do cliente."""

from __future__ import annotations

from pathlib import Path

from ...core.consulta import Achado
from .database import open_database
from .repository import OrcamentosRepository


class ConsultaOrcamentos:
    """Implementacao de `core.consulta.Consulta` em cima do banco do Orcamentos."""

    app_id = "orcamentos"

    def __init__(self, database) -> None:
        self.database = database
        self.repository = OrcamentosRepository(database)

    def _achado(self, orcamento) -> Achado:
        return Achado(
            app_id=self.app_id, tipo="Proposta", titulo=orcamento.numero,
            detalhe=orcamento.cliente, data=orcamento.data, valor=orcamento.total,
            situacao=orcamento.status_label, tom=orcamento.status_tom,
        )

    def buscar(self, termo: str, limite: int = 5) -> list[Achado]:
        return [self._achado(o) for o in self.repository.listar(busca=termo, limite=limite)]

    def do_cliente(self, nome: str, limite: int = 30) -> list[Achado]:
        return [self._achado(o) for o in self.repository.listar(cliente=nome, limite=limite)]

    def renomear_cliente(self, antigo: str, novo: str) -> int:
        return self.database.execute(
            "UPDATE orcamentos SET cliente = ? WHERE cliente = ? COLLATE NOCASE", (novo, antigo)
        ).rowcount

    def close(self) -> None:
        self.database.close()


def abrir_consulta(caminho: Path) -> ConsultaOrcamentos:
    return ConsultaOrcamentos(open_database(caminho))
