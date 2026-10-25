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

Cada linha e desenhada (`_LinhaDelegate`): nome em destaque, codigo apagado,
saldo e preco alinhados a direita - e a foto do produto, quando o Estoque tem.
O texto do item continua sendo a linha inteira (`_linha`), para leitor de tela
e para os testes.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QWidget,
)

from .. import format as fmt
from ..theme import Radius, palette_for
from .foto import miniatura, miniatura_vazia

logger = logging.getLogger(__name__)

#: menos que isto traria o catalogo inteiro a cada tecla
MINIMO = 2

#: quantos candidatos cabem na lista sem virar rolagem infinita
LIMITE = 12

#: quantas linhas aparecem antes de comecar a rolar
VISIVEIS = 8

#: foto da sugestao e altura da linha com e sem foto
FOTO = 28
ALTURA_COM_FOTO = 42
ALTURA_SEM_FOTO = 34
#: abaixo disto o nome nao cabe ao lado do saldo e do preco
LARGURA_MINIMA = 440

#: onde cada linha guarda o produto e a foto ja desenhada
PRODUTO = Qt.ItemDataRole.UserRole
DESENHO = Qt.ItemDataRole.UserRole + 1


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
        self.lista.setMouseTracking(True)  # a linha sob o mouse acende
        self._delegate = _LinhaDelegate(self.lista)
        self.lista.setItemDelegate(self._delegate)
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
        fotos = [self._foto(produto) for produto in achados]
        com_foto = any(foto is not None for foto in fotos)
        self._delegate.com_foto = com_foto
        vazia = miniatura_vazia(FOTO, palette_for(self.campo)) if com_foto else None
        for produto, foto in zip(achados, fotos):
            item = QListWidgetItem(_linha(produto))
            item.setData(PRODUTO, produto)
            item.setData(DESENHO, foto if foto is not None else vazia)
            self.lista.addItem(item)
        self.lista.setCurrentRow(-1)  # nada destacado ate alguem apertar a seta
        self._aberta = True
        self._posicionar()
        self.lista.show()
        self.lista.raise_()

    def _foto(self, produto):
        """Miniatura do produto, ou None. Foto e enfeite: falhar e silencio."""
        ler = getattr(self.catalogo, "miniatura", None)
        if ler is None or not getattr(produto, "produto_id", 0):
            return None
        try:
            return miniatura(ler(produto.produto_id), FOTO)
        except Exception:  # noqa: BLE001
            logger.exception("Nao foi possivel ler a foto do produto %s", produto.produto_id)
            return None

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
        topo = canto.y() + 2
        # a altura sai da linha de verdade, e nao de um numero chutado: fonte
        # maior no Windows deixaria a ultima linha cortada pela metade
        linha = self.lista.sizeHintForRow(0) if self.lista.count() else 20
        altura = min(self.lista.count(), VISIVEIS) * linha + 10
        # a lista e filha da janela: o que passar da borda some. Encolhe (e rola)
        # em vez de cortar - campo baixo num dialogo pequeno ainda mostra uma linha
        altura = max(linha + 10, min(altura, janela.height() - topo - 8))
        # campo estreito (o item de um orcamento) ainda precisa do nome inteiro
        largura = max(self.campo.width(), min(LARGURA_MINIMA, janela.width() - canto.x() - 8))
        self.lista.setGeometry(canto.x(), topo, largura, altura)

    def _pintar(self) -> None:
        """A lista flutua sobre o cartao: sem borda ela se confunde com ele."""
        paleta = palette_for(self.campo)
        self.lista.setStyleSheet(
            f"#BuscaCatalogo {{"
            f" background: {paleta.bg_soft};"
            f" border: 1px solid {paleta.border};"
            f" border-radius: {Radius.sm}px;"
            f" padding: 4px;"
            f"}}"
        )
        self._delegate.palette = paleta


def _saldo(produto) -> str:
    saldo = f"{float(produto.saldo or 0):.{int(produto.casas or 0)}f}".replace(".", ",")
    return f"{saldo} {(produto.unidade or '').strip()}".strip()


def _linha(produto) -> str:
    """Codigo, nome, preco e saldo - o "id e etc" que ajuda a escolher certo."""
    partes = [
        (produto.codigo or "").strip(),
        (produto.nome or "").strip(),
        fmt.moeda(produto.preco),
        f"saldo {_saldo(produto)}",
    ]
    return "   ".join(p for p in partes if p)


class _LinhaDelegate(QStyledItemDelegate):
    """[foto]  Nome  codigo ..............  saldo 6 UN   R$ 21,90"""

    PRECO = 92
    SALDO = 110
    MARGEM = 10

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.com_foto = False
        self.palette = palette_for(parent)

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 (assinatura do Qt)
        return QSize(option.rect.width(), ALTURA_COM_FOTO if self.com_foto else ALTURA_SEM_FOTO)

    def paint(self, pintor: QPainter, option, index) -> None:
        produto = index.data(PRODUTO)
        if produto is None:
            super().paint(pintor, option, index)
            return
        p = self.palette
        selecionada = bool(option.state & QStyle.StateFlag.State_Selected)
        sob_mouse = bool(option.state & QStyle.StateFlag.State_MouseOver)
        pintor.save()
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if selecionada or sob_mouse:
            fundo = QPainterPath()
            fundo.addRoundedRect(QRectF(option.rect).adjusted(0, 1, 0, -1), Radius.sm - 2, Radius.sm - 2)
            pintor.fillPath(fundo, QColor(p.accent if selecionada else p.surface_hover))

        texto = QColor(p.on_accent if selecionada else p.text)
        apagado = QColor(p.on_accent if selecionada else p.text_muted)
        if selecionada:
            apagado.setAlpha(200)

        r = option.rect.adjusted(self.MARGEM, 0, -self.MARGEM, 0)
        desenho = index.data(DESENHO)
        if self.com_foto and desenho is not None:
            pintor.drawPixmap(r.left(), r.top() + (r.height() - FOTO) // 2, desenho)
            r.setLeft(r.left() + FOTO + 10)

        normal = QFont(option.font)
        forte = QFont(option.font)
        forte.setWeight(QFont.Weight.DemiBold)
        meio = Qt.AlignmentFlag.AlignVCenter

        # direita: preco (forte) e saldo (apagado; vermelho quando acabou)
        preco = QRect(r.right() - self.PRECO, r.top(), self.PRECO, r.height())
        pintor.setFont(forte)
        pintor.setPen(texto)
        pintor.drawText(preco, Qt.AlignmentFlag.AlignRight | meio, fmt.moeda(produto.preco))
        saldo = QRect(preco.left() - self.SALDO, r.top(), self.SALDO - 14, r.height())
        sem_estoque = float(produto.saldo or 0) <= 0
        pintor.setFont(normal)
        pintor.setPen(QColor(p.danger) if sem_estoque and not selecionada else apagado)
        pintor.drawText(saldo, Qt.AlignmentFlag.AlignRight | meio,
                        "sem estoque" if sem_estoque else f"saldo {_saldo(produto)}")

        # esquerda: o nome, e o codigo depois dele enquanto couber
        livre = saldo.left() - 14 - r.left()
        nome = (produto.nome or "").strip()
        codigo = (produto.codigo or "").strip()
        medida_forte, medida = QFontMetrics(forte), QFontMetrics(normal)
        largura_codigo = medida.horizontalAdvance(codigo) + 10 if codigo else 0
        cabe_codigo = bool(codigo) and medida_forte.horizontalAdvance(nome) + largura_codigo <= livre
        espaco_nome = max(0, livre - (largura_codigo if cabe_codigo else 0))
        nome = medida_forte.elidedText(nome, Qt.TextElideMode.ElideRight, espaco_nome)
        pintor.setFont(forte)
        pintor.setPen(texto)
        pintor.drawText(QRect(r.left(), r.top(), espaco_nome, r.height()),
                        Qt.AlignmentFlag.AlignLeft | meio, nome)
        if cabe_codigo:
            x = r.left() + medida_forte.horizontalAdvance(nome) + 10
            pintor.setFont(normal)
            pintor.setPen(apagado)
            pintor.drawText(QRect(x, r.top(), largura_codigo, r.height()),
                            Qt.AlignmentFlag.AlignLeft | meio, codigo)
        pintor.restore()
