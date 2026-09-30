"""Estruturas de dados do DumTech Ordem de Servico.

As palavras aqui valem para QUALQUER ramo que trabalhe com ordem de servico -
assistencia tecnica, oficina mecanica, chaveiro, instalador, lavanderia,
grafica. As colunas do banco guardaram os nomes antigos (`equipamento`,
`defeito`, `diagnostico`, `tecnico`) porque renomear coluna nao acrescenta
nada e poria em risco o banco de quem ja usa: o que o cliente le esta nos
rotulos das telas e dos comprovantes, nao no nome da coluna.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime, timedelta
from sqlite3 import Row

from ...core.errors import RegraError

ABERTA = "aberta"
AGUARDANDO = "aguardando"
ANDAMENTO = "andamento"
CONCLUIDA = "concluida"
ENTREGUE = "entregue"
CANCELADA = "cancelada"

STATUS_LABEL = {
    ABERTA: "Aberta",
    AGUARDANDO: "Aguardando aprovacao",
    ANDAMENTO: "Em andamento",
    CONCLUIDA: "Concluida",
    ENTREGUE: "Entregue",
    CANCELADA: "Cancelada",
}
STATUS_TOM = {
    ABERTA: "warning",
    AGUARDANDO: "danger",
    ANDAMENTO: "accent",
    CONCLUIDA: "success",
    ENTREGUE: "muted",
    CANCELADA: "danger",
}
STATUS_OPCOES = [(rotulo, chave) for chave, rotulo in STATUS_LABEL.items()]

#: a ordem ainda esta em andamento
EM_ANDAMENTO = (ABERTA, AGUARDANDO, ANDAMENTO)
#: acabou (para relatorio e para a fila)
FINALIZADAS = (ENTREGUE, CANCELADA)

#: a esteira: entra, e orcada, e feita, fica pronta, sai
PROXIMO_PASSO = {
    ABERTA: AGUARDANDO,
    AGUARDANDO: ANDAMENTO,
    ANDAMENTO: CONCLUIDA,
    CONCLUIDA: ENTREGUE,
}

#: as faixas do quadro, na ordem em que aparecem. Sao sempre as quatro, mesmo
#: vazias: quem nunca orca convive com uma coluna parada, e em troca o quadro
#: nao muda de forma sozinho de um dia para o outro.
BANCADA = (ABERTA, AGUARDANDO, ANDAMENTO, CONCLUIDA)

#: tipos de item de uma ordem. `peca` no banco e "Material" na tela: cobre a
#: peca da assistencia, o produto da lavanderia e o cabo do instalador.
PECA = "peca"
SERVICO = "servico"

TIPO_ITEM_LABEL = {PECA: "Material", SERVICO: "Servico"}
TIPO_ITEM_OPCOES = [(rotulo, chave) for chave, rotulo in TIPO_ITEM_LABEL.items()]

#: o que costuma vir junto com o item (sugestao de fabrica, o usuario edita).
#: Vale para o primeiro dia de uso e mais nada: a partir da primeira ordem, o
#: repositorio devolve o que ESTA loja costuma receber. Por isso a lista e
#: curta e sem ramo - a de celular fazia o chaveiro rolar por "Pelicula".
ACESSORIOS_COMUNS = (
    "Chave", "Carregador", "Cabo", "Capa ou bolsa", "Controle",
    "Manual", "Documento", "Acessorios",
)

#: prazo de garantia padrao, em dias
GARANTIA_PADRAO = 90

#: quanto de "o que foi pedido" cabe numa linha de cartao, lista ou aviso
ASSUNTO_MAXIMO = 60

CENTAVO = 0.005


class OrdemError(RegraError):
    """Erro de regra de negocio."""


def hoje_iso() -> str:
    return date.today().isoformat()


def ler_data(texto: str | None) -> date | None:
    try:
        return datetime.fromisoformat(texto).date() if texto else None
    except ValueError:
        return None


@dataclass
class ItemOS:
    """Uma peca trocada ou um servico feito."""

    id: int | None = None
    tipo: str = SERVICO
    descricao: str = ""
    quantidade: float = 1.0
    valor_unitario: float = 0.0
    #: preenchido quando a peca veio do catalogo do Estoque (0 = texto livre)
    produto_id: int = 0
    codigo: str = ""

    @property
    def total(self) -> float:
        return round(self.quantidade * self.valor_unitario, 2)

    @property
    def tipo_label(self) -> str:
        return TIPO_ITEM_LABEL.get(self.tipo, self.tipo)

    @property
    def e_peca(self) -> bool:
        return self.tipo == PECA

    @property
    def do_estoque(self) -> bool:
        """Da para dar baixa desta linha? So peca identificada no catalogo.

        Servico nao tem saldo, e peca digitada a mao (sem produto) nao tem
        como saber de qual prateleira sairia.
        """
        return self.e_peca and self.produto_id > 0

    @classmethod
    def from_row(cls, row: Row) -> "ItemOS":
        return cls(
            id=row["id"],
            tipo=row["tipo"],
            descricao=row["descricao"],
            quantidade=float(row["quantidade"]),
            valor_unitario=float(row["valor_unitario"]),
            produto_id=int(row["produto_id"] or 0) if "produto_id" in row.keys() else 0,
            codigo=row["codigo"] if "codigo" in row.keys() else "",
        )


@dataclass
class EventoOS:
    """Uma mudanca de etapa, com data e hora."""

    id: int | None = None
    ordem_id: int = 0
    status: str = ""
    observacao: str = ""
    criado_em: str = ""

    @property
    def status_label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def status_tom(self) -> str:
        return STATUS_TOM.get(self.status, "muted")

    @classmethod
    def from_row(cls, row: Row) -> "EventoOS":
        return cls(
            id=row["id"],
            ordem_id=row["ordem_id"],
            status=row["status"],
            observacao=row["observacao"] or "",
            criado_em=row["criado_em"],
        )


@dataclass
class Ordem:
    id: int | None = None
    numero: str = ""
    cliente: str = ""
    telefone: str = ""
    equipamento: str = ""
    defeito: str = ""
    diagnostico: str = ""
    servico: str = ""
    valor: float = 0.0
    status: str = ABERTA
    tecnico: str = ""
    aberta_em: str = field(default_factory=hoje_iso)
    prazo: str = ""
    concluida_em: str | None = None
    observacoes: str = ""
    criado_em: str = ""
    #: o que entrou junto, uma linha por acessorio
    acessorios: str = ""
    #: estado do item na chegada (riscos, tela trincada, arranhao...)
    condicao: str = ""
    #: senha ou desenho para destravar
    senha: str = ""
    aprovado_em: str = ""
    aprovado_por: str = ""
    entregue_em: str = ""
    garantia_dias: int = GARANTIA_PADRAO
    #: recados da baixa de estoque na entrega (nao vai para o banco)
    avisos: list[str] = field(default_factory=list)
    desconto: float = 0.0
    itens: list[ItemOS] = field(default_factory=list)
    historico: list[EventoOS] = field(default_factory=list)

    # ------------------------------------------------------------------ dinheiro
    @property
    def subtotal(self) -> float:
        """Soma dos itens; sem itens, vale o valor digitado direto."""
        if not self.itens:
            return round(float(self.valor or 0) + float(self.desconto or 0), 2)
        return round(sum(item.total for item in self.itens), 2)

    @property
    def total(self) -> float:
        return round(max(self.subtotal - float(self.desconto or 0), 0.0), 2)

    @property
    def total_pecas(self) -> float:
        return round(sum(i.total for i in self.itens if i.e_peca), 2)

    @property
    def total_servicos(self) -> float:
        return round(sum(i.total for i in self.itens if not i.e_peca), 2)

    # -------------------------------------------------------------------- etapa
    @property
    def status_label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def status_tom(self) -> str:
        return STATUS_TOM.get(self.status, "muted")

    @property
    def aberta(self) -> bool:
        """Ainda esta em andamento (nao foi entregue nem cancelada)."""
        return self.status in EM_ANDAMENTO

    @property
    def na_bancada(self) -> bool:
        return self.status in BANCADA

    @property
    def aprovada(self) -> bool:
        return bool(self.aprovado_em)

    @property
    def atrasada(self) -> bool:
        if not self.prazo or not self.aberta:
            return False
        quando = ler_data(self.prazo)
        return quando is not None and quando < date.today()

    @property
    def dias_em_aberto(self) -> int:
        entrada = ler_data(self.aberta_em)
        if entrada is None:
            return 0
        fim = ler_data(self.entregue_em) or date.today()
        return max((fim - entrada).days, 0)

    # ----------------------------------------------------------------- garantia
    @property
    def garantia_ate(self) -> str:
        """A garantia comeca quando o servico volta para a mao do cliente."""
        entrega = ler_data(self.entregue_em)
        if entrega is None or self.garantia_dias <= 0:
            return ""
        return (entrega + timedelta(days=int(self.garantia_dias))).isoformat()

    @property
    def na_garantia(self) -> bool:
        limite = ler_data(self.garantia_ate)
        return limite is not None and limite >= date.today()

    # ------------------------------------------------------------- como citar
    @property
    def assunto(self) -> str:
        """Do que esta ordem trata, em uma linha - para cartao, lista e aviso.

        O item e OPCIONAL: quem instala ar-condicionado, lava roupa ou faz
        chave nao tem "equipamento" para digitar. Quando ele falta, quem
        identifica a ordem e o que foi pedido. Antes disso a tela dizia "Sem
        equipamento" para metade dos ramos.
        """
        if self.equipamento.strip():
            return self.equipamento.strip()
        pedido = " ".join(self.defeito.split())
        # cortado sem aviso, "Trocar a fechadura da porta dos fundos e a" parece
        # o texto inteiro; as reticencias dizem que ha mais na ficha
        return pedido if len(pedido) <= ASSUNTO_MAXIMO else pedido[:ASSUNTO_MAXIMO - 1].rstrip() + "…"

    @property
    def acessorios_lista(self) -> list[str]:
        return [linha.strip() for linha in self.acessorios.splitlines() if linha.strip()]

    @classmethod
    def from_row(cls, row: Row) -> "Ordem":
        proprios = {campo.name for campo in fields(cls)} - {"itens", "historico"}
        dados = {chave: row[chave] for chave in set(row.keys()) & proprios}
        dados["acessorios"] = dados.get("acessorios") or ""
        dados["condicao"] = dados.get("condicao") or ""
        dados["senha"] = dados.get("senha") or ""
        dados["aprovado_em"] = dados.get("aprovado_em") or ""
        dados["aprovado_por"] = dados.get("aprovado_por") or ""
        dados["entregue_em"] = dados.get("entregue_em") or ""
        dados["garantia_dias"] = int(dados.get("garantia_dias") or 0)
        dados["desconto"] = float(dados.get("desconto") or 0)
        return cls(**dados)


@dataclass
class ResumoOrdens:
    abertas: int = 0
    aguardando: int = 0
    em_andamento: int = 0
    atrasadas: int = 0
    concluidas_mes: int = 0
    valor_mes: float = 0.0
    pecas_mes: float = 0.0
    servicos_mes: float = 0.0
    tempo_medio: float = 0.0
    fila: list[Ordem] = field(default_factory=list)
    prontas: list[Ordem] = field(default_factory=list)
    aguardando_lista: list[Ordem] = field(default_factory=list)
