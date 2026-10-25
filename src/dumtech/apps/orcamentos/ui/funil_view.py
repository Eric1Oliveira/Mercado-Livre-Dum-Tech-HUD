"""O funil: quantas propostas viram venda, e por que as outras nao viraram.

Este modulo nao tem "Painel" separado - esta tela e o painel dele. Criar as duas
seria a mesma tela com dois nomes.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ....ui import format as fmt
from ....ui.graficos import ALTURA_TRACO, pintar_tracos
from ....ui.theme import Space, current_palette, palette_for
from ....ui.widgets.common import Card, FaixaDeNumeros, StatCard, label, separator, tone_label
from ....ui.widgets.panels import ListPanel, cabeca_de_painel
from ..models import EtapaFunil
from ..repository import ESPERA_LONGA, OrcamentosRepository


class Barra(QWidget):
    """A largura diz o peso da etapa; o numero sozinho nao mostra a forma.

    Em tracos, como toda barra de "quanto" da plataforma (`pintar_tracos`):
    uma barra cheia aqui destoava do resto dos modulos.
    """

    def __init__(self, tom: str = "accent", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tom = tom
        self._fracao = 0.0
        self._palette = palette_for(parent) if parent else current_palette()
        self.setFixedHeight(ALTURA_TRACO)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_fracao(self, fracao: float, tom: str = "") -> None:
        self._fracao = max(0.0, min(float(fracao), 1.0))
        if tom:
            self._tom = tom
        self.update()

    def apply_theme(self, palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (assinatura do Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pintar_tracos(painter, 0, 0, self.width(), self._fracao,
                      QColor(self._palette.resolve(self._tom)), self._palette)
        painter.end()


def _abrir_linha(caixa: QWidget, com_fio: bool) -> QVBoxLayout:
    """O corpo de uma linha do funil, com o fio tracejado acima (menos na 1a).

    O fio mora DENTRO da linha, e nao entre as linhas no layout: assim a lista
    continua sendo so de etapas (quatro etapas, quatro itens), como antes.
    """
    raiz = QVBoxLayout(caixa)
    raiz.setContentsMargins(0, 0, 0, Space.sm + 2)
    raiz.setSpacing(Space.xs + 2)
    if com_fio:
        raiz.addWidget(separator(tracejado=True))
    raiz.addSpacing(Space.sm)
    return raiz


class LinhaEtapa(QWidget):
    """Uma etapa do funil: nome, quantidade, valor e a barra."""

    def __init__(self, etapa: EtapaFunil, parent: QWidget | None = None,
                 com_fio: bool = False) -> None:
        super().__init__(parent)
        raiz = _abrir_linha(self, com_fio)

        topo = QHBoxLayout()
        topo.setSpacing(Space.sm)
        topo.addWidget(tone_label(etapa.label, etapa.tom, "strong"), 1)
        self.quantidade = label("", "muted")
        topo.addWidget(self.quantidade)
        self.valor = tone_label("", etapa.tom, "strong")
        topo.addWidget(self.valor)
        raiz.addLayout(topo)

        self.barra = Barra(etapa.tom)
        raiz.addWidget(self.barra)
        self.atualizar(etapa, etapa.valor or 1.0)

    def atualizar(self, etapa: EtapaFunil, maior: float) -> None:
        self.quantidade.setText(fmt.contagem(etapa.quantidade, "proposta"))
        self.valor.setText(fmt.moeda(etapa.valor))
        self.barra.set_fracao(etapa.valor / maior if maior else 0.0)


class FunilView(QWidget):
    """Etapas, conversao, o que esta parado e por que voce perde."""

    data_changed = Signal()

    def __init__(self, repository: OrcamentosRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self._linhas: dict[str, LinhaEtapa] = {}

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Funil", "title"))
        self.subtitulo = label("Quantas propostas viram venda", "subtitle")
        titulos.addWidget(self.subtitulo)
        raiz.addLayout(titulos)

        raiz.addWidget(self._cartoes())

        colunas = QHBoxLayout()
        colunas.setSpacing(Space.lg)
        colunas.addWidget(self._card_etapas(), 2)
        colunas.addWidget(self._card_motivos(), 2)
        raiz.addLayout(colunas)

        paineis = QHBoxLayout()
        paineis.setSpacing(Space.lg)
        # parado ha dias e o que faz alguem pegar o telefone
        self.painel_esperando = ListPanel(
            "Esperando resposta", "Nenhuma proposta aguardando o cliente."
        )
        paineis.addWidget(self.painel_esperando, 3)
        self.painel_vencendo = ListPanel(
            "Vence nos próximos 7 dias", "Nenhuma proposta perto do vencimento."
        )
        paineis.addWidget(self.painel_vencendo, 3)
        raiz.addLayout(paineis, 1)

        self.refresh()

    # ------------------------------------------------------------------ pedacos
    def _cartoes(self) -> FaixaDeNumeros:
        linha = FaixaDeNumeros()
        self.card_conversao = StatCard("Taxa de conversão", "0%", "chart", "success")
        self.card_aberto = StatCard("Em aberto", "R$ 0,00", "file", "accent")
        self.card_aprovado = StatCard("Aprovado no mês", "R$ 0,00", "check", "success")
        self.card_ticket = StatCard("Ticket médio", "R$ 0,00", "money", "warning")
        for cartao in (self.card_conversao, self.card_aberto, self.card_aprovado,
                       self.card_ticket):
            linha.add(cartao)
        return linha

    def _card(self, titulo: str) -> tuple[Card, QVBoxLayout]:
        """Cartao com a mesma cabeca e o mesmo respiro dos paineis da plataforma."""
        card = Card(padding=Space.lg + 4)
        card.body.setSpacing(Space.sm)
        topo, _nota = cabeca_de_painel(titulo)
        card.body.addLayout(topo)
        linhas = QVBoxLayout()
        linhas.setSpacing(0)
        card.body.addLayout(linhas)
        card.body.addStretch(1)
        return card, linhas

    def _card_etapas(self) -> Card:
        card, self._etapas = self._card("Por etapa")
        return card

    def _card_motivos(self) -> Card:
        card, self._motivos = self._card("Por que você perde")
        return card

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        resumo = self.repository.resumo(limite_listas=6)

        self.card_conversao.set_value(
            f"{resumo.conversao:.0f}%".replace(".", ","),
            f"{fmt.contagem(resumo.aprovados_mes, 'aprovada')} de "
            f"{fmt.contagem(resumo.respondidos, 'respondida')}"
            if resumo.respondidos else "nenhuma proposta respondida ainda",
        )
        self.card_aberto.set_value(
            fmt.moeda(resumo.valor_em_aberto),
            fmt.contagem(resumo.abertos, "proposta") + " em aberto"
        )
        self.card_aprovado.set_value(fmt.moeda(resumo.valor_aprovado_mes))
        self.card_ticket.set_value(fmt.moeda(resumo.ticket_medio), "por proposta aprovada")

        self.subtitulo.setText(
            fmt.contagem(resumo.total, "proposta") + " no total"
            if resumo.total else "Nenhuma proposta cadastrada ainda"
        )

        self._preencher_etapas(resumo)
        self._preencher_motivos(resumo)

        self.painel_esperando.set_items([
            (
                orcamento.cliente,
                f"{orcamento.numero}  ·  {self._espera(orcamento)}",
                fmt.moeda(orcamento.total),
                "danger" if (orcamento.dias_esperando or 0) >= ESPERA_LONGA else "accent",
            )
            for orcamento in resumo.aguardando
        ])

        self.painel_vencendo.set_items([
            (
                orcamento.cliente,
                f"{orcamento.numero}  ·  {fmt.prazo_texto(orcamento.vale_ate)}",
                fmt.moeda(orcamento.total),
                "danger" if orcamento.vencido else "warning",
            )
            for orcamento in resumo.vencendo
        ])

    @staticmethod
    def _espera(orcamento) -> str:
        dias = orcamento.dias_esperando
        if dias is None:
            return "sem data de envio"
        if dias == 0:
            return "enviada hoje"
        return f"parada há {fmt.dias(dias)}"

    def _preencher_etapas(self, resumo) -> None:
        self._limpar(self._etapas)
        maior = max((etapa.valor for etapa in resumo.etapas), default=0.0)
        for posicao, etapa in enumerate(resumo.etapas):
            linha = LinhaEtapa(etapa, self, com_fio=posicao > 0)
            linha.atualizar(etapa, maior)
            self._etapas.addWidget(linha)

    def _preencher_motivos(self, resumo) -> None:
        self._limpar(self._motivos)
        if not resumo.motivos:
            self._motivos.addWidget(
                label(
                    "Nenhuma proposta recusada ainda. Quando uma for, o motivo "
                    "aparece aqui.",
                    "muted",
                )
            )
            return

        maior = max(quantidade for _, quantidade, _ in resumo.motivos)
        for posicao, (rotulo, quantidade, valor) in enumerate(resumo.motivos):
            self._motivos.addWidget(
                self._linha_motivo(rotulo, quantidade, valor, maior, com_fio=posicao > 0)
            )

    def _linha_motivo(self, rotulo: str, quantidade: int, valor: float,
                      maior: int, com_fio: bool = False) -> QWidget:
        caixa = QWidget()
        raiz = _abrir_linha(caixa, com_fio)

        topo = QHBoxLayout()
        topo.setSpacing(Space.sm)
        topo.addWidget(label(rotulo, "strong"), 1)
        topo.addWidget(label(f"{quantidade}x", "muted"))
        topo.addWidget(tone_label(fmt.moeda(valor), "danger", "strong"))
        raiz.addLayout(topo)

        barra = Barra("danger", self)
        barra.set_fracao(quantidade / maior if maior else 0.0)
        raiz.addWidget(barra)
        return caixa

    @staticmethod
    def _limpar(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
