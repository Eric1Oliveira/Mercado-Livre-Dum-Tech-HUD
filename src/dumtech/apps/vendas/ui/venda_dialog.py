"""Lancamento manual de venda.

O caminho normal e o Balcao. Este formulario existe para o que o balcao nao
resolve: registrar uma venda de ontem, corrigir um cliente, lancar uma venda a
prazo combinada por telefone.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QWidget

from ....core.contas import MAXIMO_PARCELAS, vencimento_padrao
from ....core.pagamentos import PARCELADO, formas_do_balcao
from ....core.recorrencia import Recorrencia
from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.form import FormDialog
from ....ui.widgets.items_editor import ItemsEditor
from ....ui.widgets.recorrencias import CampoRepetir
from .. import financeiro, recorrencias
from ..models import CONCLUIDA, PARCELAS_PADRAO, PENDENTE, STATUS_OPCOES, ItemVenda, Venda
from ..repository import VendasRepository, pagamento_unico
from .pagamento_dialog import nota_parcelas

#: campos que o item carrega mas o editor nao mostra (ligacao com o Estoque)
EXTRAS = ("produto_id", "codigo", "unidade", "casas", "custo_unitario")


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
        #: parcela e conta no Financeiro: precisa dele, e so nasce com a venda
        self.parcelavel = contas is not None and not self.editando
        #: o Financeiro so ouve falar da venda nova ou da que mudou de situacao
        self._status_antes = self.venda.status if self.editando else None
        #: venda paga ja virou dinheiro e estoque: daqui so se corrige o cadastro
        self.so_dados = self.editando and self.venda.status != PENDENTE
        #: o que a tela mostra depois de fechar ("" = nada a dizer)
        self.recado = ""
        self.contratos = recorrencias.repositorio(repository.db)
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

        self.vendedor = form.escolha(
            [("Sem vendedor", "")]
            + [(v.nome, v.nome) for v in repository.vendedores(incluir_inativos=True)],
            self.venda.vendedor,
        )
        self.add_row("Vendedor", self.vendedor)
        self.form.setRowVisible(self.vendedor, self.vendedor.count() > 1)

        self.forma = QComboBox()
        self.forma.setEditable(True)
        self.forma.addItems(formas_do_balcao(parcelavel=self.parcelavel))
        self.forma.setCurrentText(self.venda.resumo_pagamento)
        self.forma.currentTextChanged.connect(self._forma_mudou)
        # cancelar e devolver tem botao proprio: e la que o motivo, o estoque e o
        # Financeiro andam juntos. A situacao que a venda ja tem continua na
        # lista, senao o campo cairia em outra e salvar a mudaria calado
        self.status = form.escolha(
            [(rotulo, chave) for rotulo, chave in STATUS_OPCOES
             if chave in (CONCLUIDA, PENDENTE) or chave == self.venda.status],
            self.venda.status,
        )
        self.status.currentIndexChanged.connect(self._forma_mudou)
        self.add_row("Pagamento", form.linha(self.forma, "Situação", self.status))

        self.vencimento = form.data(self.venda.vencimento or vencimento_padrao())
        self.add_row("Vencimento", self.vencimento)

        self.parcelas = form.inteiro(PARCELAS_PADRAO, minimo=2, maximo=MAXIMO_PARCELAS)
        self.parcelas.valueChanged.connect(self._atualizar_total)
        self.add_row("Parcelas", self.parcelas)
        self.form.setRowVisible(self.parcelas, False)

        # repetir nasce com a venda: depois, quem cuida e a lista de Recorrentes
        self.repeticao = CampoRepetir(
            "Repetir esta venda",
            f"Esta é a primeira. As próximas aparecem {recorrencias.ANTECEDENCIA} dias "
            "antes da data, como venda pendente.",
        )
        self.add_row("Repetir", self.repeticao)
        self.form.setRowVisible(self.repeticao, not self.editando)

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
        if self.so_dados:
            for campo in (self.numero, self.data, self.forma, self.status,
                          self.itens, self.desconto):
                campo.setEnabled(False)
            self.add_note(
                "Venda paga: o dinheiro e o estoque já andaram, então aqui só mudam "
                "o cliente e as observações. Para corrigir itens ou valores, use a "
                "Devolução ou cancele e lance de novo."
            )
        self._forma_mudou()
        self.cliente.setFocus()

    def _em_parcelado(self) -> bool:
        return (self.parcelavel
                and self.forma.currentText().strip().casefold() == PARCELADO.casefold())

    def _forma_mudou(self, _texto: str = "") -> None:
        parcelado = self._em_parcelado()
        self.form.setRowVisible(self.parcelas, parcelado)
        # a venda fecha aqui; quem cobra cada mes e o Financeiro
        self.status.setEnabled(not parcelado)
        if parcelado:
            self.status.setCurrentIndex(self.status.findData(CONCLUIDA))
            self.repeticao.marcar.setChecked(False)
        self.form.setRowVisible(self.repeticao, not (parcelado or self.editando))
        self.form.setRowVisible(self.vencimento, self._vira_conta())
        self._atualizar_total()

    def _vira_conta(self) -> bool:
        return not self.so_dados and (
            self._em_parcelado() or self.status.currentData() == PENDENTE
        )

    def _atualizar_total(self) -> None:
        subtotal = self.itens.total
        total = max(subtotal - self.desconto.value(), 0)
        texto = (
            f"Subtotal: {fmt.moeda(subtotal)}      Desconto: {fmt.moeda(self.desconto.value())}"
            f"      TOTAL DA VENDA: {fmt.moeda(total)}"
        )
        if self._em_parcelado():
            texto += f"\n{nota_parcelas(total, self.parcelas.value())}"
        self._nota_total.setText(texto)

    def _contrato(self) -> Recorrencia | None:
        """O contrato que o Repetir pede, ja conferido (None = venda de uma vez so).

        Conferir antes de gravar a venda: cliente faltando nao pode deixar uma
        venda sem contrato, e a venda recusada nao pode deixar um contrato solto.
        """
        if self.editando:
            return None
        self.venda.recorrencia = ""
        if not self.repeticao.ligado:
            return None
        contrato = recorrencias.contrato(
            self.contratos, self.venda,
            self.repeticao.frequencia.currentData(), self.repeticao.fim.iso(),
        )
        self.contratos.conferir(contrato)
        self.venda.recorrencia = contrato.numero
        return contrato

    def salvar(self) -> None:
        if self.so_dados:
            self.venda = self.repository.corrigir_dados(
                self.venda.id, self.cliente.text(), self.observacoes.toPlainText()
            )
            self.recado = financeiro.ajustar(self.contas, self.venda).strip()
            return

        parcelas = self.parcelas.value() if self._em_parcelado() else 0
        self.venda.numero = self.numero.text()
        self.venda.cliente = self.cliente.text()
        self.venda.vendedor = self.vendedor.currentData() or ""
        self.venda.data = form.iso_da_data(self.data)
        self.venda.forma_pagamento = PARCELADO if parcelas else self.forma.currentText()
        self.venda.status = self.status.currentData()
        self.venda.desconto = self.desconto.value()
        self.venda.observacoes = self.observacoes.toPlainText()
        self.venda.vencimento = form.iso_da_data(self.vencimento) if self._vira_conta() else ""
        self.venda.itens = [
            ItemVenda(
                descricao=item["descricao"],
                quantidade=item["quantidade"],
                valor_unitario=item["valor_unitario"],
                **{campo: item.get(campo) or padrao for campo, padrao in
                   (("produto_id", 0), ("codigo", ""), ("unidade", "UN"), ("casas", 0),
                    ("custo_unitario", 0.0))},
            )
            for item in self.itens.items()
        ]
        # lancamento manual tem uma forma so; venda paga entra nas contas do dia
        self.venda.pagamentos = (
            [pagamento_unico(self.venda.forma_pagamento, self.venda.total, parcelas=parcelas)]
            if self.venda.status == CONCLUIDA
            else []
        )
        contrato = self._contrato()
        # paga agora: baixa o estoque ja; pendente baixa quando o cliente pagar
        self.venda = (self.repository.alterar_pendente(self.venda) if self.editando
                      else self.repository.lancar(self.venda))
        recado = ""
        if contrato is not None:
            self.contratos.salvar(contrato)
            recado = f"  Repete {contrato.frequencia_label.lower()} ({contrato.numero})."
        if self.venda.status != self._status_antes:
            recado += financeiro.registrar(self.contas, self.venda)
        elif self.editando:
            recado += financeiro.ajustar(self.contas, self.venda)
        if self.venda.avisos:
            recado += f"  Confira o estoque: {'; '.join(self.venda.avisos)}"
        self.recado = recado.strip()
