"""Contas a receber que nascem em outro aplicativo.

Uma venda a prazo e uma ordem de servico entregue sao a mesma coisa vista de
onde o dono da loja senta: dinheiro que ele ainda vai receber. Sem ponte, ele
digita duas vezes - e e sempre a segunda que ele esquece.

Aqui mora **so o contrato**, como em `core/catalog.py`. Quem sabe lancar de
verdade e o DumTech Financeiro, em `apps/financeiro/contas.py`. Quem publica
(Vendas e Ordens) enxerga apenas `AReceber` e os dois metodos abaixo, nao
importa nada do Financeiro, e continua funcionando quando o cliente nao comprou
o Financeiro: o Hub entrega `None` e a ponte simplesmente nao existe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

#: teto de seguranca: ninguem parcela em 500x sem querer
MAXIMO_PARCELAS = 120


@dataclass(frozen=True)
class AReceber:
    """O que precisa ser dito para nascer uma conta a receber."""

    descricao: str
    valor: float
    vencimento: str
    cliente: str = ""
    categoria: str = ""
    #: numero do documento de origem (VEN-2026-0001, OS-2026-0117). E por ele
    #: que a ponte sabe que ja lancou e nao duplica.
    documento: str = ""
    #: contrato recorrente que gerou a conta (VREC-2026-0001). No Financeiro
    #: as contas do mesmo contrato viram uma serie de recorrencia - aparecem
    #: marcadas como recorrentes e somam no "recorrente" do Painel.
    recorrencia: str = ""


@dataclass(frozen=True)
class APagar:
    """O que precisa ser dito para nascer uma conta a pagar.

    Nasce da compra: a nota que entrou no Estoque e dinheiro que vai sair. Sem
    esta ponte o dono digitava a mesma nota duas vezes - e a segunda, como
    sempre, era a esquecida.
    """

    descricao: str
    valor: float
    vencimento: str
    fornecedor: str = ""
    categoria: str = ""
    #: numero da nota (NF 1234). E por ele que a ponte sabe que ja lancou.
    documento: str = ""


@runtime_checkable
class Contas(Protocol):
    """O que um aplicativo pode pedir ao Financeiro da plataforma."""

    def ja_lancado(self, documento: str) -> bool:
        """Se este documento ja virou conta - a ponte nunca lanca duas vezes."""

    def lancar(self, conta: AReceber) -> int:
        """Cria a conta a receber e devolve o id. Levanta RegraError se nao der."""

    def lancar_pagamento(self, conta: APagar) -> int:
        """Cria a conta a PAGAR (a compra) e devolve o id.

        Mesma regra do `lancar`: o documento e a chave, e lancar duas vezes o
        mesmo documento nao pode dobrar a divida.
        """

    def lancar_parcelado(self, conta: AReceber, parcelas: int) -> int:
        """Cria uma conta a receber por mes e devolve quantas nasceram.

        `conta.valor` e o TOTAL e `conta.vencimento` e o da primeira parcela.
        """

    def quitar(self, documento: str, forma: str = "") -> bool:
        """Da baixa na conta criada por este documento.

        Sem isto a ponte criaria uma divida que ninguem fecha: o cliente volta,
        paga no balcao, e o Financeiro continuaria cobrando. `False` quando nao
        existe conta daquele documento - situacao normal, nao erro.
        """

    def cancelar(
        self, documento: str, motivo: str = "", manter_pagos: bool = False, quando: str = ""
    ) -> int:
        """Tira das contas o que nasceu deste documento e devolve quantas sairam.

        A venda cancelada nao deixa dinheiro: a baixa e desfeita e a linha fica
        marcada como cancelada. Com `manter_pagos`, o que ja foi recebido fica
        (parcela paga e dinheiro que entrou mesmo). `quando` e a data do
        cancelamento, se ele nao foi agora. Sem conta daquele documento devolve
        0 - situacao normal, nao erro.
        """

    def devolver(
        self, documento: str, valor: float, data: str, motivo: str = "", cliente: str = ""
    ) -> bool:
        """Tira do Financeiro o que o cliente devolveu.

        O que ainda estava em aberto deixa de ser cobrado; o que ja tinha
        entrado sai como despesa no dia da devolucao, pela conta por onde
        entrou. `False` quando o documento nunca virou conta: nao ha o que
        desfazer.
        """
