"""A ficha da ordem de servico: simples de abrir, completa quando precisa.

A ficha serve para qualquer ramo. Quem so quer abrir uma ordem responde
quatro coisas; quem recebe aparelho na bancada abre os blocos e registra
acessorio, estado e senha - sem que um atrapalhe o outro.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from dumtech.apps.ordens.database import open_database
from dumtech.apps.ordens.models import Ordem
from dumtech.apps.ordens.repository import OrdensRepository
from dumtech.apps.ordens.ui.ordem_dialog import AcessoriosPicker, OrdemDialog

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class FichaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = open_database(Path(tempfile.mkdtemp()) / "ordens.db")
        self.repo = OrdensRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _ficha(self, ordem: Ordem | None = None) -> OrdemDialog:
        dialogo = OrdemDialog(self.repo, ordem, ["Maria Souza"])
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def _salvar(self, ordem: Ordem) -> Ordem:
        ordem.numero = ordem.numero or self.repo.proximo_numero()
        return self.repo.salvar(ordem)

    # ------------------------------------------------------- abrir e preencher
    def test_a_ficha_nova_abre_com_o_essencial_a_vista(self) -> None:
        """Os blocos de detalhe nascem fechados: ninguem rola o que nao usa."""
        ficha = self._ficha()
        self.assertFalse(ficha.bloco_entrada.aberta)
        self.assertFalse(ficha.bloco_execucao.aberta)
        self.assertFalse(ficha.bloco_controle.aberta)

    def test_abrir_ordem_so_com_cliente_e_pedido(self) -> None:
        """O caminho curto: quem pediu, o que quer, quanto custa."""
        ficha = self._ficha()
        ficha.cliente.setText("Maria Souza")
        ficha.defeito.setPlainText("Instalar o ar-condicionado da sala")
        ficha.valor.setValue(450.0)
        ficha.salvar()

        salva = self.repo.listar()[0]
        self.assertEqual(salva.cliente, "Maria Souza")
        self.assertEqual(salva.defeito, "Instalar o ar-condicionado da sala")
        self.assertEqual(salva.valor, 450.0)
        # o que nao foi preenchido continua vazio - nada e inventado
        self.assertEqual(salva.equipamento, "")
        self.assertEqual(salva.senha, "")

    def test_o_numero_sai_pronto_mesmo_escondido(self) -> None:
        """O numero mora no bloco fechado, mas nasce preenchido."""
        ficha = self._ficha()
        self.assertTrue(ficha.numero.text().strip())
        ficha.cliente.setText("Joao")
        ficha.defeito.setPlainText("Trocar a fechadura")
        ficha.salvar()
        self.assertEqual(self.repo.listar()[0].numero, ficha.numero.text())

    # ------------------------------------------------- o que estava escondido
    def test_ordem_com_dados_de_bancada_abre_os_blocos(self) -> None:
        """Abrir ordem antiga nao pode esconder o que alguem escreveu nela."""
        ordem = self._salvar(Ordem(
            cliente="Maria", equipamento="Notebook Dell",
            acessorios="Carregador", condicao="Risco na tampa", senha="1234",
            tecnico="Ana", diagnostico="Troca da fonte",
        ))
        ficha = self._ficha(self.repo.obter(ordem.id))
        self.assertTrue(ficha.bloco_entrada.aberta)
        self.assertTrue(ficha.bloco_execucao.aberta)
        self.assertEqual(ficha.bloco_entrada.marca.text(), "●")
        self.assertEqual(ficha.senha.text(), "1234")
        self.assertEqual(ficha.condicao.text(), "Risco na tampa")

    def test_os_campos_escondidos_continuam_gravando(self) -> None:
        """Mudar o desenho da tela nao pode perder coluna do banco."""
        ficha = self._ficha()
        ficha.cliente.setText("Maria")
        ficha.defeito.setPlainText("Revisao dos freios")
        ficha.equipamento.setText("Gol 2015")
        ficha.condicao.setText("Para-choque amassado")
        ficha.senha.setText("chave reserva")
        ficha.tecnico.setText("Ana")
        ficha.diagnostico.setPlainText("Troca de pastilhas")
        ficha.observacoes.setPlainText("Cliente pediu desconto")
        ficha.garantia.setValue(30)
        ficha.acessorios.outros.setText("Estepe, documento")
        ficha.salvar()

        salva = self.repo.listar()[0]
        self.assertEqual(salva.equipamento, "Gol 2015")
        self.assertEqual(salva.condicao, "Para-choque amassado")
        self.assertEqual(salva.senha, "chave reserva")
        self.assertEqual(salva.tecnico, "Ana")
        self.assertEqual(salva.diagnostico, "Troca de pastilhas")
        self.assertEqual(salva.observacoes, "Cliente pediu desconto")
        self.assertEqual(salva.garantia_dias, 30)
        self.assertIn("Estepe", salva.acessorios)

    # ------------------------------------------------------------- sugestoes
    def test_o_item_sugere_o_que_a_loja_ja_atendeu(self) -> None:
        self._salvar(Ordem(cliente="Joao", equipamento="Notebook Dell G15"))
        ficha = self._ficha()
        self.assertIn("Notebook Dell G15", self.repo.equipamentos())
        self.assertIsNotNone(ficha.equipamento.completer())

    def test_a_lista_de_acessorios_aprende_com_a_loja(self) -> None:
        """Oficina mecanica nao recebe pelicula: recebe estepe e documento."""
        for _ in range(3):
            self._salvar(Ordem(cliente="Joao", defeito="Revisao",
                               acessorios="Estepe\nDocumento"))
        usados = self.repo.acessorios_usados()
        self.assertIn("Estepe", usados)
        self.assertIn("Documento", usados)
        picker = AcessoriosPicker("", usados)
        self.addCleanup(picker.deleteLater)
        self.assertEqual([c.text() for c in picker.caixas], usados)

    def test_sem_historico_vale_a_lista_de_fabrica(self) -> None:
        picker = AcessoriosPicker("", self.repo.acessorios_usados())
        self.addCleanup(picker.deleteLater)
        self.assertTrue(picker.caixas)
        self.assertIn("Carregador", [c.text() for c in picker.caixas])

    def test_o_que_foi_digitado_fora_da_lista_nao_se_perde(self) -> None:
        picker = AcessoriosPicker("Carregador\nSuporte de parede")
        self.addCleanup(picker.deleteLater)
        self.assertEqual(picker.outros.text(), "Suporte de parede")
        self.assertIn("Carregador", picker.texto())
        self.assertIn("Suporte de parede", picker.texto())

    # ------------------------------------------------------------------ total
    def test_o_total_continua_saindo_dos_itens(self) -> None:
        from dumtech.apps.ordens.models import PECA, ItemOS

        ficha = self._ficha()
        ficha.itens.set_items([ItemOS(tipo=PECA, descricao="Fonte",
                                      quantidade=1, valor_unitario=200.0)])
        ficha.itens.changed.emit()
        ficha.desconto.setValue(20.0)
        self.assertEqual(ficha.valor.value(), 180.0)
        self.assertFalse(ficha.valor.isEnabled())


if __name__ == "__main__":
    unittest.main()
