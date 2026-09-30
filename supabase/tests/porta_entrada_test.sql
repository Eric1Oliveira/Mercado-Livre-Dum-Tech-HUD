-- =============================================================================
-- Teste da porta de entrada (cadastro, ofertas e token da loja).
--
-- Roda inteiro dentro de uma transacao e desfaz tudo no fim: pode ser colado no
-- SQL Editor do Supabase, mesmo em producao. Se aparecer "TUDO CERTO", passou.
-- =============================================================================

begin;

-- ============================================================ 1. ESTRUTURA ==
do $$
begin
    assert to_regclass('public.comunicados')   is not null, 'falta a tabela comunicados';
    assert to_regclass('public.compra_tokens') is not null, 'falta a tabela compra_tokens';
    assert exists (select 1 from information_schema.columns
                    where table_schema = 'public' and table_name = 'clientes'
                      and column_name = 'origem'), 'clientes sem a coluna origem';
    raise notice '1. estrutura ....................... ok';
end;
$$;

-- ================================================= 2. IDENTIFICAR CLIENTE ===
do $$
declare
    v_resposta jsonb;
    v_antes    integer;
begin
    select count(*) into v_antes from public.clientes;

    -- cadastro novo entra com origem 'hub'
    v_resposta := public.dumtech_identificar_cliente('ZZ Visitante', 'ZZ.Visitante@Teste.Local ');
    assert (v_resposta->>'ok')::boolean, format('cadastro recusado: %s', v_resposta);
    assert (select count(*) from public.clientes) = v_antes + 1, 'o cliente nao foi criado';
    assert (select origem from public.clientes where email = 'zz.visitante@teste.local') = 'hub',
        'o cliente do Hub deveria nascer com origem = hub';
    assert (select email from public.clientes where nome = 'ZZ Visitante') = 'zz.visitante@teste.local',
        'o e-mail deveria ser guardado em minusculas e sem espacos';

    -- o MESMO e-mail nao vira segundo cliente, e a resposta e identica
    v_resposta := public.dumtech_identificar_cliente('Outro Nome', 'zz.visitante@teste.local');
    assert (v_resposta->>'ok')::boolean, 'a segunda chamada deveria responder igual';
    assert v_resposta = '{"ok": true}'::jsonb,
        format('a resposta nao pode dizer se o e-mail ja existia: %s', v_resposta);
    assert (select count(*) from public.clientes) = v_antes + 1, 'duplicou o cliente';
    assert (select nome from public.clientes where email = 'zz.visitante@teste.local') = 'ZZ Visitante',
        'o cadastro existente nao pode ser sobrescrito pelo que foi digitado';

    -- entrada ruim
    assert public.dumtech_identificar_cliente('', 'a@b.com')->>'erro' = 'dados_incompletos',
        'aceitou cadastro sem nome';
    assert public.dumtech_identificar_cliente('Fulano', 'nao-e-email')->>'erro' = 'email_invalido',
        'aceitou e-mail invalido';
    assert public.dumtech_identificar_cliente('Fulano', '')->>'erro' = 'email_invalido',
        'aceitou e-mail vazio';
    raise notice '2. identificar cliente ............. ok';
end;
$$;

-- ========================================================= 3. COMUNICADOS ==
do $$
declare
    v_cliente  uuid;
    v_chave    text;
    v_lista    jsonb;
    v_titulos  text;
begin
    insert into public.comunicados (titulo, texto, rotulo, alvo, ordem)
    values ('ZZ Bem-vindo', 'Conheca os modulos DumTech', 'Novidade', 'todos', 1);
    insert into public.comunicados (titulo, texto, alvo, produto_codigo, ordem)
    values ('ZZ Leve o Vendas', 'Seu balcao mais rapido', 'sem_produto', 'VENDAS', 2);
    insert into public.comunicados (titulo, alvo, ordem, ativo)
    values ('ZZ Desligado', 'todos', 3, false);
    insert into public.comunicados (titulo, alvo, ordem, inicio, fim)
    values ('ZZ Fora do prazo', 'todos', 4, current_date - 30, current_date - 1);

    -- visitante sem chave ve o que e para todos e as ofertas de produto
    v_lista := public.dumtech_comunicados()->'comunicados';
    select string_agg(c->>'titulo', ', ') into v_titulos from jsonb_array_elements(v_lista) c;
    assert v_titulos like '%ZZ Bem-vindo%', 'o comunicado geral nao apareceu';
    assert v_titulos like '%ZZ Leve o Vendas%', 'a oferta de produto nao apareceu para quem nao tem';
    assert v_titulos not like '%ZZ Desligado%', 'comunicado desligado apareceu';
    assert v_titulos not like '%ZZ Fora do prazo%', 'comunicado fora do prazo apareceu';

    -- cliente que JA tem o Vendas nao ve a oferta do Vendas
    insert into public.clientes (nome, email) values ('ZZ Dono do Vendas', 'zz.vendas@teste.local')
    returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);

    v_lista := public.dumtech_comunicados(v_chave)->'comunicados';
    select string_agg(c->>'titulo', ', ') into v_titulos from jsonb_array_elements(v_lista) c;
    assert v_titulos like '%ZZ Bem-vindo%', 'o comunicado geral sumiu para quem tem licenca';
    assert v_titulos not like '%ZZ Leve o Vendas%',
        'a oferta foi mostrada para quem ja tem o produto';

    -- chave que nao existe nao quebra nem vaza: responde como visitante
    v_lista := public.dumtech_comunicados('ZZZZ-ZZZZ-ZZZZ-ZZZZ')->'comunicados';
    assert jsonb_array_length(v_lista) >= 1, 'chave invalida deveria responder como visitante';
    raise notice '3. comunicados ..................... ok';
end;
$$;

-- ================================================== 4. TOKEN DE COMPRA =====
do $$
declare
    v_cliente  uuid;
    v_chave    text;
    v_token    text;
    v_resposta jsonb;
    v_aberto   jsonb;
begin
    insert into public.clientes (nome, documento, email)
    values ('ZZ Cliente Com Licenca', '', 'zz.licenca@teste.local')
    returning id into v_cliente;
    select chave into v_chave
      from public.dumtech_emitir_licenca(v_cliente, array['ESTOQUE', 'FINANCEIRO']);
    perform public.dumtech_ativar_licenca(v_chave, 'zz-token-1');

    -- caminho de quem tem licenca: fotografia de verdade
    v_resposta := public.dumtech_token_compra(v_chave, 'zz-token-1');
    assert (v_resposta->>'ok')::boolean, format('token recusado: %s', v_resposta);
    v_token := v_resposta->>'token';
    assert length(v_token) = 32, format('token com tamanho estranho: %s', v_token);

    v_aberto := public.dumtech_abrir_compra(v_token);
    assert (v_aberto->>'ok')::boolean, format('a landing nao conseguiu abrir: %s', v_aberto);
    assert v_aberto->>'nome' = 'ZZ Cliente Com Licenca', 'nome errado na troca';
    assert v_aberto->>'email' = 'zz.licenca@teste.local', 'e-mail errado na troca';
    assert v_aberto->'produtos' = '["ESTOQUE", "FINANCEIRO"]'::jsonb,
        format('produtos errados na troca: %s', v_aberto->'produtos');

    -- uso unico
    assert public.dumtech_abrir_compra(v_token)->>'erro' = 'token_invalido',
        'o token foi aceito duas vezes';

    -- token vencido nao abre
    v_token := public.dumtech_token_compra(v_chave, 'zz-token-1')->>'token';
    update public.compra_tokens set expira_em = now() - interval '1 minute' where token = v_token;
    assert public.dumtech_abrir_compra(v_token)->>'erro' = 'token_invalido',
        'o token vencido foi aceito';
    assert public.dumtech_abrir_compra('nao-existe')->>'erro' = 'token_invalido',
        'token inventado foi aceito';

    -- computador nao ativado nao gera token
    assert public.dumtech_token_compra(v_chave, 'zz-outro-pc')->>'erro' = 'maquina_nao_ativada',
        'gerou token para um computador que nao esta na licenca';
    assert public.dumtech_token_compra('ZZZZ-ZZZZ-ZZZZ-ZZZZ', 'zz-token-1')->>'erro' = 'nao_encontrada',
        'gerou token com chave inexistente';
    raise notice '4. token de compra (com licenca) ... ok';
end;
$$;

-- ===================================== 5. TOKEN DE VISITANTE (sem licenca) ==
do $$
declare
    v_token  text;
    v_aberto jsonb;
begin
    -- o visitante informa nome e e-mail; o token carrega SO isso
    v_token := public.dumtech_token_compra('', '', 'ZZ Visita', 'zz.visitante@teste.local')->>'token';
    v_aberto := public.dumtech_abrir_compra(v_token);
    assert v_aberto->>'nome' = 'ZZ Visita', 'nome do visitante errado';
    assert v_aberto->'produtos' = '[]'::jsonb, 'visitante nao pode vir com produtos';

    -- e o ponto sensivel: usar o e-mail de um CLIENTE DE VERDADE nao entrega
    -- o nome nem os produtos dele
    v_token := public.dumtech_token_compra('', '', 'Curioso', 'zz.licenca@teste.local')->>'token';
    v_aberto := public.dumtech_abrir_compra(v_token);
    assert v_aberto->>'nome' = 'Curioso',
        format('vazou o nome do cliente de verdade: %s', v_aberto->>'nome');
    assert v_aberto->'produtos' = '[]'::jsonb,
        format('vazou os produtos do cliente de verdade: %s', v_aberto->'produtos');

    assert public.dumtech_token_compra('', '', 'Fulano', 'nao-e-email')->>'erro' = 'email_invalido',
        'gerou token com e-mail invalido';
    raise notice '5. token de visitante .............. ok';
end;
$$;

-- ================================================== 6. SEGURANCA (anon) ====
do $$
declare
    v_sobra text;
begin
    select string_agg(t || ' (' || p || ')', ', ') into v_sobra
      from unnest(array['comunicados', 'compra_tokens']) t,
           unnest(array['select', 'insert', 'update', 'delete']) p
     where has_table_privilege('anon', 'public.' || t, p);
    assert v_sobra is null, 'a chave anon tem privilegio em: ' || coalesce(v_sobra, '');

    select string_agg(p.proname, ', ') into v_sobra
      from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname like 'dumtech%'
       and has_function_privilege('anon', p.oid, 'execute')
       and p.proname not in ('dumtech_ativar_licenca', 'dumtech_verificar_licenca',
                             'dumtech_desativar_licenca', 'dumtech_identificar_cliente',
                             'dumtech_comunicados', 'dumtech_token_compra',
                             'dumtech_abrir_compra', 'dumtech_catalogo',
                             'dumtech_registrar_pedido', 'dumtech_registrar_uso',
                             'dumtech_vincular_conta', 'dumtech_hub_versao',
                             'dumtech_conferir_cupom', 'dumtech_iniciar_teste',
                             'dumtech_celular_iniciar', 'dumtech_celular_aparelhos',
                             'dumtech_celular_revogar', 'dumtech_celular_publicar',
                             'dumtech_celular_parear', 'dumtech_celular_dados');
    assert v_sobra is null, 'a chave anon executa funcoes demais: ' || coalesce(v_sobra, '');

    select string_agg(c.relname, ', ') into v_sobra
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity
       and c.relname in ('comunicados', 'compra_tokens');
    assert v_sobra is null, 'tabela sem RLS: ' || coalesce(v_sobra, '');
    raise notice '6. permissoes ...................... ok';
end;
$$;

-- 6.1 na pratica, virando a chave anon
do $$
declare
    v_resposta jsonb;
begin
    begin
        execute 'set local role anon';
        perform 1 from public.comunicados;
        raise exception 'a chave anon leu public.comunicados!';
    exception when insufficient_privilege then null;
    end;

    begin
        execute 'set local role anon';
        perform 1 from public.compra_tokens;
        raise exception 'a chave anon leu public.compra_tokens!';
    exception when insufficient_privilege then null;
    end;

    -- ... mas o que ela precisa fazer continua funcionando
    set local role anon;
    v_resposta := public.dumtech_identificar_cliente('ZZ Pela Anon', 'zz.anon@teste.local');
    reset role;
    assert (v_resposta->>'ok')::boolean, format('a anon nao conseguiu se cadastrar: %s', v_resposta);
    raise notice '6.1 chave anon ..................... ok';
end;
$$;

do $$
begin
    raise notice '';
    raise notice 'TUDO CERTO - nada foi gravado (rollback no fim do arquivo).';
end;
$$;

rollback;
