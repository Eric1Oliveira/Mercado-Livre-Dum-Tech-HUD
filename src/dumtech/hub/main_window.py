"""Janela unica do DumTech Hub.

Tudo acontece aqui dentro. A barra do topo e a navegacao da plataforma - as
abas do Inicio e de cada aplicativo, a busca, o tema e o menu da empresa (com
Licenca, Configuracoes e Sobre) - e a area de baixo mostra ou uma tela do Hub
ou um aplicativo montado no Workspace. Nenhum aplicativo abre janela propria.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core import celular as nucleo_celular
from ..core import online as nucleo_online
from ..core import confirmacoes, eventos
from ..core.acesso import AcessoService
from ..core.avisos import Config as AvisosConfig
from ..core import comunicados as comunicados_core
from ..core import novidades as novidades_core
from ..core.comunicados import ComunicadosService
from ..core.config import Settings
from ..core.conta import Conta, ContaService
from ..core.contacts import APP_ID as AGENDA
from ..core.contacts import ContactsStore
from ..core.hub_store import HubStore
from ..core.licensing import LicenseService, modo_local_ligado
from ..core.pagamentos import PagamentosService
from ..core.loja import URL_PADRAO, LojaService, e_da_loja, url_compra
from ..core.uso import UsoService
from ..core import atualizacao as nucleo_atualizacao
from ..core.atualizacao import AtualizacaoService
from ..core.versao import dispensar as dispensar_versao
from ..core import backup
from ..core.paths import get_paths
from ..core.registry import AppRegistry
from ..ui import chrome, icons, motion, tasks
from ..ui import format as fmt
from ..ui.theme import (
    Palette,
    Space,
    ThemeManager,
    current_palette,
    qt_palette,
    refresh_theme,
    stylesheet_for,
)
from ..ui.widgets.command_palette import Command, CommandPalette
from ..ui.widgets.common import IconBadge, label, menu_arredondado
from ..ui.widgets.aviso_flutuante import AvisoFlutuante
from .views.forcada_aviso import ForcadaAviso
from ..ui.widgets.confirmar import confirmar
from ..ui.widgets.indicador import TRACO, Indicador
from ..ui.widgets.pilha import Pilha
from ..ui.widgets.topbar import ALTURA as ALTURA_TOPO
from ..ui.widgets.topbar import (
    BotaoAtualizar,
    BotaoTema,
    NavTab,
    ProfileButton,
    SearchPill,
    TabStrip,
)
from .launcher import AppLauncher
from .views.about_view import AboutView
from .views.anuncio_dialog import AnuncioDialog
from .views.atualizacao_dialog import AtualizacaoDialog
from .views.avisos_view import AvisosView
from .views.backup_view import BackupView
from .views.assistente_conta_view import AssistenteContaView
from .views.celular_dialog import CelularDialog
from .views.boas_vindas_view import BoasVindasView
from .views.config_view import ConfigView
from .views.empresa_view import EmpresaView
from .views.home_view import HomeView
from .views.login_view import LoginView
from .views.mensagens_view import MensagensView
from .views.minha_conta_dialog import MinhaContaDialog
from .views.novidades_dialog import NovidadesDialog
from .views.pagamentos_view import PagamentosView
from .views.license_view import LicenseView
from .views.usuarios_view import ConfirmarSenhaDialog, UsuariosView
from .workspace import Workspace

logger = logging.getLogger(__name__)

#: onde o cliente baixa a versao nova, quando o servidor nao disser outro lugar
PAGINA_DOWNLOAD = f"{URL_PADRAO}/baixar/"

#: O menor tamanho em que o Hub continua utilizavel. Pensado para o pior caso
#: real de loja: notebook de 1366x768 com a escala do Windows em 125%, que
#: deixa pouco mais de 1090x610 de area util. Abaixo disso as telas rolam.
LARGURA_MINIMA = 900
#: por mais abas que a licenca libere, a janela nao trava acima disto: e
#: melhor a ultima aba encostar na busca do que o cliente nao conseguir
#: encaixar o Hub ao lado de outra janela
LARGURA_MINIMA_TETO = 1180
ALTURA_MINIMA = 520
#: a marca sem o nome: so o simbolo quadrado
MARCA_CURTA = 34
#: o respiro entre o simbolo e o nome "DumTech Hub"
ESPACO_MARCA = 10
#: a moldura que o Windows desenha em volta (titulo e bordas) nao entra no
#: tamanho que pedimos, mas ocupa a tela - entao fica reservada
MOLDURA_LARGURA = 16
MOLDURA_ALTURA = 48

PAGINA_INICIO = 0
PAGINA_LICENCA = 1
PAGINA_CONFIG = 2
PAGINA_SOBRE = 3
PAGINA_APP = 4
#: primeiro acesso: so existe enquanto o cliente ainda nao se apresentou
PAGINA_BOAS_VINDAS = 5
#: a porta de quem tem conta, e o assistente de quem ainda vai criar
PAGINA_LOGIN = 6
PAGINA_ASSISTENTE = 7
#: telas de dono: funcionario nao chega nelas por caminho nenhum
PAGINAS_DE_DONO = (PAGINA_LICENCA, PAGINA_CONFIG)
#: aqui ainda nao ha ninguem no Hub: sem barra do topo, sem atalho, sem paleta
PAGINAS_DA_PORTA = (PAGINA_LOGIN, PAGINA_ASSISTENTE)

#: botao so de icone da barra (tema)
LADO_BOTAO = BotaoTema.LADO


class HubWindow(QMainWindow):
    """Central da plataforma: barra de navegacao + area de trabalho."""

    def __init__(
        self,
        settings: Settings | None = None,
        license_service: LicenseService | None = None,
        registry: AppRegistry | None = None,
        hub_store: HubStore | None = None,
        theme: ThemeManager | None = None,
        contacts: ContactsStore | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings or Settings()
        self.license_service = license_service or LicenseService()
        self.registry = registry or AppRegistry(self.license_service)
        self.acesso = AcessoService(self.license_service)
        self.acesso.nova_abertura()
        self.acesso.abrir_lembrado()
        self.registry.usar_acesso(self.acesso)
        #: a chave desta abertura: mudou, as contas sao outras
        self._chave_aberta = self.license_service.current.key
        self.hub_store = hub_store or HubStore()
        self.contacts = contacts or ContactsStore()
        self.theme_manager = theme
        confirmacoes.usar(self.settings)
        self.launcher = AppLauncher(
            self.registry,
            self.hub_store,
            self,
            settings=self.settings,
            theme=self.theme_manager,
            contacts=self.contacts,
        )

        self.setWindowTitle("DumTech Hub")
        # Um minimo alto demais nao protege nada: o Windows nao encolhe a
        # janela abaixo dele, so joga o rodape para baixo da barra de tarefas -
        # era assim que os botoes do Balcao sumiam num monitor de 1280x720.
        # Com as telas dos aplicativos dentro de area de rolagem, apertado
        # vira barra de rolagem, e este minimo pode ser o que realmente cabe.
        self.setMinimumSize(LARGURA_MINIMA, ALTURA_MINIMA)
        self._abrir_no_tamanho_certo()

        self._app_items: dict[str, NavTab] = {}
        #: ja existe uma releitura marcada para o proximo giro do laco?
        self._atualizacao_marcada = False
        #: a aba de antes, para a tela nova entrar pelo lado certo
        self._aba_anterior: NavTab | None = None
        self._direcao = 0

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_topo())
        layout.addWidget(self._build_content(), 1)
        self.setCentralWidget(central)
        #: o recado do canto: chegou agendamento pelo link, por exemplo
        self.aviso_flutuante = AvisoFlutuante(self)

        self._build_shortcuts()
        self.refresh_rail()
        primeiro_acesso = self._primeiro_acesso()
        if primeiro_acesso:
            # quem acabou de instalar nao tem "antes": nada mudou para ele
            novidades_core.marcar_vista(self.settings, __version__)
        self._go(PAGINA_BOAS_VINDAS if primeiro_acesso else self._pagina_de_entrada())

        # a partir daqui o Hub fica sabendo quando um modulo mexe no dado do
        # outro - e quem estava aberto do outro lado recarrega sozinho
        eventos.ouvir(self._dados_alterados)

        if self.theme_manager is not None:
            self.theme_manager.changed.connect(self._on_theme_changed)
            self._on_theme_changed(self.theme_manager.palette)
        if self.settings.get("window", "maximized", False):
            self.showMaximized()
        # a copia diaria nao roda mais aqui: ela atrasava a janela aparecer.
        # Vai logo depois que a janela esta na tela (`showEvent`).

    def _abrir_no_tamanho_certo(self) -> None:
        """Abre no tamanho salvo, aparado pelo monitor de agora.

        O tamanho e guardado ao fechar. Quem fecha o Hub no monitor grande da
        loja e abre no notebook levaria uma janela maior que a tela, com o
        rodape escondido atras da barra de tarefas. Entao o salvo passa antes
        pela area util do monitor atual - descontada a moldura da janela, que
        o Windows desenha por fora e tambem ocupa espaco.
        """
        largura = int(self.settings.get("window", "width", 1280))
        altura = int(self.settings.get("window", "height", 820))
        tela = self.screen() or QGuiApplication.primaryScreen()
        if tela is not None:
            util = tela.availableGeometry()
            largura = min(largura, util.width() - MOLDURA_LARGURA)
            altura = min(altura, util.height() - MOLDURA_ALTURA)
        self.resize(max(largura, self.minimumWidth()),
                    max(altura, self.minimumHeight()))

    # ------------------------------------------------------------------- topo
    def _build_topo(self) -> QFrame:
        topo = QFrame()
        self.topo = topo
        topo.setObjectName("TopBar")
        topo.setFixedHeight(ALTURA_TOPO)

        linha = QHBoxLayout(topo)
        linha.setContentsMargins(Space.xl, 0, Space.lg + 2, 0)
        linha.setSpacing(0)

        self.marca = QWidget()
        marca = QHBoxLayout(self.marca)
        marca.setContentsMargins(0, 0, 0, 0)
        marca.setSpacing(10)
        marca.addWidget(IconBadge("grid", "accent", size=34, radius=10, estilo="solid"))
        self.marca_nome = label("DumTech Hub", "brand")
        marca.addWidget(self.marca_nome)
        linha.addWidget(self.marca)
        linha.addSpacing(Space.xxl + 4)

        self.item_inicio = NavTab("Início")
        self.item_inicio.clicked.connect(lambda: self._go(PAGINA_INICIO))
        linha.addWidget(self.item_inicio)
        linha.addSpacing(2)
        self.secao_apps = TabStrip()
        linha.addWidget(self.secao_apps)
        linha.addStretch(1)

        # o botao de atualizar mora ANTES da busca: e o unico recado do topo
        # que pede acao, e some assim que o cliente atualiza
        self.botao_atualizar = BotaoAtualizar()
        self.botao_atualizar.setVisible(False)
        self.botao_atualizar.clicked.connect(self.abrir_atualizacao)
        linha.addWidget(self.botao_atualizar, 0, Qt.AlignmentFlag.AlignVCenter)
        linha.addSpacing(Space.sm + 2)

        self.item_busca = SearchPill()
        self.item_busca.setToolTip("Abre a paleta de comandos (Ctrl+K)")
        self.item_busca.clicked.connect(self.open_palette)
        linha.addWidget(self.item_busca, 0, Qt.AlignmentFlag.AlignVCenter)
        linha.addSpacing(Space.sm + 2)

        self.botao_tema = BotaoTema()
        self.botao_tema.clicked.connect(self._toggle_theme)
        linha.addWidget(self.botao_tema, 0, Qt.AlignmentFlag.AlignVCenter)
        linha.addSpacing(Space.sm + 2)

        self.perfil = ProfileButton()
        self.perfil.setToolTip("Empresa, licença e configurações")
        self.perfil.clicked.connect(self._abrir_menu_perfil)
        linha.addWidget(self.perfil, 0, Qt.AlignmentFlag.AlignVCenter)

        # o traco que anda entre as abas e a pilula que segue o mouse
        self.indicador_abas = Indicador(topo, forma=TRACO, realce=True)
        self.indicador_abas.registrar(self.item_inicio)

        self._build_menu_perfil()
        return topo

    def _build_menu_perfil(self) -> None:
        """O menu da empresa: o que e "da conta", e nao do dia a dia."""
        self.menu_perfil = menu_arredondado(self)
        self._icones_menu: list[tuple] = []

        def acao(texto: str, icone: str, gatilho, marcavel: bool = False):
            item = self.menu_perfil.addAction(texto)
            item.setCheckable(marcavel)
            item.triggered.connect(lambda _=False: gatilho())
            self._icones_menu.append((item, icone))
            return item

        # versao nova: o primeiro item do menu, so enquanto ela existir
        self.item_atualizar = acao("Atualizar o Hub", "refresh", self.abrir_atualizacao)
        self.separador_atualizar = self.menu_perfil.addSeparator()
        self.item_atualizar.setVisible(False)
        self.separador_atualizar.setVisible(False)
        self.item_minha_conta = acao("Minha conta", "user", self.abrir_minha_conta)
        self.item_empresa = acao("Minha empresa", "home", lambda: self._ir_para_config(self.empresa_view))
        self.item_licenca = acao("Licença", "key", lambda: self._go(PAGINA_LICENCA), True)
        self.item_config = acao("Configurações", "wrench",
                                lambda: self._go(PAGINA_CONFIG), True)
        self.item_usuarios = acao("Usuários e acessos", "users",
                                  lambda: self._ir_para_config(self.usuarios_view))
        self.item_backup = acao("Backup", "shield", lambda: self._ir_para_config(self.backup_view))
        self.item_celular = acao("Ver no celular", "phone", self.abrir_celular)
        self.item_sobre = acao("Sobre", "info", lambda: self._go(PAGINA_SOBRE), True)
        self.separador_conta = self.menu_perfil.addSeparator()
        self.item_trocar = acao("Trocar de usuário", "users", self.trocar_de_usuario)
        self.item_sair = acao("Sair", "logout", self.sair_da_conta)
        self.menu_perfil.addSeparator()
        self.acao_tema = acao("Tema claro", "sun", self._toggle_theme)
        self.menu_perfil.addSeparator()
        self.rotulo_versao = self.menu_perfil.addAction(f"DumTech Hub  ·  versão {__version__}")
        self.rotulo_versao.setEnabled(False)

    def _ajustar_menu(self) -> None:
        """O menu de quem esta aqui: funcionario ve so o que e dele."""
        dono = self.acesso.e_adm
        for item in (self.item_empresa, self.item_licenca, self.item_config, self.item_usuarios,
                     self.item_backup, self.item_celular):
            item.setVisible(dono)
        logado = self.acesso.usuario is not None
        for item in (self.item_minha_conta, self.item_trocar, self.item_sair, self.separador_conta):
            item.setVisible(logado)

    def _abrir_menu_perfil(self) -> None:
        self._ajustar_menu()
        self._vestir(self.menu_perfil)
        largura = self.menu_perfil.sizeHint().width()
        canto = self.perfil.mapToGlobal(
            QPoint(self.perfil.width() - largura, self.perfil.height() + 8)
        )
        self.menu_perfil.popup(canto)

    def _pintar_menu(self, palette: Palette) -> None:
        for item, icone in self._icones_menu:
            if item is self.acao_tema:
                icone = "sun" if palette.is_dark else "moon"
            item.setIcon(icons.icon(icone, palette.text_muted, 16))

    def _atualizar_perfil(self) -> None:
        """O canto da barra mostra a empresa - e o que a licenca liberou."""
        empresa = self.launcher.empresa()
        preenchida = empresa is not None and empresa.preenchida
        total = len(self.registry.visiveis())
        sub = (fmt.contagem(total, "sistema ativo", "sistemas ativos")
               if total else "Ative a sua licença")
        usuario = self.acesso.usuario
        if usuario is not None:
            sub = usuario.nome
        logo = None
        if preenchida:
            caminho = empresa.caminho_logo(get_paths())
            if caminho is not None:
                logo = QPixmap(str(caminho))
        self.perfil.set_empresa(empresa.nome if preenchida else "Sua empresa", sub, logo)
        self._ajustar_topo()

    def largura_do_topo(self, marca_inteira=True, busca_larga=True,
                        perfil_largo=True) -> int:
        """Quantos pixels a barra do topo precisa nessa combinacao.

        Serve para dois trabalhos: escolher o que encolher quando a janela
        aperta e saber o minimo real da janela (`_minimo_que_cabe`), que e o
        ponto em que nem encolhendo tudo as abas caberiam inteiras.
        """
        abas = self.item_inicio.sizeHint().width()
        if not self.secao_apps.isHidden():
            abas += self.secao_apps.sizeHint().width()
        # medido pelo rotulo, e nao pelo bloco da marca: escondido o nome, o
        # bloco ja encolheu, e perguntar a ele daria 34 sempre - a barra ficava
        # escondendo e mostrando o nome a cada pixel de arrasto
        marca = MARCA_CURTA
        if marca_inteira:
            marca += ESPACO_MARCA + self.marca_nome.sizeHint().width()
        busca = SearchPill.LARGURA if busca_larga else SearchPill.ALTURA
        return (Space.xl + Space.lg + 2 + marca + Space.xxl + 4 + abas + 2
                + (Space.sm + 2) * 2 + LADO_BOTAO + Space.xxl
                + busca + self.perfil.largura(not perfil_largo))

    #: o que a barra abre mao, na ordem: primeiro o nome da empresa (o avatar
    #: fica), depois a busca (que continua no Ctrl+K e na lupa) e por ultimo o
    #: nome "DumTech Hub" (o simbolo fica). As abas nunca encolhem - elas sao
    #: a navegacao, e meia palavra cortada no topo e o que mais parece defeito.
    DEGRAUS_DO_TOPO = (
        (True, True, True),     # tudo inteiro
        (True, True, False),    # empresa so no avatar
        (True, False, False),   # busca vira lupa
        (False, False, False),  # marca so no simbolo
    )

    def _ajustar_topo(self) -> None:
        """Janela estreita: encolhe o topo na ordem certa, abas por ultimo."""
        if not hasattr(self, "perfil"):
            return
        largura = self.width()
        escolha = self.DEGRAUS_DO_TOPO[-1]
        for degrau in self.DEGRAUS_DO_TOPO:
            if self.largura_do_topo(*degrau) <= largura:
                escolha = degrau
                break
        marca_inteira, busca_larga, perfil_largo = escolha
        self.marca_nome.setVisible(marca_inteira)
        self.item_busca.set_compacto(not busca_larga)
        self.perfil.set_compacto(not perfil_largo)

    def _minimo_que_cabe(self) -> None:
        """Ajusta o minimo da janela ao que a barra do topo realmente pede.

        O numero muda com a licenca: quem tem os sete aplicativos tem mais
        abas no topo do que quem tem dois, e travar a janela num minimo maior
        do que o necessario e tirar espaco de quem nao precisa dele.
        """
        preciso = self.largura_do_topo(*self.DEGRAUS_DO_TOPO[-1])
        self.setMinimumWidth(max(LARGURA_MINIMA, min(preciso, LARGURA_MINIMA_TETO)))

    def refresh_rail(self) -> None:
        """Redesenha as abas dos aplicativos (a licenca pode ter mudado)."""
        for item in self._app_items.values():
            self.indicador_abas.remover(item)
            if self._aba_anterior is item:
                # a aba vai embora: guardar a referencia faria a proxima conta
                # de direcao medir um widget que ja nao e desta janela
                self._aba_anterior = None
        self.secao_apps.clear()
        self._app_items.clear()

        disponiveis = self.registry.visiveis()
        for entrada in self._por_uso(disponiveis):
            manifest = entrada.manifest
            item = NavTab(manifest.short_name, accent=manifest.accent, closable=True)
            item.setToolTip(manifest.name)
            item.clicked.connect(lambda _=False, i=manifest.app_id: self.open_app(i))
            item.close_requested.connect(lambda i=manifest.app_id: self.close_app(i))
            self.secao_apps.add(item)
            self.indicador_abas.registrar(item)
            self._app_items[manifest.app_id] = item

        self.secao_apps.set_empty(not disponiveis)
        self._sync_rail_state()
        self._minimo_que_cabe()
        self._atualizar_perfil()

    def _por_uso(self, entradas):
        """Mais usados primeiro; empate resolvido pelo nome."""
        uso = self.hub_store.usage()
        return sorted(
            entradas,
            key=lambda e: (-uso.get(e.app_id, 0), e.manifest.short_name.lower()),
        )

    def _sync_rail_state(self) -> None:
        indice = self.stack.currentIndex()
        atual = self.workspace.current_app if indice == PAGINA_APP else None
        abertos = set(self.launcher.open_apps)
        for app_id, item in self._app_items.items():
            item.set_open(app_id in abertos)
            item.setChecked(app_id == atual)
        self.item_inicio.setChecked(indice == PAGINA_INICIO)
        self.item_licenca.setChecked(indice == PAGINA_LICENCA)
        self.item_config.setChecked(indice == PAGINA_CONFIG)
        self.item_sobre.setChecked(indice == PAGINA_SOBRE)
        self.perfil.set_ativo(indice in (PAGINA_LICENCA, PAGINA_CONFIG, PAGINA_SOBRE))

        aba = self.item_inicio if indice == PAGINA_INICIO else self._app_items.get(atual)
        self.indicador_abas.selecionar(aba, aba.accent if aba is not None else "text")
        self._direcao = self._direcao_da_aba(aba)

    def _direcao_da_aba(self, nova) -> int:
        """Para que lado a tela nova entra: o da aba nova em relacao a antiga.

        Ir para uma aba a direita traz a tela da direita - o conteudo anda no
        mesmo sentido que o traco. Telas fora das abas (Licenca, Configuracoes)
        so sobem, sem lado.
        """
        antiga, self._aba_anterior = self._aba_anterior, nova
        if antiga is None or nova is None or antiga is nova:
            return 0
        try:
            # `mapTo` exige que a janela seja ancestral do widget: com uma aba
            # ja solta da janela (a licenca mudou e as abas foram refeitas), o
            # Qt sobe a arvore ate o nada e derruba o programa - sem excecao.
            if not (self.isAncestorOf(antiga) and self.isAncestorOf(nova)):
                return 0
            dx = (nova.mapTo(self, QPoint(0, 0)).x()
                  - antiga.mapTo(self, QPoint(0, 0)).x())
        except RuntimeError:
            return 0  # o objeto do Qt ja foi destruido
        return (dx > 0) - (dx < 0)

    # ---------------------------------------------------------------- conteudo
    def _build_content(self) -> QStackedWidget:
        self.stack = Pilha()
        self.config_avisos = AvisosConfig(self.settings)
        # a porta de entrada do cliente: cadastro, ofertas e o caminho da loja
        self.conta_service = ContaService(self.settings)
        self.comunicados_service = ComunicadosService(get_paths())
        self.loja = LojaService()
        self.uso_service = UsoService(self.hub_store)
        self.atualizacao_service = AtualizacaoService(self.settings, __version__)
        #: atualizacao silenciosa ja baixada e conferida: (instalador, aviso)
        self._silenciosa = None
        #: a contagem da atualizacao forcada, quando ha uma correndo
        self._aviso_forcada = None
        self._baixando_em_silencio = ""
        #: o Windows esta desligando: instalar agora deixaria o programa pela metade
        self._windows_saindo = False
        app = QGuiApplication.instance()
        if app is not None:
            app.commitDataRequest.connect(self._windows_desligando)
        # sem carregar aqui: o `_go(PAGINA_INICIO)` do construtor ja carrega
        self.home_view = HomeView(self.registry, self.hub_store,
                                  paths=get_paths(),
                                  config_avisos=self.config_avisos,
                                  empresa=self.launcher.empresa,
                                  novidade=lambda: self.novidade_de_versao(),
                                  consultaveis=self.launcher.consultaveis,
                                  carregar=False)
        self.home_view.configurar_empresa.connect(lambda: self._ir_para_config(self.empresa_view))
        self.home_view.abrir_backup.connect(lambda: self._ir_para_config(self.backup_view))
        self.home_view.open_app.connect(self.open_app)
        self.home_view.ativar_licenca.connect(lambda: self._go(PAGINA_LICENCA))
        self.home_view.buscar.connect(self.open_palette)
        self.home_view.adquirir.connect(self.abrir_loja)
        self.home_view.abrir_link.connect(self.abrir_anuncio)
        self.home_view.baixar_versao.connect(self._baixar_versao)
        self.home_view.dispensar_versao.connect(self._dispensar_versao)
        self.license_view = LicenseView(self.license_service, self.registry,
                                        conta=lambda: self.conta_service.atual)
        self.license_view.licenca_alterada.connect(self._on_license_changed)
        self.license_view.adquirir.connect(self.abrir_loja)
        self.license_view.comprar.connect(lambda codigo: self.abrir_loja((codigo,)))
        self.boas_vindas_view = BoasVindasView(self.settings, self.license_service,
                                               self.conta_service)
        self.boas_vindas_view.licenca_alterada.connect(self._on_license_changed)
        self.boas_vindas_view.concluido.connect(self._primeiro_acesso_concluido)
        self.config_view = ConfigView()
        self.login_view = LoginView(self.acesso, lambda: self.launcher.empresa().nome)
        self.login_view.entrou.connect(self._usuario_entrou)
        self.login_view.ativar_licenca.connect(lambda: self._go(PAGINA_LICENCA))
        self.assistente_view = AssistenteContaView(self.acesso, self._dados_da_loja)
        self.assistente_view.concluido.connect(self._assistente_terminou)
        self.assistente_view.adiado.connect(self._assistente_adiado)
        self.usuarios_view = UsuariosView(self.acesso, self.registry)
        self.usuarios_view.mudou.connect(self._acesso_mudou)
        self.usuarios_view.criar_conta.connect(lambda: self._abrir_assistente(False))
        self.usuarios_view.licenca_saiu.connect(self._licenca_saiu_daqui)
        self.empresa_view = EmpresaView(self.settings, get_paths())
        self.empresa_view.alterada.connect(self.launcher.atualizar_empresa)
        self.backup_view = BackupView(self.settings, get_paths(), __version__)
        self.backup_view.restaurado.connect(self._fechar_tudo_para_restaurar)
        self.mensagens_view = MensagensView(self.settings, self.launcher.empresa())
        self.mensagens_view.alterada.connect(self.launcher.atualizar_empresa)
        self.empresa_view.alterada.connect(self._empresa_nas_mensagens)
        self.empresa_view.alterada.connect(self._atualizar_perfil)
        self.config_view.add_secao("Minha empresa", "home", self.empresa_view)
        self.config_view.add_secao("Usuários e acessos", "users", self.usuarios_view)
        self.pagamentos_service = PagamentosService(self.settings, lambda: self.license_service.current)
        self.celular_service = nucleo_celular.CelularService(lambda: self.license_service.current,
                                                             sessao=lambda: self.acesso.sessao)
        #: o ultimo resumo que foi para o celular (sem a hora) e quando foi
        self._celular_ultimo = ""
        self._celular_quando = 0.0
        self._celular_enviando = False
        # a parte online dos aplicativos (o link de agendamento da Agenda)
        self.servidor = nucleo_online.ServidorDaLicenca(lambda: self.license_service.current)
        self.launcher.servidor = self.servidor
        self._sincronias: dict[str, object] = {}
        self._online_enviando = False
        self.pagamentos_view = PagamentosView(self.pagamentos_service)
        self.pagamentos_view.alterada.connect(self.launcher.atualizar_empresa)
        self.config_view.add_secao("Pagamentos", "money", self.pagamentos_view)
        self.avisos_view = AvisosView(self.config_avisos, self.registry)
        self.avisos_view.alterada.connect(self.home_view.refresh)
        self.config_view.add_secao("Avisos do Início", "alert", self.avisos_view)
        self.config_view.add_secao("Mensagens", "chat", self.mensagens_view)
        self.config_view.add_secao("Backup", "shield", self.backup_view)
        self.about_view = AboutView()
        self.workspace = Workspace()
        self.workspace.close_requested.connect(self.close_app)
        # "Comprar" de dentro de um modulo em teste gratis
        self.workspace.comprar_requested.connect(lambda codigo: self.abrir_loja((codigo,)))

        self.stack.addWidget(self.home_view)     # PAGINA_INICIO
        self.stack.addWidget(self.license_view)  # PAGINA_LICENCA
        self.stack.addWidget(self.config_view)   # PAGINA_CONFIG
        self.stack.addWidget(self.about_view)    # PAGINA_SOBRE
        self.stack.addWidget(self.workspace)     # PAGINA_APP
        self.stack.addWidget(self.boas_vindas_view)  # PAGINA_BOAS_VINDAS
        self.stack.addWidget(self.login_view)        # PAGINA_LOGIN
        self.stack.addWidget(self.assistente_view)   # PAGINA_ASSISTENTE
        return self.stack

    def _build_shortcuts(self) -> None:
        self.palette_dialog = CommandPalette(self)
        self.palette_dialog.buscar_dados = self.buscar_nos_dados
        self.contacts.ao_renomear = self.launcher.renomear_cliente
        buscar = QShortcut(QKeySequence("Ctrl+K"), self)
        buscar.activated.connect(self.open_palette)
        fechar = QShortcut(QKeySequence("Ctrl+W"), self)
        fechar.activated.connect(self._close_current_app)
        inicio = QShortcut(QKeySequence("Ctrl+1"), self)
        inicio.activated.connect(lambda: self._go(PAGINA_INICIO))

    # --------------------------------------------------------- paleta de comandos
    def open_palette(self) -> None:
        if self.stack.currentIndex() in PAGINAS_DA_PORTA:
            return
        paleta = self.theme_manager.palette if self.theme_manager else current_palette()
        self._vestir(self.palette_dialog, paleta)
        self.palette_dialog.show_for(self.build_commands(), paleta)

    def buscar_nos_dados(self, termo: str) -> list[Command]:
        """A busca geral: clientes e o que cada modulo liberado guarda."""
        nomes = {e.app_id: e.manifest for e in self.registry.visiveis()}
        comandos = []
        if AGENDA in nomes:
            for contato in self.contacts.listar(busca=termo, incluir_inativos=True)[:5]:
                comandos.append(self._comando_de_busca(
                    nomes[AGENDA], contato.nome, "Cliente", contato.nome))
        for achado in self.launcher.buscar(termo):
            manifesto = nomes.get(achado.app_id)
            if manifesto is None:
                continue
            titulo = f"{achado.titulo}  ·  {achado.detalhe}" if achado.detalhe else achado.titulo
            comandos.append(self._comando_de_busca(manifesto, titulo, achado.tipo, achado.titulo))
        return comandos

    def _comando_de_busca(self, manifesto, titulo: str, tipo: str, procurar: str) -> Command:
        return Command(
            title=titulo, hint=tipo, icon=manifesto.icon, accent=manifesto.accent,
            run=lambda: self._abrir_achado(manifesto.app_id, procurar),
        )

    def _abrir_achado(self, app_id: str, texto: str) -> None:
        """Abre o modulo ja com a lista filtrada no que foi escolhido."""
        if not self.open_app(app_id):
            return
        casca = self.launcher.get(app_id)
        if casca is not None:
            casca.procurar(texto)

    def build_commands(self) -> list[Command]:
        """Tudo que da para fazer daqui, na ordem em que costuma ser procurado."""
        comandos: list[Command] = []

        for entrada in self._por_uso(self.registry.visiveis()):
            manifest = entrada.manifest
            comandos.append(
                Command(
                    title=manifest.short_name,
                    hint="Aplicativo",
                    icon=manifest.icon,
                    accent=manifest.accent,
                    run=lambda i=manifest.app_id: self.open_app(i),
                )
            )
            casca = self.launcher.get(manifest.app_id)
            if casca is None:
                continue  # so quem ja esta aberto conhece as proprias telas
            for indice, tela in enumerate(casca.views):
                comandos.append(
                    Command(
                        title=f"{manifest.short_name} > {tela.title}",
                        hint="Tela",
                        icon=tela.icon,
                        accent=manifest.accent,
                        run=lambda i=manifest.app_id, v=indice: self._ir_para_tela(i, v),
                    )
                )

        atual = self.workspace.current_app if self.stack.currentIndex() == PAGINA_APP else None
        if atual:
            nome = self._app_items[atual].text() if atual in self._app_items else atual
            comandos.append(
                Command(
                    title=f"Fechar {nome}",
                    hint="Ctrl+W",
                    icon="close",
                    run=lambda i=atual: self.close_app(i),
                )
            )

        escuro = self.theme_manager.palette.is_dark if self.theme_manager else True
        comandos.append(Command("Início", "Hub", "home", run=lambda: self._go(PAGINA_INICIO)))
        if self.acesso.e_adm:
            comandos += [
                Command("Licença", "Hub", "key", run=lambda: self._go(PAGINA_LICENCA)),
                Command("Configurações", "Hub", "wrench",
                        run=lambda: self._go(PAGINA_CONFIG)),
                Command("Minha empresa", "Hub", "home",
                        run=lambda: self._ir_para_config(self.empresa_view)),
                Command("Usuários e acessos", "Hub", "users",
                        run=lambda: self._ir_para_config(self.usuarios_view)),
                Command("Pagamentos e chave Pix", "Hub", "money",
                        run=lambda: self._ir_para_config(self.pagamentos_view)),
                Command("Avisos do Início", "Hub", "alert",
                        run=lambda: self._ir_para_config(self.avisos_view)),
                Command("Mensagens de WhatsApp", "Hub", "chat",
                        run=lambda: self._ir_para_config(self.mensagens_view)),
                Command("Backup", "Hub", "shield",
                        run=lambda: self._ir_para_config(self.backup_view)),
            ]
        if self.acesso.usuario is not None:
            comandos += [
                Command("Minha conta", "Hub", "user", run=self.abrir_minha_conta),
                Command("Trocar de usuário", "Hub", "users", run=self.trocar_de_usuario),
                Command("Sair", "Hub", "logout", run=self.sair_da_conta),
            ]
        comandos += [
            Command("Sobre", "Hub", "info", run=lambda: self._go(PAGINA_SOBRE)),
            Command(
                "Tema claro" if escuro else "Tema escuro",
                "Hub",
                "sun" if escuro else "moon",
                run=self._toggle_theme,
            ),
        ]
        return comandos

    def _ir_para_tela(self, app_id: str, indice: int) -> None:
        if self.open_app(app_id):
            casca = self.launcher.get(app_id)
            if casca is not None:
                casca.show_view(indice)

    # ------------------------------------------------------------------ acoes
    def _go(self, pagina: int) -> None:
        # computador que saiu da chave: a saida e ativar de novo, e nenhuma senha
        # resolve, porque o servidor recusa quem nao tem vaga
        reativar = pagina == PAGINA_LICENCA and self.acesso.computador_fora
        if pagina in PAGINAS_DE_DONO and not self.acesso.e_adm and not reativar:
            return
        if (self.acesso.precisa_login() and not reativar
                and pagina not in (*PAGINAS_DA_PORTA, PAGINA_BOAS_VINDAS)):
            pagina = PAGINA_LOGIN
        anterior = self.stack.currentIndex()
        self.stack.setCurrentIndex(pagina)
        self.topo.setVisible(pagina not in PAGINAS_DA_PORTA)
        self._vestir(self._regiao_visivel())
        if pagina == PAGINA_INICIO:
            self.home_view.refresh()
        elif pagina == PAGINA_LICENCA:
            self.license_view.refresh()
        self._sync_rail_state()
        if anterior != pagina:
            motion.surgir(self.stack.currentWidget(), self._direcao)
        if pagina == PAGINA_INICIO:
            self._talvez_convidar()

    def open_app(self, app_id: str) -> bool:
        """Abre (ou volta para) um aplicativo dentro do Hub."""
        antes = self.workspace.current_app if self.stack.currentIndex() == PAGINA_APP else None
        surface = self.launcher.open(app_id, self)
        if surface is None:
            self._sync_rail_state()
            return False
        if not self.workspace.show_app(app_id):
            self.workspace.mount(surface)
        self.stack.setCurrentIndex(PAGINA_APP)
        self._vestir(self.workspace.currentWidget())
        self.workspace.marcar_testes(self.license_service.current)
        self._sync_rail_state()
        # o Inicio NAO e reconstruido aqui: ele esta escondido, e reconstruir
        # custava ~75 ms (sete bancos lidos) a cada troca de aplicativo. Ele
        # se atualiza sozinho quando volta a aparecer (`_go`).
        if antes != app_id:
            motion.surgir(self.workspace.currentWidget(), self._direcao)
        return True

    def close_app(self, app_id: str, perguntar: bool = True) -> None:
        entrada = self.registry.get(app_id)
        nome = entrada.manifest.short_name if entrada else app_id
        if perguntar and not confirmar(
            self, f"Fechar {nome}",
            f"Fechar o {nome}? O que estiver digitado e não salvo se perde.",
            chave=confirmacoes.FECHAR_MODULO,
            rotulo_ok="Fechar", perigoso=False,
        ):
            return

        era_atual = self.workspace.current_app == app_id
        self.workspace.unmount(app_id)
        self.launcher.close(app_id)
        if era_atual or not self.workspace.mounted:
            self._go(PAGINA_INICIO)
        else:
            self._sync_rail_state()

    def _close_current_app(self) -> None:
        if self.stack.currentIndex() != PAGINA_APP:
            return
        atual = self.workspace.current_app
        if atual:
            self.close_app(atual)

    # ------------------------------------------------------ dado que mudou
    def _dados_alterados(self, app_id: str) -> None:
        """Um modulo escreveu no dado de outro (`core/eventos.py`).

        Marcar e barato, recarregar nao: por isso o aplicativo escondido so
        fica anotado e le o banco quando voltar a aparecer. Quem esta na
        frente ve a mudanca na hora.

        A releitura vai para o proximo giro do laco de eventos de proposito:
        este aviso chega no meio da escrita de quem o disparou (um dialogo
        salvando, por exemplo), e recarregar uma tela por baixo de quem ainda
        esta trabalhando nela e pedir problema.
        """
        if app_id == AGENDA:
            self.workspace.invalidar_tudo()  # a agenda e de todo mundo
        else:
            self.workspace.invalidar(app_id)
        if not self._atualizacao_marcada:
            # uma acao so pode gerar varios avisos (a venda que baixa cinco
            # itens do estoque): marcar tudo e recarregar uma vez
            self._atualizacao_marcada = True
            QTimer.singleShot(0, self, self._aplicar_atualizacoes)
        QTimer.singleShot(self.CELULAR_ESPERA_MS, self, self.publicar_no_celular)

    def _aplicar_atualizacoes(self) -> None:
        """Recarrega o que esta na frente do usuario agora."""
        self._atualizacao_marcada = False
        if self.stack.currentIndex() == PAGINA_APP:
            self.workspace.atualizar_visivel()
        elif self.stack.currentIndex() == PAGINA_INICIO:
            self.home_view.refresh()

    def _conferir_testes(self) -> None:
        """Teste gratis que venceu com o Hub aberto: o modulo fecha, o selo anda."""
        licenca = self.license_service.current
        if any(licenca.allows(app) == self.launcher.em_consulta(app)
               for app in self.workspace.mounted):
            self._on_license_changed()
            return
        self.workspace.marcar_testes(licenca)

    def _on_license_changed(self) -> None:
        """Ativou, verificou ou removeu a licenca: o Hub reavalia os aplicativos."""
        chave = self.license_service.current.key
        if chave != self._chave_aberta:
            # outra chave, outras contas: nada da anterior fica valendo
            self._chave_aberta = chave
            self.acesso.esquecer_tudo()
            self.acesso.nova_abertura()
        self.registry.load()
        for app_id in self.workspace.mounted:  # abertos e preparados
            if self.license_service.allows(app_id) == self.launcher.em_consulta(app_id):
                self.workspace.unmount(app_id)
        self.launcher.close_blocked()
        self._remontar_desatualizados()
        self.workspace.marcar_testes(self.license_service.current)
        self.refresh_rail()
        self.home_view.refresh()
        # modulo novo (ou teste gratis) entra no celular na hora
        self.publicar_no_celular(forcar=True)
        # o que ele tem mudou: as ofertas do que ele NAO tem mudam junto
        self._tarefas_de_rede(forcar=True)
        self.login_view.conferir_licenca()
        if (self.acesso.precisa_login() and not self.acesso.computador_fora
                and self.stack.currentIndex() not in (*PAGINAS_DA_PORTA, PAGINA_BOAS_VINDAS)):
            self._go(self._pagina_de_entrada())
        elif self.stack.currentIndex() == PAGINA_APP and not self.workspace.mounted:
            self._go(PAGINA_INICIO)

    def _remontar_desatualizados(self) -> None:
        """Modulo que entrou ou saiu da licenca chega em quem ja estava montado.

        Desmontar e o caminho seguro: na proxima vez que a pessoa abrir, a casca
        nasce de novo com as pontes certas. Fica como esta so o que se perderia
        - o aplicativo na frente da pessoa, o que tem trabalho fora do banco
        (carrinho do balcao) e qualquer um com dialogo aberto por cima.
        """
        atual = self.workspace.current_app if self.stack.currentIndex() == PAGINA_APP else None
        dialogo_aberto = QApplication.activeModalWidget() is not None
        for app_id in self.launcher.desatualizados():
            if app_id in self.launcher.preparados:
                self.workspace.unmount(app_id)
                self.launcher.descartar_preparado(app_id)
                continue
            surface = self.launcher.get(app_id)
            if app_id == atual or dialogo_aberto or surface.tem_trabalho_aberto():
                continue
            self.workspace.unmount(app_id)
            self.launcher.close(app_id)

    def _toggle_theme(self) -> None:
        """Troca o tema da plataforma - com o circulo nascendo do botao de tema.

        Venha de onde vier o pedido (botao, menu da empresa, paleta de
        comandos), o circulo sai sempre do mesmo lugar: e ali que a pessoa
        aprende que o tema mora.
        """
        if self.theme_manager is None:
            return
        centro = self.botao_tema.mapTo(self, self.botao_tema.rect().center())
        motion.revelar_tema(self, QPointF(centro), self._trocar_tema)

    def _trocar_tema(self) -> None:
        self.theme_manager.toggle()
        self.settings.set("hub", "theme", self.theme_manager.mode)
        self.settings.save()

    def _on_theme_changed(self, palette: Palette) -> None:
        self.setWindowIcon(icons.icon("grid", palette.accent, 64))
        dica = "Tema claro" if palette.is_dark else "Tema escuro"
        self.botao_tema.set_icon_name("sun" if palette.is_dark else "moon")
        self.botao_tema.setToolTip(f"{dica} para toda a plataforma")
        self.acao_tema.setText(dica)
        self._pintar_menu(palette)

        # A janela do Hub NAO recebe folha de estilo inteira: isso reestilizava
        # os ~2.700 widgets de todos os aplicativos abertos, visiveis ou nao.
        # O tema vai por regiao - agora so a barra e o que esta na tela; o
        # resto veste o tema novo no instante em que aparecer (`_vestir`).
        self._dt_palette = palette
        self.setPalette(qt_palette(palette))
        self._vestir(self.topo, palette)
        self._vestir(self._regiao_visivel(), palette)
        # quem se pinta a mao (graficos, tabelas coloridas, abas) troca de cor
        # em TODO lugar agora mesmo - inclusive nas telas escondidas. Isso e
        # barato (~40 ms com sete aplicativos); caro era a folha de estilo.
        refresh_theme(self, palette)
        motion.acompanhar(self)
        chrome.pintar(self, palette)

    # ---------------------------------------------------------- tema por regiao
    def _paleta(self) -> Palette:
        return getattr(self, "_dt_palette", None) or current_palette()

    def _regiao_visivel(self) -> QWidget | None:
        if self.stack.currentIndex() == PAGINA_APP:
            return self.workspace.currentWidget()
        return self.stack.currentWidget()

    def _vestir(self, regiao: QWidget | None, palette: Palette | None = None) -> None:
        """Poe a folha de estilo do tema numa regiao (barra, pagina, app, menu).

        So mexe se ela ainda estiver com o tema antigo: voltar para uma pagina
        que ja esta no tema certo nao custa nada. Quem se pinta a mao ja foi
        avisado na troca (`_on_theme_changed`); aqui e so a folha.
        """
        if regiao is None:
            return
        palette = palette or self._paleta()
        if getattr(regiao, "_dt_tema", None) == palette.name:
            return
        folhas = self.__dict__.setdefault("_folhas", {})
        if palette.name not in folhas:
            folhas[palette.name] = stylesheet_for(palette)
        regiao.setStyleSheet(folhas[palette.name])
        regiao._dt_tema = palette.name

    def _empresa_nas_mensagens(self) -> None:
        """A previa das mensagens diz o nome da loja - e ele acabou de mudar."""
        self.mensagens_view.mensageiro.empresa = self.launcher.empresa()
        self.mensagens_view.refresh()

    def _ir_para_config(self, secao: QWidget) -> None:
        """A paleta de comandos leva direto para a secao, nao so para a tela."""
        if not self.acesso.e_adm:
            return
        self._go(PAGINA_CONFIG)
        self.config_view.mostrar(self.config_view.stack.indexOf(secao))

    # ----------------------------------------------------------------- backup
    def _fechar_tudo_para_restaurar(self) -> None:
        """Restaurar substitui arquivos .db: nada pode estar com eles aberto.

        Este metodo so FECHA. Qualquer coisa que leia os bancos depois daqui -
        ate um `refresh_rail`, que consulta o hub_store - reabre a conexao pela
        porta dos fundos e trava o arquivo na hora de trocar.
        """
        eventos.parar_de_ouvir(self._dados_alterados)
        self._preparo_parado = True
        for app_id in self.workspace.mounted:  # abertos e preparados
            self.workspace.unmount(app_id)
        self.launcher.close_all()
        self.hub_store.close()
        self.contacts.close()

    # ------------------------------------------------------------- preparo
    #: espera depois que a janela aparece, e o respiro entre um app e outro:
    #: o preparo acontece nos intervalos, sem disputar o clique de ninguem
    PREPARO_INICIO_MS = 700
    PREPARO_INTERVALO_MS = 300
    #: a copia diaria vai antes do preparo, com a janela ja na tela
    BACKUP_ESPERA_MS = 350
    #: de quanto em quanto confere se o dia virou; a copia e uma por dia
    BACKUP_INTERVALO_MS = 30 * 60 * 1000
    #: o que depende de internet (cadastro pendente, ofertas) vai por ultimo:
    #: nada disso e urgente, e ninguem pode ficar esperando por isso
    REDE_ESPERA_MS = 1500
    #: o anuncio espera o Hub estar desenhado e util: ninguem abre o programa
    #: para ver propaganda, entao ele entra depois, e so na tela de Inicio
    ANUNCIO_ESPERA_MS = 4000
    #: Hub aberto o dia inteiro tambem confere: cada tarefa decide sozinha se ja
    #: esta na hora (licenca a cada 1 h, ofertas a cada 24 h), entao o relogio
    #: pode passar com frequencia sem gastar rede
    REDE_INTERVALO_MS = 15 * 60 * 1000
    #: A VERSAO tem relogio proprio, e curto: quando a DumTech publica uma
    #: correcao, esperar a conferencia da licenca (1 h) seria uma eternidade.
    #: E uma chamada pequena - o que pesa na rede e a licenca, nao isto.
    VERSAO_INTERVALO_MS = 2 * 60 * 1000
    #: quando o cliente volta para o Hub, confere quase na hora
    VERSAO_VOLTA_MS = 800
    #: O celular: de quanto em quanto tempo o Hub CONFERE se o resumo mudou.
    #:
    #: Este e o caminho que importa, nao o aviso de `_dados_alterados`: aquele
    #: so chega quando um modulo escreve no dado de OUTRO (a venda que baixa o
    #: estoque). Mexer num produto, lancar uma conta ou marcar na agenda nao
    #: avisa ninguem - e era por isso que uma mudanca comum levava mais de um
    #: minuto para chegar no telefone.
    #:
    #: Conferir e barato: montar o resumo inteiro dos 7 modulos, medido com
    #: banco de verdade, custa ~8 ms. A cada 5 s isso e 0,15% de um nucleo, e
    #: so acontece quando ha celular pareado. Pela rede nao viaja nada se o
    #: resumo nao mudou - a comparacao e feita aqui, antes de enviar.
    CELULAR_INTERVALO_MS = 5 * 1000
    #: mesmo sem mudanca, manda de vez em quando: o celular mostra "atualizado ha"
    CELULAR_BATIDA_S = 10 * 60
    #: A parte online dos aplicativos (o link de agendamento): de quanto em
    #: quanto tempo o Hub CONFERE se ha o que publicar ou buscar. Conferir e
    #: local e barato; a rede so e chamada quando a agenda mudou ou quando ja
    #: passou o intervalo do proprio modulo (20 s na Agenda).
    ONLINE_INTERVALO_MS = 10 * 1000
    #: depois de uma escrita, espera a rajada de avisos acabar antes de montar.
    #: Curto de proposito: vendeu no balcao, o celular do dono ja sabe. Uma
    #: rajada vira um envio so - o resumo sem mudanca nao viaja.
    CELULAR_ESPERA_MS = 1200

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not getattr(self, "_preparo_agendado", False):
            self._preparo_agendado = True
            # com o proprio Hub de contexto: se ele fechar antes, nada dispara
            QTimer.singleShot(self.BACKUP_ESPERA_MS, self, self._backup_depois_de_abrir)
            # quem deixa o Hub aberto de um dia para o outro nunca abriria de novo
            self._relogio_de_backup = QTimer(self)
            self._relogio_de_backup.setInterval(self.BACKUP_INTERVALO_MS)
            self._relogio_de_backup.timeout.connect(self._backup_depois_de_abrir)
            self._relogio_de_backup.start()
            QTimer.singleShot(self.PREPARO_INICIO_MS, self, self._preparar_proximo)
            QTimer.singleShot(self.REDE_ESPERA_MS, self, self._tarefas_de_rede)
            QTimer.singleShot(self.REDE_ESPERA_MS, self, lambda: self.conferir_versao(True))
            QTimer.singleShot(self.ANUNCIO_ESPERA_MS, self, self._talvez_anunciar)
            self._atualizar_botao_versao()
            self._relogio_de_rede = QTimer(self)
            self._relogio_de_rede.setInterval(self.REDE_INTERVALO_MS)
            self._relogio_de_rede.timeout.connect(self._tarefas_de_rede)
            self._relogio_de_rede.start()

            self._relogio_de_versao = QTimer(self)
            self._relogio_de_versao.setInterval(self.VERSAO_INTERVALO_MS)
            self._relogio_de_versao.timeout.connect(self.conferir_versao)
            # o teste gratis vence sozinho, mesmo offline: o mesmo relogio
            # confere se algum modulo aberto perdeu o direito
            self._relogio_de_versao.timeout.connect(self._conferir_testes)
            # conta bloqueada no meio de uma venda: sai quando a venda acabar
            self._relogio_de_versao.timeout.connect(self._conferir_saida_pendente)
            self._relogio_de_versao.start()

            QTimer.singleShot(self.REDE_ESPERA_MS, self, lambda: self.publicar_no_celular(forcar=True))
            self._relogio_do_celular = QTimer(self)
            self._relogio_do_celular.setInterval(self.CELULAR_INTERVALO_MS)
            self._relogio_do_celular.timeout.connect(self.publicar_no_celular)
            self._relogio_do_celular.start()

            QTimer.singleShot(self.REDE_ESPERA_MS, self, self.sincronizar_online)
            self._relogio_online = QTimer(self)
            self._relogio_online.setInterval(self.ONLINE_INTERVALO_MS)
            self._relogio_online.timeout.connect(self.sincronizar_online)
            self._relogio_online.start()

    def _backup_depois_de_abrir(self) -> None:
        if not getattr(self, "_preparo_parado", False):
            self.backup_automatico()

    # ------------------------------------------------------- porta de entrada
    def _primeiro_acesso(self) -> bool:
        """As boas-vindas aparecem? So para quem nunca se apresentou.

        Quem ja tem licenca ativa (instalacao antiga, ou reinstalacao com o
        license.json no lugar) nao tem nada a contar: o cadastro e marcado como
        concluido e o Hub abre direto no Inicio.
        """
        conta = Conta.carregar(self.settings)
        if conta.concluido:
            return False
        if self.license_service.ativada:
            email = self.launcher.empresa().email
            Conta(concluido=True, email=email, pendente=bool(email)).salvar(self.settings)
            return False
        return True

    def _primeiro_acesso_concluido(self) -> None:
        """Terminou o primeiro acesso - com chave ativada ou sem ela."""
        self.refresh_rail()
        if self._loja_sem_conta():
            self._abrir_assistente(direto=True)
        else:
            self._go(self._pagina_de_entrada())
        self._tarefas_de_rede()

    # ---------------------------------------------------------- contas da loja
    def _pagina_de_entrada(self) -> int:
        if self.acesso.precisa_login():
            self.login_view.preparar()
            return PAGINA_LOGIN
        return PAGINA_INICIO

    def _dados_da_loja(self) -> dict:
        """O que o assistente ja sabe, para ninguem digitar duas vezes."""
        empresa = self.launcher.empresa()
        return {"nome": empresa.nome, "email": empresa.email or self.conta_service.atual.email,
                "computadores": self.license_service.current.used_machines}

    def _loja_sem_conta(self) -> bool:
        """Chave ativa, o servidor ja respondeu sobre as contas e nao ha nenhuma."""
        licenca = self.license_service.current
        return (licenca.ativa and licenca.source == "supabase" and not self.acesso.ha_contas
                and not self.acesso.falta_documento())

    def _abrir_assistente(self, direto: bool = False) -> None:
        self.assistente_view.abrir(obrigatorio=direto or self.acesso.exigir_conta, direto=direto)
        self._go(PAGINA_ASSISTENTE)

    def _talvez_convidar(self) -> None:
        """Quem ainda nao tem conta: uma vez por abertura, e so no Inicio.

        Quem ja esta num modulo termina o que estava fazendo e ve o convite
        quando voltar para o Inicio.
        """
        if (getattr(self, "_convidou", False) or modo_local_ligado() or not self._loja_sem_conta()
                or self.stack.currentIndex() != PAGINA_INICIO):
            return
        self._convidou = True
        self._abrir_assistente()

    def _assistente_terminou(self) -> None:
        self._recompor_para_a_pessoa()
        self._go(PAGINA_INICIO)

    def _assistente_adiado(self) -> None:
        self._go(PAGINA_INICIO)

    def _usuario_entrou(self) -> None:
        self._recompor_para_a_pessoa()
        self._go(PAGINA_INICIO)
        # o que fica pronto em segundo plano e so o que esta pessoa pode abrir
        QTimer.singleShot(self.PREPARO_INICIO_MS, self, self._preparar_proximo)

    def _recompor_para_a_pessoa(self) -> None:
        """Mudou quem esta aqui, ou o que ela ve: abas, menu e Inicio acompanham.

        Quem esta com trabalho aberto (carrinho do balcao, dialogo) nao perde
        nada: o modulo fica ate ela terminar.
        """
        dialogo_aberto = QApplication.activeModalWidget() is not None
        for app_id in self.workspace.mounted:
            if self.acesso.permite_modulo(app_id):
                continue
            surface = self.launcher.get(app_id)
            if surface is not None and (dialogo_aberto or surface.tem_trabalho_aberto()):
                continue
            self.workspace.unmount(app_id)
            self.launcher.close(app_id)
            self.launcher.descartar_preparado(app_id)
        self.refresh_rail()
        self._ajustar_menu()
        if self.stack.currentIndex() == PAGINA_INICIO:
            self.home_view.refresh()
        elif self.stack.currentIndex() in PAGINAS_DE_DONO and not self.acesso.e_adm:
            self._go(PAGINA_INICIO)  # virou funcionario com a tela de dono aberta
        elif self.stack.currentIndex() == PAGINA_APP and not self.workspace.mounted:
            self._go(PAGINA_INICIO)

    def _trabalho_aberto(self) -> bool:
        abertos = (self.launcher.get(app_id) for app_id in self.launcher.open_apps)
        return any(surface.tem_trabalho_aberto() for surface in abertos if surface is not None)

    def _fechar_modulos(self) -> None:
        for app_id in self.workspace.mounted:
            self.workspace.unmount(app_id)
        for app_id in self.launcher.open_apps:
            self.launcher.close(app_id)
        for app_id in self.launcher.preparados:
            self.launcher.descartar_preparado(app_id)

    def _encerrar_conta(self, esquecer: bool, recado: str = "") -> None:
        self.acesso.sair(esquecer)
        self._fechar_modulos()
        self.refresh_rail()
        self.login_view.preparar()
        self._go(PAGINA_LOGIN)
        if recado:
            self.login_view.avisar(recado)

    def _pode_sair_agora(self, titulo: str) -> bool:
        if not self._trabalho_aberto():
            return True
        return confirmar(self, titulo, "Há uma venda em andamento. Ao continuar, o que não foi "
                                       "finalizado se perde.", rotulo_ok="Continuar")

    def trocar_de_usuario(self) -> None:
        """Outra pessoa vai usar. Quem saiu aparece no login, e volta com a senha."""
        if self._pode_sair_agora("Trocar de usuário"):
            self._encerrar_conta(esquecer=False)

    def sair_da_conta(self) -> None:
        """Sair de verdade: na proxima abertura o Hub pede a senha."""
        if self._pode_sair_agora("Sair da conta"):
            self._encerrar_conta(esquecer=True)

    def abrir_minha_conta(self) -> None:
        if self.acesso.usuario is not None:
            MinhaContaDialog(self.acesso, self).exec()
            self._atualizar_perfil()

    def _acesso_mudou(self) -> None:
        """Chegou pacote de contas novo: de outro computador ou do painel."""
        if self.acesso.reconciliar():
            self._sair_quando_puder()
            return
        self._recompor_para_a_pessoa()

    def _sair_quando_puder(self) -> None:
        """Conta bloqueada ou senha redefinida: sai, sem perder venda no meio."""
        if self._trabalho_aberto() or QApplication.activeModalWidget() is not None:
            self._saida_pendente = True
            return
        self._saida_pendente = False
        self._encerrar_conta(True, "A sua conta mudou. Entre de novo para continuar.")

    def _conferir_saida_pendente(self) -> None:
        if getattr(self, "_saida_pendente", False):
            self._sair_quando_puder()

    def _licenca_saiu_daqui(self) -> None:
        """O ADM liberou este computador: a vaga ja foi solta no servidor."""
        self.license_service.deactivate(liberar_vaga=False)
        self._on_license_changed()
        self._go(PAGINA_LICENCA)

    def abrir_loja(self, marcar: tuple[str, ...] = ()) -> None:
        """Abre a loja DumTech no navegador, ja dizendo quem chegou.

        `marcar`: modulos que ja entram no carrinho (o "Comprar" do teste gratis).

        O codigo que identifica o cliente e pedido em segundo plano; se nao
        vier (sem internet, servidor fora), a loja abre do mesmo jeito.
        """
        if not self.acesso.e_adm:
            return
        licenca = self.license_service.current
        nome = self.launcher.empresa().nome
        email = self.conta_service.atual.email
        # o cliente vai comprar e volta esperando ver o modulo novo aqui
        self._volta_da_loja = True
        tasks.executar(
            self,
            lambda: self.loja.link(licenca, nome, email, marcar),
            self._abrir_endereco,
            lambda _erro: self._abrir_endereco(url_compra(marcar=marcar)),
        )

    def conferir_versao(self, forcar: bool = False) -> None:
        """Saiu versao nova? Pergunta em segundo plano, sem incomodar ninguem.

        Tem relogio proprio (2 min) e roda tambem quando o cliente volta para o
        Hub: publicar uma correcao e ver o botao aparecer tem de ser questao de
        minutos, nao de hora. Falhar aqui e silencio.
        """
        if getattr(self, "_preparo_parado", False) or modo_local_ligado():
            return
        agora = time.monotonic()
        if not forcar and agora - getattr(self, "_versao_conferida_em", 0.0) < 25:
            return              # acabou de perguntar: nao repete a toa
        self._versao_conferida_em = agora

        licenca = self.license_service.current
        chave, maquina = licenca.key, licenca.machine

        def concluiu(resposta) -> None:
            self._licenca_talvez_mudou(resposta)
            nova = self.atualizacao_service.guardar(resposta)
            if resposta:        # versao recolhida tambem muda a tela: o botao e a contagem somem
                self._atualizar_botao_versao()
            if nova is None:
                return
            if self.stack.currentIndex() == PAGINA_INICIO:
                self.home_view.refresh()

        tasks.executar(self, lambda: self.atualizacao_service.buscar(chave, maquina),
                       concluiu, lambda _erro: None)

    def _licenca_talvez_mudou(self, resposta) -> None:
        """O servidor mandou a impressao digital da licenca: mudou algo?

        A consulta de versao roda a cada 2 minutos e e leve. Ela traz junto
        um md5 de tudo que muda o que este computador libera (modulos,
        validade, bloqueio, vagas, chave Pix). So quando o md5 muda o Hub faz
        a conferencia pesada, com assinatura - e assim modulo liberado no
        painel aparece em minutos, sem estourar o limite de pedidos da loja.
        """
        marca = str((resposta or {}).get("licenca") or "") if isinstance(resposta, dict) else ""
        if not marca or marca == str(self.settings.get("licenca", "marca", "") or ""):
            return
        self._marca_pendente = marca
        self._tarefas_de_rede(forcar_licenca=True)

    def _guardar_marca_da_licenca(self) -> None:
        """A conferencia deu certo: a impressao nova passa a ser a conhecida.

        Guardada so DEPOIS de conferir: se a conferencia falhar (sem internet,
        servidor fora), a proxima consulta ve a diferenca e tenta de novo.
        """
        marca = getattr(self, "_marca_pendente", "")
        if marca:
            self.settings.set("licenca", "marca", marca)
            self.settings.save()
            self._marca_pendente = ""

    def novidade_de_versao(self):
        """A atualizacao que vale mostrar agora (ja conferida e nao dispensada)."""
        return nucleo_atualizacao.para_avisar(self.settings, __version__)

    def _atualizar_botao_versao(self) -> None:
        """A pilula do topo aparece quando ha versao nova - e some depois.

        Ela nao obedece ao "Lembrar em 3 dias" (isso e da faixa do Inicio):
        enquanto houver versao nova, o caminho para atualizar fica a vista. E a
        cada versao que chega - e a cada abertura do Hub - ela chama uma vez.

        Versao silenciosa nao aparece: baixa agora e instala quando o Hub fechar.
        Versao forcada aparece e, alem disso, baixa e comeca a contagem.
        """
        aviso = nucleo_atualizacao.disponivel(self.settings, __version__)
        self._conferir_contagem(aviso)
        if aviso is not None and nucleo_atualizacao.forcada_aqui(aviso):
            self._cumprir_forcada(aviso)
        elif aviso is not None and nucleo_atualizacao.em_silencio(self.settings, aviso):
            self._preparar_em_silencio(aviso)
            aviso = None
        existe = aviso is not None
        chegou = existe and aviso.versao != self.botao_atualizar.versao
        self.botao_atualizar.setVisible(existe)
        self.item_atualizar.setVisible(existe)
        self.separador_atualizar.setVisible(existe)
        if existe:
            self.botao_atualizar.set_versao(aviso.versao)
            self.item_atualizar.setText(f"Atualizar para {aviso.versao}")
            if chegou:
                self.botao_atualizar.chamar()

    def abrir_atualizacao(self) -> None:
        """A janela que explica o que muda e faz a atualizacao inteira."""
        aviso = nucleo_atualizacao.disponivel(self.settings, __version__)
        if aviso is None:
            return
        dialogo = AtualizacaoDialog(aviso, __version__, self.atualizacao_service, self)
        dialogo.dispensou.connect(lambda: self._dispensar_versao(aviso.versao))
        dialogo.instalando.connect(self._fechar_para_atualizar)
        dialogo.exec()

    def _fechar_para_atualizar(self) -> None:
        """O instalador ja esta rodando: o Hub sai de cena para ele trabalhar.

        Fechar aqui e o que libera os arquivos do programa. O instalador abre o
        Hub de novo no fim (ver build/instalador.iss).
        """
        logger.info("Atualizacao em andamento: fechando o Hub")
        self._atualizando = True
        # janela aberta por cima segura o programa no ar, e o instalador espera
        for janela in QApplication.topLevelWidgets():
            if isinstance(janela, QDialog) and janela.isVisible():
                janela.reject()
        QTimer.singleShot(400, self, self.close)

    def _preparar_em_silencio(self, aviso) -> None:
        """Baixa a versao silenciosa em segundo plano (uma vez por versao)."""
        pronta = self._silenciosa
        if (pronta is not None and pronta[1].versao == aviso.versao) \
                or self._baixando_em_silencio == aviso.versao:
            return
        self._baixando_em_silencio = aviso.versao
        servico = self.atualizacao_service

        def baixar():
            # fechar o Hub no meio interrompe o download (nao segura a saida)
            caminho = servico.baixar(
                aviso, parar=lambda: getattr(self, "_preparo_parado", False))
            servico.limpar(manter=caminho.name)
            return caminho

        def baixou(caminho) -> None:
            self._baixando_em_silencio = ""
            self._silenciosa = (caminho, aviso)
            if nucleo_atualizacao.forcada_aqui(aviso):
                self._contar_forcada(aviso)

        def falhou(erro) -> None:
            self._baixando_em_silencio = ""
            logger.info("Atualizacao silenciosa %s nao baixou: %s", aviso.versao, erro)

        tasks.executar(self, baixar, baixou, falhou)

    def _cumprir_forcada(self, aviso) -> None:
        """A DumTech mandou instalar: baixa e, com o arquivo pronto, conta o prazo."""
        pronta = self._silenciosa
        if pronta is not None and pronta[1].versao == aviso.versao:
            self._contar_forcada(aviso)
        else:
            self._preparar_em_silencio(aviso)

    def _conferir_contagem(self, aviso) -> None:
        """A DumTech recolheu ou cancelou no meio do prazo: a instalacao para aqui."""
        contagem = self._aviso_forcada
        if contagem is None:
            return
        if aviso is None or not aviso.forcada or aviso.versao != contagem.versao:
            logger.info("Atualizacao forcada %s cancelada pela DumTech", contagem.versao)
            self._encerrar_aviso_forcada()

    def _contar_forcada(self, aviso) -> None:
        if self._aviso_forcada is not None:
            return
        self._aviso_forcada = ForcadaAviso(aviso.versao, nucleo_atualizacao.PRAZO_FORCADA_S, self)
        self._aviso_forcada.instalar.connect(self._instalar_forcada)
        self._aviso_forcada.mostrar()

    def _encerrar_aviso_forcada(self) -> None:
        aviso, self._aviso_forcada = self._aviso_forcada, None
        if aviso is not None:
            aviso.encerrar()

    def _instalar_forcada(self) -> None:
        """O prazo acabou (ou a pessoa adiantou): instala e reabre.

        Se o Windows recusar, o Hub segue funcionando e a proxima conferencia
        de versao baixa de novo: atualizacao forcada nunca derruba o programa.
        """
        self._encerrar_aviso_forcada()
        pronta = self._silenciosa
        if pronta is None:
            return
        instalador, aviso = pronta
        atual = nucleo_atualizacao.disponivel(self.settings, __version__)
        if atual is None or atual.versao != aviso.versao or not atual.forcada:
            return      # chegou outra ordem depois do download
        try:
            self.atualizacao_service.instalar(instalador, aviso)
        except nucleo_atualizacao.AtualizacaoError as erro:
            logger.warning("Atualizacao forcada %s nao instalou: %s", aviso.versao, erro)
            self._silenciosa = None
            return
        self._fechar_para_atualizar()

    def _instalar_em_silencio(self) -> None:
        """O Hub esta fechando com uma versao silenciosa pronta: instala agora.

        Sem `/reabrir` - a pessoa fechou porque quis; na proxima abertura ja e
        a versao nova. Com o Windows desligando nao instala: o instalador seria
        cortado no meio. Fica para o proximo fechamento.
        """
        pronta = self._silenciosa
        if pronta is None or getattr(self, "_atualizando", False) or self._windows_saindo:
            return
        instalador, aviso = pronta
        atual = nucleo_atualizacao.disponivel(self.settings, __version__)
        if atual is None or atual.versao != aviso.versao:
            return      # chegou outra versao depois do download
        try:
            self.atualizacao_service.instalar(instalador, aviso, reabrir=False)
            logger.info("Atualizacao silenciosa %s instalando", aviso.versao)
        except nucleo_atualizacao.AtualizacaoError as erro:
            logger.warning("Atualizacao silenciosa %s nao instalou: %s", aviso.versao, erro)

    def _windows_desligando(self, _sessao) -> None:
        self._windows_saindo = True

    def _baixar_versao(self) -> None:
        """A faixa do Inicio: abre a mesma janela de atualizacao."""
        self.abrir_atualizacao()

    def _dispensar_versao(self, versao: str = "") -> None:
        aviso = nucleo_atualizacao.disponivel(self.settings, __version__)
        versao = versao or (aviso.versao if aviso else "")
        if versao:
            dispensar_versao(self.settings, versao)
            self.home_view.refresh()

    def abrir_anuncio(self, link: str) -> None:
        """Abre o anuncio - e, se ele aponta para a nossa loja, ja diz quem chegou.

        O mesmo cuidado do botao "Adquirir": o codigo de identificacao e pedido
        em segundo plano e nunca sai para endereco de terceiro (`e_da_loja`).
        """
        if not e_da_loja(link):
            self._abrir_endereco(link)
            return
        licenca = self.license_service.current
        nome = self.launcher.empresa().nome
        email = self.conta_service.atual.email
        self._volta_da_loja = True
        tasks.executar(
            self,
            lambda: self.loja.link_do_anuncio(link, licenca, nome, email),
            self._abrir_endereco,
            lambda _erro: self._abrir_endereco(link),
        )

    def changeEvent(self, event) -> None:  # noqa: N802 (Qt)
        """Voltou do navegador depois de comprar? Confere a licenca sozinho.

        E a diferenca entre "o modulo apareceu" e "tive que descobrir o botao
        Verificar licenca". Acontece uma vez por viagem a loja, e so se a
        pessoa realmente saiu daqui para comprar.
        """
        super().changeEvent(event)
        if event.type() != QEvent.Type.ActivationChange or not self.isActiveWindow():
            return
        # voltou para o Hub: e a melhor hora para saber se saiu versao nova
        QTimer.singleShot(self.VERSAO_VOLTA_MS, self, self.conferir_versao)
        if getattr(self, "_volta_da_loja", False):
            self._volta_da_loja = False
            QTimer.singleShot(400, self, self._conferir_apos_a_loja)

    def _conferir_apos_a_loja(self) -> None:
        """Pergunta ao servidor o que mudou - em silencio, em segundo plano."""
        if modo_local_ligado() or not self.license_service.ativada:
            return
        antes = set(self.license_service.current.entitlements)
        tasks.executar(
            self,
            self.license_service.verify,
            lambda licenca: self._licenca_conferida(antes, licenca),
            lambda _erro: None,  # sem internet o botao Verificar continua ali
        )

    def _licenca_conferida(self, antes: set, licenca) -> None:
        if set(licenca.entitlements) == antes:
            return
        logger.info("A licenca mudou depois da visita a loja: %s", licenca.entitlements)
        self._on_license_changed()

    @staticmethod
    def _abrir_endereco(endereco: str) -> None:
        # So pagina web. O endereco pode vir do servidor (link de anuncio): um
        # `file:` ou caminho de rede aqui abriria programa no computador do cliente.
        url = QUrl(endereco or "")
        if url.isValid() and url.scheme().lower() in ("http", "https"):
            QDesktopServices.openUrl(url)
        elif endereco:
            logger.warning("Endereco recusado (so http/https): %s", endereco[:200])

    # ---------------------------------------------------------------- celular
    def abrir_celular(self) -> None:
        """O QR que conecta o celular (Ver no celular, no menu da empresa).

        Funcionario nao tem esta visao. Com contas, o ADM confirma a senha: quem
        abre lembrado nao tem sessao, e o servidor exige uma.
        """
        if not self.acesso.e_adm:
            return
        # `ha_contas`, e nao `exige_conta`: quem decide e o servidor, e ele pede a
        # sessao assim que a chave tem conta, mesmo com este Hub aberto desde antes
        if self.acesso.ha_contas and not self.acesso.gestao_aberta:
            confirmacao = ConfirmarSenhaDialog(self.acesso, "O celular mostra os números da loja.", self)
            if not confirmacao.exec():
                return
        dialogo = CelularDialog(self.celular_service, self)
        dialogo.aparelhos_mudaram.connect(self._aparelhos_do_celular)
        dialogo.exec()

    def _aparelhos_do_celular(self, quantos: int) -> None:
        self.settings.set("celular", "pareados", quantos)
        if quantos:
            self.publicar_no_celular(forcar=True)  # o celular novo nao abre vazio

    def publicar_no_celular(self, forcar: bool = False) -> None:
        """Manda o resumo para os celulares conectados - se houver algum.

        O resumo e montado AQUI, na thread da interface (le os bancos, como
        `_tarefas_de_rede`); so a chamada de rede vai para o segundo plano. Sem
        celular pareado, nao sai nada do computador: a resposta do servidor diz
        quantos existem, e `forcar` (ao abrir, ao mudar a licenca) e a unica
        conferencia enquanto for zero.
        """
        if getattr(self, "_preparo_parado", False) or modo_local_ligado() or self._celular_enviando:
            return
        licenca = self.license_service.current
        if not licenca.ativa or licenca.is_local:
            return
        if not forcar and not self.settings.get("celular", "pareados", 0):
            return
        empresa = self.launcher.empresa()
        resumo = nucleo_celular.montar(self.registry.available(), get_paths(),
                                       empresa=empresa.nome if empresa is not None else "",
                                       versao=__version__)
        marca = json.dumps({k: v for k, v in resumo.items() if k != "gerado_em"},
                           sort_keys=True, ensure_ascii=False)
        agora = time.monotonic()
        if (not forcar and marca == self._celular_ultimo
                and agora - self._celular_quando < self.CELULAR_BATIDA_S):
            return
        self._celular_enviando = True

        def concluiu(pareados: int) -> None:
            self._celular_enviando = False
            self._celular_ultimo, self._celular_quando = marca, agora
            self.settings.set("celular", "pareados", pareados)
            logger.info("Resumo do celular enviado (%d bytes, %d pareado(s))",
                        len(marca), pareados)

        def falhou(erro: Exception) -> None:
            self._celular_enviando = False  # sem internet: o relogio tenta de novo
            # Sem esta linha um erro do servidor e invisivel: o dono ve o
            # celular parado e nao ha o que olhar para saber por que.
            logger.warning("Resumo do celular nao foi enviado: %s", erro)

        tasks.executar(self, lambda: self.celular_service.publicar(resumo), concluiu, falhou)

    # ------------------------------------------------------- parte online ---
    def sincronizar_online(self) -> None:
        """Publica e busca a parte online dos aplicativos liberados, um por vez.

        Mesmo desenho do celular: o modulo le o banco aqui (`preparar`), a rede
        vai para o segundo plano, e a resposta volta para gravar aqui
        (`aplicar`). Sem licenca ativa, em modo local ou sem nada ligado, nao
        sai nada do computador.
        """
        if getattr(self, "_preparo_parado", False) or modo_local_ligado() or self._online_enviando:
            return
        if not self.servidor.disponivel():
            return
        for entrada in self.registry.available():
            sincronia = self._sincronia_de(entrada)
            if sincronia is None:
                continue
            try:
                pedido = sincronia.preparar()
            except Exception:  # noqa: BLE001 - modulo quebrado nao derruba o Hub
                logger.exception("Falha ao preparar a parte online de %s", entrada.app_id)
                continue
            if pedido is None:
                continue
            funcao, params = pedido
            self._online_enviando = True
            tasks.executar(
                self,
                lambda: self.servidor.chamar(funcao, params),
                lambda resposta: self._online_respondeu(entrada, sincronia, funcao, params, resposta),
                lambda erro: self._online_falhou(entrada, sincronia, funcao, erro),
            )
            return

    def _sincronia_de(self, entrada):
        if entrada.app_id not in self._sincronias:
            self._sincronias[entrada.app_id] = nucleo_online.sincronia_de(
                entrada.module, get_paths(), self.launcher.empresa)
        return self._sincronias[entrada.app_id]

    def _online_respondeu(self, entrada, sincronia, funcao: str, params: dict, resposta) -> None:
        self._online_enviando = False
        if getattr(self, "_preparo_parado", False):
            return
        try:
            resultado = sincronia.aplicar(funcao, params, resposta)
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao gravar a resposta online de %s", entrada.app_id)
            return
        if resultado.mudou:
            eventos.avisar(entrada.app_id)  # a tela aberta recarrega; o Inicio tambem
        if resultado.avisos:
            texto = (resultado.avisos[0] if len(resultado.avisos) == 1
                     else f"{len(resultado.avisos)} novidades no link de agendamento")
            self.aviso_flutuante.mostrar(
                texto, entrada.manifest.short_name, "link", entrada.manifest.accent,
                acao=lambda app_id=entrada.app_id: self.open_app(app_id))
        if resultado.de_novo:
            # confirma ja o que chegou, junto com os ocupados novos
            QTimer.singleShot(1500, self, self.sincronizar_online)

    def _online_falhou(self, entrada, sincronia, funcao: str, erro: Exception) -> None:
        self._online_enviando = False
        logger.warning("A parte online de %s nao conversou com o servidor: %s", entrada.app_id, erro)
        falhou = getattr(sincronia, "falhou", None)
        if callable(falhou) and not getattr(self, "_preparo_parado", False):
            try:
                falhou(funcao, erro)
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao anotar o erro online de %s", entrada.app_id)

    def _tarefas_de_rede(self, forcar: bool = False, forcar_licenca: bool = False) -> None:
        """Cadastro pendente, licenca, uso e ofertas: em segundo plano, sem incomodar.

        Falhar aqui e silencio: o cliente abriu o programa para trabalhar.
        """
        if getattr(self, "_preparo_parado", False) or modo_local_ligado():
            return
        empresa = self.launcher.empresa()
        nome, telefone = empresa.nome, empresa.telefone
        licenca = self.license_service.current
        chave, maquina = licenca.key, licenca.machine
        buscar_ofertas = forcar or self.comunicados_service.precisa_atualizar()
        # o que a DumTech mudou no painel (modulo novo, suspensao, vaga liberada)
        # chega aqui sem o cliente precisar clicar em "Verificar"
        # `forcar_licenca`: o servidor avisou que algo mudou (ver
        # `_licenca_talvez_mudou`) - reconfere agora, sem esperar a hora cheia
        # licenca ainda sem o pacote de contas tambem confere: e ele que diz se
        # esta loja precisa do convite
        conferir_licenca = (forcar_licenca or self.license_service.precisa_conferir()
                            or self.acesso.falta_documento())
        antes = (set(licenca.entitlements), licenca.bloqueio)
        contas_antes = licenca.acesso.get("assinatura")
        # comprou no Mercado Livre (sem e-mail) e digitou o e-mail no Hub: liga os dois
        vincular = (licenca.ativa and not licenca.is_local
                    and self.conta_service.precisa_vincular(chave))
        # O banco do Hub e lido AQUI, na thread da interface. A conexao SQLite e
        # uma so; le-la no segundo plano enquanto o Hub fecha derruba o processo
        # (violacao de acesso, sem excecao). Para la vai so a chamada de rede.
        uso = self.uso_service.pendente()
        # a chave Pix vale o que o servidor diz: troca feita em outro computador da
        # loja chega aqui, e arquivo antigo (backup, copia) e corrigido
        conferir_pix = conferir_licenca and licenca.ativa and not licenca.is_local

        def trabalho():
            self.conta_service.reenviar(nome, telefone)
            conferida = self.license_service.conferir() if conferir_licenca else None
            vinculou = self.conta_service.vincular(chave, maquina, nome) if vincular else False
            enviou = self.uso_service.enviar_dados(chave, maquina, uso)
            ofertas = self.comunicados_service.atualizar(chave) if buscar_ofertas else None
            pix = self.pagamentos_service.buscar_atual() if conferir_pix else None
            return {"uso_enviado": enviou, "comunicados": ofertas, "licenca": conferida,
                    "vinculou": vinculou, "pix": pix}

        def concluiu(resultado: dict) -> None:
            if resultado.get("uso_enviado"):
                self.uso_service.marcar(uso)  # de volta na interface: pode tocar no banco
            if resultado.get("vinculou"):
                self.conta_service.marcar_vinculo(chave)
            pix = resultado.get("pix")
            if pix and self.pagamentos_service.guardar_assinado(pix.get("assinado")):
                logger.info("A chave Pix mudou no servidor: balcao atualizado")
                self.launcher.atualizar_empresa()
            conferida = resultado.get("licenca")
            if conferida is not None:
                self._guardar_marca_da_licenca()
            if conferida is not None and conferida.acesso.get("assinatura") != contas_antes:
                self._acesso_mudou()
            self._talvez_convidar()
            if conferida is not None and (set(conferida.entitlements), conferida.bloqueio) != antes:
                logger.info("A licenca mudou na conferencia: %s %s",
                            conferida.entitlements, conferida.bloqueio or "")
                self._on_license_changed()
                return  # _on_license_changed ja refaz as ofertas
            self._ofertas_atualizadas(resultado.get("comunicados"))

        tasks.executar(self, trabalho, concluiu, lambda _erro: None)

    def _ofertas_atualizadas(self, comunicados) -> None:
        if comunicados is not None and self.stack.currentIndex() == PAGINA_INICIO:
            self.home_view.refresh()
        if comunicados:
            self._talvez_anunciar()

    # ------------------------------------------------------------- o anuncio
    def _talvez_anunciar(self) -> None:
        """Mostra o anuncio que esta pessoa ainda nao viu - se a hora for boa.

        Hora boa e: o Hub na frente, na tela de Inicio, ninguem no meio de um
        aplicativo, e nenhum anuncio ja mostrado nesta abertura.
        """
        if getattr(self, "_anunciou", False) or getattr(self, "_preparo_parado", False):
            return
        if self.stack.currentIndex() != PAGINA_INICIO or not self.isActiveWindow():
            return
        if not self.acesso.e_adm:
            # oferta e assunto de quem compra. A novidade tambem espera: ela e
            # marcada como vista para o computador, e o ADM ficaria sem saber
            return
        if self._contar_novidades():
            return  # um pop-up por abertura: o anuncio fica para a proxima
        item = comunicados_core.para_anunciar(
            self.comunicados_service.listar(), self.settings)
        if item is None:
            return

        self._anunciou = True
        comunicados_core.marcar_visto(self.settings, item.id)   # visto e visto
        dialogo = AnuncioDialog(item, self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            if item.link:
                self.abrir_anuncio(item.link)
            else:
                self.abrir_loja()

    def _contar_novidades(self) -> bool:
        """Depois de atualizar: o que mudou - so no que esta pessoa usa.

        Mesma hora boa do anuncio (quem chama ja conferiu). Sem nada que diga
        respeito aos modulos dela, a versao conta como vista em silencio.
        """
        modulos = {e.app_id: e.manifest for e in self.registry.available()}
        itens = novidades_core.pendentes(self.settings, __version__, modulos)
        novidades_core.marcar_vista(self.settings, __version__)
        if not itens:
            return False
        self._anunciou = True
        NovidadesDialog(itens, __version__, modulos, self).exec()
        return True

    def _preparar_proximo(self) -> None:
        """Monta, um por vez, os aplicativos que a pessoa ainda nao abriu.

        O primeiro clique num aplicativo custava ~150-250 ms (montar as telas
        dele). Preparado de antemao, o clique so mostra o que ja existe - como
        alternar entre dois abertos. Vai do mais usado para o menos usado, e
        para se a janela sumir ou se o Hub estiver fechando tudo.
        """
        if getattr(self, "_preparo_parado", False) or not self.isVisible():
            return
        for entrada in self._por_uso(self.registry.visiveis()):
            app_id = entrada.app_id
            if app_id in self.launcher.open_apps or app_id in self.launcher.preparados:
                continue
            surface = self.launcher.preparar(app_id)
            if surface is not None:
                pagina = self.workspace.montar_escondido(surface)
                self._vestir(pagina)
            QTimer.singleShot(self.PREPARO_INTERVALO_MS, self, self._preparar_proximo)
            return

    def backup_automatico(self) -> None:
        """Uma copia por dia, ao abrir e com o Hub aberto. Nunca derruba nada.

        A falha nao interrompe quem esta trabalhando, mas tambem nao fica
        escondida no log: quem acha que tem copia e nao tem so descobre no dia
        em que precisa dela. Vira um recado aqui e na tela de Backup, e fica
        ate uma copia dar certo.
        """
        if not self.settings.get("backup", "automatico", True):
            return
        hoje = date.today().isoformat()
        if self.settings.get("backup", "ultimo", "") == hoje:
            return

        try:
            pasta = self.backup_view.pasta
            copia = backup.criar(pasta, get_paths(), automatico=True, versao=__version__)
            backup.limpar_antigos(pasta)
        except Exception as erro:  # noqa: BLE001 - backup nunca derruba a abertura
            logger.exception("Falha no backup automatico")
            self._backup_falhou(str(erro))
            return

        problema = self.backup_view.enviar_para_fora(copia)
        self.settings.set("backup", "ultimo", hoje)
        self.settings.set("backup", "falha", problema)
        self.settings.save()
        self.backup_view.refresh()
        if problema:
            self._avisar_backup(problema)

    def _backup_falhou(self, motivo: str) -> None:
        self.settings.set("backup", "falha", motivo)
        self.settings.save()
        self.backup_view.refresh()
        self._avisar_backup(motivo)

    def _avisar_backup(self, motivo: str) -> None:
        self.aviso_flutuante.mostrar(
            f"A cópia automática falhou: {motivo}", "Backup", "shield", "warning",
            acao=lambda: self._ir_para_config(self.backup_view))

    # ---------------------------------------------------------------- eventos
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._ajustar_topo()

    def closeEvent(self, event) -> None:  # noqa: N802
        eventos.parar_de_ouvir(self._dados_alterados)
        self.settings.set("window", "maximized", self.isMaximized())
        if not self.isMaximized():
            self.settings.set("window", "width", self.width())
            self.settings.set("window", "height", self.height())
        if self.theme_manager is not None:
            self.settings.set("hub", "theme", self.theme_manager.mode)
        self.settings.save()
        self._preparo_parado = True
        for app_id in self.workspace.mounted:  # abertos e preparados
            self.workspace.unmount(app_id)
        self.launcher.close_all()
        self.hub_store.close()
        self.contacts.close()
        self._encerrar_aviso_forcada()
        self._instalar_em_silencio()
        super().closeEvent(event)
