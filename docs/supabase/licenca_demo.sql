-- =============================================================================
-- Licenca de DEMONSTRACAO - para testar a ativacao nos seus computadores.
--
-- Cria (ou renova) o cliente "DumTech (demonstracao)" com a chave
-- DEMO-2026-TEST-0001, liberando TODOS os produtos a venda em ate 3
-- computadores, por um ano.
--
-- Nao existe nenhuma regra especial para a demonstracao: ela e emitida pelo
-- mesmo caminho de uma venda de verdade (dumtech_emitir_licenca), so que com
-- tipo 'teste' e uma chave fixa, para caber na documentacao e nos testes.
--
-- Pode rodar quantas vezes quiser: a segunda execucao renova o prazo e libera
-- os produtos que tiverem entrado no catalogo desde a primeira.
-- =============================================================================

do $$
declare
    v_cliente  uuid;
    v_licenca  uuid;
    v_chave    text := 'DEMO-2026-TEST-0001';
    v_prazo    date := current_date + 365;
    v_produtos text[];
begin
    select array_agg(codigo order by codigo) into v_produtos
      from public.produtos where ativo;

    select id into v_cliente from public.clientes where email = 'demo@dumtech.local';
    if not found then
        insert into public.clientes (nome, email, observacoes)
        values ('DumTech (demonstracao)', 'demo@dumtech.local', 'Cliente interno de teste')
        returning id into v_cliente;
    end if;

    select id into v_licenca from public.licencas where chave = v_chave;
    if not found then
        select licenca_id into v_licenca
          from public.dumtech_emitir_licenca(
                p_cliente_id       => v_cliente,
                p_produtos         => v_produtos,
                p_tipo             => 'teste',
                p_expira_em        => v_prazo,
                p_max_computadores => 3,
                p_observacoes      => 'Licenca de teste interna',
                p_chave            => v_chave);
        raise notice 'Licenca de demonstracao criada: %', v_chave;
    else
        update public.licencas
           set tipo = 'teste', expira_em = v_prazo, max_computadores = 3, status = 'ativa'
         where id = v_licenca;
        perform public.dumtech_liberar_produtos(v_licenca, v_produtos);
        raise notice 'Licenca de demonstracao renovada: %', v_chave;
    end if;

    raise notice 'Vence em % e libera % produto(s) em 3 computadores.',
        to_char(v_prazo, 'DD/MM/YYYY'), coalesce(array_length(v_produtos, 1), 0);
end;
$$;

-- confira o resultado
select chave, cliente, tipo, situacao, expira_em, computadores_ativos, max_computadores, produtos
  from public.licencas_resumo
 where chave = 'DEMO-2026-TEST-0001';

-- ---------------------------------------------------------------------------
-- Para apagar a demonstracao depois:
-- delete from public.licencas where chave = 'DEMO-2026-TEST-0001';
-- delete from public.clientes where email = 'demo@dumtech.local';
