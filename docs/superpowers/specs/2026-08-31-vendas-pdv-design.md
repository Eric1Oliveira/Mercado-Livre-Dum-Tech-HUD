# DumTech Vendas — PDV de balcao

Data: 2026-08-31
Status: aprovado

## O problema

Hoje o Vendas e um cadastro de vendas: abre um formulario, digita numero,
cliente, itens, uma forma de pagamento, salva. Isso registra uma venda que ja
aconteceu — nao *faz* a venda acontecer.

Quem compra este modulo tem balcao. A pessoa esta em pe, com fila, e precisa:
bipar, cobrar, receber em duas formas, dar troco, entregar comprovante e, no
fim do dia, conferir a gaveta. Nada disso existe.

## O carater deste modulo

O Estoque e um catalogo: listas, filtros, fichas. O Vendas e uma **maquina de
transacao**. A tela principal nao e uma lista — e um caixa: campo de bipe
sempre com foco, itens entrando por cima, TOTAL grande, teclado no comando.
Formulario modal e a excecao (venda a prazo, correcao), nao o caminho normal.

Por isso a ordem das telas comeca pelo **Balcao**, e nao pelo Painel como nos
outros modulos: o operador abre o aplicativo para vender.

## Telas

1. **Balcao** — o PDV. Bipe, itens, total, F-keys. Finalizar abre o pagamento.
2. **Painel** — vendido hoje/mes, ticket medio, formas de pagamento, caixa aberto.
3. **Vendas** — historico. Comprovante, cancelamento com motivo, devolucao.
4. **Caixa** — abertura, sangria/suprimento, fechamento com conferencia.

## Dados (migracao v2)

`venda_itens` e **reconstruida** (quantidade INTEGER -> REAL): balcao de
padaria e acougue vende por quilo, e o catalogo do Estoque ja trabalha com
casas decimais por unidade. Ganha `produto_id`, `codigo` e `unidade`.

`vendas` recebe colunas novas por `ALTER TABLE ADD COLUMN` (nenhum tipo muda):
`caixa_id`, `troco`, `cancelada_em`, `motivo_cancelamento`.

Tabelas novas:

- `pagamentos(venda_id, forma, valor, recebido)` — uma venda tem N pagamentos.
  `recebido` guarda o que a pessoa entregou em dinheiro, para o troco.
  `vendas.forma_pagamento` continua existindo como **resumo** ("Dinheiro + Pix")
  para a lista e os relatorios de hoje.
- `devolucoes(venda_id, data, motivo, valor, caixa_id)` e
  `devolucao_itens(devolucao_id, venda_item_id, quantidade, valor_unitario)`.
  A quantidade ja devolvida de um item nao e gravada duas vezes: sai de uma
  soma sobre `devolucao_itens` na hora de ler.
- `caixas(aberto_em, fechado_em, valor_abertura, contado, diferenca, status)`
- `caixa_movimentos(caixa_id, tipo, valor, motivo)` — sangria e suprimento.

## Regras

**Pagamento.** A soma dos pagamentos precisa cobrir o total. Troco so existe em
dinheiro: `troco = recebido_em_dinheiro - devido_em_dinheiro`. Pagar a mais em
cartao ou Pix e erro, nao troco.

**Cancelamento.** Exige motivo. Devolve o estoque. Uma venda cancelada nao
soma em lugar nenhum.

**Devolucao.** Total ou parcial, por item. Nao pode devolver mais do que foi
vendido (contando o que ja voltou antes). Devolve o estoque. O total liquido do
dia desconta a devolucao no dia em que ela aconteceu, nao no dia da venda —
e assim que o caixa fecha na pratica.

**Caixa.** Vender sem caixa aberto e permitido: loja pequena nem sempre abre
caixa, e travar a venda por causa disso e o tipo de rigidez que faz o cliente
desistir do sistema. Se houver caixa aberto, a venda entra nele.

Esperado na gaveta = abertura + dinheiro recebido - trocos + suprimentos
- sangrias - devolucoes em dinheiro. Diferenca = contado - esperado.

## A ponte com o Estoque

Decisao aprovada: o Hub passa um **catalogo opcional** para o Vendas, no mesmo
padrao de `contacts` — o aplicativo funciona igual sem ele.

`core/catalog.py` define `ItemCatalogo` (produto_id, codigo, nome, unidade,
casas, preco, saldo) e `CatalogoEstoque`, que abre `estoque.db` e traduz para
esse formato. O `AppLauncher` monta o catalogo **so quando a licenca libera o
Estoque** e entrega em `AppContext.catalog`.

Com catalogo: o bipe acha o produto, preenche descricao/preco/unidade, mostra
o saldo, e a venda da baixa. Sem catalogo: o item e texto livre e preco
digitado — exatamente como hoje.

**Estoque errado nao impede venda.** Saldo insuficiente vira aviso amarelo, nao
bloqueio: o cliente esta com o dinheiro na mao e o errado e o cadastro. Falha
ao dar baixa tambem nunca derruba a venda — a venda grava, o aviso aparece.

## Comprovante

`recibo.py` gera texto de 40 colunas (a largura da bobina termica comum).
O dialogo mostra em fonte monoespacada e imprime pelo `QPrintDialog`. Mesmo
motor para a tela e para o papel: o que se ve e o que sai.

## Fora de escopo

NF-e/NFC-e, SAT e integracao com SEFAZ. Isso e certificado digital, homologacao
por estado e obrigacao fiscal continuada — quem precisa disso compra software
fiscal. Comprovante nao fiscal cobre o balcao que este produto atende.

TEF/maquininha integrada, delivery, comissao de vendedor, programa de pontos.

## Ordem de implementacao

1. Modelos, migracao e repositorio (pagamento, caixa, devolucao) + testes
2. Ponte do catalogo (`core/catalog.py`, launcher, contexto) + testes
3. Interface: Balcao, dialogo de pagamento, Caixa, acoes do historico, recibo
4. Painel, revisao visual e suite completa
