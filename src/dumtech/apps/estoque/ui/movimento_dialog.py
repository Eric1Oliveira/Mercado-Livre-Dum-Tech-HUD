"""Baixa rapida: entrada ou saida de UM produto, sem sair da lista.

E a tela que a tecla E, a tecla S e o leitor de codigo de barras abrem. O
produto ja vem escolhido - so falta a quantidade, e Enter confirma.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.common import label
from ....ui.widgets.form import FormDialog
from ..models import TIPO_ENTRADA, TIPO_SAIDA, Movimentacao, Produto, quantidade_texto
from ..repository import EstoqueRepository


class MovimentoDialog(FormDialog):
    """Registra uma entrada ou uma saida do produto escolhido."""

    def __init__(
        self,
        repository: EstoqueRepository,
        produto: Produto,
        tipo: str = TIPO_SAIDA,
        parent: QWidget | None = None,
    ) -> None:
        self.repository = repository
        self.produto = produto
        self.tipo = tipo
        self.movimentacao: Movimentacao | None = None

        entrada = tipo == TIPO_ENTRADA
        super().__init__(
            "Entrada de estoque" if entrada else "Saída de estoque",
            f"{produto.codigo}  -  {produto.nome}",
            parent,
            largura=520,
        )
        self.botao_salvar.setText("  Registrar entrada" if entrada else "  Registrar saída")
        self.botao_salvar.set_icon_name("in" if entrada else "out")

        saldo = quantidade_texto(produto.quantidade, produto.unidade, com_unidade=True)
        self.add_row("Saldo atual", label(saldo, "strong"))

        # numa saida o campo ja nasce limitado ao que existe: o usuario nao
        # consegue nem digitar um numero que seria recusado depois
        maximo = 9_999_999.0 if entrada else max(produto.quantidade, 0.0)
        inicial = 1.0 if maximo >= 1 else maximo
        self.quantidade = form.quantidade(inicial, produto.casas, maximo)
        self.add_row(f"Quantidade ({produto.unidade})", self.quantidade)

        if entrada:
            self.custo = form.dinheiro(produto.preco_custo)
            self.add_row("Custo unitário", self.custo)
            self.fornecedor = form.sugestao(
                produto.fornecedor, "Quem vendeu para você", repository.fornecedores()
            )
            self.documento = form.texto("", "Ex.: NF 1234")
            self.add_row("Fornecedor", form.linha(self.fornecedor, "Documento", self.documento))
            self.add_note(
                "Informar o custo mantém o custo médio do produto atualizado. "
                f"Custo médio de hoje: {fmt.moeda(produto.preco_custo)}."
            )

        self.observacao = form.texto(
            "", "Compra do fornecedor" if entrada else "Venda no balcão"
        )
        self.add_row("Observação", self.observacao)

        self.quantidade.setFocus()
        self.quantidade.selectAll()

    def salvar(self) -> None:
        extras = {}
        if self.tipo == TIPO_ENTRADA:
            extras = {
                "custo_unitario": self.custo.value(),
                "fornecedor": self.fornecedor.text(),
                "documento": self.documento.text(),
            }
        self.movimentacao = self.repository.movimentar(
            self.produto.id,
            self.tipo,
            self.quantidade.value(),
            self.observacao.text(),
            **extras,
        )
