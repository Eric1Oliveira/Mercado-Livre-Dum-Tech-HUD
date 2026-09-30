"""Comprovante na tela, do mesmo jeito que sai no papel.

O texto vem em 40 colunas (`ui/recibo.py`) e e mostrado em fonte monoespacada:
o que aparece aqui e exatamente o que a impressora recebe. Usado pelo Vendas
(venda, fechamento de caixa) e pela Ordem de Servico (entrada, entrega).
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..theme import Space, apply_window_theme, palette_for
from .buttons import Button
from .common import label, repolish, separator


class ComprovanteDialog(QDialog):
    """Mostra, copia e imprime um comprovante."""

    def __init__(
        self,
        texto: str,
        titulo: str = "Comprovante",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.texto = texto

        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumSize(460, 560)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)

        cabecalho = QVBoxLayout()
        cabecalho.setSpacing(2)
        cabecalho.addWidget(label(titulo, "section"))
        cabecalho.addWidget(label("Confira antes de imprimir", "muted"))
        raiz.addLayout(cabecalho)
        raiz.addWidget(separator())

        self.papel = QPlainTextEdit(texto)
        self.papel.setReadOnly(True)
        self.papel.setFont(self._fonte())
        self.papel.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        raiz.addWidget(self.papel, 1)

        self.aviso = label("", "muted")
        raiz.addWidget(self.aviso)
        raiz.addLayout(self._botoes())

        apply_window_theme(self, palette_for(parent))

    @staticmethod
    def _fonte() -> QFont:
        """Monoespacada de verdade: com fonte proporcional o papel desalinha."""
        fonte = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fonte.setPointSizeF(10.0)
        return fonte

    def _botoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.addStretch(1)

        copiar = Button("Copiar", "file")
        copiar.clicked.connect(self._copiar)
        linha.addWidget(copiar)

        imprimir = Button("Imprimir", "check", "primary")
        imprimir.clicked.connect(self._imprimir)
        linha.addWidget(imprimir)

        fechar = Button("Fechar")
        fechar.clicked.connect(self.accept)
        linha.addWidget(fechar)
        return linha

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    def _copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.texto)
        self._dizer("Comprovante copiado.", "success")

    def _imprimir(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        impressora = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialogo = QPrintDialog(impressora, self)
        dialogo.setWindowTitle("Imprimir comprovante")
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        self.papel.print_(impressora)
        self._dizer("Enviado para a impressora.", "success")
