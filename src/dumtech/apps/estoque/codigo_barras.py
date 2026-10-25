"""Codigo de barras EAN: o digito verificador, o codigo interno e as barras.

POR QUE EAN-13 COM PREFIXO 2
    Produto de fabrica ja vem com EAN (789... no Brasil). O que a loja fabrica,
    fraciona ou recebe sem codigo precisa de um numero que nunca colida com o de
    fabrica - e a faixa 200-299 do EAN e reservada exatamente para uso interno
    da loja. Todo leitor le, todo PDV aceita, e o numero cabe no campo que o
    Estoque ja tinha.

    2 + 11 digitos de sequencia + digito verificador = 13 digitos.

AS BARRAS
    Cada digito vira 7 modulos (barra = 1, espaco = 0). O EAN-13 tem 95 modulos;
    o EAN-8, 67. As tabelas abaixo sao as da norma (GS1): conjunto A e B para a
    metade esquerda, C para a direita, e o primeiro digito do EAN-13 nao e
    desenhado - ele escolhe a mistura de A e B da esquerda.

Sem biblioteca: sao tres tabelas e um laco, e o desenho fica por conta do Qt
(`etiquetas.py`), nitido em qualquer resolucao.
"""

from __future__ import annotations

#: faixa do EAN reservada para codigos da propria loja
PREFIXO_INTERNO = "2"

_A = ("0001101", "0011001", "0010011", "0111101", "0100011",
      "0110001", "0101111", "0111011", "0110111", "0001011")
_B = ("0100111", "0110011", "0011011", "0100001", "0011101",
      "0111001", "0000101", "0010001", "0001001", "0010111")
_C = ("1110010", "1100110", "1101100", "1000010", "1011100",
      "1001110", "1010000", "1000100", "1001000", "1110100")
#: o primeiro digito do EAN-13 decide A ou B em cada posicao da esquerda
_PARIDADE = ("AAAAAA", "AABABB", "AABBAB", "AABBBA", "ABAABB",
             "ABBAAB", "ABBBAA", "ABABAB", "ABABBA", "ABBABA")

GUARDA = "101"
CENTRO = "01010"


def digito_verificador(sem_digito: str) -> int:
    """Digito do EAN-8 (7 digitos) ou EAN-13 (12 digitos).

    Da direita para a esquerda, os pesos alternam 3 e 1; o digito completa a
    soma ate a proxima dezena.
    """
    soma = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(sem_digito)))
    return (10 - soma % 10) % 10


def valido(codigo: str) -> bool:
    """EAN-8, EAN-13 ou UPC-A (12) com o digito verificador certo."""
    codigo = (codigo or "").strip()
    if not codigo.isdigit() or len(codigo) not in (8, 12, 13):
        return False
    return digito_verificador(codigo[:-1]) == int(codigo[-1])


def normalizar(codigo: str) -> str:
    """UPC-A (12 digitos, comum em produto importado) e o EAN-13 com 0 na frente."""
    codigo = (codigo or "").strip()
    return "0" + codigo if len(codigo) == 12 else codigo


def interno(sequencia: int) -> str:
    """O codigo interno numero `sequencia`: 2 + 11 digitos + verificador."""
    if not 0 < sequencia < 10 ** 11:
        raise ValueError("sequência fora da faixa do código interno")
    base = f"{PREFIXO_INTERNO}{sequencia:011d}"
    return base + str(digito_verificador(base))


def sequencia_interna(codigo: str) -> int | None:
    """O numero de sequencia de um codigo interno; None se o codigo nao for nosso."""
    codigo = (codigo or "").strip()
    if len(codigo) != 13 or not codigo.startswith(PREFIXO_INTERNO) or not valido(codigo):
        return None
    return int(codigo[1:12])


def modulos(codigo: str) -> str:
    """As barras como texto de 0 e 1 (95 modulos no EAN-13, 67 no EAN-8).

    Levanta ValueError para o que nao e EAN valido - quem chama decide o que
    fazer (a etiqueta mostra so o numero).
    """
    codigo = normalizar(codigo)
    if not valido(codigo):
        raise ValueError(f"'{codigo}' não é um EAN válido")
    digitos = [int(c) for c in codigo]
    if len(digitos) == 8:
        esquerda = "".join(_A[d] for d in digitos[:4])
        direita = "".join(_C[d] for d in digitos[4:])
    else:
        paridade = _PARIDADE[digitos[0]]
        esquerda = "".join(
            (_A if lado == "A" else _B)[d] for lado, d in zip(paridade, digitos[1:7])
        )
        direita = "".join(_C[d] for d in digitos[7:])
    return GUARDA + esquerda + CENTRO + direita + GUARDA
