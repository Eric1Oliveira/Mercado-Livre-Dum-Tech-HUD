-- =============================================================================
-- A chave vai por e-mail sozinha quando a compra pelo site e paga.
--
-- O PROBLEMA
--   A chave so aparecia na pagina do pedido. Quem fechava a aba sem anotar
--   ficava sem ela ate o dono mandar pelo painel.
--
-- COMO FUNCIONA
--   A funcao `checkout`, depois de confirmar o pagamento (pelo aviso da
--   InfinitePay ou pela pagina do pedido), pede aqui os dados da chave. O
--   pedido fica RESERVADO para envio - dois caminhos chegando juntos nao
--   mandam dois e-mails. Mandou: marca como enviado. Falhou: a reserva e
--   solta e a proxima consulta da pagina tenta de novo. Reserva esquecida
--   (a funcao caiu no meio) vence em 5 minutos.
--
-- DE QUEBRA
--   `dumtech_dados_da_chave` listava so os modulos avulsos. Licenca vendida
--   como kit saia com "Modulos:" vazio no e-mail - agora entram os do kit.
-- =============================================================================

create or replace function public.dumtech_dados_da_chave(p_licenca_id uuid)
returns jsonb
language sql
stable
set search_path = ''
as $$
    select jsonb_build_object(
        'ok', true,
        'nome', c.nome,
        'email', c.email,
        'telefone', c.telefone,
        'chave', l.chave,
        'tipo', l.tipo,
        'expira_em', l.expira_em,
        'max_computadores', l.max_computadores,
        'modulos', coalesce((
            select jsonb_agg(p.nome order by p.nome)
              from public.produtos p
             where p.id in (
                   select lp.produto_id from public.licenca_produtos lp
                    where lp.licenca_id = l.id and lp.produto_id is not null
                   union
                   select cp.produto_id from public.licenca_produtos lp
                     join public.combo_produtos cp on cp.combo_id = lp.combo_id
                    where lp.licenca_id = l.id)), '[]'::jsonb))
      from public.licencas l
      join public.clientes c on c.id = l.cliente_id
     where l.id = p_licenca_id;
$$;

create or replace function public.dumtech_checkout_reservar_email(p_pedido uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v     public.pedidos_site;
    v_lic uuid;
    v_d   jsonb;
begin
    update public.pedidos_site
       set entrega = coalesce(entrega, '{}'::jsonb) || jsonb_build_object('email_reservado_em', now())
     where id = p_pedido
       and pagamento = 'pago'
       and atendido_em is not null
       and coalesce(entrega, '{}'::jsonb) ? 'licenca_id'
       and not (coalesce(entrega, '{}'::jsonb) ? 'email_enviado_em')
       and (not (coalesce(entrega, '{}'::jsonb) ? 'email_reservado_em')
            or (entrega->>'email_reservado_em')::timestamptz < now() - interval '5 minutes')
    returning * into v;
    if not found then
        return jsonb_build_object('ok', false);
    end if;

    v_lic := (v.entrega->>'licenca_id')::uuid;
    v_d := public.dumtech_dados_da_chave(v_lic);
    if v_d is null then
        return jsonb_build_object('ok', false);
    end if;
    -- o e-mail do PEDIDO vale: e para onde o cliente pediu que fosse
    return v_d || jsonb_build_object(
        'email', coalesce(nullif(btrim(v.email), ''), v_d->>'email'),
        'nome',  coalesce(nullif(btrim(v.nome), ''),  v_d->>'nome'));
end;
$$;

create or replace function public.dumtech_checkout_email_resultado(p_pedido uuid, p_enviado boolean)
returns void
language sql
security definer
set search_path = ''
as $$
    update public.pedidos_site
       set entrega = case
             when p_enviado then (entrega - 'email_reservado_em') || jsonb_build_object('email_enviado_em', now())
             else entrega - 'email_reservado_em'
           end
     where id = p_pedido;
$$;

revoke execute on function public.dumtech_checkout_reservar_email(uuid)           from public, anon, authenticated;
revoke execute on function public.dumtech_checkout_email_resultado(uuid, boolean) from public, anon, authenticated;
grant  execute on function public.dumtech_checkout_reservar_email(uuid)           to service_role;
grant  execute on function public.dumtech_checkout_email_resultado(uuid, boolean) to service_role;

notify pgrst, 'reload schema';
