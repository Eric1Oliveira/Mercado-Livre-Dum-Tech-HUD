"""Pecas e servicos de uma ordem.

Separar os dois responde "quanto foi material e quanto foi mao de obra", que e
a conta que o dono do negocio precisa para saber se o servico valeu a pena.
"""

from __future__ import annotations

from ..models import PECA, SERVICO, ItemOS, Ordem, OrdemError
from .comum import dinheiro, quantidade


class ItensMixin:
    """Parte do OrdensRepository que cuida do que foi usado no servico."""

    def itens_de(self, ordem_id: int) -> list[ItemOS]:
        return [
            ItemOS.from_row(row)
            for row in self.db.query(
                "SELECT * FROM os_itens WHERE ordem_id = ? ORDER BY id", (ordem_id,)
            )
        ]

    def _gravar_itens(self, ordem: Ordem) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM os_itens WHERE ordem_id = ?", (ordem.id,))
            for item in ordem.itens:
                if not item.descricao.strip():
                    raise OrdemError("Todo item precisa de uma descricao.")
                if item.tipo not in (PECA, SERVICO):
                    raise OrdemError("O item precisa ser peca ou servico.")
                if quantidade(item.quantidade) <= 0:
                    raise OrdemError(
                        f"A quantidade de '{item.descricao}' precisa ser maior que zero."
                    )
                conn.execute(
                    """
                    INSERT INTO os_itens (ordem_id, tipo, descricao, quantidade,
                                          valor_unitario, produto_id, codigo)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ordem.id,
                        item.tipo,
                        item.descricao.strip(),
                        quantidade(item.quantidade),
                        dinheiro(item.valor_unitario),
                        # o vinculo com o Estoque: e ele que permite dar baixa
                        # na peca quando a ordem for entregue
                        int(item.produto_id or 0),
                        (item.codigo or "").strip(),
                    ),
                )
        ordem.itens = self.itens_de(ordem.id)
