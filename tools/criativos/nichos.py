"""O que cada anúncio diz, e para quem.

O ANÚNCIO FALA DE NICHO, NUNCA DE COMBO
    "Combo Start" não é dor de ninguém. Quem procura no Mercado Livre digita
    "sistema para mercadinho", "programa para salão". Por isso o nome do kit
    não aparece em peça nenhuma: aparece o negócio da pessoa.

AS DORES SÃO CONCRETAS DE PROPÓSITO
    "Aumente sua produtividade" não vende. "Descobre que acabou quando a
    cliente já está na cadeira" vende, porque aconteceu na semana passada com
    quem está lendo.

A ORDEM DAS DEZ NÃO É ENFEITE
    Quem estuda anúncio de aplicativo mede isto: quase ninguém passa da
    terceira foto. Então a 1 é a capa que o Mercado Livre exige, a 2 é a dor
    (para a pessoa se reconhecer) e a 3 é a tela explicada com marcadores —
    a prova de que o programa existe e faz o que promete. O resto aprofunda.
"""

from __future__ import annotations

from .base import COR_MODULO, VIOLETA

# Cada nicho: o roteiro das 10 peças, na ordem em que sobem no Mercado Livre.
NICHOS = [
    # ==================================================== mercado / mercadinho
    {
        "slug": "01-mercado",
        "nicho": "Mercado e minimercado",
        "cor": COR_MODULO["ESTOQUE"],
        "capa": "mercearia/vendas-balcao",
        "roteiro": ["capa", "dor", "explicada", "modulo:VENDAS",
                    "modulo:ESTOQUE", "modulo:FINANCEIRO", "celular",
                    "integracao", "promessa", "entrega"],
        "dor": (
            "Você sabe quanto\nvendeu hoje.\nNão sabe quanto sobrou.",
            "O caderno do balcão fecha o dia, mas não conta quantos pacotes "
            "ainda estão na prateleira — nem se o mês deu lucro.",
        ),
        "explicada": (
            "O balcão do seu mercado, por dentro.",
            "mercearia/vendas-balcao",
            [(40, "Bipa o código de barras e o preço entra sozinho"),
             (58, "A venda inteira na tela, item por item"),
             (82, "O total já com desconto, pronto para receber")],
        ),
        "modulos": {
            "VENDAS": ("Bipa, confere e recebe.\nA fila anda.",
                       "Código de barras, desconto na hora e o troco calculado. "
                       "Sem procurar preço em papel colado na gôndola.",
                       "mercearia/vendas-balcao"),
            "ESTOQUE": ("Acabou antes de acabar\nna prateleira.",
                        "Cada venda baixa o saldo sozinha, e o que está no fim "
                        "aparece marcado — dá para comprar antes de perder a venda.",
                        "mercearia/estoque-produtos"),
            "FINANCEIRO": ("O mês fecha sozinho,\ncom o que entrou e saiu.",
                           "Venda do balcão cai no caixa. Conta a pagar avisa "
                           "antes de vencer. No fim do mês o número já está pronto.",
                           "mercearia/financeiro-painel"),
        },
        "celular": (
            "O mercado no seu bolso,\nmesmo fora da loja.",
            "Leia um QR Code uma vez e o resumo do dia abre no seu celular. "
            "Não precisa instalar nada.",
            ["Quanto entrou no caixa hoje",
             "O que está acabando na prateleira",
             "As contas que vencem esta semana"],
            "mercearia/celular",
        ),
        "integracao": (
            "Uma venda no balcão.\nTrês coisas acontecem.",
            [("VENDAS", "A cliente paga e leva."),
             ("ESTOQUE", "O saldo do produto baixa na hora, sem ninguém anotar."),
             ("FINANCEIRO", "O valor entra no caixa do dia.")],
            "Ninguém digita a mesma venda três vezes.",
        ),
    },

    # ======================================================= salão de beleza
    {
        "slug": "02-salao",
        "nicho": "Salão, barbearia e estética",
        "cor": COR_MODULO["AGENDA"],
        "capa": "salao/agenda-grade",
        "roteiro": ["capa", "dor", "explicada", "modulo:AGENDA",
                    "modulo:CLIENTES", "modulo:ORCAMENTOS", "celular",
                    "integracao", "promessa", "entrega"],
        "dor": (
            "A agenda do salão\nnão pode morar\nno WhatsApp.",
            "Conversa some, horário se perde e duas clientes marcam as quatro "
            "da tarde. Quem paga o buraco na agenda é você.",
        ),
        "explicada": (
            "A semana do salão, numa tela só.",
            "salao/agenda-grade",
            [(52, "Cada cliente no horário dela, com a duração certa"),
             (70, "Serviço longo ocupa o espaço que realmente leva"),
             (88, "A cor diz o tipo: atendimento, entrega, bloqueio")],
        ),
        "modulos": {
            "AGENDA": ("O dia inteiro numa tela,\nhorário por horário.",
                       "Quem vem, com quem, quanto tempo leva. Encaixe novo sem "
                       "rolar conversa de três dias atrás para conferir.",
                       "salao/agenda-grade"),
            "CLIENTES": ("A ficha lembra o que\nvocê não tem que lembrar.",
                         "A cor da última química, a alergia, o telefone certo. "
                         "A cliente senta e você já sabe o que fazer.",
                         "salao/clientes-painel"),
            "ORCAMENTOS": ("Pacote orçado, aprovado\ne cobrado sem discussão.",
                           "Noiva, formatura, progressiva com corte: o valor sai "
                           "por escrito e ninguém discute o preço depois.",
                           "salao/orcamentos-funil"),
        },
        "celular": (
            "O salão no seu bolso,\nentre uma cliente e outra.",
            "Leia um QR Code uma vez e a agenda do dia abre no seu celular. "
            "Não precisa instalar nada.",
            ["Quem vem hoje, e a que horas",
             "Os pacotes esperando resposta",
             "Quanto foi aprovado no mês"],
            "salao/celular",
        ),
        "integracao": (
            "A cliente marca.\nO resto já está pronto.",
            [("AGENDA", "O horário entra no dia, sem conflito com outro."),
             ("CLIENTES", "A ficha abre com o histórico dela junto."),
             ("ORCAMENTOS", "O pacote combinado vira valor fechado.")],
            "Um cadastro só, do primeiro contato até a última visita.",
        ),
    },

    # ====================================================== pequena empresa
    {
        "slug": "03-pequena-empresa",
        "nicho": "Loja e pequena empresa",
        "cor": COR_MODULO["CLIENTES"],
        "capa": "empresa/vendas-painel",
        "roteiro": ["capa", "dor", "explicada", "modulo:VENDAS",
                    "modulo:ESTOQUE", "modulo:FINANCEIRO", "modulo:CLIENTES",
                    "celular", "o-que-vem", "promessa"],
        "dor": (
            "A planilha só está certa\naté alguém esquecer\nde abrir.",
            "Cliente, venda, estoque e conta a receber em quatro arquivos "
            "diferentes — e nenhum deles conversa com o outro.",
        ),
        "explicada": (
            "O dia da loja, num painel só.",
            "empresa/vendas-painel",
            [(38, "Quanto a loja vendeu hoje, sem fechar caixa"),
             (60, "O que saiu mais, e o que encalhou"),
             (82, "As últimas vendas, com cliente e valor")],
        ),
        "modulos": {
            "VENDAS": ("Vende no balcão e\nno fim do mês.",
                       "Venda à vista, a prazo ou em Pix, com o histórico de "
                       "cada cliente do lado.",
                       "empresa/vendas-balcao"),
            "ESTOQUE": ("Saldo certo sem\ncontar prateleira.",
                        "A venda baixa, a nota de entrada soma e a contagem "
                        "acerta o que ficou diferente.",
                        "empresa/estoque-produtos"),
            "FINANCEIRO": ("Quem te deve e quanto\nsobra no fim do mês.",
                           "Conta a receber com data, conta a pagar avisando "
                           "antes, e o fluxo do mês numa tela.",
                           "empresa/financeiro-fluxo"),
            "CLIENTES": ("Um cadastro só, que o\nresto do sistema usa.",
                         "O nome que você digita na venda é o mesmo da proposta "
                         "e o mesmo da cobrança. Digitado uma vez.",
                         "empresa/clientes-lista"),
        },
        "celular": (
            "A loja no seu bolso,\nmesmo longe dela.",
            "Leia um QR Code uma vez e os números do dia abrem no seu celular. "
            "Não precisa instalar nada.",
            ["Quanto a loja vendeu hoje",
             "Quem está devendo, e desde quando",
             "O que está acabando no estoque"],
            "empresa/celular",
        ),
        "o_que_vem": (
            "Quatro programas, uma chave só.",
            [("CLIENTES", "Cadastro único, histórico e contato"),
             ("VENDAS", "Balcão, prazo, Pix e histórico do cliente"),
             ("ESTOQUE", "Saldo, entrada, contagem e custo"),
             ("FINANCEIRO", "A pagar, a receber, caixa e fluxo do mês")],
            "Paga uma vez. Instala em quantos computadores quiser.",
        ),
    },

    # ================================================= negócio que cresceu
    {
        "slug": "04-negocio-que-cresceu",
        "nicho": "Para quem já passou do caderno",
        "cor": VIOLETA,
        "capa": "empresa/financeiro-painel",
        "roteiro": ["capa", "dor", "explicada", "modulo:FINANCEIRO",
                    "modulo:ORCAMENTOS", "modulo:ESTOQUE", "celular",
                    "o-que-vem", "integracao", "promessa"],
        "dor": (
            "Seu negócio cresceu.\nSeu controle\ncontinua igual.",
            "Funcionário novo que não acha nada, informação na cabeça de uma "
            "pessoa só e decisão tomada no achismo.",
        ),
        "explicada": (
            "O número que decide, pronto todo dia.",
            "empresa/financeiro-painel",
            [(38, "Quanto entrou e quanto saiu no mês"),
             (55, "O dia em que o dinheiro acaba, avisado antes"),
             (84, "Onde o dinheiro está, conta por conta")],
        ),
        "modulos": {
            "FINANCEIRO": ("O número que decide,\npronto todo dia.",
                           "Fluxo do mês, conta a pagar antes de vencer e a "
                           "receber com nome e data.",
                           "empresa/financeiro-contas"),
            "ORCAMENTOS": ("Proposta que vira venda\nsem digitar de novo.",
                           "O sim do cliente empurra os itens para a venda ou "
                           "para a ordem de serviço, já dentro.",
                           "empresa/orcamentos-funil"),
            "ESTOQUE": ("Saldo confiável para\nquem já tem giro.",
                        "Entrada por nota, contagem que acerta a diferença e "
                        "aviso do que está acabando.",
                        "empresa/estoque-movimentacoes"),
        },
        "celular": (
            "A empresa no seu bolso,\nsem pedir número a ninguém.",
            "Leia um QR Code uma vez e o resumo de todos os setores abre no "
            "seu celular. Não precisa instalar nada.",
            ["Caixa, vendas e contas do dia",
             "As propostas esperando resposta",
             "O que a equipe tem marcado hoje"],
            "empresa/celular",
        ),
        "o_que_vem": (
            "Seis programas, uma chave só.",
            [("CLIENTES", "Cadastro único do sistema inteiro"),
             ("VENDAS", "Balcão, caixa, prazo e Pix"),
             ("ESTOQUE", "Saldo, nota de entrada, contagem e custo"),
             ("FINANCEIRO", "A pagar, a receber, caixa e fluxo"),
             ("ORCAMENTOS", "Proposta, aprovação e virada em venda"),
             ("AGENDA", "Compromisso, entrega e visita da equipe")],
            "Sem mensalidade. Sem limite de computador.",
        ),
        "integracao": (
            "A proposta aprovada\nanda sozinha.",
            [("ORCAMENTOS", "O cliente aprova o orçamento."),
             ("VENDAS", "Os itens viram venda, já lançados."),
             ("ESTOQUE", "O que saiu baixa do saldo."),
             ("FINANCEIRO", "O valor entra como conta a receber.")],
            "Ninguém redigita nada entre um passo e outro.",
        ),
    },
]

# Estas duas peças falam igual em todo anúncio: a objeção é a mesma para o
# dono do mercadinho e para quem já tem funcionário.
PROMESSA = (
    "Paga uma vez.\nO programa é seu.",
    [("Sem mensalidade", "Não é assinatura. Comprou, é seu, para sempre."),
     ("Funciona sem internet", "A internet só serve para ativar. Depois, roda sozinho."),
     ("Sem limite de computador", "Instale no caixa, no escritório e na sua casa."),
     ("Atualização incluída", "Versão nova chega pelo próprio programa.")],
)

ENTREGA = (
    "Comprou agora,\nusa hoje.",
    ["A chave de ativação chega no seu e-mail, em minutos.",
     "Você baixa o instalador e abre como qualquer programa.",
     "Digita a chave uma vez e já começa a trabalhar."],
    "Windows 10 ou 11. Sem instalar banco de dados nem contratar técnico.",
)
