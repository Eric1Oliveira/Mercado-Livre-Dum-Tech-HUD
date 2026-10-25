-- =============================================================================
-- Teste da migration 20261019120000: o painel ve e controla teste gratis,
-- celular e uso - e continua sem alcancar o conteudo do celular do cliente.
-- Roda numa transacao e desfaz tudo no fim.
-- =============================================================================

begin;

do $$
declare
    v_admin    constant uuid := '11111111-1111-1111-1111-111111111111';
    v_comum    constant uuid := '22222222-2222-2222-2222-222222222222';
    v_maquina  constant text := 'AAAA-BBBB-CCCC-USO1';
    v_pc       constant text := repeat('e', 32);
    v_hoje     constant date := (now() at time zone 'America/Sao_Paulo')::date;
    v_cliente  uuid;
    v_chave    text;
    v_licenca  uuid;
    v_agenda   uuid;
    v_aparelho uuid;
    v_token    text;
    v_marca    text;
    v_antiga   text;
    v_quando   timestamptz;
    v_quantos  integer;
    v_linha    record;
    r          jsonb;
begin
    insert into public.administradores (user_id, nome) values (v_admin, 'ZZ Dona DumTech')
    on conflict do nothing;
    insert into public.clientes (nome, email) values ('Oficina ZZ Uso', 'zz.uso@teste.local')
    returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);
    select id into v_licenca from public.licencas where chave = v_chave;
    perform public.dumtech_ativar_licenca(v_chave, v_maquina, 'caixa');
    update public.ativacoes set computador = v_pc where licenca_id = v_licenca;
    select id into v_agenda from public.produtos where codigo = 'AGENDA';

    -- 1. licenca SEM teste: a impressao e a mesma da formula antiga - senao
    -- todo Hub instalado reconferiria a licenca no dia desta migration
    v_marca := public.dumtech_licenca_marca(v_chave, v_maquina);
    select md5(concat_ws('|',
               l.status, l.max_computadores::text, coalesce(l.expira_em::text, ''), coalesce(l.tipo, ''),
               (select string_agg(coalesce(lp.produto_id::text, '') || ':' || coalesce(lp.combo_id::text, ''),
                                  ',' order by lp.produto_id, lp.combo_id)
                  from public.licenca_produtos lp where lp.licenca_id = l.id),
               (select max(p.atualizado_em)::text from public.produtos p
                  join public.licenca_produtos lp on lp.produto_id = p.id where lp.licenca_id = l.id),
               (select max(c.atualizado_em)::text from public.combos c
                  join public.licenca_produtos lp on lp.combo_id = c.id where lp.licenca_id = l.id),
               (select count(*)::text from public.ativacoes a
                 where a.licenca_id = l.id and a.maquina = public.dumtech_normalizar(v_maquina, 64)),
               (select pc.atualizado_em::text from public.pagamento_config pc where pc.licenca_id = l.id)))
      into v_antiga
      from public.licencas l where l.id = v_licenca;
    assert v_marca <> '' and v_marca = v_antiga, 'licenca sem teste mudou de impressao';

    -- 2. o Hub pede o teste da Agenda: a impressao muda (o Hub busca a licenca)
    r := public.dumtech_iniciar_teste(v_chave, v_maquina, 'AGENDA');
    assert (r->>'ok')::boolean, 'teste recusado: ' || r::text;
    assert public.dumtech_licenca_marca(v_chave, v_maquina) <> v_marca, 'teste novo nao mudou a impressao';
    v_marca := public.dumtech_licenca_marca(v_chave, v_maquina);

    -- uso: a Agenda aberta ANTES do teste nao conta como uso do teste
    insert into public.uso_diario (licenca_id, maquina, dia, produto_codigo, aberturas) values
        (v_licenca, v_maquina, v_hoje, 'AGENDA', 3),
        (v_licenca, v_maquina, v_hoje - 3, 'AGENDA', 9),
        (v_licenca, v_maquina, v_hoje, 'VENDAS', 5),
        (v_licenca, v_maquina, v_hoje - 40, 'VENDAS', 2);

    -- um celular pareado, com resumo publicado (o conteudo e da empresa)
    r := public.dumtech_celular_iniciar(v_chave, v_maquina, v_pc);
    r := public.dumtech_celular_parear(r->>'codigo', 'Moto G da Ana');
    assert (r->>'ok')::boolean, 'pareamento recusado: ' || r::text;
    v_token := r->>'token';
    assert public.dumtech_celular_dados(v_token) ->> 'ok' = 'true', 'celular pareado nao abriu';
    select id into v_aparelho from public.celular_aparelhos where licenca_id = v_licenca;
    r := public.dumtech_celular_publicar(v_chave, v_maquina, v_pc,
            '{"secoes": [{"app": "vendas", "itens": ["Cliente secreto: R$ 900"]}]}'::jsonb);
    assert (r->>'ok')::boolean, 'resumo recusado: ' || r::text;

    -- o cliente clicou em "Comprar" no Hub
    r := public.dumtech_token_compra(v_chave, v_maquina, '', '');
    assert (r->>'ok')::boolean, 'token recusado: ' || r::text;

    -- ================================================ usuario comum ========
    perform set_config('request.jwt.claim.sub', v_comum::text, true);
    perform set_config('request.jwt.claims',
                       format('{"sub":"%s","aal":"aal2","role":"authenticated"}', v_comum), true);
    set local role authenticated;

    update public.licenca_testes set termina_em = now() + interval '1 year';
    get diagnostics v_quantos = row_count;
    assert v_quantos = 0, 'usuario comum estendeu teste';
    update public.celular_aparelhos set revogado_em = now();
    get diagnostics v_quantos = row_count;
    assert v_quantos = 0, 'usuario comum desconectou celular';
    select count(*) into v_quantos from public.painel_testes;
    assert v_quantos = 0, 'usuario comum viu os testes';
    reset role;

    -- ================================================ administrador ========
    perform set_config('request.jwt.claim.sub', v_admin::text, true);
    perform set_config('request.jwt.claims',
                       format('{"sub":"%s","aal":"aal2","role":"authenticated","email":"dona@zz.local"}', v_admin),
                       true);
    set local role authenticated;

    -- 3. as visoes
    select * into v_linha from public.painel_testes where licenca_id = v_licenca and codigo = 'AGENDA';
    assert v_linha.aberturas = 3, format('uso durante o teste errado: %s', v_linha.aberturas);
    assert v_linha.dias_de_uso = 1 and v_linha.ultimo_uso = v_hoje, 'dias de uso do teste errados';
    assert not v_linha.comprou, 'teste sem compra marcado como comprado';

    select aberturas, clientes into v_linha from public.painel_uso_dias where dia = v_hoje;
    assert v_linha.aberturas >= 8 and v_linha.clientes >= 1, format('uso do dia errado: %s', v_linha);

    -- a faixa: 30 dias, do mais antigo ate hoje; o uso de 40 dias atras fica fora
    select ate, ultimos_30 into v_linha from public.painel_uso_por_cliente where cliente_id = v_cliente;
    assert v_linha.ate = v_hoje, format('a faixa nao termina hoje: %s', v_linha.ate);
    assert cardinality(v_linha.ultimos_30) = 30, 'a faixa nao tem 30 dias';
    assert v_linha.ultimos_30[30] = 8 and v_linha.ultimos_30[27] = 9,
        format('a faixa pos o uso no dia errado: %s', v_linha.ultimos_30);
    assert (select sum(x) from unnest(v_linha.ultimos_30) x) = 17, 'a faixa contou uso de fora dos 30 dias';

    select * into v_linha from public.painel_modulos_da_licenca
     where licenca_id = v_licenca and codigo = 'VENDAS';
    assert v_linha.situacao = 'ativa', 'situacao da licenca faltando';
    assert v_linha.aberturas_30d = 5, format('aberturas de 30 dias erradas: %s', v_linha.aberturas_30d);
    assert v_linha.ultimo_uso = v_hoje, 'ultimo uso do modulo errado';

    -- 4. estender o teste
    update public.licenca_testes set termina_em = termina_em + interval '7 days'
     where licenca_id = v_licenca and produto_id = v_agenda;
    get diagnostics v_quantos = row_count;
    assert v_quantos = 1, 'o administrador nao estendeu o teste';

    -- 5. dar teste pelo painel: o comeco e sempre agora
    insert into public.licenca_testes (licenca_id, produto_id, termina_em)
    select v_licenca, p.id, now() + interval '7 days' from public.produtos p where p.codigo = 'FINANCEIRO';
    begin
        insert into public.licenca_testes (licenca_id, produto_id, iniciado_em, termina_em)
        select v_licenca, p.id, now() - interval '30 days', now() from public.produtos p where p.codigo = 'ESTOQUE';
        raise exception 'o painel escolheu o comeco do teste';
    exception when insufficient_privilege then null;
    end;
    begin
        delete from public.licenca_testes where licenca_id = v_licenca;
        raise exception 'o painel apagou o historico de testes';
    exception when insufficient_privilege then null;
    end;

    -- 6. celular: ve QUANDO publicou, nunca O QUE
    select e.atualizado_em into v_quando from public.celular_espelhos e where e.licenca_id = v_licenca;
    assert v_quando is not null, 'o painel nao ve quando o resumo foi publicado';
    begin
        perform e.dados from public.celular_espelhos e where e.licenca_id = v_licenca;
        raise exception 'o painel leu o conteudo do celular do cliente!';
    exception when insufficient_privilege then null;
    end;

    update public.celular_aparelhos set revogado_em = now() where id = v_aparelho;
    get diagnostics v_quantos = row_count;
    assert v_quantos = 1, 'o painel nao desconectou o celular';
    begin
        update public.celular_aparelhos set token_hash = 'x' where id = v_aparelho;
        raise exception 'o painel trocou o token do celular!';
    exception when insufficient_privilege then null;
    end;

    -- 7. loja pelo Hub: quem e quando, sem o codigo de compra
    select t.criado_em into v_quando from public.compra_tokens t where t.cliente_id = v_cliente;
    assert v_quando is not null, 'o painel nao ve quem foi a loja pelo Hub';
    begin
        perform t.token from public.compra_tokens t;
        raise exception 'o painel leu o codigo de compra!';
    exception when insufficient_privilege then null;
    end;

    reset role;
    perform set_config('request.jwt.claim.sub', '', true);
    perform set_config('request.jwt.claims', '', true);

    -- 8. o que o painel fez chegou ao Hub e a auditoria
    assert public.dumtech_licenca_marca(v_chave, v_maquina) <> v_marca, 'estender o teste nao mudou a impressao';
    assert exists (select 1 from public.auditoria
                    where tabela = 'licenca_testes' and operacao = 'update' and origem = 'painel'
                      and quem_email = 'dona@zz.local'), 'estender teste nao entrou na auditoria';
    assert exists (select 1 from public.auditoria
                    where tabela = 'celular_aparelhos' and operacao = 'update' and origem = 'painel'
                      and registro = v_aparelho::text), 'desconectar celular nao entrou na auditoria';
    -- desconectado pelo painel vale o mesmo que pelo Hub: o celular para de ver
    assert public.dumtech_celular_dados(v_token) ->> 'erro' = 'desconectado',
        'celular desconectado pelo painel continuou vendo os dados';

    -- 9. ninguem de fora alcanca as visoes; o painel nao alcanca o conteudo
    assert not has_table_privilege('anon', 'public.painel_testes', 'select'), 'anon le testes';
    assert not has_table_privilege('anon', 'public.painel_uso_dias', 'select'), 'anon le uso por dia';
    assert not has_table_privilege('anon', 'public.painel_uso_por_cliente', 'select'), 'anon le a faixa';
    assert not has_table_privilege('anon', 'public.painel_modulos_da_licenca', 'select'), 'anon le modulos';
    assert not has_table_privilege('anon', 'public.celular_espelhos', 'select'), 'anon le espelhos';
    assert not has_column_privilege('authenticated', 'public.celular_espelhos', 'dados', 'select'),
        'o painel alcanca o conteudo do celular';
    assert not has_column_privilege('authenticated', 'public.compra_tokens', 'token', 'select'),
        'o painel alcanca o codigo de compra';
    assert not has_column_privilege('authenticated', 'public.celular_aparelhos', 'token_hash', 'update'),
        'o painel troca o token do celular';

    raise notice 'painel: uso, testes e celular ...... ok';
end;
$$;

rollback;
