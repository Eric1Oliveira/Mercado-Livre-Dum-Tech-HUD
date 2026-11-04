"""Parceiros: quem indica clientes para a loja, e quanto cada um ja indicou.

O parceiro e cadastrado aqui; a indicacao nasce no cadastro do cliente
("Indicado por"). O desenho no alto responde "quem mais me manda cliente"
antes de qualquer leitura - a tabela embaixo tem os numeros de cada um.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QWidget

from ....core.contacts import ContactsStore, Indicacoes
from ....core.contas import APagar, vencimento_padrao
from ....ui import format as fmt
from ....ui.graficos import GraficoBarras, fatias_de, maiores
from ....ui.widgets.buttons import Button
from ....ui.widgets.crud_view import CrudView
from ....ui.widgets.panels import ChartPanel
from ....ui.widgets.table import DIREITA
from .parceiro_dialog import ParceiroDialog

#: parceiros com barra propria no desenho; o resto soma em "Outros"
NO_GRAFICO = 6


class ParceirosView(CrudView):
    titulo = "Parceiros"
    nome_registro = "parceiro"
    nome_plural = "parceiros"
    rotulo_novo = "Novo parceiro"
    dica_pesquisa = "Pesquisar parceiro por nome, telefone ou e-mail..."
    colunas = ["Parceiro", "Telefone", "Clientes indicados", "Ainda ativos",
               "Neste mês", "Última indicação", "Vendido no mês", "Comissão", "Situação"]
    larguras = {1: 145, 2: 140, 3: 110, 4: 100, 5: 130, 6: 125, 7: 110, 8: 100}

    def __init__(self, store: ContactsStore, parent: QWidget | None = None,
                 consultas=None, contas=None) -> None:
        self.store = store
        #: o Vendas, para somar o que os clientes indicados compraram
        self.vendas = next((c for c in consultas or [] if c.app_id == "vendas"), None)
        #: o Financeiro, para a comissao virar conta a pagar
        self.contas = contas
        super().__init__(parent)

        self.grafico = GraficoBarras(largura_rotulo=170)
        self.grafico.vazio = ("Nenhuma indicação ainda. No cadastro do cliente, "
                              "escolha quem indicou em \"Indicado por\".")
        self.painel_indicacoes = ChartPanel("Indicações por parceiro", self.grafico)
        # o desenho entra entre o cabecalho e a pesquisa
        self.layout().insertWidget(1, self.painel_indicacoes)

    # ------------------------------------------------------------------ filtros
    def build_filters(self, layout: QHBoxLayout) -> None:
        self.mostrar_inativos = QCheckBox("Mostrar inativos")
        self.mostrar_inativos.stateChanged.connect(self.refresh)
        layout.addWidget(self.mostrar_inativos)

    def build_actions(self, layout: QHBoxLayout) -> None:
        self.botao_ativar = Button("Inativar", "close")
        self.botao_ativar.setToolTip("Tira o parceiro da lista do cadastro de clientes")
        self.botao_ativar.clicked.connect(self._alternar_ativo)
        layout.addWidget(self.botao_ativar)

        self.botao_comissao = Button("Lançar comissão", "money")
        self.botao_comissao.setToolTip("Vira conta a pagar no Financeiro, uma vez por mês")
        self.botao_comissao.clicked.connect(self._lancar_comissao)
        layout.addWidget(self.botao_comissao)
        self.botao_comissao.setVisible(self.contas is not None and self.vendas is not None)

    # ------------------------------------------------------------------- dados
    def vendido_no_mes(self, parceiro) -> float:
        if self.vendas is None:
            return 0.0
        nomes = self.store.clientes_do_parceiro(parceiro.id)
        inicio = date.today().replace(day=1).isoformat()
        return round(sum(self.vendas.vendido_por_cliente(nomes, inicio).values()), 2)

    def comissao_do_mes(self, parceiro) -> float:
        return round(self.vendido_no_mes(parceiro) * parceiro.comissao / 100, 2)

    def refresh(self) -> None:
        self._desenhar()
        super().refresh()

    def carregar(self) -> list[Indicacoes]:
        busca = self.busca.text().strip().lower()
        digitos = "".join(c for c in busca if c.isdigit())
        todos = self.store.indicacoes(incluir_inativos=self.mostrar_inativos.isChecked())
        if not busca:
            return todos
        return [
            i for i in todos
            if busca in i.parceiro.nome.lower() or busca in i.parceiro.email.lower()
            or (digitos and digitos in i.parceiro.telefone)
        ]

    def montar_linha(self, item: Indicacoes) -> list:
        parceiro = item.parceiro
        return [
            self.tabela.cell(parceiro.nome, bold=True, data=parceiro.id),
            self.tabela.cell(parceiro.telefone_formatado or "-"),
            self.tabela.cell(fmt.numero(item.clientes), DIREITA, bold=bool(item.clientes)),
            self.tabela.cell(fmt.numero(item.ativos), DIREITA),
            self.tabela.cell(fmt.numero(item.no_mes), DIREITA),
            self.tabela.cell(fmt.data(item.ultimo) if item.ultimo else "-"),
            self.tabela.cell(fmt.moeda(self.vendido_no_mes(parceiro)) if self.vendas else "-",
                             DIREITA),
            self.tabela.cell(fmt.moeda(self.comissao_do_mes(parceiro)) if self.vendas else "-",
                             DIREITA, "accent", bold=True),
            self.tabela.cell("Ativo" if parceiro.ativo else "Inativo",
                             tone="success" if parceiro.ativo else "muted"),
        ]

    def _desenhar(self) -> None:
        """Quem mais indicou, com a parte de cada um no total."""
        indicacoes = [i for i in self.store.indicacoes(incluir_inativos=True) if i.clientes]
        total = sum(i.clientes for i in indicacoes)
        pares = maiores([(i.parceiro.nome, i.clientes) for i in indicacoes], NO_GRAFICO)
        self.grafico.set_fatias(fatias_de(
            [(nome, quantidade,
              f"{fmt.contagem(int(quantidade), 'cliente')}  ·  {quantidade / total:.0%}")
             for nome, quantidade in pares],
            tons=["accent"] * len(pares),
        ))
        self.grafico.setMinimumHeight(max(120, self.grafico.altura_ideal()))
        self.painel_indicacoes.set_nota(
            f"{fmt.contagem(total, 'cliente indicado', 'clientes indicados')}" if total else ""
        )

    def _atualizar_acoes(self) -> None:
        super()._atualizar_acoes()
        item = self.registro_selecionado()
        self.botao_ativar.setEnabled(item is not None)
        if item is not None:
            ativo = item.parceiro.ativo
            self.botao_ativar.setText("  Inativar" if ativo else "  Reativar")
            self.botao_ativar.set_icon_name("close" if ativo else "check")
        self.botao_comissao.setEnabled(item is not None and item.parceiro.comissao > 0)

    # ------------------------------------------------------------------- acoes
    def _lancar_comissao(self) -> None:
        """O numero do parceiro e do mes e a chave: nao paga duas vezes o mesmo mes."""
        item = self.registro_selecionado()
        if item is None or self.contas is None:
            return
        parceiro = item.parceiro
        valor = self.comissao_do_mes(parceiro)
        mes = date.today().strftime("%m/%Y")
        documento = f"COM-{parceiro.id}-{date.today():%Y%m}"
        if valor <= 0:
            self.mostrar_aviso(f"{parceiro.nome} não tem comissão neste mês.")
            return
        if self.contas.ja_lancado(documento):
            self.mostrar_aviso(f"A comissão de {mes} já foi lançada no Financeiro.", "warning")
            return
        self.contas.lancar_pagamento(APagar(
            descricao=f"Comissão {parceiro.nome} {mes}", valor=valor,
            vencimento=vencimento_padrao(), fornecedor=parceiro.nome,
            categoria="Comissões", documento=documento,
        ))
        self.mostrar_aviso(f"Comissão de {fmt.moeda(valor)} lançada no Financeiro.", "success")
        self.data_changed.emit()

    def _alternar_ativo(self) -> None:
        item = self.registro_selecionado()
        if item is None:
            return
        parceiro = item.parceiro
        parceiro.ativo = not parceiro.ativo
        self.store.atualizar_parceiro(parceiro)
        self.refresh()
        self.mostrar_aviso(
            f"'{parceiro.nome}' voltou para a lista do cadastro." if parceiro.ativo
            else f"'{parceiro.nome}' saiu da lista do cadastro. As indicações continuam contadas."
        )
        self.data_changed.emit()

    # ------------------------------------------------------------------ ganchos
    def abrir_dialogo(self, item: Indicacoes | None):
        return ParceiroDialog(self.store, item.parceiro if item else None, self)

    def excluir(self, item: Indicacoes) -> None:
        self.store.excluir_parceiro(item.parceiro.id)

    def descricao(self, item: Indicacoes) -> str:
        return item.parceiro.nome
