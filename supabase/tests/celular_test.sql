-- =============================================================================
-- Teste da migration 20260923120000: o Hub no celular (pareamento por QR).
-- Roda numa transacao e desfaz tudo no fim.
-- =============================================================================

begin;

do $$
declare
    v_cliente uuid;
    v_chave   text;
    v_licenca uuid;
    v_maquina constant text := 'AAAA-BBBB-CCCC-CELU';
    v_pc      constant text := repeat('c', 32);
    r         jsonb;
    v_codigo  text;
    v_token   text;
    v_aparelho uuid;
begin
    insert into public.clientes (nome, email) values ('Padaria ZZ', 'zz.celular@teste.local')
    returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);
    select id into v_licenca from public.licencas where chave = v_chave;
    perform public.dumtech_ativar_licenca(v_chave, v_maquina, 'caixa');
    -- a assinatura prende a ativacao neste computador (o que licenca-assinada faz)
    update public.ativacoes set computador = v_pc where licenca_id = v_licenca;

    -- sem celular pareado, publicar nao guarda nada
    r := public.dumtech_celular_publicar(v_chave, v_maquina, v_pc, '{"secoes": []}'::jsonb);
    assert (r->>'pareados')::int = 0, 'publicou sem celular: ' || r::text;
    assert not exists (select 1 from public.celular_espelhos where licenca_id = v_licenca);

    -- license.json copiado para OUTRO computador nao pede QR
    r := public.dumtech_celular_iniciar(v_chave, v_maquina, repeat('d', 32));
    assert r->>'erro' = 'licenca_invalida', 'outro computador gerou QR: ' || r::text;

    -- 1. o Hub gera o QR
    r := public.dumtech_celular_iniciar(v_chave, v_maquina, v_pc);
    assert (r->>'ok')::boolean, 'QR recusado: ' || r::text;
    v_codigo := r->>'codigo';
    assert length(v_codigo) = 64, 'codigo curto demais';
    assert not exists (select 1 from public.celular_codigos where codigo_hash = v_codigo),
        'o codigo ficou guardado em claro';

    -- 2. o celular pareia (uma vez so)
    r := public.dumtech_celular_parear(v_codigo, 'iPhone do Joao');
    assert (r->>'ok')::boolean, 'pareamento recusado: ' || r::text;
    v_token := r->>'token';
    assert r->>'cliente' = 'Padaria ZZ';
    r := public.dumtech_celular_parear(v_codigo, 'Celular do ladrao');
    assert r->>'erro' = 'codigo_invalido', 'o mesmo QR pareou duas vezes: ' || r::text;

    -- QR vencido nao pareia
    r := public.dumtech_celular_iniciar(v_chave, v_maquina, v_pc);
    update public.celular_codigos set expira_em = now() - interval '1 second' where licenca_id = v_licenca;
    assert public.dumtech_celular_parear(r->>'codigo', 'x')->>'erro' = 'codigo_invalido', 'QR vencido pareou';

    -- 3. o Hub publica e o celular le
    r := public.dumtech_celular_publicar(v_chave, v_maquina, v_pc,
            '{"versao": 1, "secoes": [{"app": "vendas", "titulo": "Vendas"}]}'::jsonb);
    assert (r->>'pareados')::int = 1, 'publicar nao viu o celular: ' || r::text;
    r := public.dumtech_celular_dados(v_token);
    assert (r->>'ok')::boolean, 'celular nao leu: ' || r::text;
    assert (r->'modulos') ? 'VENDAS', 'modulos errados: ' || r::text;
    assert jsonb_array_length(r->'espelhos') = 1, 'sem espelho: ' || r::text;

    -- comprou modulo: o celular ve NA HORA (licenca lida ao abrir)
    perform public.dumtech_liberar_produtos(v_licenca, array['ORDENS']);
    r := public.dumtech_celular_dados(v_token);
    assert (r->'modulos') ? 'ORDENS', 'modulo novo nao chegou ao celular: ' || r::text;

    -- teste gratis valendo tambem aparece
    perform public.dumtech_iniciar_teste(v_chave, v_maquina, 'AGENDA');
    r := public.dumtech_celular_dados(v_token);
    assert (r->'modulos') ? 'AGENDA', 'teste gratis fora do celular: ' || r::text;

    -- token inventado nao le nada
    assert public.dumtech_celular_dados('token-inventado')->>'erro' = 'desconectado';

    -- a lista do Hub e o "Desconectar"
    r := public.dumtech_celular_aparelhos(v_chave, v_maquina, v_pc);
    assert jsonb_array_length(r->'aparelhos') = 1, 'lista errada: ' || r::text;
    v_aparelho := (r->'aparelhos'->0->>'id')::uuid;
    assert (public.dumtech_celular_revogar(v_chave, v_maquina, v_pc, v_aparelho)->>'ok')::boolean;
    assert public.dumtech_celular_dados(v_token)->>'erro' = 'desconectado', 'celular desconectado continuou lendo';

    -- licenca bloqueada no painel: o celular para de ver
    r := public.dumtech_celular_iniciar(v_chave, v_maquina, v_pc);
    v_token := public.dumtech_celular_parear(r->>'codigo', 'Outro')->>'token';
    update public.licencas set status = 'suspensa' where id = v_licenca;
    assert public.dumtech_celular_dados(v_token)->>'erro' = 'licenca_bloqueada', 'licenca bloqueada continuou visivel';

    -- ninguem de fora le as tabelas
    assert not has_table_privilege('anon', 'public.celular_espelhos', 'select'), 'anon le espelhos';
    assert not has_table_privilege('anon', 'public.celular_aparelhos', 'select'), 'anon le aparelhos';
    assert not has_function_privilege('anon', 'public.dumtech_celular_licenca(text,text,text)', 'execute'),
        'anon chama a funcao interna';

    raise notice 'celular .......................... ok';
end;
$$;

rollback;
