-- =============================================================================
-- Teste da migration 20261101180000: versao pendente, por cliente, forcada,
-- presenca e permissoes.
--
-- Roda dentro de uma transacao e desfaz tudo no fim: pode ser colado no SQL
-- Editor do Supabase, mesmo em producao.
-- =============================================================================

begin;

do $$
declare
    v_um      uuid;
    v_dois    uuid;
    v_chave_1 text;
    v_chave_2 text;
    v_lic_1   uuid;
    v_lic_2   uuid;
    v_tres    uuid;
    v_lic_3   uuid;
    v_pc      constant text := 'PC-PRESENCA-1';
    v_sha     constant text := repeat('b', 64);
    v_url     constant text := 'https://dumtechsolution.com/baixar/DumTech-Hub-Setup-';
    r         jsonb;
begin
    insert into public.clientes (nome, email) values ('ZZ Um', 'zz.um@teste.local') returning id into v_um;
    insert into public.clientes (nome, email) values ('ZZ Dois', 'zz.dois@teste.local') returning id into v_dois;
    select chave into v_chave_1 from public.dumtech_emitir_licenca(v_um, array['VENDAS']);
    select chave into v_chave_2 from public.dumtech_emitir_licenca(v_dois, array['VENDAS']);
    select id into v_lic_1 from public.licencas where chave = v_chave_1;
    select id into v_lic_2 from public.licencas where chave = v_chave_2;
    perform public.dumtech_ativar_licenca(v_chave_1, v_pc, 'caixa');
    perform public.dumtech_ativar_licenca(v_chave_2, v_pc, 'caixa');

    update public.hub_versoes
       set versao = '1.9.0', url = v_url || '1.9.0.exe', sha256 = repeat('a', 64), tamanho = 100,
           notas = '', obrigatoria = false, automatica = true, silenciosa = false, forcada = false
     where id = 1;
    insert into public.hub_lancamentos (versao, url, sha256, tamanho, liberada_em)
    values ('1.9.0', v_url || '1.9.0.exe', repeat('a', 64), 100, now())
    on conflict (versao) do update set liberada_em = now(), descartada_em = null;

    -- ------------------------------------------------------- a batida ------
    r := public.dumtech_hub_versao(v_chave_1, v_pc, '1.8.0');
    assert (select versao from public.hub_presenca where licenca_id = v_lic_1) = '1.8.0',
        'a batida tinha que anotar a versao';
    assert (select visto_em > now() - interval '1 minute' from public.hub_presenca where licenca_id = v_lic_1),
        'a batida tinha que anotar a hora';

    -- chave inventada ou computador alheio nao anotam nada
    perform public.dumtech_hub_versao('AAAA-AAAA-AAAA-AAAA', v_pc, '1.8.0');
    perform public.dumtech_hub_versao(v_chave_1, 'OUTRO-PC', '1.8.0');
    assert (select count(*) from public.hub_presenca where licenca_id = v_lic_1) = 1,
        'batida de quem nao e daquela chave nao pode entrar';

    -- abriu de novo depois de um tempo: comeca outra sessao; batida seguida nao
    update public.hub_presenca
       set visto_em = now() - interval '2 minutes', online_desde = now() - interval '3 hours'
     where licenca_id = v_lic_1;
    perform public.dumtech_hub_versao(v_chave_1, v_pc, '1.8.0');
    assert (select online_desde < now() - interval '2 hours' from public.hub_presenca where licenca_id = v_lic_1),
        'batida seguida nao pode reiniciar o tempo online';
    update public.hub_presenca set visto_em = now() - interval '2 hours' where licenca_id = v_lic_1;
    perform public.dumtech_hub_versao(v_chave_1, v_pc, '1.8.0');
    assert (select online_desde > now() - interval '1 minute' from public.hub_presenca where licenca_id = v_lic_1),
        'voltar depois de horas tinha que abrir nova sessao';

    -- trocou de versao: anota desde quando
    update public.hub_presenca set versao_desde = now() - interval '9 days' where licenca_id = v_lic_1;
    perform public.dumtech_hub_versao(v_chave_1, v_pc, '1.8.0');
    assert (select versao_desde < now() - interval '8 days' from public.hub_presenca where licenca_id = v_lic_1),
        'a mesma versao nao muda a data';
    perform public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0');
    assert (select versao = '1.9.0' and versao_desde > now() - interval '1 minute'
              from public.hub_presenca where licenca_id = v_lic_1),
        'versao nova tinha que anotar a data da troca';

    -- batida sem versao valida mantem a que estava
    perform public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0'' or 1=1 --');
    assert (select versao from public.hub_presenca where licenca_id = v_lic_1) = '1.9.0',
        'lixo nao pode sobrescrever a versao';

    -- soltar o computador leva a presenca junto
    perform public.dumtech_ativar_licenca(v_chave_2, 'PC-SOLTO', 'caixa2');

    -- ---------------------------------------------------- versao pendente --
    insert into public.hub_lancamentos (versao, url, sha256, tamanho, notas)
    values ('1.10.0', v_url || '1.10.0.exe', v_sha, 200, 'Correcoes');

    r := public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0');
    assert r->>'versao' = '1.9.0', 'versao pendente nao pode chegar em ninguem: ' || r::text;
    assert not (r->>'forcada')::boolean, 'nada forcado sem clique: ' || r::text;
    assert not (r->>'obrigatoria')::boolean, 'nada obrigatorio sem clique: ' || r::text;

    -- ---------------------------------------------------- um cliente so ----
    r := public.dumtech_atualizar_clientes(array[v_lic_1], '1.10.0');
    assert (r->>'clientes')::integer = 1, 'liberacao por cliente: ' || r::text;

    r := public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0');
    assert r->>'versao' = '1.10.0', 'o cliente liberado tinha que receber a pendente: ' || r::text;
    assert r->>'sha256' = v_sha, 'impressao errada: ' || r::text;
    assert r->>'url' = v_url || '1.10.0.exe', 'endereco errado: ' || r::text;
    assert not (r->>'obrigatoria')::boolean, 'liberar nao e forcar: ' || r::text;
    assert length(r->>'licenca') = 32, 'a impressao da licenca segue na resposta: ' || r::text;

    r := public.dumtech_hub_versao(v_chave_2, v_pc, '1.9.0');
    assert r->>'versao' = '1.9.0', 'o outro cliente nao recebe: ' || r::text;

    r := public.dumtech_hub_versao('AAAA-AAAA-AAAA-AAAA', v_pc, '1.9.0');
    assert r->>'versao' = '1.9.0', 'quem nao e cliente nao recebe a pendente: ' || r::text;

    -- ------------------------------------------------- forcar um cliente ---
    perform public.dumtech_atualizar_clientes(array[v_lic_1], '1.10.0', true);
    r := public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0');
    assert (r->>'forcada')::boolean, 'forcar nao chegou: ' || r::text;
    assert (r->>'obrigatoria')::boolean, 'Hub antigo precisa do aviso obrigatorio: ' || r::text;
    assert (r->>'silenciosa')::boolean, 'Hub 1.5.1+ precisa instalar ao fechar: ' || r::text;

    -- Hub 1.5.1 a 1.9.0: depois dos primeiros minutos ele ja comecou a baixar, e
    -- o manifesto deixa de ser silencioso para o aviso aparecer
    update public.hub_presenca set online_desde = now() - interval '1 hour' where licenca_id = v_lic_1;
    update public.hub_liberacoes set criado_em = now() - interval '10 minutes' where licenca_id = v_lic_1;
    r := public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0');
    assert not (r->>'silenciosa')::boolean, 'Hub antigo precisa mostrar o aviso: ' || r::text;
    assert (r->>'obrigatoria')::boolean and (r->>'forcada')::boolean, 'continua obrigatoria: ' || r::text;

    -- ordem recente, com o Hub aberto ha horas: ainda precisa baixar
    update public.hub_liberacoes set criado_em = now() - interval '1 minute' where licenca_id = v_lic_1;
    r := public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0');
    assert (r->>'silenciosa')::boolean, 'a ordem nova tem que comecar o download: ' || r::text;

    -- ordem antiga, com o Hub recem aberto: tambem precisa baixar nesta sessao
    update public.hub_liberacoes set criado_em = now() - interval '2 days' where licenca_id = v_lic_1;
    update public.hub_presenca set visto_em = now() - interval '1 hour' where licenca_id = v_lic_1;
    r := public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0');
    assert (r->>'silenciosa')::boolean, 'abrir o Hub tem que comecar o download: ' || r::text;

    -- sem obrigacao, nada disso muda a resposta
    perform public.dumtech_atualizar_clientes(array[v_lic_1], '1.10.0', false);
    update public.hub_liberacoes set criado_em = now() - interval '10 minutes' where licenca_id = v_lic_1;
    r := public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0');
    assert not (r->>'silenciosa')::boolean and not (r->>'obrigatoria')::boolean, 'liberar nao obriga: ' || r::text;
    perform public.dumtech_atualizar_clientes(array[v_lic_1], '1.10.0', true);

    -- o freio do painel vale tambem aqui
    update public.hub_versoes set automatica = false where id = 1;
    r := public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0');
    assert not (r->>'automatica')::boolean, 'o freio nao valeu para o cliente: ' || r::text;
    update public.hub_versoes set automatica = true where id = 1;

    -- forcar a versao que todos ja recebem, para quem ficou para tras
    perform public.dumtech_atualizar_clientes(array[v_lic_2], '1.9.0', true);
    r := public.dumtech_hub_versao(v_chave_2, v_pc, '1.8.0');
    assert r->>'versao' = '1.9.0' and (r->>'forcada')::boolean, 'forcar a publicada: ' || r::text;
    delete from public.hub_liberacoes where licenca_id = v_lic_2;
    r := public.dumtech_hub_versao(v_chave_2, v_pc, '1.8.0');
    assert not (r->>'forcada')::boolean, 'cancelar tirou a obrigacao: ' || r::text;

    -- ---------------------------------------------------- atualizar todos --
    insert into public.hub_lancamentos (versao, url, sha256) values ('1.11.0', v_url || '1.11.0.exe', repeat('e', 64));
    insert into public.clientes (nome, email) values ('ZZ Teste', 'zz.teste@teste.local') returning id into v_tres;
    perform public.dumtech_emitir_licenca(v_tres, array['VENDAS']);
    select id into v_lic_3 from public.licencas where cliente_id = v_tres;
    perform public.dumtech_atualizar_clientes(array[v_lic_3], '1.11.0', false);
    perform public.dumtech_atualizar_clientes(array[v_lic_2], '1.10.0', false);
    perform public.dumtech_atualizar_todos('1.10.0');
    assert exists (select 1 from public.hub_liberacoes where licenca_id = v_lic_3 and versao = '1.11.0'),
        'quem testa uma versao mais nova nao pode perder o pedido';
    delete from public.hub_liberacoes where licenca_id = v_lic_3;
    r := public.dumtech_hub_versao(v_chave_2, v_pc, '1.9.0');
    assert r->>'versao' = '1.10.0', 'atualizar todos nao chegou: ' || r::text;
    assert not (r->>'obrigatoria')::boolean and not (r->>'forcada')::boolean,
        'atualizar todos nao obriga: ' || r::text;
    assert (select liberada_em is not null and forcada_em is null from public.hub_lancamentos where versao = '1.10.0'),
        'a versao tinha que ficar marcada como liberada';
    assert not exists (select 1 from public.hub_liberacoes where licenca_id = v_lic_2),
        'o pedido coberto pela geral sai';
    r := public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0');
    assert (r->>'forcada')::boolean, 'quem foi forcado nesta versao continua forcado: ' || r::text;

    -- ------------------------------------------------------ forcar todos ---
    perform public.dumtech_atualizar_todos('1.10.0', true);
    r := public.dumtech_hub_versao(v_chave_2, v_pc, '1.9.0');
    assert (r->>'forcada')::boolean and (r->>'obrigatoria')::boolean and (r->>'silenciosa')::boolean,
        'forcar todos: ' || r::text;
    r := public.dumtech_hub_versao('AAAA-AAAA-AAAA-AAAA', v_pc, '1.9.0');
    assert (r->>'forcada')::boolean, 'forcar todos vale para Hub sem licenca: ' || r::text;

    -- a mesma troca no forcar todos, contada da ordem geral
    update public.hub_versoes set atualizado_em = now() - interval '10 minutes' where id = 1;
    update public.hub_presenca set online_desde = now() - interval '1 hour' where licenca_id = v_lic_2;
    r := public.dumtech_hub_versao(v_chave_2, v_pc, '1.9.0');
    assert not (r->>'silenciosa')::boolean and (r->>'obrigatoria')::boolean and (r->>'forcada')::boolean,
        'forcar todos tem que aparecer no Hub antigo: ' || r::text;

    -- sem computador ativado nao ha sessao para contar: segue instalando ao fechar
    r := public.dumtech_hub_versao('AAAA-AAAA-AAAA-AAAA', v_pc, '1.9.0');
    assert (r->>'silenciosa')::boolean, 'Hub sem licenca segue silencioso: ' || r::text;

    -- versao antiga nao volta por aqui
    begin
        perform public.dumtech_atualizar_todos('1.9.0');
        assert false, 'lancou versao mais antiga que a publicada';
    exception when raise_exception then
        null;
    end;

    -- ---------------------------------------------------------- recolher ---
    r := public.dumtech_recolher_versao('1.10.0');
    assert r->>'voltou_para' = '1.9.0', 'recolher: ' || r::text;
    r := public.dumtech_hub_versao(v_chave_2, v_pc, '1.9.0');
    assert r->>'versao' = '1.9.0' and not (r->>'forcada')::boolean, 'recolher nao voltou: ' || r::text;
    assert (select liberada_em is null from public.hub_lancamentos where versao = '1.10.0'),
        'a recolhida volta a ser pendente';
    assert not exists (select 1 from public.hub_liberacoes where versao = '1.10.0'),
        'recolher tira tambem as liberacoes por cliente';

    -- --------------------------------------------------------- descartar ---
    perform public.dumtech_atualizar_clientes(array[v_lic_1], '1.10.0', true);
    perform public.dumtech_descartar_versao('1.10.0');
    r := public.dumtech_hub_versao(v_chave_1, v_pc, '1.9.0');
    assert r->>'versao' = '1.9.0' and not (r->>'forcada')::boolean, 'descartar nao tirou: ' || r::text;
    begin
        perform public.dumtech_atualizar_todos('1.10.0');
        assert false, 'lancou versao descartada';
    exception when raise_exception then
        null;
    end;
    begin
        perform public.dumtech_descartar_versao('1.9.0');
        assert false, 'descartou versao ja liberada';
    exception when raise_exception then
        null;
    end;

    -- ---------------------------------------------------- a visao da lista --
    update public.clientes set etiquetas = array['vip'], proximo_contato = current_date where id = v_um;
    insert into public.cliente_notas (cliente_id, texto, autor) values (v_um, 'Ligar na terça', 'eric');
    assert (select anotacoes = 1 and etiquetas = array['vip'] from public.painel_gestao where cliente_id = v_um),
        'a visao da gestao nao trouxe etiqueta e anotacao';

    -- apagar o computador leva a presenca junto
    delete from public.ativacoes where licenca_id = v_lic_1 and maquina = v_pc;
    assert not exists (select 1 from public.hub_presenca where licenca_id = v_lic_1),
        'computador solto ficou na presenca';

    raise notice 'atualizacoes_test: tudo certo';
end;
$$;

do $$
begin
    assert public.dumtech_versao_numeros('1.10.0') > public.dumtech_versao_numeros('1.9.9'), '1.10.0 > 1.9.9';
    assert public.dumtech_versao_numeros('1.10') = public.dumtech_versao_numeros('1.10.0'), '1.10 = 1.10.0';
    assert public.dumtech_versao_numeros('') < public.dumtech_versao_numeros('0.0.1'), 'vazio perde de todas';

    -- a chave publica nao enxerga nada disto
    assert not has_table_privilege('anon', 'public.hub_presenca', 'select'), 'anon le a presenca';
    assert not has_table_privilege('anon', 'public.hub_lancamentos', 'select'), 'anon le os lancamentos';
    assert not has_table_privilege('anon', 'public.hub_liberacoes', 'select'), 'anon le as liberacoes';
    assert not has_table_privilege('anon', 'public.cliente_notas', 'select'), 'anon le as anotacoes';
    assert not has_table_privilege('anon', 'public.painel_gestao', 'select'), 'anon le a gestao';
    assert not has_function_privilege('anon', 'public.dumtech_atualizar_todos(text, boolean)', 'execute'),
        'anon lanca versao';
    assert not has_function_privilege('anon', 'public.dumtech_atualizar_clientes(uuid[], text, boolean)', 'execute'),
        'anon forca cliente';
    assert not has_function_privilege('anon', 'public.dumtech_recolher_versao(text)', 'execute'), 'anon recolhe';
    assert not has_function_privilege('anon', 'public.dumtech_descartar_versao(text)', 'execute'), 'anon descarta';

    -- o painel nao apaga historico nem grava presenca
    assert not has_table_privilege('authenticated', 'public.hub_presenca', 'insert'), 'painel grava presenca';
    assert not has_table_privilege('authenticated', 'public.hub_lancamentos', 'delete'), 'painel apaga lancamento';
    assert has_table_privilege('authenticated', 'public.hub_liberacoes', 'delete'), 'painel precisa cancelar';
end;
$$;

-- conta comum, sem ser administrador: logada, mas nao lanca nem le nada
do $$
declare
    v_comum uuid := gen_random_uuid();
    v_licenca uuid;
begin
    insert into public.hub_lancamentos (versao, url, sha256)
    values ('9.9.9', 'https://dumtechsolution.com/baixar/x.exe', repeat('c', 64));
    select id into v_licenca from public.licencas limit 1;

    perform set_config('request.jwt.claim.sub', v_comum::text, true);
    perform set_config('request.jwt.claims',
                       jsonb_build_object('sub', v_comum, 'role', 'authenticated', 'aal', 'aal2')::text, true);
    set local role authenticated;

    begin
        perform public.dumtech_atualizar_todos('9.9.9', true);
        assert false, 'conta comum forcou todos';
    exception when raise_exception then
        null;
    end;
    begin
        perform public.dumtech_atualizar_clientes(array[v_licenca], '9.9.9', true);
        assert false, 'conta comum forcou um cliente';
    exception when raise_exception then
        null;
    end;
    assert (select count(*) from public.hub_lancamentos) = 0, 'conta comum viu os lancamentos';
    assert (select count(*) from public.hub_presenca) = 0, 'conta comum viu a presenca';

    reset role;
    perform set_config('request.jwt.claim.sub', '', true);
    perform set_config('request.jwt.claims', '', true);
end;
$$;

-- o administrador com 2 fatores: cada botao do painel, com as permissoes reais
do $$
declare
    v_admin   uuid;
    v_cliente uuid;
    v_chave   text;
    v_licenca uuid;
    r         jsonb;
begin
    -- em producao o administrador precisa existir em auth.users: usa o que ja ha
    select user_id into v_admin from public.administradores limit 1;
    if v_admin is null then
        v_admin := gen_random_uuid();
        insert into public.administradores (user_id, nome) values (v_admin, 'ZZ Dona DumTech');
    end if;
    insert into public.clientes (nome, email) values ('ZZ Tres', 'zz.tres@teste.local') returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);
    select id into v_licenca from public.licencas where chave = v_chave;
    update public.hub_versoes
       set versao = '9.9.8', url = 'https://dumtechsolution.com/baixar/a.exe', sha256 = repeat('a', 64)
     where id = 1;
    insert into public.hub_lancamentos (versao, url, sha256, liberada_em)
    values ('9.9.8', 'https://dumtechsolution.com/baixar/a.exe', repeat('a', 64), now());

    perform set_config('request.jwt.claim.sub', v_admin::text, true);
    perform set_config('request.jwt.claims',
                       format('{"sub":"%s","aal":"aal2","role":"authenticated","email":"dona@zz.local"}', v_admin),
                       true);
    set local role authenticated;

    r := public.dumtech_atualizar_clientes(array[v_licenca], '9.9.9', true);
    assert (r->>'clientes')::integer = 1, 'admin nao forcou o cliente: ' || r::text;
    delete from public.hub_liberacoes where licenca_id = v_licenca;
    assert not exists (select 1 from public.hub_liberacoes where licenca_id = v_licenca), 'admin nao cancelou';

    r := public.dumtech_atualizar_todos('9.9.9', false);
    assert r->>'versao' = '9.9.9', 'admin nao atualizou todos: ' || r::text;
    assert (select versao from public.hub_versoes where id = 1) = '9.9.9', 'a publicada nao mudou';

    r := public.dumtech_atualizar_todos('9.9.9', true);
    assert (select forcada from public.hub_versoes where id = 1), 'admin nao forcou todos';

    r := public.dumtech_recolher_versao('9.9.9');
    assert r->>'voltou_para' = '9.9.8', 'admin nao recolheu: ' || r::text;

    r := public.dumtech_descartar_versao('9.9.9');
    assert r->>'versao' = '9.9.9', 'admin nao descartou: ' || r::text;

    -- as telas
    assert (select count(*) from public.hub_lancamentos) >= 2, 'admin nao le os lancamentos';
    perform 1 from public.hub_presenca;
    assert (select count(*) from public.painel_gestao where cliente_id = v_cliente) = 1, 'admin nao le a gestao';

    insert into public.hub_lancamentos (versao, url, sha256)
    values ('9.9.10', 'https://dumtechsolution.com/baixar/b.exe', repeat('d', 64));
    update public.clientes set etiquetas = array['vip'], proximo_contato = current_date where id = v_cliente;
    insert into public.cliente_notas (cliente_id, texto, autor) values (v_cliente, 'Teste', 'dona');
    delete from public.cliente_notas where cliente_id = v_cliente;

    -- e quem mexeu fica registrado
    assert (select count(*) from public.auditoria
             where tabela = 'hub_versoes' and origem = 'painel' and quem = v_admin) >= 1,
        'lancar para todos tinha que aparecer em Quem mexeu em quê';

    reset role;
    perform set_config('request.jwt.claim.sub', '', true);
    perform set_config('request.jwt.claims', '', true);
end;
$$;

rollback;
