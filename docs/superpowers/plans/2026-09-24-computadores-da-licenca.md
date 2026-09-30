# Computadores da Licença — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao dono da licença uma área no Hub onde ele lista, renomeia e solta os computadores da própria licença — inclusive um que não liga mais —, protegida por PIN com criação e recuperação por código de e-mail.

**Architecture:** Espelha o mecanismo já em produção de `pagamentos` (código de 6 dígitos por e-mail → sessão curta com o segredo só na memória do Hub → funções SQL de `service_role` atrás de uma Edge Function). Por cima dele entra o PIN, guardado com bcrypt, que encurta o acesso repetido. Tabelas novas e separadas das de pagamento.

**Tech Stack:** PostgreSQL (Supabase, pgcrypto), Deno/TypeScript (Edge Functions), Python 3.11 + PySide6 (Hub), Node `node:test` (testes das funções), PGlite (bateria SQL).

**Spec:** `docs/superpowers/specs/2026-09-24-computadores-da-licenca-design.md`

## Global Constraints

- **Nomes em português, sem acento, no código** (SQL, TS, Python). Comentários em português com acento normal.
- **Toda função SQL nova é `security definer` com `set search_path = ''`** e referência tabelas por `public.x`.
- **`grant execute` só para `service_role`.** A chave `anon` não enxerga tabela nem função desta área.
- **Toda função nova que tiver bloco `EXCEPTION` precisa chamar `dumtech_dentro_do_limite` TAMBÉM dentro do handler.** Bloco com `EXCEPTION` roda em subtransação; o rollback desfaz a contagem feita no corpo. Foi o bug corrigido em `20260924220000`.
- **Limites de taxa:** `admin_codigo_ip` 20/h, `admin_codigo_licenca` 5/h, `admin_entrar_ip` 30/h, `admin_acao_ip` 120/h.
- **PIN:** exatamente 6 dígitos. Hash com `crypt(pin, gen_salt('bf'))`. Nunca trafega nem é gravado em claro.
- **Trava:** 5 erros → 15 min; sequências seguintes dobram (30, 60), teto 60 min.
- **Código de e-mail:** 6 dígitos, 10 minutos, 5 tentativas.
- **Sessão:** 15 minutos. O segredo volta uma vez e vive só na memória do Hub.
- Rodar a bateria da raiz do projeto: `powershell -ExecutionPolicy Bypass -File tools\verificar_tudo.ps1`.

---

### Task 1: Migration — tabelas, PIN e sessão

**Files:**
- Create: `supabase/migrations/20260925090000_computadores_da_licenca.sql`
- Create: `supabase/tests/admin_computadores_test.sql`
- Modify: `supabase/tests/rodar.mjs` (só se ele listar os arquivos à mão — conferir antes)

**Interfaces:**
- Consumes: `public.licencas`, `public.ativacoes`, `public.dumtech_dentro_do_limite(text,text,int,interval)`, `public.dumtech_normalizar(text,int)`, `public.dumtech_ip_do_pedido()`
- Produces:
  - `dumtech_admin_hash(p_licenca uuid, p_texto text) returns text`
  - `dumtech_admin_codigo_email() returns text`
  - `dumtech_admin_licenca(p_chave text, p_maquina text) returns uuid`
  - `dumtech_admin_sessao_valida(p_licenca uuid, p_sessao text) returns boolean`
  - `dumtech_admin_pedir_codigo(p_chave text, p_maquina text, p_ip text) returns jsonb`
  - `dumtech_admin_criar_pin(p_chave text, p_maquina text, p_computador text, p_codigo text, p_pin text, p_ip text) returns jsonb`
  - `dumtech_admin_entrar(p_chave text, p_maquina text, p_computador text, p_pin text, p_ip text) returns jsonb`
  - `dumtech_admin_trocar_pin(p_chave text, p_sessao text, p_atual text, p_novo text) returns jsonb`
  - `dumtech_admin_listar(p_chave text, p_sessao text) returns jsonb`
  - `dumtech_admin_renomear(p_chave text, p_sessao text, p_maquina text, p_apelido text) returns jsonb`
  - `dumtech_admin_soltar(p_chave text, p_sessao text, p_maquina text) returns jsonb`
  - Retorno de sucesso de `criar_pin`/`entrar`: `{"ok": true, "sessao": "<64 hex>", "expira_em": "<iso>"}`
  - Retorno de erro padrão: `{"ok": false, "erro": "<codigo>", "mensagem": "<texto>"}`
  - Códigos de erro: `nao_autorizado`, `sem_pin`, `ja_tem_pin`, `pin_invalido`, `pin_errado`, `bloqueado`, `codigo_errado`, `codigo_expirado`, `sessao_invalida`, `nao_encontrada`, `muitas_tentativas`

- [ ] **Step 1: Escrever a bateria SQL que falha**

Criar `supabase/tests/admin_computadores_test.sql` seguindo o formato de `pagamentos_test.sql` (transação que desfaz tudo no fim):

```sql
-- =============================================================================
-- Teste da migration 20260925090000: computadores da licenca.
-- Roda dentro de uma transacao e desfaz tudo no fim.
-- =============================================================================
begin;

do $$
declare
    v_cliente  uuid;
    v_chave    text;
    v_licenca  uuid;
    v_maq_a    constant text := 'AAAA-BBBB-CCCC-DDDD';
    v_maq_b    constant text := 'EEEE-FFFF-GGGG-HHHH';
    v_pc       constant text := '0123456789abcdef0123456789abcdef';
    v_ip       constant text := '203.0.113.7';
    r          jsonb;
    v_codigo   text;
    v_sessao   text;
    v_i        integer;
begin
    insert into public.clientes (nome, email) values ('ZZ Computadores', 'ZZ.Comp@Teste.local')
    returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);
    select id into v_licenca from public.licencas where chave = v_chave;
    update public.licencas set max_computadores = 3 where id = v_licenca;
    perform public.dumtech_ativar_licenca(v_chave, v_maq_a, 'balcao');
    perform public.dumtech_ativar_licenca(v_chave, v_maq_b, 'escritorio');

    -- ------------------------------------------- quem nao e da licenca cai ---
    r := public.dumtech_admin_pedir_codigo(v_chave, 'ZZZZ-ZZZZ-ZZZZ-ZZZZ', v_ip);
    assert r->>'erro' = 'nao_autorizado', 'computador nao ativado pediu codigo: ' || r::text;
    r := public.dumtech_admin_pedir_codigo('AAAA-AAAA-AAAA-AAAA', v_maq_a, v_ip);
    assert r->>'erro' = 'nao_autorizado', 'chave inexistente respondeu diferente: ' || r::text;

    -- ---------------------------------------- sem PIN ainda: entrar recusa ---
    r := public.dumtech_admin_entrar(v_chave, v_maq_a, v_pc, '123456', v_ip);
    assert r->>'erro' = 'sem_pin', 'entrou sem PIN cadastrado: ' || r::text;

    -- ------------------------------------------------- criar PIN sem codigo --
    r := public.dumtech_admin_criar_pin(v_chave, v_maq_a, v_pc, '000000', '123456', v_ip);
    assert r->>'erro' = 'codigo_errado', 'criou PIN sem codigo valido: ' || r::text;

    -- ------------------------------------------------------- o caminho feliz --
    r := public.dumtech_admin_pedir_codigo(v_chave, v_maq_a, v_ip);
    assert (r->>'ok')::boolean, 'pedir codigo falhou: ' || r::text;
    -- o codigo volta em claro para quem chama (a Edge Function precisa dele
    -- para enviar o e-mail); o banco guarda so o hash
    v_codigo := r->>'codigo';
    assert v_codigo ~ '^[0-9]{6}$', 'codigo fora do formato: ' || coalesce(v_codigo, '(nulo)');
    r := public.dumtech_admin_criar_pin(v_chave, v_maq_a, v_pc, v_codigo, '135790', v_ip);
    assert (r->>'ok')::boolean, 'criar PIN falhou: ' || r::text;
    v_sessao := r->>'sessao';
    assert length(v_sessao) = 64, 'sessao deveria ter 64 hex: ' || coalesce(v_sessao, '(nulo)');

    -- --------------------------------------------------- PIN de 6 digitos ----
    r := public.dumtech_admin_criar_pin(v_chave, v_maq_a, v_pc, v_codigo, '12ab56', v_ip);
    assert r->>'erro' in ('pin_invalido', 'codigo_errado'), 'PIN com letra passou: ' || r::text;

    -- ------------------------------------------------------------- listar ----
    r := public.dumtech_admin_listar(v_chave, v_sessao);
    assert (r->>'ok')::boolean, 'listar falhou: ' || r::text;
    assert jsonb_array_length(r->'computadores') = 2,
           'deveriam ser 2 computadores: ' || r::text;

    -- sessao de outra licenca nao ve nada
    r := public.dumtech_admin_listar(v_chave, repeat('f', 64));
    assert r->>'erro' = 'sessao_invalida', 'sessao inventada passou: ' || r::text;

    -- ----------------------------------------------------------- renomear ----
    r := public.dumtech_admin_renomear(v_chave, v_sessao, v_maq_b, 'Escritorio 2');
    assert (r->>'ok')::boolean, 'renomear falhou: ' || r::text;
    assert exists (select 1 from public.ativacoes
                    where licenca_id = v_licenca and maquina = v_maq_b
                      and apelido = 'Escritorio 2'), 'o apelido nao gravou';

    -- ------------------------------------------------------------- soltar ----
    r := public.dumtech_admin_soltar(v_chave, v_sessao, v_maq_b);
    assert (r->>'ok')::boolean, 'soltar falhou: ' || r::text;
    assert not exists (select 1 from public.ativacoes
                        where licenca_id = v_licenca and maquina = v_maq_b),
           'a vaga nao foi liberada';
    r := public.dumtech_admin_soltar(v_chave, v_sessao, 'XXXX-XXXX-XXXX-XXXX');
    assert r->>'erro' = 'nao_encontrada', 'soltar inexistente respondeu diferente: ' || r::text;

    -- -------------------------------------------- 5 erros de PIN travam -----
    for v_i in 1..5 loop
        r := public.dumtech_admin_entrar(v_chave, v_maq_a, v_pc, '999999', v_ip);
    end loop;
    assert r->>'erro' in ('pin_errado', 'bloqueado'), 'erro inesperado: ' || r::text;
    r := public.dumtech_admin_entrar(v_chave, v_maq_a, v_pc, '135790', v_ip);
    assert r->>'erro' = 'bloqueado', 'PIN certo passou durante a trava: ' || r::text;

    -- a trava solta quando o prazo vence
    update public.licenca_pin set bloqueado_ate = now() - interval '1 minute'
     where licenca_id = v_licenca;
    r := public.dumtech_admin_entrar(v_chave, v_maq_a, v_pc, '135790', v_ip);
    assert (r->>'ok')::boolean, 'PIN certo recusado apos a trava vencer: ' || r::text;

    raise notice 'admin_computadores_test: ok';
end $$;

rollback;
```

O teste lê o código do **retorno** de `dumtech_admin_pedir_codigo` — que o devolve em claro porque a Edge Function precisa dele para montar o e-mail. O banco guarda só o hash, e o código em claro nunca chega ao Hub: a Edge Function o consome e devolve apenas o e-mail mascarado.

- [ ] **Step 2: Rodar e ver falhar**

```
cd supabase && node tests/rodar.mjs
```

Esperado: `FALHOU admin_computadores_test.sql` com "function public.dumtech_admin_pedir_codigo does not exist".

- [ ] **Step 3: Escrever a migration**

Criar `supabase/migrations/20260925090000_computadores_da_licenca.sql` com, nesta ordem:

1. **Cabeçalho** explicando o buraco (vaga presa quando o computador morre) e o desenho — copiar o tom do cabeçalho de `20260916120000_pagamentos_protegidos.sql`.

2. **As três tabelas**, exatamente como no spec (`licenca_pin`, `admin_codigos`, `admin_sessoes`), cada uma com `alter table ... enable row level security` e **nenhuma policy** — ninguém além do `service_role` (que ignora RLS) precisa vê-las.

3. **Os auxiliares:**

```sql
create or replace function public.dumtech_admin_hash(p_licenca uuid, p_texto text)
returns text language sql immutable set search_path = '' as $$
    select encode(sha256(convert_to(p_licenca::text || ':' || p_texto, 'UTF8')), 'hex');
$$;

-- 6 digitos dos bits aleatorios do gen_random_uuid (vies desprezivel)
create or replace function public.dumtech_admin_codigo_email()
returns text language sql volatile set search_path = '' as $$
    select lpad(((('x' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 8))::bit(32)::bigint) % 1000000)::text, 6, '0');
$$;

-- a licenca ATIVA a que este computador pertence (ou null)
create or replace function public.dumtech_admin_licenca(p_chave text, p_maquina text)
returns uuid language sql stable security definer set search_path = '' as $$
    select l.id from public.licencas l
      join public.ativacoes a on a.licenca_id = l.id
     where l.chave = public.dumtech_normalizar(p_chave, 32)
       and a.maquina = public.dumtech_normalizar(p_maquina, 64)
       and public.dumtech_situacao_licenca(l.status, l.expira_em) = 'ativa';
$$;

create or replace function public.dumtech_admin_sessao_valida(p_licenca uuid, p_sessao text)
returns boolean language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from public.admin_sessoes
         where sessao_hash = public.dumtech_admin_hash(p_licenca, coalesce(p_sessao, ''))
           and licenca_id = p_licenca
           and expira_em > now());
$$;
```

4. **`dumtech_admin_pedir_codigo`** — limite por IP (20/h) e por licença (5/h); resolve a licença por `dumtech_admin_licenca`; gera o código, grava só o hash com `expira_em = now() + interval '10 minutes'`; devolve `{ok, email}` com o e-mail **do cliente da licença** (é a Edge Function que envia).

5. **`dumtech_admin_criar_pin`** — recusa com `ja_tem_pin` se `licenca_pin` já existir; valida `p_pin ~ '^[0-9]{6}$'` senão `pin_invalido`; confere o código (não usado, não expirado, tentativas < 5, hash bate) senão `codigo_errado`/`codigo_expirado`; marca o código como usado; grava `pin_hash = crypt(p_pin, gen_salt('bf'))`; abre sessão e devolve o segredo.

6. **`dumtech_admin_entrar`** — limite por IP (30/h); `sem_pin` se não houver linha; `bloqueado` se `bloqueado_ate > now()`; confere com `pin_hash = crypt(p_pin, pin_hash)`. Errou: `erros = erros + 1` e, ao chegar em 5, `bloqueado_ate = now() + (15 * 2^(travas anteriores)) min` com teto de 60, zerando `erros`. Acertou: zera `erros` e `bloqueado_ate`, abre sessão.

7. **`dumtech_admin_trocar_pin`** — exige sessão válida **e** o PIN atual correto; valida o formato do novo.

8. **`dumtech_admin_listar` / `renomear` / `soltar`** — todas começam exigindo `dumtech_admin_sessao_valida`, senão `sessao_invalida`; limite `admin_acao_ip` 120/h. `listar` devolve `{"ok":true,"computadores":[{maquina, apelido, ativado_em, ultima_checagem}]}`. `soltar` faz `delete from public.ativacoes` e devolve `nao_encontrada` se nada saiu.

9. **Os grants**, fechando a porta:

Fechar com `revoke execute ... from public, anon, authenticated;` e `grant execute ... to service_role;` para cada função, e `notify pgrst, 'reload schema';`.

- [ ] **Step 4: Rodar a bateria até passar**

```
cd supabase && node tests/rodar.mjs
```

Esperado: `13/13 baterias SQL passaram.`

- [ ] **Step 5: Commit**

```bash
git add "supabase/migrations/20260925090000_computadores_da_licenca.sql" "supabase/tests/admin_computadores_test.sql"
git commit -m "feat(licenca): tabelas e funcoes da area de Computadores"
```

---

### Task 2: Edge Function `computadores`

**Files:**
- Create: `supabase/functions/computadores/nucleo.ts`
- Create: `supabase/functions/computadores/index.ts`
- Create: `supabase/functions/tests/computadores.test.mjs`

**Interfaces:**
- Consumes: as funções SQL da Task 1 via `rpc`; `enviar`/`configurado` de `../enviar-chave/correio.ts`
- Produces:
  - `rotaDe(caminho: string): Rota | ""` com `Rota = "codigo" | "criar-pin" | "entrar" | "trocar-pin" | "listar" | "renomear" | "soltar"`
  - `ipDoVisitante(cabecalhos: Headers): string`
  - `mascararEmail(email: string): string`
  - `montarEmailCodigo(codigo: string): { assunto: string; texto: string; html: string }`
  - `tratar(rota: Rota, corpo: unknown, ambiente: Ambiente, ip: string): Promise<Resposta>`
  - `Ambiente = { rpc: Rpc; enviarEmail: (m: Mensagem) => Promise<boolean> }`
  - `Resposta = { status: number; corpo: Record<string, unknown> }`

- [ ] **Step 1: Escrever os testes que falham**

`supabase/functions/tests/computadores.test.mjs`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { mascararEmail, montarEmailCodigo, rotaDe, tratar } from "../computadores/nucleo.ts";

test("rotas conhecidas e so elas", () => {
  for (const boa of ["codigo", "criar-pin", "entrar", "trocar-pin", "listar", "renomear", "soltar"]) {
    assert.equal(rotaDe(`/functions/v1/computadores/${boa}`), boa);
  }
  assert.equal(rotaDe("/functions/v1/computadores/apagar-tudo"), "");
  assert.equal(rotaDe("/functions/v1/computadores"), "");
});

test("o e-mail mascarado nao entrega o endereco inteiro", () => {
  const mascarado = mascararEmail("eduardo@dumtechsolution.com");
  assert.match(mascarado, /^e\*+o@dumtechsolution\.com$/);
  assert.ok(!mascarado.includes("eduardo"));
});

test("o codigo vai por e-mail e NUNCA na resposta ao Hub", async () => {
  const enviados = [];
  const ambiente = {
    rpc: async () => ({ ok: true, codigo: "135790", email: "dono@loja.com" }),
    enviarEmail: async (m) => { enviados.push(m); return true; },
  };
  const r = await tratar("codigo", { chave: "AAAA", maquina: "BBBB" }, ambiente, "203.0.113.7");
  assert.equal(r.status, 200);
  assert.equal(r.corpo.ok, true);
  assert.ok(!JSON.stringify(r.corpo).includes("135790"), "o codigo vazou para o Hub");
  assert.equal(r.corpo.email, "d***o@loja.com");
  assert.equal(enviados.length, 1);
  assert.ok(enviados[0].texto.includes("135790"));
});

test("erro do banco volta como veio, sem inventar sucesso", async () => {
  const ambiente = {
    rpc: async () => ({ ok: false, erro: "bloqueado", mensagem: "Espere 15 minutos." }),
    enviarEmail: async () => true,
  };
  const r = await tratar("entrar", { chave: "A", maquina: "B", computador: "c".repeat(32), pin: "111111" }, ambiente, "1.2.3.4");
  assert.equal(r.corpo.erro, "bloqueado");
  assert.notEqual(r.corpo.ok, true);
});

test("banco fora do ar vira 502, nunca um ok", async () => {
  const ambiente = { rpc: async () => null, enviarEmail: async () => true };
  const r = await tratar("listar", { chave: "A", sessao: "f".repeat(64) }, ambiente, "1.2.3.4");
  assert.equal(r.status, 502);
  assert.notEqual(r.corpo.ok, true);
});
```

- [ ] **Step 2: Rodar e ver falhar**

```
cd supabase/functions && node --test tests/computadores.test.mjs
```

Esperado: FAIL — `Cannot find module '../computadores/nucleo.ts'`.

- [ ] **Step 3: Escrever `nucleo.ts`**

Espelhar `supabase/functions/pagamentos/nucleo.ts`: sem nada de Deno, tudo por parâmetro. `tratar()` faz um `switch` na rota, chama a função SQL correspondente e:
- na rota `codigo`, pega `codigo` e `email` do retorno, **envia o e-mail**, e devolve ao Hub só `{ok: true, email: mascararEmail(email)}` — o código nunca volta;
- em qualquer rota, `rpc` devolvendo `null` vira `{status: 502, corpo: {ok: false, erro: "servidor"}}`;
- o retorno do banco com `ok: false` é repassado como veio, com status 200.

`montarEmailCodigo(codigo)` devolve assunto/texto/html curtos, com o código em destaque e a validade de 10 minutos. Seguir o tom de `enviar-chave/nucleo.ts:montarEmail` e **escapar** qualquer texto que vá para o HTML.

- [ ] **Step 4: Escrever `index.ts`**

Espelhar `supabase/functions/pagamentos/index.ts`: lê `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / as chaves de e-mail do ambiente, monta o `Ambiente`, resolve a rota e responde. `--no-verify-jwt` **não** se aplica aqui: o Hub manda a `anon key`, então a verificação padrão serve.

- [ ] **Step 5: Rodar até passar**

```
cd supabase/functions && node --test tests/computadores.test.mjs
```

Esperado: `pass 5`, `fail 0`.

- [ ] **Step 6: Commit**

```bash
git add supabase/functions/computadores supabase/functions/tests/computadores.test.mjs
git commit -m "feat(licenca): Edge Function computadores"
```

---

### Task 3: `core/computadores.py` — o serviço no Hub

**Files:**
- Create: `src/dumtech/core/computadores.py`
- Create: `tests/test_computadores.py`

**Interfaces:**
- Consumes: `SupabaseClient.funcao(nome, corpo)`, `core.licensing.License` (por `licenca()`), `core.assinatura.computador_id()`
- Produces:
  - `SESSAO_SEGUNDOS = 14 * 60`
  - `class Computador` (dataclass): `maquina: str`, `apelido: str`, `ativado_em: str`, `ultima_checagem: str`, `este: bool`
  - `class ComputadoresError(Exception)`: `.codigo: str`
  - `class ComputadoresService`:
    - `pode_usar -> bool` (licença ativa e vinda do servidor)
    - `tem_pin -> bool | None` (None = ainda não perguntou)
    - `liberado -> bool`, `segundos_restantes() -> int`, `trancar() -> None`
    - `pedir_codigo() -> str` (devolve o e-mail mascarado)
    - `criar_pin(codigo: str, pin: str) -> None`
    - `entrar(pin: str) -> None`
    - `trocar_pin(atual: str, novo: str) -> None`
    - `listar() -> list[Computador]`
    - `renomear(maquina: str, apelido: str) -> None`
    - `soltar(maquina: str) -> None`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_computadores.py`:

```python
"""A area de Computadores no Hub: sessao curta e nada de segredo em disco."""
from __future__ import annotations

import unittest
from unittest import mock

from dumtech.core.computadores import (
    SESSAO_SEGUNDOS, ComputadoresError, ComputadoresService,
)


class ClienteFalso:
    def __init__(self, resposta=None):
        self.resposta = resposta or {"ok": True}
        self.chamadas = []

    def funcao(self, nome, corpo=None):
        self.chamadas.append((nome, corpo or {}))
        return self.resposta


def licenca_ativa(**extra):
    return mock.Mock(ativa=True, key="AAAA-BBBB-CCCC-DDDD", machine="MAQ",
                     source="supabase", **extra)


class ServicoTestCase(unittest.TestCase):
    def servico(self, resposta=None, relogio=None):
        self.cliente = ClienteFalso(resposta)
        return ComputadoresService(
            licenca=licenca_ativa, client=self.cliente,
            relogio=relogio or (lambda: 1000.0))

    def test_sem_licenca_do_servidor_nao_tenta_rede(self):
        servico = ComputadoresService(
            licenca=lambda: mock.Mock(ativa=False, key="", machine="", source="local"),
            client=ClienteFalso())
        self.assertFalse(servico.pode_usar)

    def test_entrar_guarda_a_sessao_so_na_memoria(self):
        servico = self.servico({"ok": True, "sessao": "f" * 64})
        servico.entrar("135790")
        self.assertTrue(servico.liberado)
        self.assertEqual(servico.segundos_restantes(), SESSAO_SEGUNDOS)
        # o PIN nunca fica guardado
        self.assertNotIn("135790", repr(servico.__dict__))

    def test_a_sessao_expira_sozinha(self):
        agora = [1000.0]
        servico = self.servico({"ok": True, "sessao": "f" * 64}, relogio=lambda: agora[0])
        servico.entrar("135790")
        agora[0] += SESSAO_SEGUNDOS + 1
        self.assertFalse(servico.liberado)
        self.assertEqual(servico.segundos_restantes(), 0)

    def test_trancar_apaga_o_segredo(self):
        servico = self.servico({"ok": True, "sessao": "f" * 64})
        servico.entrar("135790")
        servico.trancar()
        self.assertFalse(servico.liberado)
        with self.assertRaises(ComputadoresError):
            servico.listar()

    def test_erro_do_servidor_vira_excecao_com_codigo(self):
        servico = self.servico({"ok": False, "erro": "bloqueado",
                                "mensagem": "Espere alguns minutos."})
        with self.assertRaises(ComputadoresError) as caso:
            servico.entrar("999999")
        self.assertEqual(caso.exception.codigo, "bloqueado")
        self.assertIn("Espere", str(caso.exception))

    def test_listar_marca_qual_e_este_computador(self):
        servico = self.servico({"ok": True, "sessao": "f" * 64})
        servico.entrar("135790")
        self.cliente.resposta = {"ok": True, "computadores": [
            {"maquina": "MAQ", "apelido": "Balcao", "ativado_em": "2026-01-01T00:00:00Z",
             "ultima_checagem": "2026-09-01T00:00:00Z"},
            {"maquina": "OUTRA", "apelido": "", "ativado_em": "2026-01-01T00:00:00Z",
             "ultima_checagem": "2026-02-01T00:00:00Z"},
        ]}
        lista = servico.listar()
        self.assertEqual([c.este for c in lista], [True, False])

    def test_pin_fora_do_formato_nem_chega_no_servidor(self):
        servico = self.servico()
        for ruim in ("12345", "1234567", "12ab56", ""):
            with self.subTest(pin=ruim), self.assertRaises(ComputadoresError):
                servico.entrar(ruim)
        self.assertEqual(self.cliente.chamadas, [])
```

- [ ] **Step 2: Rodar e ver falhar**

```
.venv\Scripts\python.exe -m unittest tests.test_computadores -v
```

Esperado: `ModuleNotFoundError: No module named 'dumtech.core.computadores'`.

- [ ] **Step 3: Escrever `core/computadores.py`**

Espelhar `src/dumtech/core/pagamentos.py`:
- cabeçalho explicando que **não existe código de reserva em disco**: sem internet a área não abre;
- `_sessao: str` só na memória, zerado por `trancar()`;
- `_acesso: Acesso | None` com `expira` em `time.monotonic()`;
- o formato do PIN é conferido **antes** de chamar a rede (`^[0-9]{6}$`), levantando `ComputadoresError("...", "pin_invalido")`;
- toda chamada passa `chave`, `maquina` e — onde a função SQL pedir — `computador` (de `assinatura.computador_id()`) e a `sessao`;
- resposta sem `ok` vira `ComputadoresError` com o `erro` e a `mensagem` do servidor.

- [ ] **Step 4: Rodar até passar**

```
.venv\Scripts\python.exe -m unittest tests.test_computadores -v
```

Esperado: `OK`, 7 testes.

- [ ] **Step 5: Commit**

```bash
git add src/dumtech/core/computadores.py tests/test_computadores.py
git commit -m "feat(licenca): servico de Computadores no Hub"
```

---

### Task 4: A tela `ComputadoresView`

**Files:**
- Create: `src/dumtech/hub/views/computadores_view.py`
- Create: `tests/test_computadores_tela.py`

**Interfaces:**
- Consumes: `ComputadoresService` (Task 3), `ui.widgets.common.Card/EmptyState/label`, `ui.widgets.buttons.Button`, `ui.widgets.confirmar`
- Produces:
  - `class ComputadoresView(QWidget)` com `__init__(self, service, parent=None)`
  - Sinais: `licenca_removida = Signal()` (emitido quando o cliente solta ESTE computador)
  - Métodos: `refresh()`, `trancar()`, `hideEvent(evento)`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_computadores_tela.py`:

```python
"""A tela de Computadores: trancada por padrao, destrancada com PIN."""
from __future__ import annotations

import unittest
from unittest import mock

from PySide6.QtWidgets import QApplication, QLabel

from dumtech.core.computadores import Computador
from dumtech.hub.views.computadores_view import ComputadoresView


class TelaTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def servico(self, liberado=False, computadores=()):
        servico = mock.Mock()
        servico.pode_usar = True
        servico.tem_pin = True
        servico.liberado = liberado
        servico.segundos_restantes.return_value = 840 if liberado else 0
        servico.listar.return_value = list(computadores)
        return servico

    def textos(self, tela):
        return [w.text() for w in tela.findChildren(QLabel)]

    def test_trancada_nao_mostra_computador_nenhum(self):
        tela = ComputadoresView(self.servico(
            liberado=False,
            computadores=[Computador("MAQ", "Balcao", "", "", True)]))
        tela.refresh()
        self.assertNotIn("Balcao", " ".join(self.textos(tela)),
                         "a lista vazou com a area trancada")

    def test_liberada_mostra_a_lista(self):
        tela = ComputadoresView(self.servico(
            liberado=True,
            computadores=[Computador("MAQ", "Balcao", "", "", True)]))
        tela.refresh()
        self.assertIn("Balcao", " ".join(self.textos(tela)))

    def test_sair_da_tela_tranca(self):
        servico = self.servico(liberado=True)
        tela = ComputadoresView(servico)
        tela.refresh()
        tela.hide()
        servico.trancar.assert_called_once()
```

- [ ] **Step 2: Rodar e ver falhar**

```
.venv\Scripts\python.exe -m unittest tests.test_computadores_tela -v
```

Esperado: `ModuleNotFoundError`.

- [ ] **Step 3: Escrever a tela**

Espelhar `src/dumtech/hub/views/pagamentos_view.py`:
- `_pagina_trancada()` — campo de PIN (6 dígitos, `QLineEdit.EchoMode.Password`, `setMaxLength(6)`), botão Entrar, link "Esqueci o PIN" e, quando `service.tem_pin` é falso, o caminho de criação (pedir código → digitar código + PIN novo);
- `_pagina_liberada()` — a lista em `Card`s, com apelido editável, "última vez visto" em texto humano (`ui.format`), o selo "este computador", e o botão de soltar;
- `_tique()` num `QTimer` de 1 s mostrando a contagem regressiva; ao zerar, `trancar()` e voltar para a página trancada;
- `hideEvent` chama `self.trancar()`;
- soltar pede confirmação com o nome do computador. **Se a máquina for a deste computador**, o texto do aviso é outro ("os aplicativos vão fechar neste computador") e, ao confirmar, emite `licenca_removida`;
- toda chamada de rede vai por `ui.tasks.executar` para não travar a janela.

- [ ] **Step 4: Rodar até passar**

```
.venv\Scripts\python.exe -m unittest tests.test_computadores_tela -v
```

Esperado: `OK`, 3 testes.

- [ ] **Step 5: Commit**

```bash
git add src/dumtech/hub/views/computadores_view.py tests/test_computadores_tela.py
git commit -m "feat(licenca): tela de Computadores"
```

---

### Task 5: Ligar no Hub

**Files:**
- Modify: `src/dumtech/hub/main_window.py` (criar o serviço, a view e a entrada no trilho, ao lado de Licença)
- Modify: `src/dumtech/hub/views/license_view.py` (o botão "Gerenciar computadores" quando `max_machines > 1`)
- Modify: `tests/test_licenciamento.py` (o teste da entrada nova)

**Interfaces:**
- Consumes: `ComputadoresService` (Task 3), `ComputadoresView` (Task 4)
- Produces: `PAGINA_COMPUTADORES` (constante de índice, ao lado de `PAGINA_INICIO`)

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar a `tests/test_licenciamento.py`:

```python
def test_licenca_de_um_computador_nao_oferece_a_area(self) -> None:
    """Gerenciar vagas so faz sentido com mais de uma."""
    hub = self.montar(max_machines=1)
    botoes = [b.text().strip() for b in hub.license_view.findChildren(Button)]
    self.assertNotIn("Gerenciar computadores", botoes)

def test_licenca_de_varios_computadores_abre_a_area(self) -> None:
    hub = self.montar(max_machines=3)
    botoes = [b.text().strip() for b in hub.license_view.findChildren(Button)]
    self.assertIn("Gerenciar computadores", botoes)
```

> Conferir como `tests/test_licenciamento.py` monta o Hub hoje e ajustar `self.montar(...)` para aceitar `max_machines`; se não houver helper, criar um seguindo o padrão do arquivo.

- [ ] **Step 2: Rodar e ver falhar**

```
.venv\Scripts\python.exe -m unittest tests.test_licenciamento -v
```

Esperado: FAIL — "Gerenciar computadores" não está entre os botões.

- [ ] **Step 3: Ligar**

Em `main_window.py`: instanciar `ComputadoresService(licenca=lambda: self.license_service.current, client=SupabaseClient())`, criar a `ComputadoresView`, acrescentar à `stack` com a constante `PAGINA_COMPUTADORES`, e conectar `licenca_removida` ao mesmo caminho que hoje trata "Remover licença deste computador".

Em `license_view.py`: o botão "Gerenciar computadores" aparece só quando `atual.max_machines > 1`, e emite um sinal novo que o `main_window` liga à troca de página.

- [ ] **Step 4: Rodar a bateria inteira**

```
powershell -ExecutionPolicy Bypass -File tools\verificar_tudo.ps1
```

Esperado: `Tudo passou.`

- [ ] **Step 5: Commit**

```bash
git add src/dumtech/hub/main_window.py src/dumtech/hub/views/license_view.py tests/test_licenciamento.py
git commit -m "feat(licenca): area de Computadores no trilho do Hub"
```

---

### Task 6: Publicar

**Files:** nenhum — é operação.

- [ ] **Step 1: Aplicar a migration**

```
npx supabase db push
```

- [ ] **Step 2: Publicar a Edge Function**

```
npx supabase functions deploy computadores
```

- [ ] **Step 3: Conferir que o anon continua sem enxergar nada**

```bash
ANON=$(grep -A4 'SUPABASE_ANON' landingpage/js/config.js | grep -o '"[A-Za-z0-9._-]*"' | tr -d '"' | tr -d '\n')
for t in licenca_pin admin_codigos admin_sessoes; do
  curl -s -o /dev/null -w "$t %{http_code}\n" \
    -H "apikey: $ANON" -H "Authorization: Bearer $ANON" \
    "https://kpiyhhmtteojqxhhmcyr.supabase.co/rest/v1/$t?select=*&limit=1"
done
```

Esperado: `401` nas três.

- [ ] **Step 4: Lançar a versão**

Mudar `__version__` em `src/dumtech/__init__.py` e:

```
powershell -ExecutionPolicy Bypass -File tools\lancar_versao.ps1 -Notas "Gerencie os computadores da sua licenca"
```

---

## Notas de execução

- **Nunca `git add -A`** neste projeto: o repositório tem raiz em `C:/Users/User`. Versionar sempre caminhos explícitos do projeto.
- A CLI do Supabase precisa estar ligada ao projeto (`npx supabase link --project-ref kpiyhhmtteojqxhhmcyr`). A pasta `supabase/.temp/` guarda esse vínculo e é ignorada pelo git — apagá-la desliga a CLI.
- Rodar `tools\verificar_tudo.ps1` **da raiz do projeto**; de dentro de `supabase/` a CLI não acha o `project-ref`.
