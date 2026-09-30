-- =============================================================================
-- Atualizar pelo proprio Hub: um botao, sem procurar instalador no site.
--
-- O QUE MUDA AQUI
--   `hub_versoes` ganha o que falta para o Hub baixar e instalar sozinho:
--     sha256      a impressao digital do instalador. O Hub so executa o arquivo
--                 se a conta bater - download pela metade ou trocado no caminho
--                 nao vira instalacao.
--     automatica  o SEU controle: desligado, o Hub apenas avisa e manda para a
--                 pagina de download (o botao "Baixar e instalar" some).
--     tamanho     so para a tela dizer "23,4 MB" antes de comecar.
--
-- A assinatura de verdade nao esta aqui: quem assina o manifesto (versao + url
-- + sha256) e a Edge Function `versao`, com a chave privada da DumTech. O Hub
-- confere a assinatura ANTES de baixar. Assim, nem alguem que entre no painel
-- ou no banco consegue apontar o botao para um instalador falso.
-- =============================================================================

alter table public.hub_versoes add column if not exists sha256     text not null default '';
alter table public.hub_versoes add column if not exists automatica boolean not null default true;
alter table public.hub_versoes add column if not exists tamanho    bigint not null default 0;

comment on column public.hub_versoes.sha256 is
    'SHA-256 do instalador publicado (build\build.ps1 imprime). Sem ele, o Hub '
    'so avisa: baixar e instalar exige a conta bater.';
comment on column public.hub_versoes.automatica is
    'Liga o botao "Baixar e instalar" dentro do Hub. Desligado, o cliente e '
    'mandado para a pagina de download.';

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
    -- o Hub pergunta a cada 2 minutos (30 por hora). Uma loja com varios
    -- computadores sai pelo mesmo endereco, entao o teto e bem mais alto do
    -- que o das outras portas - e continua barrando enxurrada.
    if not public.dumtech_dentro_do_limite('versao_ip', left(btrim(coalesce(p_ip, '')), 64), 600, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas');
    end if;

    -- anota em silencio quem esta em que versao (so serve para o painel)
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
        'obrigatoria', coalesce(v_atual.obrigatoria, false),
        'sha256', lower(coalesce(v_atual.sha256, '')),
        'automatica', coalesce(v_atual.automatica, true),
        'tamanho', coalesce(v_atual.tamanho, 0));
end;
$$;

revoke execute on function public.dumtech_hub_versao(text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.dumtech_hub_versao(text, text, text, text) to anon, authenticated;
