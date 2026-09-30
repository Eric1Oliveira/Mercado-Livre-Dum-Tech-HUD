-- =============================================================================
-- O computador da licenca assinada deixa de ser escolhido por quem pede.
--
-- O QUE FOI ENCONTRADO (pentest de 17/09/2026)
--   `licenca-assinada` assinava a licenca para o `computador` que vinha NO
--   PEDIDO. O license.json do cliente traz a chave e a maquina - entao quem
--   copiasse esse arquivo podia pedir uma licenca assinada para o computador
--   DELE e abrir todos os modulos. O limite de computadores do plano nao valia
--   nada: bastava um arquivo.
--
-- O CONSERTO (primeiro que chegar, fica)
--   A ativacao passa a guardar o computador. A primeira assinatura prende o
--   valor; depois disso, pedido com outro computador e recusado. Quem troca de
--   maquina (ou reinstala o Windows) ATIVA de novo - e ativar solta a marca,
--   porque ativar e o ato explicito de dizer "este computador e meu agora".
--
-- Vale para as duas assinaturas: a da licenca e a da chave Pix.
-- =============================================================================

alter table public.ativacoes add column if not exists computador text not null default '';

comment on column public.ativacoes.computador is
    'Identidade do Windows (MachineGuid embaralhado) que esta ativacao usa. '
    'Preso na primeira assinatura; ativar de novo solta.';

-- ------------------------------------------------------------- a pecinha ----
-- Primeiro que chegar, fica: prende na primeira vez e confere nas seguintes.
create or replace function public.dumtech_prender_computador(
    p_licenca uuid,
    p_maquina text,
    p_computador text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_atual text;
begin
    if coalesce(p_computador, '') !~ '^[0-9a-f]{32}$' then
        return false;
    end if;

    select computador into v_atual
      from public.ativacoes
     where licenca_id = p_licenca and maquina = public.dumtech_normalizar(p_maquina, 64)
       for update;
    if not found then
        return false;            -- computador nao ativado com esta chave
    end if;

    if coalesce(v_atual, '') = '' then
        update public.ativacoes
           set computador = p_computador
         where licenca_id = p_licenca and maquina = public.dumtech_normalizar(p_maquina, 64);
        return true;
    end if;
    return v_atual = p_computador;
end;
$$;

-- --------------------------------------------- ativar solta a marca ---------
-- Reinstalou o Windows? O MachineGuid muda. Ativar de novo (o cliente digita a
-- chave) libera a nova identidade - e continua valendo o limite do plano.
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
                    'Esta licenca ja esta ativada em %s computador(es), o maximo do plano. '
                    || 'Desative em outro computador ou fale com a DumTech.',
                    v_licenca.max_computadores));
        end if;
        insert into public.ativacoes (licenca_id, maquina, apelido)
        values (v_licenca.id, p_maquina, p_apelido);
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

-- ------------------------------------- a licenca assinada agora confere ------
drop function if exists public.dumtech_licenca_para_assinar(text, text, text);

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

    -- o Hub antigo nao manda computador: continua funcionando como antes
    if coalesce(p_computador, '') <> '' then
        select id into v_licenca from public.licencas
         where chave = public.dumtech_normalizar(p_chave, 32);
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

    return v_resposta;
end;
$$;

-- ------------------------------- a chave Pix assinada tambem se prende -------
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

-- A partir daqui, as funcoes de pagamento conferem o computador tambem: quem
-- copia o license.json nao consegue nem ver, nem trocar a chave Pix da loja.
create or replace function public.dumtech_pag_licenca_do_computador(
    p_chave text, p_maquina text, p_computador text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca uuid;
begin
    v_licenca := public.dumtech_pag_licenca(p_chave, p_maquina);
    if v_licenca is null then
        return null;
    end if;
    if not public.dumtech_prender_computador(v_licenca, p_maquina, p_computador) then
        return null;   -- outro computador: responde igual a "nao autorizado"
    end if;
    return v_licenca;
end;
$$;

-- As quatro portas de Pagamentos passam a exigir o computador certo. O corpo e
-- o mesmo de 20260916120000; so troca quem responde "de quem e esta licenca".
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

    v_licenca := public.dumtech_pag_licenca_do_computador(p_chave, p_maquina, p_computador);
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
    v_licenca := public.dumtech_pag_licenca_do_computador(p_chave, p_maquina, p_computador);
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
    v_licenca := public.dumtech_pag_licenca_do_computador(p_chave, p_maquina, p_computador);
    if v_licenca is null then
        return public.dumtech_pag_recusa();
    end if;
    if not public.dumtech_pag_sessao_valida(v_licenca, p_maquina, p_computador, p_sessao) then
        return jsonb_build_object('ok', false, 'erro', 'sessao_vencida',
            'mensagem', 'O acesso a Pagamentos venceu. Entre de novo com um codigo.');
    end if;
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

-- `atual` ganha o computador: e ele que vai dentro da chave Pix assinada
drop function if exists public.dumtech_pagamentos_atual(text, text, text);

create or replace function public.dumtech_pagamentos_atual(
    p_chave      text,
    p_maquina    text,
    p_computador text default '',
    p_ip         text default ''
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
    v_licenca := public.dumtech_pag_licenca_do_computador(p_chave, p_maquina, p_computador);
    if v_licenca is null then
        return public.dumtech_pag_recusa();
    end if;
    select pix_chave into v_pix from public.pagamento_config where licenca_id = v_licenca;
    return jsonb_build_object('ok', true, 'pix_chave', coalesce(v_pix, ''));
end;
$$;

-- =========================================================== PERMISSOES ======
do $$
declare
    v_assinatura text;
begin
    foreach v_assinatura in array array[
        'public.dumtech_prender_computador(uuid, text, text)',
        'public.dumtech_pag_licenca_do_computador(text, text, text)',
        'public.dumtech_licenca_para_assinar(text, text, text, text)',
        'public.dumtech_pagamentos_pedir_codigo(text, text, text, text)',
        'public.dumtech_pagamentos_entrar(text, text, text, text, text)',
        'public.dumtech_pagamentos_salvar(text, text, text, text, text)',
        'public.dumtech_pagamentos_atual(text, text, text, text)'
    ] loop
        execute format('revoke execute on function %s from public, anon, authenticated', v_assinatura);
        execute format('grant execute on function %s to service_role', v_assinatura);
    end loop;
end;
$$;

revoke execute on function public.dumtech_ativar_licenca(text, text, text) from public;
grant execute on function public.dumtech_ativar_licenca(text, text, text) to anon, authenticated;
