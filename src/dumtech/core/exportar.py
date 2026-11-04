"""Tirar os dados do programa para uma planilha.

Ponto e virgula e BOM porque e assim que o Excel brasileiro abre sem perguntar.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable


def _celula(valor) -> str:
    """Texto que o Excel leria como formula sai como texto: = + - @."""
    texto = str(valor if valor is not None else "")
    return f"'{texto}" if texto[:1] in ("=", "+", "-", "@") else texto


def csv_de(colunas: Iterable[str], linhas: Iterable[Iterable]) -> str:
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(colunas)
    for linha in linhas:
        escritor.writerow([_celula(valor) for valor in linha])
    return saida.getvalue()


def gravar(caminho: Path | str, texto: str) -> None:
    """BOM para o Excel ler os acentos. `newline`: o CSV ja traz a quebra de linha,
    e o Windows trocaria por outra, deixando uma linha em branco entre cada uma."""
    Path(caminho).write_text(texto, encoding="utf-8-sig", newline="")
