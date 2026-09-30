# DumTech Hub — o que falta para o produto valer o preco

Data: 2026-09-01
Status: aprovado

## O diagnostico

Os sete modulos tem profundidade de dominio. O problema nao e falta de
funcionalidade — e que **o software e invisivel**:

- ele nunca aparece para o cliente do cliente (o comprovante impresso nao tem
  nem o nome da loja);
- ele nunca conta nada que o dono ja nao soubesse (os numeros existem, mas so
  aparecem quando alguem vai procurar);
- sete modulos valem sete modulos: eles compartilham a lista de nomes de
  clientes e o catalogo do Estoque, e nada mais.

Ninguem paga por funcionalidade. Paga por parecer profissional, por ser
avisado, e por nao repetir trabalho.

## A regra que atravessa tudo

> **Configuravel pelo cliente, e util sem configurar.**

Nao pode existir texto de documento nem de mensagem escrito no codigo. Tudo o
que o cliente veria vontade de mudar tem que estar numa tela — e ao mesmo tempo
**nada pode exigir configuracao para funcionar no primeiro dia**.

Consequencias praticas, que valem para todas as telas deste documento:

1. **Padrao pronto.** Toda mensagem e todo documento nascem com um texto que ja
   serve. Instalar e usar, sem tela de configuracao nenhuma.
2. **Previa ao vivo.** Onde houver modelo editavel, a tela mostra ao lado como
   fica com dados de exemplo. Ninguem precisa "testar para ver".
3. **Campos como etiqueta clicavel**, nao como manual. `{cliente}`, `{total}`
   aparecem como botoes que inserem no texto; nao existe lista escondida numa
   documentacao que ninguem le.
4. **Erro de digitacao nao quebra.** Campo desconhecido no modelo vira aviso na
   propria tela, e na hora de usar ele sai vazio em vez de derrubar.
5. **Convite, nao bloqueio.** Faltando os dados da empresa, o Inicio mostra um
   convite para preencher. Nunca uma tela obrigatoria na primeira abertura.

## As cinco frentes

### 1. Identidade da empresa

`core/empresa.py`: razao social, nome fantasia, CNPJ/CPF, telefone, WhatsApp,
e-mail, endereco e **logotipo**. Guardado com as preferencias; o logo copiado
para `config/`.

Aparece automaticamente no cabecalho de **todos** os documentos que ja existem
(venda, fechamento de caixa, entrada e entrega de OS, proposta). Sem empresa
preenchida, o documento sai como sai hoje — nao quebra.

### 2. Documento A4 em PDF

As 40 colunas estao certas para bobina termica e erradas para uma proposta que
vai por e-mail. `ui/documento.py` monta um A4 (HTML no `QTextDocument`, que da
tipografia decente de graca) com logo, dados da empresa, tabela de itens,
totais e rodape — e exporta PDF.

Cada aplicativo continua escrevendo o **conteudo**; o motor cuida da forma. O
mesmo padrao de `ui/recibo.py`: um motor, varios consumidores.

Onde entra: proposta comercial e comprovante de entrega de OS. O balcao
continua na bobina.

### 3. WhatsApp em um clique

`core/mensagens.py`: modelos editaveis com campos entre chaves, e link `wa.me`
— sem API, sem custo, sem cadastro.

Seis mensagens, cada uma com padrao pronto: proposta enviada, OS pronta,
lembrete de vencimento, agradecimento de venda, lembrete de compromisso e
aniversario. Um botao "WhatsApp" na tela de cada modulo.

### 4. Tela "Hoje"

Cada aplicativo passa a responder uma pergunta so: **o que precisa de atencao
hoje?** Contrato novo em `core/avisos.py` (`Aviso`), e cada `module.py` expoe
`avisos(paths)`. O Hub junta os aplicativos liberados e mostra no Inicio.

O que aparece ja existe calculado dentro dos modulos: contas vencendo, estoque
baixo, orcamento parado, OS atrasada, compromisso do dia, aniversariante.

Os prazos sao configuraveis (quantos dias de antecedencia, a partir de quantos
dias um orcamento esta "parado"), e cada tipo de aviso pode ser desligado.

**Efeito comercial:** quanto mais modulos o cliente tem, mais rica fica a
primeira tela. E o argumento de venda do segundo e do terceiro modulo.

### 5. Pontes entre modulos

O padrao ja existe e esta provado: o Estoque publica um catalogo em
`core/catalog.py` e o Hub so entrega quando a licenca libera. Mesmo desenho:

- `core/contas.py` — o Financeiro publica "criar conta a receber". Venda a
  prazo e OS entregue viram conta a receber sozinhas.
- `core/pedidos.py` — Vendas e Ordens publicam "abrir a partir de um
  orcamento". Proposta aprovada vira venda ou OS com um clique.

Sempre opcional: sem o outro modulo licenciado, o botao nao aparece e nada
quebra.

## Fora de escopo

API oficial do WhatsApp (o link `wa.me` resolve sem custo), envio de e-mail,
editor visual de documento, nota fiscal.

## Ordem de implementacao

1. Identidade da empresa + tela de Configuracoes (com o Backup movido para ela)
2. Documento A4 em PDF
3. Mensagens de WhatsApp
4. Tela "Hoje"
5. Pontes entre modulos
