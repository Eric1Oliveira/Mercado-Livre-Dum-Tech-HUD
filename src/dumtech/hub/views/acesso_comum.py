"""As pecas que o login, o assistente e a tela de Usuarios dividem."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ...core.acesso import AcessoError
from ...ui.theme import Palette, Space, current_palette, font_for, palette_for
from ...ui.widgets.buttons import Button
from ...ui.widgets.common import Card, IconBadge, label, repolish

#: a faixa da marca: larga o bastante para o nome da loja, sem apertar o formulario
LARGURA_FAIXA = 320
#: a coluna do formulario nao estica em monitor grande
LARGURA_COLUNA = 440
BRANCO = "#FFFFFF"


def dizer(alvo, texto: str, tom: str = "muted") -> None:
    alvo.setText(texto)
    alvo.setProperty("tone", tom)
    alvo.setVisible(bool(texto))
    repolish(alvo)


def mensagem(erro: Exception) -> str:
    return str(erro) if isinstance(erro, AcessoError) else "Algo deu errado. Tente de novo."


def tom_do_erro(erro: Exception) -> str:
    return "warning" if isinstance(erro, AcessoError) else "danger"


def iniciais(nome: str) -> str:
    partes = (nome or "").split()
    if not partes:
        return "?"
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()


def _rotulo_claro(texto: str, papel: str, alfa: int = 255) -> QWidget:
    rotulo = label(texto, papel)
    cor = QColor(BRANCO)
    cor.setAlpha(alfa)
    rotulo.setStyleSheet(f"color: rgba({cor.red()}, {cor.green()}, {cor.blue()}, {alfa});")
    rotulo.setWordWrap(True)
    return rotulo


class FaixaDaMarca(QWidget):
    """O degrade do Inicio de pe, ao lado do formulario: a porta tem cara de Hub."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette_for(parent) if parent else current_palette()
        self.setFixedWidth(LARGURA_FAIXA)
        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(Space.xxl, Space.xxl, Space.xl, Space.xl)
        coluna.setSpacing(Space.sm)

        marca = QHBoxLayout()
        marca.setSpacing(10)
        marca.addWidget(IconBadge("grid", "accent", size=34, radius=10, estilo="solid"))
        marca.addWidget(_rotulo_claro("DumTech Hub", "brand"))
        marca.addStretch(1)
        coluna.addLayout(marca)
        coluna.addStretch(1)

        self.titulo = _rotulo_claro("", "hero")
        coluna.addWidget(self.titulo)
        self.texto = _rotulo_claro("", "body", 215)
        coluna.addWidget(self.texto)
        coluna.addSpacing(Space.md)
        self.miolo = QVBoxLayout()
        self.miolo.setSpacing(Space.sm)
        coluna.addLayout(self.miolo)
        coluna.addStretch(1)

    def definir(self, titulo: str, texto: str = "") -> None:
        self.titulo.setText(titulo)
        self.texto.setText(texto)
        self.texto.setVisible(bool(texto))

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, evento) -> None:  # noqa: N802 (Qt)
        p = self._palette
        pintor = QPainter(self)
        area = QRectF(self.rect())
        degrade = QLinearGradient(area.topLeft(), area.bottomRight())
        degrade.setColorAt(0.0, QColor(p.hero_a))
        degrade.setColorAt(1.0, QColor(p.hero_b))
        pintor.fillRect(area, degrade)
        brilho = QRadialGradient(area.width() * 0.2, area.height() * 1.05, area.width())
        brilho.setColorAt(0.0, QColor(255, 255, 255, 46))
        brilho.setColorAt(1.0, QColor(255, 255, 255, 0))
        pintor.fillRect(area, brilho)
        pintor.end()


class AvatarPessoa(QWidget):
    """O circulo com as iniciais, nas listas de contas."""

    LADO = 36

    def __init__(self, nome: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._iniciais = iniciais(nome)
        self._palette = palette_for(parent) if parent else current_palette()
        self.setFixedSize(self.LADO, self.LADO)

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, evento) -> None:  # noqa: N802 (Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(self._palette.accent_soft))
        pintor.drawEllipse(QRectF(self.rect()))
        fonte = font_for("caption")
        fonte.setWeight(QFont.Weight.Bold)
        pintor.setFont(fonte)
        pintor.setPen(QColor(self._palette.accent))
        pintor.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self._iniciais)
        pintor.end()


class BotaoPessoa(QPushButton):
    """Uma pessoa da loja em um clique: o avatar com as iniciais e o nome."""

    LARGURA = 92
    ALTURA = 92
    AVATAR = 48

    escolhida = Signal(str)

    def __init__(self, nome: str, login: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.login = login
        self._nome = nome.split()[0] if nome.split() else login
        self._iniciais = iniciais(nome)
        self._palette = palette_for(parent) if parent else current_palette()
        self.setCheckable(True)
        self.setFixedSize(self.LARGURA, self.ALTURA)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"Entrar como {nome}")
        self.setToolTip(login)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.clicked.connect(lambda: self.escolhida.emit(self.login))

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, evento) -> None:  # noqa: N802 (Qt)
        p = self._palette
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.isChecked() or self.underMouse() or self.hasFocus():
            pintor.setPen(QColor(p.accent) if self.isChecked() or self.hasFocus() else QColor(p.border))
            pintor.setBrush(QColor(p.accent_soft if self.isChecked() else p.surface_hover))
            pintor.drawRoundedRect(area, 12, 12)

        circulo = QRectF((self.width() - self.AVATAR) / 2, 9, self.AVATAR, self.AVATAR)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(p.accent if self.isChecked() else p.accent_soft))
        pintor.drawEllipse(circulo)
        fonte = font_for("strong")
        fonte.setWeight(QFont.Weight.ExtraBold)
        pintor.setFont(fonte)
        pintor.setPen(QColor(p.on_accent if self.isChecked() else p.accent))
        pintor.drawText(circulo, Qt.AlignmentFlag.AlignCenter, self._iniciais)

        pintor.setFont(font_for("caption"))
        pintor.setPen(QColor(p.text))
        faixa = QRectF(4, circulo.bottom() + 5, self.width() - 8, 18)
        nome = pintor.fontMetrics().elidedText(self._nome, Qt.TextElideMode.ElideRight, int(faixa.width()))
        pintor.drawText(faixa, Qt.AlignmentFlag.AlignCenter, nome)
        pintor.end()


class Cracha(Card):
    """O crachá de quem entrou na equipe: o que o dono passa para a pessoa."""

    def __init__(self, nome: str, login: str, senha: str, funcao: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=Space.md)
        self.login = login
        self.senha = senha
        self.nome = nome
        linha = QHBoxLayout()
        linha.setSpacing(Space.md)
        linha.addWidget(IconBadge("user", "accent", size=38, radius=19))
        textos = QVBoxLayout()
        textos.setSpacing(1)
        textos.addWidget(label(nome + (f"  ·  {funcao}" if funcao else ""), "strong"))
        self.dados = label(f"{login}  ·  {senha}", "mono")
        self.dados.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        textos.addWidget(self.dados)
        linha.addLayout(textos, 1)
        self.botao = Button("Copiar acesso", "copy", "ghost")
        self.botao.setAccessibleName(f"Copiar o acesso de {nome}")
        self.botao.clicked.connect(self.copiar)
        linha.addWidget(self.botao, 0, Qt.AlignmentFlag.AlignVCenter)
        self.body.addLayout(linha)

    def texto(self) -> str:
        return (f"Seu acesso ao DumTech Hub\nLogin: {self.login}\nSenha: {self.senha}\n"
                "No primeiro acesso, o Hub pede para você criar a sua senha.")

    def copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.texto())
        self.botao.setText("  Copiado")
