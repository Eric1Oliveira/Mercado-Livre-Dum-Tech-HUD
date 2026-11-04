"""A gaveta do dia, para quem recebe dinheiro fora do balcao.

O caixa mora no DumTech Vendas. So que a OS paga na entrega e a conta recebida
em especie no Financeiro tambem vao parar na mesma gaveta, e o fechamento acusava
sobra. Aqui mora **so o contrato**, como em `core/catalog.py`: quem implementa e
`apps/vendas/pedidos.py`, e sem o Vendas na licenca o Hub entrega `None`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Gaveta(Protocol):
    """O que outro modulo pode dizer ao caixa aberto."""

    def entrada(self, valor: float, motivo: str, documento: str = "") -> bool:
        """Entrou dinheiro em especie. False quando nao ha caixa aberto."""

    def desfazer(self, valor: float, documento: str) -> bool:
        """Aquela entrada nao valeu. False quando ela nao esta no caixa aberto."""
