"""Regras do DumTech Agenda.

Uma lista responde "o que tem marcado?". Quase tudo aqui existe para responder
a outra pergunta, que e a que se faz olhando para uma agenda: **tenho horario
na quinta de manha?**
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from ...core.database import Database
from .models import (
    ABERTOS,
    BLOQUEIO,
    CONCLUIDO,
    DIARIA,
    HORA_FINAL,
    HORA_INICIAL,
    faixa_das_horas,
    MAXIMO_REPETICOES,
    MENSAL,
    QUINZENAL,
    SEMANAL,
    TIPO_LABEL,
    AgendaError,
    Compromisso,
    DiaDaGrade,
    Grade,
    ResumoAgenda,
    inicio_da_semana,
    somar_meses,
)

PERIODO_HOJE = "hoje"
PERIODO_SEMANA = "semana"
PERIODO_MES = "mes"
PERIODO_ATRASADOS = "atrasados"

CAMPOS = "titulo, cliente, inicio, duracao_min, local, status, observacoes, tipo, grupo, repeticao"


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def proxima_ocorrencia(inicio: datetime, repeticao: str, indice: int) -> datetime:
    """A data e hora da ocorrencia numero `indice` (0 = a primeira)."""
    if repeticao == DIARIA:
        return inicio + timedelta(days=indice)
    if repeticao == QUINZENAL:
        return inicio + timedelta(days=14 * indice)
    if repeticao == MENSAL:
        return somar_meses(inicio, indice)
    return inicio + timedelta(weeks=indice)


class AgendaRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    # ------------------------------------------------------------------ leitura
    def listar(
        self,
        busca: str = "",
        status: str = "",
        tipo: str = "",
        periodo: str = "",
        inicio: str = "",
        fim: str = "",
        limite: int = 500,
    ) -> list[Compromisso]:
        sql = "SELECT * FROM compromissos WHERE 1 = 1"
        params: list = []
        if busca.strip():
            sql += (" AND (titulo LIKE ? OR cliente LIKE ? OR local LIKE ?"
                    " OR observacoes LIKE ?)")
            alvo = f"%{busca.strip()}%"
            params += [alvo] * 4
        if status:
            sql += " AND status = ?"
            params.append(status)
        if tipo:
            sql += " AND tipo = ?"
            params.append(tipo)

        hoje = date.today()
        if periodo == PERIODO_HOJE:
            sql += " AND date(inicio) = ?"
            params.append(hoje.isoformat())
        elif periodo == PERIODO_SEMANA:
            primeiro = inicio_da_semana(hoje)
            sql += " AND date(inicio) BETWEEN ? AND ?"
            params += [primeiro.isoformat(), (primeiro + timedelta(days=6)).isoformat()]
        elif periodo == PERIODO_MES:
            sql += " AND substr(inicio, 1, 7) = ?"
            params.append(hoje.strftime("%Y-%m"))
        elif periodo == PERIODO_ATRASADOS:
            marcadores = ", ".join("?" for _ in ABERTOS)
            sql += f" AND datetime(inicio) < ? AND status IN ({marcadores})"
            sql += " AND tipo <> ?"
            params += [datetime.now().isoformat(timespec="seconds"), *ABERTOS, BLOQUEIO]

        if inicio:
            sql += " AND date(inicio) >= date(?)"
            params.append(inicio)
        if fim:
            sql += " AND date(inicio) <= date(?)"
            params.append(fim)

        sql += " ORDER BY datetime(inicio) LIMIT ?"
        params.append(int(limite))
        return [Compromisso.from_row(row) for row in self.db.query(sql, params)]

    def obter(self, compromisso_id: int) -> Compromisso | None:
        row = self.db.query_one(
            "SELECT * FROM compromissos WHERE id = ?", (compromisso_id,)
        )
        return Compromisso.from_row(row) if row else None

    def do_grupo(self, grupo: str) -> list[Compromisso]:
        if not grupo:
            return []
        return [
            Compromisso.from_row(row)
            for row in self.db.query(
                "SELECT * FROM compromissos WHERE grupo = ? ORDER BY datetime(inicio)",
                (grupo,),
            )
        ]

    def titulos(self, limite: int = 120) -> list[str]:
        """Titulos ja usados, do mais recente para o mais antigo.

        Agenda de servico e repetitiva: "Visita tecnica", "Manutencao mensal",
        "Entrega". Redigitar isso todo dia e trabalho a toa.
        """
        return [row["titulo"] for row in self.db.query(
            "SELECT titulo, MAX(id) AS ultimo FROM compromissos "
            "WHERE TRIM(titulo) <> '' GROUP BY titulo COLLATE NOCASE "
            "ORDER BY ultimo DESC LIMIT ?", (int(limite),)
        )]

    def locais(self) -> list[str]:
        return [row["local"] for row in self.db.query(
            "SELECT DISTINCT local FROM compromissos WHERE TRIM(local) <> ''"
            " ORDER BY local COLLATE NOCASE"
        )]

    # ------------------------------------------------------------------ conflito
    def conflitos(self, compromisso: Compromisso) -> list[Compromisso]:
        """Quem ja ocupa esse pedaco de tempo.

        Avisa, nao trava: duas pessoas atendendo ao mesmo tempo e normal, e o
        programa nao sabe quantas maos a loja tem.
        """
        if compromisso.inicio_dt is None or not compromisso.ocupa_horario:
            return []
        dia = compromisso.inicio_dt.date()
        vizinhos = self.listar(
            inicio=(dia - timedelta(days=1)).isoformat(),
            fim=(dia + timedelta(days=1)).isoformat(),
            limite=500,
        )
        return [
            outro for outro in vizinhos
            if outro.id != compromisso.id and compromisso.choca_com(outro)
        ]

    # ------------------------------------------------------------------ escrita
    def salvar(self, compromisso: Compromisso) -> Compromisso:
        self._validar(compromisso)
        momento = agora()
        valores = (
            compromisso.titulo.strip(),
            compromisso.cliente.strip(),
            compromisso.inicio,
            int(compromisso.duracao_min or 0),
            compromisso.local.strip(),
            compromisso.status,
            compromisso.observacoes.strip(),
            compromisso.tipo,
            compromisso.grupo,
            compromisso.repeticao,
        )
        if compromisso.id is None:
            marcadores = ", ".join("?" for _ in valores)
            cursor = self.db.execute(
                f"INSERT INTO compromissos ({CAMPOS}, criado_em)"
                f" VALUES ({marcadores}, ?)",
                valores + (momento,),
            )
            compromisso.id = int(cursor.lastrowid)
            compromisso.criado_em = momento
        else:
            atribuicoes = ", ".join(f"{campo.strip()} = ?" for campo in CAMPOS.split(","))
            self.db.execute(
                f"UPDATE compromissos SET {atribuicoes} WHERE id = ?",
                valores + (compromisso.id,),
            )
        return compromisso

    def repetir(
        self, base: Compromisso, vezes: int, repeticao: str = SEMANAL
    ) -> list[Compromisso]:
        """Gera ocorrencias de verdade, para cada uma poder ser remarcada."""
        vezes = int(vezes)
        if vezes < 2:
            raise AgendaError("Uma repeticao precisa de pelo menos 2 datas.")
        if vezes > MAXIMO_REPETICOES:
            raise AgendaError(f"No maximo {MAXIMO_REPETICOES} repeticoes de uma vez.")

        inicio = base.inicio_dt
        if inicio is None:
            raise AgendaError("Informe a data e a hora do compromisso.")

        grupo = uuid.uuid4().hex[:12]
        criados: list[Compromisso] = []
        for indice in range(vezes):
            momento = proxima_ocorrencia(inicio, repeticao, indice)
            criados.append(self.salvar(Compromisso(
                titulo=base.titulo, cliente=base.cliente,
                inicio=momento.isoformat(timespec="minutes"),
                duracao_min=base.duracao_min, local=base.local,
                status=base.status, observacoes=base.observacoes,
                tipo=base.tipo, grupo=grupo, repeticao=repeticao,
            )))
        return criados

    def definir_status(self, compromisso_id: int, status: str) -> Compromisso | None:
        self.db.execute(
            "UPDATE compromissos SET status = ? WHERE id = ?", (status, compromisso_id)
        )
        return self.obter(compromisso_id)

    def remarcar(self, compromisso_id: int, novo_inicio: str) -> Compromisso:
        compromisso = self.obter(compromisso_id)
        if compromisso is None:
            raise AgendaError("Compromisso nao encontrado.")
        compromisso.inicio = novo_inicio
        return self.salvar(compromisso)

    def excluir(self, compromisso_id: int) -> None:
        self.db.execute("DELETE FROM compromissos WHERE id = ?", (compromisso_id,))

    def excluir_grupo(self, grupo: str, a_partir_de: str = "") -> int:
        """Cancela a serie inteira, ou so o que ainda esta por vir."""
        alvos = [
            c for c in self.do_grupo(grupo)
            if not a_partir_de or (c.inicio or "") >= a_partir_de
        ]
        for compromisso in alvos:
            self.excluir(compromisso.id)
        return len(alvos)

    def _validar(self, compromisso: Compromisso) -> None:
        if not compromisso.titulo.strip():
            raise AgendaError("Informe o titulo do compromisso.")
        if compromisso.inicio_dt is None:
            raise AgendaError("Informe a data e a hora do compromisso.")
        if int(compromisso.duracao_min or 0) <= 0:
            raise AgendaError("A duracao precisa ser maior que zero.")
        if compromisso.tipo not in TIPO_LABEL:
            raise AgendaError("Escolha o tipo do compromisso.")

    # -------------------------------------------------------------------- grade
    def grade(
        self,
        primeiro_dia: date,
        dias: int = 7,
        hora_inicial: int = HORA_INICIAL,
        hora_final: int = HORA_FINAL,
    ) -> Grade:
        """O que a tela desenha: uma coluna por dia, com o que esta marcado."""
        ultimo = primeiro_dia + timedelta(days=dias - 1)
        compromissos = self.listar(
            inicio=primeiro_dia.isoformat(), fim=ultimo.isoformat(), limite=2000
        )

        por_dia: dict[date, list[Compromisso]] = {}
        for compromisso in compromissos:
            dia = compromisso.dia
            if dia is not None:
                por_dia.setdefault(dia, []).append(compromisso)

        # a faixa pedida e o piso; o que estiver marcado fora dela estica
        inicial, final = faixa_das_horas(compromissos, hora_inicial, hora_final)
        return Grade(
            dias=[
                DiaDaGrade(
                    data=primeiro_dia + timedelta(days=passo),
                    compromissos=por_dia.get(primeiro_dia + timedelta(days=passo), []),
                )
                for passo in range(dias)
            ],
            hora_inicial=inicial,
            hora_final=final,
        )

    # ------------------------------------------------------------------- painel
    def resumo(self, limite_listas: int = 6) -> ResumoAgenda:
        hoje = date.today()
        primeiro = inicio_da_semana(hoje)
        todos = self.listar(limite=2000)

        do_dia = [c for c in todos if c.hoje and c.ocupa_horario]
        da_semana = [
            c for c in todos
            if c.dia and primeiro <= c.dia <= primeiro + timedelta(days=6)
            and c.ocupa_horario and not c.e_bloqueio
        ]
        atrasados = [c for c in todos if c.atrasado]
        proximos = [
            c for c in todos
            if c.inicio_dt and c.inicio_dt >= datetime.now() and c.em_aberto
            and not c.e_bloqueio
        ]
        concluidos = [
            c for c in todos
            if c.status == CONCLUIDO and (c.inicio or "")[:7] == hoje.strftime("%Y-%m")
        ]

        return ResumoAgenda(
            hoje=len([c for c in do_dia if not c.e_bloqueio]),
            semana=len(da_semana),
            atrasados=len(atrasados),
            concluidos_mes=len(concluidos),
            horas_semana=round(
                sum(c.duracao_min or 0 for c in da_semana) / 60, 1
            ),
            do_dia=do_dia[:limite_listas],
            proximos=proximos[:limite_listas],
            atrasados_lista=atrasados[:limite_listas],
        )

    def abertos(self) -> list[Compromisso]:
        return [c for c in self.listar(limite=1000) if c.status in ABERTOS]


__all__ = [
    "AgendaRepository",
    "PERIODO_ATRASADOS",
    "PERIODO_HOJE",
    "PERIODO_MES",
    "PERIODO_SEMANA",
    "proxima_ocorrencia",
]
