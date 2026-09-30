-- =============================================================================
-- 20260911220000 - primeiro combo comercial: DumTech Gestao
--
-- Isto e dado comercial, nao estrutura. Entra como migration porque e assim que
-- se escreve no banco de verdade (supabase db push) e porque um banco novo
-- (homologacao) nasce com o mesmo catalogo.
--
-- Os precos ficam em 0 ate a DumTech definir a tabela de precos: ajuste com
-- UPDATE (blocos 4 e 5 de docs/supabase/operacoes_admin.sql). Rodar de novo nao
-- duplica nem sobrescreve preco.
-- =============================================================================

insert into public.combos (codigo, nome, descricao)
values ('GESTAO', 'DumTech Gestao', 'Estoque, Financeiro, Clientes e Vendas numa chave so')
on conflict (codigo) do nothing;

insert into public.combo_produtos (combo_id, produto_id)
select c.id, p.id
  from public.combos c
  join public.produtos p on p.codigo in ('ESTOQUE', 'FINANCEIRO', 'CLIENTES', 'VENDAS')
 where c.codigo = 'GESTAO'
on conflict do nothing;

-- conferencia: se o combo nao ficar com os 4 modulos, a migration falha inteira
do $$
declare
    v_itens integer;
begin
    select count(*) into v_itens
      from public.combo_produtos cp
      join public.combos c on c.id = cp.combo_id
     where c.codigo = 'GESTAO';

    if v_itens <> 4 then
        raise exception 'O combo GESTAO ficou com % produto(s), esperava 4.', v_itens;
    end if;
    raise notice 'Combo GESTAO pronto com % produtos (preco 0, a ajustar).', v_itens;
end;
$$;
