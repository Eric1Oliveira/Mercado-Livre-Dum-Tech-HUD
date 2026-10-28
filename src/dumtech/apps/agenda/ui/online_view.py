"""A aba Online da Agenda: o link que deixa o cliente marcar sozinho.

DE CIMA PARA BAIXO
    1. O link: ligado ou pausado, o endereco grande, Copiar / Enviar no
       WhatsApp / Abrir, o QR para imprimir e colar no balcao.
    2. Horario de atendimento e regras - o que a pagina oferece. Os servicos
       tem aba propria (`servicos_view.py`), que publica por esta aqui.
    3. Salvar e publicar.

Na primeira vez, nada disso: um cartao explica o que o link faz e cria tudo
com um clique, ja com o basico preenchido. O link nasce funcionando.

A tela grava aqui e publica em segundo plano. Sem internet, fica salvo: a
conversa periodica do Hub (`online.Sincronia`) publica quando a rede voltar.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from urllib.parse import quote

from PySide6.QtCore import QTime, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ....core.online import OnlineError
from ....ui import format as fmt
from ....ui import icons, tasks
from ....ui.theme import Space, current_palette
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, IconBadge, Pill, label, repolish, separator
from ....ui.widgets.confirmar import confirmar
from ....ui.widgets.qr import pixmap as qr_pixmap
from ..models import DIAS_SEMANA, AgendaError
from ..online import CORES, AjustesOnline, Dia, Online, logo_em_data_uri

LADO_QR = 132

ANTECEDENCIAS = ((0, "Sem antecedência"), (30, "30 minutos"), (60, "1 hora"), (120, "2 horas"),
                 (240, "4 horas"), (720, "12 horas"), (1440, "1 dia"), (2880, "2 dias"))
JANELAS = ((7, "7 dias"), (14, "14 dias"), (30, "30 dias"), (60, "60 dias"), (90, "90 dias"))
CANCELAMENTOS = ((0, "Até a hora marcada"), (60, "Até 1 hora antes"), (180, "Até 3 horas antes"),
                 (720, "Até 12 horas antes"), (1440, "Até 1 dia antes"), (2880, "Até 2 dias antes"))


def _qtime(minutos: int) -> QTime:
    minutos = max(0, min(int(minutos), 23 * 60 + 59))
    return QTime(minutos // 60, minutos % 60)


def _minutos(campo: QTimeEdit) -> int:
    hora = campo.time()
    return hora.hour() * 60 + hora.minute()


def _hora(minutos: int) -> QTimeEdit:
    # sem as setinhas: sete linhas com quatro pares de setas viravam ruido, e
    # a hora se digita (ou roda com a rolagem do mouse) do mesmo jeito
    campo = QTimeEdit(_qtime(minutos))
    campo.setDisplayFormat("HH:mm")
    campo.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    campo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    campo.setMinimumWidth(92)
    return campo


class Amostra(QAbstractButton):
    """Uma bolinha de cor para escolher a cor da pagina."""

    LADO = 28

    def __init__(self, chave: str, nome: str, cor: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chave = chave
        self.cor = cor
        self.setCheckable(True)
        self.setToolTip(nome)
        self.setFixedSize(self.LADO + 8, self.LADO + 8)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = current_palette()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        centro = self.rect().center()
        if self.isChecked():
            pintor.setPen(QPen(QColor(p.text), 2))
            pintor.setBrush(Qt.BrushStyle.NoBrush)
            pintor.drawEllipse(centro, self.LADO / 2 + 2, self.LADO / 2 + 2)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(self.cor))
        raio = self.LADO / 2 - (2 if self.isChecked() else 0)
        pintor.drawEllipse(centro, raio, raio)
        pintor.end()


class EditorDeHorario(QWidget):
    """Os 7 dias: aberto ou fechado, das/as e o almoco."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        grade = QGridLayout(self)
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setHorizontalSpacing(10)
        grade.setVerticalSpacing(Space.xs)
        self._dias = []
        for linha, nome in enumerate(DIAS_SEMANA):
            aberto = QCheckBox(nome)
            abre, fecha = _hora(9 * 60), _hora(18 * 60)
            almoco = QCheckBox("Almoço")
            almoco_de, almoco_ate = _hora(12 * 60), _hora(13 * 60)
            campos = (aberto, abre, fecha, almoco, almoco_de, almoco_ate)
            grade.addWidget(aberto, linha, 0)
            grade.addWidget(abre, linha, 1)
            grade.addWidget(label("às", "muted"), linha, 2)
            grade.addWidget(fecha, linha, 3)
            grade.addWidget(almoco, linha, 4)
            grade.addWidget(almoco_de, linha, 5)
            grade.addWidget(label("às", "muted"), linha, 6)
            grade.addWidget(almoco_ate, linha, 7)
            aberto.toggled.connect(lambda _=False, c=campos: self._acender(c))
            almoco.toggled.connect(lambda _=False, c=campos: self._acender(c))
            self._dias.append(campos)
        grade.setColumnStretch(8, 1)

    @staticmethod
    def _acender(campos) -> None:
        aberto, abre, fecha, almoco, almoco_de, almoco_ate = campos
        ligado = aberto.isChecked()
        for campo in (abre, fecha, almoco):
            campo.setEnabled(ligado)
        for campo in (almoco_de, almoco_ate):
            campo.setEnabled(ligado and almoco.isChecked())

    def preencher(self, semana: list[Dia]) -> None:
        for campos, dia in zip(self._dias, semana):
            aberto, abre, fecha, almoco, almoco_de, almoco_ate = campos
            aberto.setChecked(dia.aberto)
            abre.setTime(_qtime(dia.abre))
            fecha.setTime(_qtime(dia.fecha))
            almoco.setChecked(dia.almoco)
            almoco_de.setTime(_qtime(dia.almoco_de))
            almoco_ate.setTime(_qtime(dia.almoco_ate))
            self._acender(campos)

    def semana(self) -> list[Dia]:
        return [
            Dia(aberto=aberto.isChecked(), abre=_minutos(abre), fecha=_minutos(fecha),
                almoco=almoco.isChecked(), almoco_de=_minutos(almoco_de),
                almoco_ate=_minutos(almoco_ate))
            for aberto, abre, fecha, almoco, almoco_de, almoco_ate in self._dias
        ]


class OnlineView(QWidget):
    """O link de agendamento: criar, mandar, ajustar e pausar."""

    data_changed = Signal()
    #: deu certo?, a frase para o dono - a aba Servicos publica por aqui
    publicacao = Signal(bool, str)

    def __init__(self, repository, servidor=None, empresa=None, paths=None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.online = Online(repository)
        self.servidor = servidor
        #: atualizada pelo Hub quando Minha empresa muda (`AppWindow.atualizar_empresa`)
        self.empresa = empresa
        self.paths = paths
        self._publicando = False
        #: os ajustes ja foram para os campos? Depois disso, recarregar a tela
        #: (chegou agendamento, outra aba salvou) nao apaga o que o dono digita
        self._preenchido = False

        # a casca do aplicativo ja poe cada tela numa area de rolagem
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.md)

        self.cartao_vazio = self._cartao_vazio()
        raiz.addWidget(self.cartao_vazio)

        self.conteudo = QWidget()
        coluna = QVBoxLayout(self.conteudo)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(Space.md)
        coluna.addWidget(self._cartao_link())
        lado_a_lado = QHBoxLayout()
        lado_a_lado.setSpacing(Space.md)
        lado_a_lado.addWidget(self._cartao_horario(), 6)
        lado_a_lado.addWidget(self._cartao_regras(), 5)
        coluna.addLayout(lado_a_lado)
        coluna.addLayout(self._rodape())
        raiz.addWidget(self.conteudo)
        raiz.addStretch(1)

        self.refresh()

    # ------------------------------------------------------------------ pedacos
    def _cartao_vazio(self) -> Card:
        card = Card(padding=Space.xl)
        topo = QHBoxLayout()
        topo.setSpacing(Space.lg)
        topo.addWidget(IconBadge("link", "accent", size=56, radius=16), 0, Qt.AlignmentFlag.AlignTop)
        textos = QVBoxLayout()
        textos.setSpacing(Space.sm)
        textos.addWidget(label("Seus clientes marcam sozinhos", "title"))
        explica = label(
            "Crie um link de agendamento e mande no WhatsApp ou ponha na bio do Instagram. "
            "O cliente escolhe o serviço, o dia e o horário livre - e o compromisso aparece "
            "aqui na Agenda, sem você parar o que está fazendo.", "muted")
        explica.setWordWrap(True)
        textos.addWidget(explica)
        for frase in ("Só aparecem os horários livres: o que você marca aqui sai do link na hora.",
                      "Almoço, folga e feriado que você bloqueia na Agenda também fecham o link.",
                      "Nome e WhatsApp do cliente vêm junto. Você confirma pelo WhatsApp como já faz."):
            linha = QHBoxLayout()
            linha.setSpacing(Space.sm)
            marca = QLabel()
            marca.setPixmap(icons.pixmap("check", current_palette().success, 16, width=2.4))
            linha.addWidget(marca, 0, Qt.AlignmentFlag.AlignTop)
            item = label(frase, "body")
            item.setWordWrap(True)
            linha.addWidget(item, 1)
            textos.addLayout(linha)
        topo.addLayout(textos, 1)
        card.body.addLayout(topo)
        acoes = QHBoxLayout()
        acoes.addStretch(1)
        self.aviso_vazio = label("", "muted")
        self.aviso_vazio.setWordWrap(True)
        acoes.addWidget(self.aviso_vazio, 1)
        self.botao_criar = Button("Criar meu link", "link", "primary")
        self.botao_criar.setMinimumHeight(40)
        self.botao_criar.clicked.connect(self.criar)
        acoes.addWidget(self.botao_criar)
        card.body.addLayout(acoes)
        return card

    def _cartao_link(self) -> Card:
        card = Card(padding=Space.lg)
        linha = QHBoxLayout()
        linha.setSpacing(Space.lg)

        esquerda = QVBoxLayout()
        esquerda.setSpacing(Space.sm)
        cabeca = QHBoxLayout()
        cabeca.setSpacing(Space.sm)
        cabeca.addWidget(IconBadge("link", "accent", size=34, radius=11))
        cabeca.addWidget(label("Link de agendamento", "section"))
        self.situacao = Pill("No ar", "success")
        cabeca.addWidget(self.situacao)
        cabeca.addStretch(1)
        self.botao_pausar = Button("Pausar link", "", "ghost")
        self.botao_pausar.clicked.connect(self.alternar)
        cabeca.addWidget(self.botao_pausar)
        esquerda.addLayout(cabeca)

        self.endereco = label("", "title")
        self.endereco.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.endereco.setWordWrap(True)
        esquerda.addWidget(self.endereco)

        botoes = QHBoxLayout()
        botoes.setSpacing(Space.sm)
        self.botao_copiar = Button("Copiar", "copy", "primary")
        self.botao_copiar.clicked.connect(self.copiar)
        self.botao_whatsapp = Button("Enviar no WhatsApp", "chat")
        self.botao_whatsapp.clicked.connect(self.enviar_whatsapp)
        self.botao_abrir = Button("Abrir", "external", "ghost")
        self.botao_abrir.clicked.connect(self.abrir)
        for botao in (self.botao_copiar, self.botao_whatsapp, self.botao_abrir):
            botoes.addWidget(botao)
        botoes.addStretch(1)
        esquerda.addLayout(botoes)

        self.estado = label("", "muted")
        self.estado.setWordWrap(True)
        esquerda.addWidget(self.estado)
        self.origem_dos_dados = label(
            "Nome, logotipo, endereço e WhatsApp da página vêm de Minha empresa "
            "(menu da empresa, no canto de cima). Os serviços e o tempo de cada um "
            "ficam na aba Serviços.", "dim")
        self.origem_dos_dados.setWordWrap(True)
        esquerda.addWidget(self.origem_dos_dados)
        linha.addLayout(esquerda, 1)

        direita = QVBoxLayout()
        direita.setSpacing(Space.xs)
        self.qr = QLabel()
        self.qr.setFixedSize(LADO_QR, LADO_QR)
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        direita.addWidget(self.qr, 0, Qt.AlignmentFlag.AlignHCenter)
        self.botao_qr = Button("Salvar QR", "image", "ghost")
        self.botao_qr.setToolTip("Imagem para imprimir e colar no balcão")
        self.botao_qr.clicked.connect(self.salvar_qr)
        direita.addWidget(self.botao_qr, 0, Qt.AlignmentFlag.AlignHCenter)
        linha.addLayout(direita)

        card.body.addLayout(linha)
        return card

    def _cartao_horario(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Horário de atendimento", "section"))
        dica = label("Os dias e horas em que o link oferece horário.", "muted")
        dica.setWordWrap(True)
        card.body.addWidget(dica)
        card.body.addWidget(separator())
        self.horario = EditorDeHorario()
        card.body.addWidget(self.horario)
        card.body.addStretch(1)
        return card

    def _cartao_regras(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Regras", "section"))
        card.body.addWidget(separator())
        grade = QGridLayout()
        grade.setHorizontalSpacing(Space.lg)
        grade.setVerticalSpacing(Space.md)

        self.vagas = form.inteiro(1, minimo=1, maximo=10)
        self.vagas.setToolTip("Quantos clientes você atende ao mesmo tempo")
        self.antecedencia = form.escolha([(r, v) for v, r in ANTECEDENCIAS], 120)
        self.janela = form.escolha([(r, v) for v, r in JANELAS], 30)
        self.cancelar = form.escolha([(r, v) for v, r in CANCELAMENTOS], 180)
        grade.addWidget(form.campo("Vagas por horário", self.vagas), 0, 0)
        grade.addWidget(form.campo("Antecedência mínima", self.antecedencia), 0, 1)
        grade.addWidget(form.campo("Agenda aberta por", self.janela), 1, 0)
        grade.addWidget(form.campo("Cliente cancela", self.cancelar), 1, 1)

        self.mensagem = form.texto("", "Ex.: Chegue 5 minutos antes")
        self.mensagem.setMaxLength(280)
        grade.addWidget(form.campo("Recado na página (opcional)", self.mensagem), 2, 0, 1, 2)

        cores = QWidget()
        fila = QHBoxLayout(cores)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(2)
        self.grupo_cores = QButtonGroup(self)
        self.grupo_cores.setExclusive(True)
        self._amostras: dict[str, Amostra] = {}
        for chave, nome, cor in CORES:
            amostra = Amostra(chave, nome, cor)
            self.grupo_cores.addButton(amostra)
            self._amostras[chave] = amostra
            fila.addWidget(amostra)
        fila.addStretch(1)
        grade.addWidget(form.campo("Cor da página", cores), 3, 0, 1, 2)
        for coluna in range(2):
            grade.setColumnStretch(coluna, 1)
        card.body.addLayout(grade)
        card.body.addStretch(1)
        return card

    def _rodape(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        self.botao_endereco_novo = Button("Gerar endereço novo", "refresh", "ghost")
        self.botao_endereco_novo.setToolTip("Para quando o link estiver sendo usado por quem não devia")
        self.botao_endereco_novo.clicked.connect(self.gerar_endereco_novo)
        linha.addWidget(self.botao_endereco_novo)
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        linha.addWidget(self.aviso, 1)
        self.botao_salvar = Button("Salvar e publicar", "check", "primary")
        self.botao_salvar.setMinimumHeight(40)
        self.botao_salvar.clicked.connect(self.salvar)
        linha.addWidget(self.botao_salvar)
        return linha

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        criado = self.online.criado
        self.cartao_vazio.setVisible(not criado)
        self.conteudo.setVisible(criado)
        if not criado:
            self._dizer(self.aviso_vazio, "" if self._pode_publicar() else
                        "Ative a sua licença para publicar o link.", "warning")
            return
        if not self._preenchido:
            self._preencher()
        self._mostrar_link()

    def _preencher(self) -> None:
        self._preenchido = True
        ajustes = self.online.ajustes()
        self.horario.preencher(ajustes.semana)
        self.vagas.setValue(ajustes.vagas)
        for campo, valor in ((self.antecedencia, ajustes.antecedencia), (self.janela, ajustes.dias),
                             (self.cancelar, ajustes.cancelar_ate)):
            indice = campo.findData(valor)
            if indice < 0:
                campo.addItem(f"{valor}", valor)
                indice = campo.count() - 1
            campo.setCurrentIndex(indice)
        self.mensagem.setText(ajustes.mensagem)
        self._amostras.get(ajustes.cor, self._amostras["violeta"]).setChecked(True)

    def _mostrar_link(self) -> None:
        ativo = self.online.ativo
        link = self.online.link
        self.situacao.setText("No ar" if ativo else "Pausado")
        self.situacao.set_tone("success" if ativo else "warning")
        self.botao_pausar.setText("Pausar link" if ativo else "Retomar link")
        self.endereco.setText(link.replace("https://", "") if link else "Publicando o endereço...")
        for botao in (self.botao_copiar, self.botao_whatsapp, self.botao_abrir, self.botao_qr,
                      self.botao_endereco_novo):
            botao.setEnabled(bool(link))
        self.qr.setVisible(bool(link))
        if link:
            self.qr.setPixmap(qr_pixmap(link, LADO_QR))

        segunda = date.today() - timedelta(days=date.today().weekday())
        semana = self.repository.do_link_desde(datetime.combine(segunda, datetime.min.time()))
        partes = []
        publicado = self.online.publicado_em
        if publicado is not None:
            partes.append(f"Conferido {fmt.data_hora_curta(publicado.isoformat())}")
        partes.append(fmt.contagem(semana, "agendamento pelo link nesta semana",
                                   "agendamentos pelo link nesta semana"))
        erro = self.online.erro
        self._dizer(self.estado, erro or " · ".join(partes), "warning" if erro else "muted")

    def _ler(self) -> AjustesOnline:
        cor = next((chave for chave, amostra in self._amostras.items() if amostra.isChecked()), "violeta")
        # os servicos sao da aba Servicos: daqui vao como estao gravados
        guardado = self.online.ajustes()
        return AjustesOnline(
            servicos=guardado.servicos,
            semana=self.horario.semana(),
            passo=guardado.passo,
            vagas=self.vagas.value(),
            antecedencia=int(self.antecedencia.currentData()),
            dias=int(self.janela.currentData()),
            cancelar_ate=int(self.cancelar.currentData()),
            mensagem=self.mensagem.text().strip(),
            cor=cor,
        )

    # ------------------------------------------------------------------- acoes
    def criar(self) -> None:
        """O link nasce funcionando: o basico preenchido e publicado na hora.

        Servicos montados antes na aba Servicos ja entram; sem eles, o padrao.
        """
        self.online.salvar(self.online.ajustes(), ativo=True)
        self.refresh()
        self.publicar()

    def salvar(self) -> None:
        try:
            self.online.salvar(self._ler(), self.online.ativo)
        except AgendaError as erro:
            self._dizer(self.aviso, str(erro), "warning")
            return
        self.publicar()

    def alternar(self) -> None:
        ativo = not self.online.ativo
        if not ativo and not confirmar(
            self, "Pausar o link?",
            "A página passa a dizer que a agenda online está pausada e mostra o seu "
            "WhatsApp. O que já foi marcado continua valendo.", rotulo_ok="Pausar link",
            perigoso=False):
            return
        self.online.salvar(self.online.ajustes(), ativo)
        self._mostrar_link()
        self.publicar()

    def gerar_endereco_novo(self) -> None:
        if not confirmar(
            self, "Gerar um endereço novo?",
            "O link antigo para de funcionar na hora. Use quando o link estiver "
            "sendo usado por quem não devia.", rotulo_ok="Gerar endereço novo"):
            return
        self.online.pedir_endereco_novo()
        self.publicar()

    def publicar(self) -> None:
        """Manda para o servidor em segundo plano. Sem internet, fica salvo."""
        if self._publicando:
            return
        if not self._pode_publicar():
            texto = "Salvo. Ative a sua licença para publicar o link."
            self._dizer(self.aviso, texto, "warning")
            self.publicacao.emit(False, texto)
            return
        logo = ""
        if self.empresa is not None and self.paths is not None:
            logo = logo_em_data_uri(self.empresa.caminho_logo(self.paths))
        funcao, params = self.online.pedido_salvar(self.empresa, logo)
        self._publicando = True
        self.botao_salvar.setEnabled(False)
        self.botao_criar.setEnabled(False)
        self._dizer(self.aviso, "Publicando...", "accent")
        tasks.executar(self, lambda: self.servidor.chamar(funcao, params),
                       lambda resposta: self._publicado(params, resposta), self._falhou)

    def _publicado(self, params: dict, resposta: dict) -> None:
        self._publicando = False
        self.botao_salvar.setEnabled(True)
        self.botao_criar.setEnabled(True)
        self.online.registrar_salvo(params, resposta)
        texto = "Publicado. Quem abrir o link já vê o que você mudou."
        self._dizer(self.aviso, texto, "success")
        self.publicacao.emit(True, texto)
        self._mostrar_link()
        self.data_changed.emit()

    def _falhou(self, erro: Exception) -> None:
        self._publicando = False
        self.botao_salvar.setEnabled(True)
        self.botao_criar.setEnabled(True)
        texto = str(erro) if isinstance(erro, OnlineError) else "Não foi possível publicar agora."
        self.online.anotar_erro(texto)
        self._dizer(self.aviso, f"Salvo aqui. {texto}", "warning")
        self.publicacao.emit(False, f"Salvo aqui. {texto}")
        self._mostrar_link()

    def copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.online.link)
        self._dizer(self.aviso, "Link copiado. É só colar no WhatsApp, no Instagram ou onde quiser.", "success")

    def enviar_whatsapp(self) -> None:
        nome = getattr(self.empresa, "nome", "") or ""
        texto = (f"Agende seu horário{' na ' + nome if nome else ''} pelo link: {self.online.link}")
        QDesktopServices.openUrl(QUrl(f"https://wa.me/?text={quote(texto)}"))

    def abrir(self) -> None:
        QDesktopServices.openUrl(QUrl(self.online.link))

    def salvar_qr(self) -> None:
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar o QR do link", "QR do agendamento.png", "Imagem PNG (*.png)")
        if not caminho:
            return
        if qr_pixmap(self.online.link, 1024).save(caminho, "PNG"):
            self._dizer(self.aviso, "QR salvo. Imprima e cole no balcão ou na vitrine.", "success")
        else:
            self._dizer(self.aviso, "Não foi possível salvar a imagem nessa pasta.", "warning")

    # ------------------------------------------------------------------- apoio
    def _pode_publicar(self) -> bool:
        return self.servidor is not None and self.servidor.disponivel()

    @staticmethod
    def _dizer(alvo: QLabel, texto: str, tom: str = "muted") -> None:
        alvo.setText(texto)
        alvo.setProperty("tone", tom)
        alvo.setVisible(bool(texto))
        repolish(alvo)
