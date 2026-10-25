"""Imprimir etiquetas com codigo de barras.

A lista de produtos fica a esquerda, a previa da folha (ou da etiqueta) a
direita, e o que muda num lado redesenha o outro na hora. Produto sem codigo
de barras ganha um codigo interno ao entrar na lista - etiqueta sem barras nao
serve para o balcao.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ....ui import format as fmt
from ....ui.theme import Space, apply_window_theme, palette_for
from ....ui.widgets import form
from ....ui.widgets.busca_catalogo import BuscaCatalogo
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, label, repolish, separator
from ....ui.widgets.table import DIREITA, DataTable
from .. import etiquetas
from ..catalog import CatalogoEstoque
from ..models import Produto
from ..repository import EstoqueRepository

COLUNAS = ["Produto", "Código de barras", "Preço", "Etiquetas"]
#: resolucao da previa: alta o bastante para as barras nao se fundirem
PREVIA_PX_MM = 6.0
#: largura da previa na tela
PREVIA_LARGURA = 330
#: teto por produto - ninguem quer 9.999 etiquetas por engano
MAXIMO = 999


class EtiquetasDialog(QDialog):
    def __init__(
        self,
        repository: EstoqueRepository,
        itens: list[tuple[Produto, int]] | None = None,
        parent: QWidget | None = None,
        prefs=None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.prefs = prefs
        #: (produto, quantidade) na ordem em que vao sair
        self._itens: list[list] = []
        self.setWindowTitle("Etiquetas")
        self.setModal(True)
        self.resize(1040, 680)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 26, 28, 24)
        raiz.setSpacing(16)
        titulos = QVBoxLayout()
        titulos.setSpacing(3)
        titulos.addWidget(label("Etiquetas com código de barras", "section"))
        titulos.addWidget(label("Escolha os produtos e quantas etiquetas de cada um", "muted"))
        raiz.addLayout(titulos)
        raiz.addWidget(separator())

        corpo = QHBoxLayout()
        corpo.setSpacing(Space.lg)
        corpo.addLayout(self._lado_lista(), 3)
        corpo.addWidget(self._lado_previa(), 2)
        raiz.addLayout(corpo, 1)
        raiz.addLayout(self._rodape())

        apply_window_theme(self, palette_for(parent))
        for produto, quantidade in itens or []:
            self.adicionar(produto, quantidade)
        self._redesenhar()
        self.campo_produto.setFocus()

    # ------------------------------------------------------------------ montar
    def _lado_lista(self) -> QVBoxLayout:
        coluna = QVBoxLayout()
        coluna.setSpacing(Space.sm)

        busca = QHBoxLayout()
        busca.setSpacing(Space.sm)
        self.campo_produto = QLineEdit()
        self.campo_produto.setPlaceholderText("Adicionar produto: digite o nome, o código ou bipe...")
        self.campo_produto.setClearButtonEnabled(True)
        self.campo_produto.returnPressed.connect(self._localizar)
        busca.addWidget(self.campo_produto, 1)
        self.busca = BuscaCatalogo(self.campo_produto, CatalogoEstoque(self.repository.db))
        self.busca.escolhido.connect(self._escolhido)
        todos = Button("Todos com estoque", "box", "ghost")
        todos.setToolTip("Uma etiqueta para cada unidade em estoque de todos os produtos ativos")
        todos.clicked.connect(self._todos_com_estoque)
        busca.addWidget(todos)
        coluna.addLayout(busca)

        self.tabela = DataTable(COLUNAS)
        self.tabela.set_empty_message("Adicione os produtos que vão ganhar etiqueta.")
        self.tabela.itemSelectionChanged.connect(self._atualizar_botoes)
        # so a coluna de quantidade aceita edicao: dois cliques ou digitar o numero
        self.tabela.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.tabela.itemChanged.connect(self._quantidade_editada)
        coluna.addWidget(self.tabela, 1)

        acoes = QHBoxLayout()
        self.resumo = label("", "dim")
        self.resumo.setToolTip("Para mudar a quantidade, clique duas vezes no número")
        acoes.addWidget(self.resumo, 1)
        self.botao_remover = Button("Remover", "trash", "ghost")
        self.botao_remover.clicked.connect(self._remover)
        acoes.addWidget(self.botao_remover)
        self.botao_limpar = Button("Limpar lista", "close", "ghost")
        self.botao_limpar.clicked.connect(self._limpar)
        acoes.addWidget(self.botao_limpar)
        coluna.addLayout(acoes)

        opcoes = QHBoxLayout()
        opcoes.setSpacing(Space.md)
        self.formato = QComboBox()
        for formato in etiquetas.FORMATOS:
            self.formato.addItem(formato.nome, formato.chave)
        guardado = self.prefs.get("etiqueta_formato") if self.prefs is not None else None
        indice = self.formato.findData(guardado)
        self.formato.setCurrentIndex(max(indice, 0))
        self.formato.currentIndexChanged.connect(self._formato_mudou)
        opcoes.addWidget(form.campo("Papel", self.formato), 3)

        self.inicio = QSpinBox()
        self.inicio.setRange(1, 1)
        self.inicio.setToolTip("Folha já usada? Comece na primeira etiqueta livre")
        self.inicio.valueChanged.connect(self._redesenhar)
        self.campo_inicio = form.campo("Começar na etiqueta", self.inicio)
        opcoes.addWidget(self.campo_inicio, 1)
        coluna.addLayout(opcoes)

        self.mostrar_preco = QCheckBox("Mostrar o preço de venda na etiqueta")
        self.mostrar_preco.setChecked(
            bool(self.prefs.get("etiqueta_preco", True)) if self.prefs is not None else True
        )
        self.mostrar_preco.toggled.connect(self._redesenhar)
        coluna.addWidget(self.mostrar_preco)
        self._formato_mudou()
        return coluna

    def _lado_previa(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.setSpacing(Space.sm)
        topo = QHBoxLayout()
        topo.addWidget(label("Prévia", "section"))
        topo.addStretch(1)
        self.paginas = label("", "dim")
        topo.addWidget(self.paginas)
        card.body.addLayout(topo)
        self.imagem = QLabel()
        self.imagem.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.imagem.setMinimumWidth(PREVIA_LARGURA)
        card.body.addWidget(self.imagem, 1)
        return card

    def _rodape(self) -> QHBoxLayout:
        rodape = QHBoxLayout()
        rodape.setSpacing(Space.sm + 2)
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        rodape.addWidget(self.aviso, 1)
        fechar = Button("Fechar")
        fechar.setMinimumHeight(38)
        fechar.clicked.connect(self.reject)
        rodape.addWidget(fechar)
        self.botao_pdf = Button("Salvar PDF", "file")
        self.botao_pdf.setMinimumHeight(38)
        self.botao_pdf.clicked.connect(self._salvar_pdf)
        rodape.addWidget(self.botao_pdf)
        self.botao_imprimir = Button("Imprimir", "check", "primary")
        self.botao_imprimir.setMinimumHeight(38)
        self.botao_imprimir.setDefault(True)
        self.botao_imprimir.clicked.connect(self._imprimir)
        rodape.addWidget(self.botao_imprimir)
        return rodape

    # ------------------------------------------------------------------- lista
    def adicionar(self, produto: Produto, quantidade: int = 1, preencher: bool = True) -> None:
        """Poe o produto na lista; sem codigo de barras, ganha um codigo interno."""
        if not produto.codigo_barras.strip():
            produto.codigo_barras = self.repository.atribuir_codigo_barras(produto.id)
            self._dizer(f"'{produto.nome}' ganhou o código interno {produto.codigo_barras}.",
                        "success")
        quantidade = max(1, min(int(quantidade), MAXIMO))
        for item in self._itens:
            if item[0].id == produto.id:
                item[1] = min(item[1] + quantidade, MAXIMO)
                break
        else:
            self._itens.append([produto, quantidade])
        if preencher:
            self._preencher()

    def _preencher(self) -> None:
        linhas = []
        for produto, quantidade in self._itens:
            fixas = [
                self.tabela.cell(produto.nome, bold=True),
                self.tabela.cell(produto.codigo_barras),
                self.tabela.cell(fmt.moeda(produto.preco_venda), DIREITA),
            ]
            for celula in fixas:
                celula.setFlags(celula.flags() & ~Qt.ItemFlag.ItemIsEditable)
            quantas = self.tabela.cell(str(quantidade), DIREITA, "accent", bold=True)
            quantas.setToolTip("Clique duas vezes para mudar")
            linhas.append(fixas + [quantas])
        self.tabela.blockSignals(True)
        self.tabela.fill(linhas, {1: 150, 2: 95, 3: 90})
        self.tabela.blockSignals(False)
        self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._redesenhar()

    def _quantidade_editada(self, celula) -> None:
        linha = celula.row()
        if celula.column() != 3 or not 0 <= linha < len(self._itens):
            return
        try:
            valor = int(celula.text().strip())
        except ValueError:
            valor = self._itens[linha][1]
        self._itens[linha][1] = max(1, min(valor, MAXIMO))
        self.tabela.blockSignals(True)
        celula.setText(str(self._itens[linha][1]))
        self.tabela.blockSignals(False)
        self._redesenhar()

    def _remover(self) -> None:
        linha = self.tabela.currentRow()
        if 0 <= linha < len(self._itens):
            del self._itens[linha]
            self._preencher()

    def _limpar(self) -> None:
        self._itens.clear()
        self._preencher()

    def _todos_com_estoque(self) -> None:
        produtos = [p for p in self.repository.listar() if p.quantidade >= 1]
        if not produtos:
            self._dizer("Nenhum produto ativo com estoque.", "warning")
            return
        for produto in produtos:
            self.adicionar(produto, int(produto.quantidade), preencher=False)
        self._preencher()
        self._dizer(f"{fmt.contagem(len(produtos), 'produto')} na lista, uma etiqueta "
                    "por unidade em estoque.", "success")

    def _localizar(self) -> None:
        termo = self.campo_produto.text().strip()
        if not termo:
            return
        produto = self.repository.buscar(termo)
        if produto is not None:
            self._usar(produto)
        elif self.repository.listar(busca=termo):
            self.busca.procurar(termo)
            self._dizer(f"Mais de um produto com '{termo}'. Escolha na lista.")
        else:
            self._dizer(f"Nenhum produto encontrado para '{termo}'.", "danger")

    def _escolhido(self, item) -> None:
        produto = self.repository.obter(item.produto_id)
        if produto is not None:
            self._usar(produto)

    def _usar(self, produto: Produto) -> None:
        self.adicionar(produto, 1)
        self.campo_produto.clear()
        self.campo_produto.setFocus()

    # ------------------------------------------------------------------ previa
    @property
    def formato_atual(self) -> etiquetas.Formato:
        return etiquetas.POR_CHAVE.get(self.formato.currentData(), etiquetas.PADRAO)

    def lista_etiquetas(self) -> list[etiquetas.Etiqueta]:
        """Uma Etiqueta por unidade pedida, na ordem da lista."""
        return [
            etiquetas.Etiqueta(produto.nome, produto.codigo_barras, produto.preco_venda)
            for produto, quantidade in self._itens
            for _ in range(quantidade)
        ]

    def _formato_mudou(self) -> None:
        formato = self.formato_atual
        self.inicio.setRange(1, formato.por_pagina)
        self.campo_inicio.setVisible(formato.folha)
        if self.prefs is not None:
            self.prefs.set("etiqueta_formato", formato.chave)
        self._redesenhar()

    def _redesenhar(self) -> None:
        if not hasattr(self, "imagem"):
            return  # ainda montando a tela
        if self.prefs is not None:
            self.prefs.set("etiqueta_preco", self.mostrar_preco.isChecked())
        formato = self.formato_atual
        lista = self.lista_etiquetas()
        grupos = etiquetas.paginas(lista, formato, self.inicio.value())
        primeira = grupos[0] if grupos else []
        imagem = etiquetas.previa(formato, primeira, PREVIA_PX_MM, self.mostrar_preco.isChecked())
        desenho = QPixmap.fromImage(imagem)
        if formato.folha or desenho.width() > PREVIA_LARGURA:
            desenho = desenho.scaledToWidth(PREVIA_LARGURA, Qt.TransformationMode.SmoothTransformation)
        self.imagem.setPixmap(desenho)

        total = len(lista)
        if formato.folha:
            self.paginas.setText(fmt.contagem(len(grupos), "folha") if grupos else "")
        else:
            self.paginas.setText("primeira etiqueta" if grupos else "")
        self.resumo.setText(f"{fmt.contagem(total, 'etiqueta')} no total" if total else "")
        self._atualizar_botoes()

    def _atualizar_botoes(self) -> None:
        tem = bool(self._itens)
        self.botao_imprimir.setEnabled(tem)
        self.botao_pdf.setEnabled(tem)
        self.botao_limpar.setEnabled(tem)
        self.botao_remover.setEnabled(0 <= self.tabela.currentRow() < len(self._itens))

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------ saidas
    def _imprimir(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        impressora = QPrinter(QPrinter.PrinterMode.HighResolution)
        etiquetas.preparar(impressora, self.formato_atual)
        dialogo = QPrintDialog(impressora, self)
        dialogo.setWindowTitle("Imprimir etiquetas")
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        # o dialogo do Windows pode trocar o papel: o tamanho da etiqueta manda
        etiquetas.preparar(impressora, self.formato_atual)
        self._enviar(impressora, "Etiquetas enviadas para a impressora.")

    def _salvar_pdf(self) -> None:
        pasta = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        escolhido, _ = QFileDialog.getSaveFileName(
            self, "Salvar etiquetas em PDF", str(Path(pasta or Path.home()) / "Etiquetas.pdf"),
            "Documento PDF (*.pdf)",
        )
        if escolhido:
            self.gravar_pdf(Path(escolhido))

    def gravar_pdf(self, destino: Path) -> bool:
        """Separado do dialogo de arquivo para poder ser testado."""
        from PySide6.QtPrintSupport import QPrinter

        impressora = QPrinter(QPrinter.PrinterMode.HighResolution)
        impressora.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        impressora.setOutputFileName(str(destino))
        etiquetas.preparar(impressora, self.formato_atual)
        return self._enviar(impressora, f"PDF gravado em {destino}.")

    def _enviar(self, impressora, recado: str) -> bool:
        try:
            etiquetas.imprimir(impressora, self.formato_atual, self.lista_etiquetas(),
                               self.inicio.value(), self.mostrar_preco.isChecked())
        except OSError as erro:
            self._dizer(str(erro), "danger")
            return False
        self._dizer(recado, "success")
        return True
