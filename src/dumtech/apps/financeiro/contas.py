"""O DumTech Financeiro publicado como destino das contas dos outros modulos.

Unica porta de entrada do Financeiro para os outros aplicativos: traduz
`AReceber` e `APagar` (que qualquer modulo entende) em `Lancamento` (que so o
Financeiro conhece), e garante que o mesmo documento nunca vire duas contas.

Dos dois lados do caixa: a venda a prazo e a ordem entregue viram dinheiro a
entrar; a nota de compra que entrou no Estoque vira dinheiro a sair.

Quem monta isso e o Hub, e so quando a licenca libera o Financeiro.
"""

from __future__ import annotations

import re
from pathlib import Path

from ...core import eventos
from ...core.contas import APagar, AReceber
from ...ui import format as fmt
from .database import open_database
from .models import DESPESA, RECEITA, RECORRENCIA, Lancamento
from .repository import FinanceiroRepository
from .repository.comum import dinheiro

#: marca a origem no proprio lancamento - e assim que a ponte se reconhece
MARCA = "Origem: "

#: de quem e o dado que muda quando alguem passa por esta porta
APP_ID = "financeiro"

#: a despesa da devolucao leva a marca da venda; e a categoria que a separa da
#: conta do fornecedor, que pode ter o mesmo numero
DEVOLUCOES = "Devoluções"


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
        criado = self.repository.criar(self._receita(conta))
        eventos.avisar(APP_ID)
        return int(criado.id)

    def lancar_parcelado(self, conta: AReceber, parcelas: int) -> int:
        """360 em 12x vira doze contas de 30, uma por mes - a mesma do "Parcelar"."""
        criados = self.repository.parcelar(self._receita(conta), parcelas)
        eventos.avisar(APP_ID)
        return len(criados)

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
        lancamento = self._achar(documento)
        if lancamento is None or lancamento.pago:
            return False
        self.repository.quitar(
            lancamento.id, conta_id=self._conta_da_baixa(lancamento), forma=forma
        )
        eventos.avisar(APP_ID)
        return True

    def cancelar(
        self, documento: str, motivo: str = "", manter_pagos: bool = False, quando: str = ""
    ) -> int:
        """Tira das contas o que nasceu deste documento. Devolve quantas sairam."""
        canceladas = 0
        for lancamento in self._do_documento(documento):
            if lancamento.cancelado or not (lancamento.e_receita
                                            or lancamento.categoria == DEVOLUCOES):
                continue
            if manter_pagos and lancamento.pago:
                continue
            if manter_pagos and lancamento.baixado > 0:
                # parcela paga em parte: o que entrou fica, o resto para de cobrar
                self.repository.abater(lancamento.id, lancamento.em_aberto,
                                       f"Cancelado: {motivo}".rstrip(": "))
            else:
                self.repository.cancelar(lancamento.id, motivo, quando)
            canceladas += 1
        if canceladas:
            eventos.avisar(APP_ID)
        return canceladas

    def devolver(
        self, documento: str, valor: float, data: str, motivo: str = "", cliente: str = ""
    ) -> bool:
        """O que nao foi recebido deixa de ser cobrado; o que entrou, sai.

        Despesa, e nao estorno, porque o dinheiro andou duas vezes: entrou no
        dia da venda e saiu no da devolucao. Estornar reescreveria o mes da venda.
        """
        receita = next((item for item in self._do_documento(documento)
                        if item.e_receita and not item.cancelado), None)
        if receita is None:
            return False

        valor = dinheiro(valor)
        abatido = min(valor, receita.em_aberto)
        saiu = min(dinheiro(valor - abatido), receita.baixado)
        if saiu > 0:
            self._devolver_dinheiro(receita, documento, saiu, data, motivo, cliente)
        if abatido > 0:
            self.repository.abater(
                receita.id, abatido,
                f"Devolução de {fmt.moeda(abatido)}: {motivo.strip()}".rstrip(": "),
            )
        eventos.avisar(APP_ID)
        return True

    def _devolver_dinheiro(
        self, receita: Lancamento, documento: str, valor: float, data: str,
        motivo: str, cliente: str,
    ) -> None:
        # a mesma marca da venda: cancelar a venda desfaz a devolucao junto
        observacoes = f"{MARCA}{documento}"
        if motivo.strip():
            observacoes += f"\nDevolução: {motivo.strip()}"
        # sai por onde entrou; baixa antiga sem conta nunca somou no saldo, e
        # por isso tambem nao pode subtrair
        origem = self.repository.baixas_de(receita.id)[0]
        self.repository.criar(Lancamento(
            tipo=DESPESA,
            descricao=f"Devolução da venda {documento}",
            categoria=DEVOLUCOES,
            cliente=cliente,
            valor=valor,
            vencimento=data,
            pago_em=data,
            forma_pagamento=origem.forma,
            observacoes=observacoes,
            conta_id=origem.conta_id,
        ))

    def _do_documento(self, documento: str) -> list[Lancamento]:
        """Todas as contas do documento, e so as dele.

        O LIKE sozinho nao serve: o numero da venda e editavel, e "VEN-1" nao
        pode levar junto o "VEN-10" nem o "VEN-1/2". Texto depois da marca
        continua valendo, porque a observacao e livre e quem anota nao pode
        perder a ligacao.
        """
        documento = (documento or "").strip()
        if not documento:
            return []
        marca = f"{MARCA}{documento}"
        exata = re.compile(re.escape(marca) + r"(?![\w-]|[./]\w)")
        linhas = self.database.query(
            "SELECT id, observacoes FROM lancamentos WHERE observacoes LIKE ? ORDER BY id",
            (f"%{marca}%",),
        )
        achados = [self.repository.obter(int(linha["id"]))
                   for linha in linhas if exata.search(linha["observacoes"])]
        return [item for item in achados if item is not None]

    def _receita(self, conta: AReceber) -> Lancamento:
        return Lancamento(
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
        )

    def _achar(self, documento: str) -> Lancamento | None:
        """A conta que vale agora; a cancelada nao segura o numero da venda."""
        return next((item for item in self._do_documento(documento) if not item.cancelado), None)

    def _conta_padrao(self) -> int | None:
        conta = self.repository.conta_padrao()
        return conta.id if conta is not None else None

    def _conta_da_baixa(self, lancamento: Lancamento) -> int:
        """A conta prevista no lancamento; se ela sumiu, a padrao (0 = nenhuma)."""
        if lancamento.conta_id and self.repository.obter_conta(lancamento.conta_id):
            return lancamento.conta_id
        return self._conta_padrao() or 0

    def close(self) -> None:
        self.database.close()


def abrir_contas(caminho: Path) -> ContasFinanceiro:
    return ContasFinanceiro.abrir(caminho)
