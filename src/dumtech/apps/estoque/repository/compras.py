"""Fornecedores e pedidos de compra.

A entrada registra o que chegou. O pedido vem antes: o que foi encomendado, de
quem e para quando. Receber o pedido e a mesma entrada de sempre, sem redigitar.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from ..models import (
    PEDIDO_ABERTO,
    PEDIDO_CANCELADO,
    PEDIDO_RECEBIDO,
    EstoqueError,
    Fornecedor,
    ItemEntrada,
    ItemPedidoCompra,
    PedidoCompra,
)
from .comum import agora, dinheiro, quantidade


class ComprasMixin:
    """Parte do EstoqueRepository que fala com quem vende para a loja."""

    # ------------------------------------------------------------- fornecedores
    def listar_fornecedores(self, busca: str = "", incluir_inativos: bool = False) -> list[Fornecedor]:
        sql = "SELECT * FROM fornecedores WHERE 1 = 1"
        params: list = []
        if not incluir_inativos:
            sql += " AND ativo = 1"
        if busca.strip():
            sql += " AND (nome LIKE ? OR documento LIKE ? OR telefone LIKE ?)"
            params += [f"%{busca.strip()}%"] * 3
        return [Fornecedor.from_row(row)
                for row in self.db.query(f"{sql} ORDER BY nome COLLATE NOCASE", params)]

    def salvar_fornecedor(self, fornecedor: Fornecedor) -> Fornecedor:
        if not fornecedor.nome.strip():
            raise EstoqueError("Informe o nome do fornecedor.")
        valores = (fornecedor.nome.strip(), fornecedor.documento.strip(),
                   fornecedor.telefone.strip(), fornecedor.email.strip(),
                   fornecedor.observacoes.strip(), int(fornecedor.ativo))
        try:
            if fornecedor.id is None:
                cursor = self.db.execute(
                    "INSERT INTO fornecedores (nome, documento, telefone, email, observacoes,"
                    " ativo, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?)", (*valores, agora()),
                )
                fornecedor.id = int(cursor.lastrowid)
            else:
                self.db.execute(
                    "UPDATE fornecedores SET nome = ?, documento = ?, telefone = ?, email = ?,"
                    " observacoes = ?, ativo = ? WHERE id = ?", (*valores, fornecedor.id),
                )
        except sqlite3.IntegrityError as erro:
            raise EstoqueError(
                f"Já existe um fornecedor chamado '{fornecedor.nome.strip()}'."
            ) from erro
        return fornecedor

    def excluir_fornecedor(self, fornecedor_id: int) -> None:
        """Os produtos guardam o nome em texto: apagar o cadastro nao os afeta."""
        self.db.execute("DELETE FROM fornecedores WHERE id = ?", (fornecedor_id,))

    # ------------------------------------------------------------------ pedidos
    def listar_pedidos(self, busca: str = "", status: str = "", limite: int = 500) -> list[PedidoCompra]:
        sql = "SELECT * FROM pedidos_compra WHERE 1 = 1"
        params: list = []
        if busca.strip():
            sql += " AND (numero LIKE ? OR fornecedor LIKE ?)"
            params += [f"%{busca.strip()}%"] * 2
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY date(data) DESC, id DESC LIMIT ?"
        params.append(int(limite))
        pedidos = [PedidoCompra.from_row(row) for row in self.db.query(sql, params)]
        for pedido in pedidos:
            pedido.itens = self.itens_do_pedido(pedido.id)
        return pedidos

    def obter_pedido(self, pedido_id: int) -> PedidoCompra | None:
        row = self.db.query_one("SELECT * FROM pedidos_compra WHERE id = ?", (pedido_id,))
        if row is None:
            return None
        pedido = PedidoCompra.from_row(row)
        pedido.itens = self.itens_do_pedido(pedido.id)
        return pedido

    def itens_do_pedido(self, pedido_id: int) -> list[ItemPedidoCompra]:
        return [
            ItemPedidoCompra(
                produto_id=row["produto_id"], quantidade=float(row["quantidade"]),
                custo_unitario=float(row["custo_unitario"]),
                produto_nome=row["nome"], unidade=row["unidade"],
            )
            for row in self.db.query(
                """
                SELECT i.*, p.nome, p.unidade FROM pedido_compra_itens i
                JOIN produtos p ON p.id = i.produto_id
                WHERE i.pedido_id = ? ORDER BY i.id
                """,
                (pedido_id,),
            )
        ]

    def proximo_pedido(self) -> str:
        """PC-2026-0001. Continua da maior numeracao ja usada no ano."""
        prefixo = f"PC-{date.today().year}-"
        maior = 0
        for row in self.db.query(
            "SELECT numero FROM pedidos_compra WHERE numero LIKE ?", (f"{prefixo}%",)
        ):
            sufixo = str(row["numero"])[len(prefixo):]
            if sufixo.isdigit():
                maior = max(maior, int(sufixo))
        return f"{prefixo}{maior + 1:04d}"

    def salvar_pedido(self, pedido: PedidoCompra) -> PedidoCompra:
        if not pedido.itens:
            raise EstoqueError("Adicione pelo menos um produto ao pedido.")
        if any(quantidade(item.quantidade) <= 0 for item in pedido.itens):
            raise EstoqueError("Toda linha do pedido precisa de quantidade.")
        pedido.numero = pedido.numero.strip() or self.proximo_pedido()
        pedido.data = pedido.data or date.today().isoformat()
        valores = (pedido.numero, pedido.fornecedor.strip(), pedido.data, pedido.previsao or "",
                   pedido.observacoes.strip())
        with self.db.transaction() as conn:
            if pedido.id is None:
                cursor = conn.execute(
                    "INSERT INTO pedidos_compra (numero, fornecedor, data, previsao, observacoes,"
                    " criado_em) VALUES (?, ?, ?, ?, ?, ?)", (*valores, agora()),
                )
                pedido.id = int(cursor.lastrowid)
            else:
                conn.execute(
                    "UPDATE pedidos_compra SET numero = ?, fornecedor = ?, data = ?, previsao = ?,"
                    " observacoes = ? WHERE id = ?", (*valores, pedido.id),
                )
                conn.execute("DELETE FROM pedido_compra_itens WHERE pedido_id = ?", (pedido.id,))
            for item in pedido.itens:
                conn.execute(
                    "INSERT INTO pedido_compra_itens (pedido_id, produto_id, quantidade,"
                    " custo_unitario) VALUES (?, ?, ?, ?)",
                    (pedido.id, item.produto_id, quantidade(item.quantidade),
                     dinheiro(item.custo_unitario)),
                )
        return self.obter_pedido(pedido.id)

    def gerar_pedido_de_reposicao(self, fornecedor: str = "") -> PedidoCompra:
        """O que esta no minimo vira pedido, com a quantidade que falta."""
        produtos = [p for p in self.a_comprar() if p.sugestao_compra > 0
                    and (not fornecedor.strip() or p.fornecedor == fornecedor.strip())]
        if not produtos:
            raise EstoqueError("Nenhum produto precisa de reposição agora.")
        return self.salvar_pedido(PedidoCompra(
            fornecedor=fornecedor.strip() or produtos[0].fornecedor,
            itens=[ItemPedidoCompra(p.id, p.sugestao_compra, p.preco_custo) for p in produtos],
        ))

    def receber_pedido(self, pedido_id: int) -> PedidoCompra:
        """A mercadoria chegou: vira entrada, com saldo e custo medio, uma vez so."""
        pedido = self.obter_pedido(pedido_id)
        if pedido is None:
            raise EstoqueError("Pedido não encontrado.")
        if pedido.status != PEDIDO_ABERTO:
            raise EstoqueError(f"O pedido {pedido.numero} já está {pedido.status_label.lower()}.")
        with self.db.transaction() as conn:
            self.entrada_em_lote(
                [ItemEntrada(i.produto_id, i.quantidade, i.custo_unitario) for i in pedido.itens],
                fornecedor=pedido.fornecedor, documento=pedido.numero,
                observacao=f"Pedido {pedido.numero} recebido",
            )
            conn.execute(
                "UPDATE pedidos_compra SET status = ?, recebido_em = ? WHERE id = ?",
                (PEDIDO_RECEBIDO, date.today().isoformat(), pedido_id),
            )
        return self.obter_pedido(pedido_id)

    def cancelar_pedido(self, pedido_id: int) -> None:
        pedido = self.obter_pedido(pedido_id)
        if pedido is None:
            raise EstoqueError("Pedido não encontrado.")
        if pedido.status == PEDIDO_RECEBIDO:
            raise EstoqueError("Este pedido já entrou no estoque. Registre uma saída para ajustar.")
        self.db.execute("UPDATE pedidos_compra SET status = ? WHERE id = ?",
                        (PEDIDO_CANCELADO, pedido_id))

    def excluir_pedido(self, pedido_id: int) -> None:
        pedido = self.obter_pedido(pedido_id)
        if pedido is not None and pedido.status == PEDIDO_RECEBIDO:
            raise EstoqueError("Pedido recebido é histórico e não pode ser apagado.")
        self.db.execute("DELETE FROM pedidos_compra WHERE id = ?", (pedido_id,))
