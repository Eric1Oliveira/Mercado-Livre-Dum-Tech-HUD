"""Parceiros: quem indica clientes, e quanto cada um ja indicou."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dumtech.core.contacts import (
    MIGRATIONS,
    Contato,
    ContactsStore,
    ContatoError,
    Parceiro,
)
from dumtech.core.database import Database


def _arquivo() -> Path:
    return Path(tempfile.mkdtemp()) / "plataforma.db"


class ParceirosRegrasTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.loja = ContactsStore(_arquivo())
        self.addCleanup(self.loja.close)

    def test_banco_antigo_ganha_parceiros_sem_perder_ninguem(self) -> None:
        """Quem atualiza mantem os clientes, todos sem parceiro."""
        arquivo = _arquivo()
        antigo = Database(arquivo, MIGRATIONS[:2])
        antigo.execute("INSERT INTO contatos (nome, criado_em, atualizado_em) "
                       "VALUES ('Cliente antigo', '2026-01-02', '2026-01-02')")
        antigo.close()

        loja = ContactsStore(arquivo)
        self.addCleanup(loja.close)
        clientes = loja.listar()
        self.assertEqual([c.nome for c in clientes], ["Cliente antigo"])
        self.assertIsNone(clientes[0].parceiro_id)
        self.assertEqual(loja.parceiros(), [])

    def test_nome_obrigatorio_e_sem_repetir(self) -> None:
        with self.assertRaises(ContatoError):
            self.loja.criar_parceiro(Parceiro(nome="  "))
        self.loja.criar_parceiro(Parceiro(nome="Ana Arquitetura"))
        with self.assertRaises(ContatoError):
            self.loja.criar_parceiro(Parceiro(nome="ana arquitetura"))

    def test_editar_o_proprio_nome_nao_conta_como_repetido(self) -> None:
        parceiro = self.loja.criar_parceiro(Parceiro(nome="Contador", telefone="(11) 3333-4444"))
        parceiro.email = "contato@exemplo.com"
        self.loja.atualizar_parceiro(parceiro)
        salvo = self.loja.obter_parceiro(parceiro.id)
        self.assertEqual(salvo.email, "contato@exemplo.com")
        self.assertEqual(salvo.telefone, "1133334444")   # guardado limpo

    def test_conta_quanto_cada_parceiro_indicou(self) -> None:
        ana = self.loja.criar_parceiro(Parceiro(nome="Ana"))
        bia = self.loja.criar_parceiro(Parceiro(nome="Bia"))
        self.loja.criar_parceiro(Parceiro(nome="Caio"))
        self.loja.criar(Contato(nome="Um", parceiro_id=bia.id))
        self.loja.criar(Contato(nome="Dois", parceiro_id=bia.id, ativo=False))
        self.loja.criar(Contato(nome="Tres", parceiro_id=ana.id))
        self.loja.criar(Contato(nome="Sozinho"))

        indicacoes = self.loja.indicacoes()
        # quem mais indicou primeiro; quem nao indicou ninguem aparece com zero
        self.assertEqual([i.parceiro.nome for i in indicacoes], ["Bia", "Ana", "Caio"])
        bia_numeros = indicacoes[0]
        self.assertEqual((bia_numeros.clientes, bia_numeros.ativos, bia_numeros.no_mes),
                         (2, 1, 2))
        self.assertTrue(bia_numeros.ultimo)
        self.assertEqual(indicacoes[2].clientes, 0)
        self.assertEqual(indicacoes[2].ultimo, "")

    def test_parceiro_inativo_sai_da_lista_mas_continua_contado(self) -> None:
        parceiro = self.loja.criar_parceiro(Parceiro(nome="Ana"))
        self.loja.criar(Contato(nome="Um", parceiro_id=parceiro.id))
        parceiro.ativo = False
        self.loja.atualizar_parceiro(parceiro)

        self.assertEqual(self.loja.parceiros(), [])
        self.assertEqual(self.loja.indicacoes(), [])
        todas = self.loja.indicacoes(incluir_inativos=True)
        self.assertEqual(todas[0].clientes, 1)

    def test_excluir_parceiro_mantem_os_clientes(self) -> None:
        parceiro = self.loja.criar_parceiro(Parceiro(nome="Ana"))
        cliente = self.loja.criar(Contato(nome="Um", parceiro_id=parceiro.id))
        self.loja.excluir_parceiro(parceiro.id)

        self.assertIsNone(self.loja.obter_parceiro(parceiro.id))
        self.assertIsNone(self.loja.obter(cliente.id).parceiro_id)

    def test_trocar_e_tirar_o_parceiro_do_cliente(self) -> None:
        ana = self.loja.criar_parceiro(Parceiro(nome="Ana"))
        cliente = self.loja.criar(Contato(nome="Um", parceiro_id=ana.id))
        cliente.parceiro_id = None
        self.loja.atualizar(cliente)
        self.assertIsNone(self.loja.obter(cliente.id).parceiro_id)


class ParceirosTelaTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.loja = ContactsStore(_arquivo())
        self.addCleanup(self.loja.close)

    def _widget(self, widget):
        self.addCleanup(widget.deleteLater)
        return widget

    def test_cadastro_do_cliente_grava_quem_indicou(self) -> None:
        from dumtech.apps.clientes.ui.cliente_dialog import ClienteDialog

        ana = self.loja.criar_parceiro(Parceiro(nome="Ana"))
        dialogo = self._widget(ClienteDialog(self.loja))
        dialogo.nome.setText("Cliente novo")
        dialogo.parceiro.setCurrentIndex(dialogo.parceiro.findData(ana.id))
        dialogo.salvar()
        self.assertEqual(self.loja.por_nome("Cliente novo").parceiro_id, ana.id)

        # reabrindo, o parceiro ja vem escolhido; "Ninguem" tira a indicacao
        contato = self.loja.por_nome("Cliente novo")
        dialogo = self._widget(ClienteDialog(self.loja, contato))
        self.assertEqual(dialogo.parceiro.currentData(), ana.id)
        dialogo.parceiro.setCurrentIndex(0)
        dialogo.salvar()
        self.assertIsNone(self.loja.por_nome("Cliente novo").parceiro_id)

    def test_parceiro_inativo_some_do_cadastro_menos_de_quem_ja_tem(self) -> None:
        from dumtech.apps.clientes.ui.cliente_dialog import ClienteDialog

        ana = self.loja.criar_parceiro(Parceiro(nome="Ana"))
        cliente = self.loja.criar(Contato(nome="Um", parceiro_id=ana.id))
        ana.ativo = False
        self.loja.atualizar_parceiro(ana)

        novo = self._widget(ClienteDialog(self.loja))
        self.assertEqual(novo.parceiro.findData(ana.id), -1)
        antigo = self._widget(ClienteDialog(self.loja, self.loja.obter(cliente.id)))
        self.assertEqual(antigo.parceiro.currentData(), ana.id)

    def test_tela_mostra_quanto_cada_um_indicou(self) -> None:
        from dumtech.apps.clientes.ui.parceiros_view import ParceirosView

        ana = self.loja.criar_parceiro(Parceiro(nome="Ana"))
        bia = self.loja.criar_parceiro(Parceiro(nome="Bia"))
        for nome, parceiro in (("Um", ana), ("Dois", ana), ("Tres", ana), ("Quatro", bia)):
            self.loja.criar(Contato(nome=nome, parceiro_id=parceiro.id))

        tela = self._widget(ParceirosView(self.loja))
        tela.refresh()
        self.assertEqual(tela.tabela.rowCount(), 2)
        self.assertEqual(tela.tabela.item(0, 0).text(), "Ana")
        self.assertEqual(tela.tabela.item(0, 2).text(), "3")
        fatias = tela.grafico.fatias
        self.assertEqual([f.rotulo for f in fatias], ["Ana", "Bia"])
        self.assertIn("75%", fatias[0].texto)
        self.assertIn("4 clientes indicados", tela.painel_indicacoes.nota.text())

    def test_aba_parceiros_no_clientes(self) -> None:
        from dumtech.core.novidades import TELAS_NOVAS

        self.assertIn("clientes/Parceiros", TELAS_NOVAS)


if __name__ == "__main__":
    unittest.main()
