-- =============================================================================
-- Versao do Hub: o cliente fica sabendo que saiu uma nova.
--
-- O PROBLEMA
--   Ninguem avisava. Correcao de seguranca, modulo novo, conserto de defeito -
--   tudo ficava parado no instalador do site, esperando o cliente lembrar de
--   baixar de novo. E a DumTech tambem nao sabia quem estava em que versao.
--
-- O DESENHO
--   1. `hub_versoes` guarda UMA linha: a versao publicada, o endereco para
--      baixar e um recado curto. Quem edita e o painel (administrador).
--   2. o Hub pergunta de hora em hora (junto das outras tarefas de rede) e,
--      de quebra, diz em que versao ele esta - isso fica em `ativacoes.versao`,
--      e o painel mostra quem esta para tras.
--   3. nada disso e segredo: a funcao responde para a chave anon, com limite
--      por hora, e nao revela se a chave existe ou nao.
--
-- Depende de: 20260912180000_tempo_real_e_blindagem.sql (limites_de_taxa).
-- =============================================================================

create table if not exists public.hub_versoes (
    id            smallint primary key default 1 check (id = 1),
    versao        text not null default '',
    url           text not null default '',
    notas         text not null default '',
    -- versao critica (falha de seguranca): o Hub insiste em vez de so avisar
    obrigatoria   boolean not null default false,
    atualizado_em timestamptz not null default now()
);

comment on table public.hub_versoes is
    'A versao do Hub publicada hoje. Uma linha so (id = 1). O Hub pergunta de '
    'hora em hora e avisa o cliente quando a dele e mais velha.';

insert into public.hub_versoes (id, versao, url, notas)
values (1, '', 'https://dumtech-hub.netlify.app/baixar/', '')
on conflict (id) do nothing;

alter table public.ativacoes add column if not exists versao    text not null default '';
alter table public.ativacoes add column if not exists versao_em timestamptz;

comment on column public.ativacoes.versao is
    'A versao do Hub que este computador disse estar usando na ultima conversa.';

-- ============================================================== A FUNCAO =====
create or replace function public.dumtech_hub_versao(
    p_chave   text default '',
    p_maquina text default '',
    p_versao  text default '',
    p_ip      text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_atual  public.hub_versoes;
    v_versao text := left(btrim(coalesce(p_versao, '')), 20);
begin
    if not public.dumtech_dentro_do_limite('versao_ip', left(btrim(coalesce(p_ip, '')), 64), 120, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas');
    end if;

    -- anota em silencio quem esta em que versao (so serve para o painel).
    -- Chave que nao existe simplesmente nao atualiza nada - e a resposta e igual.
    if v_versao ~ '^[0-9A-Za-z.+-]{1,20}$' then
        update public.ativacoes a
           set versao = v_versao, versao_em = now()
          from public.licencas l
         where l.id = a.licenca_id
           and l.chave = public.dumtech_normalizar(p_chave, 32)
           and a.maquina = public.dumtech_normalizar(p_maquina, 64)
           and (a.versao is distinct from v_versao or a.versao_em < now() - interval '1 hour');
    end if;

    select * into v_atual from public.hub_versoes where id = 1;
    return jsonb_build_object(
        'ok', true,
        'versao', coalesce(v_atual.versao, ''),
        'url', coalesce(v_atual.url, ''),
        'notas', coalesce(v_atual.notas, ''),
        'obrigatoria', coalesce(v_atual.obrigatoria, false));
end;
$$;

-- ============================================================ PERMISSOES =====
alter table public.hub_versoes enable row level security;
revoke all on table public.hub_versoes from anon, authenticated;

-- o painel (administrador com 2 fatores) le e edita
drop policy if exists admin_le_versao on public.hub_versoes;
create policy admin_le_versao on public.hub_versoes for select to authenticated
    using (public.dumtech_e_admin());
drop policy if exists admin_escreve_versao on public.hub_versoes;
create policy admin_escreve_versao on public.hub_versoes for all to authenticated
    using (public.dumtech_e_admin()) with check (public.dumtech_e_admin());
grant select, insert, update on table public.hub_versoes to authenticated;

-- o Hub pergunta com a chave anon, como ja faz nas outras funcoes
revoke execute on function public.dumtech_hub_versao(text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.dumtech_hub_versao(text, text, text, text) to anon, authenticated;
