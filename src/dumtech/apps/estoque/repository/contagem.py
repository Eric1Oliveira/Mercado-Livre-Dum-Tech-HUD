"""Contagem fisica (balanco).

Uma folha de contagem por vez: voce percorre a loja anotando o que existe de
verdade e, no fim, aplica. Cada divergencia vira um ajuste no historico - o
saldo nunca muda sem deixar rastro.
"""

from __future__ import annotations

from ..models import EstoqueError, ItemContagem
from .comum import agora, igual, quantidade

SELECT_ITENS = """
    SELECT c.produto_id, c.contado, c.atualizado_em,
           p.codigo AS produto_codigo, p.nome AS produto_nome, p.unidade,
           p.quantidade AS saldo_sistema
    FROM contagem_itens c
    JOIN produtos p ON p.id = c.produto_id
"""


class ContagemMixin:
    """Parte do EstoqueRepository que cuida do balanco."""

    def contagem(self) -> list[ItemContagem]:
        """A folha atual, com as divergencias primeiro."""
        rows = self.db.query(
            SELECT_ITENS + " ORDER BY p.nome COLLATE NOCASE"
        )
        itens = [ItemContagem.from_row(row) for row in rows]
        itens.sort(key=lambda i: (i.confere, i.produto_nome.lower()))
        return itens

    def contagem_em_andamento(self) -> bool:
        return bool(int(self.db.scalar("SELECT COUNT(*) FROM contagem_itens")))

    def contar(self, produto_id: int, contado: float) -> ItemContagem:
        """Anota quanto existe de verdade. Contar de novo substitui o valor."""
        contado = quantidade(contado)
        if contado < 0:
            raise EstoqueError("A quantidade contada não pode ser negativa.")
        produto = self.obter(produto_id)
        if produto is None:
            raise EstoqueError("Selecione um produto válido.")

        self.db.execute(
            """
            INSERT INTO contagem_itens (produto_id, contado, atualizado_em)
            VALUES (?, ?, ?)
            ON CONFLICT(produto_id) DO UPDATE SET
                contado = excluded.contado,
                atualizado_em = excluded.atualizado_em
            """,
            (produto_id, contado, agora()),
        )
        return ItemContagem(
            produto_id=produto_id,
            produto_codigo=produto.codigo,
            produto_nome=produto.nome,
            unidade=produto.unidade,
            saldo_sistema=produto.quantidade,
            contado=contado,
            atualizado_em=agora(),
        )

    def remover_da_contagem(self, produto_id: int) -> None:
        self.db.execute("DELETE FROM contagem_itens WHERE produto_id = ?", (produto_id,))

    def cancelar_contagem(self) -> None:
        """Joga a folha fora sem mexer em saldo nenhum."""
        self.db.execute("DELETE FROM contagem_itens")

    def aplicar_contagem(self, observacao: str = "") -> int:
        """Transforma as divergencias em ajustes. Devolve quantos saldos mudaram."""
        itens = self.contagem()
        if not itens:
            raise EstoqueError("A folha de contagem está vazia.")

        texto = observacao.strip() or "Ajuste da contagem de estoque"
        ajustados = 0
        for item in itens:
            if igual(item.contado, item.saldo_sistema):
                continue
            self.ajustar(item.produto_id, item.contado, texto)
            ajustados += 1
        self.cancelar_contagem()
        return ajustados

    def resumo_contagem(self) -> tuple[int, int]:
        """(itens contados, itens com divergencia)."""
        itens = self.contagem()
        return len(itens), sum(1 for item in itens if not item.confere)
