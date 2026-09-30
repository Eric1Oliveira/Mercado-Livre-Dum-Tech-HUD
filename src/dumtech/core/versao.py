"""Comparar versao e confiar (ou nao) no endereco que o servidor mandou.

As pecinhas que o aviso de versao e o atualizador usam. Quem decide o que
aparece na tela - e quem baixa e instala - e `core/atualizacao.py`; aqui nao ha
rede nem arquivo.

Comparar versao e comparar numero, nunca texto: "1.10.0" e maior que "1.9.0",
embora venha antes no alfabeto.
"""

from __future__ import annotations

import re

from .loja import url_base

#: secao das preferencias onde o manifesto assinado da atualizacao fica guardado
SECAO = "versao"


def numeros(versao: str) -> tuple[int, ...]:
    """"1.10.2" -> (1, 10, 2). Texto que nao e versao devolve tupla vazia."""
    partes = re.findall(r"\d+", str(versao or ""))
    return tuple(int(p) for p in partes[:4]) if partes else ()


def mais_nova(candidata: str, atual: str) -> bool:
    """A candidata e realmente mais nova que a instalada?"""
    a, b = numeros(candidata), numeros(atual)
    if not a or not b:
        return False
    tamanho = max(len(a), len(b))
    return a + (0,) * (tamanho - len(a)) > b + (0,) * (tamanho - len(b))


def endereco_confiavel(url: str, padrao: str = "") -> str:
    """Endereco de atualizacao so vale se for da propria DumTech.

    O campo vem do servidor. Se um dia alguem entrar no painel (ou o banco for
    adulterado), um link para um instalador falso seria o golpe perfeito: o
    cliente clica confiando no proprio programa. Fora do dominio da loja, ou
    sem https, vale o endereco padrao.
    """
    import sys
    from urllib.parse import urlparse

    texto = str(url or "").strip()
    try:
        alvo, casa = urlparse(texto), urlparse(url_base())
    except ValueError:
        return padrao

    # servidor deste computador: so FORA do programa instalado (testes e
    # homologacao). No .exe do cliente isto nunca vale.
    local = (alvo.hostname or "").lower() in ("127.0.0.1", "localhost", "::1")
    if local and not getattr(sys, "frozen", False) and alvo.scheme.lower() in ("http", "https"):
        return texto

    if alvo.scheme.lower() != "https" or not casa.hostname:
        return padrao
    return texto if (alvo.hostname or "").lower() == casa.hostname.lower() else padrao


# -------------------------------------------------------------- "agora nao" --
def dispensar(settings, versao: str) -> None:
    """O cliente clicou em "Agora nao": cala ate sair outra versao."""
    settings.set(SECAO, "dispensada", str(versao))
    settings.save()


def foi_dispensada(settings, versao: str) -> bool:
    return str(settings.get(SECAO, "dispensada", "")) == str(versao)
