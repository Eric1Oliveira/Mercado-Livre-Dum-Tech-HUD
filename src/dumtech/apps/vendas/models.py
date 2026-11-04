"""Estruturas de dados do DumTech Vendas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from sqlite3 import Row

from ...core.errors import RegraError
from ...core.pagamentos import DINHEIRO, FORMAS, PARCELADO, PIX  # noqa: F401 - a lista mora la

CONCLUIDA = "concluida"
PENDENTE = "pendente"
CANCELADA = "cancelada"
DEVOLVIDA = "devolvida"

STATUS_LABEL = {
    CONCLUIDA: "Concluída",
    PENDENTE: "Pendente",
    CANCELADA: "Cancelada",
    DEVOLVIDA: "Devolvida",
}
STATUS_TOM = {
    CONCLUIDA: "success",
    PENDENTE: "warning",
    CANCELADA: "danger",
    DEVOLVIDA: "warning",
}
STATUS_OPCOES = [(rotulo, chave) for chave, rotulo in STATUS_LABEL.items()]

#: Caixa
ABERTO = "aberto"
FECHADO = "fechado"

TIPO_SANGRIA = "sangria"
TIPO_SUPRIMENTO = "suprimento"
#: dinheiro em especie que entrou por fora da venda (OS, conta do Financeiro)
TIPO_RECEBIMENTO = "recebimento"

TIPO_LABEL = {
    TIPO_SANGRIA: "Sangria",
    TIPO_SUPRIMENTO: "Suprimento",
    TIPO_RECEBIMENTO: "Recebimento",
}

#: a venda foi fechada pela baixa da conta no Financeiro
QUITADA_NO_FINANCEIRO = "financeiro"

#: forma do pagamento quando o Financeiro nao disse qual foi
RECEBIDO_NO_FINANCEIRO = "Recebido no Financeiro"

#: Diferenca de caixa que nao vale discussao (arredondamento de centavo).
TOLERANCIA = 0.005

#: O que o campo de parcelas ja traz: o caso comum e a mensalidade de um ano.
PARCELAS_PADRAO = 12


class VendaError(RegraError):
    """Erro de regra de negocio do Vendas."""


def hoje_iso() -> str:
    return date.today().isoformat()


def quantidade_texto(valor: float, unidade: str = "", casas: int = 0) -> str:
    """Quantidade do jeito que o balcao le: 3 UN, 1,250 KG."""
    texto = f"{float(valor or 0):.{int(casas or 0)}f}".replace(".", ",")
    return f"{texto} {unidade}".strip() if unidade else texto


@dataclass
class ItemVenda:
    id: int | None = None
    descricao: str = ""
    quantidade: float = 1.0
    valor_unitario: float = 0.0
    #: preenchido quando o item veio do catalogo do Estoque
    produto_id: int = 0
    codigo: str = ""
    unidade: str = "UN"
    casas: int = 0
    #: quanto deste item saiu do estoque de verdade: a baixa pode ser recusada
    baixado: float = 0.0
    #: custo de uma unidade no dia da venda (0 = nao se sabe)
    custo_unitario: float = 0.0
    #: quanto deste item ja voltou (calculado na leitura, nao gravado)
    devolvido: float = 0.0

    @property
    def total(self) -> float:
        return round(self.quantidade * self.valor_unitario, 2)

    @property
    def fora_do_estoque(self) -> float:
        """O que saiu da prateleira e ainda nao voltou."""
        return max(self.baixado - self.devolvido, 0.0)

    @property
    def restante(self) -> float:
        """Quanto ainda pode ser devolvido."""
        return max(self.quantidade - self.devolvido, 0.0)

    @property
    def quantidade_texto(self) -> str:
        return quantidade_texto(self.quantidade, self.unidade, self.casas)

    @property
    def do_estoque(self) -> bool:
        return self.produto_id > 0

    @classmethod
    def from_row(cls, row: Row) -> "ItemVenda":
        campos = row.keys()
        return cls(
            id=row["id"],
            descricao=row["descricao"],
            quantidade=float(row["quantidade"]),
            valor_unitario=float(row["valor_unitario"]),
            produto_id=int(row["produto_id"] or 0),
            codigo=row["codigo"] or "",
            unidade=row["unidade"] or "UN",
            casas=int(row["casas"] or 0),
            baixado=float(row["baixado"] or 0) if "baixado" in campos else 0.0,
            custo_unitario=(float(row["custo_unitario"] or 0)
                            if "custo_unitario" in campos else 0.0),
            devolvido=float(row["devolvido"] or 0) if "devolvido" in campos else 0.0,
        )


@dataclass
class Pagamento:
    id: int | None = None
    forma: str = DINHEIRO
    valor: float = 0.0
    #: o que a pessoa entregou (so faz sentido em dinheiro)
    recebido: float = 0.0
    #: em quantas vezes esta linha foi dividida; cada vez e uma conta no Financeiro
    parcelas: int = 0

    @property
    def em_dinheiro(self) -> bool:
        return self.forma == DINHEIRO

    @property
    def parcelado(self) -> bool:
        return self.parcelas > 1

    @property
    def rotulo(self) -> str:
        """A forma como a pessoa le: Pix, Parcelado 12x."""
        return f"{self.forma} {self.parcelas}x" if self.parcelado else self.forma

    @classmethod
    def from_row(cls, row: Row) -> "Pagamento":
        return cls(
            id=row["id"],
            forma=row["forma"],
            valor=float(row["valor"]),
            recebido=float(row["recebido"] or 0),
            parcelas=int(row["parcelas"] or 0),
        )


@dataclass
class Venda:
    id: int | None = None
    numero: str = ""
    cliente: str = ""
    data: str = field(default_factory=hoje_iso)
    forma_pagamento: str = DINHEIRO
    status: str = CONCLUIDA
    desconto: float = 0.0
    observacoes: str = ""
    criado_em: str = ""
    caixa_id: int = 0
    troco: float = 0.0
    cancelada_em: str = ""
    motivo_cancelamento: str = ""
    #: numero do contrato recorrente que gerou esta venda ("" = venda comum)
    recorrencia: str = ""
    #: quando vence a conta da venda a prazo, ou a 1a parcela ("" = dia da venda)
    vencimento: str = ""
    #: quem fechou a venda, quando nao foi o caixa
    quitada_por: str = ""
    #: quem vendeu ("" = ninguem em especial)
    vendedor: str = ""
    itens: list[ItemVenda] = field(default_factory=list)
    pagamentos: list[Pagamento] = field(default_factory=list)
    #: valor ja devolvido desta venda (calculado na leitura)
    devolvido: float = 0.0
    #: recados da baixa de estoque; existe so em memoria, nao vai para o banco
    avisos: list[str] = field(default_factory=list)

    @property
    def subtotal(self) -> float:
        return round(sum(item.total for item in self.itens), 2)

    @property
    def total(self) -> float:
        return round(max(self.subtotal - float(self.desconto or 0), 0.0), 2)

    @property
    def total_liquido(self) -> float:
        """O que a venda representa depois das devolucoes."""
        return round(max(self.total - float(self.devolvido or 0), 0.0), 2)

    @property
    def quantidade_itens(self) -> float:
        return round(sum(item.quantidade for item in self.itens), 3)

    @property
    def pago(self) -> float:
        return round(sum(p.valor for p in self.pagamentos), 2)

    @property
    def parcelamento(self) -> Pagamento | None:
        """A linha parcelada do pagamento, se houver (so pode haver uma)."""
        return next((p for p in self.pagamentos if p.parcelado), None)

    @property
    def a_prazo(self) -> bool:
        return any(p.forma.strip().lower() == "prazo" for p in self.pagamentos)

    @property
    def conta(self) -> bool:
        """Vendas canceladas nao somam em relatorio nenhum."""
        return self.status != CANCELADA

    @property
    def status_label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def status_tom(self) -> str:
        return STATUS_TOM.get(self.status, "muted")

    @property
    def resumo_pagamento(self) -> str:
        formas = [p.rotulo for p in self.pagamentos if p.valor > 0]
        return " + ".join(dict.fromkeys(formas)) if formas else self.forma_pagamento

    @classmethod
    def from_row(cls, row: Row) -> "Venda":
        return cls(
            id=row["id"],
            numero=row["numero"],
            cliente=row["cliente"],
            data=row["data"],
            forma_pagamento=row["forma_pagamento"],
            status=row["status"],
            desconto=float(row["desconto"]),
            observacoes=row["observacoes"],
            criado_em=row["criado_em"],
            caixa_id=int(row["caixa_id"] or 0),
            troco=float(row["troco"] or 0),
            cancelada_em=row["cancelada_em"] or "",
            motivo_cancelamento=row["motivo_cancelamento"] or "",
            recorrencia=(row["recorrencia"] or "") if "recorrencia" in row.keys() else "",
            vencimento=(row["vencimento"] or "") if "vencimento" in row.keys() else "",
            quitada_por=(row["quitada_por"] or "") if "quitada_por" in row.keys() else "",
            vendedor=(row["vendedor"] or "") if "vendedor" in row.keys() else "",
        )


@dataclass
class ItemDevolucao:
    """Uma linha da devolucao: qual item da venda e quanto voltou."""

    venda_item_id: int
    quantidade: float
    valor_unitario: float = 0.0
    descricao: str = ""
    produto_id: int = 0

    @property
    def total(self) -> float:
        return round(self.quantidade * self.valor_unitario, 2)


@dataclass
class Devolucao:
    id: int | None = None
    venda_id: int = 0
    numero_venda: str = ""
    data: str = field(default_factory=hoje_iso)
    motivo: str = ""
    valor: float = 0.0
    caixa_id: int = 0
    criado_em: str = ""
    #: quanto saiu da gaveta: venda paga no Pix devolve por fora dela
    em_dinheiro: float = 0.0
    itens: list[ItemDevolucao] = field(default_factory=list)
    #: recados da volta ao estoque; so em memoria
    avisos: list[str] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: Row) -> "Devolucao":
        campos = row.keys()
        return cls(
            id=row["id"],
            venda_id=row["venda_id"],
            numero_venda=row["numero_venda"] if "numero_venda" in campos else "",
            data=row["data"],
            motivo=row["motivo"] or "",
            valor=float(row["valor"]),
            caixa_id=int(row["caixa_id"] or 0),
            criado_em=row["criado_em"],
            em_dinheiro=float(row["em_dinheiro"] or 0) if "em_dinheiro" in campos else 0.0,
        )


@dataclass
class MovimentoCaixa:
    id: int | None = None
    caixa_id: int = 0
    tipo: str = TIPO_SANGRIA
    valor: float = 0.0
    motivo: str = ""
    criado_em: str = ""
    #: de onde veio o recebimento (OS-2026-0001)
    documento: str = ""

    @property
    def tipo_label(self) -> str:
        return TIPO_LABEL.get(self.tipo, self.tipo)

    @property
    def sinal(self) -> float:
        """So a sangria tira da gaveta."""
        return -self.valor if self.tipo == TIPO_SANGRIA else self.valor

    @classmethod
    def from_row(cls, row: Row) -> "MovimentoCaixa":
        return cls(
            id=row["id"],
            caixa_id=row["caixa_id"],
            tipo=row["tipo"],
            valor=float(row["valor"]),
            motivo=row["motivo"] or "",
            criado_em=row["criado_em"],
            documento=(row["documento"] or "") if "documento" in row.keys() else "",
        )


@dataclass
class Caixa:
    id: int | None = None
    aberto_em: str = ""
    fechado_em: str = ""
    valor_abertura: float = 0.0
    contado: float = 0.0
    diferenca: float = 0.0
    observacoes: str = ""
    status: str = ABERTO

    @property
    def aberto(self) -> bool:
        return self.status == ABERTO

    @classmethod
    def from_row(cls, row: Row) -> "Caixa":
        return cls(
            id=row["id"],
            aberto_em=row["aberto_em"],
            fechado_em=row["fechado_em"] or "",
            valor_abertura=float(row["valor_abertura"]),
            contado=float(row["contado"] or 0),
            diferenca=float(row["diferenca"] or 0),
            observacoes=row["observacoes"] or "",
            status=row["status"],
        )


@dataclass
class ConferenciaCaixa:
    """A conta da gaveta: quanto deveria ter e de onde veio cada parte."""

    caixa: Caixa | None = None
    abertura: float = 0.0
    #: o que os clientes entregaram em especie; o troco sai na linha de baixo
    vendas_dinheiro: float = 0.0
    trocos: float = 0.0
    recebimentos: float = 0.0
    suprimentos: float = 0.0
    sangrias: float = 0.0
    devolucoes_dinheiro: float = 0.0
    total_vendido: float = 0.0
    quantidade_vendas: int = 0
    por_forma: list[tuple[str, float]] = field(default_factory=list)
    movimentos: list[MovimentoCaixa] = field(default_factory=list)

    @property
    def esperado(self) -> float:
        """O que precisa estar na gaveta agora."""
        return round(
            self.abertura
            + self.vendas_dinheiro
            - self.trocos
            + self.recebimentos
            + self.suprimentos
            - self.sangrias
            - self.devolucoes_dinheiro,
            2,
        )


@dataclass
class Vendedor:
    id: int | None = None
    nome: str = ""
    #: percentual sobre o que ele vendeu
    comissao: float = 0.0
    ativo: bool = True

    @classmethod
    def from_row(cls, row: Row) -> "Vendedor":
        return cls(id=row["id"], nome=row["nome"], comissao=float(row["comissao"] or 0),
                   ativo=bool(row["ativo"]))


@dataclass
class LinhaResultado:
    """Um produto, ou um vendedor, no resultado do periodo."""

    nome: str
    quantidade: float = 0.0
    receita: float = 0.0
    custo: float = 0.0
    comissao: float = 0.0

    @property
    def lucro(self) -> float:
        return round(self.receita - self.custo, 2)

    @property
    def margem(self) -> float:
        return round(self.lucro / self.receita * 100, 1) if self.receita else 0.0


@dataclass
class ResultadoVendas:
    """O lucro de verdade: o que entrou menos o que a mercadoria custou.

    Item sem custo conhecido entra na receita e nao no custo, entao o lucro fica
    maior do que o real. A tela conta quantos sao, em vez de esconder.
    """

    inicio: str
    fim: str
    vendas: int = 0
    receita: float = 0.0
    custo: float = 0.0
    comissoes: float = 0.0
    itens_sem_custo: int = 0
    produtos: list[LinhaResultado] = field(default_factory=list)
    vendedores: list[LinhaResultado] = field(default_factory=list)

    @property
    def lucro(self) -> float:
        return round(self.receita - self.custo, 2)

    @property
    def margem(self) -> float:
        return round(self.lucro / self.receita * 100, 1) if self.receita else 0.0

    @property
    def ticket_medio(self) -> float:
        return round(self.receita / self.vendas, 2) if self.vendas else 0.0


@dataclass
class ResumoVendas:
    vendas_mes: int = 0
    total_mes: float = 0.0
    total_hoje: float = 0.0
    ticket_medio: float = 0.0
    devolvido_mes: float = 0.0
    #: canceladas nao somam, mas o dono precisa ver que aconteceram
    cancelado_hoje: float = 0.0
    cancelado_mes: float = 0.0
    caixa: Caixa | None = None
    ultimas: list[Venda] = field(default_factory=list)
    por_forma: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class DiaDeVenda:
    """Um dia do historico: o total e o total ate a hora de agora."""

    total: float = 0.0
    #: o mesmo dia so ate o relogio de hoje - e o que torna a comparacao justa.
    #: Calculado nos dias que se comparam com hoje; nos outros, e o total.
    ate_agora: float = 0.0
    vendas: int = 0


@dataclass
class MaisVendido:
    descricao: str
    quantidade: float
    valor: float
    unidade: str = "UN"
    casas: int = 0


@dataclass
class IndicadoresVendas:
    """Numero com contexto: o ritmo do dia, a tendencia e o que mais sai.

    A comparacao e sempre justa: hoje (ate agora) contra o mesmo dia da semana
    passada ATE A MESMA HORA; uma janela de dias contra a janela anterior com o
    dia correspondente cortado no mesmo horario; o mes contra o mesmo pedaco
    do mes passado. Canceladas nao contam (como no resumo).
    """

    agora: datetime
    #: "AAAA-MM-DD" -> o dia (so dias com venda)
    dias: dict[str, DiaDeVenda] = field(default_factory=dict)
    #: vendido em cada hora (0-23): hoje e o mesmo dia da semana passada
    horas_hoje: list[float] = field(default_factory=lambda: [0.0] * 24)
    horas_base: list[float] = field(default_factory=lambda: [0.0] * 24)
    mes: float = 0.0
    vendas_mes: int = 0
    #: do dia 1 ate o mesmo dia, no mes passado
    mes_anterior: float = 0.0
    vendas_mes_anterior: int = 0
    pendentes: float = 0.0
    vendas_pendentes: int = 0
    mais_vendidos: list[MaisVendido] = field(default_factory=list)
    #: como pagaram no mes, da forma mais usada para a menos usada
    por_forma: list[tuple[str, float]] = field(default_factory=list)

    @property
    def hoje(self) -> date:
        return self.agora.date()

    @property
    def base(self) -> date:
        """O dia de comparacao do "hoje": o mesmo dia da semana passada."""
        return self.hoje - timedelta(days=7)

    def dia(self, quando: date) -> DiaDeVenda:
        return self.dias.get(quando.isoformat(), DiaDeVenda())

    @property
    def total_hoje(self) -> float:
        return self.dia(self.hoje).total

    @property
    def vendas_hoje(self) -> int:
        return self.dia(self.hoje).vendas

    @property
    def base_ate_agora(self) -> float:
        return self.dia(self.base).ate_agora

    def janela(self, dias: int) -> float:
        """Vendido nos `dias` que terminam hoje (hoje conta ate agora)."""
        return round(sum(self.dia(self.hoje - timedelta(days=n)).total for n in range(dias)), 2)

    def janela_anterior(self, dias: int) -> float:
        """A janela de mesmo tamanho logo antes - com o dia que corresponde a
        hoje cortado no mesmo horario, senao hoje (pela metade) sempre perde."""
        fim = self.hoje - timedelta(days=dias)
        cheios = sum(self.dia(fim - timedelta(days=n)).total for n in range(1, dias))
        return round(cheios + self.dia(fim).ate_agora, 2)

    @staticmethod
    def _ticket(total: float, vendas: int) -> float:
        return round(total / vendas, 2) if vendas else 0.0

    @property
    def ticket_hoje(self) -> float:
        return self._ticket(self.total_hoje, self.vendas_hoje)

    @property
    def ticket_mes(self) -> float:
        return self._ticket(self.mes, self.vendas_mes)

    @property
    def ticket_mes_anterior(self) -> float:
        return self._ticket(self.mes_anterior, self.vendas_mes_anterior)
