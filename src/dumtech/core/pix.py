"""O "Pix copia e cola" da venda - o texto que vira QR Code.

O balcao resolvia isto por fora: o operador abria o aplicativo do banco no
proprio celular, gerava o QR ali e depois digitava o valor no sistema. Duas
digitacoes do mesmo numero, com a fila esperando.

Aqui mora **so o texto**, como no resto de `core/`: nada de Qt, nada de imagem.
Quem desenha o QR e `ui/widgets/qr.py`; quem mostra e o dialogo de Receber.

Este e o **Pix estatico**: o codigo e montado no proprio computador a partir da
chave do lojista, sem banco, sem cadastro e sem internet - do jeito que o resto
da plataforma funciona. O preco disso precisa estar dito em voz alta: **o
sistema nao fica sabendo se o cliente pagou.** Quem confere e o operador, no
aplicativo do banco dele. Nada neste arquivo pode sugerir o contrario.

O formato e o BR Code (EMV MPM): uma cadeia de campos `ID + tamanho + valor`,
encadeados, fechada por um CRC16. Campo dentro de campo e so mais uma cadeia.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .documentos import cnpj_valido, cpf_valido, so_digitos
from .errors import RegraError

#: identificador do arranjo Pix dentro do campo 26
GUI = "br.gov.bcb.pix"

#: tipos de chave que o Pix aceita
CPF = "CPF"
CNPJ = "CNPJ"
TELEFONE = "telefone"
EMAIL = "e-mail"
ALEATORIA = "aleatoria"

#: o campo 59 cabe 25 caracteres e o 60 cabe 15 - o banco corta ou recusa
NOME_MAXIMO = 25
CIDADE_MAXIMO = 15

#: quando a loja ainda nao preencheu os dados. Nem o nome nem a cidade mudam
#: para onde o dinheiro vai: eles so aparecem na confirmacao do celular, e um
#: QR generico que paga vale mais que um QR que nao existe.
NOME_PADRAO = "LOJA"
CIDADE_PADRAO = "BRASIL"

#: o txid quando a cobranca nao tem numero de documento
TXID_CORINGA = "***"
TXID_MAXIMO = 25


class PixError(RegraError):
    """Nao da para montar a cobranca (mensagem pronta para o usuario)."""


@dataclass(frozen=True)
class CobrancaPix:
    """O que precisa ser dito para nascer um QR Code de Pix."""

    chave: str
    beneficiario: str = ""
    cidade: str = ""
    #: zero significa QR sem valor - o cliente digita quanto vai pagar
    valor: float = 0.0
    #: numero do documento de origem (VEN-2026-0001); vira o txid
    documento: str = ""


# --------------------------------------------------------------------- chave
def tipo_chave(chave: str) -> str:
    """Qual dos cinco formatos e este. Texto vazio quando nao e chave nenhuma."""
    texto = (chave or "").strip()
    if not texto:
        return ""

    if "@" in texto:
        return EMAIL if _email_valido(texto) else ""

    digitos = so_digitos(texto)
    if len(digitos) == 11 and cpf_valido(digitos) and not _parece_telefone(texto):
        return CPF
    if len(digitos) == 14 and cnpj_valido(digitos):
        return CNPJ
    if len(digitos) in (10, 11) and _parece_telefone(texto):
        return TELEFONE
    if len(digitos) == 11 and cpf_valido(digitos):
        return CPF
    if _aleatoria_valida(texto):
        return ALEATORIA
    return ""


def normalizar(chave: str) -> str:
    """Deixa a chave no formato que o Pix espera. Levanta se nao for chave."""
    texto = (chave or "").strip()
    tipo = tipo_chave(texto)
    if tipo == EMAIL:
        return texto.lower()
    if tipo in (CPF, CNPJ):
        return so_digitos(texto)
    if tipo == TELEFONE:
        return f"+55{so_digitos(texto)}"
    if tipo == ALEATORIA:
        return texto.lower()
    raise PixError(
        "Essa chave Pix nao parece valida. Use CPF, CNPJ, telefone, e-mail ou "
        "a chave aleatoria que o banco gerou."
    )


def chave_valida(chave: str) -> bool:
    """Para a tela de Minha empresa: vazio continua valido (Pix e opcional)."""
    texto = (chave or "").strip()
    return not texto or bool(tipo_chave(texto))


# ------------------------------------------------------------------- payload
def payload(cobranca: CobrancaPix) -> str:
    """O texto do "copia e cola" - e o mesmo que vai dentro do QR."""
    chave = normalizar(cobranca.chave)
    if float(cobranca.valor or 0) < 0:
        raise PixError("O valor da cobranca nao pode ser negativo.")

    conta = _campo("00", GUI) + _campo("01", chave)
    partes = [
        _campo("00", "01"),          # formato do payload
        _campo("26", conta),         # a conta que recebe
        _campo("52", "0000"),        # categoria do comerciante
        _campo("53", "986"),         # real
    ]
    if float(cobranca.valor or 0) > 0:
        partes.append(_campo("54", f"{float(cobranca.valor):.2f}"))
    partes += [
        _campo("58", "BR"),
        _campo("59", _texto_curto(cobranca.beneficiario, NOME_MAXIMO, NOME_PADRAO)),
        _campo("60", _texto_curto(cobranca.cidade, CIDADE_MAXIMO, CIDADE_PADRAO)),
        _campo("62", _campo("05", _txid(cobranca.documento))),
    ]

    corpo = "".join(partes) + "6304"  # o CRC entra sobre a cadeia com o "6304"
    return corpo + crc16(corpo)


def campos(texto: str) -> dict[str, str]:
    """Le a cadeia de volta em `{id: valor}` - usado pelos testes e por conferencia.

    Percorrer so chega ao fim se cada tamanho declarado bater com o conteudo,
    entao isto tambem prova que a cadeia esta bem formada.
    """
    lidos: dict[str, str] = {}
    posicao = 0
    while posicao + 4 <= len(texto):
        cid = texto[posicao:posicao + 2]
        try:
            tamanho = int(texto[posicao + 2:posicao + 4])
        except ValueError as erro:
            raise PixError(f"Campo {cid} com tamanho ilegivel.") from erro
        inicio = posicao + 4
        fim = inicio + tamanho
        if fim > len(texto):
            raise PixError(f"Campo {cid} diz ter {tamanho} e nao cabe na cadeia.")
        lidos[cid] = texto[inicio:fim]
        posicao = fim
    return lidos


def crc16(dados: str) -> str:
    """CRC-16/CCITT-FALSE, em quatro maiusculas.

    Conferencia publicada do algoritmo: "123456789" -> 29B1. E ela que o teste
    usa como ancora - um payload de exemplo decorado nao serve de prova.
    """
    crc = 0xFFFF
    for byte in dados.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


# -------------------------------------------------------------------- pedacos
def _campo(cid: str, valor: str) -> str:
    """`ID + tamanho + valor`. O tamanho tem duas casas e conta caracteres."""
    return f"{cid}{len(valor):02d}{valor}"


def _texto_curto(valor: str, limite: int, padrao: str) -> str:
    """Sem acento, em maiusculas e dentro do limite do campo.

    Acento e o que mais quebra: o campo conta caracteres, e um "c" cedilha
    atravessado deixa o tamanho declarado diferente do conteudo - dai o banco
    recusa a cadeia inteira.
    """
    limpo = _sem_acento(valor).upper().strip()
    return (limpo or padrao)[:limite].strip()


def _sem_acento(valor: str) -> str:
    decomposto = unicodedata.normalize("NFKD", valor or "")
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _txid(documento: str) -> str:
    """So letra e numero: VEN-2026-0001 vira VEN20260001."""
    limpo = "".join(c for c in _sem_acento(documento) if c.isalnum())
    return limpo[:TXID_MAXIMO] if limpo else TXID_CORINGA


def _email_valido(texto: str) -> bool:
    usuario, _, dominio = texto.partition("@")
    return bool(usuario) and "." in dominio and not dominio.startswith(".") \
        and not dominio.endswith(".")


def _parece_telefone(texto: str) -> bool:
    """Telefone celular brasileiro: DDD + 9 digitos comecando em 9."""
    digitos = so_digitos(texto)
    if len(digitos) == 11:
        return digitos[2] == "9"
    return len(digitos) == 10


def _aleatoria_valida(texto: str) -> bool:
    """A chave que o banco gera: 32 hexadecimais em cinco blocos (UUID)."""
    blocos = texto.split("-")
    if len(blocos) != 5 or [len(b) for b in blocos] != [8, 4, 4, 4, 12]:
        return False
    return all(c in "0123456789abcdefABCDEF" for bloco in blocos for c in bloco)
