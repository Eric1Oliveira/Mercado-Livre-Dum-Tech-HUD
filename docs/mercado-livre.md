# Vendendo o DumTech Hub pelo Mercado Livre

O Mercado Livre cobra, segura o dinheiro e esconde o contato do comprador. Tudo o
que você manda ao cliente vai pelas **mensagens da venda**, e ali é proibido link,
e-mail e telefone. O processo abaixo entrega a chave e o programa respeitando isso.

## 1. O anúncio

Um anúncio por módulo ou por combo. Modelo (troque os colchetes):

**Título:** `Sistema [Estoque e Vendas] para Loja - DumTech Hub - Licença Vitalícia`

**Descrição** (sem link, sem telefone, sem e-mail):

```
DumTech Hub – [NOME DO MÓDULO OU COMBO]

O que você recebe
• Licença vitalícia do módulo [X] para 1 computador com Windows 10 ou 11.
• Chave de ativação pessoal, enviada pelas mensagens da compra.
• Guia de instalação em PDF, com o endereço oficial para baixar o programa.

O que o programa faz
• [3 a 5 linhas do que o módulo resolve no dia a dia]
• Funciona sem internet. Cópia de segurança automática todo dia.
• Módulos se ligam entre si: compre outros depois, na mesma chave.

Como funciona a entrega
1. Depois da compra você recebe, nas mensagens, a sua chave e o guia em PDF.
2. Baixe e instale o DumTech Hub pelo endereço do guia.
3. Cole a chave e clique em Ativar. Pronto.

Requisitos: Windows 10 ou 11, 64 bits. Internet só para ativar.
Suporte pelas mensagens da compra.
```

Preço: some a comissão do ML (10% a 19% conforme o tipo de anúncio e a categoria,
mais a tarifa por faixa de preço). Simule na calculadora do ML antes de publicar.

## 2. Chegou uma venda (passo a passo)

1. **Painel › Clientes (ou Pedidos) › Nova venda.**
2. Onde vendeu: **Mercado Livre**. Número do pedido: o do ML.
3. Nome do comprador: o que aparece na venda. **E-mail: deixe em branco** (o ML não mostra).
4. Marque o combo ou os módulos, o tipo (vitalícia), os computadores e o **valor que você recebeu**.
5. **Registrar venda e gerar a chave.** Abre a gaveta “Enviar a chave” já no modo Mercado Livre.
6. **Copiar mensagem para o Mercado Livre** e colar em *Mensagens* da venda.
7. **Anexe o guia em PDF** na mesma mensagem (link “Abrir o guia PDF” na gaveta, ou
   `build\dist\Guia-DumTech-Hub.pdf`). O endereço de download está dentro do PDF.
8. Envie. Se o ML pedir confirmação de entrega para produto digital, siga o que ele pedir.

A venda entra no “Vendido” do painel, no histórico do cliente e em “Vendas atendidas”.

## 3. O que o cliente faz

1. Abre o PDF e baixa o instalador em `dumtechsolution.com/baixar`.
2. Instala (o Windows pode avisar “protegeu o computador”: *Mais informações › Executar assim mesmo*).
3. Primeiro acesso: digita **nome e e-mail**, cola a **chave**, clica em Ativar.
4. Os módulos aparecem. Daí em diante funciona offline.

## 4. O cadastro se liga sozinho

A venda do ML criou um cliente **sem e-mail**. Quando ele ativa o Hub e digita o
e-mail, o programa avisa o servidor (`dumtech_vincular_conta`) — a prova é a chave
junto com o computador ativado — e o servidor:

- grava o e-mail no cliente da venda;
- se o e-mail já tinha criado um cadastro solto (primeiro acesso do Hub, pedido na
  loja), junta tudo nele e apaga o solto.

Resultado: **um cliente só no painel**, com a venda do ML, o e-mail e o que vier depois.
Não junta quando o e-mail é de outro cliente que já tem licença (não mistura duas pessoas).

## 5. Ele quer mais um módulo

O caminho certo é **pelo Hub**: Início › *Adquirir novo produto*. A loja abre sabendo
quem ele é e o que tem, o pedido entra ligado ao cadastro dele, você aprova e o
módulo **entra na mesma chave** e aparece sozinho em até 1 hora.

Se ele comprar de novo **pelo ML**: *Clientes › ficha dele › Registrar venda* (entra
na mesma chave). Se registrar como “Nova venda” sem escolher o cliente, informe o
e-mail dele — com o e-mail certo, a venda também cai na chave que ele já tem.

## 6. Quem compra direto pela loja (sem ML, sem Hub)

Não precisa de token. Ele digita nome e e-mail no site; o pedido nasce ligado a esse
e-mail. Você aprova, a chave vai pelo WhatsApp/e-mail (com o link de download), ele
instala e digita **o mesmo e-mail** no primeiro acesso — o servidor reconhece e não
cria outro cadastro. O token (`?t=`) só existe para a loja reconhecer quem **já tem** o
Hub e abriu a loja por dentro dele.

## 7. Devolução (7 dias)

Devolva pelo ML e, no painel, abra a ficha › **Cancelar** a licença. Em até 1 hora,
com internet, os módulos param de abrir no computador dele.

## Pontos a confirmar na sua conta do Mercado Livre

- Qual forma de entrega o ML aceita para software sem envio físico na categoria escolhida.
- Se o PDF anexado com o endereço de download passa na moderação das mensagens.
  Se não passar, a alternativa é o cliente buscar “DumTech Hub” e chegar à página
  de download.
