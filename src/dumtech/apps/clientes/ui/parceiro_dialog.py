"""Formulario de parceiro: quem indica clientes para a loja."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QWidget

from ....core.contacts import ContactsStore, Parceiro
from ....ui.widgets import form
from ....ui.widgets.form import FormDialog


class ParceiroDialog(FormDialog):
    def __init__(
        self,
        store: ContactsStore,
        parceiro: Parceiro | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self.store = store
        self.parceiro = parceiro or Parceiro()
        self.editando = parceiro is not None
        super().__init__(
            "Editar parceiro" if self.editando else "Novo parceiro",
            "Quem indica clientes para você: arquiteto, contador, outra loja...",
            parent,
            largura=560,
        )

        self.nome = form.texto(self.parceiro.nome, "Ex.: Ana Souza Arquitetura")
        self.add_row("Nome", self.nome)

        self.telefone = form.texto(self.parceiro.telefone_formatado, "(00) 00000-0000")
        self.email = form.texto(self.parceiro.email, "email@exemplo.com")
        self.add_row("Telefone", form.linha(self.telefone, "E-mail", self.email))

        self.observacoes = form.area(
            self.parceiro.observacoes, "Ex.: comissão de 5% sobre a primeira compra"
        )
        self.add_row("Observações", self.observacoes)

        if self.editando:
            self.ativo = QCheckBox("Parceiro ativo (aparece no cadastro de clientes)")
            self.ativo.setChecked(self.parceiro.ativo)
            self.add_row("", self.ativo)

        self.add_note(
            "Para contar uma indicação, abra o cadastro do cliente e escolha o "
            "parceiro em \"Indicado por\"."
        )
        self.nome.setFocus()

    def salvar(self) -> None:
        self.parceiro.nome = self.nome.text()
        self.parceiro.telefone = self.telefone.text()
        self.parceiro.email = self.email.text()
        self.parceiro.observacoes = self.observacoes.toPlainText()
        if self.editando:
            self.parceiro.ativo = self.ativo.isChecked()
            self.store.atualizar_parceiro(self.parceiro)
        else:
            self.store.criar_parceiro(self.parceiro)
