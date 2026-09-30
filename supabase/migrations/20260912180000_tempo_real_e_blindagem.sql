-- =============================================================================
-- 20260912180000 - tempo real e blindagem
--
-- O QUE ENTRA
--   1. tempo real   o banco AVISA quando algo muda (Supabase Realtime, broadcast):
--                   - canal publico  "catalogo": preco/produto/combo mudou -> o
--                     site busca o catalogo de novo, sem ninguem dar refresh
--                   - canal privado  "painel": cliente, licenca, pedido... mudou
--                     -> o painel aberto se atualiza sozinho (so administrador
--                     entra neste canal)
--                   O aviso NAO carrega dado nenhum: diz so "a tabela X mudou".
--                   Quem ouve busca de novo pelo caminho de sempre (funcao ou
--                   policy), entao o tempo real nao abre porta nova.
--   2. limites      quantas vezes por hora um endereco (ou um e-mail) pode chamar
--                   as funcoes publicas que gravam alguma coisa
--   3. correcoes    aprovar pedido trava a linha (dois cliques nao emitem duas
--                   licencas); link de anuncio so https; TRUNCATE fora do alcance
--                   de anon/authenticated; indices que o painel usa
--
-- Funciona com ou sem o schema `realtime` (testes locais nao tem): sem ele o
-- aviso simplesmente nao sai, e nenhuma gravacao falha por causa disso.
-- =============================================================================

-- ============================================================ 1. LIMITES ====
create table if not exists public.limites_de_taxa (
    acao   text        not null,
    quem   text        not null,
    janela timestamptz not null,
    vezes  integer     not null default 0,
    primary key (acao, quem, janela)
);

comment on table public.limites_de_taxa is
    'Contador por janela de tempo (acao + endereco ou e-mail). Protege as funcoes '
    'publicas contra enxurrada: pedido falso, token em massa, teste de chaves.';

create index if not exists idx_limites_janela on public.limites_de_taxa (janela);

-- O endereco de quem chamou, como o Supabase repassa ao banco. Melhor esforco:
-- cf-connecting-ip (posto pela borda, o cliente nao escolhe) vem primeiro.
-- Fora do PostgREST (SQL Editor, testes) nao ha cabecalho e devolve vazio.
create or replace function public.dumtech_ip_do_pedido()
returns text
language plpgsql
stable
set search_path = ''
as $$
declare
    v_cabecalhos jsonb;
begin
    begin
        v_cabecalhos := nullif(current_setting('request.headers', true), '')::jsonb;
    exception when others then
        return '';
    end;
    return left(coalesce(
        nullif(btrim(v_cabecalhos ->> 'cf-connecting-ip'), ''),
        nullif(btrim(v_cabecalhos ->> 'x-real-ip'), ''),
        nullif(btrim(split_part(v_cabecalhos ->> 'x-forwarded-for', ',', 1)), ''),
        ''), 64);
end;
$$;

-- Conta mais uma e diz se ainda cabe. Sem `quem` (sem endereco) nao limita:
-- limitar "ninguem" seria limitar todo mundo junto.
create or replace function public.dumtech_dentro_do_limite(
    p_acao   text,
    p_quem   text,
    p_maximo integer,
    p_janela interval
)
returns boolean
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
    v_janela timestamptz := date_bin(p_janela, now(), timestamptz '2000-01-01 00:00:00+00');
    v_vezes  integer;
begin
    if coalesce(btrim(p_quem), '') = '' then
        return true;
    end if;

    insert into public.limites_de_taxa (acao, quem, janela, vezes)
    values (p_acao, left(lower(btrim(p_quem)), 200), v_janela, 1)
    on conflict (acao, quem, janela) do update
        set vezes = public.limites_de_taxa.vezes + 1
    returning vezes into v_vezes;

    -- faxina barata, de vez em quando
    if random() < 0.02 then
        delete from public.limites_de_taxa where janela < now() - interval '2 days';
    end if;

    return v_vezes <= p_maximo;
end;
$$;

-- ========================================= 2. FUNCOES PUBLICAS COM LIMITE ===
-- Mesmos nomes, parametros e respostas de antes (o Hub e o site nao mudam).
-- A unica novidade e o erro "muitas_tentativas".

-- ------------------------------------------------------ REGISTRAR PEDIDO -----
create or replace function public.dumtech_registrar_pedido(
    p_nome     text,
    p_email    text,
    p_telefone text default '',
    p_produtos text[] default '{}',
    p_combo    text default null,
    p_origem   text default 'site',
    p_observacoes text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_nome     text := left(btrim(coalesce(p_nome, '')), 120);
    v_email    text := lower(left(btrim(coalesce(p_email, '')), 160));
    v_telefone text := left(btrim(coalesce(p_telefone, '')), 40);
    v_origem   text := case when p_origem = 'hub' then 'hub' else 'site' end;
    v_combo    public.combos;
    v_produto  public.produtos;
    v_codigo   text;
    v_itens    jsonb := '[]'::jsonb;
    v_total    numeric(12, 2) := 0;
    v_cliente  uuid;
    v_pedido   uuid;
begin
    if not public.dumtech_dentro_do_limite('pedido_ip', public.dumtech_ip_do_pedido(), 12, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Recebemos muitos pedidos seguidos daqui. Espere alguns minutos e tente de novo.');
    end if;

    if v_nome = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe o seu nome.');
    end if;
    if not public.dumtech_email_valido(v_email) then
        return jsonb_build_object('ok', false, 'erro', 'email_invalido',
                                  'mensagem', 'Confira o e-mail digitado.');
    end if;

    if not public.dumtech_dentro_do_limite('pedido_email', v_email, 6, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Ja recebemos varios pedidos com este e-mail. Espere alguns minutos e tente de novo.');
    end if;

    if coalesce(btrim(p_combo), '') <> '' then
        select * into v_combo from public.combos
         where codigo = upper(btrim(p_combo)) and ativo;
        if not found then
            return jsonb_build_object('ok', false, 'erro', 'combo_invalido',
                                      'mensagem', 'Esse pacote nao esta disponivel.');
        end if;
        v_itens := v_itens || jsonb_build_object(
            'tipo', 'combo', 'codigo', v_combo.codigo, 'nome', v_combo.nome,
            'preco', v_combo.preco);
        v_total := v_total + v_combo.preco;
    end if;

    foreach v_codigo in array coalesce(p_produtos, '{}') loop
        v_codigo := upper(btrim(v_codigo));
        continue when v_codigo = '';
        select * into v_produto from public.produtos where codigo = v_codigo and ativo;
        if not found then
            return jsonb_build_object('ok', false, 'erro', 'produto_invalido',
                                      'mensagem', format('O modulo %s nao esta disponivel.', left(v_codigo, 40)));
        end if;
        -- produto que ja entrou pelo combo nao e cobrado duas vezes
        if v_combo.id is null or not exists (
            select 1 from public.combo_produtos cp
             where cp.combo_id = v_combo.id and cp.produto_id = v_produto.id
        ) then
            v_itens := v_itens || jsonb_build_object(
                'tipo', 'produto', 'codigo', v_produto.codigo, 'nome', v_produto.nome,
                'preco', v_produto.preco);
            v_total := v_total + v_produto.preco;
        end if;
    end loop;

    if jsonb_array_length(v_itens) = 0 then
        return jsonb_build_object('ok', false, 'erro', 'kit_vazio',
                                  'mensagem', 'Escolha ao menos um modulo.');
    end if;

    -- quem ja e cadastrado fica ligado ao pedido; quem nao e, entra como
    -- interessado (mesma porta do primeiro acesso do Hub)
    select id into v_cliente from public.clientes where lower(email) = v_email;
    if not found then
        insert into public.clientes (nome, email, telefone, origem)
        values (v_nome, v_email, v_telefone, 'hub')
        returning id into v_cliente;
    end if;

    insert into public.pedidos_site (cliente_id, nome, email, telefone, itens,
                                     total, origem, observacoes)
    values (v_cliente, v_nome, v_email, v_telefone, v_itens, v_total, v_origem,
            left(btrim(coalesce(p_observacoes, '')), 500))
    returning id into v_pedido;

    return jsonb_build_object('ok', true, 'pedido', v_pedido,
                              'itens', v_itens, 'total', v_total);
end;
$$;

-- --------------------------------------------- IDENTIFICAR (primeiro acesso) --
create or replace function public.dumtech_identificar_cliente(
    p_nome  text,
    p_email text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_nome  text := left(btrim(coalesce(p_nome, '')), 120);
    v_email text := lower(left(btrim(coalesce(p_email, '')), 160));
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

    -- cliente que ja existe fica intocado: o cadastro comercial manda mais que
    -- o que foi digitado numa instalacao qualquer
    insert into public.clientes (nome, email, origem)
    select v_nome, v_email, 'hub'
     where not exists (select 1 from public.clientes c where lower(c.email) = v_email);

    return jsonb_build_object('ok', true);
end;
$$;

-- ------------------------------------------------ TOKEN DE COMPRA (Hub) ------
create or replace function public.dumtech_token_compra(
    p_chave   text default '',
    p_maquina text default '',
    p_nome    text default '',
    p_email   text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_chave    text := public.dumtech_normalizar(p_chave, 32);
    v_maquina  text := public.dumtech_normalizar(p_maquina, 64);
    v_nome     text := left(btrim(coalesce(p_nome, '')), 120);
    v_email    text := lower(left(btrim(coalesce(p_email, '')), 160));
    v_licenca  public.licencas;
    v_cliente  public.clientes;
    v_produtos jsonb := '[]'::jsonb;
    v_token    text;
begin
    if not public.dumtech_dentro_do_limite('token_ip', public.dumtech_ip_do_pedido(), 60, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas. Espere alguns minutos e tente de novo.');
    end if;

    -- faxina barata: token velho nao serve para nada
    delete from public.compra_tokens where expira_em < now() - interval '7 days';

    if v_chave <> '' and v_maquina <> '' then
        select * into v_licenca from public.licencas where chave = v_chave;
        if not found then
            return jsonb_build_object('ok', false, 'erro', 'nao_encontrada',
                                      'mensagem', 'Chave nao encontrada.');
        end if;
        if not exists (select 1 from public.ativacoes a
                        where a.licenca_id = v_licenca.id and a.maquina = v_maquina) then
            return jsonb_build_object('ok', false, 'erro', 'maquina_nao_ativada',
                                      'mensagem', 'Este computador nao esta ativado com esta chave.');
        end if;

        select * into v_cliente from public.clientes where id = v_licenca.cliente_id;
        select coalesce(jsonb_agg(p.codigo order by p.codigo), '[]'::jsonb) into v_produtos
          from public.licenca_produtos lp
          join public.produtos p on p.id = lp.produto_id
         where lp.licenca_id = v_licenca.id;

        v_nome  := v_cliente.nome;
        v_email := v_cliente.email;
    else
        if not public.dumtech_email_valido(v_email) then
            return jsonb_build_object('ok', false, 'erro', 'email_invalido',
                                      'mensagem', 'Confira o e-mail digitado.');
        end if;
        -- so para atribuir a visita a quem ja e cadastrado; NADA do cadastro
        -- dele entra no token: vale o que a pessoa digitou agora
        select * into v_cliente from public.clientes where lower(email) = v_email;
    end if;

    v_token := public.dumtech_novo_token();
    insert into public.compra_tokens (token, cliente_id, nome, email, produtos)
    values (v_token, v_cliente.id, v_nome, v_email, v_produtos);

    return jsonb_build_object('ok', true, 'token', v_token,
                              'expira_em', now() + interval '15 minutes');
end;
$$;

-- ------------------------------------------------------ ATIVAR (1a vez) -----
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
    p_chave   := public.dumtech_normalizar(p_chave, 32);
    p_maquina := public.dumtech_normalizar(p_maquina, 64);
    p_apelido := left(btrim(coalesce(p_apelido, '')), 120);

    if not public.dumtech_dentro_do_limite('licenca_ip', public.dumtech_ip_do_pedido(), 120, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas deste endereco. Espere alguns minutos e tente de novo.');
    end if;

    if p_chave = '' or p_maquina = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe a chave da licenca.');
    end if;

    v_licenca := public.dumtech_licenca_valida(p_chave);

    -- segura a licenca ate o fim da transacao: duas ativacoes ao mesmo tempo
    -- nao podem passar as duas pela contagem de vagas
    perform 1 from public.licencas where id = v_licenca.id for update;

    select exists(
        select 1 from public.ativacoes
         where licenca_id = v_licenca.id and maquina = p_maquina
    ) into v_ja;

    if v_ja then
        update public.ativacoes
           set ultima_checagem = now(),
               apelido = case when p_apelido <> '' then p_apelido else apelido end
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

-- ---------------------------------------- VERIFICAR (comprou outro produto) --
create or replace function public.dumtech_verificar_licenca(
    p_chave   text,
    p_maquina text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_licenca public.licencas;
    v_texto   text;
begin
    p_chave   := public.dumtech_normalizar(p_chave, 32);
    p_maquina := public.dumtech_normalizar(p_maquina, 64);

    if not public.dumtech_dentro_do_limite('licenca_ip', public.dumtech_ip_do_pedido(), 120, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas deste endereco. Espere alguns minutos e tente de novo.');
    end if;

    if p_chave = '' or p_maquina = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe a chave da licenca.');
    end if;

    v_licenca := public.dumtech_licenca_valida(p_chave);

    update public.ativacoes
       set ultima_checagem = now()
     where licenca_id = v_licenca.id and maquina = p_maquina;

    if not found then
        return jsonb_build_object(
            'ok', false, 'erro', 'maquina_nao_ativada',
            'mensagem', 'Este computador ainda nao foi ativado com esta chave. '
                     || 'Use o botao Ativar licenca.');
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

-- ------------------------------ DESATIVAR (liberar a vaga do computador) -----
create or replace function public.dumtech_desativar_licenca(
    p_chave   text,
    p_maquina text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_id       uuid;
    v_removeu  boolean;
begin
    p_chave   := public.dumtech_normalizar(p_chave, 32);
    p_maquina := public.dumtech_normalizar(p_maquina, 64);

    if not public.dumtech_dentro_do_limite('licenca_ip', public.dumtech_ip_do_pedido(), 120, interval '1 hour') then
        return jsonb_build_object('ok', false, 'erro', 'muitas_tentativas',
                                  'mensagem', 'Muitas tentativas seguidas deste endereco. Espere alguns minutos e tente de novo.');
    end if;

    select id into v_id from public.licencas where chave = p_chave;
    if not found then
        -- registrar tambem aqui: senao esta funcao vira um testador de chaves
        -- silencioso, sem nenhuma marca no banco
        insert into public.licenca_tentativas (chave, maquina, erro)
        values (p_chave, p_maquina, 'nao_encontrada');
        return jsonb_build_object('ok', false, 'erro', 'nao_encontrada',
                                  'mensagem', 'Chave nao encontrada.');
    end if;

    delete from public.ativacoes where licenca_id = v_id and maquina = p_maquina;
    v_removeu := found;
    return jsonb_build_object('ok', true, 'removido', v_removeu);
end;
$$;

-- ================================================ 3. APROVAR COM TRAVA ======
-- Dois cliques em "Aprovar" (ou dois administradores ao mesmo tempo) liam o
-- pedido ainda em aberto e emitiam DUAS licencas. O `for update` faz o segundo
-- esperar o primeiro terminar - e ai ele ve o pedido ja atendido.
create or replace function public.dumtech_aprovar_pedido(
    p_pedido_id        uuid,
    p_max_computadores integer default 1,
    p_tipo             text    default 'vitalicia',
    p_expira_em        date    default null
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
    v_pedido    public.pedidos_site;
    v_licenca   public.licencas;
    v_licenca_id uuid;
    v_chave     text;
    v_produtos  text[];
    v_combo     text;
    v_liberados integer;
    -- guardado no instante da decisao: `found` e reescrito por TODA instrucao
    -- seguinte, entao perguntar por ele no fim da funcao responderia outra coisa
    v_nova      boolean;
begin
    select * into v_pedido from public.pedidos_site where id = p_pedido_id for update;
    if not found then
        raise exception 'Pedido % nao existe.', p_pedido_id;
    end if;
    if v_pedido.atendido_em is not null then
        raise exception 'Este pedido ja foi atendido em %.',
            to_char(v_pedido.atendido_em, 'DD/MM/YYYY HH24:MI');
    end if;
    if v_pedido.cliente_id is null then
        raise exception 'Pedido sem cliente ligado - resolva o cadastro antes.';
    end if;

    select coalesce(array_agg(item->>'codigo')
                    filter (where item->>'tipo' = 'produto'), '{}'),
           max(item->>'codigo') filter (where item->>'tipo' = 'combo')
      into v_produtos, v_combo
      from jsonb_array_elements(v_pedido.itens) item;

    -- a licenca do cliente tambem fica travada: aprovar dois pedidos dele ao
    -- mesmo tempo nao pode criar duas licencas "primeiras"
    select * into v_licenca
      from public.licencas
     where cliente_id = v_pedido.cliente_id and status = 'ativa'
     order by criado_em
     limit 1
       for update;
    v_nova := not found;

    if not v_nova then
        v_licenca_id := v_licenca.id;
        v_chave := v_licenca.chave;
        v_liberados := public.dumtech_liberar_produtos(v_licenca_id, v_produtos, v_combo);
    else
        select e.licenca_id, e.chave into v_licenca_id, v_chave
          from public.dumtech_emitir_licenca(
                p_cliente_id       => v_pedido.cliente_id,
                p_produtos         => v_produtos,
                p_combo            => v_combo,
                p_tipo             => p_tipo,
                p_expira_em        => p_expira_em,
                p_max_computadores => p_max_computadores,
                p_observacoes      => format('pedido do site %s', p_pedido_id)) e;
        select count(*) into v_liberados
          from public.licenca_produtos where licenca_id = v_licenca_id;
    end if;

    update public.pedidos_site set atendido_em = now() where id = p_pedido_id;

    return jsonb_build_object(
        'ok', true,
        'chave', v_chave,
        'licenca_id', v_licenca_id,
        'produtos_liberados', v_liberados,
        'licenca_nova', v_nova,
        'cliente', (select nome from public.clientes where id = v_pedido.cliente_id),
        'email', v_pedido.email,
        'total', v_pedido.total);
end;
$$;

-- ====================================================== 4. TEMPO REAL =======
-- Um gatilho por comando (nao por linha): um UPDATE de 50 precos vira UM aviso.
create or replace function public.dumtech_avisar_mudanca()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_topico  text    := tg_argv[0];
    v_privado boolean := coalesce(tg_argv[1], 'false')::boolean;
begin
    if to_regprocedure('realtime.send(jsonb, text, text, boolean)') is not null then
        begin
            execute 'select realtime.send($1, $2, $3, $4)'
               using jsonb_build_object('tabela', tg_table_name, 'op', lower(tg_op)),
                     'mudou', v_topico, v_privado;
        exception when others then
            -- o aviso e cortesia: gravar o preco e o que importa
            raise warning 'dumtech: aviso de tempo real nao saiu (%): %', v_topico, sqlerrm;
        end;
    end if;
    return null;
end;
$$;

do $$
declare
    v_tabela text;
begin
    -- o site so precisa saber do catalogo
    foreach v_tabela in array array['produtos', 'combos', 'combo_produtos'] loop
        execute format('drop trigger if exists trg_tempo_real_catalogo on public.%I', v_tabela);
        execute format(
            'create trigger trg_tempo_real_catalogo after insert or update or delete on public.%I '
            'for each statement execute function public.dumtech_avisar_mudanca(%L, %L)',
            v_tabela, 'catalogo', 'false');
    end loop;

    -- o painel quer saber de tudo o que ele mostra (menos o uso diario e as
    -- tentativas recusadas: esses chegam aos montes e o painel os confere
    -- quando a aba volta a ficar visivel)
    foreach v_tabela in array array['clientes', 'licencas', 'licenca_produtos', 'ativacoes',
                                    'pedidos_site', 'comunicados', 'produtos', 'combos',
                                    'combo_produtos'] loop
        execute format('drop trigger if exists trg_tempo_real_painel on public.%I', v_tabela);
        execute format(
            'create trigger trg_tempo_real_painel after insert or update or delete on public.%I '
            'for each statement execute function public.dumtech_avisar_mudanca(%L, %L)',
            v_tabela, 'painel', 'true');
    end loop;
end;
$$;

-- canal privado "painel": so quem esta em `administradores` escuta
do $$
begin
    if to_regclass('realtime.messages') is not null then
        execute 'drop policy if exists dumtech_admin_ouve_painel on realtime.messages';
        execute $politica$
            create policy dumtech_admin_ouve_painel on realtime.messages
                for select to authenticated
                using ((select realtime.topic()) = 'painel'
                       and realtime.messages.extension = 'broadcast'
                       and public.dumtech_e_admin())
        $politica$;
    end if;
end;
$$;

-- ==================================================== 5. CORRECOES ==========

-- 5.1 link de anuncio: o Hub abre o link no computador de TODO cliente. Um
--     `file:///...exe` ou `\\servidor\pasta` ali executaria programa na maquina
--     dele. So https passa. (NOT VALID: nao reprova anuncio antigo; o Hub tambem
--     filtra do lado dele.)
alter table public.comunicados drop constraint if exists comunicados_link_https;
alter table public.comunicados add constraint comunicados_link_https
    check (link = '' or link ~* '^https://[^[:space:]\\]+$') not valid;

-- 5.2 TRUNCATE ignora o RLS. A API nao expoe TRUNCATE, mas o privilegio padrao
--     do Supabase o concede - e privilegio que ninguem usa nao fica.
revoke truncate, references, trigger on all tables in schema public from anon, authenticated;

-- 5.3 o painel filtra pedidos por cliente e ordena os atendidos
create index if not exists idx_pedidos_site_cliente  on public.pedidos_site (cliente_id);
create index if not exists idx_pedidos_site_atendido on public.pedidos_site (atendido_em desc)
    where atendido_em is not null;
create index if not exists idx_ativacoes_checagem    on public.ativacoes (ultima_checagem desc);

-- ================================================= 6. PERMISSOES ============
alter table public.limites_de_taxa enable row level security;
revoke all on table public.limites_de_taxa from anon, authenticated;

revoke execute on function public.dumtech_ip_do_pedido()                                from public, anon, authenticated;
revoke execute on function public.dumtech_dentro_do_limite(text, text, integer, interval) from public, anon, authenticated;
revoke execute on function public.dumtech_avisar_mudanca()                              from public, anon, authenticated;

-- as funcoes recriadas mantem as permissoes (create or replace nao mexe em
-- grant), mas repetir aqui deixa o arquivo valido sozinho
revoke execute on function public.dumtech_registrar_pedido(text, text, text, text[], text, text, text) from public;
revoke execute on function public.dumtech_identificar_cliente(text, text)      from public;
revoke execute on function public.dumtech_token_compra(text, text, text, text) from public;
revoke execute on function public.dumtech_ativar_licenca(text, text, text)     from public;
revoke execute on function public.dumtech_verificar_licenca(text, text)        from public;
revoke execute on function public.dumtech_desativar_licenca(text, text)        from public;
grant execute on function public.dumtech_registrar_pedido(text, text, text, text[], text, text, text) to anon, authenticated;
grant execute on function public.dumtech_identificar_cliente(text, text)      to anon, authenticated;
grant execute on function public.dumtech_token_compra(text, text, text, text) to anon, authenticated;
grant execute on function public.dumtech_ativar_licenca(text, text, text)     to anon, authenticated;
grant execute on function public.dumtech_verificar_licenca(text, text)        to anon, authenticated;
grant execute on function public.dumtech_desativar_licenca(text, text)        to anon, authenticated;

revoke execute on function public.dumtech_aprovar_pedido(uuid, integer, text, date) from public, anon;
grant  execute on function public.dumtech_aprovar_pedido(uuid, integer, text, date) to authenticated, service_role;

notify pgrst, 'reload schema';
