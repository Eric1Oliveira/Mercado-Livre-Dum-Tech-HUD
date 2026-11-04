-- =============================================================================
-- Controle da mensalidade pelo painel. Desenho:
-- docs/superpowers/specs/2026-11-04-controle-da-mensalidade-design.md
--
-- O QUE ENTRA
--   1. Os modulos ganham papel (base | adicional | fora), preco e "a venda".
--   2. Planos prontos (qualquer combinacao, preco e link proprios, de/por).
--   3. Links do "monte o seu" por combinacao de adicionais.
--   4. Cupom: codigo -> plano escondido com preco e link proprios.
--   5. A licenca guarda o plano e o valor combinado na confirmacao.
--   6. Historico de tudo que acontece com cada assinatura (quem fez e o que).
--   7. A ficha do assinante: ajustar, ativar sem pedido e reabrir.
--   8. Os textos da landing: rascunho, publicar e voltar a uma versao.
--   9. A faixa de aviso do site.
--  10. A vitrine publica traz tudo isso numa chamada so.
--
-- O QUE NAO MUDA
--   Licenca vitalicia (nenhuma funcao daqui a lista, ajusta ou cobra) e o Hub.
--   O preco e o link SEMPRE saem daqui: o navegador so mostra.
-- =============================================================================

-- ================================================================ pecas ====
create or replace function public.dumtech_link_valido(p_link text)
returns boolean language sql immutable set search_path = ''
as $$ select coalesce(p_link, '') = '' or p_link ~ '^https://[^[:space:]<>"]+$' $$;

/** A chave de uma combinacao de adicionais: em ordem alfabetica, com "+". "" = so a base. */
create or replace function public.dumtech_chave_combinacao(p_adicionais text[])
returns text language sql immutable set search_path = ''
as $$
    select coalesce(string_agg(t.codigo, '+' order by t.codigo), '')
      from (select distinct upper(btrim(x)) as codigo
              from unnest(coalesce(p_adicionais, '{}'::text[])) as x
             where btrim(x) <> '') t;
$$;

create or replace function public.dumtech_promo_vigente(p_promo_preco numeric, p_promo_ate date)
returns boolean language sql stable set search_path = ''
as $$ select p_promo_preco is not null and p_promo_ate is not null and p_promo_ate >= current_date $$;

-- ============================================================ 1. MODULOS ===
create table if not exists public.mensalidade_modulos (
    codigo  text primary key references public.produtos(codigo) on update cascade,
    papel   text not null check (papel in ('base', 'adicional', 'fora')),
    preco   numeric(10,2) not null default 0 check (preco >= 0),
    a_venda boolean not null default true,
    ordem   integer not null default 0
);
comment on table public.mensalidade_modulos is
    'Mensalidade: o papel de cada modulo (base, adicional ou fora), o preco do adicional e se esta a venda.';

insert into public.mensalidade_modulos (codigo, papel, preco, ordem)
select p.codigo,
       case when p.codigo in ('VENDAS', 'ESTOQUE', 'FINANCEIRO') then 'base'
            when p.codigo in ('CLIENTES', 'ORCAMENTOS', 'ORDENS', 'AGENDA') then 'adicional'
            else 'fora' end,
       case when p.codigo in ('CLIENTES', 'ORCAMENTOS', 'ORDENS', 'AGENDA') then 29.90 else 0 end,
       coalesce(array_position(array['VENDAS', 'ESTOQUE', 'FINANCEIRO', 'CLIENTES', 'ORCAMENTOS',
                                     'ORDENS', 'AGENDA'], p.codigo), 99)
  from public.produtos p
on conflict (codigo) do nothing;

-- base e adicionais passam a vir da tabela (o corpo antigo era fixo)
create or replace function public.dumtech_plano_base()
returns text[] language sql stable set search_path = ''
as $$
    select coalesce(array_agg(m.codigo order by m.ordem, m.codigo), '{}'::text[])
      from public.mensalidade_modulos m where m.papel = 'base';
$$;

create or replace function public.dumtech_plano_adicionais()
returns text[] language sql stable set search_path = ''
as $$
    select coalesce(array_agg(m.codigo order by m.ordem, m.codigo), '{}'::text[])
      from public.mensalidade_modulos m where m.papel = 'adicional';
$$;

/** So adicional de verdade, sem repetir, na ordem da vitrine. */
create or replace function public.dumtech_adicionais_validos(p_adicionais text[])
returns text[] language sql stable set search_path = ''
as $$
    select coalesce(array_agg(m.codigo order by m.ordem, m.codigo), '{}'::text[])
      from public.mensalidade_modulos m
     where m.papel = 'adicional'
       and m.codigo in (select upper(btrim(x)) from unnest(coalesce(p_adicionais, '{}'::text[])) as x);
$$;

/** Qualquer modulo que pode entrar num plano (base ou adicional), na ordem da vitrine. */
create or replace function public.dumtech_modulos_validos(p_modulos text[])
returns text[] language sql stable set search_path = ''
as $$
    select coalesce(array_agg(m.codigo order by m.ordem, m.codigo), '{}'::text[])
      from public.mensalidade_modulos m
     where m.papel <> 'fora'
       and m.codigo in (select upper(btrim(x)) from unnest(coalesce(p_modulos, '{}'::text[])) as x);
$$;

-- ======================================================= 2. A CONFIG ====
-- preco unico do adicional e os 5 links por quantidade dao lugar ao preco por
-- adicional e aos links por combinacao. Em producao nao havia link nenhum.
drop view if exists public.painel_mensalidades;
drop function if exists public.dumtech_valor_mensal(integer);
alter table public.mensalidade_config drop column if exists links;
alter table public.mensalidade_config drop column if exists preco_adicional;
drop function if exists public.dumtech_links_validos(jsonb);

/** Quanto custa por mes um conjunto de modulos montado: a base + cada adicional. */
create or replace function public.dumtech_valor_dos_modulos(p_modulos text[])
returns numeric language sql stable security definer set search_path = ''
as $$
    select c.preco_base + coalesce((
        select sum(m.preco) from public.mensalidade_modulos m
         where m.papel = 'adicional' and m.codigo = any(coalesce(p_modulos, '{}'::text[]))), 0)
      from public.mensalidade_config c where c.id;
$$;

-- ==================================================== 3. PLANOS PRONTOS ===
create table if not exists public.mensalidade_planos (
    id            uuid primary key default gen_random_uuid(),
    nome          text not null check (length(btrim(nome)) between 1 and 60),
    descricao     text not null default '' check (length(descricao) <= 240),
    modulos       text[] not null default '{}',
    preco         numeric(10,2) not null check (preco >= 0),
    link          text not null default '' check (public.dumtech_link_valido(link)),
    destaque      boolean not null default false,
    visivel       boolean not null default true,
    ordem         integer not null default 0,
    ativo         boolean not null default true,
    promo_preco   numeric(10,2) check (promo_preco is null or promo_preco >= 0),
    promo_link    text not null default '' check (public.dumtech_link_valido(promo_link)),
    promo_rotulo  text not null default '' check (length(promo_rotulo) <= 40),
    promo_ate     date,
    criado_em     timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    constraint mensalidade_planos_promo_check check (promo_preco is null or promo_ate is not null)
);
comment on table public.mensalidade_planos is
    'Planos prontos da mensalidade: qualquer combinacao de modulos, com preco e link da InfinitePay. visivel = false: so por cupom.';

create or replace function public.dumtech_normalizar_plano()
returns trigger language plpgsql set search_path = ''
as $$
begin
    new.nome := btrim(new.nome);
    new.descricao := btrim(coalesce(new.descricao, ''));
    new.promo_rotulo := btrim(coalesce(new.promo_rotulo, ''));
    new.modulos := public.dumtech_modulos_validos(new.modulos);
    if cardinality(new.modulos) = 0 then
        raise exception 'Escolha ao menos um módulo para o plano.' using errcode = '23514';
    end if;
    new.atualizado_em := now();
    return new;
end;
$$;
drop trigger if exists trg_mensalidade_planos on public.mensalidade_planos;
create trigger trg_mensalidade_planos before insert or update on public.mensalidade_planos
    for each row execute function public.dumtech_normalizar_plano();

/** O plano como a vitrine mostra: preco e link VIGENTES (de/por), sem o link. */
create or replace function public.dumtech_plano_json(p public.mensalidade_planos)
returns jsonb language sql stable set search_path = ''
as $$
    select jsonb_build_object(
        'id', p.id, 'nome', p.nome, 'descricao', p.descricao, 'modulos', to_jsonb(p.modulos),
        'destaque', p.destaque,
        'preco', case when promo then p.promo_preco else p.preco end,
        'preco_cheio', case when promo then p.preco end,
        'promo_rotulo', case when promo then nullif(p.promo_rotulo, '') end,
        'promo_ate', case when promo then p.promo_ate end,
        -- promocao sem link proprio nao cobra o valor promocional: vai para o WhatsApp
        'assinavel', (case when promo then p.promo_link else p.link end) <> '')
      from (select public.dumtech_promo_vigente(p.promo_preco, p.promo_ate) as promo) v;
$$;

-- ==================================================== 4. COMBINACOES ====
create table if not exists public.mensalidade_combinacoes (
    chave         text primary key check (chave ~ '^([A-Z][A-Z0-9_]*(\+[A-Z][A-Z0-9_]*)*)?$'),
    link          text not null default '' check (public.dumtech_link_valido(link)),
    atualizado_em timestamptz not null default now()
);
comment on table public.mensalidade_combinacoes is
    'Monte o seu: o link da InfinitePay de cada combinacao de adicionais (chave = adicionais em ordem alfabetica com +; vazio = so a base).';

create or replace function public.dumtech_normalizar_combinacao()
returns trigger language plpgsql set search_path = ''
as $$
begin
    new.chave := public.dumtech_chave_combinacao(string_to_array(coalesce(new.chave, ''), '+'));
    new.atualizado_em := now();
    return new;
end;
$$;
drop trigger if exists trg_mensalidade_combinacoes on public.mensalidade_combinacoes;
create trigger trg_mensalidade_combinacoes before insert or update on public.mensalidade_combinacoes
    for each row execute function public.dumtech_normalizar_combinacao();

-- ========================================================= 5. CUPONS ====
create table if not exists public.mensalidade_cupons (
    codigo     text primary key check (codigo ~ '^[A-Z0-9_-]{3,32}$'),
    plano_id   uuid not null references public.mensalidade_planos(id) on delete restrict,
    descricao  text not null default '' check (length(descricao) <= 120),
    parceiro   text not null default '' check (length(parceiro) <= 80),
    valido_ate date,
    usos_max   integer check (usos_max is null or usos_max > 0),
    ativo      boolean not null default true,
    criado_em  timestamptz not null default now()
);
comment on table public.mensalidade_cupons is
    'Cupom da mensalidade: o codigo libera um plano (normalmente escondido) com preco e link proprios.';

create or replace function public.dumtech_normalizar_cupom()
returns trigger language plpgsql set search_path = ''
as $$
begin
    new.codigo := upper(btrim(new.codigo));
    new.descricao := btrim(coalesce(new.descricao, ''));
    new.parceiro := btrim(coalesce(new.parceiro, ''));
    return new;
end;
$$;
drop trigger if exists trg_mensalidade_cupons on public.mensalidade_cupons;
create trigger trg_mensalidade_cupons before insert or update on public.mensalidade_cupons
    for each row execute function public.dumtech_normalizar_cupom();

-- ============================================ 6. PEDIDO E LICENCA ======
alter table public.assinatura_pedidos add column if not exists plano_id uuid
    references public.mensalidade_planos(id) on delete set null;
alter table public.assinatura_pedidos add column if not exists modulos text[] not null default '{}';
alter table public.assinatura_pedidos add column if not exists cupom text not null default '';

alter table public.licencas add column if not exists plano_id uuid
    references public.mensalidade_planos(id) on delete set null;
alter table public.licencas add column if not exists valor_mensal numeric(10,2);
alter table public.licencas drop constraint if exists licencas_valor_mensal_check;
alter table public.licencas add constraint licencas_valor_mensal_check
    check (valor_mensal is null or valor_mensal >= 0);
comment on column public.licencas.valor_mensal is
    'Mensalidade: o valor combinado, gravado na confirmacao (mudar o preco do plano depois nao mexe nele).';

/** Um cupom que vale agora (ativo, no prazo, com uso sobrando e plano ativo), ou nada. */
create or replace function public.dumtech_cupom_vigente(p_codigo text)
returns public.mensalidade_cupons language plpgsql stable security definer set search_path = ''
as $$
declare
    v_cupom public.mensalidade_cupons;
begin
    select c.* into v_cupom
      from public.mensalidade_cupons c
      join public.mensalidade_planos p on p.id = c.plano_id
     where c.codigo = upper(btrim(coalesce(p_codigo, '')))
       and c.ativo and p.ativo
       and (c.valido_ate is null or c.valido_ate >= current_date)
       and (c.usos_max is null or c.usos_max > (
              select count(*) from public.assinatura_pedidos ap
               where ap.cupom = c.codigo and ap.situacao <> 'descartado'));
    return v_cupom;
end;
$$;

-- ======================================================== 7. EVENTOS =====
create table if not exists public.assinatura_eventos (
    id         bigint generated always as identity primary key,
    licenca_id uuid not null references public.licencas(id) on delete cascade,
    tipo       text not null,
    detalhe    jsonb not null default '{}'::jsonb,
    admin_id   uuid,
    criado_em  timestamptz not null default now()
);
comment on table public.assinatura_eventos is
    'O historico de cada assinatura: o que aconteceu, de -> para, quando e quem fez (admin_id vazio = o site).';
create index if not exists idx_assinatura_eventos_licenca on public.assinatura_eventos (licenca_id, id desc);

create or replace function public.dumtech_registrar_evento(p_licenca uuid, p_tipo text, p_detalhe jsonb default '{}')
returns void language sql security definer set search_path = ''
as $$
    insert into public.assinatura_eventos (licenca_id, tipo, detalhe, admin_id)
    values (p_licenca, p_tipo, coalesce(jsonb_strip_nulls(p_detalhe), '{}'::jsonb), public.dumtech_admin_id());
$$;

/** Os modulos de uma licenca, em ordem alfabetica. */
create or replace function public.dumtech_modulos_da_licenca(p_licenca uuid)
returns text[] language sql stable security definer set search_path = ''
as $$
    select coalesce(array_agg(p.codigo order by p.codigo), '{}'::text[])
      from public.licenca_produtos lp join public.produtos p on p.id = lp.produto_id
     where lp.licenca_id = p_licenca;
$$;

/** Troca os modulos de uma licenca por estes (so os que existem). */
create or replace function public.dumtech_trocar_modulos(p_licenca uuid, p_modulos text[])
returns void language plpgsql security definer set search_path = ''
as $$
begin
    delete from public.licenca_produtos lp
     using public.produtos p
     where lp.licenca_id = p_licenca and p.id = lp.produto_id and not (p.codigo = any(p_modulos));
    insert into public.licenca_produtos (licenca_id, produto_id)
    select p_licenca, p.id from public.produtos p where p.codigo = any(p_modulos)
    on conflict (licenca_id, produto_id) do nothing;
end;
$$;

-- ================================================= 8. TEXTOS DO SITE =====
create table if not exists public.landing_conteudo (
    id            text primary key check (id in ('rascunho', 'publicado')),
    conteudo      jsonb not null default '{}'::jsonb
                  check (jsonb_typeof(conteudo) = 'object' and pg_column_size(conteudo) < 65536),
    atualizado_em timestamptz not null default now(),
    admin_id      uuid
);
comment on table public.landing_conteudo is
    'Os textos da landing: o rascunho (so o painel ve) e o publicado (a vitrine entrega).';
insert into public.landing_conteudo (id) values ('rascunho'), ('publicado') on conflict (id) do nothing;

create table if not exists public.landing_publicacoes (
    id           uuid primary key default gen_random_uuid(),
    conteudo     jsonb not null,
    publicado_em timestamptz not null default now(),
    admin_id     uuid
);

create or replace function public.dumtech_tocar_conteudo()
returns trigger language plpgsql set search_path = ''
as $$
begin
    new.atualizado_em := now();
    new.admin_id := public.dumtech_admin_id();
    return new;
end;
$$;
drop trigger if exists trg_landing_conteudo on public.landing_conteudo;
create trigger trg_landing_conteudo before update on public.landing_conteudo
    for each row execute function public.dumtech_tocar_conteudo();

create or replace function public.dumtech_publicar_landing()
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
    v_conteudo jsonb;
    v_id       uuid;
begin
    perform public.dumtech_painel_portao();
    select conteudo into v_conteudo from public.landing_conteudo where id = 'rascunho';
    update public.landing_conteudo set conteudo = v_conteudo where id = 'publicado';
    insert into public.landing_publicacoes (conteudo, admin_id)
    values (v_conteudo, public.dumtech_admin_id())
    returning id into v_id;
    return jsonb_build_object('ok', true, 'id', v_id);
end;
$$;

create or replace function public.dumtech_voltar_landing(p_publicacao uuid)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
    v_conteudo jsonb;
    v_id       uuid;
begin
    perform public.dumtech_painel_portao();
    select conteudo into v_conteudo from public.landing_publicacoes where id = p_publicacao;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'versao', 'mensagem', 'Esta versão não existe mais.');
    end if;
    update public.landing_conteudo set conteudo = v_conteudo where id in ('rascunho', 'publicado');
    -- voltar tambem e publicar: o historico mostra a volta
    insert into public.landing_publicacoes (conteudo, admin_id)
    values (v_conteudo, public.dumtech_admin_id())
    returning id into v_id;
    return jsonb_build_object('ok', true, 'id', v_id);
end;
$$;

-- =================================================== 9. FAIXA DE AVISO ===
create table if not exists public.landing_avisos (
    id        uuid primary key default gen_random_uuid(),
    texto     text not null check (length(btrim(texto)) between 1 and 160),
    link      text not null default '' check (link = '' or link ~ '^(https://[^[:space:]<>"]+|#[a-z0-9-]+)$'),
    tom       text not null default 'violeta' check (tom in ('violeta', 'verde', 'ambar')),
    inicio    date not null default current_date,
    fim       date,
    ativo     boolean not null default true,
    criado_em timestamptz not null default now(),
    constraint landing_avisos_periodo_check check (fim is null or fim >= inicio)
);
comment on table public.landing_avisos is
    'A faixa de aviso no topo da landing. Vale a mais nova que esta ativa e no periodo.';

-- ======================================================= 10. VITRINE =====
create or replace function public.dumtech_mensalidade_publica()
returns jsonb language sql stable security definer set search_path = ''
as $$
    select jsonb_build_object(
        'ok', true,
        'preco_base', c.preco_base,
        'dias_teste', c.dias_teste,
        'computadores', c.computadores,
        'base', to_jsonb(public.dumtech_plano_base()),
        'adicionais', coalesce((
            select jsonb_agg(jsonb_build_object('codigo', m.codigo, 'preco', m.preco) order by m.ordem, m.codigo)
              from public.mensalidade_modulos m where m.papel = 'adicional' and m.a_venda), '[]'::jsonb),
        'planos', coalesce((
            select jsonb_agg(public.dumtech_plano_json(p) order by p.ordem, p.criado_em)
              from public.mensalidade_planos p where p.ativo and p.visivel), '[]'::jsonb),
        -- quais combinacoes tem link (o link mesmo so volta depois do cadastro)
        'combinacoes', coalesce((
            select jsonb_agg(k.chave order by k.chave)
              from public.mensalidade_combinacoes k where k.link <> ''), '[]'::jsonb),
        'conteudo', coalesce((select l.conteudo from public.landing_conteudo l where l.id = 'publicado'), '{}'::jsonb),
        'aviso', (
            select jsonb_build_object('id', a.id, 'texto', a.texto, 'link', a.link, 'tom', a.tom)
              from public.landing_avisos a
             where a.ativo and a.inicio <= current_date and (a.fim is null or a.fim >= current_date)
             order by a.criado_em desc
             limit 1))
      from public.mensalidade_config c where c.id;
$$;

/** O site confere um cupom. Inexistente, vencido e esgotado respondem igual. */
create or replace function public.dumtech_cupom_publico(p_codigo text)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
    v_cupom public.mensalidade_cupons;
    v_plano public.mensalidade_planos;
begin
    if not public.dumtech_dentro_do_limite('cupom_ip', public.dumtech_ip_do_pedido(), 30, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos e tente de novo.');
    end if;
    v_cupom := public.dumtech_cupom_vigente(p_codigo);
    if v_cupom.codigo is null then
        return jsonb_build_object('ok', false, 'erro', 'cupom',
            'mensagem', 'Não encontramos esse cupom, ou ele não vale mais. Confira o código.');
    end if;
    select * into v_plano from public.mensalidade_planos where id = v_cupom.plano_id;
    return jsonb_build_object('ok', true, 'codigo', v_cupom.codigo, 'descricao', v_cupom.descricao,
                              'plano', public.dumtech_plano_json(v_plano));
end;
$$;

-- ===================================================== 11. CADASTRO ======
-- O corpo de 20261103120000 + plano pronto, cupom, preco por adicional, link
-- por combinacao e os eventos. A assinatura antiga (6 parametros) continua
-- valendo: os novos tem padrao.
drop function if exists public.dumtech_cadastrar_mensal(text, text, text, text[], boolean, text);
create or replace function public.dumtech_cadastrar_mensal(
    p_nome       text,
    p_email      text,
    p_telefone   text    default '',
    p_adicionais text[]  default '{}',
    p_assinar    boolean default false,
    p_ip         text    default '',
    p_plano      uuid    default null,
    p_cupom      text    default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_nome       text := left(btrim(coalesce(p_nome, '')), 120);
    v_email      text := lower(left(btrim(coalesce(p_email, '')), 160));
    v_telefone   text := left(regexp_replace(coalesce(p_telefone, ''), '[^0-9]', '', 'g'), 20);
    v_assinar    boolean := coalesce(p_assinar, false);
    v_config     public.mensalidade_config;
    v_cliente    public.clientes;
    v_licenca    public.licencas;
    v_plano      public.mensalidade_planos;
    v_cupom      public.mensalidade_cupons;
    v_id         uuid;
    v_caso       text;
    v_adicionais text[] := '{}';
    v_modulos    text[] := '{}';
    v_link       text := '';
    v_valor      numeric;
    v_promo      boolean;
begin
    if not public.dumtech_dentro_do_limite('mensal_ip', coalesce(nullif(btrim(p_ip), ''), 'sem-ip'),
                                           5, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Recebemos muitos cadastros seguidos daqui. Espere alguns minutos e tente de novo.');
    end if;
    if v_nome = '' then
        return jsonb_build_object('ok', false, 'erro', 'nome',
            'mensagem', 'Conte para a gente o seu nome ou o da sua empresa.');
    end if;
    if not public.dumtech_email_valido(v_email) then
        return jsonb_build_object('ok', false, 'erro', 'email_invalido',
            'mensagem', 'Confira o e-mail digitado: é por ele que a sua chave chega.');
    end if;

    -- o que vai ser assinado, conferido ANTES de criar qualquer coisa
    if v_assinar and coalesce(btrim(p_cupom), '') <> '' then
        v_cupom := public.dumtech_cupom_vigente(p_cupom);
        if v_cupom.codigo is null then
            return jsonb_build_object('ok', false, 'erro', 'cupom',
                'mensagem', 'Não encontramos esse cupom, ou ele não vale mais. Confira o código.');
        end if;
        select * into v_plano from public.mensalidade_planos where id = v_cupom.plano_id;
    elsif v_assinar and p_plano is not null then
        select * into v_plano from public.mensalidade_planos where id = p_plano and ativo and visivel;
        if not found then
            return jsonb_build_object('ok', false, 'erro', 'plano',
                'mensagem', 'Esse plano não está mais disponível. Escolha outro, por favor.');
        end if;
    end if;

    select * into v_config from public.mensalidade_config where id;

    select * into v_cliente from public.clientes where lower(email) = v_email;
    if not found then
        insert into public.clientes (nome, email, telefone, origem)
        values (v_nome, v_email, v_telefone, 'venda')
        returning * into v_cliente;
    elsif v_cliente.telefone = '' and v_telefone <> '' then
        update public.clientes set telefone = v_telefone where id = v_cliente.id;
    end if;

    -- a licenca que vale: vitalicia primeiro (nunca empurrar mensalidade a quem
    -- e para sempre), depois a mais nova
    select * into v_licenca from public.licencas l
     where l.cliente_id = v_cliente.id and l.status <> 'cancelada'
     order by (l.tipo = 'vitalicia') desc, l.criado_em desc
     limit 1;

    if found and v_licenca.tipo = 'vitalicia' then
        v_caso := 'vitalicio';
    elsif found then
        v_caso := 'ja_tem';
    else
        -- o teste e sempre completo, seja qual for o plano pedido
        select e.licenca_id into v_id
          from public.dumtech_emitir_licenca(
                   v_cliente.id,
                   public.dumtech_plano_base() || public.dumtech_plano_adicionais(),
                   null, 'teste', current_date + v_config.dias_teste, v_config.computadores,
                   'Teste do plano mensal pelo site') e;
        select * into v_licenca from public.licencas where id = v_id;
        v_caso := 'nova';
        perform public.dumtech_registrar_evento(v_id, 'teste', jsonb_build_object('ate', v_licenca.expira_em));
    end if;

    -- preco e link: aqui, nunca no navegador. Saem iguais para todos os casos
    -- (a resposta nao pode contar quem ja e cliente)
    if v_assinar then
        if v_plano.id is not null then
            v_promo := public.dumtech_promo_vigente(v_plano.promo_preco, v_plano.promo_ate);
            v_modulos := v_plano.modulos;
            v_adicionais := public.dumtech_adicionais_validos(v_plano.modulos);
            v_valor := case when v_promo then v_plano.promo_preco else v_plano.preco end;
            v_link := case when v_promo then v_plano.promo_link else v_plano.link end;
        else
            select coalesce(array_agg(m.codigo order by m.ordem, m.codigo), '{}'::text[]) into v_adicionais
              from public.mensalidade_modulos m
             where m.papel = 'adicional' and m.a_venda
               and m.codigo = any(public.dumtech_adicionais_validos(p_adicionais));
            v_modulos := public.dumtech_plano_base() || v_adicionais;
            v_valor := public.dumtech_valor_dos_modulos(v_modulos);
            v_link := coalesce((select k.link from public.mensalidade_combinacoes k
                                 where k.chave = public.dumtech_chave_combinacao(v_adicionais)), '');
        end if;
    end if;

    if v_assinar and v_caso <> 'vitalicio' then
        -- pedir de novo troca o pedido que esperava: um por licenca
        update public.assinatura_pedidos
           set situacao = 'descartado', resolvido_em = now()
         where licenca_id = v_licenca.id and situacao = 'aguardando';
        insert into public.assinatura_pedidos (licenca_id, adicionais, modulos, plano_id, cupom, valor, link)
        values (v_licenca.id, v_adicionais, v_modulos, v_plano.id, coalesce(v_cupom.codigo, ''), v_valor, v_link);
        perform public.dumtech_registrar_evento(v_licenca.id, 'pediu', jsonb_build_object(
            'plano', v_plano.nome, 'modulos', v_modulos, 'valor', v_valor, 'cupom', v_cupom.codigo));
    end if;

    return jsonb_build_object(
        'ok', true,
        'caso', v_caso,
        'nome', v_cliente.nome,
        'email', v_cliente.email,
        'chave', case when v_caso = 'vitalicio' then null else v_licenca.chave end,
        'tipo', v_licenca.tipo,
        'ate', case when v_caso = 'vitalicio' then null else v_licenca.expira_em end,
        'dias_teste', v_config.dias_teste,
        'assinar', v_assinar,
        'plano', v_plano.nome,
        'modulos', to_jsonb(v_modulos),
        'adicionais', to_jsonb(v_adicionais),
        'valor', v_valor,
        'link', v_link);
end;
$$;

-- =============================================== 12. ACOES DO PAINEL =====
create or replace function public.dumtech_confirmar_assinatura(p_pedido uuid)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
    v_pedido  public.assinatura_pedidos;
    v_licenca public.licencas;
    v_cliente public.clientes;
    v_codigos text[];
    v_mudanca boolean;
    v_plano   text;
begin
    perform public.dumtech_painel_portao();

    select * into v_pedido from public.assinatura_pedidos where id = p_pedido for update;
    if not found or v_pedido.situacao <> 'aguardando' then
        return jsonb_build_object('ok', false, 'erro', 'pedido',
                                  'mensagem', 'Este pedido já foi resolvido ou não existe mais.');
    end if;
    select * into v_licenca from public.licencas where id = v_pedido.licenca_id for update;
    if v_licenca.tipo = 'vitalicia' then
        return jsonb_build_object('ok', false, 'erro', 'tipo',
                                  'mensagem', 'Licença vitalícia não vira mensalidade.');
    end if;

    v_mudanca := v_licenca.tipo = 'assinatura';
    v_codigos := case when cardinality(v_pedido.modulos) > 0 then v_pedido.modulos
                      else public.dumtech_plano_base() || public.dumtech_adicionais_validos(v_pedido.adicionais) end;
    select nome into v_plano from public.mensalidade_planos where id = v_pedido.plano_id;

    update public.licencas
       set tipo = 'assinatura', expira_em = null, cobranca_motivo = null, cobranca_desde = null,
           assinatura_desde = case when v_mudanca then coalesce(assinatura_desde, current_date)
                                   else current_date end,
           plano_id = v_pedido.plano_id, valor_mensal = v_pedido.valor
     where id = v_licenca.id;
    perform public.dumtech_trocar_modulos(v_licenca.id, v_codigos);

    update public.assinatura_pedidos set situacao = 'confirmado', resolvido_em = now() where id = v_pedido.id;
    update public.assinatura_pedidos set situacao = 'descartado', resolvido_em = now()
     where licenca_id = v_licenca.id and situacao = 'aguardando';
    perform public.dumtech_registrar_evento(v_licenca.id, 'confirmou', jsonb_build_object(
        'plano', v_plano, 'modulos', v_codigos, 'valor', v_pedido.valor, 'cupom', nullif(v_pedido.cupom, ''),
        'mudanca', v_mudanca));

    select * into v_cliente from public.clientes where id = v_licenca.cliente_id;
    return jsonb_build_object(
        'ok', true, 'nome', v_cliente.nome, 'email', v_cliente.email, 'telefone', v_cliente.telefone,
        'chave', v_licenca.chave, 'plano', v_plano, 'modulos', to_jsonb(v_codigos),
        'adicionais', to_jsonb(public.dumtech_adicionais_validos(v_codigos)),
        'valor', v_pedido.valor, 'mudanca', v_mudanca);
end;
$$;

create or replace function public.dumtech_descartar_assinatura(p_pedido uuid)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
    v_licenca uuid;
begin
    perform public.dumtech_painel_portao();
    update public.assinatura_pedidos set situacao = 'descartado', resolvido_em = now()
     where id = p_pedido and situacao = 'aguardando'
    returning licenca_id into v_licenca;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'pedido',
                                  'mensagem', 'Este pedido já foi resolvido ou não existe mais.');
    end if;
    perform public.dumtech_registrar_evento(v_licenca, 'descartou');
    return jsonb_build_object('ok', true);
end;
$$;

create or replace function public.dumtech_cobranca(p_licenca uuid, p_acao text, p_ate date default null)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
    v_licenca public.licencas;
    v_cliente public.clientes;
    v_dias    integer;
begin
    perform public.dumtech_painel_portao();

    select * into v_licenca from public.licencas where id = p_licenca for update;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'licenca', 'mensagem', 'Licença não encontrada.');
    end if;
    if v_licenca.tipo <> 'assinatura' then
        return jsonb_build_object('ok', false, 'erro', 'tipo',
                                  'mensagem', 'Só dá para marcar cobrança em licença de mensalidade.');
    end if;
    select dias_carencia into v_dias from public.mensalidade_config where id;

    if p_acao = 'falhou' then
        update public.licencas
           set expira_em = case when cobranca_motivo = 'falhou' and expira_em is not null
                                then expira_em else current_date + v_dias end,
               cobranca_desde = case when cobranca_motivo = 'falhou' and cobranca_desde is not null
                                     then cobranca_desde else current_date end,
               cobranca_motivo = 'falhou'
         where id = p_licenca;
    elsif p_acao = 'em_dia' then
        update public.licencas
           set expira_em = null, cobranca_motivo = null, cobranca_desde = null
         where id = p_licenca;
    elsif p_acao = 'cancelou' then
        if p_ate is not null and p_ate < current_date then
            return jsonb_build_object('ok', false, 'erro', 'data',
                                      'mensagem', 'A data de encerramento não pode ficar no passado.');
        end if;
        update public.licencas
           set expira_em = coalesce(p_ate, current_date + v_dias), cobranca_motivo = 'cancelou',
               cobranca_desde = current_date
         where id = p_licenca;
    else
        return jsonb_build_object('ok', false, 'erro', 'acao', 'mensagem', 'Ação desconhecida.');
    end if;

    select * into v_licenca from public.licencas where id = p_licenca;
    perform public.dumtech_registrar_evento(p_licenca, p_acao, jsonb_build_object('ate', v_licenca.expira_em));
    select * into v_cliente from public.clientes where id = v_licenca.cliente_id;
    return jsonb_build_object('ok', true, 'acao', p_acao, 'nome', v_cliente.nome,
                              'email', v_cliente.email, 'telefone', v_cliente.telefone,
                              'ate', v_licenca.expira_em);
end;
$$;

create or replace function public.dumtech_estender_teste_mensal(p_licenca uuid, p_dias integer default 7)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
    v_licenca public.licencas;
    v_cliente public.clientes;
begin
    perform public.dumtech_painel_portao();
    if coalesce(p_dias, 0) not between 1 and 60 then
        return jsonb_build_object('ok', false, 'erro', 'dias', 'mensagem', 'Escolha de 1 a 60 dias.');
    end if;
    select * into v_licenca from public.licencas where id = p_licenca for update;
    if not found or v_licenca.tipo <> 'teste' then
        return jsonb_build_object('ok', false, 'erro', 'tipo',
                                  'mensagem', 'Só dá para estender o teste do plano mensal.');
    end if;
    update public.licencas set expira_em = greatest(expira_em, current_date) + p_dias
     where id = p_licenca
    returning * into v_licenca;
    perform public.dumtech_registrar_evento(p_licenca, 'estendeu',
        jsonb_build_object('dias', p_dias, 'ate', v_licenca.expira_em));
    select * into v_cliente from public.clientes where id = v_licenca.cliente_id;
    return jsonb_build_object('ok', true, 'nome', v_cliente.nome, 'email', v_cliente.email,
                              'telefone', v_cliente.telefone, 'ate', v_licenca.expira_em);
end;
$$;

/** A ficha: muda so o que veio preenchido, e o evento guarda de -> para. */
create or replace function public.dumtech_ajustar_assinatura(
    p_licenca      uuid,
    p_plano        uuid    default null,
    p_modulos      text[]  default null,
    p_valor        numeric default null,
    p_computadores integer default null,
    p_ate          date    default null,
    p_observacoes  text    default null
)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
    v_licenca public.licencas;
    v_cliente public.clientes;
    v_plano   public.mensalidade_planos;
    v_antes   text[];
    v_modulos text[];
    v_usados  integer;
    v_mudou   jsonb := '{}'::jsonb;
begin
    perform public.dumtech_painel_portao();

    select * into v_licenca from public.licencas where id = p_licenca for update;
    if not found or v_licenca.tipo not in ('assinatura', 'teste') then
        return jsonb_build_object('ok', false, 'erro', 'tipo',
                                  'mensagem', 'Só dá para ajustar licença de mensalidade.');
    end if;
    v_antes := public.dumtech_modulos_da_licenca(p_licenca);

    if p_plano is not null then
        select * into v_plano from public.mensalidade_planos where id = p_plano;
        if not found then
            return jsonb_build_object('ok', false, 'erro', 'plano', 'mensagem', 'Plano não encontrado.');
        end if;
        v_modulos := v_plano.modulos;
    elsif p_modulos is not null then
        v_modulos := public.dumtech_modulos_validos(p_modulos);
        if cardinality(v_modulos) = 0 then
            return jsonb_build_object('ok', false, 'erro', 'modulos', 'mensagem', 'Escolha ao menos um módulo.');
        end if;
    end if;

    if p_valor is not null and p_valor < 0 then
        return jsonb_build_object('ok', false, 'erro', 'valor', 'mensagem', 'O valor não pode ser negativo.');
    end if;
    if p_computadores is not null then
        select count(*) into v_usados from public.ativacoes where licenca_id = p_licenca;
        if p_computadores > 50 or p_computadores < 1 then
            return jsonb_build_object('ok', false, 'erro', 'computadores', 'mensagem', 'Escolha de 1 a 50 computadores.');
        end if;
        if p_computadores < v_usados then
            return jsonb_build_object('ok', false, 'erro', 'computadores',
                'mensagem', format('Esta chave está em uso em %s computadores. Para diminuir, libere um deles na tela Acessos.', v_usados));
        end if;
    end if;
    if p_ate is not null then
        if v_licenca.expira_em is null then
            return jsonb_build_object('ok', false, 'erro', 'data',
                'mensagem', 'Esta assinatura está em dia e não tem data. Para dar um prazo, use Cobrança falhou ou Cancelou.');
        end if;
        if p_ate < current_date then
            return jsonb_build_object('ok', false, 'erro', 'data', 'mensagem', 'A data não pode ficar no passado.');
        end if;
    end if;

    if v_modulos is not null then
        perform public.dumtech_trocar_modulos(p_licenca, v_modulos);
        update public.licencas set plano_id = v_plano.id where id = p_licenca;
        if v_antes is distinct from public.dumtech_modulos_da_licenca(p_licenca)
           or v_licenca.plano_id is distinct from v_plano.id then
            v_mudou := v_mudou || jsonb_build_object(
                'modulos', jsonb_build_object('de', to_jsonb(v_antes), 'para', to_jsonb(public.dumtech_modulos_da_licenca(p_licenca))),
                'plano', v_plano.nome);
        end if;
    end if;
    if p_valor is not null and v_licenca.valor_mensal is distinct from p_valor then
        update public.licencas set valor_mensal = p_valor where id = p_licenca;
        v_mudou := v_mudou || jsonb_build_object('valor', jsonb_build_object('de', v_licenca.valor_mensal, 'para', p_valor));
    end if;
    if p_computadores is not null and v_licenca.max_computadores <> p_computadores then
        update public.licencas set max_computadores = p_computadores where id = p_licenca;
        v_mudou := v_mudou || jsonb_build_object('computadores',
            jsonb_build_object('de', v_licenca.max_computadores, 'para', p_computadores));
    end if;
    if p_ate is not null and v_licenca.expira_em is distinct from p_ate then
        update public.licencas set expira_em = p_ate where id = p_licenca;
        v_mudou := v_mudou || jsonb_build_object('ate', jsonb_build_object('de', v_licenca.expira_em, 'para', p_ate));
    end if;
    if p_observacoes is not null and v_licenca.observacoes is distinct from left(p_observacoes, 2000) then
        update public.licencas set observacoes = left(p_observacoes, 2000) where id = p_licenca;
        v_mudou := v_mudou || jsonb_build_object('anotacoes', true);
    end if;

    if v_mudou <> '{}'::jsonb then
        perform public.dumtech_registrar_evento(p_licenca, 'ajustou', v_mudou);
    end if;
    select * into v_licenca from public.licencas where id = p_licenca;
    select * into v_cliente from public.clientes where id = v_licenca.cliente_id;
    return jsonb_build_object(
        'ok', true, 'mudou', v_mudou, 'nome', v_cliente.nome, 'email', v_cliente.email,
        'telefone', v_cliente.telefone, 'chave', v_licenca.chave, 'tipo', v_licenca.tipo,
        'plano', v_plano.nome, 'modulos', to_jsonb(public.dumtech_modulos_da_licenca(p_licenca)),
        'adicionais', to_jsonb(public.dumtech_adicionais_validos(public.dumtech_modulos_da_licenca(p_licenca))),
        'valor', v_licenca.valor_mensal, 'computadores', v_licenca.max_computadores, 'ate', v_licenca.expira_em);
end;
$$;

/** O teste vira assinatura sem pedido do site (fechou pelo WhatsApp). */
create or replace function public.dumtech_ativar_assinatura(
    p_licenca uuid,
    p_plano   uuid    default null,
    p_modulos text[]  default null,
    p_valor   numeric default null
)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
    v_licenca public.licencas;
    v_cliente public.clientes;
    v_plano   public.mensalidade_planos;
    v_modulos text[];
    v_valor   numeric;
begin
    perform public.dumtech_painel_portao();

    select * into v_licenca from public.licencas where id = p_licenca for update;
    if not found or v_licenca.tipo <> 'teste' then
        return jsonb_build_object('ok', false, 'erro', 'tipo',
            'mensagem', 'Só dá para ativar a assinatura de quem está no teste do plano mensal.');
    end if;

    if p_plano is not null then
        select * into v_plano from public.mensalidade_planos where id = p_plano;
        if not found then
            return jsonb_build_object('ok', false, 'erro', 'plano', 'mensagem', 'Plano não encontrado.');
        end if;
        v_modulos := v_plano.modulos;
        v_valor := coalesce(p_valor, case when public.dumtech_promo_vigente(v_plano.promo_preco, v_plano.promo_ate)
                                          then v_plano.promo_preco else v_plano.preco end);
    else
        v_modulos := public.dumtech_modulos_validos(coalesce(p_modulos, public.dumtech_plano_base()));
        if cardinality(v_modulos) = 0 then
            return jsonb_build_object('ok', false, 'erro', 'modulos', 'mensagem', 'Escolha ao menos um módulo.');
        end if;
        v_valor := coalesce(p_valor, public.dumtech_valor_dos_modulos(v_modulos));
    end if;
    if v_valor < 0 then
        return jsonb_build_object('ok', false, 'erro', 'valor', 'mensagem', 'O valor não pode ser negativo.');
    end if;

    update public.licencas
       set tipo = 'assinatura', expira_em = null, cobranca_motivo = null, cobranca_desde = null,
           assinatura_desde = current_date, plano_id = v_plano.id, valor_mensal = v_valor
     where id = p_licenca;
    perform public.dumtech_trocar_modulos(p_licenca, v_modulos);
    update public.assinatura_pedidos set situacao = 'descartado', resolvido_em = now()
     where licenca_id = p_licenca and situacao = 'aguardando';
    perform public.dumtech_registrar_evento(p_licenca, 'ativou', jsonb_build_object(
        'plano', v_plano.nome, 'modulos', v_modulos, 'valor', v_valor));

    select * into v_cliente from public.clientes where id = v_licenca.cliente_id;
    return jsonb_build_object(
        'ok', true, 'nome', v_cliente.nome, 'email', v_cliente.email, 'telefone', v_cliente.telefone,
        'chave', v_licenca.chave, 'plano', v_plano.nome, 'modulos', to_jsonb(v_modulos),
        'adicionais', to_jsonb(public.dumtech_adicionais_validos(v_modulos)), 'valor', v_valor, 'mudanca', false);
end;
$$;

/** Assinatura cancelada volta a valer (o cliente desistiu de sair). */
create or replace function public.dumtech_reabrir_assinatura(p_licenca uuid)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
    v_licenca public.licencas;
    v_cliente public.clientes;
begin
    perform public.dumtech_painel_portao();
    select * into v_licenca from public.licencas where id = p_licenca for update;
    if not found or v_licenca.tipo <> 'assinatura' or v_licenca.cobranca_motivo is distinct from 'cancelou' then
        return jsonb_build_object('ok', false, 'erro', 'tipo',
                                  'mensagem', 'Só dá para reabrir uma assinatura cancelada.');
    end if;
    update public.licencas set expira_em = null, cobranca_motivo = null, cobranca_desde = null where id = p_licenca;
    perform public.dumtech_registrar_evento(p_licenca, 'reabriu');
    select * into v_cliente from public.clientes where id = v_licenca.cliente_id;
    return jsonb_build_object('ok', true, 'nome', v_cliente.nome, 'email', v_cliente.email,
                              'telefone', v_cliente.telefone, 'chave', v_licenca.chave,
                              'valor', v_licenca.valor_mensal);
end;
$$;

-- ================================================ 13. VISOES DO PAINEL ===
create or replace view public.painel_mensalidades with (security_invoker = true) as
select l.id                 as licenca_id,
       l.chave,
       l.tipo,
       l.status,
       l.cliente_id,
       c.nome,
       c.email,
       c.telefone,
       public.dumtech_situacao_cobranca(l.tipo, l.expira_em) as situacao,
       l.expira_em,
       l.cobranca_motivo,
       l.cobranca_desde,
       l.assinatura_desde,
       l.criado_em,
       coalesce(itens.modulos, '{}'::text[]) as modulos,
       coalesce(itens.adicionais, '{}'::text[]) as adicionais,
       l.plano_id,
       p.nome as plano_nome,
       coalesce(l.valor_mensal, public.dumtech_valor_dos_modulos(itens.modulos)) as valor,
       l.valor_mensal,
       l.max_computadores,
       (select count(*) from public.ativacoes a where a.licenca_id = l.id)::integer as computadores,
       l.observacoes
  from public.licencas l
  join public.clientes c on c.id = l.cliente_id
  left join public.mensalidade_planos p on p.id = l.plano_id
  left join lateral (
        select array_agg(pr.codigo order by pr.codigo) as modulos,
               array_agg(pr.codigo order by pr.codigo)
                 filter (where pr.codigo = any(public.dumtech_plano_adicionais())) as adicionais
          from public.licenca_produtos lp
          join public.produtos pr on pr.id = lp.produto_id
         where lp.licenca_id = l.id
  ) itens on true
 where l.tipo in ('assinatura', 'teste');

drop view if exists public.painel_assinatura_pedidos;
create view public.painel_assinatura_pedidos with (security_invoker = true) as
select ap.id,
       ap.licenca_id,
       ap.adicionais,
       ap.modulos,
       ap.plano_id,
       pl.nome as plano_nome,
       ap.cupom,
       ap.valor,
       ap.link,
       ap.situacao,
       ap.criado_em,
       ap.resolvido_em,
       l.chave,
       l.tipo,
       public.dumtech_situacao_cobranca(l.tipo, l.expira_em) as situacao_licenca,
       l.expira_em,
       c.id   as cliente_id,
       c.nome,
       c.email,
       c.telefone
  from public.assinatura_pedidos ap
  join public.licencas l on l.id = ap.licenca_id
  join public.clientes c on c.id = l.cliente_id
  left join public.mensalidade_planos pl on pl.id = ap.plano_id;

-- o historico, do mais recente para o mais antigo, com o nome de quem fez
create or replace view public.painel_assinatura_eventos with (security_invoker = true) as
select e.id, e.licenca_id, e.tipo, e.detalhe, e.admin_id, e.criado_em,
       coalesce(nullif(a.nome, ''), case when e.admin_id is null then 'Site' else 'DumTech' end) as quem
  from public.assinatura_eventos e
  left join public.administradores a on a.user_id = e.admin_id
 order by e.id desc;

create or replace view public.painel_cupons with (security_invoker = true) as
select cu.*,
       p.nome as plano_nome,
       p.preco as plano_preco,
       p.visivel as plano_visivel,
       (select count(*) from public.assinatura_pedidos ap
         where ap.cupom = cu.codigo and ap.situacao <> 'descartado')::integer as pedidos,
       (select count(*) from public.assinatura_pedidos ap
         where ap.cupom = cu.codigo and ap.situacao = 'confirmado')::integer as assinaturas
  from public.mensalidade_cupons cu
  join public.mensalidade_planos p on p.id = cu.plano_id;

-- o "monte o seu": as combinacoes com link e as que alguem pediu
create or replace view public.painel_combinacoes with (security_invoker = true) as
with pedidas as (
    select public.dumtech_chave_combinacao(ap.adicionais) as chave,
           count(*)::integer as pedidos, max(ap.criado_em) as ultimo
      from public.assinatura_pedidos ap
     where ap.plano_id is null
     group by 1
)
select coalesce(k.chave, pd.chave) as chave,
       coalesce(k.link, '') as link,
       coalesce(pd.pedidos, 0) as pedidos,
       pd.ultimo
  from public.mensalidade_combinacoes k
  full join pedidas pd on pd.chave = k.chave;

-- ====================================================== 14. PERMISSOES ===
alter table public.mensalidade_modulos     enable row level security;
alter table public.mensalidade_planos      enable row level security;
alter table public.mensalidade_combinacoes enable row level security;
alter table public.mensalidade_cupons      enable row level security;
alter table public.assinatura_eventos      enable row level security;
alter table public.landing_conteudo        enable row level security;
alter table public.landing_publicacoes     enable row level security;
alter table public.landing_avisos          enable row level security;

revoke all on public.mensalidade_modulos, public.mensalidade_planos, public.mensalidade_combinacoes,
              public.mensalidade_cupons, public.assinatura_eventos, public.landing_conteudo,
              public.landing_publicacoes, public.landing_avisos
    from public, anon, authenticated;

-- o painel escreve direto nestas (as policies so deixam o admin com 2 fatores)
grant select, insert, update, delete on public.mensalidade_planos, public.mensalidade_combinacoes,
                                        public.mensalidade_cupons, public.landing_avisos
    to authenticated;
grant select, update on public.mensalidade_modulos to authenticated;
grant select on public.assinatura_eventos, public.landing_publicacoes to authenticated;
grant select, update on public.landing_conteudo to authenticated;

do $$
declare
    v_tabela text;
begin
    foreach v_tabela in array array['mensalidade_modulos', 'mensalidade_planos', 'mensalidade_combinacoes',
                                    'mensalidade_cupons', 'landing_avisos'] loop
        execute format('drop policy if exists admin_tudo on public.%I', v_tabela);
        execute format('create policy admin_tudo on public.%I for all to authenticated '
                       'using (public.dumtech_e_admin()) with check (public.dumtech_e_admin())', v_tabela);
    end loop;
    foreach v_tabela in array array['assinatura_eventos', 'landing_publicacoes'] loop
        execute format('drop policy if exists admin_le on public.%I', v_tabela);
        execute format('create policy admin_le on public.%I for select to authenticated '
                       'using (public.dumtech_e_admin())', v_tabela);
    end loop;
end;
$$;
-- o publicado so muda por dumtech_publicar_landing / dumtech_voltar_landing
drop policy if exists admin_le on public.landing_conteudo;
create policy admin_le on public.landing_conteudo for select to authenticated
    using (public.dumtech_e_admin());
drop policy if exists admin_rascunho on public.landing_conteudo;
create policy admin_rascunho on public.landing_conteudo for update to authenticated
    using (public.dumtech_e_admin() and id = 'rascunho')
    with check (public.dumtech_e_admin() and id = 'rascunho');

revoke all on public.painel_mensalidades, public.painel_assinatura_pedidos, public.painel_assinatura_eventos,
              public.painel_cupons, public.painel_combinacoes
    from public, anon;
grant select on public.painel_mensalidades, public.painel_assinatura_pedidos, public.painel_assinatura_eventos,
                public.painel_cupons, public.painel_combinacoes
    to authenticated;

-- pecas: o painel (visoes, gatilhos) usa; o site nao
revoke execute on function public.dumtech_link_valido(text)                from public, anon;
revoke execute on function public.dumtech_chave_combinacao(text[])         from public, anon;
revoke execute on function public.dumtech_promo_vigente(numeric, date)     from public, anon;
revoke execute on function public.dumtech_plano_base()                     from public, anon;
revoke execute on function public.dumtech_plano_adicionais()               from public, anon;
revoke execute on function public.dumtech_adicionais_validos(text[])       from public, anon;
revoke execute on function public.dumtech_modulos_validos(text[])          from public, anon;
revoke execute on function public.dumtech_valor_dos_modulos(text[])        from public, anon;
revoke execute on function public.dumtech_plano_json(public.mensalidade_planos) from public, anon;
revoke execute on function public.dumtech_normalizar_plano()               from public, anon;
revoke execute on function public.dumtech_normalizar_combinacao()          from public, anon;
revoke execute on function public.dumtech_normalizar_cupom()               from public, anon;
revoke execute on function public.dumtech_tocar_conteudo()                 from public, anon;
grant  execute on function public.dumtech_link_valido(text)                to authenticated, service_role;
grant  execute on function public.dumtech_chave_combinacao(text[])         to authenticated, service_role;
grant  execute on function public.dumtech_promo_vigente(numeric, date)     to authenticated, service_role;
grant  execute on function public.dumtech_plano_base()                     to authenticated, service_role;
grant  execute on function public.dumtech_plano_adicionais()               to authenticated, service_role;
grant  execute on function public.dumtech_adicionais_validos(text[])       to authenticated, service_role;
grant  execute on function public.dumtech_modulos_validos(text[])          to authenticated, service_role;
grant  execute on function public.dumtech_valor_dos_modulos(text[])        to authenticated, service_role;
grant  execute on function public.dumtech_plano_json(public.mensalidade_planos) to authenticated, service_role;
grant  execute on function public.dumtech_normalizar_plano()               to authenticated, service_role;
grant  execute on function public.dumtech_normalizar_combinacao()          to authenticated, service_role;
grant  execute on function public.dumtech_normalizar_cupom()               to authenticated, service_role;
grant  execute on function public.dumtech_tocar_conteudo()                 to authenticated, service_role;

-- por dentro: so as funcoes daqui chamam (como dono)
revoke execute on function public.dumtech_registrar_evento(uuid, text, jsonb) from public, anon, authenticated;
revoke execute on function public.dumtech_cupom_vigente(text)                 from public, anon, authenticated;
revoke execute on function public.dumtech_modulos_da_licenca(uuid)            from public, anon;
revoke execute on function public.dumtech_trocar_modulos(uuid, text[])        from public, anon, authenticated;
grant  execute on function public.dumtech_modulos_da_licenca(uuid)            to authenticated;

-- o site
revoke execute on function public.dumtech_mensalidade_publica() from public;
grant  execute on function public.dumtech_mensalidade_publica() to anon, authenticated;
revoke execute on function public.dumtech_cupom_publico(text)   from public;
grant  execute on function public.dumtech_cupom_publico(text)   to anon, authenticated;

-- a Edge Function do cadastro
revoke execute on function public.dumtech_cadastrar_mensal(text, text, text, text[], boolean, text, uuid, text)
    from public, anon, authenticated;
grant  execute on function public.dumtech_cadastrar_mensal(text, text, text, text[], boolean, text, uuid, text)
    to service_role;

-- o painel (cada uma abre com o portao do admin com 2 fatores)
revoke execute on function public.dumtech_ajustar_assinatura(uuid, uuid, text[], numeric, integer, date, text) from public, anon;
revoke execute on function public.dumtech_ativar_assinatura(uuid, uuid, text[], numeric)  from public, anon;
revoke execute on function public.dumtech_reabrir_assinatura(uuid)                        from public, anon;
revoke execute on function public.dumtech_publicar_landing()                              from public, anon;
revoke execute on function public.dumtech_voltar_landing(uuid)                            from public, anon;
grant  execute on function public.dumtech_ajustar_assinatura(uuid, uuid, text[], numeric, integer, date, text) to authenticated;
grant  execute on function public.dumtech_ativar_assinatura(uuid, uuid, text[], numeric)  to authenticated;
grant  execute on function public.dumtech_reabrir_assinatura(uuid)                        to authenticated;
grant  execute on function public.dumtech_publicar_landing()                              to authenticated;
grant  execute on function public.dumtech_voltar_landing(uuid)                            to authenticated;
