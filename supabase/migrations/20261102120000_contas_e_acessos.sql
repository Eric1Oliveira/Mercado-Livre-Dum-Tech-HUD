-- =============================================================================
-- Contas e acessos: a licenca passa a ter pessoas.
--
-- ANTES
--   A licenca era do computador: quem abria o Hub via tudo.
--
-- AGORA
--   Cada chave tem contas ADM e funcionario. O funcionario ve so os modulos e
--   avisos marcados, e o ADM gerencia contas e computadores pelo Hub. O painel
--   ve e administra tudo, loja por loja.
--
-- A SENHA NUNCA CHEGA AQUI
--   Quem deriva e confere e a Edge Function `acesso` (PBKDF2, WebCrypto). O banco
--   recebe e guarda a string derivada: a senha em claro nao passa por parametro
--   SQL nem por log do Postgres.
--
-- QUEM CHAMA
--   Todas as dumtech_acesso_* sao de service_role. As dumtech_painel_* conferem
--   dumtech_e_admin() por dentro, porque rodam como definer: e isso que deixa o
--   painel ver as contas sem nunca alcancar a coluna senha_hash.
--
-- ADITIVA
--   Loja sem conta nao sente nada: a impressao da licenca continua a mesma e o
--   celular segue sem sessao. Hub antigo ignora os campos novos.
--
-- Depende de: 20260916120000_pagamentos_protegidos.sql (padrao de codigo e
--             sessao) e 20261019120000_painel_uso_testes_celular.sql (marca).
-- =============================================================================

alter table public.licencas add column if not exists exigir_conta boolean not null default false;
comment on column public.licencas.exigir_conta is
    'O painel exige conta: o Hub tira o "Agora nao" do convite (com internet).';

-- ================================================================ TABELAS ====
create table if not exists public.licenca_usuarios (
    id               uuid primary key default gen_random_uuid(),
    licenca_id       uuid not null references public.licencas(id) on delete cascade,
    login            text not null check (login ~ '^[a-z0-9._@+-]{3,60}$'),
    nome             text not null,
    email            text not null default '',
    email_confirmado boolean not null default false,
    papel            text not null check (papel in ('adm', 'funcionario')),
    modulos          text[] not null default '{}',
    avisos           text[] not null default '{}',
    senha_hash       text not null,
    -- sobe a cada troca: invalida a copia offline dos outros computadores
    senha_versao     integer not null default 1,
    trocar_senha     boolean not null default false,
    ativo            boolean not null default true,
    erros            integer not null default 0,
    -- quantas vezes ja travou: a janela dobra a cada uma, ate 60 minutos
    travas           integer not null default 0,
    bloqueado_ate    timestamptz,
    ultimo_acesso    timestamptz,
    ultimo_computador text not null default '',
    criado_em        timestamptz not null default now(),
    -- so sobe com o que o Hub precisa saber: entrar nao muda a impressao da licenca
    atualizado_em    timestamptz not null default now(),
    unique (licenca_id, login)
);
create index if not exists idx_licenca_usuarios_licenca on public.licenca_usuarios (licenca_id);

create table if not exists public.licenca_usuario_codigos (
    id          uuid primary key default gen_random_uuid(),
    usuario_id  uuid not null references public.licenca_usuarios(id) on delete cascade,
    finalidade  text not null check (finalidade in ('confirmar_email', 'recuperar_senha')),
    codigo_hash text not null,
    criado_em   timestamptz not null default now(),
    expira_em   timestamptz not null,
    tentativas  integer not null default 0,
    usado_em    timestamptz
);
create index if not exists idx_licenca_usuario_codigos_aberto
    on public.licenca_usuario_codigos (usuario_id, finalidade, criado_em desc) where usado_em is null;

create table if not exists public.licenca_usuario_sessoes (
    sessao_hash text primary key,
    usuario_id  uuid not null references public.licenca_usuarios(id) on delete cascade,
    licenca_id  uuid not null references public.licencas(id) on delete cascade,
    maquina     text not null,
    computador  text not null,
    criado_em   timestamptz not null default now(),
    expira_em   timestamptz not null
);
create index if not exists idx_licenca_usuario_sessoes_usuario on public.licenca_usuario_sessoes (usuario_id);

-- quem fez o que nas contas (nunca apagado pela API)
create table if not exists public.licenca_usuario_eventos (
    id         bigint generated always as identity primary key,
    licenca_id uuid not null references public.licencas(id) on delete cascade,
    usuario_id uuid,
    ator       text not null default '',
    acao       text not null,
    detalhe    jsonb not null default '{}'::jsonb,
    criado_em  timestamptz not null default now()
);
create index if not exists idx_licenca_usuario_eventos on public.licenca_usuario_eventos (licenca_id, criado_em desc);

alter table public.licenca_usuarios        enable row level security;
alter table public.licenca_usuario_codigos enable row level security;
alter table public.licenca_usuario_sessoes enable row level security;
alter table public.licenca_usuario_eventos enable row level security;

revoke all on table public.licenca_usuarios        from anon, authenticated;
revoke all on table public.licenca_usuario_codigos from anon, authenticated;
revoke all on table public.licenca_usuario_sessoes from anon, authenticated;
revoke all on table public.licenca_usuario_eventos from anon, authenticated;

-- ============================================================== PECINHAS ====
-- a licenca como sal: o mesmo segredo em duas licencas da hashes diferentes
create or replace function public.dumtech_acesso_hash(p_licenca uuid, p_segredo text)
returns text
language sql
immutable
set search_path = ''
as $$
    select encode(sha256(convert_to(p_licenca::text || ':acesso:' || p_segredo, 'UTF8')), 'hex');
$$;

create or replace function public.dumtech_acesso_login(p_login text)
returns text
language sql
immutable
set search_path = ''
as $$
    select left(lower(btrim(coalesce(p_login, ''))), 60);
$$;

-- lista de codigos vinda do Hub: so o que parece codigo, sem repetir
create or replace function public.dumtech_acesso_lista(p_lista jsonb)
returns text[]
language sql
immutable
set search_path = ''
as $$
    select coalesce(array_agg(distinct v) filter (where v ~ '^[a-z][a-z0-9_]{1,40}$'), '{}')
      from jsonb_array_elements_text(
          case when jsonb_typeof(p_lista) = 'array' then p_lista else '[]'::jsonb end) v;
$$;

-- a chave esta ativada NESTA maquina, neste computador. Nao exige licenca ativa:
-- quem esta com a licenca vencida ainda entra para consultar o que e dele.
create or replace function public.dumtech_acesso_licenca(p_chave text, p_maquina text, p_computador text)
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
    select l.id
      from public.licencas l
      join public.ativacoes a on a.licenca_id = l.id
     where l.chave = public.dumtech_normalizar(p_chave, 32)
       and a.maquina = public.dumtech_normalizar(p_maquina, 64)
       and coalesce(p_computador, '') ~ '^[0-9a-f]{32}$'
       and (coalesce(a.computador, '') = '' or a.computador = p_computador)
     limit 1;
$$;

create or replace function public.dumtech_acesso_recusa()
returns jsonb
language sql
immutable
set search_path = ''
as $$
    select jsonb_build_object('ok', false, 'erro', 'nao_autorizado',
        'mensagem', 'Este computador não está com a licença ativada. Confira a licença e tente de novo.');
$$;

-- o que o Hub sabe de cada pessoa: sem hash e sem o e-mail inteiro
create or replace function public.dumtech_acesso_usuario_json(p_usuario public.licenca_usuarios)
returns jsonb
language sql
stable
set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_usuario.id,
        'login', p_usuario.login,
        'nome', p_usuario.nome,
        'papel', p_usuario.papel,
        'modulos', to_jsonb(p_usuario.modulos),
        'avisos', to_jsonb(p_usuario.avisos),
        'senha_versao', p_usuario.senha_versao,
        'trocar_senha', p_usuario.trocar_senha,
        'ativo', p_usuario.ativo,
        'tem_email', p_usuario.email <> '',
        'email_confirmado', p_usuario.email_confirmado);
$$;

-- o que o ADM e o painel veem a mais
create or replace function public.dumtech_acesso_usuario_detalhe(p_usuario public.licenca_usuarios)
returns jsonb
language sql
stable
set search_path = ''
as $$
    select public.dumtech_acesso_usuario_json(p_usuario) || jsonb_build_object(
        'email', p_usuario.email,
        'ultimo_acesso', p_usuario.ultimo_acesso,
        'ultimo_computador', p_usuario.ultimo_computador,
        'bloqueado_ate', p_usuario.bloqueado_ate,
        'criado_em', p_usuario.criado_em);
$$;

-- o documento que a Edge Function assina para o Hub funcionar offline
create or replace function public.dumtech_acesso_resumo(p_licenca uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    select jsonb_build_object(
        'exigir_conta', coalesce((select l.exigir_conta from public.licencas l where l.id = p_licenca), false),
        'usuarios', coalesce((
            select jsonb_agg(public.dumtech_acesso_usuario_json(u) order by u.nome, u.login)
              from public.licenca_usuarios u where u.licenca_id = p_licenca), '[]'::jsonb));
$$;

create or replace function public.dumtech_acesso_evento(
    p_licenca uuid, p_usuario uuid, p_ator text, p_acao text, p_detalhe jsonb default '{}'::jsonb
)
returns void
language sql
security definer
set search_path = ''
as $$
    insert into public.licenca_usuario_eventos (licenca_id, usuario_id, ator, acao, detalhe)
    values (p_licenca, p_usuario, left(coalesce(p_ator, ''), 80), p_acao, coalesce(p_detalhe, '{}'::jsonb));
$$;

-- todo pedido com sessao passa por aqui: mesma licenca, mesmo computador, no prazo
create or replace function public.dumtech_acesso_portao(
    p_chave text, p_maquina text, p_computador text, p_sessao text, p_so_adm boolean default true
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid := public.dumtech_acesso_licenca(p_chave, p_maquina, p_computador);
    v_usuario public.licenca_usuarios;
begin
    if v_licenca is null then
        return public.dumtech_acesso_recusa();
    end if;
    if not public.dumtech_dentro_do_limite('acesso_acao', v_licenca::text, 300, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Muitos pedidos seguidos. Espere alguns minutos e tente de novo.');
    end if;

    select u.* into v_usuario
      from public.licenca_usuario_sessoes s
      join public.licenca_usuarios u on u.id = s.usuario_id
     where s.sessao_hash = public.dumtech_acesso_hash(v_licenca, coalesce(p_sessao, ''))
       and s.licenca_id = v_licenca
       and s.maquina = public.dumtech_normalizar(p_maquina, 64)
       and s.computador = p_computador
       and s.expira_em > now()
       and u.ativo;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'sessao_vencida',
            'mensagem', 'Sua sessão venceu. Digite a senha de novo para continuar.');
    end if;
    if p_so_adm and v_usuario.papel <> 'adm' then
        return jsonb_build_object('ok', false, 'erro', 'so_adm',
            'mensagem', 'Só um administrador pode fazer isso.');
    end if;
    -- senha provisoria so serve para criar a senha: quem a escolheu tambem a conhece
    if p_so_adm and v_usuario.trocar_senha then
        return jsonb_build_object('ok', false, 'erro', 'trocar_senha',
            'mensagem', 'Crie a sua senha antes de continuar.');
    end if;
    return jsonb_build_object('ok', true, 'licenca', v_licenca, 'usuario', v_usuario.id,
                              'login', v_usuario.login);
end;
$$;

-- Derivar senha custa caro de proposito, e esta funcao nao exige JWT: sem esta
-- conferencia, qualquer um gastava a CPU dela mandando chave inventada.
create or replace function public.dumtech_acesso_antes_de_derivar(
    p_chave text, p_maquina text, p_computador text, p_ip text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
    if not public.dumtech_dentro_do_limite('acesso_derivar_ip', left(btrim(coalesce(p_ip, '')), 64), 40, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos e tente de novo.');
    end if;
    if public.dumtech_acesso_licenca(p_chave, p_maquina, p_computador) is null then
        return public.dumtech_acesso_recusa();
    end if;
    return jsonb_build_object('ok', true);
end;
$$;

-- NULL = pode gravar
create or replace function public.dumtech_acesso_validar(p_nome text, p_login text, p_email text, p_papel text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
    if char_length(btrim(coalesce(p_nome, ''))) < 2 then
        return jsonb_build_object('ok', false, 'erro', 'nome_invalido', 'mensagem', 'Digite o nome da pessoa.');
    end if;
    if coalesce(p_login, '') !~ '^[a-z0-9._@+-]{3,60}$' then
        return jsonb_build_object('ok', false, 'erro', 'login_invalido',
            'mensagem', 'O login precisa ter de 3 a 60 caracteres, sem espaços e sem acentos.');
    end if;
    if coalesce(p_papel, '') not in ('adm', 'funcionario') then
        return jsonb_build_object('ok', false, 'erro', 'papel_invalido', 'mensagem', 'Escolha o tipo da conta.');
    end if;
    -- sem e-mail o "esqueci minha senha" do ADM nao teria para onde ir
    if (p_papel = 'adm' and not public.dumtech_email_valido(p_email))
       or (coalesce(p_email, '') <> '' and not public.dumtech_email_valido(p_email)) then
        return jsonb_build_object('ok', false, 'erro', 'email_invalido',
            'mensagem', case when p_papel = 'adm'
                             then 'Administrador precisa de um e-mail válido: é por ele que a senha é recuperada.'
                             else 'Confira o e-mail digitado.' end);
    end if;
    return null;
end;
$$;

create or replace function public.dumtech_acesso_hash_valido(p_hash text)
returns boolean
language sql
immutable
set search_path = ''
as $$
    select coalesce(p_hash, '') ~ '^pbkdf2\$[0-9]{5,8}\$[A-Za-z0-9_-]+\$[A-Za-z0-9_-]+$';
$$;

-- abre a sessao de gestao: o segredo volta uma vez e o banco guarda so o hash
create or replace function public.dumtech_acesso_abrir_sessao(p_usuario uuid, p_maquina text, p_computador text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_usuario public.licenca_usuarios;
    v_sessao  text := public.dumtech_novo_token() || public.dumtech_novo_token();
    v_expira  timestamptz := now() + interval '30 minutes';
    v_maquina text := public.dumtech_normalizar(p_maquina, 64);
    v_apelido text;
begin
    select * into v_usuario from public.licenca_usuarios where id = p_usuario;
    delete from public.licenca_usuario_sessoes where licenca_id = v_usuario.licenca_id and expira_em < now();
    insert into public.licenca_usuario_sessoes (sessao_hash, usuario_id, licenca_id, maquina, computador, expira_em)
    values (public.dumtech_acesso_hash(v_usuario.licenca_id, v_sessao), v_usuario.id, v_usuario.licenca_id,
            v_maquina, p_computador, v_expira);

    select coalesce(nullif(a.apelido, ''), a.maquina) into v_apelido
      from public.ativacoes a where a.licenca_id = v_usuario.licenca_id and a.maquina = v_maquina;

    update public.licenca_usuarios
       set ultimo_acesso = now(), ultimo_computador = coalesce(v_apelido, ''),
           erros = 0, travas = 0, bloqueado_ate = null
     where id = v_usuario.id
    returning * into v_usuario;

    return jsonb_build_object(
        'ok', true, 'sessao', v_sessao, 'expira_em', v_expira,
        'usuario', public.dumtech_acesso_usuario_json(v_usuario),
        'resumo', public.dumtech_acesso_resumo(v_usuario.licenca_id));
end;
$$;

-- =============================================================== O CODIGO ====
create or replace function public.dumtech_acesso_novo_codigo(p_licenca uuid, p_usuario uuid, p_finalidade text)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_codigo text := public.dumtech_pag_codigo_email();
begin
    -- so o ultimo codigo vale
    update public.licenca_usuario_codigos set usado_em = now()
     where usuario_id = p_usuario and finalidade = p_finalidade and usado_em is null;
    delete from public.licenca_usuario_codigos
     where usuario_id = p_usuario and criado_em < now() - interval '1 day';
    insert into public.licenca_usuario_codigos (usuario_id, finalidade, codigo_hash, expira_em)
    values (p_usuario, p_finalidade,
            public.dumtech_acesso_hash(p_licenca, p_usuario::text || ':' || v_codigo),
            now() + interval '10 minutes');
    return v_codigo;
end;
$$;

-- '' = certo; senao, a recusa pronta
create or replace function public.dumtech_acesso_usar_codigo(
    p_licenca uuid, p_usuario uuid, p_finalidade text, p_codigo text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_texto  text := btrim(coalesce(p_codigo, ''));
    v_aberto public.licenca_usuario_codigos;
    v_erro   constant jsonb := jsonb_build_object('ok', false, 'erro', 'codigo_invalido',
                 'mensagem', 'Código incorreto ou vencido. Confira e tente de novo, ou peça outro.');
begin
    if v_texto !~ '^[0-9]{6}$' then
        return v_erro;
    end if;
    select * into v_aberto from public.licenca_usuario_codigos
     where usuario_id = p_usuario and finalidade = p_finalidade
       and usado_em is null and expira_em > now()
     order by criado_em desc limit 1
       for update;
    if not found then
        return v_erro;
    end if;
    update public.licenca_usuario_codigos set tentativas = tentativas + 1 where id = v_aberto.id;
    if v_aberto.codigo_hash <> public.dumtech_acesso_hash(p_licenca, p_usuario::text || ':' || v_texto) then
        if v_aberto.tentativas + 1 >= 5 then
            update public.licenca_usuario_codigos set usado_em = now() where id = v_aberto.id;
            return jsonb_build_object('ok', false, 'erro', 'codigo_bloqueado',
                'mensagem', 'Código errado 5 vezes: ele deixou de valer. Peça um código novo.');
        end if;
        return v_erro;
    end if;
    update public.licenca_usuario_codigos set usado_em = now() where id = v_aberto.id;
    return jsonb_build_object('ok', true);
end;
$$;

-- ====================================================== O PRIMEIRO ADM =======
create or replace function public.dumtech_acesso_criar_primeiro(
    p_chave text, p_maquina text, p_computador text,
    p_nome text, p_login text, p_email text, p_senha_hash text, p_ip text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid;
    v_login   text := public.dumtech_acesso_login(p_login);
    v_email   text := lower(btrim(coalesce(p_email, '')));
    v_nome    text := left(btrim(coalesce(p_nome, '')), 80);
    v_erro    jsonb;
    v_id      uuid;
begin
    if not public.dumtech_dentro_do_limite('acesso_criar_ip', left(btrim(coalesce(p_ip, '')), 64), 20, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos e tente de novo.');
    end if;
    v_licenca := public.dumtech_acesso_licenca(p_chave, p_maquina, p_computador);
    if v_licenca is null then
        return public.dumtech_acesso_recusa();
    end if;
    -- dois computadores no mesmo instante: um so vira o primeiro
    perform 1 from public.licencas where id = v_licenca for update;
    if exists (select 1 from public.licenca_usuarios where licenca_id = v_licenca) then
        return jsonb_build_object('ok', false, 'erro', 'ja_tem_contas',
            'mensagem', 'Esta licença já tem conta de administrador. Entre com o seu login.');
    end if;
    v_erro := public.dumtech_acesso_validar(v_nome, v_login, v_email, 'adm');
    if v_erro is not null then
        return v_erro;
    end if;
    if not public.dumtech_acesso_hash_valido(p_senha_hash) then
        return jsonb_build_object('ok', false, 'erro', 'senha_invalida', 'mensagem', 'Senha inválida.');
    end if;

    insert into public.licenca_usuarios (licenca_id, login, nome, email, papel, senha_hash)
    values (v_licenca, v_login, v_nome, v_email, 'adm', p_senha_hash)
    returning id into v_id;
    perform public.dumtech_acesso_evento(v_licenca, v_id, v_login, 'criou_primeiro_adm');
    return public.dumtech_acesso_abrir_sessao(v_id, p_maquina, p_computador);
end;
$$;

-- ================================================================= ENTRAR ====
-- Em dois tempos, porque quem compara a senha e a Edge Function.
create or replace function public.dumtech_acesso_buscar(
    p_chave text, p_maquina text, p_computador text, p_login text, p_ip text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid;
    v_usuario public.licenca_usuarios;
    v_erro    constant jsonb := jsonb_build_object('ok', false, 'erro', 'credenciais',
                  'mensagem', 'Login ou senha incorretos.');
begin
    if not public.dumtech_dentro_do_limite('acesso_entrar_ip', left(btrim(coalesce(p_ip, '')), 64), 60, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos e tente de novo.');
    end if;
    v_licenca := public.dumtech_acesso_licenca(p_chave, p_maquina, p_computador);
    if v_licenca is null then
        return public.dumtech_acesso_recusa();
    end if;
    select * into v_usuario from public.licenca_usuarios
     where licenca_id = v_licenca and login = public.dumtech_acesso_login(p_login);
    if not found then
        return v_erro;
    end if;
    if v_usuario.bloqueado_ate is not null and v_usuario.bloqueado_ate > now() then
        return jsonb_build_object('ok', false, 'erro', 'conta_travada',
            'mensagem', format('Muitas tentativas erradas. Tente de novo em %s minuto(s), ou use Esqueci minha senha.',
                               greatest(ceil(extract(epoch from v_usuario.bloqueado_ate - now()) / 60)::int, 1)));
    end if;
    return jsonb_build_object('ok', true, 'usuario_id', v_usuario.id, 'senha_hash', v_usuario.senha_hash);
end;
$$;

create or replace function public.dumtech_acesso_resultado(
    p_chave text, p_maquina text, p_computador text, p_usuario uuid, p_certo boolean, p_ip text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid := public.dumtech_acesso_licenca(p_chave, p_maquina, p_computador);
    v_usuario public.licenca_usuarios;
    v_minutos integer;
begin
    if v_licenca is null then
        return public.dumtech_acesso_recusa();
    end if;
    select * into v_usuario from public.licenca_usuarios
     where id = p_usuario and licenca_id = v_licenca for update;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'credenciais', 'mensagem', 'Login ou senha incorretos.');
    end if;

    if p_certo then
        if not v_usuario.ativo then
            return jsonb_build_object('ok', false, 'erro', 'conta_bloqueada',
                'mensagem', 'Esta conta está bloqueada. Fale com o administrador.');
        end if;
        return public.dumtech_acesso_abrir_sessao(v_usuario.id, p_maquina, p_computador);
    end if;

    if v_usuario.erros + 1 >= 5 then
        v_minutos := least(15 * power(2, least(v_usuario.travas, 6))::int, 60);
        update public.licenca_usuarios
           set erros = 0, travas = travas + 1, bloqueado_ate = now() + make_interval(mins => v_minutos)
         where id = v_usuario.id;
        return jsonb_build_object('ok', false, 'erro', 'conta_travada',
            'mensagem', format('Muitas tentativas erradas. Tente de novo em %s minutos, ou use Esqueci minha senha.', v_minutos));
    end if;
    update public.licenca_usuarios set erros = erros + 1 where id = v_usuario.id;
    return jsonb_build_object('ok', false, 'erro', 'credenciais', 'mensagem', 'Login ou senha incorretos.');
end;
$$;

-- ======================================================== ESQUECI A SENHA ====
create or replace function public.dumtech_acesso_pedir_codigo(
    p_chave text, p_maquina text, p_computador text, p_login text, p_ip text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid;
    v_usuario public.licenca_usuarios;
begin
    if not public.dumtech_dentro_do_limite('acesso_codigo_ip', left(btrim(coalesce(p_ip, '')), 64), 20, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Muitos pedidos de código. Espere alguns minutos e tente de novo.');
    end if;
    v_licenca := public.dumtech_acesso_licenca(p_chave, p_maquina, p_computador);
    if v_licenca is null then
        return public.dumtech_acesso_recusa();
    end if;
    if not public.dumtech_dentro_do_limite('acesso_codigo_licenca', v_licenca::text, 10, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Já enviamos vários códigos na última hora. Use o último que chegou ou espere um pouco.');
    end if;

    select * into v_usuario from public.licenca_usuarios
     where licenca_id = v_licenca and login = public.dumtech_acesso_login(p_login) and ativo;
    if not found then
        return jsonb_build_object('ok', true);      -- login errado responde igual
    end if;
    if not public.dumtech_email_valido(v_usuario.email) then
        return jsonb_build_object('ok', true, 'sem_email', true);
    end if;
    return jsonb_build_object(
        'ok', true, 'email', v_usuario.email, 'nome', v_usuario.nome, 'validade_minutos', 10,
        'codigo', public.dumtech_acesso_novo_codigo(v_licenca, v_usuario.id, 'recuperar_senha'));
end;
$$;

create or replace function public.dumtech_acesso_redefinir(
    p_chave text, p_maquina text, p_computador text,
    p_login text, p_codigo text, p_senha_hash text, p_ip text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid;
    v_usuario public.licenca_usuarios;
    v_uso     jsonb;
begin
    if not public.dumtech_dentro_do_limite('acesso_redefinir_ip', left(btrim(coalesce(p_ip, '')), 64), 30, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos e tente de novo.');
    end if;
    v_licenca := public.dumtech_acesso_licenca(p_chave, p_maquina, p_computador);
    if v_licenca is null then
        return public.dumtech_acesso_recusa();
    end if;
    if not public.dumtech_acesso_hash_valido(p_senha_hash) then
        return jsonb_build_object('ok', false, 'erro', 'senha_invalida', 'mensagem', 'Senha inválida.');
    end if;
    select * into v_usuario from public.licenca_usuarios
     where licenca_id = v_licenca and login = public.dumtech_acesso_login(p_login) and ativo;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'codigo_invalido',
            'mensagem', 'Código incorreto ou vencido. Confira e tente de novo, ou peça outro.');
    end if;

    v_uso := public.dumtech_acesso_usar_codigo(v_licenca, v_usuario.id, 'recuperar_senha', p_codigo);
    if not (v_uso->>'ok')::boolean then
        return v_uso;
    end if;

    update public.licenca_usuarios
       set senha_hash = p_senha_hash, senha_versao = senha_versao + 1, trocar_senha = false,
           email_confirmado = true, atualizado_em = now()
     where id = v_usuario.id;
    delete from public.licenca_usuario_sessoes where usuario_id = v_usuario.id;
    perform public.dumtech_acesso_evento(v_licenca, v_usuario.id, v_usuario.login, 'recuperou_senha');
    return public.dumtech_acesso_abrir_sessao(v_usuario.id, p_maquina, p_computador);
end;
$$;

-- ========================================================= A PROPRIA CONTA ===
create or replace function public.dumtech_acesso_codigo_email(
    p_chave text, p_maquina text, p_computador text, p_sessao text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_portao  jsonb := public.dumtech_acesso_portao(p_chave, p_maquina, p_computador, p_sessao, false);
    v_licenca uuid;
    v_usuario public.licenca_usuarios;
begin
    if not (v_portao->>'ok')::boolean then
        return v_portao;
    end if;
    v_licenca := (v_portao->>'licenca')::uuid;
    if not public.dumtech_dentro_do_limite('acesso_codigo_licenca', v_licenca::text, 10, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Já enviamos vários códigos na última hora. Use o último que chegou ou espere um pouco.');
    end if;
    select * into v_usuario from public.licenca_usuarios where id = (v_portao->>'usuario')::uuid;
    if not public.dumtech_email_valido(v_usuario.email) then
        return jsonb_build_object('ok', false, 'erro', 'sem_email', 'mensagem', 'Esta conta não tem e-mail.');
    end if;
    return jsonb_build_object(
        'ok', true, 'email', v_usuario.email, 'nome', v_usuario.nome, 'validade_minutos', 10,
        'codigo', public.dumtech_acesso_novo_codigo(v_licenca, v_usuario.id, 'confirmar_email'));
end;
$$;

create or replace function public.dumtech_acesso_confirmar_email(
    p_chave text, p_maquina text, p_computador text, p_sessao text, p_codigo text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_portao  jsonb := public.dumtech_acesso_portao(p_chave, p_maquina, p_computador, p_sessao, false);
    v_uso     jsonb;
    v_usuario public.licenca_usuarios;
begin
    if not (v_portao->>'ok')::boolean then
        return v_portao;
    end if;
    v_uso := public.dumtech_acesso_usar_codigo((v_portao->>'licenca')::uuid, (v_portao->>'usuario')::uuid,
                                               'confirmar_email', p_codigo);
    if not (v_uso->>'ok')::boolean then
        return v_uso;
    end if;
    update public.licenca_usuarios set email_confirmado = true, atualizado_em = now()
     where id = (v_portao->>'usuario')::uuid
    returning * into v_usuario;
    return jsonb_build_object('ok', true, 'usuario', public.dumtech_acesso_usuario_json(v_usuario),
                              'resumo', public.dumtech_acesso_resumo(v_usuario.licenca_id));
end;
$$;

create or replace function public.dumtech_acesso_buscar_sessao(
    p_chave text, p_maquina text, p_computador text, p_sessao text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_portao  jsonb := public.dumtech_acesso_portao(p_chave, p_maquina, p_computador, p_sessao, false);
    v_usuario public.licenca_usuarios;
begin
    if not (v_portao->>'ok')::boolean then
        return v_portao;
    end if;
    select * into v_usuario from public.licenca_usuarios where id = (v_portao->>'usuario')::uuid;
    -- quem errou demais nao continua testando senha pela troca
    if v_usuario.bloqueado_ate is not null and v_usuario.bloqueado_ate > now() then
        return jsonb_build_object('ok', false, 'erro', 'conta_travada',
            'mensagem', 'Muitas tentativas erradas. Espere alguns minutos e tente de novo.');
    end if;
    return jsonb_build_object('ok', true, 'usuario_id', v_usuario.id, 'login', v_usuario.login,
                              'senha_hash', v_usuario.senha_hash);
end;
$$;

create or replace function public.dumtech_acesso_gravar_senha(
    p_chave text, p_maquina text, p_computador text, p_sessao text, p_senha_hash text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_portao  jsonb := public.dumtech_acesso_portao(p_chave, p_maquina, p_computador, p_sessao, false);
    v_licenca uuid;
    v_usuario public.licenca_usuarios;
begin
    if not (v_portao->>'ok')::boolean then
        return v_portao;
    end if;
    if not public.dumtech_acesso_hash_valido(p_senha_hash) then
        return jsonb_build_object('ok', false, 'erro', 'senha_invalida', 'mensagem', 'Senha inválida.');
    end if;
    v_licenca := (v_portao->>'licenca')::uuid;
    update public.licenca_usuarios
       set senha_hash = p_senha_hash, senha_versao = senha_versao + 1, trocar_senha = false, atualizado_em = now()
     where id = (v_portao->>'usuario')::uuid
    returning * into v_usuario;
    -- quem estava entrando por outro lado com a senha antiga cai fora
    delete from public.licenca_usuario_sessoes
     where usuario_id = v_usuario.id
       and sessao_hash <> public.dumtech_acesso_hash(v_licenca, coalesce(p_sessao, ''));
    perform public.dumtech_acesso_evento(v_licenca, v_usuario.id, v_usuario.login, 'trocou_a_senha');
    return jsonb_build_object('ok', true, 'usuario', public.dumtech_acesso_usuario_json(v_usuario),
                              'resumo', public.dumtech_acesso_resumo(v_licenca));
end;
$$;

-- =================================================== REGRAS DE UMA CONTA ====
-- O ADM (pelo Hub) e o Eric (pelo painel) passam pelas mesmas regras.
create or replace function public.dumtech_acesso_outro_adm(p_licenca uuid, p_usuario uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (select 1 from public.licenca_usuarios u
                    where u.licenca_id = p_licenca and u.id <> p_usuario and u.papel = 'adm' and u.ativo);
$$;

create or replace function public.dumtech_acesso_gravar_usuario(
    p_licenca uuid, p_id uuid, p_dados jsonb, p_senha_hash text, p_ator text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_nome    text := left(btrim(coalesce(p_dados->>'nome', '')), 80);
    v_login   text := public.dumtech_acesso_login(p_dados->>'login');
    v_email   text := lower(btrim(coalesce(p_dados->>'email', '')));
    v_papel   text := coalesce(p_dados->>'papel', 'funcionario');
    v_ativo   boolean := coalesce((p_dados->>'ativo')::boolean, true);
    v_modulos text[] := public.dumtech_acesso_lista(p_dados->'modulos');
    v_avisos  text[] := public.dumtech_acesso_lista(p_dados->'avisos');
    v_erro    jsonb;
    v_antigo  public.licenca_usuarios;
    v_usuario public.licenca_usuarios;
begin
    perform 1 from public.licencas where id = p_licenca for update;  -- a regra do ultimo ADM
    v_erro := public.dumtech_acesso_validar(v_nome, v_login, v_email, v_papel);
    if v_erro is not null then
        return v_erro;
    end if;
    if v_papel = 'adm' then          -- ADM ve tudo: guardar lista daria falsa impressao
        v_modulos := '{}';
        v_avisos := '{}';
    end if;
    if exists (select 1 from public.licenca_usuarios u
                where u.licenca_id = p_licenca and u.login = v_login and u.id is distinct from p_id) then
        return jsonb_build_object('ok', false, 'erro', 'login_em_uso', 'mensagem', 'Já existe uma conta com esse login.');
    end if;

    if p_id is null then
        if not public.dumtech_acesso_hash_valido(p_senha_hash) then
            return jsonb_build_object('ok', false, 'erro', 'senha_invalida', 'mensagem', 'Defina uma senha para a conta.');
        end if;
        -- senha escolhida por outra pessoa: no primeiro acesso a dona da conta cria a dela
        insert into public.licenca_usuarios (licenca_id, login, nome, email, papel, modulos, avisos,
                                             senha_hash, trocar_senha, ativo)
        values (p_licenca, v_login, v_nome, v_email, v_papel, v_modulos, v_avisos, p_senha_hash, true, v_ativo)
        returning * into v_usuario;
        perform public.dumtech_acesso_evento(p_licenca, v_usuario.id, p_ator, 'criou_conta',
            jsonb_build_object('login', v_login, 'papel', v_papel));
    else
        select * into v_antigo from public.licenca_usuarios
         where id = p_id and licenca_id = p_licenca for update;
        if not found then
            return jsonb_build_object('ok', false, 'erro', 'usuario_nao_encontrado', 'mensagem', 'Conta não encontrada.');
        end if;
        if v_antigo.papel = 'adm' and v_antigo.ativo and (v_papel <> 'adm' or not v_ativo)
           and not public.dumtech_acesso_outro_adm(p_licenca, p_id) then
            return jsonb_build_object('ok', false, 'erro', 'ultimo_adm',
                'mensagem', 'A loja precisa de pelo menos um administrador ativo.');
        end if;
        update public.licenca_usuarios
           set nome = v_nome, login = v_login, email = v_email, papel = v_papel,
               modulos = v_modulos, avisos = v_avisos, ativo = v_ativo,
               email_confirmado = email_confirmado and v_email = v_antigo.email,
               atualizado_em = now()
         where id = p_id
        returning * into v_usuario;
        if not v_ativo then
            delete from public.licenca_usuario_sessoes where usuario_id = p_id;
        end if;
        perform public.dumtech_acesso_evento(p_licenca, p_id, p_ator,
            case when v_antigo.ativo and not v_ativo then 'bloqueou_conta'
                 when v_ativo and not v_antigo.ativo then 'desbloqueou_conta'
                 else 'editou_conta' end,
            jsonb_build_object('papel', v_papel, 'modulos', to_jsonb(v_modulos), 'avisos', to_jsonb(v_avisos)));
    end if;
    return jsonb_build_object('ok', true, 'usuario', public.dumtech_acesso_usuario_detalhe(v_usuario));
end;
$$;

create or replace function public.dumtech_acesso_definir_senha(p_licenca uuid, p_id uuid, p_senha_hash text, p_ator text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_usuario public.licenca_usuarios;
begin
    if not public.dumtech_acesso_hash_valido(p_senha_hash) then
        return jsonb_build_object('ok', false, 'erro', 'senha_invalida', 'mensagem', 'Senha inválida.');
    end if;
    update public.licenca_usuarios
       set senha_hash = p_senha_hash, senha_versao = senha_versao + 1, trocar_senha = true,
           erros = 0, travas = 0, bloqueado_ate = null, atualizado_em = now()
     where id = p_id and licenca_id = p_licenca
    returning * into v_usuario;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'usuario_nao_encontrado', 'mensagem', 'Conta não encontrada.');
    end if;
    delete from public.licenca_usuario_sessoes where usuario_id = p_id;
    perform public.dumtech_acesso_evento(p_licenca, p_id, p_ator, 'redefiniu_senha');
    return jsonb_build_object('ok', true, 'usuario', public.dumtech_acesso_usuario_detalhe(v_usuario));
end;
$$;

create or replace function public.dumtech_acesso_remover_usuario(p_licenca uuid, p_id uuid, p_ator text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_antigo public.licenca_usuarios;
begin
    perform 1 from public.licencas where id = p_licenca for update;
    select * into v_antigo from public.licenca_usuarios where id = p_id and licenca_id = p_licenca;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'usuario_nao_encontrado', 'mensagem', 'Conta não encontrada.');
    end if;
    if v_antigo.papel = 'adm' and v_antigo.ativo and not public.dumtech_acesso_outro_adm(p_licenca, p_id) then
        return jsonb_build_object('ok', false, 'erro', 'ultimo_adm',
            'mensagem', 'A loja precisa de pelo menos um administrador ativo.');
    end if;
    delete from public.licenca_usuarios where id = p_id;
    perform public.dumtech_acesso_evento(p_licenca, null, p_ator, 'apagou_conta',
        jsonb_build_object('login', v_antigo.login, 'papel', v_antigo.papel));
    return jsonb_build_object('ok', true);
end;
$$;

-- ================================================= O ADM, PELO HUB ===========
create or replace function public.dumtech_acesso_usuarios(
    p_chave text, p_maquina text, p_computador text, p_sessao text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_portao jsonb := public.dumtech_acesso_portao(p_chave, p_maquina, p_computador, p_sessao, true);
begin
    if not (v_portao->>'ok')::boolean then
        return v_portao;
    end if;
    return jsonb_build_object('ok', true, 'usuarios', coalesce((
        select jsonb_agg(public.dumtech_acesso_usuario_detalhe(u) order by u.papel, u.nome, u.login)
          from public.licenca_usuarios u where u.licenca_id = (v_portao->>'licenca')::uuid), '[]'::jsonb));
end;
$$;

create or replace function public.dumtech_acesso_salvar_usuario(
    p_chave text, p_maquina text, p_computador text, p_sessao text,
    p_id uuid, p_dados jsonb, p_senha_hash text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_portao jsonb := public.dumtech_acesso_portao(p_chave, p_maquina, p_computador, p_sessao, true);
    v_saida  jsonb;
begin
    if not (v_portao->>'ok')::boolean then
        return v_portao;
    end if;
    v_saida := public.dumtech_acesso_gravar_usuario((v_portao->>'licenca')::uuid, p_id, p_dados, p_senha_hash,
                                                    v_portao->>'login');
    if (v_saida->>'ok')::boolean then
        v_saida := v_saida || jsonb_build_object('resumo', public.dumtech_acesso_resumo((v_portao->>'licenca')::uuid));
    end if;
    return v_saida;
end;
$$;

create or replace function public.dumtech_acesso_senha_usuario(
    p_chave text, p_maquina text, p_computador text, p_sessao text, p_id uuid, p_senha_hash text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_portao jsonb := public.dumtech_acesso_portao(p_chave, p_maquina, p_computador, p_sessao, true);
    v_saida  jsonb;
begin
    if not (v_portao->>'ok')::boolean then
        return v_portao;
    end if;
    v_saida := public.dumtech_acesso_definir_senha((v_portao->>'licenca')::uuid, p_id, p_senha_hash, v_portao->>'login');
    if (v_saida->>'ok')::boolean then
        v_saida := v_saida || jsonb_build_object('resumo', public.dumtech_acesso_resumo((v_portao->>'licenca')::uuid));
    end if;
    return v_saida;
end;
$$;

create or replace function public.dumtech_acesso_apagar_usuario(
    p_chave text, p_maquina text, p_computador text, p_sessao text, p_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_portao jsonb := public.dumtech_acesso_portao(p_chave, p_maquina, p_computador, p_sessao, true);
    v_saida  jsonb;
begin
    if not (v_portao->>'ok')::boolean then
        return v_portao;
    end if;
    if (v_portao->>'usuario')::uuid = p_id then
        return jsonb_build_object('ok', false, 'erro', 'apagar_a_si',
            'mensagem', 'Você não pode apagar a própria conta. Peça a outro administrador.');
    end if;
    v_saida := public.dumtech_acesso_remover_usuario((v_portao->>'licenca')::uuid, p_id, v_portao->>'login');
    if (v_saida->>'ok')::boolean then
        v_saida := v_saida || jsonb_build_object('resumo', public.dumtech_acesso_resumo((v_portao->>'licenca')::uuid));
    end if;
    return v_saida;
end;
$$;

-- ---------------------------------------------------------- computadores ----
create or replace function public.dumtech_acesso_computadores(
    p_chave text, p_maquina text, p_computador text, p_sessao text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_portao  jsonb := public.dumtech_acesso_portao(p_chave, p_maquina, p_computador, p_sessao, true);
    v_licenca uuid;
    v_maquina text := public.dumtech_normalizar(p_maquina, 64);
begin
    if not (v_portao->>'ok')::boolean then
        return v_portao;
    end if;
    v_licenca := (v_portao->>'licenca')::uuid;
    return jsonb_build_object(
        'ok', true,
        'max_computadores', (select l.max_computadores from public.licencas l where l.id = v_licenca),
        'computadores', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'maquina', a.maquina, 'apelido', a.apelido, 'ativado_em', a.ativado_em,
                       'ultima_checagem', a.ultima_checagem, 'versao', a.versao,
                       'este', a.maquina = v_maquina) order by a.ativado_em)
              from public.ativacoes a where a.licenca_id = v_licenca), '[]'::jsonb));
end;
$$;

create or replace function public.dumtech_acesso_renomear_computador(
    p_chave text, p_maquina text, p_computador text, p_sessao text, p_alvo text, p_apelido text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_portao jsonb := public.dumtech_acesso_portao(p_chave, p_maquina, p_computador, p_sessao, true);
begin
    if not (v_portao->>'ok')::boolean then
        return v_portao;
    end if;
    update public.ativacoes set apelido = left(btrim(coalesce(p_apelido, '')), 120)
     where licenca_id = (v_portao->>'licenca')::uuid and maquina = public.dumtech_normalizar(p_alvo, 64);
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'computador_nao_encontrado', 'mensagem', 'Computador não encontrado.');
    end if;
    return jsonb_build_object('ok', true);
end;
$$;

create or replace function public.dumtech_acesso_liberar_computador(
    p_chave text, p_maquina text, p_computador text, p_sessao text, p_alvo text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_portao jsonb := public.dumtech_acesso_portao(p_chave, p_maquina, p_computador, p_sessao, true);
    v_alvo   text := public.dumtech_normalizar(p_alvo, 64);
begin
    if not (v_portao->>'ok')::boolean then
        return v_portao;
    end if;
    delete from public.ativacoes
     where licenca_id = (v_portao->>'licenca')::uuid and maquina = v_alvo;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'computador_nao_encontrado', 'mensagem', 'Computador não encontrado.');
    end if;
    perform public.dumtech_acesso_evento((v_portao->>'licenca')::uuid, (v_portao->>'usuario')::uuid,
        v_portao->>'login', 'liberou_computador', jsonb_build_object('maquina', v_alvo));
    return jsonb_build_object('ok', true, 'este', v_alvo = public.dumtech_normalizar(p_maquina, 64));
end;
$$;

-- ============================================================== O PAINEL =====
create or replace function public.dumtech_painel_portao()
returns void
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
    if not public.dumtech_e_admin() then
        raise exception 'Apenas a DumTech faz isso.' using errcode = '42501';
    end if;
end;
$$;

create or replace function public.dumtech_painel_acessos()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
    perform public.dumtech_painel_portao();
    return coalesce((
        select jsonb_agg(jsonb_build_object(
            'licenca_id', l.id,
            'exigir_conta', l.exigir_conta,
            'contas', n.contas,
            'adms', n.adms,
            'funcionarios', n.contas - n.adms,
            'ultimo_acesso', n.ultimo,
            'email_confirmado', n.confirmado,
            -- quem criou a conta primeiro pode nao ser o dono: o painel mostra
            'email_difere', n.contas > 0 and coalesce(c.email, '') <> '' and not n.email_igual))
          from public.licencas l
          join public.clientes c on c.id = l.cliente_id
          cross join lateral (
              select count(*)::int as contas,
                     (count(*) filter (where u.papel = 'adm' and u.ativo))::int as adms,
                     max(u.ultimo_acesso) as ultimo,
                     coalesce(bool_or(u.papel = 'adm' and u.email_confirmado), false) as confirmado,
                     coalesce(bool_or(u.papel = 'adm' and lower(u.email) = lower(c.email)), false) as email_igual
                from public.licenca_usuarios u where u.licenca_id = l.id) n), '[]'::jsonb);
end;
$$;

create or replace function public.dumtech_painel_usuarios(p_licenca uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
    perform public.dumtech_painel_portao();
    return jsonb_build_object(
        'ok', true,
        'exigir_conta', (select l.exigir_conta from public.licencas l where l.id = p_licenca),
        'usuarios', coalesce((
            select jsonb_agg(public.dumtech_acesso_usuario_detalhe(u) order by u.papel, u.nome, u.login)
              from public.licenca_usuarios u where u.licenca_id = p_licenca), '[]'::jsonb),
        'eventos', coalesce((
            select jsonb_agg(jsonb_build_object('ator', e.ator, 'acao', e.acao, 'detalhe', e.detalhe,
                                                'criado_em', e.criado_em) order by e.criado_em desc)
              from (select * from public.licenca_usuario_eventos ev
                     where ev.licenca_id = p_licenca order by ev.criado_em desc limit 20) e), '[]'::jsonb));
end;
$$;

create or replace function public.dumtech_painel_salvar_usuario(
    p_licenca uuid, p_id uuid, p_dados jsonb, p_senha_hash text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
    perform public.dumtech_painel_portao();
    return public.dumtech_acesso_gravar_usuario(p_licenca, p_id, p_dados, p_senha_hash, 'DumTech');
end;
$$;

create or replace function public.dumtech_painel_senha_provisoria(p_id uuid, p_senha_hash text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid;
begin
    perform public.dumtech_painel_portao();
    select licenca_id into v_licenca from public.licenca_usuarios where id = p_id;
    return public.dumtech_acesso_definir_senha(v_licenca, p_id, p_senha_hash, 'DumTech');
end;
$$;

create or replace function public.dumtech_painel_apagar_usuario(p_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid;
begin
    perform public.dumtech_painel_portao();
    select licenca_id into v_licenca from public.licenca_usuarios where id = p_id;
    return public.dumtech_acesso_remover_usuario(v_licenca, p_id, 'DumTech');
end;
$$;

create or replace function public.dumtech_painel_exigir_conta(p_licencas uuid[], p_valor boolean)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_quantas integer;
begin
    perform public.dumtech_painel_portao();
    update public.licencas set exigir_conta = coalesce(p_valor, false) where id = any(p_licencas);
    get diagnostics v_quantas = row_count;
    return jsonb_build_object('ok', true, 'licencas', v_quantas);
end;
$$;

-- O limite muda junto com as vagas soltas, ou nada muda: reduzir nao pode deixar
-- a chave com mais computadores do que ela permite.
create or replace function public.dumtech_ajustar_computadores(
    p_licenca uuid, p_maximo integer, p_soltar text[] default '{}'
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_ficam integer;
begin
    perform public.dumtech_painel_portao();
    if coalesce(p_maximo, 0) < 1 or p_maximo > 50 then
        return jsonb_build_object('ok', false, 'erro', 'maximo_invalido', 'mensagem', 'Use de 1 a 50 computadores.');
    end if;
    perform 1 from public.licencas where id = p_licenca for update;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'licenca_nao_encontrada', 'mensagem', 'Licença não encontrada.');
    end if;
    select count(*) into v_ficam from public.ativacoes
     where licenca_id = p_licenca and not (maquina = any(coalesce(p_soltar, '{}')));
    if v_ficam > p_maximo then
        return jsonb_build_object('ok', false, 'erro', 'soltar_mais', 'faltam', v_ficam - p_maximo,
            'mensagem', format('Faltam %s computador(es) para caber no novo limite.', v_ficam - p_maximo));
    end if;
    delete from public.ativacoes where licenca_id = p_licenca and maquina = any(coalesce(p_soltar, '{}'));
    update public.licencas set max_computadores = p_maximo where id = p_licenca;
    return jsonb_build_object('ok', true, 'max_computadores', p_maximo, 'computadores', v_ficam);
end;
$$;

-- ============================================= A IMPRESSAO DA LICENCA =======
-- Igual a de 20261019120000, mais as contas e a exigencia. Sem conta os dois
-- ultimos itens viram NULL e concat_ws pula: a impressao fica a mesma, e publicar
-- esta migration nao faz todo Hub conferir a licenca de uma vez.
--
-- Computador sem ativacao recebe uma marca CONSTANTE, e nao mais vazia. O Hub
-- ignora marca vazia: vaga solta no painel so era percebida na conferencia de
-- hora em hora, e nao em 2 minutos. A constante e a mesma para chave inventada e
-- para chave de verdade em computador estranho, entao nao entrega se a chave existe.
create or replace function public.dumtech_licenca_marca(p_chave text, p_maquina text)
returns text
language sql
stable
security definer
set search_path = ''
as $$
    select case when public.dumtech_normalizar(p_chave, 32) = '' then '' else coalesce((
        select md5(concat_ws('|',
            l.status,
            l.max_computadores::text,
            coalesce(l.expira_em::text, ''),
            coalesce(l.tipo, ''),
            (select string_agg(coalesce(lp.produto_id::text, '') || ':' || coalesce(lp.combo_id::text, ''),
                               ',' order by lp.produto_id, lp.combo_id)
               from public.licenca_produtos lp where lp.licenca_id = l.id),
            (select max(p.atualizado_em)::text
               from public.produtos p
               join public.licenca_produtos lp on lp.produto_id = p.id
              where lp.licenca_id = l.id),
            (select max(c.atualizado_em)::text
               from public.combos c
               join public.licenca_produtos lp on lp.combo_id = c.id
              where lp.licenca_id = l.id),
            (select count(*)::text from public.ativacoes a
              where a.licenca_id = l.id
                and a.maquina = public.dumtech_normalizar(p_maquina, 64)),
            (select pc.atualizado_em::text from public.pagamento_config pc
              where pc.licenca_id = l.id),
            -- sem teste: NULL, e concat_ws pula - a impressao fica a mesma
            (select string_agg(t.produto_id::text || ':' || t.termina_em::text, ',' order by t.produto_id)
               from public.licenca_testes t
              where t.licenca_id = l.id),
            nullif(l.exigir_conta::text, 'false'),
            (select string_agg(u.id::text || ':' || u.atualizado_em::text, ',' order by u.id)
               from public.licenca_usuarios u
              where u.licenca_id = l.id)
        ))
        from public.licencas l
        where l.chave = public.dumtech_normalizar(p_chave, 32)
          -- so quem tem ativacao nesta maquina recebe impressao: chave
          -- adivinhada sem maquina valida devolve vazio, igual a inexistente
          and exists (select 1 from public.ativacoes a
                       where a.licenca_id = l.id
                         and a.maquina = public.dumtech_normalizar(p_maquina, 64))
    ), md5('dumtech:sem-ativacao')) end;
$$;
revoke execute on function public.dumtech_licenca_marca(text, text) from public, anon, authenticated;

-- ================================================== A LICENCA ASSINADA ======
-- O corpo de 20260917170000, com `contas` e `acesso` na resposta.
create or replace function public.dumtech_licenca_para_assinar(
    p_chave      text,
    p_maquina    text,
    p_ip         text default '',
    p_computador text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_resposta jsonb;
    v_licenca  uuid;
begin
    if not public.dumtech_dentro_do_limite('licenca_ip', left(btrim(coalesce(p_ip, '')), 64), 120, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas deste endereco. Espere alguns minutos e tente de novo.');
    end if;

    v_resposta := public.dumtech_verificar_interno(p_chave, p_maquina);
    if not coalesce((v_resposta->>'ok')::boolean, false) then
        return v_resposta;
    end if;

    select id into v_licenca from public.licencas
     where chave = public.dumtech_normalizar(p_chave, 32);

    -- o Hub antigo nao manda computador: continua funcionando como antes
    if coalesce(p_computador, '') <> '' then
        if not public.dumtech_prender_computador(v_licenca, p_maquina, p_computador) then
            insert into public.licenca_tentativas (chave, maquina, erro)
            values (public.dumtech_normalizar(p_chave, 32),
                    public.dumtech_normalizar(p_maquina, 64), 'outro_computador');
            return jsonb_build_object(
                'ok', false, 'erro', 'outro_computador',
                'mensagem', 'Esta licenca ja esta em uso em outro computador. '
                         || 'Use o botao Ativar licenca neste computador, ou fale com a DumTech.');
        end if;
    end if;

    return v_resposta || jsonb_build_object(
        'contas', exists (select 1 from public.licenca_usuarios u where u.licenca_id = v_licenca),
        'acesso', public.dumtech_acesso_resumo(v_licenca));
end;
$$;

-- ============================================== O LIMITE DE COMPUTADORES ====
-- O corpo de 20260924220000 com a mensagem nova: quem esbarra no limite precisa
-- saber quantos estao em uso e quem resolve.
create or replace function public.dumtech_ativar_licenca(
    p_chave   text,
    p_maquina text,
    p_apelido text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca public.licencas;
    v_usadas  integer;
    v_ja      boolean;
    v_texto   text;
begin
    if not public.dumtech_dentro_do_limite('licenca_ip', public.dumtech_ip_do_pedido(), 120, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas deste endereco. Espere alguns minutos e tente de novo.');
    end if;

    p_chave   := public.dumtech_normalizar(p_chave, 32);
    p_maquina := public.dumtech_normalizar(p_maquina, 64);
    p_apelido := left(btrim(coalesce(p_apelido, '')), 120);

    if p_chave = '' or p_maquina = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe a chave da licenca.');
    end if;

    v_licenca := public.dumtech_licenca_valida(p_chave);

    select exists (
        select 1 from public.ativacoes
         where licenca_id = v_licenca.id and maquina = p_maquina
    ) into v_ja;

    if v_ja then
        update public.ativacoes
           set ultima_checagem = now(),
               apelido = case when p_apelido <> '' then p_apelido else apelido end,
               computador = ''          -- ativar de novo solta a marca
         where licenca_id = v_licenca.id and maquina = p_maquina;
    else
        select count(*) into v_usadas from public.ativacoes where licenca_id = v_licenca.id;
        if v_usadas >= v_licenca.max_computadores then
            insert into public.licenca_tentativas (chave, maquina, erro)
            values (p_chave, p_maquina, 'limite_maquinas');
            return jsonb_build_object(
                'ok', false, 'erro', 'limite_maquinas',
                'mensagem', format(
                    'Esta chave já está em uso em %s de %s computadores, o máximo dela. '
                    || 'Um administrador da loja pode liberar um computador em Usuários e acessos, '
                    || 'ou fale com a DumTech.',
                    v_usadas, v_licenca.max_computadores));
        end if;
        insert into public.ativacoes (licenca_id, maquina, apelido)
        values (v_licenca.id, p_maquina, p_apelido);
    end if;

    return public.dumtech_resposta_licenca(v_licenca.id);

exception
    when others then
        v_texto := sqlerrm;
        if position('|' in v_texto) > 0 then
            -- A contagem feita no topo foi desfeita pelo rollback da subtransacao
            -- deste bloco EXCEPTION: conta de novo aqui, depois do rollback.
            perform public.dumtech_dentro_do_limite(
                'licenca_ip', public.dumtech_ip_do_pedido(), 120, interval '1 hour');
            insert into public.licenca_tentativas (chave, maquina, erro)
            values (p_chave, p_maquina, split_part(v_texto, '|', 1));
            return jsonb_build_object('ok', false,
                                      'erro', split_part(v_texto, '|', 1),
                                      'mensagem', split_part(v_texto, '|', 2));
        end if;
        raise;
end;
$$;

-- ============================================================= O CELULAR ====
-- Funcionario nao tem a visao do celular. Licenca sem conta segue igual, entao o
-- Hub antigo nao sente nada. Publicar o resumo nao muda: ele e da loja, nao da
-- pessoa logada.
drop function if exists public.dumtech_celular_iniciar(text, text, text);
drop function if exists public.dumtech_celular_aparelhos(text, text, text);
drop function if exists public.dumtech_celular_revogar(text, text, text, uuid);

create or replace function public.dumtech_celular_pode(
    p_licenca uuid, p_maquina text, p_computador text, p_sessao text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select not exists (select 1 from public.licenca_usuarios u where u.licenca_id = p_licenca)
        or exists (
            select 1 from public.licenca_usuario_sessoes s
              join public.licenca_usuarios u on u.id = s.usuario_id
             where s.sessao_hash = public.dumtech_acesso_hash(p_licenca, coalesce(p_sessao, ''))
               and s.licenca_id = p_licenca
               and s.maquina = public.dumtech_normalizar(p_maquina, 64)
               and s.computador = p_computador
               and s.expira_em > now()
               and u.ativo and u.papel = 'adm' and not u.trocar_senha);
$$;

create or replace function public.dumtech_celular_so_adm()
returns jsonb
language sql
immutable
set search_path = ''
as $$
    select jsonb_build_object('ok', false, 'erro', 'so_adm',
        'mensagem', 'Ver no celular é só para administradores. Confirme a sua senha e tente de novo.');
$$;

create or replace function public.dumtech_celular_iniciar(
    p_chave text, p_maquina text, p_computador text, p_sessao text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid := public.dumtech_celular_licenca(p_chave, p_maquina, p_computador);
    v_codigo  text := replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', '');
    v_expira  timestamptz := now() + interval '5 minutes';
begin
    if v_licenca is null then
        return jsonb_build_object('ok', false, 'erro', 'licenca_invalida',
                                  'mensagem', 'Ative a licenca neste computador para usar o celular.');
    end if;
    if not public.dumtech_celular_pode(v_licenca, p_maquina, p_computador, p_sessao) then
        return public.dumtech_celular_so_adm();
    end if;
    if not public.dumtech_dentro_do_limite('celular_iniciar', v_licenca::text, 30, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitos codigos seguidos. Espere alguns minutos.');
    end if;
    -- codigos antigos desta maquina deixam de valer: so o QR da tela vale
    delete from public.celular_codigos
     where licenca_id = v_licenca and (maquina = public.dumtech_normalizar(p_maquina, 64)
                                       or expira_em < now() - interval '1 day');
    insert into public.celular_codigos (codigo_hash, licenca_id, maquina, expira_em)
    values (public.dumtech_celular_hash(v_codigo), v_licenca, public.dumtech_normalizar(p_maquina, 64), v_expira);
    return jsonb_build_object('ok', true, 'codigo', v_codigo, 'expira_em', v_expira);
end;
$$;

create or replace function public.dumtech_celular_aparelhos(
    p_chave text, p_maquina text, p_computador text, p_sessao text default ''
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    v_licenca uuid := public.dumtech_celular_licenca(p_chave, p_maquina, p_computador);
begin
    if v_licenca is null then
        return jsonb_build_object('ok', false, 'erro', 'licenca_invalida');
    end if;
    if not public.dumtech_celular_pode(v_licenca, p_maquina, p_computador, p_sessao) then
        return public.dumtech_celular_so_adm();
    end if;
    return jsonb_build_object('ok', true, 'aparelhos', coalesce((
        select jsonb_agg(jsonb_build_object('id', a.id, 'nome', a.nome, 'criado_em', a.criado_em,
                                            'ultimo_acesso', a.ultimo_acesso) order by a.criado_em desc)
          from public.celular_aparelhos a
         where a.licenca_id = v_licenca and a.revogado_em is null), '[]'::jsonb));
end;
$$;

create or replace function public.dumtech_celular_revogar(
    p_chave text, p_maquina text, p_computador text, p_aparelho uuid, p_sessao text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid := public.dumtech_celular_licenca(p_chave, p_maquina, p_computador);
begin
    if v_licenca is null then
        return jsonb_build_object('ok', false, 'erro', 'licenca_invalida');
    end if;
    if not public.dumtech_celular_pode(v_licenca, p_maquina, p_computador, p_sessao) then
        return public.dumtech_celular_so_adm();
    end if;
    update public.celular_aparelhos set revogado_em = now()
     where id = p_aparelho and licenca_id = v_licenca and revogado_em is null;
    return jsonb_build_object('ok', found);
end;
$$;

-- ============================================================ PERMISSOES =====
do $$
declare
    v_funcao regprocedure;
begin
    for v_funcao in
        select p.oid::regprocedure
          from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public'
           and (p.proname like 'dumtech\_acesso\_%' or p.proname in ('dumtech_celular_pode', 'dumtech_celular_so_adm'))
    loop
        execute format('revoke execute on function %s from public, anon, authenticated', v_funcao);
        execute format('grant execute on function %s to service_role', v_funcao);
    end loop;

    for v_funcao in
        select p.oid::regprocedure
          from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public'
           and (p.proname like 'dumtech\_painel\_%'
                and p.proname in ('dumtech_painel_portao', 'dumtech_painel_acessos', 'dumtech_painel_usuarios',
                                  'dumtech_painel_salvar_usuario', 'dumtech_painel_senha_provisoria',
                                  'dumtech_painel_apagar_usuario', 'dumtech_painel_exigir_conta')
                or p.proname = 'dumtech_ajustar_computadores')
    loop
        execute format('revoke execute on function %s from public, anon', v_funcao);
        execute format('grant execute on function %s to authenticated', v_funcao);
    end loop;
end;
$$;

revoke execute on function public.dumtech_celular_iniciar(text, text, text, text)         from public, authenticated;
revoke execute on function public.dumtech_celular_aparelhos(text, text, text, text)       from public, authenticated;
revoke execute on function public.dumtech_celular_revogar(text, text, text, uuid, text)   from public, authenticated;
grant  execute on function public.dumtech_celular_iniciar(text, text, text, text)         to anon;
grant  execute on function public.dumtech_celular_aparelhos(text, text, text, text)       to anon;
grant  execute on function public.dumtech_celular_revogar(text, text, text, uuid, text)   to anon;

notify pgrst, 'reload schema';
