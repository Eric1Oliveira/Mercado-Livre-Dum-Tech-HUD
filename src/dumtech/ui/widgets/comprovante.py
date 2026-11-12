"""Comprovante na tela, do mesmo jeito que sai no papel.

O texto vem em 40 colunas (`ui/recibo.py`) e e mostrado em fonte monoespacada:
o que aparece aqui e exatamente o que a impressora recebe. Usado pelo Vendas
(venda, fechamento de caixa) e pela Ordem de Servico (entrada, entrega).

NA IMPRESSORA

`imprimir_bobina` e o unico caminho do texto ate o papel. O antigo
(`QPlainTextEdit.print_`) tratava a bobina como folha A4: 2 cm de margem de
cada lado e a fonte da tela. Na bobina de 58 mm sobravam uns 28 mm para
escrever - saiam 14 das 40 colunas, e os valores, que ficam na direita,
sumiam do papel.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..recibo import LARGURA
from ..theme import Space, apply_window_theme, palette_for
from .buttons import Button
from .common import label, repolish, separator

#: traco grosso imprime melhor na termica; a Courier do sistema sai apagada
FONTES_BOBINA = ("Consolas", "Lucida Console", "Courier New")

#: menor que isto a letra some na bobina de 58 mm: ali o texto estreita em vez
#: de encolher (como a fonte pequena das proprias impressoras termicas)
MENOR_FONTE = 7.0

#: numa folha A4 o comprovante continua do tamanho de comprovante
MAIOR_FONTE = 10.0

#: folga para arredondamento: a ultima coluna nunca encosta na borda
FOLGA = 0.98


def fonte_bobina(tamanho: float = MAIOR_FONTE) -> QFont:
    """Monoespacada, em negrito: e o que a cabeca termica desenha melhor."""
    familias = set(QFontDatabase.families())
    nome = next((familia for familia in FONTES_BOBINA if familia in familias), "")
    fonte = QFont(nome) if nome else QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    fonte.setStyleHint(QFont.StyleHint.TypeWriter)
    fonte.setFixedPitch(True)
    fonte.setBold(True)
    fonte.setPointSizeF(tamanho)
    return fonte


def medida_da_bobina(largura: float, dispositivo) -> tuple[QFont, float]:
    """A fonte e o estreitamento para as 40 colunas caberem em `largura` pixels.

    Devolve (fonte, escala horizontal). A escala so fica abaixo de 1 quando
    a fonte ja chegou ao menor tamanho legivel - a bobina de 58 mm.
    """
    util = largura * FOLGA
    fonte = fonte_bobina(MAIOR_FONTE)
    cheia = QFontMetricsF(fonte, dispositivo).horizontalAdvance("0" * LARGURA)
    tamanho = MAIOR_FONTE if cheia <= util else max(MAIOR_FONTE * util / cheia, MENOR_FONTE)
    fonte.setPointSizeF(tamanho)
    # hinting arredonda a largura de cada letra: confere com a fonte de verdade
    medida = QFontMetricsF(fonte, dispositivo).horizontalAdvance("0" * LARGURA)
    return fonte, min(1.0, util / medida) if medida > 0 else 1.0


def imprimir_bobina(texto: str, impressora) -> None:
    """Imprime o texto de bobina ocupando a largura util do papel.

    Margem so a que a impressora exige (a parte do papel onde a cabeca nao
    alcanca) e a letra calculada para as 40 colunas caberem no que sobra: o
    mesmo comprovante sai inteiro na bobina de 58 mm, na de 80 mm e na folha
    A4. Texto mais comprido que a pagina continua na seguinte.
    """
    from PySide6.QtPrintSupport import QPrinter

    pagina = impressora.pageLayout()
    impressora.setPageMargins(pagina.minimumMargins(), pagina.units())

    pintor = QPainter()
    if not pintor.begin(impressora):
        raise OSError("A impressora não aceitou o comprovante.")
    try:
        area = impressora.pageRect(QPrinter.Unit.DevicePixel)
        desenhar_bobina(pintor, texto, area.width(), area.height(), impressora,
                        impressora.newPage)
    finally:
        pintor.end()


def desenhar_bobina(pintor: QPainter, texto: str, largura: float, altura: float,
                    dispositivo, nova_pagina=None) -> int:
    """Pinta o texto a partir do canto do papel. Devolve quantas paginas usou.

    Separado da impressora para ser conferido numa imagem do tamanho da
    bobina: e ali que se ve se a ultima coluna chegou ao papel.
    """
    fonte, escala = medida_da_bobina(largura, dispositivo)
    pintor.setFont(fonte)
    metricas = QFontMetricsF(fonte, dispositivo)
    passo = metricas.lineSpacing()
    # sem como virar a pagina (uma imagem), o texto so continua para baixo
    por_pagina = max(1, int(altura // passo)) if nova_pagina is not None else 0
    paginas = 1
    for indice, linha in enumerate(texto.split("\n")):
        if por_pagina and indice and indice % por_pagina == 0:
            nova_pagina()
            paginas += 1
        posicao = indice % por_pagina if por_pagina else indice
        pintor.save()
        pintor.scale(escala, 1.0)
        pintor.drawText(QPointF(0.0, posicao * passo + metricas.ascent()), linha)
        pintor.restore()
    return paginas


class ComprovanteDialog(QDialog):
    """Mostra, copia e imprime um comprovante."""

    def __init__(
        self,
        texto: str,
        titulo: str = "Comprovante",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.texto = texto

        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumSize(460, 560)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)

        cabecalho = QVBoxLayout()
        cabecalho.setSpacing(2)
        cabecalho.addWidget(label(titulo, "section"))
        cabecalho.addWidget(label("Confira antes de imprimir", "muted"))
        raiz.addLayout(cabecalho)
        raiz.addWidget(separator())

        self.papel = QPlainTextEdit(texto)
        self.papel.setReadOnly(True)
        self.papel.setFont(self._fonte())
        self.papel.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        raiz.addWidget(self.papel, 1)

        self.aviso = label("", "muted")
        raiz.addWidget(self.aviso)
        raiz.addLayout(self._botoes())

        apply_window_theme(self, palette_for(parent))

    @staticmethod
    def _fonte() -> QFont:
        """Monoespacada de verdade: com fonte proporcional o papel desalinha."""
        fonte = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fonte.setPointSizeF(10.0)
        return fonte

    def _botoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.addStretch(1)

        copiar = Button("Copiar", "file")
        copiar.clicked.connect(self._copiar)
        linha.addWidget(copiar)

        imprimir = Button("Imprimir", "check", "primary")
        imprimir.clicked.connect(self._imprimir)
        linha.addWidget(imprimir)

        fechar = Button("Fechar")
        fechar.clicked.connect(self.accept)
        linha.addWidget(fechar)
        return linha

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    def _copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.texto)
        self._dizer("Comprovante copiado.", "success")

    def _imprimir(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        impressora = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialogo = QPrintDialog(impressora, self)
        dialogo.setWindowTitle("Imprimir comprovante")
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            imprimir_bobina(self.texto, impressora)
        except OSError as erro:
            self._dizer(str(erro), "danger")
            return
        self._dizer("Enviado para a impressora.", "success")
