-- =============================================================================
-- Teste da migration 20261104120000: o controle da mensalidade pelo painel
-- (modulos, planos prontos, combinacoes, cupons, eventos, textos e avisos).
-- Roda numa transacao e desfaz tudo no fim - pode rodar em producao.
-- =============================================================================

begin;

-- ========================================== 1. MODULOS, PLANOS E VITRINE ===
do $$
declare
    r        jsonb;
    v_salao  uuid;
    v_oculto uuid;
begin
    -- a base e os adicionais de hoje vieram para a tabela
    assert public.dumtech_plano_base() @> array['VENDAS', 'ESTOQUE', 'FINANCEIRO']
       and cardinality(public.dumtech_plano_base()) = 3, 'base: ' || public.dumtech_plano_base()::text;
    assert (select count(*) from public.mensalidade_modulos where papel = 'adicional') = 4;

    -- preco por adicional e adicional fora da venda
    update public.mensalidade_config set preco_base = 89.90;
    update public.mensalidade_modulos set preco = 29.90 where papel = 'adicional';
    update public.mensalidade_modulos set preco = 39.90 where codigo = 'AGENDA';
    update public.mensalidade_modulos set a_venda = false where codigo = 'ORCAMENTOS';
    r := public.dumtech_mensalidade_publica();
    assert not (r->'adicionais' @> '[{"codigo": "ORCAMENTOS"}]'), 'adicional fora da venda na vitrine';
    assert r->'adicionais' @> '[{"codigo": "AGENDA", "preco": 39.90}]', 'preco do adicional: ' || r::text;
    assert public.dumtech_valor_dos_modulos(array['VENDAS', 'ESTOQUE', 'FINANCEIRO', 'AGENDA', 'CLIENTES']) = 159.70;

    -- plano pronto: qualquer combinacao, modulo torto sai, repetido some
    insert into public.mensalidade_planos (nome, descricao, modulos, preco, link, destaque, ordem)
    values ('  Salão ', 'Para quem atende com hora marcada', array['agenda', 'CLIENTES', 'FINANCEIRO', 'agenda', 'XYZ'],
            119.90, 'https://loja.infinitepay.io/dumtech/salao', true, 1)
    returning id into v_salao;
    assert (select modulos from public.mensalidade_planos where id = v_salao) @> array['AGENDA', 'CLIENTES', 'FINANCEIRO']
       and (select cardinality(modulos) from public.mensalidade_planos where id = v_salao) = 3, 'modulos do plano';
    assert (select nome from public.mensalidade_planos where id = v_salao) = 'Salão';
    begin
        insert into public.mensalidade_planos (nome, modulos, preco) values ('Vazio', array['XYZ'], 10);
        raise exception 'plano sem modulo entrou';
    exception when check_violation then null;
    end;
    begin
        insert into public.mensalidade_planos (nome, modulos, preco, link) values ('Torto', array['VENDAS'], 10, 'javascript:alert(1)');
        raise exception 'link torto entrou';
    exception when check_violation then null;
    end;

    -- de/por: vale ate a data; vencida, volta sozinho
    update public.mensalidade_planos
       set promo_preco = 99.90, promo_link = 'https://loja.infinitepay.io/dumtech/salao-promo',
           promo_rotulo = 'Novembro', promo_ate = current_date + 5
     where id = v_salao;
    r := public.dumtech_mensalidade_publica();
    assert r->'planos'->0->>'nome' = 'Salão', 'plano na vitrine: ' || r::text;
    assert (r->'planos'->0->>'preco')::numeric = 99.90 and (r->'planos'->0->>'preco_cheio')::numeric = 119.90,
        'de/por: ' || (r->'planos'->0)::text;
    assert position('infinitepay' in r::text) = 0, 'vitrine mostrou link';
    update public.mensalidade_planos set promo_ate = current_date - 1 where id = v_salao;
    r := public.dumtech_mensalidade_publica();
    assert (r->'planos'->0->>'preco')::numeric = 119.90 and r->'planos'->0->'preco_cheio' = 'null'::jsonb,
        'promo vencida continuou: ' || (r->'planos'->0)::text;

    -- plano escondido (so por cupom) nao aparece
    insert into public.mensalidade_planos (nome, modulos, preco, link, visivel)
    values ('Parceiro', array['VENDAS', 'ESTOQUE', 'FINANCEIRO'], 69.90, 'https://loja.infinitepay.io/dumtech/parceiro', false)
    returning id into v_oculto;
    r := public.dumtech_mensalidade_publica();
    assert jsonb_array_length(r->'planos') = 1, 'plano escondido na vitrine';

    -- combinacao do "monte o seu": a chave e a mesma em qualquer ordem
    assert public.dumtech_chave_combinacao(array['ordens', 'AGENDA', 'ORDENS']) = 'AGENDA+ORDENS';
    insert into public.mensalidade_combinacoes (chave, link) values ('ordens+agenda', 'https://loja.infinitepay.io/dumtech/ao');
    assert exists (select 1 from public.mensalidade_combinacoes where chave = 'AGENDA+ORDENS'), 'chave nao normalizou';
    r := public.dumtech_mensalidade_publica();
    assert r->'combinacoes' ? 'AGENDA+ORDENS', 'combinacao com link: ' || r::text;
end;
$$;

-- =============================================== 2. CADASTRO E CUPOM ======
do $$
declare
    r        jsonb;
    v_salao  uuid := (select id from public.mensalidade_planos where nome = 'Salão');
    v_oculto uuid := (select id from public.mensalidade_planos where nome = 'Parceiro');
    v_lic    uuid;
begin
    update public.mensalidade_planos set promo_ate = current_date + 5 where id = v_salao;

    -- plano pronto em promocao: valor e link da promocao, calculados aqui
    r := public.dumtech_cadastrar_mensal('ZZ Salao', 'zz.salao@teste.local', '', '{}', true, '10.2.0.1', v_salao, '');
    assert (r->>'ok')::boolean and (r->>'valor')::numeric = 99.90, 'plano: ' || r::text;
    assert r->>'link' = 'https://loja.infinitepay.io/dumtech/salao-promo', 'link da promo: ' || r::text;
    select licenca_id into v_lic from public.assinatura_pedidos where plano_id = v_salao and situacao = 'aguardando';
    assert v_lic is not null, 'pedido sem o plano';
    assert (select modulos from public.assinatura_pedidos where plano_id = v_salao) @> array['AGENDA', 'CLIENTES', 'FINANCEIRO'];
    -- o teste e sempre completo, seja qual for o plano pedido
    assert (select count(*) from public.licenca_produtos where licenca_id = v_lic) = 7, 'teste incompleto';
    assert exists (select 1 from public.assinatura_eventos where licenca_id = v_lic and tipo = 'teste'), 'sem evento do teste';
    assert exists (select 1 from public.assinatura_eventos where licenca_id = v_lic and tipo = 'pediu'), 'sem evento do pedido';

    -- monte o seu: preco de cada adicional e o link da combinacao
    r := public.dumtech_cadastrar_mensal('ZZ Monta', 'zz.monta@teste.local', '', array['ORDENS', 'AGENDA'], true, '10.2.0.2');
    assert (r->>'valor')::numeric = 89.90 + 29.90 + 39.90, 'monte o seu: ' || r::text;
    assert r->>'link' = 'https://loja.infinitepay.io/dumtech/ao';
    -- adicional fora da venda nao entra; combinacao sem link vai para o WhatsApp (link vazio)
    r := public.dumtech_cadastrar_mensal('ZZ Fora', 'zz.fora@teste.local', '', array['ORCAMENTOS'], true, '10.2.0.3');
    assert (r->>'valor')::numeric = 89.90 and r->>'link' = '', 'fora da venda: ' || r::text;

    -- plano escondido so por cupom
    r := public.dumtech_cadastrar_mensal('ZZ Oculto', 'zz.oculto@teste.local', '', '{}', true, '10.2.0.4', v_oculto, '');
    assert r->>'erro' = 'plano', 'plano escondido aceito sem cupom: ' || r::text;

    insert into public.mensalidade_cupons (codigo, plano_id, parceiro, usos_max) values ('parceiro10', v_oculto, 'Joao', 1);
    assert exists (select 1 from public.mensalidade_cupons where codigo = 'PARCEIRO10'), 'cupom nao normalizou';
    r := public.dumtech_cupom_publico('parceiro10');
    assert (r->>'ok')::boolean and r->'plano'->>'nome' = 'Parceiro', 'cupom publico: ' || r::text;
    assert position('infinitepay' in r::text) = 0, 'cupom mostrou link';
    r := public.dumtech_cadastrar_mensal('ZZ Cupom', 'zz.cupom@teste.local', '', '{}', true, '10.2.0.5', null, 'Parceiro10');
    assert (r->>'valor')::numeric = 69.90 and r->>'link' = 'https://loja.infinitepay.io/dumtech/parceiro', 'cupom: ' || r::text;
    assert (select cupom from public.assinatura_pedidos ap join public.licencas l on l.id = ap.licenca_id
             join public.clientes c on c.id = l.cliente_id where c.email = 'zz.cupom@teste.local') = 'PARCEIRO10';
    -- limite de usos: o segundo nao entra, e a mensagem e a mesma de cupom inexistente
    r := public.dumtech_cadastrar_mensal('ZZ Cupom 2', 'zz.cupom2@teste.local', '', '{}', true, '10.2.0.6', null, 'PARCEIRO10');
    assert r->>'erro' = 'cupom', 'cupom passou do limite: ' || r::text;
    assert public.dumtech_cupom_publico('PARCEIRO10')->>'mensagem' = public.dumtech_cupom_publico('NAOEXISTE')->>'mensagem',
        'cupom esgotado e inexistente respondem diferente';
    update public.mensalidade_cupons set usos_max = null, valido_ate = current_date - 1 where codigo = 'PARCEIRO10';
    assert not (public.dumtech_cupom_publico('PARCEIRO10')->>'ok')::boolean, 'cupom vencido aceito';

    -- quem pode chamar
    assert has_function_privilege('anon', 'public.dumtech_cupom_publico(text)', 'execute');
    assert not has_table_privilege('anon', 'public.mensalidade_planos', 'select'), 'anon le os planos (e os links)';
    assert not has_table_privilege('anon', 'public.landing_conteudo', 'select'), 'anon le o rascunho';
    assert not has_function_privilege('anon', 'public.dumtech_ajustar_assinatura(uuid,uuid,text[],numeric,integer,date,text)', 'execute');
end;
$$;

-- ====================================== 3. A FICHA DO ASSINANTE E EVENTOS ===
do $$
declare
    v_admin  uuid := '44444444-4444-4444-4444-444444444444';
    r        jsonb;
    v_salao  uuid := (select id from public.mensalidade_planos where nome = 'Salão');
    v_pedido uuid;
    v_lic    uuid;
    v_teste  uuid;
    v_vital  uuid;
    v_cli    uuid;
begin
    select id, licenca_id into v_pedido, v_lic from public.assinatura_pedidos
     where plano_id = v_salao and situacao = 'aguardando';

    -- sem ser admin: recusado
    begin
        perform public.dumtech_ajustar_assinatura(v_lic, null, null, 50);
        raise exception 'ajustou sem ser admin';
    exception when insufficient_privilege then null;
    end;

    -- em producao o administrador precisa existir em auth.users: usa o que ja ha
    select user_id into v_admin from public.administradores limit 1;
    if v_admin is null then
        v_admin := '44444444-4444-4444-4444-444444444444';
        insert into public.administradores (user_id, nome) values (v_admin, 'ZZ Eric');
    end if;
    perform set_config('request.jwt.claim.sub', v_admin::text, true);
    perform set_config('request.jwt.claims', format('{"sub":"%s","aal":"aal2","role":"authenticated"}', v_admin), true);

    -- confirmar grava o plano e o valor combinado
    r := public.dumtech_confirmar_assinatura(v_pedido);
    assert (r->>'ok')::boolean, 'confirmar: ' || r::text;
    assert (select plano_id from public.licencas where id = v_lic) = v_salao;
    assert (select valor_mensal from public.licencas where id = v_lic) = 99.90, 'valor combinado';
    assert (select array_agg(p.codigo order by p.codigo) from public.licenca_produtos lp
              join public.produtos p on p.id = lp.produto_id where lp.licenca_id = v_lic)
           = array['AGENDA', 'CLIENTES', 'FINANCEIRO'], 'modulos do plano na licenca';
    assert (select admin_id from public.assinatura_eventos where licenca_id = v_lic and tipo = 'confirmou') = v_admin,
        'evento sem quem fez';

    -- mudar o preco do plano amanha nao mexe em quem ja assina
    update public.mensalidade_planos set preco = 199.90, promo_ate = null, promo_preco = null where id = v_salao;
    assert (select valor_mensal from public.licencas where id = v_lic) = 99.90;

    -- ajustar: modulos a mao, valor, anotacoes; o evento guarda de -> para
    r := public.dumtech_ajustar_assinatura(v_lic, null, array['agenda', 'CLIENTES', 'FINANCEIRO', 'VENDAS'], 109.90, null, null, 'Pediu desconto');
    assert (r->>'ok')::boolean, 'ajustar: ' || r::text;
    assert (select plano_id from public.licencas where id = v_lic) is null, 'modulo a mao manteve o plano';
    assert (select valor_mensal from public.licencas where id = v_lic) = 109.90;
    assert (select observacoes from public.licencas where id = v_lic) = 'Pediu desconto';
    assert (select detalhe->'valor'->>'de' from public.assinatura_eventos where licenca_id = v_lic and tipo = 'ajustou'
             order by id desc limit 1)::numeric = 99.90, 'evento sem o de';
    -- computadores abaixo dos em uso vai para a tela Acessos
    insert into public.ativacoes (licenca_id, maquina) values (v_lic, 'MAQ-ZZ-1'), (v_lic, 'MAQ-ZZ-2');
    r := public.dumtech_ajustar_assinatura(v_lic, null, null, null, 1);
    assert r->>'erro' = 'computadores', 'diminuiu computador em uso: ' || r::text;
    r := public.dumtech_ajustar_assinatura(v_lic, null, null, null, 3);
    assert (select max_computadores from public.licencas where id = v_lic) = 3;
    -- data so para quem tem prazo
    r := public.dumtech_ajustar_assinatura(v_lic, null, null, null, null, current_date + 3);
    assert r->>'erro' = 'data', 'data em assinatura em dia: ' || r::text;

    -- cancelou e reabriu
    perform public.dumtech_cobranca(v_lic, 'cancelou', current_date + 10);
    r := public.dumtech_ajustar_assinatura(v_lic, null, null, null, null, current_date + 20);
    assert (select expira_em from public.licencas where id = v_lic) = current_date + 20, 'nao mudou a data do cancelamento';
    r := public.dumtech_reabrir_assinatura(v_lic);
    assert (r->>'ok')::boolean and (select expira_em is null and cobranca_motivo is null from public.licencas where id = v_lic),
        'reabrir: ' || r::text;
    r := public.dumtech_reabrir_assinatura(v_lic);
    assert r->>'erro' = 'tipo', 'reabriu o que nao estava cancelado';

    -- historico: tudo registrado, do mais recente para o mais antigo
    assert (select array_agg(tipo order by id) from public.assinatura_eventos where licenca_id = v_lic)
           @> array['teste', 'pediu', 'confirmou', 'ajustou', 'cancelou', 'reabriu'], 'historico incompleto';
    assert (select tipo from public.painel_assinatura_eventos where licenca_id = v_lic limit 1) = 'reabriu',
        'historico fora de ordem';

    -- ativar: o teste vira assinatura sem pedido (fechou pelo WhatsApp)
    r := public.dumtech_cadastrar_mensal('ZZ WhatsApp', 'zz.whats@teste.local', '', '{}', false, '10.2.0.7');
    select id into v_teste from public.licencas where chave = r->>'chave';
    r := public.dumtech_ativar_assinatura(v_teste, null, array['VENDAS', 'ESTOQUE', 'FINANCEIRO', 'ORDENS']);
    assert (r->>'ok')::boolean, 'ativar: ' || r::text;
    assert (select tipo from public.licencas where id = v_teste) = 'assinatura';
    assert (select valor_mensal from public.licencas where id = v_teste) = 89.90 + 29.90, 'valor calculado na ativacao';
    assert exists (select 1 from public.assinatura_eventos where licenca_id = v_teste and tipo = 'ativou');

    -- vitalicia: nenhuma acao da ficha encosta nela
    insert into public.clientes (nome, email) values ('ZZ Vital Ficha', 'zz.vital.ficha@teste.local') returning id into v_cli;
    select licenca_id into v_vital from public.dumtech_emitir_licenca(v_cli, array['VENDAS']);
    assert public.dumtech_ajustar_assinatura(v_vital, null, null, 10)->>'erro' = 'tipo';
    assert public.dumtech_ativar_assinatura(v_vital)->>'erro' = 'tipo';
    assert public.dumtech_reabrir_assinatura(v_vital)->>'erro' = 'tipo';
    assert (select valor_mensal is null and expira_em is null from public.licencas where id = v_vital), 'vitalicia mexida';
    assert not exists (select 1 from public.assinatura_eventos where licenca_id = v_vital);
end;
$$;

-- ============================================ 4. TEXTOS E FAIXA DE AVISO ===
do $$
declare
    v_admin uuid;
    r       jsonb;
    v_pub1  uuid;
begin
    select user_id into v_admin from public.administradores limit 1;
    perform set_config('request.jwt.claim.sub', v_admin::text, true);
    perform set_config('request.jwt.claims', format('{"sub":"%s","aal":"aal2","role":"authenticated"}', v_admin), true);

    -- o rascunho nao vai para o site
    update public.landing_conteudo set conteudo = '{"hero": {"titulo": "Rascunho A"}}' where id = 'rascunho';
    assert coalesce(public.dumtech_mensalidade_publica()->'conteudo'->'hero'->>'titulo', '') <> 'Rascunho A',
        'rascunho apareceu no site';
    r := public.dumtech_publicar_landing();
    v_pub1 := (r->>'id')::uuid;
    assert public.dumtech_mensalidade_publica()->'conteudo'->'hero'->>'titulo' = 'Rascunho A', 'publicar: ' || r::text;

    update public.landing_conteudo set conteudo = '{"hero": {"titulo": "Versao B"}}' where id = 'rascunho';
    perform public.dumtech_publicar_landing();
    assert public.dumtech_mensalidade_publica()->'conteudo'->'hero'->>'titulo' = 'Versao B';

    -- voltar a uma versao publicada: o site e o rascunho voltam juntos
    r := public.dumtech_voltar_landing(v_pub1);
    assert (r->>'ok')::boolean, 'voltar: ' || r::text;
    assert public.dumtech_mensalidade_publica()->'conteudo'->'hero'->>'titulo' = 'Rascunho A';
    assert (select conteudo->'hero'->>'titulo' from public.landing_conteudo where id = 'rascunho') = 'Rascunho A';

    -- texto que nao e objeto nao entra
    begin
        update public.landing_conteudo set conteudo = '"<script>"' where id = 'rascunho';
        raise exception 'conteudo torto entrou';
    exception when check_violation then null;
    end;

    -- faixa de aviso: so a vigente, a mais nova ganha
    insert into public.landing_avisos (texto, inicio, fim, criado_em) values ('Aviso velho', current_date - 3, current_date + 3, now() - interval '1 day');
    insert into public.landing_avisos (texto, link, tom, inicio, fim) values ('Novembro: plano Salão em promoção', '#plano', 'verde', current_date, current_date + 1);
    insert into public.landing_avisos (texto, inicio) values ('Ainda nao comecou', current_date + 2);
    assert public.dumtech_mensalidade_publica()->'aviso'->>'texto' = 'Novembro: plano Salão em promoção',
        'aviso: ' || (public.dumtech_mensalidade_publica()->'aviso')::text;
    update public.landing_avisos set ativo = false;
    assert public.dumtech_mensalidade_publica()->'aviso' = 'null'::jsonb, 'aviso desligado continuou';
    begin
        insert into public.landing_avisos (texto, tom) values ('Tom torto', 'neon');
        raise exception 'tom torto entrou';
    exception when check_violation then null;
    end;
    begin
        insert into public.landing_avisos (texto, link) values ('Link torto', 'javascript:alert(1)');
        raise exception 'link torto no aviso entrou';
    exception when check_violation then null;
    end;
end;
$$;

rollback;
