"""Foto do produto: cadastrada no Estoque, vista no balcao do Vendas."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    os.environ.setdefault("DUMTECH_DATA_DIR", tempfile.mkdtemp())
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QApplication.instance() or QApplication([])


from dumtech.apps.estoque import imagem  # noqa: E402
from dumtech.apps.estoque.catalog import CatalogoEstoque  # noqa: E402
from dumtech.apps.estoque.database import open_database as estoque_db  # noqa: E402
from dumtech.apps.estoque.models import EstoqueError, Produto  # noqa: E402
from dumtech.apps.estoque.repository import EstoqueRepository  # noqa: E402


def _pasta() -> Path:
    return Path(tempfile.mkdtemp())


def _foto(caminho: Path, largura: int, altura: int, transparente: bool = False) -> Path:
    formato = QImage.Format.Format_ARGB32 if transparente else QImage.Format.Format_RGB32
    figura = QImage(largura, altura, formato)
    figura.fill(QColor(0, 0, 0, 0) if transparente else QColor("#D8574F"))
    figura.save(str(caminho))
    return caminho


class PrepararImagemTestCase(unittest.TestCase):
    def test_foto_grande_vira_jpeg_pequeno(self) -> None:
        dados = imagem.preparar(_foto(_pasta() / "celular.png", 4000, 3000))
        lida = QImage.fromData(dados)
        self.assertEqual(max(lida.width(), lida.height()), imagem.LADO_MAXIMO)
        self.assertEqual(lida.width() / lida.height(), 4000 / 3000)  # nao deforma
        self.assertTrue(dados.startswith(b"\xff\xd8"))  # JPEG

    def test_foto_pequena_nao_cresce(self) -> None:
        lida = QImage.fromData(imagem.preparar(_foto(_pasta() / "p.jpg", 200, 120)))
        self.assertEqual((lida.width(), lida.height()), (200, 120))

    def test_fundo_transparente_continua_png(self) -> None:
        dados = imagem.preparar(_foto(_pasta() / "logo.png", 300, 300, transparente=True))
        self.assertTrue(dados.startswith(b"\x89PNG"))

    def test_arquivo_que_nao_e_imagem(self) -> None:
        falso = _pasta() / "nota.jpg"
        falso.write_text("isto nao e foto", encoding="utf-8")
        with self.assertRaises(EstoqueError):
            imagem.preparar(falso)

    def test_arquivo_que_nao_existe(self) -> None:
        with self.assertRaises(EstoqueError):
            imagem.preparar(_pasta() / "sumiu.png")


class ImagemNoBancoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = estoque_db(_pasta() / "estoque.db")
        self.repo = EstoqueRepository(self.db)
        self.produto = self.repo.criar(Produto(codigo="CAF", nome="Cafe 500g", preco_venda=21.9))
        self.dados = imagem.preparar(_foto(_pasta() / "cafe.png", 800, 800))

    def tearDown(self) -> None:
        self.db.close()

    def test_grava_troca_e_remove(self) -> None:
        self.assertIsNone(self.repo.imagem(self.produto.id))
        self.repo.salvar_imagem(self.produto.id, self.dados)
        self.assertEqual(self.repo.imagem(self.produto.id), self.dados)

        outra = imagem.preparar(_foto(_pasta() / "outra.png", 100, 100))
        self.repo.salvar_imagem(self.produto.id, outra)
        self.assertEqual(self.repo.imagem(self.produto.id), outra)

        self.repo.salvar_imagem(self.produto.id, None)
        self.assertIsNone(self.repo.imagem(self.produto.id))

    def test_excluir_produto_leva_a_imagem(self) -> None:
        sem_movimento = self.repo.criar(Produto(codigo="X", nome="Sem estoque"))
        self.repo.salvar_imagem(sem_movimento.id, self.dados)
        self.repo.excluir(sem_movimento.id)
        restantes = self.db.scalar("SELECT COUNT(*) FROM produto_imagens WHERE produto_id = ?",
                                   (sem_movimento.id,))
        self.assertEqual(restantes, 0)

    def test_arquivo_cru_gigante_e_recusado(self) -> None:
        with self.assertRaises(EstoqueError):
            self.repo.salvar_imagem(self.produto.id, b"0" * (3 * 1024 * 1024))

    def test_lista_de_produtos_nao_carrega_imagem(self) -> None:
        self.repo.salvar_imagem(self.produto.id, self.dados)
        listado = self.repo.listar()[0]
        self.assertFalse(hasattr(listado, "imagem"))

    def test_catalogo_entrega_a_imagem(self) -> None:
        self.repo.salvar_imagem(self.produto.id, self.dados)
        catalogo = CatalogoEstoque(self.db)
        self.assertEqual(catalogo.imagem(self.produto.id), self.dados)
        self.assertIsNone(catalogo.imagem(999))


class CadastroComImagemTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = estoque_db(_pasta() / "estoque.db")
        self.repo = EstoqueRepository(self.db)
        self.arquivo = _foto(_pasta() / "capinha.jpg", 1200, 900)

    def tearDown(self) -> None:
        self.db.close()

    def _dialogo(self, produto=None):
        from dumtech.apps.estoque.ui.produto_dialog import ProdutoDialog

        return ProdutoDialog(self.repo, produto)

    def _escolher(self, dialogo, caminho) -> None:
        alvo = "dumtech.apps.estoque.ui.produto_dialog.QFileDialog.getOpenFileName"
        with mock.patch(alvo, return_value=(str(caminho), "")):
            dialogo.botao_imagem.click()

    def test_novo_produto_com_imagem(self) -> None:
        dialogo = self._dialogo()
        self.assertFalse(dialogo.foto.tem_imagem)
        self.assertFalse(dialogo.botao_tirar_imagem.isEnabled())
        dialogo.codigo.setText("CAP")
        dialogo.nome.setText("Capinha")
        self._escolher(dialogo, self.arquivo)
        self.assertTrue(dialogo.foto.tem_imagem)
        self.assertIn("Trocar imagem", dialogo.botao_imagem.text())
        dialogo.salvar()
        self.assertIsNotNone(self.repo.imagem(dialogo.produto.id))

    def test_editar_sem_mexer_mantem_e_remover_tira(self) -> None:
        produto = self.repo.criar(Produto(codigo="CAP", nome="Capinha"))
        self.repo.salvar_imagem(produto.id, imagem.preparar(self.arquivo))

        dialogo = self._dialogo(self.repo.obter(produto.id))
        self.assertTrue(dialogo.foto.tem_imagem)
        dialogo.salvar()
        self.assertIsNotNone(self.repo.imagem(produto.id))

        dialogo = self._dialogo(self.repo.obter(produto.id))
        dialogo.botao_tirar_imagem.click()
        self.assertFalse(dialogo.foto.tem_imagem)
        dialogo.salvar()
        self.assertIsNone(self.repo.imagem(produto.id))

    def test_arquivo_ruim_avisa_e_nao_troca(self) -> None:
        falso = _pasta() / "nota.png"
        falso.write_text("nada", encoding="utf-8")
        dialogo = self._dialogo()
        with mock.patch("dumtech.apps.estoque.ui.produto_dialog.QMessageBox.warning") as aviso:
            self._escolher(dialogo, falso)
        aviso.assert_called_once()
        self.assertFalse(dialogo.foto.tem_imagem)

    def test_janela_nao_ficou_mais_alta(self) -> None:
        # a foto fica ao lado da descricao: cabe num notebook de 768 px
        produto = self.repo.criar(Produto(codigo="CAP", nome="Capinha"))
        self.assertLessEqual(self._dialogo(self.repo.obter(produto.id)).sizeHint().height(), 660)


class FotoNoBalcaoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from dumtech.apps.vendas.database import open_database as vendas_db
        from dumtech.apps.vendas.repository import VendasRepository
        from dumtech.apps.vendas.ui.balcao_view import BalcaoView

        pasta = _pasta()
        self.estoque_db = estoque_db(pasta / "estoque.db")
        estoque = EstoqueRepository(self.estoque_db)
        self.com_foto = estoque.criar(Produto(codigo="CAF", nome="Cafe 500g", codigo_barras="789001",
                                              quantidade=10, preco_venda=21.9))
        self.sem_foto = estoque.criar(Produto(codigo="ARR", nome="Arroz 5kg", codigo_barras="789002",
                                              quantidade=10, preco_venda=27.9))
        estoque.salvar_imagem(self.com_foto.id, imagem.preparar(_foto(pasta / "cafe.png", 500, 500)))

        self.vendas_db = vendas_db(pasta / "vendas.db")
        self.tela = BalcaoView(VendasRepository(self.vendas_db, catalogo=CatalogoEstoque(self.estoque_db)))

    def tearDown(self) -> None:
        self.tela.deleteLater()
        self.vendas_db.close()
        self.estoque_db.close()

    def _bipar(self, codigo: str) -> None:
        self.tela.bipe.setText(codigo)
        self.tela._localizar()

    def test_bipou_produto_com_foto_mostra_a_foto(self) -> None:
        self.assertTrue(self.tela.foto.isHidden())
        self._bipar("789001")
        self.assertFalse(self.tela.foto.isHidden())
        self.assertTrue(self.tela.foto.tem_imagem)

    def test_produto_sem_foto_e_avulso_escondem(self) -> None:
        self._bipar("789001")
        self._bipar("789002")
        self.assertTrue(self.tela.foto.isHidden())
        self._bipar("789001")
        self._bipar("nao-existe")
        self.assertTrue(self.tela.foto.isHidden())

    def test_lista_da_venda_ganha_miniatura_alinhada(self) -> None:
        self._bipar("789001")
        self.tela._adicionar()
        self.assertFalse(self.tela.foto.isHidden())  # continua a vista depois de adicionar
        self._bipar("789002")
        self.tela._adicionar()
        icones = [self.tela.tabela.item(linha, 0).icon() for linha in range(2)]
        self.assertTrue(all(not icone.isNull() for icone in icones))  # o sem foto ganha espaco vazio

    def test_venda_descartada_tira_a_foto(self) -> None:
        self._bipar("789001")
        self.tela._adicionar()
        self.tela._limpar()
        self.assertTrue(self.tela.foto.isHidden())

    def test_catalogo_sem_imagem_nao_atrapalha_a_venda(self) -> None:
        catalogo = self.tela.repository.catalogo
        self.tela.repository.catalogo = mock.Mock(wraps=catalogo, spec=["buscar", "procurar",
                                                                       "baixar", "devolver"])
        self.tela._imagens.clear()
        self._bipar("789001")
        self.tela._adicionar()
        self.assertTrue(self.tela.foto.isHidden())
        self.assertEqual(len(self.tela.itens), 1)

    def test_foto_que_falha_ao_ler_nao_derruba(self) -> None:
        self.tela.repository.catalogo.imagem = mock.Mock(side_effect=OSError("disco"))
        self.tela._imagens.clear()
        with self.assertLogs("dumtech.apps.vendas.ui.balcao_view", "ERROR"):
            self._bipar("789001")
        self.assertTrue(self.tela.foto.isHidden())
        self.assertEqual(self.tela.achado.text().split()[0], "CAF")


class MiniaturaTestCase(unittest.TestCase):
    """O recorte pequeno que as listas desenham, gravado junto com a foto."""

    def setUp(self) -> None:
        self.db = estoque_db(_pasta() / "estoque.db")
        self.repo = EstoqueRepository(self.db)
        self.produto = self.repo.criar(Produto(codigo="CAF", nome="Cafe 500g"))

    def tearDown(self) -> None:
        self.db.close()

    def test_foto_retangular_vira_miniatura_quadrada(self) -> None:
        self.repo.salvar_imagem(self.produto.id, imagem.preparar(_foto(_pasta() / "a.png", 900, 400)))
        lida = QImage.fromData(self.repo.miniatura(self.produto.id))
        self.assertEqual((lida.width(), lida.height()), (imagem.LADO_MINIATURA, imagem.LADO_MINIATURA))
        self.assertLess(len(self.repo.miniatura(self.produto.id)), 8 * 1024)

    def test_miniaturas_trazem_a_versao(self) -> None:
        self.assertEqual(self.repo.miniaturas(), {})
        self.repo.salvar_imagem(self.produto.id, imagem.preparar(_foto(_pasta() / "a.png", 300, 300)))
        versao, dados = self.repo.miniaturas()[self.produto.id]
        self.assertTrue(versao)
        self.assertEqual(dados, self.repo.miniatura(self.produto.id))
        self.repo.salvar_imagem(self.produto.id, None)
        self.assertIsNone(self.repo.miniatura(self.produto.id))


class FotoNaListaDeProdutosTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from dumtech.apps.estoque.ui.produtos_view import ProdutosView

        self.db = estoque_db(_pasta() / "estoque.db")
        self.repo = EstoqueRepository(self.db)
        self.com_foto = self.repo.criar(Produto(codigo="A", nome="Arroz"))
        self.sem_foto = self.repo.criar(Produto(codigo="B", nome="Batata"))
        self.tela = ProdutosView(self.repo)

    def tearDown(self) -> None:
        self.tela.deleteLater()
        self.db.close()

    def _icones(self) -> list[bool]:
        self.tela.refresh()
        return [not self.tela.tabela.item(linha, 1).icon().isNull()
                for linha in range(self.tela.tabela.rowCount())]

    def test_loja_sem_foto_ve_a_lista_de_sempre(self) -> None:
        self.assertEqual(self._icones(), [False, False])

    def test_com_uma_foto_todos_ganham_lugar(self) -> None:
        self.repo.salvar_imagem(self.com_foto.id, imagem.preparar(_foto(_pasta() / "a.png", 200, 200)))
        self.assertEqual(self._icones(), [True, True])  # o sem foto ganha o quadro vazio

    def test_foto_trocada_aparece_e_a_igual_nao_e_redesenhada(self) -> None:
        self.repo.salvar_imagem(self.com_foto.id, imagem.preparar(_foto(_pasta() / "a.png", 200, 200)))
        self.tela.refresh()
        primeira = self.tela._fotos[self.com_foto.id]
        self.tela.refresh()
        self.assertIs(self.tela._fotos[self.com_foto.id], primeira)  # guardada, nao redesenhada
        self.db.execute("UPDATE produto_imagens SET atualizado_em = 'depois'")
        self.tela.refresh()
        self.assertIsNot(self.tela._fotos[self.com_foto.id], primeira)


class FotoNaSugestaoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

        from dumtech.ui.widgets.busca_catalogo import BuscaCatalogo

        self.db = estoque_db(_pasta() / "estoque.db")
        self.repo = EstoqueRepository(self.db)
        self.cafe = self.repo.criar(Produto(codigo="CAF", nome="Cafe torrado", quantidade=5, preco_venda=21.9))
        self.repo.criar(Produto(codigo="CAP", nome="Cafe com leite", preco_venda=9.9))
        self.janela = QWidget()
        self.janela.resize(800, 300)
        QVBoxLayout(self.janela).addWidget(campo := QLineEdit())
        self.campo = campo
        self.busca = BuscaCatalogo(campo, CatalogoEstoque(self.db))
        self.janela.show()

    def tearDown(self) -> None:
        self.janela.deleteLater()
        self.db.close()

    def _desenhos(self) -> list:
        from dumtech.ui.widgets.busca_catalogo import DESENHO

        self.busca.procurar("Cafe")
        return [self.busca.lista.item(i).data(DESENHO) for i in range(self.busca.lista.count())]

    def test_sem_foto_a_lista_nao_reserva_espaco(self) -> None:
        self.assertEqual(self._desenhos(), [None, None])
        self.assertFalse(self.busca._delegate.com_foto)

    def test_com_foto_todas_as_linhas_alinham(self) -> None:
        self.repo.salvar_imagem(self.cafe.id, imagem.preparar(_foto(_pasta() / "a.png", 200, 200)))
        self.assertTrue(all(d is not None for d in self._desenhos()))
        self.assertTrue(self.busca._delegate.com_foto)
        self.assertIn("CAF", self.busca.linha_texto(0) + self.busca.linha_texto(1))  # texto continua

    def test_lista_nao_passa_da_borda_da_janela(self) -> None:
        self.janela.resize(800, 120)
        self.busca.procurar("Cafe")
        geometria = self.busca.lista.geometry()
        self.assertLessEqual(geometria.bottom(), self.janela.height())

    def test_campo_estreito_ganha_lista_mais_larga(self) -> None:
        self.campo.setFixedWidth(180)
        self.busca.procurar("Cafe")
        self.assertGreater(self.busca.lista.width(), 180)

    def test_linhas_desenham_sem_erro(self) -> None:
        self.repo.salvar_imagem(self.cafe.id, imagem.preparar(_foto(_pasta() / "a.png", 200, 200)))
        self.busca.procurar("Cafe")
        self.busca.lista.setCurrentRow(0)
        self.assertFalse(self.busca.lista.grab().isNull())


if __name__ == "__main__":
    unittest.main()
