"""Tamanhos e cores: um produto de verdade para cada combinacao."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.form import FormDialog
from ..models import Produto
from ..repository import EstoqueRepository


class VariacoesDialog(FormDialog):
    def __init__(self, repository: EstoqueRepository, produto: Produto,
                 parent: QWidget | None = None) -> None:
        self.repository = repository
        self.produto = produto
        self.criadas: list[Produto] = []
        super().__init__(f"Variações de {produto.nome}",
                         "Cada combinação vira um produto com saldo e preço próprios",
                         parent, largura=520)
        self.tamanhos = form.texto("", "Ex.: P, M, G, GG")
        self.add_row("Tamanhos", self.tamanhos)
        self.cores = form.texto("", "Ex.: Azul, Preto")
        self.add_row("Cores", self.cores)
        self.add_note("")
        self._nota = self.extras.itemAt(0).widget()
        self.tamanhos.textChanged.connect(self._contar)
        self.cores.textChanged.connect(self._contar)
        self._contar()
        self.tamanhos.setFocus()

    @staticmethod
    def _lista(texto: str) -> list[str]:
        return [parte.strip() for parte in texto.split(",") if parte.strip()]

    def _contar(self) -> None:
        tamanhos = len(self._lista(self.tamanhos.text()))
        cores = len(self._lista(self.cores.text()))
        total = (tamanhos or 1) * (cores or 1) if tamanhos or cores else 0
        self._nota.setText(f"Vai criar {fmt.contagem(total, 'produto')}, com saldo zero. "
                           "O saldo entra pela nota, como sempre.")

    def salvar(self) -> None:
        self.criadas = self.repository.criar_variacoes(
            self.produto, self._lista(self.tamanhos.text()), self._lista(self.cores.text())
        )
