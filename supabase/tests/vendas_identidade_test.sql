-- =============================================================================
-- Teste da migration 20260913090000: uma chave por cliente, venda manual
-- (Mercado Livre / direta), cadastro unico e avisos no pedido.
--
-- Roda dentro de uma transacao e desfaz tudo no fim: pode ser colado no SQL
-- Editor do Supabase, mesmo em producao.
-- =============================================================================

begin;

-- ======================================= 1. UMA CHAVE POR CLIENTE ===========
do $$
declare
    v_cliente  uuid;
    v_chave    text;
    v_pedido   uuid;
    v_resposta jsonb;
begin
    -- cliente com licenca SUSPENSA compra de novo pelo site
    insert into public.clientes (nome, email) values ('ZZ Suspenso', 'zz.suspenso@teste.local')
    returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['ESTOQUE']);
    update public.licencas set status = 'suspensa' where chave = v_chave;

    v_pedido := (public.dumtech_registrar_pedido('ZZ Suspenso', 'zz.suspenso@teste.local', '',
                                                 array['VENDAS'])->>'pedido')::uuid;
    v_resposta := public.dumtech_aprovar_pedido(v_pedido);
    assert v_resposta->>'chave' = v_chave, 'ganhou uma SEGUNDA chave em vez de usar a dele';
    assert (v_resposta->>'reativada')::boolean, 'a resposta precisa dizer que a licenca voltou';
    assert (select status from public.licencas where chave = v_chave) = 'ativa', 'a licenca nao voltou a valer';
    assert (select count(*) from public.licencas where cliente_id = v_cliente) = 1, 'nasceu licenca duplicada';
    assert (select count(*) from public.licenca_produtos lp join public.licencas l on l.id = lp.licenca_id
             where l.chave = v_chave) = 2, 'o modulo novo nao entrou na chave dele';
    raise notice '1. suspensa volta, sem segunda chave ok';
end;
$$;

-- ============================================ 2. TIPO E VENCIMENTO ==========
do $$
declare
    v_cliente uuid;
    v_chave   text;
    v_pedido  uuid;
begin
    -- teste que vira compra: passa a vitalicia sozinho
    insert into public.clientes (nome, email) values ('ZZ Teste', 'zz.teste@teste.local') returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['AGENDA'], null, 'teste',
                                                                 current_date + 7);
    v_pedido := (public.dumtech_registrar_pedido('ZZ Teste', 'zz.teste@teste.local', '', array['AGENDA'])->>'pedido')::uuid;
    perform public.dumtech_aprovar_pedido(v_pedido);
    assert (select tipo = 'vitalicia' and expira_em is null from public.licencas where chave = v_chave),
        'teste comprado deveria virar vitalicia';

    -- assinatura vencida renovada: a data que a DumTech escolher vale
    insert into public.clientes (nome, email) values ('ZZ Assina', 'zz.assina@teste.local') returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['ORDENS'], null, 'assinatura',
                                                                 current_date + 1);
    update public.licencas set expira_em = current_date - 3 where chave = v_chave;
    v_pedido := (public.dumtech_registrar_pedido('ZZ Assina', 'zz.assina@teste.local', '', array['ORDENS'])->>'pedido')::uuid;
    perform public.dumtech_aprovar_pedido(v_pedido, 1, 'assinatura', current_date + 365);
    assert (select expira_em from public.licencas where chave = v_chave) = current_date + 365,
        'renovar nao estendeu o vencimento';

    -- sem dizer o tipo, a assinatura fica como estava
    v_pedido := (public.dumtech_registrar_pedido('ZZ Assina', 'zz.assina@teste.local', '', array['CLIENTES'])->>'pedido')::uuid;
    perform public.dumtech_aprovar_pedido(v_pedido);
    assert (select tipo = 'assinatura' and expira_em = current_date + 365 from public.licencas where chave = v_chave),
        'modulo extra nao pode mexer no tipo nem no vencimento';

    begin
        perform public.dumtech_entregar_produtos(v_cliente, array['AGENDA'], null, 'assinatura', null);
        raise exception 'aceitou assinatura sem vencimento';
    exception when raise_exception then
        if sqlerrm like 'aceitou%' then raise; end if;
    end;
    raise notice '2. tipo e vencimento ............. ok';
end;
$$;

-- ================================================= 3. VENDA MANUAL ==========
do $$
declare
    v_antes    numeric := (select vendido from public.painel_resumo);
    v_resposta jsonb;
    v_cliente  uuid;
    v_mais     jsonb;
begin
    -- venda do Mercado Livre: sem e-mail (o ML nao mostra)
    v_resposta := public.dumtech_venda_manual(
        p_nome => 'ZZ Comprador ML', p_combo => 'GESTAO', p_canal => 'mercadolivre',
        p_referencia => '2000012345678', p_total => 649.90, p_max_computadores => 2);
    assert (v_resposta->>'ok')::boolean, format('venda manual falhou: %s', v_resposta);
    assert (v_resposta->>'licenca_nova')::boolean, 'comprador novo ganha licenca';
    assert v_resposta->>'chave' ~ '^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$', 'sem chave na resposta';
    v_cliente := (v_resposta->>'cliente_id')::uuid;

    assert (select origem = 'venda' and email = '' from public.clientes where id = v_cliente),
        'cliente do ML nasce como venda, sem e-mail';
    assert exists (select 1 from public.pedidos_site where cliente_id = v_cliente and origem = 'mercadolivre'
                     and referencia = '2000012345678' and total = 649.90 and atendido_em is not null),
        'a venda do ML precisa ficar registrada, atendida e com o valor recebido';
    assert (select vendido from public.painel_resumo) = v_antes + 649.90,
        '"Vendido" do painel nao contou a venda do Mercado Livre';
    assert (select total_comprado from public.painel_clientes where cliente_id = v_cliente) = 649.90,
        '"Comprou" da ficha nao contou a venda';

    -- a mesma pessoa compra mais um modulo por telefone: mesma chave
    v_mais := public.dumtech_venda_manual(p_nome => '', p_produtos => array['AGENDA'], p_total => 99,
                                          p_cliente_id => v_cliente);
    assert v_mais->>'chave' = v_resposta->>'chave', 'segunda venda gerou outra chave';
    assert (select count(*) from public.licencas where cliente_id = v_cliente) = 1, 'licenca duplicada';

    -- validacoes em portugues
    begin
        perform public.dumtech_venda_manual(p_nome => 'ZZ Vazio');
        raise exception 'vendeu nada';
    exception when raise_exception then
        if sqlerrm not like 'Escolha%' then raise; end if;
    end;
    begin
        perform public.dumtech_venda_manual(p_nome => 'ZZ Mail', p_email => 'nao-e-email', p_produtos => array['AGENDA']);
        raise exception 'aceitou e-mail torto';
    exception when raise_exception then
        if sqlerrm not like 'Confira%' then raise; end if;
    end;
    raise notice '3. venda manual (ML e direta) .... ok';
end;
$$;

-- ================================================ 4. CADASTRO UNICO =========
do $$
declare
    v_venda   jsonb;
    v_dono    uuid;
    v_chave   text;
    v_solto   uuid;
    v_pedido  uuid;
    v_r       jsonb;
begin
    -- 4.1 venda do ML (sem e-mail) -> cliente ativa o Hub -> no primeiro acesso digitou o e-mail
    v_venda := public.dumtech_venda_manual(p_nome => 'ZZ Maria ML', p_produtos => array['ESTOQUE'],
                                           p_canal => 'mercadolivre', p_total => 249);
    v_dono := (v_venda->>'cliente_id')::uuid;
    v_chave := v_venda->>'chave';
    perform public.dumtech_ativar_licenca(v_chave, 'zz-pc-maria');
    perform public.dumtech_identificar_cliente('Maria Souza', 'zz.maria@teste.local'); -- o cadastro solto
    v_solto := (select id from public.clientes where email = 'zz.maria@teste.local');
    assert v_solto is not null and v_solto <> v_dono, 'o teste precisa do cadastro duplicado para comecar';
    -- ela ainda mandou um pedido pelo site com esse e-mail antes de ligar
    v_pedido := (public.dumtech_registrar_pedido('Maria Souza', 'zz.maria@teste.local', '', array['VENDAS'])->>'pedido')::uuid;

    -- quem nao prova nada nao liga nada (e a resposta e igual para os dois casos)
    assert public.dumtech_vincular_conta(v_chave, 'zz-outro-pc', '', 'zz.maria@teste.local')->>'erro' = 'maquina_nao_ativada',
        'ligou e-mail sem computador ativado';
    assert public.dumtech_vincular_conta('ZZZZ-ZZZZ-ZZZZ-ZZZZ', 'zz-pc-maria', '', 'zz.maria@teste.local')->>'erro' = 'maquina_nao_ativada',
        'chave inexistente respondeu diferente (vira testador de chaves)';

    -- o Hub liga
    v_r := public.dumtech_vincular_conta(v_chave, 'zz-pc-maria', 'Maria Souza', 'zz.maria@teste.local');
    assert v_r = '{"ok": true, "vinculado": true}'::jsonb, format('nao ligou: %s', v_r);
    assert (select email from public.clientes where id = v_dono) = 'zz.maria@teste.local', 'o e-mail nao foi para o cliente da venda';
    assert not exists (select 1 from public.clientes where id = v_solto), 'o cadastro solto continuou existindo';
    assert (select cliente_id from public.pedidos_site where id = v_pedido) = v_dono, 'o pedido do site nao veio junto';
    assert (select count(*) from public.clientes where lower(email) = 'zz.maria@teste.local') = 1, 'ainda ha dois cadastros';

    -- ligar de novo nao estraga nada
    assert (public.dumtech_vincular_conta(v_chave, 'zz-pc-maria', '', 'zz.maria@teste.local')->>'vinculado')::boolean,
        'segunda chamada deveria confirmar';

    -- 4.2 o cadastro ja tem outro e-mail: o comercial manda, ninguem troca pelo Hub
    assert (public.dumtech_vincular_conta(v_chave, 'zz-pc-maria', '', 'zz.golpe@teste.local')->>'vinculado')::boolean = false,
        'trocou o e-mail de quem ja tinha';
    assert (select email from public.clientes where id = v_dono) = 'zz.maria@teste.local', 'o e-mail foi trocado';

    -- 4.3 e-mail de OUTRO cliente com licenca: nao mistura dois clientes de verdade
    v_venda := public.dumtech_venda_manual(p_nome => 'ZZ Sem Email', p_produtos => array['AGENDA'], p_total => 99);
    perform public.dumtech_ativar_licenca(v_venda->>'chave', 'zz-pc-sem-email');
    assert (public.dumtech_vincular_conta(v_venda->>'chave', 'zz-pc-sem-email', '', 'zz.maria@teste.local')->>'vinculado')::boolean = false,
        'juntou dois clientes que tem licenca';
    assert exists (select 1 from public.clientes where id = v_dono), 'apagou um cliente com licenca';

    assert has_function_privilege('anon', 'public.dumtech_vincular_conta(text,text,text,text)', 'execute'),
        'o Hub (anon) precisa ligar a conta';
    raise notice '4. cadastro unico ................ ok';
end;
$$;

-- ============================================= 5. AVISOS NO PEDIDO =========
do $$
declare
    v_cliente uuid;
    v_chave   text;
    v_pedido  uuid;
    v_linha   record;
begin
    insert into public.clientes (nome, email) values ('ZZ Aviso', 'zz.aviso@teste.local') returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['ESTOQUE']);
    update public.licencas set status = 'cancelada' where chave = v_chave;
    -- pede o combo Gestao, que TEM o Estoque dentro
    v_pedido := (public.dumtech_registrar_pedido('ZZ Aviso', 'zz.aviso@teste.local', '', '{}', 'GESTAO')->>'pedido')::uuid;

    select * into v_linha from public.pedidos_abertos where pedido_id = v_pedido;
    assert v_linha.ja_tem = array['ESTOQUE'], format('o aviso "ja tem" veio errado: %s', v_linha.ja_tem);
    assert v_linha.licenca_situacao = 'cancelada', 'o pedido precisa avisar que a licenca esta cancelada';
    assert v_linha.chave_atual is null, 'chave_atual continua sendo so a licenca ativa';

    assert not has_function_privilege('anon', 'public.dumtech_venda_manual(text,text,text,text[],text,text,text,numeric,text,date,integer,uuid)', 'execute'),
        'a chave publica NAO pode vender licenca';
    assert not has_function_privilege('anon', 'public.dumtech_entregar_produtos(uuid,text[],text,text,date,integer,text)', 'execute'),
        'a chave publica NAO pode entregar produto';
    raise notice '5. avisos no pedido .............. ok';
end;
$$;

-- ==================================== 6. COMO O PAINEL RODA DE VERDADE =====
-- O painel chama tudo com o papel `authenticated` (administrador com 2 fatores),
-- nunca como superusuario. Aprovar a PRIMEIRA compra de alguem chamava
-- dumtech_normalizar, que o authenticated nao podia executar: "permission
-- denied for function dumtech_normalizar" (achado em producao, 13/09/2026).
--
-- 6.1 A prova que nao depende da sessao: o PL/pgSQL guarda o plano da expressao
-- na sessao, entao uma funcao ja chamada antes como superusuario NAO confere a
-- permissao de novo - o teste "rodando como o painel" (6.2) sozinho nao pega o
-- erro. Aqui: toda funcao SEM security definer que o authenticated executa so
-- pode chamar funcoes que o authenticated tambem executa.
do $$
declare
    v_falta text;
begin
    select string_agg(distinct format('%s -> %s', f.proname, chamada.nome), ', ') into v_falta
      from pg_proc f
      join pg_namespace n on n.oid = f.pronamespace and n.nspname = 'public'
      cross join lateral (
            select (regexp_matches(f.prosrc, 'public\.(dumtech_[a-z_]+)\(', 'g'))[1] as nome
      ) chamada
      join pg_proc alvo on alvo.proname = chamada.nome
      join pg_namespace na on na.oid = alvo.pronamespace and na.nspname = 'public'
     where f.proname like 'dumtech%'
       and not f.prosecdef
       and has_function_privilege('authenticated', f.oid, 'execute')
       and not has_function_privilege('authenticated', alvo.oid, 'execute');
    assert v_falta is null,
        'o painel (authenticated) chama funcao sem permissao por dentro: ' || coalesce(v_falta, '');
    raise notice '6.1 permissoes da cadeia do painel ok';
end;
$$;

-- 6.2 o caminho completo, com o papel e o token do painel
do $$
declare
    v_admin    text := '55555555-5555-5555-5555-555555555555';
    v_pedido   uuid;
    v_resposta jsonb;
    v_venda    jsonb;
    v_licenca  uuid;
begin
    insert into public.administradores (user_id, nome) values (v_admin::uuid, 'ZZ Painel');
    -- o cliente monta o kit no site (anon)
    v_pedido := (public.dumtech_registrar_pedido('ZZ Primeira Vez', 'zz.primeira.vez@teste.local', '',
                                                 array['VENDAS'])->>'pedido')::uuid;

    perform set_config('request.jwt.claim.sub', v_admin, true);
    perform set_config('request.jwt.claims',
        format('{"sub":"%s","aal":"aal2","role":"authenticated","email":"zz.painel@dumtech.local"}', v_admin), true);
    set local role authenticated;

    -- aprovar a primeira compra (cria licenca nova: e aqui que quebrava)
    v_resposta := public.dumtech_aprovar_pedido(v_pedido, 1, null, null);
    assert (v_resposta->>'ok')::boolean and (v_resposta->>'licenca_nova')::boolean,
        format('o painel nao conseguiu aprovar a primeira compra: %s', v_resposta);

    -- venda do Mercado Livre e venda direta com e-mail, pelo painel
    v_venda := public.dumtech_venda_manual(p_nome => 'ZZ Painel ML', p_produtos => array['AGENDA'],
                                           p_canal => 'mercadolivre', p_referencia => '999', p_total => 99);
    assert (v_venda->>'ok')::boolean, format('o painel nao registrou a venda do ML: %s', v_venda);
    v_venda := public.dumtech_venda_manual(p_nome => 'ZZ Painel Direta', p_email => 'zz.painel.direta@teste.local',
                                           p_produtos => array['CLIENTES'], p_total => 149);
    assert (v_venda->>'ok')::boolean, format('o painel nao registrou a venda direta: %s', v_venda);

    -- editar licenca (renovar) e ler os dados para enviar a chave
    v_licenca := (v_venda->>'licenca_id')::uuid;
    update public.licencas set tipo = 'assinatura', expira_em = current_date + 30, max_computadores = 2
     where id = v_licenca;
    assert (public.dumtech_dados_da_chave(v_licenca)->>'ok')::boolean, 'o painel nao leu os dados da chave';
    assert (select count(*) from public.pedidos_abertos) >= 0, 'o painel nao leu os pedidos abertos';

    reset role;
    perform set_config('request.jwt.claim.sub', '', true);
    perform set_config('request.jwt.claims', '', true);
    raise notice '6. aprovar e vender pelo painel .. ok';
end;
$$;

do $$
begin
    raise notice '';
    raise notice 'TUDO CERTO - nada foi gravado (rollback no fim do arquivo).';
end;
$$;

rollback;
