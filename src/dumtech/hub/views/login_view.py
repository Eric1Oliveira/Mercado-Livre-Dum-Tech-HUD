"""A porta do Hub: quem vai usar agora, esqueci a senha e a primeira senha.

Quatro passos na mesma pagina:

* **entrar** - as pessoas que ja usaram este computador em um clique, ou login e
  senha. Funciona sem internet para quem ja entrou aqui;
* **esqueci** - o login, para mandar o codigo;
* **codigo** - os 6 numeros do e-mail e a senha nova;
* **primeira senha** - quem recebeu uma senha de outra pessoa cria a propria.

E uma PAGINA, nao um dialogo modal: modal aberto na abertura do Hub trava a suite
de testes.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ...core.acesso import AcessoError, AcessoService, validar_senha
from ...ui import tasks
from ...ui.theme import Control, Space
from ...ui.widgets import form
from ...ui.widgets.buttons import Button
from ...ui.widgets.campo_senha import CampoCodigo, CampoSenha, MedidorDeSenha
from ...ui.widgets.common import label
from ...ui.widgets.pilha import Pilha
from ...ui.widgets.rolagem import Rolagem
from .acesso_comum import LARGURA_COLUNA, BotaoPessoa, FaixaDaMarca, dizer, mensagem, tom_do_erro

PAGINA_ENTRAR = 0
PAGINA_ESQUECI = 1
PAGINA_CODIGO = 2
PAGINA_TROCAR = 3


class _Link(QPushButton):
    """Texto clicavel: um caminho alternativo, nao a acao da tela."""

    def __init__(self, texto: str, parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("variant", "ghost")


class LoginView(QWidget):
    """Quem esta chegando no computador."""

    #: a pessoa entrou: o Hub monta as abas dela
    entrou = Signal()
    #: este computador saiu da chave: so ativando de novo
    ativar_licenca = Signal()

    def __init__(self, acesso: AcessoService, empresa=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.acesso = acesso
        #: funcao que devolve o nome da loja (muda se o dono renomear)
        self.empresa = empresa
        self._senha_recebida = ""
        self._ocupado = False

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        self.faixa = FaixaDaMarca()
        raiz.addWidget(self.faixa)

        corpo = QWidget()
        centro = QHBoxLayout(corpo)
        centro.setContentsMargins(Space.xl, Space.xl, Space.xl, Space.xl)
        centro.addStretch(1)
        self.paginas = Pilha()
        self.paginas.setFixedWidth(LARGURA_COLUNA)
        self.paginas.addWidget(self._pagina_entrar())
        self.paginas.addWidget(self._pagina_esqueci())
        self.paginas.addWidget(self._pagina_codigo())
        self.paginas.addWidget(self._pagina_trocar())
        centro.addWidget(self.paginas, 0, Qt.AlignmentFlag.AlignVCenter)
        centro.addStretch(1)
        raiz.addWidget(Rolagem(corpo), 1)

        self.preparar()

    # ---------------------------------------------------------------- montagem
    @staticmethod
    def _coluna(titulo: str, texto: str = "") -> tuple[QWidget, QVBoxLayout, QWidget, QWidget]:
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
        return pagina, coluna, rotulo, explica

    @staticmethod
    def _aviso() -> QWidget:
        aviso = label("", "muted")
        aviso.setWordWrap(True)
        aviso.setVisible(False)  # vazio, ele so abriria um buraco
        return aviso

    def _pagina_entrar(self) -> QWidget:
        pagina, coluna, self.titulo_entrar, self.texto_entrar = self._coluna("Entre com a sua conta")

        self.caixa_pessoas = QWidget()
        self.linha_pessoas = QHBoxLayout(self.caixa_pessoas)
        self.linha_pessoas.setContentsMargins(0, Space.xs, 0, Space.xs)
        self.linha_pessoas.setSpacing(Space.xs)
        self.linha_pessoas.addStretch(1)
        coluna.addWidget(self.caixa_pessoas)
        self._pessoas: list[BotaoPessoa] = []

        self.campo_login = form.texto("", "O login que você recebeu")
        self.campo_login.setMinimumHeight(Control.primary)
        self.campo_login.returnPressed.connect(self._focar_senha)
        coluna.addWidget(form.campo("Login", self.campo_login))

        self.campo_senha = CampoSenha("Sua senha")
        self.campo_senha.returnPressed.connect(self.entrar)
        coluna.addWidget(form.campo("Senha", self.campo_senha))

        self.lembrar = QCheckBox("Lembrar de mim neste computador")
        self.lembrar.setChecked(True)
        self.lembrar.setToolTip("O Hub abre direto com a sua conta. Em computador de uso comum, desmarque.")
        coluna.addWidget(self.lembrar)

        self.aviso_entrar = self._aviso()
        coluna.addWidget(self.aviso_entrar)

        self.botao_entrar = Button("Entrar", "forward", "primary")
        self.botao_entrar.setMinimumHeight(Control.primary)
        self.botao_entrar.clicked.connect(self.entrar)
        coluna.addWidget(self.botao_entrar)

        self.link_esqueci = _Link("Esqueci minha senha")
        self.link_esqueci.clicked.connect(self.ir_para_esqueci)
        coluna.addWidget(self.link_esqueci, 0, Qt.AlignmentFlag.AlignLeft)

        self.link_licenca = _Link("Este computador saiu da chave. Ativar de novo")
        self.link_licenca.clicked.connect(self.ativar_licenca.emit)
        coluna.addWidget(self.link_licenca, 0, Qt.AlignmentFlag.AlignLeft)
        self.link_licenca.setVisible(False)
        return pagina

    def _pagina_esqueci(self) -> QWidget:
        pagina, coluna, _, _ = self._coluna(
            "Esqueceu a senha?",
            "Digite o seu login. Mandamos um código para o e-mail da sua conta. Precisa de internet.")
        self.campo_esqueci = form.texto("", "O seu login")
        self.campo_esqueci.setMinimumHeight(Control.primary)
        self.campo_esqueci.returnPressed.connect(self.pedir_codigo)
        coluna.addWidget(form.campo("Login", self.campo_esqueci))

        self.aviso_esqueci = self._aviso()
        coluna.addWidget(self.aviso_esqueci)

        self.botao_enviar = Button("Enviar código por e-mail", "chat", "primary")
        self.botao_enviar.setMinimumHeight(Control.primary)
        self.botao_enviar.clicked.connect(self.pedir_codigo)
        coluna.addWidget(self.botao_enviar)

        voltar = _Link("Voltar para o login")
        voltar.clicked.connect(self._voltar)
        coluna.addWidget(voltar, 0, Qt.AlignmentFlag.AlignLeft)
        return pagina

    def _pagina_codigo(self) -> QWidget:
        pagina, coluna, _, self.texto_codigo = self._coluna("Crie uma senha nova", "Enviamos um código.")
        self.campo_codigo = CampoCodigo()
        coluna.addWidget(form.campo("Código do e-mail", self.campo_codigo))
        self.nova_codigo = CampoSenha("Pelo menos 8 caracteres")
        coluna.addWidget(form.campo("Senha nova", self.nova_codigo))
        coluna.addWidget(MedidorDeSenha(self.nova_codigo))
        self.repetir_codigo = CampoSenha("Digite de novo")
        self.repetir_codigo.returnPressed.connect(self.redefinir)
        coluna.addWidget(form.campo("Repita a senha", self.repetir_codigo))

        self.aviso_codigo = self._aviso()
        coluna.addWidget(self.aviso_codigo)

        self.botao_redefinir = Button("Salvar senha e entrar", "check", "primary")
        self.botao_redefinir.setMinimumHeight(Control.primary)
        self.botao_redefinir.clicked.connect(self.redefinir)
        coluna.addWidget(self.botao_redefinir)

        linha = QHBoxLayout()
        voltar = _Link("Voltar para o login")
        voltar.clicked.connect(self._voltar)
        linha.addWidget(voltar)
        linha.addStretch(1)
        reenviar = _Link("Enviar outro código")
        reenviar.clicked.connect(self.ir_para_esqueci)
        linha.addWidget(reenviar)
        coluna.addLayout(linha)
        return pagina

    def _pagina_trocar(self) -> QWidget:
        pagina, coluna, self.titulo_trocar, _ = self._coluna(
            "Crie a sua senha",
            "A senha que você recebeu vale só para este primeiro acesso. A próxima só você vai saber.")
        self.nova_trocar = CampoSenha("Pelo menos 8 caracteres")
        coluna.addWidget(form.campo("Senha nova", self.nova_trocar))
        coluna.addWidget(MedidorDeSenha(self.nova_trocar))
        self.repetir_trocar = CampoSenha("Digite de novo")
        self.repetir_trocar.returnPressed.connect(self.trocar)
        coluna.addWidget(form.campo("Repita a senha", self.repetir_trocar))

        self.aviso_trocar = self._aviso()
        coluna.addWidget(self.aviso_trocar)

        self.botao_trocar = Button("Salvar senha e entrar", "check", "primary")
        self.botao_trocar.setMinimumHeight(Control.primary)
        self.botao_trocar.clicked.connect(self.trocar)
        coluna.addWidget(self.botao_trocar)
        return pagina

    # ------------------------------------------------------------------ estado
    def preparar(self) -> None:
        """Volta ao comeco, com as pessoas que ja usaram este computador."""
        nome = self.empresa() if callable(self.empresa) else ""
        self.faixa.definir(nome or "Sua loja no Hub", "Cada pessoa com o seu acesso.")
        self._voltar()
        self.campo_login.clear()
        self.campo_senha.clear()
        self.lembrar.setChecked(True)

        for botao in self._pessoas:
            self.linha_pessoas.removeWidget(botao)
            botao.deleteLater()
        self._pessoas = []
        recentes = self.acesso.recentes()
        for pessoa in recentes:
            botao = BotaoPessoa(pessoa.nome, pessoa.login)
            botao.escolhida.connect(self.escolher)
            self.linha_pessoas.insertWidget(len(self._pessoas), botao)
            self._pessoas.append(botao)
        self.caixa_pessoas.setVisible(bool(recentes))
        self.titulo_entrar.setText("Quem vai usar o Hub agora?" if recentes else "Entre com a sua conta")
        self.conferir_licenca()
        (self.campo_senha if recentes else self.campo_login).setFocus()

    def conferir_licenca(self) -> None:
        """Sem vaga na chave o servidor recusa toda senha: a saida fica a vista."""
        self.link_licenca.setVisible(self.acesso.computador_fora)

    def avisar(self, texto: str) -> None:
        """Um recado na porta: por que a pessoa voltou para ca."""
        dizer(self.aviso_entrar, texto, "warning")

    def escolher(self, login: str) -> None:
        self.campo_login.setText(login)
        for botao in self._pessoas:
            botao.setChecked(botao.login == login)
        dizer(self.aviso_entrar, "")
        self.campo_senha.clear()
        self.campo_senha.setFocus()

    def _focar_senha(self) -> None:
        self.campo_senha.setFocus()

    def _voltar(self) -> None:
        self.paginas.setCurrentIndex(PAGINA_ENTRAR)
        dizer(self.aviso_entrar, "")

    def _ocupar(self, ocupado: bool, *botoes) -> None:
        self._ocupado = ocupado
        for botao in botoes:
            botao.setEnabled(not ocupado)

    # ------------------------------------------------------------------ entrar
    def entrar(self) -> None:
        if self._ocupado:
            return
        login = self.campo_login.text().strip()
        senha = self.campo_senha.text()
        if not login:
            dizer(self.aviso_entrar, "Digite o seu login.", "warning")
            self.campo_login.setFocus()
            return
        if not senha:
            dizer(self.aviso_entrar, "Digite a sua senha.", "warning")
            self.campo_senha.setFocus()
            return
        self._ocupar(True, self.botao_entrar)
        dizer(self.aviso_entrar, "Entrando...")
        lembrar = self.lembrar.isChecked()

        def concluiu(resposta: dict) -> None:
            self._ocupar(False, self.botao_entrar)
            try:
                usuario = self.acesso.aplicar(resposta)
            except AcessoError as erro:
                dizer(self.aviso_entrar, str(erro), "danger")
                return
            self.campo_senha.clear()
            dizer(self.aviso_entrar, "")
            if usuario.trocar_senha:
                self._senha_recebida = senha
                self.paginas.setCurrentIndex(PAGINA_TROCAR)
                self.nova_trocar.setFocus()
                return
            self.entrou.emit()

        def falhou(erro: Exception) -> None:
            self._ocupar(False, self.botao_entrar)
            dizer(self.aviso_entrar, mensagem(erro), tom_do_erro(erro))
            self.campo_senha.selectAll()
            self.campo_senha.setFocus()

        tasks.executar(self, lambda: self.acesso.entrar(login, senha, lembrar), concluiu, falhou)

    # ----------------------------------------------------------------- esqueci
    def ir_para_esqueci(self) -> None:
        self.campo_esqueci.setText(self.campo_login.text().strip())
        dizer(self.aviso_esqueci, "")
        self.paginas.setCurrentIndex(PAGINA_ESQUECI)
        self.campo_esqueci.setFocus()

    def pedir_codigo(self) -> None:
        if self._ocupado:
            return
        login = self.campo_esqueci.text().strip()
        if not login:
            dizer(self.aviso_esqueci, "Digite o seu login.", "warning")
            return
        self._ocupar(True, self.botao_enviar)
        dizer(self.aviso_esqueci, "Enviando o código...")

        def concluiu(resposta: dict) -> None:
            self._ocupar(False, self.botao_enviar)
            if resposta.get("sem_email"):
                dizer(self.aviso_esqueci,
                      "Esta conta não tem e-mail cadastrado. Peça ao administrador da loja para "
                      "redefinir a sua senha.", "warning")
                return
            email = str(resposta.get("email") or "")
            dizer(self.texto_codigo,
                  (f"Enviamos um código para {email}. Ele vale por 10 minutos. Confira também o spam."
                   if email else
                   "Se esse login existir, o código chega no e-mail da conta. Ele vale por 10 minutos."))
            dizer(self.aviso_codigo, "")
            self.campo_login.setText(login)
            self.campo_codigo.clear()
            self.paginas.setCurrentIndex(PAGINA_CODIGO)
            self.campo_codigo.setFocus()

        def falhou(erro: Exception) -> None:
            self._ocupar(False, self.botao_enviar)
            dizer(self.aviso_esqueci, mensagem(erro), tom_do_erro(erro))

        tasks.executar(self, lambda: self.acesso.pedir_codigo(login), concluiu, falhou)

    def redefinir(self) -> None:
        if self._ocupado:
            return
        login = self.campo_login.text().strip()
        senha = self.nova_codigo.text()
        problema = self._problema_na_senha(senha, self.repetir_codigo.text(), login)
        if problema:
            dizer(self.aviso_codigo, problema, "warning")
            return
        codigo = self.campo_codigo.text()
        lembrar = self.lembrar.isChecked()
        self._ocupar(True, self.botao_redefinir)
        dizer(self.aviso_codigo, "Salvando...")

        def concluiu(resposta: dict) -> None:
            self._ocupar(False, self.botao_redefinir)
            try:
                self.acesso.aplicar(resposta)
            except AcessoError as erro:
                dizer(self.aviso_codigo, str(erro), "danger")
                return
            self.nova_codigo.clear()
            self.repetir_codigo.clear()
            self.entrou.emit()

        def falhou(erro: Exception) -> None:
            self._ocupar(False, self.botao_redefinir)
            dizer(self.aviso_codigo, mensagem(erro), tom_do_erro(erro))

        tasks.executar(self, lambda: self.acesso.redefinir(login, codigo, senha, lembrar), concluiu, falhou)

    # ---------------------------------------------------------- primeira senha
    def trocar(self) -> None:
        if self._ocupado:
            return
        usuario = self.acesso.usuario
        senha = self.nova_trocar.text()
        problema = self._problema_na_senha(senha, self.repetir_trocar.text(), usuario.login if usuario else "")
        if problema:
            dizer(self.aviso_trocar, problema, "warning")
            return
        recebida = self._senha_recebida
        if senha == recebida:
            dizer(self.aviso_trocar, "Escolha uma senha diferente da que você recebeu.", "warning")
            return
        lembrar = self.lembrar.isChecked()
        self._ocupar(True, self.botao_trocar)
        dizer(self.aviso_trocar, "Salvando...")

        def concluiu(resposta: dict) -> None:
            self._ocupar(False, self.botao_trocar)
            try:
                self.acesso.aplicar(resposta)
            except AcessoError as erro:
                dizer(self.aviso_trocar, str(erro), "danger")
                return
            self._senha_recebida = ""
            self.nova_trocar.clear()
            self.repetir_trocar.clear()
            self.entrou.emit()

        def falhou(erro: Exception) -> None:
            self._ocupar(False, self.botao_trocar)
            dizer(self.aviso_trocar, mensagem(erro), tom_do_erro(erro))

        tasks.executar(self, lambda: self.acesso.trocar_senha(recebida, senha, lembrar), concluiu, falhou)

    @staticmethod
    def _problema_na_senha(senha: str, repetida: str, login: str) -> str:
        return validar_senha(senha, login) or ("" if senha == repetida else "As duas senhas não são iguais.")
