"""O DumTech Ordem de Servico publicado como destino de proposta aprovada.

A ordem nasce **em execucao e ja aprovada**: o cliente aceitou o orcamento por
escrito, entao ela nao volta para a fila de aprovacao. O que ela ainda nao tem
e o registro do que foi feito - isso quem escreve e o responsavel.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ...core import eventos
from ...core.pedidos import Pedido, precos_fechados
from . import financeiro
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
        #: o Financeiro, para a ordem da proposta ja nascer como conta a receber
        self.contas = None

    @classmethod
    def abrir_banco(cls, caminho: Path) -> "DestinoOrdens":
        return cls(open_database(caminho))

    def abrir(self, pedido: Pedido) -> str:
        primeiro = pedido.itens[0].descricao if pedido.itens else ""
        unitarios, desconto = precos_fechados(pedido)
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
            desconto=desconto,
            observacoes=f"Gerada da proposta {pedido.origem}"
                        if pedido.origem else "",
            itens=[
                ItemOS(
                    # produto do Estoque e peca (sai do saldo na entrega);
                    # o que foi digitado a mao continua sendo servico
                    tipo=PECA if getattr(item, "produto_id", 0) else SERVICO,
                    descricao=item.descricao,
                    quantidade=float(item.quantidade or 1),
                    valor_unitario=unitario,
                    produto_id=int(getattr(item, "produto_id", 0) or 0),
                    codigo=getattr(item, "codigo", "") or "",
                )
                for item, unitario in zip(pedido.itens, unitarios)
            ],
        ))
        financeiro.da_proposta(self.contas, ordem)
        eventos.avisar(self.app_id)
        return ordem.numero

    def close(self) -> None:
        self.database.close()


def abrir_destino(caminho: Path) -> DestinoOrdens:
    return DestinoOrdens.abrir_banco(caminho)
