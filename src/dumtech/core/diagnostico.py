"""O relatorio de um erro inesperado.

Sem isto, uma excecao dentro de um clique vira "o sistema nao fez nada" - o
traceback sai no stderr, e no executavel (montado com `runw.exe`, sem console)
o stderr nao existe. O cliente liga dizendo que "travou" e nao ha o que olhar.

Aqui mora so o texto do relatorio, sem Qt: da para testar sem abrir janela.
"""

from __future__ import annotations

import platform
import sys
import traceback
from datetime import datetime

#: cabe na caixa de erro sem precisar rolar de lado
LARGURA = 60


def resumo(erro: BaseException) -> str:
    """Uma linha: o tipo do erro e a mensagem, para o titulo da caixa."""
    mensagem = str(erro).strip().splitlines()
    texto = mensagem[0] if mensagem else ""
    return f"{type(erro).__name__}: {texto}" if texto else type(erro).__name__


def onde(erro: BaseException) -> str:
    """O arquivo e a linha onde estourou - o que o suporte pergunta primeiro."""
    tb = erro.__traceback__
    if tb is None:
        return "origem desconhecida"
    ultimo = traceback.extract_tb(tb)[-1]
    arquivo = ultimo.filename.replace("\\", "/").split("/")[-1]
    return f"{arquivo}, linha {ultimo.lineno}, em {ultimo.name}()"


def relatorio(erro: BaseException, versao: str = "", contexto: str = "") -> str:
    """O texto completo: vai para o log e para a area de transferencia."""
    linhas = [
        "=" * LARGURA,
        "DumTech Hub - relatorio de erro",
        "=" * LARGURA,
        f"Quando:   {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        f"Versao:   {versao or 'desconhecida'}",
        f"Sistema:  {platform.system()} {platform.release()}",
        f"Python:   {platform.python_version()}",
        f"Programa: {'executavel' if getattr(sys, 'frozen', False) else 'codigo'}",
    ]
    if contexto:
        linhas.append(f"Momento:  {contexto}")
    linhas += [
        "-" * LARGURA,
        resumo(erro),
        f"Origem:   {onde(erro)}",
        "-" * LARGURA,
        "".join(
            traceback.format_exception(type(erro), erro, erro.__traceback__)
        ).rstrip(),
        "=" * LARGURA,
    ]
    return "\n".join(linhas)
