"""Os modelos de mensagem de WhatsApp, do jeito que o cliente quiser.

Esta tela existe para uma frase nao ficar escrita no codigo. O dono da loja tem
o tom dele, e o tom da loja de pecas nao e o tom do salao de beleza - so ele
sabe qual e.

Tres decisoes seguram a tela em pe: o texto ja vem pronto (ninguem precisa
escrever nada para usar), a previa mostra o resultado com dados de exemplo
(ninguem precisa "testar para ver") e os campos sao etiquetas clicaveis
(ninguem precisa decorar uma lista).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from ...core import mensagens
from ...core.mensagens import MODELOS, Mensageiro, Modelo
from ...ui.theme import Space
from ...ui.widgets import form
from ...ui.widgets.buttons import Button
from ...ui.widgets.rolagem import Rolagem
from ...ui.widgets.common import Card, label, repolish, separator, tone_label
from ...ui.widgets.rail import RailItem, RailSection

LARGURA_LISTA = 230
#: etiquetas por linha na grade de campos
COLUNAS_ETIQUETAS = 4


class MensagensView(QWidget):
    """Escolhe a mensagem a esquerda, escreve e ve o resultado a direita."""

    alterada = Signal()

    def __init__(self, settings, empresa=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.mensageiro = Mensageiro(settings, empresa)
        self.atual: Modelo = MODELOS[0]
        self._itens: list[RailItem] = []

        # a pagina inteira rola: em monitor pequeno isto vira uma barra
        # de rolagem fina em vez de um pedaco da tela faltando
        fora = QVBoxLayout(self)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.setSpacing(0)
        corpo = QWidget()
        fora.addWidget(Rolagem(corpo), 1)
        raiz = QVBoxLayout(corpo)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(Space.lg)
        raiz.addWidget(
            label("O WhatsApp abre com o texto pronto - quem envia é você.",
                  "subtitle")
        )

        colunas = QHBoxLayout()
        colunas.setSpacing(Space.lg)
        colunas.addWidget(self._lista())
        colunas.addWidget(self._editor(), 1)
        raiz.addLayout(colunas, 1)
        raiz.addLayout(self._acoes())

        self._escolher(0)

    # ------------------------------------------------------------------ pedacos
    def _lista(self) -> QWidget:
        caixa = QWidget()
        caixa.setFixedWidth(LARGURA_LISTA)
        coluna = QVBoxLayout(caixa)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(Space.xs)

        secao = RailSection()
        for indice, modelo in enumerate(MODELOS):
            item = RailItem(modelo.titulo, "file")
            item.clicked.connect(lambda _=False, i=indice: self._escolher(i))
            secao.add(item)
            self._itens.append(item)
        coluna.addWidget(secao)
        coluna.addStretch(1)
        return caixa

    def _editor(self) -> QWidget:
        caixa = QWidget()
        coluna = QVBoxLayout(caixa)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(Space.md)

        escrever = Card(padding=Space.lg)
        self.titulo = label("", "section")
        escrever.body.addWidget(self.titulo)
        self.quando = label("", "muted")
        self.quando.setWordWrap(True)
        escrever.body.addWidget(self.quando)
        escrever.body.addWidget(separator())

        self.corpo = form.area(altura=140)
        self.corpo.textChanged.connect(self._atualizar_previa)
        escrever.body.addWidget(self.corpo)

        escrever.body.addWidget(
            label("Clique para inserir no texto:", "dim")
        )
        # em grade, e nao em linha: sete etiquetas numa linha so ficam
        # espremidas ate o nome do campo sumir
        self.etiquetas = QGridLayout()
        self.etiquetas.setSpacing(Space.xs)
        escrever.body.addLayout(self.etiquetas)

        self.alerta = tone_label("", "warning", "caption")
        self.alerta.setWordWrap(True)
        escrever.body.addWidget(self.alerta)
        coluna.addWidget(escrever)

        previa = Card(padding=Space.lg)
        previa.body.addWidget(label("Como o cliente recebe", "section"))
        previa.body.addWidget(separator())
        self.balao = label("", "body")
        self.balao.setWordWrap(True)
        self.balao.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        previa.body.addWidget(self.balao, 1)
        coluna.addWidget(previa, 1)
        return caixa

    def _acoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        linha.addWidget(self.aviso, 1)

        restaurar = Button("Voltar ao texto original", "back", "ghost")
        restaurar.clicked.connect(self._restaurar)
        linha.addWidget(restaurar)

        salvar = Button("Salvar mensagem", "check", "primary")
        salvar.setMinimumHeight(38)
        salvar.clicked.connect(self._salvar)
        linha.addWidget(salvar)
        return linha

    # ------------------------------------------------------------------- dados
    def _escolher(self, indice: int) -> None:
        # o que estava escrito nao se perde ao trocar de mensagem
        if self._itens and self.atual is not MODELOS[indice]:
            self._guardar(silencioso=True)

        self.atual = MODELOS[indice]
        for posicao, item in enumerate(self._itens):
            item.setChecked(posicao == indice)

        self.titulo.setText(self.atual.titulo)
        self.quando.setText(self.atual.quando)
        self.corpo.blockSignals(True)
        self.corpo.setPlainText(mensagens.carregar(self.settings, self.atual.chave))
        self.corpo.blockSignals(False)
        self._montar_etiquetas()
        self._atualizar_previa()

    def _montar_etiquetas(self) -> None:
        while self.etiquetas.count():
            velha = self.etiquetas.takeAt(0).widget()
            if velha is not None:
                # tirar do pai antes de agendar a destruicao: so `deleteLater`
                # deixa o botao antigo desenhado onde estava ate o Qt respirar
                velha.setParent(None)
                velha.deleteLater()

        for posicao, campo in enumerate(self.atual.campos):
            etiqueta = Button("{" + campo + "}", variant="ghost")
            etiqueta.setToolTip(f"Insere {campo} no texto")
            etiqueta.clicked.connect(lambda _=False, c=campo: self._inserir(c))
            self.etiquetas.addWidget(
                etiqueta, posicao // COLUNAS_ETIQUETAS, posicao % COLUNAS_ETIQUETAS
            )

    def _inserir(self, campo: str) -> None:
        self.corpo.insertPlainText("{" + campo + "}")
        self.corpo.setFocus()

    def _atualizar_previa(self) -> None:
        texto = self.corpo.toPlainText()
        self.balao.setText(self.mensageiro.previa(self.atual.chave, texto))

        sobrando = mensagens.desconhecidos(texto, self.atual)
        if sobrando:
            nomes = ", ".join("{" + campo + "}" for campo in sobrando)
            self.alerta.setText(
                f"{nomes} não existe nesta mensagem e vai sair em branco."
            )
        else:
            self.alerta.setText("")
        self.alerta.setVisible(bool(self.alerta.text()))

    def refresh(self) -> None:
        self._escolher(MODELOS.index(self.atual))

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------- acoes
    def _guardar(self, silencioso: bool = False) -> None:
        mensagens.salvar(self.settings, self.atual.chave, self.corpo.toPlainText())
        self.alterada.emit()
        if not silencioso:
            self._dizer(f"'{self.atual.titulo}' salva.", "success")

    def _salvar(self) -> None:
        self._guardar()

    def _restaurar(self) -> None:
        texto = mensagens.restaurar(self.settings, self.atual.chave)
        self.corpo.setPlainText(texto)
        self.alterada.emit()
        self._dizer("Texto original restaurado.", "success")
