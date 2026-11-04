"""Regras do DumTech Ordem de Servico.

    ordens.py    o cadastro da ordem
    etapas.py    a esteira do servico e o historico com data e hora
    itens.py     pecas e servicos usados no conserto
"""

from __future__ import annotations

from datetime import date

from ....core.database import Database
from ..models import (
    ABERTA,
    AGUARDANDO,
    ANDAMENTO,
    CONCLUIDA,
    EventoOS,
    ItemOS,
    Ordem,
    ResumoOrdens,
)
from .etapas import EtapasMixin
from .itens import ItensMixin
from .anexos import AnexosMixin
from .ordens import OrdensMixin

__all__ = ["OrdensRepository", "EventoOS", "ItemOS", "Ordem", "ResumoOrdens"]


class OrdensRepository(OrdensMixin, EtapasMixin, ItensMixin, AnexosMixin):
    """Tudo que o DumTech Ordem de Servico sabe fazer."""

    def __init__(self, database: Database, catalogo=None) -> None:
        self.db = database
        #: catalogo do Estoque; None quando a licenca nao libera o modulo.
        #: E ele que faz a peca da ordem sair do saldo quando a ordem e
        #: entregue - antes disso, o material ainda e da casa.
        self.catalogo = catalogo

    # ===================================================================== painel
    def resumo(self, limite_listas: int = 6) -> ResumoOrdens:
        mes = date.today().strftime("%Y-%m")
        # soma nao tem corte: a garantia de um mes movimentado cabe aqui inteira
        todas = self.listar(limite=-1, andamento_primeiro=True)
        por_status = lambda alvo: [o for o in todas if o.status == alvo]  # noqa: E731

        abertas = por_status(ABERTA)
        aguardando = por_status(AGUARDANDO)
        andamento = por_status(ANDAMENTO)
        entregues_mes = [o for o in todas if (o.entregue_em or "")[:7] == mes]

        tempos = [o.dias_em_aberto for o in entregues_mes]
        return ResumoOrdens(
            abertas=len(abertas),
            aguardando=len(aguardando),
            em_andamento=len(andamento),
            atrasadas=len([o for o in todas if o.atrasada]),
            concluidas_mes=len(entregues_mes),
            valor_mes=round(sum(o.total for o in entregues_mes), 2),
            pecas_mes=round(sum(o.total_pecas for o in entregues_mes), 2),
            servicos_mes=round(sum(o.total_servicos for o in entregues_mes), 2),
            tempo_medio=round(sum(tempos) / len(tempos), 1) if tempos else 0.0,
            fila=(abertas + andamento)[:limite_listas],
            prontas=por_status(CONCLUIDA)[:limite_listas],
            prontas_total=len(por_status(CONCLUIDA)),
            aguardando_lista=aguardando[:limite_listas],
        )

    def por_etapa(self) -> dict[str, list[Ordem]]:
        """As faixas do quadro: cada etapa com as suas ordens."""
        faixas: dict[str, list[Ordem]] = {}
        for ordem in self.listar(limite=-1, andamento_primeiro=True):
            if ordem.na_bancada:
                faixas.setdefault(ordem.status, []).append(ordem)
        return faixas
