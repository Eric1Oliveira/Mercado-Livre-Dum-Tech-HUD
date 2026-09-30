-- =============================================================================
-- O Hub no celular: pareamento por QR Code, como o WhatsApp Web.
--
-- COMO FUNCIONA
--   1. No Hub, "Ver no celular" pede um CODIGO DE PAREAMENTO: vale 5 minutos
--      e uma vez so. Ele vai dentro do QR Code.
--   2. O celular le o QR, abre /celular/ e troca o codigo por um TOKEN do
--      aparelho - a credencial dele, que fica so no celular. Foto do QR
--      tirada depois nao serve: o codigo ja foi usado ou venceu.
--   3. O Hub publica um RESUMO (espelho) do dia enquanto houver celular
--      pareado. O celular le o espelho + a licenca ATUAL a cada abertura:
--      modulo comprado agora aparece no celular na hora.
--   4. "Desconectar" no Hub revoga o aparelho na hora.
--
-- O QUE FICA GUARDADO
--   So o HASH dos codigos e tokens (sha256). Nem quem ler o banco consegue
--   entrar como um celular pareado.
-- =============================================================================

create table if not exists public.celular_codigos (
    codigo_hash text primary key,
    licenca_id  uuid not null references public.licencas(id) on delete cascade,
    maquina     text not null,
    criado_em   timestamptz not null default now(),
    expira_em   timestamptz not null,
    usado_em    timestamptz
);

create table if not exists public.celular_aparelhos (
    id            uuid primary key default gen_random_uuid(),
    licenca_id    uuid not null references public.licencas(id) on delete cascade,
    token_hash    text not null unique,
    nome          text not null default 'Celular',
    maquina       text not null default '',
    criado_em     timestamptz not null default now(),
    ultimo_acesso timestamptz,
    revogado_em   timestamptz
);
create index if not exists idx_celular_aparelhos_licenca on public.celular_aparelhos(licenca_id);

create table if not exists public.celular_espelhos (
    licenca_id    uuid not null references public.licencas(id) on delete cascade,
    maquina       text not null,
    dados         jsonb not null,
    atualizado_em timestamptz not null default now(),
    primary key (licenca_id, maquina)
);

-- ninguem de fora toca nas tabelas: so as funcoes abaixo
alter table public.celular_codigos   enable row level security;
alter table public.celular_aparelhos enable row level security;
alter table public.celular_espelhos  enable row level security;
revoke all on table public.celular_codigos   from anon, authenticated;
revoke all on table public.celular_aparelhos from anon, authenticated;
revoke all on table public.celular_espelhos  from anon, authenticated;
-- o painel ve quantos celulares cada cliente tem (so leitura, so admin)
drop policy if exists admin_le on public.celular_aparelhos;
create policy admin_le on public.celular_aparelhos for select to authenticated using (public.dumtech_e_admin());
grant select on public.celular_aparelhos to authenticated;

create or replace function public.dumtech_celular_hash(p_segredo text)
returns text
language sql
immutable
set search_path = ''
as $$
    select encode(sha256(convert_to('dumtech-celular:' || coalesce(p_segredo, ''), 'UTF8')), 'hex');
$$;
revoke execute on function public.dumtech_celular_hash(text) from public, anon, authenticated;

/**
 * A licenca desta maquina, se estiver ativada aqui e valendo - e se o pedido
 * vem do MESMO computador que a ativacao conhece (quem copiou o license.json
 * para outro PC nao pareia celular nem le os dados da empresa).
 */
create or replace function public.dumtech_celular_licenca(p_chave text, p_maquina text, p_computador text)
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
       and public.dumtech_situacao_licenca(l.status, l.expira_em) = 'ativa'
       and (coalesce(a.computador, '') = '' or a.computador = coalesce(p_computador, ''))
     limit 1;
$$;
revoke execute on function public.dumtech_celular_licenca(text, text, text) from public, anon, authenticated;

-- ============================================================ o Hub pede ===
/** 1. O Hub pede um codigo para o QR (5 minutos, uso unico). */
create or replace function public.dumtech_celular_iniciar(p_chave text, p_maquina text, p_computador text)
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

/** Os celulares desta licenca (o Hub mostra e desconecta). */
create or replace function public.dumtech_celular_aparelhos(p_chave text, p_maquina text, p_computador text)
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
    return jsonb_build_object('ok', true, 'aparelhos', coalesce((
        select jsonb_agg(jsonb_build_object('id', a.id, 'nome', a.nome, 'criado_em', a.criado_em,
                                            'ultimo_acesso', a.ultimo_acesso) order by a.criado_em desc)
          from public.celular_aparelhos a
         where a.licenca_id = v_licenca and a.revogado_em is null), '[]'::jsonb));
end;
$$;

create or replace function public.dumtech_celular_revogar(p_chave text, p_maquina text, p_computador text, p_aparelho uuid)
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
    update public.celular_aparelhos set revogado_em = now()
     where id = p_aparelho and licenca_id = v_licenca and revogado_em is null;
    return jsonb_build_object('ok', found);
end;
$$;

/**
 * O Hub manda o resumo do dia. Sem celular pareado, nao guarda nada (e diz
 * isso: o Hub para de mandar ate alguem parear).
 */
create or replace function public.dumtech_celular_publicar(p_chave text, p_maquina text, p_computador text, p_dados jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca  uuid := public.dumtech_celular_licenca(p_chave, p_maquina, p_computador);
    v_pareados integer;
begin
    if v_licenca is null then
        return jsonb_build_object('ok', false, 'erro', 'licenca_invalida');
    end if;
    select count(*) into v_pareados from public.celular_aparelhos
     where licenca_id = v_licenca and revogado_em is null;
    if v_pareados = 0 then
        return jsonb_build_object('ok', true, 'pareados', 0);
    end if;
    if jsonb_typeof(p_dados) <> 'object' or octet_length(p_dados::text) > 300000 then
        return jsonb_build_object('ok', false, 'erro', 'resumo_invalido');
    end if;
    if not public.dumtech_dentro_do_limite('celular_publicar', v_licenca::text || ':' || p_maquina, 240,
                                           interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas');
    end if;
    insert into public.celular_espelhos (licenca_id, maquina, dados, atualizado_em)
    values (v_licenca, public.dumtech_normalizar(p_maquina, 64), p_dados, now())
    on conflict (licenca_id, maquina) do update set dados = excluded.dados, atualizado_em = now();
    return jsonb_build_object('ok', true, 'pareados', v_pareados);
end;
$$;

-- ========================================================= o celular pede ===
/** 2. O celular troca o codigo do QR pelo token dele (uma vez so). */
create or replace function public.dumtech_celular_parear(p_codigo text, p_nome text default '')
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v       public.celular_codigos;
    v_token text := replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', '');
    v_nome  text := left(btrim(coalesce(nullif(p_nome, ''), 'Celular')), 60);
    v_empresa text;
begin
    if not public.dumtech_dentro_do_limite('celular_parear', public.dumtech_ip_do_pedido(), 30, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos.');
    end if;
    update public.celular_codigos set usado_em = now()
     where codigo_hash = public.dumtech_celular_hash(btrim(coalesce(p_codigo, '')))
       and usado_em is null and expira_em > now()
    returning * into v;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'codigo_invalido',
                                  'mensagem', 'Este QR Code ja foi usado ou venceu. Gere outro no Hub.');
    end if;
    insert into public.celular_aparelhos (licenca_id, token_hash, nome, maquina)
    values (v.licenca_id, public.dumtech_celular_hash(v_token), v_nome, v.maquina);
    select c.nome into v_empresa from public.licencas l join public.clientes c on c.id = l.cliente_id
     where l.id = v.licenca_id;
    return jsonb_build_object('ok', true, 'token', v_token, 'cliente', coalesce(v_empresa, ''));
end;
$$;

/** 3. O celular abre: licenca AGORA (modulo comprado ja vale) + resumo. */
create or replace function public.dumtech_celular_dados(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v         public.celular_aparelhos;
    v_licenca public.licencas;
    v_resp    jsonb;
begin
    select * into v from public.celular_aparelhos
     where token_hash = public.dumtech_celular_hash(btrim(coalesce(p_token, '')))
       and revogado_em is null;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'desconectado',
                                  'mensagem', 'Este celular foi desconectado. Gere um QR Code novo no Hub.');
    end if;
    if not public.dumtech_dentro_do_limite('celular_ler', v.id::text, 600, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas');
    end if;
    select * into v_licenca from public.licencas where id = v.licenca_id;
    if public.dumtech_situacao_licenca(v_licenca.status, v_licenca.expira_em) <> 'ativa' then
        return jsonb_build_object('ok', false, 'erro', 'licenca_bloqueada',
                                  'mensagem', 'A licenca desta empresa nao esta ativa. Fale com a DumTech.');
    end if;
    update public.celular_aparelhos set ultimo_acesso = now() where id = v.id;

    v_resp := public.dumtech_resposta_licenca(v.licenca_id);
    return jsonb_build_object(
        'ok', true,
        'cliente', v_resp->>'cliente',
        -- comprados + testes gratis que ainda estao valendo
        'modulos', coalesce(v_resp->'produtos', '[]'::jsonb) || coalesce((
            select jsonb_agg(key) from jsonb_each_text(coalesce(v_resp->'testes', '{}'::jsonb))
             where value::timestamptz > now()), '[]'::jsonb),
        'espelhos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'computador', coalesce(nullif(a.apelido, ''), 'Computador'),
                       'atualizado_em', e.atualizado_em, 'dados', e.dados) order by e.atualizado_em desc)
              from public.celular_espelhos e
              left join public.ativacoes a on a.licenca_id = e.licenca_id and a.maquina = e.maquina
             where e.licenca_id = v.licenca_id), '[]'::jsonb),
        'agora', now());
end;
$$;

-- ================================================================ portas ===
revoke execute on function public.dumtech_celular_iniciar(text, text, text)          from public, authenticated;
revoke execute on function public.dumtech_celular_aparelhos(text, text, text)        from public, authenticated;
revoke execute on function public.dumtech_celular_revogar(text, text, text, uuid)    from public, authenticated;
revoke execute on function public.dumtech_celular_publicar(text, text, text, jsonb)  from public, authenticated;
revoke execute on function public.dumtech_celular_parear(text, text)           from public, authenticated;
revoke execute on function public.dumtech_celular_dados(text)                  from public, authenticated;
grant  execute on function public.dumtech_celular_iniciar(text, text, text)          to anon;
grant  execute on function public.dumtech_celular_aparelhos(text, text, text)        to anon;
grant  execute on function public.dumtech_celular_revogar(text, text, text, uuid)    to anon;
grant  execute on function public.dumtech_celular_publicar(text, text, text, jsonb)  to anon;
grant  execute on function public.dumtech_celular_parear(text, text)           to anon;
grant  execute on function public.dumtech_celular_dados(text)                  to anon;

notify pgrst, 'reload schema';
