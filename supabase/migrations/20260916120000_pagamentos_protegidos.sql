-- =============================================================================
-- Pagamentos protegidos: a chave Pix do Hub so muda com codigo por e-mail.
--
-- O PROBLEMA
--   A chave Pix morava no hub.json do cliente. Um funcionario, ou um virus,
--   trocava a chave e o dinheiro do balcao ia para outra conta - sem ninguem
--   perceber, porque o QR Code continuava aparecendo normalmente.
--
-- O DESENHO
--   1. codigo       o Hub pede; o banco gera 6 digitos (10 min, 5 tentativas) e a
--                   Edge Function `pagamentos` manda para o e-mail DA LICENCA -
--                   o que esta aqui no servidor, nunca o que o Hub diz.
--   2. sessao       codigo certo abre uma sessao de 15 min. O Hub recebe um
--                   segredo que so fica na memoria; o banco guarda o hash.
--   3. chave Pix    guardada por licenca (todos os computadores da loja veem a
--                   mesma). A Edge Function ASSINA a chave para cada computador;
--                   o Hub so usa no QR a chave com assinatura valida.
--
-- NAO existe codigo de reserva guardado no computador do cliente: sem internet a
-- area simplesmente nao abre (o balcao continua vendendo com a chave ja
-- confirmada). Quem perde o acesso ao e-mail resolve no painel, trocando o
-- e-mail do cadastro.
--
-- Todas as funcoes sao do service_role: so a Edge Function chama. O anon nao
-- enxerga tabela nem funcao nenhuma daqui.
--
-- Depende de: 20260912180000_tempo_real_e_blindagem.sql (limites_de_taxa) e
--             20260912210000_assinatura_mfa_auditoria.sql (verificar_interno).
-- =============================================================================

-- ================================================================ TABELAS ====
create table if not exists public.pagamento_config (
    licenca_id     uuid primary key references public.licencas(id) on delete cascade,
    pix_chave      text not null default '',
    atualizado_em  timestamptz not null default now(),
    atualizado_por text not null default ''      -- maquina que salvou
);

create table if not exists public.pagamento_codigos (
    id          uuid primary key default gen_random_uuid(),
    licenca_id  uuid not null references public.licencas(id) on delete cascade,
    maquina     text not null,
    computador  text not null,
    codigo_hash text not null,
    criado_em   timestamptz not null default now(),
    expira_em   timestamptz not null,
    tentativas  integer not null default 0,
    usado_em    timestamptz
);
create index if not exists idx_pagamento_codigos_aberto
    on public.pagamento_codigos (licenca_id, maquina, criado_em desc) where usado_em is null;

create table if not exists public.pagamento_sessoes (
    sessao_hash text primary key,
    licenca_id  uuid not null references public.licencas(id) on delete cascade,
    maquina     text not null,
    computador  text not null,
    criado_em   timestamptz not null default now(),
    expira_em   timestamptz not null
);

-- historico de trocas da chave (nunca apagado pela API)
create table if not exists public.pagamento_historico (
    id         bigint generated always as identity primary key,
    licenca_id uuid not null references public.licencas(id) on delete cascade,
    quando     timestamptz not null default now(),
    maquina    text not null default '',
    antes      text not null default '',
    depois     text not null default ''
);

alter table public.pagamento_config    enable row level security;
alter table public.pagamento_codigos   enable row level security;
alter table public.pagamento_sessoes   enable row level security;
alter table public.pagamento_historico enable row level security;

revoke all on table public.pagamento_config    from anon, authenticated;
revoke all on table public.pagamento_codigos   from anon, authenticated;
revoke all on table public.pagamento_sessoes   from anon, authenticated;
revoke all on table public.pagamento_historico from anon, authenticated;

-- ============================================================== PECINHAS ====
-- hash com a licenca como sal: o mesmo codigo em duas licencas da hashes diferentes
create or replace function public.dumtech_pag_hash(p_licenca uuid, p_codigo text)
returns text
language sql
immutable
set search_path = ''
as $$
    select encode(sha256(convert_to(p_licenca::text || ':' || p_codigo, 'UTF8')), 'hex');
$$;

-- 6 digitos dos 48 bits aleatorios do gen_random_uuid (vies desprezivel)
create or replace function public.dumtech_pag_codigo_email()
returns text
language sql
volatile
set search_path = ''
as $$
    select lpad(((('x' || left(replace(gen_random_uuid()::text, '-', ''), 12))::bit(48)::bigint)
                 % 1000000)::text, 6, '0');
$$;

-- a licenca vale E este computador foi ativado com ela. NULL = nao autorizado
-- (chave inexistente, suspensa ou computador estranho respondem igual).
create or replace function public.dumtech_pag_licenca(p_chave text, p_maquina text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_resposta jsonb;
begin
    v_resposta := public.dumtech_verificar_interno(p_chave, p_maquina);
    if not coalesce((v_resposta->>'ok')::boolean, false) then
        return null;
    end if;
    return (select l.id from public.licencas l
             where l.chave = public.dumtech_normalizar(p_chave, 32));
end;
$$;

create or replace function public.dumtech_pag_recusa()
returns jsonb
language sql
immutable
set search_path = ''
as $$
    select jsonb_build_object('ok', false, 'erro', 'nao_autorizado',
        'mensagem', 'Este computador nao esta com uma licenca ativa. Confira a licenca e tente de novo.');
$$;

-- a sessao aberta pelo codigo: mesma licenca, mesmo computador, no prazo
create or replace function public.dumtech_pag_sessao_valida(
    p_licenca uuid, p_maquina text, p_computador text, p_sessao text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1 from public.pagamento_sessoes s
         where s.sessao_hash = public.dumtech_pag_hash(p_licenca, coalesce(p_sessao, ''))
           and s.licenca_id = p_licenca
           and s.maquina = public.dumtech_normalizar(p_maquina, 64)
           and s.computador = p_computador
           and s.expira_em > now());
$$;

-- ============================================================ 1. CODIGO ======
create or replace function public.dumtech_pagamentos_pedir_codigo(
    p_chave      text,
    p_maquina    text,
    p_computador text,
    p_ip         text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid;
    v_cliente public.clientes;
    v_codigo  text;
    v_maquina text := public.dumtech_normalizar(p_maquina, 64);
begin
    if not public.dumtech_dentro_do_limite('pag_codigo_ip', left(btrim(coalesce(p_ip, '')), 64), 20, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Muitos pedidos de codigo. Espere alguns minutos e tente de novo.');
    end if;
    if coalesce(p_computador, '') !~ '^[0-9a-f]{32}$' then
        return public.dumtech_pag_recusa();
    end if;

    v_licenca := public.dumtech_pag_licenca(p_chave, p_maquina);
    if v_licenca is null then
        return public.dumtech_pag_recusa();
    end if;
    if not public.dumtech_dentro_do_limite('pag_codigo_licenca', v_licenca::text, 5, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Ja enviamos varios codigos na ultima hora. Use o ultimo que chegou ou espere um pouco.');
    end if;

    select c.* into v_cliente
      from public.clientes c join public.licencas l on l.cliente_id = c.id
     where l.id = v_licenca;
    if not public.dumtech_email_valido(v_cliente.email) then
        return jsonb_build_object('ok', false, 'erro', 'sem_email',
            'mensagem', 'Esta licenca ainda nao tem e-mail cadastrado. Fale com a DumTech para cadastrar.');
    end if;

    -- so o ultimo codigo vale
    update public.pagamento_codigos set usado_em = now()
     where licenca_id = v_licenca and maquina = v_maquina and usado_em is null;

    v_codigo := public.dumtech_pag_codigo_email();
    insert into public.pagamento_codigos (licenca_id, maquina, computador, codigo_hash, expira_em)
    values (v_licenca, v_maquina, p_computador, public.dumtech_pag_hash(v_licenca, v_codigo),
            now() + interval '10 minutes');

    return jsonb_build_object('ok', true, 'codigo', v_codigo, 'email', lower(v_cliente.email),
                              'cliente', v_cliente.nome, 'validade_minutos', 10);
end;
$$;

-- ============================================================ 2. ENTRAR ======
-- So o codigo de 6 digitos que a funcao `codigo` mandou por e-mail.
create or replace function public.dumtech_pagamentos_entrar(
    p_chave      text,
    p_maquina    text,
    p_computador text,
    p_codigo     text,
    p_ip         text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca  uuid;
    v_maquina  text := public.dumtech_normalizar(p_maquina, 64);
    v_texto    text := btrim(coalesce(p_codigo, ''));
    v_aberto   public.pagamento_codigos;
    v_sessao   text;
    v_expira   timestamptz := now() + interval '15 minutes';
    v_pix      text;
    v_erro     constant jsonb := jsonb_build_object('ok', false, 'erro', 'codigo_invalido',
                   'mensagem', 'Codigo incorreto ou vencido. Confira e tente de novo, ou peca outro.');
begin
    if not public.dumtech_dentro_do_limite('pag_entrar_ip', left(btrim(coalesce(p_ip, '')), 64), 30, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
            'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos e tente de novo.');
    end if;
    if coalesce(p_computador, '') !~ '^[0-9a-f]{32}$' then
        return public.dumtech_pag_recusa();
    end if;
    v_licenca := public.dumtech_pag_licenca(p_chave, p_maquina);
    if v_licenca is null then
        return public.dumtech_pag_recusa();
    end if;

    if v_texto !~ '^[0-9]{6}$' then
        return v_erro;
    end if;

    select * into v_aberto from public.pagamento_codigos
     where licenca_id = v_licenca and maquina = v_maquina and computador = p_computador
       and usado_em is null and expira_em > now()
     order by criado_em desc limit 1
       for update;
    if not found then
        return v_erro;
    end if;
    update public.pagamento_codigos set tentativas = tentativas + 1 where id = v_aberto.id;
    if v_aberto.codigo_hash <> public.dumtech_pag_hash(v_licenca, v_texto) then
        if v_aberto.tentativas + 1 >= 5 then
            update public.pagamento_codigos set usado_em = now() where id = v_aberto.id;
            return jsonb_build_object('ok', false, 'erro', 'codigo_bloqueado',
                'mensagem', 'Codigo errado 5 vezes: ele deixou de valer. Peca um codigo novo.');
        end if;
        return v_erro;
    end if;
    update public.pagamento_codigos set usado_em = now() where id = v_aberto.id;

    -- faxina das sessoes vencidas desta licenca
    delete from public.pagamento_sessoes where licenca_id = v_licenca and expira_em < now();

    v_sessao := public.dumtech_novo_token() || public.dumtech_novo_token();
    insert into public.pagamento_sessoes (sessao_hash, licenca_id, maquina, computador, expira_em)
    values (public.dumtech_pag_hash(v_licenca, v_sessao), v_licenca, v_maquina, p_computador, v_expira);

    select pix_chave into v_pix from public.pagamento_config where licenca_id = v_licenca;

    return jsonb_build_object(
        'ok', true,
        'sessao', v_sessao,
        'expira_em', v_expira,
        'pix_chave', coalesce(v_pix, ''));
end;
$$;

-- ============================================================ 3. SALVAR ======
create or replace function public.dumtech_pagamentos_salvar(
    p_chave      text,
    p_maquina    text,
    p_computador text,
    p_sessao     text,
    p_pix_chave  text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid;
    v_pix     text := btrim(coalesce(p_pix_chave, ''));
    v_antes   text;
    v_cliente public.clientes;
begin
    v_licenca := public.dumtech_pag_licenca(p_chave, p_maquina);
    if v_licenca is null then
        return public.dumtech_pag_recusa();
    end if;
    if not public.dumtech_pag_sessao_valida(v_licenca, p_maquina, p_computador, p_sessao) then
        return jsonb_build_object('ok', false, 'erro', 'sessao_vencida',
            'mensagem', 'O acesso a Pagamentos venceu. Entre de novo com um codigo.');
    end if;
    -- o Hub ja normalizou; aqui so barra o que nenhuma chave Pix tem
    if length(v_pix) > 77 or v_pix !~ '^[A-Za-z0-9@.+_-]*$' then
        return jsonb_build_object('ok', false, 'erro', 'pix_invalida',
            'mensagem', 'Essa chave Pix nao parece valida.');
    end if;

    select pix_chave into v_antes from public.pagamento_config where licenca_id = v_licenca for update;
    v_antes := coalesce(v_antes, '');

    insert into public.pagamento_config (licenca_id, pix_chave, atualizado_em, atualizado_por)
    values (v_licenca, v_pix, now(), public.dumtech_normalizar(p_maquina, 64))
    on conflict (licenca_id) do update
        set pix_chave = excluded.pix_chave, atualizado_em = now(), atualizado_por = excluded.atualizado_por;

    if v_antes <> v_pix then
        insert into public.pagamento_historico (licenca_id, maquina, antes, depois)
        values (v_licenca, public.dumtech_normalizar(p_maquina, 64), v_antes, v_pix);
    end if;

    select c.* into v_cliente
      from public.clientes c join public.licencas l on l.cliente_id = c.id
     where l.id = v_licenca;

    return jsonb_build_object('ok', true, 'pix_chave', v_pix, 'antes', v_antes,
                              'mudou', v_antes <> v_pix,
                              'email', lower(coalesce(v_cliente.email, '')), 'cliente', v_cliente.nome);
end;
$$;

-- ============================================================= 5. ATUAL ======
-- A conferencia de fundo do Hub: qual e a chave Pix desta loja agora?
create or replace function public.dumtech_pagamentos_atual(
    p_chave   text,
    p_maquina text,
    p_ip      text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid;
    v_pix     text;
begin
    if not public.dumtech_dentro_do_limite('pag_atual_ip', left(btrim(coalesce(p_ip, '')), 64), 120, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas', 'mensagem', 'Muitas consultas.');
    end if;
    v_licenca := public.dumtech_pag_licenca(p_chave, p_maquina);
    if v_licenca is null then
        return public.dumtech_pag_recusa();
    end if;
    select pix_chave into v_pix from public.pagamento_config where licenca_id = v_licenca;
    return jsonb_build_object('ok', true, 'pix_chave', coalesce(v_pix, ''));
end;
$$;

-- =========================================================== PERMISSOES ======
-- O Supabase da EXECUTE ao anon em toda funcao nova do schema public: tirar de
-- public, anon e authenticated (os tres), e dar so ao service_role.
do $$
declare
    v_assinatura text;
begin
    foreach v_assinatura in array array[
        'public.dumtech_pag_hash(uuid, text)',
        'public.dumtech_pag_codigo_email()',
        'public.dumtech_pag_licenca(text, text)',
        'public.dumtech_pag_recusa()',
        'public.dumtech_pag_sessao_valida(uuid, text, text, text)',
        'public.dumtech_pagamentos_pedir_codigo(text, text, text, text)',
        'public.dumtech_pagamentos_entrar(text, text, text, text, text)',
        'public.dumtech_pagamentos_salvar(text, text, text, text, text)',
        'public.dumtech_pagamentos_atual(text, text, text)'
    ] loop
        execute format('revoke execute on function %s from public, anon, authenticated', v_assinatura);
        execute format('grant execute on function %s to service_role', v_assinatura);
    end loop;
end;
$$;
