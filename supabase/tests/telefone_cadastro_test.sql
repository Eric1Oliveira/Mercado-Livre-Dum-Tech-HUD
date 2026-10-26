-- =============================================================================
-- Teste da migration 20261026120000: telefone no primeiro acesso do Hub.
-- Roda numa transacao e desfaz tudo no fim.
-- =============================================================================

begin;

do $$
declare
    r jsonb;
begin
    -- uma funcao so: o Hub antigo (nome e e-mail) e o novo caem na mesma
    assert (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public' and p.proname = 'dumtech_identificar_cliente') = 1,
        'sobrou mais de uma dumtech_identificar_cliente';

    -- Hub antigo: sem telefone, igual a antes
    r := public.dumtech_identificar_cliente('ZZ Antigo', 'zz.antigo@teste.local');
    assert (r->>'ok')::boolean, 'Hub antigo recusado: ' || r::text;
    assert (select telefone from public.clientes where email = 'zz.antigo@teste.local') = '';

    -- Hub novo: o telefone chega so com os digitos
    r := public.dumtech_identificar_cliente('ZZ Novo', 'zz.novo@teste.local', '(63) 99999-0000');
    assert (r->>'ok')::boolean, 'cadastro com telefone recusado: ' || r::text;
    assert (select telefone from public.clientes where email = 'zz.novo@teste.local') = '63999990000',
        'telefone nao gravado';

    -- quem ja existia sem telefone ganha o telefone; o nome continua o de antes
    r := public.dumtech_identificar_cliente('Outro Nome', 'zz.antigo@teste.local', '11987654321');
    assert r = '{"ok": true}'::jsonb, 'a resposta nao pode dizer se o e-mail existia: ' || r::text;
    assert (select telefone from public.clientes where email = 'zz.antigo@teste.local') = '11987654321',
        'telefone vazio deveria ser preenchido';
    assert (select nome from public.clientes where email = 'zz.antigo@teste.local') = 'ZZ Antigo',
        'o nome cadastrado nao pode mudar';

    -- telefone que ja existe nunca e trocado
    perform public.dumtech_identificar_cliente('ZZ', 'zz.novo@teste.local', '21900000000');
    assert (select telefone from public.clientes where email = 'zz.novo@teste.local') = '63999990000',
        'trocou um telefone ja cadastrado';

    -- a chave anon chama a versao nova
    assert has_function_privilege('anon', 'public.dumtech_identificar_cliente(text, text, text)', 'execute'),
        'anon sem permissao na funcao nova';
    raise notice 'TUDO CERTO - nada foi gravado (rollback no fim do arquivo).';
end;
$$;

rollback;
