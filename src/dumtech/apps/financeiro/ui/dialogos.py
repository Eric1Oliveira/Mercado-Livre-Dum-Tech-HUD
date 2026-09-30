"""Baixa, conta e transferencia: as tres decisoes rapidas do Financeiro."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QWidget

from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....core.pagamentos import PIX
from ....ui.widgets.form import FormDialog
from ....ui.widgets.painel_pix import PainelPix
from ....ui.widgets.table import DIREITA, DataTable
from ..models import (
    CONTA_OPCOES,
    FREQUENCIAS,
    PARCELAMENTO,
    Conta,
    FinanceiroError,
    Lancamento,
)
from ..repository import FinanceiroRepository, dividir


def _contas_opcoes(repository: FinanceiroRepository) -> list[tuple[str, int]]:
    contas = [(f"{c.nome}  ({c.tipo_label})", c.id) for c in repository.listar_contas()]
    return [("Sem conta definida", 0)] + contas


class BaixaDialog(FormDialog):
    """Registra o dinheiro entrando ou saindo - inteiro ou em parte."""

    def __init__(
        self,
        repository: FinanceiroRepository,
        lancamento: Lancamento,
        parent: QWidget | None = None,
        empresa=None,
    ) -> None:
        self.repository = repository
        self.lancamento = lancamento
        #: chave Pix da loja: quem esta recebendo pode cobrar aqui mesmo
        self.empresa = empresa
        recebimento = lancamento.e_receita
        super().__init__(
            "Receber" if recebimento else "Pagar",
            lancamento.descricao_completa,
            parent,
            largura=560,
        )

        self.valor = form.dinheiro(lancamento.em_aberto)
        self.valor.valueChanged.connect(self._atualizar_nota)
        self.data = form.data()
        self.add_row("Valor", form.linha(self.valor, "Data", self.data))

        padrao = lancamento.conta_id or (
            self.repository.conta_padrao().id if self.repository.conta_padrao() else 0
        )
        self.conta = form.escolha(_contas_opcoes(repository), padrao)
        self.add_row("Conta", self.conta)

        self.forma = form.combo_sugestao(
            lancamento.forma_pagamento, self.repository.formas(),
            "Ex.: Pix, boleto, dinheiro",
        )
        self.add_row("Forma", self.forma)

        # Receber em Pix sem QR Code era mandar o cliente digitar a chave na
        # mao. So no recebimento: numa conta a pagar, quem cobra e o outro.
        self.painel_pix = PainelPix(self.empresa) if recebimento else None
        if self.painel_pix is not None:
            self.extras.addWidget(self.painel_pix)
            self.forma.currentTextChanged.connect(self._pix_mudou)
            self.valor.valueChanged.connect(self._pix_mudou)
            self._pix_mudou()

        self.observacao = form.texto("", "Opcional")
        self.add_row("Observacao", self.observacao)

        self.add_note("")
        self._nota = self.extras.itemAt(self.extras.count() - 1).widget()

        self.historico = DataTable(["Data", "Conta", "Valor"])
        self.historico.setMaximumHeight(120)
        self.historico.set_empty_message("Nenhuma baixa registrada ainda.")
        self.extras.addWidget(self.historico)

        self.botao_estornar = Button("Estornar a baixa selecionada", "back", "ghost")
        self.botao_estornar.clicked.connect(self._estornar)
        self.extras.addWidget(self.botao_estornar)
        self.historico.itemSelectionChanged.connect(self._atualizar_acoes)

        self._recarregar()
        self.valor.setFocus()
        self.valor.selectAll()

    # ------------------------------------------------------------------- tela
    def _recarregar(self) -> None:
        self.baixas = self.repository.baixas_de(self.lancamento.id)
        self.historico.fill(
            [
                [
                    self.historico.cell(fmt.data(b.data)),
                    self.historico.cell(b.conta_nome or "-"),
                    self.historico.cell(fmt.moeda(b.valor), DIREITA, bold=True),
                ]
                for b in self.baixas
            ],
            {0: 110, 2: 130},
        )
        self._atualizar_nota()
        self._atualizar_acoes()

    def _atualizar_nota(self) -> None:
        atual = self.repository.obter(self.lancamento.id) or self.lancamento
        restante = max(atual.em_aberto - self.valor.value(), 0)
        self._nota.setText(
            f"Valor do lancamento: {fmt.moeda(atual.valor)}      "
            f"Ja baixado: {fmt.moeda(atual.baixado)}      "
            f"Fica em aberto: {fmt.moeda(restante)}"
        )

    def _atualizar_acoes(self) -> None:
        self.botao_estornar.setEnabled(0 <= self.historico.currentRow() < len(self.baixas))

    def _estornar(self) -> None:
        linha = self.historico.currentRow()
        if not (0 <= linha < len(self.baixas)):
            return
        self.repository.estornar(self.baixas[linha].id)
        self._recarregar()
        atual = self.repository.obter(self.lancamento.id)
        if atual is not None:
            self.valor.setValue(atual.em_aberto)

    def _pix_mudou(self) -> None:
        """Mostra o QR Code quando a forma escolhida e Pix - e so entao."""
        if self.painel_pix is None:
            return
        em_pix = self.forma.currentText().strip().casefold() == PIX.casefold()
        self.painel_pix.setVisible(em_pix)
        if em_pix:
            self.painel_pix.atualizar(self.valor.value())

    def salvar(self) -> None:
        if self.valor.value() <= 0:
            raise FinanceiroError("Informe o valor da baixa.")
        self.repository.baixar(
            self.lancamento.id,
            self.valor.value(),
            data=form.iso_da_data(self.data),
            conta_id=self.conta.currentData() or 0,
            forma=self.forma.currentText(),
            observacao=self.observacao.text(),
        )


class ContaDialog(FormDialog):
    """Onde o dinheiro fica: o caixa da loja, a conta do banco, o cartao."""

    def __init__(
        self,
        repository: FinanceiroRepository,
        conta: Conta | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self.repository = repository
        self.conta = conta or Conta()
        self.editando = conta is not None
        super().__init__(
            "Editar conta" if self.editando else "Nova conta",
            "Caixa, banco ou cartao",
            parent,
            largura=480,
        )

        self.nome = form.texto(self.conta.nome, "Ex.: Caixa da loja, Banco do Brasil")
        self.add_row("Nome", self.nome)

        self.tipo = form.escolha(CONTA_OPCOES, self.conta.tipo)
        self.add_row("Tipo", self.tipo)

        self.saldo_inicial = form.dinheiro(self.conta.saldo_inicial)
        self.add_row("Saldo inicial", self.saldo_inicial)

        self.observacoes = form.texto(self.conta.observacoes, "Opcional")
        self.add_row("Observacoes", self.observacoes)

        self.add_note(
            "O saldo inicial e quanto havia nesta conta quando voce comecou a usar "
            "o sistema. Dali para frente o saldo anda sozinho, com as baixas."
        )
        self.nome.setFocus()

    def salvar(self) -> None:
        self.conta.nome = self.nome.text()
        self.conta.tipo = self.tipo.currentData()
        self.conta.saldo_inicial = self.saldo_inicial.value()
        self.conta.observacoes = self.observacoes.text()
        if self.editando:
            self.repository.atualizar_conta(self.conta)
        else:
            self.repository.criar_conta(self.conta)


class TransferenciaDialog(FormDialog):
    """Dinheiro mudando de conta - nao e receita nem despesa."""

    def __init__(self, repository: FinanceiroRepository, parent: QWidget | None = None) -> None:
        self.repository = repository
        super().__init__(
            "Transferencia entre contas",
            "Sacar do banco, levar para o caixa, guardar o troco",
            parent,
            largura=520,
        )
        contas = [(f"{c.nome}  ({fmt.moeda(c.saldo)})", c.id)
                  for c in repository.listar_contas()]
        if len(contas) < 2:
            raise FinanceiroError(
                "Cadastre pelo menos duas contas para poder transferir entre elas."
            )

        self.origem = form.escolha(contas, contas[0][1])
        self.destino = form.escolha(contas, contas[1][1])
        self.add_row("De", self.origem)
        self.add_row("Para", self.destino)

        self.valor = form.dinheiro(0.0)
        self.data = form.data()
        self.add_row("Valor", form.linha(self.valor, "Data", self.data))

        self.observacao = form.texto("", "Opcional")
        self.add_row("Observacao", self.observacao)

        self.add_note(
            "Transferencia nao entra no resultado do mes: o dinheiro so trocou "
            "de lugar."
        )
        self.valor.setFocus()

    def salvar(self) -> None:
        self.repository.transferir(
            self.origem.currentData(),
            self.destino.currentData(),
            self.valor.value(),
            data=form.iso_da_data(self.data),
            observacao=self.observacao.text(),
        )


class SerieDialog(FormDialog):
    """Transforma um lancamento em varios: parcelas ou repeticoes."""

    def __init__(
        self,
        repository: FinanceiroRepository,
        base: Lancamento,
        modo: str,
        parent: QWidget | None = None,
    ) -> None:
        self.repository = repository
        self.base = base
        self.modo = modo
        self.criados: list[Lancamento] = []
        parcelado = modo == PARCELAMENTO

        super().__init__(
            "Parcelar" if parcelado else "Repetir",
            base.descricao or "Novo lancamento",
            parent,
            largura=520,
        )

        self.quantidade = form.inteiro(3 if parcelado else 12, minimo=2, maximo=120)
        self.quantidade.valueChanged.connect(self._atualizar_nota)
        self.add_row("Quantidade" if parcelado else "Repeticoes", self.quantidade)

        self.frequencia = QComboBox()
        for chave, rotulo in FREQUENCIAS:
            self.frequencia.addItem(rotulo, chave)
        self.add_row("Intervalo", self.frequencia)

        self.add_note("")
        self._nota = self.extras.itemAt(0).widget()
        self._atualizar_nota()
        self.quantidade.setFocus()
        self.quantidade.selectAll()

    def _atualizar_nota(self) -> None:
        quantidade = self.quantidade.value()
        if self.modo == PARCELAMENTO:
            valores = dividir(self.base.valor, quantidade)
            self._nota.setText(
                f"{fmt.moeda(self.base.valor)} viram {quantidade} contas de "
                f"{fmt.moeda(valores[-1])}"
                + (f" (a primeira, {fmt.moeda(valores[0])})"
                   if valores[0] != valores[-1] else "")
                + "."
            )
        else:
            total = self.base.valor * quantidade
            self._nota.setText(
                f"{quantidade} contas de {fmt.moeda(self.base.valor)}, "
                f"somando {fmt.moeda(total)}."
            )

    def salvar(self) -> None:
        frequencia = self.frequencia.currentData()
        if self.modo == PARCELAMENTO:
            self.criados = self.repository.parcelar(
                self.base, self.quantidade.value(), frequencia
            )
        else:
            self.criados = self.repository.repetir(
                self.base, self.quantidade.value(), frequencia
            )
