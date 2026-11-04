"""O DumTech Estoque respondendo a busca geral."""

from __future__ import annotations

from pathlib import Path

from ...core.consulta import Achado
from .database import open_database
from .models import quantidade_texto
from .repository import EstoqueRepository


class ConsultaEstoque:
    """Implementacao de `core.consulta.Consulta`. Produto nao tem cliente."""

    app_id = "estoque"

    def __init__(self, database) -> None:
        self.database = database
        self.repository = EstoqueRepository(database)

    def buscar(self, termo: str, limite: int = 5) -> list[Achado]:
        return [
            Achado(app_id=self.app_id, tipo="Produto", titulo=p.nome,
                   detalhe=quantidade_texto(p.quantidade, p.unidade), valor=p.preco_venda)
            for p in self.repository.listar(busca=termo)[:limite]
        ]

    def do_cliente(self, nome: str, limite: int = 30) -> list[Achado]:
        return []

    def renomear_cliente(self, antigo: str, novo: str) -> int:
        return 0

    def close(self) -> None:
        self.database.close()


def abrir_consulta(caminho: Path) -> ConsultaEstoque:
    return ConsultaEstoque(open_database(caminho))
