"""O DumTech Estoque publicado como catalogo da plataforma.

Este arquivo e a unica porta de entrada do Estoque para os outros aplicativos.
Ele traduz `Produto` (que so o Estoque conhece) em `ItemCatalogo` (que qualquer
aplicativo entende) e transforma "vendi 2" numa saida de estoque com historico.

Quem monta isso e o Hub, e so quando a licenca libera o Estoque.
"""

from __future__ import annotations

from pathlib import Path

from ...core import eventos
from ...core.catalog import ItemCatalogo
from .database import open_database
from .models import Produto
from .repository import EstoqueRepository

#: de quem e o dado que muda quando alguem passa por esta porta
APP_ID = "estoque"


def _para_item(produto: Produto) -> ItemCatalogo:
    return ItemCatalogo(
        produto_id=produto.id,
        codigo=produto.codigo,
        nome=produto.nome,
        unidade=produto.unidade or "UN",
        casas=produto.casas,
        preco=float(produto.preco_venda or 0),
        saldo=float(produto.quantidade or 0),
    )


class CatalogoEstoque:
    """Implementacao de `core.catalog.Catalogo` em cima do banco do Estoque."""

    def __init__(self, database) -> None:
        self.database = database
        self.repository = EstoqueRepository(database)

    @classmethod
    def abrir(cls, caminho: Path) -> "CatalogoEstoque":
        return cls(open_database(caminho))

    # ------------------------------------------------------------------ leitura
    def buscar(self, termo: str) -> ItemCatalogo | None:
        produto = self.repository.buscar(termo)
        return _para_item(produto) if produto is not None else None

    def procurar(self, termo: str, limite: int = 20) -> list[ItemCatalogo]:
        return [_para_item(p) for p in self.repository.listar(busca=termo)[:limite]]

    # ------------------------------------------------------------------ escrita
    def baixar(
        self, produto_id: int, quantidade: float, documento: str = "", motivo: str = ""
    ) -> None:
        self.repository.registrar_saida(
            produto_id, quantidade, motivo or "Venda", documento=documento
        )
        eventos.avisar(APP_ID)

    def devolver(
        self, produto_id: int, quantidade: float, documento: str = "", motivo: str = ""
    ) -> None:
        self.repository.registrar_entrada(
            produto_id, quantidade, motivo or "Devolucao de venda", documento=documento
        )
        eventos.avisar(APP_ID)

    def close(self) -> None:
        self.database.close()


def abrir_catalogo(caminho: Path) -> CatalogoEstoque:
    """Abre o catalogo a partir do arquivo estoque.db."""
    return CatalogoEstoque.abrir(caminho)
