"""Lista de lancamentos do DumTech Financeiro."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.widgets.buttons import Button
from ....ui.widgets.crud_view import CrudView
from ....ui.widgets.mensagem import mandar
from ....ui.widgets.table import DIREITA
from ..models import DESPESA, PARCELAMENTO, RECEITA, RECORRENCIA, Lancamento
from ..repository import (
    SITUACAO_ABERTO,
    SITUACAO_PAGO,
    SITUACAO_PARCIAL,
    SITUACAO_VENCIDO,
    FinanceiroRepository,
)
from .dialogos import BaixaDialog, SerieDialog
from .lancamento_dialog import LancamentoDialog


class LancamentosView(CrudView):
    titulo = "Lancamentos"
    nome_registro = "lancamento"
    nome_plural = "lancamentos"
    rotulo_novo = "Novo lancamento"
    dica_pesquisa = "Pesquisar por descricao, categoria ou cliente..."
    # sem coluna "Tipo": o sinal e a cor do valor ja dizem se entra ou sai, e a
    # largura e curta demais para gastar com informacao repetida
    colunas = ["Vencimento", "Descricao", "Cliente", "Categoria", "Valor",
               "Em aberto", "Situacao"]
    larguras = {0: 200, 2: 150, 3: 120, 4: 130, 5: 115, 6: 105}

    def __init__(
        self,
        repository: FinanceiroRepository,
        clientes: list[str] | None = None,
        parent: QWidget | None = None,
        mensageiro=None,
        contatos=None,
        empresa=None,
    ) -> None:
        self.repository = repository
        self.clientes = clientes or []
        self.mensageiro = mensageiro
        self.contatos = contatos
        #: de onde sai a chave Pix do QR Code na hora de receber
        self.empresa = empresa
        super().__init__(parent)

    def build_filters(self, layout: QHBoxLayout) -> None:
        self.filtro_tipo = QComboBox()
        self.filtro_tipo.addItem("Receitas e despesas", "")
        self.filtro_tipo.addItem("Somente receitas", RECEITA)
        self.filtro_tipo.addItem("Somente despesas", DESPESA)
        self.filtro_tipo.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_tipo, 1)

        self.filtro_situacao = QComboBox()
        self.filtro_situacao.addItem("Todas as situacoes", "")
        self.filtro_situacao.addItem("Em aberto", SITUACAO_ABERTO)
        self.filtro_situacao.addItem("Vencidos", SITUACAO_VENCIDO)
        self.filtro_situacao.addItem("Recebidos em parte", SITUACAO_PARCIAL)
        self.filtro_situacao.addItem("Pagos/recebidos", SITUACAO_PAGO)
        self.filtro_situacao.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_situacao, 1)

    def build_actions(self, layout: QHBoxLayout) -> None:
        self.botao_baixar = Button("Receber / pagar", "check", "success")
        self.botao_baixar.clicked.connect(self._baixar)
        layout.insertWidget(1, self.botao_baixar)

        self.botao_whatsapp = Button("WhatsApp", "chat")
        self.botao_whatsapp.setToolTip("Lembra o cliente do vencimento")
        self.botao_whatsapp.clicked.connect(self._whatsapp)
        layout.insertWidget(2, self.botao_whatsapp)

        self.botao_quitar = Button("Quitar", "money")
        self.botao_quitar.clicked.connect(self._quitar)
        layout.insertWidget(3, self.botao_quitar)

        self.botao_parcelar = Button("Parcelar", "list")
        self.botao_parcelar.clicked.connect(lambda: self._serie(PARCELAMENTO))
        layout.insertWidget(4, self.botao_parcelar)

        self.botao_repetir = Button("Repetir", "refresh")
        self.botao_repetir.clicked.connect(lambda: self._serie(RECORRENCIA))
        layout.insertWidget(4, self.botao_repetir)

    # ------------------------------------------------------------------- dados
    def carregar(self) -> list[Lancamento]:
        return self.repository.listar(
            busca=self.busca.text(),
            tipo=self.filtro_tipo.currentData() or "",
            situacao=self.filtro_situacao.currentData() or "",
        )

    def montar_linha(self, lancamento: Lancamento) -> list:
        tom = "success" if lancamento.e_receita else "danger"
        sinal = "+" if lancamento.e_receita else "-"
        return [
            self.tabela.cell(
                self._vencimento(lancamento), data=lancamento.id,
                tone="danger" if lancamento.vencido else "",
            ),
            self.tabela.cell(lancamento.descricao_completa, bold=True),
            self.tabela.cell(lancamento.cliente or "-"),
            self.tabela.cell(lancamento.categoria or "-"),
            self.tabela.cell(f"{sinal} {fmt.moeda(lancamento.valor)}", DIREITA, tom, True),
            self.tabela.cell(
                fmt.moeda(lancamento.em_aberto) if not lancamento.pago else "-",
                DIREITA, "warning" if lancamento.parcial else "",
            ),
            self.tabela.cell(lancamento.situacao, tone=lancamento.tom),
        ]

    @staticmethod
    def _vencimento(lancamento: Lancamento) -> str:
        """A data sozinha nao diz se ja passou: o prazo diz."""
        if lancamento.pago:
            return fmt.data(lancamento.vencimento)
        return f"{fmt.data(lancamento.vencimento)}  ({fmt.prazo_texto(lancamento.vencimento)})"

    def _atualizar_acoes(self) -> None:
        super()._atualizar_acoes()
        lancamento = self.registro_selecionado()
        tem = lancamento is not None
        aberto = tem and not lancamento.pago
        self.botao_baixar.setEnabled(tem)
        # cobranca so faz sentido com cliente e com conta em aberto
        self.botao_whatsapp.setEnabled(bool(aberto and lancamento.cliente))
        self.botao_quitar.setEnabled(aberto)
        # so faz sentido parcelar/repetir o que ainda nao virou serie nem foi pago
        pode_serie = aberto and not lancamento.grupo
        self.botao_parcelar.setEnabled(pode_serie)
        self.botao_repetir.setEnabled(pode_serie)
        if tem and lancamento.pago:
            self.botao_baixar.setText("  Ver baixas")
        else:
            self.botao_baixar.setText("  Receber / pagar")

    # ------------------------------------------------------------------- acoes
    def _whatsapp(self) -> None:
        lancamento = self.registro_selecionado()
        if lancamento is None:
            return
        falta = (lancamento.vencimento or "")
        mandar(self, self.mensageiro, "cobranca", {
            "cliente": lancamento.cliente,
            "descricao": lancamento.descricao,
            "valor": fmt.moeda(lancamento.em_aberto or lancamento.valor),
            "vencimento": fmt.data(falta),
            "dias": fmt.prazo_texto(falta) if falta else "",
        }, contatos=self.contatos)

    def _baixar(self) -> None:
        lancamento = self.registro_selecionado()
        if lancamento is None:
            return
        dialogo = BaixaDialog(self.repository, lancamento, self,
                              empresa=self.empresa)
        dialogo.exec()
        # mesmo cancelando, o estorno dentro do dialogo pode ter mudado tudo
        self.refresh()
        self.data_changed.emit()

    def _quitar(self) -> None:
        lancamento = self.registro_selecionado()
        if lancamento is None:
            return
        self.repository.alternar_pagamento(lancamento.id)
        self.refresh()
        verbo = "recebido" if lancamento.e_receita else "pago"
        self.mostrar_aviso(
            f"'{lancamento.descricao}' {verbo}: {fmt.moeda(lancamento.em_aberto)}.",
            "success",
        )
        self.data_changed.emit()

    def _serie(self, modo: str) -> None:
        lancamento = self.registro_selecionado()
        if lancamento is None:
            return
        dialogo = SerieDialog(self.repository, lancamento, modo, self)
        if not dialogo.exec():
            return
        # o lancamento original vira a serie: ele nao pode ficar duplicado
        self.repository.excluir(lancamento.id)
        self.refresh()
        self.mostrar_aviso(
            f"'{lancamento.descricao}' virou {len(dialogo.criados)} lancamentos.",
            "success",
        )
        self.data_changed.emit()

    def abrir_dialogo(self, lancamento: Lancamento | None):
        return LancamentoDialog(self.repository, lancamento, self.clientes, self)

    def excluir(self, lancamento: Lancamento) -> None:
        self.repository.excluir(lancamento.id)

    def descricao(self, lancamento: Lancamento) -> str:
        return lancamento.descricao_completa
