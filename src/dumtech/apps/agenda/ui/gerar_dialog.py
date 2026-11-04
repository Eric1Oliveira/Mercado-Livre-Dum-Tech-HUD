"""O atendimento terminou: vira venda ou ordem de servico, com o preco ja na mao."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ....core.errors import RegraError
from ....core.pedidos import ItemPedido, Pedido
from ....ui import format as fmt
from ....ui.widgets import form
from ....ui.widgets.form import FormDialog
from ..online import Online
from ..repository import AgendaRepository


class GerarDialog(FormDialog):
    """Pergunta so o que a agenda nao sabe: em que vira e por quanto."""

    def __init__(self, repository: AgendaRepository, compromisso, destinos: list,
                 parent: QWidget | None = None) -> None:
        self.repository = repository
        self.compromisso = compromisso
        self.destinos = destinos
        self.numero = ""
        self.titulo_destino = ""
        super().__init__("Gerar do atendimento",
                         f"{compromisso.titulo}  ·  {compromisso.cliente}", parent, largura=460)

        self.destino = form.escolha([(d.titulo, i) for i, d in enumerate(destinos)], 0)
        self.add_row("Vira", self.destino)
        self.valor = form.dinheiro(self._preco())
        self.add_row("Valor", self.valor)
        if compromisso.sinal:
            self.add_note(f"O sinal de {fmt.moeda(compromisso.sinal)} já recebido sai do total.")
        self.valor.setFocus()
        self.valor.selectAll()

    def _preco(self) -> float:
        """O preco do servico de mesmo nome, se a loja cadastrou um."""
        for servico in Online(self.repository).ajustes().servicos:
            if servico.nome == self.compromisso.titulo and servico.preco is not None:
                return float(servico.preco)
        return 0.0

    def salvar(self) -> None:
        if self.valor.value() <= 0:
            raise RegraError("Informe o valor do atendimento.")
        compromisso = self.compromisso
        destino = self.destinos[self.destino.currentData()]
        self.numero = destino.abrir(Pedido(
            cliente=compromisso.cliente,
            desconto=min(compromisso.sinal, self.valor.value()),
            observacoes=f"Atendimento de {fmt.data(compromisso.inicio)}: {compromisso.titulo}",
            itens=[ItemPedido(descricao=compromisso.titulo, quantidade=1,
                              valor_unitario=self.valor.value())],
        ))
        self.titulo_destino = destino.titulo
        self.repository.marcar_documento(compromisso.id, self.numero)
