"""Lista de propostas: mandar, responder, duplicar e imprimir."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QMessageBox, QWidget

from ....core.contas import AReceber, vencimento_padrao
from ....ui import format as fmt
from ....ui.widgets.buttons import Button
from ....ui.widgets.documento import DocumentoDialog
from ....ui.widgets.mensagem import mandar
from ....ui.widgets.crud_view import CrudView
from ....ui.widgets.table import DIREITA
from ..models import (
    APROVADO,
    ENVIADO,
    RASCUNHO,
    RECUSADO,
    STATUS_LABEL,
    Orcamento,
    OrcamentoError,
)
from ..documento import proposta_a4
from ..recibo import proposta
from ..repository import OrcamentosRepository
from .orcamento_dialog import OrcamentoDialog, RecusaDialog

logger = logging.getLogger(__name__)

FILTRO_TUDO = ""
FILTRO_ABERTO = "aberto"


class OrcamentosView(CrudView):
    titulo = "Orçamentos"
    limite_lista = 500
    exportavel = True
    nome_registro = "proposta"
    nome_plural = "propostas"
    genero = "f"
    rotulo_novo = "Nova proposta"
    dica_pesquisa = "Pesquisar por número, cliente ou observação..."
    colunas = ["Número", "Data", "Cliente", "Situação", "Total"]
    larguras = {0: 145, 1: 115, 3: 230, 4: 140}

    def __init__(
        self,
        repository: OrcamentosRepository,
        clientes: list[str] | None = None,
        parent: QWidget | None = None,
        empresa=None,
        paths=None,
        mensageiro=None,
        contatos=None,
        destinos=None,
        catalogo=None,
        contas=None,
    ) -> None:
        #: o Financeiro: sem Vendas nem Ordens, a proposta aprovada vira conta direto
        self.contas = contas
        self.repository = repository
        self.clientes = clientes or []
        self.empresa = empresa
        self.paths = paths
        self.mensageiro = mensageiro
        self.contatos = contatos
        #: catalogo do Estoque para sugerir produto ao digitar o item
        self.catalogo = catalogo
        #: para onde a proposta aprovada pode virar trabalho (Vendas, Ordens)
        self.destinos = list(destinos or [])
        super().__init__(parent)

    def build_filters(self, layout: QHBoxLayout) -> None:
        self.filtro_status = QComboBox()
        self.filtro_status.addItem("Todas as propostas", FILTRO_TUDO)
        self.filtro_status.addItem("Em aberto", FILTRO_ABERTO)
        for chave, rotulo in STATUS_LABEL.items():
            self.filtro_status.addItem(rotulo, chave)
        self.filtro_status.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_status, 1)

    def build_actions(self, layout: QHBoxLayout) -> None:
        self.botao_documento = Button("Documento", "file")
        self.botao_documento.setToolTip("Vê a proposta em folha A4 e salva em PDF")
        self.botao_documento.clicked.connect(self._documento)
        layout.insertWidget(1, self.botao_documento)

        self.botao_whatsapp = Button("WhatsApp", "chat")
        self.botao_whatsapp.setToolTip("Manda a proposta pronta para o cliente")
        self.botao_whatsapp.clicked.connect(self._whatsapp)
        layout.insertWidget(2, self.botao_whatsapp)

        self.botao_enviar = Button("Enviar", "external")
        self.botao_enviar.setToolTip("Marca a proposta como enviada ao cliente")
        self.botao_enviar.clicked.connect(self._enviar)
        layout.insertWidget(2, self.botao_enviar)

        self.botao_aprovar = Button("Aprovar", "check", "success")
        self.botao_aprovar.setToolTip("O cliente aceitou a proposta")
        self.botao_aprovar.clicked.connect(self._aprovar)
        layout.insertWidget(3, self.botao_aprovar)

        self.botao_recusar = Button("Recusar", "close", "danger")
        self.botao_recusar.setToolTip("O cliente não aceitou - com o motivo")
        self.botao_recusar.clicked.connect(self._recusar)
        layout.insertWidget(4, self.botao_recusar)

        self.botao_gerar = Button("Gerar", "swap", "success")
        self.botao_gerar.setToolTip(
            "Abre a venda ou a ordem de serviço com os itens desta proposta"
        )
        self.botao_gerar.clicked.connect(self._gerar)
        # entra no layout antes de decidir se aparece: sem pai, `setVisible`
        # abriria uma janela solta (ver ui/widgets/crud_view.py)
        layout.insertWidget(5, self.botao_gerar)
        self.botao_gerar.setVisible(bool(self.destinos))

        self.botao_duplicar = Button("Duplicar", "refresh")
        self.botao_duplicar.clicked.connect(self._duplicar)
        layout.insertWidget(5, self.botao_duplicar)

    # ------------------------------------------------------------------- dados
    def carregar(self, limite: int = 500) -> list[Orcamento]:
        escolha = self.filtro_status.currentData()
        return self.repository.listar(
            busca=self.busca.text(),
            status=escolha if escolha not in (FILTRO_TUDO, FILTRO_ABERTO) else "",
            em_aberto=escolha == FILTRO_ABERTO,
            limite=limite,
        )

    def montar_linha(self, orcamento: Orcamento) -> list:
        return [
            self.tabela.cell(orcamento.numero, bold=True, data=orcamento.id),
            self.tabela.cell(fmt.data(orcamento.data)),
            self.tabela.cell(orcamento.cliente, bold=True),
            self.tabela.cell(self._situacao(orcamento), tone=self._tom(orcamento)),
            self.tabela.cell(fmt.moeda(orcamento.total), DIREITA, "accent", bold=True),
        ]

    @staticmethod
    def _situacao(orcamento: Orcamento) -> str:
        """O status sozinho nao diz ha quanto tempo a proposta esta parada."""
        if orcamento.status == RECUSADO and orcamento.motivo_recusa:
            return f"Não aprovada · {orcamento.motivo_label.lower()}"
        if orcamento.status == ENVIADO:
            dias = orcamento.dias_esperando
            if orcamento.vencido:
                return f"Enviada · venceu {fmt.prazo_texto(orcamento.vale_ate)}"
            if dias:
                return f"Enviada · esperando há {fmt.dias(dias)}"
            return "Enviada hoje"
        if orcamento.gerado:
            return f"Aprovada · virou {orcamento.gerado}"
        if orcamento.status == APROVADO and orcamento.respondido_em:
            return f"Aprovada em {fmt.data(orcamento.respondido_em)}"
        return orcamento.status_label

    @staticmethod
    def _tom(orcamento: Orcamento) -> str:
        return "danger" if orcamento.vencido else orcamento.status_tom

    def _atualizar_acoes(self) -> None:
        super()._atualizar_acoes()
        orcamento = self.registro_selecionado()
        tem = orcamento is not None
        self.botao_documento.setEnabled(tem)
        self.botao_whatsapp.setEnabled(tem)
        self.botao_duplicar.setEnabled(tem)
        self.botao_enviar.setEnabled(tem and orcamento.status == RASCUNHO)
        self.botao_aprovar.setEnabled(tem and orcamento.status != APROVADO)
        self.botao_recusar.setEnabled(tem and orcamento.status != RECUSADO)
        # so proposta aprovada vira trabalho: gerar de um rascunho seria
        # comecar servico que o cliente ainda nao aceitou
        self.botao_gerar.setEnabled(
            bool(self.destinos) and tem and orcamento.status == APROVADO
        )

    # ------------------------------------------------------------------- acoes
    def abrir_dialogo(self, orcamento: Orcamento | None):
        return OrcamentoDialog(self.repository, orcamento, self.clientes, self,
                               catalogo=self.catalogo)

    def excluir(self, orcamento: Orcamento) -> None:
        self.repository.excluir(orcamento.id)

    def descricao(self, orcamento: Orcamento) -> str:
        return f"{orcamento.numero} - {orcamento.cliente}"

    def _documento(self) -> None:
        orcamento = self.registro_selecionado()
        if orcamento is not None:
            DocumentoDialog(
                proposta_a4(orcamento, self.empresa, self.paths),
                f"Proposta {orcamento.numero}",
                f"Proposta {orcamento.numero} - {orcamento.cliente}",
                proposta(orcamento, self.empresa),
                self.empresa, self.paths, self,
            ).exec()

    def _whatsapp(self) -> None:
        orcamento = self.registro_selecionado()
        if orcamento is None:
            return
        validade = (fmt.data(orcamento.vale_ate) if orcamento.vale_ate
                    else f"{fmt.dias(orcamento.validade_dias)} após o envio")
        mandar(self, self.mensageiro, "proposta", {
            "cliente": orcamento.cliente,
            "numero": orcamento.numero,
            "total": fmt.moeda(orcamento.total),
            "validade": validade,
            "pagamento": orcamento.condicao_pagamento,
            "prazo": orcamento.prazo_entrega,
        }, contatos=self.contatos)

    def _gerar(self) -> None:
        """A proposta aprovada vira venda ou ordem, com os itens ja dentro."""
        from ....core.pedidos import ItemPedido, Pedido

        orcamento = self.registro_selecionado()
        if orcamento is None or not self.destinos:
            return
        if orcamento.gerado and not self._gerar_de_novo(orcamento):
            return

        destino = self.destinos[0]
        if len(self.destinos) > 1:
            destino = self._escolher_destino()
            if destino is None:
                return

        pedido = Pedido(
            cliente=orcamento.cliente, origem=orcamento.numero,
            desconto=float(orcamento.desconto or 0),
            observacoes=orcamento.observacoes,
            itens=[
                ItemPedido(descricao=item.descricao, quantidade=item.quantidade,
                           valor_unitario=item.valor_unitario,
                           unidade=item.unidade, desconto=item.desconto,
                           produto_id=item.produto_id, codigo=item.codigo)
                for item in orcamento.itens
            ],
        )
        try:
            numero = destino.abrir(pedido)
        except Exception as erro:  # noqa: BLE001 - a proposta nao pode ser afetada
            self.mostrar_aviso(f"Não foi possível gerar: {erro}", "danger")
            return
        self.repository.marcar_gerado(orcamento.id, numero)
        self.refresh()
        self.data_changed.emit()
        self.mostrar_aviso(
            f"{destino.titulo} {numero} criada a partir de {orcamento.numero}. "
            f"Abra o {destino.titulo.lower()} para conferir.",
            "success",
        )

    def _gerar_de_novo(self, orcamento: Orcamento) -> bool:
        """Clique duplo aqui virava duas vendas: quem insiste precisa dizer."""
        resposta = QMessageBox.question(
            self, "Proposta já gerada",
            f"A proposta {orcamento.numero} já virou {orcamento.gerado}.\n\n"
            "Gerar outro documento com os mesmos itens?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resposta == QMessageBox.StandardButton.Yes

    def _escolher_destino(self):
        """Com Vendas e Ordens na licenca, quem decide e quem esta olhando."""
        from PySide6.QtWidgets import QInputDialog

        titulos = [destino.titulo for destino in self.destinos]
        escolhido, confirmou = QInputDialog.getItem(
            self, "Gerar trabalho",
            "Esta proposta vira o que?", titulos, 0, False
        )
        if not confirmou:
            return None
        return self.destinos[titulos.index(escolhido)]

    def _enviar(self) -> None:
        self._mudar(lambda ordem_id: self.repository.enviar(ordem_id),
                    "marcada como enviada")

    def _aprovar(self) -> None:
        orcamento = self.registro_selecionado()
        self._mudar(lambda ordem_id: self.repository.aprovar(ordem_id), "aprovada")
        if orcamento is not None:
            self._lancar_na_aprovacao(orcamento)

    def _lancar_na_aprovacao(self, orcamento: Orcamento) -> None:
        """Quem tem Vendas ou Ordens lanca ao gerar; quem nao tem, lanca aqui.

        O numero da proposta e a chave: aprovar de novo nao dobra a conta.
        """
        if self.destinos or self.contas is None or orcamento.total <= 0:
            return
        try:
            if self.contas.ja_lancado(orcamento.numero):
                return
            self.contas.lancar(AReceber(
                descricao=f"Proposta {orcamento.numero}", valor=orcamento.total,
                vencimento=vencimento_padrao(), cliente=orcamento.cliente,
                categoria="Vendas", documento=orcamento.numero,
            ))
        except Exception:  # noqa: BLE001 - a proposta ja foi aprovada
            logger.exception("Nao foi possivel lancar a proposta no Financeiro")
            self.mostrar_aviso("Proposta aprovada, mas não consegui lançar no Financeiro.",
                               "warning")
            return
        self.mostrar_aviso(f"Proposta {orcamento.numero} aprovada. Conta a receber criada.",
                           "success")

    def _mudar(self, acao, recado: str) -> None:
        orcamento = self.registro_selecionado()
        if orcamento is None:
            return
        try:
            acao(orcamento.id)
        except OrcamentoError as erro:
            self.refresh()
            self.mostrar_aviso(str(erro), "danger")
            return
        self.refresh()
        self.mostrar_aviso(f"Proposta {orcamento.numero} {recado}.", "success")
        self.data_changed.emit()

    def _recusar(self) -> None:
        orcamento = self.registro_selecionado()
        if orcamento is None:
            return
        dialogo = RecusaDialog(self.repository, orcamento, self)
        if not dialogo.exec():
            return
        self.refresh()
        self.mostrar_aviso(
            f"Proposta {orcamento.numero} marcada como não aprovada.", "success"
        )
        self.data_changed.emit()

    def _duplicar(self) -> None:
        orcamento = self.registro_selecionado()
        if orcamento is None:
            return
        copia = self.repository.duplicar(orcamento.id)
        self.refresh()
        self.mostrar_aviso(
            f"Proposta {copia.numero} criada a partir da {orcamento.numero}. "
            "Ela nasce como rascunho, para você ajustar antes de mandar.",
            "success",
        )
        self.data_changed.emit()
