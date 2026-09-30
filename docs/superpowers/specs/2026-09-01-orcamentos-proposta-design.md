# DumTech Orcamentos — a proposta comercial

Data: 2026-09-01
Status: aprovado

## O problema

Hoje o orcamento e uma lista de itens com um total e um status que alguem troca
a mao. Isso registra o que foi cotado — mas nao ajuda a **ganhar** a venda.

O que falta e o que existe em toda proposta de verdade:

- **condicao de pagamento e prazo de entrega** — as duas perguntas que o cliente
  faz depois do preco, e que hoje so cabem no campo de observacoes;
- **desconto por item** — negociacao real e "tiro 10% nessa peca", nao um
  abatimento no rodape;
- **um documento para mandar** — hoje nao existe nada para imprimir ou copiar;
- **duplicar** — quem cota o mesmo servico toda semana redigita tudo;
- **saber por que perdeu** — orcamento recusado some sem deixar licao.

## O carater deste modulo

O Estoque e um catalogo. O Vendas e uma maquina de transacao. O Financeiro e um
calendario de dinheiro. A Ordem de Servico acompanha um objeto fisico. O
Orcamento e diferente de todos: e um **documento que sai da loja e volta com um
sim ou um nao**.

Por isso a tela principal e o **Funil**: quanto tem em cada etapa, quanto disso
virou venda, o que esta esperando resposta ha tempo demais, o que vence esta
semana e — a pergunta que nenhum dos outros modulos faz — **por que voce
perde**.

## Telas

1. **Funil** — as etapas com valor, a taxa de conversao, o que esta parado
   esperando resposta, o que vence, e os motivos de recusa.
2. **Orcamentos** — a lista, com o documento, duplicar e responder.

Duas telas, e nao quatro. O Funil ja e o painel deste modulo; criar um "Painel"
ao lado dele seria repetir a mesma tela com outro nome — exatamente a "mesma
cara" que estamos evitando. A profundidade esta na proposta.

## Dados (migracao v2)

`orcamento_itens` e **reconstruida**: `quantidade` vira REAL (proposta cota m²,
kg e hora) e a tabela ganha `desconto` por linha.

`orcamentos` so ganha colunas (`ALTER TABLE`):

- `condicao_pagamento`, `prazo_entrega`, `validade_dias`;
- `enviado_em`, `respondido_em` — sem elas nao da para dizer ha quantos dias a
  proposta esta parada, que e o numero que faz alguem pegar o telefone;
- `motivo_recusa`;
- `total` — cache do valor final, recalculado a cada gravacao, porque a lista e
  o funil dependem dele.

## Regras

**Desconto por item, e desconto no rodape.** O item tem o seu abatimento e o
documento mostra os dois: o cliente precisa ver onde o desconto entrou.

**Enviar marca a data.** Sair de rascunho grava `enviado_em`; e dali que conta
o tempo de espera e a validade.

**Responder marca a data e, na recusa, o motivo.** Aprovar ou recusar grava
`respondido_em`. Recusar exige motivo escolhido de uma lista curta (preco,
prazo, comprou de outro, desistiu, sem resposta) — e o que transforma perda em
informacao.

**Validade em dias, contada do envio.** "Vale 15 dias" e como se fala; a data
sai disso. Vencido nao muda o status sozinho: quem responde e o cliente, nao o
calendario — mas a tela avisa.

**Taxa de conversao conta so quem respondeu.** Somar as propostas ainda em
aberto no denominador faz o numero mentir para baixo todo mes.

**Duplicar copia tudo menos a historia**: itens, condicoes e valores vao junto;
numero, datas, status e motivo comecam limpos.

## O documento

`recibo.py`, no mesmo motor de 40 colunas da plataforma: cabecalho com numero e
validade, itens com quantidade, valor e desconto por linha, subtotal, desconto
geral, total, condicao de pagamento, prazo de entrega e a data limite da
proposta.

## Fora de escopo

Envio por e-mail ou WhatsApp, assinatura eletronica, PDF com logotipo, modelos
salvos de proposta (duplicar cobre o caso), aprovacao por link e comissao de
vendedor.

## Ordem de implementacao

1. Modelos, migracao e repositorio (etapas, itens com desconto, funil) + testes
2. Documento e interface: Funil, lista, dialogo da proposta
3. Revisao visual e suite completa
