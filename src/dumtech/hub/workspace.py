"""A area onde os aplicativos rodam dentro do Hub.

Cada aplicativo montado vira uma pagina: uma faixa de contexto no topo (quem
voce e, em que tela esta) e a casca do aplicativo embaixo. A cor do aplicativo
aparece no emblema e no traco da aba do topo - e o que diferencia estar no
Vendas de estar no Estoque.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.app_module import AppManifest
from ..ui.app_shell import AppSurface
from ..ui.theme import Radius, Space, font_for
from ..ui.widgets.buttons import Button
from ..ui import format as fmt
from ..ui.widgets.common import IconBadge, Pill, label
from ..ui.widgets.indicador import PILULA, Indicador
from ..ui.widgets.pilha import Pilha

BAR_HEIGHT = 74


class ViewTab(QPushButton):
    """Uma tela do aplicativo: um segmento do seletor de telas.

    O seletor e um trilho cinza com o segmento escolhido em branco - a aba
    sublinhada ja e do topo (qual aplicativo), entao aqui a forma e outra
    (qual tela). Dois niveis de navegacao com a mesma cara se confundem.
    """

    def __init__(self, texto: str, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self._accent = accent
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setFont(font_for("tab"))
        self.setMinimumHeight(32)
        # o visual mora na folha da plataforma (regras `ViewTab` em theme.py):
        # folha propria em cada aba custava um setStyleSheet por aba a cada
        # troca de tema


class ContextBar(QFrame):
    """Diz em qual aplicativo voce esta e quais telas ele tem."""

    view_selected = Signal(int)
    close_requested = Signal()
    #: "Comprar" de um modulo em teste gratis
    comprar_requested = Signal()

    def __init__(self, manifest: AppManifest, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manifest = manifest
        self.setObjectName("ContextBar")
        self.setFixedHeight(BAR_HEIGHT)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(Space.xxl - 2, Space.lg + 2, Space.xl + 2, 0)
        linha.setSpacing(Space.md)

        self.badge = IconBadge(manifest.icon, manifest.accent, size=38, radius=11)
        linha.addWidget(self.badge)

        nome = label(manifest.short_name, "title")
        linha.addWidget(nome)

        linha.addSpacing(Space.lg)
        self.trilho = QFrame()
        self.trilho.setObjectName("ViewTrack")
        self.tabs = QHBoxLayout(self.trilho)
        self.tabs.setSpacing(2)
        self.tabs.setContentsMargins(3, 3, 3, 3)
        self.indicador = Indicador(self.trilho, forma=PILULA, raio=Radius.sm)
        linha.addWidget(self.trilho, 0, Qt.AlignmentFlag.AlignVCenter)
        linha.addStretch(1)

        # teste gratis: quantos dias faltam e o caminho para comprar, bem
        # onde a pessoa esta usando - nao escondido na tela de licenca
        self.selo_teste = Pill("", "accent")
        linha.addWidget(self.selo_teste, 0, Qt.AlignmentFlag.AlignVCenter)
        self.botao_comprar = Button("Comprar", "cart", "primary")
        self.botao_comprar.setToolTip("Abre a loja com este módulo no carrinho")
        self.botao_comprar.clicked.connect(self.comprar_requested.emit)
        linha.addWidget(self.botao_comprar)
        self.mostrar_teste(None)

        self.botao_fechar = Button("Fechar", "close", "ghost")
        self.botao_fechar.setToolTip("Fecha o aplicativo e volta para o Início (Ctrl+W)")
        self.botao_fechar.clicked.connect(self.close_requested.emit)
        linha.addWidget(self.botao_fechar)

        self._tabs: list[ViewTab] = []

    def build_tabs(self, titulos: list[str]) -> None:
        for indice, titulo in enumerate(titulos):
            aba = ViewTab(titulo, self.manifest.accent, self.trilho)
            aba.clicked.connect(lambda _=False, i=indice: self.view_selected.emit(i))
            self.tabs.addWidget(aba)
            self.indicador.registrar(aba)
            self._tabs.append(aba)
        if self._tabs:
            self._tabs[0].setChecked(True)
            self.indicador.selecionar(self._tabs[0], animar=False)

    def mostrar_teste(self, dias: int | None) -> None:
        """None = modulo comprado (nada aparece). Numero = dias de teste restantes."""
        em_teste = dias is not None
        if em_teste:
            self.selo_teste.setText(
                "Teste grátis: último dia" if dias <= 1
                else f"Teste grátis  ·  faltam {fmt.contagem(dias, 'dia', 'dias')}")
            self.selo_teste.set_tone("warning" if dias <= 2 else "accent")
        self.selo_teste.setVisible(em_teste)
        self.botao_comprar.setVisible(em_teste)

    def select(self, indice: int) -> None:
        if 0 <= indice < len(self._tabs):
            self._tabs[indice].setChecked(True)
            self.indicador.selecionar(self._tabs[indice])


class AppPage(QWidget):
    """Faixa de contexto + casca do aplicativo."""

    close_requested = Signal(str)
    #: codigo de licenca do modulo em teste que a pessoa quer comprar
    comprar_requested = Signal(str)

    def __init__(self, surface: AppSurface, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.surface = surface
        self.manifest = surface.manifest

        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)

        self.bar = ContextBar(self.manifest, self)
        self.bar.build_tabs([v.title for v in surface.views])
        self.bar.view_selected.connect(surface.show_view)
        self.bar.close_requested.connect(
            lambda: self.close_requested.emit(self.manifest.app_id)
        )
        self.bar.comprar_requested.connect(
            lambda: self.comprar_requested.emit(self.manifest.license_code)
        )
        surface.stack.currentChanged.connect(self.bar.select)
        coluna.addWidget(self.bar)

        surface.set_embedded(self)
        coluna.addWidget(surface, 1)


class Workspace(Pilha):
    """Todas as paginas de aplicativo abertas.

    Alem de mostrar, o Workspace lembra quem ficou para tras: um aplicativo
    aberto atras de outro continua com a tela desenhada com o dado de antes
    quando um vizinho escreve no banco dele (a venda que da baixa no estoque,
    a ordem entregue que vira conta a receber). Ele fica marcado como sujo e
    recarrega no instante em que volta a aparecer - assim ninguem paga a
    leitura de sete bancos para ver uma tela so.
    """

    close_requested = Signal(str)
    comprar_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pages: dict[str, AppPage] = {}
        self._sujos: set[str] = set()

    def mount(self, surface: AppSurface) -> AppPage:
        app_id = surface.manifest.app_id
        page = self._pages.get(app_id)
        if page is None:
            page = AppPage(surface, self)
            page.close_requested.connect(self.close_requested.emit)
            page.comprar_requested.connect(self.comprar_requested.emit)
            self._pages[app_id] = page
            self.addWidget(page)
        self._sujos.discard(app_id)  # acabou de nascer: ja esta atualizado
        self.setCurrentWidget(page)
        return page

    def montar_escondido(self, surface: AppSurface) -> AppPage:
        """Monta a pagina de um aplicativo preparado, sem trazer para a frente."""
        app_id = surface.manifest.app_id
        page = self._pages.get(app_id)
        if page is None:
            atual = self.currentWidget()
            page = AppPage(surface, self)
            page.close_requested.connect(self.close_requested.emit)
            page.comprar_requested.connect(self.comprar_requested.emit)
            self._pages[app_id] = page
            self.addWidget(page)
            if atual is not None:
                self.setCurrentWidget(atual)  # quem estava na frente continua
        return page

    def marcar_testes(self, licenca) -> None:
        """Atualiza o selo de teste gratis de cada modulo aberto."""
        for app_id, page in self._pages.items():
            page.bar.mostrar_teste(licenca.dias_de_teste(app_id) if licenca.teste_ativo(app_id) else None)

    def unmount(self, app_id: str) -> None:
        self._sujos.discard(app_id)
        page = self._pages.pop(app_id, None)
        if page is None:
            return
        self.removeWidget(page)
        page.setParent(None)
        page.deleteLater()

    def show_app(self, app_id: str) -> bool:
        page = self._pages.get(app_id)
        if page is None:
            return False
        self.setCurrentWidget(page)
        self._atualizar(app_id)
        return True

    # ------------------------------------------------------- dado que mudou
    def invalidar(self, app_id: str) -> None:
        """O dado deste aplicativo mudou por fora dele."""
        if app_id in self._pages:
            self._sujos.add(app_id)

    def invalidar_tudo(self) -> None:
        """Mudou algo que todo mundo usa (a agenda de clientes da plataforma)."""
        self._sujos.update(self._pages)

    def atualizar_visivel(self) -> None:
        """Quem esta na frente nao espera: recarrega agora."""
        app_id = self.current_app
        if app_id:
            self._atualizar(app_id)

    @property
    def sujos(self) -> tuple[str, ...]:
        return tuple(self._sujos)

    def _atualizar(self, app_id: str) -> None:
        if app_id not in self._sujos:
            return
        self._sujos.discard(app_id)
        page = self._pages.get(app_id)
        if page is not None:
            page.surface.refresh_all()

    @property
    def current_app(self) -> str | None:
        page = self.currentWidget()
        return page.manifest.app_id if isinstance(page, AppPage) else None

    @property
    def mounted(self) -> tuple[str, ...]:
        return tuple(self._pages)
