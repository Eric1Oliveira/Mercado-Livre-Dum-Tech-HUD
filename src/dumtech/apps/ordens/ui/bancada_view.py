"""O quadro: o que esta em andamento agora, por etapa.

Nao e uma lista - e a vista de quem chega e decide o que pegar. As etapas
ficam lado a lado, cada ordem e um cartao, e o que passou do prazo aparece com
a borda vermelha.

As quatro faixas estao sempre la, mesmo vazias. Quem nunca orca convive com
"Aguardando aprovacao" parada; em troca o quadro nao muda de forma de um dia
para o outro, e ninguem procura uma coluna que sumiu.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDrag,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ....ui import format as fmt
from ....ui.theme import Radius, Space, current_palette, palette_for
from ....ui.widgets.buttons import Button
from ....core import confirmacoes
from ....core.errors import RegraError
from ....ui.widgets.common import (
    Card,
    label,
    menu_arredondado,
    repolish,
    separator,
    tone_label,
)
from ....ui.widgets.confirmar import confirmar
from ..models import (
    AGUARDANDO,
    ANDAMENTO,
    BANCADA,
    CONCLUIDA,
    STATUS_LABEL,
    Ordem,
    OrdemError,
)
from ..repository import OrdensRepository
from .dialogos import AprovacaoDialog, EntregaDialog, MotivoDialog

ALTURA_CARTAO = 92
FAIXA = 3
#: identifica o que esta sendo arrastado - so o proprio quadro aceita
MIME = "application/x-dumtech-ordem"
#: a dica que ensina o arrasto - o quadro nao tem manual
DICA = ("Escolha uma ordem para ver as acoes  ·  arraste o cartao para outra "
        "etapa  ·  botao direito abre o menu")


class OrdemCard(QWidget):
    """Uma ordem no quadro. O cartao inteiro e clicavel."""

    clicado = Signal(int)
    aberto = Signal(int)
    #: (ordem_id, posicao na tela) - a faixa nao sabe montar o menu, a vista sabe
    menu_pedido = Signal(int, QPoint)

    def __init__(self, ordem: Ordem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ordem = ordem
        self._hover = False
        self._selecionado = False
        self._inicio_do_arrasto = QPoint()
        self._palette = palette_for(parent) if parent else current_palette()
        self.setFixedHeight(ALTURA_CARTAO)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        corpo = QVBoxLayout(self)
        corpo.setContentsMargins(Space.md, Space.sm, Space.md, Space.sm)
        corpo.setSpacing(1)
        corpo.addWidget(label(ordem.assunto or "Ordem sem descricao", "cardTitle"))
        corpo.addWidget(label(ordem.cliente or "Sem cliente", "muted"))

        rodape = QHBoxLayout()
        rodape.setSpacing(Space.sm)
        rodape.addWidget(label(ordem.numero, "caption"))
        rodape.addStretch(1)
        rodape.addWidget(tone_label(self._prazo(), self._tom_prazo(), "caption"))
        corpo.addLayout(rodape)

    def _prazo(self) -> str:
        """O prazo so importa enquanto o servico nao ficou pronto.

        Ordem concluida nao esta atrasada - esta esperando o cliente vir
        buscar, que e outra conversa.
        """
        if self.ordem.status == CONCLUIDA:
            dias = self.ordem.dias_em_aberto
            return "pronta hoje" if dias == 0 else f"pronta ha {fmt.dias(dias)}"
        if self.ordem.prazo:
            return fmt.prazo_texto(self.ordem.prazo)
        dias = self.ordem.dias_em_aberto
        return "entrou hoje" if dias == 0 else f"ha {fmt.dias(dias)}"

    def _tom_prazo(self) -> str:
        return "danger" if self.ordem.atrasada else "dim"

    def set_selecionado(self, valor: bool) -> None:
        self._selecionado = valor
        self.update()

    def apply_theme(self, palette) -> None:
        self._palette = palette
        self.update()

    # ------------------------------------------------------------------ desenho
    def paintEvent(self, event) -> None:  # noqa: N802 (assinatura do Qt)
        p = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        corpo = QPainterPath()
        corpo.addRoundedRect(rect, Radius.md, Radius.md)
        painter.fillPath(
            corpo, QColor(p.surface_alt if (self._hover or self._selecionado) else p.surface)
        )

        cor = QColor(p.resolve(self.ordem.status_tom))
        if self.ordem.atrasada:
            cor = QColor(p.danger)
        if self._selecionado:
            painter.setPen(QColor(p.accent))
        elif self.ordem.atrasada:
            painter.setPen(cor)
        else:
            painter.setPen(QColor(p.border_soft))
        painter.drawPath(corpo)

        # a faixa diz a etapa sem gastar uma etiqueta escrita no cartao
        faixa = QPainterPath()
        faixa.addRoundedRect(QRectF(1, 10, FAIXA, self.height() - 20), 2, 2)
        painter.fillPath(faixa, cor)
        painter.end()

    # ------------------------------------------------------------------ eventos
    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._inicio_do_arrasto = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """Arrastar o cartao para outra faixa muda a etapa.

        So comeca depois da distancia minima do sistema: sem isso, um clique
        com a mao tremida viraria um arrasto.
        """
        if not event.buttons() & Qt.MouseButton.LeftButton:
            return
        andou = (event.position().toPoint() - self._inicio_do_arrasto).manhattanLength()
        if andou < QApplication.startDragDistance():
            return

        self.clicado.emit(self.ordem.id)
        dados = QMimeData()
        dados.setData(MIME, str(self.ordem.id).encode())

        arrasto = QDrag(self)
        arrasto.setMimeData(dados)
        arrasto.setPixmap(self.grab())
        arrasto.setHotSpot(event.position().toPoint())
        arrasto.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit(self.ordem.id)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self.clicado.emit(self.ordem.id)
        self.menu_pedido.emit(self.ordem.id, event.globalPos())

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.aberto.emit(self.ordem.id)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.aberto.emit(self.ordem.id)
            return
        if event.key() == Qt.Key.Key_Space:
            self.clicado.emit(self.ordem.id)
            return
        super().keyPressEvent(event)


class Faixa(Card):
    """Uma etapa do quadro, com as ordens que estao nela."""

    #: (ordem_id, status de destino)
    soltou = Signal(int, str)

    def __init__(self, status: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=Space.md)
        self.status = status
        self._alvo = False
        self.setAcceptDrops(True)
        self.body.setSpacing(Space.sm)

        topo = QHBoxLayout()
        topo.setSpacing(Space.sm)
        topo.addWidget(label(STATUS_LABEL.get(status, status), "section"), 1)
        self.contador = tone_label("0", "muted", "strong")
        topo.addWidget(self.contador)
        self.body.addLayout(topo)
        self.body.addWidget(separator())

        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        interno = QWidget()
        self.coluna = QVBoxLayout(interno)
        self.coluna.setContentsMargins(0, 0, Space.xs, 0)
        self.coluna.setSpacing(Space.sm)
        self.coluna.addStretch(1)
        self._area.setWidget(interno)
        self.body.addWidget(self._area, 1)

        self.vazio = label("", "dim")
        self.vazio.setWordWrap(True)
        self.body.addWidget(self.vazio)

    # ------------------------------------------------------------- arrastar
    def dragEnterEvent(self, evento) -> None:  # noqa: N802
        if evento.mimeData().hasFormat(MIME):
            evento.acceptProposedAction()
            self._marcar(True)

    def dragMoveEvent(self, evento) -> None:  # noqa: N802
        if evento.mimeData().hasFormat(MIME):
            evento.acceptProposedAction()

    def dragLeaveEvent(self, evento) -> None:  # noqa: N802
        self._marcar(False)

    def dropEvent(self, evento) -> None:  # noqa: N802
        self._marcar(False)
        dados = evento.mimeData()
        if not dados.hasFormat(MIME):
            return
        evento.acceptProposedAction()
        self.soltou.emit(int(bytes(dados.data(MIME)).decode()), self.status)

    def _marcar(self, alvo: bool) -> None:
        self._alvo = alvo
        self.update()

    def paintEvent(self, evento) -> None:  # noqa: N802
        super().paintEvent(evento)
        if not self._alvo:
            return
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        caneta = QPen(QColor(palette_for(self).accent), 2)
        pintor.setPen(caneta)
        pintor.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2),
                               Radius.md, Radius.md)
        pintor.end()

    def preencher(self, ordens: list[Ordem], vazio: str) -> list[OrdemCard]:
        while self.coluna.count() > 1:
            item = self.coluna.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        cartoes = []
        for indice, ordem in enumerate(ordens):
            cartao = OrdemCard(ordem, self)
            self.coluna.insertWidget(indice, cartao)
            cartoes.append(cartao)

        self.contador.setText(str(len(ordens)))
        self.contador.setProperty("tone", "accent" if ordens else "muted")
        repolish(self.contador)
        self.vazio.setText("" if ordens else vazio)
        return cartoes


class BancadaView(QWidget):
    """As etapas lado a lado: o retrato do trabalho agora."""

    data_changed = Signal()
    #: pedido para abrir a ficha de uma ordem; 0 = ordem nova (a janela resolve,
    #: porque a ficha precisa da lista de clientes da plataforma)
    abrir_ficha = Signal(int)

    VAZIOS = {
        "aberta": "Nada na fila.",
        "aguardando": "Nenhum orcamento esperando o cliente.",
        "andamento": "Nada em execucao agora.",
        "concluida": "Nada pronto para entregar.",
    }

    def __init__(self, repository: OrdensRepository, parent: QWidget | None = None,
                 empresa=None, contas=None) -> None:
        super().__init__(parent)
        self.repository = repository
        #: chave Pix da loja, para o QR Code da entrega
        self.empresa = empresa
        #: ponte com o Financeiro: a entrega ja registra o pagamento
        self.contas = contas
        self.selecionada: int | None = None
        self._cartoes: list[OrdemCard] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        raiz.addLayout(self._cabecalho())

        faixas = QHBoxLayout()
        faixas.setSpacing(Space.lg)
        self.faixas = {}
        for status in BANCADA:
            faixa = Faixa(status)
            faixa.soltou.connect(self._mover_para)
            self.faixas[status] = faixa
            faixas.addWidget(faixa, 1)
        raiz.addLayout(faixas, 1)

        raiz.addLayout(self._acoes())
        self.refresh()

    # -------------------------------------------------------------- cabecalho
    def _cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Quadro", "title"))
        self.subtitulo = label("", "subtitle")
        titulos.addWidget(self.subtitulo)
        linha.addLayout(titulos)
        linha.addStretch(1)

        self.botao_nova = Button("Nova ordem", "plus", "primary")
        self.botao_nova.setMinimumHeight(38)
        self.botao_nova.clicked.connect(lambda: self.abrir_ficha.emit(0))
        linha.addWidget(self.botao_nova)
        return linha

    def _acoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        self.aviso = label(DICA, "muted")
        self.aviso.setWordWrap(True)
        linha.addWidget(self.aviso, 1)

        self.botao_ficha = Button("Abrir ficha", "file")
        self.botao_ficha.clicked.connect(self._abrir)
        linha.addWidget(self.botao_ficha)

        self.botao_avancar = Button("Avancar etapa", "check", "success")
        self.botao_avancar.setMinimumHeight(38)
        self.botao_avancar.clicked.connect(self._avancar)
        linha.addWidget(self.botao_avancar)
        return linha

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        faixas = self.repository.por_etapa()
        self._cartoes = []
        total = 0
        atrasadas = 0

        for status, faixa in self.faixas.items():
            ordens = faixas.get(status, [])
            total += len(ordens)
            atrasadas += sum(1 for o in ordens if o.atrasada)
            for cartao in faixa.preencher(ordens, self.VAZIOS.get(status, "")):
                cartao.clicado.connect(self._selecionar)
                cartao.aberto.connect(self.abrir_ficha.emit)
                cartao.menu_pedido.connect(self._menu_do_cartao)
                self._cartoes.append(cartao)

        if not total:
            self.subtitulo.setText("Nenhum servico em andamento no momento")
        else:
            texto = fmt.contagem(total, "servico") + " em andamento"
            if atrasadas:
                verbo = "passou" if atrasadas == 1 else "passaram"
                texto += f"  ·  {atrasadas} {verbo} do prazo"
            self.subtitulo.setText(texto)

        # a selecao anterior pode ter mudado de faixa (ou saido do quadro)
        if self.selecionada is not None and not any(
            c.ordem.id == self.selecionada for c in self._cartoes
        ):
            self.selecionada = None
        self._pintar_selecao()

    def ordem_selecionada(self) -> Ordem | None:
        if self.selecionada is None:
            return None
        return self.repository.obter(self.selecionada)

    def _selecionar(self, ordem_id: int) -> None:
        self.selecionada = ordem_id
        self._pintar_selecao()

    def _pintar_selecao(self) -> None:
        for cartao in self._cartoes:
            cartao.set_selecionado(cartao.ordem.id == self.selecionada)
        ordem = self.ordem_selecionada()
        self.botao_ficha.setEnabled(ordem is not None)
        self.botao_avancar.setEnabled(ordem is not None)
        if ordem is None:
            self.botao_avancar.setText("  Avancar etapa")
            self._dizer(DICA)
        else:
            self.botao_avancar.setText(f"  {self._proximo_rotulo(ordem)}")
            partes = [ordem.numero, ordem.assunto, ordem.status_label]
            self._dizer("  ·  ".join(p for p in partes if p))

    @staticmethod
    def _proximo_rotulo(ordem: Ordem) -> str:
        return {
            "aberta": "Mandar para aprovacao",
            "aguardando": "Registrar aprovacao",
            "andamento": "Marcar como concluida",
            "concluida": "Entregar ao cliente",
        }.get(ordem.status, "Avancar etapa")

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ---------------------------------------------------------- arrastar/menu
    def _mover_para(self, ordem_id: int, status: str) -> None:
        """Soltou o cartao noutra faixa: a etapa muda.

        Uma excecao: entrar em "em andamento" vindo da aprovacao ainda passa
        pela janela que pergunta quem aprovou - e a regra do negocio, e arrastar
        nao pode ser um atalho para furar regra.
        """
        ordem = self.repository.obter(ordem_id)
        if ordem is None or ordem.status == status:
            return

        if ordem.status == AGUARDANDO and status == ANDAMENTO:
            if not AprovacaoDialog(self.repository, ordem, self).exec():
                return
        else:
            try:
                self.repository.definir_status(
                    ordem_id, status, "Movido no quadro"
                )
            except RegraError as erro:
                self._dizer(str(erro), "danger")
                return

        self.selecionada = ordem_id
        self.refresh()
        self._dizer(
            f"{ordem.numero}: agora esta em "
            f"'{STATUS_LABEL.get(status, status)}'.", "success",
        )
        self.data_changed.emit()

    def _menu_do_cartao(self, ordem_id: int, posicao) -> None:
        ordem = self.repository.obter(ordem_id)
        if ordem is None:
            return

        menu = menu_arredondado(self)
        menu.addAction("Abrir ficha", lambda: self.abrir_ficha.emit(ordem_id))
        menu.addAction(self._proximo_rotulo(ordem), self._avancar)
        menu.addSeparator()
        menu.addAction("Cancelar ordem", lambda: self._cancelar(ordem_id))
        menu.addAction("Excluir ordem", lambda: self._excluir(ordem_id))
        menu.exec(posicao)

    def _cancelar(self, ordem_id: int) -> None:
        ordem = self.repository.obter(ordem_id)
        if ordem is None:
            return
        dialogo = MotivoDialog(
            f"Cancelar {ordem.numero}", ordem.assunto,
            "Por que a ordem foi cancelada?", self,
        )
        if not dialogo.exec():
            return
        try:
            self.repository.cancelar(ordem_id, dialogo.motivo)
        except RegraError as erro:
            self._dizer(str(erro), "danger")
            return
        self.selecionada = None
        self.refresh()
        self._dizer(f"{ordem.numero} cancelada.", "warning")
        self.data_changed.emit()

    def _excluir(self, ordem_id: int) -> None:
        ordem = self.repository.obter(ordem_id)
        if ordem is None:
            return
        if not confirmar(
            self, "Excluir ordem",
            f"Excluir a ordem {ordem.numero}{f' - {ordem.assunto}' if ordem.assunto else ''}?",
            chave=confirmacoes.EXCLUIR, rotulo_ok="Excluir",
            detalhe="O historico da ordem vai junto e nao volta.",
        ):
            return
        try:
            self.repository.excluir(ordem_id)
        except RegraError as erro:
            self._dizer(str(erro), "danger")
            return
        self.selecionada = None
        self.refresh()
        self._dizer(f"{ordem.numero} excluida.", "muted")
        self.data_changed.emit()

    # ------------------------------------------------------------------- acoes
    def _abrir(self) -> None:
        if self.selecionada is not None:
            self.abrir_ficha.emit(self.selecionada)

    def _avancar(self) -> None:
        """O botao muda de nome conforme a etapa - e a acao que falta agora.

        Aprovar e entregar param para perguntar quem: sao as duas etapas em que
        a oficina precisa saber com quem falou.
        """
        ordem = self.ordem_selecionada()
        if ordem is None:
            return

        if ordem.status == AGUARDANDO:
            dialogo = AprovacaoDialog(self.repository, ordem, self)
        elif ordem.status == CONCLUIDA:
            dialogo = EntregaDialog(self.repository, ordem, self,
                                    empresa=self.empresa, contas=self.contas)
        else:
            dialogo = None

        if dialogo is not None:
            if not dialogo.exec():
                return
        else:
            try:
                self.repository.avancar(ordem.id)
            except OrdemError as erro:
                self._dizer(str(erro), "danger")
                return

        atual = self.repository.obter(ordem.id)
        self.refresh()
        self._dizer(f"{ordem.numero}: agora esta em '{atual.status_label}'."
                    + getattr(dialogo, "recado_financeiro", ""), "success")
        self.data_changed.emit()
