"""Tabela padrao da plataforma (somente leitura, com selecao por linha)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..theme import Palette, palette_for

#: guarda o token do tom na propria celula - e ele que sobrevive a troca de tema
TOM = Qt.ItemDataRole.UserRole + 1

DIREITA = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
CENTRO = Qt.AlignmentFlag.AlignCenter
ESQUERDA = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


class DataTable(QTableWidget):
    def __init__(self, headers: list[str], parent: QWidget | None = None) -> None:
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.verticalHeader().setDefaultSectionSize(40)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setDefaultAlignment(ESQUERDA)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._vazio = ""

    def set_empty_message(self, texto: str) -> None:
        """O que dizer quando a tabela nao tem linha nenhuma.

        Tabela vazia sem recado deixa um bloco cinza no meio da tela e nao
        ensina nada: o espaco vazio e o melhor lugar para dizer o proximo passo.
        """
        self._vazio = texto
        self.viewport().update()

    def paintEvent(self, event) -> None:  # noqa: N802 (assinatura do Qt)
        super().paintEvent(event)
        if self.rowCount() or not self._vazio:
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor(palette_for(self).text_dim))
        painter.drawText(self.viewport().rect(), CENTRO, self._vazio)
        painter.end()

    def apply_theme(self, palette: Palette) -> None:
        """Recolore as celulas ja escritas.

        Sem isto, trocar de tema com a lista aberta deixava os valores com a
        cor do tema anterior - verde-escuro do modo noturno sobre fundo branco.
        """
        for linha in range(self.rowCount()):
            for coluna in range(self.columnCount()):
                celula = self.item(linha, coluna)
                if celula is None:
                    continue
                tom = celula.data(TOM)
                if tom:
                    celula.setForeground(QBrush(QColor(palette.resolve(tom))))
                else:
                    # sem tom: devolve a cor do texto para a folha de estilo
                    celula.setData(Qt.ItemDataRole.ForegroundRole, None)
        self.viewport().update()

    def set_column_widths(self, widths: dict[int, int]) -> None:
        header = self.horizontalHeader()
        for index in range(self.columnCount()):
            if index in widths:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Fixed)
                self.setColumnWidth(index, widths[index])
            else:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)

    def cell(
        self,
        text: str,
        align: Qt.AlignmentFlag = ESQUERDA,
        tone: str = "",
        bold: bool = False,
        data=None,
    ) -> QTableWidgetItem:
        """Cria uma celula. `tone` e um token do tema (success, danger...)."""
        item = QTableWidgetItem(text)
        item.setTextAlignment(align)
        if tone:
            # o token fica gravado: a cor resolvida envelhece quando o cliente
            # troca de tema com a lista na tela, o token nao
            item.setData(TOM, tone)
            item.setForeground(QBrush(QColor(palette_for(self).resolve(tone))))
        if bold:
            fonte = item.font()
            fonte.setBold(True)
            item.setFont(fonte)
        if data is not None:
            item.setData(Qt.ItemDataRole.UserRole, data)
        return item

    def fill(self, linhas: list[list[QTableWidgetItem]], widths: dict[int, int] | None = None) -> None:
        """Preenche a tabela inteira de uma vez."""
        self.setRowCount(len(linhas))
        for indice, celulas in enumerate(linhas):
            for coluna, celula in enumerate(celulas):
                self.setItem(indice, coluna, celula)
        if widths:
            self.set_column_widths(widths)
        if linhas:
            self._alinhar_cabecalho(linhas[0])

    def _alinhar_cabecalho(self, primeira: list[QTableWidgetItem]) -> None:
        """O titulo da coluna fica do mesmo lado que o conteudo dela.

        Cabecalho centralizado sobre nome alinhado a esquerda (ou sobre valor
        alinhado a direita) faz a coluna parecer torta.
        """
        for coluna, celula in enumerate(primeira):
            titulo = self.horizontalHeaderItem(coluna)
            if titulo is None or celula is None:
                continue
            lado = Qt.AlignmentFlag(int(celula.textAlignment())) & (
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignHCenter
            )
            titulo.setTextAlignment(lado | Qt.AlignmentFlag.AlignVCenter)

    def selected_data(self, column: int = 0):
        row = self.currentRow()
        if row < 0:
            return None
        item = self.item(row, column)
        return item.data(Qt.ItemDataRole.UserRole) if item else None
