"""Pedidos de compra: encomendar, acompanhar e dar entrada quando chegar."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QWidget

from ....core.contas import APagar, vencimento_padrao
from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....ui.widgets.crud_view import CrudView
from ....ui.widgets.form import FormDialog
from ....ui.widgets.table import DIREITA, DataTable
from ..catalog import CatalogoEstoque
from ..models import (
    PEDIDO_ABERTO,
    PEDIDO_LABEL,
    EstoqueError,
    ItemPedidoCompra,
    PedidoCompra,
    quantidade_texto,
)
from ..repository import EstoqueRepository


class PedidoDialog(FormDialog):
    def __init__(self, repository: EstoqueRepository, pedido: PedidoCompra | None,
                 parent: QWidget | None = None) -> None:
        self.repository = repository
        self.pedido = pedido or PedidoCompra(numero=repository.proximo_pedido())
        self.itens = list(self.pedido.itens)
        super().__init__(f"Pedido {self.pedido.numero}", "O que foi encomendado e de quem",
                         parent, largura=660)

        nomes = [f.nome for f in repository.listar_fornecedores()]
        self.fornecedor = form.sugestao(self.pedido.fornecedor, "Fornecedor", nomes)
        self.previsao = form.data_opcional(self.pedido.previsao)
        self.add_row("Fornecedor", form.linha(self.fornecedor, "Previsão", self.previsao))

        self.produto = QLineEdit()
        self.produto.setPlaceholderText("Código, código de barras ou nome do produto")
        self.quantidade = form.quantidade(1.0, casas=3)
        self.custo = form.dinheiro(0.0)
        adicionar = Button("Adicionar", "plus")
        adicionar.clicked.connect(self._adicionar)
        self.add_row("Produto", form.linha(self.produto, self.quantidade, self.custo, adicionar))

        self.tabela = DataTable(["Produto", "Quantidade", "Custo", "Total"])
        self.tabela.setMinimumHeight(170)
        self.add_row("Itens", self.tabela)
        self.observacoes = form.area(self.pedido.observacoes, "Combinados com o fornecedor", 50)
        self.add_row("Observações", self.observacoes)
        self.add_note("")
        self._nota = self.extras.itemAt(0).widget()
        self._desenhar()

    def _adicionar(self) -> None:
        achado = CatalogoEstoque(self.repository.db).buscar(self.produto.text())
        if achado is None or self.quantidade.value() <= 0:
            self._nota.setText("Produto não encontrado.")
            return
        self.itens.append(ItemPedidoCompra(
            achado.produto_id, self.quantidade.value(),
            self.custo.value() or self.repository.obter(achado.produto_id).preco_custo,
            achado.nome, achado.unidade,
        ))
        self.produto.clear()
        self._desenhar()

    def _desenhar(self) -> None:
        self.tabela.fill(
            [[self.tabela.cell(i.produto_nome, bold=True),
              self.tabela.cell(quantidade_texto(i.quantidade, i.unidade), DIREITA),
              self.tabela.cell(fmt.moeda(i.custo_unitario), DIREITA),
              self.tabela.cell(fmt.moeda(i.total), DIREITA)] for i in self.itens],
            {1: 110, 2: 110, 3: 110},
        )
        self._nota.setText(f"Total do pedido: {fmt.moeda(sum(i.total for i in self.itens))}")

    def salvar(self) -> None:
        self.pedido.fornecedor = self.fornecedor.text()
        self.pedido.previsao = self.previsao.iso()
        self.pedido.observacoes = self.observacoes.toPlainText()
        self.pedido.itens = self.itens
        self.repository.salvar_pedido(self.pedido)


class PedidosView(CrudView):
    titulo = "Pedidos de compra"
    limite_lista = 500
    exportavel = True
    nome_registro = "pedido"
    nome_plural = "pedidos"
    rotulo_novo = "Novo pedido"
    dica_pesquisa = "Pesquisar por número ou fornecedor..."
    colunas = ["Número", "Data", "Fornecedor", "Previsão", "Itens", "Total", "Situação"]
    larguras = {0: 140, 1: 110, 3: 110, 4: 70, 5: 130, 6: 110}

    def __init__(self, repository: EstoqueRepository, parent: QWidget | None = None,
                 contas=None) -> None:
        self.repository = repository
        #: o Financeiro: o pedido recebido vira conta a pagar
        self.contas = contas
        super().__init__(parent)

    def build_filters(self, layout: QHBoxLayout) -> None:
        self.filtro_status = QComboBox()
        self.filtro_status.addItem("Todas as situações", "")
        for chave, rotulo in PEDIDO_LABEL.items():
            self.filtro_status.addItem(rotulo, chave)
        self.filtro_status.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_status, 1)

    def build_actions(self, layout: QHBoxLayout) -> None:
        self.botao_reposicao = Button("Pedir o que falta", "refresh")
        self.botao_reposicao.setToolTip("Monta um pedido com o que está no estoque mínimo")
        self.botao_reposicao.clicked.connect(self._reposicao)
        layout.addWidget(self.botao_reposicao)

        self.botao_receber = Button("Receber", "in", "success")
        self.botao_receber.setToolTip("A mercadoria chegou: dá entrada no estoque")
        self.botao_receber.clicked.connect(self._receber)
        layout.addWidget(self.botao_receber)

        self.botao_cancelar = Button("Cancelar pedido", "close", "danger")
        self.botao_cancelar.clicked.connect(self._cancelar)
        layout.addWidget(self.botao_cancelar)

    def carregar(self, limite: int = 500) -> list[PedidoCompra]:
        return self.repository.listar_pedidos(
            self.busca.text(), self.filtro_status.currentData() or "", limite
        )

    def montar_linha(self, pedido: PedidoCompra) -> list:
        return [
            self.tabela.cell(pedido.numero, bold=True, data=pedido.id),
            self.tabela.cell(fmt.data(pedido.data)),
            self.tabela.cell(pedido.fornecedor or "-"),
            self.tabela.cell(fmt.data(pedido.previsao) if pedido.previsao else "-"),
            self.tabela.cell(fmt.numero(len(pedido.itens)), DIREITA),
            self.tabela.cell(fmt.moeda(pedido.total), DIREITA, "accent", bold=True),
            self.tabela.cell(pedido.status_label, tone=pedido.status_tom),
        ]

    def _atualizar_acoes(self) -> None:
        super()._atualizar_acoes()
        pedido = self.registro_selecionado()
        aberto = pedido is not None and pedido.status == PEDIDO_ABERTO
        self.botao_editar.setEnabled(aberto)
        self.botao_receber.setEnabled(aberto)
        self.botao_cancelar.setEnabled(aberto)

    def abrir_dialogo(self, pedido: PedidoCompra | None):
        return PedidoDialog(self.repository, pedido, self)

    def excluir(self, pedido: PedidoCompra) -> None:
        self.repository.excluir_pedido(pedido.id)

    def descricao(self, pedido: PedidoCompra) -> str:
        return pedido.numero

    def _reposicao(self) -> None:
        try:
            pedido = self.repository.gerar_pedido_de_reposicao()
        except EstoqueError as erro:
            self.mostrar_aviso(str(erro), "warning")
            return
        self.refresh()
        self.mostrar_aviso(f"Pedido {pedido.numero} criado com {len(pedido.itens)} produto(s).",
                           "success")

    def _receber(self) -> None:
        pedido = self.registro_selecionado()
        if pedido is None:
            return
        try:
            recebido = self.repository.receber_pedido(pedido.id)
        except EstoqueError as erro:
            self.mostrar_aviso(str(erro), "danger")
            return
        recado = self._lancar_conta(recebido)
        self.refresh()
        self.mostrar_aviso(f"Pedido {recebido.numero} recebido: saldos atualizados.{recado}",
                           "success")
        self.data_changed.emit()

    def _lancar_conta(self, pedido: PedidoCompra) -> str:
        """O que chegou vai ser pago: a mercadoria entrou, a divida tambem."""
        if self.contas is None or pedido.total <= 0 or self.contas.ja_lancado(pedido.numero):
            return ""
        try:
            self.contas.lancar_pagamento(APagar(
                descricao=f"Compra {pedido.numero}", valor=pedido.total,
                vencimento=vencimento_padrao(), fornecedor=pedido.fornecedor,
                categoria="Fornecedores", documento=pedido.numero,
            ))
        except Exception as erro:  # noqa: BLE001 - a mercadoria ja entrou
            return f"  Não consegui lançar a conta a pagar ({erro})."
        return "  Conta a pagar lançada no Financeiro."

    def _cancelar(self) -> None:
        pedido = self.registro_selecionado()
        if pedido is None:
            return
        self.repository.cancelar_pedido(pedido.id)
        self.refresh()
        self.mostrar_aviso(f"Pedido {pedido.numero} cancelado.", "success")
