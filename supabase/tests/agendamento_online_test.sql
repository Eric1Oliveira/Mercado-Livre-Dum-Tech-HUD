-- =============================================================================
-- Teste da migration 20261026130000: agendamento online (o link da Agenda).
-- Roda numa transacao e desfaz tudo no fim.
-- =============================================================================

begin;

do $$
declare
    v_cliente  uuid;
    v_chave    text;
    v_licenca  uuid;
    v_maquina  constant text := 'AAAA-BBBB-CCCC-AGEN';
    v_pc       constant text := repeat('a', 32);
    v_outra    text;
    v_config   jsonb;
    v_dia      date;
    v_d        text;
    r          jsonb;
    v_slug     text;
    v_codigo   text;
    v_reserva  uuid;
    v_horarios jsonb;
begin
    -- ---------------------------------------------------- uma loja com Agenda
    insert into public.clientes (nome, email) values ('Beauty ZZ', 'zz.agenda@teste.local')
    returning id into v_cliente;
    select chave into v_chave from public.dumtech_emitir_licenca(v_cliente, array['AGENDA']);
    select id into v_licenca from public.licencas where chave = v_chave;
    perform public.dumtech_ativar_licenca(v_chave, v_maquina, 'balcao');
    update public.ativacoes set computador = v_pc where licenca_id = v_licenca;

    -- todos os dias abertos 09-12 e 13-18: o teste nao depende do dia da semana
    v_config := jsonb_build_object(
        'v', 1,
        'empresa', jsonb_build_object('nome', 'Beauty & Cia', 'endereco', 'Rua das Flores, 120',
                                      'whatsapp', '5511987654321', 'logo', ''),
        'mensagem', 'Chegue 5 minutos antes',
        'cor', 'rosa',
        'servicos', jsonb_build_array(
            jsonb_build_object('id', 's1', 'nome', 'Corte', 'duracao', 60, 'preco', 60),
            jsonb_build_object('id', 's2', 'nome', 'Escova', 'duracao', 30, 'preco', null)),
        'semana', (select jsonb_agg('[[540, 720], [780, 1080]]'::jsonb) from generate_series(1, 7)),
        'passo', 30, 'vagas', 1, 'antecedencia', 0, 'dias', 30, 'cancelar_ate', 180);

    -- ------------------------------------------------------------ 1. salvar
    -- licenca sem a Agenda nao cria link
    insert into public.clientes (nome, email) values ('Mercado ZZ', 'zz.semagenda@teste.local')
    returning id into v_cliente;
    select chave into v_outra from public.dumtech_emitir_licenca(v_cliente, array['VENDAS']);
    perform public.dumtech_ativar_licenca(v_outra, 'AAAA-BBBB-CCCC-SEMA', 'caixa');
    r := public.dumtech_agenda_salvar(v_outra, 'AAAA-BBBB-CCCC-SEMA', '', true, v_config, 'Mercado ZZ');
    assert r->>'erro' = 'sem_agenda', 'licenca sem Agenda criou link: ' || r::text;

    -- outro computador (license.json copiado) nao mexe no link
    r := public.dumtech_agenda_salvar(v_chave, v_maquina, repeat('b', 32), true, v_config, 'Beauty & Cia');
    assert r->>'erro' = 'licenca_invalida', 'outro computador salvou: ' || r::text;

    -- configuracao torta nao entra
    r := public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true,
                                      v_config || '{"vagas": 0}'::jsonb, 'Beauty & Cia');
    assert r->>'erro' = 'config_invalida', 'aceitou vagas = 0: ' || r::text;
    r := public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true,
                                      jsonb_set(v_config, '{empresa,logo}', '"javascript:alert(1)"'), 'X');
    assert r->>'erro' = 'config_invalida', 'aceitou logo que nao e imagem: ' || r::text;
    r := public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true,
                                      v_config - 'semana', 'X');
    assert r->>'erro' = 'config_invalida', 'aceitou sem horario de atendimento: ' || r::text;

    r := public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true, v_config, 'Beauty & Cia');
    assert (r->>'ok')::boolean, 'link recusado: ' || r::text;
    v_slug := r->>'slug';
    assert v_slug = 'beauty-cia', 'slug inesperado: ' || v_slug;

    -- outra loja com o mesmo nome ganha sufixo
    insert into public.clientes (nome, email) values ('Beauty Dois', 'zz.agenda2@teste.local')
    returning id into v_cliente;
    select chave into v_outra from public.dumtech_emitir_licenca(v_cliente, array['AGENDA']);
    perform public.dumtech_ativar_licenca(v_outra, 'AAAA-BBBB-CCCC-DOIS', 'caixa');
    r := public.dumtech_agenda_salvar(v_outra, 'AAAA-BBBB-CCCC-DOIS', '', true, v_config, 'beauty cia');
    assert r->>'slug' ~ '^beauty-cia-[0-9a-f]{4}$', 'duas lojas no mesmo endereco: ' || r::text;

    -- salvar de novo nao troca o endereco; "gerar endereco novo" troca
    r := public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true, v_config, 'Outro Nome');
    assert r->>'slug' = v_slug, 'o endereco mudou sozinho';
    r := public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true, v_config, 'Beauty & Cia', true);
    assert r->>'slug' ~ '^beauty-cia-[0-9a-f]{4}$', 'endereco novo sem sufixo: ' || r::text;
    assert public.dumtech_agenda_pagina(v_slug)->>'erro' = 'nao_encontrado', 'o endereco antigo continua valendo';
    v_slug := r->>'slug';
    raise notice '1. salvar .......................... ok';

    -- ---------------------------------------------------------- 2. pagina
    r := public.dumtech_agenda_pagina(upper(v_slug));
    assert (r->>'ok')::boolean, 'pagina recusada: ' || r::text;
    assert r#>>'{empresa,nome}' = 'Beauty & Cia' and r->>'cor' = 'rosa';
    assert jsonb_array_length(r->'servicos') = 2;
    assert r->>'hoje' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$';
    raise notice '2. pagina .......................... ok';

    -- --------------------------------------------------------- 3. horarios
    v_dia := public.dumtech_agenda_agora(-180)::date + 2;
    v_d := to_char(v_dia, 'YYYY-MM-DD');

    r := public.dumtech_agenda_horarios(v_slug, 's1');
    assert (r->>'ok')::boolean, 'horarios recusados: ' || r::text;
    assert jsonb_array_length(r->'dias') = 30, 'a janela deveria ter 30 dias';
    select d->'horarios' into v_horarios from jsonb_array_elements(r->'dias') d where d->>'data' = v_d;
    -- 60 min: 09:00-11:00 (5) e 13:00-17:00 (9)
    assert jsonb_array_length(v_horarios) = 14, 'horarios do dia: ' || v_horarios::text;
    assert v_horarios->>0 = '09:00' and not v_horarios ? '11:30' and not v_horarios ? '12:00',
        'servico de 1 h nao cabe antes do almoco: ' || v_horarios::text;

    -- o Hub publica: 10:00 ocupado (1 h) e 15:00 bloqueado (almoco tardio)
    r := public.dumtech_agenda_sincronizar(v_chave, v_maquina, v_pc,
            jsonb_build_array(jsonb_build_array(v_d || 'T10:00', 60, 0),
                              jsonb_build_array(v_d || 'T15:00', 60, 1)), -180);
    assert (r->>'ok')::boolean and (r->>'link')::boolean, 'sincronia recusada: ' || r::text;
    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's1')->'dias') d where d->>'data' = v_d;
    assert not v_horarios ? '09:30' and not v_horarios ? '10:00' and not v_horarios ? '10:30',
        'vendeu horario ocupado: ' || v_horarios::text;
    assert v_horarios ? '09:00' and v_horarios ? '11:00', 'escondeu horario livre: ' || v_horarios::text;
    assert not v_horarios ? '14:30' and not v_horarios ? '15:00' and not v_horarios ? '15:30',
        'vendeu horario bloqueado: ' || v_horarios::text;

    -- com 2 vagas o ocupado divide; o bloqueio continua fechando tudo
    perform public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true, v_config || '{"vagas": 2}', '');
    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's1')->'dias') d where d->>'data' = v_d;
    assert v_horarios ? '10:00' and not v_horarios ? '15:00', 'vagas: ' || v_horarios::text;

    -- simultaneo de verdade: 14:00-14:30 e 14:30-15:00 ocupados deixam 14:00-15:00 com 2 vagas
    perform public.dumtech_agenda_sincronizar(v_chave, v_maquina, v_pc,
            jsonb_build_array(jsonb_build_array(v_d || 'T13:00', 30, 0),
                              jsonb_build_array(v_d || 'T13:30', 30, 0)), -180);
    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's1')->'dias') d where d->>'data' = v_d;
    assert v_horarios ? '13:00', 'contou dois atendimentos em sequencia como simultaneos: ' || v_horarios::text;
    perform public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true, v_config, '');
    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's1')->'dias') d where d->>'data' = v_d;
    assert not v_horarios ? '13:00', 'com 1 vaga, 13:00 esta ocupado: ' || v_horarios::text;

    -- antecedencia: com 72 h, o dia + 2 some
    perform public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true, v_config || '{"antecedencia": 4320}', '');
    select d->'horarios' into v_horarios
      from jsonb_array_elements(public.dumtech_agenda_horarios(v_slug, 's1')->'dias') d where d->>'data' = v_d;
    assert jsonb_array_length(v_horarios) = 0, 'antecedencia ignorada: ' || v_horarios::text;
    perform public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true, v_config, '');
    perform public.dumtech_agenda_sincronizar(v_chave, v_maquina, v_pc, '[]'::jsonb, -180);

    assert public.dumtech_agenda_horarios(v_slug, 'nao-existe')->>'erro' = 'servico';
    raise notice '3. horarios ........................ ok';

    -- ---------------------------------------------------------- 4. reservar
    r := public.dumtech_agenda_reservar(v_slug, 's1', v_d || 'T09:00', 'Maria Souza', '(11) 98765-4321', 'Primeira vez');
    assert (r->>'ok')::boolean, 'reserva recusada: ' || r::text;
    assert length(r->>'codigo') = 64 and r->>'servico' = 'Corte' and r->>'fim' = v_d || 'T10:00';
    assert r->>'cancelar_ate' = v_d || 'T06:00', 'prazo de cancelar: ' || r::text;
    v_codigo := r->>'codigo';
    v_reserva := (r->>'id')::uuid;
    assert not exists (select 1 from public.agenda_reservas where codigo_hash = v_codigo),
        'o codigo de cancelar nao pode ficar em texto puro';

    -- o mesmo horario nao e vendido duas vezes (1 vaga)
    r := public.dumtech_agenda_reservar(v_slug, 's1', v_d || 'T09:00', 'Joana', '11912345678');
    assert r->>'erro' = 'ocupado', 'vendeu o horario duas vezes: ' || r::text;
    -- e encostar nele tambem nao (09:30-10:30 cruza 09:00-10:00)
    r := public.dumtech_agenda_reservar(v_slug, 's1', v_d || 'T09:30', 'Joana', '11912345678');
    assert r->>'erro' = 'ocupado', 'vendeu horario encavalado: ' || r::text;

    -- entrada ruim
    assert public.dumtech_agenda_reservar(v_slug, 's1', v_d || 'T11:00', 'J', '11912345678')->>'erro' = 'dados';
    assert public.dumtech_agenda_reservar(v_slug, 's1', v_d || 'T11:00', 'Joana', '9999-0000')->>'erro' = 'dados';
    assert public.dumtech_agenda_reservar(v_slug, 's1', v_d || ' 11h', 'Joana', '11912345678')->>'erro' = 'dados';
    assert public.dumtech_agenda_reservar(v_slug, 's1', v_d || 'T11:00', 'Joana', '11912345678', '', 'robo')->>'erro' = 'dados',
        'a armadilha deixou o robo passar';
    assert public.dumtech_agenda_reservar(v_slug, 's1', v_d || 'T11:10', 'Joana', '11912345678')->>'erro' = 'ocupado',
        'aceitou horario fora do passo';

    -- 3 horarios futuros por telefone
    perform public.dumtech_agenda_reservar(v_slug, 's2', v_d || 'T13:00', 'Joana', '11912345678');
    perform public.dumtech_agenda_reservar(v_slug, 's2', v_d || 'T14:00', 'Joana', '+55 11 91234-5678');
    perform public.dumtech_agenda_reservar(v_slug, 's2', v_d || 'T16:00', 'Joana', '11 91234 5678');
    r := public.dumtech_agenda_reservar(v_slug, 's2', v_d || 'T17:00', 'Joana', '11912345678');
    assert r->>'erro' = 'limite_telefone', 'quarto horario do mesmo telefone: ' || r::text;
    raise notice '4. reservar ........................ ok';

    -- ------------------------------------------------------ 5. sincronizar
    r := public.dumtech_agenda_sincronizar(v_chave, v_maquina, v_pc);
    assert jsonb_array_length(r->'novas') = 4, 'novas: ' || r::text;
    assert exists (select 1 from jsonb_array_elements(r->'novas') n
                    where n->>'nome' = 'Maria Souza' and n->>'telefone' = '11987654321'
                      and n->>'observacao' = 'Primeira vez' and (n->>'duracao')::int = 60
                      and n->>'inicio' = v_d || 'T09:00' and n->>'servico' = 'Corte'),
        'a reserva chegou diferente ao Hub: ' || r::text;

    -- confirmar SEM ocupados novos nao vale (a reserva sairia da conta de ocupados)
    perform public.dumtech_agenda_sincronizar(v_chave, v_maquina, v_pc, null, null, array[v_reserva]);
    assert (select situacao from public.agenda_reservas where id = v_reserva) = 'nova',
        'confirmou sem o retrato novo';

    -- com o retrato novo: entregue e sem dados pessoais
    r := public.dumtech_agenda_sincronizar(v_chave, v_maquina, v_pc,
            jsonb_build_array(jsonb_build_array(v_d || 'T09:00', 60, 0)), -180, array[v_reserva]);
    assert jsonb_array_length(r->'novas') = 3, 'a entregue voltou na fila: ' || r::text;
    assert (select situacao = 'entregue' and nome = '' and telefone = '' and observacao = ''
              from public.agenda_reservas where id = v_reserva), 'os dados pessoais ficaram no servidor';
    -- e o horario continua ocupado (agora pelo retrato do Hub)
    assert public.dumtech_agenda_reservar(v_slug, 's1', v_d || 'T09:00', 'Ana', '21988887777')->>'erro' = 'ocupado';

    -- ocupados tortos nao entram
    r := public.dumtech_agenda_sincronizar(v_chave, v_maquina, v_pc, '[["2026-02-31T10:00", 60, 0]]'::jsonb, -180);
    assert r->>'erro' = 'ocupados_invalidos', 'aceitou data que nao existe: ' || r::text;
    raise notice '5. sincronizar ..................... ok';

    -- ---------------------------------------------------------- 6. cancelar
    -- entregue: vira cancelada e o Hub fica sabendo
    r := public.dumtech_agenda_cancelar(v_codigo);
    assert (r->>'ok')::boolean, 'cancelamento recusado: ' || r::text;
    r := public.dumtech_agenda_sincronizar(v_chave, v_maquina, v_pc);
    assert r->'canceladas' ? v_reserva::text, 'o Hub nao ficou sabendo do cancelamento: ' || r::text;
    perform public.dumtech_agenda_sincronizar(v_chave, v_maquina, v_pc, null, null, '{}', array[v_reserva]);
    assert not exists (select 1 from public.agenda_reservas where id = v_reserva), 'cancelada aplicada ficou na fila';
    assert public.dumtech_agenda_cancelar(v_codigo)->>'erro' = 'nao_encontrado';

    -- nova: some da fila (o Hub nunca soube)
    r := public.dumtech_agenda_reservar(v_slug, 's2', v_d || 'T11:00', 'Bia', '31977776666');
    perform public.dumtech_agenda_cancelar(r->>'codigo');
    assert not exists (select 1 from public.agenda_reservas where id = (r->>'id')::uuid);

    -- fora do prazo (3 h): horario de daqui a 1 h
    perform public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true,
        v_config || jsonb_build_object('semana', (select jsonb_agg('[[0, 1440]]'::jsonb) from generate_series(1, 7))), '');
    r := public.dumtech_agenda_reservar(v_slug, 's2',
            to_char(date_trunc('hour', public.dumtech_agenda_agora(-180)) + interval '2 hours', 'YYYY-MM-DD"T"HH24:MI'),
            'Carla', '41966665555');
    assert (r->>'ok')::boolean, 'reserva de daqui a pouco recusada: ' || r::text;
    assert public.dumtech_agenda_cancelar(r->>'codigo')->>'erro' = 'prazo', 'cancelou fora do prazo';
    raise notice '6. cancelar ........................ ok';

    -- ------------------------------------------------ 7. pausado e vencido
    perform public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, false, v_config, '');
    r := public.dumtech_agenda_pagina(v_slug);
    assert r->>'erro' = 'indisponivel' and r#>>'{empresa,whatsapp}' = '5511987654321',
        'pausado sem o contato da empresa: ' || r::text;
    assert public.dumtech_agenda_reservar(v_slug, 's1', v_d || 'T11:00', 'Joao', '11955554444')->>'erro' = 'indisponivel';

    perform public.dumtech_agenda_salvar(v_chave, v_maquina, v_pc, true, v_config, '');
    update public.licencas set status = 'suspensa' where id = v_licenca;
    assert public.dumtech_agenda_pagina(v_slug)->>'erro' = 'indisponivel', 'licenca suspensa continua agendando';
    assert public.dumtech_agenda_sincronizar(v_chave, v_maquina, v_pc)->>'erro' is not null;
    update public.licencas set status = 'ativa' where id = v_licenca;
    raise notice '7. pausado e vencido ............... ok';

    -- --------------------------------------------------------- 8. faxina
    insert into public.agenda_reservas (link_id, servico, inicio, duracao, codigo_hash)
    select id, 'Velha', (now() at time zone 'UTC') - interval '3 days', 30, 'x'
      from public.agenda_links where slug = v_slug;
    perform public.dumtech_agenda_faxina();
    assert not exists (select 1 from public.agenda_reservas where servico = 'Velha'), 'a faxina nao apagou o passado';
    raise notice '8. faxina .......................... ok';

    -- ------------------------------------------------------ 9. permissoes
    assert not has_table_privilege('anon', 'public.agenda_links', 'select');
    assert not has_table_privilege('anon', 'public.agenda_reservas', 'select');
    assert not has_table_privilege('authenticated', 'public.agenda_reservas', 'select');
    assert not has_function_privilege('anon', 'public.dumtech_agenda_livres(uuid, integer, integer, date, date)', 'execute');
    assert not has_function_privilege('anon', 'public.dumtech_agenda_faxina()', 'execute');
    assert has_function_privilege('anon', 'public.dumtech_agenda_pagina(text)', 'execute');
    raise notice '9. permissoes ...................... ok';

    raise notice 'TUDO CERTO - nada foi gravado (rollback no fim do arquivo).';
end;
$$;

rollback;
