"""Uma proposta aprovada vira trabalho em outro aplicativo.

O orcamento aprovado ja tem tudo: cliente, itens, quantidades, precos e
desconto. Redigitar isso no balcao ou na ficha da oficina e trabalho dobrado
com chance de erro - e o erro aqui e cobrar diferente do que foi combinado.

Contrato, e nada mais - como em `core/catalog.py`. Quem sabe abrir uma venda e
o DumTech Vendas; quem sabe abrir uma ordem e o DumTech Ordem de Servico. O
Orcamentos so enxerga `Destino` e nao importa nada de nenhum dos dois: sem
esses modulos na licenca, o Hub entrega uma lista vazia e o botao nao aparece.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ItemPedido:
    descricao: str
    quantidade: float = 1.0
    valor_unitario: float = 0.0
    unidade: str = ""
    desconto: float = 0.0
    #: produto do Estoque (0 = item digitado). Viaja junto para o destino dar
    #: baixa na hora certa - na venda recebida, na ordem entregue.
    produto_id: int = 0
    codigo: str = ""


@dataclass(frozen=True)
class Pedido:
    """O que a proposta aprovada leva consigo."""

    cliente: str = ""
    #: numero da proposta - vira a referencia do documento criado
    origem: str = ""
    itens: list[ItemPedido] = field(default_factory=list)
    desconto: float = 0.0
    observacoes: str = ""


def precos_fechados(pedido: Pedido) -> tuple[list[float], float]:
    """Unitarios e desconto do documento para o total bater no centavo.

    Quem recebe a proposta nao tem desconto por item: ele entra no preco. So
    que R$ 89,70 em 3 linhas com desconto nem sempre vira um unitario de dois
    digitos. O unitario arredonda para cima e a sobra entra no desconto do
    documento, porque cobrar um centavo diferente do combinado e erro.
    """
    unitarios: list[float] = []
    sobra = 0.0
    for item in pedido.itens:
        quantidade = float(item.quantidade or 1) or 1.0
        liquido = round(
            max(float(item.valor_unitario or 0) * quantidade - float(item.desconto or 0), 0.0), 2
        )
        unitario = math.ceil(round(liquido / quantidade * 100, 6)) / 100
        unitarios.append(unitario)
        sobra += round(unitario * quantidade, 2) - liquido
    return unitarios, round(float(pedido.desconto or 0) + sobra, 2)


@runtime_checkable
class Destino(Protocol):
    """Um aplicativo capaz de receber uma proposta aprovada."""

    #: como o destino se chama no botao ("Vendas", "Ordem de Servico")
    titulo: str
    app_id: str

    def abrir(self, pedido: Pedido) -> str:
        """Cria o documento e devolve o numero criado (VEN-..., OS-...)."""
