"""O que mudou na versao: a lista curta e um "OK, entendi".

Mesmo corpo do anuncio (`anuncio_dialog.py`), outro proposito: aqui nao ha
nada a vender. Cada linha leva o icone e a cor do modulo que mudou - a pessoa
reconhece de longe o "Balcao" ou a "Agenda" que ela usa todo dia.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from ...ui.theme import Space, apply_window_theme, palette_for
from ...ui.widgets.buttons import Button
from ...ui.widgets.common import IconBadge, Pill, label, separator
from ...ui.widgets.rolagem import rolavel_no_dialogo

LARGURA = 480


class NovidadesDialog(QDialog):
    """`modulos`: app_id -> manifesto, para o icone e a cor de cada linha."""

    def __init__(
        self,
        novidades,
        versao: str,
        modulos: dict | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        modulos = modulos or {}
        self.setWindowTitle("Novidades do DumTech Hub")
        self.setModal(True)
        self.setFixedWidth(LARGURA)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 24, 28, 22)
        raiz.setSpacing(Space.md)

        topo = QHBoxLayout()
        topo.setSpacing(Space.md)
        topo.addWidget(IconBadge("check", "success", size=40, radius=12), 0,
                       Qt.AlignmentFlag.AlignTop)
        marca = QVBoxLayout()
        marca.setSpacing(3)
        etiqueta = QHBoxLayout()
        etiqueta.addWidget(Pill("ATUALIZADO", "success"))
        etiqueta.addStretch(1)
        marca.addLayout(etiqueta)
        marca.addWidget(label(f"DumTech Hub {versao}", "dim"))
        topo.addLayout(marca, 1)
        raiz.addLayout(topo)

        titulo = label("O que mudou para você", "title")
        titulo.setWordWrap(True)
        raiz.addWidget(titulo)

        # quem pulou versoes recebe a lista de todas: num notebook ela passava
        # da tela e levava o "OK, entendi" junto. A lista rola; o botao fica
        itens = QWidget()
        lista = QVBoxLayout(itens)
        lista.setContentsMargins(0, 0, 0, 0)
        lista.setSpacing(Space.md)
        for novidade in novidades:
            lista.addLayout(self._linha(novidade, modulos.get(novidade.app_id)))
        lista.addStretch(1)
        raiz.addWidget(rolavel_no_dialogo(itens), 1)

        raiz.addSpacing(Space.xs)
        raiz.addWidget(separator())

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        self.botao_ok = Button("OK, entendi", "check", "primary")
        self.botao_ok.setMinimumHeight(38)
        self.botao_ok.setDefault(True)
        self.botao_ok.clicked.connect(self.accept)
        botoes.addWidget(self.botao_ok)
        raiz.addLayout(botoes)

        apply_window_theme(self, palette_for(parent))

    @staticmethod
    def _linha(novidade, manifesto) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.md)
        icone = getattr(manifesto, "icon", "") or "info"
        cor = getattr(manifesto, "accent", "") or "accent"
        linha.addWidget(IconBadge(icone, cor, size=32, radius=10), 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        nome = label(novidade.titulo, "strong")
        nome.setWordWrap(True)
        textos.addWidget(nome)
        if novidade.texto:
            corpo = label(novidade.texto, "muted")
            corpo.setWordWrap(True)
            textos.addWidget(corpo)
        linha.addLayout(textos, 1)
        return linha
