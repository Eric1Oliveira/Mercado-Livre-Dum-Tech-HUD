"""Os roteiros: o que cada video mostra, passo a passo.

Cada roteiro e um gerador `(d: Diretor, hub) -> yield ms`. Regras:
  * curto e simples: abrir, mostrar o painel, cadastrar UM item, mostrar o
    resultado - o cliente entende o modulo em menos de um minuto e meio;
  * legenda diz o que esta acontecendo, em portugues de balcao;
  * so o que o Hub faz de verdade (nada simulado alem do servidor).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QDate, QDateTime, QPoint, Qt, QTime, QTimer

from gravador import GRADE, cartao_de_titulo

LARGURA, ALTURA = 1600, 900

# cor e icone de cada modulo (os mesmos da loja: landingpage/js/dados.js)
MODULOS = {
    "estoque": ("#8A7BF8", "M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z M3 7.5 12 12l9-4.5 M12 12v9"),
    "vendas": ("#D8574F", "M3 4h2.2l2.3 11.2a1.5 1.5 0 0 0 1.5 1.2h8.4a1.5 1.5 0 0 0 1.5-1.2L21 8H6 M9.5 20.5h.01 M17.5 20.5h.01"),
    "financeiro": ("#2E9E6B", "M3 6h18v12H3z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M6.5 9.5h.01 M17.5 14.5h.01"),
    "orcamentos": ("#E0902F", "M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7l-4-4z M14 3v4h4 M9 12.5h6 M9 16.5h6"),
    "ordens": ("#4C7EF3", "M20.5 6.2a5.5 5.5 0 0 1-7.3 7.3L6 20.7a2 2 0 0 1-2.8-2.8l7.2-7.2a5.5 5.5 0 0 1 7.3-7.3l-3.2 3.2 2.8 2.8 3.2-3.2z"),
    "clientes": ("#2FB6A6", "M9 11.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M2.5 20a6.5 6.5 0 0 1 13 0 M17 5.2a3.5 3.5 0 0 1 0 6.6 M18 14.4a6.5 6.5 0 0 1 3.5 5.6"),
    "agenda": ("#C05FD4", "M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M4 10h16 M8.5 3v4 M15.5 3v4 M8 14h.01 M12 14h.01 M16 14h.01"),
}


class CelularDeMentira:
    """O video mostra a janela do QR sem falar com o servidor."""

    def iniciar(self):
        agora = datetime.now(timezone.utc) + timedelta(minutes=5)
        return {"codigo": "d" * 64, "link": "https://dumtechsolution.com/celular/#p=" + "d" * 64,
                "expira_em": agora.isoformat()}

    def aparelhos(self):
        return []

    def revogar(self, _):
        pass

    def publicar(self, _):
        return 0


# ------------------------------------------------------------------ pedacos
def abertura(d, modulo: str, titulo: str, texto: str, sobre: str = "Módulo"):
    cor, icone = MODULOS.get(modulo, ("#7353F6", GRADE))
    yield from d.cartao(cartao_de_titulo(LARGURA, ALTURA, sobre, titulo, texto, icone, cor, 3.4), 3.4)


def encerramento(d, texto: str):
    d.dizer("")
    yield from d.cartao(cartao_de_titulo(LARGURA, ALTURA, "DumTech Hub", "Pronto para usar",
                                         texto, GRADE, "#5b3fe0", 3.6, sair=False), 3.6, manter=True)


def abrir_modulo(d, nome_aba: str, legenda: str):
    d.dizer(legenda)
    yield from d.clicar(d.botao(nome_aba, indice=0), espera=1400)


def aba(d, nome: str, legenda: str = "", espera: int = 1800):
    if legenda:
        d.dizer(legenda)
    yield from d.clicar(d.botao(nome, indice=-1), espera=espera)


def passear(d, widget, espera: int = 900):
    yield from d.apontar(widget)
    yield espera


# ================================================================== ESTOQUE
def estoque(d, hub):
    yield from abertura(d, "estoque", "Estoque",
                        "Cadastre produtos, dê entrada nas notas e saiba o que precisa comprar.")
    yield from abrir_modulo(d, "Estoque", "O Estoque abre no Painel: o retrato do que você tem")
    yield 2200
    d.dizer("Ele avisa o que está no mínimo e precisa comprar")
    yield from passear(d, d.botao("Produtos", indice=-1), 1600)

    yield from aba(d, "Produtos", "Na aba Produtos fica o catálogo inteiro")
    yield 900
    d.dizer("Vamos cadastrar um produto novo")
    yield from d.clicar(d.botao("Novo produto"), espera=1000)

    yield from d.digitar(d.por_dica("MOU-001"), "CAP-S23")
    yield from d.digitar(d.por_dica("Bipe ou digite o EAN"), "7891000900099", por_segundo=24)
    d.dizer("Nome, categoria e fornecedor - com sugestões do que você já usa")
    yield from d.digitar(d.por_dica("Mouse USB sem fio"), "Capinha Galaxy S23 antichoque")
    yield from d.digitar(d.por_dica("Perifericos"), "Capinhas")
    yield from d.digitar(d.por_dica("De quem voce compra"), "Distribuidora Sul")
    d.dizer("Quantidade, estoque mínimo, custo e preço de venda")
    yield from d.digitar(d.campo("Quantidade"), "15")
    yield from d.digitar(d.campo("Estoque minimo"), "5")
    yield from d.digitar(d.campo("Custo medio"), "11,00")
    yield from d.digitar(d.campo("Venda"), "44,90")
    yield 600
    d.dizer("Salvou: o produto já está pronto para vender no balcão")
    yield from d.clicar(d.botao("Salvar"), espera=1500)

    d.dizer("A busca acha por nome, código ou código de barras")
    yield from d.digitar(d.por_dica("Pesquisar por codigo"), "capinha")
    yield 2200
    yield from d.digitar(d.por_dica("Pesquisar por codigo"), "", espera=800)

    yield from aba(d, "Entradas", "Em Entradas você lança a nota do fornecedor de uma vez", 2600)
    yield from aba(d, "Painel", "E o Painel mostra quanto dinheiro está parado no estoque", 2600)
    yield from encerramento(d, "O Estoque conversa com Vendas, Orçamentos e Ordens de Serviço: "
                               "vendeu, a baixa é automática.")


# =================================================================== VENDAS
def vendas(d, hub):
    yield from abertura(d, "vendas", "Vendas",
                        "O balcão da loja: bipe, receba de várias formas e feche o caixa no fim do dia.")
    yield from abrir_modulo(d, "Vendas", "Vendas abre direto no Balcão, pronto para a fila")
    yield 1200
    produto = d.por_dica("Bipe o codigo de barras")
    d.dizer("Bipou o código de barras: o produto entra na venda")
    yield from d.digitar(produto, "7891000300037", por_segundo=30)
    yield from d.tecla(produto, Qt.Key.Key_Return, 900)
    yield from d.clicar(d.botao("Adicionar"), espera=1100)
    d.dizer("Ou digite o nome: o Hub sugere do seu estoque")
    yield from d.digitar(produto, "Capinha", espera=1000)
    yield from d.clicar_sugestao(0, espera=900)
    yield from d.clicar(d.botao("Adicionar"), espera=1200)
    d.dizer("Cliente é opcional - e também vem com sugestão")
    yield from d.digitar(d.por_dica("Consumidor"), "Pedro Henrique", espera=600)
    yield from d.tecla(d.por_dica("Consumidor"), Qt.Key.Key_Tab, 600)
    d.dizer("F12 para receber")
    yield from d.clicar(d.botao("Receber  (F12)"), espera=1200)
    dialogo = d.dialogo()
    d.dizer("Dinheiro, Pix, cartão ou a prazo - e o troco é calculado na hora")
    yield from d.digitar(dialogo.recebido, "150,00", espera=600)
    yield from d.clicar(dialogo.botao_lancar, espera=1800)
    d.dizer("Recebido: o estoque baixa sozinho e a venda entra no caixa")
    yield from d.clicar(dialogo.botao_receber, espera=2200)
    if d.tem_dialogo():  # comprovante / pergunta final
        yield 1500
        yield from d.fechar_dialogo()
    yield from aba(d, "Painel", "O Painel mostra quanto vendeu hoje, no mês e de que forma", 2800)
    yield from aba(d, "Vendas", "Todas as vendas, com comprovante e devolução", 2400)
    yield from aba(d, "Caixa", "E o caixa: abertura, sangria, suprimento e fechamento conferido", 2800)
    yield from encerramento(d, "Vendeu fiado? A conta a receber nasce sozinha no Financeiro.")


# =============================================================== FINANCEIRO
def financeiro(d, hub):
    yield from abertura(d, "financeiro", "Financeiro",
                        "Contas a pagar e a receber, fluxo de caixa e o saldo de cada conta.")
    yield from abrir_modulo(d, "Financeiro", "O Financeiro começa pelo Fluxo: o que entra e o que sai")
    yield 2600
    yield from aba(d, "Painel", "O Painel mostra o que vence, o que atrasou e o saldo", 2600)
    yield from aba(d, "Lancamentos", "Em Lançamentos ficam todas as contas", 1600)
    d.dizer("Vamos lançar um conserto que o cliente vai pagar depois")
    yield from d.clicar(d.botao("Novo lancamento"), espera=1000)
    f = d.dialogo()
    yield from d.digitar(f.descricao, "Troca de tela Samsung A12")
    yield from d.digitar(f.valor, "250,00")
    yield from d.digitar(f.categoria.lineEdit(), "Serviços")
    yield from d.digitar(f.cliente, "Carlos Lima", espera=500)
    d.dizer("Salvou: a conta aparece no vencimento certo")
    yield from d.clicar(f.botao_salvar, espera=1600)

    d.dizer("O cliente pagou? Selecione a conta e clique em Receber / pagar")
    yield from d.clicar_linha("Conserto notebook Dell")
    yield from d.clicar(d.botao("Receber / pagar"), espera=1200)
    baixa = d.dialogo()
    yield 1200
    d.dizer("Pode receber tudo ou só uma parte")
    yield from d.clicar(baixa.botao_salvar, espera=1800)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from aba(d, "Contas bancárias", "Em Contas bancárias, o saldo do banco e da gaveta, sempre batendo", 2600)
    yield from encerramento(d, "Venda a prazo e nota de compra viram conta sozinhas - sem digitar duas vezes.")


# ================================================================== ORDENS
def ordens(d, hub):
    yield from abertura(d, "ordens", "Ordem de Serviço",
                        "Da entrada do aparelho à entrega: bancada por etapa, aprovação e garantia.")
    yield from abrir_modulo(d, "Ordens", "A Bancada mostra cada serviço na etapa em que está")
    yield 2600
    d.dizer("Chegou um aparelho? Nova ordem")
    yield from d.clicar(d.botao("Nova ordem"), espera=1000)
    f = d.dialogo()
    yield from d.digitar(f.cliente, "Ana Souza", espera=500)
    yield from d.digitar(f.telefone, "(11) 98765-4321", por_segundo=22)
    yield from d.digitar(f.defeito, "Trocar a tela - vidro trincado, touch funcionando")
    yield from d.digitar(f.equipamento, "iPhone 13")
    d.dizer("Peças e serviços: a peça sai do estoque quando você entregar")
    yield from d.escolher(f.itens.tipo, "Peca")
    yield from d.digitar(f.itens.descricao, "Tela iPhone 13", espera=500)
    yield from d.digitar(f.itens.valor, "590,00")
    yield from d.clicar(d.botao("Adicionar"), espera=700)
    yield from d.escolher(f.itens.tipo, "Servico")
    yield from d.digitar(f.itens.descricao, "Mão de obra - troca de tela", espera=300)
    yield from d.digitar(f.itens.valor, "100,00")
    yield from d.clicar(d.botao("Adicionar"), espera=900)
    d.dizer("Salvou: a ordem entra na bancada")
    yield from d.clicar(f.botao_salvar, espera=1800)
    d.dizer("Selecione a ordem: o botão já diz o próximo passo")
    yield from d.clicar(d.rotulo("iPhone 13"), espera=1200)
    d.dizer("Mandou para aprovação: o cliente recebe o orçamento pelo WhatsApp")
    yield from d.clicar(d.botao("Mandar para aprovacao"), espera=1800)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from aba(d, "Ordens", "A lista completa, com prazo, valor e situação", 2400)
    yield from aba(d, "Painel", "E o Painel: o que está atrasado e quanto a oficina faturou", 2600)
    yield from encerramento(d, "Entregou? Registre o pagamento: o valor cai no caixa ou vira conta a receber.")


# ============================================================== ORCAMENTOS
def orcamentos(d, hub):
    yield from abertura(d, "orcamentos", "Orçamentos",
                        "Proposta com a sua marca em PDF, acompanhamento e aprovação em um clique.")
    yield from abrir_modulo(d, "Orcamentos", "O Funil mostra cada proposta na etapa em que está")
    yield 2600
    yield from aba(d, "Orcamentos", "Na lista ficam todas as propostas", 1400)
    d.dizer("Vamos montar uma proposta")
    yield from d.clicar(d.botao("Nova proposta"), espera=1000)
    f = d.dialogo()
    yield from d.digitar(d.por_dica("Para quem e a proposta"), "Juliana Alves", espera=500)
    d.dizer("Os itens podem vir do estoque, com o preço já preenchido")
    editor = d.por_dica("O que esta sendo cotado").parentWidget()
    yield from d.digitar(editor.descricao, "Carregador USB-C 20W", espera=500)
    yield from d.digitar(editor.quantidade, "2")
    yield from d.digitar(editor.valor, "89,90")
    yield from d.clicar(d.botao("Adicionar"), espera=800)
    yield from d.digitar(editor.descricao, "Película 3D vidro temperado", espera=300)
    yield from d.digitar(editor.valor, "29,90")
    yield from d.clicar(d.botao("Adicionar"), espera=900)
    yield from d.digitar(d.por_dica("50% na entrada"), "Pix ou cartão na entrega")
    d.dizer("Salvou: a proposta vai para o funil")
    yield from d.clicar(f.botao_salvar, espera=1600)
    d.dizer("Documento gera o PDF com o seu logotipo; Enviar marca que o cliente recebeu")
    yield from d.clicar_linha("Juliana Alves")
    yield from d.clicar(d.botao("Enviar"), espera=1400)
    if d.tem_dialogo():
        yield from d.fechar_dialogo(aceitar=True)
    d.dizer("O cliente aprovou? Um clique - e a proposta vira venda ou ordem de serviço")
    yield from d.clicar_linha("Juliana Alves")
    yield from d.apontar(d.botao("Aprovar"))
    yield 1600
    yield from aba(d, "Funil", "O Funil mostra quanto está em negociação", 2600)
    yield from encerramento(d, "Aprovou? A proposta vira venda no balcão ou ordem na bancada, com os itens dentro.")


# ================================================================ CLIENTES
def clientes(d, hub):
    yield from abertura(d, "clientes", "Clientes",
                        "Um cadastro só para o balcão, as propostas, as ordens e a agenda.")
    yield from abrir_modulo(d, "Clientes", "O Painel mostra quem são seus clientes e os aniversariantes")
    yield 2600
    yield from aba(d, "Clientes", "Na lista, a busca acha por nome, telefone, cidade...", 1400)
    d.dizer("Vamos cadastrar um cliente")
    yield from d.clicar(d.botao("Novo cliente"), espera=1000)
    f = d.dialogo()
    yield from d.digitar(f.nome, "Rafael Martins")
    yield from d.digitar(f.whatsapp, "11912345678", por_segundo=22)
    d.dizer("Data de nascimento no padrão dd/mm/aaaa")
    yield from d.digitar(f.nascimento, "14/03/1990", por_segundo=18)
    d.dizer("Digitou o CEP: o endereço aparece sozinho")
    yield from d.digitar(f.cep, "09015-000", por_segundo=14, espera=2600)
    yield from d.digitar(f.numero, "250")
    yield 600
    d.dizer("Salvou: o cliente já aparece como sugestão em todos os módulos")
    yield from d.clicar(f.botao_salvar, espera=1600)
    yield from d.digitar(d.por_dica("Pesquisar por nome"), "Rafael", espera=1600)
    yield from d.clicar_linha("Rafael")
    d.dizer("Ver ficha: tudo o que ele comprou, orçou e agendou")
    yield from d.clicar(d.botao("Ver ficha"), espera=2600)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from encerramento(d, "Um cadastro só: o nome que você digita no balcão é o mesmo da proposta e da ordem.")


# ================================================================== AGENDA
def agenda(d, hub):
    yield from abertura(d, "agenda", "Agenda",
                        "A semana inteira à vista: atendimentos, visitas e entregas, sem conflito de horário.")
    yield from abrir_modulo(d, "Agenda", "A Agenda mostra a semana, hora a hora")
    yield 2600
    d.dizer("Novo compromisso")
    yield from d.clicar(d.botao("Novo compromisso"), espera=1000)
    f = d.dialogo()
    yield from d.digitar(f.titulo, "Instalação de película na loja do cliente")
    yield from d.escolher(f.tipo, "Visita")
    yield from d.digitar(f.cliente, "Juliana Alves", espera=500)
    d.dizer("Dia, hora e duração")
    yield from d.clicar(f.inicio, espera=300)
    amanha = QDateTime(QDate.currentDate().addDays(1), QTime(15, 0))
    QTimer.singleShot(0, lambda: f.inicio.setDateTime(amanha))
    yield 900
    yield from d.digitar(f.local, "Casa do cliente")
    d.dizer("Se bater com outro horário, o Hub avisa antes de salvar")
    yield 900
    yield from d.clicar(f.botao_salvar, espera=1800)
    if d.tem_dialogo():
        yield from d.fechar_dialogo(aceitar=True)
    d.dizer("Hoje volta para o dia atual; as setas andam pela semana")
    yield from d.clicar(d.botao("Hoje"), espera=1600)
    yield from aba(d, "Compromissos", "Em Compromissos, a lista para confirmar, concluir ou mandar WhatsApp", 2800)
    yield from encerramento(d, "Os compromissos de hoje também aparecem no Início e no celular.")


# ===================================================================== HUB
def hub_geral(d, hub):
    from PySide6.QtWidgets import QApplication

    yield from abertura(d, "", "O DumTech Hub", "Sete sistemas que conversam entre si, num programa só "
                        "- e que funciona sem internet.", sobre="Visão geral")
    d.dizer("A tela de Início junta o dia inteiro da sua empresa")
    yield 2600
    d.dizer("Caixa, vendas, propostas, oficina, estoque e agenda - atualizados sozinhos")
    yield from d.apontar(hub.home_view, QPoint(hub.home_view.width() // 2, 300))
    yield 2200
    for nome, legenda in (("Vendas", "Cada módulo vira uma aba. Vendas: o balcão da loja"),
                          ("Estoque", "Estoque: produtos, entradas e contagem"),
                          ("Financeiro", "Financeiro: contas a pagar e a receber"),
                          ("Ordens", "Ordens de serviço: a bancada por etapa"),
                          ("Orcamentos", "Orçamentos: o funil das propostas"),
                          ("Agenda", "Agenda: a semana hora a hora"),
                          ("Clientes", "Clientes: um cadastro para todos")):
        d.dizer(legenda)
        yield from d.clicar(d.botao(nome, indice=0), espera=2100)
    yield from d.clicar(d.botao("Inicio", indice=0), espera=900)

    d.dizer("Ctrl + K abre qualquer tela ou ação, de qualquer lugar")
    yield from d.clicar(d.botao("Buscar no Hub..."), espera=700)
    busca = hub.palette_dialog.busca
    yield from d.digitar(busca, "caixa", limpar=False, espera=1800)
    yield from d.tecla(busca, Qt.Key.Key_Escape, 600)

    d.dizer("Tema escuro para quem trabalha à noite")
    yield from d.clicar(hub.botao_tema, espera=2200)
    yield from d.clicar(hub.botao_tema, espera=1200)

    d.dizer("E o seu negócio no celular: é só ler o QR Code")
    yield from d.clicar(hub.perfil, espera=900)
    yield from d.clicar_acao(d.menu_aberto(), "Ver no celular", espera=2800)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from encerramento(d, "Atualiza sozinho, faz cópia de segurança todo dia e cresce com a sua empresa.")


ROTEIROS = {
    "hub": hub_geral,
    "vendas": vendas,
    "estoque": estoque,
    "financeiro": financeiro,
    "ordens": ordens,
    "orcamentos": orcamentos,
    "clientes": clientes,
    "agenda": agenda,
}
