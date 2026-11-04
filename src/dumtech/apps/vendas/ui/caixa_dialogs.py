"""Caixinhas de decisao do caixa: abrir, sangrar, suprir, fechar e justificar."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.form import FormDialog
from .. import financeiro
from ..models import TIPO_SANGRIA, ConferenciaCaixa, VendaError
from ..repository import VendasRepository


class AbrirCaixaDialog(FormDialog):
    """Quanto de troco esta indo para a gaveta agora."""

    def __init__(self, repository: VendasRepository, parent: QWidget | None = None) -> None:
        self.repository = repository
        super().__init__(
            "Abrir caixa",
            "O valor de abertura é o troco que já está na gaveta",
            parent,
            largura=460,
        )
        self.valor = form.dinheiro(0.0)
        self.add_row("Valor de abertura", self.valor)
        self.add_note(
            "A partir daqui as vendas entram neste caixa e o fechamento cobra "
            "esse dinheiro de volta."
        )
        self.valor.setFocus()
        self.valor.selectAll()

    def salvar(self) -> None:
        self.repository.abrir_caixa(self.valor.value())


class MovimentoCaixaDialog(FormDialog):
    """Sangria (dinheiro saindo) ou suprimento (dinheiro entrando)."""

    def __init__(
        self,
        repository: VendasRepository,
        tipo: str = TIPO_SANGRIA,
        parent: QWidget | None = None,
        contas=None,
    ) -> None:
        self.repository = repository
        self.tipo = tipo
        #: ponte com o Financeiro; None quando a licenca nao o libera
        self.contas = contas
        self.recado = ""
        sangria = tipo == TIPO_SANGRIA
        super().__init__(
            "Sangria" if sangria else "Suprimento",
            "Dinheiro saindo da gaveta" if sangria else "Dinheiro entrando na gaveta",
            parent,
            largura=460,
        )
        self.valor = form.dinheiro(0.0)
        self.add_row("Valor", self.valor)
        self.motivo = form.texto(
            "", "Ex.: depósito no banco" if sangria else "Ex.: troco extra"
        )
        self.add_row("Motivo" if sangria else "Motivo (opcional)", self.motivo)
        self.destino = form.escolha([
            ("Foi para o banco ou para o cofre", "retirada"),
            ("Pagou uma despesa", "despesa"),
        ])
        if sangria and contas is not None:
            self.add_row("Para onde foi", self.destino)
        if sangria:
            self.add_note("A sangria precisa de motivo: é assim que o dinheiro se explica.")
        self.valor.setFocus()
        self.valor.selectAll()

    def salvar(self) -> None:
        movimento = self.repository.registrar_movimento(
            self.tipo, self.valor.value(), self.motivo.text()
        )
        self.recado = financeiro.movimento_de_caixa(
            self.contas, movimento, self.destino.currentData()
        )


class FecharCaixaDialog(FormDialog):
    """Conta o que esta na gaveta e compara com o esperado."""

    def __init__(
        self,
        repository: VendasRepository,
        conferencia: ConferenciaCaixa,
        parent: QWidget | None = None,
        contas=None,
    ) -> None:
        self.repository = repository
        self.conferencia = conferencia
        self.contas = contas
        self.resultado: ConferenciaCaixa | None = None
        super().__init__(
            "Fechar caixa",
            "Conte o dinheiro da gaveta e lance aqui",
            parent,
            largura=480,
        )
        self.contado = form.dinheiro(0.0)
        self.contado.valueChanged.connect(self._recalcular)
        self.add_row("Dinheiro contado", self.contado)
        self.observacoes = form.area("", "O que explica a diferença (opcional)", 60)
        self.add_row("Observações", self.observacoes)

        self.add_note("")
        self._nota = self.extras.itemAt(0).widget()
        self._recalcular()
        self.contado.setFocus()
        self.contado.selectAll()

    def _recalcular(self) -> None:
        diferenca = self.contado.value() - self.conferencia.esperado
        if abs(diferenca) < 0.005:
            veredito = "confere"
        elif diferenca > 0:
            veredito = f"sobrando {fmt.moeda(diferenca)}"
        else:
            veredito = f"faltando {fmt.moeda(abs(diferenca))}"
        self._nota.setText(
            f"Esperado na gaveta: {fmt.moeda(self.conferencia.esperado)}      ({veredito})"
        )

    def salvar(self) -> None:
        self.resultado = self.repository.fechar_caixa(
            self.contado.value(), self.observacoes.toPlainText()
        )
        financeiro.fechamento(self.contas, self.resultado)


class MotivoDialog(FormDialog):
    """Pergunta o porque de algo que nao pode acontecer em silencio."""

    def __init__(
        self,
        titulo: str,
        subtitulo: str = "",
        dica: str = "",
        parent: QWidget | None = None,
    ) -> None:
        self.motivo = ""
        super().__init__(titulo, subtitulo, parent, largura=460)
        self.campo = form.texto("", dica)
        self.add_row("Motivo", self.campo)
        self.campo.setFocus()

    def salvar(self) -> None:
        texto = self.campo.text().strip()
        if not texto:
            raise VendaError("Informe o motivo.")
        self.motivo = texto
