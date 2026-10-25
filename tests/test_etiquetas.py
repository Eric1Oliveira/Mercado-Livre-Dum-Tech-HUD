"""Codigo de barras interno e etiquetas do Estoque.

As barras foram conferidas contra a biblioteca python-barcode (4.000 codigos
aleatorios, nenhuma diferenca) e lidas por um leitor de verdade (zxing) em
todos os formatos, a 203 e 300 dpi. Aqui fica o que protege isso de quebrar.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from dumtech.apps.estoque import codigo_barras as cb
from dumtech.apps.estoque import etiquetas as et
from dumtech.apps.estoque.database import open_database
from dumtech.apps.estoque.models import Produto
from dumtech.apps.estoque.repository import EstoqueRepository
from dumtech.core.config import MemoryPreferences

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def _repo() -> EstoqueRepository:
    db = open_database(Path(tempfile.mkdtemp()) / "estoque.db")
    return EstoqueRepository(db)


class CodigoBarrasTestCase(unittest.TestCase):
    def test_digito_verificador_da_norma(self) -> None:
        self.assertEqual(cb.digito_verificador("400638133393"), 1)
        self.assertEqual(cb.digito_verificador("9638507"), 4)
        self.assertTrue(cb.valido("4006381333931"))
        self.assertTrue(cb.valido("96385074"))
        self.assertFalse(cb.valido("4006381333932"))
        self.assertFalse(cb.valido("ABC123"))

    def test_upc_de_12_digitos_vira_ean_13(self) -> None:
        self.assertEqual(cb.normalizar("036000291452"), "0036000291452")
        self.assertTrue(cb.valido("036000291452"))

    def test_codigo_interno_comeca_com_2_e_e_valido(self) -> None:
        self.assertEqual(cb.interno(1), "2000000000015")
        self.assertTrue(cb.valido(cb.interno(987654)))
        self.assertEqual(cb.sequencia_interna(cb.interno(42)), 42)
        # codigo de fabrica nao e "nosso"
        self.assertIsNone(cb.sequencia_interna("7891000315507"))

    def test_barras_conferidas_com_a_referencia(self) -> None:
        self.assertEqual(
            cb.modulos("4006381333931"),
            "10100011010100111010111101111010001001011001101010100001010000101000010111010010000101100110101",
        )
        self.assertEqual(
            cb.modulos("96385074"),
            "1010001011010111101111010110111010101001110111001010001001011100101",
        )
        self.assertEqual(len(cb.modulos(cb.interno(7))), 95)

    def test_codigo_invalido_nao_vira_barra(self) -> None:
        with self.assertRaises(ValueError):
            cb.modulos("12345")


class CodigoInternoNoEstoqueTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _repo()
        self.addCleanup(self.repo.db.close)

    def _produto(self, codigo: str, barras: str = "", ativo: bool = True) -> Produto:
        produto = self.repo.criar(Produto(codigo=codigo, nome=f"Produto {codigo}",
                                          codigo_barras=barras, unidade="UN"))
        if not ativo:
            self.repo.inativar(produto.id)
        return produto

    def test_a_sequencia_continua_do_maior_e_ignora_o_de_fabrica(self) -> None:
        self.assertEqual(self.repo.proximo_codigo_barras(), cb.interno(1))
        self._produto("F1", "7891000315507")
        self._produto("I1", cb.interno(40))
        self.assertEqual(self.repo.proximo_codigo_barras(), cb.interno(41))

    def test_atribuir_nao_troca_o_codigo_que_ja_existe(self) -> None:
        com = self._produto("F1", "7891000315507")
        sem = self._produto("S1")
        self.assertEqual(self.repo.atribuir_codigo_barras(com.id), "7891000315507")
        gerado = self.repo.atribuir_codigo_barras(sem.id)
        self.assertEqual(self.repo.obter(sem.id).codigo_barras, gerado)
        # e o leitor acha o produto pelo codigo novo
        self.assertEqual(self.repo.buscar(gerado).id, sem.id)

    def test_gerar_os_que_faltam_da_codigos_diferentes_so_aos_ativos(self) -> None:
        a, b = self._produto("A"), self._produto("B")
        inativo = self._produto("C", ativo=False)
        self._produto("D", cb.interno(5))

        self.assertEqual(self.repo.gerar_codigos_que_faltam(), 2)
        codigos = {self.repo.obter(p.id).codigo_barras for p in (a, b)}
        self.assertEqual(codigos, {cb.interno(6), cb.interno(7)})
        self.assertEqual(self.repo.obter(inativo.id).codigo_barras, "")
        self.assertEqual(self.repo.gerar_codigos_que_faltam(), 0)


class PaginasTestCase(unittest.TestCase):
    def _lista(self, n: int) -> list[et.Etiqueta]:
        return [et.Etiqueta(f"Item {i}", cb.interno(i + 1), 9.9) for i in range(n)]

    def test_folha_usada_comeca_na_etiqueta_livre(self) -> None:
        a4 = et.POR_CHAVE["a4-21"]
        paginas = et.paginas(self._lista(25), a4, inicio=5)
        self.assertEqual(len(paginas), 2)
        self.assertEqual(paginas[0][:4], [None] * 4)
        self.assertEqual(paginas[0][4].nome, "Item 0")
        self.assertEqual(sum(1 for p in paginas for e in p if e is not None), 25)

    def test_rolo_e_uma_etiqueta_por_pagina_e_ignora_o_inicio(self) -> None:
        rolo = et.POR_CHAVE["rolo-40x25"]
        paginas = et.paginas(self._lista(3), rolo, inicio=7)
        self.assertEqual([len(p) for p in paginas], [1, 1, 1])
        self.assertEqual(et.paginas([], rolo), [])

    def test_as_grades_cabem_na_folha_a4(self) -> None:
        for formato in et.FORMATOS:
            if not formato.folha:
                continue
            with self.subTest(formato.chave):
                posicoes = formato.posicoes()
                self.assertEqual(len(posicoes), formato.por_pagina)
                self.assertGreaterEqual(min(p.left() for p in posicoes), 3.0)
                self.assertGreaterEqual(min(p.top() for p in posicoes), 3.0)
                self.assertLessEqual(max(p.right() for p in posicoes), 207.0)
                self.assertLessEqual(max(p.bottom() for p in posicoes), 294.0)


class DesenhoTestCase(unittest.TestCase):
    def _tem_preto(self, imagem) -> bool:
        preto = QColor("#000000").rgb()
        return any(imagem.pixel(x, y) == preto
                   for x in range(0, imagem.width(), 2) for y in range(0, imagem.height(), 2))

    def test_desenha_em_todos_os_formatos(self) -> None:
        etiqueta = et.Etiqueta("Cabo HDMI 2 metros", "7891000315507", 39.9)
        for formato in et.FORMATOS:
            with self.subTest(formato.chave):
                rolo = et.Formato("x", "x", formato.largura, formato.altura)
                self.assertTrue(self._tem_preto(et.previa(rolo, [etiqueta], 8.0)))

    def test_codigo_que_nao_e_ean_sai_escrito_sem_quebrar(self) -> None:
        formato = et.POR_CHAVE["rolo-50x30"]
        imagem = et.previa(formato, [et.Etiqueta("Peça", "ABC-123", 0)], 8.0)
        self.assertTrue(self._tem_preto(imagem))


class EtiquetasDialogTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from dumtech.apps.estoque.ui.etiquetas_dialog import EtiquetasDialog

        self.repo = _repo()
        self.addCleanup(self.repo.db.close)
        self.sem = self.repo.criar(Produto(codigo="S1", nome="Sem código", unidade="UN",
                                           preco_venda=10.0, quantidade=3))
        self.com = self.repo.criar(Produto(codigo="C1", nome="Com código", unidade="UN",
                                           codigo_barras="7891000315507", quantidade=2))
        self.prefs = MemoryPreferences()
        self.dialogo = EtiquetasDialog(self.repo, [(self.sem, 2)], prefs=self.prefs)
        self.addCleanup(self.dialogo.deleteLater)

    def test_produto_sem_codigo_ganha_um_ao_entrar_na_lista(self) -> None:
        gravado = self.repo.obter(self.sem.id).codigo_barras
        self.assertTrue(cb.valido(gravado))
        self.assertEqual(self.dialogo.lista_etiquetas()[0].barras, gravado)
        self.assertIn("código interno", self.dialogo.aviso.text())

    def test_quantidade_editada_na_tabela(self) -> None:
        self.dialogo.adicionar(self.com, 1)
        self.dialogo.tabela.item(1, 3).setText("5")
        self.assertEqual(len(self.dialogo.lista_etiquetas()), 7)
        self.dialogo.tabela.item(1, 3).setText("abc")   # bobagem nao vale
        self.assertEqual(len(self.dialogo.lista_etiquetas()), 7)

    def test_todos_com_estoque_uma_por_unidade(self) -> None:
        self.dialogo._limpar()
        self.dialogo._todos_com_estoque()
        self.assertEqual(len(self.dialogo.lista_etiquetas()), 5)

    def test_grava_pdf_e_lembra_o_papel(self) -> None:
        indice = self.dialogo.formato.findData("rolo-50x30")
        self.dialogo.formato.setCurrentIndex(indice)
        self.assertEqual(self.prefs.get("etiqueta_formato"), "rolo-50x30")
        destino = Path(tempfile.mkdtemp()) / "etiquetas.pdf"
        self.assertTrue(self.dialogo.gravar_pdf(destino))
        self.assertTrue(destino.read_bytes().startswith(b"%PDF"))


class GerarNoCadastroTestCase(unittest.TestCase):
    def test_botao_gerar_preenche_e_some_quando_ja_tem_codigo(self) -> None:
        from dumtech.apps.estoque.ui.produto_dialog import ProdutoDialog

        repo = _repo()
        self.addCleanup(repo.db.close)
        dialogo = ProdutoDialog(repo)
        self.addCleanup(dialogo.deleteLater)
        self.assertTrue(dialogo.botao_gerar.isEnabled())
        dialogo.botao_gerar.click()
        self.assertEqual(dialogo.codigo_barras.text(), cb.interno(1))
        self.assertFalse(dialogo.botao_gerar.isEnabled())


if __name__ == "__main__":
    unittest.main()
