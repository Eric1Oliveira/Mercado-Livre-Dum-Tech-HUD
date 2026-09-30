-- =============================================================================
-- 20260912120000 - o painel administrativo
--
-- O QUE ENTRA
--   administradores      quem pode entrar no painel (conta criada no Supabase)
--   policies de leitura  o painel le as tabelas DIRETO, como administrador
--   uso_diario           quantas vezes cada modulo foi aberto, por dia
--   integracoes          as pontes entre modulos, no banco (alimentam a recomendacao)
--   visoes painel_*      cliente, modulo e recomendacao prontos para a tela
--
-- O DESENHO DA SEGURANCA, EM TRES FRASES
--   1. A chave anon continua sem enxergar tabela nenhuma. Nada aqui muda isso.
--   2. O painel entra com Supabase Auth (papel `authenticated`) e so ve alguma
--      coisa se o usuario estiver em `administradores` - e a policy que decide,
--      nao o front.
--   3. Conta de administrador nasce no painel do Supabase, na mao. Nao existe
--      cadastro, nao existe convite, nao existe auto-promocao.
-- =============================================================================

-- ====================================================== 1. QUEM E ADMIN =====
create table if not exists public.administradores (
    user_id   uuid primary key,
    nome      text not null default '',
    criado_em timestamptz not null default now()
);

comment on table public.administradores is
    'Quem pode usar o painel. O id e o mesmo de auth.users - crie o usuario no '
    'painel do Supabase (Authentication > Users) e insira o id aqui.';

-- a chave estrangeira so existe onde existe auth.users (no Supabase); assim o
-- mesmo arquivo roda nos testes locais
do $$
begin
    if to_regclass('auth.users') is not null
       and not exists (select 1 from pg_constraint where conname = 'administradores_user_fk') then
        alter table public.administradores
            add constraint administradores_user_fk
            foreign key (user_id) references auth.users(id) on delete cascade;
    end if;
end;
$$;

-- quem esta pedindo? (mesma conta do auth.uid(), sem depender do schema auth)
create or replace function public.dumtech_admin_id()
returns uuid
language sql
stable
set search_path = ''
as $$
    select coalesce(
        nullif(current_setting('request.jwt.claim.sub', true), ''),
        nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
    )::uuid;
$$;

create or replace function public.dumtech_e_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1 from public.administradores a
         where a.user_id = public.dumtech_admin_id()
    );
$$;

-- ========================================================= 2. TELEMETRIA ====
-- Contadores agregados: "o modulo X foi aberto N vezes no dia D, naquele
-- computador". Sem hora, sem sequencia, sem o que foi feito dentro do modulo.
create table if not exists public.uso_diario (
    licenca_id     uuid not null references public.licencas(id) on delete cascade,
    maquina        text not null,
    dia            date not null,
    produto_codigo text not null references public.produtos(codigo),
    aberturas      integer not null default 0 check (aberturas between 0 and 100000),
    recebido_em    timestamptz not null default now(),
    primary key (licenca_id, maquina, dia, produto_codigo)
);

comment on table public.uso_diario is
    'Uso agregado por dia, enviado pelo Hub quando ele ja esta falando com o '
    'servidor. Nunca guarda hora nem acao - so "abriu N vezes naquele dia".';

create index if not exists idx_uso_dia on public.uso_diario (dia desc);
create index if not exists idx_uso_produto on public.uso_diario (produto_codigo, dia desc);
create index if not exists idx_uso_licenca on public.uso_diario (licenca_id, dia desc);

-- ------------------------------------------------- o Hub manda o resumo -----
create or replace function public.dumtech_registrar_uso(
    p_chave   text,
    p_maquina text,
    p_uso     jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_chave   text := public.dumtech_normalizar(p_chave, 32);
    v_maquina text := public.dumtech_normalizar(p_maquina, 64);
    v_licenca uuid;
    v_item    jsonb;
    v_dia     date;
    v_codigo  text;
    v_qtd     integer;
    v_gravados integer := 0;
begin
    if v_chave = '' or v_maquina = '' or jsonb_typeof(p_uso) <> 'array' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos');
    end if;

    select l.id into v_licenca from public.licencas l where l.chave = v_chave;
    if not found then
        return jsonb_build_object('ok', false, 'erro', 'nao_encontrada');
    end if;
    -- so aceita de computador que realmente ativou aquela chave
    if not exists (select 1 from public.ativacoes a
                    where a.licenca_id = v_licenca and a.maquina = v_maquina) then
        return jsonb_build_object('ok', false, 'erro', 'maquina_nao_ativada');
    end if;

    for v_item in
        select valor from jsonb_array_elements(p_uso) valor limit 400
    loop
        begin
            v_dia := (v_item->>'dia')::date;
            v_codigo := upper(btrim(coalesce(v_item->>'produto', '')));
            v_qtd := least(greatest(coalesce((v_item->>'aberturas')::integer, 0), 0), 100000);
        exception when others then
            continue;  -- linha estranha nao derruba o envio inteiro
        end;

        -- nada de futuro nem de passado remoto, e so produto que existe
        if v_dia is null or v_dia > current_date or v_dia < current_date - 400
           or v_qtd = 0
           or not exists (select 1 from public.produtos p where p.codigo = v_codigo) then
            continue;
        end if;

        insert into public.uso_diario (licenca_id, maquina, dia, produto_codigo, aberturas)
        values (v_licenca, v_maquina, v_dia, v_codigo, v_qtd)
        on conflict (licenca_id, maquina, dia, produto_codigo) do update
            -- reenvio do mesmo dia nao soma duas vezes: vale o maior
            set aberturas = greatest(public.uso_diario.aberturas, excluded.aberturas),
                recebido_em = now();
        v_gravados := v_gravados + 1;
    end loop;

    return jsonb_build_object('ok', true, 'gravados', v_gravados);
end;
$$;

-- ======================================================== 3. INTEGRACOES ====
-- As pontes que existem no programa, agora tambem no banco: e delas que sai a
-- recomendacao ("usa muito o Vendas e nao tem o Financeiro").
create table if not exists public.integracoes (
    produto_de   text not null references public.produtos(codigo),
    produto_para text not null references public.produtos(codigo),
    titulo       text not null,
    descricao    text not null default '',
    primary key (produto_de, produto_para),
    check (produto_de <> produto_para)
);

insert into public.integracoes (produto_de, produto_para, titulo, descricao) values
    ('ESTOQUE', 'VENDAS',      'O estoque abastece o balcao',
     'Bipou o codigo de barras: nome e preco vem do estoque, e a saida da baixa sozinha.'),
    ('ESTOQUE', 'ORCAMENTOS',  'O estoque abastece a proposta',
     'A proposta puxa produto e preco do estoque.'),
    ('ESTOQUE', 'ORDENS',      'O estoque abastece a oficina',
     'A peca usada na ordem sai do estoque.'),
    ('VENDAS',  'FINANCEIRO',  'Venda a prazo vira conta a receber',
     'A conta nasce sozinha no dia combinado; quando o cliente paga, ela se quita.'),
    ('ORDENS',  'FINANCEIRO',  'Servico entregue vira conta a receber',
     'Um clique na entrega lanca o valor no fluxo de caixa.'),
    ('ORCAMENTOS', 'VENDAS',   'Proposta aprovada vira venda',
     'O sim do cliente vira venda no balcao, com os itens ja dentro.'),
    ('ORCAMENTOS', 'ORDENS',   'Proposta aprovada vira ordem',
     'O sim do cliente vira ordem na bancada, com os itens ja dentro.'),
    ('CLIENTES', 'VENDAS',     'Um cadastro so',
     'O nome digitado no balcao e o mesmo da proposta, da ordem e do compromisso.'),
    ('CLIENTES', 'ORCAMENTOS', 'Um cadastro so', ''),
    ('CLIENTES', 'ORDENS',     'Um cadastro so', ''),
    ('CLIENTES', 'AGENDA',     'Um cadastro so', ''),
    ('CLIENTES', 'FINANCEIRO', 'Um cadastro so', '')
on conflict (produto_de, produto_para) do update
    set titulo = excluded.titulo, descricao = excluded.descricao;

-- ====================================================== 4. VISOES DO PAINEL ==

-- 4.1 a ficha de cada cliente numa linha
create or replace view public.painel_clientes with (security_invoker = true) as
with licenca_ativa as (
    select distinct on (l.cliente_id)
           l.cliente_id, l.id as licenca_id, l.chave, l.tipo, l.status, l.expira_em,
           l.max_computadores, l.criado_em
      from public.licencas l
     order by l.cliente_id, (l.status = 'ativa') desc, l.criado_em
), uso as (
    select l.cliente_id,
           sum(u.aberturas) filter (where u.dia >= current_date - 30) as aberturas_30d,
           max(u.dia) as ultimo_dia
      from public.uso_diario u
      join public.licencas l on l.id = u.licenca_id
     group by l.cliente_id
)
select c.id                                        as cliente_id,
       c.nome,
       c.email,
       c.telefone,
       c.documento,
       c.origem,
       c.criado_em                                 as cliente_desde,
       la.licenca_id,
       la.chave,
       la.tipo,
       la.status,
       public.dumtech_situacao_licenca(la.status, la.expira_em) as situacao,
       la.expira_em,
       la.max_computadores,
       (select count(*) from public.ativacoes a where a.licenca_id = la.licenca_id)
                                                   as computadores,
       (select count(*) from public.licenca_produtos lp where lp.licenca_id = la.licenca_id)
                                                   as produtos,
       coalesce((select array_agg(p.codigo order by p.codigo)
                   from public.licenca_produtos lp
                   join public.produtos p on p.id = lp.produto_id
                  where lp.licenca_id = la.licenca_id), '{}') as produtos_codigos,
       coalesce(u.aberturas_30d, 0)                as aberturas_30d,
       u.ultimo_dia                                as ultimo_uso,
       (select max(a.ultima_checagem) from public.ativacoes a where a.licenca_id = la.licenca_id)
                                                   as ultima_checagem,
       (select count(*) from public.pedidos_site ps
         where ps.cliente_id = c.id and ps.atendido_em is null) as pedidos_abertos,
       (select coalesce(sum(ps.total), 0) from public.pedidos_site ps
         where ps.cliente_id = c.id and ps.atendido_em is not null) as total_comprado
  from public.clientes c
  left join licenca_ativa la on la.cliente_id = c.id
  left join uso u on u.cliente_id = c.id;

-- 4.2 o retrato de cada modulo
create or replace view public.painel_modulos with (security_invoker = true) as
select p.codigo,
       p.nome,
       p.preco,
       p.ativo,
       (select count(distinct l.cliente_id)
          from public.licenca_produtos lp
          join public.licencas l on l.id = lp.licenca_id
         where lp.produto_id = p.id)               as clientes,
       coalesce((select sum(u.aberturas) from public.uso_diario u
                  where u.produto_codigo = p.codigo and u.dia >= current_date - 30), 0)
                                                   as aberturas_30d,
       (select count(distinct u.licenca_id) from public.uso_diario u
         where u.produto_codigo = p.codigo and u.dia >= current_date - 30)
                                                   as licencas_ativas_30d,
       (select count(*) from public.comunicados c
         where c.ativo and c.produto_codigo = p.codigo) as anuncios
  from public.produtos p;

-- 4.3 o que faz sentido oferecer a cada cliente, e POR QUE
create or replace view public.painel_recomendacoes with (security_invoker = true) as
with tem as (
    select l.cliente_id, p.codigo, l.id as licenca_id
      from public.licenca_produtos lp
      join public.licencas l on l.id = lp.licenca_id
      join public.produtos p on p.id = lp.produto_id
     where l.status = 'ativa'
), uso as (
    select l.cliente_id, u.produto_codigo,
           sum(u.aberturas) filter (where u.dia >= current_date - 30) as aberturas
      from public.uso_diario u
      join public.licencas l on l.id = u.licenca_id
     group by l.cliente_id, u.produto_codigo
)
select t.cliente_id,
       i.produto_para                              as recomendado,
       alvo.nome                                   as recomendado_nome,
       alvo.preco,
       i.produto_de                                as porque_tem,
       i.titulo                                    as porque,
       i.descricao,
       coalesce(max(u.aberturas), 0)               as aberturas_origem
  from tem t
  join public.integracoes i on i.produto_de = t.codigo
  join public.produtos alvo on alvo.codigo = i.produto_para and alvo.ativo
  left join uso u on u.cliente_id = t.cliente_id and u.produto_codigo = i.produto_de
 where not exists (
        select 1 from tem j where j.cliente_id = t.cliente_id and j.codigo = i.produto_para)
 group by t.cliente_id, i.produto_para, alvo.nome, alvo.preco, i.produto_de, i.titulo, i.descricao;

-- 4.4 o resumo do negocio
create or replace view public.painel_resumo with (security_invoker = true) as
select (select count(*) from public.clientes)                                   as clientes,
       (select count(*) from public.clientes where origem = 'hub')              as interessados,
       (select count(*) from public.licencas where status = 'ativa')            as licencas_ativas,
       (select count(*) from public.licencas
         where status = 'ativa' and expira_em is not null and expira_em < current_date) as licencas_vencidas,
       (select count(*) from public.ativacoes)                                  as computadores,
       (select count(*) from public.licenca_produtos)                           as modulos_vendidos,
       (select count(*) from public.pedidos_site where atendido_em is null)     as pedidos_abertos,
       (select coalesce(sum(total), 0) from public.pedidos_site
         where atendido_em is not null)                                         as vendido,
       (select coalesce(sum(aberturas), 0) from public.uso_diario
         where dia >= current_date - 30)                                        as aberturas_30d,
       (select count(*) from public.licenca_tentativas
         where quando > now() - interval '24 hours')                            as tentativas_24h;

-- ================================================ 5. PERMISSOES DO PAINEL ===
-- O painel entra como `authenticated` e le as tabelas direto. Quem NAO esta em
-- `administradores` nao ve uma linha: a policy pergunta, nao o front.

do $$
declare
    v_tabela text;
    v_so_leitura constant text[] := array['ativacoes', 'licenca_tentativas', 'uso_diario',
                                          'integracoes', 'combo_produtos'];
    v_escrita    constant text[] := array['clientes', 'licencas', 'licenca_produtos',
                                          'produtos', 'combos', 'comunicados', 'pedidos_site'];
begin
    foreach v_tabela in array v_so_leitura || v_escrita loop
        execute format('alter table public.%I enable row level security', v_tabela);
        execute format('drop policy if exists admin_le on public.%I', v_tabela);
        execute format(
            'create policy admin_le on public.%I for select to authenticated '
            'using (public.dumtech_e_admin())', v_tabela);
        execute format('grant select on public.%I to authenticated', v_tabela);
    end loop;

    foreach v_tabela in array v_escrita loop
        execute format('drop policy if exists admin_escreve on public.%I', v_tabela);
        execute format(
            'create policy admin_escreve on public.%I for all to authenticated '
            'using (public.dumtech_e_admin()) with check (public.dumtech_e_admin())', v_tabela);
        execute format('grant insert, update, delete on public.%I to authenticated', v_tabela);
    end loop;

    -- combo_produtos e ativacoes tambem sao editados pelo painel (montar combo,
    -- liberar vaga de computador), mas nunca atualizados: so entram e saem
    foreach v_tabela in array array['combo_produtos', 'ativacoes'] loop
        execute format('drop policy if exists admin_mexe on public.%I', v_tabela);
        execute format(
            'create policy admin_mexe on public.%I for all to authenticated '
            'using (public.dumtech_e_admin()) with check (public.dumtech_e_admin())', v_tabela);
        execute format('grant insert, delete on public.%I to authenticated', v_tabela);
    end loop;
end;
$$;

-- a propria lista de administradores: cada um se ve, ninguem se promove
alter table public.administradores enable row level security;
drop policy if exists admin_se_ve on public.administradores;
create policy admin_se_ve on public.administradores for select to authenticated
    using (user_id = public.dumtech_admin_id());
grant select on public.administradores to authenticated;

-- as visoes de apoio (security_invoker: obedecem as policies acima)
grant select on public.painel_clientes, public.painel_modulos,
                public.painel_recomendacoes, public.painel_resumo,
                public.licencas_resumo, public.pedidos_abertos to authenticated;

-- as funcoes de administracao passam a servir o painel tambem. Elas rodam com
-- o papel de quem chama (nunca definer), entao quem nao e admin esbarra nas
-- policies de escrita e nao consegue nada.
grant execute on function public.dumtech_nova_chave()                          to authenticated;
grant execute on function public.dumtech_situacao_licenca(text, date)          to authenticated;
grant execute on function public.dumtech_liberar_produtos(uuid, text[], text)  to authenticated;
grant execute on function public.dumtech_emitir_licenca(uuid, text[], text, text, date, integer, text, text)
    to authenticated;
grant execute on function public.dumtech_aprovar_pedido(uuid, integer, text, date)
    to authenticated;
grant execute on function public.dumtech_e_admin()                             to authenticated;
grant execute on function public.dumtech_admin_id()                            to authenticated;

-- o Hub (chave anon) so ganha a porta de mandar uso
revoke execute on function public.dumtech_registrar_uso(text, text, jsonb) from public;
grant execute on function public.dumtech_registrar_uso(text, text, jsonb) to anon, authenticated;

-- Nada disso vale para a chave publica. Citar PUBLIC e obrigatorio: o
-- PostgreSQL concede EXECUTE a PUBLIC em toda funcao criada, e revogar so de
-- `anon` deixa a porta aberta pelo outro lado.
revoke all on table public.uso_diario, public.integracoes, public.administradores from anon;
revoke execute on function public.dumtech_e_admin()  from public, anon;
revoke execute on function public.dumtech_admin_id() from public, anon;

notify pgrst, 'reload schema';
