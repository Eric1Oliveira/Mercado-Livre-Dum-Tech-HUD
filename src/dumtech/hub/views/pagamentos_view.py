"""Configuracoes > Pagamentos: a chave Pix e as formas do balcao, atras de um codigo.

E a unica secao das configuracoes que pede codigo - porque e a unica que decide
para onde vai o dinheiro. O resto continua aberto como sempre.

Duas paginas: **trancada** (pedir o codigo, digitar) e **liberada** (a chave e as
formas). A pagina liberada tranca sozinha quando o tempo acaba ou quando a pessoa
sai da secao. Sem internet a area nao abre, e a tela diz isso - o balcao, esse,
continua vendendo com a chave ja confirmada.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.pagamentos import FORMAS, PagamentosError, formas_ocultas, pix_confirmada
from ...core.pix import PixError
from ...core.pix import chave_valida as chave_pix_valida
from ...core.pix import tipo_chave as tipo_chave_pix
from ...ui import tasks
from ...ui.theme import Space
from ...ui.widgets import form
from ...ui.widgets.buttons import Button
from ...ui.widgets.common import Card, label, repolish, separator
from ...ui.widgets.confirmar import confirmar
from ...ui.widgets.pilha import Pilha

#: segundos ate poder pedir outro codigo
ESPERA_REENVIO = 60

LARGURA_TRANCADA = 520


def _dizer(alvo, texto: str, tom: str = "muted") -> None:
    alvo.setText(texto)
    alvo.setProperty("tone", tom)
    repolish(alvo)


class PagamentosView(QWidget):
    """A area protegida: trancada ate o codigo que chega no e-mail da licenca."""

    #: a chave Pix ou as formas mudaram - o balcao aberto precisa saber
    alterada = Signal()

    def __init__(self, service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._reenvio = 0
        self._ocupado = False
        #: o campo do codigo ja apareceu (o e-mail foi enviado)
        self._campo_aberto = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(Space.lg)

        self.paginas = Pilha()
        self.paginas.addWidget(self._pagina_trancada())
        self.paginas.addWidget(self._pagina_liberada())
        raiz.addWidget(self.paginas, 1)

        self._relogio = QTimer(self)
        self._relogio.setInterval(1000)
        self._relogio.timeout.connect(self._tique)

        self.refresh()

    # ============================================================ TRANCADA ==
    def _pagina_trancada(self) -> QWidget:
        pagina = QWidget()
        fora = QHBoxLayout(pagina)
        fora.setContentsMargins(0, Space.md, 0, 0)

        card = Card(padding=Space.xl)
        card.setMaximumWidth(LARGURA_TRANCADA)
        corpo = card.body
        corpo.setSpacing(Space.md)

        corpo.addWidget(label("Area protegida", "title"))
        explica = label(
            "A chave Pix decide para onde vai o dinheiro do balcao. Para ver ou "
            "mudar, confirme que e voce: enviamos um codigo para o e-mail da licenca.",
            "muted",
        )
        explica.setWordWrap(True)
        corpo.addWidget(explica)

        self.botao_enviar = Button("Enviar codigo por e-mail", "chat", "primary")
        self.botao_enviar.setMinimumHeight(40)
        self.botao_enviar.clicked.connect(self._pedir_codigo)
        corpo.addWidget(self.botao_enviar)

        # --- digitar o codigo (aparece depois que o e-mail sai)
        self.bloco_codigo = QWidget()
        bloco = QVBoxLayout(self.bloco_codigo)
        bloco.setContentsMargins(0, 0, 0, 0)
        bloco.setSpacing(Space.sm)
        self.codigo = QLineEdit()
        self.codigo.setMaxLength(6)
        self.codigo.setPlaceholderText("000000")
        self.codigo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.codigo.setMinimumHeight(46)
        fonte = self.codigo.font()
        fonte.setPointSizeF(15)
        fonte.setLetterSpacing(fonte.SpacingType.AbsoluteSpacing, 4)
        self.codigo.setFont(fonte)
        self.codigo.returnPressed.connect(self._entrar)
        bloco.addWidget(form.campo("Codigo do e-mail", self.codigo))

        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        self.botao_entrar = Button("Entrar", "check", "primary")
        self.botao_entrar.setMinimumHeight(38)
        self.botao_entrar.clicked.connect(self._entrar)
        linha.addWidget(self.botao_entrar, 1)
        self.botao_reenviar = Button("Reenviar", "refresh", "ghost")
        self.botao_reenviar.clicked.connect(self._pedir_codigo)
        linha.addWidget(self.botao_reenviar)
        bloco.addLayout(linha)
        corpo.addWidget(self.bloco_codigo)

        self.aviso_trancada = label("", "muted")
        self.aviso_trancada.setWordWrap(True)
        corpo.addWidget(self.aviso_trancada)

        corpo.addWidget(separator())
        self.rodape_trancada = label(
            "Perdeu o acesso a esse e-mail? Fale com a DumTech: o e-mail da licenca "
            "e trocado no cadastro, e o proximo codigo chega no novo endereco.",
            "dim",
        )
        self.rodape_trancada.setWordWrap(True)
        corpo.addWidget(self.rodape_trancada)

        fora.addWidget(card, 1, Qt.AlignmentFlag.AlignTop)
        fora.addStretch(0)
        return pagina

    # ============================================================ LIBERADA ==
    def _pagina_liberada(self) -> QWidget:
        pagina = QWidget()
        raiz = QVBoxLayout(pagina)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(Space.md)

        faixa = QHBoxLayout()
        self.estado = label("", "strong")
        faixa.addWidget(self.estado, 1)
        self.botao_trancar = Button("Trancar agora", "lock", "ghost")
        self.botao_trancar.clicked.connect(self.trancar)
        faixa.addWidget(self.botao_trancar)
        raiz.addLayout(faixa)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        dentro = QWidget()
        coluna = QVBoxLayout(dentro)
        coluna.setContentsMargins(0, 0, Space.sm, 0)
        coluna.setSpacing(Space.md)
        coluna.addWidget(self._card_pix())
        coluna.addWidget(self._card_formas())
        coluna.addStretch(1)
        area.setWidget(dentro)
        raiz.addWidget(area, 1)
        return pagina

    def _card_pix(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Chave Pix do balcao", "section"))
        card.body.addWidget(separator())
        self.pix_atual = label("", "body")
        self.pix_atual.setWordWrap(True)
        card.body.addWidget(self.pix_atual)

        self.pix_nova = form.texto("", "CPF, CNPJ, telefone, e-mail ou chave aleatoria")
        self.pix_nova.textChanged.connect(self._conferir_pix)
        self.pix_nova.returnPressed.connect(self._salvar_pix)
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        linha.addWidget(form.campo("Nova chave", self.pix_nova), 1)
        self.botao_salvar_pix = Button("Salvar chave", "check", "primary")
        self.botao_salvar_pix.clicked.connect(self._salvar_pix)
        linha.addWidget(form.campo(" ", self.botao_salvar_pix))
        card.body.addLayout(linha)

        self.aviso_pix = label("", "dim")
        self.aviso_pix.setWordWrap(True)
        card.body.addWidget(self.aviso_pix)

        self.botao_remover_pix = Button("Remover chave Pix", "trash", "ghost")
        self.botao_remover_pix.clicked.connect(self._remover_pix)
        card.body.addWidget(self.botao_remover_pix, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _card_formas(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Formas de pagamento no balcao", "section"))
        card.body.addWidget(separator())
        dica = label("Desmarque o que a loja nao aceita: some da tela de Receber.", "dim")
        dica.setWordWrap(True)
        card.body.addWidget(dica)

        grade = QGridLayout()
        grade.setHorizontalSpacing(Space.xl)
        grade.setVerticalSpacing(Space.sm)
        self.formas: dict[str, QCheckBox] = {}
        for indice, forma in enumerate(FORMAS):
            caixa = QCheckBox(forma)
            self.formas[forma] = caixa
            grade.addWidget(caixa, indice // 3, indice % 3)
        card.body.addLayout(grade)

        linha = QHBoxLayout()
        self.aviso_formas = label("", "dim")
        self.aviso_formas.setWordWrap(True)
        linha.addWidget(self.aviso_formas, 1)
        self.botao_formas = Button("Salvar formas", "check")
        self.botao_formas.clicked.connect(self._salvar_formas)
        linha.addWidget(self.botao_formas)
        card.body.addLayout(linha)
        return card

    # ============================================================== estado ==
    def refresh(self) -> None:
        if self.service.acesso is None:
            self._mostrar_trancada()
        else:
            self._mostrar_liberada()

    def trancar(self) -> None:
        self.service.trancar()
        self._campo_aberto = False
        self.codigo.clear()
        self.pix_nova.clear()
        self._mostrar_trancada()
        _dizer(self.aviso_trancada, "Area trancada.")

    def hideEvent(self, evento) -> None:  # noqa: N802 (Qt)
        # saiu da secao (nao so minimizou a janela): tranca
        if not evento.spontaneous() and self.service.liberado:
            self.trancar()
        super().hideEvent(evento)

    def _mostrar_trancada(self) -> None:
        self._relogio.stop()
        self.paginas.setCurrentIndex(0)
        pode = self.service.pode_usar
        aberto = self._campo_aberto
        self.bloco_codigo.setVisible(aberto)
        self.botao_enviar.setVisible(not aberto)
        self.botao_enviar.setEnabled(pode and not self._ocupado)
        if not pode:
            _dizer(self.aviso_trancada,
                   "Ative a licenca deste computador (em Licenca) para proteger os pagamentos.",
                   "warning")

    def _mostrar_liberada(self) -> None:
        self.paginas.setCurrentIndex(1)

        chave = pix_confirmada(self.service.settings)
        if chave:
            self.pix_atual.setText(f"Chave em uso: {chave}  ({tipo_chave_pix(chave) or 'chave'})")
        else:
            self.pix_atual.setText("Nenhuma chave cadastrada - o balcao nao mostra QR Code.")
        self.botao_remover_pix.setVisible(bool(chave))
        self._conferir_pix()

        ocultas = set(formas_ocultas(self.service.settings))
        for forma, caixa in self.formas.items():
            caixa.setChecked(forma not in ocultas)
        _dizer(self.aviso_formas, "")

        self._tique()
        self._relogio.start()

    def _tique(self) -> None:
        if self.service.acesso is None:
            self.trancar()
            _dizer(self.aviso_trancada, "O tempo acabou e a area foi trancada.")
            return
        minutos, segundos = divmod(self.service.segundos_restantes(), 60)
        _dizer(self.estado, f"Liberado  ·  tranca em {minutos:02d}:{segundos:02d}", "success")

    def _ocupar(self, ocupado: bool, *botoes) -> None:
        self._ocupado = ocupado
        for botao in botoes:
            botao.setEnabled(not ocupado)

    # ======================================================= acoes trancada ==
    def _pedir_codigo(self) -> None:
        if self._ocupado or self._reenvio > 0:
            return
        self._ocupar(True, self.botao_enviar, self.botao_reenviar)
        _dizer(self.aviso_trancada, "Enviando o codigo...")

        def concluiu(email: str) -> None:
            self._ocupar(False, self.botao_enviar)
            self._abrir_campo_codigo()
            _dizer(self.aviso_trancada,
                   f"Enviamos um codigo para {email or 'o e-mail da licenca'}. "
                   "Ele vale por 10 minutos. Confira tambem a caixa de spam.", "success")
            self._comecar_espera()

        def falhou(erro: Exception) -> None:
            self._ocupar(False, self.botao_enviar, self.botao_reenviar)
            _dizer(self.aviso_trancada, _mensagem(erro), "danger")

        tasks.executar(self, self.service.pedir_codigo, concluiu, falhou)

    def _abrir_campo_codigo(self) -> None:
        self._campo_aberto = True
        self._mostrar_trancada()
        self.codigo.setFocus()

    def _comecar_espera(self) -> None:
        self._reenvio = ESPERA_REENVIO
        self.botao_reenviar.setEnabled(False)

        def passo() -> None:
            self._reenvio -= 1
            if self._reenvio <= 0:
                self._espera.stop()
                self.botao_reenviar.setText("  Reenviar")
                self.botao_reenviar.setEnabled(True)
            else:
                self.botao_reenviar.setText(f"  Reenviar ({self._reenvio}s)")

        self._espera = QTimer(self)
        self._espera.setInterval(1000)
        self._espera.timeout.connect(passo)
        self._espera.start()

    def _entrar(self) -> None:
        if self._ocupado:
            return
        texto = self.codigo.text().strip()
        if not texto:
            _dizer(self.aviso_trancada, "Digite o codigo.", "warning")
            return
        self._ocupar(True, self.botao_entrar)
        _dizer(self.aviso_trancada, "Conferindo...")

        def concluiu(resposta: dict) -> None:
            self._ocupar(False, self.botao_entrar)
            try:
                self.service.aplicar_entrada(resposta)
            except PagamentosError as erro:
                _dizer(self.aviso_trancada, str(erro), "danger")
                return
            self.codigo.clear()
            self._campo_aberto = False
            _dizer(self.aviso_trancada, "")
            self._mostrar_liberada()

        def falhou(erro: Exception) -> None:
            self._ocupar(False, self.botao_entrar)
            _dizer(self.aviso_trancada, _mensagem(erro), "danger")

        tasks.executar(self, lambda: self.service.entrar(texto), concluiu, falhou)

    # ======================================================= acoes liberada ==
    def _conferir_pix(self, _texto: str = "") -> None:
        chave = self.pix_nova.text().strip()
        if not chave:
            _dizer(self.aviso_pix,
                   "A DumTech confirma a chave e manda um aviso para o e-mail da licenca "
                   "a cada troca. O QR Code so usa chave confirmada.")
        elif chave_pix_valida(chave):
            _dizer(self.aviso_pix, f"Chave reconhecida: {tipo_chave_pix(chave)}.", "success")
        else:
            _dizer(self.aviso_pix,
                   "Essa chave nao parece valida. Use CPF, CNPJ, telefone, e-mail ou "
                   "a chave aleatoria que o banco gerou.", "danger")

    def _salvar_pix(self) -> None:
        chave = self.pix_nova.text().strip()
        if not chave:
            _dizer(self.aviso_pix, "Digite a nova chave Pix.", "warning")
            return
        if not chave_pix_valida(chave):
            self._conferir_pix()
            return
        self._enviar_pix(chave)

    def _remover_pix(self) -> None:
        if not confirmar(self, "Remover a chave Pix?",
                         "O balcao deixa de mostrar o QR Code. Voce continua recebendo "
                         "em Pix, conferindo no aplicativo do banco.",
                         rotulo_ok="Remover chave"):
            return
        self._enviar_pix("")

    def _enviar_pix(self, chave: str) -> None:
        if self._ocupado:
            return
        self._ocupar(True, self.botao_salvar_pix, self.botao_remover_pix)
        _dizer(self.aviso_pix, "Confirmando com a DumTech...")

        def concluiu(resposta: dict) -> None:
            self._ocupar(False, self.botao_salvar_pix, self.botao_remover_pix)
            try:
                self.service.aplicar_pix(resposta)
            except PagamentosError as erro:
                _dizer(self.aviso_pix, str(erro), "danger")
                return
            self.pix_nova.clear()
            self._mostrar_liberada()
            _dizer(self.aviso_pix,
                   "Chave salva e confirmada. O balcao ja usa a nova chave, e o aviso "
                   "foi enviado para o e-mail da licenca." if chave else
                   "Chave removida. O balcao nao mostra mais o QR Code.", "success")
            self.alterada.emit()

        def falhou(erro: Exception) -> None:
            self._ocupar(False, self.botao_salvar_pix, self.botao_remover_pix)
            if isinstance(erro, PagamentosError) and erro.codigo == "sessao_vencida":
                self.trancar()
                _dizer(self.aviso_trancada, str(erro), "warning")
                return
            _dizer(self.aviso_pix, _mensagem(erro), "danger")

        tasks.executar(self, lambda: self.service.salvar_pix(chave), concluiu, falhou)

    def _salvar_formas(self) -> None:
        ocultas = [forma for forma, caixa in self.formas.items() if not caixa.isChecked()]
        try:
            self.service.salvar_formas(ocultas)
        except PagamentosError as erro:
            _dizer(self.aviso_formas, str(erro), "danger")
            if erro.codigo == "sessao_vencida":
                self.trancar()
            return
        _dizer(self.aviso_formas, "Formas salvas. O balcao ja mostra so as marcadas.", "success")
        self.alterada.emit()


def _mensagem(erro: Exception) -> str:
    if isinstance(erro, (PagamentosError, PixError)):
        return str(erro)
    return "Algo deu errado. Tente de novo."
