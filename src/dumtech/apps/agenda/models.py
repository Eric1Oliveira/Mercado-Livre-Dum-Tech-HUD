"""Estruturas de dados do DumTech Agenda."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime, time, timedelta
from sqlite3 import Row

from ...core.errors import RegraError

AGENDADO = "agendado"
CONFIRMADO = "confirmado"
CONCLUIDO = "concluido"
CANCELADO = "cancelado"
#: o cliente nao veio e nao avisou: nao e o mesmo que cancelar
FALTOU = "faltou"

STATUS_LABEL = {
    AGENDADO: "Agendado",
    CONFIRMADO: "Confirmado",
    CONCLUIDO: "Concluído",
    CANCELADO: "Cancelado",
    FALTOU: "Faltou",
}
STATUS_TOM = {
    AGENDADO: "warning",
    CONFIRMADO: "accent",
    CONCLUIDO: "success",
    CANCELADO: "danger",
    FALTOU: "danger",
}
STATUS_OPCOES = [(rotulo, chave) for chave, rotulo in STATUS_LABEL.items()]
ABERTOS = (AGENDADO, CONFIRMADO)

#: tipos de compromisso. A cor vem daqui, pela paleta - cor gravada no banco
#: quebraria no tema claro.
ATENDIMENTO = "atendimento"
VISITA = "visita"
ENTREGA = "entrega"
OUTRO = "outro"
#: almoco, folga, feriado: ocupa espaco na grade e entra no conflito
BLOQUEIO = "bloqueio"

TIPO_LABEL = {
    ATENDIMENTO: "Atendimento",
    VISITA: "Visita",
    ENTREGA: "Entrega",
    OUTRO: "Outro",
    BLOQUEIO: "Bloqueio",
}
TIPO_TOM = {
    ATENDIMENTO: "success",
    VISITA: "accent",
    ENTREGA: "warning",
    OUTRO: "text_muted",
    BLOQUEIO: "text_dim",
}
TIPO_OPCOES = [(rotulo, chave) for chave, rotulo in TIPO_LABEL.items()]

#: de onde veio o compromisso: vazio = marcado aqui; "link" = o proprio
#: cliente marcou pela pagina de agendamento online
ORIGEM_LINK = "link"

#: com que frequencia um compromisso se repete
DIARIA = "diaria"
SEMANAL = "semanal"
QUINZENAL = "quinzenal"
MENSAL = "mensal"

REPETICOES = ((SEMANAL, "Toda semana"), (QUINZENAL, "A cada 15 dias"),
              (DIARIA, "Todo dia"), (MENSAL, "Todo mês"))
REPETICAO_LABEL = dict(REPETICOES)

#: a grade mostra o dia inteiro: para marcar uma reuniao as 5h, a linha das
#: 5h precisa estar la. Faixa curta so serve para quem quer apertar a vista.
HORA_INICIAL = 0
HORA_FINAL = 24

#: a hora que a tela sugere ao marcar algo novo. A grade mostra o dia inteiro
#: porque uma reuniao pode ser as 5h; sugerir 00:00 e outra conversa.
HORA_SUGESTAO = 8

#: as faixas que o cliente escolhe - o horario da loja dele nao e o meu
FAIXAS = (
    ("Dia inteiro (0h às 24h)", "dia", 0, 24),
    ("Comercial (7h às 20h)", "comercial", 7, 20),
    ("Estendido (6h às 23h)", "estendido", 6, 23),
)
#: a faixa que segue o horario de atendimento da loja (aba Online, `Expediente`).
#: E a que a grade abre: o dia inteiro espremia cada hora numa tirinha
FAIXA_LOJA = "loja"
FAIXA_PADRAO = FAIXA_LOJA


def faixa_por_chave(chave: str) -> tuple[int, int]:
    for _, nome, inicial, final in FAIXAS:
        if nome == chave:
            return inicial, final
    return HORA_INICIAL, HORA_FINAL


def faixa_das_horas(compromissos, inicial: int = HORA_INICIAL,
                    final: int = HORA_FINAL) -> tuple[int, int]:
    """A faixa escolhida, esticada ate caber tudo que esta marcado.

    A grade nunca esconde um compromisso: marcar as 21h e nao ver o bloco e
    pior do que uma grade comprida - o compromisso existe, e a pessoa acha que
    perdeu. Entao a faixa do cliente e um piso, e nao um limite.
    """
    for compromisso in compromissos:
        comeco = compromisso.inicio_dt
        if comeco is None:
            continue
        inicial = min(inicial, comeco.hour)
        fim = compromisso.fim_dt
        # quem termina 18:30 precisa da linha das 19h; quem termina 19:00, nao
        if fim is not None and fim.date() == comeco.date():
            final = max(final, fim.hour + (1 if fim.minute else 0))
        else:
            final = 24
    return max(0, min(inicial, 23)), min(24, max(final, inicial + 1))

DIAS_SEMANA = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
DIAS_CURTOS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


def titulo_do_periodo(inicio: date, dias: int, hoje: date | None = None) -> str:
    """O periodo da grade por extenso: "26 de outubro – 1 de novembro".

    O ano so aparece quando nao e o corrente (ou quando o periodo vira o ano).
    """
    hoje = hoje or date.today()
    fim = inicio + timedelta(days=max(dias, 1) - 1)

    def extenso(dia: date, com_ano: bool) -> str:
        texto = f"{dia.day} de {MESES[dia.month - 1]}"
        return f"{texto} de {dia.year}" if com_ano else texto

    if dias <= 1:
        return f"{DIAS_SEMANA[inicio.weekday()]}, {extenso(inicio, inicio.year != hoje.year)}"
    vira_o_ano = inicio.year != fim.year
    com_ano = vira_o_ano or fim.year != hoje.year
    if (inicio.year, inicio.month) == (fim.year, fim.month):
        return f"{inicio.day} – {extenso(fim, com_ano)}"
    return f"{extenso(inicio, vira_o_ano)} – {extenso(fim, com_ano)}"

#: duracoes comuns, em minutos
DURACOES = ((15, "15 min"), (30, "30 min"), (45, "45 min"), (60, "1 hora"),
            (90, "1h30"), (120, "2 horas"), (180, "3 horas"), (240, "4 horas"),
            (480, "O dia todo"))

MAXIMO_REPETICOES = 60


class AgendaError(RegraError):
    """Erro de regra de negocio."""


def agora_iso() -> str:
    return datetime.now().replace(second=0, microsecond=0).isoformat()


def ler_momento(texto: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(texto) if texto else None
    except (TypeError, ValueError):
        return None


def inicio_da_semana(quando: date) -> date:
    """Segunda-feira da semana de `quando`."""
    return quando - timedelta(days=quando.weekday())


def somar_meses(quando: datetime, meses: int) -> datetime:
    """Mesma data e hora N meses depois; mes curto usa o ultimo dia."""
    import calendar

    indice = quando.month - 1 + meses
    ano = quando.year + indice // 12
    mes = indice % 12 + 1
    ultimo = calendar.monthrange(ano, mes)[1]
    return quando.replace(year=ano, month=mes, day=min(quando.day, ultimo))


@dataclass
class Compromisso:
    id: int | None = None
    titulo: str = ""
    cliente: str = ""
    inicio: str = field(default_factory=agora_iso)
    duracao_min: int = 60
    local: str = ""
    status: str = AGENDADO
    observacoes: str = ""
    criado_em: str = ""
    tipo: str = ATENDIMENTO
    grupo: str = ""
    repeticao: str = ""
    telefone: str = ""
    origem: str = ""
    #: id da reserva no servidor (so o que veio do link)
    reserva: str = ""
    #: quem atende; dois profissionais no mesmo horario nao sao um conflito
    profissional: str = ""
    #: quanto o cliente adiantou para segurar o horario
    sinal: float = 0.0
    #: a venda ou a ordem que este atendimento virou
    documento: str = ""

    # ------------------------------------------------------------------- tempo
    @property
    def inicio_dt(self) -> datetime | None:
        return ler_momento(self.inicio)

    @property
    def fim_dt(self) -> datetime | None:
        inicio = self.inicio_dt
        return inicio + timedelta(minutes=self.duracao_min or 0) if inicio else None

    @property
    def dia(self) -> date | None:
        inicio = self.inicio_dt
        return inicio.date() if inicio else None

    @property
    def horario(self) -> str:
        inicio = self.inicio_dt
        if inicio is None:
            return "-"
        fim = self.fim_dt
        if fim is None:
            return inicio.strftime("%H:%M")
        return f"{inicio.strftime('%H:%M')} às {fim.strftime('%H:%M')}"

    @property
    def duracao_texto(self) -> str:
        minutos = int(self.duracao_min or 0)
        horas, resto = divmod(minutos, 60)
        if horas and resto:
            return f"{horas}h{resto:02d}"
        if horas:
            return f"{horas}h" if horas > 1 else "1 hora"
        return f"{resto} min"

    # ------------------------------------------------------------------ estado
    @property
    def status_label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def status_tom(self) -> str:
        return STATUS_TOM.get(self.status, "muted")

    @property
    def tipo_label(self) -> str:
        return TIPO_LABEL.get(self.tipo, self.tipo)

    @property
    def tom(self) -> str:
        """A cor do bloco na grade vem do tipo."""
        return TIPO_TOM.get(self.tipo, "accent")

    @property
    def e_bloqueio(self) -> bool:
        return self.tipo == BLOQUEIO

    @property
    def pelo_link(self) -> bool:
        return self.origem == ORIGEM_LINK

    @property
    def em_aberto(self) -> bool:
        return self.status in ABERTOS

    @property
    def ocupa_horario(self) -> bool:
        """Cancelado devolveu o horario: nao gera conflito."""
        return self.status != CANCELADO

    @property
    def atrasado(self) -> bool:
        inicio = self.inicio_dt
        if inicio is None or self.e_bloqueio or not self.em_aberto:
            return False
        return inicio < datetime.now()

    @property
    def hoje(self) -> bool:
        return self.dia == date.today()

    def choca_com(self, outro: "Compromisso") -> bool:
        """Dois compromissos ocupam o mesmo pedaco de tempo?"""
        if not (self.ocupa_horario and outro.ocupa_horario):
            return False
        inicio, fim = self.inicio_dt, self.fim_dt
        inicio_outro, fim_outro = outro.inicio_dt, outro.fim_dt
        if None in (inicio, fim, inicio_outro, fim_outro):
            return False
        return inicio < fim_outro and inicio_outro < fim

    @classmethod
    def from_row(cls, row: Row) -> "Compromisso":
        proprios = {campo.name for campo in fields(cls)}
        dados = {chave: row[chave] for chave in set(row.keys()) & proprios}
        dados["tipo"] = dados.get("tipo") or ATENDIMENTO
        for campo in ("grupo", "repeticao", "telefone", "origem", "reserva",
                      "profissional", "documento"):
            dados[campo] = dados.get(campo) or ""
        dados["sinal"] = float(dados.get("sinal") or 0)
        return cls(**dados)


@dataclass
class DiaDaGrade:
    """Uma coluna da grade: o dia e o que esta marcado nele."""

    data: date
    compromissos: list[Compromisso] = field(default_factory=list)

    @property
    def e_hoje(self) -> bool:
        return self.data == date.today()

    @property
    def fim_de_semana(self) -> bool:
        return self.data.weekday() >= 5

    @property
    def rotulo(self) -> str:
        return f"{DIAS_CURTOS[self.data.weekday()]} {self.data.strftime('%d/%m')}"

    @property
    def ocupados(self) -> list[Compromisso]:
        return [c for c in self.compromissos if c.ocupa_horario]

    @property
    def minutos_ocupados(self) -> int:
        return sum(int(c.duracao_min or 0) for c in self.ocupados if not c.e_bloqueio)


@dataclass
class Grade:
    """O que a tela desenha: os dias, a faixa de horas e o que cabe nela."""

    dias: list[DiaDaGrade] = field(default_factory=list)
    hora_inicial: int = HORA_INICIAL
    hora_final: int = HORA_FINAL

    @property
    def vazia(self) -> bool:
        return not any(dia.compromissos for dia in self.dias)

    @property
    def total(self) -> int:
        return sum(len(dia.ocupados) for dia in self.dias)

    def primeiro_livre(self, dia: date, duracao: int = 60) -> time | None:
        """A primeira hora cheia livre do dia - o que a tela sugere.

        Comeca no horario de trabalho, e nao na primeira linha da grade: a
        grade mostra a madrugada para quem precisa marcar as 5h, mas ninguem
        quer "00:00" preenchido ao clicar em "Novo compromisso".
        """
        do_dia = next((d for d in self.dias if d.data == dia), None)
        if do_dia is None:
            return None
        comeco = max(self.hora_inicial, min(HORA_SUGESTAO, self.hora_final - 1))
        for hora in list(range(comeco, self.hora_final)) + list(
            range(self.hora_inicial, comeco)
        ):
            candidato = Compromisso(
                inicio=datetime.combine(dia, time(hora)).isoformat(),
                duracao_min=duracao,
            )
            if not any(candidato.choca_com(c) for c in do_dia.ocupados):
                return time(hora)
        return None


@dataclass(frozen=True)
class Expediente:
    """O horario da loja na semana: os pedacos abertos de cada dia, em minutos.

    Vem do horario de atendimento da aba Online. A grade usa para abrir na
    faixa certa, sombrear o que esta fechado e medir quanto cada dia ja encheu.
    """

    #: segunda a domingo; dia fechado e tupla vazia
    semana: tuple[tuple[tuple[int, int], ...], ...] = ((),) * 7
    #: quantos atendimentos cabem ao mesmo tempo (cadeiras, salas)
    vagas: int = 1

    def aberto(self, dia: date) -> tuple[tuple[int, int], ...]:
        return self.semana[dia.weekday()] if len(self.semana) == 7 else ()

    def faixa(self) -> tuple[int, int]:
        """As horas da grade: da primeira abertura a ultima, com uma de folga."""
        pedacos = [pedaco for dia in self.semana for pedaco in dia]
        if not pedacos:
            return faixa_por_chave("comercial")
        inicio = min(de for de, _ in pedacos) // 60
        fim = -(-max(ate for _, ate in pedacos) // 60)
        return max(0, inicio - 1), min(24, fim + 1)

    def ocupacao(self, dia: DiaDaGrade) -> float | None:
        """Quanto do horario aberto do dia ja esta tomado, de 0 a 1. Fechado: None."""
        abertos = self.aberto(dia.data)
        vagas = max(self.vagas, 1)
        total = sum(ate - de for de, ate in abertos) * vagas
        if total <= 0:
            return None
        tomado = 0
        for compromisso in dia.ocupados:
            comeco = compromisso.inicio_dt
            if comeco is None or comeco.date() != dia.data:
                continue
            inicio = comeco.hour * 60 + comeco.minute
            fim = min(inicio + int(compromisso.duracao_min or 0), 24 * 60)
            dentro = sum(max(0, min(fim, ate) - max(inicio, de)) for de, ate in abertos)
            # bloqueio fecha a loja inteira naquele pedaco
            tomado += dentro * (vagas if compromisso.e_bloqueio else 1)
        return min(1.0, tomado / total)


@dataclass
class ResumoAgenda:
    hoje: int = 0
    semana: int = 0
    atrasados: int = 0
    concluidos_mes: int = 0
    horas_semana: float = 0.0
    do_dia: list[Compromisso] = field(default_factory=list)
    proximos: list[Compromisso] = field(default_factory=list)
    atrasados_lista: list[Compromisso] = field(default_factory=list)
    #: compromissos de segunda a domingo desta semana
    por_dia_semana: list[int] = field(default_factory=lambda: [0] * 7)
