"""Formatacao de numeros, dinheiro e datas no padrao brasileiro.

Modulo de texto puro, sem Qt: alem da interface, as regras de negocio o usam
para escrever valores nas mensagens de erro que o usuario le.
"""

from __future__ import annotations

from datetime import datetime

from ..core.documentos import formatar_telefone


def para_numero(texto: str | None) -> float:
    """Le um numero do jeito que o brasileiro digita.

    Aceita "1000", "1.000", "1.000,50", "1000,5", "R$ 1.234,56" e ate "1.50"
    (quem digita no teclado numerico usa o ponto como virgula). A regra: o
    ultimo separador manda; ponto sozinho com tres casas depois e milhar.
    """
    limpo = "".join(c for c in (texto or "") if c.isdigit() or c in ",.-")
    negativo = limpo.startswith("-")
    limpo = limpo.lstrip("-")
    if not limpo:
        return 0.0

    ultima_virgula = limpo.rfind(",")
    ultimo_ponto = limpo.rfind(".")
    if ultima_virgula > ultimo_ponto:
        inteiro, _, decimal = limpo.rpartition(",")
    elif ultimo_ponto > -1:
        inteiro, _, decimal = limpo.rpartition(".")
        if len(decimal) == 3:  # "1.000" e mil, nao um e meio
            inteiro, decimal = inteiro + decimal, ""
    else:
        inteiro, decimal = limpo, ""

    inteiro = "".join(c for c in inteiro if c.isdigit()) or "0"
    decimal = "".join(c for c in decimal if c.isdigit())
    try:
        valor = float(f"{inteiro}.{decimal or 0}")
    except ValueError:
        return 0.0
    return -valor if negativo else valor


def telefone(valor: str | None) -> str:
    """(63) 98877-4411. Todo documento mostra telefone do mesmo jeito."""
    return formatar_telefone(valor or "")


def moeda(valor: float | int | None) -> str:
    """R$ 1.234,56 - e -R$ 400,00, com o sinal antes do simbolo."""
    valor = float(valor or 0)
    texto = f"{abs(valor):,.2f}"
    texto = texto.replace(",", "#").replace(".", ",").replace("#", ".")
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {texto}"


def numero(valor: int | float | None) -> str:
    valor = valor or 0
    if isinstance(valor, float) and not valor.is_integer():
        return f"{valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"{int(valor):,}".replace(",", ".")


def dias(quantidade: int | float | None) -> str:
    """"1 dia" / "9 dias" - "1 dia(s)" nao e portugues."""
    valor = int(quantidade or 0)
    return "1 dia" if valor == 1 else f"{numero(valor)} dias"


def contagem(quantidade: int | None, singular: str, plural: str = "") -> str:
    """"1 proposta" / "9 propostas", sem o "(s)" preguicoso."""
    valor = int(quantidade or 0)
    if valor == 1:
        return f"1 {singular}"
    return f"{numero(valor)} {plural or singular + 's'}"


def data(iso: str | None) -> str:
    """So a data, no formato brasileiro (dd/mm/aaaa)."""
    if not iso:
        return "-"
    momento = _ler(iso)
    if momento is None:
        return iso
    return momento.strftime("%d/%m/%Y")


def dias_para(iso: str | None) -> int | None:
    """Quantos dias faltam para uma data (negativo = ja passou)."""
    momento = _ler(iso) if iso else None
    if momento is None:
        return None
    return (momento.date() - datetime.now().date()).days


def prazo_texto(iso: str | None) -> str:
    """Ex.: "vence hoje", "em 3 dias", "3 dias em atraso"."""
    dias = dias_para(iso)
    if dias is None:
        return "-"
    if dias == 0:
        return "vence hoje"
    if dias == 1:
        return "vence amanha"
    if dias > 1:
        return f"em {dias} dias"
    if dias == -1:
        return "1 dia em atraso"
    return f"{abs(dias)} dias em atraso"


def data_hora(iso: str | None) -> str:
    if not iso:
        return "-"
    momento = _ler(iso)
    if momento is None:
        return iso
    return momento.strftime("%d/%m/%Y %H:%M")


def data_hora_curta(iso: str | None) -> str:
    if not iso:
        return "-"
    momento = _ler(iso)
    if momento is None:
        return iso
    hoje = datetime.now().date()
    if momento.date() == hoje:
        return f"Hoje {momento.strftime('%H:%M')}"
    return momento.strftime("%d/%m %H:%M")


def _ler(iso: str) -> datetime | None:
    """Converte texto ISO em data local (aceita datas gravadas em UTC)."""
    try:
        momento = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if momento.tzinfo is not None:
        momento = momento.astimezone().replace(tzinfo=None)
    return momento
