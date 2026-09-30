-- =============================================================================
-- Teste da migration 20260913150000: checkout direto (InfinitePay).
--
-- Roda dentro de uma transacao e desfaz tudo no fim: pode ser colado no SQL
-- Editor do Supabase, mesmo em producao.
-- =============================================================================

begin;

set local role service_role;

-- ======================================== 1. COMPRA NOVA, DO LINK A CHAVE ===
do $$
declare
    v_pedido   uuid;
    v_hash     text := repeat('a', 64);
    v_resposta jsonb;
    v_situacao jsonb;
begin
    v_pedido := (public.dumtech_registrar_pedido('ZZ Checkout', 'zz.checkout@teste.local', '11999990000',
                                                 array['ESTOQUE', 'VENDAS'])->>'pedido')::uuid;

    v_resposta := public.dumtech_checkout_preparar(v_pedido);
    assert (v_resposta->>'ok')::boolean, 'pedido novo deveria poder virar link: ' || v_resposta;
    assert (v_resposta->>'total_centavos')::integer = round((v_resposta->>'total')::numeric * 100),
        'centavos diferentes do total';

    assert (public.dumtech_checkout_registrar(v_pedido, v_hash, 'https://checkout.infinitepay.io/x')->>'ok')::boolean,
        'nao registrou o link';
    -- quem so sabe o numero do pedido nao troca o segredo
    assert not (public.dumtech_checkout_registrar(v_pedido, repeat('b', 64), 'https://golpe.io')->>'ok')::boolean,
        'deixou trocar o segredo de um checkout ja criado';
    assert (public.dumtech_checkout_preparar(v_pedido)->>'erro') = 'checkout_ja_criado', 'preparou duas vezes';

    -- antes de pagar: segredo errado nao ve nada, o certo ve "aguardando"
    assert (public.dumtech_checkout_situacao(v_pedido, repeat('b', 64))->>'ok')::boolean is false,
        'segredo errado abriu o pedido';
    v_situacao := public.dumtech_checkout_situacao(v_pedido, v_hash);
    assert v_situacao->>'pagamento' = 'aguardando' and not (v_situacao->>'entregue')::boolean,
        'situacao antes de pagar errada: ' || v_situacao;

    -- valor menor que o pedido: recusado, nada muda
    v_resposta := public.dumtech_checkout_confirmar(v_pedido, 100, 'tx-zz-1');
    assert v_resposta->>'erro' = 'valor_menor', 'aceitou pagamento menor: ' || v_resposta;
    assert (select pagamento from public.pedidos_site where id = v_pedido) = 'aguardando', 'valor menor mudou o pedido';

    -- pago de verdade (paid_amount com juros do parcelado pode ser maior)
    v_resposta := public.dumtech_checkout_confirmar(
        v_pedido, round((select total from public.pedidos_site where id = v_pedido) * 100)::integer + 350,
        'tx-zz-1', 'fatura-zz', 'pix', 'https://recibo.infinitepay.io/1');
    assert (v_resposta->>'entregue')::boolean, 'pagou e nao entregou: ' || v_resposta;

    v_situacao := public.dumtech_checkout_situacao(v_pedido, v_hash);
    assert (v_situacao->>'entregue')::boolean and (v_situacao->>'licenca_nova')::boolean, 'situacao pos-pagamento: ' || v_situacao;
    assert v_situacao->>'chave' ~ '^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', 'a chave nova nao apareceu';
    assert (select count(*) from public.licenca_produtos lp join public.licencas l on l.id = lp.licenca_id
             where l.chave = v_situacao->>'chave') = 2, 'os dois modulos nao entraram';
    assert not exists (select 1 from public.pedidos_abertos where pedido_id = v_pedido), 'pedido pago continua aberto';

    -- webhook repetido: nao entrega de novo
    v_resposta := public.dumtech_checkout_confirmar(v_pedido, 99999999, 'tx-zz-1');
    assert (v_resposta->>'ja_estava_pago')::boolean, 'confirmar duas vezes nao foi idempotente';
    assert (select count(*) from public.licencas l join public.clientes c on c.id = l.cliente_id
             where c.email = 'zz.checkout@teste.local') = 1, 'nasceu segunda licenca';
    raise notice '1. link, pagamento e chave ............ ok';

    -- a chave por e-mail: reserva uma vez so, e so de pedido pago e entregue
    v_resposta := public.dumtech_checkout_reservar_email(v_pedido);
    assert (v_resposta->>'ok')::boolean, 'pedido pago nao reservou o e-mail: ' || v_resposta::text;
    assert v_resposta->>'email' = 'zz.checkout@teste.local', 'e-mail errado: ' || v_resposta::text;
    assert length(v_resposta->>'chave') > 10, 'sem chave para mandar: ' || v_resposta::text;
    assert jsonb_array_length(v_resposta->'modulos') > 0, 'modulos vazios no e-mail';
    assert not (public.dumtech_checkout_reservar_email(v_pedido)->>'ok')::boolean,
        'reservou duas vezes: dois e-mails iguais';
    -- o envio falhou: solta para tentar de novo
    perform public.dumtech_checkout_email_resultado(v_pedido, false);
    assert (public.dumtech_checkout_reservar_email(v_pedido)->>'ok')::boolean, 'falha nao soltou a reserva';
    -- mandou: nunca mais
    perform public.dumtech_checkout_email_resultado(v_pedido, true);
    assert not (public.dumtech_checkout_reservar_email(v_pedido)->>'ok')::boolean, 'mandou de novo depois de enviado';
    assert (select entrega ? 'email_enviado_em' from public.pedidos_site where id = v_pedido), 'envio nao ficou anotado';
    raise notice '1b. chave por e-mail uma vez so ....... ok';
end;
$$;

-- ============================== 2. E-MAIL DE CLIENTE ANTIGO NAO VE A CHAVE ===
do $$
declare
    v_cliente  uuid;
    v_chave    text;
    v_pedido   uuid;
    v_hash     text := repeat('c', 64);
    v_situacao jsonb;
begin
    insert into public.clientes (nome, email) values ('ZZ Antigo', 'zz.antigo@teste.local') returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['AGENDA']);

    -- um estranho digita o e-mail dele e paga
    v_pedido := (public.dumtech_registrar_pedido('Estranho', 'zz.antigo@teste.local', '', array['CLIENTES'])->>'pedido')::uuid;
    perform public.dumtech_checkout_registrar(v_pedido, v_hash, 'https://checkout.infinitepay.io/y');
    perform public.dumtech_checkout_confirmar(v_pedido, 99999999, 'tx-zz-2', '', 'credit_card');

    v_situacao := public.dumtech_checkout_situacao(v_pedido, v_hash);
    assert (v_situacao->>'entregue')::boolean, 'nao entregou na licenca do cliente';
    assert v_situacao->>'chave' is null, 'MOSTROU A CHAVE DE UM CLIENTE ANTIGO para quem digitou o e-mail dele';
    assert v_situacao->>'final_chave' = right(v_chave, 4), 'o final da chave nao confere';
    assert (select count(*) from public.licenca_produtos lp join public.licencas l on l.id = lp.licenca_id
             where l.chave = v_chave) = 2, 'o modulo comprado nao entrou na chave existente';
    raise notice '2. cliente antigo: sem vazar chave .... ok';
end;
$$;

-- ============================================ 3. O QUE NAO PODE PASSAR ======
do $$
declare
    v_pedido  uuid;
    v_outro   uuid;
    v_manual  uuid;
    v_resposta jsonb;
begin
    -- o mesmo comprovante nao paga dois pedidos
    v_pedido := (public.dumtech_registrar_pedido('ZZ Dois', 'zz.dois@teste.local', '', array['ORDENS'])->>'pedido')::uuid;
    perform public.dumtech_checkout_registrar(v_pedido, repeat('d', 64), 'https://checkout.infinitepay.io/z');
    v_resposta := public.dumtech_checkout_confirmar(v_pedido, 99999999, 'tx-zz-1');
    assert v_resposta->>'erro' = 'transacao_ja_usada', 'um comprovante pagou dois pedidos: ' || v_resposta;

    -- pedido sem checkout (fluxo antigo) nao e pago por aqui
    v_manual := (public.dumtech_registrar_pedido('ZZ Whats', 'zz.whats@teste.local', '', array['ORDENS'])->>'pedido')::uuid;
    assert public.dumtech_checkout_confirmar(v_manual, 99999999, 'tx-zz-3')->>'erro' = 'sem_checkout',
        'pagou pedido que nunca abriu checkout';

    -- pedido velho nao vira link
    update public.pedidos_site set criado_em = now() - interval '3 hours' where id = v_manual;
    assert public.dumtech_checkout_preparar(v_manual)->>'erro' = 'pedido_expirado', 'pedido velho virou link';

    -- segredo precisa ter formato de hash; url precisa ser https
    v_outro := (public.dumtech_registrar_pedido('ZZ Tres', 'zz.tres@teste.local', '', array['ORDENS'])->>'pedido')::uuid;
    assert public.dumtech_checkout_registrar(v_outro, 'curto', 'https://x.io')->>'erro' = 'dados_invalidos', 'aceitou hash torto';
    assert public.dumtech_checkout_registrar(v_outro, repeat('e', 64), 'javascript:alert(1)')->>'erro' = 'dados_invalidos', 'aceitou url torta';

    -- pagou, mas a entrega falhou (modulo saiu de linha): o pagamento fica, o pedido segue aberto com o erro
    perform public.dumtech_checkout_registrar(v_outro, repeat('e', 64), 'https://checkout.infinitepay.io/w');
    update public.pedidos_site
       set itens = '[{"tipo":"produto","codigo":"NAO_EXISTE","nome":"Fantasma","preco":10}]'::jsonb
     where id = v_outro;
    v_resposta := public.dumtech_checkout_confirmar(v_outro, 99999999, 'tx-zz-4', '', 'pix');
    assert (v_resposta->>'ok')::boolean and not (v_resposta->>'entregue')::boolean, 'falha na entrega: ' || v_resposta;
    assert (select pagamento = 'pago' and entrega_erro is not null from public.pedidos_abertos where pedido_id = v_outro),
        'pedido pago com entrega falha precisa aparecer no painel com o erro';
    raise notice '3. recusas e entrega que falhou ....... ok';
end;
$$;

-- ================================================ 4. SO O SERVICE_ROLE ======
reset role;
do $$
declare
    v_funcao text;
begin
    foreach v_funcao in array array[
        'public.dumtech_checkout_preparar(uuid)',
        'public.dumtech_checkout_registrar(uuid, text, text)',
        'public.dumtech_checkout_confirmar(uuid, integer, text, text, text, text)',
        'public.dumtech_checkout_situacao(uuid, text)',
        'public.dumtech_checkout_reservar_email(uuid)',
        'public.dumtech_checkout_email_resultado(uuid, boolean)'] loop
        assert not has_function_privilege('anon', v_funcao, 'execute'), 'anon executa ' || v_funcao;
        assert not has_function_privilege('authenticated', v_funcao, 'execute'), 'authenticated executa ' || v_funcao;
        assert has_function_privilege('service_role', v_funcao, 'execute'), 'service_role nao executa ' || v_funcao;
    end loop;
    raise notice '4. so a Edge Function chama ........... ok';
end;
$$;

rollback;
