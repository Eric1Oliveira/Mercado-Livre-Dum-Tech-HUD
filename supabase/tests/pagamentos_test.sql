-- =============================================================================
-- Teste da migration 20260916120000: pagamentos protegidos por codigo.
--
-- Roda dentro de uma transacao e desfaz tudo no fim: pode ser colado no SQL
-- Editor do Supabase, mesmo em producao.
-- =============================================================================

begin;

do $$
declare
    v_cliente   uuid;
    v_chave     text;
    v_licenca   uuid;
    v_maquina   constant text := 'AAAA-BBBB-CCCC-DDDD';
    v_pc        constant text := '0123456789abcdef0123456789abcdef';
    v_outro_pc  constant text := 'fedcba9876543210fedcba9876543210';
    r           jsonb;
    v_codigo    text;
    v_sessao    text;
begin
    insert into public.clientes (nome, email) values ('ZZ Pagamentos', 'ZZ.Pag@Teste.local')
    returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);
    select id into v_licenca from public.licencas where chave = v_chave;
    perform public.dumtech_ativar_licenca(v_chave, v_maquina, 'caixa');

    -- ------------------------------------------------ quem nao e da licenca ---
    r := public.dumtech_pagamentos_pedir_codigo(v_chave, 'ZZZZ-ZZZZ-ZZZZ-ZZZZ', v_pc);
    assert r->>'erro' = 'nao_autorizado', 'computador nao ativado pediu codigo: ' || r::text;
    r := public.dumtech_pagamentos_pedir_codigo('AAAA-AAAA-AAAA-AAAA', v_maquina, v_pc);
    assert r->>'erro' = 'nao_autorizado', 'chave inexistente respondeu diferente: ' || r::text;
    r := public.dumtech_pagamentos_pedir_codigo(v_chave, v_maquina, 'nao-e-hex');
    assert r->>'erro' = 'nao_autorizado', 'computador mal formado passou: ' || r::text;

    -- ---------------------------------------------------------- o codigo ---
    r := public.dumtech_pagamentos_pedir_codigo(v_chave, v_maquina, v_pc);
    assert (r->>'ok')::boolean, 'pedido valido recusado: ' || r::text;
    assert r->>'email' = 'zz.pag@teste.local', 'o e-mail tem que ser o da licenca: ' || r::text;
    v_codigo := r->>'codigo';
    assert v_codigo ~ '^[0-9]{6}$', 'codigo fora do formato: ' || v_codigo;
    assert not exists (select 1 from public.pagamento_codigos where codigo_hash = v_codigo),
        'o codigo nao pode ser guardado em texto';

    -- um pedido novo mata o anterior
    r := public.dumtech_pagamentos_pedir_codigo(v_chave, v_maquina, v_pc);
    r := public.dumtech_pagamentos_entrar(v_chave, v_maquina, v_pc, v_codigo);
    assert r->>'erro' = 'codigo_invalido', 'o codigo antigo continuou valendo: ' || r::text;

    -- 5 erros queimam o codigo
    v_codigo := (public.dumtech_pagamentos_pedir_codigo(v_chave, v_maquina, v_pc))->>'codigo';
    for i in 1..4 loop
        r := public.dumtech_pagamentos_entrar(v_chave, v_maquina, v_pc,
                 lpad(((v_codigo::int + i) % 1000000)::text, 6, '0'));
        assert r->>'erro' = 'codigo_invalido', 'erro ' || i || ': ' || r::text;
    end loop;
    r := public.dumtech_pagamentos_entrar(v_chave, v_maquina, v_pc,
             lpad(((v_codigo::int + 5) % 1000000)::text, 6, '0'));
    assert r->>'erro' = 'codigo_bloqueado', 'quinto erro nao bloqueou: ' || r::text;
    r := public.dumtech_pagamentos_entrar(v_chave, v_maquina, v_pc, v_codigo);
    assert r->>'erro' = 'codigo_invalido', 'codigo bloqueado ainda abriu: ' || r::text;

    -- codigo vencido nao vale
    v_codigo := (public.dumtech_pagamentos_pedir_codigo(v_chave, v_maquina, v_pc))->>'codigo';
    update public.pagamento_codigos set expira_em = now() - interval '1 second'
     where licenca_id = v_licenca and usado_em is null;
    r := public.dumtech_pagamentos_entrar(v_chave, v_maquina, v_pc, v_codigo);
    assert r->>'erro' = 'codigo_invalido', 'codigo vencido abriu: ' || r::text;

    -- outro computador nem chega a tentar o codigo: a ativacao esta presa ao
    -- primeiro que assinou (achado do pentest de 17/09/2026)
    delete from public.limites_de_taxa where acao like 'pag_%';
    v_codigo := (public.dumtech_pagamentos_pedir_codigo(v_chave, v_maquina, v_pc))->>'codigo';
    r := public.dumtech_pagamentos_entrar(v_chave, v_maquina, v_outro_pc, v_codigo);
    assert r->>'erro' = 'nao_autorizado', 'outro computador entrou: ' || r::text;
    r := public.dumtech_pagamentos_pedir_codigo(v_chave, v_maquina, v_outro_pc);
    assert r->>'erro' = 'nao_autorizado', 'outro computador pediu codigo: ' || r::text;

    -- codigo certo: abre a sessao
    r := public.dumtech_pagamentos_entrar(v_chave, v_maquina, v_pc, v_codigo);
    assert (r->>'ok')::boolean, 'codigo certo recusado: ' || r::text;
    v_sessao := r->>'sessao';
    assert length(v_sessao) = 64, 'sessao curta demais';
    assert r->'reservas' is null, 'nao existe mais codigo de reserva: ' || r::text;
    assert not exists (select 1 from public.pagamento_sessoes where sessao_hash = v_sessao),
        'a sessao nao pode ser guardada em texto';

    -- o mesmo codigo nao entra duas vezes
    r := public.dumtech_pagamentos_entrar(v_chave, v_maquina, v_pc, v_codigo);
    assert r->>'erro' = 'codigo_invalido', 'codigo usado entrou de novo: ' || r::text;

    -- ------------------------------------------------------------ salvar ---
    r := public.dumtech_pagamentos_salvar(v_chave, v_maquina, v_pc, 'sessao-falsa', 'golpe@banco.com');
    assert r->>'erro' = 'sessao_vencida', 'sessao falsa salvou: ' || r::text;
    r := public.dumtech_pagamentos_salvar(v_chave, v_maquina, v_outro_pc, v_sessao, 'golpe@banco.com');
    assert r->>'erro' = 'nao_autorizado', 'sessao de outro computador salvou: ' || r::text;
    r := public.dumtech_pagamentos_salvar(v_chave, v_maquina, v_pc, v_sessao, 'x'' or 1=1 --');
    assert r->>'erro' = 'pix_invalida', 'lixo passou como chave Pix: ' || r::text;

    r := public.dumtech_pagamentos_salvar(v_chave, v_maquina, v_pc, v_sessao, 'loja@banco.com');
    assert (r->>'ok')::boolean and (r->>'mudou')::boolean, 'salvar valido falhou: ' || r::text;
    assert r->>'email' = 'zz.pag@teste.local', 'aviso de troca tem que ir para o e-mail da licenca';
    r := public.dumtech_pagamentos_atual(v_chave, v_maquina, v_pc);
    assert r->>'pix_chave' = 'loja@banco.com', 'atual nao devolveu a chave salva: ' || r::text;
    r := public.dumtech_pagamentos_atual(v_chave, v_maquina, v_outro_pc);
    assert r->>'erro' = 'nao_autorizado', 'outro computador leu a chave Pix: ' || r::text;
    assert (select count(*) from public.pagamento_historico where licenca_id = v_licenca) = 1,
        'a troca tem que ficar no historico';

    r := public.dumtech_pagamentos_salvar(v_chave, v_maquina, v_pc, v_sessao, 'loja@banco.com');
    assert not (r->>'mudou')::boolean, 'salvar a mesma chave nao e mudanca';

    -- sessao vencida nao salva
    update public.pagamento_sessoes set expira_em = now() - interval '1 second' where licenca_id = v_licenca;
    r := public.dumtech_pagamentos_salvar(v_chave, v_maquina, v_pc, v_sessao, 'golpe@banco.com');
    assert r->>'erro' = 'sessao_vencida', 'sessao vencida salvou: ' || r::text;

    -- codigo que nao e de 6 digitos nao abre nada (nao ha mais reserva)
    r := public.dumtech_pagamentos_entrar(v_chave, v_maquina, v_pc, 'ABCDE-FGHJK');
    assert r->>'erro' = 'codigo_invalido', 'texto estranho abriu: ' || r::text;

    -- licenca suspensa: nada funciona
    update public.licencas set status = 'suspensa' where id = v_licenca;
    r := public.dumtech_pagamentos_atual(v_chave, v_maquina, v_pc);
    assert r->>'erro' = 'nao_autorizado', 'licenca suspensa leu a chave: ' || r::text;
    update public.licencas set status = 'ativa' where id = v_licenca;

    -- sem e-mail no cadastro: diz o que fazer
    update public.clientes set email = '' where id = v_cliente;
    delete from public.limites_de_taxa where acao like 'pag_%';
    r := public.dumtech_pagamentos_pedir_codigo(v_chave, v_maquina, v_pc);
    assert r->>'erro' = 'sem_email', 'sem e-mail tem que avisar: ' || r::text;

    -- limite por licenca: 5 codigos por hora
    update public.clientes set email = 'zz.pag@teste.local' where id = v_cliente;
    delete from public.limites_de_taxa where acao like 'pag_%';
    for i in 1..5 loop
        r := public.dumtech_pagamentos_pedir_codigo(v_chave, v_maquina, v_pc);
        assert (r->>'ok')::boolean, 'pedido ' || i || ' recusado: ' || r::text;
    end loop;
    r := public.dumtech_pagamentos_pedir_codigo(v_chave, v_maquina, v_pc);
    assert r->>'erro' = 'muitas_tentativas', 'sexto codigo na hora passou: ' || r::text;

    raise notice 'pagamentos_test: tudo certo';
end;
$$;

-- ------------------------------------------------ o anon nao alcanca nada ---
do $$
begin
    assert not has_function_privilege('anon', 'public.dumtech_pagamentos_pedir_codigo(text, text, text, text)', 'execute'),
        'anon pode pedir codigo direto (tem que passar pela Edge Function)';
    assert not has_function_privilege('anon', 'public.dumtech_pagamentos_entrar(text, text, text, text, text)', 'execute'),
        'anon pode entrar direto';
    assert not has_function_privilege('authenticated', 'public.dumtech_pagamentos_salvar(text, text, text, text, text)', 'execute'),
        'authenticated pode salvar direto';
    assert not has_table_privilege('anon', 'public.pagamento_config', 'select'), 'anon le a chave Pix';
    assert not has_table_privilege('anon', 'public.pagamento_sessoes', 'select'), 'anon le as sessoes';
    assert has_function_privilege('service_role', 'public.dumtech_pagamentos_atual(text, text, text, text)', 'execute'),
        'service_role precisa chamar';
end;
$$;

rollback;
