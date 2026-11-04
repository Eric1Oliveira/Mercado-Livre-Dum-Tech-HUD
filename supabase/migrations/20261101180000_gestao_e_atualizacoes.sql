-- =============================================================================
-- Gestao de clientes e atualizacoes: o Eric decide quando cada versao sai, e
-- enxerga quem esta online.
--
-- O QUE ENTRA
--   1. PRESENCA: `hub_presenca` anota a batida de 2 em 2 minutos de cada Hub.
--      Tabela propria de proposito: em `ativacoes`, cada batida geraria auditoria
--      e aviso de tempo real. Funciona em todo Hub que ja pergunta a versao.
--   2. LANCAMENTOS: `hub_lancamentos` guarda cada versao que subiu. Pendente e a
--      que ainda nao foi liberada: nenhum Hub enxerga essa tabela.
--   3. POR CLIENTE: `hub_liberacoes` entrega uma versao a uma licenca so, com ou
--      sem obrigacao.
--   4. FORCADA: `hub_versoes.forcada` e o mesmo para todos.
--   5. GESTAO: etiquetas, proximo contato e anotacoes de cada cliente, e a visao
--      `painel_gestao`.
--
-- COMO O FORCAR CHEGA A CADA HUB
--   O manifesto sai com forcada + obrigatoria + silenciosa:
--     Hub 1.10.0 ou mais novo   conta 5 minutos, instala e reabre
--     Hub 1.5.1 a 1.9.0         ignora `forcada` e instala ao ser fechado
--     Hub anterior              ignora as duas e mostra o aviso que nao se dispensa
--
-- O QUE NAO MUDA
--   A assinatura (Edge Function `versao`), as conferencias do Hub e a resposta
--   para quem nao e cliente. Sem nenhum clique no painel, todo Hub segue
--   recebendo exatamente o que recebia.
-- =============================================================================

-- ======================================================== 1. PRESENCA =======
create table if not exists public.hub_presenca (
    licenca_id   uuid not null,
    maquina      text not null,
    visto_em     timestamptz not null default now(),
    -- quando este computador abriu o Hub (a batida anterior ficou para tras)
    online_desde timestamptz not null default now(),
    versao       text not null default '',
    versao_desde timestamptz not null default now(),
    primary key (licenca_id, maquina),
    foreign key (licenca_id, maquina) references public.ativacoes (licenca_id, maquina)
        on update cascade on delete cascade
);

comment on table public.hub_presenca is
    'A ultima batida de cada Hub. Online = bateu nos ultimos 5 minutos. Sem '
    'auditoria e sem tempo real: muda de 2 em 2 minutos por computador.';

-- ====================================================== 2. LANCAMENTOS ======
create table if not exists public.hub_lancamentos (
    versao        text primary key check (versao ~ '^[0-9]+(\.[0-9]+){0,3}$'),
    url           text not null check (url like 'https://%'),
    sha256        text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    tamanho       bigint not null default 0,
    notas         text not null default '',
    criado_em     timestamptz not null default now(),
    -- foi para todos. Vazio = pendente
    liberada_em   timestamptz,
    -- foi para todos como obrigatoria
    forcada_em    timestamptz,
    descartada_em timestamptz
);

comment on table public.hub_lancamentos is
    'Cada versao que subiu. O instalador esta no ar, mas nenhum Hub ve esta '
    'tabela: a versao so chega pelo botao do painel.';

-- a versao que ja esta no ar entra como liberada: e para ela que Recolher volta
insert into public.hub_lancamentos (versao, url, sha256, tamanho, notas, criado_em, liberada_em)
select versao, url, lower(sha256), tamanho, notas, atualizado_em, atualizado_em
  from public.hub_versoes
 where id = 1
   and versao ~ '^[0-9]+(\.[0-9]+){0,3}$'
   and url like 'https://%'
   and lower(sha256) ~ '^[0-9a-f]{64}$'
on conflict (versao) do nothing;

alter table public.hub_versoes add column if not exists forcada boolean not null default false;
comment on column public.hub_versoes.forcada is
    'Obrigatoria de verdade: o Hub instala sem esperar o clique.';

-- ====================================================== 3. POR CLIENTE ======
create table if not exists public.hub_liberacoes (
    licenca_id uuid primary key references public.licencas (id) on delete cascade,
    versao     text not null references public.hub_lancamentos (versao),
    forcada    boolean not null default false,
    criado_em  timestamptz not null default now()
);

comment on table public.hub_liberacoes is
    'Versao entregue a uma licenca so: serve para testar com um cliente antes de '
    'liberar para todos, e para forcar quem ficou para tras.';

-- "1.10.0" e maior que "1.9.0": compara numero, nunca texto
create or replace function public.dumtech_versao_numeros(p_versao text)
returns integer[]
language sql
immutable
set search_path = ''
as $$
    select case when p_versao ~ '^[0-9]+(\.[0-9]+){0,3}$'
                then (string_to_array(p_versao, '.')::integer[] || array[0, 0, 0, 0])[1:4]
                else array[0, 0, 0, 0] end;
$$;

-- ========================================================== A PERGUNTA ======
-- A mesma consulta de 20261026150000, mais a batida e a versao por cliente.
create or replace function public.dumtech_hub_versao(
    p_chave   text default '',
    p_maquina text default '',
    p_versao  text default '',
    p_ip      text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_atual   public.hub_versoes;
    v_lib     public.hub_liberacoes;
    v_alvo    public.hub_lancamentos;
    v_versao  text := left(btrim(coalesce(p_versao, '')), 20);
    v_maquina text := public.dumtech_normalizar(p_maquina, 64);
    v_licenca uuid;
    v_forcada boolean;
begin
    -- o Hub pergunta a cada 2 minutos (30 por hora). Uma loja com varios
    -- computadores sai pelo mesmo endereco, entao o teto e bem mais alto do
    -- que o das outras portas - e continua barrando enxurrada.
    if not public.dumtech_dentro_do_limite('versao_ip', left(btrim(coalesce(p_ip, '')), 64), 600, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas');
    end if;

    if v_versao !~ '^[0-9A-Za-z.+-]{1,20}$' then
        v_versao := '';
    end if;

    -- chave inventada, ou computador que nao e desta chave, nao anota nada
    select a.licenca_id into v_licenca
      from public.ativacoes a
      join public.licencas l on l.id = a.licenca_id
     where l.chave = public.dumtech_normalizar(p_chave, 32)
       and a.maquina = v_maquina;

    if v_licenca is not null then
        insert into public.hub_presenca as h (licenca_id, maquina, versao)
        values (v_licenca, v_maquina, v_versao)
        on conflict (licenca_id, maquina) do update
           set visto_em = now(),
               online_desde = case when h.visto_em < now() - interval '5 minutes'
                                   then now() else h.online_desde end,
               versao_desde = case when excluded.versao not in ('', h.versao)
                                   then now() else h.versao_desde end,
               versao = case when excluded.versao = '' then h.versao else excluded.versao end;

        -- anota em silencio quem esta em que versao (so serve para o painel)
        if v_versao <> '' then
            update public.ativacoes a
               set versao = v_versao, versao_em = now()
             where a.licenca_id = v_licenca
               and a.maquina = v_maquina
               and (a.versao is distinct from v_versao or a.versao_em < now() - interval '1 hour');
        end if;

        select * into v_lib from public.hub_liberacoes where licenca_id = v_licenca;
    end if;

    select * into v_atual from public.hub_versoes where id = 1;
    v_forcada := coalesce(v_atual.forcada, false);

    if v_lib.licenca_id is not null then
        if public.dumtech_versao_numeros(v_lib.versao) > public.dumtech_versao_numeros(v_atual.versao) then
            select * into v_alvo from public.hub_lancamentos
             where versao = v_lib.versao and descartada_em is null;
        elsif v_lib.versao = v_atual.versao and v_lib.forcada then
            v_forcada := true;
        end if;
    end if;

    -- a versao que so este cliente recebe
    if v_alvo.versao is not null then
        return jsonb_build_object(
            'ok', true,
            'versao', v_alvo.versao,
            'url', v_alvo.url,
            'notas', v_alvo.notas,
            'obrigatoria', v_lib.forcada,
            'sha256', v_alvo.sha256,
            'automatica', coalesce(v_atual.automatica, true),
            'silenciosa', v_lib.forcada,
            'forcada', v_lib.forcada,
            'tamanho', v_alvo.tamanho,
            'licenca', public.dumtech_licenca_marca(p_chave, p_maquina));
    end if;

    return jsonb_build_object(
        'ok', true,
        'versao', coalesce(v_atual.versao, ''),
        'url', coalesce(v_atual.url, ''),
        'notas', coalesce(v_atual.notas, ''),
        'obrigatoria', coalesce(v_atual.obrigatoria, false) or v_forcada,
        'sha256', lower(coalesce(v_atual.sha256, '')),
        'automatica', coalesce(v_atual.automatica, true),
        'silenciosa', coalesce(v_atual.silenciosa, false) or v_forcada,
        'forcada', v_forcada,
        'tamanho', coalesce(v_atual.tamanho, 0),
        'licenca', public.dumtech_licenca_marca(p_chave, p_maquina));
end;
$$;

revoke execute on function public.dumtech_hub_versao(text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.dumtech_hub_versao(text, text, text, text) to anon, authenticated;

-- ============================================================ OS BOTOES =====
-- SECURITY INVOKER, como as outras funcoes do painel: quem nao e administrador
-- esbarra nas policies. Nao ha `dumtech_e_admin()` aqui porque a policy ja diz.

-- Atualizar todos (p_forcar = false) e Forcar todos (true)
create or replace function public.dumtech_atualizar_todos(p_versao text, p_forcar boolean default false)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
    v_alvo  public.hub_lancamentos;
    v_atual text;
begin
    select * into v_alvo from public.hub_lancamentos
     where versao = p_versao and descartada_em is null;
    if not found then
        raise exception 'Esta versão não está disponível para lançar.';
    end if;

    select versao into v_atual from public.hub_versoes where id = 1;
    if public.dumtech_versao_numeros(p_versao) < public.dumtech_versao_numeros(v_atual) then
        raise exception 'A versão % é mais antiga que a publicada (%).', p_versao, v_atual;
    end if;

    update public.hub_versoes
       set versao = v_alvo.versao, url = v_alvo.url, sha256 = v_alvo.sha256,
           tamanho = v_alvo.tamanho, notas = v_alvo.notas,
           obrigatoria = coalesce(p_forcar, false), forcada = coalesce(p_forcar, false),
           silenciosa = false, automatica = true, atualizado_em = now()
     where id = 1;
    if not found then
        raise exception 'Esta conta não pode lançar versões.';
    end if;

    update public.hub_lancamentos
       set liberada_em = coalesce(liberada_em, now()),
           forcada_em = case when coalesce(p_forcar, false) then coalesce(forcada_em, now()) end
     where versao = p_versao;

    -- o pedido por cliente que a geral cobriu ja cumpriu o papel. Quem foi
    -- forcado nesta versao continua forcado, e quem esta testando uma mais nova
    -- continua testando
    delete from public.hub_liberacoes
     where public.dumtech_versao_numeros(versao) < public.dumtech_versao_numeros(p_versao)
        or (versao = p_versao and not forcada);

    return jsonb_build_object('ok', true, 'versao', p_versao, 'forcada', coalesce(p_forcar, false));
end;
$$;

-- Atualizar e Forcar de um cliente (ou da selecao)
create or replace function public.dumtech_atualizar_clientes(
    p_licencas uuid[],
    p_versao   text,
    p_forcar   boolean default false
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
    v_quantos integer;
begin
    if not exists (select 1 from public.hub_lancamentos
                    where versao = p_versao and descartada_em is null) then
        raise exception 'Esta versão não está disponível para lançar.';
    end if;

    insert into public.hub_liberacoes (licenca_id, versao, forcada)
    select distinct alvo, p_versao, coalesce(p_forcar, false)
      from unnest(coalesce(p_licencas, '{}'::uuid[])) as alvo
    on conflict (licenca_id) do update
       set versao = excluded.versao, forcada = excluded.forcada, criado_em = now();
    get diagnostics v_quantos = row_count;

    return jsonb_build_object('ok', true, 'versao', p_versao, 'clientes', v_quantos,
                              'forcada', coalesce(p_forcar, false));
end;
$$;

-- Recolher: a versao sai do ar para quem ainda nao instalou e volta a ser
-- pendente. Quem ja instalou fica nela (o Hub nao volta para tras).
create or replace function public.dumtech_recolher_versao(p_versao text)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
    v_anterior public.hub_lancamentos;
begin
    select * into v_anterior from public.hub_lancamentos
     where liberada_em is not null
       and descartada_em is null
       and public.dumtech_versao_numeros(versao) < public.dumtech_versao_numeros(p_versao)
     order by public.dumtech_versao_numeros(versao) desc
     limit 1;
    if not found then
        raise exception 'Não há versão anterior para voltar.';
    end if;

    update public.hub_versoes
       set versao = v_anterior.versao, url = v_anterior.url, sha256 = v_anterior.sha256,
           tamanho = v_anterior.tamanho, notas = v_anterior.notas,
           obrigatoria = false, forcada = false, silenciosa = false, atualizado_em = now()
     where id = 1 and versao = p_versao;
    if not found then
        raise exception 'A versão % não é a publicada.', p_versao;
    end if;

    update public.hub_lancamentos set liberada_em = null, forcada_em = null where versao = p_versao;
    delete from public.hub_liberacoes where versao = p_versao;

    return jsonb_build_object('ok', true, 'voltou_para', v_anterior.versao);
end;
$$;

-- Descartar: a pendente nao vai mais sair (some tambem dos clientes de teste)
create or replace function public.dumtech_descartar_versao(p_versao text)
returns jsonb
language plpgsql
set search_path = ''
as $$
begin
    update public.hub_lancamentos set descartada_em = now()
     where versao = p_versao and liberada_em is null and descartada_em is null;
    if not found then
        raise exception 'Só uma versão pendente pode ser descartada.';
    end if;
    delete from public.hub_liberacoes where versao = p_versao;
    return jsonb_build_object('ok', true, 'versao', p_versao);
end;
$$;

revoke execute on function public.dumtech_versao_numeros(text)                   from public, anon, authenticated;
revoke execute on function public.dumtech_atualizar_todos(text, boolean)         from public, anon;
revoke execute on function public.dumtech_atualizar_clientes(uuid[], text, boolean) from public, anon;
revoke execute on function public.dumtech_recolher_versao(text)                  from public, anon;
revoke execute on function public.dumtech_descartar_versao(text)                 from public, anon;
grant execute on function public.dumtech_versao_numeros(text)                    to authenticated;
grant execute on function public.dumtech_atualizar_todos(text, boolean)          to authenticated;
grant execute on function public.dumtech_atualizar_clientes(uuid[], text, boolean) to authenticated;
grant execute on function public.dumtech_recolher_versao(text)                   to authenticated;
grant execute on function public.dumtech_descartar_versao(text)                  to authenticated;

-- ========================================================== 5. GESTAO =======
alter table public.clientes add column if not exists etiquetas text[] not null default '{}';
alter table public.clientes add column if not exists proximo_contato date;

create table if not exists public.cliente_notas (
    id         uuid primary key default gen_random_uuid(),
    cliente_id uuid not null references public.clientes (id) on delete cascade,
    texto      text not null check (char_length(btrim(texto)) between 1 and 2000),
    autor      text not null default '',
    criado_em  timestamptz not null default now()
);
create index if not exists idx_cliente_notas_cliente on public.cliente_notas (cliente_id, criado_em desc);

comment on table public.cliente_notas is
    'O que a DumTech anotou sobre o cliente: ligacoes, combinados, pendencias.';

-- o que a lista de clientes precisa alem de painel_clientes: uma linha por cliente
create or replace view public.painel_gestao with (security_invoker = true) as
select c.id                                        as cliente_id,
       c.etiquetas,
       c.proximo_contato,
       coalesce(v.compras, 0)                      as compras,
       v.primeira_compra,
       v.ultima_compra,
       v.canal,
       coalesce(n.anotacoes, 0)                    as anotacoes,
       n.ultima_anotacao
  from public.clientes c
  left join lateral (
        select count(*)::integer                   as compras,
               min(p.criado_em)                    as primeira_compra,
               max(p.criado_em)                    as ultima_compra,
               (array_agg(p.origem order by p.criado_em))[1] as canal
          from public.pedidos_site p
         where p.cliente_id = c.id and p.atendido_em is not null
  ) v on true
  left join lateral (
        select count(*)::integer                   as anotacoes,
               max(a.criado_em)                    as ultima_anotacao
          from public.cliente_notas a
         where a.cliente_id = c.id
  ) n on true;

-- ========================================================= PERMISSOES =======
alter table public.hub_presenca    enable row level security;
alter table public.hub_lancamentos enable row level security;
alter table public.hub_liberacoes  enable row level security;
alter table public.cliente_notas   enable row level security;

-- tabela nova nasce com o privilegio largo do Supabase: nada para o anon
revoke all on table public.hub_presenca, public.hub_lancamentos, public.hub_liberacoes,
                    public.cliente_notas
    from public, anon, authenticated;
revoke all on public.painel_gestao from public, anon;

drop policy if exists admin_le on public.hub_presenca;
create policy admin_le on public.hub_presenca for select to authenticated
    using (public.dumtech_e_admin());
grant select on public.hub_presenca to authenticated;

drop policy if exists admin_escreve on public.hub_lancamentos;
create policy admin_escreve on public.hub_lancamentos for all to authenticated
    using (public.dumtech_e_admin()) with check (public.dumtech_e_admin());
-- as versoes nao se apagam: o historico e o caminho de volta do Recolher
grant select, insert, update on public.hub_lancamentos to authenticated;

drop policy if exists admin_escreve on public.hub_liberacoes;
create policy admin_escreve on public.hub_liberacoes for all to authenticated
    using (public.dumtech_e_admin()) with check (public.dumtech_e_admin());
grant select, insert, update, delete on public.hub_liberacoes to authenticated;

drop policy if exists admin_escreve on public.cliente_notas;
create policy admin_escreve on public.cliente_notas for all to authenticated
    using (public.dumtech_e_admin()) with check (public.dumtech_e_admin());
grant select, insert, delete on public.cliente_notas to authenticated;

grant select on public.painel_gestao to authenticated;

-- ============================================= AUDITORIA E TEMPO REAL =======
do $$
declare
    v_tabela text;
begin
    foreach v_tabela in array array['hub_versoes', 'hub_lancamentos', 'hub_liberacoes', 'cliente_notas'] loop
        execute format('drop trigger if exists trg_auditoria on public.%I', v_tabela);
        execute format(
            'create trigger trg_auditoria after insert or update or delete on public.%I '
            'for each row execute function public.dumtech_auditar()', v_tabela);
        execute format('drop trigger if exists trg_tempo_real_painel on public.%I', v_tabela);
        execute format(
            'create trigger trg_tempo_real_painel after insert or update or delete on public.%I '
            'for each statement execute function public.dumtech_avisar_mudanca(%L, %L)',
            v_tabela, 'painel', 'true');
    end loop;
end;
$$;

notify pgrst, 'reload schema';
