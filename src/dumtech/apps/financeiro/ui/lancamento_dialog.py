"""Formulario de lancamento financeiro.

Parcelar na hora de cadastrar poupa o passo mais comum do dia a dia: a compra
que ja nasce em 3x nao precisa ser criada e depois dividida.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import QComboBox, QWidget

from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.form import FormDialog
from ..models import (
    DESPESA,
    FREQUENCIAS,
    PARCELAMENTO,
    RECEITA,
    RECORRENCIA,
    Lancamento,
)
from ..repository import FinanceiroRepository, dividir

#: como o lancamento vai ser gravado
UNICO = ""

REPETICAO_OPCOES = [
    ("Lançamento único", UNICO),
    ("Parcelado (divide o valor total)", PARCELAMENTO),
    ("Recorrente (mesmo valor a cada período)", RECORRENCIA),
]

#: despesa fixa e o que se paga todo mes, use ou nao; variavel acompanha o movimento
NATUREZA_OPCOES = [
    ("Variável (compras, comissões, frete)", False),
    ("Fixa (aluguel, internet, salários)", True),
]


class LancamentoDialog(FormDialog):
    def __init__(
        self,
        repository: FinanceiroRepository,
        lancamento: Lancamento | None = None,
        clientes: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self.repository = repository
        self.lancamento = lancamento or Lancamento()
        self.editando = lancamento is not None
        self.criados: list[Lancamento] = []
        super().__init__(
            "Editar lançamento" if self.editando else "Novo lançamento",
            "Contas a receber e contas a pagar",
            parent,
            largura=620,
        )

        self.tipo = form.escolha(
            [("Receita (entrada de dinheiro)", RECEITA), ("Despesa (saída)", DESPESA)],
            self.lancamento.tipo,
        )
        self.tipo.currentIndexChanged.connect(self._tipo_mudou)
        self.add_row("Tipo", self.tipo)

        self.natureza = form.escolha(NATUREZA_OPCOES, self.lancamento.fixa)
        self.add_row("Despesa", self.natureza)

        # o que ja foi lancado antes volta como sugestao: "Aluguel", "Energia"
        # e "Fornecedor X" sao digitados todo mes
        self.descricao = form.sugestao(
            self.lancamento.descricao, "Ex.: Venda do pedido 1042",
            self.repository.descricoes(),
        )
        self.add_row("Descrição", self.descricao)

        self.valor = form.dinheiro(self.lancamento.valor)
        self.valor.valueChanged.connect(self._atualizar_nota)
        self.vencimento = form.data(self.lancamento.vencimento)
        self.add_row("Valor", form.linha(self.valor, "Vencimento", self.vencimento))

        self.categoria = form.combo_sugestao(
            self.lancamento.categoria, self.repository.categorias(),
            "Ex.: Vendas, Aluguel, Fornecedor",
        )
        self.add_row("Categoria", self.categoria)

        self.cliente = form.sugestao(
            self.lancamento.cliente, "Cliente ou fornecedor", clientes or []
        )
        self.add_row("Cliente", self.cliente)

        self.conta = form.escolha(self._contas(), self.lancamento.conta_id)
        self.forma = form.combo_sugestao(
            self.lancamento.forma_pagamento, self.repository.formas(), "Ex.: Pix, boleto"
        )
        self.add_row("Conta", form.linha(self.conta, "Forma", self.forma))

        # parcelamento so existe no cadastro: mexer nisso depois e refazer a serie
        if not self.editando:
            self.repeticao = form.escolha(REPETICAO_OPCOES, UNICO)
            self.repeticao.currentIndexChanged.connect(self._modo_mudou)
            self.quantidade = form.inteiro(3, minimo=2, maximo=120)
            self.quantidade.valueChanged.connect(self._atualizar_nota)
            self.frequencia = QComboBox()
            for chave, rotulo in FREQUENCIAS:
                self.frequencia.addItem(rotulo, chave)
            self.add_row(
                "Recorrência",
                form.linha(self.repeticao, self.quantidade, self.frequencia),
            )
            # editar nao mexe na situacao: depois que o lancamento existe, quem
            # move dinheiro e a baixa - senao o saldo da conta e o historico
            # ficariam contando historias diferentes
            self.pago = form.escolha(
                [("Em aberto", False), ("Já foi pago/recebido", True)], False
            )
            self.add_row("Situação", self.pago)

        self.observacoes = form.area(self.lancamento.observacoes, "Anotações (opcional)", 60)
        self.add_row("Observações", self.observacoes)

        self.add_note("")
        self._nota = self.extras.itemAt(0).widget()
        if not self.editando:
            self._modo_mudou()
        else:
            self._nota.setVisible(False)
        self._tipo_mudou()
        self.descricao.setFocus()

    def _contas(self) -> list[tuple[str, int]]:
        contas = [(f"{c.nome}  ({c.tipo_label})", c.id)
                  for c in self.repository.listar_contas()]
        return [("Sem conta definida", 0)] + contas

    def _tipo_mudou(self) -> None:
        # receita nao e fixa nem variavel: a linha so aparece para despesa
        self.form.setRowVisible(self.natureza, self.tipo.currentData() == DESPESA)

    # -------------------------------------------------------------------- modo
    @property
    def modo(self) -> str:
        return self.repeticao.currentData() if not self.editando else UNICO

    def _modo_mudou(self) -> None:
        em_serie = self.modo != UNICO
        self.quantidade.setVisible(em_serie)
        self.frequencia.setVisible(em_serie)
        self.pago.setEnabled(not em_serie)
        if em_serie:
            self.pago.setCurrentIndex(0)
        # o que se repete todo periodo quase sempre e despesa fixa
        if self.modo == RECORRENCIA:
            self.natureza.setCurrentIndex(self.natureza.findData(True))
        self._nota.setVisible(em_serie)
        self._atualizar_nota()

    def _atualizar_nota(self) -> None:
        if self.editando or self.modo == UNICO:
            return
        quantidade = self.quantidade.value()
        if self.modo == PARCELAMENTO:
            valores = dividir(self.valor.value(), quantidade)
            extra = (f"  (a primeira, {fmt.moeda(valores[0])})"
                     if valores[0] != valores[-1] else "")
            self._nota.setText(
                f"{fmt.moeda(self.valor.value())} viram {quantidade} contas de "
                f"{fmt.moeda(valores[-1])}{extra}."
            )
        else:
            self._nota.setText(
                f"{quantidade} contas de {fmt.moeda(self.valor.value())}, somando "
                f"{fmt.moeda(self.valor.value() * quantidade)}."
            )

    # ------------------------------------------------------------------ gravar
    def salvar(self) -> None:
        self.lancamento.tipo = self.tipo.currentData()
        self.lancamento.descricao = self.descricao.text()
        self.lancamento.valor = self.valor.value()
        self.lancamento.vencimento = form.iso_da_data(self.vencimento)
        self.lancamento.categoria = self.categoria.currentText()
        self.lancamento.cliente = self.cliente.text()
        self.lancamento.conta_id = self.conta.currentData() or 0
        self.lancamento.forma_pagamento = self.forma.currentText()
        self.lancamento.observacoes = self.observacoes.toPlainText()
        self.lancamento.fixa = (self.lancamento.tipo == DESPESA
                                and bool(self.natureza.currentData()))

        if self.modo != UNICO:
            # a serie nasce em aberto: cada parcela e baixada quando for paga
            self.lancamento.pago_em = None
            gerar = (self.repository.parcelar if self.modo == PARCELAMENTO
                     else self.repository.repetir)
            self.criados = gerar(
                self.lancamento, self.quantidade.value(), self.frequencia.currentData()
            )
            return

        if self.editando:
            self.repository.atualizar(self.lancamento)
            return

        if self.pago.currentData():
            self.lancamento.pago_em = date.today().isoformat()
        self.repository.criar(self.lancamento)
