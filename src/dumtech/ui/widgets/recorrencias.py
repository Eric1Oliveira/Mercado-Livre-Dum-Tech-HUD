"""A tela "Recorrentes" do Vendas e das Ordens: o cadastro dos contratos.

Os dois modulos usam a mesma tela - muda so como cada um chama o documento
que o contrato gera ("venda" ou "ordem") e quantos dias antes ele aparece.
Quem transforma a vez em documento e o modulo (`gerar`, recebido pronto); a
tela so cadastra, pausa e conta o que aconteceu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import QHBoxLayout, QWidget

from ...core import recorrencia as motor
from .. import format as fmt
from . import form
from .buttons import Button
from .crud_view import CrudView
from .form import FormDialog
from .items_editor import ItemsEditor
from .table import DIREITA


@dataclass(frozen=True)
class Textos:
    """O que muda de um modulo para o outro."""

    #: "venda" / "ordem" - o que cada vez vira
    documento: str
    documentos: str
    #: exemplo do campo descricao
    exemplo: str
    #: quantos dias antes o documento aparece
    antecedencia: int
    #: frase curta sobre onde a vez aparece ("como venda pendente")
    onde: str


class RecorrenciaDialog(FormDialog):
    def __init__(
        self,
        repositorio: motor.RecorrenciasRepository,
        textos: Textos,
        rec: motor.Recorrencia | None = None,
        clientes: list[str] | None = None,
        catalogo=None,
        parent: QWidget | None = None,
    ) -> None:
        self.repositorio = repositorio
        self.rec = rec or motor.Recorrencia(numero=repositorio.proximo_numero())
        editando = rec is not None
        super().__init__(
            f"Recorrência {self.rec.numero}" if editando else "Nova recorrência",
            f"Cada vez vira {textos.onde} e vai ao Financeiro como conta a receber",
            parent,
            largura=700,
        )

        self.cliente = form.sugestao(self.rec.cliente, "Quem paga", clientes or [])
        self.add_row("Cliente", self.cliente)
        self.descricao = form.texto(self.rec.descricao, textos.exemplo)
        self.add_row("Descrição", self.descricao)

        self.frequencia = form.escolha(
            [(rotulo, chave) for chave, rotulo in motor.FREQUENCIAS], self.rec.frequencia
        )
        self.inicio = form.data(self.rec.inicio)
        self.add_row("Repete", form.linha(self.frequencia, "a partir de", self.inicio))
        # mexer nisso depois de gerar seria refazer a serie (a regra do motor)
        if not self.rec.pode_mudar_serie:
            for campo in (self.frequencia, self.inicio):
                campo.setEnabled(False)
                campo.setToolTip("Já foi gerada uma vez: para mudar, crie outra recorrência.")

        self.fim = form.data_opcional(self.rec.fim)
        self.fim.setPlaceholderText("dd/mm/aaaa  ·  em branco = sem data para acabar")
        self.add_row("Termina em", self.fim)

        self.itens = ItemsEditor(catalogo=catalogo)
        self.itens.set_items(self.rec.itens)
        self.itens.changed.connect(self._atualizar_total)
        self.add_row("Itens", self.itens)

        self.desconto = form.dinheiro(self.rec.desconto)
        self.desconto.valueChanged.connect(self._atualizar_total)
        self.add_row("Desconto", self.desconto)

        self.observacoes = form.area(self.rec.observacoes, "Combinado com o cliente", 56)
        self.add_row("Observações", self.observacoes)

        self.add_note("")
        self._nota_total = self.extras.itemAt(0).widget()
        self.add_note(
            f"{textos.documento.capitalize()} de cada vez aparece {textos.antecedencia} dias "
            "antes da data. Pausar para de gerar; retomar não cobra o que ficou para trás."
        )
        self._atualizar_total()
        self.cliente.setFocus()

    def _atualizar_total(self) -> None:
        total = max(self.itens.total - self.desconto.value(), 0)
        self._nota_total.setText(
            f"Cada vez: {fmt.moeda(total)}"
            + (f"   (desconto de {fmt.moeda(self.desconto.value())})"
               if self.desconto.value() else "")
        )

    def salvar(self) -> None:
        self.rec.cliente = self.cliente.text()
        self.rec.descricao = self.descricao.text()
        self.rec.frequencia = self.frequencia.currentData()
        self.rec.inicio = form.iso_da_data(self.inicio)
        self.rec.fim = self.fim.iso()
        self.rec.itens = self.itens.items()
        self.rec.desconto = self.desconto.value()
        self.rec.observacoes = self.observacoes.toPlainText()
        self.repositorio.salvar(self.rec)


class RecorrenciasView(CrudView):
    titulo = "Recorrentes"
    nome_registro = "recorrência"
    nome_plural = "recorrências"
    genero = "f"
    rotulo_novo = "Nova recorrência"
    dica_pesquisa = "Pesquisar por número, cliente ou descrição..."
    colunas = ["Número", "Cliente", "Descrição", "Repete", "Cada vez", "Próxima",
               "Geradas", "Situação"]
    larguras = {0: 150, 1: 170, 3: 130, 4: 110, 5: 200, 6: 80, 7: 100}

    def __init__(
        self,
        repositorio: motor.RecorrenciasRepository,
        textos: Textos,
        gerar: Callable[[], list[str]],
        contar: Callable[[list[motor.Recorrencia]], None],
        clientes: list[str] | None = None,
        catalogo=None,
        parent: QWidget | None = None,
    ) -> None:
        self.repositorio = repositorio
        self.textos = textos
        self.gerar = gerar
        self.contar = contar
        self.clientes = clientes or []
        self.catalogo = catalogo
        super().__init__(parent)
        self.tabela.set_empty_message(
            f"Mensalidade, contrato, {textos.documento} que se repete: cadastre aqui "
            f"e cada {textos.documento} aparece sozinha na data."
        )

    def build_actions(self, layout: QHBoxLayout) -> None:
        self.botao_pausar = Button("Pausar", "close")
        self.botao_pausar.clicked.connect(self._pausar_ou_retomar)
        layout.insertWidget(1, self.botao_pausar)

    # ------------------------------------------------------------------- dados
    def carregar(self) -> list[motor.Recorrencia]:
        contratos = self.repositorio.listar(self.busca.text())
        self.contar(contratos)
        return contratos

    def montar_linha(self, rec: motor.Recorrencia) -> list:
        proxima = rec.proxima if rec.situacao != motor.PAUSADA else ""
        return [
            self.tabela.cell(rec.numero, bold=True, data=rec.id),
            self.tabela.cell(rec.cliente),
            self.tabela.cell(rec.descricao or "-"),
            self.tabela.cell(rec.frequencia_label),
            self.tabela.cell(fmt.moeda(rec.valor), DIREITA, "accent", bold=True),
            self.tabela.cell(
                f"{fmt.data(proxima)}  ({fmt.prazo_texto(proxima)})" if proxima else "-"
            ),
            self.tabela.cell(fmt.numero(rec.gerados), DIREITA),
            self.tabela.cell(rec.situacao_label, tone=rec.situacao_tom),
        ]

    def _atualizar_acoes(self) -> None:
        super()._atualizar_acoes()
        rec = self.registro_selecionado()
        pausada = rec is not None and rec.situacao == motor.PAUSADA
        self.botao_pausar.setText("Retomar" if pausada else "Pausar")
        self.botao_pausar.set_icon_name("refresh" if pausada else "close")
        self.botao_pausar.setEnabled(rec is not None and rec.situacao != motor.ENCERRADA)

    # ------------------------------------------------------------------- acoes
    def abrir_dialogo(self, rec: motor.Recorrencia | None):
        return RecorrenciaDialog(self.repositorio, self.textos, rec, self.clientes,
                                 self.catalogo, self)

    def novo(self) -> None:
        self._cadastrar(None)

    def editar(self) -> None:
        rec = self.registro_selecionado()
        if rec is not None:
            self._cadastrar(rec)

    def _cadastrar(self, rec: motor.Recorrencia | None) -> None:
        dialogo = self.abrir_dialogo(rec)
        if not dialogo.exec():
            return
        criados = self.gerar()
        self.refresh()
        recado = f"Recorrência {dialogo.rec.numero} salva."
        if criados:
            recado += (f" {fmt.contagem(len(criados), self.textos.documento, self.textos.documentos)}"
                       f" já gerada{'s' if len(criados) > 1 else ''}: {', '.join(criados)}.")
        self.mostrar_aviso(recado, "success")
        self.data_changed.emit()

    def _pausar_ou_retomar(self) -> None:
        rec = self.registro_selecionado()
        if rec is None:
            return
        if rec.situacao == motor.PAUSADA:
            self.repositorio.retomar(rec.id)
            self.gerar()
            recado = f"Recorrência {rec.numero} retomada."
        else:
            self.repositorio.pausar(rec.id)
            recado = (f"Recorrência {rec.numero} pausada. O que já foi gerado continua - "
                      f"cancele por lá se precisar.")
        self.refresh()
        self.mostrar_aviso(recado, "success")
        self.data_changed.emit()

    def excluir(self, rec: motor.Recorrencia) -> None:
        self.repositorio.excluir(rec.id)

    def descricao(self, rec: motor.Recorrencia) -> str:
        return f"{rec.numero} - {rec.cliente}"
