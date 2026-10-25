"""O celular com numero que responde: comparacao justa, graficos e "precisa de voce".

O que mais importa aqui e a JUSTICA da comparacao. "Vendi 30% menos que
sabado passado" as 10 da manha, comparando com o sabado passado INTEIRO,
seria mentira - e o dono tomaria decisao em cima dela.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from dumtech.core import celular as c
from dumtech.core.paths import DataPaths


def _paths() -> DataPaths:
    return DataPaths(root=Path(tempfile.mkdtemp())).ensure()


class ContratoTestCase(unittest.TestCase):
    def test_variacao_diz_para_onde_foi_e_se_e_bom(self) -> None:
        self.assertEqual(c.variacao(118, 100, "sábado passado"),
                         {"texto": "+18%", "direcao": "sobe", "tom": "ok", "comparado": "sábado passado"})
        self.assertEqual(c.variacao(80, 100, "x")["tom"], "perigo")
        # conta a pagar subir e notícia ruim
        self.assertEqual(c.variacao(120, 100, "x", bom="desce")["tom"], "perigo")
        self.assertEqual(c.variacao(100.2, 100, "x")["direcao"], "igual")
        # sem base nao existe porcentagem honesta
        self.assertIsNone(c.variacao(500, 0, "x"))
        self.assertIsNone(c.variacao(500, None, "x"))

    def test_whatsapp_so_com_numero_brasileiro(self) -> None:
        self.assertEqual(c.whatsapp("(63) 98888-7777", "Oi", "Avisar")["numero"], "5563988887777")
        self.assertEqual(c.whatsapp("6332258899", "Oi", "Avisar")["numero"], "556332258899")
        self.assertEqual(c.whatsapp("+55 63 98888-7777", "Oi", "Avisar")["numero"], "5563988887777")
        for ruim in ("", "123", "98888-7777", "+1 415 555 0100"):
            self.assertIsNone(c.whatsapp(ruim, "Oi", "Avisar"), ruim)

    def test_medidor_fica_entre_zero_e_um(self) -> None:
        self.assertEqual(c.medidor(3, 4)["fracao"], 0.75)
        self.assertEqual(c.medidor(9, 4)["fracao"], 1.0)
        self.assertEqual(c.medidor(-1, 4)["fracao"], 0.0)
        self.assertIsNone(c.medidor(1, 0))

    def test_vazio_nem_viaja_e_o_antigo_continua_la(self) -> None:
        cartao = c.cartao("Ticket", "R$ 5,00")
        self.assertEqual(cartao, {"rotulo": "Ticket", "valor": "R$ 5,00", "detalhe": "", "tom": ""})
        linha = c.linha("Ana", hora="09:00", estado="passou")
        self.assertEqual((linha["hora"], linha["estado"]), ("09:00", "passou"))
        self.assertNotIn("acao", linha)

    def test_dia_passado_concorda_com_o_dia(self) -> None:
        self.assertEqual(c.dia_passado(date(2026, 10, 10)), "sábado passado")
        self.assertEqual(c.dia_passado(date(2026, 10, 12)), "segunda passada")


class IndicadoresDeVendasTestCase(unittest.TestCase):
    """Sabado, 17/10/2026, 10:30 - e as vendas em volta dele."""

    AGORA = datetime(2026, 10, 17, 10, 30)

    def setUp(self) -> None:
        from dumtech.apps.vendas.database import open_database
        from dumtech.apps.vendas.repository import VendasRepository

        self.banco = open_database(_paths().app_db("vendas"))
        self.addCleanup(self.banco.close)
        self.repo = VendasRepository(self.banco)

    def vender(self, quando: datetime, valor: float, *, descricao="Produto", produto_id=0,
               quantidade=1, forma="Pix"):
        from dumtech.apps.vendas.models import ItemVenda, Pagamento, Venda

        venda = self.repo.salvar(Venda(
            numero=self.repo.proximo_numero(), data=quando.date().isoformat(),
            itens=[ItemVenda(descricao=descricao, quantidade=quantidade, valor_unitario=valor / quantidade,
                             produto_id=produto_id)],
            pagamentos=[Pagamento(forma=forma, valor=valor)]))
        self.banco.execute("UPDATE vendas SET criado_em = ? WHERE id = ?",
                           (quando.isoformat(timespec="seconds"), venda.id))
        return venda

    def test_hoje_contra_a_semana_passada_ate_a_mesma_hora(self) -> None:
        self.vender(self.AGORA.replace(hour=9), 100)
        self.vender(self.AGORA.replace(hour=10, minute=15), 50)
        base = self.AGORA - timedelta(days=7)
        self.vender(base.replace(hour=9, minute=40), 80)
        self.vender(base.replace(hour=15), 900)  # depois desta hora: nao entra na comparacao

        r = self.repo.indicadores(agora=self.AGORA)
        self.assertEqual(r.total_hoje, 150)
        self.assertEqual(r.vendas_hoje, 2)
        self.assertEqual(r.base_ate_agora, 80, "a semana passada so vale ate as 10:30")
        self.assertEqual(r.dia(base.date()).total, 980)
        self.assertEqual(r.horas_hoje[9], 100)
        self.assertEqual(r.horas_base[15], 900)

    def test_cancelada_nao_conta(self) -> None:
        venda = self.vender(self.AGORA.replace(hour=9), 100)
        self.repo.cancelar(venda.id, "teste")
        self.assertEqual(self.repo.indicadores(agora=self.AGORA).total_hoje, 0)

    def test_janela_anterior_corta_o_dia_equivalente_no_mesmo_horario(self) -> None:
        # semana atual: 6 dias cheios de 100 + hoje (ate agora) 50
        for n in range(1, 7):
            self.vender(self.AGORA - timedelta(days=n), 100)
        self.vender(self.AGORA.replace(hour=9), 50)
        # semana anterior: dias cheios de 100; o sabado equivalente tem 60 de manha e 500 a tarde
        for n in range(8, 14):
            self.vender(self.AGORA - timedelta(days=n), 100)
        base = self.AGORA - timedelta(days=7)
        self.vender(base.replace(hour=8), 60)
        self.vender(base.replace(hour=17), 500)

        r = self.repo.indicadores(agora=self.AGORA)
        self.assertEqual(r.janela(7), 650)
        self.assertEqual(r.janela_anterior(7), 660, "o sabado da semana passada conta so ate as 10:30")

    def test_mes_contra_o_mesmo_pedaco_do_mes_passado(self) -> None:
        self.vender(datetime(2026, 10, 2, 10), 300)
        self.vender(datetime(2026, 9, 5, 10), 200)
        self.vender(datetime(2026, 9, 25, 10), 999)  # depois do dia 17: fora do pedaco
        r = self.repo.indicadores(agora=self.AGORA)
        self.assertEqual((r.mes, r.vendas_mes), (300, 1))
        self.assertEqual((r.mes_anterior, r.vendas_mes_anterior), (200, 1))

    def test_dia_31_compara_com_o_ultimo_dia_do_mes_curto(self) -> None:
        self.vender(datetime(2026, 9, 30, 10), 70)
        r = self.repo.indicadores(agora=datetime(2026, 10, 31, 12))
        self.assertEqual(r.mes_anterior, 70)

    def test_mais_vendidos_junta_o_mesmo_produto(self) -> None:
        self.vender(self.AGORA.replace(hour=8), 30, descricao="Café 500g", produto_id=7, quantidade=2)
        self.vender(self.AGORA.replace(hour=9), 45, descricao="Café torrado 500g", produto_id=7, quantidade=3)
        self.vender(self.AGORA.replace(hour=9), 40, descricao="Pão", quantidade=4)
        r = self.repo.indicadores(agora=self.AGORA)
        primeiro = r.mais_vendidos[0]
        self.assertEqual((primeiro.quantidade, primeiro.valor), (5, 75))
        self.assertEqual(len(r.mais_vendidos), 2)
        self.assertEqual(r.por_forma, [("Pix", 115.0)])


class SecoesTestCase(unittest.TestCase):
    """Cada modulo, com banco de verdade, monta a secao nova."""

    def setUp(self) -> None:
        self.paths = _paths()

    def test_vendas_abre_com_tres_periodos_e_o_ritmo(self) -> None:
        import dumtech.apps.vendas.module as modulo
        from dumtech.apps.vendas.database import open_database
        from dumtech.apps.vendas.models import ItemVenda, Venda
        from dumtech.apps.vendas.repository import VendasRepository

        banco = open_database(self.paths.app_db("vendas"))
        repo = VendasRepository(banco)
        repo.salvar(Venda(numero=repo.proximo_numero(), cliente="Ana",
                          itens=[ItemVenda(descricao="Bolo", quantidade=1, valor_unitario=40.0)]))
        banco.close()

        secao = modulo.celular(self.paths)
        periodos = secao["destaque"]["periodos"]
        self.assertEqual([p["nome"] for p in periodos], ["Hoje", "7 dias", "30 dias"])
        ritmo = periodos[0]["grafico"]
        self.assertEqual(ritmo["tipo"], "linhas")
        self.assertEqual(len(ritmo["series"]), 2)
        self.assertEqual(ritmo["agora"]["valores"][0], 40.0)
        self.assertEqual(len(periodos[2]["grafico"]["valores"]), 30)
        # o celular antigo abre com o primeiro cartao: continua sendo o vendido hoje
        self.assertEqual((secao["cartoes"][0]["valor"], secao["cartoes"][0]["papel"]), ("R$ 40,00", "destaque"))
        json.dumps(secao)

    def test_financeiro_avisa_cobranca_e_saldo_negativo(self) -> None:
        import dumtech.apps.financeiro.module as modulo
        from dumtech.apps.financeiro.database import open_database
        from dumtech.apps.financeiro.models import DESPESA, RECEITA, Conta, Lancamento
        from dumtech.apps.financeiro.repository import FinanceiroRepository

        banco = open_database(self.paths.app_db("financeiro"))
        repo = FinanceiroRepository(banco)
        conta = repo.criar_conta(Conta(nome="Banco", saldo_inicial=500.0))
        hoje = date.today()
        repo.criar(Lancamento(tipo=RECEITA, descricao="Manutenção", valor=200.0,
                              vencimento=(hoje - timedelta(days=2)).isoformat(), conta_id=conta.id))
        repo.criar(Lancamento(tipo=DESPESA, descricao="Aluguel", valor=2000.0,
                              vencimento=(hoje + timedelta(days=5)).isoformat(), conta_id=conta.id))
        banco.close()

        secao = modulo.celular(self.paths)
        textos = [a["texto"] for a in secao["alertas"]]
        self.assertIn("Cobrar 1 conta atrasada", textos)
        self.assertTrue(any(t.startswith("Saldo fica negativo em") for t in textos))
        destaque = secao["destaque"]
        self.assertEqual(destaque["tom"], "perigo")
        grafico = destaque["periodos"][0]["grafico"]
        self.assertTrue(grafico["zero"], "saldo que fica negativo risca o zero")
        self.assertEqual(len(grafico["rotulos"]), 31)

    def test_ordens_pronta_leva_o_whatsapp_do_cliente(self) -> None:
        import dumtech.apps.ordens.module as modulo
        from dumtech.apps.ordens.database import open_database
        from dumtech.apps.ordens.models import CONCLUIDA, Ordem
        from dumtech.apps.ordens.repository import OrdensRepository

        banco = open_database(self.paths.app_db("ordens"))
        repo = OrdensRepository(banco)
        hoje = date.today()
        repo.salvar(Ordem(numero=repo.proximo_numero(), cliente="Bia Lima", telefone="63988887777",
                          equipamento="Impressora", defeito="Atola", aberta_em=(hoje - timedelta(days=3)).isoformat(),
                          prazo=(hoje + timedelta(days=3)).isoformat(), status=CONCLUIDA,
                          concluida_em=hoje.isoformat()))
        banco.close()

        secao = modulo.celular(self.paths)
        pronta = next(l for l in secao["listas"] if l["titulo"] == "Prontas para entregar")["linhas"][0]
        self.assertEqual(pronta["acao"]["numero"], "5563988887777")
        self.assertIn("Bia", pronta["acao"]["mensagem"])
        self.assertIn("Entregar 1 ordem pronta", [a["texto"] for a in secao["alertas"]])
        etapas = secao["graficos"][0]
        self.assertEqual(etapas["tipo"], "etapas")
        self.assertEqual(sum(i["valor"] for i in etapas["itens"]), 1)

    def test_estoque_separa_zerado_de_acabando(self) -> None:
        import dumtech.apps.estoque.module as modulo
        from dumtech.apps.estoque.database import open_database
        from dumtech.apps.estoque.models import Produto
        from dumtech.apps.estoque.repository import EstoqueRepository

        banco = open_database(self.paths.app_db("estoque"))
        repo = EstoqueRepository(banco)
        repo.criar(Produto(codigo="A", nome="Arroz", estoque_minimo=10, quantidade=0.0))
        repo.criar(Produto(codigo="F", nome="Feijão", estoque_minimo=10, quantidade=4.0))
        banco.close()

        secao = modulo.celular(self.paths)
        self.assertEqual([a["texto"] for a in secao["alertas"]],
                         ["Repor 1 produto zerado", "Comprar 1 produto que está acabando"])
        feijao = next(l for l in secao["listas"][0]["linhas"] if l["texto"] == "Feijão")
        self.assertEqual(feijao["medidor"]["fracao"], 0.4)

    def test_agenda_marca_o_que_passou_e_o_que_esta_acontecendo(self) -> None:
        import dumtech.apps.agenda.module as modulo
        from dumtech.apps.agenda.database import open_database
        from dumtech.apps.agenda.models import Compromisso
        from dumtech.apps.agenda.repository import AgendaRepository

        agora = datetime.now().replace(second=0, microsecond=0)
        if not (2 <= agora.hour <= 21):
            self.skipTest("o teste precisa de horas livres antes e depois de agora")
        banco = open_database(self.paths.app_db("agenda"))
        repo = AgendaRepository(banco)
        repo.salvar(Compromisso(titulo="Cedo", cliente="Ana", duracao_min=30,
                                inicio=(agora - timedelta(hours=2)).isoformat(timespec="minutes")))
        repo.salvar(Compromisso(titulo="Agora", cliente="Bia", duracao_min=60,
                                inicio=(agora - timedelta(minutes=10)).isoformat(timespec="minutes")))
        repo.salvar(Compromisso(titulo="Depois", cliente="Caio", duracao_min=30,
                                inicio=(agora + timedelta(hours=1)).isoformat(timespec="minutes")))
        banco.close()

        secao = modulo.celular(self.paths)
        hoje = next(l for l in secao["listas"] if l["titulo"] == "Hoje")["linhas"]
        self.assertEqual({l["texto"]: l.get("estado", "") for l in hoje},
                         {"Cedo": "passou", "Agora": "agora", "Depois": ""})
        self.assertEqual(secao["cartoes"][0]["rotulo"], "Próximo")
        semana = secao["graficos"][0]
        self.assertEqual(semana["valores"][date.today().weekday()], 3)

    def test_clientes_aniversario_hoje_vira_parabens(self) -> None:
        import dumtech.apps.clientes.module as modulo
        from dumtech.core.contacts import ContactsStore, Contato

        hoje = date.today()
        loja = ContactsStore(self.paths.platform_db)
        loja.criar(Contato(nome="Carlos Menezes", whatsapp="63999990000",
                           nascimento=hoje.replace(year=hoje.year - 40).isoformat()))
        loja.close()

        secao = modulo.celular(self.paths)
        linha = secao["listas"][0]["linhas"][0]
        self.assertEqual(linha["detalhe"], "Faz aniversário hoje")
        self.assertEqual(linha["acao"]["rotulo"], "Mandar parabéns")
        self.assertIsInstance(linha["detalhe"], str, "o aniversario ia como lista e aparecia '17,10'")
        self.assertEqual(secao["alertas"][0]["tom"], "ok")

    def test_resumo_inteiro_cabe_no_servidor(self) -> None:
        """O servidor recusa resumo acima de 300 KB: tem de sobrar muito espaco."""
        from types import SimpleNamespace
        from importlib import import_module

        from dumtech.apps import INSTALLED_APPS

        modulos = [import_module(caminho) for caminho in INSTALLED_APPS]
        resumo = c.montar([SimpleNamespace(module=m) for m in modulos], self.paths, empresa="X")
        self.assertEqual(resumo["formato"], 2)
        self.assertLess(len(json.dumps(resumo, ensure_ascii=False).encode("utf-8")), 60_000)


if __name__ == "__main__":
    unittest.main()
