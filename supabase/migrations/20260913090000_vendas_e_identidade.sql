-- =============================================================================
-- 20260913090000 - vendas por qualquer canal e um cadastro por cliente
--
-- O QUE MUDA
--   1. uma chave por cliente   aprovar pedido (ou vender a mao) usa a licenca que o
--                              cliente JA TEM - inclusive suspensa, cancelada ou
--                              vencida, que volta a valer. Antes, quem nao tinha
--                              licenca ATIVA ganhava uma segunda chave.
--   2. renovacao de verdade    a aprovacao pode dizer o tipo e o vencimento; teste
--                              que vira compra passa a vitalicia sozinho.
--   3. venda manual            Mercado Livre e venda direta entram como pedido
--                              atendido, com o valor recebido: "Vendido" e
--                              "Comprou" do painel passam a contar tudo.
--   4. cadastro unico          o Hub liga o e-mail digitado no primeiro acesso a
--                              licenca ativada (dumtech_vincular_conta) e junta o
--                              cadastro solto que o e-mail tinha criado.
--   5. avisos no pedido        o que o cliente ja tem, e em que situacao esta a
--                              licenca dele, aparecem antes de aprovar.
-- =============================================================================

-- ======================================================== 1. PEDIDOS ========
alter table public.pedidos_site add column if not exists referencia text not null default '';

comment on column public.pedidos_site.referencia is
    'Numero do pedido no canal de origem (ex.: venda do Mercado Livre).';

alter table public.pedidos_site drop constraint if exists pedidos_site_origem_check;
alter table public.pedidos_site add constraint pedidos_site_origem_check
    check (origem in ('hub', 'site', 'mercadolivre', 'manual'));

-- ================================================ 2. ENTREGAR PRODUTOS ======
-- O unico lugar que decide "qual licenca recebe o que foi vendido". Roda com o
-- papel de quem chama (as policies do painel decidem), como emitir e liberar.
create or replace function public.dumtech_entregar_produtos(
    p_cliente_id       uuid,
    p_produtos         text[]  default '{}',
    p_combo            text    default null,
    p_tipo             text    default null,   -- null = manter o da licenca
    p_expira_em        date    default null,
    p_max_computadores integer default 1,
    p_observacoes      text    default ''
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
    v_licenca   public.licencas;
    v_id        uuid;
    v_chave     text;
    v_nova      boolean;
    v_reativada boolean := false;
    v_tipo      text;
    v_expira    date;
    v_liberados integer;
    v_maximo    integer := greatest(coalesce(p_max_computadores, 1), 1);
begin
    if nullif(btrim(coalesce(p_tipo, '')), '') is not null
       and p_tipo not in ('vitalicia', 'assinatura', 'teste') then
        raise exception 'Tipo de licenca invalido: %.', p_tipo;
    end if;
    if p_tipo in ('assinatura', 'teste') and p_expira_em is null then
        raise exception 'Licenca de % precisa de data de vencimento.', p_tipo;
    end if;

    -- a licenca do cliente: a ativa, senao a mais recente (suspensa, cancelada...)
    select * into v_licenca
      from public.licencas
     where cliente_id = p_cliente_id
     order by (status = 'ativa') desc, criado_em desc
     limit 1
       for update;
    v_nova := not found;

    if v_nova then
        v_tipo := coalesce(nullif(btrim(coalesce(p_tipo, '')), ''), 'vitalicia');
        v_expira := case when v_tipo = 'vitalicia' then null else p_expira_em end;
        select e.licenca_id, e.chave into v_id, v_chave
          from public.dumtech_emitir_licenca(
                p_cliente_id       => p_cliente_id,
                p_produtos         => p_produtos,
                p_combo            => p_combo,
                p_tipo             => v_tipo,
                p_expira_em        => v_expira,
                p_max_computadores => v_maximo,
                p_observacoes      => coalesce(p_observacoes, '')) e;
        select count(*) into v_liberados from public.licenca_produtos where licenca_id = v_id;
    else
        v_id := v_licenca.id;
        v_chave := v_licenca.chave;
        v_reativada := v_licenca.status <> 'ativa';
        -- tipo: o que foi dito na venda manda; teste que virou compra e vitalicia;
        -- sem nada dito, fica como estava
        v_tipo := case
            when nullif(btrim(coalesce(p_tipo, '')), '') is not null then p_tipo
            when v_licenca.tipo = 'teste' then 'vitalicia'
            else v_licenca.tipo
        end;
        v_expira := case
            when v_tipo = 'vitalicia' then null
            when nullif(btrim(coalesce(p_tipo, '')), '') is not null then p_expira_em
            else v_licenca.expira_em
        end;
        update public.licencas
           set status = 'ativa',
               tipo = v_tipo,
               expira_em = v_expira,
               max_computadores = greatest(max_computadores, v_maximo)
         where id = v_id;
        v_liberados := public.dumtech_liberar_produtos(v_id, p_produtos, p_combo);
    end if;

    return jsonb_build_object(
        'licenca_id', v_id,
        'chave', v_chave,
        'licenca_nova', v_nova,
        'reativada', v_reativada,
        'produtos_liberados', v_liberados,
        'tipo', v_tipo,
        'expira_em', v_expira);
end;
$$;

-- ======================================================= 3. APROVAR =========
create or replace function public.dumtech_aprovar_pedido(
    p_pedido_id        uuid,
    p_max_computadores integer default 1,
    p_tipo             text    default null,
    p_expira_em        date    default null
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
    v_pedido   public.pedidos_site;
    v_produtos text[];
    v_combo    text;
    v_entrega  jsonb;
begin
    -- trava o pedido: dois cliques (ou dois administradores) nao entregam duas vezes
    select * into v_pedido from public.pedidos_site where id = p_pedido_id for update;
    if not found then
        raise exception 'Pedido % nao existe.', p_pedido_id;
    end if;
    if v_pedido.atendido_em is not null then
        raise exception 'Este pedido ja foi atendido em %.',
            to_char(v_pedido.atendido_em, 'DD/MM/YYYY HH24:MI');
    end if;
    if v_pedido.cliente_id is null then
        raise exception 'Pedido sem cliente ligado - resolva o cadastro antes.';
    end if;

    select coalesce(array_agg(item->>'codigo') filter (where item->>'tipo' = 'produto'), '{}'),
           max(item->>'codigo') filter (where item->>'tipo' = 'combo')
      into v_produtos, v_combo
      from jsonb_array_elements(v_pedido.itens) item;

    v_entrega := public.dumtech_entregar_produtos(
        v_pedido.cliente_id, v_produtos, v_combo, p_tipo, p_expira_em, p_max_computadores,
        format('pedido do site %s', p_pedido_id));

    update public.pedidos_site set atendido_em = now() where id = p_pedido_id;

    return v_entrega || jsonb_build_object(
        'ok', true,
        'cliente', (select nome from public.clientes where id = v_pedido.cliente_id),
        'email', v_pedido.email,
        'total', v_pedido.total);
end;
$$;

-- ================================================== 4. VENDA MANUAL =========
-- Mercado Livre e venda direta (telefone, balcao): cadastra se precisar, entrega
-- na licenca do cliente e registra a venda com o valor recebido.
create or replace function public.dumtech_venda_manual(
    p_nome             text,
    p_email            text    default '',
    p_telefone         text    default '',
    p_produtos         text[]  default '{}',
    p_combo            text    default null,
    p_canal            text    default 'manual',
    p_referencia       text    default '',
    p_total            numeric default null,
    p_tipo             text    default null,
    p_expira_em        date    default null,
    p_max_computadores integer default 1,
    p_cliente_id       uuid    default null
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
    v_nome     text := left(btrim(coalesce(p_nome, '')), 120);
    v_email    text := lower(left(btrim(coalesce(p_email, '')), 160));
    v_telefone text := left(btrim(coalesce(p_telefone, '')), 40);
    v_canal    text := case when p_canal = 'mercadolivre' then 'mercadolivre' else 'manual' end;
    v_cliente  public.clientes;
    v_combo    public.combos;
    v_produto  public.produtos;
    v_codigo   text;
    v_itens    jsonb := '[]'::jsonb;
    v_catalogo numeric(12, 2) := 0;
    v_entrega  jsonb;
    v_pedido   uuid;
begin
    if v_email <> '' and not public.dumtech_email_valido(v_email) then
        raise exception 'Confira o e-mail do comprador.';
    end if;

    -- quem e o cliente: o escolhido na ficha, senao pelo e-mail, senao nasce agora
    if p_cliente_id is not null then
        select * into v_cliente from public.clientes where id = p_cliente_id;
        if not found then
            raise exception 'Cliente % nao existe.', p_cliente_id;
        end if;
    elsif v_email <> '' then
        select * into v_cliente from public.clientes where lower(email) = v_email;
    end if;

    if v_cliente.id is null then
        if v_nome = '' then
            raise exception 'Informe o nome do comprador.';
        end if;
        insert into public.clientes (nome, email, telefone, origem)
        values (v_nome, v_email, v_telefone, 'venda')
        returning * into v_cliente;
    else
        -- completa o que o cadastro nao tinha (nunca troca o que ja existe)
        update public.clientes
           set email = case when email = '' and v_email <> ''
                             and not exists (select 1 from public.clientes o
                                              where lower(o.email) = v_email and o.id <> v_cliente.id)
                            then v_email else email end,
               telefone = case when telefone = '' then v_telefone else telefone end
         where id = v_cliente.id
        returning * into v_cliente;
    end if;

    -- o que foi vendido, com o preco de tabela so para o historico
    if coalesce(btrim(p_combo), '') <> '' then
        select * into v_combo from public.combos where codigo = upper(btrim(p_combo)) and ativo;
        if not found then
            raise exception 'O combo % nao esta a venda.', upper(btrim(p_combo));
        end if;
        v_itens := v_itens || jsonb_build_object('tipo', 'combo', 'codigo', v_combo.codigo,
                                                 'nome', v_combo.nome, 'preco', v_combo.preco);
        v_catalogo := v_catalogo + v_combo.preco;
    end if;
    foreach v_codigo in array coalesce(p_produtos, '{}') loop
        v_codigo := upper(btrim(v_codigo));
        continue when v_codigo = '';
        select * into v_produto from public.produtos where codigo = v_codigo and ativo;
        if not found then
            raise exception 'O modulo % nao esta a venda.', v_codigo;
        end if;
        v_itens := v_itens || jsonb_build_object('tipo', 'produto', 'codigo', v_produto.codigo,
                                                 'nome', v_produto.nome, 'preco', v_produto.preco);
        v_catalogo := v_catalogo + v_produto.preco;
    end loop;
    if jsonb_array_length(v_itens) = 0 then
        raise exception 'Escolha ao menos um modulo ou combo.';
    end if;
    if p_total is not null and p_total < 0 then
        raise exception 'O valor recebido nao pode ser negativo.';
    end if;

    v_entrega := public.dumtech_entregar_produtos(
        v_cliente.id, p_produtos, p_combo, p_tipo, p_expira_em, p_max_computadores,
        format('venda %s %s', v_canal, left(btrim(coalesce(p_referencia, '')), 60)));

    insert into public.pedidos_site (cliente_id, nome, email, telefone, itens, total, origem,
                                     referencia, observacoes, atendido_em)
    values (v_cliente.id, v_cliente.nome, v_cliente.email, v_cliente.telefone, v_itens,
            coalesce(p_total, v_catalogo), v_canal,
            left(btrim(coalesce(p_referencia, '')), 60), '', now())
    returning id into v_pedido;

    return v_entrega || jsonb_build_object(
        'ok', true,
        'pedido', v_pedido,
        'cliente_id', v_cliente.id,
        'nome', v_cliente.nome,
        'email', v_cliente.email,
        'telefone', v_cliente.telefone,
        'total', coalesce(p_total, v_catalogo));
end;
$$;

-- ===================================================== 5. UM CADASTRO =======
-- O Hub chama depois de ativar: "esta chave, neste computador ativado, e da
-- pessoa que digitou este e-mail". A prova e a chave + o computador ativado.
-- Nunca devolve dado de ninguem - so se ligou ou nao.
create or replace function public.dumtech_vincular_conta(
    p_chave   text,
    p_maquina text,
    p_nome    text default '',
    p_email   text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_chave   text := public.dumtech_normalizar(p_chave, 32);
    v_maquina text := public.dumtech_normalizar(p_maquina, 64);
    v_nome    text := left(btrim(coalesce(p_nome, '')), 120);
    v_email   text := lower(left(btrim(coalesce(p_email, '')), 160));
    v_licenca public.licencas;
    v_dono    public.clientes;
    v_solto   public.clientes;
begin
    if not public.dumtech_dentro_do_limite('vincular_ip', public.dumtech_ip_do_pedido(), 30, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas');
    end if;
    if v_chave = '' or v_maquina = '' or not public.dumtech_email_valido(v_email) then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos');
    end if;

    select * into v_licenca from public.licencas where chave = v_chave;
    -- chave inexistente e computador nao ativado respondem IGUAL: nada de testador de chaves
    if not found or not exists (select 1 from public.ativacoes a
                                 where a.licenca_id = v_licenca.id and a.maquina = v_maquina) then
        return jsonb_build_object('ok', false, 'erro', 'maquina_nao_ativada');
    end if;

    select * into v_dono from public.clientes where id = v_licenca.cliente_id for update;
    if lower(v_dono.email) = v_email then
        return jsonb_build_object('ok', true, 'vinculado', true);
    end if;
    if v_dono.email <> '' then
        -- o cadastro comercial ja tem outro e-mail: ele manda
        return jsonb_build_object('ok', true, 'vinculado', false);
    end if;

    -- o e-mail digitado criou um cadastro solto (primeiro acesso do Hub)? junta
    select * into v_solto from public.clientes
     where lower(email) = v_email and id <> v_dono.id
       for update;
    if found then
        if exists (select 1 from public.licencas where cliente_id = v_solto.id) then
            return jsonb_build_object('ok', true, 'vinculado', false); -- e cliente de verdade: nao mistura
        end if;
        update public.pedidos_site  set cliente_id = v_dono.id where cliente_id = v_solto.id;
        update public.compra_tokens set cliente_id = v_dono.id where cliente_id = v_solto.id;
        delete from public.clientes where id = v_solto.id;
    end if;

    update public.clientes
       set email    = v_email,
           nome     = case when btrim(nome) = '' and v_nome <> '' then v_nome else nome end,
           telefone = case when telefone = '' then coalesce(v_solto.telefone, '') else telefone end
     where id = v_dono.id;

    return jsonb_build_object('ok', true, 'vinculado', true);
end;
$$;

-- ============================================= 6. AVISOS NO PEDIDO ==========
create or replace view public.pedidos_abertos with (security_invoker = true) as
select p.id            as pedido_id,
       p.criado_em,
       p.nome,
       p.email,
       p.telefone,
       p.total,
       p.origem,
       (select string_agg(item->>'nome', ' + ' order by item->>'nome')
          from jsonb_array_elements(p.itens) item) as kit,
       c.id            as cliente_id,
       (select l.chave from public.licencas l
         where l.cliente_id = c.id and l.status = 'ativa'
         order by l.criado_em limit 1) as chave_atual,
       -- modulos do pedido que o cliente JA TEM (cobrar de novo seria erro)
       coalesce((
           select array_agg(distinct pr.codigo order by pr.codigo)
             from public.licencas l
             join public.licenca_produtos lp on lp.licenca_id = l.id
             join public.produtos pr on pr.id = lp.produto_id
            where l.cliente_id = c.id
              and pr.codigo in (
                    select item->>'codigo' from jsonb_array_elements(p.itens) item
                     where item->>'tipo' = 'produto'
                    union
                    select p2.codigo
                      from jsonb_array_elements(p.itens) item
                      join public.combos cb on cb.codigo = item->>'codigo'
                      join public.combo_produtos cp on cp.combo_id = cb.id
                      join public.produtos p2 on p2.id = cp.produto_id
                     where item->>'tipo' = 'combo')
       ), '{}') as ja_tem,
       -- a licenca que vai receber: ativa, vencida, suspensa, cancelada (ou null = nova)
       (select public.dumtech_situacao_licenca(l.status, l.expira_em)
          from public.licencas l
         where l.cliente_id = c.id
         order by (l.status = 'ativa') desc, l.criado_em desc
         limit 1) as licenca_situacao,
       p.referencia
  from public.pedidos_site p
  left join public.clientes c on c.id = p.cliente_id
 where p.atendido_em is null
 order by p.criado_em;

-- ===================================================== 7. PERMISSOES ========
-- As funcoes do painel rodam com o papel de quem chama (authenticated) e, por
-- dentro, usam duas funcoes puras que so o service_role podia executar - aprovar
-- a primeira compra de alguem dava "permission denied for function
-- dumtech_normalizar" (13/09/2026). Elas so limpam texto e conferem formato de
-- e-mail: nao leem nem gravam nada. A anon continua sem acesso a elas.
grant execute on function public.dumtech_normalizar(text, integer) to authenticated;
grant execute on function public.dumtech_email_valido(text)        to authenticated;

revoke execute on function public.dumtech_entregar_produtos(uuid, text[], text, text, date, integer, text)
    from public, anon;
revoke execute on function public.dumtech_venda_manual(text, text, text, text[], text, text, text, numeric, text, date, integer, uuid)
    from public, anon;
revoke execute on function public.dumtech_vincular_conta(text, text, text, text) from public;

grant execute on function public.dumtech_entregar_produtos(uuid, text[], text, text, date, integer, text)
    to authenticated, service_role;
grant execute on function public.dumtech_venda_manual(text, text, text, text[], text, text, text, numeric, text, date, integer, uuid)
    to authenticated, service_role;
grant execute on function public.dumtech_vincular_conta(text, text, text, text) to anon, authenticated;

revoke execute on function public.dumtech_aprovar_pedido(uuid, integer, text, date) from public, anon;
grant  execute on function public.dumtech_aprovar_pedido(uuid, integer, text, date) to authenticated, service_role;

revoke all on table public.pedidos_abertos from anon;
grant select on public.pedidos_abertos to authenticated;

notify pgrst, 'reload schema';
