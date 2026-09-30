-- =============================================================================
-- Tres pecas de venda: cupom de desconto, kit por ramo e teste gratis.
--
-- 1. CUPONS
--    `cupons` guarda o codigo (PRIMEIRA10, PARCEIRO-JOAO...), se e % ou R$,
--    validade, limite de usos, valor minimo e "so primeira compra". O banco
--    confere tudo na hora do pedido - o navegador so mostra a previa. O uso
--    so conta quando o pedido e PAGO (pedido abandonado nao gasta cupom).
--
-- 2. KIT POR RAMO
--    `combos.ramo` e o texto do botao em "Qual e o seu negocio?" na loja
--    (ex.: "Oficina ou assistencia"). Kit sem ramo nao aparece la.
--
-- 3. TESTE GRATIS DE 7 DIAS
--    `licenca_testes` guarda inicio e fim de cada teste, um por modulo por
--    licenca. O fim vai DENTRO da licenca assinada (campo `testes`), entao o
--    Hub bloqueia sozinho no dia certo, mesmo sem internet, e editar o
--    arquivo nao estica nada. Hub antigo ignora o campo: nao ganha nada.
-- =============================================================================

-- ================================================================= cupons ===
create table if not exists public.cupons (
    id              uuid primary key default gen_random_uuid(),
    codigo          text not null unique check (codigo ~ '^[A-Z0-9][A-Z0-9_-]{1,30}$'),
    descricao       text not null default '',
    tipo            text not null default 'percentual' check (tipo in ('percentual', 'valor')),
    valor           numeric(12, 2) not null check (valor > 0),
    ativo           boolean not null default true,
    valido_ate      date,
    usos_max        integer check (usos_max is null or usos_max > 0),
    usos            integer not null default 0,
    minimo          numeric(12, 2) not null default 0,
    primeira_compra boolean not null default false,
    -- quem trouxe o cliente (parceiro, revendedor): so para o relatorio
    parceiro        text not null default '',
    criado_em       timestamptz not null default now(),
    atualizado_em   timestamptz not null default now(),
    constraint cupom_percentual_sensato check (tipo <> 'percentual' or valor <= 90)
);

alter table public.cupons enable row level security;
drop policy if exists admin_le on public.cupons;
create policy admin_le on public.cupons for select to authenticated using (public.dumtech_e_admin());
drop policy if exists admin_escreve on public.cupons;
create policy admin_escreve on public.cupons for all to authenticated
    using (public.dumtech_e_admin()) with check (public.dumtech_e_admin());
grant select, insert, update, delete on public.cupons to authenticated;

drop trigger if exists trg_cupons_atualizado on public.cupons;
create trigger trg_cupons_atualizado before update on public.cupons
    for each row execute function public.dumtech_tocar_atualizado_em();

alter table public.pedidos_site add column if not exists cupom    text not null default '';
alter table public.pedidos_site add column if not exists subtotal numeric(12, 2);
alter table public.pedidos_site add column if not exists desconto numeric(12, 2) not null default 0;

/** Confere um cupom para um total. Uso interno (pedido e previa). */
create or replace function public.dumtech_aplicar_cupom(p_codigo text, p_email text, p_total numeric)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    v public.cupons;
    v_desconto numeric(12, 2);
begin
    select * into v from public.cupons where codigo = upper(btrim(coalesce(p_codigo, '')));
    if not found or not v.ativo then
        return jsonb_build_object('ok', false, 'erro', 'cupom_invalido', 'mensagem', 'Cupom não encontrado.');
    end if;
    if v.valido_ate is not null and v.valido_ate < current_date then
        return jsonb_build_object('ok', false, 'erro', 'cupom_vencido', 'mensagem', 'Este cupom venceu.');
    end if;
    if v.usos_max is not null and v.usos >= v.usos_max then
        return jsonb_build_object('ok', false, 'erro', 'cupom_esgotado', 'mensagem', 'Este cupom já foi todo usado.');
    end if;
    if p_total < v.minimo then
        return jsonb_build_object('ok', false, 'erro', 'cupom_minimo',
                                  'mensagem', format('Este cupom vale para compras a partir de R$ %s.',
                                                     replace(to_char(v.minimo, 'FM999G990D00'), '.', ',')));
    end if;
    if v.primeira_compra and coalesce(p_email, '') <> '' and exists (
        select 1 from public.pedidos_site
         where lower(email) = lower(btrim(p_email)) and pagamento = 'pago') then
        return jsonb_build_object('ok', false, 'erro', 'cupom_primeira',
                                  'mensagem', 'Este cupom é só para a primeira compra.');
    end if;

    v_desconto := case when v.tipo = 'percentual' then round(p_total * v.valor / 100, 2) else v.valor end;
    -- ninguem paga menos de R$ 1: a InfinitePay nao cobra zero
    v_desconto := least(v_desconto, greatest(p_total - 1, 0));
    return jsonb_build_object('ok', true, 'codigo', v.codigo, 'descricao', v.descricao,
                              'tipo', v.tipo, 'valor', v.valor, 'desconto', v_desconto,
                              'total', p_total - v_desconto);
end;
$$;
revoke execute on function public.dumtech_aplicar_cupom(text, text, numeric) from public, anon, authenticated;

/** A previa da loja: "PRIMEIRA10 - 10% de desconto". Com limite, contra quem chuta codigos. */
create or replace function public.dumtech_conferir_cupom(p_codigo text, p_email text default '', p_total numeric default 0)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
    if not public.dumtech_dentro_do_limite('cupom_ip', public.dumtech_ip_do_pedido(), 30, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos.');
    end if;
    return public.dumtech_aplicar_cupom(p_codigo, p_email, greatest(coalesce(p_total, 0), 0));
end;
$$;
revoke execute on function public.dumtech_conferir_cupom(text, text, numeric) from public;
grant  execute on function public.dumtech_conferir_cupom(text, text, numeric) to anon, authenticated;

-- o pedido ganha o cupom (a funcao antiga, sem ele, sai: dois formatos
-- com o mesmo nome confundiriam o PostgREST)
drop function if exists public.dumtech_registrar_pedido(text, text, text, text[], text, text, text);

create or replace function public.dumtech_registrar_pedido(
    p_nome     text,
    p_email    text,
    p_telefone text default '',
    p_produtos text[] default '{}',
    p_combo    text default null,
    p_origem   text default 'site',
    p_observacoes text default '',
    p_cupom    text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_nome     text := left(btrim(coalesce(p_nome, '')), 120);
    v_email    text := lower(left(btrim(coalesce(p_email, '')), 160));
    v_telefone text := left(btrim(coalesce(p_telefone, '')), 40);
    v_origem   text := case when p_origem = 'hub' then 'hub' else 'site' end;
    v_combo    public.combos;
    v_produto  public.produtos;
    v_codigo   text;
    v_itens    jsonb := '[]'::jsonb;
    v_total    numeric(12, 2) := 0;
    v_cupom    jsonb;
    v_desconto numeric(12, 2) := 0;
    v_cliente  uuid;
    v_pedido   uuid;
begin
    if not public.dumtech_dentro_do_limite('pedido_ip', public.dumtech_ip_do_pedido(), 12, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Recebemos muitos pedidos seguidos daqui. Espere alguns minutos e tente de novo.');
    end if;

    if v_nome = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe o seu nome.');
    end if;
    if not public.dumtech_email_valido(v_email) then
        return jsonb_build_object('ok', false, 'erro', 'email_invalido',
                                  'mensagem', 'Confira o e-mail digitado.');
    end if;

    if not public.dumtech_dentro_do_limite('pedido_email', v_email, 6, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Ja recebemos varios pedidos com este e-mail. Espere alguns minutos e tente de novo.');
    end if;

    if coalesce(btrim(p_combo), '') <> '' then
        select * into v_combo from public.combos
         where codigo = upper(btrim(p_combo)) and ativo;
        if not found then
            return jsonb_build_object('ok', false, 'erro', 'combo_invalido',
                                      'mensagem', 'Esse pacote nao esta disponivel.');
        end if;
        v_itens := v_itens || jsonb_build_object(
            'tipo', 'combo', 'codigo', v_combo.codigo, 'nome', v_combo.nome,
            'preco', v_combo.preco);
        v_total := v_total + v_combo.preco;
    end if;

    foreach v_codigo in array coalesce(p_produtos, '{}') loop
        v_codigo := upper(btrim(v_codigo));
        continue when v_codigo = '';
        select * into v_produto from public.produtos where codigo = v_codigo and ativo;
        if not found then
            return jsonb_build_object('ok', false, 'erro', 'produto_invalido',
                                      'mensagem', format('O modulo %s nao esta disponivel.', left(v_codigo, 40)));
        end if;
        -- produto que ja entrou pelo combo nao e cobrado duas vezes
        if v_combo.id is null or not exists (
            select 1 from public.combo_produtos cp
             where cp.combo_id = v_combo.id and cp.produto_id = v_produto.id
        ) then
            v_itens := v_itens || jsonb_build_object(
                'tipo', 'produto', 'codigo', v_produto.codigo, 'nome', v_produto.nome,
                'preco', v_produto.preco);
            v_total := v_total + v_produto.preco;
        end if;
    end loop;

    if jsonb_array_length(v_itens) = 0 then
        return jsonb_build_object('ok', false, 'erro', 'kit_vazio',
                                  'mensagem', 'Escolha ao menos um modulo.');
    end if;

    -- cupom: o banco decide. Cupom que nao vale recusa o pedido com a
    -- mensagem certa - pagar mais do que o combinado nao e opcao.
    if coalesce(btrim(p_cupom), '') <> '' then
        v_cupom := public.dumtech_aplicar_cupom(p_cupom, v_email, v_total);
        if not (v_cupom->>'ok')::boolean then
            return v_cupom;
        end if;
        v_desconto := (v_cupom->>'desconto')::numeric;
    end if;

    select id into v_cliente from public.clientes where lower(email) = v_email;
    if not found then
        insert into public.clientes (nome, email, telefone, origem)
        values (v_nome, v_email, v_telefone, 'hub')
        returning id into v_cliente;
    end if;

    insert into public.pedidos_site (cliente_id, nome, email, telefone, itens,
                                     subtotal, desconto, cupom, total, origem, observacoes)
    values (v_cliente, v_nome, v_email, v_telefone, v_itens,
            v_total, v_desconto, coalesce(v_cupom->>'codigo', ''), v_total - v_desconto,
            v_origem, left(btrim(coalesce(p_observacoes, '')), 500))
    returning id into v_pedido;

    return jsonb_build_object('ok', true, 'pedido', v_pedido, 'itens', v_itens,
                              'subtotal', v_total, 'desconto', v_desconto,
                              'cupom', coalesce(v_cupom->>'codigo', ''),
                              'total', v_total - v_desconto);
end;
$$;
revoke execute on function public.dumtech_registrar_pedido(text, text, text, text[], text, text, text, text) from public;
grant  execute on function public.dumtech_registrar_pedido(text, text, text, text[], text, text, text, text) to anon, authenticated;

-- o uso do cupom conta quando o pedido e PAGO - e uma vez so
create or replace function public.dumtech_contar_cupom()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if new.cupom <> '' and new.pagamento = 'pago' and old.pagamento is distinct from 'pago' then
        update public.cupons set usos = usos + 1 where codigo = new.cupom;
    end if;
    return new;
end;
$$;
drop trigger if exists trg_pedido_conta_cupom on public.pedidos_site;
create trigger trg_pedido_conta_cupom after update of pagamento on public.pedidos_site
    for each row execute function public.dumtech_contar_cupom();

-- ============================================================ kit por ramo ===
alter table public.combos add column if not exists ramo text not null default '';

create or replace function public.dumtech_catalogo()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    select jsonb_build_object(
        'ok', true,
        'produtos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'codigo', p.codigo, 'nome', p.nome, 'descricao', p.descricao,
                       'preco', p.preco, 'versao', p.versao)
                   order by p.codigo)
              from public.produtos p
             where p.ativo
        ), '[]'::jsonb),
        'combos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'codigo', c.codigo, 'nome', c.nome, 'descricao', c.descricao,
                       'preco', c.preco, 'ramo', c.ramo,
                       'produtos', coalesce((
                           select jsonb_agg(p.codigo order by p.codigo)
                             from public.combo_produtos cp
                             join public.produtos p on p.id = cp.produto_id
                            where cp.combo_id = c.id and p.ativo
                       ), '[]'::jsonb))
                   order by c.preco)
              from public.combos c
             where c.ativo
        ), '[]'::jsonb),
        'verificado_em', now());
$$;

-- ========================================================== teste gratis ===
create table if not exists public.licenca_testes (
    licenca_id  uuid not null references public.licencas(id) on delete cascade,
    produto_id  uuid not null references public.produtos(id) on delete restrict,
    iniciado_em timestamptz not null default now(),
    termina_em  timestamptz not null,
    primary key (licenca_id, produto_id)
);
alter table public.licenca_testes enable row level security;
drop policy if exists admin_le on public.licenca_testes;
create policy admin_le on public.licenca_testes for select to authenticated using (public.dumtech_e_admin());
grant select on public.licenca_testes to authenticated;

-- a resposta da licenca ganha `testes`: {"AGENDA": "2026-09-29T12:00:00Z"}.
-- Modulo comprado nao aparece como teste (ja e dele).
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

/** O Hub pede: "quero testar a Agenda". Um teste por modulo por licenca. */
create or replace function public.dumtech_iniciar_teste(
    p_chave   text,
    p_maquina text,
    p_produto text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid;
    v_produto public.produtos;
    v_fim     timestamptz;
begin
    -- o IP e o do pedido que chegou (nao um que o chamador diga ter)
    if not public.dumtech_dentro_do_limite('teste_ip', public.dumtech_ip_do_pedido(), 20, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos.');
    end if;

    -- so quem tem esta licenca ATIVADA nesta maquina (e valida) pede teste
    select l.id into v_licenca
      from public.licencas l
      join public.ativacoes a on a.licenca_id = l.id
     where l.chave = public.dumtech_normalizar(p_chave, 32)
       and a.maquina = public.dumtech_normalizar(p_maquina, 64)
       and public.dumtech_situacao_licenca(l.status, l.expira_em) = 'ativa';
    if v_licenca is null then
        return jsonb_build_object('ok', false, 'erro', 'licenca_invalida',
                                  'mensagem', 'Ative a sua licenca neste computador para testar outros modulos.');
    end if;

    select * into v_produto from public.produtos
     where codigo = upper(btrim(coalesce(p_produto, ''))) and ativo;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'produto_invalido',
                                  'mensagem', 'Este modulo nao esta disponivel para teste.');
    end if;
    if exists (select 1 from public.licenca_produtos
                where licenca_id = v_licenca and produto_id = v_produto.id) then
        return jsonb_build_object('ok', false, 'erro', 'ja_tem', 'mensagem', 'Este modulo ja e seu.');
    end if;

    v_fim := now() + interval '7 days';
    insert into public.licenca_testes (licenca_id, produto_id, termina_em)
    values (v_licenca, v_produto.id, v_fim)
    on conflict (licenca_id, produto_id) do nothing;
    if not found then
        select termina_em into v_fim from public.licenca_testes
         where licenca_id = v_licenca and produto_id = v_produto.id;
        if v_fim < now() then
            return jsonb_build_object('ok', false, 'erro', 'teste_usado',
                                      'mensagem', 'O teste gratis deste modulo ja foi usado.');
        end if;
        -- teste ainda correndo: pedir de novo so devolve a mesma data
    end if;

    return jsonb_build_object('ok', true, 'produto', v_produto.codigo, 'termina_em', v_fim);
end;
$$;
revoke execute on function public.dumtech_iniciar_teste(text, text, text) from public, authenticated;
grant  execute on function public.dumtech_iniciar_teste(text, text, text) to anon;

-- ================================================================ portas ===
-- tabelas novas nascem com as permissoes largas do Supabase: fecha tudo e
-- abre so o que o painel usa (sempre atras da policy de admin)
revoke all on table public.cupons         from anon, authenticated;
revoke all on table public.licenca_testes from anon, authenticated;
grant select, insert, update, delete on public.cupons to authenticated;
grant select on public.licenca_testes to authenticated;
-- funcao de gatilho nao e porta de ninguem
revoke execute on function public.dumtech_contar_cupom() from public, anon, authenticated;

notify pgrst, 'reload schema';
