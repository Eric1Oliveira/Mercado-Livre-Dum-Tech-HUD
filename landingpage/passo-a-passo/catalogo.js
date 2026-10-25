// Gerado por tools/videos/publicar_passo.py a partir dos roteiros - nao edite a mao.
// Cada video: titulo, perguntas que as pessoas fazem, palavras parecidas e os passos com o segundo de cada um.
export const VIDEOS = [
 {
  "id": "primeiros-passos",
  "titulo": "Conhecendo o DumTech Hub",
  "modulo": "hub",
  "grupo": "Primeiros passos",
  "resumo": "Onde fica cada coisa: o Início, as abas dos módulos e a busca.",
  "perguntas": [
   "como funciona o programa",
   "por onde começo",
   "como usar o hub",
   "primeiro acesso"
  ],
  "palavras": [
   "inicio",
   "começar",
   "comecar",
   "tela inicial",
   "abas",
   "modulos",
   "tour",
   "visao geral"
  ],
  "duracao": 22.0,
  "passos": [
   {
    "t": 2.8,
    "texto": "O Início mostra o dia inteiro da sua empresa"
   },
   {
    "t": 6.9,
    "texto": "Cada módulo é uma aba aqui em cima"
   },
   {
    "t": 9.3,
    "texto": "Clique na aba para trocar de módulo"
   },
   {
    "t": 11.6,
    "texto": "A aba Início volta para o resumo do dia"
   },
   {
    "t": 13.9,
    "texto": "Ctrl + K abre a busca de qualquer lugar"
   }
  ],
  "kb": 440
 },
 {
  "id": "cadastrar-produto",
  "titulo": "Como cadastrar um produto",
  "modulo": "estoque",
  "grupo": "Estoque",
  "resumo": "Do botão Novo produto até ele estar pronto para vender no balcão.",
  "perguntas": [
   "como cadastro produtos",
   "como cadastrar produto",
   "como adicionar um produto",
   "como incluir mercadoria",
   "como criar item no estoque",
   "onde cadastro os produtos"
  ],
  "palavras": [
   "produto",
   "produtos",
   "mercadoria",
   "item",
   "cadastro",
   "novo produto",
   "codigo de barras",
   "preço",
   "preco de venda",
   "estoque minimo"
  ],
  "duracao": 34.0,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra o Estoque pela aba no topo"
   },
   {
    "t": 4.8,
    "texto": "Vá em Produtos"
   },
   {
    "t": 6.9,
    "texto": "Clique em Novo produto"
   },
   {
    "t": 8.7,
    "texto": "Código interno e código de barras (dá para bipar)"
   },
   {
    "t": 12.5,
    "texto": "Nome, categoria e fornecedor"
   },
   {
    "t": 19.3,
    "texto": "Quantidade, estoque mínimo, custo e preço de venda"
   },
   {
    "t": 25.2,
    "texto": "Clique em Salvar"
   },
   {
    "t": 27.2,
    "texto": "Pronto: o produto já aparece na lista e no balcão"
   }
  ],
  "kb": 538
 },
 {
  "id": "buscar-produto",
  "titulo": "Como encontrar um produto",
  "modulo": "estoque",
  "grupo": "Estoque",
  "resumo": "Ache qualquer produto pelo nome, pelo código ou bipando o código de barras.",
  "perguntas": [
   "como procurar produto",
   "como achar um produto",
   "como pesquisar no estoque",
   "onde vejo meus produtos"
  ],
  "palavras": [
   "busca",
   "pesquisa",
   "procurar",
   "codigo",
   "codigo de barras",
   "bipar",
   "leitor",
   "lista de produtos"
  ],
  "duracao": 22.4,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra o Estoque"
   },
   {
    "t": 4.8,
    "texto": "Vá em Produtos"
   },
   {
    "t": 6.9,
    "texto": "Digite parte do nome"
   },
   {
    "t": 9.9,
    "texto": "Ou o código interno"
   },
   {
    "t": 12.9,
    "texto": "Ou bipe o código de barras com o leitor"
   },
   {
    "t": 16.1,
    "texto": "Duplo clique abre a ficha do produto"
   }
  ],
  "kb": 449
 },
 {
  "id": "entrada-mercadoria",
  "titulo": "Como dar entrada de mercadoria",
  "modulo": "estoque",
  "grupo": "Estoque",
  "resumo": "Lance a nota do fornecedor: o estoque soma e o custo médio se atualiza.",
  "perguntas": [
   "como dar entrada no estoque",
   "como lançar nota do fornecedor",
   "chegou mercadoria o que faço",
   "como repor estoque",
   "como registrar compra"
  ],
  "palavras": [
   "entrada",
   "nota",
   "nota fiscal",
   "fornecedor",
   "compra",
   "reposição",
   "reposicao",
   "custo",
   "custo medio"
  ],
  "duracao": 31.0,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra o Estoque"
   },
   {
    "t": 4.8,
    "texto": "Vá em Entradas"
   },
   {
    "t": 6.8,
    "texto": "Diga quem vendeu e o número da nota"
   },
   {
    "t": 11.0,
    "texto": "Bipe ou digite o produto e aperte Enter"
   },
   {
    "t": 13.8,
    "texto": "Quantidade e custo de cada unidade"
   },
   {
    "t": 16.7,
    "texto": "Clique em Adicionar"
   },
   {
    "t": 18.2,
    "texto": "Bipe ou digite o produto e aperte Enter"
   },
   {
    "t": 21.2,
    "texto": "Quantidade e custo de cada unidade"
   },
   {
    "t": 24.2,
    "texto": "Clique em Adicionar"
   },
   {
    "t": 25.7,
    "texto": "Confira o total e clique em Confirmar entrada"
   }
  ],
  "kb": 444
 },
 {
  "id": "contagem-estoque",
  "titulo": "Como fazer a contagem do estoque",
  "modulo": "estoque",
  "grupo": "Estoque",
  "resumo": "Conte o que tem na prateleira e corrija a diferença de uma vez.",
  "perguntas": [
   "como fazer inventário",
   "como ajustar o estoque",
   "o estoque está errado",
   "como conferir o estoque"
  ],
  "palavras": [
   "contagem",
   "inventario",
   "inventário",
   "ajuste",
   "conferencia",
   "balanço",
   "balanco",
   "diferença"
  ],
  "duracao": 27.8,
  "passos": [
   {
    "t": 2.9,
    "texto": "Abra o Estoque"
   },
   {
    "t": 4.9,
    "texto": "Vá em Contagem"
   },
   {
    "t": 6.9,
    "texto": "Bipe o produto e diga quantos você contou"
   },
   {
    "t": 11.2,
    "texto": "Clique em Anotar"
   },
   {
    "t": 12.8,
    "texto": "Bipe o produto e diga quantos você contou"
   },
   {
    "t": 17.3,
    "texto": "Clique em Anotar"
   },
   {
    "t": 18.9,
    "texto": "A folha mostra a diferença de cada produto"
   },
   {
    "t": 20.8,
    "texto": "Aplicar ajustes corrige o estoque de uma vez"
   }
  ],
  "kb": 403
 },
 {
  "id": "vender-balcao",
  "titulo": "Como fazer uma venda no balcão",
  "modulo": "vendas",
  "grupo": "Vendas",
  "resumo": "Bipe ou digite o produto, escolha o cliente e receba com troco calculado.",
  "perguntas": [
   "como vender",
   "como fazer uma venda",
   "como usar o pdv",
   "como passar uma venda",
   "como cobrar o cliente"
  ],
  "palavras": [
   "venda",
   "vender",
   "balcao",
   "balcão",
   "pdv",
   "caixa",
   "receber",
   "troco",
   "pix",
   "cartão",
   "cartao",
   "dinheiro",
   "f12",
   "bipar"
  ],
  "duracao": 30.3,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra Vendas: ele começa no Balcão"
   },
   {
    "t": 4.8,
    "texto": "Bipe o código de barras do produto"
   },
   {
    "t": 9.6,
    "texto": "Ou digite o nome e escolha na lista"
   },
   {
    "t": 15.4,
    "texto": "O cliente é opcional"
   },
   {
    "t": 18.5,
    "texto": "Clique em Receber (ou aperte F12)"
   },
   {
    "t": 20.6,
    "texto": "Digite quanto o cliente deu: o troco aparece na hora"
   },
   {
    "t": 24.6,
    "texto": "Confirme o recebimento"
   }
  ],
  "kb": 412
 },
 {
  "id": "caixa",
  "titulo": "Como abrir, fazer sangria e fechar o caixa",
  "modulo": "vendas",
  "grupo": "Vendas",
  "resumo": "Sangria com motivo, fechamento conferido com o que tem na gaveta e abertura do dia.",
  "perguntas": [
   "como fechar o caixa",
   "como abrir o caixa",
   "como fazer sangria",
   "como conferir o caixa",
   "como tirar dinheiro do caixa"
  ],
  "palavras": [
   "caixa",
   "sangria",
   "suprimento",
   "fechamento",
   "abertura",
   "gaveta",
   "conferir",
   "troco"
  ],
  "duracao": 32.1,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra Vendas"
   },
   {
    "t": 4.8,
    "texto": "Vá em Caixa: o dinheiro do dia, conferido"
   },
   {
    "t": 7.5,
    "texto": "Sangria: dinheiro que sai da gaveta, sempre com motivo"
   },
   {
    "t": 14.8,
    "texto": "No fim do dia, clique em Fechar caixa"
   },
   {
    "t": 16.6,
    "texto": "Conte o dinheiro da gaveta: o Hub diz se confere"
   },
   {
    "t": 23.3,
    "texto": "No dia seguinte, Abrir caixa com o troco inicial"
   }
  ],
  "kb": 536
 },
 {
  "id": "devolucao",
  "titulo": "Como fazer uma devolução",
  "modulo": "vendas",
  "grupo": "Vendas",
  "resumo": "O cliente devolveu? Escolha a venda, diga o motivo e o produto volta ao estoque.",
  "perguntas": [
   "como fazer devolução",
   "como devolver uma venda",
   "como estornar uma venda",
   "cliente quer devolver"
  ],
  "palavras": [
   "devolucao",
   "devolução",
   "troca",
   "estorno",
   "cancelar venda",
   "reembolso"
  ],
  "duracao": 20.1,
  "passos": [
   {
    "t": 2.9,
    "texto": "Abra Vendas"
   },
   {
    "t": 4.9,
    "texto": "Vá na lista de Vendas"
   },
   {
    "t": 7.1,
    "texto": "Selecione a venda do cliente"
   },
   {
    "t": 8.6,
    "texto": "Clique em Devolução"
   },
   {
    "t": 10.4,
    "texto": "Diga o motivo e o que voltou"
   },
   {
    "t": 14.6,
    "texto": "Confirme a devolução"
   }
  ],
  "kb": 369
 },
 {
  "id": "lancar-conta",
  "titulo": "Como lançar uma conta a pagar ou a receber",
  "modulo": "financeiro",
  "grupo": "Financeiro",
  "resumo": "Despesa, boleto ou conserto que o cliente paga depois: lance uma vez e acompanhe.",
  "perguntas": [
   "como lançar uma conta",
   "como cadastrar despesa",
   "como registrar um boleto",
   "conta a pagar",
   "conta a receber"
  ],
  "palavras": [
   "lancamento",
   "lançamento",
   "conta",
   "despesa",
   "receita",
   "boleto",
   "pagar",
   "receber",
   "vencimento",
   "parcelado",
   "fiado"
  ],
  "duracao": 22.1,
  "passos": [
   {
    "t": 2.9,
    "texto": "Abra o Financeiro"
   },
   {
    "t": 4.9,
    "texto": "Vá em Lançamentos"
   },
   {
    "t": 6.9,
    "texto": "Clique em Novo lançamento"
   },
   {
    "t": 8.7,
    "texto": "Descrição e valor"
   },
   {
    "t": 13.2,
    "texto": "Categoria e cliente (com sugestões)"
   },
   {
    "t": 16.8,
    "texto": "Salve: a conta aparece no vencimento certo"
   }
  ],
  "kb": 417
 },
 {
  "id": "receber-conta",
  "titulo": "Como dar baixa numa conta",
  "modulo": "financeiro",
  "grupo": "Financeiro",
  "resumo": "O cliente pagou ou você pagou um boleto: registre a baixa, total ou parcial.",
  "perguntas": [
   "como dar baixa",
   "como receber uma conta",
   "como marcar como pago",
   "cliente pagou o que faço"
  ],
  "palavras": [
   "baixa",
   "quitar",
   "pago",
   "recebido",
   "receber",
   "pagar",
   "parcial"
  ],
  "duracao": 19.0,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra o Financeiro"
   },
   {
    "t": 4.8,
    "texto": "Vá em Lançamentos"
   },
   {
    "t": 6.8,
    "texto": "Selecione a conta que foi paga"
   },
   {
    "t": 8.1,
    "texto": "Clique em Receber / pagar"
   },
   {
    "t": 10.0,
    "texto": "Confira valor, data e conta: pode ser tudo ou só uma parte"
   },
   {
    "t": 14.3,
    "texto": "A conta sai dos pendentes e o saldo atualiza"
   }
  ],
  "kb": 398
 },
 {
  "id": "fluxo-caixa",
  "titulo": "Como ver o fluxo de caixa",
  "modulo": "financeiro",
  "grupo": "Financeiro",
  "resumo": "O saldo de hoje e dos próximos dias, e quando o dinheiro pode faltar.",
  "perguntas": [
   "como ver o fluxo de caixa",
   "quanto dinheiro eu tenho",
   "como ver o saldo",
   "previsão de caixa"
  ],
  "palavras": [
   "fluxo",
   "saldo",
   "projeção",
   "projecao",
   "contas",
   "banco",
   "previsao",
   "relatorio financeiro"
  ],
  "duracao": 19.0,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra o Financeiro: ele começa no Fluxo"
   },
   {
    "t": 5.1,
    "texto": "O gráfico mostra o saldo de hoje e dos próximos dias"
   },
   {
    "t": 7.9,
    "texto": "Dia a dia: o que entra e o que sai em cada data"
   },
   {
    "t": 10.5,
    "texto": "E onde o dinheiro está: banco e gaveta"
   },
   {
    "t": 12.9,
    "texto": "O Painel mostra o que vence e o que atrasou"
   }
  ],
  "kb": 320
 },
 {
  "id": "abrir-ordem",
  "titulo": "Como abrir uma ordem de serviço",
  "modulo": "ordens",
  "grupo": "Ordem de Serviço",
  "resumo": "Chegou um aparelho: cliente, defeito, peças e serviços, tudo numa ordem.",
  "perguntas": [
   "como abrir ordem de serviço",
   "como fazer uma os",
   "como registrar um conserto",
   "chegou um aparelho"
  ],
  "palavras": [
   "ordem",
   "os",
   "ordem de servico",
   "conserto",
   "assistencia",
   "assistência",
   "oficina",
   "defeito",
   "equipamento",
   "peça",
   "serviço"
  ],
  "duracao": 37.2,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra Ordens: a Bancada mostra cada serviço"
   },
   {
    "t": 5.1,
    "texto": "Clique em Nova ordem"
   },
   {
    "t": 6.7,
    "texto": "Cliente, telefone, defeito e aparelho"
   },
   {
    "t": 16.8,
    "texto": "Adicione a peça como Material (sai do estoque na entrega)"
   },
   {
    "t": 23.7,
    "texto": "E o serviço"
   },
   {
    "t": 31.6,
    "texto": "Salve: a ordem entra na Bancada"
   }
  ],
  "kb": 463
 },
 {
  "id": "avancar-ordem",
  "titulo": "Como levar a ordem até a entrega",
  "modulo": "ordens",
  "grupo": "Ordem de Serviço",
  "resumo": "Aprovação do cliente, serviço concluído e entrega com pagamento, etapa por etapa.",
  "perguntas": [
   "como entregar o aparelho",
   "como aprovar uma ordem",
   "como concluir uma os",
   "como mudar a etapa"
  ],
  "palavras": [
   "etapa",
   "aprovação",
   "aprovacao",
   "concluir",
   "entregar",
   "entrega",
   "bancada",
   "garantia",
   "status"
  ],
  "duracao": 28.0,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra Ordens: cada faixa é uma etapa"
   },
   {
    "t": 5.1,
    "texto": "Selecione a ordem: o botão já diz o próximo passo"
   },
   {
    "t": 6.8,
    "texto": "O cliente autorizou? Registrar aprovação"
   },
   {
    "t": 13.8,
    "texto": "Serviço pronto? Marcar como concluída"
   },
   {
    "t": 17.5,
    "texto": "O cliente veio buscar? Entregar ao cliente"
   },
   {
    "t": 20.9,
    "texto": "Quem retirou e como pagou: a garantia começa hoje"
   }
  ],
  "kb": 433
 },
 {
  "id": "criar-orcamento",
  "titulo": "Como fazer um orçamento",
  "modulo": "orcamentos",
  "grupo": "Orçamentos",
  "resumo": "Monte a proposta com os itens do estoque e gere o PDF com a sua marca.",
  "perguntas": [
   "como fazer um orçamento",
   "como criar uma proposta",
   "como mandar orçamento para o cliente"
  ],
  "palavras": [
   "orcamento",
   "orçamento",
   "proposta",
   "cotação",
   "cotacao",
   "pdf",
   "itens"
  ],
  "duracao": 35.5,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra Orçamentos"
   },
   {
    "t": 4.8,
    "texto": "Vá na lista de propostas"
   },
   {
    "t": 6.7,
    "texto": "Clique em Nova proposta"
   },
   {
    "t": 8.6,
    "texto": "Para quem é a proposta"
   },
   {
    "t": 10.9,
    "texto": "Adicione os itens: do estoque, o preço já vem"
   },
   {
    "t": 23.6,
    "texto": "Condições de pagamento"
   },
   {
    "t": 26.4,
    "texto": "Salve a proposta"
   },
   {
    "t": 28.6,
    "texto": "Documento gera o PDF com a sua marca"
   }
  ],
  "kb": 448
 },
 {
  "id": "aprovar-orcamento",
  "titulo": "Como enviar e aprovar uma proposta",
  "modulo": "orcamentos",
  "grupo": "Orçamentos",
  "resumo": "Marque que enviou, registre a aprovação e transforme em venda ou ordem.",
  "perguntas": [
   "o cliente aprovou o orçamento",
   "como aprovar proposta",
   "como transformar orçamento em venda"
  ],
  "palavras": [
   "aprovar",
   "enviar",
   "funil",
   "gerar venda",
   "gerar ordem",
   "recusar",
   "proposta aceita"
  ],
  "duracao": 23.2,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra Orçamentos"
   },
   {
    "t": 4.8,
    "texto": "Vá na lista de propostas"
   },
   {
    "t": 6.7,
    "texto": "Selecione a proposta"
   },
   {
    "t": 8.0,
    "texto": "Enviar marca que o cliente recebeu"
   },
   {
    "t": 10.1,
    "texto": "O cliente aceitou? Clique em Aprovar"
   },
   {
    "t": 13.6,
    "texto": "Gerar transforma a proposta em venda ou ordem, com os itens"
   },
   {
    "t": 17.2,
    "texto": "O Funil mostra quanto está em negociação"
   }
  ],
  "kb": 401
 },
 {
  "id": "cadastrar-cliente",
  "titulo": "Como cadastrar um cliente",
  "modulo": "clientes",
  "grupo": "Clientes",
  "resumo": "Nome, WhatsApp e aniversário; o CEP preenche o endereço sozinho.",
  "perguntas": [
   "como cadastro clientes",
   "como cadastrar cliente",
   "como adicionar um cliente",
   "onde ficam meus clientes"
  ],
  "palavras": [
   "cliente",
   "clientes",
   "cadastro",
   "contato",
   "whatsapp",
   "cep",
   "endereço",
   "aniversario",
   "freguês"
  ],
  "duracao": 24.9,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra Clientes"
   },
   {
    "t": 4.9,
    "texto": "Vá na lista de clientes"
   },
   {
    "t": 6.6,
    "texto": "Clique em Novo cliente"
   },
   {
    "t": 8.5,
    "texto": "Nome e WhatsApp"
   },
   {
    "t": 12.5,
    "texto": "Aniversário no formato dia/mês/ano"
   },
   {
    "t": 14.2,
    "texto": "Digite o CEP: o endereço aparece sozinho"
   },
   {
    "t": 19.6,
    "texto": "Salve: o cliente aparece em todos os módulos"
   }
  ],
  "kb": 439
 },
 {
  "id": "ficha-cliente",
  "titulo": "Como ver o histórico de um cliente",
  "modulo": "clientes",
  "grupo": "Clientes",
  "resumo": "Tudo o que ele comprou, orçou e agendou, numa ficha só.",
  "perguntas": [
   "como ver o que o cliente comprou",
   "histórico do cliente",
   "como abrir a ficha do cliente"
  ],
  "palavras": [
   "ficha",
   "historico",
   "histórico",
   "compras do cliente",
   "cliente"
  ],
  "duracao": 17.9,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra Clientes"
   },
   {
    "t": 4.9,
    "texto": "Vá na lista de clientes"
   },
   {
    "t": 6.7,
    "texto": "Procure pelo nome, telefone ou cidade"
   },
   {
    "t": 9.4,
    "texto": "Selecione o cliente"
   },
   {
    "t": 10.6,
    "texto": "Ver ficha mostra compras, propostas e agenda"
   }
  ],
  "kb": 336
 },
 {
  "id": "marcar-compromisso",
  "titulo": "Como marcar um compromisso na agenda",
  "modulo": "agenda",
  "grupo": "Agenda",
  "resumo": "Atendimento, visita ou entrega: dia, hora e cliente, sem bater horário.",
  "perguntas": [
   "como marcar horário",
   "como agendar",
   "como usar a agenda",
   "como marcar uma visita"
  ],
  "palavras": [
   "agenda",
   "agendar",
   "compromisso",
   "horario",
   "horário",
   "visita",
   "atendimento",
   "marcar"
  ],
  "duracao": 24.2,
  "passos": [
   {
    "t": 2.8,
    "texto": "Abra a Agenda: a semana hora a hora"
   },
   {
    "t": 5.3,
    "texto": "Clique em Novo compromisso"
   },
   {
    "t": 7.1,
    "texto": "O que é, o tipo e o cliente"
   },
   {
    "t": 14.9,
    "texto": "Dia e hora"
   },
   {
    "t": 18.7,
    "texto": "Salve: se bater com outro horário, o Hub avisa"
   }
  ],
  "kb": 360
 },
 {
  "id": "busca-ctrl-k",
  "titulo": "Como achar qualquer tela com Ctrl+K",
  "modulo": "hub",
  "grupo": "Primeiros passos",
  "resumo": "A busca do Hub abre telas e ações pelo nome, de qualquer lugar.",
  "perguntas": [
   "como pesquisar no programa",
   "atalho de busca",
   "como achar uma tela"
  ],
  "palavras": [
   "ctrl k",
   "atalho",
   "busca",
   "pesquisa",
   "menu"
  ],
  "duracao": 12.2,
  "passos": [
   {
    "t": 2.8,
    "texto": "Aperte Ctrl + K (ou clique em Buscar no Hub)"
   },
   {
    "t": 4.4,
    "texto": "Digite o que procura: uma tela ou uma ação"
   },
   {
    "t": 7.3,
    "texto": "Enter abre direto o que você escolheu"
   }
  ],
  "kb": 231
 },
 {
  "id": "tema-escuro",
  "titulo": "Como usar o tema escuro",
  "modulo": "hub",
  "grupo": "Primeiros passos",
  "resumo": "Troque entre claro e escuro com um clique.",
  "perguntas": [
   "como mudar a cor",
   "como deixar escuro",
   "modo noturno"
  ],
  "palavras": [
   "tema",
   "escuro",
   "claro",
   "cor",
   "noturno",
   "dark"
  ],
  "duracao": 12.9,
  "passos": [
   {
    "t": 2.8,
    "texto": "Clique no botão de tema, no alto à direita"
   },
   {
    "t": 6.0,
    "texto": "Pronto: tema escuro, para quem trabalha à noite"
   },
   {
    "t": 7.6,
    "texto": "Clique de novo para voltar ao claro"
   }
  ],
  "kb": 254
 },
 {
  "id": "celular",
  "titulo": "Como ver o seu negócio no celular",
  "modulo": "hub",
  "grupo": "Primeiros passos",
  "resumo": "Leia o QR Code e acompanhe vendas e agenda pelo celular.",
  "perguntas": [
   "como usar no celular",
   "como ver no celular",
   "tem aplicativo"
  ],
  "palavras": [
   "celular",
   "qr code",
   "qrcode",
   "smartphone",
   "aplicativo",
   "app",
   "telefone"
  ],
  "duracao": 13.7,
  "passos": [
   {
    "t": 2.9,
    "texto": "Abra o menu da empresa, no canto de cima"
   },
   {
    "t": 4.6,
    "texto": "Escolha Ver no celular"
   },
   {
    "t": 7.2,
    "texto": "Aponte a câmera do celular para o QR Code"
   }
  ],
  "kb": 282
 },
 {
  "id": "minha-empresa",
  "titulo": "Como colocar os dados da sua empresa",
  "modulo": "hub",
  "grupo": "Configurações",
  "resumo": "Nome, contato e endereço que saem nos comprovantes e propostas.",
  "perguntas": [
   "como colocar meu logotipo",
   "como mudar o nome da empresa",
   "como configurar a empresa",
   "dados no comprovante"
  ],
  "palavras": [
   "empresa",
   "logotipo",
   "logo",
   "cnpj",
   "endereço",
   "configuracoes",
   "configurações",
   "comprovante"
  ],
  "duracao": 19.1,
  "passos": [
   {
    "t": 2.9,
    "texto": "No menu da empresa, escolha Minha empresa"
   },
   {
    "t": 6.9,
    "texto": "Nome, documento e contatos saem nos comprovantes"
   },
   {
    "t": 11.1,
    "texto": "O logotipo entra por Escolher logotipo"
   },
   {
    "t": 13.2,
    "texto": "Salve os dados da empresa"
   }
  ],
  "kb": 317
 },
 {
  "id": "backup",
  "titulo": "Como fazer uma cópia de segurança",
  "modulo": "hub",
  "grupo": "Configurações",
  "resumo": "O Hub copia sozinho todo dia, e você pode gerar uma na hora.",
  "perguntas": [
   "como fazer backup",
   "como salvar meus dados",
   "como não perder os dados",
   "trocar de computador"
  ],
  "palavras": [
   "backup",
   "copia",
   "cópia",
   "segurança",
   "seguranca",
   "restaurar",
   "pen drive",
   "dados"
  ],
  "duracao": 16.9,
  "passos": [
   {
    "t": 2.8,
    "texto": "No menu da empresa, escolha Backup"
   },
   {
    "t": 6.8,
    "texto": "O Hub faz uma cópia sozinho todo dia"
   },
   {
    "t": 8.6,
    "texto": "Fazer backup agora gera uma cópia na hora"
   },
   {
    "t": 12.0,
    "texto": "Para levar a outro computador, guarde a cópia num pen drive"
   }
  ],
  "kb": 348
 },
 {
  "id": "usar-passo-a-passo",
  "titulo": "Como usar o Passo a passo",
  "modulo": "site",
  "grupo": "Este catálogo",
  "resumo": "Escreva a sua dúvida com as suas palavras e o vídeo certo aparece na hora.",
  "perguntas": [
   "como achar um vídeo",
   "como usar o passo a passo",
   "como pesquisar uma dúvida",
   "onde tem tutorial"
  ],
  "palavras": [
   "tutorial",
   "video",
   "vídeo",
   "ajuda",
   "duvida",
   "dúvida",
   "passo a passo",
   "catalogo",
   "pesquisar"
  ],
  "duracao": 33.9,
  "passos": [
   {
    "t": 2.9,
    "texto": "No site da DumTech, clique em Passo a passo, no topo"
   },
   {
    "t": 4.7,
    "texto": "Escreva a sua dúvida do seu jeito"
   },
   {
    "t": 8.6,
    "texto": "O vídeo exato aparece na hora, com o passo a passo ao lado"
   },
   {
    "t": 12.1,
    "texto": "Dê o play: é o programa de verdade fazendo a tarefa"
   },
   {
    "t": 17.9,
    "texto": "Clique num passo para pular direto para ele"
   },
   {
    "t": 22.8,
    "texto": "Ou escolha pelo assunto, nos filtros"
   },
   {
    "t": 27.2,
    "texto": "Copiar link manda o vídeo certo para quem precisa"
   }
  ],
  "kb": 1030
 }
];
