"""A grade: dia ou semana, com a linha da hora atual.

Nao existe "Painel" separado neste modulo. Um cartao dizendo "3 hoje" ao lado
de uma tela que mostra os tres seria a mesma informacao duas vezes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ....core import confirmacoes
from ....ui import icons
from ....ui.theme import Space, current_palette
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, label, menu_arredondado, repolish, tone_label
from ....ui.widgets.confirmar import confirmar
from ..models import (
    AGENDADO,
    CANCELADO,
    CONCLUIDO,
    FAIXA_PADRAO,
    FAIXAS,
    TIPO_LABEL,
    TIPO_TOM,
    Compromisso,
    faixa_por_chave,
    inicio_da_semana,
)
from ..repository import AgendaRepository

MODOS = (("Semana", 7), ("Dia", 1), ("Próximos 3 dias", 3))


class AgendaView(QWidget):
    """A grade da semana, com navegacao e a legenda dos tipos."""

    data_changed = Signal()
    #: pedido para abrir a ficha; 0 = novo. A janela resolve (precisa dos clientes)
    abrir_ficha = Signal(int)
    #: clique no vazio: manda data e hora ja escolhidas
    novo_em = Signal(str)

    def __init__(self, repository: AgendaRepository, parent: QWidget | None = None,
                 prefs=None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.prefs = prefs
        self.primeiro_dia = inicio_da_semana(date.today())
        self.selecionado: int | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.md)

        raiz.addLayout(self._cabecalho())
        raiz.addWidget(self._card_grade(), 1)
        raiz.addLayout(self._rodape())

        self.refresh()

    # -------------------------------------------------------------- cabecalho
    def _cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Agenda", "title"))
        self.subtitulo = label("", "subtitle")
        titulos.addWidget(self.subtitulo)
        linha.addLayout(titulos)
        linha.addStretch(1)

        self.botao_antes = Button("", "back", "ghost")
        self.botao_antes.setToolTip("Período anterior")
        self.botao_antes.clicked.connect(lambda: self._navegar(-1))
        linha.addWidget(self.botao_antes)

        self.botao_hoje = Button("Hoje", "calendar")
        self.botao_hoje.clicked.connect(self._ir_para_hoje)
        linha.addWidget(self.botao_hoje)

        # o par da seta de voltar - "external" desenhava a setinha de abrir
        # link fora do programa, que aqui nao quer dizer nada
        self.botao_depois = Button("", "forward", "ghost")
        self.botao_depois.setToolTip("Próximo período")
        self.botao_depois.clicked.connect(lambda: self._navegar(1))
        linha.addWidget(self.botao_depois)

        self.modo = QComboBox()
        for rotulo, dias in MODOS:
            self.modo.addItem(rotulo, dias)
        self.modo.currentIndexChanged.connect(self._modo_mudou)
        linha.addWidget(self.modo)

        # o horario da loja do cliente nao e o meu: padaria abre as 4, bar
        # fecha as 2. A grade estica sozinha para o que estiver marcado, mas a
        # faixa que ela mostra vazia e escolha de quem usa.
        self.faixa = QComboBox()
        self.faixa.setToolTip("Faixa de horas que a grade mostra")
        for rotulo, chave, _, _ in FAIXAS:
            self.faixa.addItem(rotulo, chave)
        guardada = str(self._preferencia("faixa", FAIXA_PADRAO))
        posicao = self.faixa.findData(guardada)
        self.faixa.setCurrentIndex(posicao if posicao >= 0 else 0)
        self.faixa.currentIndexChanged.connect(self._faixa_mudou)
        linha.addWidget(self.faixa)

        self.botao_novo = Button("Novo compromisso", "plus", "primary")
        self.botao_novo.setMinimumHeight(38)
        self.botao_novo.clicked.connect(lambda: self.abrir_ficha.emit(0))
        linha.addWidget(self.botao_novo)
        return linha

    def _preferencia(self, chave: str, padrao):
        return self.prefs.get(chave, padrao) if self.prefs is not None else padrao

    def _faixa_mudou(self) -> None:
        if self.prefs is not None:
            self.prefs.set("faixa", self.faixa.currentData())
        self.refresh()

    def _card_grade(self) -> Card:
        from .grade import GradeWidget

        card = Card(padding=Space.sm)
        card.body.setSpacing(0)

        self.grade = GradeWidget(self)
        self.grade.selecionado.connect(self._selecionar)
        self.grade.aberto.connect(self.abrir_ficha.emit)
        self.grade.vazio.connect(self._clicou_no_vazio)
        self.grade.menu_pedido.connect(self._menu_do_compromisso)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area.setWidget(self.grade)
        card.body.addWidget(self.area)
        return card

    def _posicionar_a_grade(self) -> None:
        """Rola a grade ate a parte util do dia.

        Com o dia inteiro na tela nem sempre cabem as 24 linhas. Abrir em
        00:00 mostraria a madrugada vazia e esconderia a manha, entao a tela
        se posiciona no primeiro compromisso da semana - ou na hora de agora,
        se nao houver nenhum.
        """
        grade = self.grade.grade
        horas = [c.inicio_dt.hour for dia in grade.dias for c in dia.compromissos
                 if c.inicio_dt is not None]
        if horas:
            alvo = min(horas)
        elif any(dia.e_hoje for dia in grade.dias):
            alvo = datetime.now().hour
        else:
            alvo = 8
        barra = self.area.verticalScrollBar()
        barra.setValue(min(self.grade.y_da_hora_cheia(max(alvo - 1, 0)),
                           barra.maximum()))

    def _rodape(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.md)

        for tipo, rotulo in TIPO_LABEL.items():
            linha.addWidget(tone_label(f"■ {rotulo}", TIPO_TOM[tipo], "caption"))
        linha.addStretch(1)

        self.aviso = label("Clique num horário vago para marcar ali.", "muted")
        linha.addWidget(self.aviso)

        self.botao_abrir = Button("Abrir", "file")
        self.botao_abrir.clicked.connect(self._abrir)
        linha.addWidget(self.botao_abrir)

        self.botao_concluir = Button("Concluir", "check", "success")
        self.botao_concluir.clicked.connect(self._concluir)
        linha.addWidget(self.botao_concluir)
        return linha

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        dias = self.modo.currentData() or 7
        inicial, final = faixa_por_chave(self.faixa.currentData() or FAIXA_PADRAO)
        grade = self.repository.grade(self.primeiro_dia, dias=dias,
                                      hora_inicial=inicial, hora_final=final)
        self.grade.selecao = self.selecionado
        self.grade.set_grade(grade)
        # depois que o layout assentar: antes disso a barra ainda nao tem
        # tamanho e o valor seria descartado. Com `self` como contexto, o Qt
        # cancela o disparo se a tela morrer antes - sem isso o retorno cai
        # num widget destruido e derruba o processamento de eventos.
        QTimer.singleShot(0, self, self._posicionar_a_grade)

        ultimo = self.primeiro_dia + timedelta(days=dias - 1)
        if dias == 1:
            periodo = self.primeiro_dia.strftime("%d/%m/%Y")
        else:
            periodo = (f"{self.primeiro_dia.strftime('%d/%m')}"
                       f" a {ultimo.strftime('%d/%m/%Y')}")
        resumo = self.repository.resumo()
        texto = f"{periodo}  ·  {grade.total} na tela"
        if resumo.atrasados:
            texto += f"  ·  {resumo.atrasados} sem fechar"
        self.subtitulo.setText(texto)
        self._atualizar_acoes()

    def compromisso_selecionado(self) -> Compromisso | None:
        if self.selecionado is None:
            return None
        return self.repository.obter(self.selecionado)

    def _atualizar_acoes(self) -> None:
        compromisso = self.compromisso_selecionado()
        self.botao_abrir.setEnabled(compromisso is not None)
        self.botao_concluir.setEnabled(
            compromisso is not None and compromisso.em_aberto
            and not compromisso.e_bloqueio
        )
        if compromisso is None:
            self._dizer("Clique num horário vago para marcar ali.")
        else:
            self._dizer(
                f"{compromisso.horario}  ·  {compromisso.titulo}"
                f"  ·  {compromisso.tipo_label}"
            )

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------- acoes
    def _navegar(self, sentido: int) -> None:
        dias = self.modo.currentData() or 7
        self.primeiro_dia += timedelta(days=dias * sentido)
        self.refresh()

    def _ir_para_hoje(self) -> None:
        dias = self.modo.currentData() or 7
        self.primeiro_dia = (
            inicio_da_semana(date.today()) if dias == 7 else date.today()
        )
        self.refresh()

    def _modo_mudou(self) -> None:
        self._ir_para_hoje()

    def _selecionar(self, compromisso_id: int) -> None:
        self.selecionado = compromisso_id
        self.grade.selecao = compromisso_id
        self._atualizar_acoes()

    def _clicou_no_vazio(self, momento: str) -> None:
        self.selecionado = None
        self._atualizar_acoes()
        self.novo_em.emit(momento)

    def _abrir(self) -> None:
        if self.selecionado is not None:
            self.abrir_ficha.emit(self.selecionado)

    # ------------------------------------------------------- botao direito
    def _menu_do_compromisso(self, compromisso_id: int, onde) -> None:
        """O que da para fazer com o compromisso debaixo do cursor.

        A grade e onde o dia e olhado; obrigar a ir na lista para desmarcar
        alguma coisa era o caminho mais longo para a acao mais comum depois
        de abrir.
        """
        compromisso = self.repository.obter(compromisso_id)
        if compromisso is None:
            return
        cor = current_palette().text_muted
        menu = menu_arredondado(self)

        def item(texto: str, icone: str, gatilho):
            acao = menu.addAction(icons.icon(icone, cor, 16), texto)
            acao.triggered.connect(lambda _=False: gatilho())
            return acao

        item("Abrir", "file", lambda: self.abrir_ficha.emit(compromisso_id))
        if compromisso.em_aberto and not compromisso.e_bloqueio:
            item("Concluir", "check", self._concluir)
            item("Cancelar", "close", lambda: self._mudar_status(
                compromisso, CANCELADO, "cancelado"))
        elif compromisso.status == CANCELADO:
            item("Reabrir", "refresh", lambda: self._mudar_status(
                compromisso, AGENDADO, "reaberto"))
        menu.addSeparator()
        item("Excluir", "trash", lambda: self._excluir(compromisso))
        menu.popup(onde)
        self._menu_aberto = menu   # sem guardar, o Qt recolhe o menu na hora

    def _mudar_status(self, compromisso: Compromisso, status: str,
                      recado: str) -> None:
        self.repository.definir_status(compromisso.id, status)
        self.refresh()
        self._dizer(f"'{compromisso.titulo}' {recado}.", "success")
        self.data_changed.emit()

    def _excluir(self, compromisso: Compromisso) -> None:
        """Apaga o compromisso - a mesma pergunta da lista, no mesmo lugar."""
        if not confirmar(
            self,
            "Excluir compromisso",
            f"Excluir '{compromisso.titulo}' de {compromisso.horario}?",
            chave=confirmacoes.EXCLUIR,
            rotulo_ok="Excluir",
            detalhe="Esta ação não pode ser desfeita.",
        ):
            return
        self.repository.excluir(compromisso.id)
        if self.selecionado == compromisso.id:
            self.selecionado = None
            self.grade.selecao = None
        self.refresh()
        self._dizer(f"'{compromisso.titulo}' excluído.", "success")
        self.data_changed.emit()

    def _concluir(self) -> None:
        compromisso = self.compromisso_selecionado()
        if compromisso is None:
            return
        self.repository.definir_status(compromisso.id, CONCLUIDO)
        self.refresh()
        self._dizer(f"'{compromisso.titulo}' marcado como concluído.", "success")
        self.data_changed.emit()
