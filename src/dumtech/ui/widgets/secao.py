"""Um bloco que abre e fecha: o detalhe existe, mas nao atrapalha.

POR QUE ISTO EXISTE

Formulario de sistema de gestao cresce por acumulo: cada cliente pede um
campo, e um ano depois abrir uma ordem de servico pede dezesseis respostas -
sendo que catorze quase sempre ficam vazias. Quem sofre e o balconista, que
tem gente esperando na frente dele.

A saida nao e apagar campo (alguem usa), e sim ordena-los por frequencia: o
que todo mundo preenche fica a vista, o resto mora atras de um clique. Este
widget e esse clique.

COMO USA

    detalhes = Secao("Mais detalhes", "garantia, acessorios, senha")
    detalhes.form.addRow("Garantia", campo_garantia)
    layout.addWidget(detalhes)

A secao nasce fechada. `Secao(..., aberta=True)` comeca aberta, e
`marcar_preenchida(True)` acende um ponto no titulo para avisar que tem coisa
escrita ali dentro - senao o que foi digitado some junto com o bloco.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..theme import Control, Space, current_palette
from .buttons import Button
from .common import label, repolish


class Secao(QFrame):
    """Cabecalho clicavel e um formulario que aparece quando se quer."""

    def __init__(
        self,
        titulo: str,
        resumo: str = "",
        aberta: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self._aberta = aberta

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(Space.md, Space.sm, Space.md, Space.sm)
        raiz.setSpacing(Space.sm)

        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        self.botao = Button(titulo, "forward", "ghost")
        self.botao.setCheckable(True)
        self.botao.setChecked(aberta)
        self.botao.clicked.connect(lambda: self.abrir(not self._aberta))
        linha.addWidget(self.botao)

        self.resumo = label(resumo, "dim")
        linha.addWidget(self.resumo, 1)

        # o ponto que avisa "tem coisa escrita aqui dentro"
        self.marca = label("", "accent")
        linha.addWidget(self.marca)
        raiz.addLayout(linha)

        self.corpo = QWidget()
        self.form = QFormLayout(self.corpo)
        self.form.setContentsMargins(Space.sm, Space.sm, 0, Space.xs)
        self.form.setHorizontalSpacing(16)
        self.form.setVerticalSpacing(12)
        self.form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        # entra no layout ANTES de mudar a visibilidade: widget sem pai que
        # recebe setVisible(True) vira uma janela solta piscando na tela
        raiz.addWidget(self.corpo)
        self.corpo.setVisible(aberta)
        self._pintar_seta()

    # ------------------------------------------------------------------ campos
    def add_row(self, rotulo: str, campo) -> None:
        """Mesma linha de rotulo e campo dos formularios da plataforma."""
        texto = label(rotulo, "field")
        texto.setMinimumHeight(Control.field)
        texto.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.form.addRow(texto, campo)

    # ------------------------------------------------------------------ estado
    @property
    def aberta(self) -> bool:
        return self._aberta

    def abrir(self, sim: bool = True) -> None:
        self._aberta = bool(sim)
        self.botao.setChecked(self._aberta)
        self.corpo.setVisible(self._aberta)
        self._pintar_seta()

    def marcar_preenchida(self, sim: bool) -> None:
        """Acende (ou apaga) o aviso de que ha conteudo escondido aqui."""
        self.marca.setText("●" if sim else "")

    def apply_theme(self, palette=None) -> None:
        self._pintar_seta(palette)
        repolish(self)

    def _pintar_seta(self, palette=None) -> None:
        cor = (palette or current_palette()).text_muted
        self.botao.setIcon(icons.icon("in" if self._aberta else "forward", cor, 16))
