-- =============================================================================
-- Agendamento online: o cliente da loja marca sozinho, por um link.
--
-- COMO FUNCIONA
--   1. Na Agenda do Hub, o dono liga o link e diz servicos, horario de
--      atendimento e regras. O Hub guarda isso aqui (`agenda_links.config`).
--   2. Sempre que a agenda muda, o Hub publica os HORARIOS OCUPADOS: inicio,
--      minutos e se e bloqueio. Sem titulo, sem cliente, sem nada de ninguem.
--   3. A pagina /agendar/<slug> pede os horarios livres - calculados AQUI, por
--      uma funcao so (`dumtech_agenda_livres`), a mesma que confere a reserva.
--   4. A reserva entra numa fila (`agenda_reservas`). O Hub busca a fila, grava
--      na agenda dele e confirma o recebimento junto com os ocupados novos; so
--      entao nome, telefone e observacao sao APAGADOS daqui.
--   5. O cliente cancela com o codigo que so o celular dele tem (guardado aqui
--      so o hash), dentro do prazo que o dono escolheu.
--
-- O QUE PROTEGE O BANCO
--   * nenhuma tabela existente muda; as duas novas ficam com RLS e sem policy;
--   * so as funcoes abaixo tocam nelas, com limite por IP, por link e por
--     telefone, e com tamanho maximo em tudo que chega de fora;
--   * a fila se limpa sozinha: entregue perde os dados pessoais, e o que ja
--     passou ha mais de 2 dias e apagado (faxina barata dentro das funcoes).
--
-- O RELOGIO DA LOJA
--   Horarios sao hora de parede da loja (`timestamp` sem fuso), como a Agenda
--   grava. "Agora na loja" = UTC + `fuso_min`, que o Hub manda a cada
--   publicacao (o Brasil nao tem horario de verao desde 2019).
--
-- Depende de: 20260923120000_celular.sql (dumtech_celular_licenca) e
--             20260912180000_tempo_real_e_blindagem.sql (limites).
-- =============================================================================

create table if not exists public.agenda_links (
    id            uuid primary key default gen_random_uuid(),
    licenca_id    uuid not null references public.licencas(id) on delete cascade,
    maquina       text not null,
    slug          text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$'),
    ativo         boolean not null default true,
    config        jsonb not null,
    ocupados      jsonb not null default '[]'::jsonb,
    fuso_min      smallint not null default -180 check (fuso_min between -720 and 840),
    publicado_em  timestamptz,
    criado_em     timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    unique (licenca_id, maquina)
);

comment on table public.agenda_links is
    'O link de agendamento de um computador (licenca + maquina): regras da pagina '
    'e os horarios ocupados que o Hub publica (sem nome de ninguem).';

create table if not exists public.agenda_reservas (
    id            uuid primary key default gen_random_uuid(),
    link_id       uuid not null references public.agenda_links(id) on delete cascade,
    servico       text not null,
    inicio        timestamp not null,
    duracao       smallint not null check (duracao between 5 and 720),
    nome          text not null default '',
    telefone      text not null default '',
    observacao    text not null default '',
    -- so para o limite de horarios por telefone; o numero em si some na entrega
    telefone_hash text not null default '',
    codigo_hash   text not null unique,
    situacao      text not null default 'nova'
                  check (situacao in ('nova', 'entregue', 'cancelada')),
    criado_em     timestamptz not null default now(),
    entregue_em   timestamptz,
    cancelada_em  timestamptz
);

comment on table public.agenda_reservas is
    'Fila do agendamento online. nova -> entregue (dados pessoais apagados) -> '
    'cancelada. Apagada 2 dias depois do horario.';

create index if not exists idx_agenda_reservas_link   on public.agenda_reservas (link_id, situacao);
create index if not exists idx_agenda_reservas_inicio on public.agenda_reservas (link_id, inicio);

alter table public.agenda_links    enable row level security;
alter table public.agenda_reservas enable row level security;
revoke all on table public.agenda_links    from anon, authenticated;
revoke all on table public.agenda_reservas from anon, authenticated;

-- ================================================================ apoio ===
create or replace function public.dumtech_agenda_hash(p_segredo text)
returns text
language sql
immutable
set search_path = ''
as $$
    select encode(sha256(convert_to('dumtech-agenda:' || coalesce(p_segredo, ''), 'UTF8')), 'hex');
$$;

/** A hora de parede da loja agora. */
create or replace function public.dumtech_agenda_agora(p_fuso integer)
returns timestamp
language sql
stable
set search_path = ''
as $$
    select (now() at time zone 'UTC') + make_interval(mins => coalesce(p_fuso, -180));
$$;

/** A licenca pode ter link: ativa e com a Agenda comprada ou em teste. */
create or replace function public.dumtech_agenda_liberada(p_licenca uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1 from public.licencas l
         where l.id = p_licenca
           and public.dumtech_situacao_licenca(l.status, l.expira_em) = 'ativa'
           and (exists (select 1 from public.licenca_produtos lp
                          join public.produtos p on p.id = lp.produto_id
                         where lp.licenca_id = l.id and p.codigo = 'AGENDA')
                or exists (select 1 from public.licenca_testes t
                             join public.produtos p on p.id = t.produto_id
                            where t.licenca_id = l.id and p.codigo = 'AGENDA'
                              and t.termina_em > now())));
$$;

/** '' = a configuracao serve; senao, o que esta errado. */
create or replace function public.dumtech_agenda_config_valida(p jsonb)
returns text
language plpgsql
immutable
set search_path = ''
as $$
declare
    v_item jsonb;
    v_dia  jsonb;
begin
    if jsonb_typeof(p) is distinct from 'object' or octet_length(p::text) > 65536 then
        return 'configuração grande demais';
    end if;
    if jsonb_typeof(p->'empresa') is distinct from 'object'
       or length(btrim(coalesce(p#>>'{empresa,nome}', ''))) not between 1 and 80
       or length(coalesce(p#>>'{empresa,endereco}', '')) > 160
       or coalesce(p#>>'{empresa,whatsapp}', '') !~ '^[0-9]{0,15}$'
       or length(coalesce(p->>'mensagem', '')) > 280 then
        return 'dados da empresa';
    end if;
    if coalesce(p#>>'{empresa,logo}', '') <> ''
       and (length(p#>>'{empresa,logo}') > 48000
            or (p#>>'{empresa,logo}') !~ '^data:image/(png|jpeg);base64,[A-Za-z0-9+/]+=*$') then
        return 'logotipo';
    end if;
    if coalesce(p->>'cor', '') not in ('violeta', 'rosa', 'vinho', 'terracota', 'verde',
                                        'petroleo', 'azul', 'grafite') then
        return 'cor';
    end if;
    if coalesce((p->>'passo')::int, -1) not in (10, 15, 20, 30, 45, 60)
       or coalesce((p->>'vagas')::int, -1) not between 1 and 10
       or coalesce((p->>'antecedencia')::int, -1) not between 0 and 10080
       or coalesce((p->>'dias')::int, -1) not between 1 and 90
       or coalesce((p->>'cancelar_ate')::int, -1) not between 0 and 10080 then
        return 'regras';
    end if;
    if jsonb_typeof(p->'servicos') is distinct from 'array'
       or jsonb_array_length(p->'servicos') not between 1 and 20
       or (select count(distinct s->>'id') from jsonb_array_elements(p->'servicos') s)
          <> jsonb_array_length(p->'servicos') then
        return 'serviços';
    end if;
    for v_item in select * from jsonb_array_elements(p->'servicos') loop
        if coalesce(v_item->>'id', '') !~ '^[A-Za-z0-9_-]{1,20}$'
           or length(btrim(coalesce(v_item->>'nome', ''))) not between 1 and 80
           or coalesce((v_item->>'duracao')::int, -1) not between 5 and 720
           or coalesce(jsonb_typeof(v_item->'preco'), 'null') not in ('number', 'null') then
            return 'serviços';
        end if;
    end loop;
    if jsonb_typeof(p->'semana') is distinct from 'array' or jsonb_array_length(p->'semana') <> 7 then
        return 'horário de atendimento';
    end if;
    for v_dia in select * from jsonb_array_elements(p->'semana') loop
        if jsonb_typeof(v_dia) <> 'array' or jsonb_array_length(v_dia) > 4 then
            return 'horário de atendimento';
        end if;
        for v_item in select * from jsonb_array_elements(v_dia) loop
            if jsonb_typeof(v_item) <> 'array' or jsonb_array_length(v_item) <> 2
               or coalesce((v_item->>0)::int, -1) < 0
               or coalesce((v_item->>1)::int, 9999) > 1440
               or (v_item->>0)::int >= (v_item->>1)::int then
                return 'horário de atendimento';
            end if;
        end loop;
    end loop;
    return '';
exception when others then
    return 'configuração inválida';
end;
$$;

/** Os ocupados que o Hub manda: [["2026-10-28T14:00", 45, 0], ...]. */
create or replace function public.dumtech_agenda_ocupados_validos(p jsonb)
returns boolean
language plpgsql
immutable
set search_path = ''
as $$
begin
    if jsonb_typeof(p) is distinct from 'array' or jsonb_array_length(p) > 5000
       or octet_length(p::text) > 300000 then
        return false;
    end if;
    if exists (select 1 from jsonb_array_elements(p) o
                where jsonb_typeof(o) <> 'array' or jsonb_array_length(o) <> 3
                   or coalesce(o->>0, '') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$'
                   or coalesce(o->>1, '') !~ '^[0-9]{1,5}$'
                   or coalesce(o->>2, '') not in ('0', '1')) then
        return false;
    end if;
    -- data que nao existe (31/02) para aqui
    perform (o->>0)::timestamp from jsonb_array_elements(p) o;
    return not exists (select 1 from jsonb_array_elements(p) o
                        where (o->>1)::int not between 1 and 10080);
exception when others then
    return false;
end;
$$;

/**
 * Os inicios livres para um servico de `p_duracao` minutos, de `p_de` a `p_ate`.
 *
 * Livre e: cabe inteiro num intervalo aberto do dia, no passo da grade a
 * partir do comeco do intervalo; comeca depois de agora + antecedencia; esta
 * dentro da janela de dias; nao encosta em bloqueio; e o MAXIMO de atendimentos
 * simultaneos dentro dele (ocupados publicados + reservas ainda nao entregues)
 * fica abaixo das vagas. Simultaneo de verdade: com 2 vagas, 14:00-14:30 e
 * 14:30-15:00 ocupados ainda deixam livre 14:00-15:00.
 */
create or replace function public.dumtech_agenda_livres(
    p_link uuid, p_duracao integer, p_de date, p_ate date
)
returns setof timestamp
language sql
stable
security definer
set search_path = ''
as $$
    with regras as (
        select l.id, l.config, l.ocupados,
               public.dumtech_agenda_agora(l.fuso_min) as agora
          from public.agenda_links l
         where l.id = p_link
    ),
    janela as (
        select id, config, ocupados, agora,
               agora + make_interval(mins => (config->>'antecedencia')::int) as cedo,
               greatest(p_de, agora::date) as de,
               least(p_ate, agora::date + (config->>'dias')::int - 1) as ate
          from regras
    ),
    faixas as (
        select d::date as dia, j.cedo, (j.config->>'passo')::int as passo,
               (f->>0)::int as ini, (f->>1)::int as fim
          from janela j,
               generate_series(j.de, j.ate, interval '1 day') d,
               jsonb_array_elements(j.config->'semana'->(extract(isodow from d)::int - 1)) f
    ),
    candidatos as (
        select distinct f.dia + make_interval(mins => m) as s,
                        f.dia + make_interval(mins => m + p_duracao) as e,
                        f.cedo
          from faixas f, generate_series(f.ini, f.fim - p_duracao, f.passo) m
    ),
    ocupados as (
        select (o->>0)::timestamp as ini,
               (o->>0)::timestamp + make_interval(mins => (o->>1)::int) as fim,
               (o->>2) = '1' as bloqueio
          from janela j, jsonb_array_elements(j.ocupados) o
        union all
        select r.inicio, r.inicio + make_interval(mins => r.duracao::int), false
          from janela j
          join public.agenda_reservas r on r.link_id = j.id and r.situacao = 'nova'
    ),
    pertinentes as (
        select o.* from ocupados o, janela j
         where o.fim > j.de and o.ini < j.ate + 1
    )
    select c.s
      from candidatos c, janela j
     where c.s >= c.cedo
       and not exists (select 1 from pertinentes o
                        where o.bloqueio and o.ini < c.e and c.s < o.fim)
       and (select coalesce(max(n), 0) from (
                select count(*) as n
                  from (select c.s as t
                        union
                        select o.ini from pertinentes o
                         where not o.bloqueio and o.ini > c.s and o.ini < c.e) pontos
                  join pertinentes o on not o.bloqueio and o.ini <= pontos.t and pontos.t < o.fim
                 group by pontos.t) simultaneos) < (j.config->>'vagas')::int
     order by c.s;
$$;

/** Empresa e WhatsApp: o que a pagina mostra mesmo com o link pausado. */
create or replace function public.dumtech_agenda_contato(p_config jsonb)
returns jsonb
language sql
immutable
set search_path = ''
as $$
    select jsonb_build_object('nome', coalesce(p_config#>>'{empresa,nome}', ''),
                              'whatsapp', coalesce(p_config#>>'{empresa,whatsapp}', ''));
$$;

create or replace function public.dumtech_agenda_faxina()
returns void
language sql
volatile
security definer
set search_path = ''
as $$
    -- inicio e hora da loja; UTC - 2 dias e seguro para qualquer fuso do Brasil
    delete from public.agenda_reservas
     where inicio < (now() at time zone 'UTC') - interval '2 days';
$$;

-- =============================================================== a pagina ===
/** O que a pagina mostra ao abrir: a empresa, os servicos e as regras. */
create or replace function public.dumtech_agenda_pagina(p_slug text)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
    v       public.agenda_links;
    v_agora timestamp;
begin
    if not public.dumtech_dentro_do_limite('agenda_ver_ip', public.dumtech_ip_do_pedido(), 600, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos.');
    end if;
    select * into v from public.agenda_links where slug = lower(btrim(coalesce(p_slug, '')));
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'nao_encontrado',
                                  'mensagem', 'Este link de agendamento não existe. Confira o endereço com a empresa.');
    end if;
    if not v.ativo or not public.dumtech_agenda_liberada(v.licenca_id) then
        return jsonb_build_object('ok', false, 'erro', 'indisponivel',
                                  'mensagem', 'A agenda online desta empresa está pausada no momento.',
                                  'empresa', public.dumtech_agenda_contato(v.config));
    end if;
    v_agora := public.dumtech_agenda_agora(v.fuso_min);
    return jsonb_build_object(
        'ok', true,
        'empresa', v.config->'empresa',
        'mensagem', coalesce(v.config->>'mensagem', ''),
        'cor', v.config->>'cor',
        'servicos', v.config->'servicos',
        'dias', (v.config->>'dias')::int,
        'cancelar_ate', (v.config->>'cancelar_ate')::int,
        'hoje', to_char(v_agora, 'YYYY-MM-DD'),
        'agora', to_char(v_agora, 'YYYY-MM-DD"T"HH24:MI'));
end;
$$;

/** Os dias da janela, cada um com os horarios livres para o servico. */
create or replace function public.dumtech_agenda_horarios(p_slug text, p_servico text)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
    v        public.agenda_links;
    v_serv   jsonb;
    v_agora  timestamp;
    v_ultimo date;
begin
    if not public.dumtech_dentro_do_limite('agenda_ver_ip', public.dumtech_ip_do_pedido(), 600, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos.');
    end if;
    select * into v from public.agenda_links where slug = lower(btrim(coalesce(p_slug, '')));
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'nao_encontrado',
                                  'mensagem', 'Este link de agendamento não existe.');
    end if;
    if not v.ativo or not public.dumtech_agenda_liberada(v.licenca_id) then
        return jsonb_build_object('ok', false, 'erro', 'indisponivel',
                                  'mensagem', 'A agenda online desta empresa está pausada no momento.',
                                  'empresa', public.dumtech_agenda_contato(v.config));
    end if;
    select s into v_serv from jsonb_array_elements(v.config->'servicos') s
     where s->>'id' = coalesce(p_servico, '') limit 1;
    if v_serv is null then
        return jsonb_build_object('ok', false, 'erro', 'servico', 'mensagem', 'Escolha um serviço da lista.');
    end if;

    v_agora := public.dumtech_agenda_agora(v.fuso_min);
    v_ultimo := v_agora::date + (v.config->>'dias')::int - 1;
    return jsonb_build_object('ok', true, 'servico', v_serv, 'dias', (
        with livres as (
            select s from public.dumtech_agenda_livres(v.id, (v_serv->>'duracao')::int,
                                                       v_agora::date, v_ultimo) s
        )
        select jsonb_agg(jsonb_build_object(
                   'data', to_char(d, 'YYYY-MM-DD'),
                   'horarios', coalesce((select jsonb_agg(to_char(l.s, 'HH24:MI') order by l.s)
                                           from livres l where l.s::date = d::date), '[]'::jsonb))
               order by d)
          from generate_series(v_agora::date, v_ultimo, interval '1 day') d));
end;
$$;

/** Marca o horario. Confere tudo de novo, com o link travado. */
create or replace function public.dumtech_agenda_reservar(
    p_slug       text,
    p_servico    text,
    p_inicio     text,
    p_nome       text,
    p_telefone   text,
    p_observacao text default '',
    p_armadilha  text default ''
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
    v        public.agenda_links;
    v_serv   jsonb;
    v_inicio timestamp;
    v_dur    integer;
    v_nome   text := left(btrim(regexp_replace(coalesce(p_nome, ''), '\s+', ' ', 'g')), 80);
    v_tel    text := regexp_replace(coalesce(p_telefone, ''), '[^0-9]', '', 'g');
    v_obs    text := left(btrim(coalesce(p_observacao, '')), 300);
    v_codigo text := replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', '');
    v_id     uuid;
    v_agora  timestamp;
begin
    if not public.dumtech_dentro_do_limite('agenda_reservar_ip', public.dumtech_ip_do_pedido(), 30, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos.');
    end if;
    -- o campo escondido do formulario: gente nao ve, robo preenche
    if coalesce(p_armadilha, '') <> '' then
        return jsonb_build_object('ok', false, 'erro', 'dados', 'mensagem', 'Não foi possível marcar.');
    end if;
    if length(v_tel) in (12, 13) and left(v_tel, 2) = '55' then
        v_tel := substr(v_tel, 3);
    end if;
    if length(v_nome) < 2 then
        return jsonb_build_object('ok', false, 'erro', 'dados', 'mensagem', 'Digite o seu nome.');
    end if;
    if length(v_tel) not in (10, 11) or substr(v_tel, 1, 1) = '0' or substr(v_tel, 2, 1) = '0' then
        return jsonb_build_object('ok', false, 'erro', 'dados', 'mensagem', 'Digite o seu WhatsApp com DDD.');
    end if;
    if coalesce(p_inicio, '') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$' then
        return jsonb_build_object('ok', false, 'erro', 'dados', 'mensagem', 'Escolha um horário.');
    end if;
    begin
        v_inicio := p_inicio::timestamp;
    exception when others then
        return jsonb_build_object('ok', false, 'erro', 'dados', 'mensagem', 'Escolha um horário.');
    end;

    -- a trava: duas reservas no mesmo link passam uma de cada vez
    select * into v from public.agenda_links
     where slug = lower(btrim(coalesce(p_slug, ''))) for update;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'nao_encontrado',
                                  'mensagem', 'Este link de agendamento não existe.');
    end if;
    if not v.ativo or not public.dumtech_agenda_liberada(v.licenca_id) then
        return jsonb_build_object('ok', false, 'erro', 'indisponivel',
                                  'mensagem', 'A agenda online desta empresa está pausada no momento.',
                                  'empresa', public.dumtech_agenda_contato(v.config));
    end if;
    if not public.dumtech_dentro_do_limite('agenda_reservar_link', v.id::text, 100, interval '1 day') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Este link recebeu agendamentos demais hoje. Fale com a empresa.');
    end if;
    select s into v_serv from jsonb_array_elements(v.config->'servicos') s
     where s->>'id' = coalesce(p_servico, '') limit 1;
    if v_serv is null then
        return jsonb_build_object('ok', false, 'erro', 'servico', 'mensagem', 'Escolha um serviço da lista.');
    end if;
    v_dur := (v_serv->>'duracao')::int;
    v_agora := public.dumtech_agenda_agora(v.fuso_min);

    if (select count(*) from public.agenda_reservas r
         where r.link_id = v.id and r.telefone_hash = public.dumtech_agenda_hash(v_tel)
           and r.situacao in ('nova', 'entregue') and r.inicio >= v_agora) >= 3 then
        return jsonb_build_object('ok', false, 'erro', 'limite_telefone',
                                  'mensagem', 'Você já tem 3 horários marcados aqui. Para marcar mais, fale com a empresa.');
    end if;
    if not exists (select 1 from public.dumtech_agenda_livres(v.id, v_dur, v_inicio::date, v_inicio::date) s
                    where s = v_inicio) then
        return jsonb_build_object('ok', false, 'erro', 'ocupado',
                                  'mensagem', 'Esse horário acabou de ser ocupado. Escolha outro.');
    end if;

    insert into public.agenda_reservas
        (link_id, servico, inicio, duracao, nome, telefone, observacao, telefone_hash, codigo_hash)
    values (v.id, v_serv->>'nome', v_inicio, v_dur, v_nome, v_tel, v_obs,
            public.dumtech_agenda_hash(v_tel), public.dumtech_agenda_hash(v_codigo))
    returning id into v_id;

    if random() < 0.05 then
        perform public.dumtech_agenda_faxina();
    end if;

    return jsonb_build_object(
        'ok', true,
        'id', v_id,
        'codigo', v_codigo,
        'servico', v_serv->>'nome',
        'inicio', to_char(v_inicio, 'YYYY-MM-DD"T"HH24:MI'),
        'fim', to_char(v_inicio + make_interval(mins => v_dur), 'YYYY-MM-DD"T"HH24:MI'),
        'cancelar_ate', to_char(v_inicio - make_interval(mins => (v.config->>'cancelar_ate')::int),
                                'YYYY-MM-DD"T"HH24:MI'),
        'empresa', jsonb_build_object('nome', v.config#>>'{empresa,nome}',
                                      'endereco', coalesce(v.config#>>'{empresa,endereco}', ''),
                                      'whatsapp', coalesce(v.config#>>'{empresa,whatsapp}', '')));
end;
$$;

/** O cliente desiste: com o codigo que so o celular dele tem, dentro do prazo. */
create or replace function public.dumtech_agenda_cancelar(p_codigo text)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
    r public.agenda_reservas;
    v public.agenda_links;
begin
    if not public.dumtech_dentro_do_limite('agenda_cancelar_ip', public.dumtech_ip_do_pedido(), 30, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos.');
    end if;
    select * into r from public.agenda_reservas
     where codigo_hash = public.dumtech_agenda_hash(btrim(coalesce(p_codigo, ''))) for update;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'nao_encontrado',
                                  'mensagem', 'Este agendamento não existe mais.');
    end if;
    if r.situacao = 'cancelada' then
        return jsonb_build_object('ok', true);
    end if;
    select * into v from public.agenda_links where id = r.link_id;
    if public.dumtech_agenda_agora(v.fuso_min)
       > r.inicio - make_interval(mins => (v.config->>'cancelar_ate')::int) then
        return jsonb_build_object('ok', false, 'erro', 'prazo',
                                  'mensagem', 'O prazo para cancelar pelo link já passou. Fale com a empresa.');
    end if;
    if r.situacao = 'nova' then
        delete from public.agenda_reservas where id = r.id;   -- o Hub nunca soube dela
    else
        update public.agenda_reservas set situacao = 'cancelada', cancelada_em = now() where id = r.id;
    end if;
    return jsonb_build_object('ok', true);
end;
$$;

-- ================================================================== o Hub ===
/** Cria ou atualiza o link deste computador. Devolve o slug. */
create or replace function public.dumtech_agenda_salvar(
    p_chave         text,
    p_maquina       text,
    p_computador    text,
    p_ativo         boolean,
    p_config        jsonb,
    p_sugestao      text default '',
    p_novo_endereco boolean default false
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
    v_licenca uuid := public.dumtech_celular_licenca(p_chave, p_maquina, p_computador);
    v_maquina text := public.dumtech_normalizar(p_maquina, 64);
    v         public.agenda_links;
    v_existe  boolean;
    v_erro    text;
    v_base    text;
    v_slug    text;
begin
    if v_licenca is null then
        return jsonb_build_object('ok', false, 'erro', 'licenca_invalida');
    end if;
    if not public.dumtech_agenda_liberada(v_licenca) then
        return jsonb_build_object('ok', false, 'erro', 'sem_agenda');
    end if;
    if not public.dumtech_dentro_do_limite('agenda_salvar', v_licenca::text, 60, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas');
    end if;
    v_erro := public.dumtech_agenda_config_valida(p_config);
    if v_erro <> '' then
        return jsonb_build_object('ok', false, 'erro', 'config_invalida', 'mensagem', v_erro);
    end if;

    select * into v from public.agenda_links
     where licenca_id = v_licenca and maquina = v_maquina for update;
    v_existe := found;

    if not v_existe or coalesce(p_novo_endereco, false) then
        v_base := btrim(regexp_replace(lower(coalesce(p_sugestao, '')), '[^a-z0-9]+', '-', 'g'), '-');
        v_base := btrim(left(v_base, 30), '-');
        if length(v_base) < 3 then
            v_base := 'agenda';
        end if;
        v_slug := v_base;
        if coalesce(p_novo_endereco, false)
           or exists (select 1 from public.agenda_links where slug = v_slug) then
            loop
                v_slug := v_base || '-' || substr(md5(random()::text || clock_timestamp()::text), 1, 4);
                exit when not exists (select 1 from public.agenda_links where slug = v_slug);
            end loop;
        end if;
    end if;

    if not v_existe then
        insert into public.agenda_links (licenca_id, maquina, slug, ativo, config)
        values (v_licenca, v_maquina, v_slug, coalesce(p_ativo, true), p_config)
        returning * into v;
    else
        update public.agenda_links
           set ativo = coalesce(p_ativo, ativo), config = p_config,
               slug = coalesce(v_slug, slug), atualizado_em = now()
         where id = v.id
        returning * into v;
    end if;
    return jsonb_build_object('ok', true, 'slug', v.slug, 'ativo', v.ativo);
end;
$$;

/**
 * A conversa periodica do Hub: publica os ocupados, confirma o que recebeu e
 * busca o que chegou. A confirmacao so vale JUNTO com ocupados novos - assim a
 * reserva nunca sai da conta de ocupados entre a fila e o retrato do Hub.
 */
create or replace function public.dumtech_agenda_sincronizar(
    p_chave      text,
    p_maquina    text,
    p_computador text,
    p_ocupados   jsonb   default null,
    p_fuso       integer default null,
    p_recebidas  uuid[]  default '{}',
    p_canceladas uuid[]  default '{}'
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
    v_licenca uuid := public.dumtech_celular_licenca(p_chave, p_maquina, p_computador);
    v         public.agenda_links;
begin
    if v_licenca is null then
        return jsonb_build_object('ok', false, 'erro', 'licenca_invalida');
    end if;
    if not public.dumtech_agenda_liberada(v_licenca) then
        return jsonb_build_object('ok', false, 'erro', 'sem_agenda');
    end if;
    select * into v from public.agenda_links
     where licenca_id = v_licenca and maquina = public.dumtech_normalizar(p_maquina, 64) for update;
    if not found then
        return jsonb_build_object('ok', true, 'link', false);
    end if;
    if not public.dumtech_dentro_do_limite('agenda_sincronizar', v.id::text, 240, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas');
    end if;

    if p_ocupados is not null then
        if not public.dumtech_agenda_ocupados_validos(p_ocupados) then
            return jsonb_build_object('ok', false, 'erro', 'ocupados_invalidos');
        end if;
        update public.agenda_links
           set ocupados = p_ocupados, publicado_em = now(),
               fuso_min = case when p_fuso between -720 and 840 then p_fuso else fuso_min end
         where id = v.id;
        update public.agenda_reservas
           set situacao = 'entregue', entregue_em = now(), nome = '', telefone = '', observacao = ''
         where link_id = v.id and situacao = 'nova' and id = any(coalesce(p_recebidas, '{}'));
    end if;
    delete from public.agenda_reservas
     where link_id = v.id and situacao = 'cancelada' and id = any(coalesce(p_canceladas, '{}'));

    if random() < 0.05 then
        perform public.dumtech_agenda_faxina();
    end if;

    return jsonb_build_object(
        'ok', true,
        'link', true,
        'slug', v.slug,
        'ativo', v.ativo,
        'novas', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', r.id, 'servico', r.servico,
                       'inicio', to_char(r.inicio, 'YYYY-MM-DD"T"HH24:MI'),
                       'duracao', r.duracao, 'nome', r.nome, 'telefone', r.telefone,
                       'observacao', r.observacao) order by r.criado_em)
              from public.agenda_reservas r
             where r.link_id = v.id and r.situacao = 'nova'), '[]'::jsonb),
        'canceladas', coalesce((
            select jsonb_agg(r.id order by r.cancelada_em)
              from public.agenda_reservas r
             where r.link_id = v.id and r.situacao = 'cancelada'), '[]'::jsonb));
end;
$$;

-- ================================================================ portas ===
revoke execute on function public.dumtech_agenda_hash(text)                           from public, anon, authenticated;
revoke execute on function public.dumtech_agenda_agora(integer)                       from public, anon, authenticated;
revoke execute on function public.dumtech_agenda_liberada(uuid)                       from public, anon, authenticated;
revoke execute on function public.dumtech_agenda_config_valida(jsonb)                 from public, anon, authenticated;
revoke execute on function public.dumtech_agenda_ocupados_validos(jsonb)              from public, anon, authenticated;
revoke execute on function public.dumtech_agenda_livres(uuid, integer, date, date)    from public, anon, authenticated;
revoke execute on function public.dumtech_agenda_contato(jsonb)                       from public, anon, authenticated;
revoke execute on function public.dumtech_agenda_faxina()                             from public, anon, authenticated;

revoke execute on function public.dumtech_agenda_pagina(text)                                     from public, authenticated;
revoke execute on function public.dumtech_agenda_horarios(text, text)                             from public, authenticated;
revoke execute on function public.dumtech_agenda_reservar(text, text, text, text, text, text, text) from public, authenticated;
revoke execute on function public.dumtech_agenda_cancelar(text)                                   from public, authenticated;
revoke execute on function public.dumtech_agenda_salvar(text, text, text, boolean, jsonb, text, boolean) from public, authenticated;
revoke execute on function public.dumtech_agenda_sincronizar(text, text, text, jsonb, integer, uuid[], uuid[]) from public, authenticated;
grant  execute on function public.dumtech_agenda_pagina(text)                                     to anon;
grant  execute on function public.dumtech_agenda_horarios(text, text)                             to anon;
grant  execute on function public.dumtech_agenda_reservar(text, text, text, text, text, text, text) to anon;
grant  execute on function public.dumtech_agenda_cancelar(text)                                   to anon;
grant  execute on function public.dumtech_agenda_salvar(text, text, text, boolean, jsonb, text, boolean) to anon;
grant  execute on function public.dumtech_agenda_sincronizar(text, text, text, jsonb, integer, uuid[], uuid[]) to anon;

notify pgrst, 'reload schema';
