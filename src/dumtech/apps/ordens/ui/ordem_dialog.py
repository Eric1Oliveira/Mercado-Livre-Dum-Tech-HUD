"""A ficha da ordem de servico.

O QUE MUDOU E POR QUE

Esta ficha ja pediu dezesseis respostas de uma vez, na linguagem de uma
assistencia de celular: "equipamento", "defeito relatado", "senha para
destravar", "acessorios". Quem conserta celular preenchia tudo; o chaveiro, o
instalador de ar-condicionado, a lavanderia e a oficina mecanica preenchiam
tres campos e rolavam por treze que nunca serviram para nada.

Agora a ficha comeca pelo que TODO servico tem:

    quem pediu  ·  o que foi pedido  ·  para quando  ·  quanto

O resto continua existindo, na mesma ordem e nas mesmas colunas do banco -
so que atras de blocos que abrem quando interessam. Quem ja usa os campos de
assistencia nao perde nada: ao abrir uma ordem que os tem preenchidos, o
bloco correspondente ja vem aberto e com um ponto avisando que ha conteudo.

As palavras tambem sairam do nicho: "item ou local" no lugar de
"equipamento", "o que o cliente pediu" no lugar de "defeito relatado". A
mesma ficha serve para trocar uma tela, instalar uma cortina ou revisar um
carro.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QWidget

from ....ui import format as fmt
from ....ui.theme import Space
from ....ui.widgets import form
from ....ui.widgets.common import label, separator
from ....ui.widgets.flow_layout import FlowLayout
from ....ui.widgets.form import FormDialog
from ....ui.widgets.secao import Secao
from ..models import (
    ACESSORIOS_COMUNS,
    GARANTIA_PADRAO,
    STATUS_OPCOES,
    Ordem,
)
from ..repository import OrdensRepository
from .itens_editor import ItensEditor


class AcessoriosPicker(QWidget):
    """O que veio junto com o item.

    E um registro de entrada, nao um cadastro: marcar o que e comum e rapido,
    e o que nao esta na lista entra digitado. A lista de marcar aprende com a
    propria loja (`comuns`) e so cai no padrao de fabrica enquanto nao ha
    historico - assim ela serve para quem recebe carregador e para quem
    recebe estepe.
    """

    def __init__(self, texto: str = "", comuns=(), parent: QWidget | None = None) -> None:
        super().__init__(parent)
        marcados = {linha.strip().lower() for linha in texto.splitlines() if linha.strip()}
        lista = tuple(comuns) or ACESSORIOS_COMUNS

        raiz = FlowLayout(self, margin=0, spacing=Space.sm)
        self.caixas: list[QCheckBox] = []
        for nome in lista:
            caixa = QCheckBox(nome)
            caixa.setChecked(nome.lower() in marcados)
            self.caixas.append(caixa)
            raiz.addWidget(caixa)

        conhecidos = {nome.lower() for nome in lista}
        extras = [
            linha.strip() for linha in texto.splitlines()
            if linha.strip() and linha.strip().lower() not in conhecidos
        ]
        self.outros = form.texto(", ".join(extras), "Outros (separe por vírgula)")
        raiz.addWidget(self.outros)

    def texto(self) -> str:
        escolhidos = [caixa.text() for caixa in self.caixas if caixa.isChecked()]
        escolhidos += [
            parte.strip() for parte in self.outros.text().split(",") if parte.strip()
        ]
        return "\n".join(escolhidos)

    def tem_algo(self) -> bool:
        return bool(self.texto().strip())


class OrdemDialog(FormDialog):
    def __init__(
        self,
        repository: OrdensRepository,
        ordem: Ordem | None = None,
        clientes: list[str] | None = None,
        parent: QWidget | None = None,
        catalogo=None,
    ) -> None:
        self.repository = repository
        #: catalogo do Estoque; usado la embaixo, em `_o_servico`
        self._catalogo = catalogo
        self.ordem = ordem or Ordem(numero=repository.proximo_numero())
        self.editando = ordem is not None
        super().__init__(
            f"Ordem {self.ordem.numero}" if self.editando else "Nova ordem de serviço",
            "O básico para abrir. O resto só se o seu serviço precisar.",
            parent,
            largura=760,
            rolagem=True,
        )

        self._o_pedido(clientes or [])
        self._o_servico()
        self._blocos_de_detalhe()
        if self.editando:
            self._historico()
        self.cliente.setFocus()

    # ------------------------------------------------------------- o pedido
    def _o_pedido(self, clientes: list[str]) -> None:
        """Os quatro campos que existem em qualquer servico, de qualquer ramo."""
        self.cliente = form.sugestao(self.ordem.cliente, "Nome do cliente", clientes)
        self.telefone = form.texto(self.ordem.telefone, "WhatsApp ou telefone")
        self.add_row("Cliente", form.linha(self.cliente, "Telefone", self.telefone))

        self.defeito = form.area(
            self.ordem.defeito,
            "Ex.: trocar a tela / instalar o ar na sala / revisar os freios",
            60,
        )
        self.add_row("O que foi pedido", self.defeito)

        self.equipamento = form.sugestao(
            self.ordem.equipamento,
            "Opcional - ex.: Notebook Dell G15, Gol 2015, Sala 2",
            self.repository.equipamentos(),
        )
        self.add_row("Item ou local", self.equipamento)

        self.prazo = form.data(self.ordem.prazo or self.ordem.aberta_em)
        self.valor = form.dinheiro(self.ordem.valor)
        self.add_row("Entrega prevista", form.linha(self.prazo, "Valor", self.valor))

    # -------------------------------------------------------------- o servico
    def _o_servico(self) -> None:
        self.form.addRow(separator())
        self.form.addRow(label("Peças e serviços", "section"))

        self.itens = ItensEditor(catalogo=self._catalogo)
        self.itens.set_items(self.ordem.itens)
        self.itens.changed.connect(self._atualizar_total)
        self.form.addRow(self.itens)

        self.desconto = form.dinheiro(self.ordem.desconto)
        self.desconto.valueChanged.connect(self._atualizar_total)
        self.add_row("Desconto", self.desconto)

        self.add_note("")
        self._nota = self.extras.itemAt(self.extras.count() - 1).widget()
        self._atualizar_total()

    # ------------------------------------------------------- o que e opcional
    def _blocos_de_detalhe(self) -> None:
        """Tres blocos fechados: recebimento, execucao e controle.

        Cada um abre sozinho quando ja tem conteudo - abrir uma ordem antiga
        nao pode esconder o que alguem escreveu nela.
        """
        o = self.ordem

        # --- como o item chegou (a parte de quem recebe aparelho na bancada)
        self.acessorios = AcessoriosPicker(o.acessorios,
                                           self.repository.acessorios_usados())
        self.condicao = form.texto(o.condicao, "Ex.: risco na tampa, tecla solta")
        self.senha = form.texto(o.senha, "Senha ou desenho, se precisar")
        tem_entrada = bool(o.acessorios.strip() or o.condicao.strip() or o.senha.strip())
        self.bloco_entrada = Secao(
            "Como o item chegou", "o que veio junto, estado, senha", aberta=tem_entrada
        )
        self.bloco_entrada.add_row("O que veio junto", self.acessorios)
        self.bloco_entrada.add_row("Estado na chegada", self.condicao)
        self.bloco_entrada.add_row("Senha de acesso", self.senha)
        self.bloco_entrada.marcar_preenchida(tem_entrada)
        self.extras.addWidget(self.bloco_entrada)

        # --- execucao
        self.tecnico = form.sugestao(o.tecnico, "Quem vai fazer",
                                     self.repository.tecnicos())
        self.diagnostico = form.area(o.diagnostico, "O que foi encontrado e feito", 60)
        self.garantia = form.inteiro(
            o.garantia_dias or GARANTIA_PADRAO, minimo=0, maximo=3650
        )
        self.status = form.escolha(STATUS_OPCOES, o.status)
        # etapa so se escolhe ao abrir: depois quem manda e a esteira da bancada
        self.status.setEnabled(not self.editando)
        tem_execucao = bool(o.tecnico.strip() or o.diagnostico.strip())
        self.bloco_execucao = Secao(
            "Execução", "responsável, garantia, o que foi feito", aberta=tem_execucao
        )
        self.bloco_execucao.add_row("Responsável", self.tecnico)
        self.bloco_execucao.add_row("O que foi feito", self.diagnostico)
        self.bloco_execucao.add_row(
            "Garantia (dias)", form.linha(self.garantia, "Etapa", self.status)
        )
        self.bloco_execucao.marcar_preenchida(tem_execucao)
        self.extras.addWidget(self.bloco_execucao)

        # --- controle interno
        self.numero = form.texto(o.numero, "Ex.: OS-2026-0001")
        self.aberta_em = form.data(o.aberta_em)
        self.observacoes = form.area(o.observacoes, "Só você vê isto", 60)
        tem_controle = bool(o.observacoes.strip())
        self.bloco_controle = Secao(
            "Número e anotações internas", "número, data de entrada, anotações",
            aberta=tem_controle,
        )
        self.bloco_controle.add_row("Número", form.linha(self.numero, "Entrada",
                                                         self.aberta_em))
        self.bloco_controle.add_row("Anotações internas", self.observacoes)
        self.bloco_controle.marcar_preenchida(tem_controle)
        self.extras.addWidget(self.bloco_controle)

    def _historico(self) -> None:
        self.extras.addWidget(separator())
        self.extras.addWidget(label("Por onde esta ordem passou", "section"))
        for evento in self.repository.historico_de(self.ordem.id):
            texto = f"{fmt.data_hora(evento.criado_em)}   {evento.status_label}"
            if evento.observacao:
                texto += f"   -   {evento.observacao}"
            linha = label(texto, "caption")
            linha.setWordWrap(True)
            self.extras.addWidget(linha)

    # -------------------------------------------------------------------- tela
    def _atualizar_total(self) -> None:
        itens = self.itens.items()
        # com itens o valor vem deles; sem itens vale o campo Valor
        self.valor.setEnabled(not itens)
        subtotal = self.itens.total if itens else self.valor.value()
        total = max(subtotal - self.desconto.value(), 0)
        if itens:
            self.valor.setValue(total)
            self._nota.setText(
                f"Subtotal dos itens: {fmt.moeda(subtotal)}      "
                f"Desconto: {fmt.moeda(self.desconto.value())}      "
                f"TOTAL: {fmt.moeda(total)}"
            )
        else:
            self._nota.setText(
                "Sem itens lançados: o total da ordem é o valor digitado acima."
            )

    # ------------------------------------------------------------------ gravar
    def salvar(self) -> None:
        self.ordem.numero = self.numero.text()
        self.ordem.aberta_em = form.iso_da_data(self.aberta_em)
        self.ordem.prazo = form.iso_da_data(self.prazo)
        self.ordem.cliente = self.cliente.text()
        self.ordem.telefone = self.telefone.text()
        self.ordem.equipamento = self.equipamento.text()
        self.ordem.defeito = self.defeito.toPlainText()
        self.ordem.acessorios = self.acessorios.texto()
        self.ordem.condicao = self.condicao.text()
        self.ordem.senha = self.senha.text()
        self.ordem.tecnico = self.tecnico.text()
        self.ordem.diagnostico = self.diagnostico.toPlainText()
        self.ordem.itens = self.itens.items()
        self.ordem.desconto = self.desconto.value()
        self.ordem.garantia_dias = self.garantia.value()
        self.ordem.observacoes = self.observacoes.toPlainText()
        if not self.editando:
            self.ordem.status = self.status.currentData()
        if not self.ordem.itens:
            self.ordem.valor = self.valor.value()
        self.repository.salvar(self.ordem)
