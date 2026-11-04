-- =============================================================================
-- Teste do licenciamento - roda inteiro dentro de uma transacao e desfaz tudo.
--
-- COMO RODAR
--   Supabase > SQL Editor > New query > cole este arquivo > Run.
--   Se aparecer "TUDO CERTO" no fim, passou. Qualquer assert que falhar
--   interrompe com a mensagem do erro e nada e gravado (o rollback do fim
--   desfaz ate os dados de teste).
--
-- Tambem roda em qualquer Postgres 15+ com as tabelas desta migration.
-- =============================================================================

begin;

-- ============================================================ 1. ESTRUTURA ==
do $$
begin
    assert to_regclass('public.produtos')         is not null, 'falta a tabela produtos';
    assert to_regclass('public.combos')           is not null, 'falta a tabela combos';
    assert to_regclass('public.combo_produtos')   is not null, 'falta a tabela combo_produtos';
    assert to_regclass('public.licenca_produtos') is not null, 'falta a tabela licenca_produtos';

    -- a estrutura antiga tem de ter ido embora, sem sobrar tabela orfa
    assert to_regclass('public.aplicativos')  is null, 'a tabela aplicativos ainda existe';
    assert to_regclass('public.licenca_apps') is null, 'a tabela licenca_apps ainda existe';

    assert (select count(*) from public.produtos) >= 7,
        'o catalogo de produtos deveria ter ao menos os 7 modulos';
    raise notice '1. estrutura ....................... ok';
end;
$$;

-- ================================================== 2. DADOS QUE JA EXISTIAM ==
-- (so confere quando ha dados migrados; num banco vazio o bloco passa direto)
do $$
declare
    v_produtos integer;
    v_tipo     text;
begin
    if exists (select 1 from public.licencas where chave = 'DEMO-2026-TEST-0001') then
        select count(*) into v_produtos
          from public.licenca_produtos lp
          join public.licencas l on l.id = lp.licenca_id
         where l.chave = 'DEMO-2026-TEST-0001';
        assert v_produtos >= 7,
            format('a licenca de demonstracao perdeu produtos na migracao (%s)', v_produtos);

        select tipo into v_tipo from public.licencas where chave = 'DEMO-2026-TEST-0001';
        assert v_tipo is not null and v_tipo <> '', 'licenca sem tipo';
    end if;

    -- toda licenca com prazo precisa ter virado assinatura (ou teste)
    assert not exists (select 1 from public.licencas
                        where expira_em is not null and tipo = 'vitalicia'),
        'sobrou licenca vitalicia com prazo';
    raise notice '2. dados migrados .................. ok';
end;
$$;

-- ================================================== 3. CLIENTE E PRODUTO ====
do $$
declare
    v_cliente uuid;
begin
    insert into public.clientes (nome, documento, email, telefone)
    values ('ZZ Teste Automatizado', '111.111.111-11', 'zz@teste.local', '(63) 90000-0000')
    returning id into v_cliente;
    assert v_cliente is not null, 'nao criou o cliente';

    -- modulo novo = um INSERT, nunca uma tabela nova
    insert into public.produtos (codigo, nome, descricao, preco, versao)
    values ('ZZ_CRM', 'DumTech CRM (teste)', 'Produto criado pelo teste', 199.90, '1.0');
    assert (select preco from public.produtos where codigo = 'ZZ_CRM') = 199.90,
        'o produto novo nao guardou o preco';

    -- codigo fora do padrao nao entra
    begin
        insert into public.produtos (codigo, nome) values ('crm minusculo', 'x');
        raise exception 'aceitou um codigo de produto fora do padrao';
    exception when check_violation then null;
    end;
    raise notice '3. cliente e produto ............... ok';
end;
$$;

-- ========================================================= 4. GERAR CHAVE ===
do $$
declare
    v_chave  text;
    v_i      integer;
    v_chaves text[] := '{}';
begin
    for v_i in 1..200 loop
        v_chave := public.dumtech_nova_chave();
        assert v_chave ~ '^[A-Z2-9]{4}(-[A-Z2-9]{4}){3}$',
            format('chave fora do formato: %s', v_chave);
        assert v_chave !~ '[OI01]', format('chave com caractere confuso: %s', v_chave);
        v_chaves := v_chaves || v_chave;
    end loop;
    assert (select count(distinct c) from unnest(v_chaves) c) = 200,
        'o gerador repetiu chaves em 200 sorteios';
    raise notice '4. gerador de chaves ............... ok';
end;
$$;

-- ================================================ 5. EMITIR LICENCA (venda) ==
do $$
declare
    v_cliente uuid;
    v_licenca uuid;
    v_chave   text;
begin
    select id into v_cliente from public.clientes where email = 'zz@teste.local';

    select licenca_id, chave into v_licenca, v_chave
      from public.dumtech_emitir_licenca(
            p_cliente_id       => v_cliente,
            p_produtos         => array['ESTOQUE', 'FINANCEIRO'],
            p_max_computadores => 2,
            p_observacoes      => 'licenca do teste automatizado');

    assert v_licenca is not null and v_chave ~ '^[A-Z2-9]{4}(-[A-Z2-9]{4}){3}$',
        'a emissao nao devolveu licenca e chave';
    assert (select count(*) from public.licenca_produtos where licenca_id = v_licenca) = 2,
        'a licenca deveria ter 2 produtos';
    assert (select tipo from public.licencas where id = v_licenca) = 'vitalicia',
        'o tipo padrao deveria ser vitalicia';

    -- vender produto que nao existe tem de falhar alto, nao passar batido
    begin
        perform public.dumtech_emitir_licenca(v_cliente, array['NAO_EXISTE']);
        raise exception 'emitiu licenca com produto inexistente';
    exception when raise_exception then
        if position('nao existe no catalogo' in sqlerrm) = 0 then raise; end if;
    end;

    -- licenca sem nada comprado nao faz sentido
    begin
        perform public.dumtech_emitir_licenca(v_cliente);
        raise exception 'emitiu licenca sem produto nenhum';
    exception when raise_exception then
        if position('ao menos um produto' in sqlerrm) = 0 then raise; end if;
    end;
    raise notice '5. emitir licenca .................. ok';
end;
$$;

-- ====================================== 6. ATIVAR, LIMITE E VERIFICAR =======
do $$
declare
    v_chave     text;
    v_resposta  jsonb;
    v_tentativas integer;
begin
    select l.chave into v_chave
      from public.licencas l
      join public.clientes c on c.id = l.cliente_id
     where c.email = 'zz@teste.local';

    -- computador 1
    v_resposta := public.dumtech_ativar_licenca(v_chave, 'zz-maquina-1', 'PC da loja');
    assert (v_resposta->>'ok')::boolean, format('ativacao 1 recusada: %s', v_resposta);
    assert v_resposta->'produtos' = '["ESTOQUE", "FINANCEIRO"]'::jsonb,
        format('produtos errados na resposta: %s', v_resposta->'produtos');
    assert v_resposta->'aplicativos' = v_resposta->'produtos',
        'o campo antigo aplicativos precisa continuar igual ao produtos';
    assert v_resposta->>'tipo' = 'vitalicia', 'a resposta deveria trazer o tipo';
    assert (v_resposta->>'computadores_usados')::int = 1, 'contagem de computadores errada';
    -- a chave chega em minuscula e e normalizada
    assert v_resposta->>'chave' = upper(v_chave), 'a chave voltou diferente';

    -- computador 2 (o plano permite)
    v_resposta := public.dumtech_ativar_licenca(v_chave, 'zz-maquina-2');
    assert (v_resposta->>'ok')::boolean, 'ativacao 2 deveria ser aceita';
    assert (v_resposta->>'computadores_usados')::int = 2, 'deveriam ser 2 computadores';

    -- ativar de novo o mesmo computador nao ocupa vaga nova
    v_resposta := public.dumtech_ativar_licenca(v_chave, 'ZZ-MAQUINA-1');
    assert (v_resposta->>'computadores_usados')::int = 2, 'reativacao ocupou vaga nova';

    -- computador 3: barrado
    select count(*) into v_tentativas from public.licenca_tentativas;
    v_resposta := public.dumtech_ativar_licenca(v_chave, 'zz-maquina-3');
    assert v_resposta->>'erro' = 'limite_maquinas',
        format('o limite de computadores nao barrou: %s', v_resposta);
    assert (select count(*) from public.licenca_tentativas) = v_tentativas + 1,
        'a tentativa recusada nao foi registrada';

    -- verificar: computador ativado x computador desconhecido
    v_resposta := public.dumtech_verificar_licenca(v_chave, 'zz-maquina-1');
    assert (v_resposta->>'ok')::boolean, 'verificacao do computador ativado falhou';
    v_resposta := public.dumtech_verificar_licenca(v_chave, 'zz-maquina-9');
    assert v_resposta->>'erro' = 'maquina_nao_ativada', 'verificou computador nao ativado';

    -- chave e maquina em branco
    assert public.dumtech_ativar_licenca('', 'zz-maquina-1')->>'erro' = 'dados_incompletos',
        'aceitou chave vazia';
    assert public.dumtech_ativar_licenca(v_chave, '')->>'erro' = 'dados_incompletos',
        'aceitou computador vazio';

    -- chave que nao existe: recusa e registra
    select count(*) into v_tentativas from public.licenca_tentativas;
    v_resposta := public.dumtech_ativar_licenca('ZZZZ-ZZZZ-ZZZZ-ZZZZ', 'zz-maquina-1');
    assert v_resposta->>'erro' = 'nao_encontrada', 'chave inexistente foi aceita';
    assert (select count(*) from public.licenca_tentativas) = v_tentativas + 1,
        'chave inexistente nao foi registrada';

    -- texto gigante nao vira linha gigante no banco
    v_resposta := public.dumtech_ativar_licenca(repeat('X', 5000), repeat('Y', 5000));
    assert (select max(length(chave)) from public.licenca_tentativas) <= 32,
        'a chave registrada passou do tamanho limite';
    assert (select max(length(maquina)) from public.licenca_tentativas) <= 64,
        'o computador registrado passou do tamanho limite';
    raise notice '6. ativar / limite / verificar ..... ok';
end;
$$;

-- ============================== 7. COMPROU OUTRO MODULO (sem reinstalar) ====
do $$
declare
    v_chave    text;
    v_licenca  uuid;
    v_resposta jsonb;
begin
    select l.id, l.chave into v_licenca, v_chave
      from public.licencas l join public.clientes c on c.id = l.cliente_id
     where c.email = 'zz@teste.local';

    assert public.dumtech_liberar_produtos(v_licenca, array['VENDAS']) = 1,
        'nao liberou o produto novo';
    -- liberar de novo nao duplica
    assert public.dumtech_liberar_produtos(v_licenca, array['VENDAS']) = 0,
        'liberou o mesmo produto duas vezes';

    v_resposta := public.dumtech_verificar_licenca(v_chave, 'zz-maquina-1');
    assert v_resposta->'produtos' = '["ESTOQUE", "FINANCEIRO", "VENDAS"]'::jsonb,
        format('o modulo novo nao apareceu na verificacao: %s', v_resposta->'produtos');

    -- e a DumTech pode tirar um produto da licenca
    delete from public.licenca_produtos
     where licenca_id = v_licenca
       and produto_id = (select id from public.produtos where codigo = 'VENDAS');
    v_resposta := public.dumtech_verificar_licenca(v_chave, 'zz-maquina-1');
    assert v_resposta->'produtos' = '["ESTOQUE", "FINANCEIRO"]'::jsonb,
        'o produto removido continuou liberado';
    raise notice '7. comprar outro modulo ............ ok';
end;
$$;

-- ============================================ 8. SUSPENSA, CANCELADA, PRAZO ==
do $$
declare
    v_chave    text;
    v_licenca  uuid;
    v_cliente  uuid;
    v_resposta jsonb;
begin
    select l.id, l.chave, l.cliente_id into v_licenca, v_chave, v_cliente
      from public.licencas l join public.clientes c on c.id = l.cliente_id
     where c.email = 'zz@teste.local';

    update public.licencas set status = 'suspensa' where id = v_licenca;
    v_resposta := public.dumtech_verificar_licenca(v_chave, 'zz-maquina-1');
    assert v_resposta->>'erro' = 'inativa', 'licenca suspensa continuou valendo';
    assert v_resposta->>'mensagem' ilike '%suspensa%', 'mensagem de suspensa sem explicacao';

    update public.licencas set status = 'cancelada' where id = v_licenca;
    assert public.dumtech_ativar_licenca(v_chave, 'zz-maquina-4')->>'erro' = 'inativa',
        'licenca cancelada continuou ativando';

    -- reativar volta a funcionar
    update public.licencas set atualizado_em = '2000-01-01' where id = v_licenca;
    update public.licencas set status = 'ativa' where id = v_licenca;
    assert (public.dumtech_verificar_licenca(v_chave, 'zz-maquina-1')->>'ok')::boolean,
        'a licenca reativada continuou barrada';
    -- o carimbo de alteracao e do gatilho, nao de quem escreve o UPDATE
    assert (select atualizado_em from public.licencas where id = v_licenca) > '2000-01-02',
        'o gatilho nao atualizou o carimbo da licenca';

    -- assinatura vencida
    perform public.dumtech_emitir_licenca(v_cliente, array['AGENDA'], null,
                                          'assinatura', current_date - 1, 1, '',
                                          'ZZZ1-VENC-IDAA-2222');
    v_resposta := public.dumtech_ativar_licenca('ZZZ1-VENC-IDAA-2222', 'zz-maquina-1');
    assert v_resposta->>'erro' = 'expirada', 'assinatura vencida foi aceita';
    assert v_resposta->>'mensagem' ilike '%Renove%', 'mensagem de vencimento sem convite';

    -- teste (demonstracao) vencido fala a lingua certa
    perform public.dumtech_emitir_licenca(v_cliente, array['AGENDA'], null,
                                          'teste', current_date - 1, 1, '',
                                          'ZZZ2-TEST-IDAA-3333');
    v_resposta := public.dumtech_ativar_licenca('ZZZ2-TEST-IDAA-3333', 'zz-maquina-1');
    assert v_resposta->>'mensagem' ilike '%teste grátis terminou%',
        format('mensagem errada para teste vencido: %s', v_resposta->>'mensagem');

    -- estado impossivel nao entra
    begin
        update public.licencas set expira_em = current_date + 30 where id = v_licenca;
        raise exception 'aceitou licenca vitalicia com prazo';
    exception when check_violation then null;
    end;
    raise notice '8. suspensa / cancelada / prazo .... ok';
end;
$$;

-- ================================================ 9. DESATIVAR COMPUTADOR ===
do $$
declare
    v_chave      text;
    v_resposta   jsonb;
    v_tentativas integer;
begin
    select l.chave into v_chave
      from public.licencas l join public.clientes c on c.id = l.cliente_id
     where c.email = 'zz@teste.local' and l.observacoes = 'licenca do teste automatizado';

    v_resposta := public.dumtech_desativar_licenca(v_chave, 'zz-maquina-2');
    assert (v_resposta->>'ok')::boolean and (v_resposta->>'removido')::boolean,
        format('nao desativou o computador: %s', v_resposta);

    -- a vaga foi liberada de verdade
    v_resposta := public.dumtech_ativar_licenca(v_chave, 'zz-maquina-3');
    assert (v_resposta->>'ok')::boolean, 'a vaga liberada nao pode ser reutilizada';
    assert (v_resposta->>'computadores_usados')::int = 2, 'contagem errada apos a troca';

    -- desativar chave inexistente tambem fica registrado (nao e um oraculo mudo)
    select count(*) into v_tentativas from public.licenca_tentativas;
    assert public.dumtech_desativar_licenca('ZZZZ-ZZZZ-ZZZZ-ZZZZ', 'x')->>'erro' = 'nao_encontrada',
        'desativou uma chave que nao existe';
    assert (select count(*) from public.licenca_tentativas) = v_tentativas + 1,
        'desativacao de chave inexistente nao foi registrada';
    raise notice '9. desativar computador ............ ok';
end;
$$;

-- ============================================== 10. COMBO (venda de pacote) ==
do $$
declare
    v_combo    uuid;
    v_cliente  uuid;
    v_licenca  uuid;
    v_chave    text;
    v_resposta jsonb;
begin
    insert into public.combos (codigo, nome, descricao, preco)
    values ('ZZ_GESTAO', 'DumTech Gestao (teste)', 'Estoque, Financeiro, Clientes e Vendas', 899.00)
    returning id into v_combo;

    insert into public.combo_produtos (combo_id, produto_id)
    select v_combo, id from public.produtos
     where codigo in ('ESTOQUE', 'FINANCEIRO', 'CLIENTES', 'VENDAS');

    assert (select count(*) from public.combo_produtos where combo_id = v_combo) = 4,
        'o combo deveria ter 4 produtos';

    -- o mesmo produto nao entra duas vezes no combo
    begin
        insert into public.combo_produtos (combo_id, produto_id)
        select v_combo, id from public.produtos where codigo = 'ESTOQUE';
        raise exception 'o combo aceitou o mesmo produto duas vezes';
    exception when unique_violation then null;
    end;

    -- cliente compra o combo: UMA chave so
    insert into public.clientes (nome, email) values ('ZZ Cliente do Combo', 'zz2@teste.local')
    returning id into v_cliente;

    select licenca_id, chave into v_licenca, v_chave
      from public.dumtech_emitir_licenca(p_cliente_id => v_cliente, p_combo => 'ZZ_GESTAO');

    assert (select count(*) from public.licenca_produtos where licenca_id = v_licenca) = 4,
        'a compra do combo nao liberou os 4 produtos';
    assert (select count(*) from public.licencas where cliente_id = v_cliente) = 1,
        'a compra do combo criou mais de uma licenca';
    assert (select count(*) from public.licenca_produtos
             where licenca_id = v_licenca and combo_id = v_combo) = 4,
        'a origem (combo) nao ficou registrada nos produtos liberados';

    v_resposta := public.dumtech_ativar_licenca(v_chave, 'zz-combo-1');
    assert v_resposta->'produtos' = '["CLIENTES", "ESTOQUE", "FINANCEIRO", "VENDAS"]'::jsonb,
        format('o combo nao chegou inteiro no aplicativo: %s', v_resposta->'produtos');

    -- mudar o combo depois NAO mexe em quem ja comprou
    delete from public.combo_produtos
     where combo_id = v_combo
       and produto_id = (select id from public.produtos where codigo = 'VENDAS');
    v_resposta := public.dumtech_verificar_licenca(v_chave, 'zz-combo-1');
    assert v_resposta->'produtos' @> '["VENDAS"]'::jsonb,
        'mexer no combo tirou um produto de quem ja tinha comprado';

    -- combo fora de linha nao entra em venda nova
    update public.combos set ativo = false where id = v_combo;
    begin
        perform public.dumtech_emitir_licenca(v_cliente, '{}', 'ZZ_GESTAO');
        raise exception 'vendeu um combo inativo';
    exception when raise_exception then
        if position('nao esta a venda' in sqlerrm) = 0 then raise; end if;
    end;
    raise notice '10. combo .......................... ok';
end;
$$;

-- ================================= 11. PRODUTO FORA DE LINHA (nao some) =====
do $$
declare
    v_chave text;
begin
    select l.chave into v_chave
      from public.licencas l join public.clientes c on c.id = l.cliente_id
     where c.email = 'zz2@teste.local';

    update public.produtos set ativo = false where codigo = 'VENDAS';

    -- quem ja comprou continua com o produto
    assert public.dumtech_verificar_licenca(v_chave, 'zz-combo-1')->'produtos' @> '["VENDAS"]'::jsonb,
        'tirar o produto de linha apagou o modulo de quem ja tinha comprado';

    -- mas ele nao entra em licenca nova
    begin
        perform public.dumtech_liberar_produtos(
            (select id from public.licencas where chave = v_chave), array['VENDAS']);
        raise exception 'vendeu um produto fora de linha';
    exception when raise_exception then
        if position('nao esta a venda' in sqlerrm) = 0 then raise; end if;
    end;

    update public.produtos set ativo = true where codigo = 'VENDAS';
    raise notice '11. produto fora de linha .......... ok';
end;
$$;

-- ======================================== 12. A VISAO DA ADMINISTRACAO ======
do $$
declare
    v_linha record;
begin
    select * into v_linha from public.licencas_resumo
     where cliente = 'ZZ Cliente do Combo';
    assert v_linha.situacao = 'ativa', 'situacao errada na visao';
    assert v_linha.produtos like '%ESTOQUE%', 'a visao nao lista os produtos';
    assert v_linha.computadores_ativos = 1, 'a visao nao conta os computadores';

    -- expirada e calculada, nao gravada
    assert (select situacao from public.licencas_resumo where chave = 'ZZZ1-VENC-IDAA-2222')
           = 'expirada', 'a visao nao calculou a licenca vencida';
    assert (select status from public.licencas where chave = 'ZZZ1-VENC-IDAA-2222')
           = 'ativa', 'o status gravado nao deveria virar expirada';
    raise notice '12. visao da administracao ......... ok';
end;
$$;

-- ================================================== 13. SEGURANCA (anon) ====
do $$
declare
    v_sobra text;
begin
    -- 13.1 nenhuma tabela pode estar ao alcance da chave publica
    select string_agg(t || ' (' || p || ')', ', ') into v_sobra
      from unnest(array['clientes', 'produtos', 'combos', 'combo_produtos', 'licencas',
                        'licenca_produtos', 'ativacoes', 'licenca_tentativas',
                        'licencas_resumo']) t,
           unnest(array['select', 'insert', 'update', 'delete']) p
     where has_table_privilege('anon', 'public.' || t, p);
    assert v_sobra is null, 'a chave anon ainda tem privilegio em: ' || coalesce(v_sobra, '');

    -- 13.2 a chave anon so executa as funcoes do aplicativo e do site - esta
    -- lista e a API publica INTEIRA. Fora dela, de proposito:
    -- dumtech_aprovar_pedido (dar licenca) e as internas de licenca.
    select string_agg(p.proname, ', ') into v_sobra
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public'
       and p.proname like 'dumtech%'
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
                             'dumtech_celular_parear', 'dumtech_celular_dados',
                             'dumtech_agenda_pagina', 'dumtech_agenda_horarios',
                             'dumtech_agenda_reservar', 'dumtech_agenda_cancelar',
                             'dumtech_agenda_salvar', 'dumtech_agenda_sincronizar',
                             'dumtech_mensalidade_publica', 'dumtech_cupom_publico');
    assert v_sobra is null, 'a chave anon executa funcoes demais: ' || coalesce(v_sobra, '');

    -- 13.3 RLS ligado em todas as tabelas do licenciamento
    select string_agg(c.relname, ', ') into v_sobra
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity
       and c.relname in ('clientes', 'produtos', 'combos', 'combo_produtos', 'licencas',
                         'licenca_produtos', 'ativacoes', 'licenca_tentativas');
    assert v_sobra is null, 'tabela sem RLS: ' || coalesce(v_sobra, '');

    -- 13.4 As policies que existem sao do PAINEL (administrador logado, papel
    -- `authenticated`). Nenhuma pode alcancar a chave publica: policy que vale
    -- para PUBLIC ou para `anon` derruba o desenho inteiro.
    select string_agg(format('%s em %s', p.polname, c.relname), ', ') into v_sobra
      from pg_policy p
      join pg_class c on c.oid = p.polrelid
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public'
       and c.relname in ('clientes', 'produtos', 'combos', 'combo_produtos', 'licencas',
                         'licenca_produtos', 'ativacoes', 'licenca_tentativas',
                         'comunicados', 'compra_tokens', 'pedidos_site', 'uso_diario',
                         'administradores', 'integracoes')
       and (0 = any (p.polroles)                        -- PUBLIC
            or to_regrole('anon')::oid = any (p.polroles));
    assert v_sobra is null, 'policy ao alcance da chave publica: ' || coalesce(v_sobra, '');

    raise notice '13. permissoes ..................... ok';
end;
$$;

-- 13.5 na pratica, virando a chave anon
do $$
begin
    begin
        execute 'set local role anon';
        perform 1 from public.licencas;
        raise exception 'a chave anon leu public.licencas!';
    exception when insufficient_privilege then null;
    end;

    begin
        execute 'set local role anon';
        perform public.dumtech_nova_chave();
        raise exception 'a chave anon gerou uma chave de licenca!';
    exception when insufficient_privilege then null;
    end;

    begin
        execute 'set local role anon';
        perform public.dumtech_licenca_valida('ZZZZ-ZZZZ-ZZZZ-ZZZZ');
        raise exception 'a chave anon leu a licenca inteira!';
    exception when insufficient_privilege then null;
    end;
    raise notice '13.5 chave anon barrada ............ ok';
end;
$$;

-- 13.6 ... e o que ela PRECISA fazer continua funcionando
do $$
declare
    v_chave    text;
    v_resposta jsonb;
begin
    select l.chave into v_chave
      from public.licencas l join public.clientes c on c.id = l.cliente_id
     where c.email = 'zz2@teste.local';

    -- o mesmo computador do teste 10: reativar nao ocupa vaga nova
    set local role anon;
    v_resposta := public.dumtech_ativar_licenca(v_chave, 'zz-combo-1', 'PC do cliente');
    reset role;

    assert (v_resposta->>'ok')::boolean,
        format('a chave anon nao conseguiu ativar: %s', v_resposta);
    raise notice '13.6 chave anon ativa licenca ...... ok';
end;
$$;

do $$
begin
    raise notice '';
    raise notice 'TUDO CERTO - nada foi gravado (rollback no fim do arquivo).';
end;
$$;

rollback;
