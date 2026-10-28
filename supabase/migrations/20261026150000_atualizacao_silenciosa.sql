-- =============================================================================
-- Atualizacao silenciosa: versao pequena que o Hub instala sozinho.
--
-- O QUE MUDA AQUI
--   `hub_versoes.silenciosa` ligado: o Hub (1.5.1 ou mais novo) baixa em
--   segundo plano e instala quando a pessoa fecha o programa - sem pilula, sem
--   faixa e sem "O que mudou". Vai DENTRO do manifesto assinado (Edge Function
--   `versao`), entao ninguem liga o silencio por fora.
--
--   Hub mais antigo ignora o campo e mostra o botao "Atualizar" como sempre.
--   Quem liga e o `tools\lancar_versao.ps1 -Silenciosa`; o painel publica
--   sempre do jeito normal.
-- =============================================================================

alter table public.hub_versoes add column if not exists silenciosa boolean not null default false;

comment on column public.hub_versoes.silenciosa is
    'Versao pequena: o Hub instala sozinho ao ser fechado, sem aviso na tela. '
    'So vale com atualizacao pelo Hub (automatica + sha256).';

-- a mesma consulta de 20260921120000, agora devolvendo `silenciosa`
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
        'silenciosa', coalesce(v_atual.silenciosa, false),
        'tamanho', coalesce(v_atual.tamanho, 0),
        'licenca', public.dumtech_licenca_marca(p_chave, p_maquina));
end;
$$;

revoke execute on function public.dumtech_hub_versao(text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.dumtech_hub_versao(text, text, text, text) to anon, authenticated;
