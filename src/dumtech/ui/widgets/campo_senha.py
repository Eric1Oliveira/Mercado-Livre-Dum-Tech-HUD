"""Os campos de quem esta entrando: senha com olho, medidor e codigo do e-mail."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from ...core.acesso import forca_da_senha
from .. import icons
from ..theme import Control, Palette, current_palette, palette_for
from .common import label, repolish


class CampoSenha(QLineEdit):
    """Senha oculta, com o olho para conferir o que esta digitando."""

    def __init__(self, dica: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(dica)
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.setMaxLength(72)
        self.setMinimumHeight(Control.primary)
        self._palette = palette_for(parent) if parent else current_palette()
        self.olho = self.addAction(icons.icon("eye", self._palette.text_muted, 18),
                                   QLineEdit.ActionPosition.TrailingPosition)
        self.olho.triggered.connect(self.alternar)
        self._pintar()

    @property
    def visivel(self) -> bool:
        return self.echoMode() == QLineEdit.EchoMode.Normal

    def alternar(self) -> None:
        self.setEchoMode(QLineEdit.EchoMode.Password if self.visivel else QLineEdit.EchoMode.Normal)
        self._pintar()

    def ocultar(self) -> None:
        if self.visivel:
            self.alternar()

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self._pintar()

    def _pintar(self) -> None:
        self.olho.setIcon(icons.icon("eye_off" if self.visivel else "eye", self._palette.text_muted, 18))
        self.olho.setToolTip("Ocultar senha" if self.visivel else "Mostrar senha")

    def hideEvent(self, evento) -> None:  # noqa: N802 (Qt)
        # saiu da tela: quem chegar depois nao encontra a senha aberta
        self.ocultar()
        super().hideEvent(evento)


class MedidorDeSenha(QWidget):
    """Tres tracos e uma palavra: orienta enquanto a pessoa escolhe a senha."""

    ROTULOS = ("Ainda não serve", "Fraca", "Boa", "Forte")
    TOKENS = ("danger", "warning", "accent", "success")
    ALTURA_TRACO = 4
    LARGURA_TRACOS = 132

    def __init__(self, campo: QLineEdit, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette_for(parent) if parent else current_palette()
        self.forca = 0
        self.setFixedHeight(18)
        linha = QHBoxLayout(self)
        linha.setContentsMargins(self.LARGURA_TRACOS + 12, 0, 0, 0)
        self.rotulo = label("", "dim")
        linha.addWidget(self.rotulo)
        linha.addStretch(1)
        campo.textChanged.connect(self.atualizar)
        self.atualizar(campo.text())

    def atualizar(self, senha: str) -> None:
        self.forca = forca_da_senha(senha)
        self.rotulo.setText(self.ROTULOS[self.forca] if senha else "")
        self.rotulo.setProperty("tone", self.TOKENS[self.forca])
        repolish(self.rotulo)
        self.vazio = not senha
        self.update()

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, evento) -> None:  # noqa: N802 (Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pintor.setPen(Qt.PenStyle.NoPen)
        vao = 4
        largura = (self.LARGURA_TRACOS - vao * 2) / 3
        topo = (self.height() - self.ALTURA_TRACO) / 2
        ligado = QColor(self._palette.resolve(self.TOKENS[self.forca]))
        desligado = QColor(self._palette.border_strong)
        for indice in range(3):
            aceso = not self.vazio and indice < max(self.forca, 1)
            pintor.setBrush(ligado if aceso else desligado)
            pintor.drawRoundedRect(QRectF(indice * (largura + vao), topo, largura, self.ALTURA_TRACO), 2, 2)
        pintor.end()


class CampoCodigo(QLineEdit):
    """Os 6 numeros que chegam no e-mail, grandes o bastante para conferir."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMaxLength(6)
        self.setPlaceholderText("000000")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(46)
        fonte = self.font()
        fonte.setPointSizeF(15)
        fonte.setLetterSpacing(fonte.SpacingType.AbsoluteSpacing, 4)
        self.setFont(fonte)
