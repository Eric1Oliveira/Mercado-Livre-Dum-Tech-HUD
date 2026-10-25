"""Lista de clientes: pesquisar, filtrar e abrir a ficha."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QMessageBox, QWidget

from ....core.contacts import Contato, ContactsStore
from ....ui import format as fmt
from ....ui.widgets.buttons import Button
from ....ui.widgets.crud_view import CrudView
from ....ui.widgets.mensagem import mandar
from .cliente_dialog import ClienteDialog


class ClientesView(CrudView):
    titulo = "Clientes"
    nome_registro = "cliente"
    nome_plural = "clientes"
    rotulo_novo = "Novo cliente"
    dica_pesquisa = "Pesquisar por nome, documento, telefone, bairro, cidade ou segmento..."
    colunas = ["Nome", "Documento", "Telefone", "Cidade", "Segmento", "Cadastrado", "Situação"]
    larguras = {1: 165, 2: 145, 4: 140, 5: 120, 6: 110}

    def __init__(self, store: ContactsStore, parent: QWidget | None = None,
                 mensageiro=None) -> None:
        self.store = store
        self.mensageiro = mensageiro
        super().__init__(parent)
        self.tabela.doubleClicked.disconnect()
        self.tabela.doubleClicked.connect(self.abrir_ficha)

    # ------------------------------------------------------------------ filtros
    def build_filters(self, layout: QHBoxLayout) -> None:
        self.filtro_cidade = QComboBox()
        self.filtro_cidade.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_cidade, 1)

        self.filtro_segmento = QComboBox()
        self.filtro_segmento.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filtro_segmento, 1)

        self.mostrar_inativos = QCheckBox("Mostrar inativos")
        self.mostrar_inativos.stateChanged.connect(self.refresh)
        layout.addWidget(self.mostrar_inativos)

    def build_actions(self, layout: QHBoxLayout) -> None:
        self.botao_ficha = Button("Ver ficha", "file", "primary")
        self.botao_ficha.setToolTip("Abre a ficha do cliente com as anotações (duplo clique)")
        self.botao_ficha.clicked.connect(self.abrir_ficha)
        layout.insertWidget(1, self.botao_ficha)

        self.botao_whatsapp = Button("WhatsApp", "chat")
        self.botao_whatsapp.setToolTip("Manda os parabéns no aniversário do cliente")
        self.botao_whatsapp.clicked.connect(self._whatsapp)
        layout.insertWidget(2, self.botao_whatsapp)

        self.botao_ativar = Button("Inativar", "close")
        self.botao_ativar.setToolTip("Tira o cliente das listas e das sugestões")
        self.botao_ativar.clicked.connect(self._alternar_ativo)
        layout.addWidget(self.botao_ativar)

        self.botao_exportar = Button("Exportar", "external")
        self.botao_exportar.setToolTip("Salva a carteira de clientes em CSV")
        self.botao_exportar.clicked.connect(self._exportar)
        layout.addWidget(self.botao_exportar)

    # ------------------------------------------------------------------- dados
    def carregar(self) -> list[Contato]:
        self._preencher_filtros()
        return self.store.listar(
            busca=self.busca.text(),
            cidade=self.filtro_cidade.currentData() or "",
            segmento=self.filtro_segmento.currentData() or "",
            incluir_inativos=self.mostrar_inativos.isChecked(),
        )

    def montar_linha(self, contato: Contato) -> list:
        tom = "muted" if not contato.ativo else "text"
        return [
            self.tabela.cell(contato.nome, bold=True, data=contato.id),
            self.tabela.cell(contato.documento_formatado or "-"),
            self.tabela.cell(contato.telefone_formatado or contato.whatsapp_formatado or "-"),
            self.tabela.cell(
                f"{contato.cidade}/{contato.uf}" if contato.uf else (contato.cidade or "-")
            ),
            self.tabela.cell(contato.segmento or "-"),
            self.tabela.cell(fmt.data(contato.criado_em)),
            self.tabela.cell("Ativo" if contato.ativo else "Inativo",
                             tone="success" if contato.ativo else "muted"),
        ]

    def _preencher_filtros(self) -> None:
        for combo, titulo, valores in (
            (self.filtro_cidade, "Todas as cidades", self.store.cidades()),
            (self.filtro_segmento, "Todos os segmentos", self.store.segmentos()),
        ):
            atual = combo.currentData() or ""
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(titulo, "")
            for valor in valores:
                combo.addItem(valor, valor)
            indice = combo.findData(atual)
            combo.setCurrentIndex(max(indice, 0))
            combo.blockSignals(False)

    def _atualizar_acoes(self) -> None:
        super()._atualizar_acoes()
        contato = self.registro_selecionado()
        tem = contato is not None
        self.botao_ficha.setEnabled(tem)
        self.botao_whatsapp.setEnabled(tem)
        self.botao_ativar.setEnabled(tem)
        if tem:
            self.botao_ativar.setText("  Reativar" if not contato.ativo else "  Inativar")
            self.botao_ativar.set_icon_name("check" if not contato.ativo else "close")

    # ------------------------------------------------------------------- acoes
    def abrir_ficha(self) -> None:
        from .ficha_dialog import FichaDialog

        contato = self.registro_selecionado()
        if contato is None:
            return
        ficha = FichaDialog(self.store, contato, self)
        ficha.exec()
        if ficha.houve_mudanca:
            self.data_changed.emit()

    def _whatsapp(self) -> None:
        contato = self.registro_selecionado()
        if contato is None:
            return
        idade = contato.idade_neste_ano
        mandar(self, self.mensageiro, "aniversario", {
            "cliente": contato.nome,
            "idade": f"{idade} anos" if idade else "",
        }, telefone=contato.whatsapp or contato.telefone)

    def _alternar_ativo(self) -> None:
        contato = self.registro_selecionado()
        if contato is None:
            return
        if contato.ativo:
            self.store.inativar(contato.id)
            recado = f"'{contato.nome}' saiu das listas e das sugestões."
        else:
            self.store.reativar(contato.id)
            recado = f"'{contato.nome}' voltou para as listas."
        self.refresh()
        self.mostrar_aviso(recado)
        self.data_changed.emit()

    def _exportar(self) -> None:
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Exportar clientes", "clientes.csv", "Planilha CSV (*.csv);;Todos (*)"
        )
        if not caminho:
            return
        # BOM: e o que faz o Excel abrir com os acentos certos
        Path(caminho).write_text(self.store.exportar_csv(), encoding="utf-8-sig")
        QMessageBox.information(self, "Exportado", f"Arquivo salvo em:\n{caminho}")

    # ------------------------------------------------------------------ ganchos
    def abrir_dialogo(self, contato: Contato | None):
        return ClienteDialog(self.store, contato, self)

    def excluir(self, contato: Contato) -> None:
        self.store.excluir(contato.id)

    def descricao(self, contato: Contato) -> str:
        return contato.nome
