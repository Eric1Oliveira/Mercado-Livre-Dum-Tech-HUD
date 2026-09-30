"""A lista de produtos que aparece enquanto se digita.

O teste mais importante deste arquivo e o do Enter. O campo de produto do
balcao recebe leitor de codigo de barras: ele digita rapido e manda Enter sem
nunca apertar seta. Se a lista roubar esse Enter, o caixa adiciona o produto
errado - e isso e pior do que nao ter sugestao nenhuma.

A regra que os testes travam: **a lista so fica com o Enter depois que alguem
apertou a seta de proposito.**
"""

from __future__ import annotations

import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from dumtech.core.catalog import ItemCatalogo
from dumtech.ui.widgets.busca_catalogo import MINIMO, BuscaCatalogo

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


PRODUTOS = [
    ItemCatalogo(produto_id=1, codigo="A1023", nome="Cafe Torrado 500g",
                 unidade="UN", casas=0, preco=20.0, saldo=10),
    ItemCatalogo(produto_id=2, codigo="A1044", nome="Cafe com Leite Po",
                 unidade="UN", casas=0, preco=14.5, saldo=3),
    ItemCatalogo(produto_id=3, codigo="B2001", nome="Cafeteira Eletrica",
                 unidade="UN", casas=0, preco=189.0, saldo=0),
]


class CatalogoFalso:
    """So o que a busca usa - e conta quantas vezes foi consultado."""

    def __init__(self, itens=None) -> None:
        self.itens = PRODUTOS if itens is None else itens
        self.consultas: list[str] = []

    def procurar(self, termo: str, limite: int = 20) -> list[ItemCatalogo]:
        self.consultas.append(termo)
        termo = termo.casefold()
        return [i for i in self.itens
                if termo in i.nome.casefold() or termo in i.codigo.casefold()][:limite]


def _tecla(key) -> QKeyEvent:
    return QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)


class BuscaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.janela = QWidget()
        self.addCleanup(self.janela.deleteLater)
        self.campo = QLineEdit(self.janela)
        self.catalogo = CatalogoFalso()
        self.busca = BuscaCatalogo(self.campo, self.catalogo)
        self.escolhidos: list[ItemCatalogo] = []
        self.busca.escolhido.connect(self.escolhidos.append)

    def _digitar(self, texto: str) -> None:
        self.campo.setText(texto)
        self.busca.procurar(texto)

    # ------------------------------------------------------- o Enter do leitor
    def test_enter_sem_seta_nao_e_consumido(self) -> None:
        """A regra que protege o leitor de codigo de barras."""
        self._digitar("cafe")
        self.assertTrue(self.busca.aberta)
        consumiu = self.busca.tecla(_tecla(Qt.Key.Key_Return))
        self.assertFalse(consumiu, "o Enter tem que seguir para quem sempre tratou")
        self.assertEqual(self.escolhidos, [])

    def test_enter_sem_seta_fecha_a_lista(self) -> None:
        self._digitar("cafe")
        self.busca.tecla(_tecla(Qt.Key.Key_Return))
        self.assertFalse(self.busca.aberta)

    def test_so_depois_da_seta_o_enter_escolhe(self) -> None:
        self._digitar("cafe")
        self.assertTrue(self.busca.tecla(_tecla(Qt.Key.Key_Down)))
        self.assertTrue(self.busca.tecla(_tecla(Qt.Key.Key_Return)))
        self.assertEqual([i.codigo for i in self.escolhidos], ["A1023"])

    def test_a_seta_desce_pela_lista(self) -> None:
        self._digitar("cafe")
        self.busca.tecla(_tecla(Qt.Key.Key_Down))
        self.busca.tecla(_tecla(Qt.Key.Key_Down))
        self.busca.tecla(_tecla(Qt.Key.Key_Return))
        self.assertEqual([i.codigo for i in self.escolhidos], ["A1044"])

    def test_digitar_de_novo_zera_a_navegacao(self) -> None:
        """Bipar outro codigo depois de ter descido nao pode herdar o destaque."""
        self._digitar("cafe")
        self.busca.tecla(_tecla(Qt.Key.Key_Down))
        self._digitar("cafeteira")
        self.assertFalse(self.busca.tecla(_tecla(Qt.Key.Key_Return)))
        self.assertEqual(self.escolhidos, [])

    def test_com_a_lista_fechada_nenhuma_tecla_e_consumida(self) -> None:
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Down, Qt.Key.Key_Up,
                    Qt.Key.Key_Escape):
            self.assertFalse(self.busca.tecla(_tecla(key)), key)

    def test_esc_fecha_e_nao_escolhe(self) -> None:
        self._digitar("cafe")
        self.assertTrue(self.busca.tecla(_tecla(Qt.Key.Key_Escape)))
        self.assertFalse(self.busca.aberta)
        self.assertEqual(self.escolhidos, [])

    # ------------------------------------------------------------- a busca
    def test_menos_de_dois_caracteres_nao_consulta(self) -> None:
        """Uma letra so traria o catalogo inteiro a cada tecla."""
        self._digitar("c")
        self.assertEqual(self.catalogo.consultas, [])
        self.assertFalse(self.busca.aberta)
        self.assertGreaterEqual(MINIMO, 2)

    def test_dois_caracteres_ja_consultam(self) -> None:
        self._digitar("ca")
        self.assertEqual(self.catalogo.consultas, ["ca"])
        self.assertTrue(self.busca.aberta)

    def test_sem_resultado_a_lista_nao_aparece(self) -> None:
        self._digitar("parafuso")
        self.assertFalse(self.busca.aberta)

    def test_apagar_o_campo_fecha_a_lista(self) -> None:
        self._digitar("cafe")
        self._digitar("")
        self.assertFalse(self.busca.aberta)

    def test_produto_sem_saldo_aparece_na_lista(self) -> None:
        """Quem decide vender sem saldo e o lojista, nao o programa."""
        self._digitar("cafeteira")
        self.assertTrue(self.busca.aberta)
        self.busca.tecla(_tecla(Qt.Key.Key_Down))
        self.busca.tecla(_tecla(Qt.Key.Key_Return))
        self.assertEqual(self.escolhidos[0].saldo, 0)

    def test_a_linha_mostra_codigo_nome_preco_e_saldo(self) -> None:
        self._digitar("cafe")
        linha = self.busca.linha_texto(0)
        for pedaco in ("A1023", "Cafe Torrado 500g", "20,00", "10"):
            self.assertIn(pedaco, linha, linha)

    def test_escolher_fecha_a_lista(self) -> None:
        self._digitar("cafe")
        self.busca.tecla(_tecla(Qt.Key.Key_Down))
        self.busca.tecla(_tecla(Qt.Key.Key_Return))
        self.assertFalse(self.busca.aberta)

    # --------------------------------------------------------- sem catalogo
    def test_sem_catalogo_nada_acontece(self) -> None:
        """Cliente sem o Estoque na licenca: o campo continua texto livre."""
        campo = QLineEdit(self.janela)
        busca = BuscaCatalogo(campo, None)
        busca.procurar("cafe")
        self.assertFalse(busca.aberta)
        self.assertFalse(busca.tecla(_tecla(Qt.Key.Key_Return)))

    def test_catalogo_com_defeito_nao_derruba_a_venda(self) -> None:
        class Quebrado:
            def procurar(self, termo, limite=20):
                raise RuntimeError("banco fora do ar")

        campo = QLineEdit(self.janela)
        busca = BuscaCatalogo(campo, Quebrado())
        busca.procurar("cafe")  # nao pode levantar
        self.assertFalse(busca.aberta)

    def test_trocar_o_catalogo_depois_funciona(self) -> None:
        """O Hub pode entregar o catalogo so quando a licenca libera."""
        campo = QLineEdit(self.janela)
        busca = BuscaCatalogo(campo, None)
        busca.catalogo = CatalogoFalso()
        busca.procurar("cafe")
        self.assertTrue(busca.aberta)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
