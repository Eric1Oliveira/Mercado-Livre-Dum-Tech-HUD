"""Janela de cadastro/edicao de produto.

A foto fica ao lado da descricao, e nao numa linha so dela: a janela ja esta
no limite da altura de um notebook de 768 px.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from ....ui.theme import Space
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....ui.widgets.foto import FotoProduto
from ....ui.widgets.form import FormDialog
from .. import imagem
from ..models import UNIDADES, EstoqueError, Produto, casas
from ..repository import EstoqueRepository


#: altura da foto = altura da descricao = dois botoes empilhados
ALTURA_FOTO = 78


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
        #: bytes prontos para gravar; so vai ao banco se `_imagem_mudou`
        self._imagem = repository.imagem(self.produto.id) if self.produto.id else None
        self._imagem_mudou = False
        super().__init__(
            "Editar produto" if self.editando else "Novo produto",
            "Preencha os dados do produto do seu estoque",
            parent,
            largura=720,
        )

        self.codigo = form.texto(self.produto.codigo, "Ex.: MOU-001")
        self.codigo_barras = form.texto(self.produto.codigo_barras, "Bipe ou digite")
        self.add_row("Código", form.linha(self.codigo, "Código de barras", self._barras_e_gerar()))

        self.nome = form.texto(self.produto.nome, "Ex.: Mouse USB sem fio")
        self.add_row("Nome", self.nome)

        self.categoria = form.combo_sugestao(
            self.produto.categoria, self.repository.categorias(), "Ex.: Periféricos"
        )
        self.unidade = form.escolha(
            [(f"{u.sigla} - {u.nome}", u.sigla) for u in UNIDADES.values()],
            self.produto.unidade,
        )
        self.unidade.currentIndexChanged.connect(self._unidade_mudou)
        self.add_row("Categoria", form.linha(self.categoria, "Unidade", self.unidade))

        self.fornecedor = form.combo_sugestao(
            self.produto.fornecedor, self.repository.fornecedores(), "De quem você compra"
        )
        self.localizacao = form.combo_sugestao(
            self.produto.localizacao, self.repository.localizacoes(), "Ex.: Prateleira A3"
        )
        self.add_row("Fornecedor", form.linha(self.fornecedor, "Local", self.localizacao))

        decimais = casas(self.produto.unidade)
        self.quantidade = form.quantidade(self.produto.quantidade, decimais)
        self.estoque_minimo = form.quantidade(self.produto.estoque_minimo, decimais)
        self.estoque_maximo = form.quantidade(self.produto.estoque_maximo, decimais)
        # uma linha so: a janela precisa caber num notebook de 768 px
        self.add_row(
            "Quantidade",
            form.linha(
                self.quantidade,
                "Estoque mínimo",
                self.estoque_minimo,
                "Estoque máximo",
                self.estoque_maximo,
            ),
        )

        self.preco_custo = form.dinheiro(self.produto.preco_custo)
        self.preco_venda = form.dinheiro(self.produto.preco_venda)
        self.add_row("Custo médio", form.linha(self.preco_custo, "Venda", self.preco_venda))

        self.descricao = form.area(
            self.produto.descricao, "Detalhes do produto (opcional)", ALTURA_FOTO
        )
        self.add_row("Descrição", self._descricao_e_foto())

        if self.editando:
            self.ativo = QCheckBox("Produto ativo (aparece nas listas)")
            self.ativo.setChecked(self.produto.ativo)
            self.add_row("", self.ativo)
            self.add_note(
                "Estoque mínimo é o ponto de recompra; estoque máximo é o nível que "
                "você quer ter: é dele que sai a sugestão de quanto comprar. O custo "
                "médio se atualiza sozinho a cada entrada com custo informado. Alterar "
                "a quantidade aqui gera um ajuste no histórico."
            )
        else:
            self.add_note(
                "Estoque mínimo é o ponto de recompra; estoque máximo é o nível que "
                "você quer ter: é dele que sai a sugestão de quanto comprar. Deixe em "
                "zero se não usar."
            )
        self.codigo.setFocus()

    # ------------------------------------------------------------------ campos
    def _barras_e_gerar(self) -> QWidget:
        """O campo do EAN com o botao que inventa um codigo interno para ele."""
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(Space.xs)
        linha.addWidget(self.codigo_barras, 1)
        self.botao_gerar = Button("Gerar", "tag", "ghost")
        self.botao_gerar.setToolTip(
            "Produto sem código de barras? Gera um código interno (começa com 2) "
            "que o leitor lê e que nunca bate com o de fábrica."
        )
        self.botao_gerar.clicked.connect(self._gerar_codigo)
        linha.addWidget(self.botao_gerar)
        self.codigo_barras.textChanged.connect(
            lambda texto: self.botao_gerar.setEnabled(not texto.strip())
        )
        self.botao_gerar.setEnabled(not self.codigo_barras.text().strip())
        return caixa

    def _gerar_codigo(self) -> None:
        self.codigo_barras.setText(self.repository.proximo_codigo_barras())
        self.nome.setFocus()

    def _descricao_e_foto(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(10)
        linha.addWidget(self.descricao, 1)

        self.foto = FotoProduto(ALTURA_FOTO, clicavel=True, parent=self)
        self.foto.setToolTip("Imagem do produto - aparece no balcão do Vendas")
        self.foto.clicado.connect(self._escolher_imagem)
        linha.addWidget(self.foto)

        botoes = QVBoxLayout()
        botoes.setSpacing(Space.xs + 2)
        self.botao_imagem = Button("Escolher imagem", "image")
        self.botao_imagem.clicked.connect(self._escolher_imagem)
        botoes.addWidget(self.botao_imagem)
        self.botao_tirar_imagem = Button("Remover", "trash", "ghost")
        self.botao_tirar_imagem.clicked.connect(self._remover_imagem)
        botoes.addWidget(self.botao_tirar_imagem)
        linha.addLayout(botoes)

        self._mostrar_imagem()
        return caixa

    def _mostrar_imagem(self) -> None:
        tem = self.foto.set_imagem(self._imagem)
        self.botao_imagem.setText(f"  {'Trocar imagem' if tem else 'Escolher imagem'}")
        self.botao_tirar_imagem.setEnabled(tem)

    def _escolher_imagem(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Imagem do produto", "", imagem.FILTRO
        )
        if not caminho:
            return
        try:
            self._imagem = imagem.preparar(caminho)
        except EstoqueError as erro:
            QMessageBox.warning(self, "Imagem do produto", str(erro))
            return
        self._imagem_mudou = True
        self._mostrar_imagem()

    def _remover_imagem(self) -> None:
        self._imagem = None
        self._imagem_mudou = True
        self._mostrar_imagem()

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
        if self._imagem_mudou:
            self.repository.salvar_imagem(self.produto.id, self._imagem)
