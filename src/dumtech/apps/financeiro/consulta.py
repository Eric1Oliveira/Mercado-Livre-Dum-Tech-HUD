"""O DumTech Financeiro respondendo a busca geral e a ficha do cliente."""

from __future__ import annotations

from pathlib import Path

from ...core.consulta import Achado
from .database import open_database
from .repository import FinanceiroRepository
from .repository.comum import SITUACAO_ABERTO


class ConsultaFinanceiro:
    """Implementacao de `core.consulta.Consulta` em cima do banco do Financeiro."""

    app_id = "financeiro"

    def __init__(self, database) -> None:
        self.database = database
        self.repository = FinanceiroRepository(database)

    def _achado(self, conta) -> Achado:
        return Achado(
            app_id=self.app_id, tipo="Conta", titulo=conta.descricao,
            detalhe=conta.cliente, data=conta.vencimento, valor=conta.em_aberto or conta.valor,
            situacao="Paga" if conta.pago else "Em aberto",
            tom="success" if conta.pago else "warning",
        )

    def buscar(self, termo: str, limite: int = 5) -> list[Achado]:
        return [self._achado(c) for c in self.repository.listar(busca=termo, limite=limite)]

    def do_cliente(self, nome: str, limite: int = 30) -> list[Achado]:
        """So o que ele deve: o que ja foi pago esta na venda ou na ordem."""
        contas = self.repository.listar(situacao=SITUACAO_ABERTO, cliente=nome, limite=limite)
        return [self._achado(c) for c in reversed(contas)]

    def renomear_cliente(self, antigo: str, novo: str) -> int:
        return self.database.execute(
            "UPDATE lancamentos SET cliente = ? WHERE cliente = ? COLLATE NOCASE", (novo, antigo)
        ).rowcount

    def close(self) -> None:
        self.database.close()


def abrir_consulta(caminho: Path) -> ConsultaFinanceiro:
    return ConsultaFinanceiro(open_database(caminho))
