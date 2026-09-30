"""A pergunta antes de uma acao que nao tem volta.

Uma caixa de confirmacao so vale a pena se for possivel calar: quem exclui
trinta linhas seguidas nao quer trinta perguntas. Por isso a janela tem
"nao perguntar de novo", e a resposta fica guardada nas preferencias.

Nao e um `QMessageBox`: ele nao tem onde por a caixinha, e o botao perigoso
precisa ter cara de perigoso.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from ...core import confirmacoes
from ..theme import Space, apply_window_theme, palette_for
from .buttons import Button
from .common import IconBadge, label


class ConfirmarDialog(QDialog):
    """Pergunta, com a opcao de nao perguntar mais."""

    def __init__(
        self,
        titulo: str,
        mensagem: str,
        rotulo_ok: str = "Confirmar",
        detalhe: str = "",
        perigoso: bool = True,
        pode_calar: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumWidth(430)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(24, 22, 24, 20)
        raiz.setSpacing(Space.md)

        topo = QHBoxLayout()
        topo.setSpacing(Space.md)
        topo.addWidget(
            IconBadge("alert" if perigoso else "info",
                      "danger" if perigoso else "accent", size=40, radius=12),
            0, Qt.AlignmentFlag.AlignTop,
        )
        texto = QVBoxLayout()
        texto.setSpacing(4)
        texto.addWidget(label(titulo, "cardTitle"))
        corpo = label(mensagem, "body")
        corpo.setWordWrap(True)
        texto.addWidget(corpo)
        if detalhe:
            aviso = label(detalhe, "dim")
            aviso.setWordWrap(True)
            texto.addWidget(aviso)
        topo.addLayout(texto, 1)
        raiz.addLayout(topo)

        self.calar = QCheckBox("Nao perguntar de novo")
        # no layout primeiro: `setVisible` sem pai abriria uma janela solta
        raiz.addWidget(self.calar)
        self.calar.setVisible(pode_calar)

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        cancelar = Button("Cancelar")
        cancelar.clicked.connect(self.reject)
        botoes.addWidget(cancelar)
        confirmar_botao = Button(rotulo_ok, "check" if not perigoso else "trash",
                                 "danger" if perigoso else "primary")
        confirmar_botao.setMinimumHeight(38)
        confirmar_botao.setDefault(True)
        confirmar_botao.clicked.connect(self.accept)
        botoes.addWidget(confirmar_botao)
        raiz.addLayout(botoes)

        apply_window_theme(self, palette_for(parent))


def confirmar(
    parent: QWidget | None,
    titulo: str,
    mensagem: str,
    chave: str = "",
    rotulo_ok: str = "Confirmar",
    detalhe: str = "",
    perigoso: bool = True,
) -> bool:
    """Pergunta e devolve se pode seguir.

    Com `chave`, a pessoa pode calar a pergunta para sempre - e a partir dai a
    resposta e sim sem abrir janela nenhuma.
    """
    if chave and not confirmacoes.deve_perguntar(chave):
        return True

    dialogo = ConfirmarDialog(titulo, mensagem, rotulo_ok, detalhe, perigoso,
                              pode_calar=bool(chave), parent=parent)
    aceitou = dialogo.exec() == QDialog.DialogCode.Accepted
    if aceitou and chave and dialogo.calar.isChecked():
        confirmacoes.nunca_mais(chave)
    return aceitou
