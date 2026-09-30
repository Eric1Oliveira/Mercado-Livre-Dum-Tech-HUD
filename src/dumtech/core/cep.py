"""Digitou o CEP, o endereco aparece.

COMO FUNCIONA

Pergunta ao ViaCEP (https://viacep.com.br), que e publico, gratuito e nao
pede cadastro nem chave. Vai so o CEP - nome, telefone e documento do cliente
nunca saem daqui.

QUANDO NAO FUNCIONA

Sem internet, CEP novo demais ou o servico fora do ar: devolve `None` e a
tela nao muda nada. O cliente continua digitando o endereco na mao, como
sempre pode. Nunca trava o cadastro por causa disto.

A RESPOSTA E GUARDADA

O mesmo CEP costuma voltar (o bairro inteiro compra na mesma loja), e a
consulta fica na memoria enquanto o programa estiver aberto.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

URL = "https://viacep.com.br/ws/{cep}/json/"
ESPERA = 6          # segundos: o cadastro nao pode ficar parado esperando
_LEMBRADOS: dict[str, "Endereco | None"] = {}


@dataclass(frozen=True)
class Endereco:
    """O que o CEP diz. Numero e complemento sempre ficam com quem digita."""

    cep: str = ""
    logradouro: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""

    @property
    def util(self) -> bool:
        """CEP de cidade inteira nao traz rua - mas cidade e UF ja ajudam."""
        return bool(self.cidade or self.logradouro)


def so_digitos(cep: str) -> str:
    return re.sub(r"\D", "", cep or "")[:8]


def completo(cep: str) -> bool:
    """Ja da para perguntar? (oito digitos)"""
    return len(so_digitos(cep)) == 8


def formatar(cep: str) -> str:
    digitos = so_digitos(cep)
    return f"{digitos[:5]}-{digitos[5:]}" if len(digitos) == 8 else digitos


def buscar(cep: str, *, abrir=urllib.request.urlopen) -> Endereco | None:
    """O endereco do CEP, ou None quando nao da para saber.

    Roda em segundo plano (`ui.tasks.executar`): esta funcao fala com a rede e
    nao pode ser chamada direto da interface.
    """
    digitos = so_digitos(cep)
    if len(digitos) != 8:
        return None
    if digitos in _LEMBRADOS:
        return _LEMBRADOS[digitos]

    pedido = urllib.request.Request(
        URL.format(cep=digitos),
        headers={"User-Agent": "DumTechHub/cep", "Accept": "application/json"},
    )
    try:
        with abrir(pedido, timeout=ESPERA) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return None                     # sem internet ou servico fora: sem drama

    if not isinstance(dados, dict) or dados.get("erro"):
        _LEMBRADOS[digitos] = None      # CEP que nao existe continua nao existindo
        return None

    achado = Endereco(
        cep=formatar(digitos),
        logradouro=str(dados.get("logradouro") or "").strip(),
        bairro=str(dados.get("bairro") or "").strip(),
        cidade=str(dados.get("localidade") or "").strip(),
        uf=str(dados.get("uf") or "").strip().upper()[:2],
    )
    resultado = achado if achado.util else None
    _LEMBRADOS[digitos] = resultado
    return resultado


def esquecer() -> None:
    """Limpa o que ficou na memoria (usado nos testes)."""
    _LEMBRADOS.clear()
