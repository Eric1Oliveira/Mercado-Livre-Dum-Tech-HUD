"""Lista de ordens de servico: consultar, imprimir e mexer na etapa."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.widgets.buttons import Button
from ....ui.widgets.comprovante import ComprovanteDialog
from ....ui.widgets.documento import DocumentoDialog
from ....ui.widgets.mensagem import mandar
from ....ui.widgets.crud_view import CrudView
from ....ui.widgets.table import DIREITA
from ..models import (
    AGUARDANDO,
    CANCELADA,
    CONCLUIDA,
    ENTREGUE,
    PROXIMO_PASSO,
    STATUS_LABEL,
    Ordem,
    OrdemError,
)
from ..documento import entrega_a4
from ..recibo import entrada, entrega
from ..repository import OrdensRepository
from .dialogos import AprovacaoDialog, EntregaDialog, MotivoDialog
from .ordem_dialog import OrdemDialog

#: filtros que respondem perguntas do balcao, nao so estados do banco
FILTRO_TUDO = ""
FILTRO_ABERTAS = "abertas"
FILTRO_GARANTIA = "garantia"


class OrdensView(CrudView):
    titulo = "Ordens"
    nome_registro = "ordem"
    nome_plural = "ordens"
    genero = "f"
    rotulo_novo = "Nova ordem"
    dica_pesquisa = "Pesquisar por numero, cliente, item ou telefone..."
    # sem coluna "Responsavel": ela ja e filtro aqui em cima. A coluna do meio
    # mostra o item quando existe e, quando nao existe, o que foi pedido - e
    # assim serve tanto para quem recebe aparelho quanto para quem presta
    # servico no local
    colunas = ["Numero", "Entrada", "Cliente", "Servico", "Valor", "Etapa"]
    larguras = {0: 130, 1: 165, 4: 125, 5: 165}

    def __init__(
        self,
        repository: OrdensRepository,
        clientes: list[str] | None = None,
        parent: QWidget | None = None,
        empresa=None,
        paths=None,
        mensageiro=None,
        contatos=None,
        contas=None,
        catalogo=None,
    ) -> None:
        self.repository = repository
        self.clientes = clientes or []
        self.empresa = empresa
        self.paths = paths
        self.mensageiro = mensageiro
        self.contatos = contatos
        #: catalogo do Estoque para sugerir peca ao digitar o item
        self.catalogo = catalogo
        #: ponte com o Financeiro; None quando a licenca nao o libera
        self.contas = contas
        super().__init__(parent)

    def build_filters(self, layout: QHBoxLayout) -> None:
        self.filtro_status = QComboBox()
        self.filtro_status.addItem("Todas as ordens", FILTRO_TUDO)
        self.filtro_status.addItem("Em andamento agora", FILTRO_ABERTAS)
        self.filtro_status.addItem("Dentro da garantia", FILTRO_GARANTIA)
        for chave, rotulo in STATUS_LABEL.items():
            self.filtro_status.addItem(rotulo, chave)
        self.filtro_status.setCurrentIndex(1)
        self.filtro_status.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_status, 1)

        self.filtro_tecnico = QComboBox()
        self.filtro_tecnico.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_tecnico, 1)
        self._carregar_tecnicos()

    def build_actions(self, layout: QHBoxLayout) -> None:
        self.botao_entrada = Button("Entrada", "file")
        self.botao_entrada.setToolTip("Comprovante de entrada, em bobina")
        self.botao_entrada.clicked.connect(self._papel_entrada)
        layout.insertWidget(1, self.botao_entrada)

        self.botao_entrega = Button("Entrega", "file")
        self.botao_entrega.setToolTip("Comprovante de entrega, em folha A4 e PDF")
        self.botao_entrega.clicked.connect(self._papel_entrega)
        layout.insertWidget(2, self.botao_entrega)

        self.botao_whatsapp = Button("WhatsApp", "chat")
        self.botao_whatsapp.setToolTip("Avisa o cliente que o servico esta pronto")
        self.botao_whatsapp.clicked.connect(self._whatsapp)
        layout.insertWidget(3, self.botao_whatsapp)

        self.botao_avancar = Button("Avancar", "check", "success")
        self.botao_avancar.clicked.connect(self._avancar)
        layout.insertWidget(4, self.botao_avancar)

        self.botao_financeiro = Button("Financeiro", "money")
        self.botao_financeiro.setToolTip(
            "Cria a conta a receber desta ordem no DumTech Financeiro"
        )
        self.botao_financeiro.clicked.connect(self._lancar_no_financeiro)
        # entra no layout antes de decidir se aparece: sem pai, `setVisible`
        # abriria uma janela solta (ver ui/widgets/crud_view.py)
        layout.insertWidget(5, self.botao_financeiro)
        self.botao_financeiro.setVisible(self.contas is not None)

        self.botao_cancelar = Button("Cancelar", "close", "danger")
        self.botao_cancelar.setToolTip("Cancela a ordem de servico")
        self.botao_cancelar.clicked.connect(self._cancelar)
        layout.insertWidget(6, self.botao_cancelar)

    # ------------------------------------------------------------------- dados
    def _carregar_tecnicos(self) -> None:
        atual = self.filtro_tecnico.currentData()
        self.filtro_tecnico.blockSignals(True)
        self.filtro_tecnico.clear()
        self.filtro_tecnico.addItem("Todos os responsaveis", "")
        for tecnico in self.repository.tecnicos():
            self.filtro_tecnico.addItem(tecnico, tecnico)
        indice = self.filtro_tecnico.findData(atual)
        self.filtro_tecnico.setCurrentIndex(max(indice, 0))
        self.filtro_tecnico.blockSignals(False)

    def carregar(self) -> list[Ordem]:
        escolha = self.filtro_status.currentData()
        return self.repository.listar(
            busca=self.busca.text(),
            status=escolha if escolha not in (FILTRO_TUDO, FILTRO_ABERTAS,
                                              FILTRO_GARANTIA) else "",
            tecnico=self.filtro_tecnico.currentData() or "",
            somente_abertas=escolha == FILTRO_ABERTAS,
            na_garantia=escolha == FILTRO_GARANTIA,
        )

    def refresh(self) -> None:
        super().refresh()
        self._carregar_tecnicos()

    def montar_linha(self, ordem: Ordem) -> list:
        return [
            self.tabela.cell(ordem.numero, bold=True, data=ordem.id),
            self.tabela.cell(self._entrada_texto(ordem)),
            self.tabela.cell(ordem.cliente or "-"),
            self.tabela.cell(ordem.assunto, bold=True),
            self.tabela.cell(fmt.moeda(ordem.total), DIREITA, "accent", bold=True),
            self.tabela.cell(self._etapa(ordem), tone=self._tom(ordem)),
        ]

    @staticmethod
    def _entrada_texto(ordem: Ordem) -> str:
        """A data sozinha nao diz ha quanto tempo a ordem esta parada."""
        if ordem.aberta:
            dias = ordem.dias_em_aberto
            tempo = "hoje" if dias == 0 else f"ha {fmt.dias(dias)}"
            return f"{fmt.data(ordem.aberta_em)}  ({tempo})"
        return fmt.data(ordem.aberta_em)

    @staticmethod
    def _etapa(ordem: Ordem) -> str:
        if ordem.atrasada:
            return f"{ordem.status_label} · atrasada"
        if ordem.status == ENTREGUE and ordem.na_garantia:
            return f"Entregue · garantia ate {fmt.data(ordem.garantia_ate)}"
        return ordem.status_label

    @staticmethod
    def _tom(ordem: Ordem) -> str:
        return "danger" if ordem.atrasada else ordem.status_tom

    def _atualizar_acoes(self) -> None:
        super()._atualizar_acoes()
        ordem = self.registro_selecionado()
        tem = ordem is not None
        self.botao_entrada.setEnabled(tem)
        self.botao_whatsapp.setEnabled(tem)
        self.botao_entrega.setEnabled(tem and ordem.status in (CONCLUIDA, ENTREGUE))
        self.botao_avancar.setEnabled(tem and ordem.status in PROXIMO_PASSO)
        self.botao_cancelar.setEnabled(tem and ordem.status != CANCELADA)
        self.botao_financeiro.setEnabled(
            self.contas is not None and tem and ordem.status == ENTREGUE
            and ordem.total > 0 and not self.contas.ja_lancado(ordem.numero)
        )

    # ------------------------------------------------------------------- acoes
    def abrir_dialogo(self, ordem: Ordem | None):
        return OrdemDialog(self.repository, ordem, self.clientes, self,
                           catalogo=self.catalogo)

    def excluir(self, ordem: Ordem) -> None:
        self.repository.excluir(ordem.id)

    def descricao(self, ordem: Ordem) -> str:
        return f"{ordem.numero} - {ordem.equipamento}"

    def _papel_entrada(self) -> None:
        ordem = self.registro_selecionado()
        if ordem is not None:
            ComprovanteDialog(
                entrada(ordem, self.empresa), f"Entrada da {ordem.numero}", self
            ).exec()

    def _papel_entrega(self) -> None:
        ordem = self.registro_selecionado()
        if ordem is not None:
            DocumentoDialog(
                entrega_a4(ordem, self.empresa, self.paths),
                f"Entrega da {ordem.numero}",
                f"Entrega {ordem.numero} - {ordem.cliente}",
                entrega(ordem, self.empresa),
                self.empresa, self.paths, self,
            ).exec()

    def _whatsapp(self) -> None:
        ordem = self.registro_selecionado()
        if ordem is None:
            return
        mandar(self, self.mensageiro, "ordem_pronta", {
            "cliente": ordem.cliente,
            "numero": ordem.numero,
            "equipamento": ordem.assunto,
            "total": fmt.moeda(ordem.total),
            "garantia": fmt.dias(ordem.garantia_dias) if ordem.garantia_dias else "",
        }, telefone=ordem.telefone, contatos=self.contatos)

    def _lancar_no_financeiro(self) -> None:
        """A ordem entregue vira conta a receber - com um clique, e uma vez so.

        Aqui e botao, e nao automatico como na venda a prazo: boa parte das
        ordens e paga na hora da entrega, e criar conta para todas encheria o
        Financeiro de divida que nao existe.
        """
        from ....core.contas import AReceber

        ordem = self.registro_selecionado()
        if ordem is None or self.contas is None:
            return
        try:
            self.contas.lancar(AReceber(
                descricao=f"Ordem {ordem.numero}"
                          + (f" - {ordem.assunto}" if ordem.assunto else ""),
                valor=ordem.total,
                vencimento=ordem.entregue_em or ordem.aberta_em,
                cliente=ordem.cliente, categoria="Servicos",
                documento=ordem.numero,
            ))
        except Exception as erro:  # noqa: BLE001 - a ordem nao pode ser afetada
            self.mostrar_aviso(f"Nao foi possivel lancar: {erro}", "danger")
            return
        self._atualizar_acoes()
        self.mostrar_aviso(
            f"Conta a receber de {fmt.moeda(ordem.total)} criada no Financeiro.",
            "success",
        )

    def _avancar(self) -> None:
        ordem = self.registro_selecionado()
        if ordem is None:
            return

        if ordem.status == AGUARDANDO:
            dialogo = AprovacaoDialog(self.repository, ordem, self)
        elif ordem.status == CONCLUIDA:
            dialogo = EntregaDialog(self.repository, ordem, self,
                                    empresa=self.empresa, contas=self.contas)
        else:
            dialogo = None

        if dialogo is not None:
            if not dialogo.exec():
                return
        else:
            try:
                self.repository.avancar(ordem.id)
            except OrdemError as erro:
                self.refresh()
                self.mostrar_aviso(str(erro), "danger")
                return

        atual = self.repository.obter(ordem.id)
        self.refresh()
        self.mostrar_aviso(
            f"{ordem.numero}: agora esta em '{atual.status_label}'."
            + getattr(dialogo, "recado_financeiro", ""), "success"
        )
        self.data_changed.emit()

    def _cancelar(self) -> None:
        ordem = self.registro_selecionado()
        if ordem is None:
            return
        dialogo = MotivoDialog(
            f"Cancelar a ordem {ordem.numero}",
            f"{ordem.equipamento}  ·  {ordem.cliente}",
            "Ex.: o cliente desistiu do servico",
            self,
        )
        if not dialogo.exec():
            return
        self.repository.cancelar(ordem.id, dialogo.motivo)
        self.refresh()
        self.mostrar_aviso(f"Ordem {ordem.numero} cancelada.", "success")
        self.data_changed.emit()
