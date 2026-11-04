"""Cadastro de produtos: buscar, criar, editar, inativar e o que comprar."""

from __future__ import annotations

import sqlite3

from .. import codigo_barras
from ..models import UNIDADES, EstoqueError, Produto
from .comum import agora, dinheiro, quantidade

CAMPOS = """
    codigo, nome, descricao, categoria, unidade, codigo_barras, fornecedor,
    localizacao, quantidade, estoque_minimo, estoque_maximo, preco_custo,
    preco_venda, ativo, tamanho, cor, grupo
"""

#: teto do que vai para o banco. A imagem chega reduzida (dezenas de KB); isto
#: so barra quem gravar um arquivo cru sem passar por `estoque/imagem.py`
MAX_IMAGEM = 2 * 1024 * 1024


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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            raise EstoqueError("Produto sem identificação para atualizar.")
        self._validar(produto)
        atual = self.obter(produto.id)
        if atual is None:
            raise EstoqueError("Produto não encontrado.")

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
                observacao="Quantidade corrigida na edição do produto",
            )
        produto.atualizado_em = momento
        return produto

    # ----------------------------------------------------------- codigo interno
    def criar_variacoes(
        self, base: Produto, tamanhos: list[str], cores: list[str]
    ) -> list[Produto]:
        """Um produto de verdade por combinacao: CAM-01-P-AZUL, Camiseta P Azul.

        Variacao nao e um campo: cada uma tem saldo, codigo de barras e preco
        proprios, e entra na venda, na etiqueta e na contagem como qualquer
        produto. O que liga todas e o `grupo`. Nasce com saldo zero: quem da
        entrada na mercadoria e a nota.
        """
        tamanhos = [t.strip() for t in tamanhos if t.strip()]
        cores = [c.strip() for c in cores if c.strip()]
        if not tamanhos and not cores:
            raise EstoqueError("Informe pelo menos um tamanho ou uma cor.")
        criadas: list[Produto] = []
        with self.db.transaction():
            for tamanho in tamanhos or [""]:
                for cor in cores or [""]:
                    partes = [parte for parte in (tamanho, cor) if parte]
                    criadas.append(self.criar(Produto(
                        codigo="-".join([base.codigo, *partes]).upper().replace(" ", ""),
                        nome=" ".join([base.nome, *partes]),
                        descricao=base.descricao, categoria=base.categoria,
                        unidade=base.unidade, fornecedor=base.fornecedor,
                        localizacao=base.localizacao, estoque_minimo=base.estoque_minimo,
                        estoque_maximo=base.estoque_maximo, preco_custo=base.preco_custo,
                        preco_venda=base.preco_venda, tamanho=tamanho, cor=cor,
                        grupo=base.codigo,
                    )))
        return criadas

    def variacoes_de(self, codigo: str) -> list[Produto]:
        return [Produto.from_row(row) for row in self.db.query(
            "SELECT * FROM produtos WHERE grupo = ? ORDER BY nome COLLATE NOCASE", (codigo,)
        )]

    def proximo_codigo_barras(self) -> str:
        """O proximo codigo interno livre (EAN-13 com prefixo 2).

        A sequencia continua do maior codigo interno ja gravado: apagar um
        produto nao faz o numero dele voltar para outro.
        """
        linhas = self.db.query(
            "SELECT codigo_barras FROM produtos WHERE codigo_barras LIKE ? "
            "AND LENGTH(codigo_barras) = 13",
            (f"{codigo_barras.PREFIXO_INTERNO}%",),
        )
        sequencias = (codigo_barras.sequencia_interna(row["codigo_barras"]) for row in linhas)
        maior = max((s for s in sequencias if s is not None), default=0)
        return codigo_barras.interno(maior + 1)

    def atribuir_codigo_barras(self, produto_id: int) -> str:
        """Da um codigo interno ao produto que nao tem. Devolve o codigo dele."""
        produto = self.obter(produto_id)
        if produto is None:
            raise EstoqueError("Produto não encontrado.")
        if produto.codigo_barras.strip():
            return produto.codigo_barras.strip()
        codigo = self.proximo_codigo_barras()
        self.db.execute(
            "UPDATE produtos SET codigo_barras = ?, atualizado_em = ? WHERE id = ?",
            (codigo, agora(), produto_id),
        )
        return codigo

    def sem_codigo_barras(self) -> list[Produto]:
        """Produtos ativos que ainda nao tem codigo de barras."""
        return [
            Produto.from_row(row)
            for row in self.db.query(
                "SELECT * FROM produtos WHERE ativo = 1 AND TRIM(codigo_barras) = '' "
                "ORDER BY nome COLLATE NOCASE"
            )
        ]

    def gerar_codigos_que_faltam(self) -> int:
        """Codigo interno para todo produto ativo sem codigo. Devolve quantos."""
        faltando = self.sem_codigo_barras()
        if not faltando:
            return 0
        proxima = codigo_barras.sequencia_interna(self.proximo_codigo_barras())
        momento = agora()
        # tudo ou nada: metade dos produtos com codigo confundiria a conferencia
        with self.db.transaction() as conn:
            for passo, produto in enumerate(faltando):
                conn.execute(
                    "UPDATE produtos SET codigo_barras = ?, atualizado_em = ? WHERE id = ?",
                    (codigo_barras.interno(proxima + passo), momento, produto.id),
                )
        return len(faltando)

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
                "Este produto já tem movimentações registradas e não pode ser "
                "excluído sem apagar o histórico. Use 'Inativar' para tirá-lo "
                "da lista mantendo o que já aconteceu."
            )
        self.db.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))

    # ------------------------------------------------------------------- imagem
    def imagem(self, produto_id: int) -> bytes | None:
        """A imagem ja preparada (ver `estoque/imagem.py`), ou None."""
        row = self.db.query_one(
            "SELECT imagem FROM produto_imagens WHERE produto_id = ?", (produto_id,)
        )
        return bytes(row["imagem"]) if row else None

    def salvar_imagem(self, produto_id: int, dados: bytes | None) -> None:
        """Grava, troca ou (com None/vazio) tira a imagem do produto."""
        if not dados:
            self.db.execute("DELETE FROM produto_imagens WHERE produto_id = ?", (produto_id,))
            return
        if len(dados) > MAX_IMAGEM:
            raise EstoqueError("Imagem grande demais. Use uma foto menor.")
        from ..imagem import miniatura_de  # Qt so quando ha foto para gravar

        self.db.execute(
            "INSERT INTO produto_imagens (produto_id, imagem, miniatura, atualizado_em) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(produto_id) DO UPDATE SET "
            "imagem = excluded.imagem, miniatura = excluded.miniatura, "
            "atualizado_em = excluded.atualizado_em",
            (produto_id, sqlite3.Binary(dados), sqlite3.Binary(miniatura_de(dados)), agora()),
        )

    def miniatura(self, produto_id: int) -> bytes | None:
        row = self.db.query_one(
            "SELECT miniatura FROM produto_imagens WHERE produto_id = ?", (produto_id,)
        )
        return bytes(row["miniatura"]) if row else None

    def miniaturas(self) -> dict[int, tuple[str, bytes]]:
        """produto_id -> (quando mudou, miniatura): a lista guarda por versao."""
        return {
            row["produto_id"]: (row["atualizado_em"], bytes(row["miniatura"]))
            for row in self.db.query(
                "SELECT produto_id, miniatura, atualizado_em FROM produto_imagens"
            )
        }

    # ------------------------------------------------------------------ compras
    def a_comprar(self, limite: int = 0) -> list[Produto]:
        """Produtos no minimo ou abaixo, dos mais criticos para os menos.

        Zerado vem antes de baixo: produto zerado e venda perdida hoje, o baixo
        ainda vende. Dentro de cada grupo, quem esta mais longe do minimo.
        """
        sql = (
            "SELECT * FROM produtos WHERE ativo = 1 AND quantidade <= estoque_minimo "
            "ORDER BY (quantidade <= 0) DESC, (quantidade - estoque_minimo), "
            "nome COLLATE NOCASE"
        )
        params: list = []
        if limite:
            sql += " LIMIT ?"
            params.append(int(limite))
        return [Produto.from_row(row) for row in self.db.query(sql, params)]

    def maior_valor(self, limite: int = 6) -> list[Produto]:
        """Os produtos que mais pesam no valor do estoque (pelo custo)."""
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
            raise EstoqueError("Informe o código do produto.")
        if not produto.nome.strip():
            raise EstoqueError("Informe o nome do produto.")
        if produto.unidade and produto.unidade.upper().strip() not in UNIDADES:
            raise EstoqueError(
                f"Unidade '{produto.unidade}' desconhecida. "
                f"Use uma destas: {', '.join(UNIDADES)}."
            )
        if quantidade(produto.quantidade) < 0:
            raise EstoqueError("A quantidade não pode ser negativa.")
        if quantidade(produto.estoque_minimo) < 0 or quantidade(produto.estoque_maximo) < 0:
            raise EstoqueError("Os níveis de estoque não podem ser negativos.")
        if 0 < quantidade(produto.estoque_maximo) < quantidade(produto.estoque_minimo):
            raise EstoqueError("O estoque máximo não pode ser menor que o mínimo.")
        if dinheiro(produto.preco_custo) < 0 or dinheiro(produto.preco_venda) < 0:
            raise EstoqueError("Os preços não podem ser negativos.")

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
            produto.tamanho.strip(),
            produto.cor.strip(),
            produto.grupo.strip(),
        )

    @staticmethod
    def _erro_de_duplicidade(
        produto: Produto, exc: Exception, outro: bool = False
    ) -> EstoqueError:
        palavra = "outro produto" if outro else "um produto"
        if "codigo_barras" in str(exc):
            return EstoqueError(
                f"Já existe {palavra} com o código de barras "
                f"'{produto.codigo_barras.strip()}'."
            )
        return EstoqueError(
            f"Já existe {palavra} com o código '{produto.codigo.strip()}'."
        )
