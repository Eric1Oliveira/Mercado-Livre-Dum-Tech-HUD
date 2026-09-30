# DumTech Financeiro — fluxo de caixa

Data: 2026-09-01
Status: aprovado

## O problema

Hoje o Financeiro e uma lista de contas com data e um botao "marcar como pago".
Ele responde "o que venceu?" — mas nao responde a pergunta que faz o dono de
uma loja pequena perder o sono:

> **Vou ter dinheiro no dia 12?**

Falta tudo que separa uma lista de um controle financeiro: parcelamento,
despesa que se repete todo mes, recebimento parcial, em qual conta o dinheiro
esta, e a projecao do saldo.

## O carater deste modulo

O Estoque e um catalogo. O Vendas e uma maquina de transacao. O Financeiro e um
**calendario de dinheiro**: o eixo dele e o tempo. Por isso a tela principal
nao e uma lista nem um painel de cartoes — e o **Fluxo**: o saldo de hoje, o
que entra e o que sai em cada dia dos proximos 30, e a linha do saldo
projetado. Se essa linha cruza o zero, a tela diz a data em letras grandes.

## Telas

1. **Fluxo** — saldo de hoje, projecao de 30 dias, dia a dia, e o aviso do dia
   em que o dinheiro acaba.
2. **Painel** — a receber, a pagar, vencidos e o resultado do mes.
3. **Lancamentos** — a lista. Baixa (total ou parcial), parcelar, repetir.
4. **Contas** — onde o dinheiro esta (caixa, banco, cartao) e transferencias.

## Dados (migracao v2)

`lancamentos` so ganha colunas (`ALTER TABLE`, nenhum tipo muda):
`conta_id`, `grupo`, `parcela`, `parcelas`, `serie`.

Tabelas novas:

- `contas(nome, tipo, saldo_inicial, ativo)` — caixa, banco ou cartao.
- `baixas(lancamento_id, data, valor, conta_id, forma)` — **um lancamento tem N
  baixas**. E daqui que sai tanto o recebimento parcial quanto a resposta
  "quando o dinheiro entrou de verdade", que a projecao precisa.
- `transferencias(origem_id, destino_id, data, valor)`.

`lancamentos.pago_em` continua existindo como **data em que ficou quitado**,
recalculada dentro da mesma transacao das baixas. E redundante de proposito: as
consultas de lista e de resumo ja dependem dela e do indice, e reescrever tudo
para somar baixas seria mais risco do que valor.

Na migracao, todo lancamento que ja estava pago vira uma baixa do valor cheio
na data em que foi pago — ninguem perde historico.

## Regras

**Parcelamento.** "1.200 em 3x" vira **tres lancamentos** de 400, vencendo em
meses seguidos, ligados por um `grupo`. Nao e um lancamento com um contador:
parcela e uma conta de verdade, com vencimento proprio, que pode ser paga,
adiada ou cancelada sozinha. A divisao que nao fecha sobra na **primeira**
parcela (1.000 em 3x = 333,34 + 333,33 + 333,33), porque e a primeira que o
cliente confere.

**Recorrencia.** Aluguel todo mes tambem gera lancamentos de verdade, N meses a
frente (padrao 12). Mesma mecanica do parcelamento, rotulo diferente. Regra do
dia 31: mes que nao tem o dia usa o ultimo dia do mes.

**Baixa.** Total ou parcial, com data e conta proprias. Recebeu 300 de 1.000?
Fica 700 em aberto e 300 ja na conta. A baixa nao pode passar do que falta.
Estornar uma baixa desfaz so aquela.

**Contas.** Saldo = saldo inicial + baixas de receita − baixas de despesa +
transferencias recebidas − enviadas. Conta com movimento nao e apagada, e
inativada — o mesmo criterio do produto no Estoque.

**Transferencia** e movimento entre contas, **nao** receita nem despesa: sacar
do banco para o caixa nao pode inflar o resultado do mes.

**Projecao.** Comeca no saldo de hoje e soma, dia a dia, o que esta em aberto.
Atrasado entra no dia de hoje — e a tela diz isso e mostra quanto e, porque
receber atrasado e uma aposta e quem decide e o dono, nao o programa.

## Fora de escopo

Conciliacao bancaria (OFX/CNAB), DRE e centro de custo, emissao de boleto,
juros e multa automaticos por atraso, integracao com banco. Quem precisa disso
ja tem contador e sistema contabil.

## Ordem de implementacao

1. Modelos, migracao e repositorio (contas, baixas, series, projecao) + testes
2. Interface: Fluxo, Contas, baixa e parcelamento nos Lancamentos
3. Painel, revisao visual e suite completa
