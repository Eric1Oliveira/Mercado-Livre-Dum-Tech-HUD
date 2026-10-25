"""Roteiros da loja "Mercado & Cia": so Estoque, Vendas e Financeiro.

Mesmas regras e pedacos de roteiros.py; muda o que aparece na tela (os dados
de semente_mercado.py) e a visao geral, que mostra so os tres modulos.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt

from roteiros import CelularDeMentira, aba, abertura, abrir_modulo, encerramento, passear  # noqa: F401


# ================================================================== ESTOQUE
def estoque(d, hub):
    yield from abertura(d, "estoque", "Estoque",
                        "Cadastre os produtos da prateleira, dê entrada nas notas e saiba o que repor.")
    yield from abrir_modulo(d, "Estoque", "O Estoque abre no Painel: o retrato do que você tem")
    yield 2200
    d.dizer("Ele avisa o que está no mínimo - café e óleo precisam de reposição")
    yield from passear(d, d.botao("Produtos", indice=-1), 1600)

    yield from aba(d, "Produtos", "Na aba Produtos fica a prateleira inteira")
    yield 900
    d.dizer("Vamos cadastrar um produto novo")
    yield from d.clicar(d.botao("Novo produto"), espera=1000)

    yield from d.digitar(d.por_dica("MOU-001"), "MAC-500")
    yield from d.digitar(d.por_dica("Bipe ou digite o EAN"), "7896001000096", por_segundo=24)
    d.dizer("Nome, categoria e fornecedor - com sugestões do que você já usa")
    yield from d.digitar(d.por_dica("Mouse USB sem fio"), "Macarrão espaguete 500g")
    yield from d.digitar(d.por_dica("Perifericos"), "Mercearia")
    yield from d.digitar(d.por_dica("De quem voce compra"), "Distribuidora Paulista")
    d.dizer("Quantidade, estoque mínimo, custo e preço de venda")
    yield from d.digitar(d.campo("Quantidade"), "40")
    yield from d.digitar(d.campo("Minimo"), "12")
    yield from d.digitar(d.campo("Custo medio"), "3,10")
    yield from d.digitar(d.campo("Venda"), "4,99")
    yield 600
    d.dizer("Salvou: o produto já está pronto para passar no caixa")
    yield from d.clicar(d.botao("Salvar"), espera=1500)

    d.dizer("A busca acha por nome, código ou código de barras")
    yield from d.digitar(d.por_dica("Pesquisar por codigo"), "macarrão")
    yield 2200
    yield from d.digitar(d.por_dica("Pesquisar por codigo"), "", espera=800)

    yield from aba(d, "Entradas", "Em Entradas você lança a nota da distribuidora de uma vez", 2600)
    yield from aba(d, "Painel", "E o Painel mostra quanto dinheiro está parado na prateleira", 2600)
    yield from encerramento(d, "O Estoque conversa com Vendas e Financeiro: passou no caixa, a baixa é automática.")


# =================================================================== VENDAS
def vendas(d, hub):
    yield from abertura(d, "vendas", "Vendas",
                        "O caixa do mercado: bipe, receba de várias formas e feche o caixa no fim do dia.")
    yield from abrir_modulo(d, "Vendas", "Vendas abre direto no Balcão, pronto para a fila")
    yield 1200
    produto = d.por_dica("Bipe o codigo de barras")
    d.dizer("Bipou o código de barras: o produto entra na venda")
    yield from d.digitar(produto, "7896000100015", por_segundo=30)
    yield from d.tecla(produto, Qt.Key.Key_Return, 900)
    yield from d.clicar(d.botao("Adicionar"), espera=1100)
    d.dizer("Ou digite o nome: o Hub sugere do seu estoque")
    yield from d.digitar(produto, "Café", espera=1000)
    yield from d.clicar_sugestao(0, espera=900)
    yield from d.clicar(d.botao("Adicionar"), espera=1200)
    d.dizer("Cliente é opcional - e também vem com sugestão")
    yield from d.digitar(d.por_dica("Consumidor"), "Fernanda Lima", espera=600)
    yield from d.tecla(d.por_dica("Consumidor"), Qt.Key.Key_Tab, 600)
    d.dizer("F12 para receber")
    yield from d.clicar(d.botao("Receber  (F12)"), espera=1200)
    dialogo = d.dialogo()
    d.dizer("Dinheiro, Pix, cartão ou fiado - e o troco é calculado na hora")
    yield from d.digitar(dialogo.recebido, "100,00", espera=600)
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
                        "Contas a pagar e a receber, o fiado, o fluxo de caixa e o saldo de cada conta.")
    yield from abrir_modulo(d, "Financeiro", "O Financeiro começa pelo Fluxo: o que entra e o que sai")
    yield 2600
    yield from aba(d, "Painel", "O Painel mostra o que vence, o que atrasou e o saldo", 2600)
    yield from aba(d, "Lancamentos", "Em Lançamentos ficam todas as contas", 1600)
    d.dizer("Vamos lançar uma compra que o cliente vai pagar depois")
    yield from d.clicar(d.botao("Novo lancamento"), espera=1000)
    f = d.dialogo()
    yield from d.digitar(f.descricao, "Compra do mês - Sabor Caseiro")
    yield from d.digitar(f.valor, "450,00")
    yield from d.digitar(f.categoria.lineEdit(), "Vendas")
    yield from d.digitar(f.cliente, "Restaurante Sabor Caseiro", espera=500)
    d.dizer("Salvou: a conta aparece no vencimento certo")
    yield from d.clicar(f.botao_salvar, espera=1600)

    d.dizer("O cliente pagou o fiado? Selecione a conta e clique em Receber / pagar")
    yield from d.clicar_linha("Fiado do mês - Lanchonete do Zé")
    yield from d.clicar(d.botao("Receber / pagar"), espera=1200)
    baixa = d.dialogo()
    yield 1200
    d.dizer("Pode receber tudo ou só uma parte")
    yield from d.clicar(baixa.botao_salvar, espera=1800)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from aba(d, "Contas", "Em Contas, o saldo do banco e da gaveta, sempre batendo", 2600)
    yield from encerramento(d, "Venda fiado e nota de compra viram conta sozinhas - sem digitar duas vezes.")


# ===================================================================== HUB
def hub_geral(d, hub):
    yield from abertura(d, "", "O DumTech Hub", "Estoque, Vendas e Financeiro conversando entre si, num "
                        "programa só - e que funciona sem internet.", sobre="Visão geral")
    d.dizer("A tela de Início junta o dia inteiro do seu mercado")
    yield 2600
    d.dizer("Caixa, vendas, contas e estoque - atualizados sozinhos")
    yield from d.apontar(hub.home_view, QPoint(hub.home_view.width() // 2, 300))
    yield 2200
    for nome, legenda in (("Vendas", "Cada módulo vira uma aba. Vendas: o caixa do mercado"),
                          ("Estoque", "Estoque: produtos, entradas e reposição"),
                          ("Financeiro", "Financeiro: contas a pagar, a receber e o fiado")):
        d.dizer(legenda)
        yield from d.clicar(d.botao(nome, indice=0), espera=2400)
    yield from d.clicar(d.botao("Inicio", indice=0), espera=900)

    d.dizer("Ctrl + K abre qualquer tela ou ação, de qualquer lugar")
    yield from d.clicar(d.botao("Buscar no Hub..."), espera=700)
    busca = hub.palette_dialog.busca
    yield from d.digitar(busca, "caixa", limpar=False, espera=1800)
    yield from d.tecla(busca, Qt.Key.Key_Escape, 600)

    d.dizer("Tema escuro para quem fecha o caixa à noite")
    yield from d.clicar(hub.botao_tema, espera=2200)
    yield from d.clicar(hub.botao_tema, espera=1200)

    d.dizer("E o seu mercado no celular: é só ler o QR Code")
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
}
