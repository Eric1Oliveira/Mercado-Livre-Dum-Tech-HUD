"""A porta do Hub: entrar, o olho da senha, esqueci e a primeira senha."""

from __future__ import annotations

import unittest
from unittest import mock

from PySide6.QtWidgets import QApplication, QLineEdit

from dumtech.core.supabase import SemConexao
from dumtech.hub.views import login_view
from dumtech.hub.views.login_view import (
    PAGINA_CODIGO, PAGINA_ENTRAR, PAGINA_ESQUECI, PAGINA_TROCAR, LoginView,
)
from dumtech.ui.widgets.campo_senha import CampoSenha, MedidorDeSenha

from .assinante import pacote_acesso, pacote_lembranca
from .test_acesso import ADM, MARIA, Base, conta, maria

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def sincrono(_parent, funcao, ok, falha) -> None:
    try:
        resultado = funcao()
    except Exception as erro:  # noqa: BLE001 - o erro vai para a tela
        falha(erro)
    else:
        ok(resultado)


class CampoDeSenha(unittest.TestCase):
    def test_comeca_oculta_e_o_olho_mostra(self) -> None:
        campo = CampoSenha()
        campo.setText("cavalo-azul")
        self.assertEqual(campo.echoMode(), QLineEdit.EchoMode.Password)
        self.assertEqual(campo.olho.toolTip(), "Mostrar senha")
        campo.olho.trigger()
        self.assertEqual(campo.echoMode(), QLineEdit.EchoMode.Normal)
        self.assertEqual(campo.olho.toolTip(), "Ocultar senha")
        self.assertEqual(campo.text(), "cavalo-azul")
        campo.olho.trigger()
        self.assertEqual(campo.echoMode(), QLineEdit.EchoMode.Password)

    def test_sair_da_tela_esconde_de_novo(self) -> None:
        campo = CampoSenha()
        campo.show()
        campo.alternar()
        campo.hide()
        self.assertFalse(campo.visivel)

    def test_medidor_acompanha(self) -> None:
        campo = CampoSenha()
        medidor = MedidorDeSenha(campo)
        self.assertEqual(medidor.rotulo.text(), "")
        campo.setText("123")
        self.assertEqual(medidor.rotulo.text(), "Ainda não serve")
        campo.setText("Cavalo-azul-99")
        self.assertEqual(medidor.forca, 3)
        self.assertEqual(medidor.rotulo.text(), "Forte")


class Login(Base):
    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(login_view.tasks, "executar", sincrono)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.licenca([conta(), maria()])
        self.tela = LoginView(self.servico, lambda: "Padaria do Eric")
        self.entradas: list = []
        self.tela.entrou.connect(lambda: self.entradas.append(True))
        self.addCleanup(self.tela.deleteLater)

    def digitar(self, login="dona", senha="cavalo-azul") -> None:
        self.tela.campo_login.setText(login)
        self.tela.campo_senha.setText(senha)

    def test_comeca_pedindo_a_conta_e_lembrar_ligado(self) -> None:
        self.assertEqual(self.tela.titulo_entrar.text(), "Entre com a sua conta")
        self.assertTrue(self.tela.lembrar.isChecked())
        self.assertFalse(self.tela.caixa_pessoas.isVisibleTo(self.tela))
        self.assertEqual(self.tela.faixa.titulo.text(), "Padaria do Eric")

    def test_quem_ja_entrou_aparece_em_um_clique(self) -> None:
        self.entrar(login="maria", usuario=maria(), usuarios=[conta(), maria()])
        self.entrar(usuarios=[conta(), maria()])
        self.tela.preparar()
        self.assertEqual(self.tela.titulo_entrar.text(), "Quem vai usar o Hub agora?")
        self.assertEqual([b.login for b in self.tela._pessoas], ["dona", "maria"])
        self.tela._pessoas[1].click()
        self.assertEqual(self.tela.campo_login.text(), "maria")
        self.assertTrue(self.tela._pessoas[1].isChecked())
        self.assertFalse(self.tela._pessoas[0].isChecked())

    def test_entrar_certo_avisa_o_hub(self) -> None:
        self.servidor.respostas["entrar"] = self.resposta_entrar(usuarios=[conta(), maria()], lembrar=True)
        self.digitar()
        self.tela.botao_entrar.click()
        self.assertEqual(self.entradas, [True])
        self.assertEqual(self.servico.usuario.id, ADM)
        self.assertEqual(self.tela.campo_senha.text(), "", "senha nao fica no campo")

    def test_campos_vazios_dizem_o_que_falta(self) -> None:
        self.tela.entrar()
        self.assertEqual(self.tela.aviso_entrar.text(), "Digite o seu login.")
        self.tela.campo_login.setText("dona")
        self.tela.entrar()
        self.assertEqual(self.tela.aviso_entrar.text(), "Digite a sua senha.")
        self.assertEqual(self.servidor.chamadas, [])

    def test_senha_errada_mostra_recado(self) -> None:
        self.servidor.respostas["entrar"] = {"ok": False, "erro": "credenciais", "mensagem": "Login ou senha incorretos."}
        self.digitar(senha="errada")
        self.tela.entrar()
        self.assertEqual(self.tela.aviso_entrar.text(), "Login ou senha incorretos.")
        self.assertEqual(self.entradas, [])

    def test_sem_internet_quem_nunca_entrou_aqui_e_avisado(self) -> None:
        self.servidor.erro = SemConexao("sem rede")
        self.digitar(login="maria")
        self.tela.entrar()
        self.assertIn("Conecte à internet", self.tela.aviso_entrar.text())
        self.assertEqual(self.entradas, [])

    def test_sem_internet_quem_ja_entrou_passa(self) -> None:
        self.entrar()
        self.servico.sair(esquecer=True)
        self.servidor.erro = SemConexao("sem rede")
        self.digitar()
        self.tela.entrar()
        self.assertEqual(self.entradas, [True])

    def test_quem_recebeu_senha_de_outro_cria_a_propria(self) -> None:
        temporaria = maria(trocar_senha=True)
        self.servidor.respostas["entrar"] = self.resposta_entrar(temporaria, [conta(), temporaria])
        self.digitar(login="maria", senha="kmpr-4821-tzq")
        self.tela.entrar()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_TROCAR)
        self.assertEqual(self.entradas, [], "ainda nao entrou")

        self.tela.nova_trocar.setText("kmpr-4821-tzq")
        self.tela.repetir_trocar.setText("kmpr-4821-tzq")
        self.tela.trocar()
        self.assertIn("diferente", self.tela.aviso_trocar.text())

        self.tela.nova_trocar.setText("minha-senha-boa")
        self.tela.repetir_trocar.setText("outra-coisa-aqui")
        self.tela.trocar()
        self.assertIn("não são iguais", self.tela.aviso_trocar.text())

        nova = maria(senha_versao=2)
        self.servidor.respostas["trocar-senha"] = {
            "ok": True, "usuario": nova, "acesso_assinado": pacote_acesso([conta(), nova]),
            "lembranca": pacote_lembranca(MARIA, 2)}
        self.tela.repetir_trocar.setText("minha-senha-boa")
        self.tela.trocar()
        self.assertEqual(self.entradas, [True])
        corpo = self.servidor.chamadas[-1][1]
        self.assertEqual(corpo["atual"], "kmpr-4821-tzq")
        self.assertEqual(corpo["nova"], "minha-senha-boa")

    def test_esqueci_ate_entrar(self) -> None:
        self.tela.campo_login.setText("dona")
        self.tela.link_esqueci.click()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_ESQUECI)
        self.assertEqual(self.tela.campo_esqueci.text(), "dona", "nao redigita o login")

        self.servidor.respostas["pedir-codigo"] = {"ok": True, "email": "d**a@gmail.com", "validade_minutos": 10}
        self.tela.botao_enviar.click()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_CODIGO)
        self.assertIn("d**a@gmail.com", self.tela.texto_codigo.text())

        self.tela.campo_codigo.setText("654321")
        self.tela.nova_codigo.setText("minha-senha-nova")
        self.tela.repetir_codigo.setText("minha-senha-nova")
        self.servidor.respostas["redefinir"] = self.resposta_entrar(usuarios=[conta(), maria()], lembrar=True)
        self.tela.botao_redefinir.click()
        self.assertEqual(self.entradas, [True])
        self.assertEqual(self.servidor.chamadas[-1][1]["codigo"], "654321")

    def test_esqueci_sem_email_manda_pedir_ao_administrador(self) -> None:
        self.tela.ir_para_esqueci()
        self.tela.campo_esqueci.setText("maria")
        self.servidor.respostas["pedir-codigo"] = {"ok": True, "sem_email": True}
        self.tela.pedir_codigo()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_ESQUECI)
        self.assertIn("administrador", self.tela.aviso_esqueci.text())

    def test_esqueci_sem_internet_explica(self) -> None:
        self.tela.ir_para_esqueci()
        self.tela.campo_esqueci.setText("dona")
        self.servidor.erro = SemConexao("sem rede")
        self.tela.pedir_codigo()
        self.assertIn("sem internet", self.tela.aviso_esqueci.text())

    def test_codigo_incompleto_nao_vai_a_rede(self) -> None:
        self.tela.campo_login.setText("dona")
        self.tela.campo_codigo.setText("12")
        self.tela.nova_codigo.setText("minha-senha-nova")
        self.tela.repetir_codigo.setText("minha-senha-nova")
        self.tela.redefinir()
        self.assertIn("6 números", self.tela.aviso_codigo.text())
        self.assertEqual(self.servidor.chamadas, [])

    def test_computador_fora_da_chave_mostra_a_saida(self) -> None:
        self.assertTrue(self.tela.link_licenca.isHidden())
        self.licencas._bloquear("Ative de novo", "maquina_nao_ativada")
        self.tela.preparar()
        self.assertFalse(self.tela.link_licenca.isHidden())
        pedidos: list = []
        self.tela.ativar_licenca.connect(lambda: pedidos.append(True))
        self.tela.link_licenca.click()
        self.assertEqual(pedidos, [True])

    def test_preparar_volta_ao_comeco_e_limpa(self) -> None:
        self.tela.campo_senha.setText("sobrou")
        self.tela.ir_para_esqueci()
        self.tela.preparar()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_ENTRAR)
        self.assertEqual(self.tela.campo_senha.text(), "")


if __name__ == "__main__":
    unittest.main()
