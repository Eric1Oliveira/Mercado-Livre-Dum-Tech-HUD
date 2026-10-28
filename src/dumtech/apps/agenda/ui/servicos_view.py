"""A aba Servicos da Agenda: o que o cliente escolhe no link.

Cada servico tem nome, duracao, de quanto em quanto tempo aparece no link e
preco (opcional). Pedido de cliente: a barba e de 15 minutos, entao aparece de
15 em 15 - e nao de 30 em 30 como o corte. O tempo acompanha a duracao sozinho;
o dono troca se quiser, e embaixo de cada servico a tela mostra como ele fica
no link num dia sem ninguem marcado.

Os servicos moram nos ajustes do link (`online.AjustesOnline`). Da para montar
antes de criar o link: so os servicos sao gravados e nada sai do computador.
Com o link no ar, salvar publica - quem publica e a aba Online, que ja conversa
com o servidor (a janela liga as duas).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.theme import Space
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, label, repolish, separator
from ..models import DIAS_SEMANA, DURACOES, AgendaError
from ..online import (
    MAXIMO_SERVICOS,
    PASSO_PADRAO,
    PASSOS,
    AjustesOnline,
    Dia,
    Online,
    Servico,
    horarios_no_dia,
    passo_padrao,
)

#: quantos horarios a previa mostra antes das reticencias
NA_PREVIA = 4


def _rotulo_passo(minutos: int) -> str:
    return "1 hora" if minutos == 60 else f"{minutos} min"


def _hora(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _escolha_com_extra(opcoes, atual: int):
    """Combo com as opcoes de sempre - e o valor de agora, se for diferente."""
    if atual not in {valor for valor, _ in opcoes}:
        opcoes = (*opcoes, (atual, f"{atual} min"))
    return form.escolha([(rotulo, valor) for valor, rotulo in opcoes], atual)


def _dizer(alvo, texto: str, tom: str) -> None:
    alvo.setText(texto)
    alvo.setProperty("tone", tom)
    alvo.setVisible(bool(texto))
    repolish(alvo)


class LinhaDeServico(QWidget):
    """Um servico: os campos numa linha e, embaixo, como ele fica no link."""

    tirar = Signal(object)
    mudou = Signal()

    def __init__(self, servico: Servico, limite: int = PASSO_PADRAO,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.id = servico.id
        self.limite = limite
        self._duracao_antes = int(servico.duracao)

        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(Space.xs)
        campos = QHBoxLayout()
        campos.setSpacing(10)
        self.nome = form.texto(servico.nome, "Ex.: Barba")
        self.nome.setMaxLength(80)
        self.duracao = _escolha_com_extra(tuple((m, r) for m, r in DURACOES if m <= 720),
                                          int(servico.duracao))
        self.passo = _escolha_com_extra(tuple((m, _rotulo_passo(m)) for m in PASSOS),
                                        int(servico.passo) or passo_padrao(servico.duracao, limite))
        self.passo.setToolTip("De quanto em quanto tempo este serviço aparece para o cliente marcar")
        self.preco = form.dinheiro(servico.preco or 0)
        self.preco.setSpecialValueText("Sem preço")
        botao_tirar = Button("", "trash", "ghost")
        botao_tirar.setToolTip("Tirar este serviço")
        botao_tirar.setFixedWidth(36)
        campos.addWidget(self.nome, 5)
        campos.addWidget(self.duracao, 2)
        campos.addWidget(self.passo, 2)
        campos.addWidget(self.preco, 2)
        campos.addWidget(botao_tirar)
        coluna.addLayout(campos)
        self.previa = label("", "caption")
        self.previa.setWordWrap(True)
        coluna.addWidget(self.previa)

        self.duracao.currentIndexChanged.connect(self._duracao_mudou)
        self.passo.currentIndexChanged.connect(self.mudou)
        botao_tirar.clicked.connect(lambda: self.tirar.emit(self))

    def _duracao_mudou(self) -> None:
        nova = int(self.duracao.currentData())
        # o tempo que seguia a duracao acompanha; o escolhido a mao fica
        if int(self.passo.currentData()) == passo_padrao(self._duracao_antes, self.limite):
            indice = self.passo.findData(passo_padrao(nova, self.limite))
            if indice >= 0:
                self.passo.setCurrentIndex(indice)
        self._duracao_antes = nova
        self.mudou.emit()

    def mostrar_previa(self, semana: list[Dia]) -> None:
        """Os primeiros horarios do primeiro dia em que o servico cabe."""
        duracao, passo = int(self.duracao.currentData()), int(self.passo.currentData())
        for nome, dia in zip(DIAS_SEMANA, semana):
            inicios = horarios_no_dia(dia.intervalos(), duracao, passo)
            if inicios:
                primeiros = ", ".join(_hora(m) for m in inicios[:NA_PREVIA])
                resto = "…" if len(inicios) > NA_PREVIA else ""
                _dizer(self.previa, f"{nome}: {primeiros}{resto} · "
                                    f"{fmt.contagem(len(inicios), 'horário', 'horários')} no dia", "muted")
                return
        _dizer(self.previa, "Não cabe no horário de atendimento. Diminua a duração "
                            "ou aumente o horário na aba Online.", "warning")

    def servico(self) -> Servico:
        preco = self.preco.value()
        return Servico(self.id, self.nome.text().strip(), int(self.duracao.currentData() or 60),
                       round(preco, 2) if preco > 0 else None, int(self.passo.currentData()))


class EditorDeServicos(QWidget):
    """Os servicos do link: uma linha cada um e o botao de adicionar."""

    MAXIMO = MAXIMO_SERVICOS

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.linhas: list[LinhaDeServico] = []
        self.limite = PASSO_PADRAO
        self.semana: list[Dia] = AjustesOnline.padrao().semana
        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(Space.sm)
        cabeca = QHBoxLayout()
        cabeca.setSpacing(10)
        for texto, peso in (("Serviço", 5), ("Duração", 2), ("Horários a cada", 2),
                            ("Preço (opcional)", 2)):
            cabeca.addWidget(label(texto, "field"), peso)
        cabeca.addSpacing(36)
        coluna.addLayout(cabeca)
        self.lista = QVBoxLayout()
        self.lista.setSpacing(Space.md)
        coluna.addLayout(self.lista)
        self.botao_mais = Button("Adicionar serviço", "plus", "ghost")
        self.botao_mais.clicked.connect(lambda: self.adicionar(Servico(self._novo_id(), "", 60)))
        coluna.addWidget(self.botao_mais, 0, Qt.AlignmentFlag.AlignLeft)

    def _novo_id(self) -> str:
        return AjustesOnline(servicos=[Servico(linha.id, "") for linha in self.linhas]).novo_id_de_servico()

    def preencher(self, servicos: list[Servico], limite: int = PASSO_PADRAO) -> None:
        for linha in self.linhas:
            linha.deleteLater()
        self.linhas = []
        self.limite = limite
        for servico in servicos:
            self.adicionar(servico)

    def adicionar(self, servico: Servico) -> None:
        linha = LinhaDeServico(servico, self.limite)
        linha.tirar.connect(self._tirar)
        linha.mudou.connect(lambda: linha.mostrar_previa(self.semana))
        linha.mostrar_previa(self.semana)
        self.linhas.append(linha)
        self.lista.addWidget(linha)
        self.botao_mais.setEnabled(len(self.linhas) < self.MAXIMO)
        if not servico.nome:
            linha.nome.setFocus()

    def _tirar(self, linha: LinhaDeServico) -> None:
        if linha in self.linhas:
            self.linhas.remove(linha)
            linha.deleteLater()
        self.botao_mais.setEnabled(len(self.linhas) < self.MAXIMO)

    def mostrar_semana(self, semana: list[Dia]) -> None:
        """O horario de atendimento mudou (aba Online): as previas acompanham."""
        self.semana = semana
        for linha in self.linhas:
            linha.mostrar_previa(semana)

    def servicos(self) -> list[Servico]:
        return [linha.servico() for linha in self.linhas]


class ServicosView(QWidget):
    """Os servicos do link de agendamento e o tempo de cada um."""

    data_changed = Signal()
    #: com o link no ar, salvar pede a publicacao a aba Online (a janela liga)
    pedir_publicacao = Signal()

    def __init__(self, repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.online = Online(repository)
        #: os servicos ja foram para os campos? Depois disso, recarregar a tela
        #: (chegou agendamento, a aba Online salvou) nao apaga o que o dono digita
        self._preenchido = False
        self._esperando = False

        # a casca do aplicativo ja poe cada tela numa area de rolagem
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.md)

        card = Card(padding=Space.lg)
        card.body.addWidget(label("Serviços", "section"))
        dica = label("O que o cliente escolhe no link. A duração é o tempo que fica reservado na "
                     "agenda; Horários a cada é de quanto em quanto tempo o serviço aparece para marcar.",
                     "muted")
        dica.setWordWrap(True)
        card.body.addWidget(dica)
        card.body.addWidget(separator())
        self.editor = EditorDeServicos()
        card.body.addWidget(self.editor)
        raiz.addWidget(card)

        rodape = QHBoxLayout()
        rodape.setSpacing(Space.sm)
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        rodape.addWidget(self.aviso, 1)
        self.botao_salvar = Button("Salvar e publicar", "check", "primary")
        self.botao_salvar.setMinimumHeight(40)
        self.botao_salvar.clicked.connect(self.salvar)
        rodape.addWidget(self.botao_salvar)
        raiz.addLayout(rodape)
        raiz.addStretch(1)

        self.refresh()

    def refresh(self) -> None:
        ajustes = self.online.ajustes()
        if not self._preenchido:
            self._preenchido = True
            self.editor.preencher(ajustes.servicos, ajustes.passo)
        self.editor.mostrar_semana(ajustes.semana)
        criado = self.online.criado
        self.botao_salvar.setText("Salvar e publicar" if criado else "Salvar")
        if not criado and not self.aviso.text():
            _dizer(self.aviso, "O link ainda não foi criado: os serviços entram nele quando você "
                               "criar o link na aba Online.", "muted")

    def salvar(self) -> None:
        try:
            self.online.salvar_servicos(self.editor.servicos())
        except AgendaError as erro:
            _dizer(self.aviso, str(erro), "warning")
            return
        if not self.online.criado:
            _dizer(self.aviso, "Salvo. Os serviços entram no link quando você criar o link na aba Online.",
                   "success")
            return
        self._esperando = True
        _dizer(self.aviso, "Publicando...", "accent")
        self.pedir_publicacao.emit()

    def mostrar_publicacao(self, certo: bool, texto: str) -> None:
        """A resposta da aba Online - so quando foi esta aba que pediu."""
        if not self._esperando:
            return
        self._esperando = False
        _dizer(self.aviso, texto, "success" if certo else "warning")
