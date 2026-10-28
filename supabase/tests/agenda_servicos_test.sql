-- =============================================================================
-- Teste da migration 20261027120000: cada servico no tempo dele.
-- Roda numa transacao e desfaz tudo no fim.
-- =============================================================================

begin;

do $$
declare
    v_cliente  uuid;
    v_chave    text;
    v_licenca  uuid;
    v_maquina  constant text := 'AAAA-BBBB-CCCC-SERV';
    v_pc       constant text := repeat('c', 32);
    v_config   jsonb;
    v_novo     jsonb;
    v_d        text;
    v_slug     text;
    v_horarios jsonb;
    r          jsonb;
begin
    -- ------------------------------------------------- uma barbearia com Agenda
    insert into public.clientes (nome, email) values ('Barbearia ZZ', 'zz.servicos@teste.local')
    returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['AGENDA']);
    select id into v_licenca from public.licencas where chave = v_chave;
    perform public.dumtech_ativar_licenca(v_chave, v_maquina, 'balcao');
    update public.ativacoes set computador = v_pc where licenca_id = v_licenca;

    -- todos os dias 09-12 e 13-18. Configuracao de Hub antigo: o "Horarios a
    -- cada" do link (30) e nenhum tempo proprio nos servicos
    v_config := jsonb_build_object(
        'v', 1,
        'empresa', jsonb_build_object('nome', 'Barbearia ZZ', 'endereco', '', 'whatsapp', '', 'logo', ''),
        'mensagem', '',
        'cor', 'grafite',
        'servicos', jsonb_build_array(
            jsonb_build_object('id', 's1', 'nome', 'Barba', 'duracao', 15, 'preco', null),
            jsonb_build_object('id', 's2', 'nome', 'Corte', 'duracao', 30, 'preco', null),
            jsonb_build_object('id', 's3', 'nome', 'Corte e barba', 'duracao', 60, 'preco', null)),
        'semana', (select jsonb_agg('[[540, 720], [780, 1080]]'::jsonb) from generate_series(1, 7)),
        'passo', 30, 'vagas', 1, 'antecedencia', 0, 'dias', 30, 'cancelar_ate', 180);
    r := public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true, v_config, 'Barbearia ZZ');
    assert (r->>'ok')::boolean, 'link recusado: ' || r::text;
    v_slug := r->>'slug';
    v_d := to_char(public.dumtech_agenda_agora(-180)::date + 2, 'YYYY-MM-DD');

    -- ------------------------------------- 1. Hub antigo: o curto anda no tempo dele
    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's1')->'dias') d where d->>'data' = v_d;
    -- 15 min: 09:00-11:45 (12) e 13:00-17:45 (20)
    assert jsonb_array_length(v_horarios) = 32, 'barba de 15 em 15: ' || v_horarios::text;
    assert v_horarios->>0 = '09:00' and v_horarios->>1 = '09:15' and v_horarios->>3 = '09:45'
       and v_horarios ? '11:45' and not v_horarios ? '12:00',
        'barba fora do tempo dela: ' || v_horarios::text;

    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's2')->'dias') d where d->>'data' = v_d;
    assert jsonb_array_length(v_horarios) = 16 and not v_horarios ? '09:15',
        'o corte de 30 continua de 30 em 30: ' || v_horarios::text;

    -- o longo nao fica mais espacado do que o link mandava (30, nao 60)
    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's3')->'dias') d where d->>'data' = v_d;
    assert jsonb_array_length(v_horarios) = 14 and v_horarios ? '09:30',
        'corte e barba mudou sem ninguem pedir: ' || v_horarios::text;
    raise notice '1. Hub antigo ...................... ok';

    -- --------------------------------------- 2. Hub novo: o dono escolhe por servico
    v_novo := jsonb_set(jsonb_set(v_config, '{servicos,0,passo}', '30'), '{servicos,2,passo}', '60');
    r := public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true, v_novo, '');
    assert (r->>'ok')::boolean, 'passo por servico recusado: ' || r::text;

    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's1')->'dias') d where d->>'data' = v_d;
    assert jsonb_array_length(v_horarios) = 16 and not v_horarios ? '09:15',
        'a barba devia seguir o escolhido (30): ' || v_horarios::text;

    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's3')->'dias') d where d->>'data' = v_d;
    -- de hora em hora: 09, 10, 11 e 13 a 17
    assert jsonb_array_length(v_horarios) = 8 and v_horarios ? '10:00' and not v_horarios ? '09:30',
        'corte e barba devia ir de hora em hora: ' || v_horarios::text;

    -- quem nao escolheu continua na regra de antes
    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's2')->'dias') d where d->>'data' = v_d;
    assert jsonb_array_length(v_horarios) = 16, 'corte sem escolha: ' || v_horarios::text;

    -- passo fora da lista nao entra
    r := public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true,
                                      jsonb_set(v_config, '{servicos,0,passo}', '7'), '');
    assert r->>'erro' = 'config_invalida', 'aceitou passo de 7 min: ' || r::text;
    r := public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true,
                                      jsonb_set(v_config, '{servicos,0,passo}', '"x"'), '');
    assert r->>'erro' = 'config_invalida', 'aceitou passo que nao e numero: ' || r::text;
    raise notice '2. Hub novo ........................ ok';

    -- ------------------------------------------ 3. a reserva confere o mesmo passo
    perform public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true, v_config, '');
    r := public.dumtech_agenda_reservar(v_slug, 's1', v_d || 'T09:15', 'Joao Barba', '11911110001');
    assert (r->>'ok')::boolean, 'barba das 09:15 recusada: ' || r::text;
    r := public.dumtech_agenda_reservar(v_slug, 's3', v_d || 'T09:45', 'Joao Corte', '11911110002');
    assert r->>'erro' = 'ocupado', 'corte e barba fora do passo dele: ' || r::text;

    -- corte e barba trava 10:00-11:00; a barba aparece de 15 em 15 em volta
    r := public.dumtech_agenda_reservar(v_slug, 's3', v_d || 'T10:00', 'Joao Corte', '11911110002');
    assert (r->>'ok')::boolean, 'corte e barba das 10:00 recusado: ' || r::text;
    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's1')->'dias') d where d->>'data' = v_d;
    assert v_horarios ? '09:00' and v_horarios ? '09:30' and v_horarios ? '09:45'
       and v_horarios ? '11:00' and v_horarios ? '11:15',
        'escondeu barba livre: ' || v_horarios::text;
    assert not v_horarios ? '09:15' and not v_horarios ? '10:00' and not v_horarios ? '10:45',
        'vendeu barba em horario ocupado: ' || v_horarios::text;
    raise notice '3. reservar ........................ ok';

    -- ------------------------------------------------------ 4. permissoes
    assert not has_function_privilege('anon', 'public.dumtech_agenda_livres(uuid, integer, integer, date, date)', 'execute');
    assert not has_function_privilege('anon', 'public.dumtech_agenda_passo(jsonb, jsonb)', 'execute');
    assert has_function_privilege('anon', 'public.dumtech_agenda_horarios(text, text)', 'execute');
    assert has_function_privilege('anon', 'public.dumtech_agenda_reservar(text, text, text, text, text, text, text)', 'execute');
    raise notice '4. permissoes ...................... ok';

    raise notice 'TUDO CERTO - nada foi gravado (rollback no fim do arquivo).';
end;
$$;

rollback;
