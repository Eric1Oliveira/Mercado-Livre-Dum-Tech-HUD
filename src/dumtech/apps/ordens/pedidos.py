"""O DumTech Ordem de Servico publicado como destino de proposta aprovada.

A ordem nasce **em execucao e ja aprovada**: o cliente aceitou o orcamento por
escrito, entao ela nao volta para a fila de aprovacao. O que ela ainda nao tem
e o registro do que foi feito - isso quem escreve e o responsavel.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ...core import eventos
from ...core.pedidos import Pedido
from .database import open_database
from .models import ANDAMENTO, PECA, SERVICO, ItemOS, Ordem
from .repository import OrdensRepository

# O item e opcional, entao a proposta sem itens nao inventa um: "A definir na
# entrada" era linguagem de balcao de assistencia e ia parar no cartao do
# quadro e no comprovante. Quem identifica a ordem e o que foi pedido, que a
# proposta sempre preenche (`Ordem.assunto` cuida disso).


class DestinoOrdens:
    """Implementacao de `core.pedidos.Destino` em cima do banco das Ordens."""

    titulo = "Ordem de Serviço"
    app_id = "ordens"

    def __init__(self, database) -> None:
        self.database = database
        self.repository = OrdensRepository(database)

    @classmethod
    def abrir_banco(cls, caminho: Path) -> "DestinoOrdens":
        return cls(open_database(caminho))

    def abrir(self, pedido: Pedido) -> str:
        primeiro = pedido.itens[0].descricao if pedido.itens else ""
        ordem = self.repository.salvar(Ordem(
            numero=self.repository.proximo_numero(),
            cliente=pedido.cliente,
            equipamento=primeiro,
            defeito=pedido.observacoes or f"Serviço contratado na proposta "
                                          f"{pedido.origem}".strip(),
            # ja em servico: aprovacao existe (aprovado_em), a fila nao
            status=ANDAMENTO,
            aprovado_em=date.today().isoformat(),
            aprovado_por=pedido.cliente,
            desconto=float(pedido.desconto or 0),
            observacoes=f"Gerada da proposta {pedido.origem}"
                        if pedido.origem else "",
            itens=[
                ItemOS(
                    # produto do Estoque e peca (sai do saldo na entrega);
                    # o que foi digitado a mao continua sendo servico
                    tipo=PECA if getattr(item, "produto_id", 0) else SERVICO,
                    descricao=item.descricao,
                    quantidade=float(item.quantidade or 1),
                    valor_unitario=_unitario(item),
                    produto_id=int(getattr(item, "produto_id", 0) or 0),
                    codigo=getattr(item, "codigo", "") or "",
                )
                for item in pedido.itens
            ],
        ))
        eventos.avisar(self.app_id)
        return ordem.numero

    def close(self) -> None:
        self.database.close()


def _unitario(item) -> float:
    """O desconto por linha da proposta entra no preco: o total tem que bater."""
    quantidade = float(item.quantidade or 1) or 1.0
    bruto = float(item.valor_unitario or 0) * quantidade
    return round(max(bruto - float(item.desconto or 0), 0.0) / quantidade, 2)


def abrir_destino(caminho: Path) -> DestinoOrdens:
    return DestinoOrdens.abrir_banco(caminho)
