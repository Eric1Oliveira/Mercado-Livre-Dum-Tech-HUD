-- =============================================================================
-- O painel enxerga - e controla - o uso de cada cliente: teste gratis,
-- celular conectado e o Hub de cada computador.
--
-- O QUE ENTRA
--   1. TESTE GRATIS: o administrador da, estende e encerra (antes so lia).
--      A impressao digital da licenca passa a incluir os testes: estender ou
--      encerrar chega ao Hub do cliente em ate 2 minutos, como modulo liberado.
--   2. CELULAR: o administrador desconecta um aparelho (o mesmo "Desconectar"
--      do Hub) e ve QUANDO cada computador atualizou o resumo do celular -
--      nunca O QUE foi publicado. A coluna `dados` (vendas, clientes e valores
--      da empresa do cliente) continua fora do alcance do painel: o privilegio
--      e dado por coluna, e `dados` nao esta na lista.
--   3. LOJA PELO HUB: quem clicou em "Comprar" no Hub (compra_tokens), sem a
--      coluna `token` - o codigo que abre a compra nao sai do banco.
--   4. VISOES: o uso por dia, a faixa de 30 dias de cada cliente, cada modulo
--      pago com o ultimo uso, e cada teste com o uso durante o teste e se
--      virou compra.
--   5. Auditoria e tempo real nas duas tabelas que o painel passa a mexer.
--
-- O QUE NAO MUDA
--   O Hub, o site e o celular seguem pelas mesmas funcoes. Licenca sem teste
--   tem a mesma impressao digital de antes (concat_ws pula o NULL): nenhum Hub
--   reconfere a licenca por causa desta migration.
-- =============================================================================

-- ========================================================== 1. TESTES ======
drop policy if exists admin_escreve on public.licenca_testes;
create policy admin_escreve on public.licenca_testes for all to authenticated
    using (public.dumtech_e_admin()) with check (public.dumtech_e_admin());
-- dar teste (o comeco e sempre agora) e mudar o fim; apagar, nao: o teste
-- feito e historico, e e ele que impede o mesmo cliente de testar de novo
grant insert (licenca_id, produto_id, termina_em) on public.licenca_testes to authenticated;
grant update (termina_em) on public.licenca_testes to authenticated;

-- ======================================================== 2. CELULAR =======
drop policy if exists admin_desconecta on public.celular_aparelhos;
create policy admin_desconecta on public.celular_aparelhos for update to authenticated
    using (public.dumtech_e_admin()) with check (public.dumtech_e_admin());
grant update (revogado_em) on public.celular_aparelhos to authenticated;

-- o resumo do celular: so a hora em que cada computador publicou
drop policy if exists admin_le on public.celular_espelhos;
create policy admin_le on public.celular_espelhos for select to authenticated
    using (public.dumtech_e_admin());
grant select (licenca_id, maquina, atualizado_em) on public.celular_espelhos to authenticated;

-- ===================================================== 3. LOJA PELO HUB ====
drop policy if exists admin_le on public.compra_tokens;
create policy admin_le on public.compra_tokens for select to authenticated
    using (public.dumtech_e_admin());
grant select (cliente_id, nome, email, produtos, criado_em, expira_em, usado_em)
    on public.compra_tokens to authenticated;

-- ============================================ 4. IMPRESSAO DA LICENCA ======
-- Igual a de 20260921120000, mais o ultimo item: os testes (modulo e fim).
create or replace function public.dumtech_licenca_marca(p_chave text, p_maquina text)
returns text
language sql
stable
security definer
set search_path = ''
as $$
    select coalesce((
        select md5(concat_ws('|',
            l.status,
            l.max_computadores::text,
            coalesce(l.expira_em::text, ''),
            coalesce(l.tipo, ''),
            (select string_agg(coalesce(lp.produto_id::text, '') || ':' || coalesce(lp.combo_id::text, ''),
                               ',' order by lp.produto_id, lp.combo_id)
               from public.licenca_produtos lp where lp.licenca_id = l.id),
            (select max(p.atualizado_em)::text
               from public.produtos p
               join public.licenca_produtos lp on lp.produto_id = p.id
              where lp.licenca_id = l.id),
            (select max(c.atualizado_em)::text
               from public.combos c
               join public.licenca_produtos lp on lp.combo_id = c.id
              where lp.licenca_id = l.id),
            (select count(*)::text from public.ativacoes a
              where a.licenca_id = l.id
                and a.maquina = public.dumtech_normalizar(p_maquina, 64)),
            (select pc.atualizado_em::text from public.pagamento_config pc
              where pc.licenca_id = l.id),
            -- sem teste: NULL, e concat_ws pula - a impressao fica a mesma
            (select string_agg(t.produto_id::text || ':' || t.termina_em::text, ',' order by t.produto_id)
               from public.licenca_testes t
              where t.licenca_id = l.id)
        ))
        from public.licencas l
        where l.chave = public.dumtech_normalizar(p_chave, 32)
          -- so quem tem ativacao nesta maquina recebe impressao: chave
          -- adivinhada sem maquina valida devolve vazio, igual a inexistente
          and exists (select 1 from public.ativacoes a
                       where a.licenca_id = l.id
                         and a.maquina = public.dumtech_normalizar(p_maquina, 64))
    ), '');
$$;
revoke execute on function public.dumtech_licenca_marca(text, text) from public, anon, authenticated;

-- ========================================================= 5. VISOES ======
-- O PostgREST entrega no maximo 1000 linhas por leitura. Por isso o uso chega
-- ja somado: uma linha por DIA (o grafico) e uma linha por CLIENTE (a faixa) -
-- nenhuma das duas cresce com o numero de clientes vezes o numero de dias.

-- 5.1 o uso de todos, por dia: aberturas e quantos clientes abriram algo
create or replace view public.painel_uso_dias with (security_invoker = true) as
select u.dia,
       sum(u.aberturas)::integer                  as aberturas,
       count(distinct l.cliente_id)::integer      as clientes
  from public.uso_diario u
  join public.licencas l on l.id = u.licenca_id
 group by u.dia;

-- 5.1b a faixa de cada cliente: as aberturas dos ultimos 30 dias, do mais
-- antigo ate `ate` (hoje em Brasilia, o dia que o Hub anota), numa linha so
create or replace view public.painel_uso_por_cliente with (security_invoker = true) as
with hoje as (
    select (now() at time zone 'America/Sao_Paulo')::date as dia
), uso as (
    select l.cliente_id, u.dia, sum(u.aberturas)::integer as aberturas
      from public.uso_diario u
      join public.licencas l on l.id = u.licenca_id
     where u.dia between (select dia from hoje) - 29 and (select dia from hoje)
     group by l.cliente_id, u.dia
)
select c.cliente_id,
       (select dia from hoje)                     as ate,
       array_agg(coalesce(u.aberturas, 0) order by d.dia) as ultimos_30
  from (select distinct cliente_id from uso) c
 cross join lateral (
        select ((select dia from hoje) - g)::date as dia from generate_series(0, 29) g
  ) d
  left join uso u on u.cliente_id = c.cliente_id and u.dia = d.dia
 group by c.cliente_id;

-- 5.2 cada modulo pago, com o ultimo uso: "pagou e nao abre" aparece aqui
create or replace view public.painel_modulos_da_licenca with (security_invoker = true) as
select l.cliente_id,
       lp.licenca_id,
       public.dumtech_situacao_licenca(l.status, l.expira_em) as situacao,
       p.codigo,
       lp.liberado_em,
       u.ultimo_uso,
       coalesce(u.aberturas_30d, 0)               as aberturas_30d
  from public.licenca_produtos lp
  join public.licencas l on l.id = lp.licenca_id
  join public.produtos p on p.id = lp.produto_id
  left join lateral (
        select max(x.dia)                                              as ultimo_uso,
               sum(x.aberturas) filter (where x.dia >= current_date - 30)::integer as aberturas_30d
          from public.uso_diario x
         where x.licenca_id = lp.licenca_id
           and x.produto_codigo = p.codigo
  ) u on true;

-- 5.3 cada teste: quanto foi usado DURANTE o teste e se virou compra.
-- O dia do uso e o dia do computador do cliente (horario de Brasilia).
create or replace view public.painel_testes with (security_invoker = true) as
select t.licenca_id,
       l.cliente_id,
       t.produto_id,
       p.codigo,
       p.nome,
       p.preco,
       t.iniciado_em,
       t.termina_em,
       c.liberado_em is not null                  as comprou,
       c.liberado_em                              as comprou_em,
       coalesce(u.aberturas, 0)                   as aberturas,
       coalesce(u.dias, 0)                        as dias_de_uso,
       u.ultimo_uso
  from public.licenca_testes t
  join public.licencas l on l.id = t.licenca_id
  join public.produtos p on p.id = t.produto_id
  left join public.licenca_produtos c
         on c.licenca_id = t.licenca_id and c.produto_id = t.produto_id
  left join lateral (
        select sum(x.aberturas)::integer       as aberturas,
               count(distinct x.dia)::integer  as dias,
               max(x.dia)                      as ultimo_uso
          from public.uso_diario x
         where x.licenca_id = t.licenca_id
           and x.produto_codigo = p.codigo
           and x.dia between (t.iniciado_em at time zone 'America/Sao_Paulo')::date
                         and (least(t.termina_em, now()) at time zone 'America/Sao_Paulo')::date
  ) u on true;

-- visao nova nasce com o privilegio largo do Supabase: so o painel le
revoke all on public.painel_uso_dias, public.painel_uso_por_cliente, public.painel_modulos_da_licenca,
               public.painel_testes
    from public, anon;
grant select on public.painel_uso_dias, public.painel_uso_por_cliente, public.painel_modulos_da_licenca,
                public.painel_testes
    to authenticated;

-- ============================================= 6. AUDITORIA E TEMPO REAL ===
-- O Hub e o celular mexem nestas tabelas pela chave publica (iniciar teste,
-- parear, cada abertura do celular): a auditoria ja pula a chave publica, e
-- o tempo real so avisa o que muda a tela - nao cada abertura do celular.
drop trigger if exists trg_auditoria on public.licenca_testes;
create trigger trg_auditoria after insert or update or delete on public.licenca_testes
    for each row execute function public.dumtech_auditar();
drop trigger if exists trg_auditoria on public.celular_aparelhos;
create trigger trg_auditoria after update of revogado_em on public.celular_aparelhos
    for each row execute function public.dumtech_auditar();

drop trigger if exists trg_tempo_real_painel on public.licenca_testes;
create trigger trg_tempo_real_painel after insert or update or delete on public.licenca_testes
    for each statement execute function public.dumtech_avisar_mudanca('painel', 'true');
drop trigger if exists trg_tempo_real_painel on public.celular_aparelhos;
create trigger trg_tempo_real_painel after insert or delete or update of revogado_em on public.celular_aparelhos
    for each statement execute function public.dumtech_avisar_mudanca('painel', 'true');

notify pgrst, 'reload schema';
