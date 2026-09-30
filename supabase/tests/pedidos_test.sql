-- =============================================================================
-- Teste do ciclo comercial: catalogo -> kit montado no site -> aprovacao ->
-- produto liberado na licenca (que e o que o Hub do cliente vai enxergar).
--
-- Roda inteiro dentro de uma transacao e desfaz tudo no fim: pode ser colado no
-- SQL Editor do Supabase, mesmo em producao.
-- =============================================================================

begin;

-- ============================================================== 1. CATALOGO ==
do $$
declare
    v_catalogo jsonb;
    v_estoque  jsonb;
begin
    v_catalogo := public.dumtech_catalogo();
    assert (v_catalogo->>'ok')::boolean, 'o catalogo nao respondeu';
    assert jsonb_array_length(v_catalogo->'produtos') >= 7,
        'o catalogo publico deveria trazer os modulos a venda';

    select item into v_estoque
      from jsonb_array_elements(v_catalogo->'produtos') item
     where item->>'codigo' = 'ESTOQUE';
    assert v_estoque is not null, 'o Estoque sumiu do catalogo';
    assert (v_estoque->>'preco')::numeric > 0, 'o catalogo precisa trazer preco';
    assert v_estoque ? 'nome' and v_estoque ? 'descricao', 'faltou nome/descricao';

    -- produto fora de linha nao aparece na vitrine
    update public.produtos set ativo = false where codigo = 'AGENDA';
    assert not exists (
        select 1 from jsonb_array_elements(public.dumtech_catalogo()->'produtos') item
         where item->>'codigo' = 'AGENDA'), 'produto inativo apareceu na vitrine';
    update public.produtos set ativo = true where codigo = 'AGENDA';
    raise notice '1. catalogo publico ................ ok';
end;
$$;

-- ====================================================== 2. REGISTRAR PEDIDO ==
do $$
declare
    v_resposta jsonb;
    v_pedido   public.pedidos_site;
    v_cliente  uuid;
begin
    -- visitante novo: o pedido cria o cadastro
    v_resposta := public.dumtech_registrar_pedido(
        'ZZ Loja Nova', 'ZZ.Loja@Teste.Local', '(63) 90000-0000',
        array['ESTOQUE', 'VENDAS']);
    assert (v_resposta->>'ok')::boolean, format('pedido recusado: %s', v_resposta);

    select * into v_pedido from public.pedidos_site
     where id = (v_resposta->>'pedido')::uuid;
    assert v_pedido.total = 498.00,
        format('o total foi calculado errado: %s', v_pedido.total);
    assert v_pedido.cliente_id is not null, 'o pedido nasceu sem cliente';
    assert (select origem from public.clientes where id = v_pedido.cliente_id) = 'hub',
        'quem chega pelo site entra como cadastro do Hub';
    assert (select email from public.clientes where id = v_pedido.cliente_id)
           = 'zz.loja@teste.local', 'e-mail deveria ser guardado em minusculas';

    -- o MESMO e-mail nao vira segundo cliente
    v_cliente := v_pedido.cliente_id;
    v_resposta := public.dumtech_registrar_pedido(
        'Outro Nome', 'zz.loja@teste.local', '', array['AGENDA']);
    assert (select cliente_id from public.pedidos_site
             where id = (v_resposta->>'pedido')::uuid) = v_cliente,
        'o segundo pedido deveria cair no mesmo cliente';

    -- combo nao cobra duas vezes o produto que ja esta dentro dele
    v_resposta := public.dumtech_registrar_pedido(
        'ZZ Combo', 'zz.combo@teste.local', '', array['ESTOQUE', 'AGENDA'], 'GESTAO');
    assert (v_resposta->>'total')::numeric = 699.00 + 149.00,
        format('combo + avulso deu %s', v_resposta->>'total');

    -- entradas ruins
    assert public.dumtech_registrar_pedido('ZZ', 'zz@teste.local', '', '{}')->>'erro'
           = 'kit_vazio', 'aceitou pedido sem nada';
    assert public.dumtech_registrar_pedido('', 'zz@teste.local', '', array['ESTOQUE'])->>'erro'
           = 'dados_incompletos', 'aceitou pedido sem nome';
    assert public.dumtech_registrar_pedido('ZZ', 'nao-e-email', '', array['ESTOQUE'])->>'erro'
           = 'email_invalido', 'aceitou e-mail invalido';
    assert public.dumtech_registrar_pedido('ZZ', 'zz@teste.local', '', array['NAO_EXISTE'])->>'erro'
           = 'produto_invalido', 'aceitou produto que nao existe';
    raise notice '2. registrar pedido ................ ok';
end;
$$;

-- ================================= 3. APROVAR: CLIENTE QUE JA TEM LICENCA ====
do $$
declare
    v_cliente  uuid;
    v_chave    text;
    v_licenca  uuid;
    v_pedido   uuid;
    v_resposta jsonb;
    v_produtos jsonb;
begin
    -- cliente com licenca ativa de Estoque, ativada num computador
    insert into public.clientes (nome, email) values ('ZZ Ja Cliente', 'zz.ja@teste.local')
    returning id into v_cliente;
    select licenca_id, chave into v_licenca, v_chave
      from public.dumtech_emitir_licenca(v_cliente, array['ESTOQUE']);
    perform public.dumtech_ativar_licenca(v_chave, 'zz-pc-1');

    -- ele monta um kit no site com o Financeiro
    v_pedido := (public.dumtech_registrar_pedido(
        'ZZ Ja Cliente', 'zz.ja@teste.local', '', array['FINANCEIRO'])->>'pedido')::uuid;

    -- ... e a DumTech aprova
    v_resposta := public.dumtech_aprovar_pedido(v_pedido);
    assert (v_resposta->>'ok')::boolean, format('aprovacao falhou: %s', v_resposta);
    assert v_resposta->>'chave' = v_chave,
        'o produto novo tem de entrar na licenca QUE ELE JA TEM, sem trocar a chave';
    assert not (v_resposta->>'licenca_nova')::boolean, 'nao era para emitir licenca nova';

    -- e o Hub dele passa a ver os dois modulos
    v_produtos := public.dumtech_verificar_licenca(v_chave, 'zz-pc-1')->'produtos';
    assert v_produtos = '["ESTOQUE", "FINANCEIRO"]'::jsonb,
        format('o Hub veria: %s', v_produtos);

    assert (select atendido_em from public.pedidos_site where id = v_pedido) is not null,
        'o pedido deveria ficar marcado como atendido';
    assert not exists (select 1 from public.pedidos_abertos where pedido_id = v_pedido),
        'pedido atendido nao pode continuar na caixa de entrada';

    -- aprovar duas vezes nao pode
    begin
        perform public.dumtech_aprovar_pedido(v_pedido);
        raise exception 'aprovou o mesmo pedido duas vezes';
    exception when raise_exception then
        if position('ja foi atendido' in sqlerrm) = 0 then raise; end if;
    end;
    raise notice '3. aprovar (cliente com licenca) ... ok';
end;
$$;

-- ==================================== 4. APROVAR: CLIENTE SEM LICENCA =======
do $$
declare
    v_pedido   uuid;
    v_resposta jsonb;
    v_chave    text;
begin
    v_pedido := (public.dumtech_registrar_pedido(
        'ZZ Primeira Compra', 'zz.primeira@teste.local', '', '{}', 'GESTAO')->>'pedido')::uuid;

    v_resposta := public.dumtech_aprovar_pedido(v_pedido, 2);
    assert (v_resposta->>'ok')::boolean, format('aprovacao falhou: %s', v_resposta);
    assert (v_resposta->>'licenca_nova')::boolean, 'quem nao tinha licenca ganha uma';

    v_chave := v_resposta->>'chave';
    assert v_chave ~ '^[A-Z2-9]{4}(-[A-Z2-9]{4}){3}$',
        format('chave fora do formato: %s', v_chave);
    assert (select max_computadores from public.licencas where chave = v_chave) = 2,
        'o numero de computadores pedido na aprovacao nao foi respeitado';

    -- a chave nova ja ativa os quatro modulos do combo
    assert public.dumtech_ativar_licenca(v_chave, 'zz-pc-novo')->'produtos'
           = '["CLIENTES", "ESTOQUE", "FINANCEIRO", "VENDAS"]'::jsonb,
        'o combo comprado nao chegou inteiro na licenca nova';
    raise notice '4. aprovar (cliente novo) .......... ok';
end;
$$;

-- ================================================== 5. SEGURANCA (anon) =====
do $$
declare
    v_sobra text;
begin
    -- a anon registra pedido e le catalogo, mas NAO aprova nada
    assert has_function_privilege('anon', 'public.dumtech_catalogo()', 'execute'),
        'a anon precisa ler o catalogo';
    assert has_function_privilege(
        'anon', 'public.dumtech_registrar_pedido(text,text,text,text[],text,text,text,text)', 'execute'),
        'a anon precisa registrar o pedido';
    assert not has_function_privilege(
        'anon', 'public.dumtech_aprovar_pedido(uuid,integer,text,date)', 'execute'),
        'a chave publica NAO pode aprovar pedido - seria dar licenca de graca';

    select string_agg(t || ' (' || p || ')', ', ') into v_sobra
      from unnest(array['pedidos_site', 'pedidos_abertos']) t,
           unnest(array['select', 'insert', 'update', 'delete']) p
     where has_table_privilege('anon', 'public.' || t, p);
    assert v_sobra is null, 'a anon tem privilegio em: ' || coalesce(v_sobra, '');
    raise notice '5. permissoes ...................... ok';
end;
$$;

-- 5.1 na pratica, virando a chave anon
do $$
declare
    v_resposta jsonb;
begin
    begin
        execute 'set local role anon';
        perform public.dumtech_aprovar_pedido(gen_random_uuid());
        raise exception 'a chave anon aprovou um pedido!';
    exception when insufficient_privilege then null;
    end;

    set local role anon;
    v_resposta := public.dumtech_registrar_pedido(
        'ZZ Pela Anon', 'zz.anon.pedido@teste.local', '', array['AGENDA']);
    reset role;
    assert (v_resposta->>'ok')::boolean, format('a anon nao conseguiu pedir: %s', v_resposta);
    assert (v_resposta->>'total')::numeric = 149.00, 'o total veio do banco, nao do navegador';
    raise notice '5.1 chave anon ..................... ok';
end;
$$;

do $$
begin
    raise notice '';
    raise notice 'TUDO CERTO - nada foi gravado (rollback no fim do arquivo).';
end;
$$;

rollback;
