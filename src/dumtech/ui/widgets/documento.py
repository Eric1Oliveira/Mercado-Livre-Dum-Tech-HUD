"""A folha A4 na tela, do jeito que sai no PDF.

Duas coisas justificam esta janela existir separada do `ComprovanteDialog`:
o papel e branco (documento e branco, mesmo com o programa no tema escuro) e
a acao principal nao e imprimir, e **gerar o arquivo** para mandar ao cliente.

Quando existe tambem a versao de bobina, ela vem junto: o mesmo botao serve
para quem manda por e-mail e para quem imprime na termica do balcao.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QScrollArea,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import documento as doc
from ..theme import Space, apply_window_theme, palette_for
from .buttons import Button
from .common import label, repolish, separator

FOLHA = 0
BOBINA = 1


class DocumentoDialog(QDialog):
    """Mostra a folha A4, salva em PDF e imprime."""

    def __init__(
        self,
        html: str,
        titulo: str = "Documento",
        arquivo: str = "documento",
        texto_bobina: str = "",
        empresa=None,
        paths=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.html = html
        self.arquivo = arquivo
        self.texto_bobina = texto_bobina
        self.empresa = empresa
        self.paths = paths
        self.salvo: Path | None = None

        self.setWindowTitle(titulo)
        self.setModal(True)
        self.resize(880, 760)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)

        cabecalho = QVBoxLayout()
        cabecalho.setSpacing(2)
        cabecalho.addWidget(label(titulo, "section"))
        cabecalho.addWidget(label("Salve em PDF para mandar ao cliente", "muted"))
        raiz.addLayout(cabecalho)
        raiz.addWidget(separator())

        self.paginas = QStackedWidget()
        self.paginas.addWidget(self._folha())
        self.paginas.addWidget(self._bobina())
        raiz.addWidget(self.paginas, 1)

        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        raiz.addWidget(self.aviso)
        raiz.addLayout(self._botoes())

        apply_window_theme(self, palette_for(parent))

    # ------------------------------------------------------------------ pedacos
    def _folha(self) -> QWidget:
        """O papel, branco e centralizado, como numa visualizacao de impressao."""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        area.setFrameShape(QScrollArea.Shape.NoFrame)

        margem = round(doc.MARGEM_MM / 25.4 * doc.RESOLUCAO)
        self.papel = QTextBrowser()
        self.papel.setObjectName("folha")
        self.papel.setFixedWidth(doc.LARGURA)
        self.papel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.papel.setStyleSheet(
            f"QTextBrowser#folha {{ background-color: #ffffff; border: none;"
            f" padding: {margem}px; }}"
        )
        self.papel.setDocument(doc.render(self.html, self.empresa, self.paths))
        self.papel.document().setDocumentMargin(0)
        # sem barra propria: quem rola e a area, e o papel cresce ate acabar
        altura = self.papel.document().size().height() + 2 * margem
        self.papel.setFixedHeight(int(altura) + 4)

        dentro = QWidget()
        coluna = QVBoxLayout(dentro)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        coluna.addWidget(self.papel)
        area.setWidget(dentro)
        return area

    def _bobina(self) -> QWidget:
        fonte = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fonte.setPointSizeF(10.0)
        self.tira = QPlainTextEdit(self.texto_bobina)
        self.tira.setReadOnly(True)
        self.tira.setFont(fonte)
        self.tira.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        return self.tira

    def _botoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)

        if self.texto_bobina:
            self.botao_formato = Button("Ver versão de bobina", "file", "ghost")
            self.botao_formato.clicked.connect(self._trocar_formato)
            linha.addWidget(self.botao_formato)

        self.botao_abrir = Button("Abrir o PDF", "external", "ghost")
        self.botao_abrir.clicked.connect(self._abrir_salvo)
        self.botao_abrir.setVisible(False)
        linha.addWidget(self.botao_abrir)

        linha.addStretch(1)

        imprimir = Button("Imprimir", "file")
        imprimir.clicked.connect(self._imprimir)
        linha.addWidget(imprimir)

        salvar = Button("Salvar em PDF", "check", "primary")
        salvar.setMinimumHeight(38)
        salvar.clicked.connect(self._salvar)
        linha.addWidget(salvar)

        fechar = Button("Fechar")
        fechar.clicked.connect(self.accept)
        linha.addWidget(fechar)
        return linha

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------- acoes
    def _trocar_formato(self) -> None:
        folha = self.paginas.currentIndex() == BOBINA
        self.paginas.setCurrentIndex(FOLHA if folha else BOBINA)
        self.botao_formato.setText(
            "Ver versão de bobina" if folha else "Ver a folha A4"
        )

    def caminho_sugerido(self) -> Path:
        pasta = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        return Path(pasta or Path.home()) / f"{nome_de_arquivo(self.arquivo)}.pdf"

    def _salvar(self) -> None:
        escolhido, _ = QFileDialog.getSaveFileName(
            self, "Salvar documento em PDF", str(self.caminho_sugerido()),
            "Documento PDF (*.pdf)"
        )
        if not escolhido:
            return
        self.gravar(Path(escolhido))

    def gravar(self, destino: Path) -> bool:
        """Separado do dialogo para poder ser testado sem abrir caixa nenhuma."""
        try:
            self.salvo = doc.salvar_pdf(self.html, destino, self.empresa, self.paths)
        except OSError as erro:
            self._dizer(f"Não foi possível gravar o PDF: {erro}", "danger")
            return False
        self.botao_abrir.setVisible(True)
        self._dizer(f"PDF gravado em {self.salvo}.", "success")
        return True

    def _abrir_salvo(self) -> None:
        if self.salvo is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.salvo)))

    def _imprimir(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        impressora = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialogo = QPrintDialog(impressora, self)
        dialogo.setWindowTitle("Imprimir documento")
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        if self.paginas.currentIndex() == BOBINA:
            self.tira.print_(impressora)
        else:
            doc.imprimir(self.html, impressora, self.empresa, self.paths)
        self._dizer("Enviado para a impressora.", "success")


def nome_de_arquivo(texto: str) -> str:
    """Windows recusa : * ? " < > | / \\ - e o cliente nao tem culpa disso."""
    limpo = re.sub(r'[<>:"/\\|?*]+', " ", texto or "documento")
    limpo = re.sub(r"\s+", " ", limpo).strip(" .")
    return limpo or "documento"
