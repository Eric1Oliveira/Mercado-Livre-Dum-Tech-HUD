-- =============================================================================
-- 20260911235900 - o que a landing page precisa do banco
--
--   dumtech_catalogo()        -> o catalogo publico (produtos e combos)
--   pedidos_site              -> os kits montados no site
--   dumtech_registrar_pedido  -> grava o kit e devolve o resumo
--
-- Por que uma funcao para o catalogo: a chave anon NAO le tabela nenhuma (nem
-- `produtos`), e esse desenho nao vai mudar. A funcao devolve so o que e
-- vitrine - codigo, nome, descricao, preco e versao dos produtos A VENDA.
--
-- O total NUNCA vem do navegador: quem soma e o banco, a partir do proprio
-- catalogo. O site manda o que a pessoa escolheu; o preco e assunto daqui.
-- =============================================================================

-- ================================================ 1. PRECOS DE EXEMPLO ======
-- Valores plausiveis para o site nascer completo. Trocar e um UPDATE - nada
-- disso esta escrito dentro da pagina.
update public.produtos set preco = case codigo
    when 'ESTOQUE'    then 249.00
    when 'VENDAS'     then 249.00
    when 'FINANCEIRO' then 229.00
    when 'ORDENS'     then 229.00
    when 'ORCAMENTOS' then 199.00
    when 'CLIENTES'   then 149.00
    when 'AGENDA'     then 149.00
    else preco
end
where preco = 0 and codigo in
    ('ESTOQUE', 'VENDAS', 'FINANCEIRO', 'ORDENS', 'ORCAMENTOS', 'CLIENTES', 'AGENDA');

-- o combo Gestao custa menos que a soma das partes (876 -> 699)
update public.combos set preco = 699.00 where codigo = 'GESTAO' and preco = 0;

-- ==================================================== 2. PEDIDOS DO SITE ====
create table if not exists public.pedidos_site (
    id          uuid primary key default gen_random_uuid(),
    cliente_id  uuid references public.clientes(id) on delete set null,
    nome        text not null,
    email       text not null,
    telefone    text not null default '',
    -- o que foi montado: [{"tipo":"produto","codigo":"ESTOQUE","preco":249.00}, ...]
    itens       jsonb not null default '[]'::jsonb,
    total       numeric(12, 2) not null default 0 check (total >= 0),
    -- de onde veio: 'hub' (cliente identificado pelo token) ou 'site'
    origem      text not null default 'site' check (origem in ('hub', 'site')),
    observacoes text not null default '',
    criado_em   timestamptz not null default now(),
    atendido_em timestamptz
);

comment on table public.pedidos_site is
    'Kits montados na landing page. Enquanto nao existe checkout automatico, '
    'isto e a caixa de entrada comercial: quem montou, o que escolheu e quanto '
    'deu - com o total calculado pelo banco, nunca pelo navegador.';

create index if not exists idx_pedidos_site_criado on public.pedidos_site (criado_em desc);
create index if not exists idx_pedidos_site_aberto on public.pedidos_site (atendido_em)
    where atendido_em is null;

-- ========================================================== 3. FUNCOES ======

-- ------------------------------------------------ CATALOGO (vitrine publica) --
create or replace function public.dumtech_catalogo()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    select jsonb_build_object(
        'ok', true,
        'produtos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'codigo', p.codigo, 'nome', p.nome, 'descricao', p.descricao,
                       'preco', p.preco, 'versao', p.versao)
                   order by p.codigo)
              from public.produtos p
             where p.ativo
        ), '[]'::jsonb),
        'combos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'codigo', c.codigo, 'nome', c.nome, 'descricao', c.descricao,
                       'preco', c.preco,
                       'produtos', coalesce((
                           select jsonb_agg(p.codigo order by p.codigo)
                             from public.combo_produtos cp
                             join public.produtos p on p.id = cp.produto_id
                            where cp.combo_id = c.id and p.ativo
                       ), '[]'::jsonb))
                   order by c.preco)
              from public.combos c
             where c.ativo
        ), '[]'::jsonb),
        'verificado_em', now());
$$;

-- ------------------------------------------------ REGISTRAR PEDIDO (kit) -----
-- Recebe o que a pessoa escolheu e devolve o resumo com o total calculado AQUI.
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
    if v_nome = '' then
        return jsonb_build_object('ok', false, 'erro', 'dados_incompletos',
                                  'mensagem', 'Informe o seu nome.');
    end if;
    if not public.dumtech_email_valido(v_email) then
        return jsonb_build_object('ok', false, 'erro', 'email_invalido',
                                  'mensagem', 'Confira o e-mail digitado.');
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
                                      'mensagem', format('O modulo %s nao esta disponivel.', v_codigo));
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

-- ================================================= 4. RLS E PERMISSOES ======
alter table public.pedidos_site enable row level security;
revoke all on table public.pedidos_site from anon, authenticated;

revoke execute on function public.dumtech_catalogo()                 from public;
revoke execute on function public.dumtech_registrar_pedido(text, text, text, text[], text, text, text)
    from public;

grant execute on function public.dumtech_catalogo()                  to anon, authenticated;
grant execute on function public.dumtech_registrar_pedido(text, text, text, text[], text, text, text)
    to anon, authenticated;

notify pgrst, 'reload schema';
