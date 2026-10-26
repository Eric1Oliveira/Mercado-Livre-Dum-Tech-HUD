"""O tempo desenhado: horas na lateral, dias em colunas, blocos por duracao.

O espaco vazio na tela e o horario vago na vida real - e por isso que uma
agenda precisa de grade e nao de lista. Clicar no vazio marca ali mesmo, que e
o gesto natural de quem aponta para o buraco.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from ....core.documentos import formatar_telefone
from ....ui import icons
from ....ui.theme import Radius, current_palette, font_for, mix, palette_for
from ..models import CANCELADO, Compromisso, Grade

#: medidas da grade
GUTTER = 58
CABECALHO = 44
#: a linha da hora estica para o dia caber na tela, mas nao passa destes
#: limites: apertada demais some o texto, folgada demais vira desperdicio
ALTURA_HORA_MINIMA = 26
ALTURA_HORA_MAXIMA = 58
FOLGA = 2
#: abaixo disso o bloco so cabe o horario
ALTURA_MINIMA_TITULO = 30
#: a linha do horario, no topo do bloco
ALTURA_LINHA_HORA = 13


def _faixas(compromissos: list[Compromisso]) -> dict[int, tuple[int, int]]:
    """Divide a largura entre blocos que se sobrepoem.

    Sem isso, dois compromissos no mesmo horario ficam um em cima do outro e um
    deles some. Cada bloco ganha (faixa, total de faixas).
    """
    ordenados = sorted(
        [c for c in compromissos if c.inicio_dt and c.ocupa_horario],
        key=lambda c: (c.inicio_dt, c.duracao_min or 0),
    )
    resultado: dict[int, tuple[int, int]] = {}

    grupo: list[Compromisso] = []
    for compromisso in ordenados:
        # o grupo acaba quando um bloco comeca depois do fim de todos os outros
        if grupo and all(not compromisso.choca_com(c) for c in grupo):
            resultado.update(_dividir(grupo))
            grupo = []
        grupo.append(compromisso)
    resultado.update(_dividir(grupo))
    return resultado


def _dividir(grupo: list[Compromisso]) -> dict[int, tuple[int, int]]:
    if not grupo:
        return {}
    faixas: list[datetime] = []          # fim de cada faixa
    escolha: dict[int, int] = {}
    for compromisso in grupo:
        for indice, fim in enumerate(faixas):
            if compromisso.inicio_dt >= fim:
                faixas[indice] = compromisso.fim_dt
                escolha[compromisso.id] = indice
                break
        else:
            faixas.append(compromisso.fim_dt)
            escolha[compromisso.id] = len(faixas) - 1
    total = len(faixas)
    return {chave: (valor, total) for chave, valor in escolha.items()}


class GradeWidget(QWidget):
    """Desenha a grade e responde ao clique."""

    selecionado = Signal(int)
    aberto = Signal(int)
    #: clique no vazio: manda a data e a hora daquele ponto (ISO)
    vazio = Signal(str)
    #: botao direito em cima de um compromisso: id e onde abrir o menu
    menu_pedido = Signal(int, QPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.grade = Grade()
        self.selecao: int | None = None
        self._palette = palette_for(parent) if parent else current_palette()
        self._blocos: list[tuple[QRectF, Compromisso]] = []
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumWidth(560)

    def set_grade(self, grade: Grade) -> None:
        self.grade = grade
        # minimo, e nao fixo: com o dia inteiro na faixa, a grade encolhe a
        # linha ate caber; se nem assim couber, a area rola
        self.setMinimumHeight(CABECALHO + self._horas() * ALTURA_HORA_MINIMA)
        self.update()

    def apply_theme(self, palette) -> None:
        self._palette = palette
        self.update()

    def y_da_hora_cheia(self, hora: int) -> int:
        """Onde comeca a linha de uma hora - a tela usa para se posicionar."""
        passo = max(0, min(hora, self.grade.hora_final) - self.grade.hora_inicial)
        return int(CABECALHO + passo * self._altura_hora())

    def _horas(self) -> int:
        return max(self.grade.hora_final - self.grade.hora_inicial, 1)

    def _altura_hora(self) -> float:
        """Quanto vale uma hora em pixels, agora.

        Com poucas horas na faixa a linha fica folgada; com o dia inteiro ela
        aperta ate o minimo. Assim a semana inteira cabe na tela em vez de
        obrigar a rolar para ver a noite.
        """
        disponivel = (self.height() - CABECALHO) / self._horas()
        return min(ALTURA_HORA_MAXIMA, max(ALTURA_HORA_MINIMA, disponivel))

    def _largura_coluna(self) -> float:
        return max((self.width() - GUTTER) / max(len(self.grade.dias), 1), 1.0)

    def _y_da_hora(self, momento: datetime) -> float:
        minutos = (momento.hour - self.grade.hora_inicial) * 60 + momento.minute
        return CABECALHO + minutos / 60 * self._altura_hora()

    # ------------------------------------------------------------------ desenho
    def paintEvent(self, event) -> None:  # noqa: N802 (assinatura do Qt)
        if not self.grade.dias:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        self._blocos = []
        self._fundo(painter)
        self._horas_e_linhas(painter)
        self._cabecalho(painter)
        for indice, dia in enumerate(self.grade.dias):
            self._blocos_do_dia(painter, indice, dia)
        self._linha_de_agora(painter)
        painter.end()

    def _fundo(self, painter: QPainter) -> None:
        p = self._palette
        painter.fillRect(self.rect(), QColor(p.surface))
        largura = self._largura_coluna()
        for indice, dia in enumerate(self.grade.dias):
            if not (dia.e_hoje or dia.fim_de_semana):
                continue
            cor = QColor(mix(p.surface, p.accent, 0.10) if dia.e_hoje else p.bg_soft)
            painter.fillRect(
                QRectF(GUTTER + indice * largura, CABECALHO, largura,
                       self._horas() * self._altura_hora()),
                cor,
            )

    def _horas_e_linhas(self, painter: QPainter) -> None:
        p = self._palette
        painter.setFont(font_for("caption"))
        largura = self._largura_coluna()

        for passo in range(self._horas() + 1):
            y = CABECALHO + passo * self._altura_hora()
            painter.setPen(QPen(QColor(p.border_soft), 1))
            painter.drawLine(QPointF(GUTTER, y), QPointF(self.width(), y))
            if passo < self._horas():
                painter.setPen(QColor(p.text_dim))
                # abaixo da linha, senao a primeira hora fica sob o cabecalho
                painter.drawText(
                    QRectF(0, y + 2, GUTTER - 10, 15),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    f"{self.grade.hora_inicial + passo:02d}:00",
                )

        painter.setPen(QPen(QColor(p.border_soft), 1))
        for indice in range(len(self.grade.dias) + 1):
            x = GUTTER + indice * largura
            painter.drawLine(
                QPointF(x, CABECALHO),
                QPointF(x, CABECALHO + self._horas() * self._altura_hora()),
            )

    def _cabecalho(self, painter: QPainter) -> None:
        p = self._palette
        largura = self._largura_coluna()
        painter.fillRect(QRectF(0, 0, self.width(), CABECALHO), QColor(p.bg_soft))
        painter.setPen(QPen(QColor(p.border), 1))
        painter.drawLine(QPointF(0, CABECALHO), QPointF(self.width(), CABECALHO))

        for indice, dia in enumerate(self.grade.dias):
            painter.setFont(font_for("strong" if dia.e_hoje else "body"))
            painter.setPen(QColor(p.accent if dia.e_hoje else p.text_muted))
            rotulo = f"{dia.rotulo}  (hoje)" if dia.e_hoje else dia.rotulo
            painter.drawText(
                QRectF(GUTTER + indice * largura, 0, largura, CABECALHO),
                Qt.AlignmentFlag.AlignCenter,
                rotulo,
            )

    def _blocos_do_dia(self, painter: QPainter, coluna: int, dia) -> None:
        p = self._palette
        largura = self._largura_coluna()
        faixas = _faixas(dia.compromissos)

        for compromisso in dia.compromissos:
            if compromisso.inicio_dt is None or compromisso.id not in faixas:
                continue
            faixa, total = faixas[compromisso.id]
            inicio, fim = compromisso.inicio_dt, compromisso.fim_dt

            topo = max(self._y_da_hora(inicio), CABECALHO)
            base = min(self._y_da_hora(fim),
                       CABECALHO + self._horas() * self._altura_hora())
            if base <= topo:
                continue

            passo = (largura - FOLGA * 2) / total
            rect = QRectF(
                GUTTER + coluna * largura + FOLGA + faixa * passo,
                topo + 1,
                passo - FOLGA,
                base - topo - 2,
            )
            self._desenhar_bloco(painter, rect, compromisso)
            self._blocos.append((rect, compromisso))

    def _desenhar_bloco(
        self, painter: QPainter, rect: QRectF, compromisso: Compromisso
    ) -> None:
        p = self._palette
        cor = QColor(p.resolve(compromisso.tom))
        cancelado = compromisso.status == CANCELADO

        caminho = QPainterPath()
        caminho.addRoundedRect(rect, Radius.sm, Radius.sm)
        fundo = QColor(cor)
        fundo.setAlpha(30 if cancelado else (70 if p.is_dark else 46))
        painter.fillPath(caminho, fundo)

        borda = QColor(p.accent) if compromisso.id == self.selecao else cor
        painter.setPen(QPen(borda, 2 if compromisso.id == self.selecao else 1))
        painter.drawPath(caminho)

        # a faixa da esquerda e o que identifica o tipo de longe
        faixa = QPainterPath()
        faixa.addRoundedRect(QRectF(rect.left(), rect.top(), 3, rect.height()), 1.5, 1.5)
        painter.fillPath(faixa, cor)

        cor_texto = QColor(p.text_dim if cancelado else p.text)
        cor_cliente = QColor(p.text_dim if cancelado else p.text_muted)
        com_elo = compromisso.pelo_link and rect.width() >= 44 and rect.height() >= 15
        painter.save()
        painter.setClipRect(rect)
        # o texto para antes do elo: as reticencias caem antes do icone, nao embaixo dele
        area_texto = rect.adjusted(0, 0, -15, 0) if com_elo else rect
        for area, papel, texto, e_cliente, alinhamento in self._textos(area_texto, compromisso):
            painter.setFont(font_for(papel))
            painter.setPen(cor_cliente if e_cliente else cor_texto)
            painter.drawText(area, alinhamento, texto)
        # o cliente marcou sozinho, pelo link: um elo pequeno no canto
        if com_elo:
            painter.drawPixmap(QPointF(rect.right() - 15, rect.top() + 3),
                               icons.pixmap("link", cor.name(), 12, width=2.2))
        painter.restore()

    def _textos(self, rect: QRectF, compromisso: Compromisso) -> list[tuple]:
        """O que vai escrito no bloco: (onde, fonte, texto, e_cliente, alinhamento).

        De cima para baixo: horario, titulo e, bem pequeno, a cliente - quem
        bate o olho na agenda ja sabe para quem e. Sem altura para a terceira
        linha, a cliente vai ao lado do horario; no bloco mais baixo, tudo
        cabe numa linha so.
        """
        area = QRectF(rect.left() + 8, rect.top() + 3, rect.width() - 12, rect.height() - 6)
        hora = compromisso.inicio_dt.strftime("%H:%M")
        cliente = (compromisso.cliente or "").strip()
        esquerda = Qt.AlignmentFlag.AlignLeft
        legenda = QFontMetrics(font_for("caption"), self)

        if rect.height() < ALTURA_MINIMA_TITULO:
            linha = f"{hora}  {compromisso.titulo}"
            if cliente:
                linha += f"  ·  {cliente}"
            return [(area, "caption", linha, False, esquerda | Qt.AlignmentFlag.AlignVCenter)]

        forte = QFontMetrics(font_for("strong"), self)
        topo_titulo = area.top() + ALTURA_LINHA_HORA
        espaco = area.bottom() - topo_titulo
        embaixo = bool(cliente) and espaco >= forte.height() + legenda.height()

        textos = [(QRectF(area.left(), area.top(), area.width(), ALTURA_LINHA_HORA),
                   "caption", hora, False, esquerda)]
        if cliente and not embaixo:
            x = area.left() + legenda.horizontalAdvance(hora) + 6
            nome = legenda.elidedText(f"·  {cliente}", Qt.TextElideMode.ElideRight,
                                      int(area.right() - x))
            textos.append((QRectF(x, area.top(), area.right() - x, ALTURA_LINHA_HORA),
                           "caption", nome, True, esquerda))

        # o titulo ocupa so as linhas que usa: a cliente vem logo depois dele
        reserva = legenda.height() if embaixo else 0
        linhas = max(1, int((espaco - reserva) // forte.lineSpacing()))
        medido = forte.boundingRect(
            QRect(0, 0, int(area.width()), 10_000), Qt.TextFlag.TextWordWrap, compromisso.titulo
        ).height()
        altura_titulo = min(medido, linhas * forte.lineSpacing())
        textos.append((QRectF(area.left(), topo_titulo, area.width(), max(altura_titulo, 0)),
                       "strong", compromisso.titulo, False, esquerda | Qt.TextFlag.TextWordWrap))
        if embaixo:
            nome = legenda.elidedText(cliente, Qt.TextElideMode.ElideRight, int(area.width()))
            textos.append((QRectF(area.left(), topo_titulo + altura_titulo, area.width(),
                                  legenda.height()), "caption", nome, True, esquerda))
        return textos

    def _linha_de_agora(self, painter: QPainter) -> None:
        """A linha da hora atual: e o que faz a grade parecer viva."""
        agora = datetime.now()
        coluna = next(
            (i for i, dia in enumerate(self.grade.dias) if dia.data == agora.date()),
            None,
        )
        if coluna is None or not (
            self.grade.hora_inicial <= agora.hour < self.grade.hora_final
        ):
            return

        largura = self._largura_coluna()
        y = self._y_da_hora(agora)
        painter.setPen(QPen(QColor(self._palette.danger), 2))
        painter.drawLine(
            QPointF(GUTTER + coluna * largura, y),
            QPointF(GUTTER + (coluna + 1) * largura, y),
        )
        painter.setBrush(QColor(self._palette.danger))
        painter.drawEllipse(QRectF(GUTTER + coluna * largura - 3, y - 3, 6, 6))

    # ------------------------------------------------------------------ eventos
    def _bloco_em(self, posicao) -> Compromisso | None:
        for rect, compromisso in reversed(self._blocos):
            if rect.contains(posicao):
                return compromisso
        return None

    def _momento_em(self, posicao) -> str:
        """Onde o usuario clicou, em data e hora - arredondado em 30 minutos."""
        if posicao.y() < CABECALHO or posicao.x() < GUTTER:
            return ""
        coluna = int((posicao.x() - GUTTER) // self._largura_coluna())
        if not 0 <= coluna < len(self.grade.dias):
            return ""
        minutos = (posicao.y() - CABECALHO) / self._altura_hora() * 60
        # arredondar antes de fatiar: clicar exatamente na linha das 9h30 dava
        # 9h00 quando a conta em ponto flutuante caia em 149,99999
        minutos = int(round(minutos) // 30 * 30)
        quando = datetime.combine(
            self.grade.dias[coluna].data, time(self.grade.hora_inicial)
        ) + timedelta(minutes=minutos)
        return quando.isoformat(timespec="minutes")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        posicao = event.position()
        bloco = self._bloco_em(posicao)
        if bloco is not None:
            self.selecao = bloco.id
            self.update()
            self.selecionado.emit(bloco.id)
            return
        momento = self._momento_em(posicao)
        if momento:
            self.selecao = None
            self.update()
            self.vazio.emit(momento)

    def event(self, event) -> bool:  # noqa: N802 (Qt)
        """A dica do bloco: quem marcou pelo link e o WhatsApp dele."""
        if event.type() == QEvent.Type.ToolTip:
            bloco = self._bloco_em(QPointF(event.pos()))
            if bloco is not None and (bloco.pelo_link or bloco.telefone):
                linhas = [f"{bloco.horario} · {bloco.titulo}"]
                if bloco.cliente:
                    linhas.append(bloco.cliente)
                if bloco.telefone:
                    linhas.append(f"WhatsApp {formatar_telefone(bloco.telefone)}")
                if bloco.pelo_link:
                    linhas.append("Marcado pelo cliente no link de agendamento")
                QToolTip.showText(event.globalPos(), "\n".join(linhas), self)
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        bloco = self._bloco_em(event.position())
        if bloco is not None:
            self.aberto.emit(bloco.id)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """Botao direito em cima de um compromisso: seleciona e pede o menu.

        Selecionar antes de abrir o menu importa: o que o menu faz vale para o
        compromisso que esta embaixo do cursor, e nao para o que estava
        marcado de antes.
        """
        bloco = self._bloco_em(QPointF(event.pos()))
        if bloco is None:
            return
        self.selecao = bloco.id
        self.update()
        self.selecionado.emit(bloco.id)
        self.menu_pedido.emit(bloco.id, event.globalPos())
