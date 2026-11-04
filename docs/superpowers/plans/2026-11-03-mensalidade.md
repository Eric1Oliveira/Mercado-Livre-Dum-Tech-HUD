# Mensalidade - Plano de implementacao

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** vender o DumTech Hub por mensalidade (base + adicionais, teste de 7 dias, cobranca nos planos do app da InfinitePay confirmada pelo Eric), com landing page nova e o minimo necessario no Hub.

**Architecture:** a situacao da cobranca e calculada no banco a partir de `tipo` + `expira_em` e viaja assinada na licenca. Vencida continua sendo a recusa `expirada`, que ja liga o modo consulta do Hub. Uma Edge Function nova (`mensalidade`) faz o cadastro do site e as acoes do painel, e manda os e-mails pelo Brevo. Landing e painel sao JavaScript puro, sem build.

**Tech Stack:** Postgres/Supabase (PL/pgSQL, testes em PGlite), Edge Functions Deno/TypeScript (testes em Node), Python 3.11 + PySide6 (Hub), HTML/CSS/JS ES modules (landing e painel).

**Spec:** `docs/superpowers/specs/2026-11-03-mensalidade-design.md`

## Global Constraints

- Vitalicio NUNCA ve aviso de pagamento, vencimento ou modo consulta de mensalidade. `cobranca` so existe na resposta quando `tipo <> 'vitalicia'`.
- Plano base: `ESTOQUE`, `FINANCEIRO`, `VENDAS`. Adicionais: `AGENDA`, `CLIENTES`, `ORCAMENTOS`, `ORDENS`. Todo adicional tem o mesmo preco.
- Valores de exemplo: base 89,90, adicional 29,90. Teste 7 dias, carencia 7 dias, 1 computador.
- Texto para o cliente: amigavel, frases completas, sem termo tecnico.
- Sem commit (o Eric pede quando quiser). `db push` e `functions deploy` sao do Eric.
- Testes: `cd supabase && node tests/rodar.mjs mensalidade_test.sql`; `cd supabase/functions && npm test`; `cd landingpage && npm test`; Python `.venv\Scripts\python.exe -m unittest` com `PYTHONPATH=src` e `QT_QPA_PLATFORM=offscreen`.

---

### Task 1: Banco - licenca mensal, situacao e resposta

**Files:**
- Create: `supabase/migrations/20261103120000_mensalidade.sql`
- Create: `supabase/tests/mensalidade_test.sql`

**Interfaces (Produces):**
- `licencas.cobranca_motivo text` (`falhou`|`cancelou`|null), `licencas.cobranca_desde date`, `licencas.assinatura_desde date`
- `licencas_prazo_check`: vitalicia sem prazo; teste com prazo; assinatura livre
- `public.mensalidade_config` (linha unica `id = true`): `preco_base`, `preco_adicional`, `links jsonb`, `dias_teste`, `dias_carencia`, `computadores`, `atualizado_em`
- `public.dumtech_plano_base() -> text[]`, `public.dumtech_plano_adicionais() -> text[]`
- `public.dumtech_valor_mensal(p_adicionais integer) -> numeric`
- `public.dumtech_situacao_cobranca(p_tipo text, p_expira_em date) -> text` (`null`|`teste`|`em_dia`|`pendente`|`consulta`)
- `dumtech_resposta_licenca` com `cobranca: {situacao, ate, motivo, desde}` (so nao-vitalicia)
- `dumtech_licenca_valida`: mensagens amigaveis de `expirada` para teste e assinatura

- [ ] Step 1: escrever `mensalidade_test.sql` com: vitalicia com prazo e recusada; teste sem prazo e recusado; assinatura sem prazo aceita; `dumtech_situacao_cobranca` nos 5 casos; resposta de vitalicia sem `cobranca`; resposta de teste com `cobranca.situacao = 'teste'`; validar teste vencido levanta `expirada|Seu teste gratis terminou...`; assinatura vencida levanta `expirada|Nao conseguimos confirmar a sua mensalidade...`.
- [ ] Step 2: rodar `node tests/rodar.mjs mensalidade_test.sql` - falha (funcoes nao existem).
- [ ] Step 3: escrever a parte 1 da migration (regra do prazo, colunas, config com RLS de admin, base/adicionais, valor, situacao, `dumtech_resposta_licenca` = corpo de 20260922120000 + `cobranca`, `dumtech_licenca_valida` = corpo de 20260911120000 com as mensagens novas).
- [ ] Step 4: rodar o teste e a bateria SQL inteira (`node tests/rodar.mjs`) - tudo passa.

### Task 2: Banco - cadastro do site e pedidos de assinatura

**Files:** Modify `supabase/migrations/20261103120000_mensalidade.sql`, `supabase/tests/mensalidade_test.sql`

**Interfaces (Produces):**
- `public.assinatura_pedidos(id, licenca_id, adicionais text[], valor, link, situacao, criado_em, resolvido_em)`
- `public.dumtech_cadastrar_mensal(p_nome text, p_email text, p_telefone text, p_adicionais text[], p_assinar boolean, p_ip text) -> jsonb` - so `service_role`. Devolve `{ok, caso: 'nova'|'ja_tem'|'vitalicio', nome, email, chave, dias_teste, ate, link, valor, adicionais}` ou `{ok:false, erro, mensagem}`.
- `public.dumtech_mensalidade_publica() -> jsonb` - `anon`. `{ok, preco_base, preco_adicional, base[], adicionais[], dias_teste, assinavel: {"0": bool, ...}}`.
- `compra_tokens.tipo` + `dumtech_token_compra` grava o tipo quando a prova e a chave + `dumtech_abrir_compra` devolve `tipo`.

Regras: limite 5 por IP por hora (`dumtech_dentro_do_limite('mensal_ip', p_ip, 5, interval '1 hour')`); e-mail valido (`dumtech_email_valido`); nome obrigatorio; adicionais fora da lista sao ignorados; cliente achado por `lower(email)` ou criado (`origem 'venda'`, telefone); licenca mais recente nao cancelada do cliente decide o caso; nova = `dumtech_emitir_licenca(cliente, base || adicionais, null, 'teste', current_date + dias_teste, computadores, 'Teste do plano mensal pelo site')`; `p_assinar` e caso <> vitalicio grava o pedido com `valor = dumtech_valor_mensal(n)` e `link = links->>n`.

- [ ] Step 1: testes - e-mail novo cria teste com 7 modulos e prazo; repetir o e-mail devolve `ja_tem` com a mesma chave e nao cria outra licenca; vitalicio devolve `vitalicio` sem pedido; `assinar` grava pedido com valor 89,90 + 2 x 29,90 para 2 adicionais e o link da config; 6a chamada do mesmo IP na hora e recusada; anon nao executa `dumtech_cadastrar_mensal`; publica nao expoe links; token com chave devolve `tipo`.
- [ ] Step 2: rodar - falha. Step 3: implementar. Step 4: rodar tudo - passa.

### Task 3: Banco - acoes do Eric e visoes do painel

**Files:** Modify a mesma migration e o mesmo teste.

**Interfaces (Produces)** - todas `security definer`, abrem com `perform public.dumtech_painel_portao()`, `grant execute ... to authenticated`:
- `dumtech_confirmar_assinatura(p_pedido uuid) -> jsonb` `{ok, nome, email, chave, adicionais, valor, mudanca}`
- `dumtech_descartar_assinatura(p_pedido uuid) -> jsonb`
- `dumtech_cobranca(p_licenca uuid, p_acao text, p_ate date default null) -> jsonb` (`falhou`|`em_dia`|`cancelou`) `{ok, nome, email, ate, acao}`
- `dumtech_estender_teste_mensal(p_licenca uuid, p_dias integer default 7) -> jsonb` `{ok, nome, email, ate}`
- `dumtech_dados_mensais(p_licenca uuid) -> jsonb` `{ok, nome, email, chave, tipo, situacao, ate}` (para o e-mail)
- visoes `painel_mensalidades` e `painel_assinatura_pedidos` (`security_invoker`)

- [ ] Step 1: testes - confirmar troca tipo para assinatura, zera prazo, deixa so base + adicionais, marca pedido e descarta os outros aguardando; falhou poe prazo hoje + carencia e motivo; em_dia limpa; cancelou usa a data; acoes em vitalicia sao recusadas; sem admin, `42501`.
- [ ] Step 2-4: falha, implementa, passa (bateria inteira).

### Task 4: Licenca assinada leva a cobranca

**Files:** Modify `supabase/functions/licenca-assinada/nucleo.ts`; Test `supabase/functions/tests/licenca-assinada.test.mjs`

**Interfaces:** `conteudoDaLicenca` ganha `cobranca: {situacao, ate, motivo} | null` (via `cobrancaValida(dados.cobranca)`).

- [ ] Step 1: teste - vitalicia sem cobranca -> `cobranca: null`; teste com cobranca -> campos limpos; lixo -> null.
- [ ] Step 2-4: falha, implementa, `npm test` passa.

### Task 5: Edge Function `mensalidade`

**Files:**
- Create: `supabase/functions/mensalidade/nucleo.ts` (rotas puras, validacao, e-mails)
- Create: `supabase/functions/mensalidade/index.ts` (Deno.serve, rpc service_role e rpc com o token de quem chamou)
- Test: `supabase/functions/tests/mensalidade.test.mjs`

**Interfaces:**
- `cadastro(amb, corpo, ip) -> {status, corpo}`: valida, chama `dumtech_cadastrar_mensal`, manda o e-mail do caso, responde `{ok:true, link?, valor?}` igual para todos os casos.
- `admin(amb, corpo, rpcDoChamador) -> {status, corpo}`: `acao` em `confirmar|descartar|falhou|em_dia|cancelou|estender`, chama a funcao do banco com o token de quem chamou e manda o e-mail.
- `cartas.<caso>(dados) -> {assunto, texto, html}`: boas_vindas, ja_tem, vitalicio, pedido_recebido, confirmada, falhou, em_dia, cancelou, estendido.

- [ ] Step 1: testes - e-mail invalido 400; resposta do navegador identica para nova/ja_tem/vitalicio; e-mail certo por caso, com a chave so em boas_vindas e ja_tem; admin sem token 401; acao desconhecida 400; textos sem palavras tecnicas (lista proibida: licenca_id, token, RPC, erro interno).
- [ ] Step 2-4: falha, implementa, passa.

### Task 6: Hub - a licenca entende a mensalidade

**Files:**
- Modify: `src/dumtech/core/licensing.py` (campo `cobranca`, propriedades `mensal`, `situacao_cobranca`, `cobranca_ate`; le do pacote assinado)
- Create: `src/dumtech/core/mensalidade.py` (`faixa(licenca, hoje) -> Faixa | None`, `texto_consulta(licenca) -> str | None`)
- Test: `tests/test_mensalidade.py`

- [ ] Step 1: testes - vitalicia (com ou sem bloqueio) -> `faixa` None e `texto_consulta` None; teste com 3 dias -> titulo com "3 dias"; pendente -> data; teste/assinatura bloqueada `expirada` -> faixa de consulta; `cobranca` so vale se veio assinada.
- [ ] Step 2-4: falha, implementa, passa.

### Task 7: Hub - telas

**Files:** Modify `src/dumtech/hub/views/home_view.py` (faixa da mensalidade antes da faixa de consulta; texto da consulta usa `texto_consulta`), `src/dumtech/ui/app_shell.py` (faixa da janela), `src/dumtech/hub/views/license_view.py` (linha "Plano"), `src/dumtech/__init__.py` (1.12.0). Test: `tests/test_mensalidade.py` (telas offscreen).

- [ ] Step 1: testes de tela - Inicio com licenca vitalicia nao tem a faixa; com teste tem, e o botao "Assinar" emite `adquirir`.
- [ ] Step 2-4: falha, implementa, passa; rodar `test_modo_consulta`, `test_licenciamento`, `test_teste_gratis`, `test_porta_entrada`.

### Task 8: Painel - tela Mensalidades

**Files:** Create `painel/js/telas/mensalidades.js`; Modify `painel/js/painel.js` (rota), `painel/index.html` (botao do menu), `painel/css/estilo.css` (so se faltar estilo).

- [ ] Step 1: tela com numeros, Para confirmar, Assinantes, Testes do plano e Precos e links, usando `ler`, `rpc`, `funcao("mensalidade/admin")`, `atualizar("mensalidade_config")`.
- [ ] Step 2: conferir servindo `painel/` com PostgREST de mentira (`supabase/tests/servidor_local.mjs`).

### Task 9: Landing - motor do plano

**Files:** Create `landingpage/js/plano.js`; Test `landingpage/tests/plano.test.mjs`

**Interfaces:** `criarPlano(config, {jaTem, tipo})`, `alternarAdicional(plano, codigo)`, `valorDoMes(plano)`, `assinavel(plano)`, `saudacao(cliente)`.

- [ ] Steps: teste falha, implementa, passa.

### Task 10: Landing - pagina nova

**Files:** Rewrite `landingpage/index.html`, `landingpage/css/estilo.css`, `landingpage/js/app.js`; Modify `landingpage/js/api.js` (`carregarMensalidade`, `cadastrar`), `landingpage/README.md`.

- [ ] Step 1: direcao visual (frontend-design + design-skill).
- [ ] Step 2: implementar secoes do spec; `kit.js`/`pagamento.js` ficam para as paginas que ainda os usam.
- [ ] Step 3: servir (`npm run servir`) e conferir no navegador em largura de celular e de computador; `npm test`.

### Task 11: Documentacao e verificacao final

**Files:** Modify `docs/licenciamento.md`, `supabase/functions/README.md`.

- [ ] Rodar todas as baterias (SQL, funcoes, landing, Python) e relatar o resultado real.
