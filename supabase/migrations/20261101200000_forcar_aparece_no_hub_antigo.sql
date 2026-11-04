-- =============================================================================
-- Forcar aparece no Hub antigo, e continua instalando sozinho.
--
-- O PROBLEMA
--   O Hub 1.5.1 a 1.9.0 nao conhece `forcada`. Com `silenciosa` ele baixa e
--   instala ao fechar, mas esconde o botao e o aviso: quem forcava via "nada
--   aconteceu", e Atualizar parecia fazer mais do que Forcar.
--
-- A SAIDA
--   Esses Hubs guardam o instalador baixado e, ao fechar, instalam sem olhar de
--   novo para `silenciosa`. Entao o manifesto vai silencioso so nos primeiros 3
--   minutos, contados da ordem ou da abertura do Hub (o que vier depois): tempo
--   de a conferencia de 2 em 2 minutos comecar o download. Depois vai so
--   `obrigatoria`, e o botao e o aviso que nao se dispensa aparecem.
--
-- O QUE NAO MUDA
--   Sem nada forcado, a resposta e a mesma de antes. O Hub 1.10.0 ou mais novo
--   segue `forcada` e nao liga para esta troca. Hub sem computador ativado nao
--   tem sessao para contar: continua silencioso, e instala ao fechar.
-- =============================================================================

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
    v_atual    public.hub_versoes;
    v_lib      public.hub_liberacoes;
    v_alvo     public.hub_lancamentos;
    v_versao   text := left(btrim(coalesce(p_versao, '')), 20);
    v_maquina  text := public.dumtech_normalizar(p_maquina, 64);
    v_licenca  uuid;
    v_sessao   timestamptz;
    v_ordem    timestamptz;
    v_forcada  boolean;
    v_baixando boolean;
begin
    -- o Hub pergunta a cada 2 minutos (30 por hora). Uma loja com varios
    -- computadores sai pelo mesmo endereco, entao o teto e bem mais alto do
    -- que o das outras portas - e continua barrando enxurrada.
    if not public.dumtech_dentro_do_limite('versao_ip', left(btrim(coalesce(p_ip, '')), 64), 600, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas');
    end if;

    if v_versao !~ '^[0-9A-Za-z.+-]{1,20}$' then
        v_versao := '';
    end if;

    -- chave inventada, ou computador que nao e desta chave, nao anota nada
    select a.licenca_id into v_licenca
      from public.ativacoes a
      join public.licencas l on l.id = a.licenca_id
     where l.chave = public.dumtech_normalizar(p_chave, 32)
       and a.maquina = v_maquina;

    if v_licenca is not null then
        insert into public.hub_presenca as h (licenca_id, maquina, versao)
        values (v_licenca, v_maquina, v_versao)
        on conflict (licenca_id, maquina) do update
           set visto_em = now(),
               online_desde = case when h.visto_em < now() - interval '5 minutes'
                                   then now() else h.online_desde end,
               versao_desde = case when excluded.versao not in ('', h.versao)
                                   then now() else h.versao_desde end,
               versao = case when excluded.versao = '' then h.versao else excluded.versao end
        returning h.online_desde into v_sessao;

        -- anota em silencio quem esta em que versao (so serve para o painel)
        if v_versao <> '' then
            update public.ativacoes a
               set versao = v_versao, versao_em = now()
             where a.licenca_id = v_licenca
               and a.maquina = v_maquina
               and (a.versao is distinct from v_versao or a.versao_em < now() - interval '1 hour');
        end if;

        select * into v_lib from public.hub_liberacoes where licenca_id = v_licenca;
    end if;

    select * into v_atual from public.hub_versoes where id = 1;
    v_forcada := coalesce(v_atual.forcada, false);
    v_ordem := v_atual.atualizado_em;

    if v_lib.licenca_id is not null then
        if public.dumtech_versao_numeros(v_lib.versao) > public.dumtech_versao_numeros(v_atual.versao) then
            select * into v_alvo from public.hub_lancamentos
             where versao = v_lib.versao and descartada_em is null;
            if v_alvo.versao is not null then
                v_forcada := v_lib.forcada;
                v_ordem := v_lib.criado_em;
            end if;
        elsif v_lib.versao = v_atual.versao and v_lib.forcada then
            v_forcada := true;
            v_ordem := v_lib.criado_em;
        end if;
    end if;

    -- greatest ignora o vazio, mas sem sessao nao ha como contar: segue silencioso
    v_baixando := v_forcada
        and (v_sessao is null or now() - greatest(v_sessao, v_ordem) < interval '3 minutes');

    -- a versao que so este cliente recebe
    if v_alvo.versao is not null then
        return jsonb_build_object(
            'ok', true,
            'versao', v_alvo.versao,
            'url', v_alvo.url,
            'notas', v_alvo.notas,
            'obrigatoria', v_forcada,
            'sha256', v_alvo.sha256,
            'automatica', coalesce(v_atual.automatica, true),
            'silenciosa', v_baixando,
            'forcada', v_forcada,
            'tamanho', v_alvo.tamanho,
            'licenca', public.dumtech_licenca_marca(p_chave, p_maquina));
    end if;

    return jsonb_build_object(
        'ok', true,
        'versao', coalesce(v_atual.versao, ''),
        'url', coalesce(v_atual.url, ''),
        'notas', coalesce(v_atual.notas, ''),
        'obrigatoria', coalesce(v_atual.obrigatoria, false) or v_forcada,
        'sha256', lower(coalesce(v_atual.sha256, '')),
        'automatica', coalesce(v_atual.automatica, true),
        'silenciosa', coalesce(v_atual.silenciosa, false) or v_baixando,
        'forcada', v_forcada,
        'tamanho', coalesce(v_atual.tamanho, 0),
        'licenca', public.dumtech_licenca_marca(p_chave, p_maquina));
end;
$$;

revoke execute on function public.dumtech_hub_versao(text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.dumtech_hub_versao(text, text, text, text) to anon, authenticated;
