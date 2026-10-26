-- =============================================================================
-- Telefone no primeiro acesso do Hub.
--
-- O Hub 1.5.0 pede o telefone (WhatsApp) junto com nome e e-mail, e ele chega
-- aqui: a DumTech passa a conseguir falar com quem instalou o programa.
--
-- A funcao ganha `p_telefone` com valor padrao. A versao de 2 parametros SAI:
-- com as duas no banco, o PostgREST nao saberia qual chamar quando um Hub
-- antigo manda so nome e e-mail. Com o padrao, o Hub antigo continua igual.
--
-- Cliente que ja existe continua intocado (o cadastro comercial manda mais que
-- o digitado numa instalacao qualquer) - so o telefone VAZIO e preenchido.
-- =============================================================================

drop function if exists public.dumtech_identificar_cliente(text, text);

create or replace function public.dumtech_identificar_cliente(
    p_nome     text,
    p_email    text,
    p_telefone text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_nome     text := left(btrim(coalesce(p_nome, '')), 120);
    v_email    text := lower(left(btrim(coalesce(p_email, '')), 160));
    v_telefone text := left(regexp_replace(coalesce(p_telefone, ''), '[^0-9]', '', 'g'), 20);
begin
    if not public.dumtech_dentro_do_limite('identificar_ip', public.dumtech_ip_do_pedido(), 30, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos e tente de novo.');
    end if;

    if v_nome = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe o seu nome.');
    end if;
    if not public.dumtech_email_valido(v_email) then
        return jsonb_build_object('ok', false, 'erro', 'email_invalido',
                                  'mensagem', 'Confira o e-mail digitado.');
    end if;

    insert into public.clientes (nome, email, telefone, origem)
    select v_nome, v_email, v_telefone, 'hub'
     where not exists (select 1 from public.clientes c where lower(c.email) = v_email);

    -- quem ja existia so ganha o telefone se o dele estiver vazio
    if v_telefone <> '' then
        update public.clientes
           set telefone = v_telefone
         where lower(email) = v_email and telefone = '';
    end if;

    return jsonb_build_object('ok', true);
end;
$$;

revoke execute on function public.dumtech_identificar_cliente(text, text, text) from public;
grant  execute on function public.dumtech_identificar_cliente(text, text, text) to anon, authenticated;

notify pgrst, 'reload schema';
