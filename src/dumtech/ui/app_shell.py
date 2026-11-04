"""Casca de um aplicativo DumTech.

Um aplicativo NAO desenha janela, marca, menu lateral nem botao de tema: ele
apenas monta as suas telas e diz quais sao. Quem hospeda a casca decide como
apresenta-las - hoje o Hub, dentro da propria janela.

    class EstoqueWindow(AppWindow):
        def setup_data(self):   # abrir banco, criar repositorios
            ...
        def build_views(self):  # self.add_view("Painel", "dashboard", widget)
            ...

`AppSurface` e um QWidget comum: sem pai ele aparece como janela propria (util
em teste e para rodar um aplicativo sozinho); dentro de um layout ele vira o
conteudo do Hub. `AppWindow` e o nome historico da mesma coisa.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..core.app_module import AppContext
from ..core.config import MemoryPreferences
from ..core.mensagens import Mensageiro
from . import motion
from .widgets.common import tone_label
from .widgets.pilha import Pilha
from .widgets.rolagem import Rolagem
from .theme import (
    MODO_AUTO,
    MODO_CLARO,
    MODO_ESCURO,
    Palette,
    apply_window_theme,
    current_palette,
    palette_by_name,
    palette_for,
    refresh_theme,
)

ROTULOS_TEMA = {
    MODO_AUTO: "Tema: seguir o Hub",
    MODO_CLARO: "Tema: claro",
    MODO_ESCURO: "Tema: escuro",
}


@dataclass(frozen=True)
class View:
    """Uma tela do aplicativo, do jeito que o hospedeiro precisa conhecer."""

    title: str
    icon: str
    widget: QWidget


class AppSurface(QWidget):
    """Conteudo de um aplicativo: uma pilha de telas e a lista do que existe."""

    largura_inicial = 1220
    altura_inicial = 780
    #: Minimo baixo de proposito: as telas ficam dentro de uma area de rolagem
    #: (`Rolagem`), entao espaco apertado vira barra de rolagem, nao conteudo
    #: cortado. Num monitor de 1280x720 sobram cerca de 520 pixels de altura
    #: para o aplicativo depois das barras do Windows e do Hub.
    largura_minima = 720
    altura_minima = 420

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.manifest = context.manifest
        self.prefs = context.prefs or MemoryPreferences()
        self.theme_manager = context.theme
        #: dados da empresa para o cabecalho dos documentos (o Hub atualiza)
        self.empresa = context.empresa
        #: modelos de mensagem; sem Hub, os padroes (o botao funciona sempre)
        self.mensagens = context.mensagens or Mensageiro(empresa=context.empresa)
        #: pontes com outros modulos; None/vazio quando a licenca nao libera
        self.contas = context.contas
        self.destinos = list(context.destinos or [])

        self.setWindowTitle(self.manifest.name)
        self.setMinimumSize(self.largura_minima, self.altura_minima)
        self.resize(self.largura_inicial, self.altura_inicial)

        self.setup_data()

        self._views: list[View] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if context.so_consulta:
            motivo = getattr(context, "texto_consulta", "")
            faixa = tone_label(
                f"Somente consulta. {motivo}" if motivo else
                "Somente consulta: este módulo saiu da licença. Dá para ver e exportar, "
                "mas não para gravar.", "warning", "strong",
            )
            faixa.setContentsMargins(30, 10, 30, 10)
            faixa.setWordWrap(True)
            layout.addWidget(faixa)
        self.stack = Pilha()
        self.stack.currentChanged.connect(self._on_view_changed)
        layout.addWidget(self.stack, 1)

        self.build_views()
        if context.so_consulta:
            for view in self._views:
                if hasattr(view.widget, "so_consulta"):
                    view.widget.so_consulta()

        self._theme_mode = str(self.prefs.get("theme", MODO_AUTO))
        self._apply_theme_mode(self._theme_mode, salvar=False)
        if self.theme_manager is not None:
            self.theme_manager.changed.connect(self._on_hub_theme_changed)

    # ------------------------------------------------------------------ ganchos
    def setup_data(self) -> None:
        """Abrir banco e criar repositorios (implementado por cada aplicativo)."""

    def build_views(self) -> None:
        """Criar as telas com self.add_view(...) (implementado por cada app)."""

    def teardown(self) -> None:
        """Fechar recursos ao sair (implementado por cada aplicativo)."""

    def tem_trabalho_aberto(self) -> bool:
        """Ha algo na tela que se perde se a casca for refeita agora?

        Quem guarda trabalho fora do banco (o carrinho do balcao) responde
        True, e o Hub deixa a casca como esta em vez de remonta-la.
        """
        return False

    # -------------------------------------------------------------------- telas
    def add_view(self, title: str, icon_name: str, widget: QWidget) -> QWidget:
        """Guarda a tela e a coloca na pilha dentro de uma area de rolagem.

        Quem chama continua recebendo a TELA (nao o embrulho): o aplicativo
        guarda `self.painel = self.add_view(...)` e mexe nela como sempre.
        """
        self._views.append(View(title, icon_name, widget))
        self.stack.addWidget(Rolagem(widget))
        return widget

    def _tela(self, indice: int) -> QWidget | None:
        """A tela de verdade do indice - a pilha guarda o embrulho da rolagem."""
        if 0 <= indice < len(self._views):
            return self._views[indice].widget
        return None

    def procurar(self, texto: str) -> bool:
        """Vai para a tela de lista e filtra por este texto (a busca geral)."""
        for indice, view in enumerate(self._views):
            if hasattr(view.widget, "procurar"):
                self.show_view(indice)
                view.widget.procurar(texto)
                return True
        return False

    @property
    def views(self) -> tuple[View, ...]:
        """As telas do aplicativo, na ordem em que foram criadas."""
        return tuple(self._views)

    @property
    def current_view(self) -> int:
        return self.stack.currentIndex()

    def show_view(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)

    def refresh_all(self) -> None:
        """Manda todas as telas recarregarem (usado apos salvar algo)."""
        self._recarregar_agenda()
        for indice in range(self.stack.count()):
            self._refresh_view(self._tela(indice))

    def atualizar_empresa(self, empresa, mensageiro=None) -> None:
        """O Hub avisa que os dados da loja mudaram.

        Nao basta trocar em `self`: as telas guardam a propria copia da empresa
        e do mensageiro (e o que o comprovante e o WhatsApp usam). Sem repassar,
        cadastrar a chave Pix so valeria depois de fechar e abrir o aplicativo -
        o mesmo envelhecimento que a agenda de clientes tinha.
        """
        self.empresa = empresa
        if mensageiro is not None:
            self.mensagens = mensageiro
        for indice in range(self.stack.count()):
            tela = self._tela(indice)
            if hasattr(tela, "empresa"):
                tela.empresa = empresa
            if mensageiro is not None and hasattr(tela, "mensageiro"):
                tela.mensageiro = mensageiro
        self.refresh_all()

    def _recarregar_agenda(self) -> None:
        """Rele a agenda de clientes, que muda fora deste aplicativo.

        `setup_data` tira uma foto da lista de nomes e as telas guardam a
        propria copia dela para a sugestao ao digitar. A foto envelhece: o
        cliente cadastrado no DumTech Clientes agora nao aparecia aqui ate o
        aplicativo ser fechado e aberto de novo. Ler de novo custa um SELECT
        de nomes, e so quando alguma coisa realmente mudou.

        Aplicativo que nao guarda `clientes` (o proprio DumTech Clientes, que
        fala direto com a agenda) passa direto.
        """
        contatos = self.context.contacts
        atuais = getattr(self, "clientes", None)
        if contatos is None or not isinstance(atuais, list):
            return
        try:
            nomes = contatos.nomes()
        except Exception:  # noqa: BLE001 - agenda indisponivel nao trava a tela
            return
        if nomes == atuais:
            return
        self.clientes = nomes
        for indice in range(self.stack.count()):
            tela = self._tela(indice)
            if isinstance(getattr(tela, "clientes", None), list):
                tela.clientes = nomes

    def _on_view_changed(self, indice: int) -> None:
        self._refresh_view(self._tela(indice))
        # a animacao vai no embrulho da rolagem, nao na tela: efeito grafico
        # dentro de uma area de rolagem briga com a barra
        tela = self.stack.widget(indice)
        # a tela entra pelo lado do segmento escolhido: Produtos, a direita do
        # Painel, chega da direita
        anterior = getattr(self, "_tela_anterior", indice)
        self._tela_anterior = indice
        motion.surgir(tela, (indice > anterior) - (indice < anterior))

    @staticmethod
    def _refresh_view(tela: QWidget | None) -> None:
        atualizar = getattr(tela, "refresh", None)
        if callable(atualizar):
            atualizar()

    # --------------------------------------------------------------------- tema
    #
    # Dentro do Hub o aplicativo segue o tema da plataforma: a janela e uma so,
    # e um painel claro dentro de uma Hub escura fica quebrado. A preferencia
    # por aplicativo continua valendo no modo avulso (sem pai).

    @property
    def theme_mode(self) -> str:
        return self._theme_mode

    @property
    def embedded(self) -> bool:
        return not self.isWindow()

    def set_embedded(self, host: QWidget) -> None:
        """Entrega a casca para quem hospeda (o Workspace do Hub).

        A casca nasce sem pai - ou seja, como janela - e por isso ja aplicou o
        proprio tema em si mesma. Embutida, quem manda no tema passa a ser a
        janela do Hub, entao ela precisa largar a folha de estilo E o carimbo
        de paleta que trouxe: um carimbo velho aqui faz `palette_for` parar
        nele e os dialogos abrirem no tema errado.

        E precisa avisar os filhos. Largar a folha resolve quem se pinta por
        folha de estilo, mas nao quem se pinta a mao: a grade da Agenda, os
        cartoes da bancada, os graficos - todos guardaram a paleta que a casca
        tinha ao nascer. Com um tema proprio gravado no aplicativo, isso abria
        a Agenda escura dentro de um Hub claro, e so a proxima troca de tema
        corrigia.
        """
        self.setStyleSheet("")
        if hasattr(self, "_dt_palette"):
            del self._dt_palette
        self.setParent(host)
        refresh_theme(self, palette_for(host))

    def resolved_palette(self) -> Palette:
        """Tema que esta casca deve usar agora."""
        if not self.embedded and self._theme_mode in (MODO_CLARO, MODO_ESCURO):
            return palette_by_name(self._theme_mode)
        if self.theme_manager is not None:
            return self.theme_manager.palette
        return current_palette()

    def _apply_theme_mode(self, mode: str, salvar: bool = True) -> None:
        self._theme_mode = mode if mode in ROTULOS_TEMA else MODO_AUTO
        if salvar:
            self.prefs.set("theme", self._theme_mode)
        if self.embedded:
            return  # quem hospeda manda no tema
        apply_window_theme(self, self.resolved_palette())
        self.refresh_all()

    def _on_hub_theme_changed(self, _palette: Palette) -> None:
        if not self.embedded and self._theme_mode == MODO_AUTO:
            self._apply_theme_mode(MODO_AUTO, salvar=False)

    # ------------------------------------------------------------------ eventos
    def closeEvent(self, event) -> None:  # noqa: N802
        self.teardown()
        super().closeEvent(event)


#: Nome historico: os aplicativos escrevem `class VendasWindow(AppWindow)`.
AppWindow = AppSurface
