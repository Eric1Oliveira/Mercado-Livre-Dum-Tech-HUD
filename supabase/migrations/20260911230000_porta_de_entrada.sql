-- =============================================================================
-- 20260911230000 - o Hub como porta de entrada do cliente
--
-- O QUE ENTRA
--   clientes        ganha `origem` (venda | hub), `atualizado_em` e e-mail unico
--   comunicados     ofertas e recados que o Hub mostra no Inicio
--   compra_tokens   o codigo curto que a landing page troca por nome/e-mail
--
-- QUATRO FUNCOES NOVAS PARA O APLICATIVO (chave anon):
--   dumtech_identificar_cliente(nome, email)  -> cadastra quem instalou o Hub
--   dumtech_comunicados(chave)                -> ofertas de hoje, ja filtradas
--   dumtech_token_compra(chave, maquina, nome, email) -> codigo de 15 minutos
--   dumtech_abrir_compra(token)               -> a landing troca o codigo
--
-- SEGURANCA - a regra que desenha estas funcoes:
--   nenhuma delas devolve dado de cliente que o proprio chamador ja nao tenha
--   informado. `identificar_cliente` responde igual para e-mail novo e para
--   e-mail que ja existe (senao viraria uma maquina de descobrir quem compra da
--   DumTech), e o token so carrega produtos de verdade quando a prova e a chave
--   de licenca com o computador ativado.
-- =============================================================================

-- ========================================================== 1. CLIENTES =====
alter table public.clientes add column if not exists origem text not null default 'venda';
alter table public.clientes add column if not exists atualizado_em timestamptz not null default now();

comment on column public.clientes.origem is
    'venda = cadastrado pela DumTech ao vender; hub = se cadastrou sozinho no primeiro acesso do Hub.';

alter table public.clientes drop constraint if exists clientes_origem_check;
alter table public.clientes add  constraint clientes_origem_check
    check (origem in ('venda', 'hub'));

drop trigger if exists trg_clientes_atualizado on public.clientes;
create trigger trg_clientes_atualizado before update on public.clientes
    for each row execute function public.dumtech_tocar_atualizado_em();

-- o mesmo e-mail nunca pode virar dois clientes (e-mail em branco fica de fora)
do $$
begin
    if exists (select 1 from public.clientes where email <> ''
                group by lower(email) having count(*) > 1) then
        raise notice 'Ha e-mails repetidos em clientes: indice unico nao criado. '
                     'Limpe as duplicatas e crie o indice idx_clientes_email.';
    else
        create unique index if not exists idx_clientes_email
            on public.clientes (lower(email)) where email <> '';
    end if;
end;
$$;

-- ======================================================= 2. COMUNICADOS =====
create table if not exists public.comunicados (
    id             uuid primary key default gen_random_uuid(),
    titulo         text not null,
    texto          text not null default '',
    rotulo         text not null default '',      -- etiqueta curta: Oferta, Novidade
    link           text not null default '',      -- vazio = a loja padrao do Hub
    alvo           text not null default 'todos'
                   check (alvo in ('todos', 'sem_produto')),
    produto_codigo text references public.produtos(codigo),
    inicio         date not null default current_date,
    fim            date,                          -- null = sem data para sair
    ordem          integer not null default 0,    -- menor aparece primeiro
    ativo          boolean not null default true,
    criado_em      timestamptz not null default now(),
    atualizado_em  timestamptz not null default now(),
    -- 'sem_produto' exige dizer QUAL produto; 'todos' nao aceita produto
    constraint comunicados_alvo_produto
        check ((alvo = 'sem_produto') = (produto_codigo is not null))
);

comment on table public.comunicados is
    'Ofertas e recados que aparecem no Inicio do Hub. alvo = sem_produto some '
    'para quem ja tem aquele produto liberado.';

create index if not exists idx_comunicados_periodo
    on public.comunicados (ativo, inicio, fim);

drop trigger if exists trg_comunicados_atualizado on public.comunicados;
create trigger trg_comunicados_atualizado before update on public.comunicados
    for each row execute function public.dumtech_tocar_atualizado_em();

-- ===================================================== 3. COMPRA_TOKENS =====
-- O codigo que o Hub passa para a landing page. Guarda uma FOTOGRAFIA do que
-- sera mostrado: assim a troca nunca precisa ler o cadastro de novo, e um token
-- de visitante jamais revela dados de um cliente de verdade.
create table if not exists public.compra_tokens (
    token      text primary key,
    cliente_id uuid references public.clientes(id) on delete set null,
    nome       text not null default '',
    email      text not null default '',
    produtos   jsonb not null default '[]'::jsonb,
    criado_em  timestamptz not null default now(),
    expira_em  timestamptz not null default now() + interval '15 minutes',
    usado_em   timestamptz
);

create index if not exists idx_compra_tokens_expira on public.compra_tokens (expira_em);

-- ========================================================== 4. FUNCOES ======

-- 32 caracteres hexadecimais do gerador criptografico do Postgres (~122 bits).
-- Nao usa o alfabeto da chave de licenca de proposito: este codigo viaja numa
-- URL e ninguem digita a mao.
create or replace function public.dumtech_novo_token()
returns text
language sql
volatile
set search_path = ''
as $$
    select replace(gen_random_uuid()::text, '-', '');
$$;

-- e-mail que vale a pena guardar (nao e validacao de RFC, e filtro de digitacao)
create or replace function public.dumtech_email_valido(p_email text)
returns boolean
language sql
immutable
set search_path = ''
as $$
    select coalesce(p_email, '') ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]{2,}$';
$$;

-- --------------------------------------------- IDENTIFICAR (primeiro acesso) --
-- Responde EXATAMENTE igual para e-mail novo e para e-mail que ja existe.
create or replace function public.dumtech_identificar_cliente(
    p_nome  text,
    p_email text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_nome  text := left(btrim(coalesce(p_nome, '')), 120);
    v_email text := lower(left(btrim(coalesce(p_email, '')), 160));
begin
    if v_nome = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe o seu nome.');
    end if;
    if not public.dumtech_email_valido(v_email) then
        return jsonb_build_object('ok', false, 'erro', 'email_invalido',
                                  'mensagem', 'Confira o e-mail digitado.');
    end if;

    -- cliente que ja existe fica intocado: o cadastro comercial manda mais que
    -- o que foi digitado numa instalacao qualquer
    insert into public.clientes (nome, email, origem)
    select v_nome, v_email, 'hub'
     where not exists (select 1 from public.clientes c where lower(c.email) = v_email);

    return jsonb_build_object('ok', true);
end;
$$;

-- ------------------------------------------------- COMUNICADOS (ofertas) -----
create or replace function public.dumtech_comunicados(p_chave text default '')
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_chave    text := public.dumtech_normalizar(p_chave, 32);
    v_licenca  uuid;
    v_produtos text[] := '{}';
begin
    if v_chave <> '' then
        select l.id into v_licenca from public.licencas l where l.chave = v_chave;
        if found then
            select coalesce(array_agg(p.codigo), '{}') into v_produtos
              from public.licenca_produtos lp
              join public.produtos p on p.id = lp.produto_id
             where lp.licenca_id = v_licenca;
        end if;
    end if;

    return jsonb_build_object(
        'ok', true,
        'comunicados', coalesce((
            select jsonb_agg(item order by item->>'ordem', item->>'criado_em' desc)
              from (
                select jsonb_build_object(
                           'id', c.id, 'titulo', c.titulo, 'texto', c.texto,
                           'rotulo', c.rotulo, 'link', c.link,
                           'ordem', lpad(c.ordem::text, 6, '0'),
                           'criado_em', c.criado_em) as item
                  from public.comunicados c
                 where c.ativo
                   and c.inicio <= current_date
                   and (c.fim is null or c.fim >= current_date)
                   -- oferta de produto some para quem ja tem o produto
                   and (c.alvo = 'todos' or not (c.produto_codigo = any (v_produtos)))
                 limit 10
              ) escolhidos
        ), '[]'::jsonb),
        'verificado_em', now());
end;
$$;

-- ------------------------------------------------ TOKEN DE COMPRA (Hub) ------
-- Dois caminhos, uma funcao:
--   com chave + computador ativado -> fotografia real (nome, e-mail, produtos)
--   so com nome + e-mail           -> fotografia do que a pessoa acabou de digitar
create or replace function public.dumtech_token_compra(
    p_chave   text default '',
    p_maquina text default '',
    p_nome    text default '',
    p_email   text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_chave    text := public.dumtech_normalizar(p_chave, 32);
    v_maquina  text := public.dumtech_normalizar(p_maquina, 64);
    v_nome     text := left(btrim(coalesce(p_nome, '')), 120);
    v_email    text := lower(left(btrim(coalesce(p_email, '')), 160));
    v_licenca  public.licencas;
    v_cliente  public.clientes;
    v_produtos jsonb := '[]'::jsonb;
    v_token    text;
begin
    -- faxina barata: token velho nao serve para nada
    delete from public.compra_tokens where expira_em < now() - interval '7 days';

    if v_chave <> '' and v_maquina <> '' then
        select * into v_licenca from public.licencas where chave = v_chave;
        if not found then
            return jsonb_build_object('ok', false, 'erro', 'nao_encontrada',
                                      'mensagem', 'Chave nao encontrada.');
        end if;
        if not exists (select 1 from public.ativacoes a
                        where a.licenca_id = v_licenca.id and a.maquina = v_maquina) then
            return jsonb_build_object('ok', false, 'erro', 'maquina_nao_ativada',
                                      'mensagem', 'Este computador nao esta ativado com esta chave.');
        end if;

        select * into v_cliente from public.clientes where id = v_licenca.cliente_id;
        select coalesce(jsonb_agg(p.codigo order by p.codigo), '[]'::jsonb) into v_produtos
          from public.licenca_produtos lp
          join public.produtos p on p.id = lp.produto_id
         where lp.licenca_id = v_licenca.id;

        v_nome  := v_cliente.nome;
        v_email := v_cliente.email;
    else
        if not public.dumtech_email_valido(v_email) then
            return jsonb_build_object('ok', false, 'erro', 'email_invalido',
                                      'mensagem', 'Confira o e-mail digitado.');
        end if;
        -- so para atribuir a visita a quem ja e cadastrado; NADA do cadastro
        -- dele entra no token: vale o que a pessoa digitou agora
        select * into v_cliente from public.clientes where lower(email) = v_email;
    end if;

    v_token := public.dumtech_novo_token();
    insert into public.compra_tokens (token, cliente_id, nome, email, produtos)
    values (v_token, v_cliente.id, v_nome, v_email, v_produtos);

    return jsonb_build_object('ok', true, 'token', v_token,
                              'expira_em', now() + interval '15 minutes');
end;
$$;

-- ------------------------------------------- ABRIR COMPRA (landing page) -----
create or replace function public.dumtech_abrir_compra(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_linha public.compra_tokens;
begin
    update public.compra_tokens
       set usado_em = now()
     where token = left(btrim(coalesce(p_token, '')), 64)
       and usado_em is null
       and expira_em > now()
    returning * into v_linha;

    if not found then
        return jsonb_build_object('ok', false, 'erro', 'token_invalido',
                                  'mensagem', 'Este link expirou. Abra a loja pelo Hub de novo.');
    end if;

    return jsonb_build_object('ok', true, 'nome', v_linha.nome, 'email', v_linha.email,
                              'produtos', v_linha.produtos);
end;
$$;

-- ================================================= 5. RLS E PERMISSOES ======
alter table public.comunicados   enable row level security;
alter table public.compra_tokens enable row level security;

revoke all on table public.comunicados   from anon, authenticated;
revoke all on table public.compra_tokens from anon, authenticated;

revoke execute on function public.dumtech_novo_token()                from public, anon, authenticated;
revoke execute on function public.dumtech_email_valido(text)          from public, anon, authenticated;
revoke execute on function public.dumtech_identificar_cliente(text, text)     from public;
revoke execute on function public.dumtech_comunicados(text)                   from public;
revoke execute on function public.dumtech_token_compra(text, text, text, text) from public;
revoke execute on function public.dumtech_abrir_compra(text)                  from public;

grant execute on function public.dumtech_identificar_cliente(text, text)      to anon, authenticated;
grant execute on function public.dumtech_comunicados(text)                    to anon, authenticated;
grant execute on function public.dumtech_token_compra(text, text, text, text) to anon, authenticated;
grant execute on function public.dumtech_abrir_compra(text)                   to anon, authenticated;

grant execute on function public.dumtech_novo_token()       to service_role;
grant execute on function public.dumtech_email_valido(text) to service_role;

notify pgrst, 'reload schema';
