"""Regras do DumTech Estoque.

Toda a logica fica aqui, fora da interface: as telas so exibem dados e tudo
pode ser testado sem abrir janela nenhuma. O arquivo unico virou um pacote
porque as regras cresceram - a interface continua importando um nome so,
`EstoqueRepository`.

    produtos.py       cadastro, busca, inativacao, o que comprar
    movimentacoes.py  entrada, saida, ajuste, entrada em lote, historico
    contagem.py       folha de contagem (balanco) e os ajustes que ela gera
    planilha.py       importar e exportar CSV
"""

from __future__ import annotations

from ....core.database import Database
from ..models import Movimentacao, Produto, Resumo
from .compras import ComprasMixin
from .contagem import ContagemMixin
from .movimentacoes import MovimentacoesMixin
from .planilha import PlanilhaMixin
from .produtos import ProdutosMixin

__all__ = ["EstoqueRepository", "Movimentacao", "Produto", "Resumo"]


class EstoqueRepository(ProdutosMixin, MovimentacoesMixin, ContagemMixin, PlanilhaMixin,
                        ComprasMixin):
    """Tudo que o DumTech Estoque sabe fazer."""

    def __init__(self, database: Database) -> None:
        self.db = database

    # ===================================================================== painel
    def resumo(self, limite_listas: int = 6) -> Resumo:
        """Os numeros da tela inicial, numa consulta so por pergunta."""
        return Resumo(
            total_produtos=int(
                self.db.scalar("SELECT COUNT(*) FROM produtos WHERE ativo = 1")
            ),
            total_itens=float(
                self.db.scalar(
                    "SELECT COALESCE(SUM(quantidade), 0) FROM produtos WHERE ativo = 1",
                    default=0.0,
                )
            ),
            produtos_baixo=int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM produtos "
                    "WHERE ativo = 1 AND quantidade <= estoque_minimo"
                )
            ),
            valor_custo=float(
                self.db.scalar(
                    "SELECT COALESCE(SUM(quantidade * preco_custo), 0) FROM produtos "
                    "WHERE ativo = 1",
                    default=0.0,
                )
            ),
            sem_estoque=int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM produtos WHERE ativo = 1 AND quantidade <= 0"
                )
            ),
            valor_venda=float(
                self.db.scalar(
                    "SELECT COALESCE(SUM(MAX(quantidade, 0) * preco_venda), 0) FROM produtos "
                    "WHERE ativo = 1",
                    default=0.0,
                )
            ),
            ultimas=self.listar_movimentacoes(limite=limite_listas),
            baixos=self.a_comprar(limite=limite_listas),
            a_comprar=self.a_comprar(limite=limite_listas),
            maior_valor=self.maior_valor(limite=limite_listas),
            vencendo=self.vencendo(),
        )
