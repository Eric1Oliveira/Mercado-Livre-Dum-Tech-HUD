"""Os dois papeis do balcao, em 40 colunas.

**Entrada** e o papel que evita a discussao depois: registra o que foi pedido,
o que veio junto e em que estado. **Entrega** presta contas do que foi feito e
a partir de quando a garantia corre.

Servem a qualquer ramo, e por isso **nada em branco e impresso**: quem so
anota cliente e servico leva um papel curto, sem "Item ou local: ____" nem
"Acessorios recebidos: nenhum". Linha que nao diz nada e linha que faz o
cliente perguntar o que faltou.
"""

from __future__ import annotations

from ...ui import format as fmt
from ...ui.recibo import (
    cabecalho_empresa,
    centro,
    lado_a_lado,
    linha,
    quebrar,
    rodape_empresa,
)
from .models import ABERTA, AGUARDANDO, CANCELADA, Ordem

ASSINATURA = "____________________________________"


def _cabecalho(ordem: Ordem, titulo: str, empresa=None) -> list[str]:
    linhas = [*cabecalho_empresa(empresa), centro(titulo), linha("="),
              lado_a_lado(ordem.numero, fmt.data(ordem.aberta_em))]
    linhas += quebrar(f"Cliente: {ordem.cliente}")
    if ordem.telefone:
        linhas.append(f"Telefone: {fmt.telefone(ordem.telefone)}")
    if ordem.equipamento:
        linhas.append(linha())
        linhas += quebrar(f"Item ou local: {ordem.equipamento}")
    return linhas


def _assinatura(rotulo: str) -> list[str]:
    return ["", "", centro(ASSINATURA), centro(rotulo)]


def entrada(ordem: Ordem, empresa=None) -> str:
    """O comprovante que o cliente leva quando deixa o servico contratado."""
    linhas = _cabecalho(ordem, "COMPROVANTE DE ENTRADA", empresa)

    if ordem.defeito:
        linhas.append("")
        linhas.append("O que foi pedido:")
        linhas += quebrar(ordem.defeito, recuo=2)

    # O bloco so aparece quando ha alguma coisa a receber.
    #
    # Escrito "Nenhum acessorio recebido", ele protege quem FICA com o item do
    # cliente: meses depois ninguem cobra um carregador que nunca entregou. Mas
    # so faz sentido se algo entrou. Numa instalacao, numa revisao no local ou
    # numa chave feita na hora nao ha item nenhum na loja, e a linha vira uma
    # pergunta ("que acessorio?") no comprovante de quem nem recebe acessorio.
    acessorios = ordem.acessorios_lista
    if acessorios or ordem.equipamento:
        linhas.append(linha())
        linhas.append("O que veio junto:")
        linhas += ([f"  [X] {item}" for item in acessorios] or
                   ["  Nenhum acessório recebido"])

    if ordem.condicao:
        linhas.append("")
        linhas.append("Estado na entrada:")
        linhas += quebrar(ordem.condicao, recuo=2)

    linhas.append(linha())
    if ordem.prazo:
        linhas.append(lado_a_lado("Previsão", fmt.data(ordem.prazo)))
    if ordem.tecnico:
        linhas.append(lado_a_lado("Responsável", ordem.tecnico))
    if ordem.valor:
        linhas.append(lado_a_lado("Valor previsto", fmt.moeda(ordem.total)))

    # O aviso de aprovacao so vale para quem ORCA antes de fazer. Antes ele
    # saia sempre, e no comprovante do lava-jato era mentira impressa.
    #
    # O sinal de que ha orcamento pendente e concreto: ha um valor na mao do
    # cliente e ninguem aprovou ainda. Nao pode depender da etapa - a entrada
    # costuma ser impressa com a ordem ainda "aberta", antes de ir para
    # aprovacao, entao amarrar em AGUARDANDO tirava o aviso de quase todo mundo.
    aviso = "Guarde este comprovante para retirar o serviço."
    orcamento_pendente = bool(ordem.total) and not ordem.aprovada
    if orcamento_pendente and ordem.status in (ABERTA, AGUARDANDO):
        aviso = "O serviço só começa depois da aprovação do orçamento. " + aviso
    linhas += ["", *quebrar(aviso)]
    linhas += _assinatura("Assinatura do cliente")
    linhas += [linha("="), *rodape_empresa(empresa), centro("Documento sem valor fiscal")]
    return "\n".join(linhas)


def entrega(ordem: Ordem, empresa=None) -> str:
    """O comprovante que fecha o servico e abre o prazo de garantia."""
    linhas = _cabecalho(ordem, "COMPROVANTE DE ENTREGA", empresa)

    if ordem.diagnostico:
        linhas.append("")
        linhas.append("O que foi feito:")
        linhas += quebrar(ordem.diagnostico, recuo=2)

    if ordem.itens:
        linhas.append(linha())
        for item in ordem.itens:
            linhas += quebrar(f"{item.tipo_label}: {item.descricao}")
            detalhe = f"  {fmt.numero(item.quantidade)} x {fmt.moeda(item.valor_unitario)}"
            linhas.append(lado_a_lado(detalhe, fmt.moeda(item.total)))

        linhas.append(linha())
        linhas.append(lado_a_lado("Materiais", fmt.moeda(ordem.total_pecas)))
        linhas.append(lado_a_lado("Serviços", fmt.moeda(ordem.total_servicos)))

    linhas.append(linha())
    if ordem.desconto:
        linhas.append(lado_a_lado("Subtotal", fmt.moeda(ordem.subtotal)))
        linhas.append(lado_a_lado("Desconto", f"-{fmt.moeda(ordem.desconto)}"))
    linhas.append(lado_a_lado("TOTAL", fmt.moeda(ordem.total)))

    if ordem.aprovado_em:
        linhas.append("")
        linhas += quebrar(
            f"Orçamento aprovado por {ordem.aprovado_por} em "
            f"{fmt.data(ordem.aprovado_em)}."
        )

    linhas.append(linha())
    if ordem.entregue_em:
        linhas.append(lado_a_lado("Entregue em", fmt.data(ordem.entregue_em)))
    if ordem.garantia_ate:
        linhas.append(lado_a_lado(f"Garantia ({ordem.garantia_dias} dias)",
                                  f"até {fmt.data(ordem.garantia_ate)}"))
        linhas += quebrar(
            "A garantia cobre o serviço executado e os materiais aplicados. "
            "Não cobre mau uso, dano acidental nem intervenção de terceiros."
        )
    else:
        linhas.append("Sem garantia para este serviço.")

    if ordem.status == CANCELADA:
        linhas += ["", centro("*** ORDEM CANCELADA ***")]

    linhas += _assinatura("Recebi o serviço nas condições acima")
    linhas += [linha("="), *rodape_empresa(empresa), centro("Documento sem valor fiscal")]
    return "\n".join(linhas)
