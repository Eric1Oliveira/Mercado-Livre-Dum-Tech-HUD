-- =============================================================================
-- Teste do painel administrativo: quem entra, o que ve, e o uso que chega
-- do Hub.
--
-- Roda inteiro dentro de uma transacao e desfaz tudo no fim: pode ser colado no
-- SQL Editor do Supabase, mesmo em producao.
--
-- OBS: o teste finge ser um usuario logado definindo `request.jwt.claim.sub` e `request.jwt.claims` (com aal2 = senha + codigo),
-- que e de onde o `auth.uid()` do Supabase tira o id. Nao precisa do schema
-- auth para rodar.
-- =============================================================================

begin;

-- ============================================================ 1. ESTRUTURA ==
do $$
begin
    assert to_regclass('public.administradores') is not null, 'falta administradores';
    assert to_regclass('public.uso_diario')      is not null, 'falta uso_diario';
    assert to_regclass('public.integracoes')     is not null, 'falta integracoes';
    assert to_regclass('public.painel_clientes')       is not null, 'falta painel_clientes';
    assert to_regclass('public.painel_modulos')        is not null, 'falta painel_modulos';
    assert to_regclass('public.painel_recomendacoes')  is not null, 'falta painel_recomendacoes';
    assert to_regclass('public.painel_resumo')         is not null, 'falta painel_resumo';
    assert (select count(*) from public.integracoes) >= 12,
        'as pontes entre modulos deveriam estar cadastradas';
    raise notice '1. estrutura ....................... ok';
end;
$$;

-- ====================================================== 2. USO VINDO DO HUB ==
do $$
declare
    v_cliente uuid;
    v_chave   text;
    v_licenca uuid;
    v_resposta jsonb;
begin
    insert into public.clientes (nome, email) values ('ZZ Uso', 'zz.uso@teste.local')
    returning id into v_cliente;
    select licenca_id, chave into v_licenca, v_chave
      from public.dumtech_emitir_licenca(v_cliente, array['ESTOQUE', 'VENDAS']);
    perform public.dumtech_ativar_licenca(v_chave, 'zz-uso-1');

    -- o Hub manda o resumo de dois dias
    v_resposta := public.dumtech_registrar_uso(v_chave, 'zz-uso-1', jsonb_build_array(
        jsonb_build_object('dia', (current_date - 1)::text, 'produto', 'ESTOQUE', 'aberturas', 4),
        jsonb_build_object('dia', current_date::text,       'produto', 'ESTOQUE', 'aberturas', 3),
        jsonb_build_object('dia', current_date::text,       'produto', 'VENDAS',  'aberturas', 9)
    ));
    assert (v_resposta->>'ok')::boolean, format('uso recusado: %s', v_resposta);
    assert (v_resposta->>'gravados')::int = 3, 'deveriam ser tres linhas';
    assert (select sum(aberturas) from public.uso_diario where licenca_id = v_licenca) = 16,
        'a soma do uso nao bate';

    -- reenviar o MESMO dia nao soma duas vezes: fica o maior
    perform public.dumtech_registrar_uso(v_chave, 'zz-uso-1', jsonb_build_array(
        jsonb_build_object('dia', current_date::text, 'produto', 'VENDAS', 'aberturas', 11)));
    assert (select aberturas from public.uso_diario
             where licenca_id = v_licenca and produto_codigo = 'VENDAS'
               and dia = current_date) = 11, 'o reenvio deveria ficar com o maior';
    perform public.dumtech_registrar_uso(v_chave, 'zz-uso-1', jsonb_build_array(
        jsonb_build_object('dia', current_date::text, 'produto', 'VENDAS', 'aberturas', 2)));
    assert (select aberturas from public.uso_diario
             where licenca_id = v_licenca and produto_codigo = 'VENDAS'
               and dia = current_date) = 11, 'numero menor nao pode apagar o maior';

    -- lixo e ignorado sem derrubar o envio
    v_resposta := public.dumtech_registrar_uso(v_chave, 'zz-uso-1', jsonb_build_array(
        jsonb_build_object('dia', (current_date + 5)::text, 'produto', 'ESTOQUE', 'aberturas', 3),
        jsonb_build_object('dia', current_date::text, 'produto', 'NAO_EXISTE', 'aberturas', 3),
        jsonb_build_object('dia', 'nao-e-data', 'produto', 'ESTOQUE', 'aberturas', 3),
        jsonb_build_object('dia', current_date::text, 'produto', 'AGENDA', 'aberturas', 1)
    ));
    assert (v_resposta->>'gravados')::int = 1, 'so a linha valida deveria entrar';

    -- computador que nao ativou, e chave que nao existe
    assert public.dumtech_registrar_uso(v_chave, 'zz-outro-pc', '[]'::jsonb)->>'erro'
           = 'maquina_nao_ativada', 'aceitou uso de computador desconhecido';
    assert public.dumtech_registrar_uso('ZZZZ-ZZZZ-ZZZZ-ZZZZ', 'zz-uso-1', '[]'::jsonb)->>'erro'
           = 'nao_encontrada', 'aceitou uso de chave inexistente';
    assert public.dumtech_registrar_uso(v_chave, 'zz-uso-1', '"nao e lista"'::jsonb)->>'erro'
           = 'dados_incompletos', 'aceitou uso fora do formato';
    raise notice '2. uso vindo do Hub ................ ok';
end;
$$;

-- ======================================================= 3. QUEM E ADMIN ====
do $$
declare
    v_admin uuid := '11111111-1111-1111-1111-111111111111';
    v_outro uuid := '22222222-2222-2222-2222-222222222222';
begin
    insert into public.administradores (user_id, nome) values (v_admin, 'ZZ Dona DumTech');

    -- ninguem logado
    assert public.dumtech_admin_id() is null, 'sem login nao ha usuario';
    assert not public.dumtech_e_admin(), 'sem login ninguem e admin';

    -- logado, mas nao cadastrado
    perform set_config('request.jwt.claim.sub', v_outro::text, true);
    assert public.dumtech_admin_id() = v_outro, 'o id do usuario deveria vir do token';
    assert not public.dumtech_e_admin(), 'usuario fora da lista NAO e admin';

    -- logado e cadastrado, mas so com a senha (aal1): ainda nao
    perform set_config('request.jwt.claim.sub', v_admin::text, true);
    perform set_config('request.jwt.claims', format('{"sub":"%s","aal":"aal1","role":"authenticated"}', v_admin), true);
    assert not public.dumtech_e_admin(), 'senha sozinha (aal1) NAO pode abrir o painel';
    assert (public.dumtech_sou_admin() ->> 'admin')::boolean, 'a tela do codigo precisa saber que ele e admin';

    -- com o segundo fator (aal2)
    perform set_config('request.jwt.claims', format('{"sub":"%s","aal":"aal2","role":"authenticated"}', v_admin), true);
    assert public.dumtech_e_admin(), 'o administrador cadastrado deveria ser reconhecido';

    perform set_config('request.jwt.claim.sub', '', true);
    perform set_config('request.jwt.claims', '', true);
    raise notice '3. quem e admin .................... ok';
end;
$$;

-- ===================================================== 4. O QUE CADA UM VE ==
-- 4.1 a chave publica continua sem enxergar nada
do $$
begin
    begin
        execute 'set local role anon';
        perform 1 from public.clientes;
        raise exception 'a chave anon leu public.clientes!';
    exception when insufficient_privilege then null;
    end;

    begin
        execute 'set local role anon';
        perform 1 from public.uso_diario;
        raise exception 'a chave anon leu o uso dos clientes!';
    exception when insufficient_privilege then null;
    end;

    begin
        execute 'set local role anon';
        perform public.dumtech_e_admin();
        raise exception 'a chave anon perguntou se e admin!';
    exception when insufficient_privilege then null;
    end;
    raise notice '4.1 chave publica barrada .......... ok';
end;
$$;

-- 4.2 usuario logado que NAO e administrador nao ve linha nenhuma
do $$
declare
    v_quantos integer;
begin
    perform set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', true);
    perform set_config('request.jwt.claims', '{"sub":"22222222-2222-2222-2222-222222222222","aal":"aal2","role":"authenticated"}', true);
    set local role authenticated;

    select count(*) into v_quantos from public.clientes;
    assert v_quantos = 0, format('usuario comum viu %s cliente(s)', v_quantos);
    select count(*) into v_quantos from public.uso_diario;
    assert v_quantos = 0, 'usuario comum viu o uso dos clientes';
    select count(*) into v_quantos from public.painel_clientes;
    assert v_quantos = 0, 'usuario comum viu o painel';

    begin
        insert into public.comunicados (titulo) values ('ZZ Invasao');
        raise exception 'usuario comum escreveu um anuncio!';
    exception when insufficient_privilege then null;
    end;

    reset role;
    raise notice '4.2 logado sem ser admin ........... ok';
end;
$$;

-- 4.3 o administrador ve e escreve
do $$
declare
    v_quantos integer;
    v_resumo  record;
begin
    perform set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
    perform set_config('request.jwt.claims', '{"sub":"11111111-1111-1111-1111-111111111111","aal":"aal2","role":"authenticated"}', true);
    set local role authenticated;

    select count(*) into v_quantos from public.clientes;
    assert v_quantos > 0, 'o administrador precisa ver os clientes';

    select count(*) into v_quantos from public.uso_diario;
    assert v_quantos > 0, 'o administrador precisa ver o uso';

    select * into v_resumo from public.painel_resumo;
    assert v_resumo.clientes > 0 and v_resumo.licencas_ativas > 0,
        'o resumo do negocio veio vazio';
    assert v_resumo.aberturas_30d >= 16, 'o resumo nao contou as aberturas';

    -- escrever anuncio e o dia a dia do painel
    insert into public.comunicados (titulo, texto, alvo, produto_codigo, rotulo)
    values ('ZZ Leve o Financeiro', 'Sua venda a prazo vira conta sozinha',
            'sem_produto', 'FINANCEIRO', 'Oferta');
    update public.comunicados set rotulo = 'Novidade' where titulo = 'ZZ Leve o Financeiro';
    assert (select rotulo from public.comunicados where titulo = 'ZZ Leve o Financeiro')
           = 'Novidade', 'o administrador deveria conseguir editar o anuncio';

    -- e mexer no catalogo
    update public.produtos set preco = 259.00 where codigo = 'ESTOQUE';
    assert (select preco from public.produtos where codigo = 'ESTOQUE') = 259.00,
        'o administrador deveria conseguir mudar o preco';

    reset role;
    raise notice '4.3 administrador ve e escreve ..... ok';
end;
$$;

-- ================================================== 5. AS VISOES DO PAINEL ==
do $$
declare
    v_ficha  record;
    v_modulo record;
    v_reco   record;
begin
    perform set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
    perform set_config('request.jwt.claims', '{"sub":"11111111-1111-1111-1111-111111111111","aal":"aal2","role":"authenticated"}', true);
    set local role authenticated;

    -- 5.1 a ficha do cliente
    select * into v_ficha from public.painel_clientes where email = 'zz.uso@teste.local';
    assert v_ficha.chave is not null, 'a ficha precisa trazer a chave';
    assert v_ficha.produtos = 2, format('produtos errados na ficha: %s', v_ficha.produtos);
    assert v_ficha.produtos_codigos @> array['ESTOQUE', 'VENDAS'], 'faltaram codigos na ficha';
    assert v_ficha.computadores = 1, 'a ficha precisa contar os computadores';
    assert v_ficha.aberturas_30d >= 16, 'a ficha precisa somar o uso';
    assert v_ficha.ultimo_uso = current_date, 'a ficha precisa saber o ultimo dia de uso';
    assert v_ficha.situacao = 'ativa', 'situacao errada na ficha';

    -- 5.2 o retrato do modulo
    select * into v_modulo from public.painel_modulos where codigo = 'VENDAS';
    assert v_modulo.clientes >= 1, 'o modulo precisa contar quem tem';
    assert v_modulo.aberturas_30d >= 11, 'o modulo precisa contar as aberturas';

    -- 5.3 a recomendacao: usa Vendas, nao tem Financeiro
    select * into v_reco
      from public.painel_recomendacoes
     where cliente_id = (select id from public.clientes where email = 'zz.uso@teste.local')
       and recomendado = 'FINANCEIRO';
    assert v_reco.porque_tem = 'VENDAS',
        'a recomendacao deveria nascer do modulo que ele usa';
    assert v_reco.aberturas_origem >= 11,
        format('a recomendacao precisa saber o quanto ele usa: %s', v_reco.aberturas_origem);
    assert v_reco.porque ilike '%conta a receber%', 'a recomendacao precisa dizer por que';

    -- nao recomenda o que ele ja tem
    assert not exists (
        select 1 from public.painel_recomendacoes
         where cliente_id = (select id from public.clientes where email = 'zz.uso@teste.local')
           and recomendado in ('ESTOQUE', 'VENDAS')), 'recomendou o que ele ja tem';

    reset role;
    raise notice '5. visoes do painel ................ ok';
end;
$$;

do $$
begin
    raise notice '';
    raise notice 'TUDO CERTO - nada foi gravado (rollback no fim do arquivo).';
end;
$$;

rollback;
