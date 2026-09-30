-- =============================================================================
-- Mudanca feita no painel chega ao Hub em minutos, nao em uma hora.
--
-- O PROBLEMA
--   O Hub so reconferia a licenca (a chamada pesada: assinatura Ed25519) de
--   hora em hora. Liberar um modulo, renovar, bloquear, soltar um computador
--   ou trocar a chave Pix em outro computador da loja levava ate 60 minutos
--   para aparecer. Reconferir a cada 2 minutos esbarraria no limite de 120
--   pedidos por hora por IP numa loja com varios computadores.
--
-- A SAIDA
--   O Hub ja pergunta a versao a cada 2 minutos (consulta leve, limite de
--   600/h). Esta mesma consulta passa a devolver `licenca`: uma impressao
--   digital (md5) de tudo que muda o que o Hub libera. Se a impressao mudou,
--   o Hub busca a licenca assinada NA HORA; se nao mudou, nao gasta nada.
--
-- O QUE ENTRA NA IMPRESSAO
--   situacao, validade, tipo e vagas da licenca; os produtos e combos
--   liberados (e quando o cadastro deles mudou); se ESTE computador continua
--   ativado; e quando a chave Pix foi trocada.
--   Fica de fora o que muda a cada conferencia (ultima_checagem, versao):
--   senao a impressao mudaria sozinha e o Hub reconferiria sem parar.
--
-- SEGURANCA
--   A impressao nao libera nada - so diz "vale a pena perguntar de novo". O
--   que libera continua sendo a licenca assinada. Um md5 opaco nao revela
--   modulos, validade nem Pix, e sem chave+maquina validas vem vazio.
-- =============================================================================

create or replace function public.dumtech_licenca_marca(p_chave text, p_maquina text)
returns text
language sql
stable
security definer
set search_path = ''
as $$
    select coalesce((
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
              where pc.licenca_id = l.id)
        ))
        from public.licencas l
        where l.chave = public.dumtech_normalizar(p_chave, 32)
          -- so quem tem ativacao nesta maquina recebe impressao: chave
          -- adivinhada sem maquina valida devolve vazio, igual a inexistente
          and exists (select 1 from public.ativacoes a
                       where a.licenca_id = l.id
                         and a.maquina = public.dumtech_normalizar(p_maquina, 64))
    ), '');
$$;

revoke execute on function public.dumtech_licenca_marca(text, text) from public, anon, authenticated;

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
        'tamanho', coalesce(v_atual.tamanho, 0),
        'licenca', public.dumtech_licenca_marca(p_chave, p_maquina));
end;
$$;

revoke execute on function public.dumtech_hub_versao(text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.dumtech_hub_versao(text, text, text, text) to anon, authenticated;
