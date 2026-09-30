"""Os graficos da plataforma.

Um painel cheio de listas obriga a pessoa a ler numero por numero para
descobrir o que esta grande e o que esta pequeno. O grafico responde isso antes
da leitura - e essa e a unica razao de ele existir aqui.

Todos seguem as mesmas regras, que sao as que costumam faltar em grafico feito
as pressas:

- **Nada sai da area.** Cada desenho calcula a area util **depois** de reservar
  o espaco dos rotulos. Rotulo cortado e o defeito classico, e e sempre a
  informacao que interessa que some.
- **A escala mostra o zero.** Um grafico que corta o zero esconde justamente a
  diferenca que a pessoa quer ver.
- **Toda cor vem do tema.** Nada de `#hex` solto: os tons sao os mesmos tokens
  do resto do programa (`accent`, `success`, `danger`...), entao o grafico
  acompanha a troca de tema como qualquer outro widget.
- **Sem dado, sem grafico.** Aparece uma frase no lugar, e nao uma moldura
  vazia.
- **Cresce quando o dado muda, e so entao.** Voltar para a mesma tela com o
  mesmo numero nao repete o movimento - movimento sem novidade e so espera.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget

from .motion import Progresso
from .theme import Palette, current_palette, font_for, palette_for

#: sequencia de tons para series sem cor propria - contraste antes de variedade
SEQUENCIA = ("accent", "success", "warning", "info", "danger", "accent_muted")
#: a fatia que junta o resto nunca compete com as de verdade
TOM_OUTROS = "accent_muted"

RECUO = 10
ESPACO_ROTULO = 6


@dataclass(frozen=True)
class Fatia:
    """Um pedaco de qualquer grafico: um rotulo, um valor e um tom."""

    rotulo: str
    valor: float
    tom: str = ""
    #: texto pronto do valor (R$ 1.234,00); sem ele, sai o numero cru
    texto: str = ""

    def escrito(self) -> str:
        return self.texto or f"{self.valor:g}".replace(".", ",")


class GraficoBase(QWidget):
    """O que todo grafico daqui tem: tema, area util e o vazio dito em palavras."""

    vazio = "Sem dados para mostrar ainda."

    def __init__(self, parent: QWidget | None = None, altura: int = 150) -> None:
        super().__init__(parent)
        self.fatias: list[Fatia] = []
        self._palette = palette_for(parent) if parent else current_palette()
        self._progresso = Progresso(self)
        self.setMinimumHeight(altura)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    # ------------------------------------------------------------------ dados
    def set_fatias(self, fatias) -> None:
        novas = [f for f in fatias if f is not None]
        mudou = novas != self.fatias
        self.fatias = novas
        if mudou:
            self._progresso.reiniciar()
        else:
            self.update()

    def apply_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    @property
    def progresso(self) -> float:
        """0 a 1: quanto do desenho ja cresceu."""
        return self._progresso.valor

    # ------------------------------------------------------------------ pintura
    def cor(self, tom: str, posicao: int = 0) -> QColor:
        return QColor(self._palette.resolve(tom or SEQUENCIA[posicao % len(SEQUENCIA)]))

    def cor_da(self, fatia: Fatia, posicao: int) -> QColor:
        """A cor de uma fatia: a dela, a de "Outros", ou a da sequencia."""
        if not fatia.tom and fatia.rotulo == "Outros":
            return self.cor(TOM_OUTROS)
        return self.cor(fatia.tom, posicao)

    def paintEvent(self, evento) -> None:  # noqa: N802 (assinatura do Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.fatias:
            self._dizer_vazio(pintor)
        else:
            self.desenhar(pintor)
        pintor.end()

    def desenhar(self, pintor: QPainter) -> None:  # pragma: no cover - abstrato
        raise NotImplementedError

    def _dizer_vazio(self, pintor: QPainter) -> None:
        pintor.setFont(font_for("muted"))
        pintor.setPen(QColor(self._palette.text_dim))
        pintor.drawText(QRectF(0, 0, self.width(), self.height()),
                        Qt.AlignmentFlag.AlignCenter, self.vazio)

    def _texto(self, pintor: QPainter, area: QRectF, texto: str,
               alinhamento=Qt.AlignmentFlag.AlignLeft, papel: str = "caption",
               cor: str = "text_muted") -> None:
        """Escreve dentro da area, cortando com reticencias em vez de vazar."""
        pintor.setFont(font_for(papel))
        pintor.setPen(QColor(self._palette.resolve(cor)))
        metrica = QFontMetrics(font_for(papel))
        cabe = metrica.elidedText(texto, Qt.TextElideMode.ElideRight,
                                  int(area.width()))
        pintor.drawText(area, alinhamento | Qt.AlignmentFlag.AlignVCenter, cabe)


#: medidas da barra em tracos - a mesma em todo lugar que mostra "quanto"
TRACO = 4.0
VAO_TRACO = 3.0
ALTURA_TRACO = 9


def pintar_tracos(pintor: QPainter, x: float, y: float, largura: float, fracao: float,
                  cor: QColor, palette: Palette, progresso: float = 1.0,
                  altura: float = ALTURA_TRACO) -> None:
    """Uma barra feita de tracos: cheios ate a fracao, o resto e trilho.

    E o desenho de "quanto" da plataforma inteira - o grafico de barras, o
    funil do Orcamentos. Em traco, e nao em barra cheia, porque o traco da a
    escala de graca: da para contar de olho quantas vezes uma cabe na outra.
    """
    quantos = max(1, int((largura + VAO_TRACO) // (TRACO + VAO_TRACO)))
    cheios = round(quantos * max(0.0, min(fracao, 1.0)) * progresso)
    if fracao > 0 and cheios == 0 and progresso > 0.2:
        cheios = 1  # valor pequeno nao some: ganha pelo menos um traco
    trilho = QColor(palette.surface_hover if palette.is_dark else palette.surface_alt)
    pintor.setPen(Qt.PenStyle.NoPen)
    for indice in range(quantos):
        pintor.setBrush(cor if indice < cheios else trilho)
        pintor.drawRoundedRect(
            QRectF(x + indice * (TRACO + VAO_TRACO), y, TRACO, altura), 1.6, 1.6
        )


class GraficoBarras(GraficoBase):
    """Barras deitadas, em tracos: para ranking - quem vende mais, onde vai.

    Deitadas, e nao em pe, porque o rotulo e um nome ("Fornecedor de
    perifericos") e nome em pe vira texto de lado, que ninguem le. Em tracos,
    e nao em barra cheia, porque o traco da a escala de graca: da para contar
    de olho quantas vezes uma linha cabe na outra.

    Com altura sobrando, o nome e o valor ficam em cima da barra; apertado,
    tudo vai para a mesma linha - nunca por cima um do outro.
    """

    ALTURA_BARRA = ALTURA_TRACO
    ESPACO = 12
    ALTURA_TEXTO = 17

    def __init__(self, parent: QWidget | None = None, largura_rotulo: int = 150) -> None:
        super().__init__(parent, altura=120)
        self.largura_rotulo = largura_rotulo

    def _passo_alto(self) -> int:
        return self.ALTURA_TEXTO + 6 + self.ALTURA_BARRA + self.ESPACO

    def altura_ideal(self) -> int:
        return max(len(self.fatias), 1) * self._passo_alto()

    def desenhar(self, pintor: QPainter) -> None:
        maior = max((abs(f.valor) for f in self.fatias), default=0.0) or 1.0
        if len(self.fatias) * self._passo_alto() - self.ESPACO <= self.height():
            self._em_duas_linhas(pintor, maior)
        else:
            self._em_uma_linha(pintor, maior)

    def _tracos(self, pintor: QPainter, x: float, y: float, largura: float,
                fracao: float, cor: QColor) -> None:
        pintar_tracos(pintor, x, y, largura, fracao, cor, self._palette,
                      self.progresso, self.ALTURA_BARRA)

    def _em_duas_linhas(self, pintor: QPainter, maior: float) -> None:
        passo = self._passo_alto()
        ocupado = len(self.fatias) * passo - self.ESPACO
        topo = max(0.0, (self.height() - ocupado) / 2)
        metrica = QFontMetricsF(font_for("strong"))
        for posicao, fatia in enumerate(self.fatias):
            y = topo + posicao * passo
            valor = fatia.escrito()
            largura_valor = metrica.horizontalAdvance(valor) + 4
            self._texto(pintor, QRectF(0, y, self.width() - largura_valor - 12,
                                       self.ALTURA_TEXTO),
                        fatia.rotulo, papel="body", cor="text")
            self._texto(pintor, QRectF(self.width() - largura_valor, y, largura_valor,
                                       self.ALTURA_TEXTO),
                        valor, Qt.AlignmentFlag.AlignRight, "strong", "text")
            self._tracos(pintor, 0, y + self.ALTURA_TEXTO + 6, self.width(),
                         abs(fatia.valor) / maior, self.cor_da(fatia, posicao))

    def _em_uma_linha(self, pintor: QPainter, maior: float) -> None:
        linha = 24
        metrica = QFontMetricsF(font_for("strong"))
        # o valor tem largura propria reservada: sem isso a barra passa por
        # baixo do texto quando o numero e grande
        largura_valor = max(
            (metrica.horizontalAdvance(f.escrito()) for f in self.fatias), default=60
        ) + ESPACO_ROTULO
        rotulo = min(self.largura_rotulo, int(self.width() * 0.34))
        trilho = self.width() - rotulo - largura_valor - ESPACO_ROTULO * 2
        if trilho <= 10:
            return
        topo = max(0.0, (self.height() - len(self.fatias) * linha) / 2)
        for posicao, fatia in enumerate(self.fatias):
            y = topo + posicao * linha
            if y + linha > self.height() + 1:
                return  # o que nao cabe nao entra pela metade
            self._texto(pintor, QRectF(0, y, rotulo, linha), fatia.rotulo,
                        papel="body", cor="text")
            self._tracos(pintor, rotulo + ESPACO_ROTULO, y + (linha - self.ALTURA_BARRA) / 2,
                         trilho, abs(fatia.valor) / maior, self.cor_da(fatia, posicao))
            self._texto(pintor, QRectF(self.width() - largura_valor, y, largura_valor, linha),
                        fatia.escrito(), Qt.AlignmentFlag.AlignRight, "strong", "text")


class GraficoRosca(GraficoBase):
    """Rosca com o total no meio: para composicao - de que e feito o todo.

    O buraco no meio nao e enfeite: e onde mora o numero que resume tudo, e sem
    ele a pessoa fica somando fatia de olho. As fatias tem um vao entre si
    para que duas cores vizinhas nao virem uma mancha so.
    """

    ESPESSURA = 22
    #: acima disso a rosca vira enfeite e come o espaco da legenda
    MAIOR_LADO = 200
    #: vao entre as fatias, em graus
    VAO = 2.4

    def __init__(self, parent: QWidget | None = None, titulo_centro: str = "Total") -> None:
        super().__init__(parent, altura=180)
        self.titulo_centro = titulo_centro
        self.total_texto = ""

    def set_total(self, texto: str) -> None:
        self.total_texto = texto
        self.update()

    def desenhar(self, pintor: QPainter) -> None:
        total = sum(abs(f.valor) for f in self.fatias) or 1.0
        # a legenda fica a direita quando ha espaco, embaixo quando nao ha
        deitado = self.width() > 320
        lado = min(self.height(), self.width() * (0.45 if deitado else 1.0),
                   self.MAIOR_LADO)
        anel = QRectF(RECUO, (self.height() - lado) / 2 + RECUO,
                      lado - RECUO * 2, lado - RECUO * 2)
        espessura = max(14.0, min(float(self.ESPESSURA), anel.width() * 0.16))
        miolo = anel.adjusted(espessura / 2, espessura / 2, -espessura / 2, -espessura / 2)

        trilho = QPen(QColor(self._palette.surface_alt), espessura)
        trilho.setCapStyle(Qt.PenCapStyle.FlatCap)
        pintor.setPen(trilho)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawEllipse(miolo)

        vao = self.VAO if len(self.fatias) > 1 else 0.0
        limite = 360.0 * self.progresso
        comeco = 90.0
        andado = 0.0
        for posicao, fatia in enumerate(self.fatias):
            extensao = 360.0 * abs(fatia.valor) / total
            visivel = min(extensao, max(0.0, limite - andado))
            andado += extensao
            desenho = visivel - vao
            if desenho > 0.2:
                caneta = QPen(self.cor_da(fatia, posicao), espessura)
                caneta.setCapStyle(Qt.PenCapStyle.FlatCap)
                pintor.setPen(caneta)
                pintor.drawArc(miolo, int((comeco - vao / 2) * 16), int(-desenho * 16))
            comeco -= extensao

        if self.total_texto:
            interno = anel.adjusted(espessura + 6, espessura + 6, -espessura - 6, -espessura - 6)
            papel = "metricSoft" if interno.width() > 120 else "cardTitle"
            altura_total = QFontMetricsF(font_for(papel)).height()
            bloco = altura_total + 16
            y = interno.center().y() - bloco / 2
            self._texto(pintor, QRectF(interno.x(), y, interno.width(), altura_total),
                        self.total_texto, Qt.AlignmentFlag.AlignCenter, papel, "text")
            self._texto(pintor, QRectF(interno.x(), y + altura_total, interno.width(), 16),
                        self.titulo_centro, Qt.AlignmentFlag.AlignCenter, "caption")

        self._legenda(pintor, anel, total, deitado)

    def _legenda(self, pintor: QPainter, anel: QRectF, total: float,
                 deitado: bool) -> None:
        x = anel.right() + RECUO * 2.4 if deitado else RECUO
        largura = (self.width() - x - RECUO) if deitado else self.width() - RECUO * 2
        if largura < 80:
            return
        fonte_pct = font_for("strong")
        coluna_pct = QFontMetricsF(fonte_pct).horizontalAdvance("100%") + 4
        metrica = QFontMetricsF(font_for("caption"))
        coluna_valor = min(
            max((metrica.horizontalAdvance(f.escrito()) for f in self.fatias), default=40) + 8,
            largura * 0.42,
        )
        x_pct = x + largura - coluna_pct
        x_valor = x_pct - 10 - coluna_valor
        # sem espaco para o nome, sai o valor escrito e fica so a porcentagem
        com_valor = x_valor - (x + 18) >= 60
        fim_rotulo = x_valor - 6 if com_valor else x_pct - 8

        passo = 26
        altura = len(self.fatias) * passo
        y = (self.height() - altura) / 2 if deitado else anel.bottom() + RECUO

        for posicao, fatia in enumerate(self.fatias):
            linha = y + posicao * passo
            if linha + passo > self.height():
                return  # o que nao cabe nao entra pela metade
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(self.cor_da(fatia, posicao))
            pintor.drawRoundedRect(QRectF(x, linha + 8, 10, 10), 3, 3)

            self._texto(pintor, QRectF(x + 18, linha, max(0.0, fim_rotulo - x - 18), passo),
                        fatia.rotulo, papel="body", cor="text")
            if com_valor:
                self._texto(pintor, QRectF(x_valor, linha, coluna_valor, passo),
                            fatia.escrito(), Qt.AlignmentFlag.AlignRight, "caption")
            self._texto(pintor, QRectF(x_pct, linha, coluna_pct, passo),
                        f"{100 * abs(fatia.valor) / total:.0f}%",
                        Qt.AlignmentFlag.AlignRight, "strong", "text")


class GraficoColunas(GraficoBase):
    """Colunas em pe: para o tempo - o mes dia a dia, a semana hora a hora."""

    ALTURA_ROTULO = 18
    ALTURA_VALOR = 16

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, altura=140)

    def desenhar(self, pintor: QPainter) -> None:
        maior = max((abs(f.valor) for f in self.fatias), default=0.0) or 1.0
        # o valor fica acima da coluna: a altura sozinha diz "maior", nao "quanto"
        area = QRectF(RECUO, RECUO + self.ALTURA_VALOR,
                      self.width() - RECUO * 2,
                      self.height() - RECUO - self.ALTURA_ROTULO - self.ALTURA_VALOR)
        if area.width() <= 10 or area.height() <= 10:
            return

        pintor.setPen(QPen(QColor(self._palette.border_soft), 1))
        pintor.drawLine(QPointF(area.left(), area.bottom() + 0.5),
                        QPointF(area.right(), area.bottom() + 0.5))

        vao = area.width() / len(self.fatias)
        largura = min(34.0, max(6.0, vao * 0.56))
        raio = min(6.0, largura / 2)
        for posicao, fatia in enumerate(self.fatias):
            altura = area.height() * abs(fatia.valor) / maior * self.progresso
            x = area.x() + vao * posicao + (vao - largura) / 2
            barra = QRectF(x, area.bottom() - altura, largura, max(altura, 2.0))

            coluna = QPainterPath()
            coluna.addRoundedRect(barra, raio, raio)
            # so o topo e redondo: o pe da coluna encosta reto na linha de base
            coluna.addRect(QRectF(barra.x(), barra.bottom() - min(raio, barra.height() / 2),
                                  barra.width(), min(raio, barra.height() / 2)))
            pintor.fillPath(coluna.simplified(), self.cor_da(fatia, posicao))

            self._texto(pintor,
                        QRectF(area.x() + vao * posicao,
                               barra.top() - self.ALTURA_VALOR, vao, self.ALTURA_VALOR),
                        fatia.escrito(), Qt.AlignmentFlag.AlignCenter, "caption", "text")
            self._texto(pintor,
                        QRectF(area.x() + vao * posicao, area.bottom() + 2,
                               vao, self.ALTURA_ROTULO),
                        fatia.rotulo, Qt.AlignmentFlag.AlignCenter)


class GraficoLinha(GraficoBase):
    """Linha com area: para a forma de uma serie - onde ela sobe e onde afunda.

    Reserva espaco para os rotulos dos dois eixos **antes** de calcular a area
    do desenho, e e por isso que o rotulo do ponto marcado nao sai cortado no
    pe do cartao. A curva e suave, mas nunca passa do ponto: entre dois dias
    ela fica sempre entre os dois valores, sem inventar pico que nao houve.
    """

    ALTURA_EIXO = 18
    LARGURA_EIXO = 62

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, altura=170)
        self.valores: list[float] = []
        self.rotulos: list[str] = []
        self.marca: int | None = None
        self.marca_texto = ""
        self.formatar = lambda valor: f"{valor:,.0f}".replace(",", ".")

    def set_serie(self, valores, rotulos=None, marca=None, marca_texto="") -> None:
        valores = list(valores)
        mudou = valores != self.valores
        self.valores = valores
        self.rotulos = list(rotulos or [])
        self.marca = marca
        self.marca_texto = marca_texto
        self.fatias = [Fatia("", v) for v in self.valores]  # so para nao ficar vazio
        if mudou:
            self._progresso.reiniciar()
        else:
            self.update()

    def desenhar(self, pintor: QPainter) -> None:
        if len(self.valores) < 2:
            self._dizer_vazio(pintor)
            return

        # a area sai depois de reservar os eixos - nunca antes. E a largura do
        # eixo vem da medida do texto, senao "R$ 6.910,00" vira "R$ 6.910,..."
        eixo = self._largura_do_eixo()
        area = QRectF(
            eixo, RECUO,
            self.width() - eixo - RECUO,
            self.height() - RECUO - self.ALTURA_EIXO * 2,
        )
        if area.width() <= 20 or area.height() <= 20:
            return

        teto = max(max(self.valores), 0.0)
        piso = min(min(self.valores), 0.0)
        faixa = (teto - piso) or 1.0

        def ponto(indice: int, valor: float) -> QPointF:
            x = area.x() + area.width() * indice / (len(self.valores) - 1)
            y = area.y() + area.height() * (teto - valor) / faixa
            return QPointF(x, y)

        self._eixo_vertical(pintor, area, teto, piso, faixa)
        self._eixo_horizontal(pintor, area)
        # a serie se desenha da esquerda para a direita quando o dado muda
        pintor.save()
        pintor.setClipRect(QRectF(0, 0, area.x() + area.width() * self.progresso + 4,
                                  self.height()))
        self._area(pintor, area, ponto, teto, faixa)
        self._curva(pintor, ponto)
        pintor.restore()
        if self.progresso >= 0.999:
            self._marcar(pintor, area, ponto)

    # ------------------------------------------------------------------ eixos
    def _marcas(self) -> list[float]:
        """Tres marcas: o teto, o zero e o piso. Mais que isso vira grade suja."""
        teto = max(max(self.valores), 0.0)
        piso = min(min(self.valores), 0.0)
        marcas = {teto, piso}
        if piso < 0 < teto:
            marcas.add(0.0)
        return sorted(marcas)

    def _largura_do_eixo(self) -> float:
        metrica = QFontMetrics(font_for("caption"))
        maior = max(
            (metrica.horizontalAdvance(self.formatar(valor)) for valor in self._marcas()),
            default=0,
        )
        return min(maior + ESPACO_ROTULO * 2, self.width() * 0.35)

    def _eixo_vertical(self, pintor: QPainter, area: QRectF, teto: float,
                       piso: float, faixa: float) -> None:
        for valor in self._marcas():
            y = area.y() + area.height() * (teto - valor) / faixa
            zero = abs(valor) < 0.005
            caneta = QPen(QColor(self._palette.border_strong if zero
                                 else self._palette.border_soft), 1)
            caneta.setStyle(Qt.PenStyle.DashLine)
            pintor.setPen(caneta)
            pintor.drawLine(QPointF(area.x(), y), QPointF(area.right(), y))
            self._texto(pintor,
                        QRectF(0, y - 8, area.x() - ESPACO_ROTULO, 16),
                        self.formatar(valor), Qt.AlignmentFlag.AlignRight)

    def _eixo_horizontal(self, pintor: QPainter, area: QRectF) -> None:
        if not self.rotulos:
            return
        primeiro, ultimo = self.rotulos[0], self.rotulos[-1]
        y = area.bottom() + 2
        self._texto(pintor, QRectF(area.x(), y, area.width() / 2, self.ALTURA_EIXO),
                    primeiro)
        self._texto(pintor,
                    QRectF(area.center().x(), y, area.width() / 2, self.ALTURA_EIXO),
                    ultimo, Qt.AlignmentFlag.AlignRight)

    # ---------------------------------------------------------------- desenho
    def _caminho(self, ponto, valores) -> QPainterPath:
        """Curva suave que nunca passa do ponto (controles na metade do vao)."""
        anterior = ponto(0, valores[0])
        caminho = QPainterPath(anterior)
        for indice, valor in enumerate(valores[1:], start=1):
            atual = ponto(indice, valor)
            meio = (anterior.x() + atual.x()) / 2
            caminho.cubicTo(QPointF(meio, anterior.y()), QPointF(meio, atual.y()), atual)
            anterior = atual
        return caminho

    def _area(self, pintor: QPainter, area: QRectF, ponto, teto: float,
              faixa: float) -> None:
        y_zero = area.y() + area.height() * teto / faixa
        y_zero = min(max(y_zero, area.y()), area.bottom())
        for tom, acima in (("success", True), ("danger", False)):
            limitados = [max(v, 0.0) if acima else min(v, 0.0) for v in self.valores]
            if not any(limitados):
                continue
            caminho = self._caminho(ponto, limitados)
            caminho.lineTo(QPointF(ponto(len(self.valores) - 1, 0).x(), y_zero))
            caminho.lineTo(QPointF(ponto(0, 0).x(), y_zero))
            caminho.closeSubpath()
            cor = QColor(self._palette.resolve(tom))
            forte, fraca = QColor(cor), QColor(cor)
            forte.setAlpha(70 if self._palette.is_dark else 52)
            fraca.setAlpha(0)
            degrade = QLinearGradient(0, area.y() if acima else area.bottom(), 0, y_zero)
            degrade.setColorAt(0.0, forte)
            degrade.setColorAt(1.0, fraca)
            pintor.fillPath(caminho, degrade)

    def _curva(self, pintor: QPainter, ponto) -> None:
        caminho = self._caminho(ponto, self.valores)
        cor = (self._palette.danger if min(self.valores) < 0
               else self._palette.accent)
        caneta = QPen(QColor(cor), 2.4)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawPath(caminho)

    def _marcar(self, pintor: QPainter, area: QRectF, ponto) -> None:
        if self.marca is None or not 0 <= self.marca < len(self.valores):
            return
        centro = ponto(self.marca, self.valores[self.marca])

        pintor.setPen(QPen(QColor(self._palette.danger), 2.4))
        pintor.setBrush(QColor(self._palette.surface))
        pintor.drawEllipse(centro, 4.5, 4.5)
        if not self.marca_texto:
            return

        metrica = QFontMetrics(font_for("caption"))
        largura = metrica.horizontalAdvance(self.marca_texto) + 16
        x = min(max(centro.x() - largura / 2, area.x()), area.right() - largura)
        # abaixo do ponto quando ha espaco; acima quando nao ha - nunca fora
        abaixo = centro.y() + 10 + 20 <= area.bottom() + self.ALTURA_EIXO
        y = centro.y() + 10 if abaixo else centro.y() - 30
        etiqueta = QPainterPath()
        etiqueta.addRoundedRect(QRectF(x, y, largura, 20), 10, 10)
        pintor.fillPath(etiqueta, QColor(self._palette.danger_soft))
        self._texto(pintor, QRectF(x, y, largura, 20), self.marca_texto,
                    Qt.AlignmentFlag.AlignCenter, "caption", "danger")


def fatias_de(pares, tons=()) -> list[Fatia]:
    """Atalho para transformar [(rotulo, valor, texto)] em fatias."""
    saida = []
    for posicao, par in enumerate(pares):
        rotulo, valor = par[0], par[1]
        texto = par[2] if len(par) > 2 else ""
        tom = tons[posicao] if posicao < len(tons) else ""
        saida.append(Fatia(rotulo, float(valor), tom, texto))
    return saida


def maiores(pares, limite: int = 5) -> list:
    """Os maiores primeiro, com o resto somado em 'Outros'.

    Uma lista de vinte categorias vira um grafico ilegivel; cinco e o resto
    somado diz a mesma coisa e cabe na tela.
    """
    ordenados = sorted(pares, key=lambda p: abs(float(p[1])), reverse=True)
    if len(ordenados) <= limite:
        return ordenados
    resto = sum(abs(float(p[1])) for p in ordenados[limite:])
    return ordenados[:limite] + [("Outros", resto)]
