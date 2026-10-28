-- =============================================================================
-- Cada servico no tempo dele: a barba de 15 min aparece de 15 em 15.
--
-- O QUE MUDA AQUI
--   O link tinha um "Horarios a cada" so (30 min, se ninguem mexeu), que valia
--   para todos os servicos: a barba de 15 min so aparecia 9:00, 9:30, 10:00.
--   Agora cada servico leva o proprio `passo`, escolhido na aba Servicos do
--   Hub (1.5.3 ou mais novo).
--
--   Configuracao de Hub antigo (sem o campo): o servico mais curto que o passo
--   geral anda no tempo dele; os outros ficam como estavam. E a mesma regra
--   que o Hub novo usa para preencher o campo (`online.passo_padrao`).
--
--   `dumtech_agenda_livres` recebe o passo: a lista de horarios da pagina e a
--   conferencia da reserva continuam fazendo a mesma conta.
--
-- Depende de: 20261026130000_agendamento_online.sql
-- =============================================================================

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
           or coalesce(jsonb_typeof(v_item->'preco'), 'null') not in ('number', 'null')
           -- de quanto em quanto tempo aparece: opcional, Hub antigo nao manda
           or (v_item ? 'passo'
               and coalesce((v_item->>'passo')::int, -1) not in (10, 15, 20, 30, 45, 60)) then
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

/**
 * De quanto em quanto tempo o servico aparece no link.
 *
 * O que o dono escolheu na aba Servicos. Sem isso (Hub antigo): o tempo do
 * proprio servico, arredondado para baixo na lista de passos, sem passar do
 * passo geral do link. Barba de 15 min num link de 30 em 30: de 15 em 15.
 */
create or replace function public.dumtech_agenda_passo(p_config jsonb, p_servico jsonb)
returns integer
language sql
immutable
set search_path = ''
as $$
    select coalesce(
        (p_servico->>'passo')::int,
        least(coalesce((p_config->>'passo')::int, 30),
              coalesce((select max(p) from unnest(array[10, 15, 20, 30, 45, 60]) p
                         where p <= coalesce((p_servico->>'duracao')::int, 60)), 10)));
$$;

-- a assinatura muda (ganha o passo): a antiga sai para ninguem chamar sem ele
drop function if exists public.dumtech_agenda_livres(uuid, integer, date, date);

/**
 * Os inicios livres para um servico de `p_duracao` minutos, de `p_de` a `p_ate`,
 * de `p_passo` em `p_passo` minutos (`dumtech_agenda_passo`).
 *
 * Livre e: cabe inteiro num intervalo aberto do dia, no passo da grade a
 * partir do comeco do intervalo; comeca depois de agora + antecedencia; esta
 * dentro da janela de dias; nao encosta em bloqueio; e o MAXIMO de atendimentos
 * simultaneos dentro dele (ocupados publicados + reservas ainda nao entregues)
 * fica abaixo das vagas. Simultaneo de verdade: com 2 vagas, 14:00-14:30 e
 * 14:30-15:00 ocupados ainda deixam livre 14:00-15:00.
 */
create or replace function public.dumtech_agenda_livres(
    p_link uuid, p_duracao integer, p_passo integer, p_de date, p_ate date
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
        select d::date as dia, j.cedo, greatest(coalesce(p_passo, 30), 5) as passo,
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
                                                       public.dumtech_agenda_passo(v.config, v_serv),
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
    if not exists (select 1 from public.dumtech_agenda_livres(v.id, v_dur, public.dumtech_agenda_passo(v.config, v_serv),
                                                                v_inicio::date, v_inicio::date) s
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

-- ================================================================ portas ===
revoke execute on function public.dumtech_agenda_passo(jsonb, jsonb)                       from public, anon, authenticated;
revoke execute on function public.dumtech_agenda_livres(uuid, integer, integer, date, date) from public, anon, authenticated;

notify pgrst, 'reload schema';
