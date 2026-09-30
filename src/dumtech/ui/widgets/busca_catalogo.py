"""Sugestao de produto enquanto se digita, ligada ao catalogo da plataforma.

Antes disto, achar um produto era digitar no escuro e apertar Enter para
descobrir se existia. Agora a lista aparece embaixo do campo com codigo, nome,
preco e saldo - e escolher preenche a linha inteira.

**A regra que manda aqui e o Enter.** O campo de produto do balcao recebe leitor
de codigo de barras: ele digita depressa e manda Enter sem nunca apertar seta.
Se a lista ficar com esse Enter, o caixa adiciona o produto errado - pior que
nao ter sugestao nenhuma. Entao:

    o Enter so pertence a lista DEPOIS que alguem apertou a seta de proposito.

Bipou e mandou Enter? A lista se fecha e o Enter segue para quem sempre tratou,
sem passar por aqui. Isso nao depende de o Qt se comportar de um jeito ou de
outro: a lista nunca pega foco e nunca instala nada no caminho do Enter - ela
so responde `False` e sai da frente.

Pelo mesmo motivo a lista e um widget filho da janela, e nao uma janela popup:
janela popup captura teclado e mouse do sistema, e era exatamente disso que
precisavamos fugir.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QWidget

from .. import format as fmt
from ..theme import palette_for

logger = logging.getLogger(__name__)

#: menos que isto traria o catalogo inteiro a cada tecla
MINIMO = 2

#: quantos candidatos cabem na lista sem virar rolagem infinita
LIMITE = 12

#: quantas linhas aparecem antes de comecar a rolar
VISIVEIS = 8


class BuscaCatalogo(QObject):
    """Liga um campo de texto ao catalogo: sugere enquanto digita.

    Quem usa conecta `escolhido` e preenche os proprios campos - esta classe
    nao sabe o que e uma venda, um orcamento ou uma ordem.
    """

    #: o produto que o usuario escolheu (`core.catalog.ItemCatalogo`)
    escolhido = Signal(object)

    def __init__(
        self,
        campo: QLineEdit,
        catalogo=None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or campo)
        self.campo = campo
        #: None quando a licenca nao libera o Estoque - ai nada acontece
        self.catalogo = catalogo
        self._itens: list = []
        #: so vira True quando alguem aperta a seta; e o que libera o Enter
        self._navegou = False
        #: a lista esta valendo? Estado proprio, e nao `isVisible()`: quem decide
        #: de quem e o Enter nao pode depender de a janela ja estar desenhada
        self._aberta = False

        # sem pai por enquanto: na hora que este objeto nasce, o campo ainda
        # nao foi encaixado na tela, e `window()` devolveria o cartao que o
        # contem - a lista nasceria recortada dentro dele. Quem resolve a
        # janela e `_posicionar`, ja com tudo montado.
        self.lista = QListWidget()
        self.lista.setObjectName("BuscaCatalogo")
        self.lista.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # o campo nunca perde o foco
        self.lista.setUniformItemSizes(True)
        self.lista.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lista.itemClicked.connect(self._clicou)
        self.lista.hide()

        campo.textEdited.connect(self.procurar)
        campo.installEventFilter(self)

    # ------------------------------------------------------------------ estado
    @property
    def aberta(self) -> bool:
        return self._aberta

    def linha_texto(self, indice: int) -> str:
        item = self.lista.item(indice)
        return item.text() if item is not None else ""

    # ------------------------------------------------------------------ buscar
    def procurar(self, termo: str) -> None:
        """Refaz a lista para o que esta escrito agora."""
        self._navegou = False
        termo = (termo or "").strip()
        if self.catalogo is None or len(termo) < MINIMO:
            self.fechar()
            return

        try:
            achados = list(self.catalogo.procurar(termo, LIMITE))
        except Exception:  # noqa: BLE001 - catalogo fora do ar nao trava a venda
            logger.exception("Nao foi possivel procurar '%s' no catalogo", termo)
            self.fechar()
            return

        if not achados:
            self.fechar()
            return

        self._itens = achados
        self.lista.clear()
        for produto in achados:
            self.lista.addItem(QListWidgetItem(_linha(produto)))
        self.lista.setCurrentRow(-1)  # nada destacado ate alguem apertar a seta
        self._aberta = True
        self._posicionar()
        self.lista.show()
        self.lista.raise_()

    def fechar(self) -> None:
        self._navegou = False
        self._aberta = False
        self.lista.clear()
        self._itens = []
        self.lista.hide()

    # ----------------------------------------------------------------- teclado
    def eventFilter(self, alvo: QObject, evento: QEvent) -> bool:  # noqa: N802
        if alvo is self.campo and evento.type() == QEvent.Type.KeyPress:
            return self.tecla(evento)
        return False

    def tecla(self, evento) -> bool:
        """True quando a lista fica com a tecla. Testado direto pelos testes."""
        if not self.aberta:
            return False

        codigo = evento.key()
        if codigo == Qt.Key.Key_Escape:
            self.fechar()
            return True
        if codigo == Qt.Key.Key_Down:
            self._mover(1)
            return True
        if codigo == Qt.Key.Key_Up:
            self._mover(-1)
            return True
        if codigo in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # o coracao da regra: sem seta, o Enter nao e nosso
            if self._navegou and 0 <= self.lista.currentRow() < len(self._itens):
                self._escolher(self.lista.currentRow())
                return True
            self.fechar()
            return False
        return False

    def _mover(self, passo: int) -> None:
        total = self.lista.count()
        if not total:
            return
        atual = self.lista.currentRow()
        proximo = 0 if not self._navegou else (atual + passo) % total
        self._navegou = True
        self.lista.setCurrentRow(proximo)

    def _clicou(self, item: QListWidgetItem) -> None:
        self._escolher(self.lista.row(item))

    def _escolher(self, indice: int) -> None:
        if not 0 <= indice < len(self._itens):
            return
        produto = self._itens[indice]
        self.fechar()
        self.escolhido.emit(produto)

    # -------------------------------------------------------------- desenhar
    def _posicionar(self) -> None:
        """Encaixa a lista logo abaixo do campo, com a mesma largura.

        A janela e resolvida agora, e nao no construtor: so aqui o campo ja
        esta dentro da tela de verdade. Reparentar antes de mostrar - trocar o
        pai de um widget visivel o esconde.
        """
        janela: QWidget = self.campo.window()
        if self.lista.parentWidget() is not janela:
            self.lista.setParent(janela)
        self._pintar()
        canto = self.campo.mapTo(janela, self.campo.rect().bottomLeft())
        # a altura sai da linha de verdade, e nao de um numero chutado: fonte
        # maior no Windows deixaria a ultima linha cortada pela metade
        linha = self.lista.sizeHintForRow(0) if self.lista.count() else 20
        altura = min(self.lista.count(), VISIVEIS) * linha + 8
        self.lista.setGeometry(canto.x(), canto.y() + 2, self.campo.width(), altura)

    def _pintar(self) -> None:
        """A lista flutua sobre o cartao: sem borda ela se confunde com ele."""
        paleta = palette_for(self.campo)
        self.lista.setStyleSheet(
            f"#BuscaCatalogo {{"
            f" background: {paleta.bg_soft};"
            f" border: 1px solid {paleta.border};"
            f" border-radius: 6px;"
            f" padding: 2px;"
            f"}}"
            f"#BuscaCatalogo::item {{ padding: 3px 6px; border-radius: 4px; }}"
            f"#BuscaCatalogo::item:selected {{"
            f" background: {paleta.accent}; color: #FFFFFF;"
            f"}}"
        )


def _linha(produto) -> str:
    """Codigo, nome, preco e saldo - o "id e etc" que ajuda a escolher certo."""
    saldo = f"{float(produto.saldo or 0):.{int(produto.casas or 0)}f}".replace(".", ",")
    unidade = (produto.unidade or "").strip()
    partes = [
        (produto.codigo or "").strip(),
        (produto.nome or "").strip(),
        fmt.moeda(produto.preco),
        f"saldo {saldo} {unidade}".strip(),
    ]
    return "   ".join(p for p in partes if p)
