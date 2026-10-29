"""Historico de vendas: consultar, imprimir, cancelar, devolver e receber.

O balcao faz a venda; esta tela cuida do que vem depois dela.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.widgets.buttons import Button
from ....ui.widgets.crud_view import CrudView
from ....ui.widgets.comprovante import ComprovanteDialog
from ....ui.widgets.mensagem import mandar
from ....ui.widgets.table import DIREITA
from .. import financeiro
from ..models import PENDENTE, STATUS_LABEL, Venda
from ..recibo import comprovante
from ..repository import VendasRepository
from .caixa_dialogs import MotivoDialog
from .devolucao_dialog import DevolucaoDialog
from .pagamento_dialog import PagamentoDialog
from .venda_dialog import VendaDialog

#: (rotulo, dias contados para tras); 0 = hoje, -1 = tudo
PERIODOS = (("Hoje", 0), ("Últimos 7 dias", 7), ("Últimos 30 dias", 30), ("Tudo", -1))


class VendasView(CrudView):
    titulo = "Vendas"
    nome_registro = "venda"
    nome_plural = "vendas"
    genero = "f"
    rotulo_novo = "Lançar venda"
    dica_pesquisa = "Pesquisar por número, cliente ou forma de pagamento..."
    colunas = ["Número", "Data", "Cliente", "Itens", "Pagamento", "Total", "Situação"]
    larguras = {0: 150, 1: 110, 3: 80, 4: 170, 5: 140, 6: 190}

    def __init__(
        self,
        repository: VendasRepository,
        clientes: list[str] | None = None,
        parent: QWidget | None = None,
        empresa=None,
        mensageiro=None,
        contatos=None,
        contas=None,
    ) -> None:
        self.repository = repository
        self.clientes = clientes or []
        self.empresa = empresa
        self.mensageiro = mensageiro
        self.contatos = contatos
        self.contas = contas
        super().__init__(parent)

    def build_filters(self, layout: QHBoxLayout) -> None:
        self.filtro_status = QComboBox()
        self.filtro_status.addItem("Todas as situações", "")
        for chave, rotulo in STATUS_LABEL.items():
            self.filtro_status.addItem(rotulo, chave)
        self.filtro_status.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_status, 1)

        self.filtro_periodo = QComboBox()
        for rotulo, dias in PERIODOS:
            self.filtro_periodo.addItem(rotulo, dias)
        self.filtro_periodo.setCurrentIndex(2)  # 30 dias: o mes de trabalho
        self.filtro_periodo.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_periodo, 1)

    def build_actions(self, layout: QHBoxLayout) -> None:
        self.botao_comprovante = Button("Comprovante", "file")
        self.botao_comprovante.clicked.connect(self._comprovante)
        layout.insertWidget(1, self.botao_comprovante)

        self.botao_whatsapp = Button("WhatsApp", "chat")
        self.botao_whatsapp.setToolTip("Agradece a compra e manda o comprovante")
        self.botao_whatsapp.clicked.connect(self._whatsapp)
        layout.insertWidget(2, self.botao_whatsapp)

        self.botao_receber = Button("Receber", "money", "success")
        self.botao_receber.clicked.connect(self._receber)
        layout.insertWidget(3, self.botao_receber)

        self.botao_devolver = Button("Devolução", "in")
        self.botao_devolver.clicked.connect(self._devolver)
        layout.insertWidget(4, self.botao_devolver)

        self.botao_cancelar = Button("Cancelar venda", "close", "danger")
        self.botao_cancelar.clicked.connect(self._cancelar)
        layout.insertWidget(4, self.botao_cancelar)

    # ------------------------------------------------------------------- dados
    def carregar(self) -> list[Venda]:
        dias = self.filtro_periodo.currentData()
        inicio = "" if dias < 0 else (date.today() - timedelta(days=dias)).isoformat()
        return self.repository.listar(
            busca=self.busca.text(),
            status=self.filtro_status.currentData() or "",
            inicio=inicio,
        )

    def montar_linha(self, venda: Venda) -> list:
        return [
            self.tabela.cell(venda.numero, bold=True, data=venda.id),
            self.tabela.cell(fmt.data(venda.data)),
            self.tabela.cell(venda.cliente or "Consumidor"),
            self.tabela.cell(fmt.numero(venda.quantidade_itens), DIREITA),
            self.tabela.cell(venda.forma_pagamento or "-"),
            self.tabela.cell(fmt.moeda(venda.total), DIREITA, "accent", bold=True),
            self.tabela.cell(self._situacao(venda), tone=venda.status_tom),
        ]

    @staticmethod
    def _situacao(venda: Venda) -> str:
        """Uma devolucao parcial nao muda o status, mas precisa aparecer."""
        if venda.devolvido and venda.status not in ("cancelada", "devolvida"):
            return f"{venda.status_label} · devolvido {fmt.moeda(venda.devolvido)}"
        return venda.status_label

    def _atualizar_acoes(self) -> None:
        super()._atualizar_acoes()
        venda = self.registro_selecionado()
        tem = venda is not None
        self.botao_comprovante.setEnabled(tem)
        self.botao_whatsapp.setEnabled(tem and bool(venda.cliente))
        self.botao_receber.setEnabled(tem and venda.status == PENDENTE)
        self.botao_devolver.setEnabled(
            tem and venda.conta and any(item.restante > 0 for item in venda.itens)
        )
        self.botao_cancelar.setEnabled(tem and venda.conta)
        # editar so faz sentido enquanto nada aconteceu depois da venda
        self.botao_editar.setEnabled(tem and venda.conta and not venda.devolvido)

    # ------------------------------------------------------------------- acoes
    def abrir_dialogo(self, venda: Venda | None):
        return VendaDialog(self.repository, venda, self.clientes, self, contas=self.contas)

    def novo(self) -> None:
        self._lancar(None)

    def editar(self) -> None:
        venda = self.registro_selecionado()
        if venda is not None:
            self._lancar(venda)

    def _lancar(self, venda: Venda | None) -> None:
        """Como o da casa, mas conta o que aconteceu no Estoque e no Financeiro."""
        dialogo = self.abrir_dialogo(venda)
        if not dialogo.exec():
            return
        self.refresh()
        if dialogo.recado:
            tom = "warning" if dialogo.venda.avisos else "success"
            self.mostrar_aviso(f"Venda {dialogo.venda.numero} salva. {dialogo.recado}", tom)
        self.data_changed.emit()

    def excluir(self, venda: Venda) -> None:
        self.repository.excluir(venda.id)

    def descricao(self, venda: Venda) -> str:
        return f"{venda.numero} - {venda.cliente or 'Consumidor'}"

    def _comprovante(self) -> None:
        venda = self.registro_selecionado()
        if venda is None:
            return
        ComprovanteDialog(
            comprovante(venda, self.empresa), f"Venda {venda.numero}", self
        ).exec()

    def _whatsapp(self) -> None:
        venda = self.registro_selecionado()
        if venda is None:
            return
        mandar(self, self.mensageiro, "venda", {
            "cliente": venda.cliente,
            "numero": venda.numero,
            "total": fmt.moeda(venda.total_liquido),
            "data": fmt.data(venda.data),
        }, contatos=self.contatos)

    def _receber(self) -> None:
        venda = self.registro_selecionado()
        if venda is None:
            return
        dialogo = PagamentoDialog(
            venda.total,
            f"Venda {venda.numero}  ·  {venda.cliente or 'Consumidor'}",
            conferir=self.repository.conferir_pagamento,
            parent=self,
            # sem isto o QR Code do Pix nascia em branco aqui: a chave e da
            # empresa, e o dialogo nao tem como adivinha-la sozinho
            empresa=self.empresa,
        )
        if not dialogo.exec():
            return
        recebida = self.repository.receber_pendente(venda.id, dialogo.pagamentos)
        # a conta que a ponte criou tem que fechar junto, senao o Financeiro
        # continua cobrando uma venda que ja foi paga; e a venda que veio da
        # proposta, sem conta nenhuma, entra ja recebida
        recado = financeiro.registrar(self.contas, recebida)
        self.refresh()
        self.mostrar_aviso(f"Venda {venda.numero} recebida.{recado}", "success")
        self.data_changed.emit()

    def _devolver(self) -> None:
        venda = self.registro_selecionado()
        if venda is None:
            return
        dialogo = DevolucaoDialog(self.repository, venda, self)
        if not dialogo.exec():
            return
        devolucao = dialogo.devolucao
        self.refresh()
        recado = f"Devolução registrada: {fmt.moeda(devolucao.valor)}."
        if devolucao.avisos:
            self.mostrar_aviso(f"{recado} {'; '.join(devolucao.avisos)}", "warning")
        else:
            self.mostrar_aviso(recado, "success")
        self.data_changed.emit()

    def _cancelar(self) -> None:
        venda = self.registro_selecionado()
        if venda is None:
            return
        dialogo = MotivoDialog(
            f"Cancelar a venda {venda.numero}",
            "O cancelamento devolve os itens ao estoque e some dos relatórios",
            "Ex.: cliente desistiu",
            self,
        )
        if not dialogo.exec():
            return
        cancelada = self.repository.cancelar(venda.id, dialogo.motivo)
        self.refresh()
        recado = f"Venda {venda.numero} cancelada."
        if cancelada.avisos:
            self.mostrar_aviso(f"{recado} {'; '.join(cancelada.avisos)}", "warning")
        else:
            self.mostrar_aviso(recado, "success")
        self.data_changed.emit()
