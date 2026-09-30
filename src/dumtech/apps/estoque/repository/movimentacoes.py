"""Entradas, saidas, ajustes e o historico do estoque.

Toda mudanca de saldo passa por aqui e deixa registro: o saldo do produto e
sempre explicavel pela lista de movimentacoes.
"""

from __future__ import annotations

from ..models import (
    TIPO_AJUSTE,
    TIPO_ENTRADA,
    TIPO_SAIDA,
    EstoqueError,
    ItemEntrada,
    Movimentacao,
    quantidade_texto,
)
from .comum import agora, dinheiro, igual, maior_que, quantidade

SELECT_MOV = """
    SELECT m.*, COALESCE(p.unidade, 'UN') AS unidade
    FROM movimentacoes m
    LEFT JOIN produtos p ON p.id = m.produto_id
"""


class MovimentacoesMixin:
    """Parte do EstoqueRepository que mexe no saldo."""

    # -------------------------------------------------------------- movimentar
    def registrar_entrada(
        self, produto_id: int, qtd: float, observacao: str = "", **extras
    ) -> Movimentacao:
        return self.movimentar(produto_id, TIPO_ENTRADA, qtd, observacao, **extras)

    def registrar_saida(
        self, produto_id: int, qtd: float, observacao: str = "", **extras
    ) -> Movimentacao:
        return self.movimentar(produto_id, TIPO_SAIDA, qtd, observacao, **extras)

    def movimentar(
        self,
        produto_id: int,
        tipo: str,
        qtd: float,
        observacao: str = "",
        custo_unitario: float = 0.0,
        fornecedor: str = "",
        documento: str = "",
    ) -> Movimentacao:
        """Registra entrada ou saida, atualiza o saldo e o custo medio."""
        qtd = quantidade(qtd)
        if qtd <= 0:
            raise EstoqueError("A quantidade precisa ser maior que zero.")
        if tipo not in (TIPO_ENTRADA, TIPO_SAIDA):
            raise EstoqueError("Tipo de movimentacao invalido.")

        produto = self.obter(produto_id)
        if produto is None:
            raise EstoqueError("Selecione um produto valido.")

        anterior = quantidade(produto.quantidade)
        custo_unitario = dinheiro(custo_unitario)
        if tipo == TIPO_ENTRADA:
            atual = quantidade(anterior + qtd)
            novo_custo = self._custo_medio(produto.preco_custo, anterior, qtd, custo_unitario)
        else:
            if maior_que(qtd, anterior):
                raise EstoqueError(
                    f"Estoque insuficiente para '{produto.nome}'. "
                    f"Disponivel: {quantidade_texto(anterior, produto.unidade)}, "
                    f"saida pedida: {quantidade_texto(qtd, produto.unidade)}."
                )
            atual = quantidade(anterior - qtd)
            novo_custo = produto.preco_custo

        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE produtos SET quantidade = ?, preco_custo = ?, "
                "atualizado_em = ? WHERE id = ?",
                (atual, dinheiro(novo_custo), agora(), produto.id),
            )
        produto.quantidade = atual
        produto.preco_custo = dinheiro(novo_custo)
        return self._gravar_movimentacao(
            produto,
            tipo,
            qtd,
            anterior,
            atual,
            observacao=observacao,
            custo_unitario=custo_unitario,
            fornecedor=fornecedor,
            documento=documento,
        )

    def ajustar(self, produto_id: int, novo_saldo: float, observacao: str = "") -> Movimentacao | None:
        """Corrige o saldo para o que foi contado de verdade."""
        novo_saldo = quantidade(novo_saldo)
        if novo_saldo < 0:
            raise EstoqueError("O saldo contado nao pode ser negativo.")

        produto = self.obter(produto_id)
        if produto is None:
            raise EstoqueError("Selecione um produto valido.")

        anterior = quantidade(produto.quantidade)
        if igual(anterior, novo_saldo):
            return None  # nada mudou: nao suja o historico

        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE produtos SET quantidade = ?, atualizado_em = ? WHERE id = ?",
                (novo_saldo, agora(), produto.id),
            )
        produto.quantidade = novo_saldo
        return self._gravar_movimentacao(
            produto,
            TIPO_AJUSTE,
            abs(novo_saldo - anterior),
            anterior,
            novo_saldo,
            observacao=observacao or "Ajuste manual de saldo",
        )

    def entrada_em_lote(
        self,
        itens: list[ItemEntrada],
        fornecedor: str = "",
        documento: str = "",
        observacao: str = "",
    ) -> list[Movimentacao]:
        """A chegada de mercadoria: ou a nota inteira entra, ou nada entra.

        Valida tudo antes de gravar qualquer coisa - meia nota lancada seria
        pior do que nota nenhuma.
        """
        if not itens:
            raise EstoqueError("Adicione pelo menos um produto na entrada.")

        preparados = []
        for posicao, item in enumerate(itens, start=1):
            qtd = quantidade(item.quantidade)
            if qtd <= 0:
                raise EstoqueError(f"Linha {posicao}: a quantidade precisa ser maior que zero.")
            produto = self.obter(item.produto_id)
            if produto is None:
                raise EstoqueError(f"Linha {posicao}: produto nao encontrado.")
            if dinheiro(item.custo_unitario) < 0:
                raise EstoqueError(f"Linha {posicao}: o custo nao pode ser negativo.")
            preparados.append((produto, qtd, dinheiro(item.custo_unitario)))

        registros: list[Movimentacao] = []
        with self.db.transaction() as conn:
            for produto, qtd, custo in preparados:
                anterior = quantidade(produto.quantidade)
                atual = quantidade(anterior + qtd)
                novo_custo = self._custo_medio(produto.preco_custo, anterior, qtd, custo)
                conn.execute(
                    "UPDATE produtos SET quantidade = ?, preco_custo = ?, "
                    "atualizado_em = ? WHERE id = ?",
                    (atual, dinheiro(novo_custo), agora(), produto.id),
                )
                produto.quantidade = atual
                produto.preco_custo = dinheiro(novo_custo)
                registros.append(
                    self._inserir_movimentacao(
                        conn,
                        produto,
                        TIPO_ENTRADA,
                        qtd,
                        anterior,
                        atual,
                        observacao=observacao,
                        custo_unitario=custo,
                        fornecedor=fornecedor,
                        documento=documento,
                    )
                )
        return registros

    @staticmethod
    def _custo_medio(
        custo_atual: float, saldo: float, entrando: float, custo_entrada: float
    ) -> float:
        """Media ponderada. Entrada sem custo informado nao mexe no custo medio."""
        if custo_entrada <= 0:
            return custo_atual
        if saldo <= 0 or custo_atual <= 0:
            return custo_entrada
        return (saldo * custo_atual + entrando * custo_entrada) / (saldo + entrando)

    # ---------------------------------------------------------------- historico
    def listar_movimentacoes(
        self,
        tipo: str = "",
        produto_id: int | None = None,
        busca: str = "",
        fornecedor: str = "",
        desde: str = "",
        limite: int = 300,
    ) -> list[Movimentacao]:
        sql = SELECT_MOV + " WHERE 1 = 1"
        params: list = []
        if tipo:
            sql += " AND m.tipo = ?"
            params.append(tipo)
        if produto_id:
            sql += " AND m.produto_id = ?"
            params.append(produto_id)
        if fornecedor.strip():
            sql += " AND m.fornecedor = ?"
            params.append(fornecedor.strip())
        if desde:
            sql += " AND m.criado_em >= ?"
            params.append(desde)
        if busca.strip():
            sql += (
                " AND (m.produto_nome LIKE ? OR m.produto_codigo LIKE ?"
                " OR m.observacao LIKE ? OR m.documento LIKE ? OR m.fornecedor LIKE ?)"
            )
            alvo = f"%{busca.strip()}%"
            params += [alvo] * 5
        sql += " ORDER BY datetime(m.criado_em) DESC, m.id DESC LIMIT ?"
        params.append(int(limite))
        return [Movimentacao.from_row(row) for row in self.db.query(sql, params)]

    # ----------------------------------------------------------------- gravacao
    def _gravar_movimentacao(self, produto, tipo, qtd, anterior, atual, **extras):
        with self.db.transaction() as conn:
            return self._inserir_movimentacao(
                conn, produto, tipo, qtd, anterior, atual, **extras
            )

    @staticmethod
    def _inserir_movimentacao(
        conn,
        produto,
        tipo: str,
        qtd: float,
        anterior: float,
        atual: float,
        observacao: str = "",
        custo_unitario: float = 0.0,
        fornecedor: str = "",
        documento: str = "",
    ) -> Movimentacao:
        momento = agora()
        dados = (
            produto.id,
            produto.codigo.strip(),
            produto.nome.strip(),
            tipo,
            quantidade(qtd),
            quantidade(anterior),
            quantidade(atual),
            dinheiro(custo_unitario),
            fornecedor.strip(),
            documento.strip(),
            observacao.strip(),
            momento,
        )
        cursor = conn.execute(
            """
            INSERT INTO movimentacoes (
                produto_id, produto_codigo, produto_nome, tipo, quantidade,
                saldo_anterior, saldo_atual, custo_unitario, fornecedor,
                documento, observacao, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            dados,
        )
        return Movimentacao(
            id=int(cursor.lastrowid),
            produto_id=produto.id,
            produto_codigo=dados[1],
            produto_nome=dados[2],
            tipo=tipo,
            quantidade=dados[4],
            saldo_anterior=dados[5],
            saldo_atual=dados[6],
            custo_unitario=dados[7],
            fornecedor=dados[8],
            documento=dados[9],
            observacao=dados[10],
            criado_em=momento,
            unidade=produto.unidade,
        )
