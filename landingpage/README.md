# Landing page da DumTech

Site estático (HTML, CSS e JavaScript puro — sem build, sem framework) que
vende os módulos do DumTech Hub. Três coisas acontecem aqui:

1. **Monte seu kit** — o visitante escolhe os módulos e vê, em tempo real,
   quais integrações o kit dele ativa e quais ficam apagadas (e por quê).
2. **Reconhecimento pelo Hub** — quem clicou em "Adquirir novo produto" dentro
   do programa chega com um código na URL (`?t=…`). A página troca esse código
   por nome, e-mail e o que a pessoa já comprou: **sem login, sem digitar nada**,
   e sem oferecer o que ela já tem.
3. **Pedido** — o kit é gravado no Supabase e a conversa continua no WhatsApp.

## Rodar aqui

```bash
cd landingpage
npm test        # testes do motor do kit (sem navegador, sem internet)
npm run servir  # http://127.0.0.1:5173
```

Módulos ES não carregam por `file://` — abra sempre pelo servidor.

## Enquanto não há domínio

Esta pasta **viaja dentro do DumTech Hub** (entra no `.exe` pelo
`build/dumtech_hub.spec`). No primeiro clique em "Adquirir novo produto", o Hub
serve a página em `http://127.0.0.1:<porta livre>` e abre o navegador ali — sem
domínio, sem internet, sem instalar nada.

Abrir o `index.html` com dois cliques (`file://`) **não** funciona: o navegador
recusa módulos ES vindos de arquivo e a página abre em branco. Use
`npm run servir` ou o próprio Hub.

## Publicar

Copie a pasta inteira para qualquer hospedagem estática (HostGator, GitHub
Pages, HostGator). Não há nada para compilar.

Depois de publicar, preencha `URL_PADRAO` em
[`src/dumtech/core/loja.py`](../src/dumtech/core/loja.py) com o endereço novo —
o Hub para de servir a cópia local e passa a abrir o site de verdade.

Antes de publicar, abra [js/config.js](js/config.js) e preencha:

| Campo | Para que serve |
|---|---|
| `WHATSAPP` | número que recebe os kits (55 + DDD + número). Vazio = o site só confirma o pedido na tela |
| `SUPABASE_URL` / `SUPABASE_ANON` | já vêm preenchidos com o projeto de licenças; a chave anon é pública por natureza e **não lê tabela nenhuma** |

## Preços

**Não estão no site.** Vêm de `produtos.preco` e `combos.preco` no Supabase
(`dumtech_catalogo`). Para mudar um preço:

```sql
update public.produtos set preco = 299.00 where codigo = 'ESTOQUE';
```

**A página aberta muda sozinha, sem refresh.** Um gatilho no banco avisa o canal
público `catalogo` do Supabase Realtime; o site ([js/tempo-real.js](js/tempo-real.js))
busca o catálogo de novo e o preço que mudou pisca uma vez. O aviso não traz dado
nenhum — o preço vem pela mesma `dumtech_catalogo`. Aba que volta a ficar visível
também confere. Módulo tirado de linha aparece como "Indisponível" e sai do kit.

A primeira pintura usa o último catálogo do servidor guardado no navegador (7 dias);
sem ele, os números em `PRECO_PADRAO` ([js/dados.js](js/dados.js)) — só a rede de
segurança para o site abrir se o servidor não responder. Mantenha-os espelhando o banco.

**Segurança da página:** `index.html` tem Content-Security-Policy (só scripts
desta pasta, rede só para o Supabase do projeto). **Trocou de projeto Supabase?**
Troque o endereço também no `connect-src` dessa meta. `?api=` só aceita servidor
neste computador, e `?kit=`/`?tem=` só aceitam código de módulo.

O **total nunca é calculado pelo navegador**: ao enviar, o banco recalcula a
partir do próprio catálogo (`dumtech_registrar_pedido`). O que o visitante vê
antes é uma prévia.

## Depende destas migrations

| Migration | O que a página usa |
|---|---|
| `20260911230000_porta_de_entrada` | `dumtech_abrir_compra` — o reconhecimento pelo token |
| `20260911235900_landing_catalogo_e_pedidos` | `dumtech_catalogo` e `dumtech_registrar_pedido` |
| `20260912090000_aprovar_pedido` | `dumtech_aprovar_pedido` e a visão `pedidos_abertos` — o que fecha o ciclo (não é usado pela página; é você quem chama) |
| `20260912180000_tempo_real_e_blindagem` | o aviso de catálogo ao vivo e o limite de pedidos por hora (12 por endereço, 6 por e-mail) |

## O ciclo da compra

```
Hub → botão "Adquirir novo produto" → site (?t=token, já sabe quem é)
   → monta o kit → "Quero este kit" → pedido gravado
   → VOCÊ aprova:  select public.dumtech_aprovar_pedido('<pedido_id>');
   → o produto entra na licença que o cliente já tem
   → ele volta para o Hub e o módulo aparece sozinho
```

O Hub confere a licença **sozinho** quando a janela volta a ficar ativa depois
de uma ida à loja — sem clicar em "Verificar licença".

A aprovação é manual de propósito: liberar licença a partir de um clique no
site seria liberar licença a partir da chave pública. Quando houver checkout
automático, quem chama `dumtech_aprovar_pedido` passa a ser o webhook do
gateway, e mais nada muda.

## Quem já visitou não se apresenta de novo

O token da URL vale 15 minutos e é de uso único — ele serve para a **primeira**
visita. Depois disso o navegador guarda nome, e-mail e o que a pessoa já tem
(`js/memoria.js`, 90 dias), então abrir o site direto no dia seguinte continua
sendo "Olá, Joao". O limite é honesto: vale por navegador, e existe um
**"Não é você?"** visível no cartão para apagar tudo.

Sem elas aplicadas, a página **continua de pé**: usa o catálogo local e o envio
cai no WhatsApp. Só não reconhece o cliente nem grava o pedido.

## Os arquivos

| Arquivo | Papel |
|---|---|
| `index.html` | a página |
| `css/estilo.css` | o sistema visual (o mesmo do Hub: violeta #7353F6, cartão branco com fio, Plus Jakarta Sans) |
| `js/dados.js` | **a cópia da vitrine**: nome, descrição, cor e ícone de cada módulo, e as integrações reais |
| `js/kit.js` | o motor do kit: escolha, combo, preço e integrações. Puro, sem DOM — é o que os testes exercitam |
| `js/api.js` | as chamadas ao Supabase, com queda para o catálogo local |
| `js/app.js` | liga o motor na tela: cartões, grafo, resumo e envio |
| `js/config.js` | o que você troca para publicar |
| `tests/kit.test.mjs` | 15 testes do motor |
| `servidor.mjs` | servidor local de desenvolvimento |

## Por que os textos são assim

Cor, ícone, nome e descrição de cada módulo saem do `MANIFEST` do aplicativo
correspondente (`src/dumtech/apps/<id>/module.py`) e de `ui/icons.py` — a
página usa os mesmos traços do programa. As cinco integrações descritas
existem no código (`hub/launcher.py`, `core/catalog.py`, `core/contas.py`,
`core/pedidos.py`, `core/contacts.py`): nenhuma delas é promessa.
