"""Passo a passo: um video curto por tarefa, para o catalogo "Passo a passo" do site.

Cada video responde UMA pergunta ("como cadastro um produto?") do comeco ao fim, em menos de um minuto.
As legendas viram a lista de passos clicavel do site (o gravador anota o segundo de cada uma), entao
cada `d.dizer` deve ser um passo que se entende sozinho.

CATALOGO e a fonte da busca do site: titulo, perguntas que as pessoas fazem e palavras parecidas.
`publicar_passo.py` junta isto aos videos gravados e escreve landingpage/passo-a-passo/catalogo.js.
"""

from __future__ import annotations

from PySide6.QtCore import QDate, QDateTime, QPoint, Qt, QTime, QTimer

from gravador import GRADE, cartao_de_titulo
from roteiros import MODULOS, CelularDeMentira  # noqa: F401 - o gravar.py pega o celular de mentira daqui

LARGURA, ALTURA = 1280, 720

# ------------------------------------------------------------------ o catalogo (busca do site)
#: id -> dados do cartao no site. "perguntas": como as pessoas escrevem; "palavras": sinonimos.
CATALOGO = {
    "primeiros-passos": dict(
        titulo="Conhecendo o DumTech Hub", modulo="hub", grupo="Primeiros passos",
        resumo="Onde fica cada coisa: o Início, as abas dos módulos e a busca.",
        perguntas=["como funciona o programa", "por onde começo", "como usar o hub", "primeiro acesso"],
        palavras=["inicio", "começar", "comecar", "tela inicial", "abas", "modulos", "tour", "visao geral"]),
    "cadastrar-produto": dict(
        titulo="Como cadastrar um produto", modulo="estoque", grupo="Estoque",
        resumo="Do botão Novo produto até ele estar pronto para vender no balcão.",
        perguntas=["como cadastro produtos", "como cadastrar produto", "como adicionar um produto", "como incluir mercadoria",
                   "como criar item no estoque", "onde cadastro os produtos"],
        palavras=["produto", "produtos", "mercadoria", "item", "cadastro", "novo produto", "codigo de barras", "preço",
                  "preco de venda", "estoque minimo"]),
    "buscar-produto": dict(
        titulo="Como encontrar um produto", modulo="estoque", grupo="Estoque",
        resumo="Ache qualquer produto pelo nome, pelo código ou bipando o código de barras.",
        perguntas=["como procurar produto", "como achar um produto", "como pesquisar no estoque", "onde vejo meus produtos"],
        palavras=["busca", "pesquisa", "procurar", "codigo", "codigo de barras", "bipar", "leitor", "lista de produtos"]),
    "entrada-mercadoria": dict(
        titulo="Como dar entrada de mercadoria", modulo="estoque", grupo="Estoque",
        resumo="Lance a nota do fornecedor: o estoque soma e o custo médio se atualiza.",
        perguntas=["como dar entrada no estoque", "como lançar nota do fornecedor", "chegou mercadoria o que faço",
                   "como repor estoque", "como registrar compra"],
        palavras=["entrada", "nota", "nota fiscal", "fornecedor", "compra", "reposição", "reposicao", "custo", "custo medio"]),
    "contagem-estoque": dict(
        titulo="Como fazer a contagem do estoque", modulo="estoque", grupo="Estoque",
        resumo="Conte o que tem na prateleira e corrija a diferença de uma vez.",
        perguntas=["como fazer inventário", "como ajustar o estoque", "o estoque está errado", "como conferir o estoque"],
        palavras=["contagem", "inventario", "inventário", "ajuste", "conferencia", "balanço", "balanco", "diferença"]),
    "vender-balcao": dict(
        titulo="Como fazer uma venda no balcão", modulo="vendas", grupo="Vendas",
        resumo="Bipe ou digite o produto, escolha o cliente e receba com troco calculado.",
        perguntas=["como vender", "como fazer uma venda", "como usar o pdv", "como passar uma venda", "como cobrar o cliente"],
        palavras=["venda", "vender", "balcao", "balcão", "pdv", "caixa", "receber", "troco", "pix", "cartão", "cartao", "dinheiro",
                  "f12", "bipar"]),
    "caixa": dict(
        titulo="Como abrir, fazer sangria e fechar o caixa", modulo="vendas", grupo="Vendas",
        resumo="Sangria com motivo, fechamento conferido com o que tem na gaveta e abertura do dia.",
        perguntas=["como fechar o caixa", "como abrir o caixa", "como fazer sangria", "como conferir o caixa",
                   "como tirar dinheiro do caixa"],
        palavras=["caixa", "sangria", "suprimento", "fechamento", "abertura", "gaveta", "conferir", "troco"]),
    "devolucao": dict(
        titulo="Como fazer uma devolução", modulo="vendas", grupo="Vendas",
        resumo="O cliente devolveu? Escolha a venda, diga o motivo e o produto volta ao estoque.",
        perguntas=["como fazer devolução", "como devolver uma venda", "como estornar uma venda", "cliente quer devolver"],
        palavras=["devolucao", "devolução", "troca", "estorno", "cancelar venda", "reembolso"]),
    "lancar-conta": dict(
        titulo="Como lançar uma conta a pagar ou a receber", modulo="financeiro", grupo="Financeiro",
        resumo="Despesa, boleto ou conserto que o cliente paga depois: lance uma vez e acompanhe.",
        perguntas=["como lançar uma conta", "como cadastrar despesa", "como registrar um boleto", "conta a pagar",
                   "conta a receber"],
        palavras=["lancamento", "lançamento", "conta", "despesa", "receita", "boleto", "pagar", "receber", "vencimento",
                  "parcelado", "fiado"]),
    "receber-conta": dict(
        titulo="Como dar baixa numa conta", modulo="financeiro", grupo="Financeiro",
        resumo="O cliente pagou ou você pagou um boleto: registre a baixa, total ou parcial.",
        perguntas=["como dar baixa", "como receber uma conta", "como marcar como pago", "cliente pagou o que faço"],
        palavras=["baixa", "quitar", "pago", "recebido", "receber", "pagar", "parcial"]),
    "fluxo-caixa": dict(
        titulo="Como ver o fluxo de caixa", modulo="financeiro", grupo="Financeiro",
        resumo="O saldo de hoje e dos próximos dias, e quando o dinheiro pode faltar.",
        perguntas=["como ver o fluxo de caixa", "quanto dinheiro eu tenho", "como ver o saldo", "previsão de caixa"],
        palavras=["fluxo", "saldo", "projeção", "projecao", "contas", "banco", "previsao", "relatorio financeiro"]),
    "abrir-ordem": dict(
        titulo="Como abrir uma ordem de serviço", modulo="ordens", grupo="Ordem de Serviço",
        resumo="Chegou um aparelho: cliente, defeito, peças e serviços, tudo numa ordem.",
        perguntas=["como abrir ordem de serviço", "como fazer uma os", "como registrar um conserto", "chegou um aparelho"],
        palavras=["ordem", "os", "ordem de servico", "conserto", "assistencia", "assistência", "oficina", "defeito",
                  "equipamento", "peça", "serviço"]),
    "avancar-ordem": dict(
        titulo="Como levar a ordem até a entrega", modulo="ordens", grupo="Ordem de Serviço",
        resumo="Aprovação do cliente, serviço concluído e entrega com pagamento, etapa por etapa.",
        perguntas=["como entregar o aparelho", "como aprovar uma ordem", "como concluir uma os", "como mudar a etapa"],
        palavras=["etapa", "aprovação", "aprovacao", "concluir", "entregar", "entrega", "bancada", "garantia", "status"]),
    "criar-orcamento": dict(
        titulo="Como fazer um orçamento", modulo="orcamentos", grupo="Orçamentos",
        resumo="Monte a proposta com os itens do estoque e gere o PDF com a sua marca.",
        perguntas=["como fazer um orçamento", "como criar uma proposta", "como mandar orçamento para o cliente"],
        palavras=["orcamento", "orçamento", "proposta", "cotação", "cotacao", "pdf", "itens"]),
    "aprovar-orcamento": dict(
        titulo="Como enviar e aprovar uma proposta", modulo="orcamentos", grupo="Orçamentos",
        resumo="Marque que enviou, registre a aprovação e transforme em venda ou ordem.",
        perguntas=["o cliente aprovou o orçamento", "como aprovar proposta", "como transformar orçamento em venda"],
        palavras=["aprovar", "enviar", "funil", "gerar venda", "gerar ordem", "recusar", "proposta aceita"]),
    "cadastrar-cliente": dict(
        titulo="Como cadastrar um cliente", modulo="clientes", grupo="Clientes",
        resumo="Nome, WhatsApp e aniversário; o CEP preenche o endereço sozinho.",
        perguntas=["como cadastro clientes", "como cadastrar cliente", "como adicionar um cliente", "onde ficam meus clientes"],
        palavras=["cliente", "clientes", "cadastro", "contato", "whatsapp", "cep", "endereço", "aniversario", "freguês"]),
    "ficha-cliente": dict(
        titulo="Como ver o histórico de um cliente", modulo="clientes", grupo="Clientes",
        resumo="Tudo o que ele comprou, orçou e agendou, numa ficha só.",
        perguntas=["como ver o que o cliente comprou", "histórico do cliente", "como abrir a ficha do cliente"],
        palavras=["ficha", "historico", "histórico", "compras do cliente", "cliente"]),
    "marcar-compromisso": dict(
        titulo="Como marcar um compromisso na agenda", modulo="agenda", grupo="Agenda",
        resumo="Atendimento, visita ou entrega: dia, hora e cliente, sem bater horário.",
        perguntas=["como marcar horário", "como agendar", "como usar a agenda", "como marcar uma visita"],
        palavras=["agenda", "agendar", "compromisso", "horario", "horário", "visita", "atendimento", "marcar"]),
    "link-de-agendamento": dict(
        titulo="Como criar o link para o cliente marcar sozinho", modulo="agenda", grupo="Agenda",
        resumo="Mande o link no WhatsApp: o cliente escolhe um horário livre e o compromisso cai na Agenda.",
        perguntas=["como o cliente marca sozinho", "link de agendamento", "como criar agendamento online",
                   "como mandar a agenda para o cliente", "cliente agendar pelo celular", "agendamento pelo instagram"],
        palavras=["link", "agendamento", "agendamento online", "online", "agendar", "whatsapp", "instagram",
                  "reserva", "horário livre", "horario livre", "cliente marca", "qr code"]),
    "busca-ctrl-k": dict(
        titulo="Como achar qualquer tela com Ctrl+K", modulo="hub", grupo="Primeiros passos",
        resumo="A busca do Hub abre telas e ações pelo nome, de qualquer lugar.",
        perguntas=["como pesquisar no programa", "atalho de busca", "como achar uma tela"],
        palavras=["ctrl k", "atalho", "busca", "pesquisa", "menu"]),
    "tema-escuro": dict(
        titulo="Como usar o tema escuro", modulo="hub", grupo="Primeiros passos",
        resumo="Troque entre claro e escuro com um clique.",
        perguntas=["como mudar a cor", "como deixar escuro", "modo noturno"],
        palavras=["tema", "escuro", "claro", "cor", "noturno", "dark"]),
    "celular": dict(
        titulo="Como ver o seu negócio no celular", modulo="hub", grupo="Primeiros passos",
        resumo="Leia o QR Code e acompanhe vendas e agenda pelo celular.",
        perguntas=["como usar no celular", "como ver no celular", "tem aplicativo"],
        palavras=["celular", "qr code", "qrcode", "smartphone", "aplicativo", "app", "telefone"]),
    "minha-empresa": dict(
        titulo="Como colocar os dados da sua empresa", modulo="hub", grupo="Configurações",
        resumo="Nome, contato e endereço que saem nos comprovantes e propostas.",
        perguntas=["como colocar meu logotipo", "como mudar o nome da empresa", "como configurar a empresa",
                   "dados no comprovante"],
        palavras=["empresa", "logotipo", "logo", "cnpj", "endereço", "configuracoes", "configurações", "comprovante"]),
    "backup": dict(
        titulo="Como fazer uma cópia de segurança", modulo="hub", grupo="Configurações",
        resumo="O Hub copia sozinho todo dia, e você pode gerar uma na hora.",
        perguntas=["como fazer backup", "como salvar meus dados", "como não perder os dados", "trocar de computador"],
        palavras=["backup", "copia", "cópia", "segurança", "seguranca", "restaurar", "pen drive", "dados"]),
}


# ------------------------------------------------------------------ pedacos
def abrir(d, id_: str):
    """Cartao de abertura: a pergunta que o video responde."""
    info = CATALOGO[id_]
    cor, icone = MODULOS.get(info["modulo"], ("#7353F6", GRADE))
    yield from d.cartao(cartao_de_titulo(LARGURA, ALTURA, "Passo a passo", info["titulo"], info["resumo"], icone, cor, 2.8), 2.8)


def fim(d, texto: str):
    d.dizer("")
    yield from d.cartao(cartao_de_titulo(LARGURA, ALTURA, "Pronto", "Feito!", texto, GRADE, "#5b3fe0", 2.6, sair=False),
                        2.6, manter=True)


def modulo(d, nome_aba: str, legenda: str, espera: int = 1300):
    d.dizer(legenda)
    yield from d.clicar(d.botao(nome_aba, indice=0), espera=espera)


def aba(d, nome: str, legenda: str = "", espera: int = 1500):
    if legenda:
        d.dizer(legenda)
    yield from d.clicar(d.botao(nome, indice=-1), espera=espera)


def menu_da_empresa(d, hub, item: str, espera: int = 1500):
    yield from d.clicar(hub.perfil, espera=800)
    yield from d.clicar_acao(d.menu_aberto(), item, espera=espera)


# ================================================================ HUB
def primeiros_passos(d, hub):
    yield from abrir(d, "primeiros-passos")
    d.dizer("O Início mostra o dia inteiro da sua empresa")
    yield 2200
    yield from d.apontar(hub.home_view, QPoint(hub.home_view.width() // 2, 300))
    yield 1400
    for nome, legenda in (("Vendas", "Cada módulo é uma aba aqui em cima"),
                          ("Estoque", "Clique na aba para trocar de módulo"),
                          ("Inicio", "A aba Início volta para o resumo do dia")):
        yield from modulo(d, nome, legenda, 1700)
    d.dizer("Ctrl + K abre a busca de qualquer lugar")
    yield from d.clicar(d.botao("Buscar no Hub..."), espera=700)
    busca = hub.palette_dialog.busca
    yield from d.digitar(busca, "produto", limpar=False, espera=1500)
    yield from d.tecla(busca, Qt.Key.Key_Escape, 500)
    yield from fim(d, "Cada vídeo do Passo a passo mostra uma tarefa do começo ao fim.")


def busca_ctrl_k(d, hub):
    yield from abrir(d, "busca-ctrl-k")
    d.dizer("Aperte Ctrl + K (ou clique em Buscar no Hub)")
    yield from d.clicar(d.botao("Buscar no Hub..."), espera=800)
    busca = hub.palette_dialog.busca
    d.dizer("Digite o que procura: uma tela ou uma ação")
    yield from d.digitar(busca, "contagem", limpar=False, espera=1400)
    d.dizer("Enter abre direto o que você escolheu")
    yield from d.tecla(busca, Qt.Key.Key_Return, 1800)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from fim(d, "Funciona em qualquer tela: é o caminho mais curto para tudo.")


def tema_escuro(d, hub):
    yield from abrir(d, "tema-escuro")
    d.dizer("Clique no botão de tema, no alto à direita")
    yield from d.clicar(hub.botao_tema, espera=2400)
    d.dizer("Pronto: tema escuro, para quem trabalha à noite")
    yield 1600
    d.dizer("Clique de novo para voltar ao claro")
    yield from d.clicar(hub.botao_tema, espera=1800)
    yield from fim(d, "A escolha fica guardada para a próxima vez.")


def celular(d, hub):
    yield from abrir(d, "celular")
    d.dizer("Abra o menu da empresa, no canto de cima")
    yield from d.clicar(hub.perfil, espera=900)
    d.dizer("Escolha Ver no celular")
    yield from d.clicar_acao(d.menu_aberto(), "Ver no celular", espera=1800)
    d.dizer("Aponte a câmera do celular para o QR Code")
    yield 2600
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from fim(d, "No celular você acompanha vendas, caixa e agenda de qualquer lugar.")


def minha_empresa(d, hub):
    yield from abrir(d, "minha-empresa")
    d.dizer("No menu da empresa, escolha Minha empresa")
    yield from menu_da_empresa(d, hub, "Minha empresa", 1600)
    d.dizer("Nome, documento e contatos saem nos comprovantes")
    yield from d.digitar(d.campo("WhatsApp"), "11912345678", por_segundo=20)
    yield from d.digitar(d.campo("E-mail"), "contato@conecta.com.br", por_segundo=22)
    d.dizer("O logotipo entra por Escolher logotipo")
    yield from d.apontar(d.botao("Escolher logotipo"))
    yield 1300
    d.dizer("Salve os dados da empresa")
    yield from d.rolar_ate(d.botao("Salvar dados da empresa"))
    yield from d.clicar(d.botao("Salvar dados da empresa"), espera=1600)
    if d.tem_dialogo():
        yield from d.fechar_dialogo(aceitar=True)
    yield from fim(d, "Comprovantes, propostas e mensagens já saem com os seus dados.")


def backup(d, hub):
    yield from abrir(d, "backup")
    d.dizer("No menu da empresa, escolha Backup")
    yield from menu_da_empresa(d, hub, "Backup", 1600)
    d.dizer("O Hub faz uma cópia sozinho todo dia")
    yield 1800
    d.dizer("Fazer backup agora gera uma cópia na hora")
    yield from d.rolar_ate(d.botao("Fazer backup agora"))
    yield from d.clicar(d.botao("Fazer backup agora"), espera=2200)
    if d.tem_dialogo():
        yield 1000
        yield from d.fechar_dialogo(aceitar=True)
    d.dizer("Para levar a outro computador, guarde a cópia num pen drive")
    yield 1800
    yield from fim(d, "Trocou de computador? Restaure a cópia no novo e continue de onde parou.")


# ============================================================ ESTOQUE
def cadastrar_produto(d, hub):
    yield from abrir(d, "cadastrar-produto")
    yield from modulo(d, "Estoque", "Abra o Estoque pela aba no topo")
    yield from aba(d, "Produtos", "Vá em Produtos")
    d.dizer("Clique em Novo produto")
    yield from d.clicar(d.botao("Novo produto"), espera=1000)
    d.dizer("Código interno e código de barras (dá para bipar)")
    yield from d.digitar(d.por_dica("MOU-001"), "CAP-S23")
    yield from d.digitar(d.por_dica("Bipe ou digite"), "7891000900099", por_segundo=24)
    d.dizer("Nome, categoria e fornecedor")
    yield from d.digitar(d.por_dica("Mouse USB sem fio"), "Capinha Galaxy S23 antichoque")
    yield from d.digitar(d.por_dica("Perifericos"), "Capinhas")
    yield from d.digitar(d.por_dica("De quem voce compra"), "Distribuidora Sul")
    d.dizer("Quantidade, estoque mínimo, custo e preço de venda")
    yield from d.digitar(d.campo("Quantidade"), "15")
    yield from d.digitar(d.campo("Estoque minimo"), "5")
    yield from d.digitar(d.campo("Custo medio"), "11,00")
    yield from d.digitar(d.campo("Venda"), "44,90")
    yield 500
    d.dizer("Clique em Salvar")
    yield from d.clicar(d.botao("Salvar"), espera=1500)
    d.dizer("Pronto: o produto já aparece na lista e no balcão")
    yield from d.digitar(d.por_dica("Pesquisar por codigo"), "galaxy", espera=2200)
    yield from fim(d, "Vendeu no balcão? O estoque baixa sozinho.")


def buscar_produto(d, hub):
    yield from abrir(d, "buscar-produto")
    yield from modulo(d, "Estoque", "Abra o Estoque")
    yield from aba(d, "Produtos", "Vá em Produtos")
    busca = d.por_dica("Pesquisar por codigo")
    d.dizer("Digite parte do nome")
    yield from d.digitar(busca, "fone", espera=1900)
    d.dizer("Ou o código interno")
    yield from d.digitar(busca, "CAR-20W", espera=1900)
    d.dizer("Ou bipe o código de barras com o leitor")
    yield from d.digitar(busca, "7891000100013", por_segundo=30, espera=1900)
    d.dizer("Duplo clique abre a ficha do produto")
    yield from d.clicar_linha("Capinha iPhone 13", duplo=True, espera=1900)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from fim(d, "A mesma busca funciona no balcão de Vendas.")


def entrada_mercadoria(d, hub):
    yield from abrir(d, "entrada-mercadoria")
    yield from modulo(d, "Estoque", "Abra o Estoque")
    yield from aba(d, "Entradas", "Vá em Entradas")
    d.dizer("Diga quem vendeu e o número da nota")
    yield from d.digitar(d.por_dica("Quem vendeu para voce"), "Distribuidora Sul", espera=500)
    yield from d.digitar(d.por_dica("Ex.: NF 1234"), "NF 2041")
    for barras, quantidade, custo in (("7891000200020", "20", "4,50"), ("7891000600068", "10", "14,00")):
        d.dizer("Bipe ou digite o produto e aperte Enter")
        bipe = d.por_dica("Bipe o codigo de barras")
        yield from d.digitar(bipe, barras, por_segundo=30)
        yield from d.tecla(bipe, Qt.Key.Key_Return, 900)
        d.dizer("Quantidade e custo de cada unidade")
        yield from d.digitar(d.campo("Quantidade"), quantidade)
        yield from d.digitar(d.campo("Custo unitario"), custo)
        d.dizer("Clique em Adicionar")
        yield from d.clicar(d.botao("Adicionar"), espera=1000)
    d.dizer("Confira o total e clique em Confirmar entrada")
    yield from d.clicar(d.botao("Confirmar entrada"), espera=1700)
    if d.tem_dialogo():
        yield 1000
        yield from d.fechar_dialogo(aceitar=True)
    yield from fim(d, "O estoque somou e o custo médio foi recalculado. Com o Financeiro, a nota vira conta a pagar.")


def contagem_estoque(d, hub):
    yield from abrir(d, "contagem-estoque")
    yield from modulo(d, "Estoque", "Abra o Estoque")
    yield from aba(d, "Contagem", "Vá em Contagem")
    for barras, contado in (("7891000100013", "22"), ("7891000500051", "8")):
        d.dizer("Bipe o produto e diga quantos você contou")
        bipe = d.por_dica("Bipe o codigo de barras")
        yield from d.digitar(bipe, barras, por_segundo=30)
        yield from d.tecla(bipe, Qt.Key.Key_Return, 900)
        yield from d.digitar(d.campo("Quantidade contada"), contado)
        d.dizer("Clique em Anotar")
        yield from d.clicar(d.botao("Anotar"), espera=1100)
    d.dizer("A folha mostra a diferença de cada produto")
    yield 1900
    d.dizer("Aplicar ajustes corrige o estoque de uma vez")
    yield from d.clicar(d.botao("Aplicar ajustes"), espera=1500)
    if d.tem_dialogo():
        yield 1000
        yield from d.fechar_dialogo(aceitar=True)
    yield from fim(d, "Cada ajuste fica registrado em Movimentações, com data e motivo.")


# ============================================================= VENDAS
def vender_balcao(d, hub):
    yield from abrir(d, "vender-balcao")
    yield from modulo(d, "Vendas", "Abra Vendas: ele começa no Balcão")
    produto = d.por_dica("Bipe o codigo de barras")
    d.dizer("Bipe o código de barras do produto")
    yield from d.digitar(produto, "7891000300037", por_segundo=30)
    yield from d.tecla(produto, Qt.Key.Key_Return, 900)
    yield from d.clicar(d.botao("Adicionar"), espera=1000)
    d.dizer("Ou digite o nome e escolha na lista")
    yield from d.digitar(produto, "Capinha", espera=1000)
    yield from d.clicar_sugestao(0, espera=900)
    yield from d.clicar(d.botao("Adicionar"), espera=1100)
    d.dizer("O cliente é opcional")
    yield from d.digitar(d.por_dica("Consumidor"), "Pedro Henrique", espera=600)
    yield from d.tecla(d.por_dica("Consumidor"), Qt.Key.Key_Tab, 500)
    d.dizer("Clique em Receber (ou aperte F12)")
    yield from d.clicar(d.botao("Receber  (F12)"), espera=1200)
    dialogo = d.dialogo()
    d.dizer("Digite quanto o cliente deu: o troco aparece na hora")
    yield from d.digitar(dialogo.recebido, "150,00", espera=600)
    yield from d.clicar(dialogo.botao_lancar, espera=1500)
    d.dizer("Confirme o recebimento")
    yield from d.clicar(dialogo.botao_receber, espera=2000)
    if d.tem_dialogo():
        yield 1300
        yield from d.fechar_dialogo()
    yield from fim(d, "O estoque baixou sozinho e a venda já está no caixa.")


def caixa(d, hub):
    yield from abrir(d, "caixa")
    yield from modulo(d, "Vendas", "Abra Vendas")
    yield from aba(d, "Caixa", "Vá em Caixa: o dinheiro do dia, conferido", 2000)
    d.dizer("Sangria: dinheiro que sai da gaveta, sempre com motivo")
    yield from d.clicar(d.botao("Sangria"), espera=1000)
    f = d.dialogo()
    yield from d.digitar(f.valor, "100,00")
    yield from d.digitar(f.motivo, "Depósito no banco")
    yield from d.clicar(f.botao_salvar, espera=1500)
    d.dizer("No fim do dia, clique em Fechar caixa")
    yield from d.clicar(d.botao("Fechar caixa"), espera=1100)
    f = d.dialogo()
    d.dizer("Conte o dinheiro da gaveta: o Hub diz se confere")
    yield from d.digitar(f.contado, "300,00", espera=1400)
    yield from d.clicar(f.botao_salvar, espera=1700)
    if d.tem_dialogo():
        yield 1000
        yield from d.fechar_dialogo()
    d.dizer("No dia seguinte, Abrir caixa com o troco inicial")
    yield from d.clicar(d.botao("Abrir caixa"), espera=1000)
    f = d.dialogo()
    yield from d.digitar(f.valor, "150,00")
    yield from d.clicar(f.botao_salvar, espera=1700)
    yield from fim(d, "Cada fechamento fica guardado com o que faltou ou sobrou.")


def devolucao(d, hub):
    yield from abrir(d, "devolucao")
    yield from modulo(d, "Vendas", "Abra Vendas")
    yield from aba(d, "Vendas", "Vá na lista de Vendas", 1500)
    d.dizer("Selecione a venda do cliente")
    yield from d.clicar_linha("Juliana Alves", espera=900)
    d.dizer("Clique em Devolução")
    yield from d.clicar(d.botao("Devolucao"), espera=1100)
    d.dizer("Diga o motivo e o que voltou")
    yield from d.digitar(d.campo("Motivo"), "Cliente desistiu da compra")
    yield from d.clicar(d.botao("Devolver tudo"), espera=900)
    d.dizer("Confirme a devolução")
    yield from d.clicar(d.botao("Confirmar devolucao"), espera=1800)
    if d.tem_dialogo():
        yield 1000
        yield from d.fechar_dialogo()
    yield from fim(d, "O produto voltou ao estoque e o valor saiu do caixa do dia.")


# ========================================================== FINANCEIRO
def lancar_conta(d, hub):
    yield from abrir(d, "lancar-conta")
    yield from modulo(d, "Financeiro", "Abra o Financeiro")
    yield from aba(d, "Lancamentos", "Vá em Lançamentos")
    d.dizer("Clique em Novo lançamento")
    yield from d.clicar(d.botao("Novo lancamento"), espera=1000)
    f = d.dialogo()
    d.dizer("Descrição e valor")
    yield from d.digitar(f.descricao, "Troca de tela Samsung A12")
    yield from d.digitar(f.valor, "250,00")
    d.dizer("Categoria e cliente (com sugestões)")
    yield from d.digitar(f.categoria.lineEdit(), "Serviços")
    yield from d.digitar(f.cliente, "Carlos Lima", espera=500)
    d.dizer("Salve: a conta aparece no vencimento certo")
    yield from d.clicar(f.botao_salvar, espera=1600)
    yield from fim(d, "Despesa ou receita, à vista ou parcelada: tudo entra no fluxo de caixa.")


def receber_conta(d, hub):
    yield from abrir(d, "receber-conta")
    yield from modulo(d, "Financeiro", "Abra o Financeiro")
    yield from aba(d, "Lancamentos", "Vá em Lançamentos")
    d.dizer("Selecione a conta que foi paga")
    yield from d.clicar_linha("Conserto notebook Dell")
    d.dizer("Clique em Receber / pagar")
    yield from d.clicar(d.botao("Receber / pagar"), espera=1200)
    baixa = d.dialogo()
    d.dizer("Confira valor, data e conta: pode ser tudo ou só uma parte")
    yield 1800
    yield from d.clicar(baixa.botao_salvar, espera=1700)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    d.dizer("A conta sai dos pendentes e o saldo atualiza")
    yield 1600
    yield from fim(d, "Venda a prazo no balcão vira conta a receber sozinha.")


def fluxo_caixa(d, hub):
    yield from abrir(d, "fluxo-caixa")
    yield from modulo(d, "Financeiro", "Abra o Financeiro: ele começa no Fluxo", 1600)
    d.dizer("O gráfico mostra o saldo de hoje e dos próximos dias")
    yield from d.apontar(d.rotulo("Saldo projetado"))
    yield 2000
    d.dizer("Dia a dia: o que entra e o que sai em cada data")
    yield from d.apontar(d.rotulo("Dia a dia"))
    yield 1800
    d.dizer("E onde o dinheiro está: banco e gaveta")
    yield from d.apontar(d.rotulo("Onde o dinheiro esta"))
    yield 1600
    yield from aba(d, "Painel", "O Painel mostra o que vence e o que atrasou", 2200)
    yield from fim(d, "Se o saldo for ficar negativo, o Fluxo avisa a data antes.")


# ============================================================== ORDENS
def abrir_ordem(d, hub):
    yield from abrir(d, "abrir-ordem")
    yield from modulo(d, "OS", "Abra a OS: a Bancada mostra cada serviço", 1600)
    d.dizer("Clique em Nova ordem")
    yield from d.clicar(d.botao("Nova ordem"), espera=1000)
    f = d.dialogo()
    d.dizer("Cliente, telefone, defeito e aparelho")
    yield from d.digitar(f.cliente, "Ana Souza", espera=500)
    yield from d.digitar(f.telefone, "(11) 98765-4321", por_segundo=22)
    yield from d.digitar(f.defeito, "Trocar a tela - vidro trincado, touch funcionando")
    yield from d.digitar(f.equipamento, "iPhone 13")
    d.dizer("Adicione a peça como Material (sai do estoque na entrega)")
    yield from d.escolher(f.itens.tipo, "Material")
    yield from d.digitar(f.itens.descricao, "Tela iPhone 13", espera=500)
    yield from d.digitar(f.itens.valor, "590,00")
    yield from d.clicar(d.botao("Adicionar"), espera=700)
    d.dizer("E o serviço")
    yield from d.escolher(f.itens.tipo, "Servico")
    yield from d.digitar(f.itens.descricao, "Mão de obra - troca de tela", espera=300)
    yield from d.digitar(f.itens.valor, "100,00")
    yield from d.clicar(d.botao("Adicionar"), espera=900)
    d.dizer("Salve: a ordem entra na Bancada")
    yield from d.clicar(f.botao_salvar, espera=1800)
    yield from fim(d, "O cliente recebe o orçamento pelo WhatsApp quando você mandar para aprovação.")


def avancar_ordem(d, hub):
    yield from abrir(d, "avancar-ordem")
    yield from modulo(d, "OS", "Abra a OS: cada faixa é uma etapa", 1600)
    d.dizer("Selecione a ordem: o botão já diz o próximo passo")
    yield from d.clicar(d.rotulo("Notebook Dell Inspiron"), espera=1100)
    d.dizer("O cliente autorizou? Registrar aprovação")
    yield from d.clicar(d.botao("Registrar aprovacao"), espera=1100)
    if d.tem_dialogo():
        f = d.dialogo()
        yield from d.digitar(f.observacao, "Autorizou pelo WhatsApp")
        yield from d.clicar(f.botao_salvar, espera=1600)
    d.dizer("Serviço pronto? Marcar como concluída")
    yield from d.clicar(d.rotulo("Samsung A12"), espera=1000)
    yield from d.clicar(d.botao("Marcar como concluida"), espera=1500)
    if d.tem_dialogo():
        yield from d.fechar_dialogo(aceitar=True)
    d.dizer("O cliente veio buscar? Entregar ao cliente")
    yield from d.clicar(d.rotulo("iPhone 11"), espera=1000)
    yield from d.clicar(d.botao("Entregar ao cliente"), espera=1200)
    if d.tem_dialogo():
        f = d.dialogo()
        d.dizer("Quem retirou e como pagou: a garantia começa hoje")
        yield 1600
        yield from d.clicar(f.botao_salvar, espera=1800)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from fim(d, "Cada passo fica no histórico da ordem, com hora e quem fez.")


# ========================================================== ORCAMENTOS
def criar_orcamento(d, hub):
    yield from abrir(d, "criar-orcamento")
    yield from modulo(d, "Orcamentos", "Abra Orçamentos")
    yield from aba(d, "Orcamentos", "Vá na lista de propostas", 1300)
    d.dizer("Clique em Nova proposta")
    yield from d.clicar(d.botao("Nova proposta"), espera=1000)
    f = d.dialogo()
    d.dizer("Para quem é a proposta")
    yield from d.digitar(d.por_dica("Para quem e a proposta"), "Juliana Alves", espera=500)
    d.dizer("Adicione os itens: do estoque, o preço já vem")
    editor = d.por_dica("O que esta sendo cotado").parentWidget()
    yield from d.digitar(editor.descricao, "Carregador USB-C 20W", espera=500)
    yield from d.digitar(editor.quantidade, "2")
    yield from d.digitar(editor.valor, "89,90")
    yield from d.clicar(d.botao("Adicionar"), espera=800)
    yield from d.digitar(editor.descricao, "Película 3D vidro temperado", espera=300)
    yield from d.digitar(editor.valor, "29,90")
    yield from d.clicar(d.botao("Adicionar"), espera=900)
    d.dizer("Condições de pagamento")
    yield from d.digitar(d.por_dica("50% na entrada"), "Pix ou cartão na entrega")
    d.dizer("Salve a proposta")
    yield from d.clicar(f.botao_salvar, espera=1600)
    d.dizer("Documento gera o PDF com a sua marca")
    yield from d.clicar_linha("Juliana Alves")
    yield from d.apontar(d.botao("Documento"))
    yield 1500
    yield from fim(d, "Mande o PDF pelo WhatsApp e acompanhe no Funil.")


def aprovar_orcamento(d, hub):
    yield from abrir(d, "aprovar-orcamento")
    yield from modulo(d, "Orcamentos", "Abra Orçamentos")
    yield from aba(d, "Orcamentos", "Vá na lista de propostas", 1300)
    d.dizer("Selecione a proposta")
    yield from d.clicar_linha("Ana Souza")
    d.dizer("Enviar marca que o cliente recebeu")
    yield from d.clicar(d.botao("Enviar"), espera=1400)
    if d.tem_dialogo():
        yield from d.fechar_dialogo(aceitar=True)
    d.dizer("O cliente aceitou? Clique em Aprovar")
    yield from d.clicar_linha("Pedro Henrique")
    yield from d.clicar(d.botao("Aprovar"), espera=1500)
    if d.tem_dialogo():
        yield from d.fechar_dialogo(aceitar=True)
    d.dizer("Gerar transforma a proposta em venda ou ordem, com os itens")
    yield from d.clicar_linha("Pedro Henrique")
    yield from d.apontar(d.botao("Gerar"))
    yield 1700
    yield from aba(d, "Funil", "O Funil mostra quanto está em negociação", 2000)
    yield from fim(d, "Nada é digitado de novo: os itens vão juntos para a venda ou a ordem.")


# ============================================================ CLIENTES
def cadastrar_cliente(d, hub):
    yield from abrir(d, "cadastrar-cliente")
    yield from modulo(d, "Clientes", "Abra Clientes")
    yield from aba(d, "Clientes", "Vá na lista de clientes", 1300)
    d.dizer("Clique em Novo cliente")
    yield from d.clicar(d.botao("Novo cliente"), espera=1000)
    f = d.dialogo()
    d.dizer("Nome e WhatsApp")
    yield from d.digitar(f.nome, "Rafael Martins")
    yield from d.digitar(f.whatsapp, "11912345678", por_segundo=22)
    d.dizer("Aniversário no formato dia/mês/ano")
    yield from d.digitar(f.nascimento, "14/03/1990", por_segundo=18)
    d.dizer("Digite o CEP: o endereço aparece sozinho")
    yield from d.digitar(f.cep, "09015-000", por_segundo=14, espera=2400)
    yield from d.digitar(f.numero, "250")
    d.dizer("Salve: o cliente aparece em todos os módulos")
    yield from d.clicar(f.botao_salvar, espera=1600)
    yield from fim(d, "No balcão, na proposta e na agenda, é só começar a digitar o nome.")


def ficha_cliente(d, hub):
    yield from abrir(d, "ficha-cliente")
    yield from modulo(d, "Clientes", "Abra Clientes")
    yield from aba(d, "Clientes", "Vá na lista de clientes", 1300)
    d.dizer("Procure pelo nome, telefone ou cidade")
    yield from d.digitar(d.por_dica("Pesquisar por nome"), "Juliana", espera=1500)
    d.dizer("Selecione o cliente")
    yield from d.clicar_linha("Juliana")
    d.dizer("Ver ficha mostra compras, propostas e agenda")
    yield from d.clicar(d.botao("Ver ficha"), espera=2800)
    if d.tem_dialogo():
        yield from d.fechar_dialogo()
    yield from fim(d, "Tudo do cliente num lugar só, para atender sem perguntar de novo.")


# ============================================================== AGENDA
def marcar_compromisso(d, hub):
    yield from abrir(d, "marcar-compromisso")
    yield from modulo(d, "Agenda", "Abra a Agenda: a semana hora a hora", 1700)
    d.dizer("Clique em Novo compromisso")
    yield from d.clicar(d.botao("Novo compromisso"), espera=1000)
    f = d.dialogo()
    d.dizer("O que é, o tipo e o cliente")
    yield from d.digitar(f.titulo, "Instalação de película na loja do cliente")
    yield from d.escolher(f.tipo, "Visita")
    yield from d.digitar(f.cliente, "Juliana Alves", espera=500)
    d.dizer("Dia e hora")
    yield from d.clicar(f.inicio, espera=300)
    amanha = QDateTime(QDate.currentDate().addDays(1), QTime(15, 0))
    QTimer.singleShot(0, lambda: f.inicio.setDateTime(amanha))
    yield 900
    yield from d.digitar(f.local, "Casa do cliente")
    d.dizer("Salve: se bater com outro horário, o Hub avisa")
    yield from d.clicar(f.botao_salvar, espera=1800)
    if d.tem_dialogo():
        yield from d.fechar_dialogo(aceitar=True)
    yield from fim(d, "Os compromissos de hoje também aparecem no Início e no celular.")


class ServidorDeMentira:
    """O servidor da DumTech no video: publica o link e devolve uma reserva quando pedirem."""

    def disponivel(self) -> bool:
        return True

    def chamar(self, funcao: str, params: dict | None = None) -> dict:
        from dumtech.apps.agenda.online import slug_de

        nome = ((params or {}).get("p_config") or {}).get("empresa", {}).get("nome", "")
        return {"ok": True, "slug": slug_de(nome) or "minha-agenda", "ativo": True, "link": True,
                "novas": [], "canceladas": []}


def link_de_agendamento(d, hub):
    yield from abrir(d, "link-de-agendamento")
    yield from modulo(d, "Agenda", "Abra a Agenda", 1500)
    yield from aba(d, "Online", "Na aba Online fica o seu link de agendamento", 1700)
    d.dizer("Clique em Criar meu link: ele já nasce pronto para usar")
    yield from d.clicar(d.botao("Criar meu link"), espera=2400)
    d.dizer("Copie o link e mande no WhatsApp ou ponha na bio do Instagram")
    yield from d.clicar(d.botao("Copiar"), espera=1600)
    yield from d.apontar(d.botao("Enviar no WhatsApp"), QPoint(40, 16))
    yield 1200
    d.dizer("Em Serviços e Horário de atendimento você escolhe o que aparece")
    yield from d.apontar(d.botao("Adicionar serviço"), QPoint(30, 14))
    yield 2200

    # um cliente marca pelo celular: a resposta do servidor chega como chegaria de verdade
    entrada = next(e for e in hub.registry.available() if e.app_id == "agenda")
    sincronia = hub._sincronia_de(entrada)
    amanha = QDate.currentDate().addDays(1).toString("yyyy-MM-dd")
    reserva = {"id": "video-1", "servico": "Atendimento", "inicio": f"{amanha}T14:00", "duracao": 60,
               "nome": "Camila Rocha", "telefone": "11987654321", "observacao": ""}
    d.dizer("Quando o cliente marca pelo celular, o Hub avisa na hora")
    hub._online_respondeu(entrada, sincronia, "dumtech_agenda_sincronizar",
                          {"p_recebidas": [], "p_canceladas": []},
                          {"ok": True, "link": True, "novas": [reserva], "canceladas": []})
    yield 3200
    yield from aba(d, "Agenda", "E o horário já está na grade, com o WhatsApp do cliente", 2600)
    yield from fim(d, "Seus clientes marcam a qualquer hora, sem você parar o que está fazendo.")


ROTEIROS = {
    "primeiros-passos": primeiros_passos,
    "cadastrar-produto": cadastrar_produto,
    "buscar-produto": buscar_produto,
    "entrada-mercadoria": entrada_mercadoria,
    "contagem-estoque": contagem_estoque,
    "vender-balcao": vender_balcao,
    "caixa": caixa,
    "devolucao": devolucao,
    "lancar-conta": lancar_conta,
    "receber-conta": receber_conta,
    "fluxo-caixa": fluxo_caixa,
    "abrir-ordem": abrir_ordem,
    "avancar-ordem": avancar_ordem,
    "criar-orcamento": criar_orcamento,
    "aprovar-orcamento": aprovar_orcamento,
    "cadastrar-cliente": cadastrar_cliente,
    "ficha-cliente": ficha_cliente,
    "marcar-compromisso": marcar_compromisso,
    "link-de-agendamento": link_de_agendamento,
    "busca-ctrl-k": busca_ctrl_k,
    "tema-escuro": tema_escuro,
    "celular": celular,
    "minha-empresa": minha_empresa,
    "backup": backup,
}
assert set(ROTEIROS) == set(CATALOGO), "cada video do catalogo precisa de um roteiro (e vice-versa)"
