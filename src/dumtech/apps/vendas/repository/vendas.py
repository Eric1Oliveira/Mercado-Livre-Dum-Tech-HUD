"""A venda em si: ler, gravar, cancelar.

Um item de venda so vira baixa de estoque se ele veio do catalogo. Item de
texto livre (quem nao comprou o Estoque) e apenas descricao e preco.
"""

from __future__ import annotations

from datetime import date

from ....core.errors import RegraError
from ..models import CANCELADA, ItemVenda, Venda, VendaError
from .comum import agora, dinheiro, quantidade

#: soma o que ja foi devolvido de cada item, sem gravar isso duas vezes
SELECT_ITENS = """
    SELECT i.*, COALESCE((
        SELECT SUM(d.quantidade) FROM devolucao_itens d WHERE d.venda_item_id = i.id
    ), 0) AS devolvido
    FROM venda_itens i
    WHERE i.venda_id = ?
    ORDER BY i.id
"""


class VendasMixin:
    """Parte do VendasRepository que cuida da venda."""

    # ------------------------------------------------------------------ leitura
    def listar(
        self,
        busca: str = "",
        status: str = "",
        inicio: str = "",
        fim: str = "",
        limite: int = 500,
    ) -> list[Venda]:
        sql = "SELECT * FROM vendas WHERE 1 = 1"
        params: list = []
        if busca.strip():
            sql += " AND (numero LIKE ? OR cliente LIKE ? OR forma_pagamento LIKE ?)"
            alvo = f"%{busca.strip()}%"
            params += [alvo, alvo, alvo]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if inicio:
            sql += " AND date(data) >= date(?)"
            params.append(inicio)
        if fim:
            sql += " AND date(data) <= date(?)"
            params.append(fim)
        sql += " ORDER BY date(data) DESC, id DESC LIMIT ?"
        params.append(int(limite))

        vendas = [Venda.from_row(row) for row in self.db.query(sql, params)]
        devolvido = self._devolvido_por_venda()
        for venda in vendas:
            venda.itens = self.itens_de(venda.id)
            venda.pagamentos = self.pagamentos_de(venda.id)
            venda.devolvido = devolvido.get(venda.id, 0.0)
        return vendas

    def obter(self, venda_id: int) -> Venda | None:
        row = self.db.query_one("SELECT * FROM vendas WHERE id = ?", (venda_id,))
        if row is None:
            return None
        venda = Venda.from_row(row)
        venda.itens = self.itens_de(venda.id)
        venda.pagamentos = self.pagamentos_de(venda.id)
        venda.devolvido = self.total_devolvido(venda.id)
        return venda

    def itens_de(self, venda_id: int) -> list[ItemVenda]:
        return [ItemVenda.from_row(row) for row in self.db.query(SELECT_ITENS, (venda_id,))]

    def _devolvido_por_venda(self) -> dict[int, float]:
        return {
            row["venda_id"]: float(row["valor"])
            for row in self.db.query(
                "SELECT venda_id, SUM(valor) AS valor FROM devolucoes GROUP BY venda_id"
            )
        }

    def proximo_numero(self) -> str:
        """VEN-2026-0001. Continua da maior numeracao ja usada no ano."""
        ano = date.today().year
        prefixo = f"VEN-{ano}-"
        maior = 0
        for row in self.db.query(
            "SELECT numero FROM vendas WHERE numero LIKE ?", (f"{prefixo}%",)
        ):
            sufixo = str(row["numero"])[len(prefixo):]
            if sufixo.isdigit():
                maior = max(maior, int(sufixo))
        return f"{prefixo}{maior + 1:04d}"

    # ------------------------------------------------------------------ escrita
    def salvar(self, venda: Venda) -> Venda:
        """Grava a venda inteira (cabecalho, itens e pagamentos)."""
        self._validar(venda)
        momento = agora()
        valores = (
            venda.numero.strip(),
            venda.cliente.strip(),
            venda.data,
            (venda.resumo_pagamento or venda.forma_pagamento).strip(),
            venda.status,
            dinheiro(venda.desconto),
            venda.observacoes.strip(),
            int(venda.caixa_id or 0),
            dinheiro(venda.troco),
        )
        if venda.id is None:
            cursor = self.db.execute(
                """
                INSERT INTO vendas (numero, cliente, data, forma_pagamento, status,
                                    desconto, observacoes, caixa_id, troco, criado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                valores + (momento,),
            )
            venda.id = int(cursor.lastrowid)
            venda.criado_em = momento
        else:
            self.db.execute(
                """
                UPDATE vendas SET numero = ?, cliente = ?, data = ?, forma_pagamento = ?,
                                  status = ?, desconto = ?, observacoes = ?,
                                  caixa_id = ?, troco = ?
                WHERE id = ?
                """,
                valores + (venda.id,),
            )
        venda.forma_pagamento = valores[3]
        self._gravar_itens(venda)
        self.gravar_pagamentos(venda.id, venda.pagamentos)
        venda.itens = self.itens_de(venda.id)
        return venda

    def definir_status(self, venda_id: int, status: str) -> None:
        self.db.execute("UPDATE vendas SET status = ? WHERE id = ?", (status, venda_id))

    def cancelar(self, venda_id: int, motivo: str) -> Venda:
        """Cancela a venda inteira e devolve o que saiu do estoque.

        Motivo e obrigatorio: cancelamento sem explicacao e o buraco por onde
        some dinheiro de balcao.
        """
        motivo = motivo.strip()
        if not motivo:
            raise VendaError("Informe o motivo do cancelamento.")

        venda = self.obter(venda_id)
        if venda is None:
            raise VendaError("Venda não encontrada.")
        if venda.status == CANCELADA:
            raise VendaError(f"A venda {venda.numero} já está cancelada.")

        self.db.execute(
            "UPDATE vendas SET status = ?, cancelada_em = ?, motivo_cancelamento = ?"
            " WHERE id = ?",
            (CANCELADA, agora(), motivo, venda_id),
        )
        venda.status = CANCELADA
        venda.motivo_cancelamento = motivo
        # o que ja tinha voltado por devolucao nao volta de novo
        venda.avisos = self._devolver_ao_estoque(
            [(item, item.restante) for item in venda.itens],
            documento=venda.numero,
            motivo=f"Cancelamento: {motivo}",
        )
        return venda

    def excluir(self, venda_id: int) -> None:
        venda = self.obter(venda_id)
        if venda is not None and venda.status != CANCELADA and venda.itens:
            raise VendaError(
                f"A venda {venda.numero} não pode ser apagada. "
                "Cancele a venda para manter o histórico."
            )
        self.db.execute("DELETE FROM vendas WHERE id = ?", (venda_id,))

    # -------------------------------------------------------------------- itens
    def _gravar_itens(self, venda: Venda) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM venda_itens WHERE venda_id = ?", (venda.id,))
            for item in venda.itens:
                conn.execute(
                    """
                    INSERT INTO venda_itens (venda_id, descricao, quantidade,
                                             valor_unitario, produto_id, codigo,
                                             unidade, casas)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        venda.id,
                        item.descricao.strip(),
                        quantidade(item.quantidade),
                        dinheiro(item.valor_unitario),
                        int(item.produto_id or 0),
                        item.codigo.strip(),
                        (item.unidade or "UN").strip(),
                        int(item.casas or 0),
                    ),
                )

    # ---------------------------------------------------------------- estoque
    def _baixar_do_estoque(self, venda: Venda) -> list[str]:
        """Tira do estoque o que a venda levou. Nunca derruba a venda.

        A venda ja aconteceu e o dinheiro ja entrou: se o estoque recusar (saldo
        errado no cadastro), isso e um recado para o operador conferir depois,
        nao motivo para perder a venda.
        """
        if self.catalogo is None:
            return []
        avisos: list[str] = []
        for item in venda.itens:
            if not item.do_estoque:
                continue
            try:
                self.catalogo.baixar(
                    item.produto_id,
                    item.quantidade,
                    documento=venda.numero,
                    motivo=f"Venda {venda.numero}",
                )
            except RegraError as erro:
                avisos.append(f"{item.descricao}: {erro}")
            except Exception as erro:  # noqa: BLE001 - o estoque nunca derruba a venda
                avisos.append(f"{item.descricao}: não foi possível dar baixa ({erro})")
        return avisos

    def _devolver_ao_estoque(
        self, linhas: list[tuple[ItemVenda, float]], documento: str, motivo: str
    ) -> list[str]:
        if self.catalogo is None:
            return []
        avisos: list[str] = []
        for item, qtd in linhas:
            if not item.do_estoque or qtd <= 0:
                continue
            try:
                self.catalogo.devolver(
                    item.produto_id, qtd, documento=documento, motivo=motivo
                )
            except Exception as erro:  # noqa: BLE001
                avisos.append(f"{item.descricao}: não voltou ao estoque ({erro})")
        return avisos

    # ------------------------------------------------------------------ regras
    def _validar(self, venda: Venda) -> None:
        if not venda.numero.strip():
            raise VendaError("Informe o número da venda.")
        if not venda.itens:
            raise VendaError("Adicione pelo menos um item na venda.")
        for item in venda.itens:
            if not item.descricao.strip():
                raise VendaError("Todo item precisa de uma descrição.")
            if quantidade(item.quantidade) <= 0:
                raise VendaError(f"A quantidade de '{item.descricao}' precisa ser maior que zero.")
        if dinheiro(venda.desconto) > venda.subtotal:
            raise VendaError("O desconto não pode ser maior que o total dos itens.")
        # regravar os itens apagaria as linhas da devolucao junto (CASCADE):
        # depois que mercadoria voltou, a venda vira historico
        if venda.id is not None and self.total_devolvido(venda.id) > 0:
            raise VendaError(
                f"A venda {venda.numero} tem devolução registrada e não pode mais "
                "ser alterada."
            )
        repetido = self.db.query_one(
            "SELECT id FROM vendas WHERE numero = ? AND id IS NOT ?",
            (venda.numero.strip(), venda.id),
        )
        if repetido is not None:
            raise VendaError(f"Já existe uma venda com o número {venda.numero}.")
