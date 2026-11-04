"""O que cada modulo responde sobre o que guarda.

Cada aplicativo tem o seu banco e nao enxerga o dos outros. So que tres perguntas
atravessam todos eles: "onde esta aquela venda?" (a busca geral), "o que esse
cliente ja fez aqui?" (a ficha) e "esse cliente mudou de nome". Sem uma porta
comum, cada uma viraria uma ponte propria.

Aqui mora **so o contrato**, como em `core/catalog.py`. Quem implementa e o
`consulta.py` de cada aplicativo, e o Hub entrega so os que a licenca liberou.

O cliente continua sendo ligado pelo nome: e o que os modulos sempre gravaram.
Duas pessoas com o mesmo nome aparecem juntas na ficha.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Achado:
    """Uma linha da busca ou da ficha."""

    app_id: str
    #: o que e, como a pessoa le: Venda, OS, Proposta
    tipo: str
    #: o que identifica: VEN-2026-0001; e o que a tela de lista procura
    titulo: str
    detalhe: str = ""
    data: str = ""
    valor: float = 0.0
    situacao: str = ""
    tom: str = "muted"


@runtime_checkable
class Consulta(Protocol):
    app_id: str

    def buscar(self, termo: str, limite: int = 5) -> list[Achado]:
        """O que combina com o que foi digitado."""

    def do_cliente(self, nome: str, limite: int = 30) -> list[Achado]:
        """O que este cliente tem aqui, do mais recente para o mais antigo."""

    def renomear_cliente(self, antigo: str, novo: str) -> int:
        """Troca o nome gravado e devolve quantas linhas mudaram."""

    def close(self) -> None:
        """Solta o banco."""
