"""Teste de fumaca da interface: Hub, aplicativos e troca de tema."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from datetime import date

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QWidget

from dumtech.apps.estoque.models import Produto
from dumtech.apps.vendas.models import Pagamento
from dumtech.core.config import Settings
from dumtech.hub.main_window import PAGINA_APP, PAGINA_INICIO, HubWindow
from dumtech.ui.theme import (
    MODO_AUTO,
    MODO_CLARO,
    MODO_ESCURO,
    ThemeManager,
    palette_for,
)

_app: QApplication | None = None
_theme: ThemeManager | None = None


def setUpModule() -> None:
    """Uma QApplication e UM gerenciador de tema para o arquivo inteiro.

    `ThemeManager` nasce filho da QApplication (nunca e coletado) e cada
    `set_mode` reaplica a folha de estilo na aplicacao toda. Um gerenciador por
    teste fazia o custo crescer a cada janela ja criada - a suite ia de
    segundos a minutos sozinha.
    """
    global _app, _theme
    _app = QApplication.instance() or QApplication([])
    _theme = ThemeManager(_app, MODO_ESCURO)


def _destruir(hub: HubWindow) -> None:
    """Fecha a janela e destroi a arvore de widgets de verdade.

    `deleteLater` sozinho nao basta: `processEvents` NAO entrega eventos
    DeferredDelete. Sem isso os widgets de cada teste ficam vivos, e como
    trocar o tema reaplica a folha de estilo na aplicacao inteira, a suite
    fica mais lenta a cada teste.
    """
    hub.close()
    hub.deleteLater()
    _app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _hub_de_teste(pasta: Path | None = None) -> tuple[Settings, ThemeManager]:
    """Preferencias novas e o tema compartilhado, sempre no escuro."""
    _theme.set_mode(MODO_ESCURO)
    return Settings((pasta or Path(tempfile.mkdtemp())) / "hub.json"), _theme


class InterfaceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        # nos testes nao abrimos caixas de aviso (elas travariam a execucao)
        self.hub.launcher.notify = lambda *args: None

    def tearDown(self) -> None:
        _destruir(self.hub)

    # --------------------------------------------------------------------- hub
    def test_hub_mostra_os_aplicativos(self) -> None:
        self.assertEqual(self.hub.windowTitle(), "DumTech Hub")
        nomes = [e.manifest.short_name for e in self.hub.registry.available()]
        self.assertIn("Estoque", nomes)
        self.assertGreaterEqual(len(nomes), 7)
        # Inicio, Licenca, Configuracoes, Sobre, o aplicativo aberto, as
        # boas-vindas do primeiro acesso, o login e o assistente de conta
        self.assertEqual(self.hub.stack.count(), 8)

    def test_todo_aplicativo_liberado_esta_no_trilho(self) -> None:
        liberados = {e.app_id for e in self.hub.registry.available()}
        self.assertEqual(set(self.hub._app_items), liberados)

    def test_abre_todos_os_aplicativos_dentro_do_hub(self) -> None:
        for entrada in self.hub.registry.available():
            with self.subTest(app=entrada.app_id):
                self.assertTrue(self.hub.open_app(entrada.app_id))
                casca = self.hub.launcher.get(entrada.app_id)
                self.assertEqual(casca.windowTitle(), entrada.manifest.name)
                self.assertGreaterEqual(len(casca.views), 2)
                # montado no Hub: nao virou uma janela solta
                self.assertTrue(casca.embedded)
                self.assertEqual(self.hub.stack.currentIndex(), PAGINA_APP)
                self.assertEqual(self.hub.workspace.current_app, entrada.app_id)

    def test_reabrir_reaproveita_a_mesma_casca(self) -> None:
        self.hub.open_app("estoque")
        casca = self.hub.launcher.get("estoque")
        self.hub.open_app("estoque")
        self.assertIs(self.hub.launcher.get("estoque"), casca)
        self.assertEqual(self.hub.workspace.mounted, ("estoque",))

    def test_trocar_de_aplicativo_mantem_os_dois_montados(self) -> None:
        self.hub.open_app("estoque")
        self.hub.open_app("vendas")
        self.assertEqual(set(self.hub.workspace.mounted), {"estoque", "vendas"})
        self.assertEqual(self.hub.workspace.current_app, "vendas")

    def test_fechar_aplicativo_desmonta_e_volta_para_o_inicio(self) -> None:
        self.hub.open_app("estoque")
        # sem pergunta: a caixa de confirmacao e testada em ConfirmacoesTestCase
        self.hub.close_app("estoque", perguntar=False)
        self.assertEqual(self.hub.workspace.mounted, ())
        self.assertEqual(self.hub.launcher.open_apps, ())
        self.assertIsNone(self.hub.launcher.get("estoque"))
        self.assertEqual(self.hub.stack.currentIndex(), PAGINA_INICIO)

    def test_aplicativo_inexistente_nao_abre(self) -> None:
        self.assertFalse(self.hub.open_app("juridico"))
        self.assertEqual(self.hub.workspace.mounted, ())

    def test_produto_cadastrado_aparece_na_tela(self) -> None:
        self.hub.open_app("estoque")
        casca = self.hub.launcher.get("estoque")
        casca.repository.criar(
            Produto(codigo="TST-1", nome="Produto de teste", quantidade=4, estoque_minimo=1)
        )
        casca.refresh_all()
        self.assertGreaterEqual(casca.produtos_view.tabela.rowCount(), 1)
        self.assertNotEqual(casca.dashboard_view.card_produtos.value_label.text(), "0")

    def test_as_telas_do_aplicativo_saem_na_ordem_em_que_foram_criadas(self) -> None:
        self.hub.open_app("estoque")
        titulos = [v.title for v in self.hub.launcher.get("estoque").views]
        self.assertEqual(titulos[0], "Painel")
        self.assertEqual(len(titulos), self.hub.launcher.get("estoque").stack.count())

    def test_estoque_monta_as_telas(self) -> None:
        self.hub.open_app("estoque")
        casca = self.hub.launcher.get("estoque")
        self.assertEqual(
            [v.title for v in casca.views],
            ["Painel", "Produtos", "Entradas", "Movimentações", "Contagem", "Compras",
             "Fornecedores"],
        )

    def test_estoque_movimenta_pela_lista_de_produtos(self) -> None:
        """A baixa rapida: bipar/selecionar e movimentar sem trocar de tela."""
        self.hub.open_app("estoque")
        casca = self.hub.launcher.get("estoque")
        produto = casca.repository.criar(
            Produto(codigo="BIP-1", nome="Produto bipavel", quantidade=10,
                    codigo_barras="7890000000017")
        )
        casca.produtos_view.refresh()

        # o leitor manda o codigo de barras e um Enter
        self.assertIs(casca.repository.buscar("7890000000017").id, produto.id)

        casca.repository.registrar_saida(produto.id, 3, "Venda")
        casca.refresh_all()
        self.assertEqual(casca.repository.obter(produto.id).quantidade, 7)
        self.assertGreaterEqual(casca.produtos_view.tabela.rowCount(), 1)

    def test_estoque_contagem_aparece_na_tela(self) -> None:
        self.hub.open_app("estoque")
        casca = self.hub.launcher.get("estoque")
        produto = casca.repository.criar(
            Produto(codigo="CT-9", nome="Contado", quantidade=10)
        )
        casca.repository.contar(produto.id, 8)
        casca.contagem_view.refresh()
        self.assertEqual(casca.contagem_view.tabela.rowCount(), 1)
        self.assertTrue(casca.contagem_view.botao_aplicar.isEnabled())

    # ------------------------------------------------------- paleta de comandos
    def test_paleta_encontra_aplicativo_por_parte_do_nome(self) -> None:
        from dumtech.ui.widgets.command_palette import filtrar

        comandos = self.hub.build_commands()
        self.assertEqual(filtrar(comandos, "orca")[0].title, "Orçamentos")
        self.assertEqual(filtrar(comandos, "vnd")[0].title, "Vendas")
        self.assertEqual(filtrar(comandos, "xyzw"), [])

    def test_paleta_lista_as_telas_de_quem_esta_aberto(self) -> None:
        titulos = lambda: [c.title for c in self.hub.build_commands()]
        self.assertNotIn("Estoque > Produtos", titulos())

        self.hub.open_app("estoque")
        self.assertIn("Estoque > Produtos", titulos())
        self.assertIn("Fechar Estoque", titulos())

    def test_paleta_pula_direto_para_uma_tela(self) -> None:
        self.hub._ir_para_tela("estoque", 1)
        self.assertEqual(self.hub.launcher.get("estoque").current_view, 1)

    # -------------------------------------------------------------------- tema
    def test_hub_troca_o_tema_da_plataforma(self) -> None:
        self.assertEqual(self.theme.mode, MODO_ESCURO)
        self.hub._toggle_theme()
        self.assertEqual(self.theme.mode, MODO_CLARO)
        self.assertEqual(self.settings.get("hub", "theme"), MODO_CLARO)

    def _tema_de_um_modal(self, app_id: str) -> str:
        """A paleta que um dialogo aberto de dentro do aplicativo vai usar."""
        from dumtech.ui.theme import palette_for

        casca = self.hub.launcher.get(app_id)
        return palette_for(casca.views[1].widget).name

    def test_modal_acompanha_a_troca_de_tema_com_o_app_ja_aberto(self) -> None:
        """O caso que quebrava: casca montada guardava a paleta de quando nasceu."""
        self.hub.open_app("estoque")
        self.assertEqual(self._tema_de_um_modal("estoque"), MODO_ESCURO)

        self.theme.set_mode(MODO_CLARO)
        self.assertEqual(self._tema_de_um_modal("estoque"), MODO_CLARO)

        self.theme.set_mode(MODO_ESCURO)
        self.assertEqual(self._tema_de_um_modal("estoque"), MODO_ESCURO)

    def test_modal_ignora_a_preferencia_antiga_de_tema_do_aplicativo(self) -> None:
        """Quem usou 'sempre claro' no app nao pode abrir modal branco na Hub escura."""
        self.settings.set("app:vendas", "theme", MODO_CLARO)
        self.settings.save()
        self.hub.open_app("vendas")
        self.assertEqual(self._tema_de_um_modal("vendas"), MODO_ESCURO)

    def test_dialogos_do_qt_respondem_em_portugues(self) -> None:
        """Caixa que pergunta em portugues nao pode responder "Yes/No"."""
        from PySide6.QtWidgets import QMessageBox

        from dumtech.main import _traduzir_qt

        _traduzir_qt(_app)
        caixa = QMessageBox(
            QMessageBox.Icon.Question, "Excluir", "Excluir mesmo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            self.hub,
        )
        rotulos = [b.text().replace("&", "") for b in caixa.buttons()]
        self.assertEqual(rotulos, ["Sim", "Não"])
        caixa.deleteLater()

    def test_aplicativo_montado_no_hub_segue_o_tema_do_hub(self) -> None:
        self.hub.open_app("estoque")
        casca = self.hub.launcher.get("estoque")
        self.assertEqual(casca.resolved_palette().name, MODO_ESCURO)

        self.theme.set_mode(MODO_CLARO)
        self.assertEqual(casca.resolved_palette().name, MODO_CLARO)

        # mesmo com preferencia fixada: dentro da janela unica quem manda e o Hub
        casca._apply_theme_mode(MODO_ESCURO)
        self.assertEqual(casca.resolved_palette().name, MODO_CLARO)


class BalcaoTestCase(unittest.TestCase):
    """O PDV: bipar, somar e fechar - sem abrir formulario."""

    def setUp(self) -> None:
        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None
        self.hub.open_app("vendas")
        self.casca = self.hub.launcher.get("vendas")
        self.balcao = self.casca.balcao_view
        self._limpar_banco()

    def _limpar_banco(self) -> None:
        """Os aplicativos compartilham o mesmo vendas.db durante a suite."""
        for tabela in ("devolucao_itens", "devolucoes", "pagamentos", "venda_itens",
                       "caixa_movimentos", "caixas", "vendas"):
            self.casca.repository.db.execute(f"DELETE FROM {tabela}")
        self.casca.refresh_all()

    def tearDown(self) -> None:
        _destruir(self.hub)

    def _bipar(self, texto: str, quantidade: float = 1, valor: float = 0.0) -> None:
        self.balcao.bipe.setText(texto)
        self.balcao._localizar()
        if quantidade:
            self.balcao.quantidade.setValue(quantidade)
        if valor:
            self.balcao.valor.setValue(valor)
        self.balcao._adicionar()

    def test_vendas_comeca_pelo_balcao(self) -> None:
        self.assertEqual(
            [v.title for v in self.casca.views],
            ["Balcão", "Painel", "Vendas", "Caixa", "Resultado"],
        )

    def test_item_avulso_entra_na_venda(self) -> None:
        self._bipar("Servico de instalacao", 2, 30.0)
        self.assertEqual(len(self.balcao.itens), 1)
        self.assertEqual(self.balcao.tabela.rowCount(), 1)
        self.assertIn("60,00", self.balcao.total.text())
        self.assertTrue(self.balcao.botao_receber.isEnabled())

    def test_produto_do_estoque_chega_com_preco_e_saldo(self) -> None:
        from dumtech.apps.estoque.models import Produto

        catalogo = self.casca.repository.catalogo
        catalogo.repository.criar(
            Produto(codigo="PDV-1", nome="Produto do balcao", quantidade=5,
                    preco_venda=12.5, codigo_barras="7899999000015")
        )
        self.balcao.bipe.setText("7899999000015")
        self.balcao._localizar()

        self.assertEqual(self.balcao.valor.value(), 12.5)
        self.assertIn("saldo", self.balcao.achado.text())

        self.balcao.quantidade.setValue(2)
        self.balcao._adicionar()
        item = self.balcao.itens[0]
        self.assertTrue(item.do_estoque)
        self.assertEqual(item.codigo, "PDV-1")
        self.assertEqual(self.balcao.itens[0].total, 25.0)

    def test_bipar_o_mesmo_produto_soma_em_vez_de_repetir_linha(self) -> None:
        from dumtech.apps.estoque.models import Produto

        self.casca.repository.catalogo.repository.criar(
            Produto(codigo="PDV-2", nome="Repetido", quantidade=50, preco_venda=10.0)
        )
        self._bipar("PDV-2")
        self._bipar("PDV-2")
        self.assertEqual(len(self.balcao.itens), 1)
        self.assertEqual(self.balcao.itens[0].quantidade, 2)

    def test_desconto_muda_o_total_na_hora(self) -> None:
        self._bipar("Item", 1, 100.0)
        self.balcao.desconto.setValue(10.0)
        self.assertIn("90,00", self.balcao.total.text())

    def test_receber_sem_item_avisa_em_vez_de_abrir_o_pagamento(self) -> None:
        self.balcao.receber()
        self.assertIn("Adicione um item", self.balcao.aviso.text())

    def test_receber_abre_o_pagamento_de_verdade_e_guarda_o_vendedor(self) -> None:
        """Os outros testes trocam o dialogo por um falso, e foi assim que um
        argumento que ele nao aceita chegou ao cliente e travou o Receber."""
        from unittest import mock

        from dumtech.apps.vendas.repository import pagamento_unico
        from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

        def pagar(dialogo) -> int:
            dialogo.pagamentos = [pagamento_unico("Dinheiro", 50.0)]
            return 1

        self.balcao.vendedor.addItem("Bia", "Bia")
        self.balcao.vendedor.setCurrentIndex(1)
        self._bipar("Item", 1, 50.0)
        with mock.patch.object(PagamentoDialog, "exec", pagar):
            self.balcao.receber()
        vendas = self.casca.repository.listar()
        self.assertEqual(len(vendas), 1, self.balcao.aviso.text())
        self.assertEqual(vendas[0].vendedor, "Bia")

    def test_descartar_a_venda_nao_grava_nada(self) -> None:
        self._bipar("Item", 1, 50.0)
        self.balcao._limpar()
        self.assertEqual(self.balcao.itens, [])
        self.assertEqual(self.casca.repository.listar(), [])

    def test_venda_finalizada_aparece_nas_outras_telas(self) -> None:
        from dumtech.apps.vendas.repository import pagamento_unico

        venda = self.casca.repository.finalizar(
            self._venda_simples(), [pagamento_unico("Dinheiro", 50.0)]
        )
        self.casca.refresh_all()
        self.assertEqual(self.casca.vendas_view.tabela.rowCount(), 1)
        self.assertIn(venda.numero, self.casca.vendas_view.tabela.item(0, 0).text())

    def _venda_simples(self):
        from dumtech.apps.vendas.models import ItemVenda, Venda

        return Venda(itens=[ItemVenda(descricao="Item", quantidade=1, valor_unitario=50.0)])

    def test_caixa_mostra_a_conta_da_gaveta(self) -> None:
        caixa = self.casca.caixa_view
        self.assertIn("Nenhum caixa aberto", caixa.subtitulo.text())
        self.assertEqual(caixa.botao_principal.text().strip(), "Abrir caixa")
        self.assertFalse(caixa.botao_sangria.isEnabled())

        self.casca.repository.abrir_caixa(150.0)
        caixa.refresh()
        self.assertEqual(caixa.botao_principal.text().strip(), "Fechar caixa")
        self.assertTrue(caixa.botao_sangria.isEnabled())
        self.assertIn("150,00", caixa.card_gaveta.value_label.text())
        # a conta aparece linha a linha, nao como um numero solto
        self.assertGreaterEqual(caixa._contas.count(), 6)

    def test_comprovante_sai_do_mesmo_texto_que_vai_para_o_papel(self) -> None:
        from dumtech.apps.vendas.recibo import comprovante

        venda = self.casca.repository.finalizar(
            self._venda_simples(), [Pagamento(forma="Dinheiro", valor=50.0, recebido=100.0)]
        )
        texto = comprovante(self.casca.repository.obter(venda.id))
        self.assertIn(venda.numero, texto)
        self.assertIn("TROCO", texto)
        self.assertIn("Documento sem valor fiscal", texto)
        self.assertTrue(all(len(linha) <= 40 for linha in texto.splitlines()))


class FluxoDeCaixaTestCase(unittest.TestCase):
    """O Financeiro: projecao, contas e baixa parcial na tela."""

    def setUp(self) -> None:
        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None
        self.hub.open_app("financeiro")
        self.casca = self.hub.launcher.get("financeiro")
        self.repo = self.casca.repository
        self._limpar_banco()

    def tearDown(self) -> None:
        _destruir(self.hub)

    def _limpar_banco(self) -> None:
        """Os aplicativos compartilham o mesmo financeiro.db durante a suite."""
        for tabela in ("baixas", "transferencias", "lancamentos", "contas"):
            self.repo.db.execute(f"DELETE FROM {tabela}")
        self.casca.refresh_all()

    @staticmethod
    def _dia(offset: int) -> str:
        from datetime import date, timedelta

        return (date.today() + timedelta(days=offset)).isoformat()

    def _conta(self, saldo: float):
        from dumtech.apps.financeiro.models import Conta

        return self.repo.criar_conta(Conta(nome="Banco", saldo_inicial=saldo))

    def _despesa(self, valor: float, dias: int):
        from dumtech.apps.financeiro.models import DESPESA, Lancamento

        return self.repo.criar(Lancamento(
            tipo=DESPESA, descricao="Fornecedor", valor=valor,
            vencimento=self._dia(dias),
        ))

    def test_financeiro_comeca_pelo_fluxo(self) -> None:
        self.assertEqual(
            [v.title for v in self.casca.views],
            ["Fluxo de caixa", "Visão geral", "Lançamentos", "Resultado", "Contas bancárias"],
        )

    def test_sem_conta_a_tela_ensina_o_proximo_passo(self) -> None:
        fluxo = self.casca.fluxo_view
        fluxo.refresh()
        self.assertIn("R$ 0,00", fluxo.card_hoje.value_label.text())
        self.assertIn("não fica negativo", fluxo.recado.text())

    def test_a_tela_diz_o_dia_em_que_o_dinheiro_acaba(self) -> None:
        self._conta(100.0)
        self._despesa(500.0, 7)

        fluxo = self.casca.fluxo_view
        fluxo.refresh()
        self.assertIn("Saldo negativo em", fluxo.recado.text())
        self.assertIn("-R$ 400,00", fluxo.recado.text())
        self.assertEqual(fluxo.projecao.dia_no_vermelho.data, self._dia(7))
        # so os dias com movimento entram na tabela
        self.assertEqual(fluxo.tabela.rowCount(), 1)

    def test_o_grafico_recebe_a_mesma_serie_da_tela(self) -> None:
        self._conta(1000.0)
        self._despesa(300.0, 3)
        fluxo = self.casca.fluxo_view
        fluxo.refresh()

        self.assertEqual(fluxo.grafico.valores,
                         [dia.saldo for dia in fluxo.projecao.dias])
        self.assertEqual(len(fluxo.grafico.valores), 31)
        # o eixo horizontal precisa de um rotulo por ponto
        self.assertEqual(len(fluxo.grafico.rotulos), 31)

    def test_o_dia_do_aperto_e_marcado_na_linha(self) -> None:
        """O rotulo da marca ja saiu cortado no pe do cartao: ele fica na area."""
        self._conta(100.0)
        self._despesa(400.0, 7)
        fluxo = self.casca.fluxo_view
        fluxo.refresh()

        self.assertIsNotNone(fluxo.grafico.marca)
        self.assertIn("-R$ 300,00", fluxo.grafico.marca_texto)
        self.assertEqual(fluxo.grafico.valores[fluxo.grafico.marca], -300.0)

    def test_vencido_aparece_como_recado_no_fluxo(self) -> None:
        self._conta(0.0)
        self._despesa(80.0, -5)
        fluxo = self.casca.fluxo_view
        fluxo.refresh()
        self.assertIn("Vencidos entram no dia de hoje", fluxo.atrasados.text())

    def test_saldo_atual_diz_o_que_soma(self) -> None:
        fluxo = self.casca.fluxo_view
        fluxo.refresh()
        self.assertEqual(fluxo.card_hoje.title_label.text(), "Saldo atual")
        self.assertEqual(fluxo.card_hoje.hint_label.text(), "Caixa + contas bancárias")

    def test_primeiro_grafico_e_so_o_que_ja_andou(self) -> None:
        """Entradas e Saidas do mes pela baixa; o que so vence nao entra."""
        from dumtech.apps.financeiro.models import Lancamento

        conta = self._conta(0.0)
        recebida = self.repo.criar(Lancamento(descricao="Servico", valor=500.0,
                                              vencimento=self._dia(0)))
        self.repo.baixar(recebida.id, conta_id=conta.id)
        paga = self._despesa(120.0, 0)
        self.repo.baixar(paga.id, conta_id=conta.id)
        self._despesa(900.0, 5)                       # ainda nao saiu

        fluxo = self.casca.fluxo_view
        fluxo.refresh()
        fatias = {f.rotulo: f.valor for f in fluxo.grafico_realizado.fatias}
        self.assertEqual(fatias, {"Entradas": 500.0, "Saídas": 120.0})
        self.assertEqual(fluxo.resultado.text(), "+ R$ 380,00")

    def test_sem_movimento_o_realizado_diz_em_palavras(self) -> None:
        fluxo = self.casca.fluxo_view
        fluxo.refresh()
        self.assertEqual(fluxo.grafico_realizado.fatias, [])

    def test_grafico_da_projecao_diz_o_periodo(self) -> None:
        fluxo = self.casca.fluxo_view
        fluxo.refresh()
        self.assertEqual(fluxo.periodo.text(), "próximos 30 dias")
        fluxo.horizonte.setCurrentIndex(fluxo.horizonte.findData(60))
        self.assertEqual(fluxo.periodo.text(), "próximos 60 dias")

    def test_visao_geral_mostra_o_resultado_do_periodo(self) -> None:
        from dumtech.apps.financeiro.models import Lancamento

        conta = self._conta(0.0)
        recebida = self.repo.criar(Lancamento(descricao="Servico", valor=200.0,
                                              vencimento=self._dia(0)))
        self.repo.baixar(recebida.id, conta_id=conta.id)
        paga = self._despesa(450.0, 0)
        self.repo.baixar(paga.id, conta_id=conta.id)

        visao = self.casca.dashboard_view
        visao.refresh()
        self.assertEqual(visao.card_saldo.title_label.text(), "Saldo disponível")
        fatias = visao.grafico_resultado.fatias
        self.assertEqual([f.valor for f in fatias], [200.0, 450.0, -250.0])
        self.assertEqual(fatias[2].texto, "- R$ 250,00")
        self.assertEqual(fatias[2].tom, "danger")

    def test_baixa_parcial_aparece_na_lista(self) -> None:
        from dumtech.apps.financeiro.models import Lancamento

        lancamento = self.repo.criar(Lancamento(
            descricao="Servico", valor=1000.0, vencimento=self._dia(2)
        ))
        self.repo.baixar(lancamento.id, 300.0)

        lista = self.casca.lancamentos_view
        lista.refresh()
        self.assertEqual(lista.tabela.rowCount(), 1)
        self.assertEqual(lista.tabela.item(0, 5).text(), "R$ 700,00")
        self.assertEqual(lista.tabela.item(0, 6).text(), "Parcial")

    def test_parcelas_viram_linhas_separadas_com_o_rotulo(self) -> None:
        from dumtech.apps.financeiro.models import DESPESA, Lancamento

        self.repo.parcelar(
            Lancamento(tipo=DESPESA, descricao="Equipamento", valor=1200.0,
                       vencimento=self._dia(1)),
            3,
        )
        lista = self.casca.lancamentos_view
        lista.refresh()
        self.assertEqual(lista.tabela.rowCount(), 3)
        self.assertIn("(3/3)", lista.tabela.item(0, 1).text())
        self.assertIn("(1/3)", lista.tabela.item(2, 1).text())

    def test_contas_mostram_o_saldo_e_o_total(self) -> None:
        self._conta(1500.0)
        contas = self.casca.contas_view
        contas.refresh()
        self.assertEqual(contas.tabela.rowCount(), 1)
        self.assertEqual(contas.total.text(), "R$ 1.500,00")
        self.assertIn("1 conta ativa", contas.subtitulo.text())
        # transferir precisa de duas contas
        self.assertFalse(contas.botao_transferir.isEnabled())

    def test_conta_com_movimento_avisa_em_vez_de_sumir(self) -> None:
        from dumtech.apps.financeiro.models import Lancamento

        conta = self._conta(0.0)
        lancamento = self.repo.criar(Lancamento(
            descricao="Servico", valor=100.0, vencimento=self._dia(0)
        ))
        self.repo.baixar(lancamento.id, conta_id=conta.id)

        contas = self.casca.contas_view
        contas.refresh()
        contas.tabela.selectRow(0)
        contas._excluir()
        self.assertIn("já tem movimento", contas.aviso.text())
        self.assertEqual(contas.tabela.rowCount(), 1)


class OficinaTestCase(unittest.TestCase):
    """A Ordem de Servico: quadro por etapa, ficha e comprovantes."""

    def setUp(self) -> None:
        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None
        self.hub.open_app("ordens")
        self.casca = self.hub.launcher.get("ordens")
        self.repo = self.casca.repository
        for tabela in ("os_itens", "os_historico", "ordens"):
            self.repo.db.execute(f"DELETE FROM {tabela}")
        self.casca.refresh_all()

    def tearDown(self) -> None:
        _destruir(self.hub)

    def _ordem(self, **campos):
        from dumtech.apps.ordens.models import Ordem

        dados = dict(
            numero=self.repo.proximo_numero(), cliente="Joao da Silva",
            equipamento="Notebook Dell G15", defeito="Nao liga",
        )
        dados.update(campos)
        return self.repo.salvar(Ordem(**dados))

    def test_arrastar_o_cartao_para_outra_faixa_muda_a_etapa(self) -> None:
        from dumtech.apps.ordens.models import ABERTA, ANDAMENTO

        ordem = self._ordem()
        bancada = self.casca.bancada_view
        self.assertEqual(self.repo.obter(ordem.id).status, ABERTA)

        bancada._mover_para(ordem.id, ANDAMENTO)

        self.assertEqual(self.repo.obter(ordem.id).status, ANDAMENTO)
        self.assertIn("Em andamento", bancada.aviso.text())
        # o passo fica no historico, como qualquer mudanca de etapa
        historico = self.repo.historico_de(ordem.id)
        self.assertTrue(any("quadro" in e.observacao.lower() for e in historico))

    def test_soltar_na_propria_faixa_nao_faz_nada(self) -> None:
        from dumtech.apps.ordens.models import ABERTA

        ordem = self._ordem()
        bancada = self.casca.bancada_view
        bancada._mover_para(ordem.id, ABERTA)
        self.assertEqual(self.repo.obter(ordem.id).status, ABERTA)
        self.assertEqual(len(self.repo.historico_de(ordem.id)), 1)

    def test_as_faixas_aceitam_o_que_e_solto_nelas(self) -> None:
        for status, faixa in self.casca.bancada_view.faixas.items():
            with self.subTest(status):
                self.assertTrue(faixa.acceptDrops())

    def test_excluir_pelo_menu_do_cartao(self) -> None:
        from dumtech.core import confirmacoes

        ordem = self._ordem()
        confirmacoes.nunca_mais(confirmacoes.EXCLUIR)  # sem abrir caixa no teste
        self.casca.bancada_view._excluir(ordem.id)

        self.assertIsNone(self.repo.obter(ordem.id))
        self.assertIsNone(self.casca.bancada_view.selecionada)

    def test_ordens_comeca_pelo_quadro(self) -> None:
        self.assertEqual(
            [v.title for v in self.casca.views], ["Quadro", "Painel", "Ordens de Serviço"]
        )

    def test_cada_ordem_vira_um_cartao_na_faixa_da_etapa(self) -> None:
        from dumtech.apps.ordens.models import ABERTA, AGUARDANDO

        aberta = self._ordem()
        esperando = self._ordem(cliente="Maria Souza", equipamento="Impressora")
        self.repo.avancar(esperando.id)

        bancada = self.casca.bancada_view
        bancada.refresh()
        self.assertEqual(bancada.faixas[ABERTA].contador.text(), "1")
        self.assertEqual(bancada.faixas[AGUARDANDO].contador.text(), "1")
        self.assertEqual(len(bancada._cartoes), 2)
        self.assertIn("2 servicos em andamento", bancada.subtitulo.text())
        del aberta

    def test_o_quadro_avisa_o_que_passou_do_prazo(self) -> None:
        from datetime import date, timedelta

        ontem = (date.today() - timedelta(days=1)).isoformat()
        self._ordem(prazo=ontem)
        bancada = self.casca.bancada_view
        bancada.refresh()
        self.assertIn("passou do prazo", bancada.subtitulo.text())

    def test_o_botao_diz_qual_e_a_proxima_acao(self) -> None:
        ordem = self._ordem()
        bancada = self.casca.bancada_view
        bancada.refresh()
        self.assertFalse(bancada.botao_avancar.isEnabled())

        bancada._selecionar(ordem.id)
        self.assertTrue(bancada.botao_avancar.isEnabled())
        self.assertIn("Mandar para aprovação", bancada.botao_avancar.text())

        self.repo.avancar(ordem.id)
        bancada.refresh()
        bancada._selecionar(ordem.id)
        self.assertIn("Registrar aprovação", bancada.botao_avancar.text())

    def test_faixa_vazia_ensina_em_vez_de_ficar_em_branco(self) -> None:
        from dumtech.apps.ordens.models import CONCLUIDA

        bancada = self.casca.bancada_view
        bancada.refresh()
        self.assertIn("Nada pronto para entregar", bancada.faixas[CONCLUIDA].vazio.text())

    def test_a_lista_mostra_o_tempo_parado_e_a_garantia(self) -> None:
        from datetime import date, timedelta

        ordem = self._ordem(garantia_dias=90)
        self.repo.avancar(ordem.id)
        self.repo.aprovar(ordem.id, "Joao da Silva")
        self.repo.avancar(ordem.id)
        self.repo.entregar(ordem.id, "Joao da Silva")

        lista = self.casca.ordens_view
        lista.filtro_status.setCurrentIndex(0)   # todas as ordens
        lista.refresh()
        self.assertEqual(lista.tabela.rowCount(), 1)
        limite = (date.today() + timedelta(days=90)).strftime("%d/%m/%Y")
        self.assertIn(f"garantia até {limite}", lista.tabela.item(0, 6).text())

    def test_o_filtro_padrao_mostra_o_que_esta_na_oficina(self) -> None:
        na_oficina = self._ordem()
        pronta = self._ordem(cliente="Outro cliente", equipamento="Impressora")
        self.repo.avancar(pronta.id)
        self.repo.aprovar(pronta.id, "Outro cliente")
        self.repo.avancar(pronta.id)
        self.repo.entregar(pronta.id)

        lista = self.casca.ordens_view
        lista.refresh()
        self.assertEqual(lista.tabela.rowCount(), 1)
        self.assertEqual(lista.tabela.item(0, 0).text(), na_oficina.numero)

    def test_a_ficha_guarda_os_acessorios_marcados(self) -> None:
        from dumtech.apps.ordens.ui.ordem_dialog import AcessoriosPicker

        escolha = AcessoriosPicker("Carregador\nMochila azul")
        marcados = [c.text() for c in escolha.caixas if c.isChecked()]
        self.assertEqual(marcados, ["Carregador"])
        self.assertEqual(escolha.outros.text(), "Mochila azul")
        self.assertEqual(escolha.texto(), "Carregador\nMochila azul")

    def test_comprovantes_saem_do_mesmo_motor_de_40_colunas(self) -> None:
        from dumtech.apps.ordens.recibo import entrada, entrega

        ordem = self._ordem(
            acessorios="Carregador", condicao="Risco na tampa", garantia_dias=90
        )
        papel = entrada(self.repo.obter(ordem.id))
        self.assertIn("[X] Carregador", papel)
        self.assertTrue(all(len(linha) <= 40 for linha in papel.splitlines()))

        self.repo.avancar(ordem.id)
        self.repo.aprovar(ordem.id, "Joao da Silva")
        self.repo.avancar(ordem.id)
        entregue = self.repo.entregar(ordem.id, "Joao da Silva")
        self.assertIn("Garantia (90 dias)", entrega(entregue))


class PropostaTestCase(unittest.TestCase):
    """Orcamentos: funil, conversao, motivo da recusa e o documento."""

    def setUp(self) -> None:
        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None
        self.hub.open_app("orcamentos")
        self.casca = self.hub.launcher.get("orcamentos")
        self.repo = self.casca.repository
        for tabela in ("orcamento_itens", "orcamentos"):
            self.repo.db.execute(f"DELETE FROM {tabela}")
        self.casca.refresh_all()

    def tearDown(self) -> None:
        _destruir(self.hub)

    def _orcamento(self, cliente="Mercado Central", valor=1800.0):
        from dumtech.apps.orcamentos.models import ItemOrcamento, Orcamento

        return self.repo.salvar(Orcamento(
            numero=self.repo.proximo_numero(), cliente=cliente,
            itens=[ItemOrcamento(descricao="Instalacao", valor_unitario=valor)],
        ))

    def test_orcamentos_tem_duas_telas_comecando_pelo_funil(self) -> None:
        self.assertEqual([v.title for v in self.casca.views], ["Funil", "Orçamentos"])

    def test_o_funil_mostra_as_quatro_etapas(self) -> None:
        funil = self.casca.funil_view
        funil.refresh()
        self.assertEqual(funil._etapas.count(), 4)
        self.assertIn("Nenhuma proposta cadastrada", funil.subtitulo.text())

    def test_a_conversao_conta_so_quem_respondeu(self) -> None:
        from dumtech.apps.orcamentos.models import MOTIVO_PRECO

        aprovado = self._orcamento("Cliente A")
        self.repo.aprovar(aprovado.id)
        perdido = self._orcamento("Cliente B")
        self.repo.recusar(perdido.id, MOTIVO_PRECO)
        self._orcamento("Cliente C")   # ainda em aberto: nao entra na conta

        funil = self.casca.funil_view
        funil.refresh()
        self.assertEqual(funil.card_conversao.value_label.text(), "50%")
        self.assertIn("de 2 respondidas", funil.card_conversao.hint_label.text())

    def test_sem_recusa_o_painel_de_motivos_ensina_em_vez_de_ficar_vazio(self) -> None:
        funil = self.casca.funil_view
        funil.refresh()
        primeiro = funil._motivos.itemAt(0).widget()
        self.assertIn("Nenhuma proposta recusada ainda", primeiro.text())

    def test_por_que_voce_perde_aparece_no_funil(self) -> None:
        from dumtech.apps.orcamentos.models import MOTIVO_CONCORRENTE

        perdido = self._orcamento("Cliente B")
        self.repo.recusar(perdido.id, MOTIVO_CONCORRENTE)

        funil = self.casca.funil_view
        funil.refresh()
        self.assertEqual(funil._motivos.count(), 1)

    def test_a_lista_diz_ha_quanto_tempo_a_proposta_esta_parada(self) -> None:
        from datetime import date, timedelta

        orcamento = self._orcamento()
        self.repo.enviar(orcamento.id, quando=(date.today() - timedelta(days=8)).isoformat())

        lista = self.casca.orcamentos_view
        lista.refresh()
        self.assertIn("esperando há 8 dias", lista.tabela.item(0, 3).text())

    def test_a_lista_diz_por_que_perdeu(self) -> None:
        from dumtech.apps.orcamentos.models import MOTIVO_PRECO

        orcamento = self._orcamento()
        self.repo.recusar(orcamento.id, MOTIVO_PRECO)

        lista = self.casca.orcamentos_view
        lista.refresh()
        self.assertIn("achou caro", lista.tabela.item(0, 3).text())

    def test_duplicar_cria_um_rascunho_novo(self) -> None:
        orcamento = self._orcamento()
        self.repo.aprovar(orcamento.id)

        lista = self.casca.orcamentos_view
        lista.refresh()
        lista.tabela.selectRow(0)
        lista._duplicar()

        self.assertEqual(lista.tabela.rowCount(), 2)
        self.assertIn("criada a partir da", lista.aviso.text())

    def test_o_documento_sai_do_mesmo_motor_de_40_colunas(self) -> None:
        from dumtech.apps.orcamentos.recibo import proposta

        orcamento = self._orcamento()
        orcamento.condicao_pagamento = "3x sem juros"
        orcamento.prazo_entrega = "10 dias uteis"
        self.repo.salvar(orcamento)

        texto = proposta(self.repo.obter(orcamento.id))
        self.assertIn("PROPOSTA COMERCIAL", texto)
        self.assertIn("3x sem juros", texto)
        self.assertTrue(all(len(linha) <= 40 for linha in texto.splitlines()))


class GradeDaAgendaTestCase(unittest.TestCase):
    """A Agenda: grade, conflito, bloqueio e clique no vazio."""

    def setUp(self) -> None:
        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None
        self.hub.open_app("agenda")
        self.casca = self.hub.launcher.get("agenda")
        self.repo = self.casca.repository
        self.repo.db.execute("DELETE FROM compromissos")
        self.casca.refresh_all()

    def tearDown(self) -> None:
        _destruir(self.hub)

    @staticmethod
    def _quando(dias: int = 0, hora: int = 9, minuto: int = 0) -> str:
        from datetime import date, datetime, time, timedelta

        momento = datetime.combine(
            date.today() + timedelta(days=dias), time(hora, minuto)
        )
        return momento.isoformat(timespec="minutes")

    def _marcar(self, **campos):
        from dumtech.apps.agenda.models import Compromisso

        dados = dict(titulo="Visita tecnica", cliente="Mercado Central",
                     inicio=self._quando(0, 9), duracao_min=60)
        dados.update(campos)
        return self.repo.salvar(Compromisso(**dados))

    def test_agenda_comeca_pela_grade_e_tem_o_link_online(self) -> None:
        self.assertEqual(
            [v.title for v in self.casca.views], ["Agenda", "Compromissos", "Serviços", "Online"]
        )

    def test_a_grade_desenha_uma_coluna_por_dia_da_semana(self) -> None:
        vista = self.casca.agenda_view
        vista.refresh()
        self.assertEqual(len(vista.grade.grade.dias), 7)
        self.assertIn("Nenhum compromisso", vista.subtitulo.text())

    def test_o_titulo_e_o_periodo_e_a_grade_abre_no_horario_da_loja(self) -> None:
        from dumtech.apps.agenda.models import titulo_do_periodo

        vista = self.casca.agenda_view
        vista.refresh()
        self.assertEqual(vista.titulo.text(), titulo_do_periodo(vista.primeiro_dia, 7))
        self.assertEqual(vista.faixa.currentData(), "loja")
        self.assertIn("8h às 19h", vista.faixa.currentText())
        self.assertEqual((vista.grade.grade.hora_inicial, vista.grade.grade.hora_final), (8, 19))
        self.assertIsNotNone(vista.grade.expediente)

    def test_o_compromisso_aparece_na_grade(self) -> None:
        self._marcar()
        vista = self.casca.agenda_view
        vista.refresh()
        self.assertEqual(vista.grade.grade.total, 1)
        self.assertIn("1 compromisso", vista.subtitulo.text())

    def test_o_cabecalho_dos_dias_fica_parado_ao_rolar(self) -> None:
        """Rolou a grade: o cabecalho cobre o topo, e clicar nele nao marca nada."""
        from PySide6.QtCore import QPointF

        from dumtech.apps.agenda.ui.grade import CABECALHO, GUTTER

        vista = self.casca.agenda_view
        vista.faixa.setCurrentIndex(vista.faixa.findData("dia"))
        grade = vista.grade
        grade.resize(700, 1600)
        grade.move(0, -400)                      # o que a area de rolagem faz
        no_cabecalho = QPointF(GUTTER + 20, 400 + CABECALHO / 2)
        logo_abaixo = QPointF(GUTTER + 20, 400 + CABECALHO + 6)
        self.assertEqual(grade._momento_em(no_cabecalho), "")
        self.assertIsNone(grade._bloco_em(no_cabecalho))
        self.assertTrue(grade._momento_em(logo_abaixo))

    def test_navegar_troca_a_semana_e_hoje_volta(self) -> None:
        from datetime import timedelta

        from dumtech.apps.agenda.models import inicio_da_semana
        from datetime import date

        vista = self.casca.agenda_view
        inicial = vista.primeiro_dia
        vista._navegar(1)
        self.assertEqual(vista.primeiro_dia, inicial + timedelta(days=7))
        vista._ir_para_hoje()
        self.assertEqual(vista.primeiro_dia, inicio_da_semana(date.today()))

    def test_o_modo_dia_mostra_uma_coluna_so(self) -> None:
        vista = self.casca.agenda_view
        vista.modo.setCurrentIndex(1)   # Dia
        self.assertEqual(len(vista.grade.grade.dias), 1)

    def test_o_clique_no_vazio_vira_dia_e_hora(self) -> None:
        """O sinal nao e exercitado aqui: ele abre dialogo modal e travaria."""
        from PySide6.QtCore import QPointF

        from dumtech.apps.agenda.ui.grade import CABECALHO, GUTTER

        vista = self.casca.agenda_view
        vista.modo.setCurrentIndex(1)          # Dia: uma coluna so
        grade = vista.grade
        grade.resize(600, 700)

        # a altura da hora agora depende do tamanho da grade: ela estica para o
        # dia caber na tela, entao a conta sai do proprio widget
        ponto = QPointF(GUTTER + 20, CABECALHO + grade._altura_hora() * 2.6)
        momento = grade._momento_em(ponto)
        esperado = grade.grade.hora_inicial + 2
        self.assertTrue(momento.endswith(f"{esperado:02d}:30"), momento)
        self.assertTrue(momento.startswith(date.today().isoformat()))

        # clique no cabecalho ou na regua de horas nao marca nada
        self.assertEqual(grade._momento_em(QPointF(GUTTER + 20, 10)), "")
        self.assertEqual(grade._momento_em(QPointF(10, CABECALHO + 40)), "")

    def test_selecionar_liga_as_acoes(self) -> None:
        compromisso = self._marcar()
        vista = self.casca.agenda_view
        vista.refresh()
        self.assertFalse(vista.botao_concluir.isEnabled())

        vista._selecionar(compromisso.id)
        self.assertTrue(vista.botao_concluir.isEnabled())
        self.assertIn("Visita tecnica", vista.aviso.text())

    def test_bloqueio_nao_pode_ser_concluido(self) -> None:
        from dumtech.apps.agenda.models import BLOQUEIO

        almoco = self._marcar(titulo="Almoco", tipo=BLOQUEIO, cliente="",
                              inicio=self._quando(0, 12))
        vista = self.casca.agenda_view
        vista.refresh()
        vista._selecionar(almoco.id)
        self.assertFalse(vista.botao_concluir.isEnabled())

    def test_o_dialogo_avisa_o_conflito_e_pede_confirmacao(self) -> None:
        from dumtech.apps.agenda.models import Compromisso
        from dumtech.apps.agenda.ui.compromisso_dialog import CompromissoDialog

        self._marcar(inicio=self._quando(0, 9), duracao_min=60)

        novo = Compromisso(titulo="Em cima", inicio=self._quando(0, 9, 30))
        dialogo = CompromissoDialog(self.repo, novo, [], self.casca.agenda_view)
        self.assertIn("Já existe algo neste horário", dialogo._nota.text())

        # o primeiro clique so avisa: nada e gravado ainda
        self.assertIs(dialogo.salvar(), False)
        self.assertEqual(len(self.repo.listar()), 1)
        self.assertIn("Salvar de novo", dialogo._nota.text())

        # o segundo confirma
        dialogo.salvar()
        self.assertEqual(len(self.repo.listar()), 2)

    def test_horario_livre_salva_de_primeira(self) -> None:
        from dumtech.apps.agenda.models import Compromisso
        from dumtech.apps.agenda.ui.compromisso_dialog import CompromissoDialog

        novo = Compromisso(titulo="Sozinho", inicio=self._quando(2, 15))
        dialogo = CompromissoDialog(self.repo, novo, [], self.casca.agenda_view)
        self.assertIn("Horário livre", dialogo._nota.text())
        dialogo.salvar()
        self.assertEqual(len(self.repo.listar()), 1)

    def test_a_lista_avisa_o_que_passou_sem_fechar(self) -> None:
        self._marcar(titulo="Passou", inicio=self._quando(-1, 9))
        lista = self.casca.compromissos_view
        lista.filtro_periodo.setCurrentIndex(0)   # todos os periodos
        lista.refresh()
        self.assertIn("sem fechar", lista.tabela.item(0, 6).text())


class BackupNoHubTestCase(unittest.TestCase):
    """A copia de seguranca dentro do Hub: tela, aviso e restauracao."""

    def setUp(self) -> None:
        self.pasta = Path(tempfile.mkdtemp())
        self.settings, self.theme = _hub_de_teste(self.pasta)
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None
        self.vista = self.hub.backup_view

    def tearDown(self) -> None:
        _destruir(self.hub)

    def test_o_backup_e_uma_secao_de_configuracoes(self) -> None:
        from dumtech.hub.main_window import PAGINA_CONFIG

        self.hub._go(PAGINA_CONFIG)
        self.assertEqual(self.hub.stack.currentIndex(), PAGINA_CONFIG)
        self.assertTrue(self.hub.item_config.isChecked())

        titulos = [c.title for c in self.hub.build_commands()]
        self.assertIn("Configurações", titulos)
        self.assertIn("Backup", titulos)

        # a paleta leva direto para a secao, nao so para a tela - e o comando
        # e quem sabe o indice dela (secoes novas nao podem quebrar isto)
        comando = next(c for c in self.hub.build_commands() if c.title == "Backup")
        comando.run()
        self.assertIs(self.hub.config_view.stack.currentWidget(), self.vista)

    def test_avisa_quando_a_copia_fica_no_mesmo_computador(self) -> None:
        """Copia no mesmo HD nao salva de HD queimado - a tela tem que dizer."""
        self.vista.refresh()
        self.assertIn("mesmo computador", self.vista.alerta.text())
        self.assertIn("pendrive", self.vista.alerta.text())

    def test_escolher_pasta_de_fora_tira_o_aviso(self) -> None:
        externa = Path(tempfile.mkdtemp())
        self.settings.set("backup", "pasta", str(externa))
        self.vista.refresh()
        self.assertEqual(self.vista.alerta.text(), "")
        self.assertEqual(self.vista.pasta, externa)

    def test_fazer_backup_grava_e_lista(self) -> None:
        externa = Path(tempfile.mkdtemp())
        self.settings.set("backup", "pasta", str(externa))
        self.vista.refresh()
        self.assertEqual(self.vista.tabela.rowCount(), 0)

        self.vista._fazer_backup()
        self.assertEqual(self.vista.tabela.rowCount(), 1)
        self.assertIn("Cópia gravada", self.vista.aviso.text())
        self.assertEqual(len(list(externa.glob("*.zip"))), 1)

    def test_restaurar_devolve_os_dados_e_fecha_os_bancos(self) -> None:
        from dumtech.apps.estoque.models import Produto

        externa = Path(tempfile.mkdtemp())
        self.settings.set("backup", "pasta", str(externa))

        self.hub.open_app("estoque")
        casca = self.hub.launcher.get("estoque")
        casca.repository.db.execute("DELETE FROM produtos")
        casca.repository.criar(
            Produto(codigo="BKP-1", nome="Antes do backup", quantidade=5)
        )
        self.vista.refresh()
        self.vista._fazer_backup()

        # depois da copia, alguem estraga o cadastro
        produto = casca.repository.buscar_por_codigo("BKP-1")
        produto.nome = "Nome errado"
        casca.repository.atualizar(produto)
        self.assertEqual(
            casca.repository.buscar_por_codigo("BKP-1").nome, "Nome errado"
        )

        self.vista.refresh()
        self.vista.tabela.selectRow(0)
        self.assertTrue(self.vista.restaurar_agora(self.vista.selecionada()))

        # o aplicativo foi desmontado: nada podia estar com o .db aberto
        self.assertEqual(self.hub.launcher.open_apps, ())
        self.assertIn("Feche e abra", self.vista.aviso.text())

        # e o dado voltou (lendo o arquivo do zero, como faria o programa novo)
        from dumtech.apps.estoque.database import open_database
        from dumtech.apps.estoque.repository import EstoqueRepository
        from dumtech.core.paths import get_paths

        banco = open_database(get_paths().app_db("estoque"))
        self.addCleanup(banco.close)
        recuperado = EstoqueRepository(banco).buscar_por_codigo("BKP-1")
        self.assertIsNotNone(recuperado)
        self.assertEqual(recuperado.nome, "Antes do backup")

    def test_a_copia_automatica_roda_uma_vez_por_dia(self) -> None:
        from datetime import date

        externa = Path(tempfile.mkdtemp())
        self.settings.set("backup", "pasta", str(externa))
        self.settings.set("backup", "automatico", True)
        self.settings.set("backup", "ultimo", "")

        self.hub.backup_automatico()
        self.assertEqual(len(list(externa.glob("*.zip"))), 1)
        self.assertEqual(self.settings.get("backup", "ultimo"), date.today().isoformat())

        # de novo no mesmo dia: nao duplica
        self.hub.backup_automatico()
        self.assertEqual(len(list(externa.glob("*.zip"))), 1)

    def test_desligar_a_copia_automatica_e_respeitado(self) -> None:
        externa = Path(tempfile.mkdtemp())
        self.settings.set("backup", "pasta", str(externa))
        self.settings.set("backup", "automatico", False)
        self.settings.set("backup", "ultimo", "")

        self.hub.backup_automatico()
        self.assertEqual(list(externa.glob("*.zip")), [])

    def test_backup_quebrado_nao_derruba_a_abertura(self) -> None:
        """O cliente abriu o programa para trabalhar, nao para cuidar de backup."""
        self.settings.set("backup", "pasta", "Z:/pasta/que/nao/existe")
        self.settings.set("backup", "automatico", True)
        self.settings.set("backup", "ultimo", "")

        self.hub.backup_automatico()   # nao levanta
        self.assertEqual(self.settings.get("backup", "ultimo", ""), "")


class ErroInesperadoTestCase(unittest.TestCase):
    """O caminho completo: erro num clique de verdade vira log e caixa."""

    def setUp(self) -> None:
        import sys

        from dumtech.ui import erros

        self.erros = erros
        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None

        # a caixa e modal e travaria a suite: aqui so registramos que ela abriria
        self.abertas = []
        original = erros.ErroDialog
        erros.ErroDialog = lambda *args, **kw: self._falsa(args)
        self.addCleanup(setattr, erros, "ErroDialog", original)

        self.anterior = sys.excepthook
        self.addCleanup(lambda: setattr(sys, "excepthook", self.anterior))

    def _falsa(self, args):
        self.abertas.append(args)

        class Fingida:
            def exec(self_inner):
                return 1

        return Fingida()

    def tearDown(self) -> None:
        _destruir(self.hub)

    def test_erro_dentro_de_um_clique_e_registrado_e_mostrado(self) -> None:
        import logging

        from PySide6.QtWidgets import QPushButton

        self.erros.instalar("9.9.9")

        botao = QPushButton(self.hub)

        def estoura():
            raise RuntimeError("o botao explodiu")

        botao.clicked.connect(estoura)

        with self.assertLogs("dumtech.ui.erros", level=logging.ERROR) as capturado:
            botao.click()

        registro = "\n".join(capturado.output)
        self.assertIn("o botao explodiu", registro)
        self.assertIn("9.9.9", registro)
        # a caixa foi montada com o erro e o relatorio
        self.assertEqual(len(self.abertas), 1)
        erro, texto = self.abertas[0][0], self.abertas[0][1]
        self.assertIsInstance(erro, RuntimeError)
        self.assertIn("Traceback", texto)

    def test_o_programa_continua_de_pe_depois_do_erro(self) -> None:
        """Erro numa tela nao pode fazer o cliente perder o resto do trabalho."""
        import logging

        from PySide6.QtWidgets import QPushButton

        self.erros.instalar("9.9.9")
        botao = QPushButton(self.hub)
        botao.clicked.connect(lambda: 1 / 0)

        with self.assertLogs("dumtech.ui.erros", level=logging.ERROR):
            botao.click()

        # a janela responde normalmente logo depois
        self.assertTrue(self.hub.open_app("estoque"))
        self.assertEqual(self.hub.workspace.current_app, "estoque")


class CatalogoDaPlataformaTestCase(unittest.TestCase):
    """A ponte opcional Vendas <-> Estoque, no mesmo padrao da agenda de clientes."""

    def setUp(self) -> None:
        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None

    def tearDown(self) -> None:
        _destruir(self.hub)

    def test_vendas_recebe_o_catalogo_do_estoque(self) -> None:
        self.hub.open_app("vendas")
        casca = self.hub.launcher.get("vendas")
        self.assertIsNotNone(casca.repository.catalogo)
        self.assertTrue(casca.repository.tem_catalogo)

    def test_o_estoque_nao_recebe_o_proprio_catalogo(self) -> None:
        contexto = self.hub.launcher.build_context(
            self.hub.registry.get("estoque").manifest
        )
        self.assertIsNone(contexto.catalog)

    def test_sem_licenca_do_estoque_o_vendas_trabalha_com_texto_livre(self) -> None:
        licenca = self.hub.registry.license_service
        original = licenca.allows
        licenca.allows = lambda app_id: app_id != "estoque"
        self.addCleanup(setattr, licenca, "allows", original)

        self.hub.launcher.close_catalog()
        self.hub.open_app("vendas")
        casca = self.hub.launcher.get("vendas")
        self.assertIsNone(casca.repository.catalogo)
        self.assertFalse(casca.repository.tem_catalogo)

    def test_o_catalogo_e_um_so_para_todos_os_aplicativos(self) -> None:
        primeiro = self.hub.launcher.catalog("vendas")
        self.assertIs(self.hub.launcher.catalog("ordens"), primeiro)


class PainelDoInicioTestCase(unittest.TestCase):
    """O Inicio e o centro de comando: identidade, sinais vitais e atencao."""

    def setUp(self) -> None:
        self.settings, self.theme = _hub_de_teste()

    def tearDown(self) -> None:
        _destruir(self.hub)

    def _hub(self, modulos=None) -> HubWindow:
        """Um Hub com a licenca que o teste quiser."""
        from dumtech.core.licensing import LicenseService, LocalLicenseGateway
        from dumtech.core.registry import AppRegistry

        if modulos is None:
            self.hub = HubWindow(settings=self.settings, theme=self.theme)
        else:
            servico = LicenseService(
                file_path=Path(tempfile.mkdtemp()) / "license.json",
                gateway=LocalLicenseGateway(tuple(modulos)),
            )
            servico.activate("DUMT-TEST-0000-0001")
            self.hub = HubWindow(settings=self.settings, theme=self.theme,
                                 license_service=servico,
                                 registry=AppRegistry(servico))
        self.hub.launcher.notify = lambda *args: None
        return self.hub

    def _sinais(self, hub) -> list:
        from dumtech.ui.widgets.painel_inicio import SinalVital

        return hub.home_view.findChildren(SinalVital)

    def test_o_inicio_abre_com_o_nome_da_empresa(self) -> None:
        from dumtech.core.empresa import Empresa

        hub = self._hub()
        Empresa(nome="Casa do Parafuso", cidade="Palmas", uf="TO").salvar(self.settings)
        hub.home_view.refresh()
        self.assertEqual(hub.home_view.cabecalho.nome.text(), "Casa do Parafuso")
        self.assertIn("Palmas", hub.home_view.cabecalho.detalhe.text())

    def test_sem_empresa_o_cabecalho_convida_em_vez_de_ficar_vazio(self) -> None:
        hub = self._hub()
        self.assertEqual(hub.home_view.cabecalho.nome.text(), "Sua empresa")
        self.assertIn("Minha empresa", hub.home_view.cabecalho.detalhe.text())

    def test_a_vitrine_cresce_com_os_modulos(self) -> None:
        """Um modulo ja da um painel coerente; sete dao o retrato do negocio."""
        um = self._hub(["vendas"])
        # o modulo mais o sinal da propria plataforma
        self.assertEqual(len(self._sinais(um)), 2)
        _destruir(um)

        sete = self._hub()
        self.assertEqual(len(self._sinais(sete)), 8)

    def test_a_plataforma_tem_sinal_proprio(self) -> None:
        """E ele que impede a vitrine de parecer pela metade no comeco."""
        from dumtech.hub.views.home_view import SINAL_DA_PLATAFORMA

        hub = self._hub(["vendas"])
        donos = [s.indicador.app_id for s in self._sinais(hub)]
        self.assertIn(SINAL_DA_PLATAFORMA, donos)

    def test_sem_aviso_aparece_tudo_em_dia_e_nao_um_buraco(self) -> None:
        """Espaco vazio ali pareceria defeito; a frase e a resposta certa."""
        from dumtech.core.avisos import TIPOS
        from dumtech.ui.widgets.painel_inicio import LinhaDeAviso, TudoEmDia

        hub = self._hub()
        # os bancos sao compartilhados pela suite: em vez de limpar sete
        # modulos, desliga-se cada tipo de aviso - que e o mesmo caminho que o
        # cliente usa em Configuracoes
        for tipo in TIPOS:
            hub.config_avisos.definir(tipo.chave, ligado=False)
        hub.home_view.refresh()

        self.assertTrue(hub.home_view.findChildren(TudoEmDia))
        self.assertFalse(hub.home_view.findChildren(LinhaDeAviso))

    def test_o_aviso_vira_linha_e_leva_para_o_modulo(self) -> None:
        from dumtech.apps.estoque.models import Produto
        from dumtech.ui.widgets.painel_inicio import LinhaDeAviso, TudoEmDia

        hub = self._hub()
        hub.open_app("estoque")
        casca = hub.launcher.get("estoque")
        casca.repository.db.execute("DELETE FROM produtos")
        casca.repository.criar(
            Produto(codigo="MIN-1", nome="No minimo", quantidade=0, estoque_minimo=5)
        )
        hub.launcher.close_all()
        hub.home_view.refresh()

        linhas = hub.home_view.findChildren(LinhaDeAviso)
        self.assertFalse(hub.home_view.findChildren(TudoEmDia))
        # "algum" e nao "o primeiro": os bancos sao compartilhados pela suite e
        # a ordem e por urgencia - uma conta vencida vem antes do estoque baixo
        donos = {linha.aviso.app_id for linha in linhas}
        self.assertIn("estoque", donos)

        # o nome do teste promete que o aviso LEVA ao modulo; entao ele tem
        # que clicar de verdade, e nao so conferir que a linha existe
        do_estoque = next(x for x in linhas if x.aviso.app_id == "estoque")
        do_estoque.clicado.emit(do_estoque.aviso.app_id)
        self.assertEqual(hub.workspace.current_app, "estoque")

    def test_o_clique_no_sinal_da_plataforma_leva_ao_backup(self) -> None:
        from dumtech.hub.views.home_view import SINAL_DA_PLATAFORMA
        from dumtech.hub.main_window import PAGINA_CONFIG

        hub = self._hub(["vendas"])
        hub.home_view._abrir_sinal(SINAL_DA_PLATAFORMA)
        self.assertEqual(hub.stack.currentIndex(), PAGINA_CONFIG)
        self.assertIs(hub.config_view.stack.currentWidget(), hub.backup_view)


class BotaoDireitoTestCase(unittest.TestCase):
    """O menu do botao direito repete a barra de acoes, sem lista duplicada."""

    def setUp(self) -> None:
        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None
        self.hub.open_app("estoque")
        self.casca = self.hub.launcher.get("estoque")
        self.vista = self.casca.produtos_view

    def tearDown(self) -> None:
        _destruir(self.hub)

    def test_a_tabela_abre_menu_proprio(self) -> None:
        self.assertEqual(self.vista.tabela.contextMenuPolicy(),
                         Qt.ContextMenuPolicy.CustomContextMenu)

    def test_o_menu_sai_da_barra_de_acoes(self) -> None:
        rotulos = [b.text().strip() for b in self.vista.acoes_da_barra()]
        self.assertIn("Editar", rotulos)
        self.assertIn("Excluir", rotulos)
        self.assertIn("Entrada", rotulos)

    def test_todo_modulo_com_lista_tem_acoes_no_menu(self) -> None:
        from dumtech.ui.widgets.crud_view import CrudView

        for entrada in self.hub.registry.available():
            self.hub.open_app(entrada.app_id)
            casca = self.hub.launcher.get(entrada.app_id)
            listas = [v.widget for v in casca.views
                      if isinstance(v.widget, CrudView)]
            for vista in listas:
                with self.subTest(app=entrada.app_id, tela=type(vista).__name__):
                    self.assertTrue(vista.acoes_da_barra())


class ConfirmacoesTestCase(unittest.TestCase):
    """Excluir e fechar perguntam - ate a pessoa dizer para nao perguntar mais."""

    def setUp(self) -> None:
        from dumtech.core import confirmacoes

        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None
        self.confirmacoes = confirmacoes

    def tearDown(self) -> None:
        _destruir(self.hub)

    def test_por_padrao_o_programa_pergunta(self) -> None:
        self.assertTrue(self.confirmacoes.deve_perguntar(self.confirmacoes.EXCLUIR))
        self.assertTrue(
            self.confirmacoes.deve_perguntar(self.confirmacoes.FECHAR_MODULO)
        )

    def test_nunca_mais_cala_a_pergunta_e_fica_gravado(self) -> None:
        from dumtech.core.config import Settings

        self.confirmacoes.nunca_mais(self.confirmacoes.EXCLUIR)
        self.assertFalse(self.confirmacoes.deve_perguntar(self.confirmacoes.EXCLUIR))
        # a outra pergunta continua de pe: calar uma nao cala todas
        self.assertTrue(
            self.confirmacoes.deve_perguntar(self.confirmacoes.FECHAR_MODULO)
        )

        # gravado no disco, nao so na memoria
        outro = Settings(self.settings.file_path)
        self.assertIs(outro.get("confirmacoes", "excluir"), False)

    def test_calada_a_pergunta_a_acao_segue_sem_abrir_janela(self) -> None:
        """`confirmar` devolve True sem dialogo - e o que nao trava a suite."""
        from dumtech.ui.widgets.confirmar import confirmar

        self.confirmacoes.nunca_mais(self.confirmacoes.EXCLUIR)
        self.assertTrue(
            confirmar(self.hub, "Excluir", "Excluir?", chave=self.confirmacoes.EXCLUIR)
        )

    def test_voltar_a_perguntar_desfaz(self) -> None:
        self.confirmacoes.nunca_mais(self.confirmacoes.EXCLUIR)
        self.confirmacoes.voltar_a_perguntar()
        self.assertTrue(self.confirmacoes.deve_perguntar(self.confirmacoes.EXCLUIR))

    def test_fechar_sem_perguntar_continua_possivel(self) -> None:
        """A restauracao de backup fecha tudo: ali nao cabe perguntar."""
        self.hub.open_app("estoque")
        self.hub.close_app("estoque", perguntar=False)
        self.assertEqual(self.hub.launcher.open_apps, ())


class TrocaDeTemaTestCase(unittest.TestCase):
    """Trocar de tema com a tela aberta nao pode deixar cor do tema anterior."""

    def setUp(self) -> None:
        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None

    def tearDown(self) -> None:
        self.theme.set_mode(MODO_ESCURO)
        _destruir(self.hub)

    def _tabela_com_tons(self):
        from dumtech.ui.widgets.table import DataTable

        tabela = DataTable(["Item", "Situacao"])
        tabela.setParent(self.hub)
        tabela.fill([
            [tabela.cell("Sem tom"), tabela.cell("Vencido", tone="danger")],
            [tabela.cell("Outro"), tabela.cell("Em dia", tone="success")],
        ])
        return tabela

    def _cor(self, tabela, linha: int) -> str:
        return tabela.item(linha, 1).foreground().color().name().lower()

    def test_a_celula_colorida_acompanha_a_troca(self) -> None:
        """O bug: a lista ficava com o verde do modo noturno sobre fundo branco."""
        from dumtech.ui.theme import DARK, LIGHT

        tabela = self._tabela_com_tons()
        self.theme.set_mode(MODO_ESCURO)
        self.assertEqual(self._cor(tabela, 0), DARK.danger.lower())

        self.theme.set_mode(MODO_CLARO)
        self.assertEqual(self._cor(tabela, 0), LIGHT.danger.lower())
        self.assertEqual(self._cor(tabela, 1), LIGHT.success.lower())

        self.theme.set_mode(MODO_ESCURO)
        self.assertEqual(self._cor(tabela, 0), DARK.danger.lower())

    def test_celula_sem_tom_nao_ganha_cor_fixa(self) -> None:
        """Quem nao tem tom fica com a cor da folha de estilo, nao com preto."""
        from dumtech.ui.theme import LIGHT

        tabela = self._tabela_com_tons()
        self.theme.set_mode(MODO_CLARO)
        self.assertIsNone(tabela.item(0, 0).data(Qt.ItemDataRole.ForegroundRole))
        self.assertEqual(self._cor(tabela, 0), LIGHT.danger.lower())

    def test_o_calendario_nao_herda_o_estilo_das_listas(self) -> None:
        """O bug: `QTableView::item` deformava a grade de dias do calendario.

        O calendario e uma QTableView por dentro; com o recuo e a borda das
        listas do programa, as colunas nao fechavam a semana.
        """
        from dumtech.ui.theme import DARK, LIGHT, stylesheet_for

        for paleta in (LIGHT, DARK):
            with self.subTest(paleta.name):
                folha = stylesheet_for(paleta)
                self.assertIn("QCalendarWidget QAbstractItemView::item", folha)
                self.assertIn("qt_calendar_navigationbar", folha)
                # as setas do calendario sao as do programa, nao as do Qt
                self.assertIn("qt_calendar_prevmonth", folha)
                self.assertIn("qt_calendar_nextmonth", folha)

    def test_a_grade_de_dias_fecha_a_semana(self) -> None:
        """Sete colunas e o cabecalho dos dias - era isso que quebrava."""
        from PySide6.QtWidgets import QCalendarWidget

        from dumtech.apps.agenda.ui.compromisso_dialog import CompromissoDialog

        self.hub.open_app("agenda")
        casca = self.hub.launcher.get("agenda")
        dialogo = CompromissoDialog(casca.repository, None, [], self.hub)
        calendario = dialogo.inicio.calendarWidget()

        self.assertIsInstance(calendario, QCalendarWidget)
        vista = calendario.findChild(QWidget, "qt_calendar_calendarview")
        self.assertIsNotNone(vista)
        self.assertEqual(vista.model().columnCount(), 7)
        dialogo.close()

    def test_aplicativo_com_tema_proprio_entra_no_tema_do_hub(self) -> None:
        """O bug: a Agenda abria escura dentro de um Hub claro.

        A casca nasce sem pai, resolve o tema gravado do proprio aplicativo e
        pinta tudo; so depois e embutida. Quem se pinta a mao - a grade da
        Agenda - ficava com a paleta velha ate a proxima troca de tema.
        """
        self.settings.set("app:agenda", "theme", MODO_ESCURO)
        self.theme.set_mode(MODO_CLARO)

        self.hub.open_app("agenda")
        casca = self.hub.launcher.get("agenda")

        self.assertTrue(casca.embedded)
        self.assertEqual(casca.theme_mode, MODO_ESCURO)   # a preferencia fica
        # mas quem manda e o Hub, inclusive nos widgets pintados a mao
        self.assertEqual(casca.resolved_palette().name, MODO_CLARO)
        self.assertEqual(casca.agenda_view.grade._palette.name, MODO_CLARO)

    def test_a_bancada_tambem_nasce_no_tema_do_hub(self) -> None:
        self.settings.set("app:ordens", "theme", MODO_ESCURO)
        self.theme.set_mode(MODO_CLARO)

        self.hub.open_app("ordens")
        casca = self.hub.launcher.get("ordens")
        faixa = next(iter(casca.bancada_view.faixas.values()))
        self.assertEqual(palette_for(faixa).name, MODO_CLARO)

    def test_o_grafico_tambem_troca(self) -> None:
        from dumtech.ui.graficos import GraficoRosca
        from dumtech.ui.theme import DARK, LIGHT

        grafico = GraficoRosca(self.hub)
        self.theme.set_mode(MODO_CLARO)
        self.assertEqual(grafico._palette.accent, LIGHT.accent)
        self.theme.set_mode(MODO_ESCURO)
        self.assertEqual(grafico._palette.accent, DARK.accent)


class TemaAvulsoTestCase(unittest.TestCase):
    """Fora do Hub, o aplicativo continua podendo fixar o proprio tema."""

    def setUp(self) -> None:
        self.settings, self.theme = _hub_de_teste()
        self.hub = HubWindow(settings=self.settings, theme=self.theme)
        self.hub.launcher.notify = lambda *args: None

    def tearDown(self) -> None:
        _destruir(self.hub)

    def _casca_avulsa(self, app_id: str):
        """A casca sai do launcher sem pai: e uma janela por si so."""
        casca = self.hub.launcher.open(app_id)
        self.assertFalse(casca.embedded)
        return casca

    def test_segue_o_hub_por_padrao(self) -> None:
        casca = self._casca_avulsa("estoque")
        self.assertEqual(casca.theme_mode, MODO_AUTO)
        self.assertEqual(casca.resolved_palette().name, MODO_ESCURO)
        self.theme.set_mode(MODO_CLARO)
        self.assertEqual(casca.resolved_palette().name, MODO_CLARO)

    def test_tema_fixado_e_independente_e_fica_gravado(self) -> None:
        casca = self._casca_avulsa("estoque")
        casca._apply_theme_mode(MODO_CLARO)

        self.theme.set_mode(MODO_ESCURO)
        self.assertEqual(casca.resolved_palette().name, MODO_CLARO)
        self.assertEqual(self.settings.get("app:estoque", "theme"), MODO_CLARO)

        outra = self._casca_avulsa("clientes")
        self.assertEqual(outra.resolved_palette().name, MODO_ESCURO)

    def test_preferencia_e_lida_ao_abrir_de_novo(self) -> None:
        self.settings.set("app:vendas", "theme", MODO_CLARO)
        self.settings.save()
        casca = self._casca_avulsa("vendas")
        self.assertEqual(casca.theme_mode, MODO_CLARO)
        self.assertEqual(casca.resolved_palette().name, MODO_CLARO)


if __name__ == "__main__":
    unittest.main()

