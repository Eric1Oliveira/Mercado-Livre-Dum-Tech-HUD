"""O cliente visto por todos os modulos, e a Agenda virando trabalho e dinheiro."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dumtech.apps.agenda import consulta as consulta_agenda
from dumtech.apps.agenda import financeiro as financeiro_agenda
from dumtech.apps.agenda.models import CONCLUIDO, FALTOU, Compromisso
from dumtech.apps.agenda.database import open_database as abrir_agenda
from dumtech.apps.agenda.repository import AgendaRepository
from dumtech.apps.clientes.ui.ficha_dialog import FichaDialog
from dumtech.apps.clientes.ui.parceiros_view import ParceirosView
from dumtech.apps.estoque import consulta as consulta_estoque
from dumtech.apps.estoque.database import open_database as abrir_estoque
from dumtech.apps.estoque.models import Produto
from dumtech.apps.estoque.repository import EstoqueRepository
from dumtech.apps.financeiro import consulta as consulta_financeiro
from dumtech.apps.financeiro.contas import abrir_contas
from dumtech.apps.orcamentos import consulta as consulta_orcamentos
from dumtech.apps.orcamentos.models import ItemOrcamento, Orcamento
from dumtech.apps.ordens import consulta as consulta_ordens
from dumtech.apps.ordens.models import Ordem
from dumtech.apps.vendas import consulta as consulta_vendas
from dumtech.apps.vendas import financeiro
from dumtech.apps.vendas.models import ItemVenda, Venda
from dumtech.apps.vendas.pedidos import DestinoVendas
from dumtech.apps.vendas.database import open_database as abrir_vendas
from dumtech.apps.vendas.repository import pagamento_unico
from dumtech.core.consulta import Consulta
from dumtech.core.contacts import Contato, ContactsStore, Parceiro
from dumtech.core.contas import AReceber

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta = Path(tempfile.mkdtemp(prefix="dt_cli_"))
        self.vendas = consulta_vendas.abrir_consulta(pasta / "vendas.db")
        self.ordens = consulta_ordens.abrir_consulta(pasta / "ordens.db")
        self.orcamentos = consulta_orcamentos.abrir_consulta(pasta / "orcamentos.db")
        self.agenda = consulta_agenda.abrir_consulta(pasta / "agenda.db")
        self.financeiro = consulta_financeiro.abrir_consulta(pasta / "financeiro.db")
        self.estoque = consulta_estoque.abrir_consulta(pasta / "estoque.db")
        self.consultas = [self.vendas, self.ordens, self.orcamentos, self.agenda,
                          self.financeiro, self.estoque]
        for consulta in self.consultas:
            self.addCleanup(consulta.close)
        self.contas = abrir_contas(pasta / "financeiro.db")
        self.addCleanup(self.contas.close)
        self.store = ContactsStore(pasta / "plataforma.db")
        self.addCleanup(self.store.close)

    def vender(self, cliente: str = "Ana", valor: float = 100.0, data: str = "") -> Venda:
        venda = Venda(cliente=cliente, itens=[ItemVenda(descricao="x", valor_unitario=valor)])
        if data:
            venda.data = data
        return self.vendas.repository.finalizar(venda, [pagamento_unico("Pix", valor)])


class HistoricoTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        self.ana = self.store.criar(Contato(nome="Ana"))
        self.vender()
        self.vender(cliente="Bruno")
        self.ordens.repository.salvar(Ordem(numero="OS-1", cliente="Ana", equipamento="Celular"))
        self.orcamentos.repository.salvar(Orcamento(
            numero="ORC-1", cliente="Ana",
            itens=[ItemOrcamento(descricao="y", quantidade=1, valor_unitario=5.0)]))
        self.agenda.repository.salvar(Compromisso(titulo="Corte", cliente="ana"))
        self.contas.lancar(AReceber(descricao="Fiado", valor=30.0, vencimento="2020-01-01",
                                    cliente="Ana", documento="X-1"))

    def test_toda_consulta_cumpre_o_contrato(self) -> None:
        for consulta in self.consultas:
            self.assertIsInstance(consulta, Consulta)

    def test_ficha_junta_tudo_e_so_dele(self) -> None:
        ficha = FichaDialog(self.store, self.ana, consultas=self.consultas, contas=self.contas)
        self.addCleanup(ficha.deleteLater)
        tipos = sorted(achado.tipo for achado in ficha.historico())
        self.assertEqual(tipos, ["Conta", "Horário", "OS", "Proposta", "Venda"])
        datas = [achado.data for achado in ficha.historico()]
        self.assertEqual(datas, sorted(datas, reverse=True))

    def test_divida_soma_o_aberto_e_o_vencido(self) -> None:
        amanha = (date.today() + timedelta(days=1)).isoformat()
        self.contas.lancar(AReceber(descricao="Outra", valor=20.0, vencimento=amanha,
                                    cliente="ana", documento="X-2"))
        divida = self.contas.divida_de("Ana")
        self.assertEqual((divida.em_aberto, divida.vencido), (50.0, 30.0))
        self.assertFalse(self.contas.divida_de("Bruno").deve)

    def test_ficha_sem_modulos_continua_abrindo(self) -> None:
        ficha = FichaDialog(self.store, self.ana)
        self.addCleanup(ficha.deleteLater)
        self.assertEqual(ficha.historico(), [])

    def test_renomear_leva_o_historico_junto(self) -> None:
        self.store.ao_renomear = lambda antigo, novo: [
            consulta.renomear_cliente(antigo, novo) for consulta in self.consultas
        ]
        self.ana.nome = "Ana Maria"
        self.store.atualizar(self.ana)
        ficha = FichaDialog(self.store, self.ana, consultas=self.consultas)
        self.addCleanup(ficha.deleteLater)
        self.assertEqual(len(ficha.historico()), 5)
        self.assertEqual(self.contas.divida_de("Ana Maria").em_aberto, 30.0)
        self.assertEqual(len(self.vendas.do_cliente("Bruno")), 1)

    def test_salvar_sem_mudar_o_nome_nao_avisa_ninguem(self) -> None:
        chamadas = []
        self.store.ao_renomear = lambda *nomes: chamadas.append(nomes)
        self.ana.telefone = "11999998888"
        self.store.atualizar(self.ana)
        self.assertEqual(chamadas, [])

    def test_balcao_avisa_de_quem_deve_sem_travar(self) -> None:
        from dumtech.apps.vendas.ui.balcao_view import BalcaoView

        tela = BalcaoView(self.vendas.repository, contas=self.contas)
        self.addCleanup(tela.deleteLater)
        tela.cliente.setText("Ana")
        tela._avisar_divida()
        self.assertIn("R$ 30,00", tela.aviso.text())


class BuscaTestCase(Base):
    def test_cada_modulo_acha_o_seu(self) -> None:
        self.vender()
        EstoqueRepository(self.estoque.database).criar(Produto(codigo="T1", nome="Tela LG"))
        self.assertEqual(self.vendas.buscar("VEN-")[0].tipo, "Venda")
        self.assertEqual(self.estoque.buscar("Tela")[0].titulo, "Tela LG")
        self.assertEqual(self.ordens.buscar("nada disso"), [])

    def test_a_paleta_mostra_o_que_veio_dos_dados(self) -> None:
        from dumtech.ui.widgets.command_palette import Command, CommandPalette

        paleta = CommandPalette()
        self.addCleanup(paleta.deleteLater)
        paleta.buscar_dados = lambda termo: [Command(title=f"achei {termo}")]
        paleta._filtrar("an")
        self.assertEqual(paleta.lista.count(), 0)
        paleta._filtrar("ana")
        self.assertEqual(paleta.lista.count(), 1)

    def test_procurar_tira_os_filtros_da_frente(self) -> None:
        from dumtech.apps.vendas.ui.vendas_view import VendasView

        antiga = (date.today() - timedelta(days=90)).isoformat()
        venda = self.vender(data=antiga)
        tela = VendasView(self.vendas.repository)
        self.addCleanup(tela.deleteLater)
        tela.refresh()
        self.assertEqual(tela._registros, [])
        tela.procurar(venda.numero)
        self.assertEqual([v.numero for v in tela._registros], [venda.numero])


class ParceiroTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        self.parceiro = self.store.criar_parceiro(Parceiro(nome="Arquiteta", comissao=10.0))
        self.store.criar(Contato(nome="Ana", parceiro_id=self.parceiro.id))
        self.store.criar(Contato(nome="Bia", parceiro_id=self.parceiro.id))
        self.vender("Ana", 100.0)
        self.vender("Bia", 50.0)
        self.vender("Sem parceiro", 999.0)
        self.tela = ParceirosView(self.store, consultas=self.consultas, contas=self.contas)
        self.addCleanup(self.tela.deleteLater)
        self.tela.refresh()
        self.tela.tabela.selectRow(0)

    def test_comissao_sobre_o_que_os_indicados_compraram(self) -> None:
        self.assertEqual(self.tela.vendido_no_mes(self.parceiro), 150.0)
        self.assertEqual(self.tela.comissao_do_mes(self.parceiro), 15.0)

    def test_comissao_vira_conta_a_pagar_uma_vez_por_mes(self) -> None:
        self.tela._lancar_comissao()
        self.tela._lancar_comissao()
        contas = self.contas.repository.listar()
        self.assertEqual([(c.valor, c.categoria) for c in contas], [(15.0, "Comissões")])

    def test_comissao_invalida_e_recusada(self) -> None:
        self.parceiro.comissao = 150.0
        with self.assertRaises(Exception):
            self.store.atualizar_parceiro(self.parceiro)


class AgendaTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        self.repo = self.agenda.repository
        self.destino = DestinoVendas(abrir_vendas(self.pasta / "vendas.db"))
        self.addCleanup(self.destino.close)
        self.destino.contas = self.contas
        self.inicio = f"{date.today().isoformat()}T10:00"

    def compromisso(self, **campos) -> Compromisso:
        return self.repo.salvar(Compromisso(titulo="Corte", cliente="Ana", inicio=self.inicio,
                                            **campos))

    def test_profissionais_diferentes_nao_conflitam(self) -> None:
        self.compromisso(profissional="Bia")
        outro = Compromisso(titulo="Barba", inicio=self.inicio, profissional="Caio")
        self.assertEqual(self.repo.conflitos(outro), [])

    def test_mesmo_profissional_conflita(self) -> None:
        self.compromisso(profissional="Bia")
        outro = Compromisso(titulo="Barba", inicio=self.inicio, profissional="Bia")
        self.assertEqual(len(self.repo.conflitos(outro)), 1)

    def test_sem_profissional_o_horario_e_da_loja(self) -> None:
        self.compromisso()
        outro = Compromisso(titulo="Barba", inicio=self.inicio, profissional="Bia")
        self.assertEqual(len(self.repo.conflitos(outro)), 1)

    def test_grade_filtra_por_profissional(self) -> None:
        self.compromisso(profissional="Bia")
        self.compromisso(profissional="Caio")
        primeiro = date.today()
        grade = self.repo.grade(primeiro, dias=1, profissional="Bia")
        self.assertEqual(len(grade.dias[0].compromissos), 1)
        self.assertEqual(self.repo.profissionais(), ["Bia", "Caio"])

    def test_falta_sai_da_conta_de_quem_vem(self) -> None:
        compromisso = self.compromisso()
        self.repo.definir_status(compromisso.id, FALTOU)
        self.assertEqual(self.repo.obter(compromisso.id).status_label, "Faltou")
        self.assertEqual(self.repo.abertos(), [])

    def test_sinal_entra_recebido_e_uma_vez_so(self) -> None:
        compromisso = self.compromisso(sinal=20.0)
        self.assertTrue(financeiro_agenda.lancar_sinal(self.contas, compromisso))
        financeiro_agenda.lancar_sinal(self.contas, compromisso)
        contas = self.contas.repository.listar()
        self.assertEqual([(c.valor, c.pago) for c in contas], [(20.0, True)])

    def test_gerar_vira_venda_pendente_e_tira_o_sinal(self) -> None:
        from dumtech.apps.agenda.ui.gerar_dialog import GerarDialog

        compromisso = self.compromisso(sinal=20.0, status=CONCLUIDO)
        dialogo = GerarDialog(self.repo, compromisso, [self.destino])
        self.addCleanup(dialogo.deleteLater)
        dialogo.valor.setValue(100.0)
        dialogo.salvar()

        venda = self.vendas.repository.listar()[0]
        self.assertEqual((venda.total, venda.cliente), (80.0, "Ana"))
        self.assertEqual(self.repo.obter(compromisso.id).documento, venda.numero)
        self.assertEqual(self.contas.situacao(venda.numero).em_aberto, 80.0)

    def test_gerar_usa_o_preco_do_servico(self) -> None:
        from dumtech.apps.agenda.online import AjustesOnline, Online, Servico
        from dumtech.apps.agenda.ui.gerar_dialog import GerarDialog

        online = Online(self.repo)
        ajustes = AjustesOnline.padrao()
        ajustes.servicos = [Servico(id="c", nome="Corte", duracao=30, preco=45.0)]
        online.salvar(ajustes, False)
        dialogo = GerarDialog(self.repo, self.compromisso(), [self.destino])
        self.addCleanup(dialogo.deleteLater)
        self.assertEqual(dialogo.valor.value(), 45.0)

    def test_botao_faltou_marca_a_falta(self) -> None:
        from dumtech.apps.agenda.ui.compromissos_view import CompromissosView

        compromisso = self.compromisso()
        tela = CompromissosView(self.repo)
        self.addCleanup(tela.deleteLater)
        tela.filtro_periodo.setCurrentIndex(0)
        tela.refresh()
        tela.tabela.selectRow(0)
        tela.botao_faltou.click()
        self.assertEqual(self.repo.obter(compromisso.id).status, FALTOU)

    def test_botao_gerar_cria_a_venda_pela_tela(self) -> None:
        from unittest import mock

        from dumtech.apps.agenda.ui import compromissos_view

        compromisso = self.compromisso(status=CONCLUIDO)
        tela = compromissos_view.CompromissosView(self.repo, destinos=[self.destino])
        self.addCleanup(tela.deleteLater)
        tela.filtro_periodo.setCurrentIndex(0)
        tela.refresh()
        tela.tabela.selectRow(0)
        real = compromissos_view.GerarDialog

        def abrir(*argumentos):
            dialogo = real(*argumentos)
            dialogo.valor.setValue(60.0)
            dialogo.salvar()
            dialogo.exec = lambda: True
            self.addCleanup(dialogo.deleteLater)
            return dialogo

        with mock.patch.object(compromissos_view, "GerarDialog", abrir):
            tela.botao_gerar.click()
        self.assertTrue(self.repo.obter(compromisso.id).documento)
        self.assertIn("criada", tela.aviso.text())

    def test_tela_so_libera_gerar_para_o_concluido_e_uma_vez(self) -> None:
        from dumtech.apps.agenda.ui.compromissos_view import CompromissosView

        compromisso = self.compromisso(status=CONCLUIDO)
        tela = CompromissosView(self.repo, destinos=[self.destino])
        self.addCleanup(tela.deleteLater)
        tela.filtro_periodo.setCurrentIndex(0)
        tela.refresh()
        tela.tabela.selectRow(0)
        self.assertTrue(tela.botao_gerar.isEnabled())
        self.repo.marcar_documento(compromisso.id, "VEN-1")
        tela.refresh()
        tela.tabela.selectRow(0)
        self.assertFalse(tela.botao_gerar.isEnabled())


if __name__ == "__main__":
    unittest.main()
