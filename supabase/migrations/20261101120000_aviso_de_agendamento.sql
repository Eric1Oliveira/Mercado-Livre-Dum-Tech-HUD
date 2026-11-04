-- =============================================================================
-- O dono fica sabendo do agendamento com o Hub fechado.
--
-- A reserva feita pelo link esperava no servidor ate o Hub abrir: quem deixava o
-- computador desligado so descobria no dia seguinte. Agora ela chega de dois
-- jeitos que nao dependem dele:
--
--   1. um e-mail, pedido pela Edge Function `avisar-reserva`;
--   2. o app do celular, que passa a ler as reservas direto daqui.
--
-- O servidor continua guardando so o necessario: quando o Hub importa, a reserva
-- vira 'entregue' e os dados pessoais somem, como antes.
-- =============================================================================

alter table public.agenda_reservas add column if not exists avisada_em timestamptz;

comment on column public.agenda_reservas.avisada_em is
    'Quando o dono foi avisado por e-mail. Trava o aviso: cada reserva gera um so.';

-- ---------------------------------------------------- o aviso por e-mail ---
/** Marca a reserva como avisada e devolve o que o e-mail precisa dizer.
 *
 * So a Edge Function chama, com a chave de servico. Reserva velha nao avisa: o
 * id circula no navegador de quem marcou, e nao pode virar um disparador. */
create or replace function public.dumtech_agenda_aviso(p_reserva uuid)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
    v_reserva public.agenda_reservas;
    v_link    public.agenda_links;
    v_email   text;
begin
    update public.agenda_reservas
       set avisada_em = now()
     where id = p_reserva
       and avisada_em is null
       and situacao = 'nova'
       and criado_em > now() - interval '1 hour'
    returning * into v_reserva;
    if not found then
        return jsonb_build_object('ok', false);
    end if;

    select * into v_link from public.agenda_links where id = v_reserva.link_id;
    select c.email into v_email
      from public.licencas l
      join public.clientes c on c.id = l.cliente_id
     where l.id = v_link.licenca_id;
    if coalesce(v_email, '') = '' then
        return jsonb_build_object('ok', false);
    end if;

    return jsonb_build_object(
        'ok', true,
        'email', v_email,
        'empresa', coalesce(v_link.config#>>'{empresa,nome}', ''),
        'servico', v_reserva.servico,
        'inicio', to_char(v_reserva.inicio, 'YYYY-MM-DD"T"HH24:MI'),
        'nome', v_reserva.nome,
        'telefone', v_reserva.telefone);
end;
$$;

revoke execute on function public.dumtech_agenda_aviso(uuid) from public, anon, authenticated;

-- ----------------------------------------------------------- o celular ---
/** O mesmo de antes, mais as reservas que o Hub ainda nao buscou. */
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
        -- so nome e servico: o telefone do cliente segue viajando so no e-mail
        'reservas', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'servico', r.servico, 'nome', r.nome,
                       'inicio', to_char(r.inicio, 'YYYY-MM-DD"T"HH24:MI')) order by r.inicio)
              from public.agenda_reservas r
              join public.agenda_links l on l.id = r.link_id
             where l.licenca_id = v.licenca_id and r.situacao = 'nova'), '[]'::jsonb),
        'agora', now());
end;
$$;

revoke execute on function public.dumtech_celular_dados(text) from public, authenticated;
grant  execute on function public.dumtech_celular_dados(text) to anon;

notify pgrst, 'reload schema';
