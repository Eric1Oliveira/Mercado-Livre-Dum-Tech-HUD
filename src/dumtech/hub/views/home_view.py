"""Tela Inicio: o centro de comando da empresa.

Ela abre com o nome da propria loja, e nao com o nome do programa - e a
diferenca entre "um sistema aberto" e "a minha empresa". Depois vem os sinais
vitais, o que precisa de atencao hoje ao lado de onde voce parou e, por fim,
os sistemas em uso.

A tela cresce com a licenca: cada modulo acrescenta um sinal na vitrine e os
seus avisos. Com um modulo ela ja e um painel coerente; com sete, e o retrato
do negocio inteiro. O que sustenta isso e uma regra: **nenhum bloco fica com
buraco** - sem empresa preenchida o cabecalho convida, sem aviso aparece o
cartao de tudo em dia, e a vitrine se ajusta ao numero de sinais que existir.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core import avisos as nucleo_avisos
from ...core import indicadores as nucleo_indicadores
from ...core.hub_store import HubStore
from ...core.registry import AppEntry, AppRegistry
from ...ui import format as fmt
from ...ui.theme import Space
from ...ui.widgets.app_card import AppCard, ContinueCard
from ...ui.widgets.buttons import Button
from ...ui.widgets.common import Card, EmptyState, IconBadge, label, overline
from ...ui.widgets.flow_layout import FlowLayout
from ...ui.widgets.painel_inicio import (
    CabecalhoEmpresa,
    PainelContinuar,
    PainelDeAvisos,
    TudoEmDia,
    VitrineDeSinais,
)

MAX_CONTINUAR = 3
LIMITE_AGRUPAMENTO = 8
#: quantos assuntos cabem na faixa de atencao antes de virar parede de cartao
MAX_AVISOS = 6
#: o sinal que e da plataforma, e nao de um aplicativo
SINAL_DA_PLATAFORMA = "hub"


class HomeView(QWidget):
    """Central de comando da plataforma."""

    open_app = Signal(str)
    ativar_licenca = Signal()
    #: o cabecalho pede para preencher os dados da empresa
    configurar_empresa = Signal()
    #: o sinal da plataforma leva para a tela de backup
    abrir_backup = Signal()
    #: o cabecalho oferece a busca (a mesma do Ctrl+K)
    buscar = Signal()
    #: o cliente quer conhecer/comprar outro modulo (o Hub abre a loja)
    adquirir = Signal()
    #: o link de um anuncio (pop-up) foi clicado
    abrir_link = Signal(str)
    #: "Baixar agora" na faixa de versao nova
    baixar_versao = Signal()
    #: "Agora nao" na faixa de versao nova
    dispensar_versao = Signal()

    def __init__(
        self,
        registry: AppRegistry,
        hub_store: HubStore,
        parent: QWidget | None = None,
        paths=None,
        config_avisos=None,
        empresa=None,
        novidade=None,
        carregar: bool = True,
    ) -> None:
        super().__init__(parent)
        self.registry = registry
        self.hub_store = hub_store
        self.paths = paths
        self.config_avisos = config_avisos or nucleo_avisos.Config()
        #: funcao que devolve os dados da empresa (o Hub le das preferencias)
        self.empresa = empresa
        #: funcao que devolve a versao nova ja conhecida (`core/versao.py`)
        self.novidade = novidade

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # a pagina rola inteira, cabecalho junto: a faixa de abertura e alta,
        # e presa no topo ela comeria um terco da tela de quem desce a lista
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.corpo = QWidget()
        pagina = QVBoxLayout(self.corpo)
        pagina.setContentsMargins(Space.xxl, Space.xl + 2, Space.xxl - 6, Space.xxl)
        pagina.setSpacing(Space.lg + 4)

        self.cabecalho = CabecalhoEmpresa()
        self.cabecalho.configurar.connect(self.configurar_empresa.emit)
        self.cabecalho.buscar.connect(self.buscar.emit)
        pagina.addWidget(self.cabecalho)

        self.empty = self._build_empty()
        pagina.addWidget(self.empty)

        self.coluna = QVBoxLayout()
        self.coluna.setContentsMargins(0, 0, 0, 0)
        self.coluna.setSpacing(Space.lg + 4)
        pagina.addLayout(self.coluna, 1)

        self.scroll.setWidget(self.corpo)
        root.addWidget(self.scroll, 1)

        # quem ja vai mostrar o Inicio logo em seguida (o Hub) pede para nao
        # carregar aqui: eram duas montagens seguidas, lendo sete bancos cada
        if carregar:
            self.refresh()

    def _build_empty(self) -> EmptyState:
        empty = EmptyState(
            "Nenhum aplicativo liberado",
            "Ative a sua licenca DumTech para liberar os aplicativos que voce comprou.",
            "key",
        )
        empty.setMinimumHeight(260)
        botao = Button("Ativar licenca", "key", "primary")
        botao.setMinimumHeight(40)
        botao.clicked.connect(self.ativar_licenca.emit)
        # quem ainda nao comprou precisa de uma saida daqui que nao seja a chave
        conhecer = Button("Conhecer os modulos", "cart", "ghost")
        conhecer.setMinimumHeight(40)
        conhecer.clicked.connect(self.adquirir.emit)
        caixa = QHBoxLayout()
        caixa.setSpacing(Space.sm)
        caixa.addStretch(1)
        caixa.addWidget(botao)
        caixa.addWidget(conhecer)
        caixa.addStretch(1)
        empty.layout().addLayout(caixa)
        empty.setVisible(False)
        return empty

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        self._limpar()
        self.registry.load()
        # o Inicio mostra SOMENTE o que a licenca liberou; o catalogo completo
        # (com o que ainda nao foi comprado) fica na tela "Licenca"
        disponiveis = self.registry.available()
        avisos = self._avisos(disponiveis)

        self.cabecalho.preencher(
            self._empresa_atual(), self.paths, len(disponiveis),
            len(avisos) if self.paths is not None and disponiveis else None,
        )
        self.cabecalho.setVisible(True)
        self.empty.setVisible(not disponiveis)

        # antes de tudo: programa desatualizado e o unico recado que vale
        # interromper a leitura do painel
        self._faixa_versao()

        # Anuncio NAO mora aqui. O Inicio e do trabalho do cliente: o que
        # precisa de atencao hoje. Oferta chega por pop-up (AnuncioDialog), uma
        # vez por anuncio - um bloco fixo mostrava a mesma coisa para sempre e
        # so roubava espaco. Quem nao tem licenca continua com saida para a
        # loja pelo "Conhecer os modulos" do estado vazio.
        if not disponiveis:
            self.coluna.addStretch(1)
            return

        self._secao_sinais(disponiveis)

        linha = QHBoxLayout()
        linha.setSpacing(Space.lg)
        atencao = self._secao_atencao(disponiveis, avisos)
        if atencao is not None:
            linha.addWidget(atencao, 3)
        continuar = self._secao_continuar(disponiveis)
        if continuar is not None:
            linha.addWidget(continuar, 2)
        if linha.count():
            self.coluna.addLayout(linha)
        else:
            linha.setParent(None)

        self._secao_catalogo(disponiveis)
        self.coluna.addStretch(1)

    def _empresa_atual(self):
        if callable(self.empresa):
            return self.empresa()
        return self.empresa

    def _avisos(self, disponiveis: list[AppEntry]) -> list:
        if self.paths is None:
            return []
        encontrados = []
        for entrada in disponiveis:
            encontrados += nucleo_avisos.coletar(
                entrada.module, self.paths, self.config_avisos
            )
        return nucleo_avisos.ordenar(encontrados)

    # ------------------------------------------------------------ sinais vitais
    def _secao_sinais(self, disponiveis: list[AppEntry]) -> None:
        """A vitrine: um numero por modulo, o mais importante primeiro."""
        if self.paths is None:
            return
        encontrados = []
        for entrada in disponiveis:
            encontrados += nucleo_indicadores.coletar(entrada.module, self.paths)
        if not encontrados:
            return

        vitrine = VitrineDeSinais()
        vitrine.abrir.connect(self._abrir_sinal)
        # a plataforma tambem tem o seu sinal: ele existe com um modulo ou com
        # sete, e e o que impede a vitrine de parecer pela metade no comeco
        encontrados = nucleo_indicadores.ordenar(encontrados) + [self._sinal_da_copia()]
        vitrine.preencher(encontrados)
        self.coluna.addWidget(vitrine)

    def _abrir_sinal(self, app_id: str) -> None:
        if app_id == SINAL_DA_PLATAFORMA:
            self.abrir_backup.emit()
            return
        self.open_app.emit(app_id)

    def _sinal_da_copia(self):
        """Quando foi a ultima copia de seguranca.

        E o unico numero da tela que nao vem de modulo nenhum - e o que a
        plataforma responde por conta propria.
        """
        from ...core import backup

        copias = backup.listar(backup.pasta_padrao(self.paths))
        ultima = copias[0].momento if copias else None
        if ultima is None:
            return nucleo_indicadores.Indicador(
                app_id=SINAL_DA_PLATAFORMA, rotulo="Copia de seguranca",
                valor="Nenhuma", detalhe="seus dados ainda nao tem copia",
                tom="warning", icone="shield", peso=-10,
            )
        dias = (date.today() - ultima.date()).days
        return nucleo_indicadores.Indicador(
            app_id=SINAL_DA_PLATAFORMA, rotulo="Copia de seguranca",
            valor="Hoje" if dias == 0 else fmt.data(ultima.date().isoformat()),
            detalhe=(f"{fmt.contagem(len(copias), 'copia', 'copias')} guardadas"
                     if dias <= 1 else f"a ultima foi ha {fmt.dias(dias)}"),
            tom="success" if dias <= 1 else "warning",
            icone="shield", peso=-10,
        )

    # ------------------------------------------------------------- o que urge
    def _secao_atencao(self, disponiveis: list[AppEntry], encontrados: list):
        """O que pede atencao hoje, numa lista - e o "tudo em dia" quando nao ha.

        Passando de seis, o resto fica na tela do proprio modulo, e o cartao
        diz quantos sao.
        """
        if self.paths is None:
            return None
        if not encontrados:
            return TudoEmDia(len(disponiveis))

        nomes = {e.app_id: e.manifest.short_name for e in disponiveis}
        painel = PainelDeAvisos()
        painel.abrir.connect(self.open_app.emit)
        painel.preencher(encontrados[:MAX_AVISOS], nomes,
                         sobrando=len(encontrados) - MAX_AVISOS)
        return painel

    # --------------------------------------------------------------- sistemas
    def _secao_continuar(self, disponiveis: list[AppEntry]):
        por_id = {e.app_id: e for e in disponiveis}
        recentes = [por_id[i] for i in self.hub_store.recent(MAX_CONTINUAR) if i in por_id]
        if len(recentes) < 2:
            return None  # com um aplicativo so, "continuar" nao ajuda ninguem

        painel = PainelContinuar()
        for entrada in recentes:
            aberto = self.hub_store.last_opened(entrada.app_id)
            cartao = ContinueCard(
                entrada.manifest,
                f"Aberto em {fmt.data_hora_curta(aberto)}" if aberto else "",
            )
            cartao.clicked.connect(self.open_app.emit)
            painel.adicionar(cartao)
        return painel

    # ------------------------------------------------------------ versao nova
    def _faixa_versao(self) -> None:
        """Uma faixa fina no topo: o que mudou e o botao para baixar."""
        aviso = self.novidade() if callable(self.novidade) else self.novidade
        if aviso is None:
            return

        card = Card()
        card.setProperty("tom", "accent")
        linha = QHBoxLayout()
        linha.setSpacing(Space.md)
        linha.addWidget(IconBadge("refresh", "accent", size=38, radius=12), 0,
                        Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = "Atualizacao importante do DumTech Hub" if aviso.obrigatoria \
            else f"Versao {aviso.versao} do DumTech Hub disponivel"
        textos.addWidget(label(titulo, "strong"))
        recado = label(aviso.notas or "Baixe a versao nova para receber as melhorias e as correcoes.",
                       "muted")
        recado.setWordWrap(True)
        textos.addWidget(recado)
        linha.addLayout(textos, 1)

        botoes = QVBoxLayout()
        botoes.setSpacing(Space.xs)
        baixar = Button("Baixar agora", "external", "primary")
        baixar.clicked.connect(self.baixar_versao.emit)
        botoes.addWidget(baixar)
        if not aviso.obrigatoria:     # obrigatoria fica ate a pessoa atualizar
            depois = Button("Agora nao", "", "ghost")
            depois.clicked.connect(self.dispensar_versao.emit)
            botoes.addWidget(depois)
        linha.addLayout(botoes)

        card.body.addLayout(linha)
        self.coluna.addWidget(card)

    # ------------------------------------------------------------------ ofertas
    def _botao_adquirir(self, variante: str = "ghost") -> Button:
        botao = Button("Adquirir novo produto", "cart", variante)
        botao.setToolTip("Abre a loja DumTech no navegador")
        botao.clicked.connect(self.adquirir.emit)
        return botao

    def _secao_catalogo(self, disponiveis: list[AppEntry]) -> None:
        # Agrupar por categoria so ajuda quando ha catalogo suficiente para
        # isso significar alguma coisa; com poucos aplicativos, os titulos
        # picotam a tela em grupos de dois e nao informam nada.
        if len(disponiveis) > LIMITE_AGRUPAMENTO:
            for indice, (categoria, entradas) in enumerate(self._por_categoria(disponiveis)):
                self.coluna.addLayout(self._titulo_de_secao(
                    categoria, len(entradas),
                    self._botao_adquirir() if indice == 0 else None,
                ))
                self.coluna.addWidget(self._grade(entradas))
        else:
            self.coluna.addLayout(self._titulo_de_secao(
                "Seus sistemas", len(disponiveis), self._botao_adquirir()
            ))
            self.coluna.addWidget(self._grade(sorted(
                disponiveis, key=lambda e: e.manifest.short_name.lower()
            )))

    @staticmethod
    def _titulo_de_secao(titulo: str, quantidade: int, acao=None) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setContentsMargins(0, Space.xs, 0, 0)
        linha.setSpacing(Space.sm)
        linha.addWidget(overline(titulo))
        linha.addWidget(label(fmt.contagem(quantidade, "aplicativo"), "dim"), 0,
                        Qt.AlignmentFlag.AlignBottom)
        linha.addStretch(1)
        if acao is not None:
            linha.addWidget(acao)
        return linha

    def _grade(self, entradas: list[AppEntry]) -> QWidget:
        """Os cartoes em um widget proprio: assim a grade ocupa a largura toda."""
        caixa = QWidget()
        grade = FlowLayout(caixa, spacing=Space.lg)
        for entrada in entradas:
            aberto = self.hub_store.last_opened(entrada.app_id)
            cartao = AppCard(
                entrada.manifest,
                f"Aberto em {fmt.data_hora_curta(aberto)}" if aberto else "",
            )
            cartao.clicked.connect(self.open_app.emit)
            grade.addWidget(cartao)
        return caixa

    @staticmethod
    def _por_categoria(entradas: list[AppEntry]) -> list[tuple[str, list[AppEntry]]]:
        grupos: dict[str, list[AppEntry]] = {}
        for entrada in entradas:
            grupos.setdefault(entrada.manifest.category, []).append(entrada)
        for lista in grupos.values():
            lista.sort(key=lambda e: e.manifest.short_name.lower())
        return sorted(grupos.items(), key=lambda par: (-len(par[1]), par[0].lower()))

    # ------------------------------------------------------------------ limpeza
    def _limpar(self) -> None:
        while self.coluna.count():
            item = self.coluna.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
                continue
            filho = item.layout() if item else None
            if filho is not None:
                self._limpar_layout(filho)

    def _limpar_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item is not None and item.layout() is not None:
                self._limpar_layout(item.layout())
        layout.setParent(None)
