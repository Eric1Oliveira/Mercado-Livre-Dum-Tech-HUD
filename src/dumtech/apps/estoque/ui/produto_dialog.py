"""Janela de cadastro/edicao de produto."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QWidget

from ....ui.widgets import form
from ....ui.widgets.form import FormDialog
from ..models import UNIDADES, Produto, casas
from ..repository import EstoqueRepository


class ProdutoDialog(FormDialog):
    """Formulario unico usado para adicionar e para editar um produto."""

    def __init__(
        self,
        repository: EstoqueRepository,
        produto: Produto | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self.repository = repository
        self.produto = produto or Produto()
        self.editando = produto is not None
        super().__init__(
            "Editar produto" if self.editando else "Novo produto",
            "Preencha os dados do produto do seu estoque",
            parent,
            largura=620,
        )

        self.codigo = form.texto(self.produto.codigo, "Ex.: MOU-001")
        self.codigo_barras = form.texto(self.produto.codigo_barras, "Bipe ou digite o EAN")
        self.add_row("Codigo", form.linha(self.codigo, "Codigo de barras", self.codigo_barras))

        self.nome = form.texto(self.produto.nome, "Ex.: Mouse USB sem fio")
        self.add_row("Nome", self.nome)

        self.categoria = form.combo_sugestao(
            self.produto.categoria, self.repository.categorias(), "Ex.: Perifericos"
        )
        self.unidade = form.escolha(
            [(f"{u.sigla} - {u.nome}", u.sigla) for u in UNIDADES.values()],
            self.produto.unidade,
        )
        self.unidade.currentIndexChanged.connect(self._unidade_mudou)
        self.add_row("Categoria", form.linha(self.categoria, "Unidade", self.unidade))

        self.fornecedor = form.combo_sugestao(
            self.produto.fornecedor, self.repository.fornecedores(), "De quem voce compra"
        )
        self.localizacao = form.combo_sugestao(
            self.produto.localizacao, self.repository.localizacoes(), "Ex.: Prateleira A3"
        )
        self.add_row("Fornecedor", form.linha(self.fornecedor, "Local", self.localizacao))

        decimais = casas(self.produto.unidade)
        self.quantidade = form.quantidade(self.produto.quantidade, decimais)
        self.estoque_minimo = form.quantidade(self.produto.estoque_minimo, decimais)
        self.estoque_maximo = form.quantidade(self.produto.estoque_maximo, decimais)
        self.add_row(
            "Quantidade",
            form.linha(
                self.quantidade,
                "Minimo",
                self.estoque_minimo,
                "Maximo",
                self.estoque_maximo,
            ),
        )

        self.preco_custo = form.dinheiro(self.produto.preco_custo)
        self.preco_venda = form.dinheiro(self.produto.preco_venda)
        self.add_row("Custo medio", form.linha(self.preco_custo, "Venda", self.preco_venda))

        self.descricao = form.area(self.produto.descricao, "Detalhes do produto (opcional)")
        self.add_row("Descricao", self.descricao)

        if self.editando:
            self.ativo = QCheckBox("Produto ativo (aparece nas listas)")
            self.ativo.setChecked(self.produto.ativo)
            self.add_row("", self.ativo)
            self.add_note(
                "O maximo e o nivel que voce quer ter em estoque: e dele que sai a "
                "sugestao de quanto comprar. O custo medio se atualiza sozinho a cada "
                "entrada com custo informado. Alterar a quantidade aqui gera um ajuste "
                "no historico."
            )
        else:
            self.add_note(
                "O maximo e o nivel que voce quer ter em estoque: e dele que sai a "
                "sugestao de quanto comprar. Deixe em zero se nao usar."
            )
        self.codigo.setFocus()

    # ------------------------------------------------------------------ campos
    def _unidade_mudou(self) -> None:
        """Unidade de medida aceita fracao; unidade contavel, nao."""
        decimais = casas(self.unidade.currentData())
        for campo in (self.quantidade, self.estoque_minimo, self.estoque_maximo):
            campo.setDecimals(decimais)

    # ------------------------------------------------------------------ salvar
    def salvar(self) -> None:
        self.produto.codigo = self.codigo.text()
        self.produto.codigo_barras = self.codigo_barras.text()
        self.produto.nome = self.nome.text()
        self.produto.descricao = self.descricao.toPlainText()
        self.produto.categoria = self.categoria.currentText()
        self.produto.unidade = self.unidade.currentData()
        self.produto.fornecedor = self.fornecedor.currentText()
        self.produto.localizacao = self.localizacao.currentText()
        self.produto.quantidade = self.quantidade.value()
        self.produto.estoque_minimo = self.estoque_minimo.value()
        self.produto.estoque_maximo = self.estoque_maximo.value()
        self.produto.preco_custo = self.preco_custo.value()
        self.produto.preco_venda = self.preco_venda.value()
        if self.editando:
            self.produto.ativo = self.ativo.isChecked()

        if self.editando:
            self.repository.atualizar(self.produto)
        else:
            self.repository.criar(self.produto)
