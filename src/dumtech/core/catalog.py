"""Catalogo de produtos compartilhado pela plataforma.

Cada aplicativo tem o seu proprio banco e nao enxerga o dos outros. A excecao
combinada sao os dados que so fazem sentido compartilhados: a agenda de
clientes (`core/contacts.py`) e, agora, o catalogo de produtos.

Aqui mora **so o contrato**. Quem sabe ler produto de verdade e o DumTech
Estoque, em `apps/estoque/catalog.py`; quem consome (hoje o Vendas) enxerga
apenas `ItemCatalogo` e os quatro metodos abaixo. Assim o Vendas nao importa
nada do Estoque, e continua funcionando quando o cliente nao comprou o Estoque:
o Hub simplesmente entrega `None` e o item vira texto livre.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ItemCatalogo:
    """Um produto, do jeito que quem vende precisa conhecer."""

    produto_id: int
    codigo: str
    nome: str
    unidade: str = "UN"
    #: casas decimais da unidade (0 = so numero inteiro, 3 = KG)
    casas: int = 0
    preco: float = 0.0
    saldo: float = 0.0

    @property
    def rotulo(self) -> str:
        return f"{self.codigo} - {self.nome}" if self.codigo else self.nome


@runtime_checkable
class Catalogo(Protocol):
    """O que um aplicativo pode pedir ao catalogo da plataforma."""

    def buscar(self, termo: str) -> ItemCatalogo | None:
        """Acha UM produto por codigo de barras, codigo interno ou nome."""

    def procurar(self, termo: str, limite: int = 20) -> list[ItemCatalogo]:
        """Lista candidatos para o usuario escolher."""

    def imagem(self, produto_id: int) -> bytes | None:
        """Foto do produto (JPEG/PNG), ou None quando nao ha."""

    def miniatura(self, produto_id: int) -> bytes | None:
        """Recorte quadrado pequeno da foto, para listas; None quando nao ha."""

    def custo_de(self, produto_id: int) -> float:
        """Custo medio de agora: a venda guarda, para o lucro nao mudar depois."""

    def baixar(
        self, produto_id: int, quantidade: float, documento: str = "", motivo: str = ""
    ) -> None:
        """Tira do estoque (venda). Levanta RegraError se nao for possivel."""

    def devolver(
        self, produto_id: int, quantidade: float, documento: str = "", motivo: str = ""
    ) -> None:
        """Devolve ao estoque (cancelamento ou devolucao do cliente)."""
