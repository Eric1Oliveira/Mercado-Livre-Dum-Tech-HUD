"""Comprovante na impressora termica: as 40 colunas inteiras no papel.

O caso real (11/2026): o fechamento de caixa saiu numa bobina de 58 mm com so
as 14 primeiras colunas. O Qt pintava a bobina como folha A4 - 2 cm de margem
de cada lado e a fonte da tela - e os valores, que ficam na direita, sumiram.

A conferencia e feita numa imagem do tamanho da area util da bobina, na
resolucao das termicas (203 dpi): e la que se ve onde a tinta comeca e acaba.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication, QDialog

from dumtech.apps.vendas.models import Caixa, ConferenciaCaixa
from dumtech.apps.vendas.recibo import fechamento
from dumtech.ui.recibo import lado_a_lado, linha
from dumtech.ui.widgets import comprovante
from dumtech.ui.widgets.comprovante import (
    MENOR_FONTE,
    ComprovanteDialog,
    desenhar_bobina,
    imprimir_bobina,
    medida_da_bobina,
)

_app: QApplication | None = None

DPI_TERMICA = 203

#: a linha que mais sofria: o valor encostado na coluna 40
TEXTO = "\n".join([linha("="), lado_a_lado("Dinheiro recebido", "R$ 1.234,56"), linha("=")])

#: onde a tinta precisa chegar. Antes do conserto parava em ~35% (14 de 40
#: colunas). Com a Consolas de verdade chega a 97%; a bateria roda sem fonte
#: nenhuma instalada (QT_QPA_PLATFORM=offscreen), e a letra de reserva tem
#: mais respiro nas bordas - dai a folga.
ALCANCE = 0.85


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def bobina(largura_mm: float, altura: int = 120) -> QImage:
    """Uma tira em branco do tamanho da area util, na resolucao da termica."""
    imagem = QImage(round(largura_mm / 25.4 * DPI_TERMICA), altura, QImage.Format.Format_RGB32)
    imagem.fill(QColor("white"))
    pontos = round(DPI_TERMICA / 0.0254)
    imagem.setDotsPerMeterX(pontos)
    imagem.setDotsPerMeterY(pontos)
    return imagem


def pintar(imagem: QImage, texto: str = TEXTO) -> None:
    pintor = QPainter(imagem)
    try:
        desenhar_bobina(pintor, texto, imagem.width(), imagem.height(), imagem)
    finally:
        pintor.end()


def tinta(imagem: QImage) -> tuple[int, int]:
    """(primeira, ultima) coluna de pixels com tinta."""
    colunas = [x for x in range(imagem.width())
               if any(imagem.pixelColor(x, y).lightness() < 128 for y in range(imagem.height()))]
    return (colunas[0], colunas[-1]) if colunas else (-1, -1)


class LarguraDoPapelTestCase(unittest.TestCase):
    def test_bobina_de_58mm_mostra_as_40_colunas(self) -> None:
        imagem = bobina(48)  # 58 mm de papel, 48 mm onde a cabeca alcanca
        pintar(imagem)
        primeira, ultima = tinta(imagem)

        self.assertLessEqual(primeira, imagem.width() * 0.03, "comeca no canto, sem margem de A4")
        self.assertGreater(ultima, imagem.width() * ALCANCE, "o valor da coluna 40 chegou ao papel")
        self.assertLess(ultima, imagem.width() - 1, "e nao foi cortado na borda")

    def test_bobina_de_80mm_tambem(self) -> None:
        imagem = bobina(72)
        pintar(imagem)
        primeira, ultima = tinta(imagem)
        self.assertLessEqual(primeira, imagem.width() * 0.03)
        self.assertGreater(ultima, imagem.width() * ALCANCE)
        self.assertLess(ultima, imagem.width() - 1)

    def test_na_58mm_a_letra_estreita_mas_nao_some(self) -> None:
        imagem = bobina(48)
        fonte, escala = medida_da_bobina(imagem.width(), imagem)
        self.assertGreaterEqual(fonte.pointSizeF(), MENOR_FONTE)
        self.assertLess(escala, 1.0)
        self.assertGreater(escala, 0.6, "estreitar demais tambem nao se le")

    def test_na_80mm_a_letra_nao_precisa_estreitar(self) -> None:
        imagem = bobina(72)
        fonte, escala = medida_da_bobina(imagem.width(), imagem)
        self.assertEqual(escala, 1.0)
        self.assertGreater(fonte.pointSizeF(), MENOR_FONTE)

    def test_numa_folha_a4_continua_do_tamanho_de_comprovante(self) -> None:
        imagem = bobina(190)
        pintar(imagem)
        _primeira, ultima = tinta(imagem)
        self.assertLess(ultima, imagem.width() * 0.6, "nao vira cartaz na folha inteira")

    def test_numa_imagem_o_texto_comprido_desce_e_nao_se_sobrepoe(self) -> None:
        """Sem como virar a pagina, a linha 30 nao pode ir para cima da 1."""
        imagem = bobina(48, altura=60)
        texto = "\n".join(["=" * 40] + ["" for _ in range(30)])
        pintor = QPainter(imagem)
        try:
            paginas = desenhar_bobina(pintor, texto + "\nX", imagem.width(), 60, imagem)
        finally:
            pintor.end()
        self.assertEqual(paginas, 1)
        # o X da ultima linha caiu muito abaixo da imagem: so a linha 1 aparece
        linhas_com_tinta = [y for y in range(imagem.height())
                            if any(imagem.pixelColor(x, y).lightness() < 128
                                   for x in range(0, imagem.width(), 3))]
        self.assertLess(max(linhas_com_tinta), 40)


class ImpressoraTestCase(unittest.TestCase):
    def _impressora(self, pasta: Path) -> QPrinter:
        impressora = QPrinter(QPrinter.PrinterMode.HighResolution)
        impressora.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        impressora.setOutputFileName(str(pasta / "bobina.pdf"))
        cinco = QMarginsF(5, 0, 5, 0)
        impressora.setPageLayout(QPageLayout(
            QPageSize(QSizeF(58, 120), QPageSize.Unit.Millimeter, "Bobina 58"),
            QPageLayout.Orientation.Portrait, cinco, QPageLayout.Unit.Millimeter, cinco,
        ))
        return impressora

    def test_margem_e_so_a_que_a_impressora_exige(self) -> None:
        pasta = Path(tempfile.mkdtemp())
        impressora = self._impressora(pasta)
        impressora.setPageMargins(QMarginsF(20, 20, 20, 20), QPageLayout.Unit.Millimeter)

        imprimir_bobina(TEXTO, impressora)

        margens = impressora.pageLayout().margins(QPageLayout.Unit.Millimeter)
        self.assertAlmostEqual(margens.left(), 5, places=1)
        self.assertAlmostEqual(margens.right(), 5, places=1)
        self.assertGreater((pasta / "bobina.pdf").stat().st_size, 0)

    def test_comprovante_comprido_continua_na_pagina_seguinte(self) -> None:
        pasta = Path(tempfile.mkdtemp())
        texto = "\n".join(lado_a_lado(f"Item {n}", "R$ 1,00") for n in range(300))

        imprimir_bobina(texto, self._impressora(pasta))

        paginas = re.findall(rb"/Type\s*/Page[^s]", (pasta / "bobina.pdf").read_bytes())
        self.assertGreater(len(paginas), 1)

    def test_o_botao_imprimir_usa_a_bobina_e_nao_a_folha(self) -> None:
        dialogo = ComprovanteDialog(TEXTO)
        self.addCleanup(dialogo.deleteLater)
        with mock.patch("PySide6.QtPrintSupport.QPrintDialog") as escolha, \
                mock.patch.object(comprovante, "imprimir_bobina") as imprimir:
            escolha.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialogo._imprimir()
        imprimir.assert_called_once()
        self.assertEqual(imprimir.call_args.args[0], TEXTO)
        self.assertIn("Enviado", dialogo.aviso.text())


class FechamentoTestCase(unittest.TestCase):
    def test_recebimento_de_conta_aparece_no_papel(self) -> None:
        """Entrava no ESPERADO sem aparecer: a conta do papel nao fechava."""
        conferencia = ConferenciaCaixa(caixa=Caixa(id=1, aberto_em="2026-11-11T08:00:00"),
                                       abertura=50.0, recebimentos=100.0)
        texto = fechamento(conferencia)
        self.assertIn("Recebimentos", texto)
        self.assertIn("R$ 150,00", texto)


if __name__ == "__main__":
    unittest.main()
