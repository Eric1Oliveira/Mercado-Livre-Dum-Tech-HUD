"""Lucro, margem, vendedores e comissao.

Vendeu nao e ganhou. Aqui entra o que a mercadoria custou, a devolucao (que tira
a receita e a mercadoria volta) e o desconto da venda (que se divide pelas linhas).
"""

from __future__ import annotations

from ..models import LinhaResultado, ResultadoVendas, Vendedor, VendaError
from .comum import dinheiro


class ResultadoMixin:
    """Parte do VendasRepository que responde 'quanto eu ganhei?'."""

    # -------------------------------------------------------------- vendedores
    def vendedores(self, incluir_inativos: bool = False) -> list[Vendedor]:
        sql = "SELECT * FROM vendedores"
        if not incluir_inativos:
            sql += " WHERE ativo = 1"
        return [Vendedor.from_row(row) for row in self.db.query(f"{sql} ORDER BY nome")]

    def salvar_vendedor(self, nome: str, comissao: float = 0.0) -> None:
        nome = nome.strip()
        if not nome:
            raise VendaError("Informe o nome do vendedor.")
        if not 0 <= float(comissao or 0) <= 100:
            raise VendaError("A comissão precisa ficar entre 0 e 100%.")
        self.db.execute(
            "INSERT INTO vendedores (nome, comissao) VALUES (?, ?)"
            " ON CONFLICT(nome) DO UPDATE SET comissao = excluded.comissao, ativo = 1",
            (nome, dinheiro(comissao)),
        )

    def inativar_vendedor(self, nome: str) -> None:
        """Quem saiu da loja sai da lista; as vendas dele continuam no nome dele."""
        self.db.execute("UPDATE vendedores SET ativo = 0 WHERE nome = ?", (nome.strip(),))

    # --------------------------------------------------------------- resultado
    def resultado(self, inicio: str, fim: str, limite_listas: int = 10) -> ResultadoVendas:
        comissoes = {v.nome.lower(): v.comissao for v in self.vendedores(incluir_inativos=True)}
        vendas = [v for v in self.listar(inicio=inicio, fim=fim, limite=-1) if v.conta]
        resultado = ResultadoVendas(inicio=inicio, fim=fim, vendas=len(vendas))
        produtos: dict[str, LinhaResultado] = {}
        por_vendedor: dict[str, LinhaResultado] = {}

        for venda in vendas:
            # desconto da venda vale proporcionalmente para cada linha
            fator = venda.total / venda.subtotal if venda.subtotal > 0 else 1.0
            custo_da_venda = 0.0
            receita_da_venda = 0.0
            for item in venda.itens:
                ficou = max(item.quantidade - item.devolvido, 0.0)
                if ficou <= 0:
                    continue
                receita = item.valor_unitario * ficou * fator
                custo = item.custo_unitario * ficou
                if item.custo_unitario <= 0:
                    resultado.itens_sem_custo += 1
                linha = produtos.setdefault(item.descricao, LinhaResultado(item.descricao))
                linha.quantidade += ficou
                linha.receita += receita
                linha.custo += custo
                receita_da_venda += receita
                custo_da_venda += custo
            resultado.receita += receita_da_venda
            resultado.custo += custo_da_venda

            if venda.vendedor:
                linha = por_vendedor.setdefault(venda.vendedor, LinhaResultado(venda.vendedor))
                linha.quantidade += 1
                linha.receita += receita_da_venda
                linha.custo += custo_da_venda

        for linha in por_vendedor.values():
            linha.comissao = dinheiro(linha.receita * comissoes.get(linha.nome.lower(), 0.0) / 100)
        for linha in (*produtos.values(), *por_vendedor.values()):
            linha.receita = dinheiro(linha.receita)
            linha.custo = dinheiro(linha.custo)

        resultado.receita = dinheiro(resultado.receita)
        resultado.custo = dinheiro(resultado.custo)
        resultado.comissoes = dinheiro(sum(v.comissao for v in por_vendedor.values()))
        resultado.produtos = sorted(produtos.values(), key=lambda l: -l.lucro)[:limite_listas]
        resultado.vendedores = sorted(por_vendedor.values(), key=lambda l: -l.receita)
        return resultado
