"""Estruturas de dados do DumTech Estoque."""

from __future__ import annotations

from dataclasses import dataclass, field
from sqlite3 import Row

from ...core.errors import RegraError

TIPO_ENTRADA = "entrada"
TIPO_SAIDA = "saida"
TIPO_AJUSTE = "ajuste"

TIPOS_LABEL = {
    TIPO_ENTRADA: "Entrada",
    TIPO_SAIDA: "Saida",
    TIPO_AJUSTE: "Ajuste",
}


@dataclass(frozen=True)
class Unidade:
    """Como o produto e contado. Define as casas decimais em TODA a plataforma."""

    sigla: str
    nome: str
    casas: int


UNIDADES: dict[str, Unidade] = {
    u.sigla: u
    for u in (
        # contaveis: nao existe meia caixa
        Unidade("UN", "Unidade", 0),
        Unidade("CX", "Caixa", 0),
        Unidade("PC", "Peca", 0),
        Unidade("PAR", "Par", 0),
        # de medida: aceitam fracao
        Unidade("KG", "Quilo", 3),
        Unidade("G", "Grama", 0),
        Unidade("L", "Litro", 3),
        Unidade("M", "Metro", 3),
        Unidade("M2", "Metro quadrado", 3),
        Unidade("M3", "Metro cubico", 3),
    )
}
UNIDADE_PADRAO = "UN"


def unidade(sigla: str | None) -> Unidade:
    return UNIDADES.get((sigla or "").upper().strip(), UNIDADES[UNIDADE_PADRAO])


def casas(sigla: str | None) -> int:
    """Quantas casas decimais essa unidade aceita (0 = so numero inteiro)."""
    return unidade(sigla).casas


def _numero(valor: float, casas_decimais: int) -> str:
    texto = f"{float(valor or 0):,.{casas_decimais}f}"
    return texto.replace(",", "#").replace(".", ",").replace("#", ".")


def quantidade_texto(valor: float, sigla: str | None = None, com_unidade: bool = False) -> str:
    """Quantidade no padrao brasileiro, com as casas que a unidade permite.

    E o unico lugar que decide como uma quantidade aparece: 2 unidades viram
    "2", 1.5 quilos viram "1,500".
    """
    u = unidade(sigla)
    texto = _numero(valor, u.casas)
    return f"{texto} {u.sigla}" if com_unidade else texto


class EstoqueError(RegraError):
    """Erro de regra do Estoque (mensagem pronta para mostrar ao usuario)."""


@dataclass
class Produto:
    id: int | None = None
    codigo: str = ""
    nome: str = ""
    descricao: str = ""
    categoria: str = ""
    unidade: str = UNIDADE_PADRAO
    codigo_barras: str = ""
    fornecedor: str = ""
    localizacao: str = ""
    quantidade: float = 0.0
    estoque_minimo: float = 0.0
    estoque_maximo: float = 0.0
    #: custo medio, recalculado a cada entrada com custo informado
    preco_custo: float = 0.0
    preco_venda: float = 0.0
    ativo: bool = True
    criado_em: str = ""
    atualizado_em: str = ""

    @property
    def estoque_baixo(self) -> bool:
        return self.quantidade <= self.estoque_minimo

    @property
    def sem_estoque(self) -> bool:
        return self.quantidade <= 0

    @property
    def valor_em_estoque(self) -> float:
        return self.quantidade * self.preco_custo

    @property
    def casas(self) -> int:
        return casas(self.unidade)

    @property
    def margem(self) -> float | None:
        """Margem sobre a venda, em porcentagem. None quando nao da para saber."""
        if self.preco_venda <= 0 or self.preco_custo <= 0:
            return None
        return (self.preco_venda - self.preco_custo) / self.preco_venda * 100

    @property
    def sugestao_compra(self) -> float:
        """Quanto comprar para voltar ao nivel desejado."""
        alvo = self.estoque_maximo if self.estoque_maximo > 0 else self.estoque_minimo
        return max(0.0, alvo - self.quantidade)

    @classmethod
    def from_row(cls, row: Row) -> "Produto":
        return cls(
            id=row["id"],
            codigo=row["codigo"],
            nome=row["nome"],
            descricao=row["descricao"],
            categoria=row["categoria"],
            unidade=row["unidade"],
            codigo_barras=row["codigo_barras"],
            fornecedor=row["fornecedor"],
            localizacao=row["localizacao"],
            quantidade=float(row["quantidade"]),
            estoque_minimo=float(row["estoque_minimo"]),
            estoque_maximo=float(row["estoque_maximo"]),
            preco_custo=float(row["preco_custo"]),
            preco_venda=float(row["preco_venda"]),
            ativo=bool(row["ativo"]),
            criado_em=row["criado_em"],
            atualizado_em=row["atualizado_em"],
        )


@dataclass
class Movimentacao:
    id: int | None = None
    produto_id: int | None = None
    produto_codigo: str = ""
    produto_nome: str = ""
    tipo: str = TIPO_ENTRADA
    quantidade: float = 0.0
    saldo_anterior: float = 0.0
    saldo_atual: float = 0.0
    custo_unitario: float = 0.0
    fornecedor: str = ""
    documento: str = ""
    observacao: str = ""
    criado_em: str = ""
    unidade: str = UNIDADE_PADRAO

    @property
    def tipo_label(self) -> str:
        return TIPOS_LABEL.get(self.tipo, self.tipo)

    @property
    def total(self) -> float:
        return self.quantidade * self.custo_unitario

    @property
    def variacao(self) -> str:
        """Quanto entrou ou saiu, com o sinal - "+3", "-1,5", "=12"."""
        quantidade = _numero(self.quantidade, casas(self.unidade))
        if self.tipo == TIPO_ENTRADA:
            return f"+{quantidade}"
        if self.tipo == TIPO_SAIDA:
            return f"-{quantidade}"
        return f"={_numero(self.saldo_atual, casas(self.unidade))}"

    @classmethod
    def from_row(cls, row: Row) -> "Movimentacao":
        colunas = row.keys()
        return cls(
            id=row["id"],
            produto_id=row["produto_id"],
            produto_codigo=row["produto_codigo"],
            produto_nome=row["produto_nome"],
            tipo=row["tipo"],
            quantidade=float(row["quantidade"]),
            saldo_anterior=float(row["saldo_anterior"]),
            saldo_atual=float(row["saldo_atual"]),
            custo_unitario=float(row["custo_unitario"]),
            fornecedor=row["fornecedor"],
            documento=row["documento"],
            observacao=row["observacao"],
            criado_em=row["criado_em"],
            # vem do JOIN com produtos quando a consulta pede
            unidade=row["unidade"] if "unidade" in colunas else UNIDADE_PADRAO,
        )


@dataclass
class ItemContagem:
    """Uma linha da folha de contagem (balanco)."""

    produto_id: int
    produto_codigo: str = ""
    produto_nome: str = ""
    unidade: str = UNIDADE_PADRAO
    saldo_sistema: float = 0.0
    contado: float = 0.0
    atualizado_em: str = ""

    @property
    def diferenca(self) -> float:
        return self.contado - self.saldo_sistema

    @property
    def confere(self) -> bool:
        return abs(self.diferenca) < 1e-9

    @classmethod
    def from_row(cls, row: Row) -> "ItemContagem":
        return cls(
            produto_id=row["produto_id"],
            produto_codigo=row["produto_codigo"],
            produto_nome=row["produto_nome"],
            unidade=row["unidade"],
            saldo_sistema=float(row["saldo_sistema"]),
            contado=float(row["contado"]),
            atualizado_em=row["atualizado_em"],
        )


@dataclass
class ItemEntrada:
    """Uma linha da chegada de mercadoria."""

    produto_id: int
    quantidade: float
    custo_unitario: float = 0.0

    @property
    def total(self) -> float:
        return self.quantidade * self.custo_unitario


@dataclass
class PreviaImportacao:
    """O que uma planilha faria com o catalogo, antes de fazer."""

    criar: list[Produto] = field(default_factory=list)
    atualizar: list[Produto] = field(default_factory=list)
    recusados: list[tuple[int, str]] = field(default_factory=list)  # (linha, motivo)

    @property
    def total_valido(self) -> int:
        return len(self.criar) + len(self.atualizar)


@dataclass
class Resumo:
    """Numeros exibidos no painel inicial."""

    total_produtos: int = 0
    total_itens: float = 0.0
    produtos_baixo: int = 0
    valor_custo: float = 0.0
    ultimas: list[Movimentacao] = field(default_factory=list)
    baixos: list[Produto] = field(default_factory=list)
    a_comprar: list[Produto] = field(default_factory=list)
    maior_valor: list[Produto] = field(default_factory=list)
