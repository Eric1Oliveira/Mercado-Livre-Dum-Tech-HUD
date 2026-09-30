# DumTech Ordem de Servico — a oficina

Data: 2026-09-01
Status: aprovado

## O problema

Hoje a ordem e um cadastro: cliente, equipamento, defeito, um campo de valor e
um status que anda para frente. Isso descreve a ordem — nao protege a oficina.

O que falta e exatamente o que vira discussao no balcao:

- **"o carregador veio junto?"** — nao existe registro do que entrou;
- **"esse risco na tampa ja estava?"** — nao existe estado de entrada;
- **"eu autorizei esse valor?"** — nao existe aprovacao, nem quando, nem quem;
- **"quanto foi de peca e quanto foi de mao de obra?"** — o valor e um numero
  solto, digitado a mao;
- **"quando foi que voces me entregaram?"** — nao existe historico com hora;
- **"isso tem garantia?"** — nao existe prazo de garantia.

## O carater deste modulo

O Estoque e um catalogo, o Vendas e uma maquina de transacao, o Financeiro e um
calendario de dinheiro. A Ordem de Servico acompanha **um objeto fisico ao longo
do tempo**: um aparelho entra, fica numa fila, alguem mexe nele, o cliente
aprova, e ele sai.

Por isso a tela principal e a **Bancada**: as ordens em faixas por etapa
(esperando, aguardando aprovacao, em andamento, prontas para entregar), em
cartoes que mostram equipamento, cliente e prazo. Nao e uma lista — e a vista
de quem olha a bancada e decide o que pegar agora.

## Telas

1. **Bancada** — as etapas lado a lado, com o que esta atrasado em destaque.
2. **Painel** — fila, atrasadas, concluidas e faturamento do mes.
3. **Ordens** — a lista completa, com filtros, ficha e comprovantes.

Tres telas, nao quatro: inventar uma quarta so para igualar os outros modulos
seria a "mesma cara" que nao queremos. A profundidade esta na ficha.

## Fluxo

    Aberta -> Aguardando aprovacao -> Em andamento -> Concluida -> Entregue
                                                                     |
                                                                 Cancelada

"Aguardando aprovacao" e o estado que faltava: entre diagnosticar e consertar
existe um cliente decidindo. Sem ele, a oficina nao consegue responder quantos
aparelhos estao parados esperando resposta.

## Dados (migracao v2)

`ordens` so ganha colunas (`ALTER TABLE`, nenhum tipo muda):

- `acessorios`, `condicao`, `senha` — o que entrou junto, em que estado, e como
  destravar o aparelho;
- `aprovado_em`, `aprovado_por` — a autorizacao do orcamento;
- `entregue_em`, `garantia_dias` — a entrega e o prazo que corre a partir dela;
- `desconto`.

Tabelas novas:

- `os_itens(ordem_id, tipo, descricao, quantidade, valor_unitario)` — tipo e
  `peca` ou `servico`. Separar os dois responde "quanto foi de material e
  quanto foi de mao de obra", que e a conta que o dono da oficina precisa.
- `os_historico(ordem_id, status, observacao, criado_em)` — cada mudanca de
  etapa com data e hora. E o que responde "quando voces me entregaram?".

`ordens.valor` continua existindo como **total**, recalculado a partir dos itens
sempre que eles mudam. E redundante de proposito: a lista e o resumo ja
dependem dele, e uma ordem sem itens (servico simples) continua podendo ter o
valor digitado direto.

## Regras

**Acessorios sao um registro de entrada, nao um cadastro.** Ficam em texto, uma
linha por item, escolhidos de uma lista sugerida ou digitados. Nao viram tabela
porque ninguem precisa consultar "todas as ordens que tinham carregador".

**Aprovacao.** Sair de "aguardando aprovacao" exige registrar quem aprovou. Uma
ordem aprovada guarda a data — e ela aparece no comprovante de entrega.

**Historico.** Toda mudanca de etapa grava uma linha com data e hora. O
historico nunca e apagado, nem quando a ordem e cancelada.

**Garantia** conta a partir da **entrega**, nao da conclusao: o prazo do cliente
comeca quando o aparelho volta para a mao dele. Padrao de 90 dias, editavel.

**Entregar exige estar concluida.** Nao se entrega o que nao ficou pronto.

## Comprovantes

Dois papeis, no mesmo motor de 40 colunas do Vendas:

- **Entrada**: equipamento, defeito relatado, acessorios, estado de entrada,
  senha e prazo. E o papel que evita a discussao do risco na tampa.
- **Entrega**: diagnostico, pecas e servicos discriminados, total, forma de
  garantia e ate quando ela vale.

O gerador de texto de 40 colunas e o dialogo de comprovante saem de
`apps/vendas/` para `ui/` — sao infraestrutura da plataforma, e agora tem dois
consumidores.

## Fora de escopo

Controle de bancada por tecnico com apontamento de horas, fila de pecas
encomendadas, integracao com o Estoque para baixar peca (o Vendas ja carrega a
ponte; trazer para ca sem pedido do cliente e escopo inventado), assinatura
digital e envio automatico de WhatsApp.

## Ordem de implementacao

1. Modelos, migracao e repositorio (itens, historico, aprovacao) + testes
2. Extrair comprovante/recibo para `ui/` e adaptar o Vendas
3. Interface: Bancada, ficha completa, comprovantes, lista
4. Painel, revisao visual e suite completa
