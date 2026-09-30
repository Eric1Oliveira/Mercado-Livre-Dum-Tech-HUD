"""O que o programa ainda pergunta antes de fazer.

Excluir e fechar sao acoes que a pessoa nao desfaz com Ctrl+Z, entao o programa
pergunta. Mas quem faz a mesma coisa cinquenta vezes por dia nao quer ser
perguntado cinquenta vezes - e por isso cada pergunta tem um "nao perguntar de
novo", e a resposta fica guardada.

Guardado nas preferencias do Hub (`hub.json`), e nao no banco de nenhum
aplicativo: e uma preferencia da pessoa, nao um dado de trabalho.
"""

from __future__ import annotations

SECAO = "confirmacoes"

#: as perguntas que existem hoje, com o texto que a tela de Configuracoes usa
EXCLUIR = "excluir"
FECHAR_MODULO = "fechar_modulo"

PERGUNTAS = {
    EXCLUIR: "Confirmar antes de excluir um registro",
    FECHAR_MODULO: "Confirmar antes de fechar um aplicativo",
}

_settings = None


def usar(settings) -> None:
    """Define onde as respostas ficam guardadas (o Hub chama na abertura)."""
    global _settings
    _settings = settings


def _atual():
    """As preferencias do Hub, abertas na primeira vez que alguem pergunta.

    Sem isto, cada tela precisaria receber as preferencias so para saber se
    pergunta ou nao - e sao dezenas de telas para uma decisao de duas linhas.
    """
    global _settings
    if _settings is None:
        from .config import Settings

        _settings = Settings()
    return _settings


def deve_perguntar(chave: str) -> bool:
    """Se ainda vale perguntar. Sem resposta guardada, pergunta."""
    return bool(_atual().get(SECAO, chave, True))


def nunca_mais(chave: str) -> None:
    _guardar(chave, False)


def voltar_a_perguntar(chave: str = "") -> None:
    """Desfaz o "nao perguntar de novo" - de uma pergunta ou de todas."""
    for alvo in ([chave] if chave else list(PERGUNTAS)):
        _guardar(alvo, True)


def _guardar(chave: str, valor: bool) -> None:
    settings = _atual()
    settings.set(SECAO, chave, valor)
    settings.save()
