"""Minha conta: o que qualquer pessoa pode fazer na propria conta.

Trocar a senha e confirmar o e-mail. Funcionario nao chega a Usuarios, entao e
aqui que ele resolve a propria senha. Precisa de internet: quem decide e o servidor.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget

from ...core.acesso import AcessoError, AcessoService, validar_senha
from ...ui import tasks
from ...ui.theme import Space
from ...ui.widgets import form
from ...ui.widgets.buttons import Button
from ...ui.widgets.campo_senha import CampoCodigo, CampoSenha, MedidorDeSenha
from ...ui.widgets.common import label, separator
from .acesso_comum import dizer, mensagem


class MinhaContaDialog(form.FormDialog):
    """Quem esta aqui, a troca de senha e a confirmacao do e-mail."""

    def __init__(self, acesso: AcessoService, parent: QWidget | None = None) -> None:
        usuario = acesso.usuario
        super().__init__("Minha conta", f"{usuario.nome}  ·  {usuario.login}", parent, largura=480)
        self.acesso = acesso
        self.usuario = usuario
        self.botao_salvar.setText("  Trocar senha")

        self.campo_atual = CampoSenha("Sua senha de agora")
        self.add_row("Senha atual", self.campo_atual)
        self.campo_nova = CampoSenha("Pelo menos 8 caracteres")
        self.add_row("Senha nova", self.campo_nova)
        self.add_row("", MedidorDeSenha(self.campo_nova))
        self.campo_repetir = CampoSenha("Digite de novo")
        self.add_row("Repita a senha", self.campo_repetir)

        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        self.aviso.setVisible(False)
        self.extras.addWidget(self.aviso)

        self.bloco_email = QWidget()
        coluna = form.QVBoxLayout(self.bloco_email)
        coluna.setContentsMargins(0, Space.sm, 0, 0)
        coluna.setSpacing(Space.sm)
        coluna.addWidget(separator())
        coluna.addWidget(label("Confirme o seu e-mail", "strong"))
        texto = label("É por ele que você recupera a senha. Para enviar o código, digite a sua senha atual acima.", "dim")
        texto.setWordWrap(True)
        coluna.addWidget(texto)
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        self.campo_codigo = CampoCodigo()
        linha.addWidget(self.campo_codigo, 1)
        self.botao_enviar = Button("Enviar código", "chat", "ghost")
        self.botao_enviar.clicked.connect(self.enviar_codigo)
        linha.addWidget(self.botao_enviar)
        self.botao_confirmar = Button("Confirmar", "check")
        self.botao_confirmar.clicked.connect(self.confirmar_email)
        linha.addWidget(self.botao_confirmar)
        coluna.addLayout(linha)
        self.aviso_email = label("", "muted")
        self.aviso_email.setWordWrap(True)
        self.aviso_email.setVisible(False)
        coluna.addWidget(self.aviso_email)
        self.extras.addWidget(self.bloco_email)
        self.bloco_email.setVisible(usuario.tem_email and not usuario.email_confirmado)

    # -------------------------------------------------------------------- senha
    def salvar(self):
        atual = self.campo_atual.text()
        nova = self.campo_nova.text()
        if not atual:
            dizer(self.aviso, "Digite a sua senha atual.", "warning")
            return False
        problema = validar_senha(nova, self.usuario.login)
        if problema:
            dizer(self.aviso, problema, "warning")
            return False
        if nova != self.campo_repetir.text():
            dizer(self.aviso, "As duas senhas não são iguais.", "warning")
            return False
        lembrar = self.acesso.esta_lembrado()
        self.botao_salvar.setEnabled(False)
        dizer(self.aviso, "Salvando...")

        def concluiu(resposta: dict) -> None:
            self.botao_salvar.setEnabled(True)
            try:
                self.acesso.aplicar(resposta)
            except AcessoError as erro:
                dizer(self.aviso, str(erro), "danger")
                return
            self.accept()

        def falhou(erro: Exception) -> None:
            self.botao_salvar.setEnabled(True)
            dizer(self.aviso, mensagem(erro), "warning")

        tasks.executar(self, lambda: self.acesso.trocar_senha(atual, nova, lembrar), concluiu, falhou)
        return False  # quem fecha e a resposta do servidor

    # ------------------------------------------------------------------- e-mail
    def enviar_codigo(self) -> None:
        senha = self.campo_atual.text()
        if not self.acesso.gestao_aberta and not senha:
            dizer(self.aviso_email, "Digite a sua senha atual acima para enviar o código.", "warning")
            return
        self.botao_enviar.setEnabled(False)
        dizer(self.aviso_email, "Enviando...")

        def trabalho() -> dict | None:
            return self.acesso.reabrir_gestao(senha) if not self.acesso.gestao_aberta else None

        def abriu(entrada) -> None:
            if entrada is not None:
                self.acesso.aplicar(entrada)
            tasks.executar(self, self.acesso.pedir_confirmacao, enviou, falhou)

        def enviou(email: str) -> None:
            self.botao_enviar.setEnabled(True)
            dizer(self.aviso_email, f"Enviamos um código para {email}.", "success")

        def falhou(erro: Exception) -> None:
            self.botao_enviar.setEnabled(True)
            dizer(self.aviso_email, mensagem(erro), "warning")

        tasks.executar(self, trabalho, abriu, falhou)

    def confirmar_email(self) -> None:
        codigo = self.campo_codigo.text().strip()
        if len(codigo) != 6:
            dizer(self.aviso_email, "Digite os 6 números que chegaram no e-mail.", "warning")
            return
        self.botao_confirmar.setEnabled(False)

        def concluiu(resposta: dict) -> None:
            self.botao_confirmar.setEnabled(True)
            self.acesso.guardar_documento(resposta.get("acesso_assinado"))
            dizer(self.aviso_email, "E-mail confirmado.", "success")

        def falhou(erro: Exception) -> None:
            self.botao_confirmar.setEnabled(True)
            dizer(self.aviso_email, mensagem(erro), "warning")

        tasks.executar(self, lambda: self.acesso.confirmar_email(codigo), concluiu, falhou)
