-- =============================================================================
-- 20260824060000 - licenciamento inicial (MIGRATION BASE)
--
-- Este arquivo e a fotografia do banco como ele nasceu, em 24/08/2026: o antigo
-- docs/supabase/01_schema.sql mais o gerador de chaves que vivia dentro do
-- docs/supabase/03_emitir_licenca.sql. Ele existe para que um banco novo
-- (homologacao, por exemplo) possa ser montado do zero rodando as migrations em
-- ordem, e para que a historia do schema fique versionada.
--
-- NAO edite este arquivo: a evolucao comercial (produtos, combos, licenca_
-- produtos) esta na migration seguinte.
--
-- Seguranca: as tabelas ficam com RLS ligado e SEM policies, ou seja, a chave
-- publica (anon) do aplicativo NAO consegue ler nem escrever nada diretamente.
-- Todo acesso passa pelas funcoes abaixo, que sao SECURITY DEFINER e so
-- devolvem os dados daquela chave especifica.
-- =============================================================================

-- ------------------------------------------------------------------ tabelas --
create table if not exists public.clientes (
    id          uuid primary key default gen_random_uuid(),
    nome        text not null,
    documento   text not null default '',
    email       text not null default '',
    telefone    text not null default '',
    observacoes text not null default '',
    criado_em   timestamptz not null default now()
);

create table if not exists public.aplicativos (
    codigo    text primary key,              -- ESTOQUE, FINANCEIRO, ...
    nome      text not null,
    descricao text not null default '',
    ativo     boolean not null default true,
    criado_em timestamptz not null default now()
);

create table if not exists public.licencas (
    id               uuid primary key default gen_random_uuid(),
    cliente_id       uuid not null references public.clientes(id) on delete cascade,
    chave            text not null unique,   -- XXXX-XXXX-XXXX-XXXX
    status           text not null default 'ativa'
                     check (status in ('ativa', 'suspensa', 'cancelada')),
    max_computadores integer not null default 1 check (max_computadores > 0),
    expira_em        date,                   -- null = sem prazo
    observacoes      text not null default '',
    criado_em        timestamptz not null default now()
);

create table if not exists public.licenca_apps (
    licenca_id        uuid not null references public.licencas(id) on delete cascade,
    aplicativo_codigo text not null references public.aplicativos(codigo),
    liberado_em       timestamptz not null default now(),
    primary key (licenca_id, aplicativo_codigo)
);

create table if not exists public.ativacoes (
    id              uuid primary key default gen_random_uuid(),
    licenca_id      uuid not null references public.licencas(id) on delete cascade,
    maquina         text not null,
    apelido         text not null default '',
    ativado_em      timestamptz not null default now(),
    ultima_checagem timestamptz not null default now(),
    unique (licenca_id, maquina)
);

-- registro de tentativas que deram errado (ajuda no suporte)
create table if not exists public.licenca_tentativas (
    id       bigserial primary key,
    chave    text not null default '',
    maquina  text not null default '',
    erro     text not null default '',
    quando   timestamptz not null default now()
);

create index if not exists idx_licenca_apps_licenca on public.licenca_apps(licenca_id);
create index if not exists idx_ativacoes_licenca on public.ativacoes(licenca_id);
create index if not exists idx_tentativas_quando on public.licenca_tentativas(quando desc);

-- ---------------------------------------------------------------------- RLS --
alter table public.clientes           enable row level security;
alter table public.aplicativos        enable row level security;
alter table public.licencas           enable row level security;
alter table public.licenca_apps       enable row level security;
alter table public.ativacoes          enable row level security;
alter table public.licenca_tentativas enable row level security;

-- ------------------------------------------------- catalogo de aplicativos --
insert into public.aplicativos (codigo, nome, descricao) values
    ('ESTOQUE',    'DumTech Estoque',           'Produtos, entradas e saidas'),
    ('CLIENTES',   'DumTech Clientes',          'Cadastro de clientes'),
    ('FINANCEIRO', 'DumTech Financeiro',        'Contas a pagar e a receber'),
    ('ORCAMENTOS', 'DumTech Orcamentos',        'Orcamentos com itens'),
    ('VENDAS',     'DumTech Vendas',            'Vendas e formas de pagamento'),
    ('ORDENS',     'DumTech Ordem de Servico',  'Ordens de servico'),
    ('AGENDA',     'DumTech Agenda',            'Compromissos e atendimentos')
on conflict (codigo) do update
    set nome = excluded.nome, descricao = excluded.descricao;

-- ================================================================= funcoes ==
-- Formato de resposta (sempre jsonb):
--   sucesso: {"ok": true, "chave": ..., "cliente": ..., "aplicativos": [...],
--             "expira_em": ..., "max_computadores": n, "computadores_usados": n}
--   erro:    {"ok": false, "erro": "<codigo>", "mensagem": "<texto ao cliente>"}

create or replace function public.dumtech_resposta_licenca(p_licenca_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
    select jsonb_build_object(
        'ok', true,
        'chave', l.chave,
        'cliente', c.nome,
        'aplicativos', coalesce((
            select jsonb_agg(la.aplicativo_codigo order by la.aplicativo_codigo)
              from licenca_apps la
              join aplicativos a on a.codigo = la.aplicativo_codigo
             where la.licenca_id = l.id and a.ativo
        ), '[]'::jsonb),
        'expira_em', l.expira_em,
        'max_computadores', l.max_computadores,
        'computadores_usados', (select count(*) from ativacoes where licenca_id = l.id),
        'verificado_em', now()
    )
      from licencas l
      join clientes c on c.id = l.cliente_id
     where l.id = p_licenca_id;
$$;

-- Busca a licenca e aplica as regras comuns (existe? ativa? no prazo?).
create or replace function public.dumtech_licenca_valida(p_chave text, p_maquina text)
returns public.licencas
language plpgsql
security definer
set search_path = public
as $$
declare
    v_licenca public.licencas;
begin
    select * into v_licenca from licencas where chave = p_chave;

    -- os erros viajam como 'codigo|mensagem' e sao convertidos em JSON por quem chamou
    if not found then
        raise exception 'nao_encontrada|Chave nao encontrada. Confira os caracteres digitados.';
    end if;

    if v_licenca.status = 'suspensa' then
        raise exception 'inativa|Esta licenca esta suspensa. Fale com a DumTech.';
    end if;

    if v_licenca.status = 'cancelada' then
        raise exception 'inativa|Esta licenca foi cancelada. Fale com a DumTech.';
    end if;

    if v_licenca.expira_em is not null and v_licenca.expira_em < current_date then
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
set search_path = public
as $$
declare
    v_licenca public.licencas;
    v_usadas  integer;
    v_ja      boolean;
    v_texto   text;
begin
    p_chave   := upper(trim(coalesce(p_chave, '')));
    p_maquina := upper(trim(coalesce(p_maquina, '')));

    if p_chave = '' or p_maquina = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe a chave da licenca.');
    end if;

    v_licenca := dumtech_licenca_valida(p_chave, p_maquina);

    select exists(
        select 1 from ativacoes
         where licenca_id = v_licenca.id and maquina = p_maquina
    ) into v_ja;

    if v_ja then
        update ativacoes
           set ultima_checagem = now(),
               apelido = case when coalesce(p_apelido, '') <> '' then p_apelido else apelido end
         where licenca_id = v_licenca.id and maquina = p_maquina;
    else
        select count(*) into v_usadas from ativacoes where licenca_id = v_licenca.id;
        if v_usadas >= v_licenca.max_computadores then
            insert into licenca_tentativas (chave, maquina, erro)
            values (p_chave, p_maquina, 'limite_maquinas');
            return jsonb_build_object(
                'ok', false, 'erro', 'limite_maquinas',
                'mensagem', format(
                    'Esta licenca ja esta ativada em %s computador(es), o maximo do plano. '
                    || 'Desative em outro computador ou fale com a DumTech.',
                    v_licenca.max_computadores));
        end if;
        insert into ativacoes (licenca_id, maquina, apelido)
        values (v_licenca.id, p_maquina, coalesce(p_apelido, ''));
    end if;

    return dumtech_resposta_licenca(v_licenca.id);

exception
    when others then
        v_texto := sqlerrm;
        if position('|' in v_texto) > 0 then
            insert into licenca_tentativas (chave, maquina, erro)
            values (p_chave, p_maquina, split_part(v_texto, '|', 1));
            return jsonb_build_object('ok', false,
                                      'erro', split_part(v_texto, '|', 1),
                                      'mensagem', split_part(v_texto, '|', 2));
        end if;
        raise;
end;
$$;

-- ------------------------------------- VERIFICAR (comprou outro aplicativo) --
create or replace function public.dumtech_verificar_licenca(
    p_chave   text,
    p_maquina text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_licenca public.licencas;
    v_texto   text;
begin
    p_chave   := upper(trim(coalesce(p_chave, '')));
    p_maquina := upper(trim(coalesce(p_maquina, '')));

    if p_chave = '' or p_maquina = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe a chave da licenca.');
    end if;

    v_licenca := dumtech_licenca_valida(p_chave, p_maquina);

    update ativacoes
       set ultima_checagem = now()
     where licenca_id = v_licenca.id and maquina = p_maquina;

    if not found then
        return jsonb_build_object(
            'ok', false, 'erro', 'maquina_nao_ativada',
            'mensagem', 'Este computador ainda nao foi ativado com esta chave. '
                     || 'Use o botao Ativar licenca.');
    end if;

    return dumtech_resposta_licenca(v_licenca.id);

exception
    when others then
        v_texto := sqlerrm;
        if position('|' in v_texto) > 0 then
            insert into licenca_tentativas (chave, maquina, erro)
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
set search_path = public
as $$
declare
    v_id uuid;
begin
    p_chave   := upper(trim(coalesce(p_chave, '')));
    p_maquina := upper(trim(coalesce(p_maquina, '')));

    select id into v_id from licencas where chave = p_chave;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'nao_encontrada',
                                  'mensagem', 'Chave nao encontrada.');
    end if;

    delete from ativacoes where licenca_id = v_id and maquina = p_maquina;
    return jsonb_build_object('ok', true, 'removido', found);
end;
$$;

-- ------------------------------------------- gerador de chaves (era o 03_) ---
-- formato XXXX-XXXX-XXXX-XXXX, sem as letras/numeros que o cliente confunde
create or replace function public.dumtech_nova_chave()
returns text
language plpgsql
as $$
declare
    v_alfabeto text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    v_chave    text := '';
    v_i        integer;
begin
    for v_i in 1..16 loop
        v_chave := v_chave || substr(v_alfabeto, 1 + floor(random() * length(v_alfabeto))::int, 1);
        if v_i in (4, 8, 12) then
            v_chave := v_chave || '-';
        end if;
    end loop;
    return v_chave;
end;
$$;

-- ------------------------------------------------------------- permissoes ---
-- O aplicativo (chave anon) so pode chamar as tres funcoes publicas abaixo.
revoke execute on function public.dumtech_licenca_valida(text, text) from public;
revoke execute on function public.dumtech_resposta_licenca(uuid) from public;
revoke execute on function public.dumtech_nova_chave() from public;

grant execute on function public.dumtech_ativar_licenca(text, text, text) to anon, authenticated;
grant execute on function public.dumtech_verificar_licenca(text, text) to anon, authenticated;
grant execute on function public.dumtech_desativar_licenca(text, text) to anon, authenticated;

notify pgrst, 'reload schema';
