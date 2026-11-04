# Landing page da DumTech

Site estático (HTML, CSS e JavaScript puro — sem build, sem framework) que
vende o DumTech Hub **por mensalidade** (desde 03/11/2026). Quatro coisas
acontecem na página inicial:

1. **O plano** — plano base (Vendas, Estoque e Financeiro) + adicionais
   (Clientes, Orçamentos, Ordem de Serviço e Agenda), todos pelo mesmo preço.
   O visitante liga e desliga os adicionais e o **cupom** ao lado imprime uma
   linha para cada um, com o total do mês.
2. **Teste grátis de 7 dias, sem cartão** — nome, e-mail e WhatsApp. A chave
   vai **só por e-mail** (Edge Function `mensalidade`), com o link para baixar.
3. **Assinar** — o mesmo cadastro, e a pessoa segue para o plano da
   InfinitePay com a quantidade de adicionais que escolheu. Quem confirma a
   assinatura é o Eric, no painel (tela Hoje).
4. **Reconhecimento pelo Hub** — quem clica em "Adquirir novo produto" chega
   com `?t=…`. Cliente **vitalício** vê uma saudação e o WhatsApp: a página
   esconde o plano e o cadastro, e nunca empurra mensalidade para ele.
   Teste e assinante veem o plano para assinar ou mudar.

O desenho e as decisões estão em
[docs/superpowers/specs/2026-11-03-mensalidade-design.md](../docs/superpowers/specs/2026-11-03-mensalidade-design.md).

## Rodar aqui

```bash
cd landingpage
npm test        # testes do plano, da memoria e das outras paginas (sem navegador)
npm run servir  # http://127.0.0.1:5173
```

Módulos ES não carregam por `file://` — abra sempre pelo servidor.

## Enquanto não há domínio

Esta pasta **viaja dentro do DumTech Hub** (entra no `.exe` pelo
`build/dumtech_hub.spec`). No primeiro clique em "Adquirir novo produto", o Hub
serve a página em `http://127.0.0.1:<porta livre>` e abre o navegador ali.

## Publicar

Copie a pasta inteira para a hospedagem estática (`tools\publicar_site.ps1`).
Não há nada para compilar. Em [js/config.js](js/config.js) ficam o WhatsApp e o
endereço do Supabase.

## Preços, planos, textos e promoções

**Nada disso está no código.** Tudo vem de `dumtech_mensalidade_publica`, numa
chamada só, e é editado no painel:

| No painel | O que muda no site |
|---|---|
| Planos > Planos e preços | preço da base, cada adicional (preço e "à venda"), os planos prontos (cartões, com de/por e o selo "Recomendado") e quais combinações do monte o seu têm link |
| Site > Textos do site | todo texto da página, com rascunho, "Ver como fica" (`?previa=1`) e publicar |
| Site > Faixa de aviso | o recado no topo, com datas |
| Planos > Cupons | os cupons dos parceiros (`?cupom=CODIGO` aplica sozinho) |

A vitrine **nunca entrega os links** da InfinitePay: o link volta só depois do
cadastro, e o preço é recalculado no banco. Os padrões de
[js/plano.js](js/plano.js) e [js/conteudo.js](js/conteudo.js) são a rede de
segurança para a página pintar na hora. Vitalício que chega pelo Hub não vê o
plano, o cadastro nem a faixa de aviso.

**Segurança da página:** `index.html` tem Content-Security-Policy (só scripts
desta pasta, rede só para o Supabase do projeto). `?api=` só aceita servidor
neste computador, e `?kit=` só aceita código de módulo.

A resposta do cadastro é **igual para todo mundo** (novo, quem já tem chave,
vitalício): o que muda vai só no e-mail. Assim ninguém descobre quem é cliente
digitando um e-mail.

## Os arquivos da página inicial

| Arquivo | Papel |
|---|---|
| `index.html` | a página |
| `css/inicio.css` | o visual da página inicial (violeta #7353F6, Plus Jakarta Sans, IBM Plex Mono no cupom) |
| `css/estilo.css` | o visual das **outras** páginas (baixar, guia, pedido, termos...) — não mexa nele pela página inicial |
| `js/plano.js` | o motor do plano: planos prontos, monte o seu, cupom, de/por, quem chegou. Puro, sem DOM (`tests/plano.test.mjs`) |
| `js/conteudo.js` | os textos: o padrão, a mistura com o publicado, os marcadores e a prévia. Puro (`tests/conteudo.test.mjs`); o painel também lê os padrões daqui |
| `js/app.js` | liga o motor na tela: adicionais, cupom, saudação, tour e cadastro |
| `js/api.js` | as chamadas ao Supabase (`carregarMensalidade`, `cadastrar`, `reconhecer`) |
| `js/memoria.js` | quem já visitou (nome, e-mail e o tipo da licença, 90 dias) |
| `js/dados.js` | nome, cor e ícone de cada módulo (os mesmos do programa) |
| `img/` | telas reais do programa (Vendas, Estoque e Financeiro) |

`js/kit.js`, `js/pagamento.js` e `pedido/` são do modelo antigo (módulo avulso
com checkout da InfinitePay): continuam de pé para os pedidos que já existiam e
para as páginas de kit.

## Por que os textos são assim

Quem lê é dono de pequeno negócio: frases completas, o que muda para ele e o
que fazer, sem termo técnico. Cada frase de módulo descreve algo que o programa
faz de fato hoje.
