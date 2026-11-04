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

from ..core import eventos
from ..core.app_module import AppContext
from ..core.database import Database
from ..core.config import AppPreferences, Settings
from ..core.hub_store import HubStore
from ..core.registry import AppRegistry
from ..ui import icons

logger = logging.getLogger(__name__)

#: quem responde a busca geral e a ficha do cliente (`core/consulta.py`)
COM_CONSULTA = ("vendas", "ordens", "orcamentos", "agenda", "financeiro", "estoque")


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
        #: o servidor com as credenciais da licenca, para quem tem parte online
        #: (o Hub entrega; trocado nos testes e nos videos)
        self.servidor = None
        #: abertos so para consulta: a licenca nao os libera, os dados sao do cliente
        self._consulta: set[str] = set()

    # ---------------------------------------------------------------- consulta
    def _banco_de(self, app_id: str):
        from ..core.paths import get_paths

        paths = get_paths()
        return paths.platform_db if app_id == "clientes" else paths.app_db(app_id)

    def consultavel(self, app_id: str) -> bool:
        """Saiu da licenca, mas tem dados aqui: da para abrir so para ver.

        So libera o que o proprio cliente gravou: sem arquivo nao ha nada a
        mostrar, e quem nunca usou o modulo continua vendo a tela de compra.
        """
        if self.registry.license_service.allows(app_id):
            return False
        return self.registry.get(app_id) is not None and self._banco_de(app_id).exists()

    def consultaveis(self) -> list:
        return [e for e in self.registry.locked() if self.consultavel(e.app_id) and self._pessoa_ve(e.app_id)]

    def _pessoa_ve(self, app_id: str) -> bool:
        """A conta de quem esta aqui permite? As pontes nao perguntam isto: quem so
        tem Vendas continua baixando estoque, mesmo sem ver a tela do Estoque."""
        acesso = self.registry.acesso
        return acesso is None or acesso.permite_modulo(app_id)

    def em_consulta(self, app_id: str) -> bool:
        return app_id in self._consulta

    def _motivo_mensal(self) -> str:
        """O texto da mensalidade, quando e ela que deixa o modulo so para consulta."""
        from ..core import mensalidade

        licenca = getattr(self.registry.license_service, "current", None)
        return (mensalidade.texto_consulta(licenca) or "") if licenca is not None else ""

    def _travar(self, app_id: str) -> None:
        Database.so_leitura.add(self._banco_de(app_id))
        self._consulta.add(app_id)
        Database.aviso_consulta = self._motivo_mensal()
        # a agenda de clientes e uma conexao so, aberta desde a abertura do Hub
        if app_id == "clientes" and self.contacts is not None:
            self.contacts.db.connection.execute("PRAGMA query_only = ON")

    def _destravar(self, app_id: str) -> None:
        Database.so_leitura.discard(self._banco_de(app_id))
        self._consulta.discard(app_id)
        if not self._consulta:
            Database.aviso_consulta = ""
        if app_id == "clientes" and self.contacts is not None:
            self.contacts.db.connection.execute("PRAGMA query_only = OFF")

    # ------------------------------------------------------------------ abrir
    def open(self, app_id: str, parent_window: QWidget | None = None):
        """Devolve a casca do aplicativo pronta para ser montada, ou None."""
        entry = self.registry.get(app_id)
        if entry is None:
            self._error(parent_window, "Aplicativo não encontrado", app_id)
            return None
        if not self._pessoa_ve(app_id):
            self._error(parent_window, "Aplicativo bloqueado",
                        f"A sua conta não tem acesso a {entry.manifest.name}.")
            return None

        consulta = self.consultavel(app_id)
        if not consulta and not self.registry.license_service.allows(app_id):
            self._error(
                parent_window,
                "Aplicativo bloqueado",
                f"{entry.manifest.name} não está liberado na licença deste computador.",
            )
            return None

        existing = self._open.get(app_id)
        if existing is not None:
            return existing
        if consulta:
            self._travar(app_id)

        # ja montado de antemao: abrir e so passar para a lista dos abertos
        surface = self._preparados.pop(app_id, None)
        if surface is None:
            try:
                surface = entry.create_window(self.build_context(entry.manifest, consulta))
            except Exception as exc:  # o Hub continua vivo mesmo se o app falhar
                if consulta:
                    self._destravar(app_id)
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
        if entry is None or not self.registry.license_service.allows(app_id) or not self._pessoa_ve(app_id):
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

    def build_context(self, manifest, consulta: bool = False) -> AppContext:
        """Monta os recursos que o aplicativo recebe do Hub.

        Em modo consulta nao ha ponte: o modulo fora da licenca so olha o que e
        dele, e nao escreve no dos outros.
        """
        prefs = AppPreferences(self.settings, manifest.app_id) if self.settings else None
        if consulta:
            from ..core.paths import get_paths

            return AppContext(
                manifest=manifest, paths=get_paths(), prefs=prefs, theme=self.theme,
                contacts=self.contacts,
                empresa=self.empresa(), mensagens=self.mensageiro(), so_consulta=True,
                texto_consulta=self._motivo_mensal(),
            )
        return AppContext(
            manifest=manifest,
            prefs=prefs,
            theme=self.theme,
            contacts=self.contacts,
            catalog=self.catalog(manifest.app_id),
            contas=self.contas(manifest.app_id),
            destinos=self.destinos(manifest.app_id),
            consultas=self.consultas() if manifest.app_id == "clientes" else [],
            origens=self.origens(manifest.app_id),
            gaveta=self.gaveta(manifest.app_id),
            empresa=self.empresa(),
            mensagens=self.mensageiro(),
            servidor=self.servidor,
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
        if para_app not in ("orcamentos", "agenda"):
            return []
        encontrados = []
        vendas = self._ponte_vendas()
        if vendas is not None:
            encontrados.append(vendas)
        ordens = self._ponte("ordens", "dumtech.apps.ordens.pedidos", "abrir_destino")
        if ordens is not None:
            ordens.contas = self.contas("ordens")
            encontrados.append(ordens)
        return encontrados

    def consultas(self) -> list:
        """O que cada modulo liberado sabe responder. Sem licenca, nao entra."""
        encontrados = []
        for app_id in COM_CONSULTA:
            ponte = self._ponte(app_id, f"dumtech.apps.{app_id}.consulta", "abrir_consulta",
                                chave=f"consulta:{app_id}")
            if ponte is not None:
                encontrados.append(ponte)
        return encontrados

    def buscar(self, termo: str, limite: int = 5) -> list:
        """A busca geral: um modulo com defeito nao apaga o resultado dos outros."""
        achados = []
        for consulta in self.consultas():
            try:
                achados += consulta.buscar(termo, limite)
            except Exception:  # noqa: BLE001
                logger.exception("A busca falhou em %s", consulta.app_id)
        return achados

    def renomear_cliente(self, antigo: str, novo: str) -> None:
        """O cliente mudou de nome: o historico dele vai junto."""
        for consulta in self.consultas():
            try:
                if consulta.renomear_cliente(antigo, novo):
                    eventos.avisar(consulta.app_id)
            except Exception:  # noqa: BLE001 - o cadastro ja foi salvo
                logger.exception("Nao renomeei o cliente em %s", consulta.app_id)

    def origens(self, para_app: str = "") -> list:
        """Quem precisa saber o que acontece com as contas no Financeiro."""
        if para_app != "financeiro":
            return []
        vendas = self._ponte_vendas()
        return [vendas] if vendas is not None else []

    def gaveta(self, para_app: str = ""):
        """O caixa do dia, para quem recebe em especie fora do balcao."""
        if para_app not in ("financeiro", "ordens"):
            return None
        return self._ponte_vendas()

    def _ponte_vendas(self):
        """A mesma ponte serve de destino, origem e gaveta: e um banco so.

        Catalogo e contas sao religados a cada pedido, porque a licenca pode ter
        mudado depois de a ponte abrir. Sem o catalogo, a venda recebida pelo
        Financeiro fecharia sem tirar nada do estoque.
        """
        ponte = self._ponte("vendas", "dumtech.apps.vendas.pedidos", "abrir_destino")
        if ponte is not None:
            ponte.repository.catalogo = self.catalog("vendas")
            ponte.contas = self.contas("vendas")
        return ponte

    def desatualizados(self) -> list[str]:
        """Montados com uma ponte que a licenca acabou de ligar ou desligar.

        A casca recebe as pontes (catalogo, contas, destinos) quando nasce. Se
        o Estoque entra na licenca depois - compra, teste gratis -, o Vendas
        que ja estava montado continuava sem catalogo ate o Hub reiniciar: o
        produto do Estoque nao aparecia na venda. O inverso tambem conta: um
        modulo que saiu da licenca nao pode continuar sendo usado por ponte.
        """
        velhos = []
        for app_id, surface in [*self._open.items(), *self._preparados.items()]:
            if app_id in self._consulta:
                continue
            antes = surface.context
            if ((antes.catalog is None) != (self.catalog(app_id) is None)
                    or (antes.contas is None) != (self.contas(app_id) is None)
                    or len(antes.destinos) != len(self.destinos(app_id))
                    or len(antes.origens) != len(self.origens(app_id))
                    or (app_id == "clientes" and len(antes.consultas) != len(self.consultas()))
                    or (antes.gaveta is None) != (self.gaveta(app_id) is None)):
                velhos.append(app_id)
        return velhos

    def _ponte(self, app_id: str, modulo: str, funcao: str, chave: str = ""):
        """Abre (uma vez) a porta que outro aplicativo publicou.

        Ponte que nao abre nao pode impedir o aplicativo de funcionar: o
        chamador recebe None e segue sem ela, como sempre seguiu. `chave` separa
        duas portas do mesmo aplicativo.
        """
        if not self.registry.license_service.allows(app_id):
            return None
        chave = chave or app_id
        if chave not in self._pontes:
            try:
                from importlib import import_module

                from ..core.paths import get_paths

                abrir = getattr(import_module(modulo), funcao)
                self._pontes[chave] = abrir(get_paths().app_db(app_id))
            except Exception:  # noqa: BLE001 - sem ponte o app funciona igual
                logger.exception("Nao foi possivel abrir a ponte com %s", app_id)
                self._pontes[chave] = None
        return self._pontes[chave]

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
            liberado = self.registry.license_service.allows(app_id)
            # consulta fica aberta; se a licenca voltou, fecha e reabre para gravar
            if liberado == (app_id in self._consulta):
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
        if app_id in self._consulta:
            self._destravar(app_id)
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
