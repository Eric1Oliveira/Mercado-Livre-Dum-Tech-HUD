"""Estruturas de dados do DumTech Orcamentos."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime, timedelta
from sqlite3 import Row

from ...core.errors import RegraError

RASCUNHO = "rascunho"
ENVIADO = "enviado"
APROVADO = "aprovado"
RECUSADO = "recusado"

STATUS_LABEL = {
    RASCUNHO: "Rascunho",
    ENVIADO: "Enviado",
    APROVADO: "Aprovado",
    RECUSADO: "Recusado",
}
STATUS_TOM = {
    RASCUNHO: "muted",
    ENVIADO: "accent",
    APROVADO: "success",
    RECUSADO: "danger",
}
STATUS_OPCOES = [(rotulo, chave) for chave, rotulo in STATUS_LABEL.items()]

#: as etapas do funil, na ordem
FUNIL = (RASCUNHO, ENVIADO, APROVADO, RECUSADO)
#: quem ja respondeu (entra na taxa de conversao)
RESPONDIDOS = (APROVADO, RECUSADO)

#: por que se perde um orcamento - lista curta, para virar estatistica
MOTIVO_PRECO = "preco"
MOTIVO_PRAZO = "prazo"
MOTIVO_CONCORRENTE = "concorrente"
MOTIVO_DESISTIU = "desistiu"
MOTIVO_SEM_RESPOSTA = "sem_resposta"

MOTIVOS_LABEL = {
    MOTIVO_PRECO: "Achou caro",
    MOTIVO_PRAZO: "Prazo não serviu",
    MOTIVO_CONCORRENTE: "Comprou de outro",
    MOTIVO_DESISTIU: "Desistiu da compra",
    MOTIVO_SEM_RESPOSTA: "Nunca respondeu",
}
MOTIVOS_OPCOES = [(rotulo, chave) for chave, rotulo in MOTIVOS_LABEL.items()]

#: condicoes de pagamento comuns (sugestao editavel)
CONDICOES = (
    "A vista",
    "50% na entrada, 50% na entrega",
    "3x sem juros",
    "30 dias",
    "30/60 dias",
    "Cartão em até 12x",
)

#: quantos dias uma proposta costuma valer
VALIDADE_PADRAO = 15

CENTAVO = 0.005


class OrcamentoError(RegraError):
    """Erro de regra de negocio."""


def hoje_iso() -> str:
    return date.today().isoformat()


def ler_data(texto: str | None) -> date | None:
    try:
        return datetime.fromisoformat(texto).date() if texto else None
    except ValueError:
        return None


@dataclass
class ItemOrcamento:
    id: int | None = None
    descricao: str = ""
    quantidade: float = 1.0
    valor_unitario: float = 0.0
    #: abatimento desta linha; negociacao real e por item, nao so no rodape
    desconto: float = 0.0
    unidade: str = ""
    #: produto do Estoque que esta linha e (0 = digitado a mao). E o que faz
    #: a proposta aprovada dar baixa no estoque quando vira venda ou ordem.
    produto_id: int = 0
    codigo: str = ""

    @property
    def bruto(self) -> float:
        return round(self.quantidade * self.valor_unitario, 2)

    @property
    def total(self) -> float:
        return round(max(self.bruto - float(self.desconto or 0), 0.0), 2)

    @property
    def quantidade_texto(self) -> str:
        texto = f"{self.quantidade:g}".replace(".", ",")
        return f"{texto} {self.unidade}".strip() if self.unidade else texto

    @classmethod
    def from_row(cls, row: Row) -> "ItemOrcamento":
        campos = row.keys()
        return cls(
            id=row["id"],
            descricao=row["descricao"],
            quantidade=float(row["quantidade"]),
            valor_unitario=float(row["valor_unitario"]),
            desconto=float(row["desconto"] or 0) if "desconto" in campos else 0.0,
            unidade=(row["unidade"] or "") if "unidade" in campos else "",
            produto_id=int(row["produto_id"] or 0) if "produto_id" in campos else 0,
            codigo=(row["codigo"] or "") if "codigo" in campos else "",
        )


@dataclass
class Orcamento:
    id: int | None = None
    numero: str = ""
    cliente: str = ""
    data: str = field(default_factory=hoje_iso)
    validade: str = ""
    status: str = RASCUNHO
    desconto: float = 0.0
    observacoes: str = ""
    criado_em: str = ""
    condicao_pagamento: str = ""
    prazo_entrega: str = ""
    validade_dias: int = VALIDADE_PADRAO
    enviado_em: str = ""
    respondido_em: str = ""
    motivo_recusa: str = ""
    total_gravado: float = 0.0
    itens: list[ItemOrcamento] = field(default_factory=list)

    # ------------------------------------------------------------------ dinheiro
    @property
    def bruto(self) -> float:
        """Antes de qualquer desconto."""
        return round(sum(item.bruto for item in self.itens), 2)

    @property
    def descontos_dos_itens(self) -> float:
        return round(sum(float(item.desconto or 0) for item in self.itens), 2)

    @property
    def subtotal(self) -> float:
        """Ja com os descontos de cada linha, antes do desconto geral."""
        return round(sum(item.total for item in self.itens), 2)

    @property
    def total(self) -> float:
        return round(max(self.subtotal - float(self.desconto or 0), 0.0), 2)

    @property
    def desconto_total(self) -> float:
        return round(self.descontos_dos_itens + float(self.desconto or 0), 2)

    # -------------------------------------------------------------------- etapa
    @property
    def status_label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def status_tom(self) -> str:
        return STATUS_TOM.get(self.status, "muted")

    @property
    def respondido(self) -> bool:
        return self.status in RESPONDIDOS

    @property
    def em_aberto(self) -> bool:
        return self.status in (RASCUNHO, ENVIADO)

    @property
    def motivo_label(self) -> str:
        return MOTIVOS_LABEL.get(self.motivo_recusa, self.motivo_recusa)

    # ----------------------------------------------------------------- validade
    @property
    def vale_ate(self) -> str:
        """A validade conta do envio: antes disso a proposta nem saiu."""
        if self.validade:
            return self.validade
        inicio = ler_data(self.enviado_em)
        if inicio is None or self.validade_dias <= 0:
            return ""
        return (inicio + timedelta(days=int(self.validade_dias))).isoformat()

    @property
    def vencido(self) -> bool:
        if self.respondido:
            return False
        limite = ler_data(self.vale_ate)
        return limite is not None and limite < date.today()

    @property
    def dias_esperando(self) -> int | None:
        """Ha quantos dias a proposta esta parada esperando resposta."""
        if self.status != ENVIADO:
            return None
        saida = ler_data(self.enviado_em)
        return (date.today() - saida).days if saida else None

    @classmethod
    def from_row(cls, row: Row) -> "Orcamento":
        proprios = {campo.name for campo in fields(cls)} - {"itens", "total_gravado"}
        dados = {chave: row[chave] for chave in set(row.keys()) & proprios}
        for texto in ("validade", "condicao_pagamento", "prazo_entrega",
                      "enviado_em", "respondido_em", "motivo_recusa"):
            dados[texto] = dados.get(texto) or ""
        dados["validade_dias"] = int(dados.get("validade_dias") or 0)
        orcamento = cls(**dados)
        if "total" in row.keys():
            orcamento.total_gravado = round(float(row["total"] or 0), 2)
        return orcamento


@dataclass
class EtapaFunil:
    """Uma etapa do funil: quantos e quanto."""

    status: str
    quantidade: int = 0
    valor: float = 0.0

    @property
    def label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def tom(self) -> str:
        return STATUS_TOM.get(self.status, "muted")


@dataclass
class ResumoOrcamentos:
    total: int = 0
    abertos: int = 0
    aprovados_mes: int = 0
    valor_aprovado_mes: float = 0.0
    valor_em_aberto: float = 0.0
    #: aprovados / respondidos - quem ainda nao respondeu nao conta
    conversao: float = 0.0
    respondidos: int = 0
    ticket_medio: float = 0.0
    etapas: list[EtapaFunil] = field(default_factory=list)
    recentes: list[Orcamento] = field(default_factory=list)
    aguardando: list[Orcamento] = field(default_factory=list)
    vencendo: list[Orcamento] = field(default_factory=list)
    motivos: list[tuple[str, int, float]] = field(default_factory=list)
