-- =============================================================================
-- Teste da migration 20261103120000: mensalidade (base + adicionais, teste de
-- 7 dias, cobranca confirmada pelo Eric). Roda numa transacao e desfaz tudo.
-- =============================================================================

begin;

-- ========================================== 1. PRAZO, SITUACAO E RESPOSTA ===
do $$
declare
    v_cliente uuid;
    v_vital   uuid;
    v_teste   uuid;
    v_chave   text;
    r         jsonb;
    v_erro    text;
begin
    insert into public.clientes (nome, email) values ('ZZ Mensal', 'zz.mensal@teste.local')
    returning id into v_cliente;

    -- a regra do prazo: vitalicia sem, teste com, assinatura com ou sem
    begin
        insert into public.licencas (cliente_id, chave, tipo, expira_em)
        values (v_cliente, 'ZZZZ-AAAA-0001-0001', 'vitalicia', current_date + 1);
        raise exception 'vitalicia com prazo entrou';
    exception when check_violation then null;
    end;
    begin
        insert into public.licencas (cliente_id, chave, tipo, expira_em)
        values (v_cliente, 'ZZZZ-AAAA-0001-0002', 'teste', null);
        raise exception 'teste sem prazo entrou';
    exception when check_violation then null;
    end;
    insert into public.licencas (cliente_id, chave, tipo, expira_em)
    values (v_cliente, 'ZZZZ-AAAA-0001-0003', 'assinatura', null);

    -- a situacao, em um lugar so
    assert public.dumtech_situacao_cobranca('vitalicia', null) is null, 'vitalicia tem situacao';
    assert public.dumtech_situacao_cobranca('teste', current_date + 3) = 'teste';
    assert public.dumtech_situacao_cobranca('assinatura', null) = 'em_dia';
    assert public.dumtech_situacao_cobranca('assinatura', current_date + 2) = 'pendente';
    assert public.dumtech_situacao_cobranca('assinatura', current_date) = 'pendente', 'o ultimo dia ainda vale';
    assert public.dumtech_situacao_cobranca('assinatura', current_date - 1) = 'consulta';
    assert public.dumtech_situacao_cobranca('teste', current_date - 1) = 'consulta';

    -- vitalicia: a resposta NAO ganha cobranca (nem como null)
    select licenca_id into v_vital from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);
    r := public.dumtech_resposta_licenca(v_vital);
    assert not (r ? 'cobranca'), 'vitalicia recebeu cobranca: ' || r::text;

    -- teste: a resposta diz a situacao e ate quando
    select licenca_id, chave into v_teste, v_chave
      from public.dumtech_emitir_licenca(v_cliente, array['VENDAS', 'ESTOQUE'], null, 'teste', current_date + 5);
    r := public.dumtech_resposta_licenca(v_teste);
    assert r->'cobranca'->>'situacao' = 'teste', 'teste sem situacao: ' || r::text;
    assert (r->'cobranca'->>'ate')::date = current_date + 5, 'teste sem data: ' || r::text;

    -- vencido: continua recusa `expirada` (liga o modo consulta), com texto amigavel
    update public.licencas set expira_em = current_date - 1 where id = v_teste;
    begin
        perform public.dumtech_licenca_valida(v_chave);
        raise exception 'teste vencido passou';
    exception when raise_exception then
        get stacked diagnostics v_erro = message_text;
        assert v_erro like 'expirada|Seu teste grátis terminou em %', 'texto do teste: ' || v_erro;
    end;

    update public.licencas set tipo = 'assinatura', cobranca_motivo = 'falhou' where id = v_teste;
    begin
        perform public.dumtech_licenca_valida(v_chave);
        raise exception 'assinatura vencida passou';
    exception when raise_exception then
        get stacked diagnostics v_erro = message_text;
        assert v_erro like 'expirada|Não conseguimos confirmar a sua mensalidade%', 'texto da assinatura: ' || v_erro;
    end;

    update public.licencas set cobranca_motivo = 'cancelou' where id = v_teste;
    begin
        perform public.dumtech_licenca_valida(v_chave);
        raise exception 'assinatura encerrada passou';
    exception when raise_exception then
        get stacked diagnostics v_erro = message_text;
        assert v_erro like 'expirada|Sua assinatura foi encerrada em %', 'texto do encerramento: ' || v_erro;
    end;

    -- o valor do mes: base + adicionais, nunca mais que 4
    -- (desde 20261104120000 cada adicional tem o seu preco)
    update public.mensalidade_config set preco_base = 89.90;
    update public.mensalidade_modulos set preco = 29.90 where papel = 'adicional';
    assert public.dumtech_valor_dos_modulos(public.dumtech_plano_base()) = 89.90;
    assert public.dumtech_valor_dos_modulos(public.dumtech_plano_base() || array['AGENDA', 'ORDENS']) = 149.70;
end;
$$;

-- ================================================ 2. CADASTRO PELO SITE ====
do $$
declare
    r        jsonb;
    r2       jsonb;
    v_cli    uuid;
    v_total  integer;
begin
    update public.mensalidade_config
       set preco_base = 89.90, dias_teste = 7, computadores = 1;
    update public.mensalidade_modulos set preco = 29.90, a_venda = true where papel = 'adicional';
    insert into public.mensalidade_combinacoes (chave, link) values
        ('', 'https://loja.infinitepay.io/dumtech/base'),
        ('AGENDA+ORDENS', 'https://loja.infinitepay.io/dumtech/base-2');

    -- e-mail novo: teste com os 7 modulos, prazo de 7 dias, 1 computador
    r := public.dumtech_cadastrar_mensal('ZZ Loja Nova', 'ZZ.Nova@Teste.Local', '(11) 90000-0001',
                                         '{}', false, '10.0.0.1');
    assert (r->>'ok')::boolean and r->>'caso' = 'nova', 'cadastro novo: ' || r::text;
    assert r->>'chave' ~ '^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', 'sem chave: ' || r::text;
    assert (r->>'ate')::date = current_date + 7, 'prazo do teste: ' || r::text;
    assert (select tipo from public.licencas where chave = r->>'chave') = 'teste';
    assert (select max_computadores from public.licencas where chave = r->>'chave') = 1;
    assert (select count(*) from public.licenca_produtos lp join public.licencas l on l.id = lp.licenca_id
             where l.chave = r->>'chave') = 7, 'teste nao tem o plano completo';
    assert (select telefone from public.clientes where email = 'zz.nova@teste.local') = '11900000001';

    -- o mesmo e-mail de novo: a mesma chave, nenhuma licenca a mais
    r2 := public.dumtech_cadastrar_mensal('Outro Nome', 'zz.nova@teste.local', '', '{}', false, '10.0.0.1');
    assert r2->>'caso' = 'ja_tem' and r2->>'chave' = r->>'chave', 'repetido: ' || r2::text;
    select id into v_cli from public.clientes where email = 'zz.nova@teste.local';
    assert (select count(*) from public.licencas where cliente_id = v_cli) = 1, 'criou segunda licenca';

    -- assinar: pedido com o valor e o link da quantidade de adicionais
    r2 := public.dumtech_cadastrar_mensal('ZZ Loja Nova', 'zz.nova@teste.local', '',
                                          array['ordens', 'AGENDA', 'invalido', 'ORDENS'], true, '10.0.0.1');
    assert r2->>'link' = 'https://loja.infinitepay.io/dumtech/base-2', 'link errado: ' || r2::text;
    assert (r2->>'valor')::numeric = 149.70, 'valor errado: ' || r2::text;
    assert (select adicionais from public.assinatura_pedidos ap join public.licencas l on l.id = ap.licenca_id
             where l.chave = r->>'chave' and ap.situacao = 'aguardando') = array['ORDENS', 'AGENDA'];

    -- pedir de novo troca o pedido aguardando (nao empilha)
    r2 := public.dumtech_cadastrar_mensal('ZZ Loja Nova', 'zz.nova@teste.local', '', '{}', true, '10.0.0.1');
    assert (select count(*) from public.assinatura_pedidos ap join public.licencas l on l.id = ap.licenca_id
             where l.chave = r->>'chave' and ap.situacao = 'aguardando') = 1, 'empilhou pedido';
    assert r2->>'link' = 'https://loja.infinitepay.io/dumtech/base';

    -- quantidade sem link: pedido gravado, link vazio (o site oferece o WhatsApp)
    r2 := public.dumtech_cadastrar_mensal('ZZ Loja Nova', 'zz.nova@teste.local', '', array['CLIENTES'], true, '10.0.0.2');
    assert r2->>'link' = '', 'inventou link: ' || r2::text;

    -- vitalicio: nada de teste, nada de pedido
    insert into public.clientes (nome, email) values ('ZZ Vitalicio', 'zz.vitalicio@teste.local') returning id into v_cli;
    perform public.dumtech_emitir_licenca(v_cli, array['VENDAS']);
    r2 := public.dumtech_cadastrar_mensal('ZZ Vitalicio', 'zz.vitalicio@teste.local', '', '{}', true, '10.0.0.3');
    assert r2->>'caso' = 'vitalicio' and r2->>'chave' is null, 'vitalicio: ' || r2::text;
    -- o navegador recebe o mesmo link que qualquer um: nao da para descobrir quem e cliente
    assert r2->>'link' = 'https://loja.infinitepay.io/dumtech/base', 'resposta do vitalicio diferente: ' || r2::text;
    assert (select count(*) from public.licencas where cliente_id = v_cli) = 1, 'vitalicio ganhou teste';
    assert not exists (select 1 from public.assinatura_pedidos ap join public.licencas l on l.id = ap.licenca_id
                        where l.cliente_id = v_cli), 'vitalicio ganhou pedido';

    -- o que chega errado
    r2 := public.dumtech_cadastrar_mensal('', 'zz.semnome@teste.local', '', '{}', false, '10.0.0.4');
    assert r2->>'erro' = 'nome', 'sem nome: ' || r2::text;
    r2 := public.dumtech_cadastrar_mensal('ZZ', 'nao-e-email', '', '{}', false, '10.0.0.4');
    assert r2->>'erro' = 'email_invalido', 'e-mail torto: ' || r2::text;

    -- limite por IP: 5 por hora
    select count(*) into v_total from generate_series(1, 5) n
     where (public.dumtech_cadastrar_mensal('ZZ Muitos ' || n, 'zz.muitos' || n || '@teste.local', '', '{}', false, '10.9.9.9')->>'ok')::boolean;
    assert v_total = 5, 'limite cedo demais';
    r2 := public.dumtech_cadastrar_mensal('ZZ Muitos 6', 'zz.muitos6@teste.local', '', '{}', false, '10.9.9.9');
    assert r2->>'erro' = 'muitas_tentativas', 'sem limite: ' || r2::text;

    -- quem pode chamar
    assert not has_function_privilege('anon', 'public.dumtech_cadastrar_mensal(text,text,text,text[],boolean,text,uuid,text)', 'execute'),
        'anon cadastra sem passar pela funcao do e-mail';
    assert not has_function_privilege('authenticated', 'public.dumtech_cadastrar_mensal(text,text,text,text[],boolean,text,uuid,text)', 'execute');
    assert has_function_privilege('anon', 'public.dumtech_mensalidade_publica()', 'execute');

    -- a vitrine: preco e o que da para assinar, sem os links
    r2 := public.dumtech_mensalidade_publica();
    assert (r2->>'preco_base')::numeric = 89.90;
    assert (r2->>'computadores')::int = 1, 'vitrine sem computadores: ' || r2::text;
    assert r2->'base' = '["VENDAS", "ESTOQUE", "FINANCEIRO"]'::jsonb, 'base: ' || r2::text;
    assert jsonb_array_length(r2->'adicionais') = 4 and r2->'adicionais' @> '[{"codigo": "AGENDA", "preco": 29.90}]';
    assert r2->'combinacoes' ? '' and not (r2->'combinacoes' ? 'CLIENTES'), 'combinacoes: ' || r2::text;
    assert position('infinitepay' in r2::text) = 0, 'vitrine mostrou link';

    -- link que nao e https nao entra
    begin
        insert into public.mensalidade_combinacoes (chave, link) values ('CLIENTES', 'javascript:alert(1)');
        raise exception 'link torto entrou';
    exception when check_violation then null;
    end;
end;
$$;

-- ================================================ 3. A LOJA PELO HUB ========
do $$
declare
    v_cli   uuid;
    v_chave text;
    r       jsonb;
begin
    insert into public.clientes (nome, email) values ('ZZ Hub', 'zz.hub@teste.local') returning id into v_cli;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cli, array['VENDAS']);
    insert into public.ativacoes (licenca_id, maquina)
    select id, 'MAQ-ZZ-HUB' from public.licencas where chave = v_chave;

    -- com a prova (chave + computador ativado): a loja sabe que e vitalicio
    r := public.dumtech_token_compra(v_chave, 'MAQ-ZZ-HUB', '', '');
    r := public.dumtech_abrir_compra(r->>'token');
    assert r->>'tipo' = 'vitalicia', 'loja nao soube do vitalicio: ' || r::text;

    -- so com o e-mail: nada do cadastro dele, nem o tipo
    r := public.dumtech_token_compra('', '', 'Alguem', 'zz.hub@teste.local');
    r := public.dumtech_abrir_compra(r->>'token');
    assert coalesce(r->>'tipo', '') = '', 'e-mail sozinho revelou o tipo: ' || r::text;
end;
$$;

-- ================================================ 4. AS ACOES DO ERIC ======
do $$
declare
    v_admin  uuid := '33333333-3333-3333-3333-333333333333';
    r        jsonb;
    v_lic    uuid;
    v_pedido uuid;
    v_vital  uuid;
    v_cli    uuid;
begin
    update public.mensalidade_config set dias_carencia = 7;
    delete from public.mensalidade_combinacoes;
    r := public.dumtech_cadastrar_mensal('ZZ Assinante', 'zz.assinante@teste.local', '', array['ORDENS'], true, '10.1.1.1');
    select id into v_lic from public.licencas where chave = r->>'chave';
    select id into v_pedido from public.assinatura_pedidos where licenca_id = v_lic and situacao = 'aguardando';

    -- sem ser admin: recusado
    begin
        perform public.dumtech_confirmar_assinatura(v_pedido);
        raise exception 'confirmou sem ser admin';
    exception when insufficient_privilege then null;
    end;
    assert not has_function_privilege('anon', 'public.dumtech_cobranca(uuid,text,date)', 'execute');

    -- em producao o administrador precisa existir em auth.users: usa o que ja ha
    select user_id into v_admin from public.administradores limit 1;
    if v_admin is null then
        v_admin := '33333333-3333-3333-3333-333333333333';
        insert into public.administradores (user_id, nome) values (v_admin, 'ZZ Eric');
    end if;
    perform set_config('request.jwt.claim.sub', v_admin::text, true);
    perform set_config('request.jwt.claims', format('{"sub":"%s","aal":"aal2","role":"authenticated"}', v_admin), true);

    -- confirmar: vira assinatura em dia, com a base + o adicional escolhido
    r := public.dumtech_confirmar_assinatura(v_pedido);
    assert (r->>'ok')::boolean and r->>'email' = 'zz.assinante@teste.local', 'confirmar: ' || r::text;
    assert (select tipo from public.licencas where id = v_lic) = 'assinatura';
    assert (select expira_em from public.licencas where id = v_lic) is null;
    assert (select assinatura_desde from public.licencas where id = v_lic) = current_date;
    assert (select array_agg(p.codigo order by p.codigo) from public.licenca_produtos lp
              join public.produtos p on p.id = lp.produto_id where lp.licenca_id = v_lic)
           = array['ESTOQUE', 'FINANCEIRO', 'ORDENS', 'VENDAS'], 'modulos do plano errados';
    assert (select situacao from public.assinatura_pedidos where id = v_pedido) = 'confirmado';
    r := public.dumtech_confirmar_assinatura(v_pedido);
    assert r->>'erro' = 'pedido', 'confirmou duas vezes: ' || r::text;

    -- cobranca falhou: carencia, e clicar de novo nao estica o prazo
    r := public.dumtech_cobranca(v_lic, 'falhou');
    assert (r->>'ate')::date = current_date + 7, 'falhou: ' || r::text;
    assert public.dumtech_situacao_cobranca('assinatura', (r->>'ate')::date) = 'pendente';
    update public.licencas set expira_em = current_date + 2 where id = v_lic;
    r := public.dumtech_cobranca(v_lic, 'falhou');
    assert (r->>'ate')::date = current_date + 2, 'clicar de novo esticou: ' || r::text;

    -- pagamento em dia: limpa tudo
    r := public.dumtech_cobranca(v_lic, 'em_dia');
    assert (select expira_em is null and cobranca_motivo is null from public.licencas where id = v_lic), 'em dia: ' || r::text;

    -- cancelou: na data escolhida
    r := public.dumtech_cobranca(v_lic, 'cancelou', current_date + 10);
    assert (select expira_em from public.licencas where id = v_lic) = current_date + 10;
    assert (select cobranca_motivo from public.licencas where id = v_lic) = 'cancelou';
    r := public.dumtech_cobranca(v_lic, 'cancelou', current_date - 3);
    assert r->>'erro' = 'data', 'aceitou data no passado: ' || r::text;
    r := public.dumtech_cobranca(v_lic, 'qualquer');
    assert r->>'erro' = 'acao', 'aceitou acao estranha: ' || r::text;

    -- vitalicia: nenhuma acao de cobranca encosta nela
    insert into public.clientes (nome, email) values ('ZZ Vital Eric', 'zz.vital.eric@teste.local') returning id into v_cli;
    select licenca_id into v_vital from public.dumtech_emitir_licenca(v_cli, array['VENDAS']);
    r := public.dumtech_cobranca(v_vital, 'falhou');
    assert r->>'erro' = 'tipo', 'marcou cobranca em vitalicia: ' || r::text;
    assert (select expira_em is null from public.licencas where id = v_vital), 'vitalicia ganhou prazo';
    r := public.dumtech_estender_teste_mensal(v_vital, 7);
    assert r->>'erro' = 'tipo', 'estendeu vitalicia: ' || r::text;

    -- estender teste
    r := public.dumtech_cadastrar_mensal('ZZ Testando', 'zz.testando@teste.local', '', '{}', false, '10.1.1.2');
    select id into v_lic from public.licencas where chave = r->>'chave';
    r := public.dumtech_estender_teste_mensal(v_lic, 3);
    assert (r->>'ate')::date = current_date + 10, 'estender: ' || r::text;

    -- descartar e as visoes do painel
    r := public.dumtech_cadastrar_mensal('ZZ Testando', 'zz.testando@teste.local', '', '{}', true, '10.1.1.2');
    select id into v_pedido from public.assinatura_pedidos where licenca_id = v_lic and situacao = 'aguardando';
    r := public.dumtech_descartar_assinatura(v_pedido);
    assert (select situacao from public.assinatura_pedidos where id = v_pedido) = 'descartado', 'descartar: ' || r::text;
    assert exists (select 1 from public.painel_mensalidades where licenca_id = v_lic and situacao = 'teste');
    assert not exists (select 1 from public.painel_mensalidades where licenca_id = v_vital), 'vitalicia no painel de mensalidade';
    assert exists (select 1 from public.painel_assinatura_pedidos where id = v_pedido);
end;
$$;

rollback;
