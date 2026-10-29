"""Lancamento manual de venda.

O caminho normal e o Balcao. Este formulario existe para o que o balcao nao
resolve: registrar uma venda de ontem, corrigir um cliente, lancar uma venda a
prazo combinada por telefone.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QWidget

from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.form import FormDialog
from ....ui.widgets.items_editor import ItemsEditor
from .. import financeiro
from ..models import CONCLUIDA, FORMAS, STATUS_OPCOES, ItemVenda, Venda
from ..repository import VendasRepository, pagamento_unico

#: campos que o item carrega mas o editor nao mostra (ligacao com o Estoque)
EXTRAS = ("produto_id", "codigo", "unidade", "casas")


class VendaDialog(FormDialog):
    def __init__(
        self,
        repository: VendasRepository,
        venda: Venda | None = None,
        clientes: list[str] | None = None,
        parent: QWidget | None = None,
        contas=None,
    ) -> None:
        self.repository = repository
        #: ponte com o Financeiro; None quando a licenca nao o libera
        self.contas = contas
        self.venda = venda or Venda(numero=repository.proximo_numero())
        self.editando = venda is not None
        #: o Financeiro so ouve falar da venda nova ou da que mudou de situacao
        self._status_antes = self.venda.status if self.editando else None
        #: o que a tela mostra depois de fechar ("" = nada a dizer)
        self.recado = ""
        super().__init__(
            f"Venda {self.venda.numero}" if self.editando else "Lançar venda",
            "Itens vendidos, pagamento e total",
            parent,
            largura=680,
        )

        self.numero = form.texto(self.venda.numero, "Ex.: VEN-2026-0001")
        self.data = form.data(self.venda.data)
        self.add_row("Número", form.linha(self.numero, "Data", self.data))

        self.cliente = form.sugestao(self.venda.cliente, "Cliente (opcional)", clientes or [])
        self.add_row("Cliente", self.cliente)

        self.forma = QComboBox()
        self.forma.setEditable(True)
        self.forma.addItems(list(FORMAS))
        self.forma.setCurrentText(self.venda.resumo_pagamento)
        self.status = form.escolha(STATUS_OPCOES, self.venda.status)
        self.add_row("Pagamento", form.linha(self.forma, "Situação", self.status))

        # com o Estoque na licenca, o item sugere produto e baixa o saldo
        self.itens = ItemsEditor(
            catalogo=repository.catalogo if repository.tem_catalogo else None
        )
        # o editor nao mostra a ligacao com o Estoque, mas nao pode perde-la
        self.itens.set_items([
            {
                "descricao": item.descricao,
                "quantidade": item.quantidade,
                "valor_unitario": item.valor_unitario,
                **{campo: getattr(item, campo) for campo in EXTRAS},
            }
            for item in self.venda.itens
        ])
        self.itens.changed.connect(self._atualizar_total)
        self.add_row("Itens", self.itens)

        self.desconto = form.dinheiro(self.venda.desconto)
        self.desconto.valueChanged.connect(self._atualizar_total)
        self.add_row("Desconto", self.desconto)

        self.observacoes = form.area(self.venda.observacoes, "Anotações da venda", 60)
        self.add_row("Observações", self.observacoes)

        self.add_note("")
        self._nota_total = self.extras.itemAt(0).widget()
        self._atualizar_total()
        self.cliente.setFocus()

    def _atualizar_total(self) -> None:
        subtotal = self.itens.total
        total = max(subtotal - self.desconto.value(), 0)
        self._nota_total.setText(
            f"Subtotal: {fmt.moeda(subtotal)}      Desconto: {fmt.moeda(self.desconto.value())}"
            f"      TOTAL DA VENDA: {fmt.moeda(total)}"
        )

    def salvar(self) -> None:
        self.venda.numero = self.numero.text()
        self.venda.cliente = self.cliente.text()
        self.venda.data = form.iso_da_data(self.data)
        self.venda.forma_pagamento = self.forma.currentText()
        self.venda.status = self.status.currentData()
        self.venda.desconto = self.desconto.value()
        self.venda.observacoes = self.observacoes.toPlainText()
        self.venda.itens = [
            ItemVenda(
                descricao=item["descricao"],
                quantidade=item["quantidade"],
                valor_unitario=item["valor_unitario"],
                **{campo: item.get(campo) or padrao for campo, padrao in
                   (("produto_id", 0), ("codigo", ""), ("unidade", "UN"), ("casas", 0))},
            )
            for item in self.itens.items()
        ]
        # lancamento manual tem uma forma so; venda paga entra nas contas do dia
        self.venda.pagamentos = (
            [pagamento_unico(self.venda.forma_pagamento, self.venda.total)]
            if self.venda.status == CONCLUIDA
            else []
        )
        # paga agora: baixa o estoque ja; pendente baixa quando o cliente pagar
        self.venda = self.repository.lancar(self.venda)
        recado = ""
        if self.venda.status != self._status_antes:
            recado = financeiro.registrar(self.contas, self.venda)
        if self.venda.avisos:
            recado += f"  Confira o estoque: {'; '.join(self.venda.avisos)}"
        self.recado = recado.strip()
