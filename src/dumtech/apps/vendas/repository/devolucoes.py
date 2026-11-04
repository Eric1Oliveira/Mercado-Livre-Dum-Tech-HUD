"""Devolucao: o cliente voltou e trouxe parte (ou tudo) da compra.

Nao mexe na venda original - ela continua sendo o que foi vendido naquele dia.
A devolucao e um registro proprio, com data propria, e e no dia dela que o
dinheiro sai da gaveta. E assim que o fechamento de caixa fecha na pratica.
"""

from __future__ import annotations

from ..models import (
    CANCELADA,
    DEVOLVIDA,
    PENDENTE,
    Devolucao,
    ItemDevolucao,
    VendaError,
    hoje_iso,
    quantidade_texto,
)
from .comum import CENTAVO, agora, dinheiro, quantidade


class DevolucoesMixin:
    """Parte do VendasRepository que recebe mercadoria de volta."""

    # ------------------------------------------------------------------ leitura
    def total_devolvido(self, venda_id: int) -> float:
        return dinheiro(
            self.db.scalar(
                "SELECT COALESCE(SUM(valor), 0) FROM devolucoes WHERE venda_id = ?",
                (venda_id,),
                default=0.0,
            )
        )

    def devolucoes_de(self, venda_id: int) -> list[Devolucao]:
        return [
            Devolucao.from_row(row)
            for row in self.db.query(
                "SELECT * FROM devolucoes WHERE venda_id = ? ORDER BY id DESC", (venda_id,)
            )
        ]

    def listar_devolucoes(self, inicio: str = "", fim: str = "", limite: int = 200):
        sql = """
            SELECT d.*, v.numero AS numero_venda
            FROM devolucoes d
            LEFT JOIN vendas v ON v.id = d.venda_id
            WHERE 1 = 1
        """
        params: list = []
        if inicio:
            sql += " AND date(d.data) >= date(?)"
            params.append(inicio)
        if fim:
            sql += " AND date(d.data) <= date(?)"
            params.append(fim)
        sql += " ORDER BY date(d.data) DESC, d.id DESC LIMIT ?"
        params.append(int(limite))
        return [Devolucao.from_row(row) for row in self.db.query(sql, params)]

    # ------------------------------------------------------------------ escrita
    def devolver(
        self,
        venda_id: int,
        linhas: list[tuple[int, float]],
        motivo: str = "",
        data: str = "",
    ) -> Devolucao:
        """Registra a volta de itens. `linhas` sao pares (id do item, quantidade)."""
        venda = self.obter(venda_id)
        if venda is None:
            raise VendaError("Venda não encontrada.")
        if venda.status == CANCELADA:
            raise VendaError(f"A venda {venda.numero} está cancelada: não há o que devolver.")
        # ninguem pagou, entao nao ha dinheiro para voltar da gaveta - e venda com
        # devolucao nao pode mais ser gravada, entao nunca seria recebida
        if venda.status == PENDENTE:
            raise VendaError(
                f"A venda {venda.numero} ainda não foi paga: cancele a venda "
                "ou receba antes de devolver."
            )
        # o cliente nao pagou na gaveta e as parcelas continuariam cobrando
        if venda.parcelamento is not None:
            raise VendaError(
                f"A venda {venda.numero} é parcelada: cancele a venda para encerrar as parcelas."
            )

        por_id = {item.id: item for item in venda.itens}
        devolvidos: list[ItemDevolucao] = []
        for item_id, qtd in linhas:
            qtd = quantidade(qtd)
            if qtd <= 0:
                continue
            item = por_id.get(item_id)
            if item is None:
                raise VendaError("Item que não pertence a esta venda.")
            if qtd > item.restante + CENTAVO:
                raise VendaError(
                    f"'{item.descricao}': só restam "
                    f"{quantidade_texto(item.restante, item.unidade, item.casas)} "
                    "para devolver."
                )
            devolvidos.append(
                ItemDevolucao(
                    venda_item_id=item.id,
                    quantidade=qtd,
                    valor_unitario=item.valor_unitario,
                    descricao=item.descricao,
                    produto_id=item.produto_id,
                )
            )

        if not devolvidos:
            raise VendaError("Escolha o que está sendo devolvido.")

        # o desconto da venda vale para o que volta tambem: quem pagou menos
        # nao recebe de volta o preco cheio
        fator = (venda.total / venda.subtotal) if venda.subtotal > 0 else 1.0
        valor = dinheiro(sum(linha.total for linha in devolvidos) * fator)

        caixa = self.caixa_aberto()
        momento = agora()
        em_dinheiro = self._sai_da_gaveta(venda, valor)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO devolucoes (venda_id, data, motivo, valor, caixa_id,
                                        em_dinheiro, criado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    venda_id,
                    data or hoje_iso(),
                    motivo.strip(),
                    valor,
                    caixa.id if caixa is not None else 0,
                    em_dinheiro,
                    momento,
                ),
            )
            devolucao_id = int(cursor.lastrowid)
            for linha in devolvidos:
                conn.execute(
                    """
                    INSERT INTO devolucao_itens (devolucao_id, venda_item_id,
                                                 quantidade, valor_unitario)
                    VALUES (?, ?, ?, ?)
                    """,
                    (devolucao_id, linha.venda_item_id, linha.quantidade, linha.valor_unitario),
                )

        # tudo o que foi vendido voltou: a venda vira uma devolucao completa
        restantes = self.itens_de(venda_id)
        if all(item.restante <= CENTAVO for item in restantes):
            self.definir_status(venda_id, DEVOLVIDA)

        devolucao = Devolucao(
            id=devolucao_id,
            venda_id=venda_id,
            numero_venda=venda.numero,
            data=data or hoje_iso(),
            motivo=motivo.strip(),
            valor=valor,
            caixa_id=caixa.id if caixa is not None else 0,
            criado_em=momento,
            em_dinheiro=em_dinheiro,
            itens=devolvidos,
        )
        devolucao.avisos = self._devolver_ao_estoque(
            [
                (por_id[linha.venda_item_id],
                 min(linha.quantidade, por_id[linha.venda_item_id].fora_do_estoque))
                for linha in devolvidos
            ],
            documento=venda.numero,
            motivo=f"Devolução da venda {venda.numero}",
        )
        return devolucao

    def _sai_da_gaveta(self, venda, valor: float) -> float:
        """A devolucao tira da gaveta so o dinheiro em especie que entrou nela."""
        pago = sum(p.valor for p in venda.pagamentos if p.em_dinheiro)
        ja_saiu = float(self.db.scalar(
            "SELECT COALESCE(SUM(em_dinheiro), 0) FROM devolucoes WHERE venda_id = ?",
            (venda.id,), default=0.0,
        ))
        return dinheiro(min(valor, max(pago - ja_saiu, 0.0)))
