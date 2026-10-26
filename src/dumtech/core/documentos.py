"""CPF e CNPJ: validacao pelo digito verificador e formatacao.

Validar de verdade (e nao so contar os digitos) evita o erro que mais suja
cadastro no Brasil: o documento digitado errado que so aparece na hora de
emitir a nota. Sem dependencia externa - a conta e simples.
"""

from __future__ import annotations

CPF_TAMANHO = 11
CNPJ_TAMANHO = 14


def so_digitos(valor: str | None) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


def _digito(numeros: list[int], pesos: list[int]) -> int:
    soma = sum(n * p for n, p in zip(numeros, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cpf_valido(valor: str | None) -> bool:
    numeros = [int(d) for d in so_digitos(valor)]
    if len(numeros) != CPF_TAMANHO or len(set(numeros)) == 1:
        return False  # 111.111.111-11 passa na conta, mas nao existe
    primeiro = _digito(numeros[:9], list(range(10, 1, -1)))
    segundo = _digito(numeros[:10], list(range(11, 1, -1)))
    return numeros[9] == primeiro and numeros[10] == segundo


def cnpj_valido(valor: str | None) -> bool:
    numeros = [int(d) for d in so_digitos(valor)]
    if len(numeros) != CNPJ_TAMANHO or len(set(numeros)) == 1:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    primeiro = _digito(numeros[:12], pesos1)
    segundo = _digito(numeros[:13], pesos2)
    return numeros[12] == primeiro and numeros[13] == segundo


def documento_valido(valor: str | None) -> bool:
    """Aceita CPF ou CNPJ. Vazio e valido: o documento nao e obrigatorio."""
    digitos = so_digitos(valor)
    if not digitos:
        return True
    if len(digitos) == CPF_TAMANHO:
        return cpf_valido(digitos)
    if len(digitos) == CNPJ_TAMANHO:
        return cnpj_valido(digitos)
    return False


def tipo_documento(valor: str | None) -> str:
    """"CPF", "CNPJ" ou "" quando nao da para saber."""
    tamanho = len(so_digitos(valor))
    if tamanho == CPF_TAMANHO:
        return "CPF"
    if tamanho == CNPJ_TAMANHO:
        return "CNPJ"
    return ""


def formatar_documento(valor: str | None) -> str:
    """000.000.000-00 ou 00.000.000/0000-00. Devolve como veio se nao encaixar."""
    d = so_digitos(valor)
    if len(d) == CPF_TAMANHO:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == CNPJ_TAMANHO:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return (valor or "").strip()


def formatar_telefone(valor: str | None) -> str:
    """(63) 99999-0000 e (63) 3225-8899."""
    d = so_digitos(valor)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return (valor or "").strip()


def telefone_valido(valor: str | None) -> bool:
    """Telefone brasileiro com DDD: 10 ou 11 digitos (o 55 na frente e aceito).

    DDD vai de 11 a 99 e nenhum termina em 0 - "(10)" e "(01)" sao erro de
    digitacao, nao um numero que alguem vai atender.
    """
    d = so_digitos(valor)
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    return len(d) in (10, 11) and d[0] != "0" and d[1] != "0"


def mascara_telefone(valor: str | None) -> str:
    """O telefone formatado enquanto a pessoa digita: (63) 9, (63) 99999-0..."""
    d = so_digitos(valor)[:11]
    if len(d) <= 2:
        return f"({d}" if d else ""
    ddd, resto = d[:2], d[2:]
    if len(resto) <= 4:
        return f"({ddd}) {resto}"
    corte = 5 if len(d) == 11 else 4
    return f"({ddd}) {resto[:corte]}-{resto[corte:]}"


def formatar_cep(valor: str | None) -> str:
    d = so_digitos(valor)
    return f"{d[:5]}-{d[5:]}" if len(d) == 8 else (valor or "").strip()
