-- =============================================================================
-- 20260912210000 - licenca assinada, painel com 2 fatores e auditoria
--
-- O QUE ENTRA
--   1. licenca assinada   `dumtech_licenca_para_assinar`: a conferencia que a Edge
--                         Function `licenca-assinada` usa antes de assinar (so o
--                         service_role chama). A regra e a MESMA do Hub: as duas
--                         portas passam por `dumtech_verificar_interno`.
--   2. dois fatores       o painel so enxerga dado com sessao `aal2` (senha +
--                         codigo do aplicativo autenticador). Quem decide e o
--                         banco: pular a tela do codigo no navegador nao adianta.
--   3. auditoria          quem mudou o que, quando, e o valor de antes e de depois.
--                         So leitura, so administrador, e ninguem apaga pela API.
--   4. dados da chave     o que a mensagem "sua licenca esta pronta" precisa.
--
-- ATENCAO NA ORDEM: publique o painel NOVO (com a tela do codigo) antes de
-- aplicar esta migration. O painel antigo entra com senha so (aal1) e, depois
-- dela, passa a ver tudo vazio.
--
-- PERDEU O CELULAR? Supabase > Authentication > Users > (voce) > apague o fator
-- MFA. No proximo login o painel pede para cadastrar de novo.
-- =============================================================================

-- ================================================ 1. LICENCA ASSINADA =======
-- O miolo da verificacao, sem limite (quem chama conta o limite do jeito dele).
create or replace function public.dumtech_verificar_interno(
    p_chave   text,
    p_maquina text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca public.licencas;
    v_texto   text;
begin
    p_chave   := public.dumtech_normalizar(p_chave, 32);
    p_maquina := public.dumtech_normalizar(p_maquina, 64);

    if p_chave = '' or p_maquina = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe a chave da licenca.');
    end if;

    v_licenca := public.dumtech_licenca_valida(p_chave);

    update public.ativacoes
       set ultima_checagem = now()
     where licenca_id = v_licenca.id and maquina = p_maquina;

    if not found then
        return jsonb_build_object(
            'ok', false, 'erro', 'maquina_nao_ativada',
            'mensagem', 'Este computador ainda nao foi ativado com esta chave. '
                     || 'Use o botao Ativar licenca.');
    end if;

    return public.dumtech_resposta_licenca(v_licenca.id);

exception
    when others then
        v_texto := sqlerrm;
        if position('|' in v_texto) > 0 then
            insert into public.licenca_tentativas (chave, maquina, erro)
            values (p_chave, p_maquina, split_part(v_texto, '|', 1));
            return jsonb_build_object('ok', false,
                                      'erro', split_part(v_texto, '|', 1),
                                      'mensagem', split_part(v_texto, '|', 2));
        end if;
        raise;
end;
$$;

-- a porta do Hub (chave anon): limite pelo endereco do cabecalho
create or replace function public.dumtech_verificar_licenca(
    p_chave   text,
    p_maquina text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
    if not public.dumtech_dentro_do_limite('licenca_ip', public.dumtech_ip_do_pedido(), 120, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas deste endereco. Espere alguns minutos e tente de novo.');
    end if;
    return public.dumtech_verificar_interno(p_chave, p_maquina);
end;
$$;

-- a porta da Edge Function (service_role): o endereco vem da propria funcao,
-- senao todos os Hubs dividiriam o limite do endereco do servidor da funcao
create or replace function public.dumtech_licenca_para_assinar(
    p_chave   text,
    p_maquina text,
    p_ip      text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
    if not public.dumtech_dentro_do_limite('licenca_ip', left(btrim(coalesce(p_ip, '')), 64), 120, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas deste endereco. Espere alguns minutos e tente de novo.');
    end if;
    return public.dumtech_verificar_interno(p_chave, p_maquina);
end;
$$;

-- ===================================================== 2. DOIS FATORES ======
-- Nivel da sessao que o Supabase Auth carimba no token: aal1 = so senha,
-- aal2 = senha + codigo. Fora da API (SQL Editor) nao ha token: vazio.
create or replace function public.dumtech_nivel_sessao()
returns text
language plpgsql
stable
set search_path = ''
as $$
declare
    v_claims jsonb;
begin
    begin
        v_claims := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
    exception when others then
        v_claims := null;
    end;
    return coalesce(v_claims ->> 'aal', nullif(current_setting('request.jwt.claim.aal', true), ''), '');
end;
$$;

-- O painel pergunta ANTES do codigo: "esta conta e administradora, e em que
-- nivel ela esta?". Responde so sobre quem pergunta.
create or replace function public.dumtech_sou_admin()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    select jsonb_build_object(
        'admin', exists (select 1 from public.administradores a
                          where a.user_id = public.dumtech_admin_id()),
        'nivel', public.dumtech_nivel_sessao());
$$;

-- Toda policy do painel (e o canal privado do tempo real) pergunta esta funcao.
-- A partir daqui ela exige o segundo fator.
create or replace function public.dumtech_e_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select public.dumtech_nivel_sessao() = 'aal2'
       and exists (select 1 from public.administradores a
                    where a.user_id = public.dumtech_admin_id());
$$;

-- ======================================================== 3. AUDITORIA ======
create table if not exists public.auditoria (
    id         bigint generated always as identity primary key,
    quando     timestamptz not null default now(),
    quem       uuid,
    quem_email text not null default '',
    origem     text not null check (origem in ('painel', 'servico', 'sql')),
    tabela     text not null,
    operacao   text not null check (operacao in ('insert', 'update', 'delete')),
    registro   text not null default '',
    antes      jsonb,
    depois     jsonb
);

comment on table public.auditoria is
    'Quem mudou o que no cadastro comercial. Gravada por gatilho; ninguem escreve '
    'nem apaga pela API. Nao registra o que o Hub e o site fazem pelas funcoes '
    'publicas (ativar, conferir, pedir) - isso ja esta em ativacoes, tentativas e pedidos.';

create index if not exists idx_auditoria_quando on public.auditoria (quando desc);
create index if not exists idx_auditoria_tabela on public.auditoria (tabela, quando desc);

create or replace function public.dumtech_auditar()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_claims jsonb;
    v_papel  text;
    v_linha  jsonb;
    v_antes  jsonb;
    v_depois jsonb;
begin
    begin
        v_claims := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
    exception when others then
        v_claims := null;
    end;
    v_papel := coalesce(v_claims ->> 'role', '');

    -- Hub e site pelas funcoes publicas: nao e "alguem mexendo no cadastro"
    if v_papel = 'anon' then
        return null;
    end if;

    if tg_op = 'INSERT' then
        v_linha := to_jsonb(new);
        v_depois := v_linha;
    elsif tg_op = 'DELETE' then
        v_linha := to_jsonb(old);
        v_antes := v_linha;
    else
        v_linha := to_jsonb(new);
        -- so o que mudou de verdade; carimbo de hora nao e alteracao
        select jsonb_object_agg(n.key, n.value),
               jsonb_object_agg(n.key, to_jsonb(old) -> n.key)
          into v_depois, v_antes
          from jsonb_each(v_linha) n
         where n.value is distinct from (to_jsonb(old) -> n.key)
           and n.key not in ('atualizado_em', 'ultima_checagem');
        if v_depois is null then
            return null;
        end if;
    end if;

    insert into public.auditoria (quem, quem_email, origem, tabela, operacao, registro, antes, depois)
    values (
        case when v_papel = 'authenticated' then public.dumtech_admin_id() end,
        left(coalesce(v_claims ->> 'email', ''), 160),
        case v_papel when 'authenticated' then 'painel' when 'service_role' then 'servico' else 'sql' end,
        tg_table_name,
        lower(tg_op),
        coalesce(v_linha ->> 'id', v_linha ->> 'user_id',
                 concat_ws(':', v_linha ->> 'licenca_id', v_linha ->> 'combo_id', v_linha ->> 'produto_id')),
        v_antes,
        v_depois);
    return null;
end;
$$;

do $$
declare
    v_tabela text;
begin
    foreach v_tabela in array array['clientes', 'licencas', 'licenca_produtos', 'ativacoes',
                                    'produtos', 'combos', 'combo_produtos', 'comunicados',
                                    'pedidos_site', 'administradores'] loop
        execute format('drop trigger if exists trg_auditoria on public.%I', v_tabela);
        execute format(
            'create trigger trg_auditoria after insert or update or delete on public.%I '
            'for each row execute function public.dumtech_auditar()', v_tabela);
    end loop;
end;
$$;

-- ==================================================== 4. DADOS DA CHAVE ======
-- O que vai na mensagem ao cliente. SECURITY INVOKER: quem nao e administrador
-- (com 2 fatores) recebe null - as policies decidem, nao a funcao.
create or replace function public.dumtech_dados_da_chave(p_licenca_id uuid)
returns jsonb
language sql
stable
set search_path = ''
as $$
    select jsonb_build_object(
        'ok', true,
        'nome', c.nome,
        'email', c.email,
        'telefone', c.telefone,
        'chave', l.chave,
        'tipo', l.tipo,
        'expira_em', l.expira_em,
        'max_computadores', l.max_computadores,
        'modulos', coalesce((select jsonb_agg(p.nome order by p.nome)
                               from public.licenca_produtos lp
                               join public.produtos p on p.id = lp.produto_id
                              where lp.licenca_id = l.id), '[]'::jsonb))
      from public.licencas l
      join public.clientes c on c.id = l.cliente_id
     where l.id = p_licenca_id;
$$;

-- ======================================================= 5. PERMISSOES ======
alter table public.auditoria enable row level security;
revoke all on table public.auditoria from anon, authenticated;
grant select on table public.auditoria to authenticated;
drop policy if exists admin_le on public.auditoria;
create policy admin_le on public.auditoria for select to authenticated
    using (public.dumtech_e_admin());

revoke execute on function public.dumtech_verificar_interno(text, text)           from public, anon, authenticated;
revoke execute on function public.dumtech_licenca_para_assinar(text, text, text)  from public, anon, authenticated;
revoke execute on function public.dumtech_nivel_sessao()                          from public, anon;
revoke execute on function public.dumtech_sou_admin()                             from public, anon;
revoke execute on function public.dumtech_auditar()                               from public, anon, authenticated;
revoke execute on function public.dumtech_dados_da_chave(uuid)                    from public, anon;

grant execute on function public.dumtech_licenca_para_assinar(text, text, text) to service_role;
grant execute on function public.dumtech_nivel_sessao()                         to authenticated, service_role;
grant execute on function public.dumtech_sou_admin()                            to authenticated;
grant execute on function public.dumtech_dados_da_chave(uuid)                   to authenticated, service_role;

revoke execute on function public.dumtech_verificar_licenca(text, text) from public;
grant  execute on function public.dumtech_verificar_licenca(text, text) to anon, authenticated;

notify pgrst, 'reload schema';
