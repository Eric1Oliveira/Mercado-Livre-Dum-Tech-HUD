"""O DumTech Vendas respondendo a busca geral e a ficha do cliente."""

from __future__ import annotations

from pathlib import Path

from ...core.consulta import Achado
from .database import open_database
from .repository import VendasRepository


class ConsultaVendas:
    """Implementacao de `core.consulta.Consulta` em cima do banco do Vendas."""

    app_id = "vendas"

    def __init__(self, database) -> None:
        self.database = database
        self.repository = VendasRepository(database)

    def _achado(self, venda) -> Achado:
        return Achado(
            app_id=self.app_id, tipo="Venda", titulo=venda.numero,
            detalhe=venda.cliente or "Consumidor", data=venda.data,
            valor=venda.total_liquido, situacao=venda.status_label, tom=venda.status_tom,
        )

    def buscar(self, termo: str, limite: int = 5) -> list[Achado]:
        return [self._achado(v) for v in self.repository.listar(busca=termo, limite=limite)]

    def do_cliente(self, nome: str, limite: int = 30) -> list[Achado]:
        return [self._achado(v) for v in self.repository.listar(cliente=nome, limite=limite)]

    def renomear_cliente(self, antigo: str, novo: str) -> int:
        with self.database.transaction() as conn:
            mudou = conn.execute("UPDATE vendas SET cliente = ? WHERE cliente = ? COLLATE NOCASE",
                                 (novo, antigo)).rowcount
            conn.execute("UPDATE recorrencias SET cliente = ? WHERE cliente = ? COLLATE NOCASE",
                         (novo, antigo))
        return mudou

    def vendido_por_cliente(self, nomes: list[str], inicio: str, fim: str = "") -> dict[str, float]:
        """Quanto cada cliente comprou no periodo: e a base da comissao do parceiro."""
        total: dict[str, float] = {}
        for nome in nomes:
            vendas = self.repository.listar(cliente=nome, inicio=inicio, fim=fim, limite=-1)
            total[nome] = round(sum(v.total_liquido for v in vendas if v.conta), 2)
        return total

    def close(self) -> None:
        self.database.close()


def abrir_consulta(caminho: Path) -> ConsultaVendas:
    return ConsultaVendas(open_database(caminho))
