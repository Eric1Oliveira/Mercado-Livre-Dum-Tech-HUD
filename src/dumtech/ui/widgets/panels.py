"""Paineis de lista, de tabela e de grafico do painel inicial de cada aplicativo.

Todos tem a mesma cabeca: o titulo a esquerda e uma nota curta a direita,
sem fio embaixo - o espaco ja separa o titulo do conteudo.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..theme import Space, apply_type
from .common import Card, label, repolish, separator, tone_label

PADDING = Space.lg + 4


def cabeca_de_painel(titulo: str, nota: str = ""):
    """Titulo de cartao a esquerda, nota curta a direita - sem fio embaixo.

    Publica: cartao montado a mao num modulo usa a mesma cabeca dos paineis,
    senao cada modulo inventa a sua (e um deles vinha com fio cheio).
    """
    topo = QHBoxLayout()
    topo.setSpacing(Space.sm)
    topo.addWidget(label(titulo, "section"))
    topo.addStretch(1)
    rotulo_nota = label(nota, "dim")
    topo.addWidget(rotulo_nota, 0, Qt.AlignmentFlag.AlignVCenter)
    return topo, rotulo_nota


class ListPanel(Card):
    """Cartao com titulo e uma lista simples de linhas.

    Cada item e uma tupla: (titulo, detalhe, valor, tom_do_valor).
    """

    def __init__(
        self,
        titulo: str,
        vazio: str = "Nada por aqui ainda.",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, padding=PADDING)
        self._vazio = vazio
        self.body.setSpacing(Space.sm)
        topo, self.nota = cabeca_de_painel(titulo)
        self.body.addLayout(topo)
        self.lista = QVBoxLayout()
        self.lista.setSpacing(0)
        self.body.addLayout(self.lista)
        self.body.addStretch(1)

    def set_nota(self, texto: str) -> None:
        self.nota.setText(texto)

    def set_items(self, itens: list[tuple[str, str, str, str]]) -> None:
        while self.lista.count():
            item = self.lista.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)   # tira da tela na hora
                widget.deleteLater()

        if not itens:
            vazio = label(self._vazio, "muted")
            vazio.setContentsMargins(0, Space.sm, 0, 0)
            self.lista.addWidget(vazio)
            return

        for posicao, (titulo, detalhe, valor, tom) in enumerate(itens):
            if posicao:
                self.lista.addWidget(separator(tracejado=True))
            self.lista.addWidget(_linha(titulo, detalhe, valor, tom))


def _linha(titulo: str, detalhe: str, valor: str, tom: str) -> QWidget:
    linha = QWidget()
    layout = QHBoxLayout(linha)
    layout.setContentsMargins(0, 10, 0, 10)
    layout.setSpacing(10)

    texto = QVBoxLayout()
    texto.setSpacing(2)
    texto.addWidget(label(titulo, "strong"))
    if detalhe:
        texto.addWidget(label(detalhe, "caption"))
    layout.addLayout(texto, 1)

    if valor:
        etiqueta = tone_label(valor, tom or "muted", "strong")
        etiqueta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        etiqueta.setMinimumWidth(80)
        layout.addWidget(etiqueta)
    return linha


class ChartPanel(Card):
    """Cartao com titulo e um grafico dentro.

    Existe para o painel nao virar uma pilha de listas: onde a pergunta e
    "quanto de cada", o desenho responde antes da leitura.
    """

    def __init__(
        self,
        titulo: str,
        grafico,
        subtitulo: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, padding=PADDING)
        self.grafico = grafico
        self.body.setSpacing(Space.md + 2)
        topo, self.nota = cabeca_de_painel(titulo, subtitulo)
        self.body.addLayout(topo)
        self.body.addWidget(grafico, 1)

    def set_nota(self, texto: str) -> None:
        self.nota.setText(texto)


class TablePanel(Card):
    """Cartao com titulo e uma tabela curta, de colunas alinhadas.

    Para quando cada linha tem mais de uma coisa para ler lado a lado - o
    produto, o quanto e que parte do todo - e a lista de duas linhas do
    `ListPanel` obrigaria a procurar o numero. A primeira coluna e a do nome:
    ela estica e corta com reticencias; as outras ficam do tamanho do conteudo.

    `colunas` e uma lista de (titulo, alinhamento). Cada celula de `set_linhas`
    e um texto, ou (texto, tom) quando a celula merece destaque - o resto fica
    na cor do texto, para o destaque significar alguma coisa.
    """

    def __init__(
        self,
        titulo: str,
        colunas: list[tuple[str, Qt.AlignmentFlag]],
        vazio: str = "Nada por aqui ainda.",
        apoio: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, padding=PADDING)
        self._vazio = vazio
        self._colunas = list(colunas)
        self.body.setSpacing(Space.sm)
        topo, self.nota = cabeca_de_painel(titulo)
        self.body.addLayout(topo)

        self.apoio = label(apoio, "dim")
        self.apoio.setWordWrap(True)
        self.body.addWidget(self.apoio)
        self.apoio.setVisible(bool(apoio))

        self.grade = QGridLayout()
        self.grade.setHorizontalSpacing(Space.lg)
        self.grade.setVerticalSpacing(0)
        self.grade.setColumnStretch(0, 1)
        self.body.addLayout(self.grade)
        self.body.addStretch(1)
        self.linhas = 0

    def set_nota(self, texto: str) -> None:
        self.nota.setText(texto)

    def set_linhas(self, linhas: list[list]) -> None:
        while self.grade.count():
            item = self.grade.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.linhas = len(linhas)

        if not linhas:
            vazio = label(self._vazio, "muted")
            vazio.setWordWrap(True)
            vazio.setContentsMargins(0, Space.sm, 0, 0)
            self.grade.addWidget(vazio, 0, 0, 1, len(self._colunas))
            return

        for coluna, (titulo, lado) in enumerate(self._colunas):
            cabeca = label(titulo, "caption")
            cabeca.setAlignment(lado | Qt.AlignmentFlag.AlignVCenter)
            cabeca.setContentsMargins(0, 0, 0, 6)
            self.grade.addWidget(cabeca, 0, coluna)

        for posicao, celulas in enumerate(linhas):
            linha = 1 + posicao * 2
            self.grade.addWidget(separator(tracejado=True), linha, 0, 1, len(self._colunas))
            for coluna, celula in enumerate(celulas):
                texto, tom = (celula, "") if isinstance(celula, str) else celula
                lado = self._colunas[coluna][1]
                self.grade.addWidget(_celula(texto, tom, lado, coluna == 0), linha + 1, coluna)


def _celula(texto: str, tom: str, lado: Qt.AlignmentFlag, nome: bool) -> QLabel:
    celula = _NomeCortado(texto) if nome else tone_label(texto, tom or "text", "body")
    if nome and tom:
        celula.setProperty("tone", tom)
        repolish(celula)
    celula.setAlignment(lado | Qt.AlignmentFlag.AlignVCenter)
    celula.setContentsMargins(0, 9, 0, 9)
    return celula


class _NomeCortado(QLabel):
    """Nome que cede com reticencias, em vez de empurrar as outras colunas."""

    def __init__(self, texto: str) -> None:
        super().__init__(texto)
        self._inteiro = texto
        self.setProperty("role", "strong")
        apply_type(self, "strong")
        self.setToolTip(texto)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def resizeEvent(self, evento) -> None:  # noqa: N802 (assinatura do Qt)
        super().resizeEvent(evento)
        largura = self.width() - self.contentsMargins().left() - self.contentsMargins().right()
        cortado = self.fontMetrics().elidedText(
            self._inteiro, Qt.TextElideMode.ElideRight, max(largura, 0)
        )
        if cortado != self.text():
            self.setText(cortado)
