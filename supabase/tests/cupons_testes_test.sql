-- =============================================================================
-- Teste da migration 20260922120000: cupom, kit por ramo e teste gratis.
-- Roda numa transacao e desfaz tudo no fim.
-- =============================================================================

begin;

-- ------------------------------------------------------------------ cupons --
do $$
declare
    r        jsonb;
    v_pedido uuid;
begin
    insert into public.cupons (codigo, descricao, tipo, valor, primeira_compra)
    values ('PRIMEIRA10', '10% na primeira compra', 'percentual', 10, true);
    insert into public.cupons (codigo, tipo, valor, usos_max, minimo, parceiro)
    values ('PARCEIRO20', 'valor', 20, 1, 100, 'Joao Revenda');

    -- a previa da loja
    r := public.dumtech_conferir_cupom('primeira10', 'zz.cupom@teste.local', 199.60);
    assert (r->>'ok')::boolean, 'cupom valido recusado: ' || r::text;
    assert (r->>'desconto')::numeric = 19.96, 'desconto errado: ' || r::text;

    -- o pedido cobra com desconto e guarda de onde veio
    r := public.dumtech_registrar_pedido('ZZ Cupom', 'zz.cupom@teste.local', '',
                                         array['VENDAS', 'ESTOQUE'], null, 'site', '', 'PRIMEIRA10');
    assert (r->>'ok')::boolean, 'pedido com cupom recusado: ' || r::text;
    v_pedido := (r->>'pedido')::uuid;
    assert (r->>'total')::numeric = (r->>'subtotal')::numeric - round((r->>'subtotal')::numeric * 0.10, 2),
        'total com cupom errado: ' || r::text;
    assert (select cupom from public.pedidos_site where id = v_pedido) = 'PRIMEIRA10';
    assert (select subtotal from public.pedidos_site where id = v_pedido) = (r->>'subtotal')::numeric;

    -- pedido abandonado nao gasta o cupom; pago, gasta uma vez so
    assert (select usos from public.cupons where codigo = 'PRIMEIRA10') = 0, 'contou sem pagar';
    update public.pedidos_site set pagamento = 'pago' where id = v_pedido;
    update public.pedidos_site set pagamento = 'pago' where id = v_pedido;
    assert (select usos from public.cupons where codigo = 'PRIMEIRA10') = 1, 'uso nao contou certo';

    -- "so primeira compra": quem ja pagou nao usa de novo
    r := public.dumtech_conferir_cupom('PRIMEIRA10', 'zz.cupom@teste.local', 100);
    assert r->>'erro' = 'cupom_primeira', 'primeira compra nao foi respeitada: ' || r::text;

    -- minimo e limite de usos
    r := public.dumtech_conferir_cupom('PARCEIRO20', 'outro@teste.local', 50);
    assert r->>'erro' = 'cupom_minimo', 'minimo nao valeu: ' || r::text;
    update public.cupons set usos = 1 where codigo = 'PARCEIRO20';
    r := public.dumtech_conferir_cupom('PARCEIRO20', 'outro@teste.local', 150);
    assert r->>'erro' = 'cupom_esgotado', 'limite de usos nao valeu: ' || r::text;

    -- cupom que nao vale recusa o pedido (pagar mais que o combinado nao e opcao)
    r := public.dumtech_registrar_pedido('ZZ Cupom 2', 'zz.cupom2@teste.local', '',
                                         array['VENDAS'], null, 'site', '', 'NAOEXISTE');
    assert r->>'erro' = 'cupom_invalido', 'cupom inventado passou: ' || r::text;

    -- nunca abaixo de R$ 1
    insert into public.cupons (codigo, tipo, valor) values ('GRANDAO', 'valor', 500);
    r := public.dumtech_conferir_cupom('GRANDAO', '', 49.90);
    assert (r->>'total')::numeric = 1, 'desconto passou do total: ' || r::text;

    -- anon nao le a tabela de cupons nem chama a funcao interna
    assert not has_table_privilege('anon', 'public.cupons', 'select'), 'anon le cupons';
    assert not has_function_privilege('anon', 'public.dumtech_aplicar_cupom(text,text,numeric)', 'execute'),
        'anon chama a funcao interna do cupom';

    raise notice 'cupons ........................... ok';
end;
$$;

-- ------------------------------------------------------------ kit por ramo --
do $$
declare
    r jsonb;
begin
    update public.combos set ramo = '' where true;
    insert into public.combos (codigo, nome, preco, ramo) values ('ZZRAMO', 'Kit ZZ', 10, 'Oficina ou assistencia')
    on conflict (codigo) do update set ramo = excluded.ramo, ativo = true;
    r := public.dumtech_catalogo();
    assert exists (select 1 from jsonb_array_elements(r->'combos') c
                    where c->>'codigo' = 'ZZRAMO' and c->>'ramo' = 'Oficina ou assistencia'),
        'o catalogo nao levou o ramo: ' || (r->'combos')::text;
    raise notice 'kit por ramo ..................... ok';
end;
$$;

-- ------------------------------------------------------------ teste gratis --
do $$
declare
    v_cliente uuid;
    v_chave   text;
    v_licenca uuid;
    v_maquina constant text := 'AAAA-BBBB-CCCC-TTTT';
    r         jsonb;
begin
    insert into public.clientes (nome, email) values ('ZZ Teste', 'zz.teste@teste.local')
    returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);
    select id into v_licenca from public.licencas where chave = v_chave;
    perform public.dumtech_ativar_licenca(v_chave, v_maquina, 'caixa');

    -- quem nao tem a licenca ativada nesta maquina nao testa nada
    r := public.dumtech_iniciar_teste(v_chave, 'OUTRA-MAQUINA', 'AGENDA');
    assert r->>'erro' = 'licenca_invalida', 'maquina estranha comecou teste: ' || r::text;

    -- modulo que ja e dele nao vira teste
    r := public.dumtech_iniciar_teste(v_chave, v_maquina, 'VENDAS');
    assert r->>'erro' = 'ja_tem', 'testou o que ja tinha: ' || r::text;

    -- comeca: 7 dias, e aparece na licenca como teste (nao como compra)
    r := public.dumtech_iniciar_teste(v_chave, v_maquina, 'agenda');
    assert (r->>'ok')::boolean, 'teste recusado: ' || r::text;
    assert (r->>'termina_em')::timestamptz between now() + interval '6 days 23 hours'
                                               and now() + interval '7 days 1 minute', 'prazo errado';
    r := public.dumtech_resposta_licenca(v_licenca);
    assert r->'testes' ? 'AGENDA', 'teste fora da licenca: ' || r::text;
    assert not (r->'produtos') ? 'AGENDA', 'teste virou compra: ' || r::text;

    -- pedir de novo durante o teste nao estica nada
    r := public.dumtech_iniciar_teste(v_chave, v_maquina, 'AGENDA');
    assert (r->>'ok')::boolean, 'segundo pedido recusado durante o teste';
    assert (select count(*) from public.licenca_testes where licenca_id = v_licenca) = 1;

    -- acabou: nao da para testar o mesmo modulo outra vez
    update public.licenca_testes set termina_em = now() - interval '1 minute' where licenca_id = v_licenca;
    r := public.dumtech_iniciar_teste(v_chave, v_maquina, 'AGENDA');
    assert r->>'erro' = 'teste_usado', 'testou duas vezes: ' || r::text;

    -- comprou durante/depois do teste: some dos testes, vira produto
    perform public.dumtech_liberar_produtos(v_licenca, array['AGENDA']);
    r := public.dumtech_resposta_licenca(v_licenca);
    assert not (r->'testes') ? 'AGENDA', 'modulo comprado continuou como teste: ' || r::text;
    assert (r->'produtos') ? 'AGENDA', 'modulo comprado nao entrou: ' || r::text;

    assert not has_table_privilege('anon', 'public.licenca_testes', 'select'), 'anon le os testes';
    raise notice 'teste gratis ..................... ok';
end;
$$;

rollback;
