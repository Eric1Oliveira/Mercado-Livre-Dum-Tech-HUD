"""Configuracoes > Usuarios e acessos: as pessoas e os computadores da chave.

Tres estados: **sem contas** (o convite para criar a primeira), **trancada** (pede
a senha do administrador) e **liberada** (a gestao). Como em Pagamentos, a area
tranca sozinha quando a sessao vence ou quando a pessoa sai da secao, e sem
internet nao abre: quem decide tudo aqui e o servidor.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from ...core.acesso import (
    ADM,
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
from ...core.avisos import TIPOS
from ...core.conta import email_valido
from ...ui import format as fmt
from ...ui import tasks
from ...ui.theme import Control, Space
from ...ui.widgets import form
from ...ui.widgets.buttons import Button
from ...ui.widgets.campo_senha import CampoSenha
from ...ui.widgets.common import Card, IconBadge, Pill, label, separator
from ...ui.widgets.confirmar import confirmar
from ...ui.widgets.pilha import Pilha
from ...ui.widgets.rolagem import Rolagem
from .acesso_comum import AvatarPessoa, Cracha, dizer, mensagem

PAGINA_SEM_CONTAS = 0
PAGINA_TRANCADA = 1
PAGINA_LIBERADA = 2

LARGURA_TRANCADA = 520
#: "Selecionar" do combo: nenhum modelo, o que vale e o que esta marcado
SEM_MODELO = ""


def _quando(valor) -> str:
    if not valor:
        return "nunca entrou"
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return ""
    return fmt.data_hora_curta(momento.replace(tzinfo=None).isoformat())


class UsuarioDialog(form.FormDialog):
    """Criar ou editar uma conta: quem e, o papel e o que essa pessoa ve."""

    def __init__(self, acesso: AcessoService, modulos: dict[str, str], dados: dict | None = None,
                 parent: QWidget | None = None) -> None:
        self.dados = dict(dados or {})
        self.novo = not self.dados.get("id")
        super().__init__("Nova conta" if self.novo else "Editar conta",
                         "" if self.novo else self.dados.get("nome", ""), parent, largura=620)
        self.acesso = acesso
        #: app_id -> nome curto, so do que a licenca liberou
        self.modulos = modulos
        self.resposta: dict | None = None
        self.senha_escolhida = ""
        self._login_tocado = not self.novo
        self._aplicando_modelo = False

        self.campo_nome = form.texto(self.dados.get("nome", ""), "Nome da pessoa")
        self.campo_nome.textEdited.connect(self._sugerir_login)
        self.add_row("Nome", self.campo_nome)
        self.campo_login = form.texto(self.dados.get("login", ""), "Sem espaços e sem acentos")
        self.campo_login.textEdited.connect(self._login_digitado)
        self.add_row("Login", self.campo_login)
        self.campo_email = form.texto(self.dados.get("email", ""), "Opcional para funcionário")
        self.add_row("E-mail", self.campo_email)
        self.campo_papel = form.escolha([("Funcionário", FUNCIONARIO), ("Administrador", ADM)],
                                        self.dados.get("papel", FUNCIONARIO))
        self.campo_papel.currentIndexChanged.connect(self._papel_mudou)
        self.add_row("Tipo", self.campo_papel)
        self.campo_senha = None
        if self.novo:
            self.campo_senha = CampoSenha("Senha inicial")
            self.campo_senha.setText(gerar_senha())
            self.campo_senha.alternar()
            self.add_row("Senha inicial", self.campo_senha)
            self.add_note("No primeiro acesso, a pessoa cria a própria senha.")

        self.bloco_permissoes = QWidget()
        bloco = QVBoxLayout(self.bloco_permissoes)
        bloco.setContentsMargins(0, Space.sm, 0, 0)
        bloco.setSpacing(Space.sm)
        bloco.addWidget(separator())
        self.campo_modelo = form.escolha(
            [("Escolher um modelo pronto...", SEM_MODELO), *((nome, nome) for nome in MODELOS)], SEM_MODELO)
        self.campo_modelo.currentIndexChanged.connect(self._aplicar_modelo)
        bloco.addWidget(self.campo_modelo)

        bloco.addWidget(label("Módulos que esta pessoa vê", "strong"))
        grade = QGridLayout()
        grade.setHorizontalSpacing(Space.xl)
        grade.setVerticalSpacing(Space.xs)
        self.caixas_modulos: dict[str, QCheckBox] = {}
        escolhidos = set(self.dados.get("modulos") or ())
        for indice, (app_id, nome) in enumerate(self.modulos.items()):
            caixa = QCheckBox(nome)
            caixa.setChecked(app_id in escolhidos)
            caixa.toggled.connect(lambda ligado, app=app_id: self._modulo_mudou(app, ligado))
            self.caixas_modulos[app_id] = caixa
            grade.addWidget(caixa, indice // 3, indice % 3)
        bloco.addLayout(grade)

        self.titulo_avisos = label("Avisos que aparecem no Início", "strong")
        bloco.addWidget(self.titulo_avisos)
        self.grade_avisos = QGridLayout()
        self.grade_avisos.setHorizontalSpacing(Space.xl)
        self.grade_avisos.setVerticalSpacing(Space.xs)
        self.caixas_avisos: dict[str, QCheckBox] = {}
        avisos = set(self.dados.get("avisos") or ())
        for tipo in TIPOS:
            if tipo.app_id not in self.modulos:
                continue
            caixa = QCheckBox(tipo.titulo)
            caixa.setToolTip(tipo.explicacao)
            caixa.setChecked(tipo.chave in avisos)
            self.caixas_avisos[tipo.chave] = caixa
        bloco.addLayout(self.grade_avisos)
        self.extras.addWidget(self.bloco_permissoes)

        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        self.aviso.setVisible(False)
        self.extras.addWidget(self.aviso)
        self._papel_mudou()
        self._mostrar_avisos()

    # ------------------------------------------------------------------- campos
    def _login_digitado(self, _texto: str) -> None:
        self._login_tocado = True

    def _sugerir_login(self, nome: str) -> None:
        if not self._login_tocado:
            self.campo_login.setText(sugerir_login(nome))

    def _papel_mudou(self, _indice: int = 0) -> None:
        self.bloco_permissoes.setVisible(self.campo_papel.currentData() == FUNCIONARIO)

    def _modulo_mudou(self, app_id: str, ligado: bool) -> None:
        """Marcar um modulo traz os avisos dele; desmarcar leva embora."""
        if not self._aplicando_modelo:
            self.campo_modelo.setCurrentIndex(0)
        for tipo in TIPOS:
            if tipo.app_id == app_id and tipo.chave in self.caixas_avisos:
                self.caixas_avisos[tipo.chave].setChecked(ligado)
        self._mostrar_avisos()

    def _mostrar_avisos(self) -> None:
        """So os avisos dos modulos marcados, sem buraco na grade."""
        ligados = {app for app, caixa in self.caixas_modulos.items() if caixa.isChecked()}
        por_chave = {tipo.chave: tipo for tipo in TIPOS}
        for caixa in self.caixas_avisos.values():
            self.grade_avisos.removeWidget(caixa)
        posicao = 0
        for chave, caixa in self.caixas_avisos.items():
            ligado = por_chave[chave].app_id in ligados
            if ligado:
                self.grade_avisos.addWidget(caixa, posicao // 2, posicao % 2)
                posicao += 1
            caixa.setVisible(ligado)
        self.titulo_avisos.setVisible(bool(ligados))

    def _aplicar_modelo(self, _indice: int = 0) -> None:
        modelo = str(self.campo_modelo.currentData() or SEM_MODELO)
        if modelo == SEM_MODELO:
            return
        modulos, avisos = permissoes_do_modelo(modelo)
        self._aplicando_modelo = True
        for app_id, caixa in self.caixas_modulos.items():
            caixa.setChecked(app_id in modulos)
        for chave, caixa in self.caixas_avisos.items():
            caixa.setChecked(chave in avisos)
        self._aplicando_modelo = False
        self._mostrar_avisos()

    # ------------------------------------------------------------------- salvar
    def montar(self) -> dict:
        papel = self.campo_papel.currentData()
        funcionario = papel == FUNCIONARIO
        ligados = [app for app, caixa in self.caixas_modulos.items() if caixa.isChecked()] if funcionario else []
        por_chave = {tipo.chave: tipo for tipo in TIPOS}
        avisos = ([chave for chave, caixa in self.caixas_avisos.items()
                   if caixa.isChecked() and por_chave[chave].app_id in ligados] if funcionario else [])
        return {
            "id": self.dados.get("id"), "nome": self.campo_nome.text().strip(),
            "login": self.campo_login.text().strip().lower(), "email": self.campo_email.text().strip().lower(),
            "papel": papel, "modulos": ligados, "avisos": avisos, "ativo": self.dados.get("ativo", True),
        }

    def salvar(self):
        dados = self.montar()
        senha = self.campo_senha.text() if self.campo_senha is not None else ""
        problema = ""
        if len(dados["nome"]) < 2:
            problema = "Digite o nome da pessoa."
        elif validar_login(dados["login"]):
            problema = validar_login(dados["login"])
        elif dados["email"] and not email_valido(dados["email"]):
            problema = "Confira o e-mail digitado."
        elif dados["papel"] == ADM and not dados["email"]:
            problema = "Administrador precisa de e-mail: é por ele que a senha é recuperada."
        elif self.campo_senha is not None and validar_senha(senha, dados["login"]):
            problema = validar_senha(senha, dados["login"])
        if problema:
            dizer(self.aviso, problema, "warning")
            return False

        self.botao_salvar.setEnabled(False)
        dizer(self.aviso, "Salvando...")

        def concluiu(resposta: dict) -> None:
            self.resposta = resposta
            self.senha_escolhida = senha
            self.accept()

        def falhou(erro: Exception) -> None:
            self.botao_salvar.setEnabled(True)
            dizer(self.aviso, mensagem(erro), "warning")

        tasks.executar(self, lambda: self.acesso.salvar_usuario(dados, senha), concluiu, falhou)
        return False  # quem fecha e a resposta do servidor


class SenhaDialog(form.FormDialog):
    """O ADM redefine a senha de alguem. A pessoa cria a propria ao entrar."""

    def __init__(self, acesso: AcessoService, usuario: dict, parent: QWidget | None = None) -> None:
        super().__init__("Redefinir senha", usuario.get("nome", ""), parent, largura=460)
        self.acesso = acesso
        self.usuario = usuario
        self.senha_escolhida = ""
        self.resposta: dict | None = None
        self.campo = CampoSenha("Senha provisória")
        self.campo.setText(gerar_senha())
        self.campo.alternar()
        self.add_row("Senha provisória", self.campo)
        self.add_note("Quem estiver usando a conta sai na hora. No próximo acesso, a pessoa cria a própria senha.")
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        self.aviso.setVisible(False)
        self.extras.addWidget(self.aviso)

    def salvar(self):
        senha = self.campo.text()
        problema = validar_senha(senha, self.usuario.get("login", ""))
        if problema:
            dizer(self.aviso, problema, "warning")
            return False
        self.botao_salvar.setEnabled(False)

        def concluiu(resposta: dict) -> None:
            self.resposta = resposta
            self.senha_escolhida = senha
            self.accept()

        def falhou(erro: Exception) -> None:
            self.botao_salvar.setEnabled(True)
            dizer(self.aviso, mensagem(erro), "warning")

        tasks.executar(self, lambda: self.acesso.definir_senha(str(self.usuario.get("id")),
                                                               self.usuario.get("login", ""), senha),
                       concluiu, falhou)
        return False


class ConfirmarSenhaDialog(form.FormDialog):
    """A senha de novo, para abrir o que e so do administrador."""

    def __init__(self, acesso: AcessoService, motivo: str, parent: QWidget | None = None) -> None:
        super().__init__("Confirme a sua senha", motivo, parent, largura=440)
        self.acesso = acesso
        self.botao_salvar.setText("  Continuar")
        self.campo = CampoSenha("Sua senha")
        self.add_row("Senha", self.campo)
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        self.aviso.setVisible(False)
        self.extras.addWidget(self.aviso)

    def salvar(self):
        senha = self.campo.text()
        if not senha:
            dizer(self.aviso, "Digite a sua senha.", "warning")
            return False
        self.botao_salvar.setEnabled(False)

        def concluiu(resposta: dict) -> None:
            self.botao_salvar.setEnabled(True)
            try:
                self.acesso.aplicar(resposta)
            except AcessoError as erro:
                dizer(self.aviso, str(erro), "danger")
                return
            self.accept()

        def falhou(erro: Exception) -> None:
            self.botao_salvar.setEnabled(True)
            dizer(self.aviso, mensagem(erro), "warning")

        tasks.executar(self, lambda: self.acesso.reabrir_gestao(senha), concluiu, falhou)
        return False  # quem fecha e a resposta do servidor


class ApelidoDialog(form.FormDialog):
    """Vaga sem nome nao se gerencia: Balcao e Escritorio resolvem."""

    def __init__(self, apelido: str, parent: QWidget | None = None) -> None:
        super().__init__("Renomear computador", "", parent, largura=420)
        self.apelido = apelido
        self.campo = form.texto(apelido, "Ex.: Balcão, Escritório")
        self.add_row("Nome", self.campo)

    def salvar(self):
        self.apelido = self.campo.text().strip()
        if not self.apelido:
            raise ValueError("Digite um nome para o computador.")


class UsuariosView(QWidget):
    """As contas e os computadores da chave, atras da senha do administrador."""

    #: contas ou permissoes mudaram: o Hub reavalia o que esta na tela
    mudou = Signal()
    #: ainda nao ha conta: o Hub abre o assistente
    criar_conta = Signal()
    #: este computador foi liberado aqui: a licenca saiu dele
    licenca_saiu = Signal()

    def __init__(self, acesso: AcessoService, registry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.acesso = acesso
        self.registry = registry
        self.usuarios: list[dict] = []
        self.computadores: list[dict] = []
        self._ocupado = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        self.paginas = Pilha()
        self.paginas.addWidget(self._pagina_sem_contas())
        self.paginas.addWidget(self._pagina_trancada())
        self.paginas.addWidget(self._pagina_liberada())
        raiz.addWidget(self.paginas, 1)

    # ---------------------------------------------------------------- montagem
    @staticmethod
    def _cartao_estreito() -> tuple[QWidget, Card]:
        pagina = QWidget()
        fora = QHBoxLayout(pagina)
        fora.setContentsMargins(0, Space.md, 0, 0)
        card = Card(padding=Space.xl)
        card.setMaximumWidth(LARGURA_TRANCADA)
        card.body.setSpacing(Space.md)
        fora.addWidget(card, 1, Qt.AlignmentFlag.AlignTop)
        return pagina, card

    def _pagina_sem_contas(self) -> QWidget:
        pagina, card = self._cartao_estreito()
        card.body.addWidget(label("Sua loja ainda não tem contas", "title"))
        texto = label("Crie a conta do administrador para cadastrar a equipe e decidir o que "
                      "cada pessoa vê. Leva cerca de 1 minuto.", "muted")
        texto.setWordWrap(True)
        card.body.addWidget(texto)
        botao = Button("Criar minha conta", "forward", "primary")
        botao.setMinimumHeight(Control.primary)
        botao.clicked.connect(self.criar_conta.emit)
        card.body.addWidget(botao)
        return pagina

    def _pagina_trancada(self) -> QWidget:
        pagina, card = self._cartao_estreito()
        card.body.addWidget(label("Confirme a sua senha", "title"))
        self.texto_trancada = label("Contas e computadores ficam protegidos pela senha do administrador.", "muted")
        self.texto_trancada.setWordWrap(True)
        card.body.addWidget(self.texto_trancada)
        self.campo_senha = CampoSenha("Sua senha")
        self.campo_senha.returnPressed.connect(self.liberar)
        card.body.addWidget(form.campo("Senha", self.campo_senha))
        self.aviso_trancada = label("", "muted")
        self.aviso_trancada.setWordWrap(True)
        self.aviso_trancada.setVisible(False)
        card.body.addWidget(self.aviso_trancada)
        self.botao_liberar = Button("Continuar", "forward", "primary")
        self.botao_liberar.setMinimumHeight(Control.primary)
        self.botao_liberar.clicked.connect(self.liberar)
        card.body.addWidget(self.botao_liberar)
        return pagina

    def _pagina_liberada(self) -> QWidget:
        pagina = QWidget()
        coluna = QVBoxLayout(pagina)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(Space.md)

        dentro = QWidget()
        lista = QVBoxLayout(dentro)
        lista.setContentsMargins(0, 0, Space.sm, 0)
        lista.setSpacing(Space.md)

        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        self.aviso.setVisible(False)
        lista.addWidget(self.aviso)

        self.caixa_crachas = QVBoxLayout()
        self.caixa_crachas.setSpacing(Space.sm)
        lista.addLayout(self.caixa_crachas)

        self.card_usuarios = Card(padding=Space.lg)
        topo = QHBoxLayout()
        self.titulo_usuarios = label("Usuários", "section")
        topo.addWidget(self.titulo_usuarios, 1)
        self.botao_novo = Button("Nova conta", "plus", "primary")
        self.botao_novo.clicked.connect(self.nova_conta)
        topo.addWidget(self.botao_novo)
        self.card_usuarios.body.addLayout(topo)
        self.card_usuarios.body.addWidget(separator())
        self.linhas_usuarios = QVBoxLayout()
        self.linhas_usuarios.setSpacing(Space.xs)
        self.card_usuarios.body.addLayout(self.linhas_usuarios)
        lista.addWidget(self.card_usuarios)

        self.card_computadores = Card(padding=Space.lg)
        self.titulo_computadores = label("Computadores", "section")
        self.card_computadores.body.addWidget(self.titulo_computadores)
        explica = label("A chave define quantos computadores podem usar o Hub. Para ter mais, fale com a DumTech.", "dim")
        explica.setWordWrap(True)
        self.card_computadores.body.addWidget(explica)
        self.card_computadores.body.addWidget(separator())
        self.linhas_computadores = QVBoxLayout()
        self.linhas_computadores.setSpacing(Space.xs)
        self.card_computadores.body.addLayout(self.linhas_computadores)
        lista.addWidget(self.card_computadores)
        lista.addStretch(1)

        coluna.addWidget(Rolagem(dentro), 1)
        return pagina

    # ------------------------------------------------------------------ estado
    def showEvent(self, evento) -> None:  # noqa: N802 (Qt)
        super().showEvent(evento)
        if not evento.spontaneous():
            self.refresh()

    def refresh(self) -> None:
        if not self.acesso.ha_contas:
            self.paginas.setCurrentIndex(PAGINA_SEM_CONTAS)
        elif self.acesso.gestao_aberta:
            self.paginas.setCurrentIndex(PAGINA_LIBERADA)
            self.carregar()
        else:
            self._mostrar_trancada()

    def _mostrar_trancada(self, recado: str = "") -> None:
        self.campo_senha.clear()
        dizer(self.aviso_trancada, recado, "warning")
        self.paginas.setCurrentIndex(PAGINA_TRANCADA)

    def trancar(self) -> None:
        self.acesso.trancar_gestao()
        self._limpar_crachas()
        self._mostrar_trancada()

    def hideEvent(self, evento) -> None:  # noqa: N802 (Qt)
        # saiu da secao (nao so minimizou a janela): tranca
        if not evento.spontaneous() and self.acesso.gestao_aberta:
            self.trancar()
        super().hideEvent(evento)

    def _limpar_crachas(self) -> None:
        while self.caixa_crachas.count():
            item = self.caixa_crachas.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _sessao_acabou(self, erro: Exception) -> bool:
        if isinstance(erro, AcessoError) and erro.codigo == "sessao_vencida":
            self.acesso.trancar_gestao()
            self._mostrar_trancada(str(erro))
            return True
        return False

    # ------------------------------------------------------------------ liberar
    def liberar(self) -> None:
        if self._ocupado:
            return
        senha = self.campo_senha.text()
        if not senha:
            dizer(self.aviso_trancada, "Digite a sua senha.", "warning")
            return
        self._ocupado = True
        self.botao_liberar.setEnabled(False)
        dizer(self.aviso_trancada, "Conferindo...")

        def concluiu(resposta: dict) -> None:
            self._ocupado = False
            self.botao_liberar.setEnabled(True)
            try:
                self.acesso.aplicar(resposta)
            except AcessoError as erro:
                dizer(self.aviso_trancada, str(erro), "danger")
                return
            self.campo_senha.clear()
            dizer(self.aviso_trancada, "")
            self.refresh()

        def falhou(erro: Exception) -> None:
            self._ocupado = False
            self.botao_liberar.setEnabled(True)
            dizer(self.aviso_trancada, mensagem(erro), "warning")

        tasks.executar(self, lambda: self.acesso.reabrir_gestao(senha), concluiu, falhou)

    # ------------------------------------------------------------------- listas
    def carregar(self) -> None:
        def buscar() -> tuple:
            return self.acesso.listar_usuarios(), self.acesso.computadores()

        def concluiu(resultado: tuple) -> None:
            self.usuarios, computadores = resultado
            self.computadores = list(computadores.get("computadores") or [])
            self._desenhar(int(computadores.get("max_computadores") or 1))

        def falhou(erro: Exception) -> None:
            if not self._sessao_acabou(erro):
                dizer(self.aviso, mensagem(erro), "warning")

        tasks.executar(self, buscar, concluiu, falhou)

    @staticmethod
    def _esvaziar(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _desenhar(self, maximo: int) -> None:
        dizer(self.aviso, "")
        self._esvaziar(self.linhas_usuarios)
        self.titulo_usuarios.setText(f"Usuários ({len(self.usuarios)})")
        for dados in self.usuarios:
            self.linhas_usuarios.addWidget(self._linha_usuario(dados))
        self._esvaziar(self.linhas_computadores)
        self.titulo_computadores.setText(f"Computadores: {len(self.computadores)} de {maximo}")
        for dados in self.computadores:
            self.linhas_computadores.addWidget(self._linha_computador(dados))

    def _linha_usuario(self, dados: dict) -> QWidget:
        linha = QFrame()
        caixa = QHBoxLayout(linha)
        caixa.setContentsMargins(0, Space.xs, 0, Space.xs)
        caixa.setSpacing(Space.md)
        caixa.addWidget(AvatarPessoa(dados.get("nome", "")))

        textos = QVBoxLayout()
        textos.setSpacing(1)
        textos.addWidget(label(dados.get("nome", ""), "strong"))
        detalhe = f"{dados.get('login', '')}  ·  {_quando(dados.get('ultimo_acesso'))}"
        textos.addWidget(label(detalhe, "dim"))
        caixa.addLayout(textos, 1)

        adm = dados.get("papel") == ADM
        caixa.addWidget(Pill("Administrador" if adm else "Funcionário", "accent" if adm else "muted"))
        if not dados.get("ativo", True):
            caixa.addWidget(Pill("Bloqueada", "danger"))

        editar = Button("Editar", "edit", "ghost")
        editar.clicked.connect(lambda: self.editar(dados))
        caixa.addWidget(editar)
        senha = Button("Senha", "key", "ghost")
        senha.setToolTip("Redefinir a senha")
        senha.clicked.connect(lambda: self.redefinir(dados))
        caixa.addWidget(senha)
        ativo = dados.get("ativo", True)
        bloquear = Button("Bloquear" if ativo else "Desbloquear", "lock", "ghost")
        bloquear.clicked.connect(lambda: self.alternar_bloqueio(dados))
        caixa.addWidget(bloquear)
        apagar = Button("", "trash", "ghost")
        apagar.setToolTip("Apagar a conta")
        apagar.setAccessibleName(f"Apagar a conta de {dados.get('nome', '')}")
        apagar.clicked.connect(lambda: self.apagar(dados))
        caixa.addWidget(apagar)
        return linha

    def _linha_computador(self, dados: dict) -> QWidget:
        linha = QFrame()
        caixa = QHBoxLayout(linha)
        caixa.setContentsMargins(0, Space.xs, 0, Space.xs)
        caixa.setSpacing(Space.md)
        caixa.addWidget(IconBadge("grid", "accent", size=34, radius=10))
        textos = QVBoxLayout()
        textos.setSpacing(1)
        nome = dados.get("apelido") or dados.get("maquina", "")
        textos.addWidget(label(nome, "strong"))
        versao = dados.get("versao") or ""
        textos.addWidget(label(f"Último contato: {_quando(dados.get('ultima_checagem'))}"
                               + (f"  ·  versão {versao}" if versao else ""), "dim"))
        caixa.addLayout(textos, 1)
        if dados.get("este"):
            caixa.addWidget(Pill("Este computador", "accent"))
        renomear = Button("Renomear", "edit", "ghost")
        renomear.clicked.connect(lambda: self.renomear(dados))
        caixa.addWidget(renomear)
        liberar = Button("Liberar", "logout", "ghost")
        liberar.setToolTip("Solta a vaga: o Hub para de abrir neste computador")
        liberar.clicked.connect(lambda: self.liberar_computador(dados))
        caixa.addWidget(liberar)
        return linha

    # -------------------------------------------------------------------- acoes
    def _modulos(self) -> dict[str, str]:
        return {e.app_id: e.manifest.short_name for e in self.registry.available()}

    def _depois_de_mudar(self, resposta: dict) -> None:
        self.acesso.guardar_documento(resposta.get("acesso_assinado"))
        self.mudou.emit()
        self.carregar()

    def _chamar(self, funcao, concluir=None) -> None:
        def concluiu(resposta: dict) -> None:
            if concluir is not None:
                concluir(resposta)
            self._depois_de_mudar(resposta)

        def falhou(erro: Exception) -> None:
            if not self._sessao_acabou(erro):
                dizer(self.aviso, mensagem(erro), "warning")

        tasks.executar(self, funcao, concluiu, falhou)

    def _mostrar_cracha(self, nome: str, login: str, senha: str) -> None:
        self.caixa_crachas.addWidget(Cracha(nome, login, senha))

    def nova_conta(self) -> None:
        dialogo = UsuarioDialog(self.acesso, self._modulos(), parent=self)
        if dialogo.exec():
            dados = dialogo.montar()
            self._mostrar_cracha(dados["nome"], dados["login"], dialogo.senha_escolhida)
            self._depois_de_mudar(dialogo.resposta or {})

    def editar(self, dados: dict) -> None:
        dialogo = UsuarioDialog(self.acesso, self._modulos(), dados, parent=self)
        if dialogo.exec():
            self._depois_de_mudar(dialogo.resposta or {})

    def redefinir(self, dados: dict) -> None:
        dialogo = SenhaDialog(self.acesso, dados, parent=self)
        if dialogo.exec():
            self._mostrar_cracha(dados.get("nome", ""), dados.get("login", ""), dialogo.senha_escolhida)
            self._depois_de_mudar(dialogo.resposta or {})

    def alternar_bloqueio(self, dados: dict) -> None:
        ativo = dados.get("ativo", True)
        if ativo and not confirmar(self, f"Bloquear {dados.get('nome', '')}?",
                                   "A pessoa sai do Hub e não entra mais até você desbloquear.",
                                   rotulo_ok="Bloquear conta"):
            return
        campos = {campo: dados.get(campo) for campo in ("nome", "login", "email", "papel", "modulos", "avisos")}
        novo = {**campos, "id": dados.get("id"), "ativo": not ativo}
        self._chamar(lambda: self.acesso.salvar_usuario(novo))

    def apagar(self, dados: dict) -> None:
        if not confirmar(self, f"Apagar a conta de {dados.get('nome', '')}?",
                         "A pessoa deixa de entrar no Hub. O que ela lançou nos módulos continua lá.",
                         rotulo_ok="Apagar conta"):
            return
        self._chamar(lambda: self.acesso.apagar_usuario(str(dados.get("id"))))

    def renomear(self, dados: dict) -> None:
        dialogo = ApelidoDialog(dados.get("apelido") or "", parent=self)
        if dialogo.exec():
            self._chamar(lambda: self.acesso.renomear_computador(dados.get("maquina", ""), dialogo.apelido))

    def liberar_computador(self, dados: dict) -> None:
        nome = dados.get("apelido") or dados.get("maquina", "")
        este = bool(dados.get("este"))
        texto = ("A licença sai deste computador agora e os módulos fecham. Para usar de novo, será "
                 "preciso ativar a chave." if este else
                 "O Hub para de abrir nesse computador e a vaga fica livre para outro.")
        if not confirmar(self, f"Liberar {nome}?", texto, rotulo_ok="Liberar computador"):
            return
        self._chamar(lambda: self.acesso.liberar_computador(dados.get("maquina", "")),
                     (lambda _r: self.licenca_saiu.emit()) if este else None)
