"""Abertura dos aplicativos a partir do Hub.

O Hub nao sabe o que existe dentro de um aplicativo: ele apenas pede ao modulo
que crie a casca e cuida do resto (reaproveitar o que ja esta carregado,
registrar o uso e desmontar o que a licenca bloqueou). Quem coloca a casca na
tela e o Workspace.
"""

from __future__ import annotations

import logging

from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from ..core.app_module import AppContext
from ..core.config import AppPreferences, Settings
from ..core.hub_store import HubStore
from ..core.registry import AppRegistry
from ..ui import icons

logger = logging.getLogger(__name__)


def _avisar(parent: QWidget | None, titulo: str, mensagem: str) -> None:
    QMessageBox.warning(parent, titulo, mensagem)


class AppLauncher(QObject):
    """Controla as janelas dos aplicativos abertos."""

    app_opened = Signal(str)
    app_closed = Signal(str)

    def __init__(
        self,
        registry: AppRegistry,
        hub_store: HubStore,
        parent: QObject | None = None,
        settings: Settings | None = None,
        theme=None,
        contacts=None,
    ) -> None:
        super().__init__(parent)
        self.registry = registry
        self.hub_store = hub_store
        self.settings = settings
        self.theme = theme
        self.contacts = contacts
        self._catalog = None
        self._pontes: dict = {}
        self._open: dict[str, QWidget] = {}
        #: Cascas montadas de antemao, nos intervalos ociosos (`preparar`). Nao
        #: contam como abertas: nao ganham o ponto na aba nem entram no "mais
        #: usados" ate a pessoa abrir de verdade.
        self._preparados: dict = {}
        #: Como avisar o usuario. Pode ser trocado (testes, modo silencioso).
        self.notify: Callable[[QWidget | None, str, str], None] = _avisar

    # ------------------------------------------------------------------ abrir
    def open(self, app_id: str, parent_window: QWidget | None = None):
        """Devolve a casca do aplicativo pronta para ser montada, ou None."""
        entry = self.registry.get(app_id)
        if entry is None:
            self._error(parent_window, "Aplicativo não encontrado", app_id)
            return None

        if not self.registry.license_service.allows(app_id):
            self._error(
                parent_window,
                "Aplicativo bloqueado",
                f"{entry.manifest.name} não está liberado na licença deste computador.",
            )
            return None

        existing = self._open.get(app_id)
        if existing is not None:
            return existing

        # ja montado de antemao: abrir e so passar para a lista dos abertos
        surface = self._preparados.pop(app_id, None)
        if surface is None:
            try:
                surface = entry.create_window(self.build_context(entry.manifest))
            except Exception as exc:  # o Hub continua vivo mesmo se o app falhar
                logger.exception("Falha ao abrir o aplicativo %s", app_id)
                self._error(parent_window, "Não foi possível abrir o aplicativo", str(exc))
                return None
            surface.setWindowIcon(icons.icon(entry.manifest.icon, entry.manifest.accent, 64))
        self._open[app_id] = surface

        self.hub_store.register_open(app_id)
        self.app_opened.emit(app_id)
        return surface

    def preparar(self, app_id: str):
        """Monta a casca antes de a pessoa pedir - sem contar como aberta.

        Montar um aplicativo custa ~150-250 ms (as telas dele, o banco). Feito
        num intervalo ocioso, o primeiro clique no aplicativo so mostra o que
        ja existe. Falhar aqui e silencioso: o clique de verdade tenta de novo
        e ai sim avisa.
        """
        if app_id in self._open or app_id in self._preparados:
            return None
        entry = self.registry.get(app_id)
        if entry is None or not self.registry.license_service.allows(app_id):
            return None
        try:
            surface = entry.create_window(self.build_context(entry.manifest))
        except Exception:  # noqa: BLE001 - preparar nunca derruba nada
            logger.exception("Falha ao preparar o aplicativo %s", app_id)
            return None
        surface.setWindowIcon(icons.icon(entry.manifest.icon, entry.manifest.accent, 64))
        self._preparados[app_id] = surface
        return surface

    @property
    def preparados(self) -> tuple[str, ...]:
        return tuple(self._preparados)

    def descartar_preparado(self, app_id: str) -> bool:
        """Solta uma casca preparada que ninguem abriu (fecha o banco dela)."""
        surface = self._preparados.pop(app_id, None)
        if surface is None:
            return False
        surface.teardown()
        surface.setParent(None)
        surface.deleteLater()
        return True

    def build_context(self, manifest) -> AppContext:
        """Monta os recursos que o aplicativo recebe do Hub."""
        prefs = AppPreferences(self.settings, manifest.app_id) if self.settings else None
        return AppContext(
            manifest=manifest,
            prefs=prefs,
            theme=self.theme,
            contacts=self.contacts,
            catalog=self.catalog(manifest.app_id),
            contas=self.contas(manifest.app_id),
            destinos=self.destinos(manifest.app_id),
            empresa=self.empresa(),
            mensagens=self.mensageiro(),
        )

    def empresa(self):
        """Dados da empresa, lidos na hora: eles mudam na tela de configuracoes."""
        from ..core.empresa import Empresa

        return Empresa.carregar(self.settings) if self.settings else Empresa()

    def mensageiro(self):
        """Modelos de mensagem, lidos na hora - eles mudam nas configuracoes."""
        from ..core.mensagens import Mensageiro

        return Mensageiro(self.settings, self.empresa())

    def atualizar_empresa(self) -> None:
        """O cliente mexeu nos dados: quem ja esta aberto precisa saber."""
        nova = self.empresa()
        mensageiro = self.mensageiro()
        for surface in [*self._open.values(), *self._preparados.values()]:
            surface.atualizar_empresa(nova, mensageiro)

    def catalog(self, para_app: str = ""):
        """Catalogo de produtos da plataforma, ou None.

        So existe quando a licenca libera o Estoque - e o Estoque nao recebe o
        proprio catalogo de volta. Aberto na primeira vez que alguem pede: quem
        nao vende produto nunca encosta no arquivo.
        """
        if para_app == "estoque" or not self.registry.license_service.allows("estoque"):
            return None
        if self._catalog is None:
            try:
                from ..apps.estoque.catalog import abrir_catalogo
                from ..core.paths import get_paths

                self._catalog = abrir_catalogo(get_paths().app_db("estoque"))
            except Exception:  # noqa: BLE001 - sem catalogo o app funciona igual
                logger.exception("Nao foi possivel abrir o catalogo do Estoque")
                return None
        return self._catalog

    def contas(self, para_app: str = ""):
        """O Financeiro como destino de contas a receber, ou None.

        Mesmo desenho do catalogo: so existe quando a licenca libera o
        Financeiro, e o proprio Financeiro nao recebe a ponte de volta.
        """
        if para_app == "financeiro":
            return None
        return self._ponte(
            "financeiro", "dumtech.apps.financeiro.contas", "abrir_contas"
        )

    def destinos(self, para_app: str = "") -> list:
        """Para onde uma proposta aprovada pode virar trabalho.

        Lista vazia quando o cliente nao tem Vendas nem Ordens - e ai o botao
        simplesmente nao aparece no Orcamentos.
        """
        if para_app != "orcamentos":
            return []
        encontrados = []
        for app_id, modulo in (("vendas", "dumtech.apps.vendas.pedidos"),
                               ("ordens", "dumtech.apps.ordens.pedidos")):
            ponte = self._ponte(app_id, modulo, "abrir_destino")
            if ponte is not None:
                encontrados.append(ponte)
        return encontrados

    def _ponte(self, app_id: str, modulo: str, funcao: str):
        """Abre (uma vez) a porta que outro aplicativo publicou.

        Ponte que nao abre nao pode impedir o aplicativo de funcionar: o
        chamador recebe None e segue sem ela, como sempre seguiu.
        """
        if not self.registry.license_service.allows(app_id):
            return None
        if app_id not in self._pontes:
            try:
                from importlib import import_module

                from ..core.paths import get_paths

                abrir = getattr(import_module(modulo), funcao)
                self._pontes[app_id] = abrir(get_paths().app_db(app_id))
            except Exception:  # noqa: BLE001 - sem ponte o app funciona igual
                logger.exception("Nao foi possivel abrir a ponte com %s", app_id)
                self._pontes[app_id] = None
        return self._pontes[app_id]

    def close_pontes(self) -> None:
        for ponte in self._pontes.values():
            if ponte is not None:
                ponte.close()
        self._pontes.clear()

    def close_catalog(self) -> None:
        if self._catalog is not None:
            self._catalog.close()
            self._catalog = None

    def close_blocked(self) -> None:
        """Descarrega aplicativos que a licenca nao libera mais."""
        for app_id in list(self._open):
            if not self.registry.license_service.allows(app_id):
                self.close(app_id)
        for app_id in list(self._preparados):
            if not self.registry.license_service.allows(app_id):
                self.descartar_preparado(app_id)

    # ----------------------------------------------------------------- fechar
    def close(self, app_id: str) -> bool:
        """Encerra um aplicativo: fecha banco, solta a casca, avisa o Hub."""
        surface = self._open.pop(app_id, None)
        if surface is None:
            return False
        surface.teardown()
        surface.setParent(None)
        surface.deleteLater()
        self.app_closed.emit(app_id)
        return True

    def close_all(self) -> None:
        for app_id in list(self._open):
            self.close(app_id)
        # os preparados tambem seguram o banco aberto: restaurar um backup
        # precisa deles fechados tanto quanto dos abertos
        for app_id in list(self._preparados):
            self.descartar_preparado(app_id)
        self.close_catalog()
        self.close_pontes()

    def get(self, app_id: str):
        return self._open.get(app_id)

    @property
    def open_apps(self) -> tuple[str, ...]:
        return tuple(self._open)

    def _error(self, parent: QWidget | None, title: str, message: str) -> None:
        logger.warning("%s: %s", title, message)
        self.notify(parent, title, message)
