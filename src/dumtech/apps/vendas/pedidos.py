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
    hoje_iso,
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
        """A conta quitou: o que a venda ainda devia entra com esta forma."""
        venda = self._pendente(documento)
        if venda is None or venda.status != PENDENTE:
            return False
        return self._receber(venda, forma, data, venda.em_aberto)

    def conta_recebida_em_parte(self, documento: str, forma: str = "", data: str = "",
                                valor: float = 0.0) -> bool:
        """Uma parte foi paga no Financeiro: a venda continua devendo o resto."""
        venda = self._pendente(documento)
        if venda is None or venda.status != PENDENTE:
            return False
        return self._receber(venda, forma, data, min(float(valor or 0), venda.em_aberto))

    def _receber(self, venda: Venda, forma: str, data: str, valor: float) -> bool:
        if valor <= 0:
            return False
        dia = (data or hoje_iso())[:10]
        self.repository.receber_pendente(
            venda.id, [pagamento_unico(forma or RECEBIDO_NO_FINANCEIRO, valor)],
            # baixa com data de outro dia e acerto: esse dinheiro nao esta
            # entrando agora, e a gaveta de hoje nao pode conta-lo
            gaveta=dia == hoje_iso(), quitada_por=QUITADA_NO_FINANCEIRO, quando=dia,
        )
        eventos.avisar(self.app_id)
        return True

    def baixa_estornada(self, documento: str, forma: str = "", valor: float = 0.0,
                        data: str = "") -> bool:
        """Uma baixa foi desfeita no Financeiro: aquela parte volta a ser devida.

        A entrada paga no balcao nao volta por aqui: ela passou pela gaveta na
        hora da venda, e desfazer a baixa dela nao tira nota nenhuma de la.
        """
        venda = self._pendente(documento)
        if venda is None:
            return False
        if self.repository.estornar_recebimento(venda.id, forma, valor, data) is not None:
            eventos.avisar(self.app_id)
            return True
        # venda de antes desta versao (nenhuma parte com o dia em que foi
        # paga): vale o de antes. Com marca, a baixa desfeita nao era de parte
        # recebida depois - era a entrada - e a venda fica como esta
        if not any(p.recebido_em for p in venda.pagamentos):
            return self.conta_reaberta(documento)
        return False

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
