-- =============================================================================
-- Teste do tempo real e da blindagem (migration 20260912180000).
--
-- Roda inteiro dentro de uma transacao e desfaz tudo no fim: pode ser colado no
-- SQL Editor do Supabase, mesmo em producao.
--
-- Onde NAO existe o schema `realtime` (testes locais), o teste cria um de
-- mentira para capturar os avisos. No Supabase ele existe de verdade, e essa
-- parte e pulada - la o aviso vai para o Realtime, que nao se le por SQL.
-- =============================================================================

begin;

-- ================================================= 1. OS GATILHOS EXISTEM ===
do $$
declare
    v_falta text;
begin
    select string_agg(t, ', ') into v_falta
      from unnest(array['produtos', 'combos', 'combo_produtos']) t
     where not exists (select 1 from pg_trigger g
                        where g.tgrelid = ('public.' || t)::regclass
                          and g.tgname = 'trg_tempo_real_catalogo');
    assert v_falta is null, 'sem aviso de catalogo em: ' || coalesce(v_falta, '');

    select string_agg(t, ', ') into v_falta
      from unnest(array['clientes', 'licencas', 'licenca_produtos', 'ativacoes',
                        'pedidos_site', 'comunicados', 'produtos', 'combos',
                        'combo_produtos']) t
     where not exists (select 1 from pg_trigger g
                        where g.tgrelid = ('public.' || t)::regclass
                          and g.tgname = 'trg_tempo_real_painel');
    assert v_falta is null, 'sem aviso de painel em: ' || coalesce(v_falta, '');
    raise notice '1. gatilhos de tempo real ......... ok';
end;
$$;

-- ============================================ 2. O AVISO SAI, E SEM DADOS ===
do $$
declare
    v_local boolean := to_regnamespace('realtime') is null;
    v_aviso record;
begin
    if not v_local then
        raise notice '2. avisos .......................... pulado (Realtime de verdade)';
        return;
    end if;

    create schema realtime;
    create table realtime.enviados (payload jsonb, evento text, topico text, privado boolean);
    create function realtime.send(p_payload jsonb, p_evento text, p_topico text, p_privado boolean)
    returns void language sql as
    $f$ insert into realtime.enviados values (p_payload, p_evento, p_topico, p_privado) $f$;

    -- mudar preco avisa o site (publico) E o painel (privado)
    update public.produtos set preco = preco + 1 where codigo = 'ESTOQUE';

    select * into v_aviso from realtime.enviados where topico = 'catalogo';
    assert found, 'mudar o preco nao avisou o site';
    assert v_aviso.privado = false, 'o canal do catalogo precisa ser publico (o site nao tem login)';
    assert v_aviso.evento = 'mudou', 'evento errado';
    assert v_aviso.payload = jsonb_build_object('tabela', 'produtos', 'op', 'update'),
        format('o aviso deveria dizer so a tabela e a operacao, veio: %s', v_aviso.payload);

    select * into v_aviso from realtime.enviados where topico = 'painel';
    assert found and v_aviso.privado, 'o canal do painel precisa ser privado';

    -- UPDATE de varias linhas = um aviso por canal
    delete from realtime.enviados;
    update public.produtos set preco = preco where codigo in ('ESTOQUE', 'VENDAS', 'AGENDA');
    assert (select count(*) from realtime.enviados where topico = 'catalogo') = 1,
        'um comando deveria gerar um aviso so';

    -- pedido novo avisa o painel, nunca o site
    delete from realtime.enviados;
    perform public.dumtech_registrar_pedido('ZZ Tempo Real', 'zz.tempo@teste.local', '',
                                            array['AGENDA']);
    assert exists (select 1 from realtime.enviados
                    where topico = 'painel' and payload->>'tabela' = 'pedidos_site'),
        'pedido novo nao avisou o painel';
    assert not exists (select 1 from realtime.enviados where topico = 'catalogo'),
        'pedido novo nao muda o catalogo';

    -- se o Realtime falhar, o preco grava do mesmo jeito
    create or replace function realtime.send(p_payload jsonb, p_evento text, p_topico text, p_privado boolean)
    returns void language plpgsql as
    $f$ begin raise exception 'realtime fora do ar'; end $f$;
    update public.produtos set preco = 321.00 where codigo = 'AGENDA';
    assert (select preco from public.produtos where codigo = 'AGENDA') = 321.00,
        'uma falha no tempo real impediu a gravacao';

    drop schema realtime cascade;
    raise notice '2. avisos sem dados, sem travar .... ok';
end;
$$;

-- ================================================ 3. LIMITE POR ENDERECO ====
do $$
declare
    v_resposta jsonb;
    v_i integer;
begin
    -- sem cabecalho (SQL Editor) nao ha endereco e nao ha limite
    assert public.dumtech_ip_do_pedido() = '', 'fora da API o endereco deveria vir vazio';
    assert public.dumtech_dentro_do_limite('zz', '', 0, interval '1 hour'),
        'sem endereco nao pode bloquear';

    -- a borda do Supabase manda o endereco nos cabecalhos
    perform set_config('request.headers',
        '{"cf-connecting-ip":"203.0.113.9","x-forwarded-for":"198.51.100.1, 10.0.0.1"}', true);
    assert public.dumtech_ip_do_pedido() = '203.0.113.9', 'deveria preferir o cf-connecting-ip';
    perform set_config('request.headers', '{"x-forwarded-for":"198.51.100.1, 10.0.0.1"}', true);
    assert public.dumtech_ip_do_pedido() = '198.51.100.1', 'sem cf, vale o primeiro x-forwarded-for';
    perform set_config('request.headers', 'isto nao e json', true);
    assert public.dumtech_ip_do_pedido() = '', 'cabecalho estragado nao pode derrubar a funcao';

    -- 12 pedidos por hora do mesmo endereco, cada um com um e-mail diferente
    perform set_config('request.headers', '{"cf-connecting-ip":"203.0.113.77"}', true);
    for v_i in 1..12 loop
        v_resposta := public.dumtech_registrar_pedido('ZZ Enxurrada', format('zz.enx%s@teste.local', v_i),
                                                      '', array['AGENDA']);
        assert (v_resposta->>'ok')::boolean, format('pedido %s recusado cedo demais: %s', v_i, v_resposta);
    end loop;
    v_resposta := public.dumtech_registrar_pedido('ZZ Enxurrada', 'zz.enx13@teste.local', '', array['AGENDA']);
    assert v_resposta->>'erro' = 'muitas_tentativas', format('o 13o pedido deveria parar: %s', v_resposta);

    -- 6 por hora com o mesmo e-mail, mesmo trocando de endereco
    for v_i in 1..6 loop
        perform set_config('request.headers', format('{"cf-connecting-ip":"192.0.2.%s"}', v_i), true);
        v_resposta := public.dumtech_registrar_pedido('ZZ Mesmo', 'zz.mesmo@teste.local', '', array['AGENDA']);
        assert (v_resposta->>'ok')::boolean, format('pedido %s recusado cedo demais: %s', v_i, v_resposta);
    end loop;
    perform set_config('request.headers', '{"cf-connecting-ip":"192.0.2.99"}', true);
    v_resposta := public.dumtech_registrar_pedido('ZZ Mesmo', 'zz.mesmo@teste.local', '', array['AGENDA']);
    assert v_resposta->>'erro' = 'muitas_tentativas', 'o 7o pedido do mesmo e-mail deveria parar';

    -- as funcoes de licenca, de token e de cadastro tambem contam
    perform set_config('request.headers', '{"cf-connecting-ip":"203.0.113.200"}', true);
    insert into public.limites_de_taxa (acao, quem, janela, vezes)
    values ('licenca_ip', '203.0.113.200', date_bin(interval '1 hour', now(), timestamptz '2000-01-01 00:00:00+00'), 120),
           ('token_ip', '203.0.113.200', date_bin(interval '1 hour', now(), timestamptz '2000-01-01 00:00:00+00'), 60),
           ('identificar_ip', '203.0.113.200', date_bin(interval '1 hour', now(), timestamptz '2000-01-01 00:00:00+00'), 30);
    assert public.dumtech_ativar_licenca('ZZZZ-ZZZZ-ZZZZ-ZZZZ', 'zz-pc')->>'erro' = 'muitas_tentativas',
        'ativar nao respeitou o limite';
    assert public.dumtech_verificar_licenca('ZZZZ-ZZZZ-ZZZZ-ZZZZ', 'zz-pc')->>'erro' = 'muitas_tentativas',
        'verificar nao respeitou o limite';
    assert public.dumtech_desativar_licenca('ZZZZ-ZZZZ-ZZZZ-ZZZZ', 'zz-pc')->>'erro' = 'muitas_tentativas',
        'desativar nao respeitou o limite';
    assert public.dumtech_token_compra('', '', 'ZZ', 'zz.tok@teste.local')->>'erro' = 'muitas_tentativas',
        'token nao respeitou o limite';
    assert public.dumtech_identificar_cliente('ZZ', 'zz.id@teste.local')->>'erro' = 'muitas_tentativas',
        'identificar nao respeitou o limite';

    -- outro endereco continua passando
    perform set_config('request.headers', '{"cf-connecting-ip":"203.0.113.201"}', true);
    assert public.dumtech_ativar_licenca('ZZZZ-ZZZZ-ZZZZ-ZZZZ', 'zz-pc')->>'erro' = 'nao_encontrada',
        'o limite de um endereco nao pode travar os outros';

    perform set_config('request.headers', '', true);
    raise notice '3. limites por endereco e e-mail ... ok';
end;
$$;

-- ============================================ 4. APROVAR TRAVA O PEDIDO =====
do $$
begin
    assert pg_get_functiondef('public.dumtech_aprovar_pedido(uuid,integer,text,date)'::regprocedure)
           ~* 'from public\.pedidos_site where id = p_pedido_id for update',
        'aprovar precisa travar o pedido - senao dois cliques emitem duas licencas';
    raise notice '4. aprovar trava o pedido .......... ok';
end;
$$;

-- ===================================================== 5. LINK SO HTTPS =====
do $$
declare
    v_link text;
begin
    foreach v_link in array array['file:///C:/Users/Public/x.exe', 'javascript:alert(1)',
                                  'http://dumtech.com.br', '\\servidor\pasta\x.exe',
                                  'https://ok.com/ com espaco'] loop
        begin
            insert into public.comunicados (titulo, link) values ('ZZ Link', v_link);
            raise exception 'aceitou link perigoso: %', v_link;
        exception when check_violation then null;
        end;
    end loop;

    insert into public.comunicados (titulo, link) values ('ZZ Link bom', 'https://dumtech.com.br/oferta?x=1');
    insert into public.comunicados (titulo, link) values ('ZZ Sem link', '');
    raise notice '5. link de anuncio so https ........ ok';
end;
$$;

-- ==================================================== 6. PRIVILEGIOS ========
do $$
declare
    v_sobra text;
begin
    select string_agg(c.relname || ' (' || r || ')', ', ') into v_sobra
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
      cross join unnest(array['anon', 'authenticated']) r
     where n.nspname = 'public' and c.relkind in ('r', 'p')
       and has_table_privilege(r, c.oid, 'truncate');
    assert v_sobra is null, 'TRUNCATE (que ignora o RLS) sobrou em: ' || coalesce(v_sobra, '');

    assert not has_table_privilege('anon', 'public.limites_de_taxa', 'select'),
        'a anon nao pode ver os contadores';
    assert not has_table_privilege('authenticated', 'public.limites_de_taxa', 'select'),
        'usuario logado nao pode ver os contadores';
    assert not has_function_privilege('anon', 'public.dumtech_dentro_do_limite(text,text,integer,interval)', 'execute'),
        'a anon nao pode mexer no contador';
    assert not has_function_privilege('anon', 'public.dumtech_avisar_mudanca()', 'execute'),
        'a anon nao pode disparar aviso';

    if to_regclass('realtime.messages') is not null then
        assert exists (select 1 from pg_policies
                        where schemaname = 'realtime' and tablename = 'messages'
                          and policyname = 'dumtech_admin_ouve_painel'),
            'falta a policy do canal privado do painel';
    end if;
    raise notice '6. privilegios ..................... ok';
end;
$$;

do $$
begin
    raise notice '';
    raise notice 'TUDO CERTO - nada foi gravado (rollback no fim do arquivo).';
end;
$$;

rollback;
