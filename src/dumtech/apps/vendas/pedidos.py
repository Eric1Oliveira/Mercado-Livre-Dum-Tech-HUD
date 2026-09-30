"""O DumTech Vendas publicado como destino de proposta aprovada.

A venda nasce **pendente**, e nao concluida: o cliente aprovou a proposta, mas
ainda nao pagou. Quem fecha o pagamento e o balcao, com o caixa aberto e a
forma escolhida - a ponte nao inventa dinheiro que ninguem recebeu.
"""

from __future__ import annotations

from pathlib import Path

from ...core import eventos
from ...core.pedidos import Pedido
from .database import open_database
from .models import PENDENTE, ItemVenda, Venda
from .repository import VendasRepository


class DestinoVendas:
    """Implementacao de `core.pedidos.Destino` em cima do banco do Vendas."""

    titulo = "Venda"
    app_id = "vendas"

    def __init__(self, database) -> None:
        self.database = database
        self.repository = VendasRepository(database)

    @classmethod
    def abrir_banco(cls, caminho: Path) -> "DestinoVendas":
        return cls(open_database(caminho))

    def abrir(self, pedido: Pedido) -> str:
        venda = self.repository.salvar(Venda(
            numero=self.repository.proximo_numero(),
            cliente=pedido.cliente,
            status=PENDENTE,
            desconto=float(pedido.desconto or 0),
            observacoes=_observacao(pedido),
            itens=[
                ItemVenda(
                    descricao=item.descricao,
                    quantidade=float(item.quantidade or 1),
                    # o desconto por linha da proposta entra no preco: a venda
                    # nao tem desconto por item, e o total tem que bater
                    valor_unitario=_unitario(item),
                    unidade=item.unidade or "UN",
                    produto_id=int(getattr(item, "produto_id", 0) or 0),
                    codigo=getattr(item, "codigo", "") or "",
                )
                for item in pedido.itens
            ],
        ))
        eventos.avisar(self.app_id)
        return venda.numero

    def close(self) -> None:
        self.database.close()


def _unitario(item) -> float:
    quantidade = float(item.quantidade or 1) or 1.0
    bruto = float(item.valor_unitario or 0) * quantidade
    return round(max(bruto - float(item.desconto or 0), 0.0) / quantidade, 2)


def _observacao(pedido: Pedido) -> str:
    partes = [f"Gerada da proposta {pedido.origem}" if pedido.origem else ""]
    if pedido.observacoes:
        partes.append(pedido.observacoes)
    return "\n".join(parte for parte in partes if parte)


def abrir_destino(caminho: Path) -> DestinoVendas:
    return DestinoVendas.abrir_banco(caminho)
