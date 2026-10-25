"""Importar e exportar o catalogo em CSV.

A importacao nunca grava direto: primeiro mostra o que vai acontecer, com os
motivos de cada linha recusada, e so grava depois do "Importar".
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ....ui.theme import Space, apply_window_theme, palette_for
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import label, separator
from ....ui.widgets.table import DataTable
from ..models import EstoqueError, PreviaImportacao
from ..repository import EstoqueRepository

FILTRO_CSV = "Planilha CSV (*.csv);;Todos os arquivos (*)"


def _ler_arquivo(caminho: Path) -> str:
    """Planilha brasileira costuma vir em cp1252, nao em UTF-8."""
    bruto = caminho.read_bytes()
    for codificacao in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return bruto.decode(codificacao)
        except UnicodeDecodeError:
            continue
    raise EstoqueError(
        "Não foi possível ler o arquivo. Salve a planilha como CSV UTF-8 e tente de novo."
    )


def exportar(parent: QWidget, repository: EstoqueRepository, movimentacoes: bool = False) -> None:
    """Grava um CSV com o catalogo ou com o historico."""
    padrao = "movimentacoes.csv" if movimentacoes else "produtos.csv"
    caminho, _ = QFileDialog.getSaveFileName(parent, "Exportar para CSV", padrao, FILTRO_CSV)
    if not caminho:
        return
    texto = (
        repository.exportar_movimentacoes_csv()
        if movimentacoes
        else repository.exportar_produtos_csv(incluir_inativos=True)
    )
    # BOM: e o que faz o Excel abrir o arquivo com os acentos certos
    Path(caminho).write_text(texto, encoding="utf-8-sig")
    QMessageBox.information(
        parent,
        "Exportado",
        f"Arquivo salvo em:\n{caminho}",
    )


def importar(parent: QWidget, repository: EstoqueRepository) -> bool:
    """Abre a planilha, mostra a previa e importa se o usuario confirmar."""
    caminho, _ = QFileDialog.getOpenFileName(parent, "Importar produtos", "", FILTRO_CSV)
    if not caminho:
        return False

    try:
        texto = _ler_arquivo(Path(caminho))
        previa = repository.prever_importacao(texto)
    except EstoqueError as erro:
        QMessageBox.warning(parent, "Não foi possível ler a planilha", str(erro))
        return False

    dialogo = PreviaDialog(previa, Path(caminho).name, parent)
    if not dialogo.exec():
        return False

    try:
        criados, atualizados = repository.importar(texto)
    except EstoqueError as erro:
        QMessageBox.warning(parent, "Não foi possível importar", str(erro))
        return False

    QMessageBox.information(
        parent,
        "Importação concluída",
        f"{criados} produto(s) criado(s) e {atualizados} atualizado(s).",
    )
    return True


class PreviaDialog(QDialog):
    """O que a planilha vai fazer, antes de fazer."""

    def __init__(
        self, previa: PreviaImportacao, arquivo: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Conferir importação")
        self.setModal(True)
        self.setMinimumSize(680, 460)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)

        raiz.addWidget(label("Conferir importação", "section"))
        raiz.addWidget(label(arquivo, "muted"))
        raiz.addWidget(separator())

        resumo = (
            f"{len(previa.criar)} produto(s) serão criados   ·   "
            f"{len(previa.atualizar)} serão atualizados"
        )
        raiz.addWidget(label(resumo, "strong"))
        raiz.addWidget(
            label(
                "Em produtos que já existem, a quantidade da planilha é ignorada: "
                "quem manda no saldo é o histórico de movimentações.",
                "dim",
            )
        )

        if previa.recusados:
            raiz.addWidget(
                label(f"{len(previa.recusados)} linha(s) serão ignoradas:", "muted")
            )
            tabela = DataTable(["Linha", "Motivo"])
            tabela.fill(
                [
                    [tabela.cell(str(numero)), tabela.cell(motivo, tone="danger")]
                    for numero, motivo in previa.recusados
                ],
                {0: 90},
            )
            raiz.addWidget(tabela, 1)
        else:
            raiz.addWidget(label("Nenhuma linha com problema.", "muted"))
            raiz.addStretch(1)

        rodape = QHBoxLayout()
        rodape.addStretch(1)
        cancelar = Button("Cancelar")
        cancelar.clicked.connect(self.reject)
        rodape.addWidget(cancelar)

        self.botao_importar = Button("Importar", "check", "primary")
        self.botao_importar.setDefault(True)
        self.botao_importar.setEnabled(previa.total_valido > 0)
        self.botao_importar.clicked.connect(self.accept)
        rodape.addWidget(self.botao_importar)
        raiz.addLayout(rodape)

        apply_window_theme(self, palette_for(parent))
