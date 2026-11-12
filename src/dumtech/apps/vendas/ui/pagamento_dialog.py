"""Recebimento: uma ou varias formas na mesma venda, e o troco.

Este dialogo e o unico lugar do sistema onde alguem esta com a fila esperando.
Ele abre com a linha em dinheiro ja preenchida com o total e o foco em
"Recebido": digitar 200 e apertar Enter duas vezes fecha a venda.

DOIS JEITOS DE ABRIR

* no Balcao: as linhas fecham o total da venda. E ali que se escolhe Prazo
  (o cliente leva e paga depois) ou Parcelado - com ou sem entrada ("300 hoje
  e mais 3 de 350").
* na venda pendente (`parcial=True`): o cliente voltou para pagar. Pode pagar
  tudo ou so uma parte ("da 100 dos 150"); o resto continua em aberto, na
  venda e no Financeiro. Cada forma e uma linha: o Pix nao entra na gaveta
  como dinheiro.

O miolo rola e a janela acompanha o conteudo (`ui/tela.py`): escolher Pix
abre o QR Code sem empurrar o Receber para fora da tela.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ....core.contas import MAXIMO_PARCELAS, vencimento_padrao
from ....core.pagamentos import (
    PARCELADO,
    PRAZO,
    forma_canonica,
    formas_a_vista,
    formas_do_balcao,
)
from ....ui import format as fmt
from ....ui.tela import caber_na_tela, natural_com_miolo, vigiar
from ....ui.theme import Space, apply_window_theme, palette_for
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import label, repolish, separator, tone_label
from ....ui.widgets.painel_pix import PainelPix
from ....ui.widgets.rolagem import rolavel_no_dialogo
from ....ui.widgets.table import DIREITA, DataTable
from ..models import DINHEIRO, PARCELAS_PADRAO, PIX, Pagamento, VendaError
from ..repository.comum import CENTAVO, dinheiro

#: altura da lista de formas: vazia so precisa do cabecalho e do recado - no
#: notebook, cada pixel a menos e o QR do Pix inteiro sem rolar
TABELA_CHEIA = 150
TABELA_VAZIA = 100

#: campo de valor que mostra "R$ 12.345,67" inteiro
LARGURA_VALOR = 164

#: a largura da janela: a forma, os dois valores e o Lancar lado a lado
LARGURA = 680


def nota_parcelas(valor: float, parcelas: int, entrada: float = 0.0,
                  forma_entrada: str = "") -> str:
    """O que vai acontecer com o dinheiro, dito antes de acontecer."""
    entrada = dinheiro(entrada)
    parcela = fmt.moeda(dinheiro((valor - entrada) / max(parcelas, 1)))
    if entrada > 0:
        em = f" em {forma_entrada}" if forma_entrada else ""
        inicio = f"Entrada de {fmt.moeda(entrada)} hoje{em} + {parcelas}x de {parcela}"
    else:
        inicio = f"{parcelas}x de {parcela}"
    return (
        f"{inicio}. A 1ª vence na data escolhida e as outras, todo mês: cada parcela "
        "vira uma conta a receber no Financeiro."
    )


class PagamentoDialog(QDialog):
    """Recebe o pagamento de uma venda ja montada."""

    def __init__(
        self,
        total: float,
        titulo: str = "",
        conferir=None,
        parent: QWidget | None = None,
        empresa=None,
        parcelavel: bool = False,
        cliente: str = "",
        parcial: bool = False,
    ) -> None:
        super().__init__(parent)
        #: o que esta sendo cobrado: o total da venda, ou o que falta dela
        self.total = dinheiro(total)
        #: quem valida (o repositorio); injetado para o dialogo nao conhecer regra
        self._conferir = conferir
        #: de onde sai a chave Pix; None quando o dialogo roda sem Hub
        self.empresa = empresa
        #: venda pendente: o cliente pode pagar so uma parte, e o resto fica
        #: em aberto sozinho - por isso aqui nao existe Prazo nem Parcelado
        self.parcial = parcial
        #: so quem sabe levar as parcelas ao Financeiro oferece esta forma
        self.parcelavel = parcelavel and not parcial
        #: parcela sem cliente nao tem de quem cobrar; o aviso vem antes de fechar
        #: a venda, porque a esta altura outra linha ja pode ter sido paga
        self.cliente = cliente.strip()
        self.pagamentos: list[Pagamento] = []
        self._ajustado = False
        #: o valor de antes, para o Recebido saber se estava so acompanhando
        self._valor_anterior = self.total

        self.setWindowTitle("Receber")
        self.setModal(True)
        self.setMinimumWidth(560)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)

        cabecalho = QVBoxLayout()
        cabecalho.setSpacing(2)
        cabecalho.addWidget(label("Receber", "section"))
        cabecalho.addWidget(label(titulo or "Pagamento da venda", "muted"))
        raiz.addLayout(cabecalho)

        # o miolo rola; o cabecalho e os botoes ficam sempre a vista
        miolo = QVBoxLayout()
        miolo.setContentsMargins(0, 0, 0, 0)
        miolo.setSpacing(Space.md)
        miolo.addWidget(self._painel_total())
        miolo.addWidget(separator())
        miolo.addWidget(self._linha_lancamento())
        miolo.addWidget(self._linha_conta())

        self.nota_parcelas = label("", "dim")
        self.nota_parcelas.setWordWrap(True)
        self.nota_parcelas.setVisible(False)
        miolo.addWidget(self.nota_parcelas)

        miolo.addWidget(self._painel_pix())

        self.tabela = DataTable(["Forma", "Valor", "Recebido"])
        self.tabela.setMaximumHeight(TABELA_CHEIA)
        # vazia, ela ensina o que da para fazer - e ocupa menos (ver `_atualizar`)
        self.tabela.set_empty_message("Pagou de mais de um jeito? Lance cada forma: "
                                      "ela aparece aqui.")
        self.tabela.itemSelectionChanged.connect(self._atualizar_acoes)
        miolo.addWidget(self.tabela)

        miolo.addLayout(self._rodape())
        miolo.addStretch(1)

        self._interno = QWidget()
        self._interno.setLayout(miolo)
        self._area = rolavel_no_dialogo(self._interno)
        raiz.addWidget(self._area, 1)

        raiz.addWidget(separator())
        raiz.addLayout(self._botoes())
        vigiar(self, self._interno)

        apply_window_theme(self, palette_for(parent))
        self._atualizar()
        self.recebido.setFocus()
        self.recebido.selectAll()

    # ------------------------------------------------------------------ tamanho
    def showEvent(self, evento) -> None:  # noqa: N802 (Qt)
        # so na primeira vez: depois quem cuida e o reajuste (`ui/tela.py`)
        if not self._ajustado:
            self._ajustado = True
            self.resize(self.tamanho_natural())
            caber_na_tela(self, centralizar=True)
        super().showEvent(evento)

    def tamanho_natural(self) -> QSize:
        """Tudo a vista, sem rolar (a tela ainda pode aparar)."""
        return natural_com_miolo(self, self._interno, self._area, LARGURA)

    # ------------------------------------------------------------------ pedacos
    def _painel_total(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.addWidget(label("Em aberto" if self.parcial else "Total da venda", "muted"))
        linha.addStretch(1)
        self.rotulo_total = tone_label(fmt.moeda(self.total), "accent", "metric")
        linha.addWidget(self.rotulo_total)
        return caixa

    def _formas(self, conta: bool = True) -> list[str]:
        """As formas liberadas em Configuracoes > Pagamentos.

        `conta=False` tira as que viram conta (Prazo e Parcelado): a entrada
        do parcelado e o recebimento da venda pendente sao dinheiro de agora.
        """
        ocultas = getattr(self.empresa, "formas_ocultas", ())
        if conta and not self.parcial:
            return formas_do_balcao(ocultas, self.parcelavel)
        return formas_a_vista(ocultas)

    def _linha_lancamento(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(Space.md)

        self.forma = QComboBox()
        self.forma.setEditable(True)
        self.forma.addItems(self._formas())
        self.forma.setCurrentText(DINHEIRO)
        self.forma.currentTextChanged.connect(self._forma_mudou)
        linha.addWidget(form.campo("Forma", self.forma), 3)

        self.valor = form.dinheiro(self.total)
        self.valor.valueChanged.connect(self._valor_mudou)
        linha.addWidget(form.campo("Valor", self.valor), 2)

        self.recebido = form.dinheiro(self.total)
        self.campo_recebido = form.campo("Recebido", self.recebido)
        linha.addWidget(self.campo_recebido, 2)

        # no lugar do Recebido: parcelado nao da troco, e o dialogo nao cresce
        self.parcelas = form.inteiro(PARCELAS_PADRAO, minimo=2, maximo=MAXIMO_PARCELAS)
        self.parcelas.valueChanged.connect(self._atualizar_parcelas)
        self.campo_parcelas = form.campo("Parcelas", self.parcelas)
        self.campo_parcelas.setVisible(False)
        linha.addWidget(self.campo_parcelas, 2)

        self.botao_lancar = Button("Lançar", "plus")
        self.botao_lancar.clicked.connect(self._lancar)
        linha.addWidget(form.campo(" ", self.botao_lancar), 1)
        self._caber_valor(self.valor, self.recebido)
        return caixa

    @staticmethod
    def _caber_valor(*campos) -> None:
        """O valor inteiro a vista: "R$ 1.350,0" (sem o ultimo zero) confunde.

        As setas e o respiro do campo comem uns 70 pixels; com 140, o que
        sobrava para o numero cortava o ultimo digito de qualquer milhar.
        """
        for campo in campos:
            campo.setMinimumWidth(max(campo.minimumWidth(), LARGURA_VALOR))

    def _linha_conta(self) -> QWidget:
        """O que so existe quando parte vira conta: entrada e vencimento."""
        self.linha_conta = QWidget()
        linha = QHBoxLayout(self.linha_conta)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(Space.md)

        # "300 hoje e mais 3 de 350": a entrada e a primeira linha do parcelado
        self.entrada = form.dinheiro(0.0)
        self.entrada.valueChanged.connect(self._atualizar_parcelas)
        self.campo_entrada = form.campo("Entrada (paga hoje)", self.entrada)
        self._caber_valor(self.entrada)
        linha.addWidget(self.campo_entrada, 2)

        self.forma_entrada = QComboBox()
        self.forma_entrada.addItems(self._formas(conta=False))
        self.forma_entrada.setCurrentText(DINHEIRO)
        self.forma_entrada.currentTextChanged.connect(self._atualizar_parcelas)
        self.campo_forma_entrada = form.campo("Entrada em", self.forma_entrada)
        linha.addWidget(self.campo_forma_entrada, 3)

        # so para o que vira conta: quem paga agora nao tem vencimento
        self.vencimento = form.data(vencimento_padrao())
        self.campo_vencimento = form.campo("Vencimento", self.vencimento)
        self.rotulo_vencimento = self.campo_vencimento.findChild(QLabel)
        linha.addWidget(self.campo_vencimento, 2)
        linha.addStretch(1)
        return self.linha_conta

    def _rodape(self) -> QHBoxLayout:
        rodape = QHBoxLayout()
        rodape.setSpacing(Space.xl)

        faltando = QVBoxLayout()
        faltando.setSpacing(1)
        faltando.addWidget(label("Falta receber", "field"))
        self.rotulo_falta = tone_label(fmt.moeda(self.total), "warning", "cardTitle")
        faltando.addWidget(self.rotulo_falta)
        rodape.addLayout(faltando)

        troco = QVBoxLayout()
        troco.setSpacing(1)
        troco.addWidget(label("Troco", "field"))
        self.rotulo_troco = tone_label(fmt.moeda(0), "success", "cardTitle")
        troco.addWidget(self.rotulo_troco)
        rodape.addLayout(troco)

        rodape.addStretch(1)
        self.botao_remover = Button("Remover linha", "trash", "ghost")
        self.botao_remover.clicked.connect(self._remover)
        rodape.addWidget(self.botao_remover)
        return rodape

    def _botoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        linha.addWidget(self.aviso, 1)

        cancelar = Button("Cancelar")
        cancelar.setAutoDefault(False)
        cancelar.clicked.connect(self.reject)
        linha.addWidget(cancelar)

        self.botao_receber = Button("Receber", "check", "success")
        self.botao_receber.setMinimumHeight(38)
        self.botao_receber.setDefault(True)
        self.botao_receber.clicked.connect(self._confirmar)
        linha.addWidget(self.botao_receber)
        return linha

    def _painel_pix(self) -> QWidget:
        """O QR Code que o cliente aponta o celular.

        Fica escondido ate alguem escolher Pix: e uma forma entre seis, e o
        dialogo do balcao nao pode ficar maior por causa de quem paga em
        dinheiro. O desenho em si e o painel da plataforma, o mesmo que o
        Financeiro e as Ordens usam.
        """
        self.painel_pix = PainelPix(self.empresa)
        # nomes antigos, mesma coisa: o resto do dialogo (e os testes) leem daqui
        self.imagem_pix = self.painel_pix.imagem
        self.texto_pix = self.painel_pix.texto
        self.botao_copiar_pix = self.painel_pix.botao_copiar
        self.recado_pix = self.painel_pix.recado
        self.painel_pix.setVisible(False)
        return self.painel_pix

    @property
    def payload_pix(self) -> str:
        """O copia e cola de agora - vazio quando nao ha o que cobrar."""
        return self.painel_pix.payload

    def _atualizar_pix(self) -> None:
        """Refaz o QR para o valor que esta no campo agora.

        Sem valor (tudo ja lancado) nao ha o que cobrar: o QR sai da frente.
        """
        if not self._em_pix() or self.valor.value() <= 0:
            self.painel_pix.setVisible(False)
            return
        self.painel_pix.setVisible(True)
        self.painel_pix.atualizar(self.valor.value())

    def _copiar_pix(self) -> None:
        if self.painel_pix.copiar():
            self._dizer("Código Pix copiado - cole no aplicativo do cliente.", "success")

    def _em_pix(self) -> bool:
        return self.forma.currentText().strip().casefold() == PIX.casefold()

    # -------------------------------------------------------------------- conta
    @property
    def pago(self) -> float:
        return dinheiro(sum(p.valor for p in self.pagamentos))

    @property
    def falta(self) -> float:
        return dinheiro(max(self.total - self.pago, 0.0))

    @property
    def troco(self) -> float:
        return dinheiro(
            sum(max(p.recebido - p.valor, 0.0) for p in self.pagamentos if p.em_dinheiro)
        )

    @property
    def vencimento_iso(self) -> str:
        """Quando vence a conta; vazio quando ninguem ficou devendo."""
        vira_conta = any(p.parcelado or p.a_prazo for p in self.pagamentos)
        return form.iso_da_data(self.vencimento) if vira_conta else ""

    def _em_dinheiro(self) -> bool:
        return forma_canonica(self.forma.currentText()) == DINHEIRO

    def _em_parcelado(self) -> bool:
        return (self.parcelavel
                and self.forma.currentText().strip().casefold() == PARCELADO.casefold())

    def _vira_conta(self) -> bool:
        return (self._em_parcelado()
                or self.forma.currentText().strip().casefold() == PRAZO.casefold())

    # ------------------------------------------------------------------- acoes
    def _forma_mudou(self, _texto: str = "") -> None:
        parcelado = self._em_parcelado()
        # so dinheiro tem troco: nas outras formas o recebido acompanha o valor
        self.recebido.setEnabled(self._em_dinheiro())
        if not self._em_dinheiro():
            self.recebido.setValue(self.valor.value())
        self.campo_recebido.setVisible(not parcelado)
        self.campo_parcelas.setVisible(parcelado)
        self.campo_entrada.setVisible(parcelado)
        self.campo_forma_entrada.setVisible(parcelado)
        vencimento = self._vira_conta() or any(p.parcelado or p.a_prazo for p in self.pagamentos)
        self.campo_vencimento.setVisible(vencimento)
        self.rotulo_vencimento.setText("1ª parcela vence" if parcelado else "Vencimento")
        self.linha_conta.setVisible(parcelado or vencimento)
        self._atualizar_parcelas()
        self._atualizar_pix()

    def _valor_mudou(self, valor: float) -> None:
        # o Recebido acompanha o Valor enquanto ninguem mexeu nele: baixar o
        # valor para dividir a conta nao pode inventar um troco
        acompanhava = abs(self.recebido.value() - self._valor_anterior) < CENTAVO
        if not self._em_dinheiro() or acompanhava or self.recebido.value() < valor:
            self.recebido.setValue(valor)
        self._valor_anterior = valor
        self._atualizar_parcelas()
        self._atualizar_pix()
        self._atualizar_acoes()

    def _atualizar_parcelas(self, *_args) -> None:
        self.nota_parcelas.setVisible(self._em_parcelado())
        if self._em_parcelado():
            self.nota_parcelas.setText(nota_parcelas(
                self.valor.value(), self.parcelas.value(),
                self.entrada.value(), self.forma_entrada.currentText(),
            ))

    def _lancar(self) -> None:
        valor = dinheiro(self.valor.value())
        if valor <= 0:
            self._dizer("Informe um valor maior que zero.", "danger")
            return
        recebido = dinheiro(self.recebido.value()) if self._em_dinheiro() else valor
        if recebido < valor:
            self._dizer("O recebido não cobre o valor lançado.", "danger")
            return

        parcelado = self._em_parcelado()
        if self._vira_conta() and not self.cliente:
            self._dizer(
                f"Para {'parcelar' if parcelado else 'vender a prazo'}, feche esta "
                "janela e informe o cliente.", "danger",
            )
            return
        if parcelado and any(p.parcelado for p in self.pagamentos):
            self._dizer("Esta venda já tem uma linha parcelada.", "danger")
            return
        entrada = dinheiro(self.entrada.value()) if parcelado else 0.0
        if entrada and entrada + CENTAVO >= valor:
            self._dizer("A entrada precisa ser menor que o valor: o resto é que vira "
                        "parcelas.", "danger")
            return

        if entrada:
            forma = forma_canonica(self.forma_entrada.currentText()) or DINHEIRO
            self.pagamentos.append(Pagamento(forma=forma, valor=entrada, recebido=entrada))
        self.pagamentos.append(Pagamento(
            forma=PARCELADO if parcelado else forma_canonica(self.forma.currentText()),
            valor=dinheiro(valor - entrada),
            recebido=dinheiro(recebido - entrada),
            parcelas=self.parcelas.value() if parcelado else 0,
        ))
        self.entrada.setValue(0.0)
        self._atualizar()

    def _remover(self) -> None:
        linha = self.tabela.currentRow()
        if 0 <= linha < len(self.pagamentos):
            self.pagamentos.pop(linha)
            self._atualizar()

    def _confirmar(self) -> None:
        # na venda pendente da para receber direto o que esta digitado, sem
        # passar pelo Lancar: "ela deu 100" e um clique so
        if self.parcial and not self.pagamentos:
            self._lancar()
            if not self.pagamentos:
                return
        try:
            if self._conferir is not None:
                self._conferir(self.total, self.pagamentos)
        except VendaError as erro:
            self._dizer(str(erro), "danger")
            return
        self.accept()

    # ------------------------------------------------------------------- tela
    def _atualizar(self) -> None:
        self.tabela.fill(
            [
                [
                    self.tabela.cell(p.rotulo),
                    self.tabela.cell(fmt.moeda(p.valor), DIREITA, bold=True),
                    self.tabela.cell(
                        fmt.moeda(p.recebido) if p.em_dinheiro else "-", DIREITA
                    ),
                ]
                for p in self.pagamentos
            ],
            {1: 140, 2: 140},
        )
        self.tabela.setMaximumHeight(TABELA_CHEIA if self.pagamentos else TABELA_VAZIA)
        self.rotulo_falta.setText(fmt.moeda(self.falta))
        self.rotulo_falta.setProperty("tone", "warning" if self.falta > CENTAVO else "muted")
        repolish(self.rotulo_falta)
        self.rotulo_troco.setText(fmt.moeda(self.troco))

        # a proxima linha ja vem preenchida com o que ainda falta
        self.valor.setValue(self.falta)
        self._forma_mudou()
        self._dizer("")
        if self.parcial and self.pagamentos and self.falta > CENTAVO:
            self._dizer(
                f"Faltam {fmt.moeda(self.falta)}. Lance outra forma ou clique em Receber "
                "parte: o resto continua em aberto."
            )
        self._atualizar_acoes()

    def _atualizar_acoes(self) -> None:
        fechou = self.falta <= CENTAVO
        if self.parcial:
            # direto do campo (sem linha) ou com as linhas lancadas. Passou do
            # que falta? O botao continua ativo: a conferencia diz o porque
            agora = self.pago if self.pagamentos else dinheiro(self.valor.value())
            self.botao_receber.setEnabled(agora > 0)
            parte = agora + CENTAVO < self.total
            self.botao_receber.setText("  Receber parte" if parte else "  Receber")
        else:
            self.botao_receber.setEnabled(fechou and bool(self.pagamentos))
        self.botao_lancar.setEnabled(not fechou)
        self.botao_remover.setEnabled(0 <= self.tabela.currentRow() < len(self.pagamentos))

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ---------------------------------------------------------------- teclado
    def keyPressEvent(self, event) -> None:  # noqa: N802 (assinatura do Qt)
        """Enter lanca a linha enquanto falta dinheiro; depois disso, recebe.

        Na venda pendente, depois da primeira linha o Enter recebe: o segundo
        Enter do costume do balcao nao pode lancar sozinho o resto que ja vem
        preenchido - a cliente deu 100, nao 150. Outra forma, so pelo Lancar.
        """
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.parcial and self.pagamentos:
                self._confirmar()
                return
            if self.falta > CENTAVO:
                self._lancar()
                return
        super().keyPressEvent(event)
