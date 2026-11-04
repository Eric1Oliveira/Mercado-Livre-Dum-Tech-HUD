# Controle da mensalidade - Plano de implementacao

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** planos prontos, preco por adicional, ficha do assinante com historico, textos da landing com rascunho/publicar e promocoes (faixa, de/por, cupom), tudo editavel no painel.

**Architecture:** uma migration nova (`20261104120000_controle_mensalidade.sql`) com as tabelas, a vitrine publica numa chamada so e as acoes de admin (que gravam eventos). A Edge Function `mensalidade` ganha as acoes novas com `avisar`. A landing le tudo da vitrine (com os textos de hoje como reserva). O painel ganha o grupo Mensalidade com 4 telas.

**Tech Stack:** Postgres/PL-pgSQL (PGlite nos testes), Edge Functions TS (Node nos testes), HTML/CSS/JS puro.

**Spec:** `docs/superpowers/specs/2026-11-04-controle-da-mensalidade-design.md`

## Global Constraints

- Vitalicia: nenhuma funcao daqui altera, lista ou cobra licenca vitalicia.
- Preco e link SEMPRE calculados no servidor; o navegador so mostra.
- Texto do painel entra no site como texto puro (`textContent`), com limite de tamanho.
- Listas do painel: mais recente primeiro (historico).
- Textos para o cliente: amigaveis, sem termo tecnico.
- Sem versao nova do Hub. Sem commit. `db push` e deploy de funcao sao do Eric.

---

### Task 1: Banco - modulos, planos, combinacoes, cupons, eventos, conteudo e avisos
Files: `supabase/migrations/20261104120000_controle_mensalidade.sql`, `supabase/tests/controle_mensalidade_test.sql`; ajustar `mensalidade_test.sql` e as listas de funcoes publicas em `licenciamento_test.sql` / `porta_entrada_test.sql`.
Produces: `mensalidade_modulos`, `mensalidade_planos`, `mensalidade_combinacoes`, `mensalidade_cupons`, `assinatura_eventos`, `landing_conteudo`, `landing_publicacoes`, `landing_avisos`; `dumtech_chave_combinacao(text[])`, `dumtech_link_valido(text)`, `dumtech_mensalidade_publica()` (vitrine completa), `dumtech_cupom_publico(text)`, `dumtech_cadastrar_mensal(..., p_plano uuid, p_cupom text)`, `dumtech_ajustar_assinatura`, `dumtech_ativar_assinatura`, `dumtech_reabrir_assinatura`, `dumtech_publicar_landing()`, `dumtech_voltar_landing(uuid)`; visoes `painel_mensalidades` (com plano e valor gravado), `painel_assinatura_pedidos` (com plano, modulos, cupom), `painel_assinatura_eventos`, `painel_cupons`, `painel_combinacoes`.
- [ ] Teste SQL falhando -> migration -> 20/20 baterias passam.

### Task 2: Edge Function - acoes ajustar/ativar/reabrir, `avisar`, cadastro com plano e cupom
Files: `supabase/functions/mensalidade/nucleo.ts`, `supabase/functions/tests/mensalidade.test.mjs`.
- [ ] Teste falhando -> codigo -> `npm test` passa.

### Task 3: Landing - motor (planos, combinacoes, promo, cupom, conteudo com marcadores)
Files: `landingpage/js/plano.js`, `landingpage/js/conteudo.js` (novo), testes `plano.test.mjs`, `conteudo.test.mjs`.
- [ ] Teste falhando -> codigo -> `npm test` passa.

### Task 4: Landing - pagina (cartoes de plano, monte o seu, cupom, faixa de aviso, textos, previa)
Files: `landingpage/index.html`, `landingpage/css/inicio.css`, `landingpage/js/app.js`, `landingpage/js/api.js`.
- [ ] Conferir no navegador (computador e celular), com servidor de mentira.

### Task 5: Painel - grupo Mensalidade (Assinantes + ficha, Planos e precos, Textos do site, Promocoes)
Files: `painel/js/telas/mensalidades.js` (assinantes + ficha), `painel/js/telas/planos.js`, `painel/js/telas/textos-site.js`, `painel/js/telas/promocoes.js`, `painel/js/painel.js`, `painel/index.html`.
- [ ] Conferir no navegador com servidor de mentira.

### Task 6: Publicacao e documentacao
Files: `tools/publicar_site.ps1` (titulo/descricao publicados no HTML), `docs/licenciamento.md`, `landingpage/README.md`.
- [ ] Todas as baterias (SQL, funcoes, landing, Python) e relato do resultado real.
