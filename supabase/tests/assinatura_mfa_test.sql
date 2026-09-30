-- =============================================================================
-- Teste da migration 20260912210000: porta da licenca assinada, dois fatores
-- no painel, auditoria e dados da chave.
--
-- Roda inteiro dentro de uma transacao e desfaz tudo no fim: pode ser colado no
-- SQL Editor do Supabase, mesmo em producao.
-- =============================================================================

begin;

-- dados de trabalho (todos com prefixo ZZ, e somem no rollback)
do $$
declare
    v_cliente uuid;
    v_chave   text;
begin
    insert into public.clientes (nome, email, telefone)
    values ('ZZ Assinada', 'zz.assinada@teste.local', '11999990000')
    returning id into v_cliente;
    select chave into v_chave
      from public.dumtech_emitir_licenca(v_cliente, array['ESTOQUE', 'VENDAS']);
    perform public.dumtech_ativar_licenca(v_chave, 'zz-pc-assinado');
    insert into public.administradores (user_id, nome)
    values ('33333333-3333-3333-3333-333333333333', 'ZZ Admin');
end;
$$;

-- ============================================ 1. A PORTA DA ASSINATURA ======
do $$
declare
    v_chave text := (select l.chave from public.licencas l
                       join public.clientes c on c.id = l.cliente_id
                      where c.email = 'zz.assinada@teste.local');
    v_resposta jsonb;
begin
    v_resposta := public.dumtech_licenca_para_assinar(v_chave, 'zz-pc-assinado', '203.0.113.50');
    assert (v_resposta ->> 'ok')::boolean, format('a funcao deveria confirmar: %s', v_resposta);
    assert v_resposta -> 'produtos' = '["ESTOQUE", "VENDAS"]'::jsonb, 'produtos errados';

    -- a MESMA regra do Hub: computador que nao ativou nao ganha licenca assinada
    assert public.dumtech_licenca_para_assinar(v_chave, 'zz-outro-pc', '203.0.113.50') ->> 'erro'
           = 'maquina_nao_ativada', 'assinaria licenca para computador nao ativado';
    assert public.dumtech_licenca_para_assinar('ZZZZ-ZZZZ-ZZZZ-ZZZZ', 'zz-pc-assinado', '203.0.113.50') ->> 'erro'
           = 'nao_encontrada', 'assinaria chave inexistente';

    -- suspensa no painel: a funcao recusa, e o Hub bloqueia na conferencia
    update public.licencas set status = 'suspensa' where chave = v_chave;
    assert public.dumtech_licenca_para_assinar(v_chave, 'zz-pc-assinado', '203.0.113.50') ->> 'erro'
           = 'inativa', 'assinaria licenca suspensa';
    update public.licencas set status = 'ativa' where chave = v_chave;

    -- o limite conta o endereco que a funcao repassou (nao o do servidor da funcao)
    insert into public.limites_de_taxa (acao, quem, janela, vezes)
    values ('licenca_ip', '203.0.113.51',
            date_bin(interval '1 hour', now(), timestamptz '2000-01-01 00:00:00+00'), 120);
    assert public.dumtech_licenca_para_assinar(v_chave, 'zz-pc-assinado', '203.0.113.51') ->> 'erro'
           = 'muitas_tentativas', 'o limite por endereco nao valeu na porta da assinatura';

    -- PENTEST 17/09/2026: o computador vai preso a ativacao. Quem copia o
    -- license.json (que traz chave e maquina) nao ganha licenca assinada para
    -- a maquina dele.
    delete from public.limites_de_taxa where acao = 'licenca_ip';
    update public.licencas set status = 'ativa' where chave = v_chave;
    assert (public.dumtech_licenca_para_assinar(v_chave, 'zz-pc-assinado', '203.0.113.60',
            '0123456789abcdef0123456789abcdef') ->> 'ok')::boolean,
        'o primeiro computador tinha que ser aceito';
    assert public.dumtech_licenca_para_assinar(v_chave, 'zz-pc-assinado', '203.0.113.60',
            'fedcba9876543210fedcba9876543210') ->> 'erro' = 'outro_computador',
        'o license.json copiado ganhou licenca assinada em outro computador';
    -- ativar de novo solta a marca: quem reinstala o Windows nao fica preso
    perform public.dumtech_ativar_licenca(v_chave, 'zz-pc-assinado', 'caixa');
    assert (public.dumtech_licenca_para_assinar(v_chave, 'zz-pc-assinado', '203.0.113.60',
            'fedcba9876543210fedcba9876543210') ->> 'ok')::boolean,
        'depois de ativar de novo, o computador novo tinha que entrar';

    -- a porta antiga do Hub continua respondendo igual
    assert (public.dumtech_verificar_licenca(v_chave, 'zz-pc-assinado') ->> 'ok')::boolean,
        'a verificacao do Hub parou de funcionar';

    -- so o servidor chama
    assert has_function_privilege('service_role', 'public.dumtech_licenca_para_assinar(text,text,text,text)', 'execute'),
        'a Edge Function (service_role) precisa chamar';
    assert not has_function_privilege('anon', 'public.dumtech_licenca_para_assinar(text,text,text,text)', 'execute'),
        'a chave anon nao pode chamar a porta da assinatura (ela nao conta o limite do visitante)';
    assert not has_function_privilege('authenticated', 'public.dumtech_licenca_para_assinar(text,text,text,text)', 'execute'),
        'usuario logado nao pode chamar a porta da assinatura';
    assert not has_function_privilege('anon', 'public.dumtech_verificar_interno(text,text)', 'execute'),
        'o miolo sem limite nao pode ficar exposto';
    raise notice '1. porta da licenca assinada ....... ok';
end;
$$;

-- =============================================== 2. DOIS FATORES ============
do $$
declare
    v_admin   text := '33333333-3333-3333-3333-333333333333';
    v_quantos integer;
begin
    -- so a senha (aal1): a policy nao entrega nada
    perform set_config('request.jwt.claim.sub', v_admin, true);
    perform set_config('request.jwt.claims', format('{"sub":"%s","aal":"aal1","role":"authenticated"}', v_admin), true);
    assert public.dumtech_sou_admin() = '{"admin": true, "nivel": "aal1"}'::jsonb,
        format('a tela do codigo precisa saber quem e e em que nivel: %s', public.dumtech_sou_admin());
    set local role authenticated;
    select count(*) into v_quantos from public.clientes;
    assert v_quantos = 0, format('com senha so, o painel viu %s cliente(s)', v_quantos);
    reset role;

    -- senha + codigo (aal2)
    perform set_config('request.jwt.claims', format('{"sub":"%s","aal":"aal2","role":"authenticated"}', v_admin), true);
    set local role authenticated;
    select count(*) into v_quantos from public.clientes;
    assert v_quantos > 0, 'com os dois fatores o painel precisa ver os clientes';
    reset role;

    -- quem nao e admin, mesmo com dois fatores, continua de fora
    perform set_config('request.jwt.claim.sub', '44444444-4444-4444-4444-444444444444', true);
    perform set_config('request.jwt.claims', '{"sub":"44444444-4444-4444-4444-444444444444","aal":"aal2","role":"authenticated"}', true);
    assert public.dumtech_sou_admin() ->> 'admin' = 'false', 'conta comum se disse admin';
    assert not public.dumtech_e_admin(), 'conta comum com aal2 NAO e admin';

    assert not has_function_privilege('anon', 'public.dumtech_sou_admin()', 'execute'),
        'a chave anon nao pergunta quem e admin';

    perform set_config('request.jwt.claim.sub', '', true);
    perform set_config('request.jwt.claims', '', true);
    raise notice '2. dois fatores .................... ok';
end;
$$;

-- ==================================================== 3. AUDITORIA ==========
do $$
declare
    v_admin  text := '33333333-3333-3333-3333-333333333333';
    v_antes  bigint := (select count(*) from public.auditoria);
    v_linha  public.auditoria;
    v_quantos integer;
begin
    -- administrador muda um preco pelo painel
    perform set_config('request.jwt.claim.sub', v_admin, true);
    perform set_config('request.jwt.claims',
        format('{"sub":"%s","aal":"aal2","role":"authenticated","email":"zz.admin@dumtech.local"}', v_admin), true);
    set local role authenticated;
    update public.produtos set preco = 777.00 where codigo = 'AGENDA';
    reset role;

    select * into v_linha from public.auditoria
     where tabela = 'produtos' and operacao = 'update' order by id desc limit 1;
    assert found, 'mudar preco pelo painel nao ficou registrado';
    assert v_linha.origem = 'painel' and v_linha.quem = v_admin::uuid, 'auditoria sem dono';
    assert v_linha.quem_email = 'zz.admin@dumtech.local', 'auditoria sem e-mail de quem mexeu';
    assert v_linha.depois ? 'preco' and (v_linha.depois ->> 'preco')::numeric = 777,
        format('o valor novo precisa estar la: %s', v_linha.depois);
    assert not (v_linha.depois ? 'atualizado_em'), 'carimbo de hora nao e alteracao';
    assert not (v_linha.depois ? 'nome'), 'so o que mudou vai para a auditoria';

    -- o Hub (anon) conferindo a licenca nao enche a auditoria
    v_antes := (select count(*) from public.auditoria);
    perform set_config('request.jwt.claims', '{"role":"anon"}', true);
    perform public.dumtech_registrar_pedido('ZZ Visitante', 'zz.visitante@teste.local', '', array['AGENDA']);
    assert (select count(*) from public.auditoria) = v_antes, 'pedido do site nao e alteracao de administrador';

    -- servidor (service_role) so tocando a hora da checagem: nada
    perform set_config('request.jwt.claims', '{"role":"service_role"}', true);
    update public.ativacoes set ultima_checagem = now() where maquina = 'ZZ-PC-ASSINADO';
    assert (select count(*) from public.auditoria) = v_antes, 'hora da checagem virou alteracao';

    -- SQL Editor (sem token) tambem fica registrado
    perform set_config('request.jwt.claims', '', true);
    delete from public.comunicados where titulo like 'ZZ%';
    insert into public.comunicados (titulo) values ('ZZ Auditado');
    delete from public.comunicados where titulo = 'ZZ Auditado';
    select * into v_linha from public.auditoria where tabela = 'comunicados' order by id desc limit 1;
    assert v_linha.operacao = 'delete' and v_linha.origem = 'sql' and v_linha.antes ->> 'titulo' = 'ZZ Auditado',
        'apagar precisa guardar o que foi apagado';

    -- quem le e quem apaga
    perform set_config('request.jwt.claims', format('{"sub":"%s","aal":"aal2","role":"authenticated"}', v_admin), true);
    set local role authenticated;
    select count(*) into v_quantos from public.auditoria;
    assert v_quantos > 0, 'o administrador precisa ler a auditoria';
    begin
        delete from public.auditoria;
        raise exception 'o administrador apagou a auditoria!';
    exception when insufficient_privilege then null;
    end;
    reset role;

    perform set_config('request.jwt.claim.sub', '44444444-4444-4444-4444-444444444444', true);
    perform set_config('request.jwt.claims', '{"sub":"44444444-4444-4444-4444-444444444444","aal":"aal2","role":"authenticated"}', true);
    set local role authenticated;
    select count(*) into v_quantos from public.auditoria;
    assert v_quantos = 0, 'conta comum leu a auditoria';
    reset role;

    assert not has_table_privilege('anon', 'public.auditoria', 'select'), 'a anon le a auditoria';
    assert not has_table_privilege('authenticated', 'public.auditoria', 'truncate'), 'TRUNCATE na auditoria';

    perform set_config('request.jwt.claim.sub', '', true);
    perform set_config('request.jwt.claims', '', true);
    raise notice '3. auditoria ....................... ok';
end;
$$;

-- ================================================= 4. DADOS DA CHAVE ========
do $$
declare
    v_admin   text := '33333333-3333-3333-3333-333333333333';
    v_licenca uuid := (select l.id from public.licencas l
                         join public.clientes c on c.id = l.cliente_id
                        where c.email = 'zz.assinada@teste.local');
    v_dados   jsonb;
begin
    perform set_config('request.jwt.claim.sub', v_admin, true);
    perform set_config('request.jwt.claims', format('{"sub":"%s","aal":"aal2","role":"authenticated"}', v_admin), true);
    set local role authenticated;
    v_dados := public.dumtech_dados_da_chave(v_licenca);
    reset role;
    assert v_dados ->> 'email' = 'zz.assinada@teste.local', format('dados errados: %s', v_dados);
    assert jsonb_array_length(v_dados -> 'modulos') = 2, 'a mensagem precisa listar os modulos';
    assert v_dados ->> 'chave' ~ '^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$', 'a mensagem precisa da chave';

    -- conta comum: nada (a policy responde, nao a funcao)
    perform set_config('request.jwt.claim.sub', '44444444-4444-4444-4444-444444444444', true);
    perform set_config('request.jwt.claims', '{"sub":"44444444-4444-4444-4444-444444444444","aal":"aal2","role":"authenticated"}', true);
    set local role authenticated;
    v_dados := public.dumtech_dados_da_chave(v_licenca);
    reset role;
    assert v_dados is null, 'conta comum leu a chave de um cliente';
    assert not has_function_privilege('anon', 'public.dumtech_dados_da_chave(uuid)', 'execute'),
        'a anon nao pode pedir dados de chave';

    perform set_config('request.jwt.claim.sub', '', true);
    perform set_config('request.jwt.claims', '', true);
    raise notice '4. dados da chave .................. ok';
end;
$$;

do $$
begin
    raise notice '';
    raise notice 'TUDO CERTO - nada foi gravado (rollback no fim do arquivo).';
end;
$$;

rollback;
