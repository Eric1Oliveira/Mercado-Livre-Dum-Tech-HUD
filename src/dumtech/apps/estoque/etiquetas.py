"""Etiquetas com codigo de barras: os formatos, o desenho e a impressao.

O MESMO DESENHO EM TODO LUGAR
    `desenhar_pagina` recebe um QPainter e quantos pixels vale um milimetro. A
    previa na tela, a impressora e o PDF chamam a mesma funcao - o que se ve e o
    que sai.

BARRA NITIDA
    O leitor erra quando as barras saem com larguras desiguais. Por isso a
    largura do modulo e arredondada para um numero INTEIRO de pontos da
    impressora (8 pontos/mm numa termica de 203 dpi): todas as barras finas
    saem iguais, e o codigo fica um pouco menor em vez de borrado.

FOLHA A4 E ROLO
    Folha adesiva (Pimaco) imprime em qualquer impressora comum; a grade fica
    centralizada na folha, como as folhas sao cortadas. Impressora de etiqueta
    (Elgin, Argox, Zebra) recebe uma pagina do tamanho de UMA etiqueta - e o
    driver dela que avanca o rolo.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPageLayout, QPageSize, QPainter, QPen

from ...ui import format as fmt
from . import codigo_barras

#: folha A4 em milimetros
A4 = (210.0, 297.0)

#: zona em branco obrigatoria antes e depois das barras (em modulos)
SILENCIO = {13: (11, 7), 8: (7, 7)}
#: onde ficam as barras de guarda (descem mais que as outras)
GUARDAS = {
    13: ((0, 3), (45, 50), (92, 95)),
    8: ((0, 3), (31, 36), (64, 67)),
}

PRETO = QColor("#000000")
CINZA = QColor("#C9CCD3")


@dataclass(frozen=True)
class Formato:
    """Um tamanho de etiqueta e como ela vem no papel (medidas em mm)."""

    chave: str
    nome: str
    largura: float
    altura: float
    colunas: int = 1
    linhas: int = 1
    #: espaco entre uma etiqueta e a do lado / a de baixo
    folga_x: float = 0.0
    folga_y: float = 0.0
    #: True = folha A4 com varias etiquetas; False = rolo, uma por pagina
    folha: bool = False

    @property
    def por_pagina(self) -> int:
        return self.colunas * self.linhas

    @property
    def pagina(self) -> tuple[float, float]:
        return A4 if self.folha else (self.largura, self.altura)

    def posicoes(self) -> list[QRectF]:
        """Retangulo (em mm) de cada etiqueta, linha por linha, a grade centralizada."""
        largura_total = self.colunas * self.largura + (self.colunas - 1) * self.folga_x
        altura_total = self.linhas * self.altura + (self.linhas - 1) * self.folga_y
        esquerda = (self.pagina[0] - largura_total) / 2
        topo = (self.pagina[1] - altura_total) / 2
        return [
            QRectF(
                esquerda + coluna * (self.largura + self.folga_x),
                topo + linha * (self.altura + self.folga_y),
                self.largura,
                self.altura,
            )
            for linha in range(self.linhas)
            for coluna in range(self.colunas)
        ]


FORMATOS: tuple[Formato, ...] = (
    Formato("a4-21", "Folha A4 · 21 etiquetas de 63,5 × 38,1 mm (Pimaco A4260)",
            63.5, 38.1, 3, 7, 2.5, 0.0, True),
    Formato("a4-33", "Folha A4 · 33 etiquetas de 63,5 × 25,4 mm (Pimaco A4256)",
            63.5, 25.4, 3, 11, 2.5, 0.0, True),
    Formato("a4-65", "Folha A4 · 65 etiquetas de 38,1 × 21,2 mm (Pimaco A4251)",
            38.1, 21.2, 5, 13, 2.5, 0.0, True),
    Formato("rolo-40x25", "Impressora de etiqueta · 40 × 25 mm", 40.0, 25.0),
    Formato("rolo-50x30", "Impressora de etiqueta · 50 × 30 mm", 50.0, 30.0),
    Formato("rolo-60x40", "Impressora de etiqueta · 60 × 40 mm", 60.0, 40.0),
)
POR_CHAVE = {formato.chave: formato for formato in FORMATOS}
PADRAO = FORMATOS[0]


@dataclass(frozen=True)
class Etiqueta:
    """O que vai escrito numa etiqueta."""

    nome: str
    barras: str
    preco: float = 0.0


def paginas(etiquetas: list[Etiqueta], formato: Formato, inicio: int = 1) -> list[list[Etiqueta | None]]:
    """Distribui as etiquetas pelas paginas.

    `inicio` e a primeira etiqueta livre da folha (1 = a do canto): folha A4
    usada pela metade volta para a impressora sem desperdicar o resto. None e
    uma posicao que fica em branco.
    """
    pulo = max(0, min(inicio, formato.por_pagina) - 1) if formato.folha else 0
    fila: list[Etiqueta | None] = [None] * pulo + list(etiquetas)
    tamanho = formato.por_pagina
    return [fila[i:i + tamanho] for i in range(0, len(fila), tamanho)] if etiquetas else []


# --------------------------------------------------------------------- desenho
def _fonte(altura_px: float, negrito: bool = False) -> QFont:
    fonte = QFont("Segoe UI")
    fonte.setPixelSize(max(1, round(altura_px)))
    fonte.setBold(negrito)
    return fonte


def desenhar_barras(pintor: QPainter, area: QRectF, codigo: str) -> bool:
    """Barras e numeros dentro de `area` (em pixels). False se nao for EAN."""
    try:
        padrao = codigo_barras.modulos(codigo)
    except ValueError:
        return False
    numero = codigo_barras.normalizar(codigo)
    tipo = 13 if len(numero) == 13 else 8
    silencio_esq, silencio_dir = SILENCIO[tipo]
    total = silencio_esq + len(padrao) + silencio_dir

    # modulo em pixels INTEIROS: barras iguais, leitura firme
    modulo = max(1, floor(area.width() / total))
    largura = modulo * total
    x0 = round(area.left() + (area.width() - largura) / 2) + silencio_esq * modulo

    texto = max(1.0, min(area.height() * 0.24, modulo * 9))
    topo = area.top()
    fim_barra = area.bottom() - texto * 0.75
    fim_guarda = area.bottom() - texto * 0.35
    guardas = GUARDAS[tipo]

    pintor.save()
    pintor.setPen(Qt.PenStyle.NoPen)
    inicio = None
    for i, bit in enumerate(padrao + "0"):
        if bit == "1" and inicio is None:
            inicio = i
        elif bit == "0" and inicio is not None:
            guarda = any(a <= inicio < b for a, b in guardas)
            fundo = fim_guarda if guarda else fim_barra
            pintor.fillRect(QRectF(x0 + inicio * modulo, topo, (i - inicio) * modulo,
                                   fundo - topo), PRETO)
            inicio = None

    # os numeros embaixo, no lugar da norma: o primeiro do EAN-13 fica de fora
    pintor.setPen(PRETO)
    pintor.setFont(_fonte(texto))
    linha_texto = QRectF(0, fim_barra, 0, area.bottom() - fim_barra + texto * 0.3)

    def escrever(texto_grupo: str, de: int, ate: int) -> None:
        caixa = QRectF(x0 + de * modulo, linha_texto.top(), (ate - de) * modulo,
                       linha_texto.height())
        pintor.drawText(caixa, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                        texto_grupo)

    if tipo == 13:
        escrever(numero[0], -silencio_esq, -1)
        escrever(numero[1:7], 3, 45)
        escrever(numero[7:], 50, 92)
    else:
        escrever(numero[:4], 3, 31)
        escrever(numero[4:], 36, 64)
    pintor.restore()
    return True


def desenhar_etiqueta(pintor: QPainter, caixa: QRectF, etiqueta: Etiqueta,
                      px_mm: float, mostrar_preco: bool = True) -> None:
    """Nome em cima, preco embaixo dele e as barras ocupando o resto."""
    margem = min(1.6, caixa.height() * 0.07) * px_mm
    util = caixa.adjusted(margem, margem, -margem, -margem)
    altura_mm = caixa.height() / px_mm

    pintor.save()
    pintor.setPen(PRETO)
    y = util.top()

    nome_px = min(3.0, altura_mm * 0.12) * px_mm
    fonte_nome = _fonte(nome_px, negrito=True)
    pintor.setFont(fonte_nome)
    medida = QFontMetrics(fonte_nome)
    nome = medida.elidedText(etiqueta.nome, Qt.TextElideMode.ElideRight, int(util.width()))
    pintor.drawText(QRectF(util.left(), y, util.width(), medida.height()),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, nome)
    y += medida.height()

    if mostrar_preco and etiqueta.preco > 0:
        preco_px = min(4.4, altura_mm * 0.16) * px_mm
        fonte_preco = _fonte(preco_px, negrito=True)
        pintor.setFont(fonte_preco)
        altura_preco = QFontMetrics(fonte_preco).height()
        pintor.drawText(QRectF(util.left(), y, util.width(), altura_preco),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                        fmt.moeda(etiqueta.preco))
        y += altura_preco

    y += 0.6 * px_mm
    area = QRectF(util.left(), y, util.width(), util.bottom() - y)
    if area.height() > 2 * px_mm and not desenhar_barras(pintor, area, etiqueta.barras):
        # codigo que nao e EAN (de fornecedor, alfanumerico): sai o numero, legivel
        pintor.setFont(_fonte(min(3.0, area.height() / px_mm * 0.4) * px_mm))
        pintor.drawText(area, Qt.AlignmentFlag.AlignCenter, etiqueta.barras or "sem código")
    pintor.restore()


def desenhar_pagina(pintor: QPainter, formato: Formato, itens: list[Etiqueta | None],
                    px_mm: float, mostrar_preco: bool = True, contorno: bool = False) -> None:
    """Uma pagina inteira; `contorno` mostra o recorte das etiquetas (so na previa)."""
    for posicao, item in zip(formato.posicoes(), itens + [None] * formato.por_pagina):
        caixa = QRectF(posicao.left() * px_mm, posicao.top() * px_mm,
                       posicao.width() * px_mm, posicao.height() * px_mm)
        if contorno:
            pintor.save()
            caneta = QPen(CINZA, 1, Qt.PenStyle.DashLine)
            pintor.setPen(caneta)
            pintor.setBrush(Qt.BrushStyle.NoBrush)
            pintor.drawRoundedRect(caixa.adjusted(0.5, 0.5, -0.5, -0.5), 2 * px_mm, 2 * px_mm)
            pintor.restore()
        if item is not None:
            desenhar_etiqueta(pintor, caixa, item, px_mm, mostrar_preco)


def previa(formato: Formato, itens: list[Etiqueta | None], px_mm: float,
           mostrar_preco: bool = True) -> QImage:
    """A primeira pagina como imagem, para a tela."""
    largura, altura = formato.pagina
    imagem = QImage(round(largura * px_mm), round(altura * px_mm), QImage.Format.Format_RGB32)
    imagem.fill(QColor("#FFFFFF"))
    pintor = QPainter(imagem)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pintor.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    desenhar_pagina(pintor, formato, itens, px_mm, mostrar_preco, contorno=True)
    pintor.end()
    return imagem


# ------------------------------------------------------------------- impressao
def preparar(impressora, formato: Formato) -> None:
    """Papel do tamanho certo e sem margem: quem posiciona e a grade."""
    largura, altura = formato.pagina
    if largura > altura:
        # o Qt guarda papel sempre em pe; etiqueta deitada vira paisagem
        tamanho = QPageSize(QSizeF(altura, largura), QPageSize.Unit.Millimeter,
                            formato.chave, QPageSize.SizeMatchPolicy.ExactMatch)
        orientacao = QPageLayout.Orientation.Landscape
    else:
        tamanho = (QPageSize(QPageSize.PageSizeId.A4) if formato.folha else
                   QPageSize(QSizeF(largura, altura), QPageSize.Unit.Millimeter,
                             formato.chave, QPageSize.SizeMatchPolicy.ExactMatch))
        orientacao = QPageLayout.Orientation.Portrait
    impressora.setPageLayout(QPageLayout(tamanho, orientacao, QMarginsF(0, 0, 0, 0),
                                         QPageLayout.Unit.Millimeter))
    impressora.setFullPage(True)


def imprimir(impressora, formato: Formato, etiquetas: list[Etiqueta], inicio: int = 1,
             mostrar_preco: bool = True) -> int:
    """Manda as etiquetas para a impressora (ou PDF). Devolve quantas paginas."""
    grupos = paginas(etiquetas, formato, inicio)
    if not grupos:
        return 0
    px_mm = impressora.resolution() / 25.4
    pintor = QPainter()
    if not pintor.begin(impressora):
        raise OSError("A impressora não aceitou o trabalho.")
    try:
        for numero, grupo in enumerate(grupos):
            if numero:
                impressora.newPage()
            desenhar_pagina(pintor, formato, grupo, px_mm, mostrar_preco)
    finally:
        pintor.end()
    return len(grupos)
