"""O DumTech Financeiro publicado como destino das contas dos outros modulos.

Unica porta de entrada do Financeiro para os outros aplicativos: traduz
`AReceber` e `APagar` (que qualquer modulo entende) em `Lancamento` (que so o
Financeiro conhece), e garante que o mesmo documento nunca vire duas contas.

Dos dois lados do caixa: a venda a prazo e a ordem entregue viram dinheiro a
entrar; a nota de compra que entrou no Estoque vira dinheiro a sair.

Quem monta isso e o Hub, e so quando a licenca libera o Financeiro.
"""

from __future__ import annotations

from pathlib import Path

from ...core import eventos
from ...core.contas import APagar, AReceber
from .database import open_database
from .models import DESPESA, RECEITA, RECORRENCIA, Lancamento
from .repository import FinanceiroRepository

#: marca a origem no proprio lancamento - e assim que a ponte se reconhece
MARCA = "Origem: "

#: de quem e o dado que muda quando alguem passa por esta porta
APP_ID = "financeiro"


class ContasFinanceiro:
    """Implementacao de `core.contas.Contas` em cima do banco do Financeiro."""

    def __init__(self, database) -> None:
        self.database = database
        self.repository = FinanceiroRepository(database)

    @classmethod
    def abrir(cls, caminho: Path) -> "ContasFinanceiro":
        return cls(open_database(caminho))

    def ja_lancado(self, documento: str) -> bool:
        """Ja existe conta vinda deste documento?

        A marca fica na observacao do proprio lancamento, e a consulta e feita
        aqui em SQL: a ponte nao pode obrigar o Financeiro a ganhar uma coluna
        so para ela - o modulo tem que continuar funcionando sozinho,
        exatamente como funcionava antes de existir ponte nenhuma.
        """
        return self._achar(documento) is not None

    def lancar(self, conta: AReceber) -> int:
        criado = self.repository.criar(Lancamento(
            tipo=RECEITA,
            descricao=conta.descricao,
            categoria=conta.categoria or "Vendas",
            cliente=conta.cliente,
            valor=float(conta.valor or 0),
            vencimento=conta.vencimento,
            observacoes=f"{MARCA}{conta.documento}" if conta.documento else "",
            conta_id=self._conta_padrao(),
            # as contas do mesmo contrato formam uma serie de recorrencia, como
            # a que o proprio Financeiro cria: filtro e Painel enxergam igual
            grupo=f"rec:{conta.recorrencia}" if conta.recorrencia else "",
            serie=RECORRENCIA if conta.recorrencia else "",
        ))
        eventos.avisar(APP_ID)
        return int(criado.id)

    def lancar_pagamento(self, conta: APagar) -> int:
        """A compra vira conta a pagar: mesma porta, outro sentido."""
        criado = self.repository.criar(Lancamento(
            tipo=DESPESA,
            descricao=conta.descricao,
            categoria=conta.categoria or "Fornecedores",
            # o campo e o mesmo que guarda o cliente: no Financeiro esta linha
            # e "com quem foi o negocio", e numa compra isso e o fornecedor
            cliente=conta.fornecedor,
            valor=float(conta.valor or 0),
            vencimento=conta.vencimento,
            observacoes=f"{MARCA}{conta.documento}" if conta.documento else "",
            conta_id=self._conta_padrao(),
        ))
        eventos.avisar(APP_ID)
        return int(criado.id)

    def quitar(self, documento: str, forma: str = "") -> bool:
        """Fecha a conta que nasceu deste documento - o cliente pagou."""
        achado = self._achar(documento)
        if achado is None:
            return False
        lancamento = self.repository.obter(int(achado["id"]))
        if lancamento is None or lancamento.pago:
            return False
        self.repository.quitar(lancamento.id, forma=forma)
        eventos.avisar(APP_ID)
        return True

    def _achar(self, documento: str):
        documento = (documento or "").strip()
        if not documento:
            return None
        return self.database.query_one(
            "SELECT id FROM lancamentos WHERE observacoes LIKE ?",
            (f"%{MARCA}{documento}%",),
        )

    def _conta_padrao(self) -> int | None:
        conta = self.repository.conta_padrao()
        return conta.id if conta is not None else None

    def close(self) -> None:
        self.database.close()


def abrir_contas(caminho: Path) -> ContasFinanceiro:
    return ContasFinanceiro.abrir(caminho)
