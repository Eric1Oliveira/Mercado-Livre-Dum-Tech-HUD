"""Erro inesperado: o que o cliente ve e o que o suporte recebe.

Um erro que some sem deixar rastro vira "o sistema fechou sozinho" no telefone,
e voce sem nada para olhar. Aqui todo erro nao tratado:

1. vai inteiro para o arquivo de log;
2. aparece numa caixa que explica o que fazer, com o texto pronto para copiar.

O programa **continua aberto**: um erro numa tela nao e motivo para o cliente
perder o que estava fazendo em outra.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.database import aviso_so_consulta, e_so_consulta
from ..core.diagnostico import onde, relatorio, resumo
from .theme import Space, apply_window_theme, current_palette, palette_for
from .widgets.buttons import Button
from .widgets.common import label, repolish, separator, tone_label

logger = logging.getLogger(__name__)

#: caixa aberta agora: um erro em cascata nao pode virar vinte janelas
_mostrando = False


class ErroDialog(QDialog):
    """Explica o que aconteceu e entrega o relatorio pronto para o suporte."""

    def __init__(
        self,
        erro: BaseException,
        texto: str,
        log: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.texto = texto
        self.log = log

        self.setWindowTitle("Erro inesperado")
        self.setModal(True)
        self.setMinimumWidth(620)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)

        cabecalho = QVBoxLayout()
        cabecalho.setSpacing(4)
        cabecalho.addWidget(label("Alguma coisa deu errado", "section"))
        aviso = tone_label(
            "O programa continua aberto e os dados não foram perdidos. "
            "Se o problema se repetir, clique em 'Copiar relatório' e mande "
            "para o suporte.",
            "muted",
        )
        aviso.setWordWrap(True)
        cabecalho.addWidget(aviso)
        raiz.addLayout(cabecalho)
        raiz.addWidget(separator())

        detalhe = tone_label(f"{resumo(erro)}\n{onde(erro)}", "danger", "strong")
        detalhe.setWordWrap(True)
        detalhe.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        raiz.addWidget(detalhe)

        self.corpo = QPlainTextEdit(texto)
        self.corpo.setReadOnly(True)
        self.corpo.setFont(self._fonte())
        # relatorio de erro nao pode ser requebrado: as linhas tem significado
        self.corpo.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.corpo.setMinimumHeight(220)
        self.corpo.setVisible(False)
        raiz.addWidget(self.corpo, 1)

        self.recado = label("", "muted")
        raiz.addWidget(self.recado)
        raiz.addLayout(self._botoes())

        apply_window_theme(self, palette_for(parent) if parent else current_palette())

    @staticmethod
    def _fonte() -> QFont:
        fonte = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fonte.setPointSizeF(9.0)
        return fonte

    def _botoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        self.botao_detalhes = Button("Ver detalhes", "caret-down", "ghost")
        self.botao_detalhes.clicked.connect(self._alternar_detalhes)
        linha.addWidget(self.botao_detalhes)
        linha.addStretch(1)

        if self.log is not None:
            abrir = Button("Abrir o log", "external")
            abrir.clicked.connect(self._abrir_log)
            linha.addWidget(abrir)

        copiar = Button("Copiar relatório", "file")
        copiar.clicked.connect(self._copiar)
        linha.addWidget(copiar)

        fechar = Button("Continuar", "check", "primary")
        fechar.setDefault(True)
        fechar.clicked.connect(self.accept)
        linha.addWidget(fechar)
        return linha

    def _alternar_detalhes(self) -> None:
        mostrar = not self.corpo.isVisible()
        self.corpo.setVisible(mostrar)
        self.botao_detalhes.setText("  Esconder detalhes" if mostrar else "  Ver detalhes")
        self.botao_detalhes.set_icon_name("caret-up" if mostrar else "caret-down")
        self.adjustSize()

    def _copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.texto)
        self._dizer("Relatório copiado. Cole no WhatsApp ou no e-mail do suporte.")

    def _abrir_log(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log)))

    def _dizer(self, texto: str, tom: str = "success") -> None:
        self.recado.setText(texto)
        self.recado.setProperty("tone", tom)
        repolish(self.recado)


def tratar(erro: BaseException, versao: str = "", log: Path | None = None) -> str:
    """Registra o erro e mostra a caixa. Devolve o relatorio (util em teste)."""
    global _mostrando

    # botao de tela em modo consulta: nao e defeito, nao vai para o relatorio
    if e_so_consulta(erro) and QApplication.instance() is not None:
        aviso = aviso_so_consulta()
        QMessageBox.information(QApplication.activeWindow(), "Somente consulta", aviso)
        return aviso

    texto = relatorio(erro, versao)
    logger.error("Erro nao tratado\n%s", texto)

    # sem janela viva (erro na abertura, ou ja fechando) o log e o que sobra
    if _mostrando or QApplication.instance() is None:
        return texto

    _mostrando = True
    try:
        janela = QApplication.activeWindow()
        ErroDialog(erro, texto, log, janela).exec()
    except Exception:  # noqa: BLE001 - falhar ao mostrar o erro nao pode matar o app
        logger.exception("Nao foi possivel mostrar a caixa de erro")
    finally:
        _mostrando = False
    return texto


def instalar(versao: str = "", log: Path | None = None) -> None:
    """Liga o tratador para o resto da vida do programa.

    Um erro dentro de um slot do Qt chega aqui e o programa continua rodando -
    confirmado no PySide6 6.8. Sem isto, o traceback iria para o stderr, que no
    executavel nao existe.
    """
    anterior = sys.excepthook

    def gancho(tipo, erro, tb) -> None:
        if issubclass(tipo, KeyboardInterrupt):
            anterior(tipo, erro, tb)
            return
        if erro.__traceback__ is None:
            erro.__traceback__ = tb
        tratar(erro, versao, log)

    sys.excepthook = gancho
