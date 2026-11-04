# Mensalidade: plano base + adicionais, teste gratis e landing nova

Data: 2026-11-03. Pedido do Eric: sair do vitalicio para mensalidade, reformular
por completo a landing page e, no Hub, mexer so no que a mensalidade exige.

## Decisoes do Eric (brainstorming)

| Tema | Decisao |
|---|---|
| Planos | **Base + adicionais.** Base = Vendas + Estoque + Financeiro. Adicionais = Clientes, Orcamentos, Ordem de Servico, Agenda. **Todo adicional tem o mesmo preco.** |
| Valores | Decididos depois, no painel. O site sai com valores de exemplo. |
| Vitalicios | **Continuam vitalicios.** Recebem as atualizacoes, mas **nunca veem aviso de pagamento, vencimento ou modo consulta.** Para ganhar mais um modulo, falam com a DumTech no WhatsApp e o Eric libera no painel, como hoje. |
| Cobranca | **Planos e Assinaturas do app da InfinitePay.** A API da InfinitePay so cria link avulso, entao a InfinitePay nao avisa o sistema: o Eric confirma cada assinatura nova com 1 clique e marca no painel quem falhou. Asaas (taxa) e Mercado Pago (so cartao, ~4,9%) descartados. |
| Atraso | Carencia com aviso gentil e, depois, **modo consulta**: ve e exporta tudo, nao lanca nada novo. Pagou e o Eric confirmou, volta. |
| Teste | **7 dias gratis, sem cartao**, com o plano completo (base + os 4 adicionais). |
| Hub | So o que a mensalidade exige. Nada de visual novo nem funcionalidade nova. |
| Landing | Reformulada por completo. |

## O que ja existe e e reaproveitado

- `licencas.tipo` ja aceita `vitalicia`, `assinatura` e `teste`, e `expira_em` ja e
  a data em que a licenca para. Em producao hoje: **6 licencas, todas vitalicias,
  sem prazo** - nada do que muda para assinatura/teste atinge alguem.
- O Hub ja tem **modo consulta**: modulo fora da licenca que tem dados abre o
  banco com `PRAGMA query_only` (`hub/launcher.py::consultavel`,
  `core/database.py::so_leitura`), com faixa na janela e mensagem amigavel ao
  tentar gravar (`ui/erros.py`). Licenca vencida ja cai nele.
- A licenca assinada (`licenca-assinada`) ja tem prazo offline (`valida_ate`, 30
  dias) e e conferida pelo Hub de hora em hora.
- E-mail pelo Brevo (`enviar-chave/correio.ts`), remetente `dumtechsolutions@gmail.com`.

## 1. Licenca mensal (servidor)

### Situacoes

Calculadas em um lugar so (`dumtech_situacao_cobranca`), nunca gravadas:

| tipo | expira_em | situacao | O cliente |
|---|---|---|---|
| vitalicia | sempre vazio | *(nenhuma)* | nada muda, nenhum aviso |
| teste | hoje ou depois | `teste` | plano completo, faixa com os dias que faltam |
| assinatura | vazio | `em_dia` | os modulos do plano, nenhum aviso |
| assinatura | hoje ou depois | `pendente` | tudo funciona, aviso gentil ate a data |
| teste/assinatura | antes de hoje | *(recusa `expirada`)* | modo consulta |

Mudancas no banco:

- A regra `licencas_prazo_check` passa a ser: vitalicia **sem** prazo; teste
  **com** prazo; assinatura com ou sem (vazio = em dia).
- `licencas` ganha `cobranca_motivo` (`falhou` | `cancelou` | vazio),
  `cobranca_desde` (data) e `assinatura_desde` (data, mostra o dia da cobranca).
- `mensalidade_config` (uma linha so): `preco_base`, `preco_adicional`,
  `links` (jsonb `{"0": url, ..., "4": url}` - um plano da InfinitePay por
  quantidade de adicionais), `dias_teste` (7), `dias_carencia` (7),
  `computadores` (1). Valores de exemplo: base R$ 89,90, adicional R$ 29,90.
- `assinatura_pedidos`: quem pediu para assinar pelo site (licenca, adicionais,
  valor, link usado, situacao `aguardando` | `confirmado` | `descartado`).

A resposta da licenca (`dumtech_resposta_licenca`) ganha
`cobranca: {situacao, ate, motivo}` **so quando o tipo nao e vitalicia**. A
`licenca-assinada` passa o campo para dentro do pacote assinado.

Vencida (`expirada`) continua sendo recusa - e isso que liga o modo consulta
nos Hubs novos **e nos antigos**. So o texto muda, amigavel:

- teste: "Seu teste gratis terminou em DD/MM. Esta tudo guardado: assine para
  voltar a lancar."
- assinatura: "Nao conseguimos confirmar a sua mensalidade. Seus dados estao
  guardados e voce pode consultar tudo. Assim que o pagamento for confirmado, o
  Hub volta ao normal sozinho."

### Acoes do Eric (painel)

| Botao | O que faz |
|---|---|
| Confirmar assinatura | a licenca vira `assinatura` em dia, os modulos viram base + adicionais escolhidos, `assinatura_desde` = hoje |
| Cobranca falhou | `expira_em` = hoje + carencia, motivo `falhou` |
| Pagamento em dia | `expira_em` vazio, motivo vazio |
| Cancelou | `expira_em` = data escolhida (padrao hoje + carencia), motivo `cancelou` |
| +7 dias de teste | estende o teste |

Funcoes so para administrador com 2 fatores (`dumtech_e_admin()`), no mesmo
padrao das outras.

## 2. Cadastro, assinatura e e-mails (Edge Function `mensalidade`)

Funcao nova, publicada com `--no-verify-jwt` (o site chama sem login). Duas rotas:

- **POST `/cadastro`** (site): `{nome, email, whatsapp, adicionais[], assinar}`.
  Limite por IP. Responde **sempre igual** ao navegador ("Pronto! Mandamos tudo
  para o seu e-mail"), para nao virar maquina de descobrir quem e cliente - a
  diferenca vai so no e-mail:
  - e-mail novo: cria cliente e licenca `teste` com os 7 modulos; e-mail com a
    chave, o link de download e o passo a passo;
  - ja tem teste/assinatura: reenvia a chave que ja existe;
  - e vitalicio: e-mail carinhoso dizendo que a licenca dele continua para
    sempre e que, para mais modulos, e so chamar no WhatsApp.

  Com `assinar = true` grava o pedido em `assinatura_pedidos` e devolve o link
  do plano certo da InfinitePay (link publico de qualquer forma). Sem link
  cadastrado para aquela quantidade, o site oferece o WhatsApp.
- **POST `/admin`** (painel): `{acao, ...}`. Chama a funcao do banco **com o
  token de quem chamou** (o banco decide se e admin, como na `enviar-chave`) e
  manda o e-mail que combina com a acao.

E-mails (todos amigaveis, como o Eric pede: frases completas, o que muda
para a pessoa, sem termo tecnico): boas-vindas do teste, reenvio da chave,
vitalicio, pedido de assinatura recebido, assinatura confirmada, cobranca nao
confirmada (gentil, com a data ate quando tudo funciona), pagamento em dia,
assinatura encerrada (dados guardados, volta quando quiser).

## 3. Painel: tela Mensalidades

- **Numeros:** testando agora, assinantes em dia, pendentes, receita mensal.
- **Para confirmar:** pedidos `aguardando` (nome, e-mail, WhatsApp, plano,
  valor, quando). Confirmar / Descartar. Mudanca de plano lembra: "cancele a
  assinatura antiga na InfinitePay".
- **Assinantes:** situacao, plano, valor, desde. Cobranca falhou / Pagamento em
  dia / Cancelou / WhatsApp.
- **Testes do plano:** dias que faltam, +7 dias, WhatsApp.
- **Precos e links:** os campos de `mensalidade_config`.

A tela Testes (teste por modulo, usado pelos vitalicios) nao muda.

## 4. Landing page nova

Reescrita de `index.html`, `css/estilo.css` e da logica da pagina. As outras
paginas (`baixar/`, `pedido/`, `celular/`, `agendar/`, `guia/`,
`passo-a-passo/`, termos e privacidade) ficam como estao; `pedido/` segue
atendendo pedidos antigos do checkout avulso.

Secoes: topo com "Testar gratis"; abertura (o que o programa faz pelo negocio,
preco "a partir de", 7 dias gratis sem cartao); o que muda no dia a dia; **o
plano** (cartao da base com o que vem incluso + os 4 adicionais para ligar e
desligar, com o total do mes na hora); como funciona (testa, assina, usa);
perguntas frequentes (atraso, cancelar, internet, computadores, onde ficam os
dados); WhatsApp; rodape.

- **Formulario unico** (nome, e-mail, WhatsApp): "Testar 7 dias gratis" ou
  "Assinar" (este leva ao link da InfinitePay do plano montado).
- **Quem chega pelo Hub** (`?t=`): `dumtech_abrir_compra` passa a devolver
  tambem o `tipo`, so quando a prova e a chave ativada. Vitalicio ve uma
  saudacao e o WhatsApp para ganhar mais modulos, **nenhum preco mensal
  empurrado**. Teste/assinante ve o plano dele ja marcado.
- Preco e links vem do banco (`dumtech_mensalidade_publica`); a pagina tem um
  valor de seguranca para pintar na hora.
- Fica fora: montador por modulo avulso, kits, cupom, barra de valor do kit.
- Direcao visual definida na implementacao com frontend-design + design-skill.

## 5. Hub (so o que a mensalidade exige)

- `License` le `cobranca` **do pacote assinado** e ganha `mensal`
  (tipo assinatura/teste), `situacao_cobranca` e `cobranca_ate`.
- Uma faixa no Inicio, **so quando `mensal`**: teste (dias que faltam +
  Assinar), pendente (aviso gentil + ate quando funciona), consulta (dados
  guardados + Assinar / WhatsApp). O texto mora numa funcao pura testavel.
- A faixa da janela em modo consulta usa o texto da mensalidade quando o motivo
  e a mensalidade; o texto atual continua para o resto.
- Tela da licenca: uma linha com o plano e a situacao.
- "Assinar" abre a loja pelo caminho que ja existe (`core/loja.py`).
- **Vitalicio:** nenhum caminho muda. Teste automatizado garante: licenca
  vitalicia nao gera faixa, texto nem botao de cobranca.
- Versao **1.12.0** (inclui a 1.11.1 pendente).

## 6. Testes

- SQL (PGlite, `supabase/tests/mensalidade_test.sql`): regra do prazo,
  situacoes, cadastro novo/existente/vitalicio, limite por IP, acoes do Eric,
  `cobranca` ausente para vitalicia, texto da recusa, permissoes (anon nao
  alcanca acao de admin).
- Edge Functions: `mensalidade.test.mjs` (validacao, e-mails, rotas) e
  `licenca-assinada` com `cobranca`.
- Landing: `plano.test.mjs` (preco, link por quantidade, reconhecimento).
- Python: leitura de `cobranca`, texto da faixa (vazio para vitalicia), faixa do
  modo consulta.

## 7. Lancamento (quem roda e o Eric)

1. `npx supabase db push --linked --yes` (migration nova).
2. `npx supabase functions deploy mensalidade --no-verify-jwt --use-api` e
   `licenca-assinada`.
3. Hub 1.12.0 como pendente, testar, e liberar para todos **antes do site**: quem
   faz o teste baixa o instalador publico.
4. Publicar o painel, colocar precos e os 5 links da InfinitePay.
5. Publicar o site.

## Fica de fora, de proposito

- Lembrete por e-mail do fim do teste (precisaria de tarefa agendada; o Hub
  avisa na faixa).
- Saber sozinho quem pagou (a InfinitePay nao avisa).
- Cupom, plano anual, kits por ramo na landing.
- Qualquer mudanca para vitalicios.
