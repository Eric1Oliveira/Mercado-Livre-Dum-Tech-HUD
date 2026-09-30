"""Tela de licenca do Hub: ativar, verificar e ver o que esta liberado."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QMessageBox, QVBoxLayout, QWidget

from ...core.licensing import (
    LicenseError,
    LicenseService,
    License,
    SemInternet,
    machine_id,
    normalize_key,
)
from ...core.registry import AppRegistry
from ...ui import format as fmt
from ...ui import tasks
from ...ui.widgets.buttons import Button
from ...ui.widgets.rolagem import Rolagem
from ...ui.widgets.common import Card, IconBadge, Pill, label, repolish


class LicenseView(QWidget):
    """Ativacao da licenca e situacao dos aplicativos comprados."""

    #: emitido quando a licenca muda (ativou, verificou ou removeu)
    licenca_alterada = Signal()
    #: o cliente quer comprar outro modulo (o Hub abre a loja)
    adquirir = Signal()
    #: "Comprar" na linha de um modulo: a loja abre com ele ja no carrinho
    comprar = Signal(str)

    def __init__(
        self,
        license_service: LicenseService,
        registry: AppRegistry,
        parent: QWidget | None = None,
        conta=None,
    ) -> None:
        super().__init__(parent)
        self.license_service = license_service
        self.registry = registry
        #: funcao que devolve a conta DumTech deste computador (opcional)
        self.conta = conta
        self._entitlements_antes: tuple[str, ...] = ()

        # a pagina inteira rola: em monitor pequeno isto vira uma barra
        # de rolagem fina em vez de um pedaco da tela faltando
        fora = QVBoxLayout(self)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.setSpacing(0)
        corpo = QWidget()
        fora.addWidget(Rolagem(corpo), 1)
        raiz = QVBoxLayout(corpo)
        raiz.setContentsMargins(32, 28, 32, 24)
        raiz.setSpacing(18)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Licenca", "title"))
        self.subtitulo = label("", "subtitle")
        titulos.addWidget(self.subtitulo)
        raiz.addLayout(titulos)

        self.card_ativacao = self._montar_ativacao()
        raiz.addWidget(self.card_ativacao)

        self.card_dados = self._montar_dados()
        raiz.addWidget(self.card_dados)

        self.card_apps = Card()
        cabeca_apps = QHBoxLayout()
        cabeca_apps.addWidget(label("Aplicativos desta licenca", "section"), 1)
        self.botao_adquirir = Button("Adquirir novo produto", "cart", "primary")
        self.botao_adquirir.setToolTip("Abre a loja DumTech no navegador")
        self.botao_adquirir.clicked.connect(self.adquirir.emit)
        cabeca_apps.addWidget(self.botao_adquirir)
        self.card_apps.body.addLayout(cabeca_apps)
        self.lista_apps = QVBoxLayout()
        self.lista_apps.setSpacing(10)
        self.card_apps.body.addLayout(self.lista_apps)
        raiz.addWidget(self.card_apps)

        self.status = label("", "muted")
        self.status.setWordWrap(True)
        raiz.addWidget(self.status)

        raiz.addStretch(1)
        self.refresh()

    # ---------------------------------------------------------------- montagem
    def _montar_ativacao(self) -> Card:
        card = Card()
        linha = QHBoxLayout()
        linha.setSpacing(14)
        linha.addWidget(IconBadge("key", "accent", size=46, radius=14), 0, Qt.AlignmentFlag.AlignTop)

        coluna = QVBoxLayout()
        coluna.setSpacing(6)
        coluna.addWidget(label("Ativar licenca", "section"))
        explicacao = label(
            "Digite a chave que voce recebeu ao comprar os aplicativos DumTech. "
            "A internet e necessaria apenas neste momento: depois de ativada, a "
            "licenca fica gravada neste computador e o programa funciona offline.",
            "muted",
        )
        explicacao.setWordWrap(True)
        coluna.addWidget(explicacao)

        campos = QHBoxLayout()
        campos.setSpacing(10)
        self.campo_chave = QLineEdit()
        self.campo_chave.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self.campo_chave.setMaxLength(19)
        self.campo_chave.setMinimumWidth(240)
        self.campo_chave.textEdited.connect(self._formatar_chave)
        self.campo_chave.returnPressed.connect(self.ativar)
        campos.addWidget(self.campo_chave, 2)

        self.botao_ativar = Button("Ativar", "check", "primary")
        self.botao_ativar.setMinimumHeight(38)
        self.botao_ativar.clicked.connect(self.ativar)
        campos.addWidget(self.botao_ativar)
        campos.addStretch(1)
        coluna.addLayout(campos)

        linha.addLayout(coluna, 1)
        card.body.addLayout(linha)
        return card

    def _montar_dados(self) -> Card:
        card = Card()
        cabecalho = QHBoxLayout()
        cabecalho.addWidget(label("Licenca deste computador", "section"), 1)

        self.botao_verificar = Button("Verificar licenca", "refresh")
        self.botao_verificar.setToolTip(
            "Consulta a DumTech de novo - use depois de comprar um novo aplicativo"
        )
        self.botao_verificar.clicked.connect(self.verificar)
        cabecalho.addWidget(self.botao_verificar)

        self.botao_remover = Button("Trocar chave", "close", "ghost")
        self.botao_remover.setToolTip("Remove a licenca deste computador e libera a vaga")
        self.botao_remover.clicked.connect(self.remover)
        cabecalho.addWidget(self.botao_remover)
        card.body.addLayout(cabecalho)

        self.grade = QGridLayout()
        self.grade.setHorizontalSpacing(28)
        self.grade.setVerticalSpacing(14)
        card.body.addLayout(self.grade)
        return card

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        atual = self.license_service.reload()
        ativa = atual.ativa

        self.card_ativacao.setVisible(not ativa)
        self.card_dados.setVisible(ativa)
        self.card_apps.setVisible(ativa)

        if ativa and atual.bloqueio:
            # a chave continua aqui: quando a DumTech reativar, "Verificar" devolve tudo
            self.subtitulo.setText(
                str(atual.extras.get("mensagem") or "A DumTech bloqueou esta licenca.")
            )
        elif ativa:
            total = len(atual.entitlements)
            plural = "aplicativo liberado" if total == 1 else "aplicativos liberados"
            self.subtitulo.setText(f"{atual.customer}  -  {total} {plural}")
        elif atual.is_expired:
            self.subtitulo.setText("A licenca deste computador venceu")
        else:
            self.subtitulo.setText("Nenhuma licenca ativada neste computador")

        self._preencher_dados(atual)
        self._preencher_apps(atual)

    def _preencher_dados(self, atual: License) -> None:
        while self.grade.count():
            item = self.grade.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        origem = "Instalacao local (desenvolvimento)" if atual.is_local else "DumTech online"
        linhas = [
            ("Chave", atual.key or "-"),
            ("Cliente", atual.customer or "-"),
            ("Computador", atual.machine or machine_id()),
            ("Ativada em", fmt.data_hora(atual.activated_at)),
            ("Ultima verificacao", fmt.data_hora(atual.last_check)),
            ("Validade", self._validade(atual)),
            ("Origem", origem),
            ("Computadores", f"{atual.used_machines} de {atual.max_machines}"),
            ("Conta DumTech", self._conta_atual() or "-"),
        ]
        for indice, (chave, valor) in enumerate(linhas):
            linha, coluna = divmod(indice, 2)
            caixa = QVBoxLayout()
            caixa.setSpacing(2)
            caixa.addWidget(label(chave.upper(), "dim"))
            caixa.addWidget(label(str(valor), "strong"))
            bloco = QWidget()
            bloco.setLayout(caixa)
            self.grade.addWidget(bloco, linha, coluna)

    def _conta_atual(self) -> str:
        """O e-mail com que este computador se cadastrou (se ja se cadastrou)."""
        if self.conta is None:
            return ""
        conta = self.conta() if callable(self.conta) else self.conta
        return getattr(conta, "email", "") or ""

    @staticmethod
    def _validade(atual: License) -> str:
        """Prazo e plano na mesma linha: 'Assinatura ate 31/12/2027'."""
        if not atual.expires_at:
            return "Vitalicia" if atual.tipo == "vitalicia" else "Sem prazo"
        quando = fmt.data(atual.expires_at)
        if atual.tipo == "assinatura":
            return f"Assinatura ate {quando}"
        if atual.tipo == "teste":
            return f"Teste ate {quando}"
        return quando

    def _preencher_apps(self, atual: License) -> None:
        while self.lista_apps.count():
            item = self.lista_apps.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        for entrada in self.registry.entries:
            app = entrada.app_id
            comprado = app in atual.entitlements
            em_teste = atual.teste_ativo(app)
            linha = QWidget()
            caixa = QHBoxLayout(linha)
            caixa.setContentsMargins(0, 0, 0, 0)
            caixa.setSpacing(12)
            cor = entrada.manifest.accent if (comprado or em_teste) else "text_dim"
            caixa.addWidget(IconBadge(entrada.manifest.icon, cor, size=34, radius=10))
            nome = label(f"{entrada.manifest.name}   ({entrada.manifest.license_code})", "strong")
            caixa.addWidget(nome, 1)

            if comprado:
                caixa.addWidget(Pill("Liberado", "success"))
            else:
                # quem nao tem: experimenta de graca ou compra, na mesma linha
                if em_teste:
                    dias = atual.dias_de_teste(app)
                    caixa.addWidget(Pill(f"Teste gratis  ·  {fmt.contagem(dias, 'dia', 'dias')}", "accent"))
                elif atual.teste_acabou(app):
                    caixa.addWidget(Pill("Teste encerrado", "muted"))
                elif atual.ativa and not atual.bloqueio:
                    testar = Button("Testar 7 dias gratis", "", "ghost")
                    testar.clicked.connect(lambda _=False, a=app: self.testar(a))
                    caixa.addWidget(testar)
                botao = Button("Comprar", "cart", "primary" if em_teste else "")
                botao.clicked.connect(lambda _=False, c=entrada.manifest.license_code: self.comprar.emit(c))
                caixa.addWidget(botao)
            self.lista_apps.addWidget(linha)

        if not self.registry.entries:
            self.lista_apps.addWidget(label("Nenhum aplicativo instalado.", "muted"))

    # ------------------------------------------------------------------ acoes
    def _formatar_chave(self, texto: str) -> None:
        formatada = normalize_key(texto)
        if formatada != texto:
            self.campo_chave.setText(formatada)
            self.campo_chave.setCursorPosition(len(formatada))

    def _mostrar_aviso(self, texto: str, tom: str = "muted") -> None:
        self.status.setText(texto)
        self.status.setProperty("tone", tom)
        repolish(self.status)

    def _ocupado(self, ocupado: bool, mensagem: str = "") -> None:
        for botao in (self.botao_ativar, self.botao_verificar, self.botao_remover):
            botao.setEnabled(not ocupado)
        self.campo_chave.setEnabled(not ocupado)
        if mensagem:
            self._mostrar_aviso(mensagem, "accent")

    def ativar(self) -> None:
        chave = normalize_key(self.campo_chave.text())
        if not chave:
            self._mostrar_aviso("Digite a chave da licenca.", "warning")
            return

        self._ocupado(True, "Falando com a DumTech...")
        tasks.executar(
            self,
            lambda: self.license_service.activate(chave),
            self._ativacao_concluida,
            self._falha,
        )

    def testar(self, app_id: str) -> None:
        """Libera 7 dias gratis do modulo. Precisa de internet so agora."""
        self._testando = app_id
        self._ocupado(True, f"Liberando o teste gratis de {self._nome_do_app(app_id)}...")
        tasks.executar(self, lambda: self.license_service.iniciar_teste(app_id),
                       self._teste_liberado, self._falha)

    def _teste_liberado(self, licenca: License) -> None:
        app = getattr(self, "_testando", "")
        self._ocupado(False)
        self.refresh()
        self.licenca_alterada.emit()
        if licenca.teste_ativo(app):
            self._mostrar_aviso(
                f"Pronto: {self._nome_do_app(app)} liberado por 7 dias. Ele ja esta na barra de cima. "
                "Gostou? O botao Comprar fica aqui e dentro do modulo.", "success")
        else:
            self._mostrar_aviso("O servidor aceitou, mas o teste ainda nao chegou. Clique em "
                                "Verificar licenca em instantes.", "warning")

    def verificar(self) -> None:
        self._entitlements_antes = tuple(self.license_service.current.entitlements)
        self._ocupado(True, "Consultando a DumTech...")
        tasks.executar(self, self.license_service.verify, self._verificacao_concluida, self._falha)

    def remover(self) -> None:
        atual = self.license_service.current
        resposta = QMessageBox.question(
            self,
            "Trocar chave",
            f"Remover a licenca {atual.key} deste computador?\n\n"
            "Os aplicativos ficarao bloqueados ate uma nova ativacao. "
            "Os dados ja cadastrados continuam guardados no computador.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        self._ocupado(True, "Removendo a licenca...")
        tasks.executar(
            self, self.license_service.deactivate, self._remocao_concluida, self._falha_remocao
        )

    # --------------------------------------------------------------- respostas
    def _ativacao_concluida(self, licenca: License) -> None:
        self._ocupado(False)
        self.campo_chave.clear()
        total = len(licenca.entitlements)
        self._mostrar_aviso(
            f"Licenca ativada para {licenca.customer}: {total} aplicativo(s) liberado(s).",
            "success",
        )
        self.refresh()
        self.licenca_alterada.emit()

    def _verificacao_concluida(self, licenca: License) -> None:
        anteriores = self._entitlements_antes
        novos = [app for app in licenca.entitlements if app not in anteriores]
        perdidos = [app for app in anteriores if app not in licenca.entitlements]

        self._ocupado(False)
        self.refresh()
        self.licenca_alterada.emit()

        if novos:
            nomes = ", ".join(self._nome_do_app(app) for app in novos)
            self._mostrar_aviso(f"Licenca conferida. Liberado agora: {nomes}.", "success")
        elif perdidos:
            nomes = ", ".join(self._nome_do_app(app) for app in perdidos)
            self._mostrar_aviso(f"Licenca conferida. Nao esta mais liberado: {nomes}.", "warning")
        else:
            total = len(licenca.entitlements)
            self._mostrar_aviso(
                f"Licenca conferida com a DumTech: {total} aplicativo(s) liberado(s). "
                "Nada mudou desde a ultima vez.",
                "success",
            )

    def _nome_do_app(self, app_id: str) -> str:
        entrada = self.registry.get(app_id)
        return entrada.manifest.short_name if entrada else app_id

    def _remocao_concluida(self, _resultado) -> None:
        self._ocupado(False)
        self._mostrar_aviso("Licenca removida deste computador.", "warning")
        self.refresh()
        self.licenca_alterada.emit()

    def _falha(self, erro: Exception) -> None:
        self._ocupado(False)
        self._mostrar_aviso(str(erro), "warning" if isinstance(erro, SemInternet) else "danger")
        if not isinstance(erro, LicenseError):
            QMessageBox.warning(self, "Nao foi possivel validar a licenca", str(erro))

    def _falha_remocao(self, erro: Exception) -> None:
        self._ocupado(False)
        resposta = QMessageBox.question(
            self,
            "Nao foi possivel avisar a DumTech",
            f"{erro}\n\nRemover a licenca somente deste computador mesmo assim?\n"
            "(a vaga continuara ocupada ate voce falar com a DumTech)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta == QMessageBox.StandardButton.Yes:
            self.license_service.deactivate(liberar_vaga=False)
            self.refresh()
            self.licenca_alterada.emit()
