-- =============================================================================
-- Teste da migration 20260917140000: a versao publicada do Hub.
--
-- Roda dentro de uma transacao e desfaz tudo no fim: pode ser colado no SQL
-- Editor do Supabase, mesmo em producao.
-- =============================================================================

begin;

do $$
declare
    v_cliente uuid;
    v_chave   text;
    v_licenca uuid;
    v_maquina constant text := 'AAAA-BBBB-CCCC-DDDD';
    r         jsonb;
begin
    insert into public.clientes (nome, email) values ('ZZ Versao', 'zz.versao@teste.local')
    returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);
    select id into v_licenca from public.licencas where chave = v_chave;
    perform public.dumtech_ativar_licenca(v_chave, v_maquina, 'caixa');

    update public.hub_versoes
       set versao = '1.2.0', url = 'https://exemplo/baixar/', notas = 'Pagamentos protegidos'
     where id = 1;

    -- o Hub pergunta e diz em que versao esta
    r := public.dumtech_hub_versao(v_chave, v_maquina, '1.1.0');
    assert (r->>'ok')::boolean, 'consulta recusada: ' || r::text;
    assert r->>'versao' = '1.2.0', 'versao errada: ' || r::text;
    assert r->>'url' = 'https://exemplo/baixar/', 'url errada: ' || r::text;
    assert not (r->>'obrigatoria')::boolean, 'nao era obrigatoria: ' || r::text;
    assert (select versao from public.ativacoes
             where licenca_id = v_licenca and maquina = v_maquina) = '1.1.0',
        'a versao do computador tinha que ficar registrada';

    -- quem nao tem licenca recebe a MESMA resposta (nao serve de testador de chaves)
    r := public.dumtech_hub_versao('AAAA-AAAA-AAAA-AAAA', 'QUALQUER', '1.1.0');
    assert (r->>'ok')::boolean and r->>'versao' = '1.2.0', 'resposta diferente para quem nao e cliente: ' || r::text;
    assert (select count(*) from public.ativacoes where versao = '1.1.0') = 1,
        'chave inexistente nao pode gravar versao em ninguem';

    -- sem versao publicada, o Hub simplesmente nao avisa nada
    update public.hub_versoes set versao = '' where id = 1;
    r := public.dumtech_hub_versao(v_chave, v_maquina, '1.1.0');
    assert r->>'versao' = '', 'sem versao publicada tem que voltar vazio: ' || r::text;

    -- versao mal formada nao entra no banco
    update public.hub_versoes set versao = '1.3.0' where id = 1;
    r := public.dumtech_hub_versao(v_chave, v_maquina, '1.1.0'' or 1=1 --');
    assert (r->>'ok')::boolean, 'lixo na versao derrubou a consulta: ' || r::text;
    assert (select versao from public.ativacoes
             where licenca_id = v_licenca and maquina = v_maquina) = '1.1.0',
        'lixo nao pode sobrescrever a versao registrada';

    -- os campos que o atualizador usa
    update public.hub_versoes
       set versao = '1.3.0', sha256 = repeat('a', 64), tamanho = 29781768, automatica = true
     where id = 1;
    r := public.dumtech_hub_versao(v_chave, v_maquina, '1.2.1');
    assert r->>'sha256' = repeat('a', 64), 'sha256 nao voltou: ' || r::text;
    assert (r->>'automatica')::boolean, 'automatica nao voltou: ' || r::text;
    assert (r->>'tamanho')::bigint = 29781768, 'tamanho nao voltou: ' || r::text;

    -- desligar no painel e o freio: o Hub deixa de instalar sozinho
    update public.hub_versoes set automatica = false where id = 1;
    r := public.dumtech_hub_versao(v_chave, v_maquina, '1.2.1');
    assert not (r->>'automatica')::boolean, 'o freio do painel nao valeu: ' || r::text;
    update public.hub_versoes set automatica = true where id = 1;

    -- ---------------------------------------------------------------------
    -- a impressao digital da licenca (20260921120000): e ela que faz mudanca
    -- do painel chegar em minutos
    declare
        v_marca text;
        v_nova  text;
    begin
        r := public.dumtech_hub_versao(v_chave, v_maquina, '1.2.3');
        v_marca := r->>'licenca';
        assert length(v_marca) = 32, 'cliente ativado tinha que receber a impressao: ' || r::text;

        -- perguntar de novo (que grava a versao) nao pode mudar a impressao,
        -- senao o Hub reconferiria a licenca sem parar
        r := public.dumtech_hub_versao(v_chave, v_maquina, '1.2.4');
        assert r->>'licenca' = v_marca, 'a propria consulta mudou a impressao';

        -- quem nao e cliente, ou nao e ESTA maquina, recebe vazio
        r := public.dumtech_hub_versao('AAAA-AAAA-AAAA-AAAA', v_maquina, '1.2.3');
        assert r->>'licenca' = '', 'chave inventada recebeu impressao: ' || r::text;
        r := public.dumtech_hub_versao(v_chave, 'OUTRA-MAQUINA', '1.2.3');
        assert r->>'licenca' = '', 'maquina sem ativacao recebeu impressao: ' || r::text;

        -- mudar as vagas no painel muda a impressao
        update public.licencas set max_computadores = max_computadores + 1 where id = v_licenca;
        v_nova := public.dumtech_hub_versao(v_chave, v_maquina, '1.2.3')->>'licenca';
        assert v_nova <> v_marca, 'mudar a licenca no painel nao mudou a impressao';
        v_marca := v_nova;

        -- trocar a chave Pix (em outro computador da loja) tambem
        insert into public.pagamento_config (licenca_id, pix_chave, atualizado_em)
        values (v_licenca, 'loja@exemplo.com', now() + interval '1 minute')
        on conflict (licenca_id) do update set atualizado_em = excluded.atualizado_em;
        v_nova := public.dumtech_hub_versao(v_chave, v_maquina, '1.2.3')->>'licenca';
        assert v_nova <> v_marca, 'trocar o Pix nao mudou a impressao';

        -- soltar este computador no painel: a impressao some
        delete from public.ativacoes where licenca_id = v_licenca and maquina = v_maquina;
        r := public.dumtech_hub_versao(v_chave, v_maquina, '1.2.3');
        assert r->>'licenca' = '', 'computador solto continuou com impressao: ' || r::text;

        -- e o anon nao chama a funcao da impressao direto
        assert not has_function_privilege('anon', 'public.dumtech_licenca_marca(text, text)', 'execute'),
            'anon consegue chamar dumtech_licenca_marca direto';
    end;

    -- uma linha so, sempre
    begin
        insert into public.hub_versoes (id, versao) values (2, '9.9.9');
        assert false, 'a tabela aceitou uma segunda linha';
    exception when check_violation then
        null;   -- era o esperado
    end;

    raise notice 'versao_test: tudo certo';
end;
$$;

do $$
begin
    assert has_function_privilege('anon', 'public.dumtech_hub_versao(text, text, text, text)', 'execute'),
        'o Hub (chave anon) precisa perguntar a versao';
    assert not has_table_privilege('anon', 'public.hub_versoes', 'select'),
        'anon nao le a tabela direto - so pela funcao';
    assert has_table_privilege('authenticated', 'public.hub_versoes', 'update'),
        'o painel precisa publicar a versao nova';
end;
$$;

rollback;
