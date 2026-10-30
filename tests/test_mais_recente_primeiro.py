"""Historico se le de cima para baixo: o mais recente primeiro, em todo o Hub.

A excecao e o que ainda vai acontecer: a lista "Em aberto" do Financeiro e a
agenda seguem do mais proximo para o mais longe, porque ali a pergunta e "o que
vem agora?". O fluxo de caixa e o painel leem essa mesma lista.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from dumtech.apps.agenda.database import open_database as abrir_agenda
from dumtech.apps.agenda.models import CONCLUIDO, Compromisso
from dumtech.apps.agenda.repository import AgendaRepository
from dumtech.apps.financeiro.contas import abrir_contas
from dumtech.apps.financeiro.models import CAIXA, RECEITA, Conta, Lancamento
from dumtech.apps.financeiro.repository import (
    SITUACAO_ABERTO,
    SITUACAO_PAGO,
    SITUACAO_VENCIDO,
)
from dumtech.apps.ordens.database import open_database as abrir_ordens
from dumtech.apps.ordens.models import AGUARDANDO, ANDAMENTO, ABERTA, CANCELADA, Ordem
from dumtech.apps.ordens.repository import OrdensRepository
from dumtech.core.contas import AReceber


def _dias(quantos: int) -> str:
    return (date.today() + timedelta(days=quantos)).isoformat()


class FinanceiroTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.contas = abrir_contas(Path(tempfile.mkdtemp()) / "financeiro.db")
        self.addCleanup(self.contas.close)
        self.repo = self.contas.repository

    def _lancar(self, vencimento: str, pago: bool = False) -> Lancamento:
        lancamento = self.repo.criar(Lancamento(
            tipo=RECEITA, descricao=f"Conta de {vencimento}", valor=10.0,
            vencimento=vencimento,
        ))
        if pago:
            self.repo.baixar(lancamento.id, data=vencimento)
        return lancamento

    def _vencimentos(self, **filtros) -> list[str]:
        return [item.vencimento for item in self.repo.listar(**filtros)]

    def test_lancamentos_do_mais_recente_para_o_mais_antigo(self) -> None:
        """Pago e em aberto juntos: a data manda, nao a situacao."""
        self._lancar(_dias(-30), pago=True)
        self._lancar(_dias(-1), pago=True)
        self._lancar(_dias(-60))
        self._lancar(_dias(0))

        self.assertEqual(self._vencimentos(),
                         [_dias(0), _dias(-1), _dias(-30), _dias(-60)])

    def test_pagos_vencidos_seguem_a_mesma_regra(self) -> None:
        self._lancar(_dias(-30), pago=True)
        self._lancar(_dias(-1), pago=True)
        self._lancar(_dias(-20))
        self._lancar(_dias(-2))

        self.assertEqual(self._vencimentos(situacao=SITUACAO_PAGO),
                         [_dias(-1), _dias(-30)])
        self.assertEqual(self._vencimentos(situacao=SITUACAO_VENCIDO),
                         [_dias(-2), _dias(-20)])

    def test_o_limite_corta_o_mais_antigo(self) -> None:
        """De 500 em diante some o que ja passou, nunca o que acabou de entrar."""
        self._lancar(_dias(-30), pago=True)
        self._lancar(_dias(-1), pago=True)
        self.assertEqual(self._vencimentos(limite=1), [_dias(-1)])

    def test_em_aberto_segue_pelo_que_vence_primeiro(self) -> None:
        """E uma agenda: o fluxo de caixa e o painel leem esta mesma lista."""
        self._lancar(_dias(30))
        self._lancar(_dias(1))
        self._lancar(_dias(-5))

        self.assertEqual(self._vencimentos(situacao=SITUACAO_ABERTO),
                         [_dias(-5), _dias(1), _dias(30)])

    def test_ver_baixas_mostra_a_ultima_em_cima(self) -> None:
        lancamento = self._lancar(_dias(-10))
        self.repo.baixar(lancamento.id, valor=3.0, data=_dias(-9))
        self.repo.baixar(lancamento.id, valor=3.0, data=_dias(-2))

        self.assertEqual([b.data for b in self.repo.baixas_de(lancamento.id)],
                         [_dias(-2), _dias(-9)])

    def test_devolucao_sai_pela_conta_da_ultima_baixa(self) -> None:
        """Mudar a ordem da lista nao pode mudar de onde o dinheiro sai."""
        caixa = self.repo.criar_conta(Conta(nome="Caixa", tipo=CAIXA))
        banco = self.repo.criar_conta(Conta(nome="Banco", tipo=CAIXA))
        self.contas.lancar(AReceber(descricao="Venda VEN-1", valor=100.0,
                                    vencimento=_dias(-10), documento="VEN-1"))
        receita = self.contas._achar("VEN-1")
        self.repo.baixar(receita.id, valor=50.0, data=_dias(-9), conta_id=caixa.id)
        self.repo.baixar(receita.id, valor=50.0, data=_dias(-2), conta_id=banco.id)

        self.assertTrue(self.contas.devolver("VEN-1", 20.0, _dias(0)))

        saida = next(item for item in self.repo.listar() if not item.e_receita)
        self.assertEqual(saida.conta_id, banco.id)


class OrdensTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = abrir_ordens(Path(tempfile.mkdtemp()) / "ordens.db")
        self.addCleanup(self.db.close)
        self.repo = OrdensRepository(self.db)

    def _ordem(self, aberta_em: str) -> Ordem:
        return self.repo.salvar(Ordem(
            numero=self.repo.proximo_numero(), cliente="Ana", defeito="Revisar",
            aberta_em=aberta_em,
        ))

    def test_historico_da_ordem_comeca_pelo_ultimo_passo(self) -> None:
        ordem = self._ordem(_dias(0))
        self.repo.avancar(ordem.id)
        self.repo.aprovar(ordem.id, "Ana")

        self.assertEqual([e.status for e in self.repo.historico_de(ordem.id)],
                         [ANDAMENTO, AGUARDANDO, ABERTA])

    def test_todas_as_ordens_vao_pela_data_de_entrada(self) -> None:
        """A cancelada de ontem vem antes da aberta do mes passado."""
        antiga = self._ordem(_dias(-30))
        nova = self._ordem(_dias(-1))
        self.repo.cancelar(nova.id, "Desistiu")

        ordens = self.repo.listar()

        self.assertEqual([o.id for o in ordens], [nova.id, antiga.id])
        self.assertEqual(ordens[0].status, CANCELADA)

    def test_painel_e_quadro_nao_perdem_ordem_antiga_em_andamento(self) -> None:
        """Eles leem ate mil: a que esta na bancada nao pode cair no corte."""
        antiga = self._ordem(_dias(-30))
        nova = self._ordem(_dias(-1))
        self.repo.cancelar(nova.id, "Desistiu")

        self.assertEqual(
            [o.id for o in self.repo.listar(limite=1, andamento_primeiro=True)],
            [antiga.id],
        )


class AgendaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = abrir_agenda(Path(tempfile.mkdtemp()) / "agenda.db")
        self.addCleanup(self.db.close)
        self.repo = AgendaRepository(self.db)

    def _compromisso(self, dias: int, status: str = "") -> Compromisso:
        quando = f"{_dias(dias)}T10:00:00"
        compromisso = Compromisso(titulo=f"Visita {dias}", inicio=quando)
        if status:
            compromisso.status = status
        return self.repo.salvar(compromisso)

    def test_concluidos_sao_historico(self) -> None:
        self._compromisso(-20, CONCLUIDO)
        self._compromisso(-1, CONCLUIDO)

        self.assertEqual([c.titulo for c in self.repo.listar(status=CONCLUIDO)],
                         ["Visita -1", "Visita -20"])

    def test_o_que_vem_pela_frente_segue_na_ordem_do_dia(self) -> None:
        self._compromisso(5)
        self._compromisso(1)

        self.assertEqual([c.titulo for c in self.repo.listar()],
                         ["Visita 1", "Visita 5"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
