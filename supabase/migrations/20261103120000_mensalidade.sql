-- =============================================================================
-- Mensalidade: plano base + adicionais, teste de 7 dias e cobranca que o Eric
-- confirma no painel (os planos ficam no app da InfinitePay, que nao avisa o
-- sistema). Desenho: docs/superpowers/specs/2026-11-03-mensalidade-design.md
--
-- O QUE ENTRA
--   1. A licenca mensal: assinatura sem prazo = em dia; com prazo = pendente
--      ate a data; passou = recusa `expirada` (o Hub abre em modo consulta).
--      A resposta ganha `cobranca` - so quando o tipo nao e vitalicia.
--   2. Precos e links da InfinitePay em `mensalidade_config`, editaveis no painel.
--   3. O cadastro do site (teste gratis e pedido de assinatura), chamado so
--      pela Edge Function `mensalidade`, que manda a chave por e-mail.
--   4. As acoes do Eric: confirmar, descartar, cobranca falhou, em dia,
--      cancelou, estender teste. E as visoes da tela Mensalidades.
--   5. A loja pelo Hub sabe o tipo da licenca (so com a prova da chave).
--
-- O QUE NAO MUDA
--   Licenca vitalicia: continua sem prazo, a resposta dela sai igual a antes
--   (byte a byte) e nenhuma funcao daqui mexe nela.
-- =============================================================================

-- ======================================================= 1. A LICENCA =====
alter table public.licencas drop constraint if exists licencas_prazo_check;
alter table public.licencas add  constraint licencas_prazo_check check (
    case tipo
        when 'vitalicia' then expira_em is null
        when 'teste'     then expira_em is not null
        else true        -- assinatura: sem prazo = em dia
    end);

alter table public.licencas add column if not exists cobranca_motivo  text;
alter table public.licencas add column if not exists cobranca_desde   date;
alter table public.licencas add column if not exists assinatura_desde date;
alter table public.licencas drop constraint if exists licencas_cobranca_motivo_check;
alter table public.licencas add  constraint licencas_cobranca_motivo_check
    check (cobranca_motivo is null or cobranca_motivo in ('falhou', 'cancelou'));

comment on column public.licencas.cobranca_motivo is
    'Mensalidade: por que ha prazo - falhou (cobranca nao confirmada) ou cancelou.';
comment on column public.licencas.assinatura_desde is
    'Mensalidade: quando a assinatura foi confirmada (o dia da cobranca no mes).';

-- O plano: fixo aqui, igual ao site e ao Hub
create or replace function public.dumtech_plano_base()
returns text[] language sql immutable set search_path = ''
as $$ select array['ESTOQUE', 'FINANCEIRO', 'VENDAS']::text[] $$;

create or replace function public.dumtech_plano_adicionais()
returns text[] language sql immutable set search_path = ''
as $$ select array['AGENDA', 'CLIENTES', 'ORCAMENTOS', 'ORDENS']::text[] $$;

/** So adicional de verdade, sem repetir, em ordem. O resto e texto de estranho. */
create or replace function public.dumtech_adicionais_validos(p_adicionais text[])
returns text[] language sql immutable set search_path = ''
as $$
    select coalesce(array_agg(distinct x.codigo order by x.codigo), '{}'::text[])
      from unnest(coalesce(p_adicionais, '{}'::text[])) as u(bruto)
      cross join lateral (select upper(btrim(u.bruto)) as codigo) x
     where x.codigo = any(public.dumtech_plano_adicionais());
$$;

-- A situacao da cobranca: calculada, nunca gravada (como `expirada`)
create or replace function public.dumtech_situacao_cobranca(p_tipo text, p_expira_em date)
returns text language sql stable set search_path = ''
as $$
    select case
        when p_tipo is null or p_tipo not in ('assinatura', 'teste') then null
        when p_expira_em is not null and p_expira_em < current_date then 'consulta'
        when p_tipo = 'teste' then 'teste'
        when p_expira_em is null then 'em_dia'
        else 'pendente'
    end;
$$;

-- ================================================ 2. PRECOS E LINKS ========
/** Cada link: vazio ou https. Chave = quantos adicionais (0 a 4). */
create or replace function public.dumtech_links_validos(p_links jsonb)
returns boolean language sql immutable set search_path = ''
as $$
    select jsonb_typeof(p_links) = 'object'
       and coalesce((select bool_and(e.k in ('0', '1', '2', '3', '4')
                                     and jsonb_typeof(e.v) = 'string'
                                     and (e.v #>> '{}' = '' or e.v #>> '{}' ~ '^https://[^[:space:]<>"]+$'))
                       from jsonb_each(p_links) as e(k, v)), true);
$$;

create table if not exists public.mensalidade_config (
    id              boolean primary key default true check (id),
    preco_base      numeric(10,2) not null default 89.90 check (preco_base >= 0),
    preco_adicional numeric(10,2) not null default 29.90 check (preco_adicional >= 0),
    links           jsonb not null default '{}'::jsonb check (public.dumtech_links_validos(links)),
    dias_teste      integer not null default 7 check (dias_teste between 1 and 60),
    dias_carencia   integer not null default 7 check (dias_carencia between 0 and 60),
    computadores    integer not null default 1 check (computadores between 1 and 50),
    atualizado_em   timestamptz not null default now()
);
comment on table public.mensalidade_config is
    'Uma linha so: precos do plano mensal, links dos planos da InfinitePay (por quantidade de adicionais) e prazos.';
insert into public.mensalidade_config (id) values (true) on conflict (id) do nothing;

drop trigger if exists trg_mensalidade_config_atualizado on public.mensalidade_config;
create trigger trg_mensalidade_config_atualizado before update on public.mensalidade_config
    for each row execute function public.dumtech_tocar_atualizado_em();

alter table public.mensalidade_config enable row level security;
revoke all on table public.mensalidade_config from public, anon, authenticated;
grant select, update on table public.mensalidade_config to authenticated;
drop policy if exists admin_le on public.mensalidade_config;
create policy admin_le on public.mensalidade_config for select to authenticated
    using (public.dumtech_e_admin());
drop policy if exists admin_muda on public.mensalidade_config;
create policy admin_muda on public.mensalidade_config for update to authenticated
    using (public.dumtech_e_admin()) with check (public.dumtech_e_admin());

create or replace function public.dumtech_valor_mensal(p_adicionais integer)
returns numeric language sql stable security definer set search_path = ''
as $$
    select c.preco_base + greatest(0, least(coalesce(p_adicionais, 0), 4)) * c.preco_adicional
      from public.mensalidade_config c where c.id;
$$;

/** A vitrine do site: preco e o que da para assinar. Os links nao saem daqui. */
create or replace function public.dumtech_mensalidade_publica()
returns jsonb language sql stable security definer set search_path = ''
as $$
    select jsonb_build_object(
        'ok', true,
        'preco_base', c.preco_base,
        'preco_adicional', c.preco_adicional,
        'base', to_jsonb(public.dumtech_plano_base()),
        'adicionais', to_jsonb(public.dumtech_plano_adicionais()),
        'dias_teste', c.dias_teste,
        'computadores', c.computadores,
        'assinavel', (select jsonb_object_agg(n::text, coalesce(c.links ->> n::text, '') <> '')
                        from generate_series(0, 4) as n))
      from public.mensalidade_config c where c.id;
$$;

-- ============================================ 3. RESPOSTA E RECUSA =========
-- O corpo de 20260922120000 + `cobranca`, so para assinatura e teste: a
-- resposta da vitalicia sai identica a de antes.
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
        'testes', coalesce((
            select jsonb_object_agg(p.codigo, to_char(t.termina_em at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'))
              from public.licenca_testes t
              join public.produtos p on p.id = t.produto_id
             where t.licenca_id = l.id
               and not exists (select 1 from public.licenca_produtos lp
                                where lp.licenca_id = l.id and lp.produto_id = t.produto_id)
        ), '{}'::jsonb),
        'expira_em', l.expira_em,
        'max_computadores', l.max_computadores,
        'computadores_usados', (select count(*) from public.ativacoes a
                                 where a.licenca_id = l.id),
        'verificado_em', now()
    ) || case when l.tipo in ('assinatura', 'teste') then jsonb_build_object(
        'cobranca', jsonb_build_object(
            'situacao', public.dumtech_situacao_cobranca(l.tipo, l.expira_em),
            'ate', l.expira_em,
            'motivo', l.cobranca_motivo,
            'desde', l.assinatura_desde))
        else '{}'::jsonb end
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

-- O corpo de 20260911120000 com as recusas da mensalidade em texto de gente:
-- e o Hub que mostra, e quem le e o cliente.
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
            raise exception 'expirada|Seu teste grátis terminou em %. Está tudo guardado: você pode consultar o que lançou e, para voltar a lançar, é só assinar.',
                to_char(v_licenca.expira_em, 'DD/MM/YYYY');
        end if;
        if v_licenca.tipo = 'assinatura' and v_licenca.cobranca_motivo = 'cancelou' then
            raise exception 'expirada|Sua assinatura foi encerrada em %. Seus dados continuam guardados e você pode consultar tudo. Quando quiser voltar, é só assinar de novo.',
                to_char(v_licenca.expira_em, 'DD/MM/YYYY');
        end if;
        if v_licenca.tipo = 'assinatura' and v_licenca.cobranca_motivo = 'falhou' then
            raise exception 'expirada|Não conseguimos confirmar a sua mensalidade. Seus dados estão guardados e você pode consultar tudo. Assim que o pagamento for confirmado, o Hub volta ao normal sozinho.';
        end if;
        raise exception 'expirada|Esta licenca venceu em %. Renove para continuar.',
            to_char(v_licenca.expira_em, 'DD/MM/YYYY');
    end if;

    return v_licenca;
end;
$$;

-- ============================================ 4. O CADASTRO DO SITE =======
create table if not exists public.assinatura_pedidos (
    id           uuid primary key default gen_random_uuid(),
    licenca_id   uuid not null references public.licencas(id) on delete cascade,
    adicionais   text[] not null default '{}',
    valor        numeric(10,2) not null check (valor >= 0),
    link         text not null default '',
    situacao     text not null default 'aguardando'
                 check (situacao in ('aguardando', 'confirmado', 'descartado')),
    criado_em    timestamptz not null default now(),
    resolvido_em timestamptz
);
comment on table public.assinatura_pedidos is
    'Quem pediu para assinar pelo site. O Eric confirma quando a assinatura aparece no app da InfinitePay.';
create index if not exists idx_assinatura_pedidos_licenca on public.assinatura_pedidos (licenca_id);

alter table public.assinatura_pedidos enable row level security;
revoke all on table public.assinatura_pedidos from public, anon, authenticated;
grant select on table public.assinatura_pedidos to authenticated;
drop policy if exists admin_le on public.assinatura_pedidos;
create policy admin_le on public.assinatura_pedidos for select to authenticated
    using (public.dumtech_e_admin());

/**
 * Teste gratis e pedido de assinatura. So a Edge Function `mensalidade` chama
 * (service_role): e ela que manda a chave por e-mail - o navegador nunca ve a
 * chave, entao o e-mail digitado precisa ser de verdade.
 *
 * caso: nova (licenca de teste criada) | ja_tem (devolve a chave que existe) |
 *       vitalicio (nada muda: vitalicio nunca e empurrado para mensalidade).
 */
create or replace function public.dumtech_cadastrar_mensal(
    p_nome       text,
    p_email      text,
    p_telefone   text    default '',
    p_adicionais text[]  default '{}',
    p_assinar    boolean default false,
    p_ip         text    default ''
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
    v_adicionais text[] := public.dumtech_adicionais_validos(p_adicionais);
    v_config     public.mensalidade_config;
    v_cliente    public.clientes;
    v_licenca    public.licencas;
    v_id         uuid;
    v_caso       text;
    v_n          integer;
    v_link       text := '';
    v_valor      numeric;
    v_assinar    boolean := coalesce(p_assinar, false);
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
        select e.licenca_id into v_id
          from public.dumtech_emitir_licenca(
                   v_cliente.id,
                   public.dumtech_plano_base() || public.dumtech_plano_adicionais(),
                   null, 'teste', current_date + v_config.dias_teste, v_config.computadores,
                   'Teste do plano mensal pelo site') e;
        select * into v_licenca from public.licencas where id = v_id;
        v_caso := 'nova';
    end if;

    -- link e valor saem iguais para todos os casos: a resposta que chega ao
    -- navegador nao pode contar quem ja e cliente. O vitalicio nao ganha
    -- pedido, e o e-mail dele explica que nao precisa assinar nada.
    if v_assinar then
        v_n := coalesce(array_length(v_adicionais, 1), 0);
        v_valor := v_config.preco_base + v_n * v_config.preco_adicional;
        v_link := coalesce(v_config.links ->> v_n::text, '');
    end if;
    if v_assinar and v_caso <> 'vitalicio' then
        -- pedir de novo troca o pedido que esperava: um por licenca
        update public.assinatura_pedidos
           set situacao = 'descartado', resolvido_em = now()
         where licenca_id = v_licenca.id and situacao = 'aguardando';
        insert into public.assinatura_pedidos (licenca_id, adicionais, valor, link)
        values (v_licenca.id, v_adicionais, v_valor, v_link);
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
        'adicionais', to_jsonb(v_adicionais),
        'valor', v_valor,
        'link', v_link);
end;
$$;

-- ========================================= 5. A LOJA PELO HUB SABE O TIPO ===
-- O corpo de 20260911230000 + `tipo`. So vem quando o token nasceu da chave com
-- o computador ativado (produtos nao vazio): quem so digitou um e-mail nao
-- descobre nada do cadastro de ninguem.
create or replace function public.dumtech_abrir_compra(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_linha public.compra_tokens;
    v_tipo  text := '';
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

    if v_linha.cliente_id is not null and jsonb_array_length(v_linha.produtos) > 0 then
        select l.tipo into v_tipo from public.licencas l
         where l.cliente_id = v_linha.cliente_id and l.status <> 'cancelada'
         order by (l.tipo = 'vitalicia') desc, l.criado_em desc
         limit 1;
    end if;

    return jsonb_build_object('ok', true, 'nome', v_linha.nome, 'email', v_linha.email,
                              'produtos', v_linha.produtos, 'tipo', coalesce(v_tipo, ''));
end;
$$;

-- ============================================== 6. AS ACOES DO ERIC =======
-- Todas abrem com o portao do painel (admin com 2 fatores) e devolvem o que
-- a Edge Function precisa para mandar o e-mail.

create or replace function public.dumtech_confirmar_assinatura(p_pedido uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_pedido  public.assinatura_pedidos;
    v_licenca public.licencas;
    v_cliente public.clientes;
    v_codigos text[];
    v_mudanca boolean;
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
    v_codigos := public.dumtech_plano_base() || public.dumtech_adicionais_validos(v_pedido.adicionais);

    update public.licencas
       set tipo = 'assinatura', expira_em = null, cobranca_motivo = null, cobranca_desde = null,
           assinatura_desde = case when v_mudanca then coalesce(assinatura_desde, current_date)
                                   else current_date end
     where id = v_licenca.id;

    delete from public.licenca_produtos lp
     using public.produtos p
     where lp.licenca_id = v_licenca.id and p.id = lp.produto_id and not (p.codigo = any(v_codigos));
    insert into public.licenca_produtos (licenca_id, produto_id)
    select v_licenca.id, p.id from public.produtos p where p.codigo = any(v_codigos)
    on conflict (licenca_id, produto_id) do nothing;

    update public.assinatura_pedidos set situacao = 'confirmado', resolvido_em = now()
     where id = v_pedido.id;
    update public.assinatura_pedidos set situacao = 'descartado', resolvido_em = now()
     where licenca_id = v_licenca.id and situacao = 'aguardando';

    select * into v_cliente from public.clientes where id = v_licenca.cliente_id;
    return jsonb_build_object(
        'ok', true, 'nome', v_cliente.nome, 'email', v_cliente.email, 'telefone', v_cliente.telefone,
        'chave', v_licenca.chave, 'adicionais', to_jsonb(public.dumtech_adicionais_validos(v_pedido.adicionais)),
        'valor', v_pedido.valor, 'mudanca', v_mudanca);
end;
$$;

create or replace function public.dumtech_descartar_assinatura(p_pedido uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
    perform public.dumtech_painel_portao();
    update public.assinatura_pedidos set situacao = 'descartado', resolvido_em = now()
     where id = p_pedido and situacao = 'aguardando';
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'pedido',
                                  'mensagem', 'Este pedido já foi resolvido ou não existe mais.');
    end if;
    return jsonb_build_object('ok', true);
end;
$$;

/** falhou (carencia) | em_dia (limpa) | cancelou (encerra na data, padrao: carencia). */
create or replace function public.dumtech_cobranca(p_licenca uuid, p_acao text, p_ate date default null)
returns jsonb
language plpgsql
security definer
set search_path = ''
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
        -- clicar de novo nao estica o prazo de quem ja esta pendente
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
    select * into v_cliente from public.clientes where id = v_licenca.cliente_id;
    return jsonb_build_object('ok', true, 'acao', p_acao, 'nome', v_cliente.nome,
                              'email', v_cliente.email, 'telefone', v_cliente.telefone,
                              'ate', v_licenca.expira_em);
end;
$$;

create or replace function public.dumtech_estender_teste_mensal(p_licenca uuid, p_dias integer default 7)
returns jsonb
language plpgsql
security definer
set search_path = ''
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
    select * into v_cliente from public.clientes where id = v_licenca.cliente_id;
    return jsonb_build_object('ok', true, 'nome', v_cliente.nome, 'email', v_cliente.email,
                              'telefone', v_cliente.telefone, 'ate', v_licenca.expira_em);
end;
$$;

-- ================================================= 7. VISOES DO PAINEL ====
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
       coalesce(itens.adicionais, '{}'::text[]) as adicionais,
       public.dumtech_valor_mensal(coalesce(array_length(itens.adicionais, 1), 0)) as valor,
       (select count(*) from public.ativacoes a where a.licenca_id = l.id)::integer as computadores
  from public.licencas l
  join public.clientes c on c.id = l.cliente_id
  left join lateral (
        select array_agg(p.codigo order by p.codigo)
                 filter (where p.codigo = any(public.dumtech_plano_adicionais())) as adicionais
          from public.licenca_produtos lp
          join public.produtos p on p.id = lp.produto_id
         where lp.licenca_id = l.id
  ) itens on true
 where l.tipo in ('assinatura', 'teste');

create or replace view public.painel_assinatura_pedidos with (security_invoker = true) as
select ap.id,
       ap.licenca_id,
       ap.adicionais,
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
  join public.clientes c on c.id = l.cliente_id;

-- ======================================================= 8. PERMISSOES ====
revoke all on public.painel_mensalidades, public.painel_assinatura_pedidos from public, anon;
grant select on public.painel_mensalidades, public.painel_assinatura_pedidos to authenticated;

revoke execute on function public.dumtech_cadastrar_mensal(text, text, text, text[], boolean, text)
    from public, anon, authenticated;
grant  execute on function public.dumtech_cadastrar_mensal(text, text, text, text[], boolean, text)
    to service_role;

-- as pecas pequenas: o painel (visoes e a regra dos links) usa, o site nao
revoke execute on function public.dumtech_plano_base()                 from public, anon;
revoke execute on function public.dumtech_plano_adicionais()           from public, anon;
revoke execute on function public.dumtech_adicionais_validos(text[])   from public, anon;
revoke execute on function public.dumtech_situacao_cobranca(text, date) from public, anon;
revoke execute on function public.dumtech_links_validos(jsonb)         from public, anon;
grant  execute on function public.dumtech_plano_base()                 to authenticated, service_role;
grant  execute on function public.dumtech_plano_adicionais()           to authenticated, service_role;
grant  execute on function public.dumtech_adicionais_validos(text[])   to authenticated, service_role;
grant  execute on function public.dumtech_situacao_cobranca(text, date) to authenticated, service_role;
grant  execute on function public.dumtech_links_validos(jsonb)         to authenticated, service_role;

revoke execute on function public.dumtech_mensalidade_publica() from public;
grant  execute on function public.dumtech_mensalidade_publica() to anon, authenticated;

revoke execute on function public.dumtech_valor_mensal(integer) from public, anon;
grant  execute on function public.dumtech_valor_mensal(integer) to authenticated, service_role;

revoke execute on function public.dumtech_confirmar_assinatura(uuid)            from public, anon;
revoke execute on function public.dumtech_descartar_assinatura(uuid)            from public, anon;
revoke execute on function public.dumtech_cobranca(uuid, text, date)            from public, anon;
revoke execute on function public.dumtech_estender_teste_mensal(uuid, integer)  from public, anon;
grant  execute on function public.dumtech_confirmar_assinatura(uuid)            to authenticated;
grant  execute on function public.dumtech_descartar_assinatura(uuid)            to authenticated;
grant  execute on function public.dumtech_cobranca(uuid, text, date)            to authenticated;
grant  execute on function public.dumtech_estender_teste_mensal(uuid, integer)  to authenticated;
