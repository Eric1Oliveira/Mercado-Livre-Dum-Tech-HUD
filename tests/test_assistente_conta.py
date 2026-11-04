"""O assistente: migrar nao pode travar a loja, e o novo cliente sai com tudo pronto."""

from __future__ import annotations

import unittest
from unittest import mock

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from dumtech.core import acesso as nucleo
from dumtech.core.supabase import SemConexao
from dumtech.hub.views import assistente_conta_view
from dumtech.hub.views.assistente_conta_view import (
    PAGINA_CONTA, PAGINA_CONVITE, PAGINA_EMAIL, PAGINA_EQUIPE, PAGINA_PRONTO, AssistenteContaView,
)

from .assinante import pacote_acesso, pacote_lembranca
from .test_acesso import ADM, Base, conta, maria
from .test_login_tela import sincrono

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


class Assistente(Base):
    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(assistente_conta_view.tasks, "executar", sincrono)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.licenca()
        self.loja = {"nome": "Eric Oliveira", "email": "eric@teste.com", "computadores": 3}
        self.tela = AssistenteContaView(self.servico, lambda: self.loja)
        self.addCleanup(self.tela.deleteLater)
        self.concluidos: list = []
        self.adiados: list = []
        self.tela.concluido.connect(lambda: self.concluidos.append(True))
        self.tela.adiado.connect(lambda: self.adiados.append(True))

    def preencher(self) -> None:
        self.tela.campo_senha.setText("cavalo-azul")
        self.tela.campo_repetir.setText("cavalo-azul")

    def criar(self) -> None:
        self.tela.abrir(direto=True)
        self.preencher()
        self.servidor.respostas["criar-primeiro"] = {
            "ok": True, "sessao": "segredo", "usuario": conta(nome="Eric Oliveira"),
            "acesso_assinado": pacote_acesso([conta(nome="Eric Oliveira")]), "lembranca": pacote_lembranca(ADM, 1)}
        self.servidor.respostas["pedir-confirmacao"] = {"ok": True, "email": "e**c@teste.com"}
        self.tela.criar_conta()

    def test_convite_tem_agora_nao(self) -> None:
        self.tela.abrir()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_CONVITE)
        self.assertFalse(self.tela.botao_agora_nao.isHidden())
        self.tela.botao_agora_nao.click()
        self.assertEqual(self.adiados, [True])

    def test_obrigatorio_tira_o_agora_nao(self) -> None:
        self.tela.abrir(obrigatorio=True)
        self.assertTrue(self.tela.botao_agora_nao.isHidden())
        self.assertIn("passou a usar contas", self.tela.nota_convite.text())
        self.tela.adiar()
        self.assertEqual(self.adiados, [], "obrigatorio nao adia")

    def test_ja_vem_preenchido_para_nao_digitar_duas_vezes(self) -> None:
        self.tela.abrir()
        self.tela.botao_comecar.click()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_CONTA)
        self.assertEqual(self.tela.campo_email.text(), "eric@teste.com")
        self.assertEqual(self.tela.campo_nome.text(), "Eric Oliveira")
        self.assertEqual(self.tela.campo_login.text(), "eric.oliveira")

    def test_login_sugerido_nao_passa_por_cima_do_digitado(self) -> None:
        self.tela.abrir(direto=True)
        self.tela.campo_login.textEdited.emit("eric")
        self.tela.campo_login.setText("eric")
        self.tela.campo_nome.textEdited.emit("Outro Nome")
        self.assertEqual(self.tela.campo_login.text(), "eric")

    def test_senhas_diferentes_nao_vao_a_rede(self) -> None:
        self.tela.abrir(direto=True)
        self.tela.campo_senha.setText("cavalo-azul")
        self.tela.campo_repetir.setText("cavalo-verde")
        self.tela.criar_conta()
        self.assertIn("não são iguais", self.tela.aviso_conta.text())
        self.assertEqual(self.servidor.chamadas, [])

    def test_email_errado_nao_vai_a_rede(self) -> None:
        self.tela.abrir(direto=True)
        self.tela.campo_email.setText("semarroba")
        self.preencher()
        self.tela.criar_conta()
        self.assertIn("e-mail", self.tela.aviso_conta.text())
        self.assertEqual(self.servidor.chamadas, [])

    def test_criar_entra_e_pede_o_codigo(self) -> None:
        self.criar()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_EMAIL)
        self.assertEqual(self.servico.usuario.id, ADM)
        self.assertIn("e**c@teste.com", self.tela.texto_email.text())
        self.assertEqual(self.servidor.rotas(), ["criar-primeiro", "pedir-confirmacao"])
        self.assertEqual(self.tela.campo_senha.text(), "", "senha nao fica no campo")

    def test_email_que_nao_sai_nao_prende_ninguem(self) -> None:
        self.tela.abrir(direto=True)
        self.preencher()
        self.servidor.respostas["criar-primeiro"] = {
            "ok": True, "sessao": "s", "usuario": conta(), "acesso_assinado": pacote_acesso([conta()]),
            "lembranca": pacote_lembranca(ADM, 1)}
        self.servidor.respostas["pedir-confirmacao"] = {"ok": False, "erro": "falha_no_envio", "mensagem": "x"}
        self.tela.criar_conta()
        self.assertIn("Minha conta", self.tela.texto_email.text())
        self.tela.botao_email_depois.click()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_EQUIPE)

    def test_confirmar_o_email_segue_para_a_equipe(self) -> None:
        self.criar()
        self.servidor.respostas["confirmar-email"] = {
            "ok": True, "usuario": conta(), "acesso_assinado": pacote_acesso([conta(email_confirmado=True)])}
        self.tela.campo_codigo.setText("123456")
        self.tela.confirmar_email()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_EQUIPE)

    def test_codigo_errado_fica_na_tela(self) -> None:
        self.criar()
        self.servidor.respostas["confirmar-email"] = {"ok": False, "erro": "codigo_invalido", "mensagem": "Código incorreto"}
        self.tela.campo_codigo.setText("000000")
        self.tela.confirmar_email()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_EMAIL)
        self.assertIn("incorreto", self.tela.aviso_email.text())

    def test_equipe_vira_cracha_com_o_acesso_para_copiar(self) -> None:
        self.criar()
        self.tela.botao_email_depois.click()
        self.assertEqual(self.tela.botao_equipe_seguir.text().strip(), "Pular por enquanto")

        self.tela.equipe_nome.setText("Maria Conceição")
        self.tela.equipe_nome.textEdited.emit("Maria Conceição")
        self.assertEqual(self.tela.equipe_login.text(), "maria.conceicao")
        senha = self.tela.equipe_senha.text()
        self.assertRegex(senha, r"^[a-z]{4}-\d{4}-[a-z]{3}$")
        self.tela.equipe_funcao.setCurrentText("Estoque")
        self.servidor.respostas["salvar-usuario"] = {
            "ok": True, "usuario": maria(), "acesso_assinado": pacote_acesso([conta(), maria()])}
        self.tela.adicionar()

        corpo = self.servidor.chamadas[-1][1]
        self.assertEqual(corpo["usuario"]["modulos"], ["estoque"])
        self.assertIn("estoque_baixo", corpo["usuario"]["avisos"])
        self.assertEqual(corpo["usuario"]["papel"], "funcionario")
        self.assertEqual(corpo["senha"], senha)

        self.assertEqual(len(self.tela.crachas), 1)
        self.tela.crachas[0].botao.click()
        copiado = QGuiApplication.clipboard().text()
        self.assertIn("maria.conceicao", copiado)
        self.assertIn(senha, copiado)
        self.assertEqual(self.tela.botao_equipe_seguir.text().strip(), "Continuar")
        self.assertEqual(self.tela.equipe_nome.text(), "", "pronto para o proximo")
        self.assertNotEqual(self.tela.equipe_senha.text(), senha, "cada um com a sua")

    def test_login_repetido_explica_e_nao_vira_cracha(self) -> None:
        self.criar()
        self.tela.equipe_nome.setText("Maria")
        self.tela.equipe_login.setText("maria")
        self.servidor.respostas["salvar-usuario"] = {"ok": False, "erro": "login_em_uso", "mensagem": "Já existe uma conta com esse login."}
        self.tela.adicionar()
        self.assertIn("Já existe", self.tela.aviso_equipe.text())
        self.assertEqual(self.tela.crachas, [])

    def test_fim_conta_os_outros_computadores(self) -> None:
        self.criar()
        self.tela.botao_email_depois.click()
        self.tela.botao_equipe_seguir.click()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_PRONTO)
        self.assertEqual(self.tela.titulo_pronto.text(), "Tudo pronto, Eric")
        self.assertIn("2 outros computadores", self.tela.texto_pronto.text())
        self.tela.botao_abrir.click()
        self.assertEqual(self.concluidos, [True])

    def test_um_outro_computador_concorda_no_singular(self) -> None:
        self.loja["computadores"] = 2
        self.criar()
        self.tela.botao_email_depois.click()
        self.tela.botao_equipe_seguir.click()
        self.assertIn("1 outro computador desta chave vai pedir", self.tela.texto_pronto.text())

    def test_computador_unico_nao_fala_de_outros(self) -> None:
        self.loja["computadores"] = 1
        self.criar()
        self.tela.botao_email_depois.click()
        self.tela.botao_equipe_seguir.click()
        self.assertNotIn("computador", self.tela.texto_pronto.text())

    def test_sem_internet_nao_trava_a_loja_nem_quando_obrigatorio(self) -> None:
        self.tela.abrir(obrigatorio=True)
        self.tela.ir_para_conta()
        self.preencher()
        self.servidor.erro = SemConexao("sem rede")
        self.tela.criar_conta()
        self.assertIn("sem internet", self.tela.aviso_conta.text())
        self.assertFalse(self.tela.botao_depois_conta.isHidden())
        self.tela.botao_depois_conta.click()
        self.assertEqual(self.adiados, [True])


class Formatos(unittest.TestCase):
    def test_sugerir_login(self) -> None:
        self.assertEqual(nucleo.sugerir_login("Maria"), "maria")
        self.assertEqual(nucleo.sugerir_login("Maria Conceição"), "maria.conceicao")
        self.assertEqual(nucleo.sugerir_login("João da Silva Souza"), "joao.souza")
        self.assertEqual(nucleo.sugerir_login("   "), "")


if __name__ == "__main__":
    unittest.main()
