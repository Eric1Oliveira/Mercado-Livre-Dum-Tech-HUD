"""Testes das regras dos aplicativos da plataforma (sem abrir janela)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from dumtech.core.contacts import Contato, ContactsStore, ContatoError


def _arquivo(nome: str) -> Path:
    return Path(tempfile.mkdtemp()) / nome


class ClientesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.store = ContactsStore(_arquivo("plataforma.db"))

    def tearDown(self) -> None:
        self.store.close()

    def test_cadastra_e_pesquisa(self) -> None:
        self.store.criar(Contato(nome="Joao da Silva", cidade="Palmas", telefone="63 99999-0000"))
        self.store.criar(Contato(nome="Maria Souza", cidade="Goiania"))
        self.assertEqual(self.store.total(), 2)
        self.assertEqual(len(self.store.listar("joao")), 1)
        self.assertEqual(len(self.store.listar("goiania")), 1)
        self.assertIn("Maria Souza", self.store.nomes())

    def test_nome_obrigatorio(self) -> None:
        with self.assertRaises(ContatoError):
            self.store.criar(Contato(nome="   "))

    def test_edita_e_exclui(self) -> None:
        contato = self.store.criar(Contato(nome="Cliente Teste"))
        contato.telefone = "(63) 98888-1111"
        self.store.atualizar(contato)
        # o telefone e guardado so com digitos e formatado na hora de exibir
        salvo = self.store.obter(contato.id)
        self.assertEqual(salvo.telefone, "63988881111")
        self.assertEqual(salvo.telefone_formatado, "(63) 98888-1111")
        self.store.excluir(contato.id)
        self.assertEqual(self.store.total(), 0)


class FinanceiroTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from dumtech.apps.financeiro.database import open_database
        from dumtech.apps.financeiro.repository import FinanceiroRepository

        self.db = open_database(_arquivo("financeiro.db"))
        self.repo = FinanceiroRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _lancamento(self, **campos):
        from dumtech.apps.financeiro.models import RECEITA, Lancamento

        dados = dict(tipo=RECEITA, descricao="Venda 1", valor=100.0,
                     vencimento=date.today().isoformat())
        dados.update(campos)
        return self.repo.criar(Lancamento(**dados))

    def test_valor_precisa_ser_positivo(self) -> None:
        from dumtech.apps.financeiro.models import FinanceiroError

        with self.assertRaises(FinanceiroError):
            self._lancamento(valor=0)

    def test_marcar_como_pago_e_desfazer(self) -> None:
        lancamento = self._lancamento()
        self.assertFalse(lancamento.pago)
        self.repo.alternar_pagamento(lancamento.id)
        self.assertTrue(self.repo.obter(lancamento.id).pago)
        self.repo.alternar_pagamento(lancamento.id)
        self.assertFalse(self.repo.obter(lancamento.id).pago)

    def test_resumo_separa_receitas_e_despesas(self) -> None:
        from dumtech.apps.financeiro.models import DESPESA

        self._lancamento(valor=300.0)
        self._lancamento(tipo=DESPESA, descricao="Aluguel", valor=200.0)
        resumo = self.repo.resumo()
        self.assertEqual(resumo.a_receber, 300.0)
        self.assertEqual(resumo.a_pagar, 200.0)

    def test_conta_vencida_entra_no_resumo(self) -> None:
        ontem = (date.today() - timedelta(days=2)).isoformat()
        self._lancamento(vencimento=ontem)
        resumo = self.repo.resumo()
        self.assertEqual(resumo.vencidos_quantidade, 1)
        self.assertEqual(len(self.repo.listar(situacao="vencido")), 1)


class OrcamentosTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from dumtech.apps.orcamentos.database import open_database
        from dumtech.apps.orcamentos.repository import OrcamentosRepository

        self.db = open_database(_arquivo("orcamentos.db"))
        self.repo = OrcamentosRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _orcamento(self, **campos):
        from dumtech.apps.orcamentos.models import ItemOrcamento, Orcamento

        dados = dict(
            numero=self.repo.proximo_numero(),
            cliente="Joao",
            itens=[ItemOrcamento(descricao="Servico", quantidade=2, valor_unitario=150.0)],
        )
        dados.update(campos)
        return self.repo.salvar(Orcamento(**dados))

    def test_numero_automatico_e_total(self) -> None:
        orcamento = self._orcamento()
        self.assertTrue(orcamento.numero.startswith("ORC-"))
        self.assertEqual(orcamento.total, 300.0)
        self.assertEqual(len(self.repo.listar()), 1)

    def test_exige_itens_e_cliente(self) -> None:
        from dumtech.apps.orcamentos.models import OrcamentoError

        with self.assertRaises(OrcamentoError):
            self._orcamento(itens=[])
        with self.assertRaises(OrcamentoError):
            self._orcamento(cliente="  ")

    def test_desconto_nao_passa_do_total(self) -> None:
        from dumtech.apps.orcamentos.models import OrcamentoError

        with self.assertRaises(OrcamentoError):
            self._orcamento(desconto=1000.0)

    def test_aprovar_entra_no_resumo(self) -> None:
        orcamento = self._orcamento()
        self.repo.aprovar(orcamento.id)
        resumo = self.repo.resumo()
        self.assertEqual(resumo.aprovados_mes, 1)
        self.assertEqual(resumo.valor_aprovado_mes, 300.0)

    def test_itens_sao_regravados_na_edicao(self) -> None:
        from dumtech.apps.orcamentos.models import ItemOrcamento

        orcamento = self._orcamento()
        orcamento.itens = [ItemOrcamento(descricao="Novo", quantidade=1, valor_unitario=50.0)]
        self.repo.salvar(orcamento)
        salvo = self.repo.obter(orcamento.id)
        self.assertEqual(len(salvo.itens), 1)
        self.assertEqual(salvo.total, 50.0)


class VendasTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from dumtech.apps.vendas.database import open_database
        from dumtech.apps.vendas.repository import VendasRepository

        self.db = open_database(_arquivo("vendas.db"))
        self.repo = VendasRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _venda(self, **campos):
        from dumtech.apps.vendas.models import ItemVenda, Venda

        dados = dict(
            numero=self.repo.proximo_numero(),
            cliente="Maria",
            forma_pagamento="Pix",
            itens=[ItemVenda(descricao="Produto", quantidade=3, valor_unitario=20.0)],
        )
        dados.update(campos)
        return self.repo.salvar(Venda(**dados))

    def test_total_e_desconto(self) -> None:
        venda = self._venda(desconto=10.0)
        self.assertEqual(venda.subtotal, 60.0)
        self.assertEqual(venda.total, 50.0)
        self.assertEqual(venda.quantidade_itens, 3)

    def test_venda_precisa_de_itens(self) -> None:
        from dumtech.apps.vendas.models import VendaError

        with self.assertRaises(VendaError):
            self._venda(itens=[])

    def test_cancelada_sai_do_resumo(self) -> None:
        from dumtech.apps.vendas.models import CANCELADA

        venda = self._venda()
        self.assertEqual(self.repo.resumo().vendas_mes, 1)
        self.repo.definir_status(venda.id, CANCELADA)
        self.assertEqual(self.repo.resumo().vendas_mes, 0)

    def test_numero_nao_se_repete(self) -> None:
        from dumtech.apps.vendas.models import VendaError

        venda = self._venda()
        with self.assertRaises(VendaError):
            self._venda(numero=venda.numero)


class OrdensTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from dumtech.apps.ordens.database import open_database
        from dumtech.apps.ordens.repository import OrdensRepository

        self.db = open_database(_arquivo("ordens.db"))
        self.repo = OrdensRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _ordem(self, **campos):
        from dumtech.apps.ordens.models import Ordem

        dados = dict(
            numero=self.repo.proximo_numero(),
            cliente="Carlos",
            equipamento="Notebook",
            defeito="Nao liga",
            valor=250.0,
        )
        dados.update(campos)
        return self.repo.salvar(Ordem(**dados))

    # a esteira (com aprovacao e entrega) vive em tests/test_ordens.py

    def test_conclusao_grava_a_data(self) -> None:
        from dumtech.apps.ordens.models import CONCLUIDA

        ordem = self._ordem()
        self.repo.definir_status(ordem.id, CONCLUIDA)
        self.assertEqual(self.repo.obter(ordem.id).concluida_em, date.today().isoformat())

    def test_campos_obrigatorios(self) -> None:
        """Cliente sempre; e pelo menos dizer o que foi pedido OU qual item.

        Exigir "equipamento" so servia para assistencia tecnica: a lavanderia
        e o instalador escrevem o pedido e nao tem aparelho nenhum para
        nomear. Ficar sem os dois, porem, e uma ordem que nao diz nada.
        """
        from dumtech.apps.ordens.models import OrdemError

        with self.assertRaises(OrdemError):
            self._ordem(cliente="")
        with self.assertRaises(OrdemError):
            self._ordem(equipamento="", defeito="")

        so_pedido = self._ordem(equipamento="", defeito="Instalar a cortina")
        self.assertEqual(so_pedido.equipamento, "")
        so_item = self._ordem(equipamento="Notebook Dell", defeito="")
        self.assertEqual(so_item.defeito, "")

    def test_ordem_atrasada(self) -> None:
        ontem = (date.today() - timedelta(days=1)).isoformat()
        ordem = self._ordem(prazo=ontem)
        self.assertTrue(self.repo.obter(ordem.id).atrasada)
        self.assertEqual(self.repo.resumo().atrasadas, 1)


class AgendaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from dumtech.apps.agenda.database import open_database
        from dumtech.apps.agenda.repository import AgendaRepository

        self.db = open_database(_arquivo("agenda.db"))
        self.repo = AgendaRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _compromisso(self, **campos):
        from dumtech.apps.agenda.models import Compromisso

        inicio = (datetime.now() + timedelta(hours=2)).replace(second=0, microsecond=0)
        dados = dict(
            titulo="Visita tecnica",
            cliente="Joao",
            inicio=inicio.isoformat(),
            duracao_min=60,
        )
        dados.update(campos)
        return self.repo.salvar(Compromisso(**dados))

    def test_titulo_e_duracao_obrigatorios(self) -> None:
        from dumtech.apps.agenda.models import AgendaError

        with self.assertRaises(AgendaError):
            self._compromisso(titulo=" ")
        with self.assertRaises(AgendaError):
            self._compromisso(duracao_min=0)

    def test_compromisso_de_hoje_aparece_no_painel(self) -> None:
        # horario fixo do dia: o teste nao pode depender da hora em que roda
        manha = datetime.combine(date.today(), datetime.min.time()).replace(hour=8)
        self._compromisso(inicio=manha.isoformat(timespec="minutes"))
        self.assertEqual(self.repo.resumo().hoje, 1)

    def test_proximos_mostra_os_futuros(self) -> None:
        futuro = (datetime.now() + timedelta(days=2)).isoformat(timespec="minutes")
        self._compromisso(inicio=futuro)
        self.assertEqual(len(self.repo.resumo().proximos), 1)

    def test_compromisso_passado_fica_atrasado(self) -> None:
        passado = (datetime.now() - timedelta(hours=3)).isoformat(timespec="minutes")
        self._compromisso(inicio=passado)
        self.assertEqual(self.repo.resumo().atrasados, 1)

    def test_concluir_tira_do_atraso(self) -> None:
        from dumtech.apps.agenda.models import CONCLUIDO

        passado = (datetime.now() - timedelta(hours=3)).isoformat(timespec="minutes")
        compromisso = self._compromisso(inicio=passado)
        self.repo.definir_status(compromisso.id, CONCLUIDO)
        self.assertEqual(self.repo.resumo().atrasados, 0)

    def test_filtro_por_periodo(self) -> None:
        from dumtech.apps.agenda.repository import PERIODO_HOJE, PERIODO_SEMANA

        manha = datetime.combine(date.today(), datetime.min.time()).replace(hour=8)
        self._compromisso(inicio=manha.isoformat(timespec="minutes"))
        futuro = (datetime.now() + timedelta(days=20)).isoformat(timespec="minutes")
        self._compromisso(inicio=futuro)
        self.assertEqual(len(self.repo.listar(periodo=PERIODO_HOJE)), 1)
        self.assertEqual(len(self.repo.listar(periodo=PERIODO_SEMANA)), 1)
        self.assertEqual(len(self.repo.listar()), 2)


if __name__ == "__main__":
    unittest.main()
