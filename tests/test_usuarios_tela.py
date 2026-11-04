"""Usuarios e acessos: a gestao do ADM, atras da senha dele."""

from __future__ import annotations

import unittest
from unittest import mock

from PySide6.QtWidgets import QApplication

from dumtech.core.supabase import SemConexao
from dumtech.hub.views import minha_conta_dialog, usuarios_view
from dumtech.hub.views.minha_conta_dialog import MinhaContaDialog
from dumtech.hub.views.usuarios_view import (
    PAGINA_LIBERADA, PAGINA_SEM_CONTAS, PAGINA_TRANCADA, SenhaDialog, UsuarioDialog, UsuariosView,
)

from .assinante import pacote_acesso, pacote_lembranca
from .test_acesso import ADM, MARIA, Base, conta, maria
from .test_login_tela import sincrono

_app: QApplication | None = None

MODULOS = {"vendas": "Vendas", "estoque": "Estoque", "agenda": "Agenda"}


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def detalhe(dados: dict, **extras) -> dict:
    return {**dados, "email": "", "ultimo_acesso": "2026-11-02T12:30:00+00:00", "ultimo_computador": "Caixa", **extras}


class BaseUsuarios(Base):
    def setUp(self) -> None:
        super().setUp()
        for modulo in (usuarios_view, minha_conta_dialog):
            patcher = mock.patch.object(modulo.tasks, "executar", sincrono)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.licenca([conta(), maria()])
        self.registro = mock.Mock()
        self.registro.available.return_value = [
            mock.Mock(app_id=a, manifest=mock.Mock(short_name=n)) for a, n in MODULOS.items()]
        self.servidor.respostas["usuarios"] = {"ok": True, "usuarios": [detalhe(conta()), detalhe(maria())]}
        self.servidor.respostas["computadores"] = {"ok": True, "max_computadores": 3, "computadores": [
            {"maquina": "AAAA-BBBB", "apelido": "Caixa", "este": True, "versao": "1.11.0",
             "ultima_checagem": "2026-11-02T12:30:00+00:00"},
            {"maquina": "CCCC-DDDD", "apelido": "", "este": False, "versao": "1.9.0", "ultima_checagem": None},
        ]}


class Portao(BaseUsuarios):
    def test_loja_sem_conta_convida(self) -> None:
        self.licenca()
        tela = UsuariosView(self.servico, self.registro)
        criar: list = []
        tela.criar_conta.connect(lambda: criar.append(True))
        tela.refresh()
        self.assertEqual(tela.paginas.currentIndex(), PAGINA_SEM_CONTAS)

    def test_sem_sessao_pede_a_senha(self) -> None:
        self.entrar(lembrar=True, usuarios=[conta(), maria()])
        self.servico.trancar_gestao()
        tela = UsuariosView(self.servico, self.registro)
        tela.refresh()
        self.assertEqual(tela.paginas.currentIndex(), PAGINA_TRANCADA)
        self.assertNotIn("usuarios", self.servidor.rotas(), "trancada nao busca nada")

    def test_senha_certa_libera(self) -> None:
        self.entrar(usuarios=[conta(), maria()])
        self.servico.trancar_gestao()
        tela = UsuariosView(self.servico, self.registro)
        tela.refresh()
        self.servidor.respostas["entrar"] = self.resposta_entrar(usuarios=[conta(), maria()])
        tela.campo_senha.setText("cavalo-azul")
        tela.liberar()
        self.assertEqual(tela.paginas.currentIndex(), PAGINA_LIBERADA)
        self.assertEqual(tela.campo_senha.text(), "")

    def test_sem_internet_diz_e_nao_abre(self) -> None:
        self.entrar(usuarios=[conta(), maria()])
        self.servico.trancar_gestao()
        tela = UsuariosView(self.servico, self.registro)
        tela.refresh()
        self.servidor.erro = SemConexao("sem rede")
        tela.campo_senha.setText("cavalo-azul")
        tela.liberar()
        self.assertEqual(tela.paginas.currentIndex(), PAGINA_TRANCADA)
        self.assertIn("sem internet", tela.aviso_trancada.text())

    def test_sair_da_secao_tranca(self) -> None:
        self.entrar(usuarios=[conta(), maria()])
        tela = UsuariosView(self.servico, self.registro)
        tela.show()
        tela.refresh()
        self.assertTrue(self.servico.gestao_aberta)
        tela.hide()
        self.assertFalse(self.servico.gestao_aberta)


class Gestao(BaseUsuarios):
    def setUp(self) -> None:
        super().setUp()
        self.entrar(usuarios=[conta(), maria()])
        self.tela = UsuariosView(self.servico, self.registro)
        self.tela.refresh()
        self.mudancas: list = []
        self.tela.mudou.connect(lambda: self.mudancas.append(True))

    def test_mostra_quantos_de_quantos(self) -> None:
        self.assertEqual(self.tela.titulo_usuarios.text(), "Usuários (2)")
        self.assertEqual(self.tela.titulo_computadores.text(), "Computadores: 2 de 3")

    def test_sessao_vencida_no_servidor_tranca_a_tela(self) -> None:
        self.servidor.respostas["usuarios"] = {"ok": False, "erro": "sessao_vencida", "mensagem": "Sua sessão venceu."}
        self.tela.carregar()
        self.assertEqual(self.tela.paginas.currentIndex(), PAGINA_TRANCADA)
        self.assertIn("venceu", self.tela.aviso_trancada.text())

    def test_bloquear_confirma_e_manda_inativo(self) -> None:
        self.servidor.respostas["salvar-usuario"] = {
            "ok": True, "usuario": maria(ativo=False), "acesso_assinado": pacote_acesso([conta(), maria(ativo=False)])}
        with mock.patch.object(usuarios_view, "confirmar", return_value=True) as pergunta:
            self.tela.alternar_bloqueio(detalhe(maria()))
        pergunta.assert_called_once()
        corpo = next(c for n, c in self.servidor.chamadas if n.endswith("salvar-usuario"))
        self.assertEqual(corpo["usuario"]["ativo"], False)
        self.assertEqual(self.mudancas, [True])

    def test_bloquear_cancelado_nao_faz_nada(self) -> None:
        with mock.patch.object(usuarios_view, "confirmar", return_value=False):
            self.tela.alternar_bloqueio(detalhe(maria()))
        self.assertNotIn("salvar-usuario", self.servidor.rotas())

    def test_desbloquear_nao_pergunta(self) -> None:
        self.servidor.respostas["salvar-usuario"] = {"ok": True, "usuario": maria()}
        with mock.patch.object(usuarios_view, "confirmar") as pergunta:
            self.tela.alternar_bloqueio(detalhe(maria(ativo=False)))
        pergunta.assert_not_called()

    def test_apagar_mostra_a_recusa_do_ultimo_adm(self) -> None:
        self.servidor.respostas["apagar-usuario"] = {"ok": False, "erro": "ultimo_adm",
                                                     "mensagem": "A loja precisa de pelo menos um administrador ativo."}
        with mock.patch.object(usuarios_view, "confirmar", return_value=True):
            self.tela.apagar(detalhe(conta()))
        self.assertIn("pelo menos um administrador", self.tela.aviso.text())
        self.assertEqual(self.mudancas, [])

    def test_liberar_outro_computador_avisa_e_a_licenca_fica(self) -> None:
        self.servidor.respostas["liberar-computador"] = {"ok": True, "este": False}
        saiu: list = []
        self.tela.licenca_saiu.connect(lambda: saiu.append(True))
        with mock.patch.object(usuarios_view, "confirmar", return_value=True) as pergunta:
            self.tela.liberar_computador({"maquina": "CCCC-DDDD", "apelido": "", "este": False})
        self.assertIn("vaga fica livre", pergunta.call_args.args[2])
        self.assertEqual(saiu, [])

    def test_liberar_este_computador_avisa_diferente(self) -> None:
        self.servidor.respostas["liberar-computador"] = {"ok": True, "este": True}
        saiu: list = []
        self.tela.licenca_saiu.connect(lambda: saiu.append(True))
        with mock.patch.object(usuarios_view, "confirmar", return_value=True) as pergunta:
            self.tela.liberar_computador({"maquina": "AAAA-BBBB", "apelido": "Caixa", "este": True})
        self.assertIn("sai deste computador", pergunta.call_args.args[2])
        self.assertEqual(saiu, [True])


class Formulario(BaseUsuarios):
    def setUp(self) -> None:
        super().setUp()
        self.entrar(usuarios=[conta(), maria()])

    def dialogo(self, dados=None) -> UsuarioDialog:
        dialogo = UsuarioDialog(self.servico, MODULOS, dados)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def test_modelo_marca_e_ainda_da_para_ajustar(self) -> None:
        dialogo = self.dialogo()
        dialogo.campo_modelo.setCurrentText("Vendedor")
        self.assertTrue(dialogo.caixas_modulos["vendas"].isChecked())
        self.assertTrue(dialogo.caixas_modulos["agenda"].isChecked())
        self.assertFalse(dialogo.caixas_modulos["estoque"].isChecked())
        dialogo.caixas_modulos["estoque"].setChecked(True)
        self.assertEqual(dialogo.campo_modelo.currentIndex(), 0, "mexeu: nao e mais o modelo")
        dados = dialogo.montar()
        self.assertCountEqual(dados["modulos"], ["vendas", "agenda", "estoque"])

    def test_aviso_acompanha_o_modulo(self) -> None:
        dialogo = self.dialogo()
        dialogo.show()
        dialogo.caixas_modulos["estoque"].setChecked(True)
        self.assertTrue(dialogo.caixas_avisos["estoque_baixo"].isChecked())
        self.assertTrue(dialogo.caixas_avisos["estoque_baixo"].isVisible())
        dialogo.caixas_modulos["estoque"].setChecked(False)
        self.assertFalse(dialogo.caixas_avisos["estoque_baixo"].isVisible())
        self.assertNotIn("estoque_baixo", dialogo.montar()["avisos"])
        dialogo.hide()

    def test_so_aparece_o_que_a_licenca_liberou(self) -> None:
        dialogo = self.dialogo()
        self.assertNotIn("financeiro", dialogo.caixas_modulos)
        self.assertNotIn("conta_vencida", dialogo.caixas_avisos)

    def test_adm_nao_escolhe_modulos(self) -> None:
        dialogo = self.dialogo()
        dialogo.caixas_modulos["vendas"].setChecked(True)
        dialogo.campo_papel.setCurrentIndex(1)
        self.assertTrue(dialogo.bloco_permissoes.isHidden())
        dados = dialogo.montar()
        self.assertEqual(dados["modulos"], [])
        self.assertEqual(dados["avisos"], [])

    def test_adm_precisa_de_email(self) -> None:
        dialogo = self.dialogo()
        dialogo.campo_nome.setText("Chefe")
        dialogo.campo_login.setText("chefe")
        dialogo.campo_papel.setCurrentIndex(1)
        self.assertIs(dialogo.salvar(), False)
        self.assertIn("e-mail", dialogo.aviso.text())
        self.assertNotIn("salvar-usuario", self.servidor.rotas())

    def test_edicao_abre_com_o_que_a_pessoa_tem(self) -> None:
        dialogo = self.dialogo(detalhe(maria()))
        self.assertTrue(dialogo.caixas_modulos["vendas"].isChecked())
        self.assertFalse(dialogo.caixas_modulos["estoque"].isChecked())
        self.assertIsNone(dialogo.campo_senha, "editar nao mexe em senha")

    def test_recusa_do_servidor_mantem_o_formulario_aberto(self) -> None:
        dialogo = self.dialogo()
        dialogo.campo_nome.setText("Maria")
        dialogo.campo_login.setText("maria")
        self.servidor.respostas["salvar-usuario"] = {"ok": False, "erro": "login_em_uso", "mensagem": "Já existe uma conta com esse login."}
        self.assertIs(dialogo.salvar(), False)
        self.assertIn("Já existe", dialogo.aviso.text())
        self.assertTrue(dialogo.botao_salvar.isEnabled())

    def test_redefinir_senha_manda_para_a_conta_certa(self) -> None:
        dialogo = SenhaDialog(self.servico, detalhe(maria()))
        self.addCleanup(dialogo.deleteLater)
        self.servidor.respostas["senha-usuario"] = {"ok": True, "usuario": maria(), "acesso_assinado": pacote_acesso([conta(), maria()])}
        dialogo.salvar()
        corpo = next(c for n, c in self.servidor.chamadas if n.endswith("senha-usuario"))
        self.assertEqual(corpo["id"], MARIA)
        self.assertEqual(corpo["senha"], dialogo.senha_escolhida)


class MinhaConta(BaseUsuarios):
    def dialogo(self) -> MinhaContaDialog:
        dialogo = MinhaContaDialog(self.servico)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def test_funcionario_troca_a_propria_senha_sem_sessao_aberta(self) -> None:
        self.entrar(login="maria", usuario=maria(), usuarios=[conta(), maria()], lembrar=True)
        self.servico.trancar_gestao()
        nova = maria(senha_versao=2)
        self.servidor.respostas["entrar"] = self.resposta_entrar(maria(), [conta(), maria()])
        self.servidor.respostas["trocar-senha"] = {
            "ok": True, "usuario": nova, "acesso_assinado": pacote_acesso([conta(), nova]),
            "lembranca": pacote_lembranca(MARIA, 2)}
        dialogo = self.dialogo()
        dialogo.campo_atual.setText("cavalo-azul")
        dialogo.campo_nova.setText("outra-senha-boa")
        dialogo.campo_repetir.setText("outra-senha-boa")
        dialogo.salvar()
        self.assertEqual(self.servidor.rotas()[-2:], ["entrar", "trocar-senha"])
        self.assertEqual(self.servico.usuario.senha_versao, 2)
        self.assertFalse(self.servico.reconciliar())

    def test_validacoes_nao_vao_a_rede(self) -> None:
        self.entrar()
        dialogo = self.dialogo()
        antes = len(self.servidor.chamadas)
        dialogo.salvar()
        self.assertIn("senha atual", dialogo.aviso.text())
        dialogo.campo_atual.setText("cavalo-azul")
        dialogo.campo_nova.setText("outra-senha-boa")
        dialogo.campo_repetir.setText("diferente-aqui")
        dialogo.salvar()
        self.assertIn("não são iguais", dialogo.aviso.text())
        self.assertEqual(len(self.servidor.chamadas), antes)

    def test_email_ja_confirmado_nao_incomoda(self) -> None:
        self.entrar()
        self.assertTrue(self.dialogo().bloco_email.isHidden())

    def test_email_sem_confirmar_oferece_confirmar(self) -> None:
        pendente = conta(email_confirmado=False)
        self.entrar(usuario=pendente, usuarios=[pendente])
        dialogo = self.dialogo()
        self.assertFalse(dialogo.bloco_email.isHidden())
        self.servidor.respostas["pedir-confirmacao"] = {"ok": True, "email": "d**a@x.com"}
        dialogo.enviar_codigo()
        self.assertIn("d**a@x.com", dialogo.aviso_email.text())
        self.servidor.respostas["confirmar-email"] = {"ok": True, "usuario": conta(), "acesso_assinado": pacote_acesso([conta()])}
        dialogo.campo_codigo.setText("123456")
        dialogo.confirmar_email()
        self.assertEqual(dialogo.aviso_email.text(), "E-mail confirmado.")


if __name__ == "__main__":
    unittest.main()
