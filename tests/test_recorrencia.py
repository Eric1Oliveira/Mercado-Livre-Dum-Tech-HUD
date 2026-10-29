"""Venda e servico recorrentes: o contrato, as datas e o caminho ate o Financeiro.

O que o cliente espera: cadastrar a mensalidade uma vez, ver a venda (ou a
ordem) aparecer sozinha na data, e o Financeiro ja contando com o dinheiro.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from dumtech.apps.estoque.catalog import CatalogoEstoque
from dumtech.apps.estoque.database import open_database as abrir_estoque
from dumtech.apps.estoque.models import Produto
from dumtech.apps.estoque.repository import EstoqueRepository
from dumtech.apps.financeiro.contas import ContasFinanceiro
from dumtech.apps.financeiro.database import open_database as abrir_financeiro
from dumtech.apps.financeiro.models import RECEITA, RECORRENCIA
from dumtech.core import recorrencia as motor
from dumtech.core.recorrencia import MENSAL, SEMANAL, Recorrencia, data_da_vez


def _pasta() -> Path:
    return Path(tempfile.mkdtemp())


def _contrato(**extra) -> Recorrencia:
    dados = dict(cliente="Maria", descricao="Mensalidade", frequencia=MENSAL,
                 inicio="2026-01-31",
                 itens=[{"descricao": "Plano mensal", "quantidade": 1,
                         "valor_unitario": 100.0}])
    dados.update(extra)
    return Recorrencia(**dados)


class DatasTestCase(unittest.TestCase):
    def test_o_dia_31_volta_depois_do_fevereiro_curto(self) -> None:
        inicio = date(2026, 1, 31)
        self.assertEqual(data_da_vez(inicio, MENSAL, 1), date(2026, 2, 28))
        self.assertEqual(data_da_vez(inicio, MENSAL, 2), date(2026, 3, 31))

    def test_semanal_e_anual(self) -> None:
        self.assertEqual(data_da_vez(date(2026, 1, 1), SEMANAL, 2), date(2026, 1, 15))
        self.assertEqual(data_da_vez(date(2024, 2, 29), motor.ANUAL, 1), date(2025, 2, 28))

    def test_proxima_some_quando_passa_do_fim(self) -> None:
        rec = _contrato(inicio="2026-01-10", fim="2026-02-10", indice=2)
        self.assertEqual(rec.proxima, "")
        self.assertEqual(rec.situacao, motor.ENCERRADA)


class MotorTestCase(unittest.TestCase):
    """O motor sozinho, num banco qualquer com a tabela."""

    def setUp(self) -> None:
        from dumtech.apps.vendas.database import open_database
        self.db = open_database(_pasta() / "vendas.db")
        self.addCleanup(self.db.close)
        self.repo = motor.RecorrenciasRepository(self.db, "VREC")
        self.criadas: list[tuple[str, date]] = []

    def _criar(self, rec, quando) -> str:
        self.criadas.append((rec.numero, quando))
        return f"DOC-{len(self.criadas)}"

    def test_gera_so_o_que_esta_devido_com_a_antecedencia(self) -> None:
        self.repo.salvar(_contrato(inicio="2026-03-10"))
        motor.gerar(self.repo, self._criar, hoje=date(2026, 3, 1), antecedencia=5)
        self.assertEqual(self.criadas, [])
        motor.gerar(self.repo, self._criar, hoje=date(2026, 3, 5), antecedencia=5)
        self.assertEqual([q for _, q in self.criadas], [date(2026, 3, 10)])

    def test_rodar_de_novo_nao_duplica(self) -> None:
        self.repo.salvar(_contrato(inicio="2026-03-10"))
        for _ in range(3):
            motor.gerar(self.repo, self._criar, hoje=date(2026, 3, 10))
        self.assertEqual(len(self.criadas), 1)

    def test_respeita_a_data_final(self) -> None:
        self.repo.salvar(_contrato(inicio="2026-01-05", fim="2026-03-05"))
        motor.gerar(self.repo, self._criar, hoje=date(2026, 12, 1))
        self.assertEqual(len(self.criadas), 3)  # jan, fev, mar

    def test_pausada_nao_gera_e_retomar_nao_cobra_o_atrasado(self) -> None:
        rec = self.repo.salvar(_contrato(inicio="2026-01-05"))
        self.repo.pausar(rec.id)
        motor.gerar(self.repo, self._criar, hoje=date(2026, 4, 1))
        self.assertEqual(self.criadas, [])
        self.repo.retomar(rec.id, hoje=date(2026, 4, 1))
        motor.gerar(self.repo, self._criar, hoje=date(2026, 4, 1), antecedencia=5)
        self.assertEqual([q for _, q in self.criadas], [date(2026, 4, 5)])

    def test_inicio_esquecido_nao_despeja_tudo_de_uma_vez(self) -> None:
        self.repo.salvar(_contrato(inicio="2020-01-01", frequencia=SEMANAL))
        motor.gerar(self.repo, self._criar, hoje=date(2026, 1, 1))
        self.assertEqual(len(self.criadas), motor.LIMITE_POR_RODADA)

    def test_falha_num_contrato_nao_trava_o_outro(self) -> None:
        self.repo.salvar(_contrato(cliente="Ruim", inicio="2026-01-05"))
        self.repo.salvar(_contrato(cliente="Bom", inicio="2026-01-05"))

        def criar(rec, quando):
            if rec.cliente == "Ruim":
                raise RuntimeError("boom")
            return self._criar(rec, quando)

        motor.gerar(self.repo, criar, hoje=date(2026, 1, 5))
        self.assertEqual(len(self.criadas), 1)
        ruim = [r for r in self.repo.listar() if r.cliente == "Ruim"][0]
        self.assertEqual(ruim.indice, 0, "a vez que falhou fica para a proxima rodada")

    def test_frequencia_trava_depois_da_primeira_vez(self) -> None:
        rec = self.repo.salvar(_contrato(inicio="2026-01-05"))
        motor.gerar(self.repo, self._criar, hoje=date(2026, 1, 5))
        rec = self.repo.obter(rec.id)
        rec.frequencia = SEMANAL
        with self.assertRaises(motor.RecorrenciaError):
            self.repo.salvar(rec)

    def test_editar_nao_desfaz_o_que_foi_gerado_enquanto_isso(self) -> None:
        rec = self.repo.salvar(_contrato(inicio="2026-01-05"))
        aberto_no_dialogo = self.repo.obter(rec.id)          # indice 0
        motor.gerar(self.repo, self._criar, hoje=date(2026, 1, 5))
        aberto_no_dialogo.descricao = "Mensalidade nova"
        self.repo.salvar(aberto_no_dialogo)
        salvo = self.repo.obter(rec.id)
        self.assertEqual((salvo.indice, salvo.descricao), (1, "Mensalidade nova"))

    def test_validacao(self) -> None:
        with self.assertRaises(motor.RecorrenciaError):
            self.repo.salvar(_contrato(cliente=""))
        with self.assertRaises(motor.RecorrenciaError):
            self.repo.salvar(_contrato(itens=[]))
        with self.assertRaises(motor.RecorrenciaError):
            self.repo.salvar(_contrato(fim="2025-01-01"))

    def test_numero_por_modulo(self) -> None:
        rec = self.repo.salvar(_contrato())
        self.assertTrue(rec.numero.startswith(f"VREC-{date.today().year}-"))


class Base(unittest.TestCase):
    def setUp(self) -> None:
        pasta = _pasta()
        self.db_estoque = abrir_estoque(pasta / "estoque.db")
        self.estoque = EstoqueRepository(self.db_estoque)
        self.catalogo = CatalogoEstoque(self.db_estoque)
        self.db_financeiro = abrir_financeiro(pasta / "financeiro.db")
        self.contas = ContasFinanceiro(self.db_financeiro)
        self.addCleanup(self.db_estoque.close)
        self.addCleanup(self.db_financeiro.close)
        self.produto = self.estoque.criar(Produto(
            codigo="AGUA20", nome="Galão de água 20L", quantidade=10, preco_venda=15.0,
        ))

    def _receitas_recorrentes(self):
        return self.contas.repository.listar(tipo=RECEITA, serie=RECORRENCIA)


class VendaRecorrenteTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        from dumtech.apps.vendas import recorrencias
        from dumtech.apps.vendas.database import open_database
        from dumtech.apps.vendas.repository import VendasRepository

        self.recorrencias = recorrencias
        self.db = open_database(_pasta() / "vendas.db")
        self.addCleanup(self.db.close)
        self.vendas = VendasRepository(self.db, catalogo=self.catalogo)
        self.repo = recorrencias.repositorio(self.db)
        self.rec = self.repo.salvar(_contrato(
            inicio="2026-05-10",
            itens=[{"descricao": "Galão de água 20L", "quantidade": 2, "valor_unitario": 15.0,
                    "produto_id": self.produto.id, "codigo": "AGUA20"}],
        ))

    def test_a_vez_vira_venda_pendente_e_conta_recorrente(self) -> None:
        from dumtech.apps.vendas.models import PENDENTE

        numeros = self.recorrencias.gerar(self.vendas, self.contas, hoje=date(2026, 5, 1))
        self.assertEqual(len(numeros), 1)
        venda = self.vendas.listar(busca=numeros[0], inicio="2026-01-01")[0]
        self.assertEqual((venda.status, venda.data, venda.recorrencia),
                         (PENDENTE, "2026-05-10", self.rec.numero))
        self.assertEqual(venda.total, 30.0)
        self.assertEqual(self.estoque.obter(self.produto.id).quantidade, 10,
                         "pendente: o galao so sai quando o cliente pagar")

        contas = self._receitas_recorrentes()
        self.assertEqual(len(contas), 1)
        self.assertEqual((contas[0].valor, contas[0].vencimento, contas[0].categoria),
                         (30.0, "2026-05-10", "Vendas recorrentes"))
        self.assertIn(self.rec.numero, contas[0].descricao)

    def test_receber_quita_a_conta_e_baixa_o_estoque(self) -> None:
        from dumtech.apps.vendas import financeiro
        from dumtech.apps.vendas.models import Pagamento

        numero = self.recorrencias.gerar(self.vendas, self.contas, hoje=date(2026, 5, 10))[0]
        venda = self.vendas.listar(busca=numero, inicio="2026-01-01")[0]
        recebida = self.vendas.receber_pendente(venda.id, [Pagamento(forma="Pix", valor=30.0)])
        financeiro.registrar(self.contas, recebida)
        self.assertTrue(self._receitas_recorrentes()[0].pago)
        self.assertEqual(self.estoque.obter(self.produto.id).quantidade, 8)

    def test_resumo_do_financeiro_conta_o_recorrente(self) -> None:
        hoje = date.today()
        self.repo.salvar(_contrato(cliente="Joao", inicio=hoje.isoformat()))
        self.recorrencias.gerar(self.vendas, self.contas, hoje=hoje)
        resumo = self.contas.repository.resumo()
        self.assertGreaterEqual(resumo.recorrente_mes, 100.0)

    def test_sem_financeiro_gera_igual(self) -> None:
        numeros = self.recorrencias.gerar(self.vendas, None, hoje=date(2026, 5, 10))
        self.assertEqual(len(numeros), 1)

    def test_contar_geradas(self) -> None:
        self.recorrencias.gerar(self.vendas, None, hoje=date(2026, 6, 10))
        contratos = self.repo.listar()
        self.recorrencias.contar_geradas(self.vendas, contratos)
        # maio e junho, mais julho: com 30 dias de antecedencia ja esta devida
        self.assertEqual(contratos[0].gerados, 3)


class OrdemRecorrenteTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        from dumtech.apps.ordens import recorrencias
        from dumtech.apps.ordens.database import open_database
        from dumtech.apps.ordens.repository import OrdensRepository

        self.recorrencias = recorrencias
        self.db = open_database(_pasta() / "ordens.db")
        self.addCleanup(self.db.close)
        self.ordens = OrdensRepository(self.db, catalogo=self.catalogo)
        self.repo = recorrencias.repositorio(self.db)
        self.rec = self.repo.salvar(_contrato(
            descricao="Preventiva do ar-condicionado", frequencia=motor.TRIMESTRAL,
            inicio="2026-05-10",
            itens=[{"descricao": "Limpeza", "quantidade": 1, "valor_unitario": 180.0}],
        ))

    def test_a_vez_abre_ordem_no_quadro_com_prazo_e_conta(self) -> None:
        from dumtech.apps.ordens.models import ABERTA, SERVICO

        self.assertEqual(self.recorrencias.gerar(self.ordens, self.contas,
                                                 hoje=date(2026, 5, 1)), [],
                         "mais de 7 dias antes ainda nao aparece")
        numero = self.recorrencias.gerar(self.ordens, self.contas, hoje=date(2026, 5, 4))[0]
        ordem = [o for o in self.ordens.listar() if o.numero == numero][0]
        self.assertEqual((ordem.status, ordem.prazo, ordem.aberta_em, ordem.recorrencia),
                         (ABERTA, "2026-05-10", "2026-05-04", self.rec.numero))
        self.assertEqual(ordem.equipamento, "Preventiva do ar-condicionado")
        self.assertEqual(ordem.itens[0].tipo, SERVICO)
        contas = self._receitas_recorrentes()
        self.assertEqual((contas[0].valor, contas[0].categoria), (180.0, "Serviços recorrentes"))

    def test_material_do_estoque_vira_peca(self) -> None:
        from dumtech.apps.ordens.models import PECA

        self.repo.salvar(_contrato(inicio="2026-05-10", itens=[
            {"descricao": "Galão", "quantidade": 1, "valor_unitario": 15.0,
             "produto_id": self.produto.id, "codigo": "AGUA20"}]))
        self.recorrencias.gerar(self.ordens, None, hoje=date(2026, 5, 10))
        pecas = [i for o in self.ordens.listar() for i in o.itens if i.e_peca]
        self.assertEqual(pecas[0].tipo, PECA)


class PastaOcultaTestCase(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "atributo de pasta do Windows")
    def test_ocultar_marca_a_pasta_e_ela_continua_usavel(self) -> None:
        import ctypes

        from dumtech.core.paths import DataPaths, ocultar

        pasta = _pasta() / "DumTech Hub"
        paths = DataPaths(root=pasta).ensure()
        self.assertTrue(ocultar(pasta))
        atributos = ctypes.windll.kernel32.GetFileAttributesW(str(pasta))
        self.assertTrue(atributos & 0x2)
        self.assertTrue(ocultar(pasta), "de novo nao quebra")
        # o programa continua lendo e gravando ali
        arquivo = paths.data_dir / "teste.txt"
        arquivo.write_text("ok", encoding="utf-8")
        self.assertEqual(arquivo.read_text(encoding="utf-8"), "ok")

    def test_pasta_que_nao_existe_nao_levanta(self) -> None:
        from dumtech.core.paths import ocultar

        self.assertFalse(ocultar(_pasta() / "nao-existe"))

    def test_a_pasta_dos_testes_nao_e_ocultada(self) -> None:
        """Com DUMTECH_DATA_DIR (desenvolvimento), a pasta fica a vista."""
        self.assertTrue(os.environ.get("DUMTECH_DATA_DIR"))


class TelasTestCase(unittest.TestCase):
    """Com o Hub de verdade: a aba nasce, o cadastro gera e o Financeiro ve."""

    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from dumtech.core.config import Settings
        from dumtech.hub.main_window import HubWindow

        self.hub = HubWindow(settings=Settings(_pasta() / "hub.json"))
        self.hub.launcher.notify = lambda *args: None
        self.addCleanup(self._fechar)

    def _fechar(self) -> None:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication

        self.hub.close()
        self.hub.deleteLater()
        QApplication.instance().sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _cadastrar(self, app_id: str, descricao: str):
        self.assertTrue(self.hub.open_app(app_id))
        janela = self.hub.launcher.get(app_id)
        self.assertIn("Recorrentes", [v.title for v in janela.views])
        tela = janela.recorrentes_view
        dialogo = tela.abrir_dialogo(None)
        self.addCleanup(dialogo.deleteLater)
        dialogo.cliente.setText("Cliente Recorrente")
        dialogo.descricao.setText(descricao)
        dialogo.itens.campo_descricao.setText("Plano")
        dialogo.itens.campo_valor.setValue(99.0)
        dialogo.itens.adicionar()
        dialogo.salvar()
        criados = tela.gerar()
        tela.refresh()
        return janela, dialogo.rec, criados

    def test_vendas_cadastra_e_a_venda_de_hoje_aparece(self) -> None:
        janela, rec, criados = self._cadastrar("vendas", "Mensalidade")
        self.assertEqual(len(criados), 1, "a primeira vez e hoje: ja vira venda")
        venda = janela.repository.listar(busca=criados[0])[0]
        self.assertEqual(venda.recorrencia, rec.numero)
        self.assertEqual(janela.recorrentes_view._registros[0].gerados, 1)

        contas = self.hub.launcher.contas("vendas")
        self.assertTrue(contas.ja_lancado(criados[0]), "foi ao Financeiro")

    def test_ordens_cadastra_e_a_ordem_entra_no_quadro(self) -> None:
        from dumtech.apps.ordens.models import ABERTA

        janela, rec, criados = self._cadastrar("ordens", "Preventiva")
        self.assertEqual(len(criados), 1)
        ordem = [o for o in janela.repository.listar() if o.numero == criados[0]][0]
        self.assertEqual((ordem.status, ordem.recorrencia), (ABERTA, rec.numero))

    def test_financeiro_filtra_as_receitas_recorrentes(self) -> None:
        self._cadastrar("vendas", "Mensalidade")
        self.assertTrue(self.hub.open_app("financeiro"))
        lancamentos = self.hub.launcher.get("financeiro").lancamentos_view
        filtro = lancamentos.filtro_tipo
        filtro.setCurrentIndex(filtro.findData("recorrentes"))
        self.assertTrue(lancamentos._registros)
        self.assertTrue(all(item.serie == RECORRENCIA for item in lancamentos._registros))

    def test_pausar_e_retomar_pela_tela(self) -> None:
        janela, rec, _ = self._cadastrar("vendas", "Mensalidade")
        tela = janela.recorrentes_view

        def selecionar():
            # a pasta de dados e do arquivo inteiro: pode haver outros contratos
            linha = [r.numero for r in tela._registros].index(rec.numero)
            tela.tabela.selectRow(linha)
            return tela._registros[linha]

        selecionar()
        tela._pausar_ou_retomar()
        self.assertEqual(selecionar().situacao, motor.PAUSADA)
        self.assertEqual(tela.botao_pausar.text(), "Retomar")
        tela._pausar_ou_retomar()
        self.assertEqual(selecionar().situacao, motor.ATIVA)

    def test_sobre_nao_mostra_mais_a_pasta(self) -> None:
        from dumtech.ui.widgets.buttons import Button

        textos = [b.text() for b in self.hub.findChildren(Button)]
        self.assertNotIn("Abrir pasta de dados", textos)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
