-- =============================================================================
-- O dia a dia da DumTech no SQL Editor do Supabase.
--
-- Cada bloco e independente: copie so o que precisar. Os valores para ajustar
-- estao marcados com <<<.
--
-- Enquanto o painel administrativo nao existe, este arquivo E o painel.
-- =============================================================================


-- ===========================================================================
-- 1. VENDER (cliente novo comprando produtos avulsos)
-- ===========================================================================
do $$
declare
    v_cliente uuid;
    v_chave   text;
begin
    insert into public.clientes (nome, documento, email, telefone)
    values ('Joao da Silva',                     -- <<< nome
            '000.000.000-00',                    -- <<< CPF/CNPJ
            'joao@exemplo.com',                  -- <<< e-mail
            '(63) 99999-0000')                   -- <<< telefone
    returning id into v_cliente;

    select chave into v_chave
      from public.dumtech_emitir_licenca(
            p_cliente_id       => v_cliente,
            p_produtos         => array['ESTOQUE', 'FINANCEIRO'],  -- <<< o que comprou
            p_tipo             => 'vitalicia',   -- <<< vitalicia | assinatura | teste
            p_expira_em        => null,          -- <<< null so em vitalicia
            p_max_computadores => 1,             -- <<< em quantos computadores
            p_observacoes      => '');

    raise notice 'CHAVE DO CLIENTE: %', v_chave;
end;
$$;


-- ===========================================================================
-- 2. VENDER UM COMBO (uma chave so libera todos os produtos do pacote)
-- ===========================================================================
do $$
declare
    v_cliente uuid;
    v_chave   text;
begin
    insert into public.clientes (nome, documento, email, telefone)
    values ('Maria Souza', '', 'maria@exemplo.com', '')             -- <<<
    returning id into v_cliente;

    select chave into v_chave
      from public.dumtech_emitir_licenca(
            p_cliente_id       => v_cliente,
            p_combo            => 'GESTAO',      -- <<< codigo do combo
            p_max_computadores => 2);

    raise notice 'CHAVE DO CLIENTE: %', v_chave;
end;
$$;


-- ===========================================================================
-- 3. CLIENTE QUE JA TEM LICENCA COMPROU MAIS (ele so clica em "Verificar")
-- ===========================================================================
select public.dumtech_liberar_produtos(
           (select id from public.licencas where chave = 'XXXX-XXXX-XXXX-XXXX'),  -- <<<
           array['VENDAS']);                                                       -- <<<

-- o mesmo, mas comprando um combo inteiro:
-- select public.dumtech_liberar_produtos(
--            (select id from public.licencas where chave = 'XXXX-XXXX-XXXX-XXXX'),
--            '{}', 'GESTAO');

-- tirar um produto da licenca (o modulo some no proximo "Verificar licenca"):
-- delete from public.licenca_produtos
--  where licenca_id = (select id from public.licencas where chave = 'XXXX-XXXX-XXXX-XXXX')
--    and produto_id = (select id from public.produtos where codigo = 'VENDAS');


-- ===========================================================================
-- 4. CATALOGO: lancar um modulo novo e um INSERT (nunca uma tabela nova)
-- ===========================================================================
insert into public.produtos (codigo, nome, descricao, preco, versao)
values ('CRM', 'DumTech CRM', 'Funil de relacionamento', 299.00, '1.0')   -- <<<
on conflict (codigo) do update
   set nome = excluded.nome, descricao = excluded.descricao, preco = excluded.preco;

-- precos e versao dos produtos que ja existem:
-- update public.produtos set preco = 249.00, versao = '1.0' where codigo = 'ESTOQUE';

-- tirar de linha (quem ja comprou continua com o modulo; so nao entra em venda nova):
-- update public.produtos set ativo = false where codigo = 'CRM';


-- ===========================================================================
-- 5. COMBOS
-- ===========================================================================
insert into public.combos (codigo, nome, descricao, preco)
values ('GESTAO', 'DumTech Gestao', 'Estoque, Financeiro, Clientes e Vendas', 899.00)  -- <<<
on conflict (codigo) do update
   set nome = excluded.nome, descricao = excluded.descricao, preco = excluded.preco;

insert into public.combo_produtos (combo_id, produto_id)
select c.id, p.id
  from public.combos c
  join public.produtos p on p.codigo in ('ESTOQUE', 'FINANCEIRO', 'CLIENTES', 'VENDAS')  -- <<<
 where c.codigo = 'GESTAO'
on conflict do nothing;

-- tirar um produto do combo (nao mexe em quem ja comprou):
-- delete from public.combo_produtos
--  where combo_id = (select id from public.combos where codigo = 'GESTAO')
--    and produto_id = (select id from public.produtos where codigo = 'VENDAS');


-- ===========================================================================
-- 6. SUSPENDER, REATIVAR, CANCELAR, RENOVAR
-- ===========================================================================
-- update public.licencas set status = 'suspensa'  where chave = 'XXXX-XXXX-XXXX-XXXX';
-- update public.licencas set status = 'ativa'     where chave = 'XXXX-XXXX-XXXX-XXXX';
-- update public.licencas set status = 'cancelada' where chave = 'XXXX-XXXX-XXXX-XXXX';

-- renovar uma assinatura por mais um ano:
-- update public.licencas set expira_em = expira_em + 365 where chave = 'XXXX-XXXX-XXXX-XXXX';

-- transformar assinatura em vitalicia (o prazo TEM de ir junto: e uma regra do banco):
-- update public.licencas set tipo = 'vitalicia', expira_em = null where chave = 'XXXX-XXXX-XXXX-XXXX';


-- ===========================================================================
-- 7. COMPUTADORES (cliente trocou de maquina e nao desativou a antiga)
-- ===========================================================================
select a.maquina, a.apelido, a.ativado_em, a.ultima_checagem
  from public.ativacoes a
  join public.licencas l on l.id = a.licenca_id
 where l.chave = 'XXXX-XXXX-XXXX-XXXX';                                      -- <<<

-- liberar a vaga de um computador:
-- delete from public.ativacoes
--  where maquina = 'XXXX-XXXX-XXXX-XXXX'                                     -- <<< o ID do computador
--    and licenca_id = (select id from public.licencas where chave = 'XXXX-XXXX-XXXX-XXXX');


-- ===========================================================================
-- 8. VER TUDO
-- ===========================================================================
-- todas as licencas emitidas, com produtos e computadores:
select * from public.licencas_resumo order by criado_em desc;

-- a ficha de um cliente (o que ele tem e o que ainda nao comprou):
select c.nome,
       l.chave,
       p.codigo,
       case when lp.licenca_id is null then 'nao comprado' else 'liberado' end as situacao
  from public.clientes c
  join public.licencas l on l.cliente_id = c.id
 cross join public.produtos p
  left join public.licenca_produtos lp on lp.licenca_id = l.id and lp.produto_id = p.id
 where c.email = 'joao@exemplo.com'                                          -- <<<
 order by p.codigo;

-- quanto cada produto vendeu:
-- select p.codigo, p.nome, count(lp.licenca_id) as licencas
--   from public.produtos p
--   left join public.licenca_produtos lp on lp.produto_id = p.id
--  group by p.codigo, p.nome order by licencas desc;


-- ===========================================================================
-- 9. SUPORTE E SEGURANCA (tentativas recusadas)
-- ===========================================================================
select quando, chave, maquina, erro
  from public.licenca_tentativas
 order by quando desc
 limit 50;

-- alguem tentando adivinhar chaves nas ultimas 24 horas:
-- select maquina, count(*) as tentativas
--   from public.licenca_tentativas
--  where quando > now() - interval '24 hours' and erro = 'nao_encontrada'
--  group by maquina having count(*) > 20 order by tentativas desc;

-- limpeza (o registro so serve para suporte recente; rode de vez em quando):
-- delete from public.licenca_tentativas where quando < now() - interval '90 days';


-- ===========================================================================
-- 10. PEDIDOS DO SITE (o cliente montou o kit na landing page)
-- ===========================================================================
-- a caixa de entrada: o que chegou e ainda nao foi atendido
select * from public.pedidos_abertos;

-- APROVAR: libera os produtos na licenca do cliente e devolve a chave.
-- Quem ja tem licenca ativa recebe os modulos NELA (o Hub dele ve aparecer
-- sozinho ao voltar do navegador); quem nao tem, ganha uma licenca nova.
-- select public.dumtech_aprovar_pedido('00000000-0000-0000-0000-000000000000');  -- <<< pedido_id

-- com mais computadores, ou como assinatura de um ano:
-- select public.dumtech_aprovar_pedido('<pedido_id>', 3);
-- select public.dumtech_aprovar_pedido('<pedido_id>', 1, 'assinatura', current_date + 365);

-- ja atendidos, do mais recente para o mais antigo:
-- select criado_em, atendido_em, nome, email, total, itens
--   from public.pedidos_site where atendido_em is not null order by atendido_em desc;
