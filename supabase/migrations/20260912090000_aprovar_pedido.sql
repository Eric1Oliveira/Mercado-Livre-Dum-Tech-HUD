-- =============================================================================
-- 20260912090000 - aprovar um pedido do site (o que fecha o ciclo)
--
--   dumtech_aprovar_pedido(pedido_id)  ->  libera os produtos na licenca do
--   cliente e devolve a chave. Depois disso o Hub daquele cliente ve os modulos
--   novos na primeira verificacao.
--
-- POR QUE ISSO NAO E AUTOMATICO: liberar licenca a partir de um clique no site
-- seria liberar licenca a partir da chave publica - qualquer pessoa se daria os
-- sete modulos. A aprovacao mora do lado de ca, com o service_role, e e o unico
-- lugar onde um pedido vira produto liberado.
--
-- Quando existir checkout automatico, quem chama esta funcao passa a ser o
-- webhook do gateway (confirmado o pagamento), sem mudar mais nada.
-- =============================================================================

create or replace function public.dumtech_aprovar_pedido(
    p_pedido_id        uuid,
    p_max_computadores integer default 1,
    p_tipo             text    default 'vitalicia',
    p_expira_em        date    default null
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
    v_pedido    public.pedidos_site;
    v_licenca   public.licencas;
    v_licenca_id uuid;
    v_chave     text;
    v_produtos  text[];
    v_combo     text;
    v_liberados integer;
    -- guardado no instante da decisao: `found` e reescrito por TODA instrucao
    -- seguinte (o select da emissao, o count, o update), entao perguntar por
    -- ele no fim da funcao responderia outra coisa
    v_nova      boolean;
begin
    select * into v_pedido from public.pedidos_site where id = p_pedido_id;
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

    -- o que foi comprado, separado como as funcoes de licenca esperam
    select coalesce(array_agg(item->>'codigo')
                    filter (where item->>'tipo' = 'produto'), '{}'),
           max(item->>'codigo') filter (where item->>'tipo' = 'combo')
      into v_produtos, v_combo
      from jsonb_array_elements(v_pedido.itens) item;

    -- cliente que ja tem licenca ativa recebe os produtos NELA: e assim que o
    -- Hub dele ve o modulo novo aparecer sem trocar de chave
    select * into v_licenca
      from public.licencas
     where cliente_id = v_pedido.cliente_id and status = 'ativa'
     order by criado_em
     limit 1;
    v_nova := not found;

    if not v_nova then
        v_licenca_id := v_licenca.id;
        v_chave := v_licenca.chave;
        v_liberados := public.dumtech_liberar_produtos(v_licenca_id, v_produtos, v_combo);
    else
        select e.licenca_id, e.chave into v_licenca_id, v_chave
          from public.dumtech_emitir_licenca(
                p_cliente_id       => v_pedido.cliente_id,
                p_produtos         => v_produtos,
                p_combo            => v_combo,
                p_tipo             => p_tipo,
                p_expira_em        => p_expira_em,
                p_max_computadores => p_max_computadores,
                p_observacoes      => format('pedido do site %s', p_pedido_id)) e;
        select count(*) into v_liberados
          from public.licenca_produtos where licenca_id = v_licenca_id;
    end if;

    update public.pedidos_site set atendido_em = now() where id = p_pedido_id;

    return jsonb_build_object(
        'ok', true,
        'chave', v_chave,
        'licenca_id', v_licenca_id,
        'produtos_liberados', v_liberados,
        'licenca_nova', v_nova,
        'cliente', (select nome from public.clientes where id = v_pedido.cliente_id),
        'email', v_pedido.email,
        'total', v_pedido.total);
end;
$$;

-- ------------------------------------------------------ pedidos em aberto ----
-- A caixa de entrada comercial: o que chegou e ainda nao foi atendido.
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
         order by l.criado_em limit 1) as chave_atual
  from public.pedidos_site p
  left join public.clientes c on c.id = p.cliente_id
 where p.atendido_em is null
 order by p.criado_em;

-- ================================================== RLS E PERMISSOES ========
revoke all on table public.pedidos_abertos from anon, authenticated;

revoke execute on function public.dumtech_aprovar_pedido(uuid, integer, text, date)
    from public, anon, authenticated;
grant execute on function public.dumtech_aprovar_pedido(uuid, integer, text, date)
    to service_role;

notify pgrst, 'reload schema';
