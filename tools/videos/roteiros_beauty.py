"""Roteiros da loja "Beauty & Cia": so Clientes e Agenda.

Mesmas regras e pedacos de roteiros.py; muda o que aparece na tela (os dados
de semente_beauty.py) e a visao geral, que mostra so os dois modulos.
"""

from __future__ import annotations

from PySide6.QtCore import QDate, QDateTime, QPoint, Qt, QTime, QTimer

from roteiros import CelularDeMentira, aba, abertura, abrir_modulo, encerramento  # noqa: F401


# ================================================================ CLIENTES
def clientes(d, hub):
    yield from abertura(d, "clientes", "Clientes",
                        "Cada cliente do salão com telefone, aniversário e as preferências anotadas.")
    yield from abrir_modulo(d, "Clientes", "O Painel mostra suas clientes e as aniversariantes do mês")
    yield 2600
    yield from aba(d, "Clientes", "Na lista, a busca acha por nome, telefone, cidade...", 1400)
    d.dizer("Chegou cliente nova? Vamos cadastrar")
    yield from d.clicar(d.botao("Novo cliente"), espera=1000)
    f = d.dialogo()
    yield from d.digitar(f.nome, "Bianca Ribeiro")
    yield from d.digitar(f.whatsapp, "11912345678", por_segundo=22)
    d.dizer("Data de nascimento no padrão dd/mm/aaaa - o Hub lembra do aniversário")
    yield from d.digitar(f.nascimento, "22/10/1995", por_segundo=18)
    d.dizer("Digitou o CEP: o endereço aparece sozinho")
    yield from d.digitar(f.cep, "09015-000", por_segundo=14, espera=2600)
    yield from d.digitar(f.numero, "250")
    yield 600
    d.dizer("Salvou: ela já aparece como sugestão na hora de agendar")
    yield from d.clicar(f.botao_salvar, espera=1600)
    yield from d.digitar(d.por_dica("Pesquisar por nome"), "Patrícia", espera=1600)
    yield from d.clicar_linha("Patrícia")
    d.dizer("Ver ficha: contato, aniversário e as anotações - como a alergia a amônia")
    yield from d.clicar(d.botao("Ver ficha"), espera=3000)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from encerramento(d, "Um cadastro só: o nome que você digita aqui é o mesmo da agenda.")


# ================================================================== AGENDA
def agenda(d, hub):
    yield from abertura(d, "agenda", "Agenda",
                        "A semana do salão à vista: cada horário, cada cadeira, sem marcar duas clientes juntas.")
    yield from abrir_modulo(d, "Agenda", "A Agenda mostra a semana, hora a hora")
    yield 2600
    d.dizer("Cliente ligou para marcar? Novo compromisso")
    yield from d.clicar(d.botao("Novo compromisso"), espera=1000)
    f = d.dialogo()
    yield from d.digitar(f.titulo, "Corte e hidratação")
    yield from d.escolher(f.tipo, "Atendimento")
    yield from d.digitar(f.cliente, "Juliana Prado", espera=500)
    d.dizer("Dia, hora e duração")
    yield from d.clicar(f.inicio, espera=300)
    amanha = QDateTime(QDate.currentDate().addDays(1), QTime(16, 0))
    QTimer.singleShot(0, lambda: f.inicio.setDateTime(amanha))
    yield 900
    yield from d.digitar(f.local, "Cadeira 2")
    d.dizer("Se bater com outro horário, o Hub avisa antes de salvar")
    yield 900
    yield from d.clicar(f.botao_salvar, espera=1800)
    if d.tem_dialogo():
        yield from d.fechar_dialogo(aceitar=True)
    d.dizer("Hoje volta para o dia atual; as setas andam pela semana")
    yield from d.clicar(d.botao("Hoje"), espera=1600)
    yield from aba(d, "Compromissos", "Em Compromissos, a lista para confirmar, concluir ou mandar WhatsApp", 2800)
    yield from encerramento(d, "Os horários de hoje também aparecem no Início e no celular.")


# ===================================================================== HUB
def hub_geral(d, hub):
    yield from abertura(d, "", "O DumTech Hub", "Clientes e Agenda conversando entre si, num programa só "
                        "- e que funciona sem internet.", sobre="Visão geral")
    d.dizer("A tela de Início junta o dia inteiro do seu salão")
    yield 2600
    d.dizer("Os horários de hoje e as aniversariantes - atualizados sozinhos")
    yield from d.apontar(hub.home_view, QPoint(hub.home_view.width() // 2, 300))
    yield 2200
    for nome, legenda in (("Agenda", "Cada módulo vira uma aba. Agenda: a semana do salão hora a hora"),
                          ("Clientes", "Clientes: telefone, aniversário e preferências de cada cliente")):
        d.dizer(legenda)
        yield from d.clicar(d.botao(nome, indice=0), espera=2600)
    yield from d.clicar(d.botao("Inicio", indice=0), espera=900)

    d.dizer("Ctrl + K abre qualquer tela ou ação, de qualquer lugar")
    yield from d.clicar(d.botao("Buscar no Hub..."), espera=700)
    busca = hub.palette_dialog.busca
    yield from d.digitar(busca, "agenda", limpar=False, espera=1800)
    yield from d.tecla(busca, Qt.Key.Key_Escape, 600)

    d.dizer("Tema escuro para quem atende até mais tarde")
    yield from d.clicar(hub.botao_tema, espera=2200)
    yield from d.clicar(hub.botao_tema, espera=1200)

    d.dizer("E a agenda do salão no celular: é só ler o QR Code")
    yield from d.clicar(hub.perfil, espera=900)
    yield from d.clicar_acao(d.menu_aberto(), "Ver no celular", espera=2800)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from encerramento(d, "Atualiza sozinho, faz cópia de segurança todo dia e cresce com a sua empresa.")


ROTEIROS = {
    "hub": hub_geral,
    "clientes": clientes,
    "agenda": agenda,
}
