"""O tempo desenhado: horas na lateral, dias em colunas, blocos por duracao.

O espaco vazio na tela e o horario vago na vida real - e por isso que uma
agenda precisa de grade e nao de lista. Clicar no vazio marca ali mesmo, que e
o gesto natural de quem aponta para o buraco.

O cabecalho dos dias fica parado no topo enquanto as horas rolam: sem ele, a
coluna de quarta e igual a de quinta. Cada dia mostra quanto do horario da loja
ja encheu, e o que esta fechado (almoco, domingo, a noite) fica sombreado - as
duas coisas saem do `Expediente`, o horario de atendimento da aba Online.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QToolTip, QWidget

from ....core.documentos import formatar_telefone
from ....ui import format as fmt
from ....ui import icons
from ....ui.theme import Radius, current_palette, font_for, mix, palette_for
from ..models import (
    AGENDADO,
    CANCELADO,
    CONCLUIDO,
    DIAS_SEMANA,
    MESES,
    Compromisso,
    Expediente,
    Grade,
)

#: medidas da grade
GUTTER = 58
CABECALHO = 74
#: a linha da hora estica para o dia caber na tela, mas nao passa destes
#: limites: apertada demais o texto some, folgada demais vira desperdicio
ALTURA_HORA_MINIMA = 44
ALTURA_HORA_MAXIMA = 64
FOLGA = 3
#: 15 minutos tambem precisam de uma linha que se leia
ALTURA_MINIMA_BLOCO = 20
#: a partir destas alturas o bloco ganha a segunda e a terceira linha
ALTURA_DUAS_LINHAS = 34
ALTURA_TRES_LINHAS = 50
#: o vazio apontado pelo mouse vira um horario deste tamanho
PASSO_DO_VAZIO = 30

DIAS_DO_CABECALHO = ("SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM")


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
        #: o horario da loja; sem ele, sombreia o fim de semana e nao mede nada
        self.expediente: Expediente | None = None
        self.selecao: int | None = None
        self._palette = palette_for(parent) if parent else current_palette()
        self._blocos: list[tuple[QRectF, Compromisso]] = []
        #: o que esta debaixo do mouse: um bloco (id) ou um vazio (coluna, minutos)
        self._sobre: int | None = None
        self._vago: tuple[int, int] | None = None
        self.setMouseTracking(True)
        self.setMinimumWidth(560)
        # a linha de agora anda sozinha
        self._relogio = QTimer(self)
        self._relogio.setInterval(30_000)
        self._relogio.timeout.connect(self._passou_o_tempo)
        self._relogio.start()

    def set_grade(self, grade: Grade, expediente: Expediente | None = None) -> None:
        self.grade = grade
        if expediente is not None:
            self.expediente = expediente
        # minimo, e nao fixo: com poucas horas a linha estica ate encher a
        # tela; se nem no minimo couber, a area rola
        self.setMinimumHeight(CABECALHO + self._horas() * ALTURA_HORA_MINIMA)
        self.update()

    def apply_theme(self, palette) -> None:
        self._palette = palette
        self.update()

    def y_da_hora_cheia(self, hora: int) -> int:
        """Onde comeca a linha de uma hora - a tela usa para se posicionar."""
        passo = max(0, min(hora, self.grade.hora_final) - self.grade.hora_inicial)
        return int(CABECALHO + passo * self._altura_hora())

    def _passou_o_tempo(self) -> None:
        if self.isVisible():
            self.update()

    def _horas(self) -> int:
        return max(self.grade.hora_final - self.grade.hora_inicial, 1)

    def _altura_hora(self) -> float:
        """Quanto vale uma hora em pixels, agora.

        Com poucas horas na faixa a linha fica folgada; com muitas ela aperta
        ate o minimo e a area rola - o cabecalho fica parado no topo.
        """
        disponivel = (self.height() - CABECALHO) / self._horas()
        return min(ALTURA_HORA_MAXIMA, max(ALTURA_HORA_MINIMA, disponivel))

    def _largura_coluna(self) -> float:
        return max((self.width() - GUTTER) / max(len(self.grade.dias), 1), 1.0)

    def _y_da_hora(self, momento: datetime) -> float:
        minutos = (momento.hour - self.grade.hora_inicial) * 60 + momento.minute
        return CABECALHO + minutos / 60 * self._altura_hora()

    def _topo(self) -> float:
        """Onde o cabecalho fica agora: no topo do que esta a vista.

        Dentro da area de rolagem o widget inteiro sobe; o cabecalho desce o
        mesmo tanto e parece parado. A area avisa quando rola (`update`).
        """
        return float(max(0, -self.y()))

    # ------------------------------------------------------------------ desenho
    def paintEvent(self, event) -> None:  # noqa: N802 (assinatura do Qt)
        if not self.grade.dias:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        self._blocos = []
        self._fundo(painter)
        self._horas_e_linhas(painter)
        for indice, dia in enumerate(self.grade.dias):
            self._blocos_do_dia(painter, indice, dia)
        self._vazio_apontado(painter)
        self._linha_de_agora(painter)
        # por ultimo: o que rolou para baixo do cabecalho fica escondido
        self._cabecalho(painter)
        painter.end()

    def _fechados(self, dia) -> list[tuple[int, int]]:
        """Os pedacos do dia (em minutos) em que a loja esta fechada."""
        inicio, fim = self.grade.hora_inicial * 60, self.grade.hora_final * 60
        if self.expediente is None:
            return [(inicio, fim)] if dia.fim_de_semana else []
        fechados, cursor = [], inicio
        for de, ate in sorted(self.expediente.aberto(dia.data)):
            if de > cursor:
                fechados.append((cursor, min(de, fim)))
            cursor = max(cursor, ate)
        if cursor < fim:
            fechados.append((cursor, fim))
        return [(de, ate) for de, ate in fechados if ate > de]

    def _fundo(self, painter: QPainter) -> None:
        p = self._palette
        painter.fillRect(self.rect(), QColor(p.surface))
        largura = self._largura_coluna()
        altura = self._altura_hora()
        hoje = QColor(mix(p.surface, p.accent, 0.08 if p.is_dark else 0.05))
        # fechado e mais escuro nos dois temas: no escuro, clarear parecia destaque
        sombra = QColor(0, 0, 0) if p.is_dark else QColor(p.text)
        sombra.setAlphaF(0.22 if p.is_dark else 0.035)
        for indice, dia in enumerate(self.grade.dias):
            x = GUTTER + indice * largura
            if dia.e_hoje:
                painter.fillRect(QRectF(x, CABECALHO, largura, self._horas() * altura), hoje)
            for de, ate in self._fechados(dia):
                topo = CABECALHO + (de - self.grade.hora_inicial * 60) / 60 * altura
                painter.fillRect(QRectF(x, topo, largura, (ate - de) / 60 * altura), sombra)

    def _horas_e_linhas(self, painter: QPainter) -> None:
        p = self._palette
        painter.setFont(font_for("caption"))
        largura = self._largura_coluna()
        altura = self._altura_hora()
        base = CABECALHO + self._horas() * altura
        hora_cheia = QPen(QColor(p.border_soft), 1)
        meia = QColor(p.border_soft)
        meia.setAlphaF(0.55)
        meia_hora = QPen(meia, 1, Qt.PenStyle.DashLine)

        for passo in range(self._horas() + 1):
            y = CABECALHO + passo * altura
            painter.setPen(hora_cheia)
            painter.drawLine(QPointF(GUTTER, y), QPointF(self.width(), y))
            if passo == self._horas():
                continue
            # a meia hora, mais leve: ajuda a mirar o clique
            painter.setPen(meia_hora)
            painter.drawLine(QPointF(GUTTER, y + altura / 2), QPointF(self.width(), y + altura / 2))
            painter.setPen(QColor(p.text_dim))
            # abaixo da linha, senao a primeira hora fica sob o cabecalho
            painter.drawText(
                QRectF(0, y + 3, GUTTER - 12, 15),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{self.grade.hora_inicial + passo:02d}:00",
            )

        painter.setPen(hora_cheia)
        for indice in range(len(self.grade.dias) + 1):
            x = GUTTER + indice * largura
            painter.drawLine(QPointF(x, CABECALHO), QPointF(x, base))

    def _cabecalho(self, painter: QPainter) -> None:
        """Dia da semana, o numero grande e quanto o dia ja encheu."""
        p = self._palette
        topo = self._topo()
        largura = self._largura_coluna()
        painter.fillRect(QRectF(0, topo, self.width(), CABECALHO), QColor(p.surface))
        if topo > 0:
            # rolou: uma sombra curta mostra que as horas passam por baixo
            gradiente = QLinearGradient(0, topo + CABECALHO, 0, topo + CABECALHO + 8)
            gradiente.setColorAt(0, QColor(0, 0, 0, 46 if p.is_dark else 20))
            gradiente.setColorAt(1, QColor(0, 0, 0, 0))
            painter.fillRect(QRectF(0, topo + CABECALHO, self.width(), 8), gradiente)
        painter.setPen(QPen(QColor(p.border), 1))
        painter.drawLine(QPointF(0, topo + CABECALHO - 0.5),
                         QPointF(self.width(), topo + CABECALHO - 0.5))

        hoje = date.today()
        centro_v = Qt.AlignmentFlag.AlignCenter
        for indice, dia in enumerate(self.grade.dias):
            x = GUTTER + indice * largura
            meio = x + largura / 2
            passado = dia.data < hoje

            painter.setFont(font_for("overline"))
            painter.setPen(QColor(p.accent if dia.e_hoje else (p.text_dim if passado else p.text_muted)))
            painter.drawText(QRectF(x, topo + 8, largura, 14), centro_v,
                             DIAS_DO_CABECALHO[dia.data.weekday()])

            circulo = QRectF(meio - 18, topo + 24, 36, 36)
            if dia.e_hoje:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(p.accent))
                painter.drawEllipse(circulo)
                painter.setPen(QColor(p.on_accent))
            else:
                painter.setPen(QColor(p.text_muted if passado else p.text))
            painter.setFont(font_for("title"))
            painter.drawText(circulo, centro_v, str(dia.data.day))

            self._ocupacao(painter, dia, x, largura, topo + 65)

    def _ocupacao(self, painter: QPainter, dia, x: float, largura: float, y: float) -> None:
        """A barrinha do dia: quanto do horario aberto ja tem gente marcada."""
        if self.expediente is None:
            return
        p = self._palette
        cheio = self.expediente.ocupacao(dia)
        if cheio is None:
            painter.setFont(font_for("caption"))
            painter.setPen(QColor(p.text_dim))
            painter.drawText(QRectF(x, y - 6, largura, 13), Qt.AlignmentFlag.AlignCenter, "Fechado")
            return
        comprimento = min(largura - 28, 56.0)
        if comprimento < 16:
            return
        trilho = QRectF(x + (largura - comprimento) / 2, y, comprimento, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(mix(p.surface, p.text, 0.10)))
        painter.drawRoundedRect(trilho, 2, 2)
        if cheio > 0:
            painter.setBrush(QColor(p.accent))
            painter.drawRoundedRect(
                QRectF(trilho.left(), y, max(4.0, comprimento * cheio), 4), 2, 2)

    def _blocos_do_dia(self, painter: QPainter, coluna: int, dia) -> None:
        largura = self._largura_coluna()
        faixas = _faixas(dia.compromissos)
        fundo_da_grade = CABECALHO + self._horas() * self._altura_hora()

        for compromisso in dia.compromissos:
            if compromisso.inicio_dt is None or compromisso.id not in faixas:
                continue
            faixa, total = faixas[compromisso.id]
            topo = max(self._y_da_hora(compromisso.inicio_dt), CABECALHO)
            base = min(self._y_da_hora(compromisso.fim_dt), fundo_da_grade)
            if base <= topo:
                continue
            base = min(max(base, topo + ALTURA_MINIMA_BLOCO), fundo_da_grade)

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
        concluido = compromisso.status == CONCLUIDO

        # o cartao e opaco: a linha da meia hora nao atravessa o texto
        forca = 0.05 if cancelado else 0.09 if concluido else (0.26 if p.is_dark else 0.15)
        if compromisso.id == self._sobre and not cancelado:
            forca += 0.06
        caminho = QPainterPath()
        caminho.addRoundedRect(rect, Radius.sm, Radius.sm)
        painter.fillPath(caminho, QColor(mix(p.surface, cor.name(), forca)))
        if compromisso.id == self.selecao:
            painter.setPen(QPen(QColor(p.accent), 2))
        else:
            painter.setPen(QPen(QColor(mix(p.surface, cor.name(), 0.18 if cancelado else 0.38)), 1))
        painter.drawPath(caminho)

        painter.save()
        painter.setClipPath(caminho)
        self._faixa_do_tipo(painter, rect, cor, compromisso)
        painter.restore()

        painter.save()
        painter.setClipRect(rect)
        sinais = self._sinais(painter, rect, compromisso, cor)
        self._escrever(painter, rect.adjusted(0, 0, -14 * sinais, 0), compromisso, cor)
        painter.restore()

    def _faixa_do_tipo(self, painter: QPainter, rect: QRectF, cor: QColor,
                       compromisso: Compromisso) -> None:
        """A faixa da esquerda diz o tipo de longe.

        Cheia quando o cliente ja confirmou; tracejada enquanto o horario
        ainda espera confirmacao. Fechado ou cancelado, ela desbota.
        """
        faixa = QColor(cor)
        if compromisso.status in (CANCELADO, CONCLUIDO):
            faixa.setAlphaF(0.45)
        barra = QRectF(rect.left(), rect.top(), 3.5, rect.height())
        if compromisso.status != AGENDADO or compromisso.e_bloqueio:
            painter.fillRect(barra, faixa)
            return
        y = barra.top()
        while y < barra.bottom():
            painter.fillRect(QRectF(barra.left(), y, barra.width(), min(5.0, barra.bottom() - y)), faixa)
            y += 8

    def _sinais(self, painter: QPainter, rect: QRectF, compromisso: Compromisso,
                cor: QColor) -> int:
        """Os sinais do canto: marcado pelo link, ja concluido, passou sem fechar."""
        p = self._palette
        if rect.width() < 56 or rect.height() < 16:
            return 0
        sinais: list[tuple[str, str]] = []
        if compromisso.pelo_link:
            sinais.append(("link", cor.name()))
        if compromisso.status == CONCLUIDO:
            sinais.append(("check", p.success))
        if compromisso.atrasado:
            sinais.append(("ponto", p.warning))
        x = rect.right() - 16
        y = rect.top() + (4 if rect.height() >= ALTURA_DUAS_LINHAS else (rect.height() - 12) / 2)
        for nome, tom in sinais:
            if nome == "ponto":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(tom))
                painter.drawEllipse(QPointF(x + 6, y + 6), 3.5, 3.5)
            else:
                painter.drawPixmap(QPointF(x, y), icons.pixmap(nome, tom, 12, width=2.2))
            x -= 14
        return len(sinais)

    def _escrever(self, painter: QPainter, rect: QRectF, compromisso: Compromisso,
                  cor: QColor) -> None:
        """Pinta o que `_textos` arrumou, cada pedaco na sua cor."""
        p = self._palette
        cancelado = compromisso.status == CANCELADO
        apagado = cancelado or compromisso.status == CONCLUIDO
        cores = {
            "hora": QColor(p.text_dim if apagado else mix(cor.name(), p.text, 0.25)),
            "titulo": QColor(p.text_dim if cancelado else (p.text_muted if apagado else p.text)),
            "cliente": QColor(p.text_dim if apagado else p.text_muted),
        }
        for area, papel, texto, _cliente, alinhamento, tom in self._textos(rect, compromisso):
            fonte = font_for(papel)
            fonte.setStrikeOut(cancelado and tom == "titulo")
            painter.setFont(fonte)
            painter.setPen(cores[tom])
            painter.drawText(area, alinhamento, texto)

    def _textos(self, rect: QRectF, compromisso: Compromisso) -> list[tuple]:
        """O que vai escrito no bloco: (onde, fonte, texto, e_cliente, alinhamento, tom).

        Cartao alto: o horario inteiro, o servico (quebra linha) e, pequeno, a
        cliente embaixo - quem bate o olho na agenda ja sabe para quem e. No
        medio, horario e servico dividem a primeira linha e a cliente vem na
        segunda. No baixo, tudo numa linha so, no que couber.
        """
        area = QRectF(rect.left() + 10, rect.top() + 4, rect.width() - 16, rect.height() - 7)
        inicio, fim = compromisso.inicio_dt, compromisso.fim_dt
        hora = inicio.strftime("%H:%M")
        cliente = (compromisso.cliente or "").strip()
        esquerda = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        medida = QFontMetrics(font_for("caption"), self)
        medida_forte = QFontMetrics(font_for("strong"), self)

        def cortar(texto: str, metrica: QFontMetrics, largura: float) -> str:
            return metrica.elidedText(texto, Qt.TextElideMode.ElideRight, int(largura))

        depois_da_hora = area.left() + medida.horizontalAdvance(hora) + 6
        if rect.height() < ALTURA_DUAS_LINHAS:
            resto = compromisso.titulo + (f"  ·  {cliente}" if cliente else "")
            return [
                (QRectF(area.left(), rect.top(), area.width(), rect.height()),
                 "caption", hora, False, esquerda, "hora"),
                (QRectF(depois_da_hora, rect.top(), area.right() - depois_da_hora, rect.height()),
                 "caption", cortar(resto, medida, area.right() - depois_da_hora), False, esquerda,
                 "titulo"),
            ]

        if rect.height() < ALTURA_TRES_LINHAS:
            primeira = medida_forte.height()
            textos = [
                (QRectF(area.left(), area.top(), area.width(), primeira),
                 "caption", hora, False, esquerda, "hora"),
                (QRectF(depois_da_hora, area.top(), area.right() - depois_da_hora, primeira),
                 "strong", cortar(compromisso.titulo, medida_forte, area.right() - depois_da_hora),
                 False, esquerda, "titulo"),
            ]
            if cliente:
                textos.append((QRectF(area.left(), area.top() + primeira, area.width(), medida.height()),
                               "caption", cortar(cliente, medida, area.width()), True, esquerda,
                               "cliente"))
            return textos

        intervalo = f"{hora} – {fim.strftime('%H:%M')}" if fim is not None else hora
        if medida.horizontalAdvance(intervalo) > area.width():
            intervalo = hora
        textos = [(QRectF(area.left(), area.top(), area.width(), medida.height()),
                   "caption", intervalo, False, esquerda, "hora")]

        topo = area.top() + medida.height() + 1
        reserva = medida.height() if cliente else 0
        linhas = max(1, int((area.bottom() - topo - reserva) // medida_forte.lineSpacing()))
        medido = medida_forte.boundingRect(
            QRect(0, 0, int(area.width()), 10_000), Qt.TextFlag.TextWordWrap, compromisso.titulo
        ).height()
        altura_titulo = min(medido, linhas * medida_forte.lineSpacing())
        lugar = QRectF(area.left(), topo, area.width(), altura_titulo)
        if linhas == 1 and medido > medida_forte.lineSpacing():
            # uma linha so: reticencias, e nao a palavra cortada no meio
            textos.append((lugar, "strong", cortar(compromisso.titulo, medida_forte, area.width()),
                           False, esquerda, "titulo"))
        else:
            textos.append((lugar, "strong", compromisso.titulo, False,
                           Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, "titulo"))
        if cliente and topo + altura_titulo + medida.height() <= area.bottom() + 2:
            textos.append((QRectF(area.left(), topo + altura_titulo, area.width(), medida.height()),
                           "caption", cortar(cliente, medida, area.width()), True, esquerda, "cliente"))
        return textos

    def _vazio_apontado(self, painter: QPainter) -> None:
        """O horario vago debaixo do mouse vira um convite: "+ 14:30"."""
        if self._vago is None:
            return
        p = self._palette
        rect = self._rect_do_vago(*self._vago)
        if rect.top() < self._topo() + CABECALHO:
            return
        caminho = QPainterPath()
        caminho.addRoundedRect(rect, Radius.sm, Radius.sm)
        painter.fillPath(caminho, QColor(mix(p.surface, p.accent, 0.10)))
        painter.setPen(QPen(QColor(mix(p.surface, p.accent, 0.60)), 1, Qt.PenStyle.DashLine))
        painter.drawPath(caminho)
        minutos = self._vago[1]
        painter.setFont(font_for("caption"))
        painter.setPen(QColor(p.accent))
        painter.drawText(rect.adjusted(9, 0, -6, 0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"+  {minutos // 60:02d}:{minutos % 60:02d}")

    def _rect_do_vago(self, coluna: int, minutos: int) -> QRectF:
        largura = self._largura_coluna()
        altura = self._altura_hora()
        y = CABECALHO + (minutos - self.grade.hora_inicial * 60) / 60 * altura
        return QRectF(GUTTER + coluna * largura + FOLGA, y + 1,
                      largura - FOLGA * 2, PASSO_DO_VAZIO / 60 * altura - 2)

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

        p = self._palette
        largura = self._largura_coluna()
        y = self._y_da_hora(agora)
        vermelho = QColor(p.danger)
        fraco = QColor(p.danger)
        fraco.setAlphaF(0.30)
        # fraca na semana toda, forte no dia de hoje
        painter.setPen(QPen(fraco, 1))
        painter.drawLine(QPointF(GUTTER, y), QPointF(self.width(), y))
        x = GUTTER + coluna * largura
        painter.setPen(QPen(vermelho, 2))
        painter.drawLine(QPointF(x, y), QPointF(x + largura, y))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(vermelho)
        painter.drawEllipse(QPointF(x, y), 4, 4)

        # a hora certa na regua, por cima do rotulo da hora cheia
        fonte = font_for("kbd")
        texto = agora.strftime("%H:%M")
        largura_texto = QFontMetrics(fonte, self).horizontalAdvance(texto) + 12
        etiqueta = QRectF(GUTTER - 6 - largura_texto, y - 8, largura_texto, 16)
        painter.drawRoundedRect(etiqueta, 8, 8)
        painter.setFont(fonte)
        painter.setPen(QColor(p.on_accent))
        painter.drawText(etiqueta, Qt.AlignmentFlag.AlignCenter, texto)

    # ------------------------------------------------------------------ eventos
    def _no_cabecalho(self, posicao) -> bool:
        return posicao.y() < self._topo() + CABECALHO

    def _bloco_em(self, posicao) -> Compromisso | None:
        if self._no_cabecalho(posicao):
            return None
        for rect, compromisso in reversed(self._blocos):
            if rect.contains(posicao):
                return compromisso
        return None

    def _vago_em(self, posicao) -> tuple[int, int] | None:
        """(coluna, minutos desde a meia-noite) do ponto - em passos de 30 min."""
        if self._no_cabecalho(posicao) or posicao.x() < GUTTER:
            return None
        coluna = int((posicao.x() - GUTTER) // self._largura_coluna())
        if not 0 <= coluna < len(self.grade.dias):
            return None
        minutos = (posicao.y() - CABECALHO) / self._altura_hora() * 60
        if minutos >= self._horas() * 60:
            return None
        # arredondar antes de fatiar: clicar exatamente na linha das 9h30 dava
        # 9h00 quando a conta em ponto flutuante caia em 149,99999
        minutos = int(round(minutos) // PASSO_DO_VAZIO * PASSO_DO_VAZIO)
        return coluna, self.grade.hora_inicial * 60 + minutos

    def _momento_em(self, posicao) -> str:
        """Onde o usuario clicou, em data e hora - arredondado em 30 minutos."""
        vago = self._vago_em(posicao)
        if vago is None:
            return ""
        coluna, minutos = vago
        quando = datetime.combine(self.grade.dias[coluna].data, time()) + timedelta(minutes=minutos)
        return quando.isoformat(timespec="minutes")

    def _vago_livre(self, vago: tuple[int, int]) -> bool:
        """O convite so aparece onde nao ha bloco desenhado."""
        rect = self._rect_do_vago(*vago)
        return not any(rect.intersects(bloco) for bloco, _ in self._blocos)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        posicao = event.position()
        bloco = self._bloco_em(posicao)
        vago = None if bloco is not None else self._vago_em(posicao)
        if vago is not None and not self._vago_livre(vago):
            vago = None
        sobre = bloco.id if bloco is not None else None
        if (sobre, vago) != (self._sobre, self._vago):
            self._sobre, self._vago = sobre, vago
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor if (bloco or vago)
                                   else Qt.CursorShape.ArrowCursor))
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._sobre is not None or self._vago is not None:
            self._sobre = self._vago = None
            self.update()
        super().leaveEvent(event)

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
            self._vago = None
            self.update()
            self.vazio.emit(momento)

    def _dica_do_dia(self, posicao) -> str:
        coluna = int((posicao.x() - GUTTER) // self._largura_coluna())
        if posicao.x() < GUTTER or not 0 <= coluna < len(self.grade.dias):
            return ""
        dia = self.grade.dias[coluna]
        texto = (f"{DIAS_SEMANA[dia.data.weekday()]}, {dia.data.day} de "
                 f"{MESES[dia.data.month - 1]}\n"
                 f"{fmt.contagem(len(dia.ocupados), 'compromisso', 'compromissos')}")
        cheio = self.expediente.ocupacao(dia) if self.expediente is not None else None
        if self.expediente is not None:
            texto += " · fechado" if cheio is None else f" · {round(cheio * 100)}% do horário ocupado"
        return texto

    def event(self, event) -> bool:  # noqa: N802 (Qt)
        """A dica: o dia (no cabecalho) ou o compromisso (no bloco)."""
        if event.type() == QEvent.Type.ToolTip:
            posicao = QPointF(event.pos())
            if self._no_cabecalho(posicao):
                texto = self._dica_do_dia(posicao)
            else:
                bloco = self._bloco_em(posicao)
                texto = self._dica_do_bloco(bloco) if bloco is not None else ""
            if texto:
                QToolTip.showText(event.globalPos(), texto, self)
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)

    @staticmethod
    def _dica_do_bloco(bloco: Compromisso) -> str:
        linhas = [f"{bloco.horario} · {bloco.titulo}"]
        if bloco.cliente:
            linhas.append(bloco.cliente)
        if bloco.telefone:
            linhas.append(f"WhatsApp {formatar_telefone(bloco.telefone)}")
        situacao = bloco.status_label
        if bloco.atrasado:
            situacao += " · passou e ainda está em aberto"
        elif bloco.status == AGENDADO and not bloco.e_bloqueio:
            situacao += " · falta confirmar"
        linhas.append(situacao)
        if bloco.pelo_link:
            linhas.append("Marcado pelo cliente no link de agendamento")
        return "\n".join(linhas)

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
