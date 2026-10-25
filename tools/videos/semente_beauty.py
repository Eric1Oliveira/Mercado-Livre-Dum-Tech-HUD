"""A loja de demonstracao "Beauty & Cia": um salao de beleza.

So tem Clientes e Agenda liberados (MODULOS vira a licenca local do video).
As clientes tem aniversario e anotacoes; a agenda tem a semana do salao com
horarios marcados, para nenhuma tela abrir vazia.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

EMPRESA = "Beauty & Cia"
CIDADE = "Santo André"
MODULOS = ("clientes", "agenda")


def hora(dias: int, h: int, m: int = 0) -> str:
    base = datetime.combine(date.today() + timedelta(days=dias), datetime.min.time())
    return base.replace(hour=h, minute=m).isoformat(timespec="seconds")


CLIENTES = [
    # nome, fone, cidade, dias ate o aniversario, segmento, observacoes
    ("Camila Ferreira", "11987112233", "Santo André", 0, "Cabelo", "Prefere escova modelada. Café sem açúcar."),
    ("Larissa Mendes", "11976223344", "São Bernardo", 3, "Unhas", ""),
    ("Patrícia Gomes", "11965334455", "Santo André", 25, "Cabelo", "Alergia a amônia - usar coloração sem amônia."),
    ("Renata Oliveira", "11954445566", "Santo André", 90, "Cabelo", ""),
    ("Aline Barbosa", "11943556677", "São Caetano", 6, "Estética", ""),
    ("Vanessa Costa", "11932667788", "Mauá", 150, "Noivas", "Noiva em novembro: teste de penteado feito."),
    ("Marcos Paulo", "11921778899", "Santo André", 200, "Barbearia", "Corte degradê, máquina 1 na lateral."),
    ("Juliana Prado", "11910889900", "Santo André", 45, "Unhas", ""),
]


def semear(paths) -> None:
    from dumtech.apps.agenda.database import open_database as agenda_db
    from dumtech.apps.agenda.models import ATENDIMENTO, CONFIRMADO, CONCLUIDO, VISITA, Compromisso
    from dumtech.apps.agenda.repository import AgendaRepository
    from dumtech.core.contacts import ContactsStore, Contato

    # ---- clientes
    loja = ContactsStore(paths.platform_db)
    hoje = date.today()
    for nome, fone, cidade, dias_aniv, segmento, obs in CLIENTES:
        nasc = (hoje + timedelta(days=dias_aniv)).replace(year=1992)
        loja.criar(Contato(nome=nome, telefone=fone, whatsapp=fone, cidade=cidade, uf="SP",
                           nascimento=nasc.isoformat(), segmento=segmento, observacoes=obs))
    loja.close()

    # ---- agenda: ontem, hoje e os proximos dias
    banco = agenda_db(paths.app_db("agenda"))
    agenda = AgendaRepository(banco)
    for titulo, cliente, inicio, dur, local, tipo, status in (
        ("Hidratação capilar", "Juliana Prado", hora(-1, 15, 0), 60, "Cadeira 2", ATENDIMENTO, CONCLUIDO),
        ("Corte e escova", "Camila Ferreira", hora(0, 9, 0), 60, "Cadeira 1", ATENDIMENTO, CONFIRMADO),
        ("Manicure e pedicure", "Larissa Mendes", hora(0, 10, 30), 60, "Mesa de unhas", ATENDIMENTO, CONFIRMADO),
        ("Coloração sem amônia", "Patrícia Gomes", hora(0, 14, 0), 120, "Cadeira 1", ATENDIMENTO, CONFIRMADO),
        ("Design de sobrancelha", "Aline Barbosa", hora(0, 16, 30), 30, "Sala de estética", ATENDIMENTO, "agendado"),
        ("Progressiva", "Renata Oliveira", hora(1, 10, 0), 180, "Cadeira 1", ATENDIMENTO, "agendado"),
        ("Corte masculino e barba", "Marcos Paulo", hora(1, 14, 0), 45, "Cadeira 2", ATENDIMENTO, CONFIRMADO),
        ("Penteado de noiva - teste final", "Vanessa Costa", hora(2, 9, 30), 90, "Casa da cliente", VISITA, "agendado"),
        ("Manicure", "Camila Ferreira", hora(3, 11, 0), 45, "Mesa de unhas", ATENDIMENTO, "agendado"),
    ):
        agenda.salvar(Compromisso(titulo=titulo, cliente=cliente, inicio=inicio, duracao_min=dur,
                                  local=local, tipo=tipo, status=status))
    banco.close()
