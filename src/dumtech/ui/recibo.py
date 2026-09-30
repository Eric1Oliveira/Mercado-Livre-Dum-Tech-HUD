"""Texto de comprovante em 40 colunas - a largura da bobina termica comum.

Aqui moram so as pecas de montagem; cada aplicativo escreve o proprio
documento com elas (`apps/vendas/recibo.py`, `apps/ordens/recibo.py`).
O mesmo texto vai para a tela e para a impressora: o que se ve e o que sai.
"""

from __future__ import annotations

LARGURA = 40


def linha(caractere: str = "-") -> str:
    return caractere * LARGURA


def centro(texto: str) -> str:
    return texto.center(LARGURA).rstrip()


def lado_a_lado(esquerda: str, direita: str) -> str:
    """Rotulo na esquerda, valor colado na direita."""
    espaco = LARGURA - len(direita)
    return f"{esquerda[:espaco - 1]:<{espaco}}{direita}"


def cabecalho_empresa(empresa) -> list[str]:
    """O topo de todo documento: quem esta entregando aquele papel.

    Sem empresa preenchida devolve nada - o documento sai como saia antes, e o
    programa continua util no primeiro dia, sem tela de configuracao nenhuma.
    """
    if empresa is None or not empresa.preenchida:
        return []

    linhas = [centro(empresa.nome.upper())]
    if empresa.razao_social.strip() and empresa.razao_social.strip() != empresa.nome.strip():
        linhas += quebrar(empresa.razao_social, centralizado=True)
    if empresa.documento_formatado:
        rotulo = empresa.tipo_documento or "Documento"
        linhas.append(centro(f"{rotulo}: {empresa.documento_formatado}"))
    if empresa.endereco_completo:
        linhas += quebrar(empresa.endereco_completo, centralizado=True)
    if empresa.contato:
        linhas += quebrar(empresa.contato, centralizado=True)
    return linhas


def rodape_empresa(empresa) -> list[str]:
    """A linha livre que o cliente escreve: garantia, condicoes, agradecimento."""
    if empresa is None or not empresa.rodape.strip():
        return []
    return quebrar(empresa.rodape, centralizado=True)


def quebrar(texto: str, recuo: int = 0, centralizado: bool = False) -> list[str]:
    """Quebra um texto longo respeitando a largura da bobina."""
    largura = LARGURA - recuo
    palavras = texto.split()
    linhas: list[str] = []
    atual = ""
    for palavra in palavras:
        if len(atual) + len(palavra) + 1 > largura:
            linhas.append(atual)
            atual = palavra[:largura]
        else:
            atual = f"{atual} {palavra}".strip()
    if atual:
        linhas.append(atual)
    return [centro(l) if centralizado else " " * recuo + l for l in linhas]
