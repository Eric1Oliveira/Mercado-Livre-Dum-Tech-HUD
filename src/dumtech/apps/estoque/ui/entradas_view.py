"""Chegada de mercadoria: lanca a nota inteira de uma vez.

O fornecedor e o numero da nota valem para todas as linhas. Nada e gravado ate
"Confirmar entrada" - e entao tudo entra junto, numa transacao so.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ....ui import format as fmt
from ....ui import icons
from ....ui.theme import Space, palette_for
from ....ui.widgets import form
from ....ui.widgets.busca_catalogo import BuscaCatalogo
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, label, repolish
from ....ui.widgets.table import DIREITA, DataTable
from ....core.contas import APagar
from ..catalog import CatalogoEstoque
from ..models import EstoqueError, ItemEntrada, Produto, quantidade_texto
from ..repository import EstoqueRepository

COLUNAS = ["Código", "Produto", "Quantidade", "Custo unitário", "Total"]


class EntradasView(QWidget):
    """Monta a nota do fornecedor linha a linha e grava tudo junto."""

    data_changed = Signal()

    def __init__(self, repository: EstoqueRepository, parent: QWidget | None = None,
                 contas=None) -> None:
        super().__init__(parent)
        self.repository = repository
        #: ponte com o DumTech Financeiro; None quando a licenca nao o libera
        self.contas = contas
        self._linhas: list[tuple[Produto, ItemEntrada]] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Entradas", "title"))
        titulos.addWidget(
            label("Chegou mercadoria? Lance a nota inteira aqui", "subtitle")
        )
        raiz.addLayout(titulos)

        raiz.addWidget(self._cabecalho_nota())
        raiz.addWidget(self._linha_produto())

        self.tabela = DataTable(COLUNAS)
        self.tabela.itemSelectionChanged.connect(self._atualizar_acoes)
        raiz.addWidget(self.tabela, 1)
        raiz.addLayout(self._rodape())

        self.refresh()

    # -------------------------------------------------------------- cabecalho
    def _cabecalho_nota(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.setSpacing(Space.sm)
        card.body.addWidget(label("Dados da nota", "section"))

        linha = QHBoxLayout()
        linha.setSpacing(Space.md)
        self.fornecedor = form.sugestao(
            "", "Quem vendeu para você", self.repository.fornecedores()
        )
        linha.addWidget(form.campo("Fornecedor", self.fornecedor), 3)
        self.documento = form.texto("", "Ex.: NF 1234")
        linha.addWidget(form.campo("Documento", self.documento), 2)
        self.observacao = form.texto("", "Opcional")
        linha.addWidget(form.campo("Observação", self.observacao), 3)
        card.body.addLayout(linha)

        # Comprar mercadoria e criar uma divida. Com o Financeiro na casa, a
        # nota que entra aqui vira conta a pagar sem redigitacao - e quem nao
        # tem o Financeiro nem ve esta linha.
        if self.contas is not None:
            conta = QHBoxLayout()
            conta.setSpacing(Space.md)
            self.lancar_conta = QCheckBox("Lançar no Financeiro como conta a pagar")
            self.lancar_conta.setChecked(True)
            self.lancar_conta.toggled.connect(self._conta_mudou)
            conta.addWidget(self.lancar_conta)
            self.vencimento = form.data()
            self.campo_vencimento = form.campo("Vencimento", self.vencimento)
            conta.addWidget(self.campo_vencimento)
            conta.addStretch(1)
            card.body.addLayout(conta)
        return card

    def _conta_mudou(self, marcado: bool) -> None:
        self.campo_vencimento.setVisible(marcado)

    def _linha_produto(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.setSpacing(Space.sm)
        card.body.addWidget(label("Adicionar produto", "section"))

        linha = QHBoxLayout()
        linha.setSpacing(Space.md)

        self.bipe = QLineEdit()
        self.bipe.setPlaceholderText("Bipe o código de barras ou digite o código ou o nome...")
        self._acao_bipe = self.bipe.addAction(
            icons.icon("tag", palette_for(self).accent, 16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.bipe.returnPressed.connect(self._localizar)
        linha.addWidget(form.campo("Produto", self.bipe), 4)
        # os produtos cadastrados aparecem enquanto se digita; o Enter do leitor
        # de codigo de barras continua caindo no `_localizar`
        self.busca = BuscaCatalogo(self.bipe, CatalogoEstoque(self.repository.db))
        self.busca.escolhido.connect(self._escolhido)

        self.quantidade = QDoubleSpinBox()
        self.quantidade.setRange(0, 9_999_999)
        self.quantidade.setDecimals(0)
        self.quantidade.setValue(1)
        self.quantidade.setMinimumWidth(110)
        linha.addWidget(form.campo("Quantidade", self.quantidade), 1)

        self.custo = form.dinheiro(0.0)
        linha.addWidget(form.campo("Custo unitário", self.custo), 2)

        self.botao_adicionar = Button("Adicionar", "plus", "primary")
        self.botao_adicionar.clicked.connect(self._adicionar)
        self.botao_adicionar.setEnabled(False)
        linha.addWidget(form.campo(" ", self.botao_adicionar), 1)
        card.body.addLayout(linha)

        self.encontrado = label("Nenhum produto selecionado", "dim")
        card.body.addWidget(self.encontrado)
        self._produto: Produto | None = None
        return card

    def _rodape(self) -> QHBoxLayout:
        rodape = QHBoxLayout()
        rodape.setSpacing(Space.md)
        self.aviso = label("", "muted")
        rodape.addWidget(self.aviso, 1)

        self.total = label("", "section")
        rodape.addWidget(self.total)

        self.botao_remover = Button("Remover linha", "trash")
        self.botao_remover.clicked.connect(self._remover)
        rodape.addWidget(self.botao_remover)

        self.botao_limpar = Button("Limpar", "close", "ghost")
        self.botao_limpar.clicked.connect(self._limpar)
        rodape.addWidget(self.botao_limpar)

        self.botao_confirmar = Button("Confirmar entrada", "check", "success")
        self.botao_confirmar.setMinimumHeight(38)
        self.botao_confirmar.clicked.connect(self._confirmar)
        rodape.addWidget(self.botao_confirmar)
        return rodape

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        """Recarrega o que vem do banco sem perder a nota em digitacao."""
        completador = self.fornecedor.completer()
        if completador is not None:
            from PySide6.QtCore import QStringListModel

            completador.setModel(QStringListModel(self.repository.fornecedores()))
        self._preencher_tabela()

    def _preencher_tabela(self) -> None:
        linhas = []
        for produto, item in self._linhas:
            linhas.append([
                self.tabela.cell(produto.codigo),
                self.tabela.cell(produto.nome, bold=True),
                self.tabela.cell(
                    quantidade_texto(item.quantidade, produto.unidade, com_unidade=True),
                    DIREITA,
                ),
                self.tabela.cell(fmt.moeda(item.custo_unitario), DIREITA),
                self.tabela.cell(fmt.moeda(item.total), DIREITA, bold=True),
            ])
        self.tabela.fill(linhas, {0: 130, 2: 150, 3: 140, 4: 140})

        total = sum(item.total for _, item in self._linhas)
        quantidade_linhas = len(self._linhas)
        if quantidade_linhas:
            plural = "item" if quantidade_linhas == 1 else "itens"
            self.total.setText(f"{quantidade_linhas} {plural}   ·   {fmt.moeda(total)}")
        else:
            self.total.setText("")
        self._atualizar_acoes()

    def _atualizar_acoes(self) -> None:
        tem_linhas = bool(self._linhas)
        self.botao_confirmar.setEnabled(tem_linhas)
        self.botao_limpar.setEnabled(tem_linhas)
        self.botao_remover.setEnabled(0 <= self.tabela.currentRow() < len(self._linhas))
        self.botao_adicionar.setEnabled(self._produto is not None)

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------- acoes
    def _localizar(self) -> None:
        termo = self.bipe.text().strip()
        if not termo:
            return
        produto = self.repository.buscar(termo)
        if produto is None:
            self._selecionar(None)
            if self.repository.listar(busca=termo):
                # o nome bate com mais de um produto: a lista mostra quais
                self.busca.procurar(termo)
                self._dizer(f"Mais de um produto com '{termo}'. Escolha na lista.")
            else:
                self._dizer(f"Nenhum produto encontrado para '{termo}'.", "danger")
            return
        self._usar(produto)

    def _escolhido(self, item) -> None:
        """Produto escolhido na lista de sugestões."""
        produto = self.repository.obter(item.produto_id)
        if produto is not None:
            self._usar(produto)

    def _usar(self, produto: Produto) -> None:
        self.bipe.blockSignals(True)
        self.bipe.setText(produto.nome)
        self.bipe.blockSignals(False)
        self._selecionar(produto)
        self._dizer("")
        self.quantidade.setFocus()
        self.quantidade.selectAll()

    def _selecionar(self, produto: Produto | None) -> None:
        self._produto = produto
        if produto is None:
            self.encontrado.setText("Nenhum produto selecionado")
            self.encontrado.setProperty("role", "dim")
        else:
            saldo = quantidade_texto(produto.quantidade, produto.unidade, com_unidade=True)
            self.encontrado.setText(
                f"{produto.codigo}  -  {produto.nome}   (saldo atual: {saldo})"
            )
            self.quantidade.setDecimals(produto.casas)
            self.quantidade.setValue(1)
            self.custo.setValue(produto.preco_custo)
        repolish(self.encontrado)
        self._atualizar_acoes()

    def _adicionar(self) -> None:
        if self._produto is None:
            return
        if self.quantidade.value() <= 0:
            self._dizer("Informe uma quantidade maior que zero.", "danger")
            return

        # o mesmo produto duas vezes na nota soma, em vez de virar duas linhas
        for produto, item in self._linhas:
            if produto.id == self._produto.id:
                item.quantidade += self.quantidade.value()
                item.custo_unitario = self.custo.value()
                break
        else:
            self._linhas.append((
                self._produto,
                ItemEntrada(self._produto.id, self.quantidade.value(), self.custo.value()),
            ))

        self._dizer(f"'{self._produto.nome}' adicionado a nota.", "success")
        self.bipe.clear()
        self._selecionar(None)
        self._preencher_tabela()
        self.bipe.setFocus()

    def _remover(self) -> None:
        linha = self.tabela.currentRow()
        if 0 <= linha < len(self._linhas):
            produto, _ = self._linhas.pop(linha)
            self._dizer(f"'{produto.nome}' removido da nota.")
            self._preencher_tabela()

    def _limpar(self) -> None:
        self._linhas.clear()
        self._dizer("Nota descartada. Nada foi gravado.")
        self._preencher_tabela()

    def _confirmar(self) -> None:
        try:
            registros = self.repository.entrada_em_lote(
                [item for _, item in self._linhas],
                fornecedor=self.fornecedor.text(),
                documento=self.documento.text(),
                observacao=self.observacao.text(),
            )
        except EstoqueError as erro:
            self._dizer(str(erro), "danger")
            return

        total = sum(m.total for m in registros)
        plural = "produto" if len(registros) == 1 else "produtos"
        recado_conta = self._lancar_no_financeiro(total)
        self._linhas.clear()
        self.documento.clear()
        self.observacao.clear()
        self._preencher_tabela()
        self.refresh()
        self._dizer(
            f"Entrada confirmada: {len(registros)} {plural}, {fmt.moeda(total)}. "
            f"Os saldos e os custos médios foram atualizados.{recado_conta}",
            "success",
        )
        self.data_changed.emit()

    def _lancar_no_financeiro(self, total: float) -> str:
        """A nota de compra vira conta a pagar. Devolve o que dizer na tela.

        Nunca derruba a entrada: a mercadoria ja esta no estoque, e um
        tropeco do Financeiro e recado para conferir, nao motivo para desfazer
        o que ja entrou.
        """
        if self.contas is None or not self.lancar_conta.isChecked() or total <= 0:
            return ""
        documento = self.documento.text().strip()
        fornecedor = self.fornecedor.text().strip()
        if documento and self.contas.ja_lancado(documento):
            return f"  A nota {documento} já tinha conta no Financeiro - não lancei de novo."
        try:
            self.contas.lancar_pagamento(APagar(
                descricao=f"Compra {documento}".strip() if documento
                          else f"Compra de mercadoria{f' - {fornecedor}' if fornecedor else ''}",
                valor=total,
                vencimento=form.iso_da_data(self.vencimento),
                fornecedor=fornecedor,
                categoria="Fornecedores",
                documento=documento,
            ))
        except Exception as erro:  # noqa: BLE001 - a compra ja entrou, nao se desfaz
            return f"  Não consegui lançar a conta a pagar ({erro}) - lance na mão."
        return "  A conta a pagar foi lançada no Financeiro."

    def apply_theme(self, palette) -> None:
        self._acao_bipe.setIcon(icons.icon("tag", palette.accent, 16))
