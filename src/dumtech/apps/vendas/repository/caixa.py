"""O caixa do dia: abertura, sangria, suprimento e fechamento.

Vender sem caixa aberto e permitido de proposito. Loja pequena nem sempre abre
caixa, e travar a venda por causa disso e o tipo de rigidez que faz o dono
desistir do sistema. Se houver caixa aberto, a venda entra nele.
"""

from __future__ import annotations

from ..models import (
    ABERTO,
    FECHADO,
    TIPO_SANGRIA,
    TIPO_SUPRIMENTO,
    Caixa,
    ConferenciaCaixa,
    MovimentoCaixa,
    Venda,
    VendaError,
)
from .comum import agora, dinheiro


class CaixaMixin:
    """Parte do VendasRepository que responde 'quanto tem na gaveta?'."""

    # ------------------------------------------------------------------ leitura
    def caixa_aberto(self) -> Caixa | None:
        row = self.db.query_one(
            "SELECT * FROM caixas WHERE status = ? ORDER BY id DESC LIMIT 1", (ABERTO,)
        )
        return Caixa.from_row(row) if row else None

    def obter_caixa(self, caixa_id: int) -> Caixa | None:
        row = self.db.query_one("SELECT * FROM caixas WHERE id = ?", (caixa_id,))
        return Caixa.from_row(row) if row else None

    def listar_caixas(self, limite: int = 30) -> list[Caixa]:
        return [
            Caixa.from_row(row)
            for row in self.db.query(
                "SELECT * FROM caixas ORDER BY id DESC LIMIT ?", (int(limite),)
            )
        ]

    def movimentos_de(self, caixa_id: int) -> list[MovimentoCaixa]:
        return [
            MovimentoCaixa.from_row(row)
            for row in self.db.query(
                "SELECT * FROM caixa_movimentos WHERE caixa_id = ? ORDER BY id",
                (caixa_id,),
            )
        ]

    def vendas_do_caixa(self, caixa_id: int) -> list[Venda]:
        vendas = [
            self.obter(row["id"])
            for row in self.db.query(
                "SELECT id FROM vendas WHERE caixa_id = ? ORDER BY id", (caixa_id,)
            )
        ]
        return [v for v in vendas if v is not None]

    # ------------------------------------------------------------------ abertura
    def abrir_caixa(self, valor_abertura: float = 0.0) -> Caixa:
        if self.caixa_aberto() is not None:
            raise VendaError("Ja existe um caixa aberto. Feche o atual antes de abrir outro.")
        valor_abertura = dinheiro(valor_abertura)
        if valor_abertura < 0:
            raise VendaError("O valor de abertura nao pode ser negativo.")
        momento = agora()
        cursor = self.db.execute(
            "INSERT INTO caixas (aberto_em, valor_abertura, status) VALUES (?, ?, ?)",
            (momento, valor_abertura, ABERTO),
        )
        return Caixa(
            id=int(cursor.lastrowid),
            aberto_em=momento,
            valor_abertura=valor_abertura,
            status=ABERTO,
        )

    # ---------------------------------------------------------------- movimentos
    def registrar_movimento(self, tipo: str, valor: float, motivo: str = "") -> MovimentoCaixa:
        if tipo not in (TIPO_SANGRIA, TIPO_SUPRIMENTO):
            raise VendaError("Movimento de caixa invalido.")
        caixa = self.caixa_aberto()
        if caixa is None:
            raise VendaError("Abra o caixa antes de lancar sangria ou suprimento.")

        valor = dinheiro(valor)
        if valor <= 0:
            raise VendaError("O valor precisa ser maior que zero.")
        # dinheiro saindo da gaveta sem explicacao e como dinheiro sumindo
        if tipo == TIPO_SANGRIA and not motivo.strip():
            raise VendaError("Informe o motivo da sangria.")

        momento = agora()
        cursor = self.db.execute(
            """
            INSERT INTO caixa_movimentos (caixa_id, tipo, valor, motivo, criado_em)
            VALUES (?, ?, ?, ?, ?)
            """,
            (caixa.id, tipo, valor, motivo.strip(), momento),
        )
        return MovimentoCaixa(
            id=int(cursor.lastrowid),
            caixa_id=caixa.id,
            tipo=tipo,
            valor=valor,
            motivo=motivo.strip(),
            criado_em=momento,
        )

    def sangria(self, valor: float, motivo: str) -> MovimentoCaixa:
        return self.registrar_movimento(TIPO_SANGRIA, valor, motivo)

    def suprimento(self, valor: float, motivo: str = "") -> MovimentoCaixa:
        return self.registrar_movimento(TIPO_SUPRIMENTO, valor, motivo)

    # --------------------------------------------------------------- conferencia
    def conferencia(self, caixa_id: int | None = None) -> ConferenciaCaixa:
        """A conta da gaveta, parte por parte."""
        caixa = self.obter_caixa(caixa_id) if caixa_id else self.caixa_aberto()
        if caixa is None:
            return ConferenciaCaixa()

        vendas = [v for v in self.vendas_do_caixa(caixa.id) if v.conta]
        movimentos = self.movimentos_de(caixa.id)

        por_forma: dict[str, float] = {}
        vendas_dinheiro = 0.0
        for venda in vendas:
            for pagamento in venda.pagamentos:
                por_forma[pagamento.forma] = por_forma.get(pagamento.forma, 0.0) + pagamento.valor
                if pagamento.em_dinheiro:
                    vendas_dinheiro += pagamento.valor

        devolvido = float(
            self.db.scalar(
                "SELECT COALESCE(SUM(valor), 0) FROM devolucoes WHERE caixa_id = ?",
                (caixa.id,),
                default=0.0,
            )
        )

        return ConferenciaCaixa(
            caixa=caixa,
            abertura=caixa.valor_abertura,
            vendas_dinheiro=dinheiro(vendas_dinheiro),
            trocos=dinheiro(sum(v.troco for v in vendas)),
            suprimentos=dinheiro(
                sum(m.valor for m in movimentos if m.tipo == TIPO_SUPRIMENTO)
            ),
            sangrias=dinheiro(sum(m.valor for m in movimentos if m.tipo == TIPO_SANGRIA)),
            devolucoes_dinheiro=dinheiro(devolvido),
            total_vendido=dinheiro(sum(v.total for v in vendas)),
            quantidade_vendas=len(vendas),
            por_forma=sorted(por_forma.items(), key=lambda item: -item[1]),
            movimentos=movimentos,
        )

    # ----------------------------------------------------------------- fechamento
    def fechar_caixa(self, contado: float, observacoes: str = "") -> ConferenciaCaixa:
        """Fecha o caixa e grava a diferenca entre o contado e o esperado."""
        caixa = self.caixa_aberto()
        if caixa is None:
            raise VendaError("Nao ha caixa aberto para fechar.")

        conferencia = self.conferencia(caixa.id)
        contado = dinheiro(contado)
        if contado < 0:
            raise VendaError("O valor contado nao pode ser negativo.")
        diferenca = dinheiro(contado - conferencia.esperado)

        self.db.execute(
            """
            UPDATE caixas SET fechado_em = ?, contado = ?, diferenca = ?,
                              observacoes = ?, status = ?
            WHERE id = ?
            """,
            (agora(), contado, diferenca, observacoes.strip(), FECHADO, caixa.id),
        )
        conferencia.caixa = self.obter_caixa(caixa.id)
        return conferencia
