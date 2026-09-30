-- ============================================================================
-- O limite de tentativas de ativacao nao contava as FALHAS
--
-- Achado numa auditoria: 142 tentativas seguidas com chave inventada, do mesmo
-- IP, contra um teto de 120/hora. Nenhuma bloqueada, e `limites_de_taxa` nao
-- ganhou uma linha sequer.
--
-- A CAUSA
--   O corpo desta funcao e um bloco unico com EXCEPTION. Em PL/pgSQL, bloco
--   com EXCEPTION roda dentro de uma SUBTRANSACAO. Chave inexistente faz
--   `dumtech_licenca_valida` levantar excecao, a subtransacao da rollback - e
--   o rollback desfaz o INSERT que o limitador acabara de fazer no topo do
--   MESMO bloco.
--
--   O insert em `licenca_tentativas` sobrevivia porque acontece depois, ja
--   dentro do handler. Dai o sintoma: 142 tentativas registradas, zero
--   contagem de limite. As duas gravacoes estao em lados opostos do rollback.
--
--   Ou seja: so ativacao BEM-SUCEDIDA contava para o teto. A falha - que e
--   exatamente o que se quer limitar - era invisivel.
--
-- A CORRECAO
--   Contar de novo dentro do handler. A chamada do topo continua sendo quem
--   BLOQUEIA; a de baixo e quem deixa a marca para a proxima tentativa.
--
-- O corpo abaixo e o de 20260917170000 sem nenhuma outra alteracao.
-- Roda duas vezes sem estrago (create or replace).
-- ============================================================================

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
            -- A CORRECAO: a contagem feita no topo foi desfeita pelo rollback
            -- da subtransacao deste bloco EXCEPTION. Conta de novo aqui, que e
            -- depois do rollback e portanto persiste.
            perform public.dumtech_dentro_do_limite(
                'licenca_ip', public.dumtech_ip_do_pedido(), 120, interval '1 hour');
            insert into public.licenca_tentativas (chave, maquina, erro)
            values (p_chave, p_maquina, split_part(v_texto, '|', 1));
            return jsonb_build_object('ok', false,
                                      'erro', split_part(v_texto, '|', 1),
                                      'mensagem', split_part(v_texto, '|', 2));
        end if;
        raise;
end;
$$;

notify pgrst, 'reload schema';
