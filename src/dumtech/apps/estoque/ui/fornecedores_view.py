"""Quem vende para a loja: quem ligar quando o produto acabar."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget

from ....core.documentos import formatar_telefone
from ....ui.widgets import form
from ....ui.widgets.crud_view import CrudView
from ....ui.widgets.form import FormDialog
from ..models import Fornecedor
from ..repository import EstoqueRepository


class FornecedorDialog(FormDialog):
    def __init__(self, repository: EstoqueRepository, fornecedor: Fornecedor | None,
                 parent: QWidget | None = None) -> None:
        self.repository = repository
        self.fornecedor = fornecedor or Fornecedor()
        super().__init__("Editar fornecedor" if fornecedor else "Novo fornecedor",
                         "Quem vende mercadoria para você", parent, largura=540)
        self.nome = form.texto(self.fornecedor.nome, "Ex.: Atacado Central")
        self.add_row("Nome", self.nome)
        self.documento = form.texto(self.fornecedor.documento, "CNPJ ou CPF")
        self.telefone = form.texto(formatar_telefone(self.fornecedor.telefone), "(00) 00000-0000")
        self.add_row("Documento", form.linha(self.documento, "Telefone", self.telefone))
        self.email = form.texto(self.fornecedor.email, "email@exemplo.com")
        self.add_row("E-mail", self.email)
        self.observacoes = form.area(self.fornecedor.observacoes, "Prazo, condições, contato...")
        self.add_row("Observações", self.observacoes)
        self.nome.setFocus()

    def salvar(self) -> None:
        self.fornecedor.nome = self.nome.text()
        self.fornecedor.documento = self.documento.text()
        self.fornecedor.telefone = self.telefone.text()
        self.fornecedor.email = self.email.text()
        self.fornecedor.observacoes = self.observacoes.toPlainText()
        self.repository.salvar_fornecedor(self.fornecedor)


class FornecedoresView(CrudView):
    titulo = "Fornecedores"
    nome_registro = "fornecedor"
    nome_plural = "fornecedores"
    rotulo_novo = "Novo fornecedor"
    dica_pesquisa = "Pesquisar por nome, documento ou telefone..."
    colunas = ["Fornecedor", "Documento", "Telefone", "E-mail"]
    larguras = {1: 170, 2: 150}
    exportavel = True

    def __init__(self, repository: EstoqueRepository, parent: QWidget | None = None) -> None:
        self.repository = repository
        super().__init__(parent)

    def build_filters(self, layout: QHBoxLayout) -> None:
        return None

    def carregar(self) -> list[Fornecedor]:
        return self.repository.listar_fornecedores(self.busca.text())

    def montar_linha(self, fornecedor: Fornecedor) -> list:
        return [
            self.tabela.cell(fornecedor.nome, bold=True, data=fornecedor.id),
            self.tabela.cell(fornecedor.documento or "-"),
            self.tabela.cell(formatar_telefone(fornecedor.telefone) or "-"),
            self.tabela.cell(fornecedor.email or "-"),
        ]

    def abrir_dialogo(self, fornecedor: Fornecedor | None):
        return FornecedorDialog(self.repository, fornecedor, self)

    def excluir(self, fornecedor: Fornecedor) -> None:
        self.repository.excluir_fornecedor(fornecedor.id)

    def descricao(self, fornecedor: Fornecedor) -> str:
        return fornecedor.nome
