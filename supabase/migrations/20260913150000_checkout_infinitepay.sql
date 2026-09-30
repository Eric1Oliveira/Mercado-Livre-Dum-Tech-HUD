-- =============================================================================
-- 20260913150000 - checkout direto (InfinitePay)
--
-- O CAMINHO DE UMA COMPRA NA LOJA
--   1. o site grava o kit (dumtech_registrar_pedido, o total sai do banco)
--   2. a Edge Function `checkout` le o pedido, cria o link na InfinitePay com os
--      itens e precos DO BANCO e guarda so o HASH do segredo do comprador
--   3. o comprador paga (Pix ou cartao) e volta para /pedido/
--   4. a InfinitePay avisa a funcao (webhook). O aviso nao e assinado: a funcao
--      PERGUNTA de novo a InfinitePay (payment_check) e so entao confirma aqui,
--      com o valor que a InfinitePay disse ter cobrado
--   5. dumtech_checkout_confirmar entrega os modulos na licenca do cliente (a
--      mesma regra da aprovacao do painel) e o pedido sai da caixa de entrada
--
-- Tudo aqui so executa com service_role (a Edge Function). Nem o site nem o
-- painel chamam estas funcoes.
--
-- DEPENDE DE 20260913090000_vendas_e_identidade.sql (dumtech_entregar_produtos).
-- =============================================================================

-- ======================================================= 1. COLUNAS =========
alter table public.pedidos_site
    add column if not exists pagamento           text not null default '',
    add column if not exists checkout_segredo    text,
    add column if not exists checkout_url        text not null default '',
    add column if not exists checkout_criado_em  timestamptz,
    add column if not exists pago_em             timestamptz,
    add column if not exists pago_valor          numeric(12, 2),
    add column if not exists pagamento_metodo    text not null default '',
    add column if not exists pagamento_transacao text,
    add column if not exists pagamento_fatura    text not null default '',
    add column if not exists pagamento_recibo    text not null default '',
    add column if not exists entrega             jsonb;

alter table public.pedidos_site drop constraint if exists pedidos_site_pagamento_check;
alter table public.pedidos_site add constraint pedidos_site_pagamento_check
    check (pagamento in ('', 'aguardando', 'pago'));

-- uma transacao paga UM pedido: o mesmo comprovante nao libera dois kits
create unique index if not exists idx_pedidos_site_transacao
    on public.pedidos_site (pagamento_transacao) where pagamento_transacao is not null;

comment on column public.pedidos_site.pagamento is
    ''''' = sem checkout (WhatsApp, Mercado Livre, manual); aguardando = link criado; pago = confirmado na InfinitePay.';
comment on column public.pedidos_site.checkout_segredo is
    'SHA-256 (hex) do segredo que so o navegador do comprador tem. Abre a pagina do pedido.';
comment on column public.pedidos_site.entrega is
    'O que o checkout entregou: {licenca_id, licenca_nova, reativada} ou {erro} quando a entrega falhou.';

-- ===================================================== 2. PREPARAR ==========
-- O pedido pode virar link? Devolve o que vai para a InfinitePay.
create or replace function public.dumtech_checkout_preparar(p_pedido uuid)
returns jsonb
language plpgsql
stable
set search_path = ''
as $$
declare
    v public.pedidos_site;
begin
    select * into v from public.pedidos_site where id = p_pedido;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'pedido_nao_existe');
    end if;
    if v.origem not in ('site', 'hub') or v.total <= 0 then
        return jsonb_build_object('ok', false, 'erro', 'pedido_invalido');
    end if;
    if v.atendido_em is not null or v.pagamento = 'pago' then
        return jsonb_build_object('ok', false, 'erro', 'pedido_encerrado');
    end if;
    -- o link sai uma vez: quem so conhece o numero do pedido nao troca o segredo
    if v.checkout_segredo is not null then
        return jsonb_build_object('ok', false, 'erro', 'checkout_ja_criado');
    end if;
    if v.criado_em < now() - interval '2 hours' then
        return jsonb_build_object('ok', false, 'erro', 'pedido_expirado');
    end if;

    return jsonb_build_object(
        'ok', true,
        'pedido', v.id,
        'nome', v.nome,
        'email', v.email,
        'telefone', v.telefone,
        'itens', v.itens,
        'total', v.total,
        'total_centavos', round(v.total * 100)::integer);
end;
$$;

-- ==================================================== 3. REGISTRAR ==========
create or replace function public.dumtech_checkout_registrar(
    p_pedido       uuid,
    p_segredo_hash text,
    p_url          text
)
returns jsonb
language plpgsql
set search_path = ''
as $$
begin
    if coalesce(p_segredo_hash, '') !~ '^[0-9a-f]{64}$' or coalesce(p_url, '') !~ '^https://' then
        return jsonb_build_object('ok', false, 'erro', 'dados_invalidos');
    end if;

    update public.pedidos_site
       set checkout_segredo   = p_segredo_hash,
           checkout_url       = left(p_url, 500),
           checkout_criado_em = now(),
           pagamento          = 'aguardando'
     where id = p_pedido
       and checkout_segredo is null
       and atendido_em is null
       and pagamento = '';
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'checkout_ja_criado');
    end if;
    return jsonb_build_object('ok', true);
end;
$$;

-- ==================================================== 4. CONFIRMAR ==========
-- Chamada DEPOIS que a InfinitePay confirmou o pagamento (payment_check).
-- Idempotente: webhook repetido, a pagina do pedido e o webhook ao mesmo tempo -
-- a trava na linha faz so o primeiro entregar.
create or replace function public.dumtech_checkout_confirmar(
    p_pedido    uuid,
    p_centavos  integer,
    p_transacao text,
    p_fatura    text default '',
    p_metodo    text default '',
    p_recibo    text default ''
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
    v          public.pedidos_site;
    v_produtos text[];
    v_combo    text;
    v_entrega  jsonb;
    v_transacao text := left(btrim(coalesce(p_transacao, '')), 100);
begin
    select * into v from public.pedidos_site where id = p_pedido for update;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'pedido_nao_existe');
    end if;
    if v.pagamento = 'pago' then
        return jsonb_build_object('ok', true, 'ja_estava_pago', true,
                                  'entregue', v.atendido_em is not null);
    end if;
    -- pedido que nunca abriu checkout (WhatsApp, venda manual) nao se paga por aqui
    if v.pagamento <> 'aguardando' then
        return jsonb_build_object('ok', false, 'erro', 'sem_checkout');
    end if;
    if v_transacao = '' then
        return jsonb_build_object('ok', false, 'erro', 'transacao_invalida');
    end if;
    if p_centavos is null or p_centavos < round(v.total * 100) then
        return jsonb_build_object('ok', false, 'erro', 'valor_menor');
    end if;
    if exists (select 1 from public.pedidos_site
                where pagamento_transacao = v_transacao and id <> p_pedido) then
        return jsonb_build_object('ok', false, 'erro', 'transacao_ja_usada');
    end if;

    -- 1. o pagamento fica registrado aconteca o que acontecer com a entrega
    update public.pedidos_site
       set pagamento           = 'pago',
           pago_em             = now(),
           pago_valor          = p_centavos / 100.0,
           pagamento_metodo    = left(btrim(coalesce(p_metodo, '')), 20),
           pagamento_transacao = v_transacao,
           pagamento_fatura    = left(btrim(coalesce(p_fatura, '')), 100),
           pagamento_recibo    = case when coalesce(p_recibo, '') ~ '^https://'
                                      then left(p_recibo, 500) else '' end
     where id = p_pedido;

    -- 2. a entrega. Se falhar (modulo que saiu de linha, cadastro sem cliente),
    --    o pedido pago continua na caixa de entrada do painel com o erro
    if v.atendido_em is null then
        begin
            select coalesce(array_agg(item->>'codigo') filter (where item->>'tipo' = 'produto'), '{}'),
                   max(item->>'codigo') filter (where item->>'tipo' = 'combo')
              into v_produtos, v_combo
              from jsonb_array_elements(v.itens) item;

            if v.cliente_id is null then
                raise exception 'Pedido sem cliente ligado.';
            end if;

            v_entrega := public.dumtech_entregar_produtos(
                v.cliente_id, v_produtos, v_combo, null, null, 1,
                format('checkout InfinitePay %s', p_pedido));

            update public.pedidos_site
               set atendido_em = now(),
                   entrega = jsonb_build_object(
                       'licenca_id',   v_entrega->'licenca_id',
                       'licenca_nova', v_entrega->'licenca_nova',
                       'reativada',    v_entrega->'reativada')
             where id = p_pedido;
        exception when others then
            update public.pedidos_site
               set entrega = jsonb_build_object('erro', left(sqlerrm, 300))
             where id = p_pedido;
            return jsonb_build_object('ok', true, 'entregue', false, 'erro_entrega', left(sqlerrm, 300));
        end;
    end if;

    return jsonb_build_object('ok', true, 'entregue', true);
end;
$$;

-- ===================================================== 5. SITUACAO ==========
-- O que a pagina /pedido/ mostra. So com o segredo do comprador.
-- A CHAVE so aparece quando nasceu nesta compra: quem digitou o e-mail de um
-- cliente antigo nao ve a chave dele (os modulos entram la, e ele ja tem a chave).
create or replace function public.dumtech_checkout_situacao(
    p_pedido       uuid,
    p_segredo_hash text
)
returns jsonb
language plpgsql
stable
set search_path = ''
as $$
declare
    v         public.pedidos_site;
    v_licenca public.licencas;
    v_nova    boolean;
    v_base    jsonb;
begin
    select * into v from public.pedidos_site where id = p_pedido;
    if not found or v.checkout_segredo is null
       or v.checkout_segredo <> coalesce(p_segredo_hash, '') then
        return jsonb_build_object('ok', false, 'erro', 'nao_encontrado');
    end if;

    v_base := jsonb_build_object(
        'ok', true,
        'pagamento', v.pagamento,
        'nome', v.nome,
        'email', v.email,
        'total', v.total,
        'itens', (select coalesce(jsonb_agg(item->>'nome'), '[]'::jsonb)
                    from jsonb_array_elements(v.itens) item),
        'metodo', v.pagamento_metodo,
        'recibo', v.pagamento_recibo,
        'checkout_url', case when v.pagamento = 'aguardando' then v.checkout_url else '' end,
        'transacao', coalesce(v.pagamento_transacao, ''),
        'fatura', v.pagamento_fatura);

    if v.pagamento <> 'pago' or v.atendido_em is null then
        return v_base || jsonb_build_object('entregue', false);
    end if;

    v_nova := coalesce((v.entrega->>'licenca_nova')::boolean, false);
    if v.entrega ? 'licenca_id' then
        select * into v_licenca from public.licencas where id = (v.entrega->>'licenca_id')::uuid;
    else
        -- atendido a mao pelo painel: a licenca do cliente
        select * into v_licenca from public.licencas
         where cliente_id = v.cliente_id
         order by (status = 'ativa') desc, criado_em desc limit 1;
    end if;

    return v_base || jsonb_build_object(
        'entregue', true,
        'licenca_nova', v_nova,
        'chave', case when v_nova then v_licenca.chave end,
        'final_chave', right(coalesce(v_licenca.chave, ''), 4),
        'max_computadores', v_licenca.max_computadores);
end;
$$;

-- ============================================= 6. AVISOS NO PEDIDO ==========
-- A mesma vista de 20260913090000 com o pagamento no fim: o painel separa
-- "desistiu no pagamento" de "pagou e a entrega falhou".
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
       (select public.dumtech_situacao_licenca(l.status, l.expira_em)
          from public.licencas l
         where l.cliente_id = c.id
         order by (l.status = 'ativa') desc, l.criado_em desc
         limit 1) as licenca_situacao,
       p.referencia,
       p.pagamento,
       p.pago_em,
       p.pagamento_metodo,
       p.entrega->>'erro' as entrega_erro
  from public.pedidos_site p
  left join public.clientes c on c.id = p.cliente_id
 where p.atendido_em is null
 order by p.criado_em;

-- ===================================================== 7. PERMISSOES ========
revoke execute on function public.dumtech_checkout_preparar(uuid)                              from public, anon, authenticated;
revoke execute on function public.dumtech_checkout_registrar(uuid, text, text)                 from public, anon, authenticated;
revoke execute on function public.dumtech_checkout_confirmar(uuid, integer, text, text, text, text) from public, anon, authenticated;
revoke execute on function public.dumtech_checkout_situacao(uuid, text)                        from public, anon, authenticated;

grant execute on function public.dumtech_checkout_preparar(uuid)                              to service_role;
grant execute on function public.dumtech_checkout_registrar(uuid, text, text)                 to service_role;
grant execute on function public.dumtech_checkout_confirmar(uuid, integer, text, text, text, text) to service_role;
grant execute on function public.dumtech_checkout_situacao(uuid, text)                        to service_role;

revoke all on table public.pedidos_abertos from anon;
grant select on public.pedidos_abertos to authenticated;

notify pgrst, 'reload schema';
