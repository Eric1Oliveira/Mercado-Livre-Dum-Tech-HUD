"""Regras da agenda: conflito, bloqueio, repeticao e a grade."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

from dumtech.apps.agenda.database import MIGRATIONS, open_database
from dumtech.apps.agenda.models import (
    AGENDADO,
    ATENDIMENTO,
    BLOQUEIO,
    CANCELADO,
    CONCLUIDO,
    DIARIA,
    MENSAL,
    QUINZENAL,
    VISITA,
    FAIXAS,
    HORA_FINAL,
    HORA_INICIAL,
    AgendaError,
    Compromisso,
    faixa_por_chave,
    inicio_da_semana,
)
from dumtech.apps.agenda.repository import AgendaRepository


def _arquivo(nome: str) -> Path:
    return Path(tempfile.mkdtemp()) / nome


def quando(dias: int = 0, hora: int = 9, minuto: int = 0) -> str:
    momento = datetime.combine(date.today() + timedelta(days=dias), time(hora, minuto))
    return momento.isoformat(timespec="minutes")


class AgendaBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = open_database(_arquivo("agenda.db"))
        self.repo = AgendaRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _marcar(self, **campos) -> Compromisso:
        dados = dict(
            titulo="Visita tecnica", cliente="Mercado Central",
            inicio=quando(0, 9), duracao_min=60,
        )
        dados.update(campos)
        return self.repo.salvar(Compromisso(**dados))


class ConflitoTestCase(AgendaBase):
    def test_dois_no_mesmo_horario_se_chocam(self) -> None:
        self._marcar(inicio=quando(0, 9), duracao_min=60)
        novo = Compromisso(titulo="Outro", inicio=quando(0, 9, 30), duracao_min=60)

        conflitos = self.repo.conflitos(novo)
        self.assertEqual(len(conflitos), 1)
        self.assertEqual(conflitos[0].titulo, "Visita tecnica")

    def test_encostar_nao_e_conflito(self) -> None:
        """Um termina 10h, o outro comeca 10h: cabe."""
        self._marcar(inicio=quando(0, 9), duracao_min=60)
        novo = Compromisso(titulo="Depois", inicio=quando(0, 10), duracao_min=60)
        self.assertEqual(self.repo.conflitos(novo), [])

    def test_cancelado_devolve_o_horario(self) -> None:
        marcado = self._marcar(inicio=quando(0, 9), duracao_min=60)
        novo = Compromisso(titulo="Outro", inicio=quando(0, 9), duracao_min=60)
        self.assertEqual(len(self.repo.conflitos(novo)), 1)

        self.repo.definir_status(marcado.id, CANCELADO)
        self.assertEqual(self.repo.conflitos(novo), [])

    def test_editar_o_proprio_compromisso_nao_acusa_conflito(self) -> None:
        marcado = self._marcar(inicio=quando(0, 9), duracao_min=60)
        marcado.duracao_min = 90
        self.assertEqual(self.repo.conflitos(marcado), [])

    def test_bloqueio_conflita_como_qualquer_outro(self) -> None:
        """Almoco ocupa espaco: marcar em cima dele tem que avisar."""
        self._marcar(titulo="Almoco", tipo=BLOQUEIO, inicio=quando(0, 12),
                     duracao_min=60, cliente="")
        novo = Compromisso(titulo="Atendimento", inicio=quando(0, 12, 30))
        conflitos = self.repo.conflitos(novo)
        self.assertEqual(len(conflitos), 1)
        self.assertTrue(conflitos[0].e_bloqueio)

    def test_conflito_atravessa_a_meia_noite(self) -> None:
        self._marcar(titulo="Plantao", inicio=quando(0, 23), duracao_min=180)
        novo = Compromisso(titulo="Madrugada", inicio=quando(1, 1), duracao_min=60)
        self.assertEqual(len(self.repo.conflitos(novo)), 1)

    def test_dia_diferente_nao_conflita(self) -> None:
        self._marcar(inicio=quando(0, 9))
        novo = Compromisso(titulo="Amanha", inicio=quando(1, 9))
        self.assertEqual(self.repo.conflitos(novo), [])


class RepeticaoTestCase(AgendaBase):
    def test_semanal_gera_compromissos_de_verdade(self) -> None:
        base = Compromisso(titulo="Manutencao preventiva", cliente="Mercado Central",
                           inicio=quando(0, 14), duracao_min=120)
        criados = self.repo.repetir(base, 4)

        self.assertEqual(len(criados), 4)
        self.assertEqual(len(self.repo.listar()), 4)
        # cada um e um registro proprio, uma semana depois do anterior
        primeiro, segundo = criados[0].inicio_dt, criados[1].inicio_dt
        self.assertEqual((segundo - primeiro).days, 7)
        self.assertEqual(len({c.id for c in criados}), 4)
        # e todos ligados pelo mesmo grupo
        self.assertEqual(len(self.repo.do_grupo(criados[0].grupo)), 4)

    def test_a_hora_nao_muda_ao_repetir(self) -> None:
        base = Compromisso(titulo="Aula", inicio=quando(0, 8, 30), duracao_min=45)
        criados = self.repo.repetir(base, 3, DIARIA)
        self.assertTrue(all(c.inicio_dt.hour == 8 and c.inicio_dt.minute == 30
                            for c in criados))

    def test_frequencias(self) -> None:
        base = Compromisso(titulo="Reuniao", inicio="2026-03-31T10:00")
        quinzenal = self.repo.repetir(base, 3, QUINZENAL)
        self.assertEqual([c.inicio[:10] for c in quinzenal],
                         ["2026-03-31", "2026-04-14", "2026-04-28"])

        mensal = self.repo.repetir(base, 3, MENSAL)
        # 31 de abril nao existe: usa o ultimo dia do mes
        self.assertEqual([c.inicio[:10] for c in mensal],
                         ["2026-03-31", "2026-04-30", "2026-05-31"])

    def test_uma_ocorrencia_pode_ser_remarcada_sozinha(self) -> None:
        criados = self.repo.repetir(
            Compromisso(titulo="Visita", inicio=quando(0, 9)), 3
        )
        self.repo.remarcar(criados[1].id, quando(8, 15))

        salvo = self.repo.obter(criados[1].id)
        self.assertEqual(salvo.inicio_dt.hour, 15)
        # as outras continuam onde estavam
        self.assertEqual(self.repo.obter(criados[0].id).inicio_dt.hour, 9)

    def test_cancelar_so_o_que_ainda_vem(self) -> None:
        criados = self.repo.repetir(
            Compromisso(titulo="Visita", inicio=quando(-7, 9)), 4
        )
        apagados = self.repo.excluir_grupo(criados[0].grupo, a_partir_de=quando(0, 0))
        self.assertEqual(apagados, 3)
        self.assertIsNotNone(self.repo.obter(criados[0].id))

    def test_repeticao_de_uma_vez_so_e_recusada(self) -> None:
        with self.assertRaises(AgendaError):
            self.repo.repetir(Compromisso(titulo="X", inicio=quando()), 1)


class GradeTestCase(AgendaBase):
    def test_a_grade_tem_uma_coluna_por_dia(self) -> None:
        primeiro = inicio_da_semana(date.today())
        grade = self.repo.grade(primeiro, dias=7)

        self.assertEqual(len(grade.dias), 7)
        self.assertEqual(grade.dias[0].data, primeiro)
        self.assertEqual(grade.dias[-1].data, primeiro + timedelta(days=6))
        self.assertTrue(grade.vazia)

    def test_cada_compromisso_cai_na_sua_coluna(self) -> None:
        self._marcar(inicio=quando(0, 9))
        self._marcar(titulo="Amanha", inicio=quando(1, 14))

        primeiro = inicio_da_semana(date.today())
        grade = self.repo.grade(primeiro, dias=14)
        por_data = {dia.data: dia for dia in grade.dias}
        self.assertEqual(len(por_data[date.today()].compromissos), 1)
        self.assertEqual(len(por_data[date.today() + timedelta(days=1)].compromissos), 1)
        self.assertEqual(grade.total, 2)

    def test_o_dia_de_hoje_se_identifica(self) -> None:
        grade = self.repo.grade(inicio_da_semana(date.today()), dias=7)
        hoje = [dia for dia in grade.dias if dia.e_hoje]
        self.assertEqual(len(hoje), 1)
        self.assertEqual(hoje[0].data, date.today())

    def test_a_grade_sugere_o_primeiro_horario_livre(self) -> None:
        self._marcar(inicio=quando(0, 7), duracao_min=60)
        self._marcar(titulo="Segundo", inicio=quando(0, 8), duracao_min=60)

        grade = self.repo.grade(date.today(), dias=1)
        self.assertEqual(grade.primeiro_livre(date.today()), time(9))

    def test_bloqueio_nao_conta_como_atendimento_no_dia(self) -> None:
        self._marcar(inicio=quando(0, 9), duracao_min=60)
        self._marcar(titulo="Almoco", tipo=BLOQUEIO, inicio=quando(0, 12),
                     duracao_min=60)

        grade = self.repo.grade(date.today(), dias=1)
        dia = grade.dias[0]
        self.assertEqual(len(dia.ocupados), 2)
        self.assertEqual(dia.minutos_ocupados, 60)   # o almoco nao e atendimento


class ResumoTestCase(AgendaBase):
    def test_atrasado_e_o_que_passou_e_ninguem_fechou(self) -> None:
        passado = self._marcar(titulo="Passou", inicio=quando(-1, 9))
        self._marcar(titulo="Futuro", inicio=quando(3, 9))

        resumo = self.repo.resumo()
        self.assertEqual(resumo.atrasados, 1)
        self.assertEqual([c.titulo for c in resumo.atrasados_lista], ["Passou"])

        self.repo.definir_status(passado.id, CONCLUIDO)
        self.assertEqual(self.repo.resumo().atrasados, 0)

    def test_bloqueio_nunca_fica_atrasado(self) -> None:
        self._marcar(titulo="Feriado", tipo=BLOQUEIO, inicio=quando(-2, 8),
                     duracao_min=480)
        self.assertEqual(self.repo.resumo().atrasados, 0)

    def test_horas_da_semana(self) -> None:
        primeiro = inicio_da_semana(date.today())
        offset = (primeiro - date.today()).days
        self._marcar(inicio=quando(offset, 9), duracao_min=90)
        self._marcar(titulo="Outro", inicio=quando(offset + 1, 9), duracao_min=30)

        resumo = self.repo.resumo()
        self.assertEqual(resumo.semana, 2)
        self.assertEqual(resumo.horas_semana, 2.0)

    def test_cancelado_sai_da_contagem_do_dia(self) -> None:
        marcado = self._marcar(inicio=quando(0, 9))
        self.assertEqual(self.repo.resumo().hoje, 1)
        self.repo.definir_status(marcado.id, CANCELADO)
        self.assertEqual(self.repo.resumo().hoje, 0)

    def test_filtro_de_atrasados(self) -> None:
        self._marcar(titulo="Passou", inicio=quando(-1, 9))
        self._marcar(titulo="Futuro", inicio=quando(3, 9))
        from dumtech.apps.agenda.repository import PERIODO_ATRASADOS

        achados = self.repo.listar(periodo=PERIODO_ATRASADOS)
        self.assertEqual([c.titulo for c in achados], ["Passou"])


class ValidacaoTestCase(AgendaBase):
    def test_campos_obrigatorios(self) -> None:
        with self.assertRaises(AgendaError):
            self._marcar(titulo="   ")
        with self.assertRaises(AgendaError):
            self._marcar(duracao_min=0)
        with self.assertRaises(AgendaError):
            self._marcar(inicio="nao e data")

    def test_tipo_invalido_e_recusado(self) -> None:
        with self.assertRaises(AgendaError):
            self._marcar(tipo="churrasco")

    def test_duracao_em_texto_amigavel(self) -> None:
        self.assertEqual(Compromisso(duracao_min=30).duracao_texto, "30 min")
        self.assertEqual(Compromisso(duracao_min=60).duracao_texto, "1 hora")
        self.assertEqual(Compromisso(duracao_min=90).duracao_texto, "1h30")
        self.assertEqual(Compromisso(duracao_min=120).duracao_texto, "2h")


class MigracaoTestCase(unittest.TestCase):
    """Quem ja tinha compromissos na versao 1 nao pode perder nada."""

    def test_v1_vira_v2_com_tipo_padrao(self) -> None:
        arquivo = _arquivo("agenda.db")
        conn = sqlite3.connect(arquivo)
        conn.executescript(MIGRATIONS[0].statements[0])
        conn.execute(
            "INSERT INTO compromissos (id, titulo, cliente, inicio, duracao_min,"
            " local, status, observacoes, criado_em)"
            " VALUES (1, 'Visita antiga', 'Maria', '2025-11-10T09:00', 90,"
            " 'Loja do cliente', 'confirmado', 'levar cabo', '2025-11-01T08:00:00')"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        db = open_database(arquivo)
        self.addCleanup(db.close)
        repo = AgendaRepository(db)
        # passa pela 2 e chega na ultima (a 3 trouxe o agendamento online)
        self.assertEqual(db.schema_version, MIGRATIONS[-1].version)

        antigo = repo.obter(1)
        self.assertEqual(antigo.titulo, "Visita antiga")
        self.assertEqual(antigo.cliente, "Maria")
        self.assertEqual(antigo.duracao_min, 90)
        self.assertEqual(antigo.local, "Loja do cliente")
        self.assertEqual(antigo.observacoes, "levar cabo")
        # campos novos chegam com padrao util
        self.assertEqual(antigo.tipo, ATENDIMENTO)
        self.assertEqual(antigo.grupo, "")
        self.assertFalse(antigo.e_bloqueio)

        # e o banco migrado continua marcando
        nova = repo.salvar(Compromisso(
            titulo="Nova visita", tipo=VISITA, inicio=quando(1, 10), status=AGENDADO
        ))
        self.assertEqual(repo.obter(nova.id).tipo, VISITA)
        self.assertEqual(len(repo.grade(date.today(), dias=3).dias), 3)


if __name__ == "__main__":
    unittest.main()


class FaixaDeHorasTestCase(unittest.TestCase):
    """A grade nunca esconde um compromisso - nem as 5h, nem as 23h."""

    def setUp(self) -> None:
        self.repo = AgendaRepository(open_database(
            Path(tempfile.mkdtemp()) / "agenda.db"
        ))
        self.hoje = date.today()

    def _marcar(self, hora: int, minuto: int = 0, duracao: int = 60):
        quando = datetime.combine(self.hoje, datetime.min.time()).replace(
            hour=hora, minute=minuto
        )
        return self.repo.salvar(Compromisso(
            titulo=f"As {hora}h", inicio=quando.isoformat(timespec="minutes"),
            duracao_min=duracao,
        ))

    def _grade(self):
        return self.repo.grade(inicio_da_semana(self.hoje), 7)

    def test_a_grade_mostra_o_dia_inteiro_por_padrao(self) -> None:
        """Para marcar as 5h, a linha das 5h precisa estar la."""
        grade = self._grade()
        self.assertEqual((grade.hora_inicial, grade.hora_final), (0, 24))

    def test_a_faixa_curta_estica_para_o_que_esta_marcado(self) -> None:
        """Quem aperta a faixa nao pode perder o que marcou fora dela."""
        self._marcar(5)
        self._marcar(21, duracao=90)
        grade = self.repo.grade(inicio_da_semana(self.hoje), 7,
                                hora_inicial=7, hora_final=20)

        self.assertEqual(grade.hora_inicial, 5)
        self.assertEqual(grade.hora_final, 23)
        for dia in grade.dias:
            for compromisso in dia.compromissos:
                hora = compromisso.inicio_dt.hour
                with self.subTest(compromisso.titulo):
                    self.assertGreaterEqual(hora, grade.hora_inicial)
                    self.assertLess(hora, grade.hora_final)

    def test_quem_termina_na_hora_cheia_nao_pede_linha_extra(self) -> None:
        def com_faixa_curta():
            return self.repo.grade(inicio_da_semana(self.hoje), 7,
                                   hora_inicial=7, hora_final=20)

        self._marcar(18, duracao=120)             # termina exatamente as 20h
        self.assertEqual(com_faixa_curta().hora_final, 20)

        self._marcar(18, minuto=30, duracao=120)  # termina 20h30
        self.assertEqual(com_faixa_curta().hora_final, 21)

    def test_o_dia_inteiro_nunca_precisa_esticar(self) -> None:
        self._marcar(0)
        self._marcar(23, duracao=59)
        grade = self._grade()
        self.assertEqual((grade.hora_inicial, grade.hora_final), (0, 24))

    def test_a_faixa_escolhida_e_piso_e_nao_limite(self) -> None:
        self._marcar(22)
        grade = self.repo.grade(inicio_da_semana(self.hoje), 7,
                                hora_inicial=8, hora_final=18)
        self.assertEqual(grade.hora_inicial, 8)
        self.assertEqual(grade.hora_final, 23)

    def test_novo_compromisso_nao_sugere_meia_noite(self) -> None:
        """A grade mostra a madrugada; a sugestao comeca no horario de trabalho."""
        from dumtech.apps.agenda.models import HORA_SUGESTAO

        grade = self._grade()
        self.assertEqual(grade.primeiro_livre(self.hoje), time(HORA_SUGESTAO))

    def test_com_o_dia_cheio_a_sugestao_procura_na_madrugada(self) -> None:
        """Ninguem fica sem sugestao: esgotado o dia, vale a hora que sobrar."""
        for hora in range(8, 24):
            self._marcar(hora)
        self.assertEqual(self._grade().primeiro_livre(self.hoje), time(0))

    def test_as_faixas_prontas_sao_coerentes(self) -> None:
        for rotulo, chave, inicial, final in FAIXAS:
            with self.subTest(chave):
                self.assertEqual(faixa_por_chave(chave), (inicial, final))
                self.assertLess(inicial, final)
                self.assertTrue(rotulo.strip())
        self.assertEqual(faixa_por_chave("nao existe"), (HORA_INICIAL, HORA_FINAL))
