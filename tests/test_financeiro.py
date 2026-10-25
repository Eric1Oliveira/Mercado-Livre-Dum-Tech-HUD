"""Regras do fluxo de caixa: parcelamento, baixa parcial, contas e projecao."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from dumtech.apps.financeiro.database import MIGRATIONS, open_database
from dumtech.apps.financeiro.models import (
    BANCO,
    CAIXA,
    DESPESA,
    QUINZENAL,
    RECEITA,
    SEMANAL,
    Conta,
    FinanceiroError,
    Lancamento,
)
from dumtech.apps.financeiro.repository import FinanceiroRepository, dividir


def _arquivo(nome: str) -> Path:
    return Path(tempfile.mkdtemp()) / nome


def dia(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


class FinanceiroBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = open_database(_arquivo("financeiro.db"))
        self.repo = FinanceiroRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _lancamento(self, **campos) -> Lancamento:
        dados = dict(
            tipo=RECEITA, descricao="Servico prestado", valor=1000.0, vencimento=dia(5)
        )
        dados.update(campos)
        return self.repo.criar(Lancamento(**dados))

    def _conta(self, nome="Banco do Brasil", **campos) -> Conta:
        dados = dict(nome=nome, tipo=BANCO, saldo_inicial=0.0)
        dados.update(campos)
        return self.repo.criar_conta(Conta(**dados))


class ParcelamentoTestCase(FinanceiroBase):
    def test_divide_em_centavos_exatos_com_a_sobra_na_primeira(self) -> None:
        self.assertEqual(dividir(1000.0, 3), [333.34, 333.33, 333.33])
        self.assertEqual(dividir(1200.0, 3), [400.0, 400.0, 400.0])
        self.assertEqual(sum(dividir(0.10, 3)), 0.10)

    def test_parcelar_gera_contas_de_verdade(self) -> None:
        parcelas = self.repo.parcelar(
            Lancamento(tipo=DESPESA, descricao="Compra de equipamento",
                       valor=1200.0, vencimento=dia(10)),
            3,
        )
        self.assertEqual(len(parcelas), 3)
        self.assertEqual([p.valor for p in parcelas], [400.0, 400.0, 400.0])
        self.assertEqual([p.parcela for p in parcelas], [1, 2, 3])
        self.assertEqual(parcelas[0].rotulo_parcela, "1/3")
        # cada parcela e um lancamento proprio, com vencimento proprio
        self.assertEqual(len(self.repo.listar()), 3)
        self.assertNotEqual(parcelas[0].vencimento, parcelas[1].vencimento)
        # e todas ligadas pelo mesmo grupo
        self.assertEqual(len(self.repo.do_grupo(parcelas[0].grupo)), 3)

    def test_parcela_pode_ser_paga_sozinha(self) -> None:
        parcelas = self.repo.parcelar(
            Lancamento(tipo=DESPESA, descricao="Fornecedor", valor=900.0,
                       vencimento=dia(1)),
            3,
        )
        self.repo.baixar(parcelas[0].id)
        self.assertTrue(self.repo.obter(parcelas[0].id).pago)
        self.assertFalse(self.repo.obter(parcelas[1].id).pago)

    def test_serie_precisa_de_pelo_menos_duas(self) -> None:
        with self.assertRaises(FinanceiroError):
            self.repo.parcelar(Lancamento(descricao="X", valor=10.0), 1)

    def test_recorrencia_repete_o_mesmo_valor(self) -> None:
        itens = self.repo.repetir(
            Lancamento(tipo=DESPESA, descricao="Aluguel", valor=2200.0,
                       vencimento="2026-01-10"),
            12,
        )
        self.assertEqual(len(itens), 12)
        self.assertTrue(all(i.valor == 2200.0 for i in itens))
        self.assertEqual(itens[0].vencimento, "2026-01-10")
        self.assertEqual(itens[11].vencimento, "2026-12-10")

    def test_dia_31_usa_o_ultimo_dia_do_mes_curto(self) -> None:
        itens = self.repo.repetir(
            Lancamento(tipo=DESPESA, descricao="Assinatura", valor=99.0,
                       vencimento="2026-01-31"),
            3,
        )
        self.assertEqual(
            [i.vencimento for i in itens], ["2026-01-31", "2026-02-28", "2026-03-31"]
        )

    def test_frequencias_semanal_e_quinzenal(self) -> None:
        semanal = self.repo.repetir(
            Lancamento(descricao="Feira", valor=100.0, vencimento="2026-03-02"),
            3, SEMANAL,
        )
        self.assertEqual([i.vencimento for i in semanal],
                         ["2026-03-02", "2026-03-09", "2026-03-16"])

        quinzenal = self.repo.repetir(
            Lancamento(descricao="Comissao", valor=100.0, vencimento="2026-03-01"),
            3, QUINZENAL,
        )
        self.assertEqual([i.vencimento for i in quinzenal],
                         ["2026-03-01", "2026-03-16", "2026-03-31"])

    def test_excluir_serie_preserva_o_que_ja_foi_pago(self) -> None:
        parcelas = self.repo.parcelar(
            Lancamento(tipo=DESPESA, descricao="Compra", valor=300.0, vencimento=dia(0)),
            3,
        )
        self.repo.baixar(parcelas[0].id)
        apagadas = self.repo.excluir_grupo(parcelas[0].grupo)
        self.assertEqual(apagadas, 2)
        self.assertIsNotNone(self.repo.obter(parcelas[0].id))


class BaixaTestCase(FinanceiroBase):
    def test_baixa_parcial_deixa_o_resto_em_aberto(self) -> None:
        lancamento = self._lancamento(valor=1000.0)
        self.repo.baixar(lancamento.id, 300.0)

        salvo = self.repo.obter(lancamento.id)
        self.assertEqual(salvo.baixado, 300.0)
        self.assertEqual(salvo.em_aberto, 700.0)
        self.assertFalse(salvo.pago)
        self.assertTrue(salvo.parcial)
        self.assertEqual(salvo.situacao, "Parcial")

    def test_a_ultima_baixa_quita_o_lancamento(self) -> None:
        lancamento = self._lancamento(valor=1000.0)
        self.repo.baixar(lancamento.id, 300.0, data=dia(-2))
        self.repo.baixar(lancamento.id, 700.0, data=dia(-1))

        salvo = self.repo.obter(lancamento.id)
        self.assertTrue(salvo.pago)
        self.assertEqual(salvo.em_aberto, 0.0)
        # a data de quitacao e a da ultima baixa, nao a de hoje
        self.assertEqual(salvo.pago_em, dia(-1))

    def test_baixa_sem_valor_quita_o_que_falta(self) -> None:
        lancamento = self._lancamento(valor=500.0)
        self.repo.baixar(lancamento.id, 200.0)
        baixa = self.repo.baixar(lancamento.id)
        self.assertEqual(baixa.valor, 300.0)
        self.assertTrue(self.repo.obter(lancamento.id).pago)

    def test_nao_baixa_mais_do_que_falta(self) -> None:
        lancamento = self._lancamento(valor=500.0)
        self.repo.baixar(lancamento.id, 400.0)
        with self.assertRaises(FinanceiroError) as erro:
            self.repo.baixar(lancamento.id, 200.0)
        self.assertIn("R$ 100,00", str(erro.exception))

    def test_estornar_desfaz_so_uma_baixa(self) -> None:
        lancamento = self._lancamento(valor=1000.0)
        primeira = self.repo.baixar(lancamento.id, 400.0)
        self.repo.baixar(lancamento.id, 600.0)
        self.assertTrue(self.repo.obter(lancamento.id).pago)

        self.repo.estornar(primeira.id)
        salvo = self.repo.obter(lancamento.id)
        self.assertFalse(salvo.pago)
        self.assertEqual(salvo.baixado, 600.0)
        self.assertEqual(len(self.repo.baixas_de(lancamento.id)), 1)

    def test_botao_de_um_clique_quita_e_desfaz(self) -> None:
        lancamento = self._lancamento(valor=250.0)
        self.assertTrue(self.repo.alternar_pagamento(lancamento.id).pago)
        self.assertFalse(self.repo.alternar_pagamento(lancamento.id).pago)
        self.assertEqual(self.repo.baixas_de(lancamento.id), [])

    def test_lancamento_criado_ja_pago_gera_a_baixa(self) -> None:
        lancamento = self._lancamento(valor=80.0, pago_em=dia(0))
        self.assertEqual(len(self.repo.baixas_de(lancamento.id)), 1)
        self.assertEqual(self.repo.obter(lancamento.id).baixado, 80.0)

    def test_nao_reduz_o_valor_abaixo_do_que_ja_foi_baixado(self) -> None:
        lancamento = self._lancamento(valor=1000.0)
        self.repo.baixar(lancamento.id, 600.0)
        salvo = self.repo.obter(lancamento.id)
        salvo.valor = 500.0
        with self.assertRaises(FinanceiroError):
            self.repo.atualizar(salvo)


class ContasTestCase(FinanceiroBase):
    def test_saldo_soma_inicial_e_baixas(self) -> None:
        conta = self._conta(saldo_inicial=1000.0)
        receita = self._lancamento(valor=500.0)
        despesa = self._lancamento(tipo=DESPESA, descricao="Energia", valor=200.0)
        self.repo.baixar(receita.id, conta_id=conta.id)
        self.repo.baixar(despesa.id, conta_id=conta.id)

        self.assertEqual(self.repo.obter_conta(conta.id).saldo, 1300.0)
        self.assertEqual(self.repo.saldo_total(), 1300.0)

    def test_nome_repetido_e_recusado(self) -> None:
        self._conta("Caixa da loja")
        with self.assertRaises(FinanceiroError):
            self._conta("caixa da loja")

    def test_conta_com_movimento_nao_e_apagada(self) -> None:
        conta = self._conta()
        lancamento = self._lancamento(valor=100.0)
        self.repo.baixar(lancamento.id, conta_id=conta.id)

        with self.assertRaises(FinanceiroError):
            self.repo.excluir_conta(conta.id)

        self.repo.inativar_conta(conta.id)
        self.assertEqual(self.repo.listar_contas(), [])
        self.assertEqual(len(self.repo.listar_contas(incluir_inativas=True)), 1)

    def test_conta_sem_movimento_pode_sumir(self) -> None:
        conta = self._conta("Conta errada")
        self.repo.excluir_conta(conta.id)
        self.assertIsNone(self.repo.obter_conta(conta.id))

    def test_transferencia_move_sem_virar_receita_ou_despesa(self) -> None:
        banco = self._conta("Banco", saldo_inicial=1000.0)
        caixa = self._conta("Caixa", tipo=CAIXA, saldo_inicial=100.0)

        self.repo.transferir(banco.id, caixa.id, 300.0)

        self.assertEqual(self.repo.obter_conta(banco.id).saldo, 700.0)
        self.assertEqual(self.repo.obter_conta(caixa.id).saldo, 400.0)
        # o total nao muda: dinheiro so trocou de lugar
        self.assertEqual(self.repo.saldo_total(), 1100.0)

        resumo = self.repo.resumo()
        self.assertEqual(resumo.recebido_mes, 0.0)
        self.assertEqual(resumo.pago_mes, 0.0)

    def test_transferencia_para_a_mesma_conta_e_recusada(self) -> None:
        conta = self._conta()
        with self.assertRaises(FinanceiroError):
            self.repo.transferir(conta.id, conta.id, 100.0)

    def test_conta_padrao_prefere_o_caixa(self) -> None:
        self._conta("Banco")
        caixa = self._conta("Caixa", tipo=CAIXA)
        self.assertEqual(self.repo.conta_padrao().id, caixa.id)


class ProjecaoTestCase(FinanceiroBase):
    def test_projecao_parte_do_saldo_de_hoje(self) -> None:
        self._conta(saldo_inicial=500.0)
        projecao = self.repo.projecao()
        self.assertEqual(projecao.saldo_inicial, 500.0)
        self.assertEqual(projecao.saldo_final, 500.0)
        self.assertIsNone(projecao.dia_no_vermelho)
        self.assertEqual(len(projecao.dias), 31)

    def test_entradas_e_saidas_caem_no_dia_do_vencimento(self) -> None:
        self._conta(saldo_inicial=1000.0)
        self._lancamento(valor=300.0, vencimento=dia(5))
        self._lancamento(tipo=DESPESA, descricao="Aluguel", valor=800.0,
                         vencimento=dia(10))

        projecao = self.repo.projecao()
        por_data = {d.data: d for d in projecao.dias}
        self.assertEqual(por_data[dia(5)].entradas, 300.0)
        self.assertEqual(por_data[dia(5)].saldo, 1300.0)
        self.assertEqual(por_data[dia(10)].saidas, 800.0)
        self.assertEqual(por_data[dia(10)].saldo, 500.0)
        self.assertEqual(projecao.saldo_final, 500.0)

    def test_diz_o_dia_em_que_o_dinheiro_acaba(self) -> None:
        self._conta(saldo_inicial=100.0)
        self._lancamento(tipo=DESPESA, descricao="Fornecedor", valor=500.0,
                         vencimento=dia(7))

        projecao = self.repo.projecao()
        vermelho = projecao.dia_no_vermelho
        self.assertIsNotNone(vermelho)
        self.assertEqual(vermelho.data, dia(7))
        self.assertEqual(vermelho.saldo, -400.0)
        self.assertEqual(projecao.menor_saldo, -400.0)

    def test_atrasado_entra_no_dia_de_hoje_e_e_contado_a_parte(self) -> None:
        self._conta(saldo_inicial=0.0)
        self._lancamento(valor=200.0, vencimento=dia(-10))
        self._lancamento(tipo=DESPESA, descricao="Conta vencida", valor=50.0,
                         vencimento=dia(-3))

        projecao = self.repo.projecao()
        hoje = projecao.dias[0]
        self.assertEqual(hoje.data, dia(0))
        self.assertEqual(hoje.entradas, 200.0)
        self.assertEqual(hoje.saidas, 50.0)
        self.assertTrue(hoje.atrasado)
        self.assertEqual(projecao.atrasado_receber, 200.0)
        self.assertEqual(projecao.atrasado_pagar, 50.0)

    def test_so_o_que_falta_entra_na_projecao(self) -> None:
        self._conta(saldo_inicial=0.0)
        lancamento = self._lancamento(valor=1000.0, vencimento=dia(3))
        self.repo.baixar(lancamento.id, 600.0)

        projecao = self.repo.projecao()
        por_data = {d.data: d for d in projecao.dias}
        self.assertEqual(por_data[dia(3)].entradas, 400.0)

    def test_o_que_vence_depois_do_horizonte_fica_de_fora(self) -> None:
        self._conta(saldo_inicial=0.0)
        self._lancamento(valor=5000.0, vencimento=dia(60))
        self.assertEqual(self.repo.projecao().saldo_final, 0.0)


class ResumoTestCase(FinanceiroBase):
    def test_o_mes_conta_pela_data_da_baixa(self) -> None:
        """Recebi hoje uma conta que vencia mes passado: entra no mes de hoje."""
        lancamento = self._lancamento(valor=400.0, vencimento=dia(-40))
        self.repo.baixar(lancamento.id, data=dia(0))
        self.assertEqual(self.repo.resumo().recebido_mes, 400.0)

    def test_a_receber_desconta_o_que_ja_entrou(self) -> None:
        lancamento = self._lancamento(valor=1000.0)
        self.repo.baixar(lancamento.id, 250.0)
        resumo = self.repo.resumo()
        self.assertEqual(resumo.a_receber, 750.0)
        self.assertEqual(resumo.a_pagar, 0.0)

    def test_vencidos_e_proximos_ficam_separados(self) -> None:
        self._lancamento(descricao="Atrasada", valor=100.0, vencimento=dia(-5))
        self._lancamento(descricao="Futura", valor=200.0, vencimento=dia(5))

        resumo = self.repo.resumo()
        self.assertEqual(resumo.vencidos_quantidade, 1)
        self.assertEqual(resumo.vencidos_valor, 100.0)
        self.assertEqual([i.descricao for i in resumo.atrasados], ["Atrasada"])
        self.assertEqual([i.descricao for i in resumo.proximos], ["Futura"])

    def test_para_onde_o_dinheiro_foi_no_mes(self) -> None:
        for categoria, valor in (("Fixas", 2200.0), ("Compras", 800.0), ("Fixas", 380.0)):
            item = self._lancamento(
                tipo=DESPESA, descricao=f"Despesa {categoria}", categoria=categoria,
                valor=valor, vencimento=dia(0),
            )
            self.repo.baixar(item.id)

        self.assertEqual(
            self.repo.resumo().por_categoria, [("Fixas", 2580.0), ("Compras", 800.0)]
        )


class DespesaFixaTestCase(FinanceiroBase):
    """Aluguel e internet separados do que varia com o movimento do mes."""

    def test_grava_le_e_edita_a_marca_de_fixa(self) -> None:
        aluguel = self._lancamento(tipo=DESPESA, descricao="Aluguel", fixa=True)
        self.assertTrue(self.repo.obter(aluguel.id).fixa)

        aluguel.fixa = False
        self.repo.atualizar(aluguel)
        self.assertFalse(self.repo.obter(aluguel.id).fixa)

    def test_receita_nunca_fica_marcada_como_fixa(self) -> None:
        venda = self._lancamento(tipo=RECEITA, fixa=True)
        self.assertFalse(self.repo.obter(venda.id).fixa)

    def test_a_recorrencia_inteira_herda_a_marca(self) -> None:
        base = Lancamento(tipo=DESPESA, descricao="Internet", valor=120.0,
                          vencimento=dia(0), fixa=True)
        criados = self.repo.repetir(base, 3)
        self.assertTrue(all(self.repo.obter(item.id).fixa for item in criados))

    def test_filtra_fixas_e_variaveis(self) -> None:
        self._lancamento(tipo=DESPESA, descricao="Aluguel", fixa=True)
        self._lancamento(tipo=DESPESA, descricao="Frete")
        self._lancamento(tipo=RECEITA, descricao="Venda")

        fixas = self.repo.listar(tipo=DESPESA, fixa=True)
        variaveis = self.repo.listar(tipo=DESPESA, fixa=False)
        self.assertEqual([i.descricao for i in fixas], ["Aluguel"])
        self.assertEqual([i.descricao for i in variaveis], ["Frete"])

    def test_resumo_separa_o_pago_no_mes(self) -> None:
        for descricao, valor, fixa in (("Aluguel", 2200.0, True), ("Frete", 300.0, False)):
            item = self._lancamento(tipo=DESPESA, descricao=descricao, valor=valor,
                                    vencimento=dia(0), fixa=fixa)
            self.repo.baixar(item.id)

        resumo = self.repo.resumo()
        self.assertEqual(resumo.pago_mes, 2500.0)
        self.assertEqual(resumo.pago_fixas_mes, 2200.0)
        self.assertEqual(resumo.pago_variaveis_mes, 300.0)


class MigracaoTestCase(unittest.TestCase):
    """Quem ja usava a versao 1 nao pode perder lancamento nem pagamento."""

    def test_v1_vira_v2_e_o_que_estava_pago_vira_baixa(self) -> None:
        arquivo = _arquivo("financeiro.db")
        conn = sqlite3.connect(arquivo)
        conn.executescript(MIGRATIONS[0].statements[0])
        conn.execute(
            "INSERT INTO lancamentos (id, tipo, descricao, categoria, cliente, valor,"
            " vencimento, pago_em, forma_pagamento, observacoes, criado_em)"
            " VALUES (1, 'receita', 'Venda antiga', 'Vendas', 'Maria', 500.0,"
            " '2026-01-10', '2026-01-12', 'Pix', 'ok', '2026-01-05T10:00:00')"
        )
        conn.execute(
            "INSERT INTO lancamentos (id, tipo, descricao, categoria, cliente, valor,"
            " vencimento, pago_em, forma_pagamento, observacoes, criado_em)"
            " VALUES (2, 'despesa', 'Conta em aberto', 'Fixas', '', 300.0,"
            " '2026-02-10', NULL, '', '', '2026-01-05T10:00:00')"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        db = open_database(arquivo)
        self.addCleanup(db.close)
        repo = FinanceiroRepository(db)
        self.assertEqual(db.schema_version, 3)

        paga = repo.obter(1)
        self.assertEqual(paga.descricao, "Venda antiga")
        self.assertTrue(paga.pago)
        self.assertEqual(paga.baixado, 500.0)
        self.assertEqual(paga.em_aberto, 0.0)
        # o pagamento antigo virou baixa, na data em que aconteceu
        baixas = repo.baixas_de(1)
        self.assertEqual(len(baixas), 1)
        self.assertEqual(baixas[0].data, "2026-01-12")
        self.assertEqual(baixas[0].forma, "Pix")

        aberta = repo.obter(2)
        self.assertFalse(aberta.pago)
        self.assertEqual(repo.baixas_de(2), [])
        # campos novos chegam com padrao util
        self.assertEqual(aberta.conta_id, 0)
        self.assertEqual(aberta.grupo, "")
        # o que ja existia nasce variavel
        self.assertFalse(aberta.fixa)

        # e o banco migrado continua funcionando
        conta = repo.criar_conta(Conta(nome="Caixa", tipo=CAIXA, saldo_inicial=50.0))
        repo.baixar(2, 100.0, conta_id=conta.id)
        self.assertEqual(repo.obter_conta(conta.id).saldo, -50.0)


if __name__ == "__main__":
    unittest.main()
