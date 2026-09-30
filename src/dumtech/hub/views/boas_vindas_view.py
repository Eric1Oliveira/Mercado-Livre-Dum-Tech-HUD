"""Primeiro acesso: quem e voce, e qual e a sua chave.

Dois passos, um de cada vez:

1. **Quem e voce** - nome e e-mail. Vao para a secao ``empresa`` do
   ``hub.json`` (a mesma que assina os comprovantes, para ninguem digitar duas
   vezes a mesma coisa) e, em segundo plano, para o servidor da DumTech.
2. **Sua chave** - a ativacao da licenca, com a saida "ainda nao tenho chave"
   para quem esta conhecendo o programa.

Regras que sustentam a tela:

* **nenhum passo espera a internet.** O cadastro segue em segundo plano; se nao
  chegar, fica pendente e o Hub tenta de novo na proxima abertura;
* e uma PAGINA, nao um dialogo modal: modal aberto na abertura do Hub trava a
  suite de testes (e o cliente que so quer olhar o programa);
* quem ja tem licenca nunca ve esta tela.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ...core.conta import ContaService, email_valido
from ...core.empresa import Empresa
from ...core.licensing import LicenseError, LicenseService, SemInternet, normalize_key
from ...ui import tasks
from ...ui.theme import Space
from ...ui.widgets import form
from ...ui.widgets.buttons import Button
from ...ui.widgets.rolagem import Rolagem
from ...ui.widgets.common import Card, IconBadge, label, repolish
from ...ui.widgets.pilha import Pilha

PASSO_CADASTRO = 0
PASSO_CHAVE = 1


class BoasVindasView(QWidget):
    """A porta de entrada do cliente."""

    #: o primeiro acesso terminou (com ou sem chave): pode abrir o Inicio
    concluido = Signal()
    #: uma licenca foi ativada aqui - o Hub precisa reavaliar os modulos
    licenca_alterada = Signal()

    def __init__(
        self,
        settings,
        license_service: LicenseService,
        conta_service: ContaService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.license_service = license_service
        self.conta_service = conta_service or ContaService(settings)

        # a pagina inteira rola: em monitor pequeno isto vira uma barra
        # de rolagem fina em vez de um pedaco da tela faltando
        fora = QVBoxLayout(self)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.setSpacing(0)
        corpo = QWidget()
        fora.addWidget(Rolagem(corpo), 1)
        raiz = QVBoxLayout(corpo)
        raiz.setContentsMargins(Space.xxl, Space.xl, Space.xxl, Space.xl)
        raiz.setSpacing(Space.lg)

        self.passos = Pilha()
        self.passos.addWidget(self._passo_cadastro())
        self.passos.addWidget(self._passo_chave())
        raiz.addStretch(1)
        raiz.addWidget(self.passos, 0, Qt.AlignmentFlag.AlignHCenter)
        raiz.addStretch(2)

        self._preencher()

    # ---------------------------------------------------------------- montagem
    def _moldura(self, titulo: str, explicacao: str, icone: str) -> tuple[QWidget, QVBoxLayout]:
        card = Card()
        # largura minima junto com a maxima: sem ela o cartao nasce do tamanho
        # do sizeHint e a explicacao quebra numa coluna fina de tres linhas
        card.setMinimumWidth(560)
        card.setMaximumWidth(620)

        cabeca = QHBoxLayout()
        cabeca.setSpacing(Space.md)
        cabeca.addWidget(IconBadge(icone, "accent", size=46, radius=14),
                         0, Qt.AlignmentFlag.AlignTop)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(label(titulo, "title"))
        frase = label(explicacao, "muted")
        frase.setWordWrap(True)
        textos.addWidget(frase)
        cabeca.addLayout(textos, 1)
        card.body.addLayout(cabeca)

        corpo = QVBoxLayout()
        corpo.setSpacing(Space.md)
        card.body.addLayout(corpo)

        # A pilha da a MESMA altura aos dois passos (a do maior). Sem prender o
        # cartao no topo, o passo mais curto espalha a sobra por dentro - e
        # abre um vao entre o titulo e a explicacao.
        pagina = QWidget()
        caixa = QVBoxLayout(pagina)
        caixa.setContentsMargins(0, 0, 0, 0)
        caixa.addWidget(card, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        caixa.addStretch(1)
        return pagina, corpo

    def _passo_cadastro(self) -> QWidget:
        pagina, corpo = self._moldura(
            "Bem-vindo a DumTech",
            "Para comecar, diga quem voce e. Usamos esses dados para identificar "
            "a sua conta e para assinar os comprovantes que voce emite.",
            "user",
        )

        self.campo_nome = form.texto("", "Nome da sua empresa ou o seu nome")
        corpo.addWidget(form.campo("Nome", self.campo_nome))

        self.campo_email = form.texto("", "voce@suaempresa.com.br")
        corpo.addWidget(form.campo("E-mail", self.campo_email))

        self.campo_telefone = form.texto("", "(00) 00000-0000")
        corpo.addWidget(form.campo("Telefone (opcional)", self.campo_telefone))

        self.aviso_cadastro = label("", "muted")
        self.aviso_cadastro.setWordWrap(True)
        self.aviso_cadastro.setVisible(False)  # vazio, ele so abriria um buraco
        corpo.addWidget(self.aviso_cadastro)

        acoes = QHBoxLayout()
        acoes.addStretch(1)
        self.botao_continuar = Button("Continuar", "check", "primary")
        self.botao_continuar.setMinimumHeight(40)
        self.botao_continuar.clicked.connect(self.continuar)
        acoes.addWidget(self.botao_continuar)
        corpo.addLayout(acoes)

        for campo in (self.campo_nome, self.campo_email, self.campo_telefone):
            campo.returnPressed.connect(self.continuar)
        return pagina

    def _passo_chave(self) -> QWidget:
        pagina, corpo = self._moldura(
            "Sua chave DumTech",
            "Digite a chave que voce recebeu na compra. A internet e necessaria "
            "apenas agora: depois disso o programa funciona offline.",
            "key",
        )

        self.campo_chave = form.texto("", "XXXX-XXXX-XXXX-XXXX")
        self.campo_chave.setMaxLength(19)
        self.campo_chave.textEdited.connect(self._formatar_chave)
        self.campo_chave.returnPressed.connect(self.ativar)
        corpo.addWidget(form.campo("Chave da licenca", self.campo_chave))

        self.aviso_chave = label("", "muted")
        self.aviso_chave.setWordWrap(True)
        self.aviso_chave.setVisible(False)
        corpo.addWidget(self.aviso_chave)

        acoes = QHBoxLayout()
        self.botao_sem_chave = Button("Ainda nao tenho chave", "forward", "ghost")
        self.botao_sem_chave.setToolTip(
            "Conheca o programa e veja os modulos DumTech; voce ativa quando comprar"
        )
        self.botao_sem_chave.clicked.connect(self.pular)
        acoes.addWidget(self.botao_sem_chave)
        acoes.addStretch(1)

        self.botao_ativar = Button("Ativar", "check", "primary")
        self.botao_ativar.setMinimumHeight(40)
        self.botao_ativar.clicked.connect(self.ativar)
        acoes.addWidget(self.botao_ativar)
        corpo.addLayout(acoes)
        return pagina

    # ------------------------------------------------------------------- dados
    def _preencher(self) -> None:
        """Reaproveita o que ja estiver preenchido (reinstalacao, por exemplo)."""
        empresa = Empresa.carregar(self.settings)
        self.campo_nome.setText(empresa.nome)
        self.campo_email.setText(empresa.email or self.conta_service.atual.email)
        self.campo_telefone.setText(empresa.telefone_formatado)

    # ------------------------------------------------------------------ acoes
    def continuar(self) -> None:
        nome = self.campo_nome.text().strip()
        email = self.campo_email.text().strip()

        if not nome:
            self._dizer(self.aviso_cadastro, "Digite o seu nome ou o da sua empresa.", "warning")
            self.campo_nome.setFocus()
            return
        if not email_valido(email):
            self._dizer(self.aviso_cadastro, "Confira o e-mail digitado.", "warning")
            self.campo_email.setFocus()
            return

        # a identidade da empresa e do cliente sao a mesma coisa aqui: assim os
        # comprovantes ja saem com nome, sem ninguem repetir o cadastro
        empresa = Empresa.carregar(self.settings)
        empresa.nome = empresa.nome or nome
        empresa.email = email
        if self.campo_telefone.text().strip():
            empresa.telefone = self.campo_telefone.text()
        empresa.salvar(self.settings)

        # o cadastro segue em segundo plano: o cliente nao espera a internet
        tasks.executar(
            self,
            lambda: self.conta_service.registrar(nome, email),
            lambda _conta: None,
            lambda _erro: None,
        )
        self.passos.setCurrentIndex(PASSO_CHAVE)
        self.campo_chave.setFocus()

    def pular(self) -> None:
        self.concluido.emit()

    def ativar(self) -> None:
        chave = normalize_key(self.campo_chave.text())
        if not chave:
            self._dizer(self.aviso_chave, "Digite a chave da licenca.", "warning")
            return

        self._ocupado(True)
        self._dizer(self.aviso_chave, "Falando com a DumTech...", "accent")
        tasks.executar(
            self,
            lambda: self.license_service.activate(chave),
            self._ativacao_concluida,
            self._falha,
        )

    # --------------------------------------------------------------- respostas
    def _ativacao_concluida(self, licenca) -> None:
        self._ocupado(False)
        self.licenca_alterada.emit()
        self.concluido.emit()

    def _falha(self, erro: Exception) -> None:
        self._ocupado(False)
        tom = "warning" if isinstance(erro, (SemInternet, LicenseError)) else "danger"
        self._dizer(self.aviso_chave, str(erro), tom)

    # ------------------------------------------------------------------ apoio
    def _formatar_chave(self, texto: str) -> None:
        formatada = normalize_key(texto)
        if formatada != texto:
            self.campo_chave.setText(formatada)
            self.campo_chave.setCursorPosition(len(formatada))

    def _ocupado(self, ocupado: bool) -> None:
        for botao in (self.botao_ativar, self.botao_sem_chave):
            botao.setEnabled(not ocupado)
        self.campo_chave.setEnabled(not ocupado)

    @staticmethod
    def _dizer(alvo, texto: str, tom: str = "muted") -> None:
        alvo.setText(texto)
        alvo.setProperty("tone", tom)
        alvo.setVisible(bool(texto))
        repolish(alvo)
