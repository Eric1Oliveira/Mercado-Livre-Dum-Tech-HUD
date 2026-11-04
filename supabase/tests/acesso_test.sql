-- =============================================================================
-- Teste da migration 20261102120000: contas, permissoes e computadores da chave.
--
-- Roda dentro de uma transacao e desfaz tudo no fim: pode ser colado no SQL
-- Editor do Supabase, mesmo em producao.
-- =============================================================================

begin;

do $$
declare
    v_cliente uuid;
    v_outro   uuid;
    v_chave   text;
    v_outra   text;
    v_licenca uuid;
    v_lic2    uuid;
    v_maquina constant text := 'AAAA-BBBB-CCCC-CONT';
    v_segunda constant text := 'AAAA-BBBB-CCCC-SEGU';
    v_pc      constant text := repeat('a', 32);
    v_pc2     constant text := repeat('b', 32);
    v_hash    constant text := 'pbkdf2$600000$c2Fs$ZGVyaXZhZG8';
    v_hash2   constant text := 'pbkdf2$600000$c2Fs$b3V0cm8';
    v_adm     uuid;
    v_func    uuid;
    v_sessao  text;
    v_sessao_f text;
    v_marca   text;
    r         jsonb;
    i         integer;
begin
    insert into public.clientes (nome, email) values ('ZZ Contas', 'zz.contas@teste.local')
    returning id into v_cliente;
    insert into public.clientes (nome, email) values ('ZZ Vizinho', 'zz.vizinho@teste.local')
    returning id into v_outro;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);
    select chave into v_outra from public.dumtech_emitir_licenca(v_outro, array['VENDAS']);
    select id into v_licenca from public.licencas where chave = v_chave;
    select id into v_lic2 from public.licencas where chave = v_outra;
    perform public.dumtech_ativar_licenca(v_chave, v_maquina, 'caixa');
    perform public.dumtech_ativar_licenca(v_outra, v_maquina, 'caixa');
    update public.ativacoes set computador = v_pc where licenca_id in (v_licenca, v_lic2);

    -- ------------------------------------------- loja sem conta nao sente nada
    v_marca := public.dumtech_licenca_marca(v_chave, v_maquina);
    r := public.dumtech_licenca_para_assinar(v_chave, v_maquina, '', v_pc);
    assert (r->>'ok')::boolean and not (r->>'contas')::boolean, 'sem conta: ' || r::text;
    assert jsonb_array_length(r->'acesso'->'usuarios') = 0;
    assert not (r->'acesso'->>'exigir_conta')::boolean;

    -- celular sem sessao segue funcionando enquanto nao ha conta
    r := public.dumtech_celular_iniciar(v_chave, v_maquina, v_pc);
    assert (r->>'ok')::boolean, 'celular sem conta: ' || r::text;

    -- ------------------------------------------------------- o primeiro ADM
    -- computador estranho nao cria
    r := public.dumtech_acesso_criar_primeiro(v_chave, v_maquina, v_pc2, 'Dona', 'dona', 'dona@teste.local', v_hash);
    assert r->>'erro' = 'nao_autorizado', 'computador estranho criou: ' || r::text;
    -- dados ruins
    r := public.dumtech_acesso_criar_primeiro(v_chave, v_maquina, v_pc, 'Dona', 'a b', 'dona@teste.local', v_hash);
    assert r->>'erro' = 'login_invalido', 'login ruim: ' || r::text;
    r := public.dumtech_acesso_criar_primeiro(v_chave, v_maquina, v_pc, 'Dona', 'dona', 'semarroba', v_hash);
    assert r->>'erro' = 'email_invalido', 'adm sem e-mail: ' || r::text;
    r := public.dumtech_acesso_criar_primeiro(v_chave, v_maquina, v_pc, 'Dona', 'dona', 'dona@teste.local', 'senha-em-claro');
    assert r->>'erro' = 'senha_invalida', 'senha em claro aceita: ' || r::text;

    r := public.dumtech_acesso_criar_primeiro(v_chave, v_maquina, v_pc, ' Dona ', ' Dona.Loja ', 'dona@teste.local', v_hash, '10.0.0.1');
    assert (r->>'ok')::boolean, 'primeiro ADM recusado: ' || r::text;
    assert r->'usuario'->>'login' = 'dona.loja', 'login nao normalizou';
    assert r->'usuario'->>'papel' = 'adm';
    v_adm := (r->'usuario'->>'id')::uuid;
    v_sessao := r->>'sessao';
    assert length(v_sessao) >= 40, 'sessao curta';
    assert not exists (select 1 from public.licenca_usuario_sessoes where sessao_hash = v_sessao),
        'sessao em claro no banco';
    assert not (r::text like '%' || v_hash || '%'), 'hash saiu na resposta';
    assert not ((r->'resumo')::text like '%senha_hash%'), 'resumo com hash';
    assert jsonb_array_length(r->'resumo'->'usuarios') = 1;

    -- so vale uma vez
    r := public.dumtech_acesso_criar_primeiro(v_chave, v_maquina, v_pc, 'Outro', 'outro', 'o@teste.local', v_hash);
    assert r->>'erro' = 'ja_tem_contas', 'criou segundo primeiro: ' || r::text;

    -- a marca muda quando ha conta, para o Hub conferir
    assert public.dumtech_licenca_marca(v_chave, v_maquina) <> v_marca, 'marca nao mudou com conta';
    r := public.dumtech_licenca_para_assinar(v_chave, v_maquina, '', v_pc);
    assert (r->>'contas')::boolean, 'contas falso com conta: ' || r::text;

    -- -------------------------------------------------- entrar e as travas
    r := public.dumtech_acesso_buscar(v_chave, v_maquina, v_pc, 'ninguem', '10.0.0.1');
    assert r->>'erro' = 'credenciais', 'login inexistente: ' || r::text;
    r := public.dumtech_acesso_buscar(v_outra, v_maquina, v_pc, 'dona.loja', '10.0.0.1');
    assert r->>'erro' = 'credenciais', 'login de outra chave: ' || r::text;
    r := public.dumtech_acesso_buscar(v_chave, v_maquina, v_pc, 'DONA.LOJA', '10.0.0.1');
    assert (r->>'ok')::boolean and r->>'senha_hash' = v_hash, 'buscar: ' || r::text;

    for i in 1..4 loop
        r := public.dumtech_acesso_resultado(v_chave, v_maquina, v_pc, v_adm, false, '10.0.0.1');
        assert r->>'erro' = 'credenciais', 'erro ' || i || ': ' || r::text;
    end loop;
    r := public.dumtech_acesso_resultado(v_chave, v_maquina, v_pc, v_adm, false, '10.0.0.1');
    assert r->>'erro' = 'conta_travada', 'quinto erro nao travou: ' || r::text;
    assert (select bloqueado_ate > now() + interval '14 minutes' and bloqueado_ate < now() + interval '16 minutes'
              from public.licenca_usuarios where id = v_adm), 'trava de 15 minutos';
    r := public.dumtech_acesso_buscar(v_chave, v_maquina, v_pc, 'dona.loja', '10.0.0.1');
    assert r->>'erro' = 'conta_travada', 'travada entrou: ' || r::text;

    -- a janela dobra na proxima sequencia, com teto de 60
    update public.licenca_usuarios set bloqueado_ate = now() - interval '1 second' where id = v_adm;
    for i in 1..5 loop
        r := public.dumtech_acesso_resultado(v_chave, v_maquina, v_pc, v_adm, false, '10.0.0.1');
    end loop;
    assert (select bloqueado_ate > now() + interval '29 minutes' and bloqueado_ate < now() + interval '31 minutes'
              from public.licenca_usuarios where id = v_adm), 'janela nao dobrou';
    update public.licenca_usuarios set bloqueado_ate = now() - interval '1 second', travas = 9 where id = v_adm;
    for i in 1..5 loop
        r := public.dumtech_acesso_resultado(v_chave, v_maquina, v_pc, v_adm, false, '10.0.0.1');
    end loop;
    assert (select bloqueado_ate < now() + interval '61 minutes'
              from public.licenca_usuarios where id = v_adm), 'teto de 60 minutos';

    update public.licenca_usuarios set bloqueado_ate = null where id = v_adm;
    r := public.dumtech_acesso_resultado(v_chave, v_maquina, v_pc, v_adm, true, '10.0.0.1');
    assert (r->>'ok')::boolean, 'senha certa recusada: ' || r::text;
    v_sessao := r->>'sessao';
    assert (select erros = 0 and travas = 0 and ultimo_acesso is not null
              from public.licenca_usuarios where id = v_adm), 'nao limpou a trava';

    -- ------------------------------------------------------- gerir usuarios
    r := public.dumtech_acesso_salvar_usuario(v_chave, v_maquina, v_pc, v_sessao, null,
        '{"nome":"Maria","login":"maria","papel":"funcionario","modulos":["vendas","estoque"],"avisos":["estoque_baixo"]}',
        v_hash);
    assert (r->>'ok')::boolean, 'criar funcionario: ' || r::text;
    v_func := (r->'usuario'->>'id')::uuid;
    assert (r->'usuario'->>'trocar_senha')::boolean, 'senha definida por outro nao pede troca';
    assert (r->'usuario'->'modulos') ? 'vendas';

    r := public.dumtech_acesso_salvar_usuario(v_chave, v_maquina, v_pc, v_sessao, null,
        '{"nome":"Maria 2","login":"MARIA","papel":"funcionario"}', v_hash);
    assert r->>'erro' = 'login_em_uso', 'login repetido: ' || r::text;
    r := public.dumtech_acesso_salvar_usuario(v_chave, v_maquina, v_pc, v_sessao, null,
        '{"nome":"Sem Senha","login":"semsenha","papel":"funcionario"}', '');
    assert r->>'erro' = 'senha_invalida', 'conta sem senha: ' || r::text;
    r := public.dumtech_acesso_salvar_usuario(v_chave, v_maquina, v_pc, v_sessao, null,
        '{"nome":"Chefe","login":"chefe","papel":"adm"}', v_hash);
    assert r->>'erro' = 'email_invalido', 'adm sem e-mail: ' || r::text;

    -- ADM nao guarda lista de modulos: ve tudo
    r := public.dumtech_acesso_salvar_usuario(v_chave, v_maquina, v_pc, v_sessao, null,
        '{"nome":"Chefe","login":"chefe","email":"chefe@teste.local","papel":"adm","modulos":["vendas"]}', v_hash);
    assert (r->>'ok')::boolean and jsonb_array_length(r->'usuario'->'modulos') = 0, 'adm com modulos: ' || r::text;
    r := public.dumtech_acesso_apagar_usuario(v_chave, v_maquina, v_pc, v_sessao, (r->'usuario'->>'id')::uuid);
    assert (r->>'ok')::boolean, 'apagar adm extra: ' || r::text;

    -- funcionario entra e nao gerencia
    r := public.dumtech_acesso_resultado(v_chave, v_maquina, v_pc, v_func, true, '10.0.0.1');
    v_sessao_f := r->>'sessao';
    r := public.dumtech_acesso_usuarios(v_chave, v_maquina, v_pc, v_sessao_f);
    assert r->>'erro' = 'so_adm', 'funcionario listou: ' || r::text;
    r := public.dumtech_acesso_salvar_usuario(v_chave, v_maquina, v_pc, v_sessao_f, v_func,
        '{"nome":"Maria","login":"maria","papel":"adm","email":"m@teste.local"}', '');
    assert r->>'erro' = 'so_adm', 'funcionario virou adm: ' || r::text;
    r := public.dumtech_acesso_senha_usuario(v_chave, v_maquina, v_pc, v_sessao_f, v_adm, v_hash2);
    assert r->>'erro' = 'so_adm', 'funcionario trocou senha do adm: ' || r::text;
    r := public.dumtech_acesso_apagar_usuario(v_chave, v_maquina, v_pc, v_sessao_f, v_adm);
    assert r->>'erro' = 'so_adm';
    r := public.dumtech_acesso_computadores(v_chave, v_maquina, v_pc, v_sessao_f);
    assert r->>'erro' = 'so_adm';
    r := public.dumtech_acesso_liberar_computador(v_chave, v_maquina, v_pc, v_sessao_f, v_maquina);
    assert r->>'erro' = 'so_adm';

    -- sessao de outra licenca ou vencida
    r := public.dumtech_acesso_usuarios(v_outra, v_maquina, v_pc, v_sessao);
    assert r->>'erro' = 'sessao_vencida', 'sessao atravessou licenca: ' || r::text;
    r := public.dumtech_acesso_usuarios(v_chave, v_maquina, v_pc, 'inventada');
    assert r->>'erro' = 'sessao_vencida';

    r := public.dumtech_acesso_usuarios(v_chave, v_maquina, v_pc, v_sessao);
    assert (r->>'ok')::boolean and jsonb_array_length(r->'usuarios') = 2, 'listar: ' || r::text;
    assert not (r::text like '%senha_hash%'), 'lista com hash';

    -- senha provisoria nao administra nada: so serve para criar a senha
    update public.licenca_usuarios set trocar_senha = true where id = v_adm;
    r := public.dumtech_acesso_usuarios(v_chave, v_maquina, v_pc, v_sessao);
    assert r->>'erro' = 'trocar_senha', 'provisoria gerenciou: ' || r::text;
    r := public.dumtech_acesso_buscar_sessao(v_chave, v_maquina, v_pc, v_sessao);
    assert (r->>'ok')::boolean, 'provisoria nao troca a senha: ' || r::text;
    update public.licenca_usuarios set trocar_senha = false where id = v_adm;

    -- ------------------------------------------------- antes de gastar CPU
    r := public.dumtech_acesso_antes_de_derivar(v_chave, v_maquina, v_pc, '10.0.0.9');
    assert (r->>'ok')::boolean, 'antes de derivar: ' || r::text;
    r := public.dumtech_acesso_antes_de_derivar('CHAVE-INVENTADA', v_maquina, v_pc, '10.0.0.9');
    assert r->>'erro' = 'nao_autorizado', 'chave inventada passou: ' || r::text;
    r := public.dumtech_acesso_antes_de_derivar(v_chave, v_maquina, v_pc2, '10.0.0.9');
    assert r->>'erro' = 'nao_autorizado', 'computador estranho passou: ' || r::text;

    -- ------------------------------------------------------- o ultimo ADM
    r := public.dumtech_acesso_salvar_usuario(v_chave, v_maquina, v_pc, v_sessao, v_adm,
        '{"nome":"Dona","login":"dona.loja","email":"dona@teste.local","papel":"funcionario"}', '');
    assert r->>'erro' = 'ultimo_adm', 'rebaixou o ultimo: ' || r::text;
    r := public.dumtech_acesso_salvar_usuario(v_chave, v_maquina, v_pc, v_sessao, v_adm,
        '{"nome":"Dona","login":"dona.loja","email":"dona@teste.local","papel":"adm","ativo":false}', '');
    assert r->>'erro' = 'ultimo_adm', 'bloqueou o ultimo: ' || r::text;
    r := public.dumtech_acesso_apagar_usuario(v_chave, v_maquina, v_pc, v_sessao, v_adm);
    assert r->>'erro' = 'apagar_a_si', 'apagou a si: ' || r::text;

    -- ------------------------------------------------------ senhas e versao
    r := public.dumtech_acesso_senha_usuario(v_chave, v_maquina, v_pc, v_sessao, v_func, v_hash2);
    assert (r->>'ok')::boolean, 'redefinir: ' || r::text;
    assert (select senha_versao = 2 and trocar_senha and senha_hash = v_hash2
              from public.licenca_usuarios where id = v_func), 'versao nao subiu';
    r := public.dumtech_acesso_usuarios(v_chave, v_maquina, v_pc, v_sessao_f);
    assert r->>'erro' = 'sessao_vencida', 'sessao sobreviveu a redefinicao: ' || r::text;

    r := public.dumtech_acesso_resultado(v_chave, v_maquina, v_pc, v_func, true, '10.0.0.1');
    v_sessao_f := r->>'sessao';
    r := public.dumtech_acesso_buscar_sessao(v_chave, v_maquina, v_pc, v_sessao_f);
    assert r->>'senha_hash' = v_hash2, 'buscar_sessao: ' || r::text;
    r := public.dumtech_acesso_gravar_senha(v_chave, v_maquina, v_pc, v_sessao_f, v_hash);
    assert (r->>'ok')::boolean, 'gravar senha: ' || r::text;
    assert (select senha_versao = 3 and not trocar_senha from public.licenca_usuarios where id = v_func);

    -- conta travada nao testa senha pela rota de troca
    update public.licenca_usuarios set bloqueado_ate = now() + interval '5 minutes' where id = v_func;
    r := public.dumtech_acesso_buscar_sessao(v_chave, v_maquina, v_pc, v_sessao_f);
    assert r->>'erro' = 'conta_travada' and not r ? 'senha_hash', 'travada testou senha: ' || r::text;
    update public.licenca_usuarios set bloqueado_ate = null where id = v_func;

    -- ------------------------------------------------------ esqueci a senha
    r := public.dumtech_acesso_pedir_codigo(v_chave, v_maquina, v_pc, 'ninguem', '10.0.0.2');
    assert (r->>'ok')::boolean and not r ? 'codigo' and not r ? 'sem_email', 'inexistente: ' || r::text;
    r := public.dumtech_acesso_pedir_codigo(v_chave, v_maquina, v_pc, 'maria', '10.0.0.2');
    assert (r->>'sem_email')::boolean, 'funcionario sem e-mail: ' || r::text;

    r := public.dumtech_acesso_pedir_codigo(v_chave, v_maquina, v_pc, 'dona.loja', '10.0.0.2');
    assert r->>'email' = 'dona@teste.local' and r->>'codigo' ~ '^[0-9]{6}$', 'pedir codigo: ' || r::text;
    declare
        v_codigo text := r->>'codigo';
        v_errado text := lpad(((v_codigo::int + 1) % 1000000)::text, 6, '0');
    begin
        assert not exists (select 1 from public.licenca_usuario_codigos where codigo_hash = v_codigo),
            'codigo em claro no banco';
        r := public.dumtech_acesso_redefinir(v_chave, v_maquina, v_pc, 'dona.loja', v_errado, v_hash2, '10.0.0.2');
        assert r->>'erro' = 'codigo_invalido', 'codigo errado: ' || r::text;
        -- codigo de outra conta nao serve aqui
        r := public.dumtech_acesso_redefinir(v_chave, v_maquina, v_pc, 'maria', v_codigo, v_hash2, '10.0.0.2');
        assert r->>'erro' = 'codigo_invalido', 'codigo atravessou conta: ' || r::text;
        r := public.dumtech_acesso_redefinir(v_chave, v_maquina, v_pc, 'dona.loja', v_codigo, v_hash2, '10.0.0.2');
        assert (r->>'ok')::boolean, 'redefinir por codigo: ' || r::text;
        v_sessao := r->>'sessao';
        assert (select senha_hash = v_hash2 and email_confirmado and senha_versao = 2
                  from public.licenca_usuarios where id = v_adm), 'nao gravou a senha nova';
        r := public.dumtech_acesso_redefinir(v_chave, v_maquina, v_pc, 'dona.loja', v_codigo, v_hash, '10.0.0.2');
        assert r->>'erro' = 'codigo_invalido', 'codigo usado duas vezes: ' || r::text;
    end;

    -- codigo vencido e cinco tentativas
    r := public.dumtech_acesso_pedir_codigo(v_chave, v_maquina, v_pc, 'dona.loja', '10.0.0.2');
    update public.licenca_usuario_codigos set expira_em = now() - interval '1 minute'
     where usuario_id = v_adm and usado_em is null;
    r := public.dumtech_acesso_redefinir(v_chave, v_maquina, v_pc, 'dona.loja', r->>'codigo', v_hash, '10.0.0.2');
    assert r->>'erro' = 'codigo_invalido', 'codigo vencido: ' || r::text;

    r := public.dumtech_acesso_pedir_codigo(v_chave, v_maquina, v_pc, 'dona.loja', '10.0.0.2');
    declare
        v_certo  text := r->>'codigo';
        v_errado text := lpad(((v_certo::int + 1) % 1000000)::text, 6, '0');
    begin
        for i in 1..5 loop
            r := public.dumtech_acesso_redefinir(v_chave, v_maquina, v_pc, 'dona.loja', v_errado, v_hash, '10.0.0.2');
        end loop;
        assert r->>'erro' = 'codigo_bloqueado', 'cinco erros: ' || r::text;
        r := public.dumtech_acesso_redefinir(v_chave, v_maquina, v_pc, 'dona.loja', v_certo, v_hash, '10.0.0.2');
        assert r->>'erro' = 'codigo_invalido', 'codigo queimado voltou: ' || r::text;
    end;

    -- confirmar e-mail
    update public.licenca_usuarios set email_confirmado = false where id = v_adm;
    r := public.dumtech_acesso_codigo_email(v_chave, v_maquina, v_pc, v_sessao);
    assert r->>'codigo' ~ '^[0-9]{6}$', 'codigo de confirmacao: ' || r::text;
    r := public.dumtech_acesso_confirmar_email(v_chave, v_maquina, v_pc, v_sessao, r->>'codigo');
    assert (r->>'ok')::boolean, 'confirmar: ' || r::text;
    assert (select email_confirmado from public.licenca_usuarios where id = v_adm);

    -- ------------------------------------------------- conta bloqueada
    r := public.dumtech_acesso_salvar_usuario(v_chave, v_maquina, v_pc, v_sessao, v_func,
        '{"nome":"Maria","login":"maria","papel":"funcionario","ativo":false}', '');
    assert (r->>'ok')::boolean, 'bloquear: ' || r::text;
    r := public.dumtech_acesso_resultado(v_chave, v_maquina, v_pc, v_func, true, '10.0.0.1');
    assert r->>'erro' = 'conta_bloqueada', 'bloqueada entrou: ' || r::text;
    assert not exists (select 1 from public.licenca_usuario_sessoes where usuario_id = v_func),
        'sessao de conta bloqueada ficou';
    r := public.dumtech_acesso_salvar_usuario(v_chave, v_maquina, v_pc, v_sessao, v_func,
        '{"nome":"Maria","login":"maria","papel":"funcionario","ativo":true}', '');

    -- ------------------------------------------------------- celular
    r := public.dumtech_celular_iniciar(v_chave, v_maquina, v_pc);
    assert r->>'erro' = 'so_adm', 'celular sem sessao com conta: ' || r::text;
    r := public.dumtech_celular_aparelhos(v_chave, v_maquina, v_pc);
    assert r->>'erro' = 'so_adm', 'aparelhos sem sessao: ' || r::text;
    r := public.dumtech_acesso_resultado(v_chave, v_maquina, v_pc, v_func, true, '10.0.0.1');
    r := public.dumtech_celular_iniciar(v_chave, v_maquina, v_pc, r->>'sessao');
    assert r->>'erro' = 'so_adm', 'funcionario pediu QR: ' || r::text;
    r := public.dumtech_celular_iniciar(v_chave, v_maquina, v_pc, v_sessao);
    assert (r->>'ok')::boolean, 'adm pediu QR: ' || r::text;
    -- quem publica e a loja, nao a pessoa
    r := public.dumtech_celular_publicar(v_chave, v_maquina, v_pc, '{"secoes": []}'::jsonb);
    assert r ? 'pareados', 'publicar: ' || r::text;

    -- ------------------------------------------------------- computadores
    update public.licencas set max_computadores = 3 where id = v_licenca;
    perform public.dumtech_ativar_licenca(v_chave, v_segunda, 'escritorio');
    r := public.dumtech_acesso_computadores(v_chave, v_maquina, v_pc, v_sessao);
    assert (r->>'max_computadores')::int = 3 and jsonb_array_length(r->'computadores') = 2, 'computadores: ' || r::text;
    assert exists (select 1 from jsonb_array_elements(r->'computadores') c
                    where c->>'maquina' = v_maquina and (c->>'este')::boolean), 'nao marcou este';
    r := public.dumtech_acesso_renomear_computador(v_chave, v_maquina, v_pc, v_sessao, v_segunda, 'Balcão');
    assert (r->>'ok')::boolean, 'renomear: ' || r::text;
    assert (select apelido = 'Balcão' from public.ativacoes where licenca_id = v_licenca and maquina = v_segunda);
    r := public.dumtech_acesso_liberar_computador(v_chave, v_maquina, v_pc, v_sessao, v_segunda);
    assert (r->>'ok')::boolean and not (r->>'este')::boolean, 'liberar: ' || r::text;
    -- o computador solto precisa notar em 2 minutos: marca vazia o Hub ignora
    assert length(public.dumtech_licenca_marca(v_chave, v_segunda)) = 32, 'vaga solta devolveu marca vazia';
    assert public.dumtech_licenca_marca(v_chave, v_segunda) = public.dumtech_licenca_marca('CHAVE-INVENTADA', v_segunda),
        'a marca entrega se a chave existe';
    assert public.dumtech_licenca_marca('', v_segunda) = '', 'sem chave nao ha o que conferir';
    r := public.dumtech_acesso_liberar_computador(v_chave, v_maquina, v_pc, v_sessao, 'NAO-EXISTE');
    assert r->>'erro' = 'computador_nao_encontrado', 'liberar inexistente: ' || r::text;

    -- ------------------------------------------------- o limite da chave
    update public.licencas set max_computadores = 1 where id = v_licenca;
    r := public.dumtech_ativar_licenca(v_chave, 'TERCEIRO-PC', 'novo');
    assert r->>'erro' = 'limite_maquinas', 'passou do limite: ' || r::text;
    assert r->>'mensagem' like '%1 de 1%', 'mensagem do limite: ' || r::text;
    update public.licencas set max_computadores = 3 where id = v_licenca;
end;
$$;

-- ------------------------------------------------- anon nao alcanca nada aqui
do $$
begin
    assert not has_table_privilege('anon', 'public.licenca_usuarios', 'select'), 'anon le contas';
    assert not has_table_privilege('authenticated', 'public.licenca_usuarios', 'select'), 'authenticated le contas';
    assert not has_table_privilege('anon', 'public.licenca_usuario_sessoes', 'select');
    assert not has_table_privilege('anon', 'public.licenca_usuario_codigos', 'select');
    assert not has_table_privilege('anon', 'public.licenca_usuario_eventos', 'select');
    assert not has_function_privilege('anon', 'public.dumtech_acesso_buscar(text,text,text,text,text)', 'execute'), 'anon le hash';
    assert not has_function_privilege('anon', 'public.dumtech_acesso_resultado(text,text,text,uuid,boolean,text)', 'execute'), 'anon abre sessao';
    assert not has_function_privilege('anon', 'public.dumtech_acesso_pedir_codigo(text,text,text,text,text)', 'execute'), 'anon pede codigo';
    assert not has_function_privilege('anon', 'public.dumtech_painel_usuarios(uuid)', 'execute'), 'anon ve contas';
    assert not has_function_privilege('anon', 'public.dumtech_ajustar_computadores(uuid,integer,text[])', 'execute');
    assert has_function_privilege('anon', 'public.dumtech_celular_iniciar(text,text,text,text)', 'execute'), 'Hub antigo perdeu o celular';
end;
$$;

-- ------------------------------------------------- o painel do Eric
do $$
declare
    v_admin   uuid;
    v_cliente uuid;
    v_chave   text;
    v_licenca uuid;
    v_comum   constant uuid := gen_random_uuid();
    v_hash    constant text := 'pbkdf2$600000$c2Fs$ZGVyaXZhZG8';
    v_conta   uuid;
    r         jsonb;
    v_negou   boolean;
begin
    insert into public.clientes (nome, email) values ('ZZ Painel', 'zz.painel@teste.local') returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);
    select id into v_licenca from public.licencas where chave = v_chave;
    update public.licencas set max_computadores = 3 where id = v_licenca;
    perform public.dumtech_ativar_licenca(v_chave, 'PC-UM', 'um');
    perform public.dumtech_ativar_licenca(v_chave, 'PC-DOIS', 'dois');
    perform public.dumtech_ativar_licenca(v_chave, 'PC-TRES', 'tres');

    -- quem nao e administrador nao passa
    perform set_config('request.jwt.claim.sub', v_comum::text, true);
    perform set_config('request.jwt.claims',
        json_build_object('sub', v_comum, 'role', 'authenticated', 'aal', 'aal2')::text, true);
    v_negou := false;
    begin
        perform public.dumtech_painel_usuarios(v_licenca);
    exception when insufficient_privilege then
        v_negou := true;
    end;
    assert v_negou, 'usuario comum viu as contas';
    v_negou := false;
    begin
        perform public.dumtech_ajustar_computadores(v_licenca, 1, array['PC-UM']);
    exception when insufficient_privilege then
        v_negou := true;
    end;
    assert v_negou, 'usuario comum mexeu no limite';

    select user_id into v_admin from public.administradores limit 1;
    if v_admin is null then
        v_admin := gen_random_uuid();
        insert into public.administradores (user_id, nome) values (v_admin, 'ZZ Dona DumTech');
    end if;
    perform set_config('request.jwt.claim.sub', v_admin::text, true);
    perform set_config('request.jwt.claims',
        json_build_object('sub', v_admin, 'role', 'authenticated', 'aal', 'aal2')::text, true);

    -- criar conta pelo painel
    r := public.dumtech_painel_salvar_usuario(v_licenca, null,
        '{"nome":"Dono","login":"dono","email":"dono@teste.local","papel":"adm"}', v_hash);
    assert (r->>'ok')::boolean, 'painel criou: ' || r::text;
    v_conta := (r->'usuario'->>'id')::uuid;
    r := public.dumtech_painel_usuarios(v_licenca);
    assert jsonb_array_length(r->'usuarios') = 1 and not (r::text like '%senha_hash%'), 'painel usuarios: ' || r::text;
    r := public.dumtech_painel_senha_provisoria(v_conta, 'pbkdf2$600000$c2Fs$b3V0cm8');
    assert (r->>'ok')::boolean, 'provisoria: ' || r::text;
    assert (select trocar_senha and senha_versao = 2 from public.licenca_usuarios where id = v_conta);
    assert exists (select 1 from public.licenca_usuario_eventos where usuario_id = v_conta and ator = 'DumTech'),
        'painel sem rastro';
    r := public.dumtech_painel_apagar_usuario(v_conta);
    assert r->>'erro' = 'ultimo_adm', 'painel apagou o ultimo ADM: ' || r::text;

    -- exigir conta
    r := public.dumtech_painel_exigir_conta(array[v_licenca], true);
    assert (r->>'ok')::boolean and (select exigir_conta from public.licencas where id = v_licenca), 'exigir: ' || r::text;

    -- reduzir limite
    r := public.dumtech_ajustar_computadores(v_licenca, 1, array['PC-UM']);
    assert r->>'erro' = 'soltar_mais' and (r->>'faltam')::int = 1, 'soltou de menos: ' || r::text;
    assert (select count(*) = 3 from public.ativacoes where licenca_id = v_licenca), 'recusa apagou vaga';
    assert (select max_computadores = 3 from public.licencas where id = v_licenca), 'recusa mudou limite';
    r := public.dumtech_ajustar_computadores(v_licenca, 1, array['PC-UM', 'PC-DOIS']);
    assert (r->>'ok')::boolean, 'reduzir: ' || r::text;
    assert (select count(*) = 1 from public.ativacoes where licenca_id = v_licenca and maquina = 'PC-TRES'), 'vagas erradas';
    assert (select max_computadores = 1 from public.licencas where id = v_licenca);
    r := public.dumtech_ajustar_computadores(v_licenca, 10);
    assert (r->>'ok')::boolean and (select max_computadores = 10 from public.licencas where id = v_licenca), 'aumentar: ' || r::text;
    r := public.dumtech_ajustar_computadores(v_licenca, 0);
    assert r->>'erro' = 'maximo_invalido', 'zero computadores: ' || r::text;

    -- a visao de todas as lojas
    r := public.dumtech_painel_acessos();
    assert exists (select 1 from jsonb_array_elements(r) e
                    where (e->>'licenca_id')::uuid = v_licenca and (e->>'contas')::int = 1
                      and (e->>'exigir_conta')::boolean and (e->>'email_difere')::boolean), 'visao geral: ' || r::text;

    perform set_config('request.jwt.claim.sub', '', true);
    perform set_config('request.jwt.claims', '', true);
end;
$$;

rollback;
