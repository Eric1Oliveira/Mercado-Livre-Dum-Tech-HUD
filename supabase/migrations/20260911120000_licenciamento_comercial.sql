-- =============================================================================
-- 20260911120000 - licenciamento comercial: clientes -> licencas -> produtos
--
-- O QUE MUDA
--   aplicativos   -> produtos        (catalogo comercial: preco, versao, ativo)
--   licenca_apps  -> licenca_produtos (o que cada licenca libera)
--   novas         -> combos, combo_produtos
--   licencas      ganha tipo (vitalicia/assinatura/teste) e atualizado_em
--
-- O QUE NAO MUDA
--   As tres funcoes que o aplicativo chama continuam com o mesmo nome, os
--   mesmos parametros e o mesmo formato de resposta (o campo "aplicativos"
--   segue na resposta, ao lado do novo "produtos", para nao quebrar os .exe
--   ja instalados).
--
-- Os dados existentes sao preservados: catalogo, licencas, o que cada licenca
-- libera e as ativacoes dos computadores.
-- =============================================================================

-- ============================================================== 1. TABELAS ==

create table if not exists public.produtos (
    id            uuid primary key default gen_random_uuid(),
    codigo        text not null unique
                  check (codigo ~ '^[A-Z][A-Z0-9_]*$'),   -- ESTOQUE, CRM, PDV...
    nome          text not null,
    descricao     text not null default '',
    preco         numeric(12, 2) not null default 0 check (preco >= 0),
    versao        text not null default '',
    ativo         boolean not null default true,          -- ativo = esta a venda
    criado_em     timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);

comment on table public.produtos is
    'Catalogo comercial da DumTech. Cada modulo do Hub e um registro aqui: '
    'lancar um modulo novo e um INSERT, nunca uma tabela nova.';
comment on column public.produtos.ativo is
    'false = saiu de linha (nao entra em licenca nem em combo novo). Quem ja '
    'comprou continua com o produto liberado.';

create table if not exists public.combos (
    id            uuid primary key default gen_random_uuid(),
    codigo        text not null unique check (codigo ~ '^[A-Z][A-Z0-9_]*$'),
    nome          text not null,
    descricao     text not null default '',
    preco         numeric(12, 2) not null default 0 check (preco >= 0),
    ativo         boolean not null default true,
    criado_em     timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);

comment on table public.combos is
    'Pacote comercial (ex.: DumTech Gestao). Nao duplica produto: aponta para '
    'os registros de public.produtos.';

create table if not exists public.combo_produtos (
    combo_id   uuid not null references public.combos(id)   on delete cascade,
    produto_id uuid not null references public.produtos(id) on delete restrict,
    primary key (combo_id, produto_id)   -- o mesmo produto nao entra duas vezes
);

create table if not exists public.licenca_produtos (
    licenca_id  uuid not null references public.licencas(id)  on delete cascade,
    produto_id  uuid not null references public.produtos(id)  on delete restrict,
    combo_id    uuid references public.combos(id) on delete set null,
    liberado_em timestamptz not null default now(),
    primary key (licenca_id, produto_id)
);

comment on table public.licenca_produtos is
    'O que a licenca libera. Combo comprado entra aqui expandido em produtos '
    '(fotografia do que foi vendido); combo_id so registra a origem, entao '
    'mudar o combo depois nao tira nem da produto a quem ja comprou.';

-- ------------------------------------------------- licencas: tipo e carimbo --
alter table public.licencas add column if not exists tipo text not null default 'vitalicia';
alter table public.licencas add column if not exists atualizado_em timestamptz not null default now();

comment on column public.licencas.tipo is
    'vitalicia (sem prazo), assinatura (renovavel) ou teste (demonstracao).';

-- licencas que ja existiam: quem tem prazo e assinatura, quem nao tem e vitalicia
update public.licencas
   set tipo = 'assinatura'
 where expira_em is not null and tipo = 'vitalicia';

alter table public.licencas drop constraint if exists licencas_tipo_check;
alter table public.licencas add  constraint licencas_tipo_check
    check (tipo in ('vitalicia', 'assinatura', 'teste'));

-- estado impossivel nao entra no banco: vitalicia com prazo, assinatura sem prazo
alter table public.licencas drop constraint if exists licencas_prazo_check;
alter table public.licencas add  constraint licencas_prazo_check
    check ((tipo = 'vitalicia') = (expira_em is null));

-- ==================================================== 2. MIGRACAO DE DADOS ==
do $$
begin
    if to_regclass('public.aplicativos') is not null then
        insert into public.produtos (codigo, nome, descricao, ativo, criado_em)
        select a.codigo, a.nome, a.descricao, a.ativo, a.criado_em
          from public.aplicativos a
        on conflict (codigo) do nothing;
    end if;

    if to_regclass('public.licenca_apps') is not null then
        insert into public.licenca_produtos (licenca_id, produto_id, liberado_em)
        select la.licenca_id, p.id, la.liberado_em
          from public.licenca_apps la
          join public.produtos p on p.codigo = la.aplicativo_codigo
        on conflict do nothing;
    end if;
end;
$$;

-- as funcoes antigas apontam para estas tabelas; sao todas recriadas abaixo
drop function if exists public.dumtech_licenca_valida(text, text);
drop table    if exists public.licenca_apps;
drop table    if exists public.aplicativos;

-- ============================================================== 3. INDICES ==
create index if not exists idx_licencas_cliente          on public.licencas(cliente_id);
create index if not exists idx_licenca_produtos_produto  on public.licenca_produtos(produto_id);
create index if not exists idx_combo_produtos_produto    on public.combo_produtos(produto_id);
-- "buscar produtos de uma licenca" e "produtos de um combo" ja usam a PK;
-- "buscar licenca pela chave" usa o unique de licencas.chave;
-- "ativacoes de uma licenca" usa o unique (licenca_id, maquina) - por isso o
-- indice avulso abaixo era peso morto.
drop index if exists public.idx_ativacoes_licenca;
drop index if exists public.idx_licenca_apps_licenca;

-- mesmo CPF/CNPJ nao pode virar dois clientes (documento em branco e ignorado)
do $$
begin
    if exists (select 1 from public.clientes
                where documento <> ''
                group by documento having count(*) > 1) then
        raise notice 'Ha documentos repetidos em clientes: indice unico nao criado. '
                     'Limpe as duplicatas e rode: create unique index idx_clientes_documento '
                     'on public.clientes(documento) where documento <> '''';';
    else
        create unique index if not exists idx_clientes_documento
            on public.clientes(documento) where documento <> '';
    end if;
end;
$$;

-- ========================================================= 4. UTILITARIOS ===

-- carimbo de alteracao (produtos, combos e licencas)
create or replace function public.dumtech_tocar_atualizado_em()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.atualizado_em := now();
    return new;
end;
$$;

drop trigger if exists trg_produtos_atualizado on public.produtos;
create trigger trg_produtos_atualizado before update on public.produtos
    for each row execute function public.dumtech_tocar_atualizado_em();

drop trigger if exists trg_combos_atualizado on public.combos;
create trigger trg_combos_atualizado before update on public.combos
    for each row execute function public.dumtech_tocar_atualizado_em();

drop trigger if exists trg_licencas_atualizado on public.licencas;
create trigger trg_licencas_atualizado before update on public.licencas
    for each row execute function public.dumtech_tocar_atualizado_em();

-- "expirada" NAO e um status gravado: e calculado aqui, em um lugar so
create or replace function public.dumtech_situacao_licenca(p_status text, p_expira_em date)
returns text
language sql
stable
set search_path = ''
as $$
    select case
        when p_status <> 'ativa' then p_status
        when p_expira_em is not null and p_expira_em < current_date then 'expirada'
        else 'ativa'
    end;
$$;

-- texto vindo da internet: sem espacos, em maiuscula e com tamanho limitado
create or replace function public.dumtech_normalizar(p_texto text, p_tamanho integer)
returns text
language sql
immutable
set search_path = ''
as $$
    select upper(left(btrim(coalesce(p_texto, '')), p_tamanho));
$$;

-- chave XXXX-XXXX-XXXX-XXXX, sem os caracteres que o cliente confunde (O/0/I/1).
-- 16 simbolos de um alfabeto de 32 = 80 bits de aleatoriedade.
-- gen_random_uuid() usa o gerador criptografico do Postgres; os 6 primeiros
-- bytes de um UUID v4 sao 100% aleatorios (versao e variante ficam nos bytes
-- 7 e 9). 256 e multiplo de 32, entao o "% 32" nao distorce o sorteio.
create or replace function public.dumtech_nova_chave()
returns text
language plpgsql
volatile
set search_path = ''
as $$
declare
    v_alfabeto constant text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    v_bytes    bytea;
    v_chave    text := '';
    v_i        integer;
begin
    v_bytes := substring(uuid_send(gen_random_uuid()) from 1 for 6)
            || substring(uuid_send(gen_random_uuid()) from 1 for 6)
            || substring(uuid_send(gen_random_uuid()) from 1 for 4);
    for v_i in 0..15 loop
        v_chave := v_chave || substr(v_alfabeto, 1 + (get_byte(v_bytes, v_i) % 32), 1);
        if v_i in (3, 7, 11) then
            v_chave := v_chave || '-';
        end if;
    end loop;
    return v_chave;
end;
$$;

-- ================================================== 5. FUNCOES DO APLICATIVO ==
-- Formato de resposta (sempre jsonb):
--   sucesso: {"ok": true, "chave": ..., "cliente": ..., "tipo": ...,
--             "produtos": [...], "aplicativos": [...],  <- mesma lista
--             "expira_em": ..., "max_computadores": n, "computadores_usados": n}
--   erro:    {"ok": false, "erro": "<codigo>", "mensagem": "<texto ao cliente>"}

create or replace function public.dumtech_resposta_licenca(p_licenca_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    select jsonb_build_object(
        'ok', true,
        'chave', l.chave,
        'cliente', c.nome,
        'tipo', l.tipo,
        'produtos', coalesce(itens.codigos, '[]'::jsonb),
        -- "aplicativos" e o nome antigo do mesmo campo: continua na resposta
        -- para os Hubs instalados antes desta mudanca
        'aplicativos', coalesce(itens.codigos, '[]'::jsonb),
        'expira_em', l.expira_em,
        'max_computadores', l.max_computadores,
        'computadores_usados', (select count(*) from public.ativacoes a
                                 where a.licenca_id = l.id),
        'verificado_em', now()
    )
      from public.licencas l
      join public.clientes c on c.id = l.cliente_id
      left join lateral (
            select jsonb_agg(p.codigo order by p.codigo) as codigos
              from public.licenca_produtos lp
              join public.produtos p on p.id = lp.produto_id
             where lp.licenca_id = l.id
      ) itens on true
     where l.id = p_licenca_id;
$$;

-- Busca a licenca e aplica as regras comuns (existe? ativa? no prazo?).
create or replace function public.dumtech_licenca_valida(p_chave text)
returns public.licencas
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca  public.licencas;
    v_situacao text;
begin
    select * into v_licenca from public.licencas where chave = p_chave;

    -- os erros viajam como 'codigo|mensagem' e sao convertidos em JSON por quem chamou
    if not found then
        raise exception 'nao_encontrada|Chave nao encontrada. Confira os caracteres digitados.';
    end if;

    v_situacao := public.dumtech_situacao_licenca(v_licenca.status, v_licenca.expira_em);

    if v_situacao = 'suspensa' then
        raise exception 'inativa|Esta licenca esta suspensa. Fale com a DumTech.';
    end if;

    if v_situacao = 'cancelada' then
        raise exception 'inativa|Esta licenca foi cancelada. Fale com a DumTech.';
    end if;

    if v_situacao = 'expirada' then
        if v_licenca.tipo = 'teste' then
            raise exception 'expirada|O periodo de teste terminou em %. Fale com a DumTech para continuar.',
                to_char(v_licenca.expira_em, 'DD/MM/YYYY');
        end if;
        raise exception 'expirada|Esta licenca venceu em %. Renove para continuar.',
            to_char(v_licenca.expira_em, 'DD/MM/YYYY');
    end if;

    return v_licenca;
end;
$$;

-- ------------------------------------------------------ ATIVAR (1a vez) -----
create or replace function public.dumtech_ativar_licenca(
    p_chave   text,
    p_maquina text,
    p_apelido text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca public.licencas;
    v_usadas  integer;
    v_ja      boolean;
    v_texto   text;
begin
    p_chave   := public.dumtech_normalizar(p_chave, 32);
    p_maquina := public.dumtech_normalizar(p_maquina, 64);
    p_apelido := left(btrim(coalesce(p_apelido, '')), 120);

    if p_chave = '' or p_maquina = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe a chave da licenca.');
    end if;

    v_licenca := public.dumtech_licenca_valida(p_chave);

    -- segura a licenca ate o fim da transacao: duas ativacoes ao mesmo tempo
    -- nao podem passar as duas pela contagem de vagas
    perform 1 from public.licencas where id = v_licenca.id for update;

    select exists(
        select 1 from public.ativacoes
         where licenca_id = v_licenca.id and maquina = p_maquina
    ) into v_ja;

    if v_ja then
        update public.ativacoes
           set ultima_checagem = now(),
               apelido = case when p_apelido <> '' then p_apelido else apelido end
         where licenca_id = v_licenca.id and maquina = p_maquina;
    else
        select count(*) into v_usadas from public.ativacoes where licenca_id = v_licenca.id;
        if v_usadas >= v_licenca.max_computadores then
            insert into public.licenca_tentativas (chave, maquina, erro)
            values (p_chave, p_maquina, 'limite_maquinas');
            return jsonb_build_object(
                'ok', false, 'erro', 'limite_maquinas',
                'mensagem', format(
                    'Esta licenca ja esta ativada em %s computador(es), o maximo do plano. '
                    || 'Desative em outro computador ou fale com a DumTech.',
                    v_licenca.max_computadores));
        end if;
        insert into public.ativacoes (licenca_id, maquina, apelido)
        values (v_licenca.id, p_maquina, p_apelido);
    end if;

    return public.dumtech_resposta_licenca(v_licenca.id);

exception
    when others then
        v_texto := sqlerrm;
        if position('|' in v_texto) > 0 then
            insert into public.licenca_tentativas (chave, maquina, erro)
            values (p_chave, p_maquina, split_part(v_texto, '|', 1));
            return jsonb_build_object('ok', false,
                                      'erro', split_part(v_texto, '|', 1),
                                      'mensagem', split_part(v_texto, '|', 2));
        end if;
        raise;
end;
$$;

-- ---------------------------------------- VERIFICAR (comprou outro produto) --
create or replace function public.dumtech_verificar_licenca(
    p_chave   text,
    p_maquina text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca public.licencas;
    v_texto   text;
begin
    p_chave   := public.dumtech_normalizar(p_chave, 32);
    p_maquina := public.dumtech_normalizar(p_maquina, 64);

    if p_chave = '' or p_maquina = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe a chave da licenca.');
    end if;

    v_licenca := public.dumtech_licenca_valida(p_chave);

    update public.ativacoes
       set ultima_checagem = now()
     where licenca_id = v_licenca.id and maquina = p_maquina;

    if not found then
        return jsonb_build_object(
            'ok', false, 'erro', 'maquina_nao_ativada',
            'mensagem', 'Este computador ainda nao foi ativado com esta chave. '
                     || 'Use o botao Ativar licenca.');
    end if;

    return public.dumtech_resposta_licenca(v_licenca.id);

exception
    when others then
        v_texto := sqlerrm;
        if position('|' in v_texto) > 0 then
            insert into public.licenca_tentativas (chave, maquina, erro)
            values (p_chave, p_maquina, split_part(v_texto, '|', 1));
            return jsonb_build_object('ok', false,
                                      'erro', split_part(v_texto, '|', 1),
                                      'mensagem', split_part(v_texto, '|', 2));
        end if;
        raise;
end;
$$;

-- ------------------------------ DESATIVAR (liberar a vaga do computador) -----
create or replace function public.dumtech_desativar_licenca(
    p_chave   text,
    p_maquina text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_id       uuid;
    v_removeu  boolean;
begin
    p_chave   := public.dumtech_normalizar(p_chave, 32);
    p_maquina := public.dumtech_normalizar(p_maquina, 64);

    select id into v_id from public.licencas where chave = p_chave;
    if not found then
        -- registrar tambem aqui: senao esta funcao vira um testador de chaves
        -- silencioso, sem nenhuma marca no banco
        insert into public.licenca_tentativas (chave, maquina, erro)
        values (p_chave, p_maquina, 'nao_encontrada');
        return jsonb_build_object('ok', false, 'erro', 'nao_encontrada',
                                  'mensagem', 'Chave nao encontrada.');
    end if;

    delete from public.ativacoes where licenca_id = v_id and maquina = p_maquina;
    v_removeu := found;
    return jsonb_build_object('ok', true, 'removido', v_removeu);
end;
$$;

-- ============================================= 6. FUNCOES DA ADMINISTRACAO ===
-- Usadas por voce (SQL Editor hoje, painel administrativo amanha). Rodam com o
-- papel de quem chama - nunca SECURITY DEFINER - e so o service_role recebe
-- permissao. Assim, mesmo que um dia escapem para a chave anon, o RLS barra.

-- Libera produtos avulsos e/ou um combo inteiro numa licenca ja existente.
create or replace function public.dumtech_liberar_produtos(
    p_licenca_id uuid,
    p_produtos   text[] default '{}',
    p_combo      text   default null
)
returns integer                      -- quantos produtos entraram de fato
language plpgsql
set search_path = ''
as $$
declare
    v_combo   public.combos;
    v_produto public.produtos;
    v_codigo  text;
    v_novos   integer := 0;
    v_linhas  integer;
begin
    if not exists (select 1 from public.licencas where id = p_licenca_id) then
        raise exception 'Licenca % nao existe.', p_licenca_id;
    end if;

    if coalesce(btrim(p_combo), '') <> '' then
        select * into v_combo from public.combos where codigo = upper(btrim(p_combo));
        if not found then
            raise exception 'Combo % nao existe.', upper(btrim(p_combo));
        end if;
        if not v_combo.ativo then
            raise exception 'Combo % nao esta a venda (ativo = false).', v_combo.codigo;
        end if;

        insert into public.licenca_produtos (licenca_id, produto_id, combo_id)
        select p_licenca_id, cp.produto_id, v_combo.id
          from public.combo_produtos cp
         where cp.combo_id = v_combo.id
        on conflict do nothing;
        get diagnostics v_linhas = row_count;
        v_novos := v_novos + v_linhas;
    end if;

    foreach v_codigo in array coalesce(p_produtos, '{}') loop
        v_codigo := upper(btrim(v_codigo));
        continue when v_codigo = '';

        select * into v_produto from public.produtos where codigo = v_codigo;
        if not found then
            raise exception 'Produto % nao existe no catalogo.', v_codigo;
        end if;
        if not v_produto.ativo then
            raise exception 'Produto % nao esta a venda (ativo = false).', v_codigo;
        end if;

        insert into public.licenca_produtos (licenca_id, produto_id)
        values (p_licenca_id, v_produto.id)
        on conflict do nothing;
        get diagnostics v_linhas = row_count;
        v_novos := v_novos + v_linhas;
    end loop;

    return v_novos;
end;
$$;

-- Emite uma licenca inteira: gera a chave, cria a licenca e libera o que foi
-- comprado (produtos avulsos, um combo, ou os dois).
create or replace function public.dumtech_emitir_licenca(
    p_cliente_id       uuid,
    p_produtos         text[]  default '{}',
    p_combo            text    default null,
    p_tipo             text    default 'vitalicia',
    p_expira_em        date    default null,
    p_max_computadores integer default 1,
    p_observacoes      text    default '',
    p_chave            text    default null   -- so para casos especiais (demo)
)
returns table (licenca_id uuid, chave text)
language plpgsql
set search_path = ''
as $$
declare
    v_id        uuid;
    v_chave     text;
    v_tentativa integer := 0;
begin
    if not exists (select 1 from public.clientes c where c.id = p_cliente_id) then
        raise exception 'Cliente % nao existe.', p_cliente_id;
    end if;

    if coalesce(array_length(p_produtos, 1), 0) = 0
       and coalesce(btrim(p_combo), '') = '' then
        raise exception 'Informe ao menos um produto ou um combo.';
    end if;

    loop
        v_tentativa := v_tentativa + 1;
        v_chave := coalesce(nullif(public.dumtech_normalizar(p_chave, 32), ''),
                            public.dumtech_nova_chave());
        begin
            insert into public.licencas (cliente_id, chave, tipo, max_computadores,
                                         expira_em, observacoes)
            values (p_cliente_id, v_chave, p_tipo, p_max_computadores,
                    p_expira_em, coalesce(p_observacoes, ''))
            returning id into v_id;
            exit;
        exception when unique_violation then
            -- chave sorteada ja existe (praticamente impossivel): sorteia outra
            if p_chave is not null or v_tentativa >= 5 then
                raise exception 'Ja existe uma licenca com a chave %.', v_chave;
            end if;
        end;
    end loop;

    perform public.dumtech_liberar_produtos(v_id, p_produtos, p_combo);

    return query select v_id, v_chave;
end;
$$;

-- Visao de apoio da administracao (e a base da futura tela de clientes do Hub).
create or replace view public.licencas_resumo with (security_invoker = true) as
select l.id                as licenca_id,
       l.chave,
       c.id                as cliente_id,
       c.nome              as cliente,
       c.email,
       l.tipo,
       l.status,
       public.dumtech_situacao_licenca(l.status, l.expira_em) as situacao,
       l.expira_em,
       l.max_computadores,
       (select count(*) from public.ativacoes a where a.licenca_id = l.id)
                           as computadores_ativos,
       coalesce((select string_agg(p.codigo, ', ' order by p.codigo)
                   from public.licenca_produtos lp
                   join public.produtos p on p.id = lp.produto_id
                  where lp.licenca_id = l.id), '') as produtos,
       l.observacoes,
       l.criado_em,
       l.atualizado_em
  from public.licencas l
  join public.clientes c on c.id = l.cliente_id;

-- ================================================== 7. RLS E PERMISSOES ====
-- Filosofia mantida: RLS ligado e SEM policies em tudo. A chave anon nao le
-- nem escreve tabela nenhuma; ela so executa as tres funcoes do aplicativo.

alter table public.produtos         enable row level security;
alter table public.combos           enable row level security;
alter table public.combo_produtos   enable row level security;
alter table public.licenca_produtos enable row level security;

-- Defesa em profundidade: o Supabase concede privilegios de tabela a anon e
-- authenticated por padrao, e hoje so o RLS segura. Tirando o privilegio, um
-- "disable row level security" acidental deixa de virar vazamento.
revoke all on table public.clientes           from anon, authenticated;
revoke all on table public.produtos           from anon, authenticated;
revoke all on table public.combos             from anon, authenticated;
revoke all on table public.combo_produtos     from anon, authenticated;
revoke all on table public.licencas           from anon, authenticated;
revoke all on table public.licenca_produtos   from anon, authenticated;
revoke all on table public.ativacoes          from anon, authenticated;
revoke all on table public.licenca_tentativas from anon, authenticated;
revoke all on table public.licencas_resumo    from anon, authenticated;
revoke all on sequence public.licenca_tentativas_id_seq from anon, authenticated;

-- Funcoes: por padrao o PostgreSQL da EXECUTE a PUBLIC, e o Supabase da EXECUTE
-- nominalmente a anon/authenticated - por isso o revoke precisa citar os tres.
revoke execute on function public.dumtech_resposta_licenca(uuid)      from public, anon, authenticated;
revoke execute on function public.dumtech_licenca_valida(text)        from public, anon, authenticated;
revoke execute on function public.dumtech_situacao_licenca(text,date) from public, anon, authenticated;
revoke execute on function public.dumtech_normalizar(text, integer)   from public, anon, authenticated;
revoke execute on function public.dumtech_tocar_atualizado_em()       from public, anon, authenticated;
revoke execute on function public.dumtech_nova_chave()                from public, anon, authenticated;
revoke execute on function public.dumtech_liberar_produtos(uuid, text[], text) from public, anon, authenticated;
revoke execute on function public.dumtech_emitir_licenca(uuid, text[], text, text, date, integer, text, text)
    from public, anon, authenticated;
revoke execute on function public.dumtech_ativar_licenca(text, text, text) from public;
revoke execute on function public.dumtech_verificar_licenca(text, text)    from public;
revoke execute on function public.dumtech_desativar_licenca(text, text)    from public;

-- as tres unicas funcoes que o aplicativo instalado pode chamar
grant execute on function public.dumtech_ativar_licenca(text, text, text) to anon, authenticated;
grant execute on function public.dumtech_verificar_licenca(text, text)    to anon, authenticated;
grant execute on function public.dumtech_desativar_licenca(text, text)    to anon, authenticated;

-- administracao (SQL Editor / painel futuro), nunca a chave anon
grant execute on function public.dumtech_nova_chave()                         to service_role;
grant execute on function public.dumtech_liberar_produtos(uuid, text[], text) to service_role;
grant execute on function public.dumtech_emitir_licenca(uuid, text[], text, text, date, integer, text, text)
    to service_role;
grant execute on function public.dumtech_situacao_licenca(text, date)         to service_role;

notify pgrst, 'reload schema';
