"""A janela de atualizar o Hub: o que mudou, e um botao que resolve.

O QUE ELA PRECISA FAZER
    Dizer, em portugues, **o que muda** e **o que vai acontecer** - porque o
    programa vai fechar sozinho. Ninguem clica em "instalar" sem saber disso.

O CAMINHO INTEIRO
    Baixar (com barra, porque sao ~30 MB) -> conferir a impressao digital ->
    abrir o instalador em silencio -> fechar o Hub. O instalador troca os
    arquivos e abre o Hub de novo, ja atualizado.

QUANDO O BOTAO NAO APARECE
    Sem `automatica` (decisao da DumTech no painel), ou rodando do codigo em
    vez do programa instalado: ai o caminho e a pagina de download, e a janela
    diz isso em vez de fingir que instala.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ...core import atualizacao as nucleo
from ...core.atualizacao import Atualizacao, AtualizacaoError
from ...ui import tasks
from ...ui.theme import Space, apply_window_theme, palette_for
from ...ui.widgets.buttons import Button
from ...ui.widgets.common import IconBadge, label, repolish, separator

LARGURA = 480


class AtualizacaoDialog(QDialog):
    """Mostra a novidade e cuida de baixar e instalar."""

    #: o cliente escolheu "Agora nao" (some ate sair outra versao)
    dispensou = Signal()
    #: vai instalar: quem chamou precisa fechar o Hub
    instalando = Signal()

    def __init__(self, aviso: Atualizacao, instalada: str, service,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.aviso = aviso
        self.service = service
        self.instalada = instalada
        self._baixando = False
        self._cancelar = False
        self._instalador: Path | None = None

        self.setWindowTitle("Atualizar o DumTech Hub")
        self.setModal(True)
        self.setFixedWidth(LARGURA)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 24, 28, 22)
        raiz.setSpacing(Space.md)

        topo = QHBoxLayout()
        topo.setSpacing(Space.md)
        topo.addWidget(IconBadge("in", "accent", size=42, radius=13), 0,
                       Qt.AlignmentFlag.AlignTop)
        cabeca = QVBoxLayout()
        cabeca.setSpacing(2)
        cabeca.addWidget(label(
            "Atualização importante" if aviso.obrigatoria else "Versão nova disponível",
            "title"))
        cabeca.addWidget(label(
            f"{instalada}  →  {aviso.versao}"
            + (f"   ·   {aviso.tamanho_texto}" if aviso.tamanho_texto else ""), "muted"))
        topo.addLayout(cabeca, 1)
        raiz.addLayout(topo)

        if aviso.notas:
            notas = label(aviso.notas, "body")
            notas.setWordWrap(True)
            raiz.addWidget(notas)

        raiz.addWidget(separator())
        self.explica = label(self._explicacao(), "dim")
        self.explica.setWordWrap(True)
        raiz.addWidget(self.explica)

        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setTextVisible(True)
        self.barra.setFormat("%p%")
        self.barra.setVisible(False)
        raiz.addWidget(self.barra)

        self.aviso_tela = label("", "muted")
        self.aviso_tela.setWordWrap(True)
        raiz.addWidget(self.aviso_tela)

        # a saida de emergencia e um link, nao um terceiro botao: so aparece
        # quando o caminho normal falhou, e nao disputa espaco com a acao
        # a cor vem do tema: o azul de fabrica do link some no fundo escuro
        cor_link = palette_for(parent).accent
        self.link_site = label(
            f'<a href="#" style="color:{cor_link}; text-decoration:none">'
            "Baixar pelo site em vez disso</a>", "muted")
        self.link_site.setTextFormat(Qt.TextFormat.RichText)
        self.link_site.linkActivated.connect(lambda _: self._abrir_site())
        raiz.addWidget(self.link_site)
        self.link_site.setVisible(False)

        botoes = QHBoxLayout()
        botoes.setSpacing(Space.sm)
        self.botao_depois = Button("Agora não", "", "ghost")
        self.botao_depois.setAutoDefault(False)
        self.botao_depois.clicked.connect(self._depois)
        botoes.addWidget(self.botao_depois)
        botoes.addStretch(1)

        # UMA acao principal: instalar aqui, ou (quando a DumTech desligou a
        # instalacao pelo Hub) abrir a pagina de download
        pode = aviso.automatica and nucleo.pode_atualizar_aqui()
        self.botao_instalar = Button(
            "Baixar e instalar" if pode else "Abrir o site", "in" if pode else "external",
            "primary")
        self.botao_instalar.setMinimumHeight(38)
        self.botao_instalar.setDefault(True)
        self.botao_instalar.clicked.connect(self._baixar if pode else self._abrir_site)
        botoes.addWidget(self.botao_instalar)
        raiz.addLayout(botoes)
        if aviso.obrigatoria:
            self.botao_depois.setText("  Fechar")

        apply_window_theme(self, palette_for(parent))

    # ------------------------------------------------------------------ texto
    def _explicacao(self) -> str:
        if not self.aviso.automatica:
            return "Esta versão é instalada pelo site. Seus dados continuam onde estão."
        if not nucleo.pode_atualizar_aqui():
            return "Rodando pelo código: instale pelo site."
        return "O Hub fecha, instala e abre sozinho em menos de 1 minuto. Seus dados não são tocados."

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso_tela.setText(texto)
        self.aviso_tela.setProperty("tone", tom)
        repolish(self.aviso_tela)

    # ------------------------------------------------------------------ acoes
    def _depois(self) -> None:
        if self._baixando:
            self._cancelar = True
            self._dizer("Cancelando...")
            return
        if not self.aviso.obrigatoria:
            self.dispensou.emit()
        self.reject()

    def _abrir_site(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(self.aviso.url))
        self.reject()

    def _baixar(self) -> None:
        if self._baixando:
            return
        self._baixando = True
        self._cancelar = False
        self.botao_instalar.setEnabled(False)
        self.botao_depois.setText("  Cancelar")
        self.barra.setValue(0)
        self.barra.setVisible(True)
        self._dizer("Baixando a atualização...")

        def andar(baixado: int, total: int) -> None:
            # vem da thread do download: so numeros, nenhum widget tocado aqui
            self._progresso = (baixado, total)

        def trabalho():
            return self.service.baixar(self.aviso, progresso=andar,
                                       parar=lambda: self._cancelar)

        tasks.executar(self, trabalho, self._baixou, self._falhou)
        self._relogio_barra()

    def _relogio_barra(self) -> None:
        """A barra anda na thread da tela, lendo o numero que o download deixou."""
        from PySide6.QtCore import QTimer

        def passo() -> None:
            if not self._baixando:
                return
            baixado, total = getattr(self, "_progresso", (0, 0))
            if total > 0:
                self.barra.setRange(0, 100)
                self.barra.setValue(min(int(baixado * 100 / total), 100))
            else:
                self.barra.setRange(0, 0)   # sem tamanho: barra indeterminada
            QTimer.singleShot(120, self, passo)

        QTimer.singleShot(120, self, passo)

    def _baixou(self, instalador: Path) -> None:
        self._baixando = False
        self._instalador = instalador
        self.barra.setRange(0, 100)
        self.barra.setValue(100)
        self.botao_depois.setVisible(False)
        self._dizer("Arquivo conferido. Instalando - o Hub vai fechar e abrir de novo.",
                    "success")
        try:
            self.service.instalar(instalador, self.aviso)
        except AtualizacaoError as erro:
            self.botao_depois.setVisible(True)
            self.botao_depois.setText("  Fechar")
            self.botao_instalar.setEnabled(True)
            self._dizer(str(erro), "danger")
            return
        self.instalando.emit()
        self.accept()

    def _falhou(self, erro: Exception) -> None:
        self._baixando = False
        self.barra.setVisible(False)
        self.botao_instalar.setEnabled(True)
        self.botao_depois.setText("  Agora não")
        if isinstance(erro, AtualizacaoError) and erro.codigo == "cancelado":
            self._dizer("Download cancelado.")
            return
        texto = str(erro) if isinstance(erro, AtualizacaoError) else \
            "Não foi possível baixar agora."
        self._dizer(texto, "danger")
        self.botao_instalar.setText("  Tentar de novo")
        self.link_site.setVisible(True)
        # a janela cresce para a linha nova - sem isto o titulo era empurrado
        # para fora por cima
        self.adjustSize()
