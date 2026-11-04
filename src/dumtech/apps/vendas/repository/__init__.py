"""Regras do DumTech Vendas.

Toda a logica fica aqui, fora da interface: as telas so exibem dados e tudo
pode ser testado sem abrir janela nenhuma. O arquivo unico virou um pacote
porque o modulo deixou de ser um cadastro de vendas e virou um PDV.

    vendas.py       a venda: ler, gravar, cancelar
    pagamentos.py   varias formas na mesma compra, e o troco
    caixa.py        abertura, sangria, suprimento e fechamento do dia
    devolucoes.py   o cliente voltou e trouxe parte (ou tudo) da compra
    indicadores.py  o ritmo do dia e a tendencia (o celular mostra)

O `catalogo` e opcional: com ele, o item vem do DumTech Estoque e a venda da
baixa; sem ele, o item e texto livre e nada mais acontece.
"""

from __future__ import annotations

from datetime import date

from ....core.database import Database
from ..models import Pagamento, ResumoVendas, Venda
from .caixa import CaixaMixin
from .devolucoes import DevolucoesMixin
from .indicadores import IndicadoresMixin
from .pagamentos import PagamentosMixin, pagamento_unico
from .resultado import ResultadoMixin
from .vendas import VendasMixin

__all__ = ["VendasRepository", "Pagamento", "Venda", "ResumoVendas", "pagamento_unico"]


class VendasRepository(VendasMixin, PagamentosMixin, CaixaMixin, DevolucoesMixin,
                       IndicadoresMixin, ResultadoMixin):
    """Tudo que o DumTech Vendas sabe fazer."""

    def __init__(self, database: Database, catalogo=None) -> None:
        self.db = database
        #: catalogo de produtos da plataforma (None quando nao ha Estoque)
        self.catalogo = catalogo

    @property
    def tem_catalogo(self) -> bool:
        return self.catalogo is not None

    # ===================================================================== painel
    def resumo(self, limite_listas: int = 6) -> ResumoVendas:
        hoje = date.today().isoformat()
        mes = date.today().strftime("%Y-%m")
        # soma nao pode ter corte: a loja que vende muito via o mes pela metade
        todas = self.listar(inicio=f"{mes}-01", limite=-1)
        vendas = [v for v in todas if v.conta]
        canceladas = [v for v in todas if not v.conta]
        do_mes = [v for v in vendas if (v.data or "")[:7] == mes]
        total_mes = sum(v.total for v in do_mes)

        por_forma: dict[str, float] = {}
        for venda in do_mes:
            for pagamento in venda.pagamentos:
                por_forma[pagamento.forma] = por_forma.get(pagamento.forma, 0.0) + pagamento.valor
            if not venda.pagamentos:  # venda antiga, de antes do PDV
                chave = venda.forma_pagamento or "Não informado"
                por_forma[chave] = por_forma.get(chave, 0.0) + venda.total

        devolvido = sum(
            d.valor for d in self.listar_devolucoes(inicio=f"{mes}-01", limite=-1)
            if (d.data or "")[:7] == mes
        )

        return ResumoVendas(
            vendas_mes=len(do_mes),
            total_mes=round(total_mes, 2),
            total_hoje=round(sum(v.total for v in vendas if v.data == hoje), 2),
            ticket_medio=round((total_mes / len(do_mes)) if do_mes else 0.0, 2),
            devolvido_mes=round(devolvido, 2),
            cancelado_hoje=round(sum(v.total for v in canceladas if v.data == hoje), 2),
            cancelado_mes=round(
                sum(v.total for v in canceladas if (v.data or "")[:7] == mes), 2
            ),
            caixa=self.caixa_aberto(),
            # o dia 1 tambem tem historico: a lista nao depende do mes
            ultimas=[v for v in self.listar(limite=limite_listas * 3) if v.conta][:limite_listas],
            por_forma=sorted(por_forma.items(), key=lambda item: -item[1])[:limite_listas],
        )
