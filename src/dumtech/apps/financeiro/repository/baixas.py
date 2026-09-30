"""Baixa: o momento em que o dinheiro realmente andou.

Um lancamento pode ser baixado em partes ("recebi 300 dos 1.000"), cada baixa
com a sua data e a sua conta. `lancamentos.pago_em` continua existindo como a
data em que a conta ficou quitada, recalculada aqui dentro da mesma transacao -
e redundante de proposito, porque a lista e o resumo dependem dela.
"""

from __future__ import annotations

from ....ui import format as fmt
from ..models import (
    CENTAVO,
    Baixa,
    FinanceiroError,
    Lancamento,
    hoje_iso,
    ler_data,
)
from .comum import agora, dinheiro, maior_que

SELECT_BAIXA = """
    SELECT b.*, COALESCE(c.nome, '') AS conta_nome
    FROM baixas b
    LEFT JOIN contas c ON c.id = b.conta_id
"""


class BaixasMixin:
    """Parte do FinanceiroRepository que registra o dinheiro entrando/saindo."""

    # ------------------------------------------------------------------ leitura
    def baixas_de(self, lancamento_id: int) -> list[Baixa]:
        return [
            Baixa.from_row(row)
            for row in self.db.query(
                f"{SELECT_BAIXA} WHERE b.lancamento_id = ? ORDER BY b.data, b.id",
                (lancamento_id,),
            )
        ]

    def baixas_do_periodo(self, inicio: str, fim: str) -> list[Baixa]:
        return [
            Baixa.from_row(row)
            for row in self.db.query(
                f"{SELECT_BAIXA} WHERE date(b.data) BETWEEN date(?) AND date(?)"
                " ORDER BY b.data DESC, b.id DESC",
                (inicio, fim),
            )
        ]

    # ------------------------------------------------------------------ escrita
    def baixar(
        self,
        lancamento_id: int,
        valor: float = 0.0,
        data: str = "",
        conta_id: int = 0,
        forma: str = "",
        observacao: str = "",
    ) -> Baixa:
        """Registra um pagamento/recebimento. Sem `valor`, quita o que falta."""
        lancamento = self.obter(lancamento_id)
        if lancamento is None:
            raise FinanceiroError("Lancamento nao encontrado.")

        valor = dinheiro(valor) or lancamento.em_aberto
        if valor <= 0:
            raise FinanceiroError("O valor da baixa precisa ser maior que zero.")
        if maior_que(valor, lancamento.em_aberto):
            raise FinanceiroError(
                f"Faltam apenas {fmt.moeda(lancamento.em_aberto)} neste lancamento."
            )

        data = data or hoje_iso()
        if ler_data(data) is None:
            raise FinanceiroError("Data da baixa invalida.")
        if conta_id and self.obter_conta(conta_id) is None:
            raise FinanceiroError("Conta nao encontrada.")

        momento = agora()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO baixas (lancamento_id, data, valor, conta_id, forma,
                                    observacao, criado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lancamento_id,
                    data,
                    valor,
                    int(conta_id or 0),
                    forma.strip() or lancamento.forma_pagamento,
                    observacao.strip(),
                    momento,
                ),
            )
            baixa_id = int(cursor.lastrowid)
            self._recalcular_situacao(conn, lancamento)

        return Baixa(
            id=baixa_id,
            lancamento_id=lancamento_id,
            data=data,
            valor=valor,
            conta_id=int(conta_id or 0),
            forma=forma.strip() or lancamento.forma_pagamento,
            observacao=observacao.strip(),
            criado_em=momento,
        )

    def quitar(self, lancamento_id: int, **campos) -> Baixa:
        """Baixa o que falta de uma vez."""
        return self.baixar(lancamento_id, **campos)

    def estornar(self, baixa_id: int) -> None:
        """Desfaz UMA baixa; as outras do mesmo lancamento continuam valendo."""
        row = self.db.query_one("SELECT * FROM baixas WHERE id = ?", (baixa_id,))
        if row is None:
            raise FinanceiroError("Baixa nao encontrada.")
        lancamento = self.obter(row["lancamento_id"])
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM baixas WHERE id = ?", (baixa_id,))
            if lancamento is not None:
                self._recalcular_situacao(conn, lancamento)

    def estornar_tudo(self, lancamento_id: int) -> None:
        lancamento = self.obter(lancamento_id)
        if lancamento is None:
            raise FinanceiroError("Lancamento nao encontrado.")
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM baixas WHERE lancamento_id = ?", (lancamento_id,))
            conn.execute(
                "UPDATE lancamentos SET pago_em = NULL WHERE id = ?", (lancamento_id,)
            )

    def alternar_pagamento(self, lancamento_id: int) -> Lancamento:
        """O botao de um clique: quita tudo, ou desfaz tudo se ja estava pago."""
        lancamento = self.obter(lancamento_id)
        if lancamento is None:
            raise FinanceiroError("Lancamento nao encontrado.")
        if lancamento.pago:
            self.estornar_tudo(lancamento_id)
        else:
            self.baixar(lancamento_id, conta_id=lancamento.conta_id)
        return self.obter(lancamento_id)

    def registrar_baixa_inicial(self, lancamento: Lancamento) -> None:
        """Lancamento criado ja pago: grava a baixa correspondente."""
        self.db.execute(
            """
            INSERT INTO baixas (lancamento_id, data, valor, conta_id, forma,
                                observacao, criado_em)
            VALUES (?, ?, ?, ?, ?, '', ?)
            """,
            (
                lancamento.id,
                lancamento.pago_em,
                dinheiro(lancamento.valor),
                int(lancamento.conta_id or 0),
                lancamento.forma_pagamento.strip(),
                agora(),
            ),
        )

    # ------------------------------------------------------------------ interno
    @staticmethod
    def _recalcular_situacao(conn, lancamento: Lancamento) -> None:
        """`pago_em` = data da ultima baixa, quando elas cobrem o valor."""
        linha = conn.execute(
            "SELECT COALESCE(SUM(valor), 0) AS total, MAX(data) AS ultima"
            " FROM baixas WHERE lancamento_id = ?",
            (lancamento.id,),
        ).fetchone()
        total = dinheiro(linha["total"])
        quitado = total + CENTAVO >= dinheiro(lancamento.valor)
        conn.execute(
            "UPDATE lancamentos SET pago_em = ? WHERE id = ?",
            (linha["ultima"] if quitado else None, lancamento.id),
        )
