"""Checklist, fotos e assinatura da ordem, numa janela so."""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ....core.errors import RegraError
from ....ui.theme import Space, apply_window_theme, palette_for
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import label, repolish
from ..models import Ordem, OrdemError
from ..repository import OrdensRepository

#: lado maior da foto guardada: o bastante para ler, sem encher o backup
LADO_FOTO = 1280
QUALIDADE_FOTO = 80


def preparar_foto(caminho: str) -> bytes:
    """Le a foto, reduz e devolve JPEG."""
    leitor = QImageReader(caminho)
    leitor.setAutoTransform(True)
    imagem = leitor.read()
    if imagem.isNull():
        raise OrdemError("Não consegui abrir esta imagem.")
    if max(imagem.width(), imagem.height()) > LADO_FOTO:
        imagem = imagem.scaled(LADO_FOTO, LADO_FOTO, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
    return _bytes(imagem.convertToFormat(QImage.Format.Format_RGB888), "JPG", QUALIDADE_FOTO)


def _bytes(imagem: QImage, formato: str, qualidade: int = -1) -> bytes:
    dados = QByteArray()
    saida = QBuffer(dados)
    saida.open(QIODevice.OpenModeFlag.WriteOnly)
    imagem.save(saida, formato, qualidade)
    return bytes(dados)


class PapelDeAssinatura(QWidget):
    """Assina com o mouse ou com a caneta da mesa."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.traco: list[list[QPoint]] = []

    @property
    def vazio(self) -> bool:
        return not self.traco

    def limpar(self) -> None:
        self.traco = []
        self.update()

    def mousePressEvent(self, evento) -> None:  # noqa: N802
        self.traco.append([evento.position().toPoint()])
        self.update()

    def mouseMoveEvent(self, evento) -> None:  # noqa: N802
        if self.traco:
            self.traco[-1].append(evento.position().toPoint())
            self.update()

    def _desenhar(self, pintor: QPainter) -> None:
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(QPen(QColor("#15151a"), 2.4, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for linha in self.traco:
            for inicio, fim in zip(linha, linha[1:]):
                pintor.drawLine(inicio, fim)
            if len(linha) == 1:
                pintor.drawPoint(linha[0])

    def paintEvent(self, evento) -> None:  # noqa: N802
        pintor = QPainter(self)
        pintor.fillRect(self.rect(), QColor("#ffffff"))
        self._desenhar(pintor)
        pintor.end()

    def imagem(self) -> bytes:
        tela = QImage(self.size(), QImage.Format.Format_ARGB32)
        tela.fill(Qt.GlobalColor.white)
        pintor = QPainter(tela)
        self._desenhar(pintor)
        pintor.end()
        return _bytes(tela, "PNG")


class AnexosDialog(QDialog):
    def __init__(self, repository: OrdensRepository, ordem: Ordem,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.ordem = ordem
        self.setWindowTitle(f"Checklist e fotos - {ordem.numero}")
        self.setModal(True)
        self.setMinimumSize(640, 520)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)
        raiz.addWidget(label(f"{ordem.numero}  ·  {ordem.assunto or ordem.cliente}", "section"))

        abas = QTabWidget()
        abas.addTab(self._aba_checklist(), "Checklist")
        abas.addTab(self._aba_fotos(), "Fotos")
        abas.addTab(self._aba_assinatura(), "Assinatura")
        raiz.addWidget(abas, 1)

        rodape = QHBoxLayout()
        self.aviso = label("", "muted")
        rodape.addWidget(self.aviso, 1)
        fechar = Button("Fechar", "check", "primary")
        fechar.clicked.connect(self.accept)
        rodape.addWidget(fechar)
        raiz.addLayout(rodape)

        apply_window_theme(self, palette_for(parent))
        self.carregar_checklist()
        self.carregar_fotos()

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # --------------------------------------------------------------- checklist
    def _aba_checklist(self) -> QWidget:
        aba = QWidget()
        coluna = QVBoxLayout(aba)
        linha = QHBoxLayout()
        self.nova_tarefa = QLineEdit()
        self.nova_tarefa.setPlaceholderText("O que precisa ser conferido? Ex.: testar a tela")
        self.nova_tarefa.returnPressed.connect(self._adicionar_tarefa)
        linha.addWidget(self.nova_tarefa, 1)
        adicionar = Button("Adicionar", "plus")
        adicionar.clicked.connect(self._adicionar_tarefa)
        linha.addWidget(adicionar)
        coluna.addLayout(linha)
        self.lista = QListWidget()
        self.lista.itemChanged.connect(self._tarefa_mudou)
        coluna.addWidget(self.lista, 1)
        remover = Button("Remover linha", "trash", "ghost")
        remover.clicked.connect(self._remover_tarefa)
        coluna.addWidget(remover, 0, Qt.AlignmentFlag.AlignRight)
        return aba

    def carregar_checklist(self) -> None:
        self.lista.blockSignals(True)
        self.lista.clear()
        for tarefa in self.repository.checklist_de(self.ordem.id):
            item = QListWidgetItem(tarefa.texto)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if tarefa.feito else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, tarefa.id)
            self.lista.addItem(item)
        self.lista.blockSignals(False)

    def _adicionar_tarefa(self) -> None:
        try:
            self.repository.adicionar_tarefa(self.ordem.id, self.nova_tarefa.text())
        except RegraError as erro:
            self._dizer(str(erro), "danger")
            return
        self.nova_tarefa.clear()
        self.carregar_checklist()

    def _tarefa_mudou(self, item: QListWidgetItem) -> None:
        self.repository.marcar_tarefa(item.data(Qt.ItemDataRole.UserRole),
                                      item.checkState() == Qt.CheckState.Checked)

    def _remover_tarefa(self) -> None:
        item = self.lista.currentItem()
        if item is not None:
            self.repository.remover_tarefa(item.data(Qt.ItemDataRole.UserRole))
            self.carregar_checklist()

    # ------------------------------------------------------------------- fotos
    def _aba_fotos(self) -> QWidget:
        aba = QWidget()
        coluna = QVBoxLayout(aba)
        self.fotos = QListWidget()
        self.fotos.setViewMode(QListView.ViewMode.IconMode)
        self.fotos.setIconSize(QSize(150, 150))
        self.fotos.setResizeMode(QListView.ResizeMode.Adjust)
        self.fotos.setSpacing(8)
        coluna.addWidget(self.fotos, 1)
        linha = QHBoxLayout()
        linha.addStretch(1)
        remover = Button("Remover foto", "trash", "ghost")
        remover.clicked.connect(self._remover_foto)
        linha.addWidget(remover)
        adicionar = Button("Adicionar foto", "plus")
        adicionar.clicked.connect(self._escolher_foto)
        linha.addWidget(adicionar)
        coluna.addLayout(linha)
        return aba

    def carregar_fotos(self) -> None:
        self.fotos.clear()
        for foto in self.repository.fotos_de(self.ordem.id):
            imagem = QPixmap()
            imagem.loadFromData(foto.imagem)
            item = QListWidgetItem(QIcon(imagem), "")
            item.setData(Qt.ItemDataRole.UserRole, foto.id)
            self.fotos.addItem(item)

    def adicionar_foto(self, caminho: str) -> None:
        try:
            self.repository.adicionar_foto(self.ordem.id, preparar_foto(caminho))
        except RegraError as erro:
            self._dizer(str(erro), "danger")
            return
        self.carregar_fotos()

    def _escolher_foto(self) -> None:
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Escolher fotos", "", "Imagens (*.jpg *.jpeg *.png *.bmp *.webp)"
        )
        for caminho in caminhos:
            self.adicionar_foto(caminho)

    def _remover_foto(self) -> None:
        item = self.fotos.currentItem()
        if item is not None:
            self.repository.remover_foto(item.data(Qt.ItemDataRole.UserRole))
            self.carregar_fotos()

    # -------------------------------------------------------------- assinatura
    def _aba_assinatura(self) -> QWidget:
        aba = QWidget()
        coluna = QVBoxLayout(aba)
        self.situacao_assinatura = label("", "muted")
        coluna.addWidget(self.situacao_assinatura)
        self.papel = PapelDeAssinatura()
        coluna.addWidget(self.papel, 1)
        linha = QHBoxLayout()
        linha.addStretch(1)
        limpar = Button("Limpar", "close", "ghost")
        limpar.clicked.connect(self.papel.limpar)
        linha.addWidget(limpar)
        guardar = Button("Guardar assinatura", "check", "success")
        guardar.clicked.connect(self.guardar_assinatura)
        linha.addWidget(guardar)
        coluna.addLayout(linha)
        self._mostrar_situacao()
        return aba

    def _mostrar_situacao(self) -> None:
        assinada = self.repository.assinatura_de(self.ordem.id) is not None
        self.situacao_assinatura.setText(
            "Esta ordem já tem assinatura. Guardar outra troca a anterior." if assinada
            else "O cliente assina aqui: ela sai no comprovante de entrega."
        )

    def guardar_assinatura(self) -> None:
        if self.papel.vazio:
            self._dizer("Assine no quadro antes de guardar.", "danger")
            return
        self.repository.assinar(self.ordem.id, self.papel.imagem())
        self.papel.limpar()
        self._mostrar_situacao()
        self._dizer("Assinatura guardada.", "success")
