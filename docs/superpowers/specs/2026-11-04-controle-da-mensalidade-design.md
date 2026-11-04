# Controle da mensalidade pelo painel (planos, assinantes, textos e promocoes)

Data: 2026-11-04. Pedido do Eric: "poder de edicao e controle bem melhor no
painel referente a mensalidade, ate coisas que editam direto na landing:
precos, planos, links".

Base: a mensalidade da 1.12.0 (`2026-11-03-mensalidade-design.md`), no ar desde
04/11. Em producao nao ha nenhum assinante, teste nem link da InfinitePay
configurado: a troca nao tem dado para migrar.

**Nao muda:** o Hub (nenhuma versao nova) e as licencas vitalicias. Nada aqui
aparece para vitalicio.

## Decisoes do Eric

| Tema | Decisao |
|---|---|
| Escopo | As quatro etapas: montagem dos planos, cada assinante, textos da landing, promocoes e avisos |
| Links | **Planos prontos + "monte o seu"**: plano pronto tem preco e link proprios; combinacao montada sem link vai para o WhatsApp |
| Plano pronto | **Qualquer combinacao de modulos** (ex.: Salao = Agenda + Clientes + Financeiro) |
| Pagamentos | **So as excecoes** (como hoje), mas com historico automatico de tudo que acontece |
| Mudanca direta | Caixinha **"Avisar o cliente por e-mail"**, marcada por padrao |
| Landing | **Textos e listas** editaveis; o desenho fica fixo |
| Publicar textos | **Rascunho, "Ver como fica" e "Publicar"**, com volta a versao anterior |
| Promocoes | Faixa de aviso, preco de/por num plano pronto e cupom. **1o mes com desconto fica para depois** |

## Etapa 1 - Montagem dos planos

**Banco**
- `mensalidade_modulos` (uma linha por modulo): `papel` (`base` | `adicional` |
  `fora`), `preco` (do adicional), `a_venda`, `ordem`. Semeada com o de hoje:
  base Vendas, Estoque, Financeiro; adicionais Clientes, Orcamentos, Ordem de
  Servico, Agenda a 29,90.
- `mensalidade_config` fica com `preco_base`, `dias_teste`, `dias_carencia`,
  `computadores`. `preco_adicional` e `links` (por quantidade) saem.
- `mensalidade_planos`: `nome`, `descricao`, `modulos` (qualquer combinacao),
  `preco`, `link`, `destaque`, `visivel` (falso = so por cupom), `ordem`,
  `ativo`, e a promocao (`promo_preco`, `promo_link`, `promo_rotulo`, `promo_ate`).
- `mensalidade_combinacoes`: o link de cada combinacao do "monte o seu"
  (chave = adicionais em ordem, `""` = so a base).
- `assinatura_pedidos` ganha `plano_id`, `modulos` e `cupom`.
- `licencas` ganha `plano_id` e `valor_mensal`, gravados na confirmacao: mudar
  um preco amanha nao mexe em quem ja assina.
- **O preco e o link sempre saem do servidor** (`dumtech_cadastrar_mensal`
  recebe plano, adicionais ou cupom, e calcula). O navegador so mostra.

**Vitrine:** `dumtech_mensalidade_publica` passa a devolver numa chamada so a
base, os adicionais a venda com preco, os planos visiveis (preco vigente, de/por,
se tem link), quais combinacoes tem link (nunca o link), o texto publicado e o
aviso vigente.

**Site:** os planos prontos em cartoes no topo da secao do plano; escolher um
preenche o cupom com os modulos e o preco. Abaixo, "ou monte o seu", com o
preco de cada adicional. "Assinar" vai para o link do plano ou da combinacao;
sem link, WhatsApp.

**Painel:** tela **Planos e precos** - base (modulos e preco), adicionais (a
venda e preco), planos prontos (criar, editar, destacar, reordenar, desligar),
combinacoes do "monte o seu" (total, link e o selo "alguem pediu e falta link"),
teste, carencia e computadores.

## Etapa 2 - Cada assinante

**Ficha** (gaveta ao clicar na linha, tela Mensalidades):
- dados: nome, e-mail, WhatsApp, chave, situacao, plano, valor do mes, desde e
  dia da cobranca;
- editar: plano (pronto ou modulos a mao), valor combinado, computadores, data
  "funciona ate", anotacoes internas (`licencas.observacoes`);
- acoes: cobranca falhou, em dia, cancelou, estender teste, **ativar
  assinatura** (teste ou quem fechou pelo WhatsApp, sem pedido) e **reabrir**
  assinatura cancelada;
- toda mudanca e acao com **"Avisar o cliente por e-mail"** marcada;
- **historico** do mais recente para o mais antigo: o que, de -> para, quando e
  quem.

**Banco:** `assinatura_eventos` (`licenca_id`, `tipo`, `detalhe`, `admin_id`,
`criado_em`), gravado por TODAS as acoes (inclusive as que ja existem). Funcoes
novas, so admin: `dumtech_ajustar_assinatura`, `dumtech_ativar_assinatura`,
`dumtech_reabrir_assinatura`. Diminuir computadores abaixo dos em uso continua
pela tela Acessos (ela pergunta qual sai).

**E-mails novos** (Edge Function `mensalidade`, rota admin, com `avisar`):
plano atualizado, assinatura ativada, assinatura reaberta, data alterada.

## Etapa 3 - Textos da landing

- `landing_conteudo`: duas linhas, `rascunho` e `publicado` (jsonb). O
  rascunho nunca sai para o publico. `landing_publicacoes` guarda cada versao
  publicada (volta com um clique).
- Campos, na ordem da pagina: abertura (rotulo, titulo, chamada, nota), os 4
  fatos, o programa (titulo, texto, e titulo/frase/detalhe de cada modulo da
  base), o plano (titulo, texto, "o que vem incluso", frase de cada adicional),
  como comecar (passos), comecar (titulo), duvidas (pergunta/resposta), contato
  (titulo, texto) e WhatsApp.
- Listas (fatos, inclusos, passos, duvidas): acrescentar, tirar, subir, descer.
- Marcadores `{preco_base}`, `{dias_teste}`, `{computadores}` trocados na hora.
- Tudo entra como texto puro (`textContent`), com limite de tamanho.
- Sem nada publicado, a pagina usa o texto de hoje, que fica no codigo.
- **"Ver como fica"**: o painel e o site estao no mesmo endereco; o rascunho vai
  para a aba nova pelo armazenamento do proprio navegador e a pagina mostra a
  faixa "Pre-visualizacao: ainda nao publicado". Nao passa pela internet.
- O titulo e a descricao que o Google e o WhatsApp leem vem do HTML: o
  `publicar_site.ps1` grava neles o texto publicado.

**Painel:** tela **Textos do site** - formulario por secao, "Ver como fica",
"Publicar", "Descartar rascunho" e "Versoes publicadas".

## Etapa 4 - Promocoes e avisos

- **Faixa de aviso** (`landing_avisos`): texto, link opcional, tom (violeta,
  verde, ambar), inicio, fim, ativo. Vale a mais recente vigente. O visitante
  fecha e ela nao volta naquele navegador.
- **De/por num plano pronto:** `promo_preco` + `promo_link` + `promo_ate` (+
  rotulo). O site mostra "de X por Y ate dd/mm"; vencida a data, volta sozinho.
  Quem assinou na promocao paga o valor promocional (a recorrencia dele na
  InfinitePay tem esse valor): a ficha mostra.
- **Cupom** (`mensalidade_cupons`): codigo -> um plano escondido (`visivel =
  false`) com preco e link proprios; validade, limite de usos, parceiro, ativo.
  Digitado no site ou no link `?cupom=CODIGO`. O painel mostra quantos pedidos e
  quantas assinaturas cada cupom trouxe. Conferencia publica com limite por IP,
  e resposta que nao revela se o cupom existiu antes.

**Painel:** tela **Promocoes** - faixa de aviso, cupons, e um resumo dos planos
em promocao (o de/por e editado no plano).

## Painel: o grupo Mensalidade

No menu, um grupo **Mensalidade** com: Assinantes (a tela de hoje + a ficha),
Planos e precos, Textos do site, Promocoes.

## Testes

- SQL (PGlite): papeis dos modulos, plano pronto qualquer combinacao, preco e
  link sempre do servidor (plano, combinacao, cupom, promo vigente/vencida),
  valor gravado na confirmacao, eventos de todas as acoes, ajustar/ativar/
  reabrir, rascunho invisivel ao publico, publicar/voltar, aviso por data,
  cupom (validade, limite, plano escondido), permissoes (anon nao alcanca nada
  de admin), vitalicia intocada.
- Funcoes: novas acoes e e-mails, `avisar = false` nao manda.
- Landing: motor do plano com planos, combinacoes, promo e cupom; conteudo com
  marcadores e texto puro.
- Painel e site: conferidos no navegador em computador e celular.

## Lancamento

Sem versao nova do Hub. Ordem: migration, funcao `mensalidade`, site e painel.
Entre a migration e a publicacao do site, a pagina no ar continua de pe (cai
nos valores de seguranca) e o cadastro antigo continua aceito.

## Fica de fora

- 1o mes com desconto (proxima rodada).
- Registro de cada mensalidade paga (o Eric escolheu so as excecoes).
- Trocar fotos e esconder secoes pelo painel.
