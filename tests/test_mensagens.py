"""As mensagens de WhatsApp.

O que precisa ficar de pe: o texto padrao serve sem ninguem configurar nada, o
que o cliente escreve substitui o padrao, um campo errado nao derruba nada, e o
numero vira um link que o WhatsApp aceita.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

from dumtech.core import mensagens
from dumtech.core.config import Settings
from dumtech.core.empresa import Empresa
from dumtech.core.mensagens import MODELOS, Mensageiro, MensagemError


class ModelosTestCase(unittest.TestCase):
    def test_todo_modelo_nasce_escrito_e_coerente(self) -> None:
        """Instalar e usar: nenhuma mensagem comeca vazia."""
        for modelo in MODELOS:
            with self.subTest(modelo.chave):
                self.assertTrue(modelo.padrao.strip())
                self.assertTrue(modelo.quando.strip())
                # todo campo usado no padrao e um campo declarado
                self.assertEqual(mensagens.desconhecidos(modelo.padrao, modelo), [])
                # e todo campo declarado tem exemplo, senao a previa mente
                for campo in modelo.campos:
                    self.assertIn(campo, modelo.exemplo)

    def test_modelo_inexistente_e_recusado(self) -> None:
        with self.assertRaises(MensagemError):
            mensagens.obter("promocao")


class PreencherTestCase(unittest.TestCase):
    def test_troca_os_campos(self) -> None:
        texto = mensagens.preencher("Ola, {cliente}! Total {total}.",
                                    {"cliente": "Ana", "total": "R$ 10,00"})
        self.assertEqual(texto, "Ola, Ana! Total R$ 10,00.")

    def test_campo_desconhecido_sai_vazio_em_vez_de_derrubar(self) -> None:
        """Erro de digitacao no modelo nao pode explodir na frente do cliente."""
        self.assertEqual(mensagens.preencher("Ola, {clente}!", {"cliente": "Ana"}),
                         "Ola,!")

    def test_a_tela_sabe_apontar_o_campo_errado(self) -> None:
        self.assertEqual(
            mensagens.desconhecidos("Oi {clente}, {total}", mensagens.VENDA),
            ["clente"],
        )

    def test_campo_vazio_nao_deixa_buraco_no_texto(self) -> None:
        texto = mensagens.preencher(
            "Seu {equipamento} esta pronto.\n\n{garantia}\n\nAte mais.",
            {"equipamento": "notebook", "garantia": ""},
        )
        self.assertEqual(texto, "Seu notebook esta pronto.\n\nAte mais.")


class GuardadasTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(Path(tempfile.mkdtemp()) / "hub.json")

    def test_sem_nada_guardado_vem_o_padrao(self) -> None:
        self.assertEqual(mensagens.carregar(self.settings, "venda"),
                         mensagens.VENDA.padrao)
        self.assertEqual(mensagens.carregar(None, "venda"), mensagens.VENDA.padrao)

    def test_o_texto_do_cliente_substitui_o_padrao(self) -> None:
        mensagens.salvar(self.settings, "venda", "Valeu, {cliente}!")
        self.assertEqual(mensagens.carregar(self.settings, "venda"),
                         "Valeu, {cliente}!")

    def test_apagar_tudo_volta_ao_padrao_em_vez_de_virar_silencio(self) -> None:
        mensagens.salvar(self.settings, "venda", "Valeu!")
        self.assertEqual(mensagens.salvar(self.settings, "venda", "   "),
                         mensagens.VENDA.padrao)

    def test_restaurar_devolve_o_texto_original(self) -> None:
        mensagens.salvar(self.settings, "proposta", "Oi")
        mensagens.restaurar(self.settings, "proposta")
        self.assertEqual(mensagens.carregar(self.settings, "proposta"),
                         mensagens.PROPOSTA.padrao)


class NumeroTestCase(unittest.TestCase):
    def test_aceita_o_que_o_brasileiro_digita(self) -> None:
        for digitado in ("(63) 98877-4411", "63988774411", "63 98877 4411"):
            with self.subTest(digitado):
                self.assertEqual(mensagens.numero_internacional(digitado),
                                 "5563988774411")

    def test_numero_fixo_tambem_serve(self) -> None:
        self.assertEqual(mensagens.numero_internacional("6332258899"), "556332258899")

    def test_numero_ja_com_o_pais_nao_ganha_outro(self) -> None:
        self.assertEqual(mensagens.numero_internacional("5563988774411"),
                         "5563988774411")

    def test_numero_incompleto_nao_vira_link(self) -> None:
        for ruim in ("", "988774411", "12", "abc"):
            with self.subTest(ruim):
                self.assertEqual(mensagens.numero_internacional(ruim), "")
        with self.assertRaises(MensagemError):
            mensagens.link("988774411", "oi")

    def test_o_link_leva_o_texto_junto(self) -> None:
        endereco = mensagens.link("(63) 98877-4411", "Ola, Ana! Tudo bem?")
        self.assertTrue(endereco.startswith("https://wa.me/5563988774411?text="))
        self.assertIn("Ola, Ana! Tudo bem?", unquote(endereco))


class MensageiroTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(Path(tempfile.mkdtemp()) / "hub.json")
        self.empresa = Empresa(nome="Casa do Parafuso")
        self.mensageiro = Mensageiro(self.settings, self.empresa)

    def test_o_nome_da_loja_entra_sozinho(self) -> None:
        """Nenhum aplicativo precisa saber que a empresa existe."""
        texto = self.mensageiro.texto("venda", {"cliente": "Ana", "total": "R$ 10,00"})
        self.assertIn("Casa do Parafuso", texto)
        self.assertIn("Ana", texto)

    def test_sem_empresa_preenchida_a_mensagem_continua_de_pe(self) -> None:
        texto = Mensageiro().texto("venda", {"cliente": "Ana"})
        self.assertIn("Ana", texto)
        self.assertNotIn("{", texto)

    def test_a_previa_usa_dados_de_exemplo(self) -> None:
        """Ninguem precisa 'testar para ver' como a mensagem fica."""
        previa = self.mensageiro.previa("aniversario")
        self.assertIn("Carlos Menezes", previa)
        self.assertIn("Casa do Parafuso", previa)

    def test_a_previa_acompanha_o_que_esta_sendo_digitado(self) -> None:
        self.assertEqual(self.mensageiro.previa("venda", "Valeu, {cliente}!"),
                         "Valeu, Maria Souza!")

    def test_usa_o_texto_que_o_cliente_salvou(self) -> None:
        mensagens.salvar(self.settings, "venda", "Valeu, {cliente}! Volte sempre.")
        self.assertEqual(self.mensageiro.texto("venda", {"cliente": "Ana"}),
                         "Valeu, Ana! Volte sempre.")

    def test_monta_o_link_direto(self) -> None:
        endereco = self.mensageiro.link("venda", "63988774411", {"cliente": "Ana"})
        self.assertIn("wa.me/5563988774411", endereco)


class AgendaTestCase(unittest.TestCase):
    """A busca do numero na agenda de clientes da plataforma."""

    def setUp(self) -> None:
        from dumtech.ui.widgets.mensagem import telefone_do_cliente

        self.buscar = telefone_do_cliente

    def test_sem_agenda_o_campo_comeca_vazio(self) -> None:
        """Quem nao tem o DumTech Clientes digita o numero na janela."""
        self.assertEqual(self.buscar(None, "Ana"), "")

    def test_prefere_o_whatsapp_ao_telefone(self) -> None:
        from dumtech.core.contacts import Contato

        class Agenda:
            @staticmethod
            def por_nome(nome):
                return Contato(nome=nome, telefone="6332258899",
                               whatsapp="63988774411")

        self.assertEqual(self.buscar(Agenda(), "Ana"), "63988774411")

    def test_agenda_com_problema_nao_trava_o_botao(self) -> None:
        class Quebrada:
            @staticmethod
            def por_nome(nome):
                raise RuntimeError("banco fechado")

        self.assertEqual(self.buscar(Quebrada(), "Ana"), "")


if __name__ == "__main__":
    unittest.main()
