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

from PySide6.QtCore import QDate

from dumtech.apps.estoque.catalog import CatalogoEstoque
from dumtech.apps.estoque.database import open_database as abrir_estoque
from dumtech.apps.estoque.models import Produto
from dumtech.apps.estoque.repository import EstoqueRepository
from dumtech.apps.financeiro.contas import ContasFinanceiro
from dumtech.apps.financeiro.database import open_database as abrir_financeiro
from dumtech.apps.financeiro.models import RECEITA, RECORRENCIA
from dumtech.core import recorrencia as motor
from dumtech.core.errors import RegraError
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


class FormulariosBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from dumtech.apps.financeiro.contas import abrir_contas

        self.pasta = _pasta()
        self.contas = abrir_contas(self.pasta / "financeiro.db")
        self.addCleanup(self.contas.close)


class RepetirNaVendaTestCase(FormulariosBase):
    """Repetir mora no Lancar venda: ela e a primeira vez, o contrato faz o resto."""

    def setUp(self) -> None:
        from dumtech.apps.vendas import recorrencias
        from dumtech.apps.vendas.database import open_database
        from dumtech.apps.vendas.repository import VendasRepository

        super().setUp()
        self.banco = open_database(self.pasta / "vendas.db")
        self.addCleanup(self.banco.close)
        self.vendas = VendasRepository(self.banco)
        self.modulo = recorrencias
        self.contratos = recorrencias.repositorio(self.banco)

    def _dialogo(self, venda=None):
        from dumtech.apps.vendas.ui.venda_dialog import VendaDialog

        dialogo = VendaDialog(self.vendas, venda, contas=self.contas)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def _preenchido(self, cliente: str = "Ana"):
        dialogo = self._dialogo()
        dialogo.cliente.setText(cliente)
        dialogo.itens.set_items([{"descricao": "Plano", "quantidade": 1,
                                  "valor_unitario": 99.0}])
        dialogo.data.setDate(QDate(2026, 3, 10))
        dialogo.repeticao.marcar.setChecked(True)
        return dialogo

    def test_a_venda_e_a_primeira_vez_do_contrato(self) -> None:
        dialogo = self._preenchido()
        dialogo.salvar()

        contrato = self.contratos.listar()[0]
        self.assertEqual(
            (contrato.cliente, contrato.descricao, contrato.inicio, contrato.indice,
             contrato.valor, contrato.proxima),
            ("Ana", "Plano", "2026-03-10", 1, 99.0, "2026-04-10"),
        )
        self.assertEqual(dialogo.venda.recorrencia, contrato.numero)
        self.assertEqual(dialogo.venda.status, "concluida", "paga agora, como qualquer venda")
        self.assertTrue(self.contas.ja_lancado(dialogo.venda.numero))
        self.assertIn("todo mês", dialogo.recado)

    def test_a_proxima_nasce_pendente_e_a_primeira_nao_duplica(self) -> None:
        self._preenchido().salvar()

        criadas = self.modulo.gerar(self.vendas, self.contas, hoje=date(2026, 3, 20))

        self.assertEqual(len(criadas), 1)
        nova = self.vendas.listar(busca=criadas[0], inicio="2026-01-01")[0]
        self.assertEqual((nova.data, nova.status, nova.total, nova.cliente),
                         ("2026-04-10", "pendente", 99.0, "Ana"))
        contratos = self.contratos.listar()
        self.modulo.contar_geradas(self.vendas, contratos)
        self.assertEqual(contratos[0].gerados, 2, "a primeira conta como gerada")

    def test_frequencia_e_fim_escolhidos_valem(self) -> None:
        dialogo = self._preenchido()
        repeticao = dialogo.repeticao
        repeticao.frequencia.setCurrentIndex(repeticao.frequencia.findData(motor.TRIMESTRAL))
        repeticao.fim.definir_iso("2026-12-31")
        dialogo.salvar()

        contrato = self.contratos.listar()[0]
        self.assertEqual((contrato.frequencia, contrato.fim, contrato.proxima),
                         (motor.TRIMESTRAL, "2026-12-31", "2026-06-10"))

    def test_sem_cliente_nada_e_gravado(self) -> None:
        dialogo = self._preenchido(cliente="")
        with self.assertRaises(motor.RecorrenciaError):
            dialogo.salvar()
        self.assertEqual(self.vendas.listar(), [])
        self.assertEqual(self.contratos.listar(), [])

    def test_desmarcar_depois_do_erro_vira_venda_comum(self) -> None:
        dialogo = self._preenchido(cliente="")
        with self.assertRaises(motor.RecorrenciaError):
            dialogo.salvar()
        dialogo.repeticao.marcar.setChecked(False)
        dialogo.salvar()
        self.assertEqual(dialogo.venda.recorrencia, "")
        self.assertEqual(self.contratos.listar(), [])

    def test_venda_recusada_nao_deixa_contrato_solto(self) -> None:
        primeira = self._preenchido()
        primeira.repeticao.marcar.setChecked(False)
        primeira.salvar()

        repetida = self._preenchido()
        repetida.numero.setText(primeira.venda.numero)
        with self.assertRaises(RegraError):
            repetida.salvar()
        self.assertEqual(self.contratos.listar(), [])

        repetida.numero.setText(self.vendas.proximo_numero())
        repetida.repeticao.marcar.setChecked(False)
        repetida.salvar()
        self.assertEqual(repetida.venda.recorrencia, "", "o erro nao deixou marca na venda")

    def test_venda_comum_nao_vira_contrato(self) -> None:
        dialogo = self._preenchido()
        dialogo.repeticao.marcar.setChecked(False)
        dialogo.salvar()
        self.assertEqual(self.contratos.listar(), [])

    def test_parcelado_e_repetir_nao_andam_juntos(self) -> None:
        dialogo = self._preenchido()
        dialogo.forma.setCurrentText("Parcelado")
        self.assertFalse(dialogo.repeticao.ligado)
        self.assertTrue(dialogo.repeticao.isHidden())
        dialogo.forma.setCurrentText("Pix")
        self.assertFalse(dialogo.repeticao.isHidden())

    def test_editar_nao_oferece_e_nao_perde_o_contrato(self) -> None:
        primeira = self._preenchido()
        primeira.salvar()
        numero = primeira.venda.recorrencia

        edicao = self._dialogo(self.vendas.obter(primeira.venda.id))
        self.assertTrue(edicao.repeticao.isHidden())
        edicao.observacoes.setPlainText("Corrigi a anotação")
        edicao.salvar()

        self.assertEqual(self.vendas.obter(primeira.venda.id).recorrencia, numero)
        self.assertEqual(len(self.contratos.listar()), 1)


class RepetirNaOrdemTestCase(FormulariosBase):
    """O mesmo na Nova OS: a ordem aberta e a primeira, as proximas abrem sozinhas."""

    def setUp(self) -> None:
        from dumtech.apps.ordens import recorrencias
        from dumtech.apps.ordens.database import open_database
        from dumtech.apps.ordens.repository import OrdensRepository

        super().setUp()
        self.banco = open_database(self.pasta / "ordens.db")
        self.addCleanup(self.banco.close)
        self.ordens = OrdensRepository(self.banco)
        self.modulo = recorrencias
        self.contratos = recorrencias.repositorio(self.banco)

    def _ficha(self, ordem=None, contas="padrao"):
        from dumtech.apps.ordens.ui.ordem_dialog import OrdemDialog

        ficha = OrdemDialog(self.ordens, ordem,
                            contas=self.contas if contas == "padrao" else contas)
        self.addCleanup(ficha.deleteLater)
        return ficha

    def _preenchida(self, contas="padrao"):
        ficha = self._ficha(contas=contas)
        ficha.cliente.setText("Bia")
        ficha.defeito.setPlainText("Limpar a piscina")
        ficha.valor.setValue(150.0)
        ficha.prazo.setDate(QDate(2026, 3, 10))
        ficha.repeticao.marcar.setChecked(True)
        return ficha

    def test_ordem_sem_itens_repete_o_valor_digitado(self) -> None:
        ficha = self._preenchida()
        ficha.salvar()

        contrato = self.contratos.listar()[0]
        self.assertEqual(
            (contrato.cliente, contrato.descricao, contrato.inicio, contrato.indice,
             contrato.valor, contrato.proxima),
            ("Bia", "Limpar a piscina", "2026-03-10", 1, 150.0, "2026-04-10"),
        )
        self.assertEqual(ficha.ordem.recorrencia, contrato.numero)

    def test_a_primeira_ja_nasce_com_a_conta_como_as_proximas(self) -> None:
        ficha = self._preenchida()
        ficha.salvar()
        self.assertTrue(self.contas.ja_lancado(ficha.ordem.numero))

    def test_a_proxima_abre_igual_e_a_primeira_nao_duplica(self) -> None:
        self._preenchida().salvar()

        criadas = self.modulo.gerar(self.ordens, self.contas, hoje=date(2026, 4, 5))

        self.assertEqual(len(criadas), 1)
        nova = next(o for o in self.ordens.listar() if o.numero == criadas[0])
        self.assertEqual((nova.prazo, nova.total, nova.defeito, nova.cliente),
                         ("2026-04-10", 150.0, "Limpar a piscina", "Bia"))

    def test_itens_e_desconto_vao_para_o_contrato(self) -> None:
        from dumtech.apps.ordens.models import PECA, SERVICO, ItemOS

        ficha = self._preenchida()
        ficha.itens.set_items([
            ItemOS(tipo=SERVICO, descricao="Limpeza", quantidade=1, valor_unitario=100.0),
            ItemOS(tipo=PECA, descricao="Cloro", quantidade=2, valor_unitario=25.0,
                   produto_id=7, codigo="CLO"),
        ])
        ficha.desconto.setValue(10.0)
        ficha.salvar()

        contrato = self.contratos.listar()[0]
        self.assertEqual(contrato.valor, 140.0)
        self.assertEqual(contrato.itens[1]["produto_id"], 7, "a peca segue ligada ao Estoque")

    def test_sem_financeiro_a_ordem_repete_do_mesmo_jeito(self) -> None:
        self._preenchida(contas=None).salvar()
        self.assertEqual(len(self.contratos.listar()), 1)

    def test_ordem_recusada_nao_deixa_contrato_solto(self) -> None:
        ficha = self._preenchida()
        ficha.defeito.clear()
        with self.assertRaises(RegraError):
            ficha.salvar()
        self.assertEqual(self.contratos.listar(), [])
        self.assertEqual(self.ordens.listar(), [])

    def test_editar_nao_oferece_repetir(self) -> None:
        ficha = self._preenchida()
        ficha.salvar()
        edicao = self._ficha(self.ordens.obter(ficha.ordem.id))
        self.assertTrue(edicao.repeticao.isHidden())
        edicao.salvar()
        self.assertEqual(len(self.contratos.listar()), 1)
        self.assertEqual(self.ordens.obter(ficha.ordem.id).recorrencia, ficha.ordem.recorrencia)


class TelasTestCase(unittest.TestCase):
    """Com o Hub de verdade: sem aba propria, e o contrato continua cuidado."""

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

    def _cadastrar(self, app_id: str):
        self.assertTrue(self.hub.open_app(app_id))
        janela = self.hub.launcher.get(app_id)
        self.assertNotIn("Recorrentes", [v.title for v in janela.views])
        if app_id == "vendas":
            dialogo = janela.vendas_view.abrir_dialogo(None)
            dialogo.itens.set_items([{"descricao": "Plano", "quantidade": 1,
                                      "valor_unitario": 99.0}])
        else:
            dialogo = janela.ordens_view.abrir_dialogo(None)
            dialogo.defeito.setPlainText("Preventiva")
            dialogo.valor.setValue(99.0)
        self.addCleanup(dialogo.deleteLater)
        dialogo.cliente.setText("Cliente Recorrente")
        dialogo.repeticao.marcar.setChecked(True)
        dialogo.salvar()
        janela.refresh_all()
        return janela, dialogo

    def _lista(self, janela):
        """A janela dos contratos, sem o `exec` que trava o teste."""
        dialogo = janela.dialogo_recorrentes()
        self.addCleanup(dialogo.deleteLater)
        return dialogo.tela

    def test_vendas_repete_pelo_formulario(self) -> None:
        janela, dialogo = self._cadastrar("vendas")
        numero = dialogo.venda.numero
        self.assertEqual(janela.repository.listar(busca=numero)[0].recorrencia,
                         dialogo.venda.recorrencia)

        contrato = next(r for r in self._lista(janela)._registros
                        if r.numero == dialogo.venda.recorrencia)
        self.assertGreaterEqual(contrato.gerados, 1)
        self.assertTrue(self.hub.launcher.contas("vendas").ja_lancado(numero))

    def test_ordens_repete_pelo_formulario(self) -> None:
        from dumtech.apps.ordens.models import ABERTA

        janela, dialogo = self._cadastrar("ordens")
        ordem = next(o for o in janela.repository.listar()
                     if o.numero == dialogo.ordem.numero)
        self.assertEqual((ordem.status, ordem.recorrencia),
                         (ABERTA, dialogo.ordem.recorrencia))

    def test_o_botao_da_lista_abre_os_contratos(self) -> None:
        from unittest import mock

        from dumtech.ui.widgets.recorrencias import RecorrenciasDialog

        for app_id, tela in (("vendas", "vendas_view"), ("ordens", "ordens_view")):
            with self.subTest(app_id):
                self.assertTrue(self.hub.open_app(app_id))
                janela = self.hub.launcher.get(app_id)
                with mock.patch.object(RecorrenciasDialog, "exec", return_value=0) as abrir:
                    getattr(janela, tela).botao_recorrentes.click()
                abrir.assert_called_once()

    def test_contrato_novo_so_nasce_no_formulario(self) -> None:
        self.assertTrue(self.hub.open_app("vendas"))
        tela = self._lista(self.hub.launcher.get("vendas"))
        self.assertTrue(tela.botao_novo.isHidden())

    def test_financeiro_filtra_as_receitas_recorrentes(self) -> None:
        self._cadastrar("vendas")
        self.assertTrue(self.hub.open_app("financeiro"))
        lancamentos = self.hub.launcher.get("financeiro").lancamentos_view
        filtro = lancamentos.filtro_tipo
        filtro.setCurrentIndex(filtro.findData("recorrentes"))
        self.assertTrue(lancamentos._registros)
        self.assertTrue(all(item.serie == RECORRENCIA for item in lancamentos._registros))

    def test_pausar_e_retomar_pela_tela(self) -> None:
        janela, dialogo = self._cadastrar("vendas")
        tela = self._lista(janela)
        numero = dialogo.venda.recorrencia

        def selecionar():
            # a pasta de dados e do arquivo inteiro: pode haver outros contratos
            linha = [r.numero for r in tela._registros].index(numero)
            tela.tabela.selectRow(linha)
            return tela._registros[linha]

        selecionar()
        tela._pausar_ou_retomar()
        self.assertEqual(selecionar().situacao, motor.PAUSADA)
        self.assertEqual(tela.botao_pausar.text(), "Retomar")
        tela._pausar_ou_retomar()
        self.assertEqual(selecionar().situacao, motor.ATIVA)

    def test_editar_o_contrato_muda_o_valor_das_proximas(self) -> None:
        janela, dialogo = self._cadastrar("vendas")
        tela = self._lista(janela)
        rec = next(r for r in tela._registros if r.numero == dialogo.venda.recorrencia)

        edicao = tela.abrir_dialogo(rec)
        self.addCleanup(edicao.deleteLater)
        self.assertFalse(edicao.frequencia.isEnabled(), "a primeira vez ja foi gerada")
        edicao.desconto.setValue(9.0)
        edicao.salvar()

        self.assertEqual(tela.repositorio.obter(rec.id).valor, 90.0)

    def test_sobre_nao_mostra_mais_a_pasta(self) -> None:
        from dumtech.ui.widgets.buttons import Button

        textos = [b.text() for b in self.hub.findChildren(Button)]
        self.assertNotIn("Abrir pasta de dados", textos)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
