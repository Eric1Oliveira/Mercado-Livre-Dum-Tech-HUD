"""Tela padrao de listagem/cadastro usada pelos aplicativos.

Cabecalho + pesquisa + tabela + botoes Novo/Editar/Excluir. A subclasse so
descreve as colunas, de onde vem os dados e qual formulario abrir.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ...core import confirmacoes
from ...core.errors import RegraError
from .. import icons
from ..theme import palette_for
from .buttons import Button
from .common import label, menu_arredondado, repolish
from .confirmar import confirmar
from .flow_layout import FlowLayout
from .table import DataTable


class CrudView(QWidget):
    """Base das telas de cadastro. Veja os "ganchos" no fim da classe."""

    data_changed = Signal()

    titulo = "Registros"
    nome_registro = "registro"
    nome_plural = "registros"
    #: genero do nome do registro: "uma ordem encontrada", "um produto encontrado"
    genero = "m"
    rotulo_novo = "Novo"
    icone_novo = "plus"
    colunas: list[str] = []
    larguras: dict[int, int] = {}
    dica_pesquisa = "Pesquisar..."
    permite_excluir = True

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registros: list[Any] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(16)

        cabecalho = QHBoxLayout()
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label(self.titulo, "title"))
        self.subtitulo = label("", "subtitle")
        titulos.addWidget(self.subtitulo)
        cabecalho.addLayout(titulos)
        cabecalho.addStretch(1)
        self.botao_novo = Button(self.rotulo_novo, self.icone_novo, "primary")
        self.botao_novo.setMinimumHeight(38)
        self.botao_novo.clicked.connect(self.novo)
        cabecalho.addWidget(self.botao_novo, 0, Qt.AlignmentFlag.AlignVCenter)
        raiz.addLayout(cabecalho)

        filtros = QHBoxLayout()
        filtros.setSpacing(10)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText(self.dica_pesquisa)
        self.busca.setClearButtonEnabled(True)
        self._acao_busca = self.busca.addAction(
            icons.icon("search", palette_for(self).text_dim, 16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.busca.textChanged.connect(self._nova_busca)
        filtros.addWidget(self.busca, 3)
        self.build_filters(filtros)
        raiz.addLayout(filtros)
        self._filtros_layout = filtros

        self.tabela = DataTable(self.colunas)
        self.tabela.set_empty_message(
            f"{'Nenhuma' if self.genero == 'f' else 'Nenhum'} "
            f"{self.nome_registro} por aqui ainda."
        )
        self.tabela.doubleClicked.connect(self.editar)
        self.tabela.itemSelectionChanged.connect(self._atualizar_acoes)
        raiz.addWidget(self.tabela, 1)

        # a barra quebra linha: com sete ou oito acoes, uma linha so espremia
        # os botoes ate o rotulo virar "Comprovant..." - e ai ninguem le nada
        barra = QWidget()
        acoes = FlowLayout(barra, spacing=10)
        # linha de recado da propria tela: caixa modal em callback trava os
        # testes e interrompe quem esta trabalhando
        self.aviso = label("", "muted")
        acoes.addWidget(self.aviso)
        self.botao_editar = Button("Editar", "edit")
        self.botao_editar.clicked.connect(self.editar)
        acoes.addWidget(self.botao_editar)
        self.botao_excluir = Button("Excluir", "trash", "danger")
        self.botao_excluir.clicked.connect(self.excluir_selecionado)
        # PRIMEIRO entra no layout, DEPOIS decide se aparece: `setVisible` num
        # widget que ainda nao tem pai abre uma janela solta - e o Hub piscava
        # uma janelinha por aplicativo enquanto preparava as telas de fundo
        acoes.addWidget(self.botao_excluir)
        self.botao_excluir.setVisible(self.permite_excluir)
        self.build_actions(acoes)
        self._barra_de_acoes = acoes
        raiz.addWidget(barra)

        # o botao direito repete as mesmas acoes da barra: quem trabalha rapido
        # nao quer atravessar a tela ate o rodape a cada linha
        self.tabela.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabela.customContextMenuRequested.connect(self._menu_de_contexto)

    # ------------------------------------------------------------- botao direito
    def acoes_da_barra(self) -> list:
        """Os botoes da barra, na ordem em que aparecem."""
        botoes = []
        for posicao in range(self._barra_de_acoes.count()):
            widget = self._barra_de_acoes.itemAt(posicao).widget()
            # `isHidden`, e nao `isVisible`: numa janela ainda nao exibida
            # todo widget e "invisivel", e a lista sairia vazia
            if isinstance(widget, Button) and not widget.isHidden():
                botoes.append(widget)
        return botoes

    def _menu_de_contexto(self, ponto) -> None:
        """Menu do botao direito, montado a partir da propria barra de acoes.

        Nao ha lista de acoes duplicada: o que o modulo poe na barra aparece
        aqui, com o mesmo estado de habilitado, e um clique chama o mesmo botao.
        """
        item = self.tabela.itemAt(ponto)
        if item is None:
            return
        self.tabela.selectRow(item.row())

        menu = menu_arredondado(self)
        for botao in self.acoes_da_barra():
            acao = menu.addAction(botao.icon(), botao.text().strip())
            acao.setEnabled(botao.isEnabled())
            acao.triggered.connect(botao.click)
        if menu.actions():
            menu.exec(self.tabela.viewport().mapToGlobal(ponto))

    # ------------------------------------------------------------------ recados
    def _nova_busca(self) -> None:
        """Procurar outra coisa e comecar de novo: o recado anterior sai."""
        self.mostrar_aviso("")
        self.refresh()

    def mostrar_aviso(self, texto: str, tom: str = "muted") -> None:
        """Escreve na linha de recado da tela (sem interromper o usuario)."""
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------- dados
    def apply_theme(self, palette) -> None:
        self._acao_busca.setIcon(icons.icon("search", palette.text_dim, 16))

    def refresh(self) -> None:
        """Recarrega a lista. NAO apaga a linha de recado.

        Toda acao termina em `mostrar_aviso` + `data_changed`, e o sinal faz a
        janela recarregar todas as telas: se o refresh limpasse o recado, a
        mensagem sumiria no mesmo instante em que foi escrita.
        """
        self._registros = list(self.carregar())
        self.tabela.fill([self.montar_linha(r) for r in self._registros], self.larguras)

        total = len(self._registros)
        feminino = self.genero == "f"
        nenhum = "Nenhuma" if feminino else "Nenhum"
        achado = "encontrada" if feminino else "encontrado"
        if total == 0:
            self.subtitulo.setText(f"{nenhum} {self.nome_registro} {achado}")
        elif total == 1:
            self.subtitulo.setText(f"1 {self.nome_registro} {achado}")
        else:
            self.subtitulo.setText(f"{total} {self.nome_plural} {achado}s")
        self._atualizar_acoes()

    def registro_selecionado(self) -> Any | None:
        linha = self.tabela.currentRow()
        if 0 <= linha < len(self._registros):
            return self._registros[linha]
        return None

    def _atualizar_acoes(self) -> None:
        tem = self.registro_selecionado() is not None
        self.botao_editar.setEnabled(tem)
        self.botao_excluir.setEnabled(tem)

    # ------------------------------------------------------------------ acoes
    def novo(self) -> None:
        dialogo = self.abrir_dialogo(None)
        if dialogo is not None and dialogo.exec():
            self.refresh()
            self.data_changed.emit()

    def editar(self) -> None:
        registro = self.registro_selecionado()
        if registro is None:
            return
        dialogo = self.abrir_dialogo(registro)
        if dialogo is not None and dialogo.exec():
            self.refresh()
            self.data_changed.emit()

    def excluir_selecionado(self) -> None:
        registro = self.registro_selecionado()
        if registro is None:
            return
        if not confirmar(
            self,
            f"Excluir {self.nome_registro}",
            f"Excluir '{self.descricao(registro)}'?",
            chave=confirmacoes.EXCLUIR,
            rotulo_ok="Excluir",
            detalhe="Esta acao nao pode ser desfeita.",
        ):
            return
        try:
            self.excluir(registro)
        except RegraError as erro:
            # o aplicativo pode recusar a exclusao (ex.: o registro tem
            # historico); isso e um aviso na tela, nao um travamento
            QMessageBox.warning(self, "Nao foi possivel excluir", str(erro))
            return
        self.refresh()
        self.data_changed.emit()

    # ---------------------------------------------------------------- ganchos
    def build_filters(self, layout: QHBoxLayout) -> None:
        """Filtros extras ao lado da pesquisa (opcional)."""

    def build_actions(self, layout: QHBoxLayout) -> None:
        """Botoes extras ao lado de Editar/Excluir (opcional)."""

    def carregar(self) -> list[Any]:
        raise NotImplementedError

    def montar_linha(self, registro: Any) -> list:
        raise NotImplementedError

    def abrir_dialogo(self, registro: Any | None):
        raise NotImplementedError

    def excluir(self, registro: Any) -> None:
        raise NotImplementedError

    def descricao(self, registro: Any) -> str:
        return str(registro)
