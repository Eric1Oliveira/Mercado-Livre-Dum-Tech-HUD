"""O assistente de conta: quem ja usa migra aqui, e quem chega comeca por aqui.

Dois caminhos pela mesma tela:

* **quem ja usa** ve o convite, com "Agora nao". O painel da DumTech pode tirar o
  "Agora nao", mas nunca sem internet: criar conta precisa de rede, e a loja nao
  pode parar por isso;
* **quem acabou de ativar** a chave vai direto para a conta, sem convite.

Depois sao sempre os mesmos passos, nesta ordem: a conta do administrador, o
e-mail, a equipe e o fim. So a conta e obrigatoria. E uma PAGINA, nao um dialogo:
modal aberto na abertura do Hub trava a suite de testes.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ...core.acesso import (
    FUNCIONARIO,
    MODELOS,
    AcessoError,
    AcessoService,
    gerar_senha,
    permissoes_do_modelo,
    sugerir_login,
    validar_login,
    validar_senha,
)
from ...core.conta import email_valido
from ...ui import format as fmt
from ...ui import tasks
from ...ui.theme import Control, Space
from ...ui.widgets import form
from ...ui.widgets.buttons import Button
from ...ui.widgets.campo_senha import CampoCodigo, CampoSenha, MedidorDeSenha
from ...ui.widgets.common import IconBadge, label
from ...ui.widgets.pilha import Pilha
from ...ui.widgets.rolagem import Rolagem
from .acesso_comum import LARGURA_COLUNA, Cracha, FaixaDaMarca, _rotulo_claro, dizer, mensagem, tom_do_erro

PAGINA_CONVITE = 0
PAGINA_CONTA = 1
PAGINA_EMAIL = 2
PAGINA_EQUIPE = 3
PAGINA_PRONTO = 4

#: ordem real: e por isso que os passos sao numerados
PASSOS = ("Sua conta", "Seu e-mail", "Sua equipe", "Pronto")

CONVITE = (
    ("key", "Você é o administrador", "Escolha o seu login e a sua senha. Você decide quem entra e o que cada um vê."),
    ("users", "Cada funcionário com o seu acesso", "Marque os módulos e os avisos de cada pessoa. O celular fica só com você."),
    ("shield", "Senha esquecida tem volta", "O código para criar uma senha nova chega no seu e-mail."),
)


class AssistenteContaView(QWidget):
    """Criar a conta do administrador e montar a equipe."""

    #: terminou: a conta existe e a pessoa ja esta dentro
    concluido = Signal()
    #: "Agora nao": o Hub segue sem conta e pergunta na proxima abertura
    adiado = Signal()

    def __init__(self, acesso: AcessoService, dados=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.acesso = acesso
        #: funcao que devolve {"nome", "email", "computadores"} da loja
        self.dados = dados
        self.obrigatorio = False
        self._ocupado = False
        self._login_tocado = False
        self._login_equipe_tocado = False
        self.crachas: list[Cracha] = []

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        self.faixa = FaixaDaMarca()
        self.rotulos_passos = []
        for indice, nome in enumerate(PASSOS, 1):
            rotulo = _rotulo_claro(f"{indice}   {nome}", "strong", 150)
            self.faixa.miolo.addWidget(rotulo)
            self.rotulos_passos.append(rotulo)
        raiz.addWidget(self.faixa)

        corpo = QWidget()
        centro = QHBoxLayout(corpo)
        centro.setContentsMargins(Space.xl, Space.xl, Space.xl, Space.xl)
        centro.addStretch(1)
        self.paginas = Pilha()
        self.paginas.setFixedWidth(LARGURA_COLUNA)
        self.paginas.addWidget(self._pagina_convite())
        self.paginas.addWidget(self._pagina_conta())
        self.paginas.addWidget(self._pagina_email())
        self.paginas.addWidget(self._pagina_equipe())
        self.paginas.addWidget(self._pagina_pronto())
        centro.addWidget(self.paginas, 0, Qt.AlignmentFlag.AlignVCenter)
        centro.addStretch(1)
        raiz.addWidget(Rolagem(corpo), 1)

    # ---------------------------------------------------------------- montagem
    @staticmethod
    def _coluna(titulo: str, texto: str = "") -> tuple[QWidget, QVBoxLayout, QWidget]:
        # a pilha da a mesma altura a todos os passos (a do maior): sem as sobras
        # em volta, o passo curto espalharia o espaco entre as proprias linhas
        pagina = QWidget()
        fora = QVBoxLayout(pagina)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.addStretch(1)
        coluna = QVBoxLayout()
        coluna.setSpacing(Space.md)
        fora.addLayout(coluna)
        fora.addStretch(1)
        rotulo = label(titulo, "display")
        rotulo.setWordWrap(True)
        coluna.addWidget(rotulo)
        explica = label(texto, "muted")
        explica.setWordWrap(True)
        coluna.addWidget(explica)
        explica.setVisible(bool(texto))  # depois de ter pai: sem ele, viraria janela solta
        return pagina, coluna, explica

    @staticmethod
    def _aviso() -> QWidget:
        aviso = label("", "muted")
        aviso.setWordWrap(True)
        aviso.setVisible(False)
        return aviso

    @staticmethod
    def _botao(texto: str, icone: str, variante: str = "primary") -> Button:
        botao = Button(texto, icone, variante)
        botao.setMinimumHeight(Control.primary)
        return botao

    def _pagina_convite(self) -> QWidget:
        pagina, coluna, _ = self._coluna("Agora a sua loja tem contas")
        coluna.addSpacing(Space.xs)
        for icone, titulo, texto in CONVITE:
            linha = QHBoxLayout()
            linha.setSpacing(Space.md)
            linha.addWidget(IconBadge(icone, "accent", size=38, radius=12), 0, Qt.AlignmentFlag.AlignTop)
            textos = QVBoxLayout()
            textos.setSpacing(1)
            textos.addWidget(label(titulo, "strong"))
            frase = label(texto, "muted")
            frase.setWordWrap(True)
            textos.addWidget(frase)
            linha.addLayout(textos, 1)
            coluna.addLayout(linha)
        coluna.addSpacing(Space.xs)
        self.nota_convite = label("", "dim")
        self.nota_convite.setWordWrap(True)
        coluna.addWidget(self.nota_convite)

        acoes = QHBoxLayout()
        acoes.setSpacing(Space.sm)
        self.botao_agora_nao = self._botao("Agora não", "", "ghost")
        self.botao_agora_nao.clicked.connect(self.adiar)
        acoes.addWidget(self.botao_agora_nao)
        acoes.addStretch(1)
        self.botao_comecar = self._botao("Criar minha conta", "forward")
        self.botao_comecar.clicked.connect(self.ir_para_conta)
        acoes.addWidget(self.botao_comecar)
        coluna.addLayout(acoes)
        return pagina

    def _pagina_conta(self) -> QWidget:
        pagina, coluna, _ = self._coluna(
            "Crie a conta do administrador",
            "Você escolhe o login e a senha. O e-mail é o que recupera a senha se você esquecer.")
        self.campo_nome = form.texto("", "Como você quer ser chamado")
        self.campo_nome.textEdited.connect(self._sugerir_login)
        coluna.addWidget(form.campo("Seu nome", self.campo_nome))
        self.campo_login = form.texto("", "Sem espaços e sem acentos")
        self.campo_login.textEdited.connect(self._login_digitado)
        coluna.addWidget(form.campo("Login", self.campo_login))
        self.campo_email = form.texto("", "voce@suaempresa.com.br")
        coluna.addWidget(form.campo("E-mail", self.campo_email))
        self.campo_senha = CampoSenha("Pelo menos 8 caracteres")
        coluna.addWidget(form.campo("Senha", self.campo_senha))
        coluna.addWidget(MedidorDeSenha(self.campo_senha))
        self.campo_repetir = CampoSenha("Digite de novo")
        self.campo_repetir.returnPressed.connect(self.criar_conta)
        coluna.addWidget(form.campo("Repita a senha", self.campo_repetir))

        self.aviso_conta = self._aviso()
        coluna.addWidget(self.aviso_conta)

        acoes = QHBoxLayout()
        acoes.setSpacing(Space.sm)
        self.botao_depois_conta = self._botao("Continuar sem conta por enquanto", "", "ghost")
        self.botao_depois_conta.setVisible(False)
        self.botao_depois_conta.clicked.connect(self.adiado.emit)
        acoes.addWidget(self.botao_depois_conta)
        acoes.addStretch(1)
        self.botao_criar = self._botao("Criar conta", "check")
        self.botao_criar.clicked.connect(self.criar_conta)
        acoes.addWidget(self.botao_criar)
        coluna.addLayout(acoes)
        return pagina

    def _pagina_email(self) -> QWidget:
        pagina, coluna, self.texto_email = self._coluna("Confirme o seu e-mail", "Enviando o código...")
        self.campo_codigo = CampoCodigo()
        self.campo_codigo.returnPressed.connect(self.confirmar_email)
        coluna.addWidget(form.campo("Código do e-mail", self.campo_codigo))
        self.aviso_email = self._aviso()
        coluna.addWidget(self.aviso_email)

        acoes = QHBoxLayout()
        acoes.setSpacing(Space.sm)
        self.botao_email_depois = self._botao("Confirmar depois", "", "ghost")
        self.botao_email_depois.clicked.connect(self._ir_para_equipe)
        acoes.addWidget(self.botao_email_depois)
        self.botao_reenviar = self._botao("Enviar outro", "refresh", "ghost")
        self.botao_reenviar.clicked.connect(self._pedir_confirmacao)
        acoes.addWidget(self.botao_reenviar)
        acoes.addStretch(1)
        self.botao_confirmar = self._botao("Confirmar", "check")
        self.botao_confirmar.clicked.connect(self.confirmar_email)
        acoes.addWidget(self.botao_confirmar)
        coluna.addLayout(acoes)
        return pagina

    def _pagina_equipe(self) -> QWidget:
        pagina, coluna, _ = self._coluna(
            "Quem mais usa o Hub?",
            "Cada pessoa ganha um crachá com login e senha. No primeiro acesso, ela cria a própria senha.")
        self.equipe_nome = form.texto("", "Nome da pessoa")
        self.equipe_nome.textEdited.connect(self._sugerir_login_equipe)
        coluna.addWidget(form.campo("Nome", self.equipe_nome))
        self.equipe_login = form.texto("", "Sem espaços e sem acentos")
        self.equipe_login.textEdited.connect(self._login_equipe_digitado)
        self.equipe_senha = form.texto(gerar_senha(), "")
        coluna.addWidget(form.linha(form.campo("Login", self.equipe_login),
                                    form.campo("Senha inicial", self.equipe_senha)))
        self.equipe_funcao = form.escolha([(nome, nome) for nome in MODELOS], next(iter(MODELOS)))
        coluna.addWidget(form.campo("O que ela faz na loja", self.equipe_funcao))
        dica = label("A função só marca módulos e avisos. Ajuste pessoa por pessoa em Usuários e acessos.", "dim")
        dica.setWordWrap(True)
        coluna.addWidget(dica)

        self.aviso_equipe = self._aviso()
        coluna.addWidget(self.aviso_equipe)
        self.botao_adicionar = self._botao("Adicionar à equipe", "plus", "")
        self.botao_adicionar.clicked.connect(self.adicionar)
        coluna.addWidget(self.botao_adicionar)

        self.lista_crachas = QVBoxLayout()
        self.lista_crachas.setSpacing(Space.sm)
        coluna.addLayout(self.lista_crachas)

        acoes = QHBoxLayout()
        acoes.addStretch(1)
        self.botao_equipe_seguir = self._botao("Pular por enquanto", "forward")
        self.botao_equipe_seguir.clicked.connect(self._ir_para_pronto)
        acoes.addWidget(self.botao_equipe_seguir)
        coluna.addLayout(acoes)
        return pagina

    def _pagina_pronto(self) -> QWidget:
        pagina, coluna, _ = self._coluna("Tudo pronto")
        self.titulo_pronto = coluna.itemAt(0).widget()
        self.texto_pronto = label("", "body")
        self.texto_pronto.setWordWrap(True)
        coluna.addWidget(self.texto_pronto)
        dica = label("Você muda tudo isso quando quiser em Configurações, Usuários e acessos.", "dim")
        dica.setWordWrap(True)
        coluna.addWidget(dica)
        acoes = QHBoxLayout()
        acoes.addStretch(1)
        self.botao_abrir = self._botao("Abrir o Hub", "forward")
        self.botao_abrir.clicked.connect(self.concluido.emit)
        acoes.addWidget(self.botao_abrir)
        coluna.addLayout(acoes)
        return pagina

    # ------------------------------------------------------------------ estado
    def abrir(self, obrigatorio: bool = False, direto: bool = False) -> None:
        """Convite para quem ja usa; `direto` leva a conta (acabou de ativar)."""
        self.obrigatorio = obrigatorio
        loja = self.dados() if callable(self.dados) else {}
        self.campo_email.setText(str(loja.get("email") or ""))
        self.campo_nome.setText(str(loja.get("nome") or ""))
        self._login_tocado = False
        self._sugerir_login(self.campo_nome.text())
        self.campo_senha.clear()
        self.campo_repetir.clear()
        dizer(self.aviso_conta, "")
        self.botao_depois_conta.setVisible(False)

        self.botao_agora_nao.setVisible(not obrigatorio)
        self.nota_convite.setText(
            "Esta loja passou a usar contas para entrar no Hub. Leva cerca de 1 minuto, e nada "
            "do que já está no programa muda." if obrigatorio else
            "Leva cerca de 1 minuto, e nada do que já está no programa muda.")
        self._ir(PAGINA_CONTA if direto else PAGINA_CONVITE)

    def _ir(self, pagina: int) -> None:
        self.paginas.setCurrentIndex(pagina)
        if pagina == PAGINA_CONVITE:
            self.faixa.definir("Cada pessoa da loja com o seu acesso")
        else:
            self.faixa.definir("Vamos deixar a sua loja pronta")
        for indice, rotulo in enumerate(self.rotulos_passos):
            rotulo.setVisible(pagina != PAGINA_CONVITE)
            alfa = 255 if indice == pagina - 1 else 150
            rotulo.setStyleSheet(f"color: rgba(255, 255, 255, {alfa});")

    def _ocupar(self, ocupado: bool, *botoes) -> None:
        self._ocupado = ocupado
        for botao in botoes:
            botao.setEnabled(not ocupado)

    def adiar(self) -> None:
        if not self.obrigatorio:
            self.adiado.emit()

    def ir_para_conta(self) -> None:
        self._ir(PAGINA_CONTA)
        self.campo_login.setFocus()

    # -------------------------------------------------------------------- login
    def _login_digitado(self, _texto: str) -> None:
        self._login_tocado = True

    def _login_equipe_digitado(self, _texto: str) -> None:
        self._login_equipe_tocado = True

    def _sugerir_login(self, nome: str) -> None:
        if not self._login_tocado:
            self.campo_login.setText(sugerir_login(nome))

    def _sugerir_login_equipe(self, nome: str) -> None:
        if not self._login_equipe_tocado:
            self.equipe_login.setText(sugerir_login(nome))

    # -------------------------------------------------------------------- conta
    def _problema_na_conta(self) -> tuple[str, QWidget | None]:
        nome = self.campo_nome.text().strip()
        login = self.campo_login.text().strip().lower()
        senha = self.campo_senha.text()
        if len(nome) < 2:
            return "Digite o seu nome.", self.campo_nome
        problema = validar_login(login)
        if problema:
            return problema, self.campo_login
        if not email_valido(self.campo_email.text()):
            return "Confira o e-mail: é por ele que você recupera a senha.", self.campo_email
        problema = validar_senha(senha, login)
        if problema:
            return problema, self.campo_senha
        if senha != self.campo_repetir.text():
            return "As duas senhas não são iguais.", self.campo_repetir
        return "", None

    def criar_conta(self) -> None:
        if self._ocupado:
            return
        problema, campo = self._problema_na_conta()
        if problema:
            dizer(self.aviso_conta, problema, "warning")
            campo.setFocus()
            return
        nome = self.campo_nome.text().strip()
        login = self.campo_login.text().strip().lower()
        email = self.campo_email.text().strip().lower()
        senha = self.campo_senha.text()
        self._ocupar(True, self.botao_criar)
        dizer(self.aviso_conta, "Criando a sua conta...")

        def concluiu(resposta: dict) -> None:
            self._ocupar(False, self.botao_criar)
            try:
                self.acesso.aplicar(resposta)
            except AcessoError as erro:
                dizer(self.aviso_conta, str(erro), "danger")
                return
            self.campo_senha.clear()
            self.campo_repetir.clear()
            self._ir(PAGINA_EMAIL)
            self.campo_codigo.setFocus()
            self._pedir_confirmacao()

        def falhou(erro: Exception) -> None:
            self._ocupar(False, self.botao_criar)
            dizer(self.aviso_conta, mensagem(erro), tom_do_erro(erro))
            # sem internet ninguem cria conta: a loja nao pode parar por isso
            if isinstance(erro, AcessoError) and erro.codigo in ("sem_internet", "indisponivel"):
                self.botao_depois_conta.setVisible(True)

        tasks.executar(self, lambda: self.acesso.criar_primeiro(nome, login, email, senha), concluiu, falhou)

    # ------------------------------------------------------------------- e-mail
    def _pedir_confirmacao(self) -> None:
        dizer(self.texto_email, "Enviando o código...")

        def concluiu(email: str) -> None:
            dizer(self.texto_email, f"Enviamos um código para {email}. Ele vale por 10 minutos. "
                                    "Confira também o spam.")

        def falhou(erro: Exception) -> None:
            dizer(self.texto_email, "Não foi possível enviar o código agora. Você confirma depois, "
                                    "em Minha conta.", "warning")

        tasks.executar(self, self.acesso.pedir_confirmacao, concluiu, falhou)

    def confirmar_email(self) -> None:
        if self._ocupado:
            return
        codigo = self.campo_codigo.text().strip()
        if len(codigo) != 6:
            dizer(self.aviso_email, "Digite os 6 números que chegaram no e-mail.", "warning")
            return
        self._ocupar(True, self.botao_confirmar)
        dizer(self.aviso_email, "Conferindo...")

        def concluiu(resposta: dict) -> None:
            self._ocupar(False, self.botao_confirmar)
            self.acesso.guardar_documento(resposta.get("acesso_assinado"))
            dizer(self.aviso_email, "")
            self._ir_para_equipe()

        def falhou(erro: Exception) -> None:
            self._ocupar(False, self.botao_confirmar)
            dizer(self.aviso_email, mensagem(erro), tom_do_erro(erro))

        tasks.executar(self, lambda: self.acesso.confirmar_email(codigo), concluiu, falhou)

    # ------------------------------------------------------------------- equipe
    def _ir_para_equipe(self) -> None:
        self._ir(PAGINA_EQUIPE)
        self.equipe_nome.setFocus()

    def adicionar(self) -> None:
        if self._ocupado:
            return
        nome = self.equipe_nome.text().strip()
        login = self.equipe_login.text().strip().lower()
        senha = self.equipe_senha.text().strip()
        if len(nome) < 2:
            dizer(self.aviso_equipe, "Digite o nome da pessoa.", "warning")
            self.equipe_nome.setFocus()
            return
        problema = validar_login(login) or validar_senha(senha, login)
        if problema:
            dizer(self.aviso_equipe, problema, "warning")
            return
        funcao = str(self.equipe_funcao.currentData())
        modulos, avisos = permissoes_do_modelo(funcao)
        dados = {"nome": nome, "login": login, "email": "", "papel": FUNCIONARIO,
                 "modulos": list(modulos), "avisos": list(avisos), "ativo": True}
        self._ocupar(True, self.botao_adicionar)
        dizer(self.aviso_equipe, "Adicionando...")

        def concluiu(resposta: dict) -> None:
            self._ocupar(False, self.botao_adicionar)
            self.acesso.guardar_documento(resposta.get("acesso_assinado"))
            dizer(self.aviso_equipe, "")
            cracha = Cracha(nome, login, senha, funcao)
            self.crachas.append(cracha)
            self.lista_crachas.addWidget(cracha)
            self.equipe_nome.clear()
            self.equipe_login.clear()
            self.equipe_senha.setText(gerar_senha())
            self._login_equipe_tocado = False
            self.botao_equipe_seguir.setText("  Continuar")
            self.equipe_nome.setFocus()

        def falhou(erro: Exception) -> None:
            self._ocupar(False, self.botao_adicionar)
            dizer(self.aviso_equipe, mensagem(erro), tom_do_erro(erro))

        tasks.executar(self, lambda: self.acesso.salvar_usuario(dados, senha), concluiu, falhou)

    # -------------------------------------------------------------------- fim
    def _ir_para_pronto(self) -> None:
        loja = self.dados() if callable(self.dados) else {}
        usuario = self.acesso.usuario
        primeiro = usuario.nome.split()[0] if usuario and usuario.nome.split() else ""
        self.titulo_pronto.setText(f"Tudo pronto, {primeiro}" if primeiro else "Tudo pronto")
        linhas = ["Sua conta de administrador está ativa."]
        if self.crachas:
            linhas.append(f"{fmt.contagem(len(self.crachas), 'pessoa')} na equipe. Lembre de passar o acesso de cada uma.")
        outros = max(int(loja.get("computadores") or 1) - 1, 0)
        if outros:
            verbo = "vai" if outros == 1 else "vão"
            linhas.append(f"{fmt.contagem(outros, 'outro computador', 'outros computadores')} desta chave "
                          f"{verbo} pedir login na próxima vez que o Hub abrir.")
        self.texto_pronto.setText("\n".join(linhas))
        self._ir(PAGINA_PRONTO)
