"""Cadastro de produtos: buscar, criar, editar, inativar e o que comprar."""

from __future__ import annotations

import sqlite3

from ..models import UNIDADES, EstoqueError, Produto
from .comum import agora, dinheiro, quantidade

CAMPOS = """
    codigo, nome, descricao, categoria, unidade, codigo_barras, fornecedor,
    localizacao, quantidade, estoque_minimo, estoque_maximo, preco_custo,
    preco_venda, ativo
"""


class ProdutosMixin:
    """Parte do EstoqueRepository que cuida do catalogo."""

    # ------------------------------------------------------------------ leitura
    def listar(
        self,
        busca: str = "",
        categoria: str = "",
        apenas_baixo: bool = False,
        incluir_inativos: bool = False,
    ) -> list[Produto]:
        sql = "SELECT * FROM produtos WHERE 1 = 1"
        params: list = []
        if not incluir_inativos:
            sql += " AND ativo = 1"
        if busca.strip():
            sql += (
                " AND (nome LIKE ? OR codigo LIKE ? OR descricao LIKE ?"
                " OR categoria LIKE ? OR codigo_barras LIKE ? OR localizacao LIKE ?)"
            )
            alvo = f"%{busca.strip()}%"
            params += [alvo] * 6
        if categoria.strip():
            sql += " AND categoria = ?"
            params.append(categoria.strip())
        if apenas_baixo:
            sql += " AND quantidade <= estoque_minimo"
        sql += " ORDER BY nome COLLATE NOCASE"
        return [Produto.from_row(row) for row in self.db.query(sql, params)]

    def obter(self, produto_id: int) -> Produto | None:
        row = self.db.query_one("SELECT * FROM produtos WHERE id = ?", (produto_id,))
        return Produto.from_row(row) if row else None

    def buscar_por_codigo(self, codigo: str) -> Produto | None:
        row = self.db.query_one(
            "SELECT * FROM produtos WHERE codigo = ? COLLATE NOCASE", (codigo.strip(),)
        )
        return Produto.from_row(row) if row else None

    def buscar_por_barras(self, codigo: str) -> Produto | None:
        codigo = codigo.strip()
        if not codigo:
            return None
        row = self.db.query_one(
            "SELECT * FROM produtos WHERE codigo_barras = ?", (codigo,)
        )
        return Produto.from_row(row) if row else None

    def buscar(self, termo: str) -> Produto | None:
        """O que o campo de bipe usa.

        O leitor manda o codigo de barras, mas o usuario tambem digita o codigo
        interno ou parte do nome. Procura na ordem do mais exato para o mais
        solto e so aceita nome quando ele identifica UM produto.
        """
        termo = termo.strip()
        if not termo:
            return None
        achado = self.buscar_por_barras(termo) or self.buscar_por_codigo(termo)
        if achado is not None:
            return achado
        candidatos = self.listar(busca=termo)
        return candidatos[0] if len(candidatos) == 1 else None

    def categorias(self) -> list[str]:
        return self._valores_distintos("categoria")

    def fornecedores(self) -> list[str]:
        """De quem se compra - alimenta o autocompletar, sem tabela de cadastro."""
        nomes = set(self._valores_distintos("fornecedor"))
        nomes.update(
            row["fornecedor"]
            for row in self.db.query(
                "SELECT DISTINCT fornecedor FROM movimentacoes "
                "WHERE TRIM(fornecedor) <> ''"
            )
        )
        return sorted(nomes, key=str.lower)

    def localizacoes(self) -> list[str]:
        return self._valores_distintos("localizacao")

    def _valores_distintos(self, coluna: str) -> list[str]:
        rows = self.db.query(
            f"SELECT DISTINCT {coluna} AS valor FROM produtos "
            f"WHERE TRIM({coluna}) <> '' ORDER BY {coluna} COLLATE NOCASE"
        )
        return [row["valor"] for row in rows]

    # ------------------------------------------------------------------ escrita
    def criar(self, produto: Produto) -> Produto:
        self._validar(produto)
        momento = agora()
        try:
            cursor = self.db.execute(
                f"""
                INSERT INTO produtos ({CAMPOS}, criado_em, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*self._valores(produto), momento, momento),
            )
        except sqlite3.IntegrityError as exc:
            raise self._erro_de_duplicidade(produto, exc) from exc

        produto.id = int(cursor.lastrowid)
        produto.criado_em = produto.atualizado_em = momento
        if produto.quantidade:
            self._gravar_movimentacao(
                produto,
                "entrada",
                produto.quantidade,
                0,
                produto.quantidade,
                observacao="Estoque inicial do cadastro",
                custo_unitario=produto.preco_custo,
            )
        return produto

    def atualizar(self, produto: Produto) -> Produto:
        if produto.id is None:
            raise EstoqueError("Produto sem identificacao para atualizar.")
        self._validar(produto)
        atual = self.obter(produto.id)
        if atual is None:
            raise EstoqueError("Produto nao encontrado.")

        momento = agora()
        atribuicoes = ", ".join(f"{campo.strip()} = ?" for campo in CAMPOS.split(","))
        try:
            self.db.execute(
                f"UPDATE produtos SET {atribuicoes}, atualizado_em = ? WHERE id = ?",
                (*self._valores(produto), momento, produto.id),
            )
        except sqlite3.IntegrityError as exc:
            raise self._erro_de_duplicidade(produto, exc, outro=True) from exc

        if quantidade(produto.quantidade) != quantidade(atual.quantidade):
            self._gravar_movimentacao(
                produto,
                "ajuste",
                abs(quantidade(produto.quantidade) - quantidade(atual.quantidade)),
                atual.quantidade,
                produto.quantidade,
                observacao="Quantidade corrigida na edicao do produto",
            )
        produto.atualizado_em = momento
        return produto

    def inativar(self, produto_id: int) -> None:
        """Some da lista sem apagar o historico - o caminho normal."""
        self.db.execute(
            "UPDATE produtos SET ativo = 0, atualizado_em = ? WHERE id = ?",
            (agora(), produto_id),
        )

    def reativar(self, produto_id: int) -> None:
        self.db.execute(
            "UPDATE produtos SET ativo = 1, atualizado_em = ? WHERE id = ?",
            (agora(), produto_id),
        )

    def excluir(self, produto_id: int) -> None:
        """So apaga de verdade quem nunca se movimentou."""
        movimentos = int(
            self.db.scalar(
                "SELECT COUNT(*) FROM movimentacoes WHERE produto_id = ?", (produto_id,)
            )
        )
        if movimentos:
            raise EstoqueError(
                "Este produto ja tem movimentacoes registradas e nao pode ser "
                "excluido sem apagar o historico. Use 'Inativar' para tira-lo "
                "da lista mantendo o que ja aconteceu."
            )
        self.db.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))

    # ------------------------------------------------------------------ compras
    def a_comprar(self, limite: int = 0) -> list[Produto]:
        """Produtos no minimo ou abaixo, dos mais criticos para os menos."""
        sql = (
            "SELECT * FROM produtos WHERE ativo = 1 AND quantidade <= estoque_minimo "
            "ORDER BY (quantidade - estoque_minimo), nome COLLATE NOCASE"
        )
        params: list = []
        if limite:
            sql += " LIMIT ?"
            params.append(int(limite))
        return [Produto.from_row(row) for row in self.db.query(sql, params)]

    def maior_valor(self, limite: int = 6) -> list[Produto]:
        """Onde o dinheiro esta parado."""
        return [
            Produto.from_row(row)
            for row in self.db.query(
                "SELECT * FROM produtos WHERE ativo = 1 AND quantidade > 0 "
                "ORDER BY (quantidade * preco_custo) DESC LIMIT ?",
                (int(limite),),
            )
        ]

    # ---------------------------------------------------------------- validacao
    def _validar(self, produto: Produto) -> None:
        if not produto.codigo.strip():
            raise EstoqueError("Informe o codigo do produto.")
        if not produto.nome.strip():
            raise EstoqueError("Informe o nome do produto.")
        if produto.unidade and produto.unidade.upper().strip() not in UNIDADES:
            raise EstoqueError(
                f"Unidade '{produto.unidade}' desconhecida. "
                f"Use uma destas: {', '.join(UNIDADES)}."
            )
        if quantidade(produto.quantidade) < 0:
            raise EstoqueError("A quantidade nao pode ser negativa.")
        if quantidade(produto.estoque_minimo) < 0 or quantidade(produto.estoque_maximo) < 0:
            raise EstoqueError("Os niveis de estoque nao podem ser negativos.")
        if 0 < quantidade(produto.estoque_maximo) < quantidade(produto.estoque_minimo):
            raise EstoqueError("O estoque maximo nao pode ser menor que o minimo.")
        if dinheiro(produto.preco_custo) < 0 or dinheiro(produto.preco_venda) < 0:
            raise EstoqueError("Os precos nao podem ser negativos.")

    @staticmethod
    def _valores(produto: Produto) -> tuple:
        return (
            produto.codigo.strip(),
            produto.nome.strip(),
            produto.descricao.strip(),
            produto.categoria.strip(),
            (produto.unidade or "UN").upper().strip(),
            produto.codigo_barras.strip(),
            produto.fornecedor.strip(),
            produto.localizacao.strip(),
            quantidade(produto.quantidade),
            quantidade(produto.estoque_minimo),
            quantidade(produto.estoque_maximo),
            dinheiro(produto.preco_custo),
            dinheiro(produto.preco_venda),
            1 if produto.ativo else 0,
        )

    @staticmethod
    def _erro_de_duplicidade(
        produto: Produto, exc: Exception, outro: bool = False
    ) -> EstoqueError:
        palavra = "outro produto" if outro else "um produto"
        if "codigo_barras" in str(exc):
            return EstoqueError(
                f"Ja existe {palavra} com o codigo de barras "
                f"'{produto.codigo_barras.strip()}'."
            )
        return EstoqueError(
            f"Ja existe {palavra} com o codigo '{produto.codigo.strip()}'."
        )
