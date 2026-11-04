"""O aviso da atualizacao forcada: uma contagem que nao se dispensa.

POR QUE NAO E UMA JANELA MODAL
    Modal trava o Hub inteiro, e a pessoa nao conseguiria terminar a venda que
    esta na tela - que e justamente para isso que o prazo existe. Entao e um
    cartao solto, sempre por cima, que nao rouba o foco do teclado e nao fecha.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ...ui.theme import Space, apply_window_theme, palette_for
from ...ui.widgets.buttons import Button
from ...ui.widgets.common import IconBadge, label

LARGURA = 400
MARGEM = 24


class ForcadaAviso(QWidget):
    """Conta o prazo e pede a instalacao. Quem instala e o Hub."""

    #: o prazo acabou, ou a pessoa clicou em "Instalar agora"
    instalar = Signal()

    def __init__(self, versao: str, segundos: int, janela: QWidget) -> None:
        # sem pai: filho de janela minimizada some junto, e o prazo correria escondido
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(LARGURA)
        self.versao = versao
        self.restam = max(0, int(segundos))
        self._janela = janela
        self._pode_fechar = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(20, 18, 20, 18)
        raiz.setSpacing(Space.sm)

        topo = QHBoxLayout()
        topo.setSpacing(Space.md)
        topo.addWidget(IconBadge("in", "accent", size=38, radius=12), 0, Qt.AlignmentFlag.AlignTop)
        cabeca = QVBoxLayout()
        cabeca.setSpacing(2)
        cabeca.addWidget(label("Atualização obrigatória", "title"))
        cabeca.addWidget(label(f"Versão {versao} do DumTech Hub", "muted"))
        topo.addLayout(cabeca, 1)
        raiz.addLayout(topo)

        explica = label(
            "Termine o que está fazendo. O Hub fecha, instala e abre sozinho. "
            "Seus dados não são tocados.", "body")
        explica.setWordWrap(True)
        raiz.addWidget(explica)

        rodape = QHBoxLayout()
        self.contagem = label("", "strong")
        rodape.addWidget(self.contagem, 1)
        self.botao_instalar = Button("Instalar agora", "in", "primary")
        self.botao_instalar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.botao_instalar.clicked.connect(self._acabou)
        rodape.addWidget(self.botao_instalar)
        raiz.addLayout(rodape)

        self._relogio = QTimer(self)
        self._relogio.setInterval(1000)
        self._relogio.timeout.connect(self._passo)
        self._mostrar_contagem()
        apply_window_theme(self, palette_for(janela))

    def mostrar(self) -> None:
        self.adjustSize()
        area = (self._janela.screen() or self.screen()).availableGeometry()
        self.move(area.right() - self.width() - MARGEM, area.bottom() - self.height() - MARGEM)
        self.show()
        self._relogio.start()

    def _mostrar_contagem(self) -> None:
        minutos, segundos = divmod(self.restam, 60)
        self.contagem.setText(f"Instala em {minutos}:{segundos:02d}")

    def _passo(self) -> None:
        self.restam = max(0, self.restam - 1)
        self._mostrar_contagem()
        if self.restam == 0:
            self._acabou()

    def _acabou(self) -> None:
        self._relogio.stop()
        self.instalar.emit()

    def encerrar(self) -> None:
        """So o Hub fecha este aviso: Alt+F4 nao adia a atualizacao."""
        self._relogio.stop()
        self._pode_fechar = True
        self.close()
        self.deleteLater()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._pode_fechar:
            super().closeEvent(event)
        else:
            event.ignore()
