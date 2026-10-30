"""O que mudou nesta versao - contado uma vez, e so para quem usa o que mudou.

POR QUE EXISTE
    A atualizacao chega, o Hub reabre e a pessoa nao sabe que o defeito que ela
    reclamou foi resolvido. Entao, na primeira abertura depois de atualizar,
    o Hub mostra o que mudou e um "OK, entendi".

AS REGRAS
    * cada mudanca pertence a um modulo (`app_id`). Quem nao tem o modulo nao
      ve o aviso dela - e, sem nada que lhe diga respeito, nao ve aviso nenhum;
    * aparece uma vez: o que ja foi contado nao volta (`marcar_vista`);
    * quem pulou versoes ve tudo o que perdeu, numa janela so;
    * quem acabou de instalar nao tem "antes": nao ve novidade de nada.

O texto mora aqui, no codigo, e nao no servidor: chega junto com a versao,
funciona sem internet e nao depende de ninguem lembrar de cadastrar.

TELAS NOVAS
    A aba de uma tela nova ganha a etiqueta "Novo" ate a pessoa abrir a tela
    uma vez (`TELAS_NOVAS`). Nao precisa de janela nem de versao com aviso:
    serve tambem para a atualizacao silenciosa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .versao import mais_nova, numeros

#: secao das preferencias onde fica a ultima versao ja contada
SECAO = "novidades"


@dataclass(frozen=True)
class Novidade:
    """Uma mudanca que o cliente percebe."""

    #: modulo da mudanca ("vendas", "agenda"...); vazio = vale para todos
    app_id: str
    titulo: str
    texto: str = ""


#: versao -> o que mudou. So entra o que o cliente PERCEBE: correcao interna
#: nao vira aviso. Escreva como quem explica no balcao, sem termo tecnico.
VERSOES: dict[str, tuple[Novidade, ...]] = {
    "1.7.0": (
        Novidade(
            "clientes", "Parceiros: quem indica clientes para você",
            "Na nova aba Parceiros do Clientes, cadastre quem manda cliente para a loja. "
            "No cadastro do cliente, escolha em \"Indicado por\" e veja quantos clientes "
            "cada parceiro já indicou.",
        ),
        Novidade(
            "estoque", "Estoque: produtos para reposição",
            "No Painel, clique em Produtos para reposição para ver o que está zerado e o "
            "que está abaixo do mínimo, com a quantidade sugerida, o fornecedor e a última "
            "reposição - e registre a entrada ali mesmo. O valor do estoque agora mostra a "
            "participação de cada produto.",
        ),
        Novidade(
            "financeiro", "Financeiro mais claro",
            "O Fluxo de caixa mostra primeiro o que já entrou e já saiu no mês, e o saldo "
            "projetado diz o período. A Visão geral traz o resultado financeiro do mês, e "
            "as abas ganharam nomes novos: Fluxo de caixa, Visão geral, Lançamentos e "
            "Contas bancárias.",
        ),
    ),
    "1.6.1": (
        Novidade(
            "", "Janelas inteiras em qualquer tela",
            "Em notebook e tela menor, os cadastros agora abrem do tamanho da tela, com "
            "Salvar e Cancelar sempre à vista. Quando tem muita coisa, é o meio da janela "
            "que rola.",
        ),
        Novidade(
            "", "Atualizar ficou mais seguro",
            "Ao atualizar, aparece uma janelinha mostrando o andamento, e o Hub abre "
            "sozinho quando termina. Não precisa clicar no ícone.",
        ),
    ),
    "1.6.0": (
        Novidade(
            "vendas", "Vendas recorrentes: mensalidade sem esquecer",
            "Na aba Recorrentes do Vendas, cadastre uma vez a venda que se repete "
            "(mensalidade, fornecimento do mês). Ela aparece sozinha como venda "
            "pendente e já entra no Financeiro como conta a receber.",
        ),
        Novidade(
            "ordens", "Serviço recorrente na Ordem de Serviço",
            "Manutenção preventiva, limpeza mensal: cadastre em OS > Recorrentes e a "
            "ordem abre sozinha no Quadro alguns dias antes, com a cobrança no Financeiro.",
        ),
        Novidade(
            "financeiro", "Financeiro mostra o que é recorrente",
            "Em Lançamentos, filtre por Receitas recorrentes. No Painel, o A receber "
            "mostra quanto vem de mensalidades e contratos.",
        ),
    ),
    "1.5.5": (
        Novidade(
            "vendas", "Lançar venda com os produtos do Estoque",
            "Em Vendas > Lançar venda, comece a digitar e escolha o produto do Estoque: "
            "o preço vem sozinho e o saldo baixa quando a venda está paga. E o cliente "
            "cadastrado agora aparece na hora no campo Cliente do Balcão.",
        ),
    ),
    "1.5.4": (
        Novidade(
            "vendas", "Toda venda cai no Financeiro",
            "Venda paga na hora (dinheiro, Pix ou cartão) já entra no Financeiro como "
            "recebida. Venda a prazo continua virando conta a receber e fecha sozinha "
            "quando o cliente paga.",
        ),
    ),
    "1.5.1": (
        Novidade(
            "", "Melhorias pequenas agora chegam sozinhas",
            "Quando sair um ajuste pequeno, o Hub baixa sozinho e instala quando você "
            "fechar o programa. Na próxima vez que abrir, já está atualizado, sem clicar "
            "em nada. E tela nova aparece com a etiqueta Novo até você abrir.",
        ),
    ),
    "1.5.0": (
        Novidade(
            "agenda", "Agenda: seus clientes marcam sozinhos",
            "Na aba Online da Agenda, crie o seu link de agendamento e mande no WhatsApp "
            "ou ponha na bio do Instagram. O cliente escolhe o serviço, o dia e um horário "
            "livre, e o compromisso aparece aqui na hora, com o WhatsApp dele. Ele também "
            "pode cancelar pelo próprio link, dentro do prazo que você escolher.",
        ),
    ),
    "1.4.5": (
        Novidade(
            "estoque", "Estoque: etiquetas com código de barras",
            "Produto sem código? Clique em Gerar no cadastro e ele ganha um código "
            "que o leitor lê. Em Produtos > Etiquetas, imprima em folha A4 adesiva "
            "(Pimaco) ou na impressora de etiqueta, com nome e preço - ou salve em "
            "PDF. Depois de lançar uma nota em Entradas, o botão \"Etiquetas desta "
            "nota\" já traz a quantidade que chegou.",
        ),
    ),
    "1.4.4": (
        Novidade(
            "", "Início: o que pede atenção agora salta aos olhos",
            "O quadro \"Atenção\" ganhou cor: vermelho quando algo venceu, âmbar "
            "quando está chegando. E todos os textos do sistema agora têm acento.",
        ),
        Novidade(
            "financeiro", "Financeiro: despesa fixa e nomes mais claros",
            "No lançamento, marque se a despesa é fixa (aluguel, internet) ou "
            "variável - o Painel mostra quanto foi para cada uma. \"Repetição\" virou "
            "Recorrência, e o Fluxo mostra Saldo atual, Entradas e Saídas previstas "
            "e Saldo futuro, com o valor do dia numa coluna só.",
        ),
        Novidade(
            "estoque", "Estoque: ache o produto pelo nome",
            "Em Entradas e em Movimentações, digite parte do nome e escolha na lista. "
            "No cadastro, os campos agora se chamam Estoque mínimo e Estoque máximo.",
        ),
        Novidade(
            "ordens", "Ordens de Serviço agora se chamam OS",
            "O módulo aparece como OS, e a lista como Ordens de Serviço.",
        ),
    ),
    "1.4.3": (
        Novidade(
            "", "Celular: o resumo da empresa ficou completo",
            "Vendas de hoje comparadas com a semana passada na mesma hora, graficos "
            "de 7 e 30 dias, saldo previsto do mes e a lista do que precisa de voce "
            "hoje. Para conectar: menu da empresa > Ver no celular.",
        ),
    ),
    "1.4.2": (
        Novidade(
            "vendas", "Balcao: o Adicionar libera na hora",
            "Digitou o produto e o valor, o botao Adicionar ja acende. "
            "Nao precisa mais trocar de aba para ele funcionar.",
        ),
        Novidade(
            "agenda", "Agenda: o nome da cliente no horario",
            "Cada compromisso mostra, pequeno embaixo do titulo, para quem e. "
            "Bateu o olho, ja sabe quem vem.",
        ),
        Novidade(
            "estoque", "Estoque: foto do produto",
            "Coloque uma foto no cadastro do produto. Ela aparece na lista, "
            "na busca e no Balcao, na hora de vender.",
        ),
    ),
}


def pendentes(
    settings,
    instalada: str,
    modulos: Iterable[str],
    versoes: dict[str, tuple[Novidade, ...]] | None = None,
) -> list[Novidade]:
    """O que esta pessoa ainda nao viu e que diz respeito a ela.

    Do mais novo para o mais antigo. Sem marca guardada (primeira abertura com
    este recurso), conta so a versao instalada - e nao o historico inteiro.
    """
    versoes = VERSOES if versoes is None else versoes
    vista = str(settings.get(SECAO, "vista", "") or "")
    tem = {str(m).lower() for m in modulos}
    achadas: list[Novidade] = []
    for versao in sorted(versoes, key=numeros, reverse=True):
        if mais_nova(versao, instalada):
            continue  # texto de uma versao que ainda nao chegou aqui
        if vista:
            if not mais_nova(versao, vista):
                continue  # ja contada
        elif numeros(versao) != numeros(instalada):
            continue
        achadas.extend(n for n in versoes[versao] if not n.app_id or n.app_id in tem)
    return achadas


def marcar_vista(settings, instalada: str) -> None:
    """Tudo ate a versao instalada ja foi contado. So anda para a frente."""
    vista = str(settings.get(SECAO, "vista", "") or "")
    if vista and not mais_nova(instalada, vista):
        return
    settings.set(SECAO, "vista", str(instalada))
    settings.save()


# ---------------------------------------------------------------- telas novas --
#: "app_id/Titulo da aba" que mostram "Novo" ate a primeira visita.
#: Tire daqui quando a tela deixar de ser novidade.
TELAS_NOVAS: frozenset[str] = frozenset({
    "agenda/Online", "agenda/Serviços", "vendas/Recorrentes", "ordens/Recorrentes",
    "clientes/Parceiros",
})

#: nas preferencias de cada aplicativo: as telas novas que ja foram abertas
TELAS_VISTAS = "telas_vistas"


def _vistas(prefs) -> list[str]:
    vistas = prefs.get(TELAS_VISTAS) or []
    return list(vistas) if isinstance(vistas, list) else []


def tela_nova(prefs, app_id: str, titulo: str) -> bool:
    """A aba desta tela ainda mostra a etiqueta "Novo"?"""
    chave = f"{app_id}/{titulo}"
    return chave in TELAS_NOVAS and chave not in _vistas(prefs)


def marcar_tela_vista(prefs, app_id: str, titulo: str) -> None:
    """A pessoa abriu a tela: a etiqueta some e nao volta."""
    vistas = _vistas(prefs)
    chave = f"{app_id}/{titulo}"
    if chave not in vistas:
        prefs.set(TELAS_VISTAS, [*vistas, chave])
