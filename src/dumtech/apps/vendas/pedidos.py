"""O DumTech Vendas publicado para os outros modulos.

Destino de proposta aprovada: a venda nasce **pendente**, e nao concluida. O
cliente aprovou a proposta, mas ainda nao pagou. Quem fecha o pagamento e o
balcao, com o caixa aberto e a forma escolhida - a ponte nao inventa dinheiro
que ninguem recebeu.

Origem das contas de venda: quando o dono da baixa na tela de contas, e por
aqui que a venda fica sabendo. E gaveta: o caixa do dia mora neste banco, e
quem recebe em especie em outro modulo conta para ele.
"""

from __future__ import annotations

from pathlib import Path

from ...core import eventos
from ...core.pedidos import Pedido, precos_fechados
from . import financeiro
from .database import open_database
from .models import (
    PENDENTE,
    QUITADA_NO_FINANCEIRO,
    RECEBIDO_NO_FINANCEIRO,
    ItemVenda,
    Venda,
)
from .repository import VendasRepository, pagamento_unico


class DestinoVendas:
    """Implementa `core.pedidos.Destino`, `core.contas.Origem` e `core.caixa.Gaveta`."""

    titulo = "Venda"
    app_id = "vendas"

    def __init__(self, database) -> None:
        self.database = database
        self.repository = VendasRepository(database)
        #: o Financeiro, para a venda da proposta ja nascer como conta a receber
        self.contas = None

    @classmethod
    def abrir_banco(cls, caminho: Path) -> "DestinoVendas":
        return cls(open_database(caminho))

    def abrir(self, pedido: Pedido) -> str:
        unitarios, desconto = precos_fechados(pedido)
        venda = self.repository.lancar(Venda(
            numero=self.repository.proximo_numero(),
            cliente=pedido.cliente,
            status=PENDENTE,
            desconto=desconto,
            observacoes=_observacao(pedido),
            itens=[
                ItemVenda(
                    descricao=item.descricao,
                    quantidade=float(item.quantidade or 1),
                    # o desconto por linha da proposta entra no preco: a venda
                    # nao tem desconto por item, e o total tem que bater
                    valor_unitario=unitario,
                    unidade=item.unidade or "UN",
                    produto_id=int(getattr(item, "produto_id", 0) or 0),
                    codigo=getattr(item, "codigo", "") or "",
                )
                for item, unitario in zip(pedido.itens, unitarios)
            ],
        ))
        financeiro.registrar(self.contas, venda)
        eventos.avisar(self.app_id)
        return venda.numero

    # ----------------------------------------------------- origem das contas
    def _pendente(self, documento: str) -> Venda | None:
        linha = self.database.query_one("SELECT id FROM vendas WHERE numero = ?", (documento,))
        return self.repository.obter(linha["id"]) if linha else None

    def dona_de(self, documento: str) -> bool:
        return self._pendente(documento) is not None

    def conta_recebida(self, documento: str, forma: str = "", data: str = "") -> bool:
        venda = self._pendente(documento)
        if venda is None or venda.status != PENDENTE:
            return False
        self.repository.receber_pendente(
            venda.id, [pagamento_unico(forma or RECEBIDO_NO_FINANCEIRO, venda.total)],
            quitada_por=QUITADA_NO_FINANCEIRO,
        )
        eventos.avisar(self.app_id)
        return True

    def conta_reaberta(self, documento: str) -> bool:
        venda = self._pendente(documento)
        if venda is None or self.repository.desfazer_quitacao(venda.id) is None:
            return False
        eventos.avisar(self.app_id)
        return True

    # ----------------------------------------------------------------- gaveta
    def entrada(self, valor: float, motivo: str, documento: str = "") -> bool:
        entrou = self.repository.receber_na_gaveta(valor, motivo, documento)
        if entrou:
            eventos.avisar(self.app_id)
        return entrou

    def desfazer(self, valor: float, documento: str) -> bool:
        saiu = self.repository.desfazer_recebimento(valor, documento)
        if saiu:
            eventos.avisar(self.app_id)
        return saiu

    def close(self) -> None:
        self.database.close()


def _observacao(pedido: Pedido) -> str:
    partes = [f"Gerada da proposta {pedido.origem}" if pedido.origem else ""]
    if pedido.observacoes:
        partes.append(pedido.observacoes)
    return "\n".join(parte for parte in partes if parte)


def abrir_destino(caminho: Path) -> DestinoVendas:
    return DestinoVendas.abrir_banco(caminho)
