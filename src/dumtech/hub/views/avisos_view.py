"""O que aparece no "Hoje", e com quanta antecedencia.

O prazo certo nao existe: quem vende a prazo quer saber da conta com sete dias,
quem trabalha com obra quer trinta. Em vez de escolher por eles - ou de atender
o telefone para explicar por que o aviso apareceu - o numero fica aqui.

So aparecem os tipos dos aplicativos que a licenca liberou: uma tela cheia de
ajustes para modulos que a pessoa nao comprou so confunde.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core import confirmacoes
from ...core.avisos import TIPOS, Config
from ...ui.theme import Space
from ...ui.widgets.buttons import Button
from ...ui.widgets.common import Card, EmptyState, label, separator


class AvisosView(QWidget):
    """Liga, desliga e ajusta os prazos de cada aviso."""

    alterada = Signal()

    def __init__(self, config: Config, registry=None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.registry = registry
        self._linhas: dict[str, tuple[QCheckBox, QSpinBox | None]] = {}

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(Space.lg)
        raiz.addWidget(
            label("O Inicio mostra o que precisa de atencao. Voce decide o que "
                  "entra e com quanta antecedencia.", "subtitle")
        )

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.Shape.NoFrame)
        raiz.addWidget(self.area, 1)

        raiz.addWidget(self._card_perguntas())

        self.vazio = EmptyState(
            "Nenhum aplicativo liberado",
            "Os avisos aparecem conforme os aplicativos que a sua licenca libera.",
            "alert",
        )
        raiz.addWidget(self.vazio, 1)

        self.refresh()

    def _card_perguntas(self) -> Card:
        """A saida do "nao perguntar de novo" - senao ele e uma porta so de ida."""
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Perguntas de confirmacao", "section"))
        card.body.addWidget(separator())

        linha = QHBoxLayout()
        linha.setSpacing(Space.md)
        self.estado_perguntas = label("", "muted")
        self.estado_perguntas.setWordWrap(True)
        linha.addWidget(self.estado_perguntas, 1)
        self.botao_perguntas = Button("Voltar a perguntar tudo", "refresh")
        self.botao_perguntas.clicked.connect(self._voltar_a_perguntar)
        linha.addWidget(self.botao_perguntas)
        card.body.addLayout(linha)
        return card

    def _voltar_a_perguntar(self) -> None:
        confirmacoes.voltar_a_perguntar()
        self._atualizar_perguntas()
        self.alterada.emit()

    def _atualizar_perguntas(self) -> None:
        caladas = [texto for chave, texto in confirmacoes.PERGUNTAS.items()
                   if not confirmacoes.deve_perguntar(chave)]
        if caladas:
            self.estado_perguntas.setText(
                "Voce pediu para nao perguntar mais: " + "; ".join(caladas).lower() + "."
            )
        else:
            self.estado_perguntas.setText(
                "O programa confirma antes de excluir um registro e antes de "
                "fechar um aplicativo."
            )
        self.botao_perguntas.setEnabled(bool(caladas))

    # ------------------------------------------------------------------- dados
    def _liberados(self) -> dict[str, str]:
        """app_id -> nome curto, so dos aplicativos que a licenca liberou."""
        if self.registry is None:
            return {tipo.app_id: tipo.app_id.capitalize() for tipo in TIPOS}
        return {
            entrada.app_id: entrada.manifest.short_name
            for entrada in self.registry.available()
        }

    def refresh(self) -> None:
        self._atualizar_perguntas()
        liberados = self._liberados()
        tipos = [tipo for tipo in TIPOS if tipo.app_id in liberados]

        self.vazio.setVisible(not tipos)
        self.area.setVisible(bool(tipos))
        self._linhas.clear()

        dentro = QWidget()
        coluna = QVBoxLayout(dentro)
        coluna.setContentsMargins(0, 0, Space.sm, 0)
        coluna.setSpacing(Space.md)

        for app_id in dict.fromkeys(tipo.app_id for tipo in tipos):
            coluna.addWidget(self._card(
                liberados[app_id], [t for t in tipos if t.app_id == app_id]
            ))
        coluna.addStretch(1)
        self.area.setWidget(dentro)

    def _card(self, nome: str, tipos) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label(nome, "section"))
        card.body.addWidget(separator())

        for posicao, tipo in enumerate(tipos):
            if posicao:
                card.body.addWidget(separator())
            card.body.addLayout(self._linha(tipo))
        return card

    def _linha(self, tipo) -> QVBoxLayout:
        bloco = QVBoxLayout()
        bloco.setSpacing(2)

        ligado = QCheckBox(tipo.titulo)
        ligado.setChecked(self.config.ligado(tipo.chave))
        ligado.stateChanged.connect(lambda _=0, t=tipo: self._salvar(t))
        bloco.addWidget(ligado)

        explicacao = label(tipo.explicacao, "muted")
        explicacao.setWordWrap(True)
        explicacao.setContentsMargins(26, 0, 0, 0)
        bloco.addWidget(explicacao)

        dias = None
        if tipo.dias is not None:
            linha = QHBoxLayout()
            linha.setContentsMargins(26, Space.xs, 0, 0)
            linha.setSpacing(Space.sm)
            linha.addWidget(label(tipo.rotulo_dias, "caption"))
            dias = QSpinBox()
            dias.setRange(tipo.minimo, tipo.maximo)
            dias.setValue(self.config.dias(tipo.chave))
            dias.setSuffix(" dias")
            dias.setFixedWidth(110)
            dias.valueChanged.connect(lambda _=0, t=tipo: self._salvar(t))
            linha.addWidget(dias)
            linha.addStretch(1)
            bloco.addLayout(linha)

        self._linhas[tipo.chave] = (ligado, dias)
        return bloco

    # ------------------------------------------------------------------- acoes
    def _salvar(self, tipo) -> None:
        ligado, dias = self._linhas[tipo.chave]
        self.config.definir(
            tipo.chave, ligado=ligado.isChecked(),
            dias=dias.value() if dias is not None else None,
        )
        if dias is not None:
            dias.setEnabled(ligado.isChecked())
        self.alterada.emit()
