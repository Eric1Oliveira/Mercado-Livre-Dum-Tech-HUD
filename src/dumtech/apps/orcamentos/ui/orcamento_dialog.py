"""A proposta: itens, condicoes e validade."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QWidget

from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.form import FormDialog
from ..models import (
    CONDICOES,
    MOTIVOS_OPCOES,
    STATUS_OPCOES,
    VALIDADE_PADRAO,
    Orcamento,
    OrcamentoError,
)
from ..repository import OrcamentosRepository
from .itens_editor import ItensEditor

PRAZOS = (
    "Imediato",
    "3 dias úteis",
    "5 dias úteis",
    "10 dias úteis",
    "15 dias úteis",
    "30 dias",
    "A combinar",
)


class OrcamentoDialog(FormDialog):
    def __init__(
        self,
        repository: OrcamentosRepository,
        orcamento: Orcamento | None = None,
        clientes: list[str] | None = None,
        parent: QWidget | None = None,
        catalogo=None,
    ) -> None:
        self.repository = repository
        self.orcamento = orcamento or Orcamento(numero=repository.proximo_numero())
        self.editando = orcamento is not None
        super().__init__(
            f"Orçamento {self.orcamento.numero}" if self.editando else "Nova proposta",
            "Itens, condições e validade da proposta",
            parent,
            largura=880,
            rolagem=True,
        )

        self.numero = form.texto(self.orcamento.numero, "Ex.: ORC-2026-0001")
        self.data = form.data(self.orcamento.data)
        self.add_row("Número", form.linha(self.numero, "Data", self.data))

        self.cliente = form.sugestao(
            self.orcamento.cliente, "Para quem é a proposta", clientes or []
        )
        self.add_row("Cliente", self.cliente)

        self.itens = ItensEditor(catalogo=catalogo)
        self.itens.set_items(self.orcamento.itens)
        self.itens.changed.connect(self._atualizar_total)
        self.add_row("Itens", self.itens)

        self.desconto = form.dinheiro(self.orcamento.desconto)
        self.desconto.valueChanged.connect(self._atualizar_total)
        self.add_row("Desconto na proposta", self.desconto)

        self.condicao = QComboBox()
        self.condicao.setEditable(True)
        self.condicao.addItems([""] + self._condicoes())
        self.condicao.setCurrentText(self.orcamento.condicao_pagamento)
        self.condicao.lineEdit().setPlaceholderText("Ex.: 50% na entrada, 50% na entrega")
        self.add_row("Condição de pagamento", self.condicao)

        self.prazo = QComboBox()
        self.prazo.setEditable(True)
        self.prazo.addItems([""] + list(PRAZOS))
        self.prazo.setCurrentText(self.orcamento.prazo_entrega)
        self.prazo.lineEdit().setPlaceholderText("Ex.: 10 dias úteis")
        self.validade = form.inteiro(
            self.orcamento.validade_dias or VALIDADE_PADRAO, minimo=0, maximo=365
        )
        self.add_row("Prazo de entrega", form.linha(self.prazo, "Validade (dias)",
                                                    self.validade))

        self.status = form.escolha(STATUS_OPCOES, self.orcamento.status)
        self.status.setEnabled(not self.editando)
        self.add_row("Etapa", self.status)

        self.observacoes = form.area(
            self.orcamento.observacoes, "O que mais o cliente precisa saber", 70
        )
        self.add_row("Observações", self.observacoes)

        self.add_note("")
        self._nota = self.extras.itemAt(self.extras.count() - 1).widget()
        self._atualizar_total()
        self.cliente.setFocus()

    def _condicoes(self) -> list[str]:
        usadas = self.repository.condicoes_usadas()
        return list(CONDICOES) + [c for c in usadas if c not in CONDICOES]

    def _atualizar_total(self) -> None:
        subtotal = self.itens.subtotal
        total = max(subtotal - self.desconto.value(), 0)
        partes = [f"Itens: {fmt.moeda(subtotal)}"]
        if self.itens.descontos:
            partes.append(f"já com {fmt.moeda(self.itens.descontos)} de desconto nas linhas")
        if self.desconto.value():
            partes.append(f"desconto na proposta: {fmt.moeda(self.desconto.value())}")
        partes.append(f"TOTAL: {fmt.moeda(total)}")
        self._nota.setText("      ".join(partes))

    def salvar(self) -> None:
        self.orcamento.numero = self.numero.text()
        self.orcamento.data = form.iso_da_data(self.data)
        self.orcamento.cliente = self.cliente.text()
        self.orcamento.itens = self.itens.items()
        self.orcamento.desconto = self.desconto.value()
        self.orcamento.condicao_pagamento = self.condicao.currentText()
        self.orcamento.prazo_entrega = self.prazo.currentText()
        self.orcamento.validade_dias = self.validade.value()
        self.orcamento.observacoes = self.observacoes.toPlainText()
        if not self.editando:
            self.orcamento.status = self.status.currentData()
        self.repository.salvar(self.orcamento)


class RecusaDialog(FormDialog):
    """Perder sem motivo nao vira licao nenhuma."""

    def __init__(
        self,
        repository: OrcamentosRepository,
        orcamento: Orcamento,
        parent: QWidget | None = None,
    ) -> None:
        self.repository = repository
        self.orcamento = orcamento
        super().__init__(
            f"Orçamento {orcamento.numero} não aprovado",
            f"{orcamento.cliente}  ·  {fmt.moeda(orcamento.total)}",
            parent,
            largura=500,
        )
        self.motivo = form.escolha(MOTIVOS_OPCOES, MOTIVOS_OPCOES[0][1])
        self.add_row("Motivo", self.motivo)

        self.observacao = form.texto("", "Opcional")
        self.add_row("Observação", self.observacao)

        self.add_note(
            "O motivo entra no funil: é assim que dá para saber se você perde "
            "por preço, por prazo ou por demora."
        )
        self.motivo.setFocus()

    def salvar(self) -> None:
        escolha = self.motivo.currentData()
        if not escolha:
            raise OrcamentoError("Escolha por que o orçamento não foi aprovado.")
        atualizado = self.repository.recusar(self.orcamento.id, escolha)
        if self.observacao.text().strip():
            atualizado.observacoes = (
                f"{atualizado.observacoes}\n{self.observacao.text().strip()}".strip()
            )
            self.repository.salvar(atualizado)
