"""O lancamento: contas a receber e a pagar, parceladas ou repetidas.

Parcela nao e um contador dentro de um registro: **cada parcela e uma conta de
verdade**, com vencimento proprio, que pode ser paga, adiada ou cancelada
sozinha. Por isso "1.200 em 3x" grava tres lancamentos ligados por um grupo.
"""

from __future__ import annotations

from datetime import date, timedelta

from ....core.contas import MAXIMO_PARCELAS
from ....core.pagamentos import formas_do_balcao
from ....ui import format as fmt
from ..models import (
    ANUAL,
    CADA_30_DIAS,
    DESPESA,
    MENSAL,
    PARCELAMENTO,
    QUINZENAL,
    RECEITA,
    RECORRENCIA,
    SEMANAL,
    FinanceiroError,
    Lancamento,
    ler_data,
    somar_meses,
)
from .comum import (
    BAIXADO,
    SELECT_LANCAMENTO,
    SITUACAO_ABERTO,
    SITUACAO_CANCELADO,
    SITUACAO_PAGO,
    SITUACAO_PARCIAL,
    SITUACAO_VENCIDO,
    agora,
    dinheiro,
    novo_grupo,
)

#: quantas vezes uma recorrencia e gerada quando o usuario nao diz
REPETICOES_PADRAO = 12


def proximo_vencimento(inicio: date, frequencia: str, indice: int) -> date:
    """A data da ocorrencia numero `indice` (0 = a primeira)."""
    if frequencia == SEMANAL:
        return inicio + timedelta(weeks=indice)
    if frequencia == QUINZENAL:
        return inicio + timedelta(days=15 * indice)
    if frequencia == CADA_30_DIAS:
        return inicio + timedelta(days=30 * indice)
    if frequencia == ANUAL:
        return somar_meses(inicio, 12 * indice)
    return somar_meses(inicio, indice)


def dividir(total: float, partes: int) -> list[float]:
    """Divide em centavos exatos; a sobra vai para a PRIMEIRA parcela.

    1.000 em 3x = 333,34 + 333,33 + 333,33. A sobra fica na primeira porque e a
    primeira que o cliente confere.
    """
    centavos = round(dinheiro(total) * 100)
    base, resto = divmod(centavos, partes)
    valores = [base] * partes
    valores[0] += resto
    return [valor / 100 for valor in valores]


class LancamentosMixin:
    """Parte do FinanceiroRepository que cuida das contas a pagar/receber."""

    # ------------------------------------------------------------------ leitura
    def listar(
        self,
        busca: str = "",
        tipo: str = "",
        situacao: str = "",
        categoria: str = "",
        conta_id: int = 0,
        limite: int = 500,
        fixa: bool | None = None,
        serie: str = "",
        cancelados: bool = False,
        cliente: str = "",
    ) -> list[Lancamento]:
        """Cancelado so vem a pedido: quem soma dinheiro nao pode enxergar."""
        sql = f"{SELECT_LANCAMENTO} WHERE 1 = 1"
        params: list = []
        if situacao == SITUACAO_CANCELADO:
            sql += " AND l.cancelado_em <> ''"
        elif not cancelados:
            sql += " AND l.cancelado_em = ''"
        if serie:
            sql += " AND l.serie = ?"
            params.append(serie)
        if busca.strip():
            sql += " AND (l.descricao LIKE ? OR l.categoria LIKE ? OR l.cliente LIKE ?)"
            alvo = f"%{busca.strip()}%"
            params += [alvo, alvo, alvo]
        if tipo:
            sql += " AND l.tipo = ?"
            params.append(tipo)
        if cliente.strip():
            sql += " AND l.cliente = ? COLLATE NOCASE"
            params.append(cliente.strip())
        if fixa is not None:
            sql += " AND l.fixa = ?"
            params.append(int(fixa))
        if categoria.strip():
            sql += " AND l.categoria = ?"
            params.append(categoria.strip())
        if conta_id:
            sql += " AND l.conta_id = ?"
            params.append(int(conta_id))

        if situacao == SITUACAO_PAGO:
            sql += " AND l.pago_em IS NOT NULL"
        elif situacao == SITUACAO_ABERTO:
            sql += " AND l.pago_em IS NULL"
        elif situacao == SITUACAO_VENCIDO:
            sql += " AND l.pago_em IS NULL AND l.vencimento < ?"
            params.append(date.today().isoformat())
        elif situacao == SITUACAO_PARCIAL:
            sql += f" AND l.pago_em IS NULL AND {BAIXADO} > 0"

        # "em aberto" e agenda, o que vence antes vem antes (o fluxo de caixa e o
        # painel leem por aqui)
        if situacao == SITUACAO_ABERTO:
            sql += " ORDER BY l.vencimento, l.id DESC LIMIT ?"
            params.append(int(limite))
        else:
            # o resto e historico: mais recente primeiro. Mas o corte fica com o
            # que esta mais perto de hoje, e nao com as ultimas parcelas de um
            # carne de 12 vezes: a conta de hoje nao pode cair fora da lista
            sql = (f"SELECT * FROM ({sql} ORDER BY ABS(julianday(l.vencimento) - julianday(?)),"
                   " l.id DESC LIMIT ?) AS l ORDER BY l.vencimento DESC, l.id DESC")
            params += [date.today().isoformat(), int(limite)]
        return [Lancamento.from_row(row) for row in self.db.query(sql, params)]

    def obter(self, lancamento_id: int) -> Lancamento | None:
        row = self.db.query_one(
            f"{SELECT_LANCAMENTO} WHERE l.id = ?", (lancamento_id,)
        )
        return Lancamento.from_row(row) if row else None

    def do_grupo(self, grupo: str) -> list[Lancamento]:
        """Todas as parcelas (ou repeticoes) que nasceram juntas."""
        if not grupo:
            return []
        return [
            Lancamento.from_row(row)
            for row in self.db.query(
                f"{SELECT_LANCAMENTO} WHERE l.grupo = ? ORDER BY l.parcela, l.vencimento",
                (grupo,),
            )
        ]

    def descricoes(self, limite: int = 200) -> list[str]:
        """O que ja foi lancado antes - aluguel, energia e fornecedor se repetem.

        Vem do mais recente para o mais antigo e sem repetir: o que a loja
        escreveu neste mes e o que ela vai escrever no mes que vem.
        """
        rows = self.db.query(
            "SELECT descricao, MAX(id) AS ultimo FROM lancamentos "
            "WHERE TRIM(descricao) <> '' "
            "GROUP BY descricao COLLATE NOCASE ORDER BY ultimo DESC LIMIT ?",
            (int(limite),),
        )
        return [row["descricao"] for row in rows]

    def formas(self) -> list[str]:
        """Formas de pagamento ja usadas, somadas as que o Hub ja conhece."""
        usadas = [row["forma_pagamento"] for row in self.db.query(
            "SELECT DISTINCT forma_pagamento FROM lancamentos "
            "WHERE TRIM(forma_pagamento) <> '' ORDER BY forma_pagamento COLLATE NOCASE"
        )]
        conhecidas = formas_do_balcao()
        vistas, saida = set(), []
        for nome in usadas + conhecidas:
            chave = nome.strip().lower()
            if chave and chave not in vistas:
                vistas.add(chave)
                saida.append(nome)
        return saida

    def categorias(self) -> list[str]:
        rows = self.db.query(
            "SELECT DISTINCT categoria FROM lancamentos WHERE TRIM(categoria) <> ''"
            " ORDER BY categoria COLLATE NOCASE"
        )
        return [row["categoria"] for row in rows]

    # ------------------------------------------------------------------ escrita
    def criar(self, lancamento: Lancamento) -> Lancamento:
        self._validar(lancamento)
        momento = agora()
        cursor = self.db.execute(
            """
            INSERT INTO lancamentos (tipo, descricao, categoria, cliente, valor,
                                     vencimento, pago_em, forma_pagamento,
                                     observacoes, conta_id, grupo, parcela,
                                     parcelas, serie, fixa, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._valores(lancamento) + (momento,),
        )
        lancamento.id = int(cursor.lastrowid)
        lancamento.criado_em = momento
        # criado ja pago: a baixa e o registro de que o dinheiro andou
        if lancamento.pago_em:
            self.registrar_baixa_inicial(lancamento)
        return lancamento

    def atualizar(self, lancamento: Lancamento) -> Lancamento:
        if lancamento.id is None:
            raise FinanceiroError("Lançamento sem identificação.")
        self._validar(lancamento)
        atual = self.obter(lancamento.id)
        if atual is not None and atual.baixado > lancamento.valor + 0.005:
            raise FinanceiroError(
                f"Já foram baixados {fmt.moeda(atual.baixado)} deste lançamento. "
                "O valor não pode ficar menor que isso."
            )
        self.db.execute(
            """
            UPDATE lancamentos SET tipo = ?, descricao = ?, categoria = ?, cliente = ?,
                                   valor = ?, vencimento = ?, pago_em = ?,
                                   forma_pagamento = ?, observacoes = ?, conta_id = ?,
                                   grupo = ?, parcela = ?, parcelas = ?, serie = ?,
                                   fixa = ?
            WHERE id = ?
            """,
            self._valores(lancamento) + (lancamento.id,),
        )
        return lancamento

    def excluir(self, lancamento_id: int) -> None:
        self.db.execute("DELETE FROM lancamentos WHERE id = ?", (lancamento_id,))

    def excluir_grupo(self, grupo: str) -> int:
        """Apaga a serie inteira, menos o que ja teve dinheiro andando."""
        pendentes = [
            item for item in self.do_grupo(grupo) if item.baixado <= 0.005
        ]
        for item in pendentes:
            self.excluir(item.id)
        return len(pendentes)

    # -------------------------------------------------------------------- series
    def parcelar(
        self,
        base: Lancamento,
        parcelas: int,
        frequencia: str = MENSAL,
    ) -> list[Lancamento]:
        """`base.valor` e o TOTAL: 1.200 em 3x vira tres contas de 400."""
        return self._gerar(base, parcelas, frequencia, PARCELAMENTO)

    def repetir(
        self,
        base: Lancamento,
        vezes: int = REPETICOES_PADRAO,
        frequencia: str = MENSAL,
    ) -> list[Lancamento]:
        """`base.valor` e o valor de CADA vez: aluguel de 2.200 por 12 meses."""
        return self._gerar(base, vezes, frequencia, RECORRENCIA)

    def _gerar(
        self, base: Lancamento, quantidade: int, frequencia: str, serie: str
    ) -> list[Lancamento]:
        quantidade = int(quantidade)
        if quantidade < 2:
            raise FinanceiroError("Uma série precisa de pelo menos 2 lançamentos.")
        if quantidade > MAXIMO_PARCELAS:
            raise FinanceiroError(f"No máximo {MAXIMO_PARCELAS} lançamentos por série.")

        inicio = ler_data(base.vencimento)
        if inicio is None:
            raise FinanceiroError("Informe a data do primeiro vencimento.")

        if serie == PARCELAMENTO:
            valores = dividir(base.valor, quantidade)
        else:
            valores = [dinheiro(base.valor)] * quantidade

        grupo = novo_grupo()
        criados: list[Lancamento] = []
        for indice in range(quantidade):
            item = Lancamento(
                tipo=base.tipo,
                descricao=base.descricao,
                categoria=base.categoria,
                cliente=base.cliente,
                valor=valores[indice],
                vencimento=proximo_vencimento(inicio, frequencia, indice).isoformat(),
                forma_pagamento=base.forma_pagamento,
                observacoes=base.observacoes,
                conta_id=base.conta_id,
                grupo=grupo,
                parcela=indice + 1,
                parcelas=quantidade,
                serie=serie,
                fixa=base.fixa,
            )
            criados.append(self.criar(item))
        return criados

    # ------------------------------------------------------------------ interno
    def _valores(self, lancamento: Lancamento) -> tuple:
        return (
            lancamento.tipo,
            lancamento.descricao.strip(),
            lancamento.categoria.strip(),
            lancamento.cliente.strip(),
            dinheiro(lancamento.valor),
            lancamento.vencimento,
            lancamento.pago_em,
            lancamento.forma_pagamento.strip(),
            lancamento.observacoes.strip(),
            int(lancamento.conta_id or 0),
            lancamento.grupo,
            int(lancamento.parcela or 0),
            int(lancamento.parcelas or 0),
            lancamento.serie,
            # receita nao e fixa nem variavel: a marca so vale para despesa
            int(bool(lancamento.fixa) and lancamento.tipo == DESPESA),
        )

    def _validar(self, lancamento: Lancamento) -> None:
        if lancamento.tipo not in (RECEITA, DESPESA):
            raise FinanceiroError("Escolha se é uma receita ou uma despesa.")
        if not lancamento.descricao.strip():
            raise FinanceiroError("Informe a descrição do lançamento.")
        if dinheiro(lancamento.valor) <= 0:
            raise FinanceiroError("O valor precisa ser maior que zero.")
        if not lancamento.vencimento:
            raise FinanceiroError("Informe a data de vencimento.")
        if ler_data(lancamento.vencimento) is None:
            raise FinanceiroError("Data de vencimento inválida.")
