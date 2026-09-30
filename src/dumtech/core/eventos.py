"""Quando um modulo escreve no dado de outro, alguem precisa contar.

As pontes (`core/contas.py`, `core/catalog.py`, `core/pedidos.py` e a agenda de
`core/contacts.py`) resolvem metade do problema: o dado atravessa. A outra
metade e esta - o modulo do outro lado ja esta aberto, com a tela desenhada, e
nao tem como adivinhar que o saldo mudou. Sem aviso, a venda dava baixa no
estoque e o Estoque aberto ao lado continuava mostrando o numero velho ate ser
fechado e aberto de novo.

Aqui mora **so o recado**, e ele e do tamanho de um bilhete: o app_id de quem
teve o dado alterado. Quem escreve nao sabe quem esta ouvindo (pode nao haver
ninguem - o cliente pode nem ter comprado o outro modulo) e quem ouve decide o
que fazer. Hoje quem ouve e o Hub, que manda a casca correspondente recarregar.

De proposito sem Qt: `core/` nao depende de interface, e um barramento que
precisa de QApplication para existir nao poderia ser testado nem usado por
quem so escreve no banco.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

#: quem quer saber que um dado mudou. Cada ouvinte recebe o app_id da origem.
Ouvinte = Callable[[str], None]

_ouvintes: list[Ouvinte] = []


def ouvir(ouvinte: Ouvinte) -> None:
    """Passa a receber os avisos. Registrar duas vezes nao duplica o recado."""
    if ouvinte not in _ouvintes:
        _ouvintes.append(ouvinte)


def parar_de_ouvir(ouvinte: Ouvinte) -> None:
    """Sai da lista. Sair sem estar na lista e situacao normal, nao erro."""
    if ouvinte in _ouvintes:
        _ouvintes.remove(ouvinte)


def avisar(app_id: str) -> None:
    """Anuncia que o dado deste aplicativo mudou.

    Nunca levanta: isto e chamado logo depois de uma escrita que ja deu certo,
    e derrubar a venda porque a tela do vizinho nao conseguiu recarregar seria
    trocar um desconforto por um prejuizo. Ouvinte com defeito vira log.
    """
    if not app_id:
        return
    for ouvinte in list(_ouvintes):
        try:
            ouvinte(app_id)
        except Exception:  # noqa: BLE001 - aviso nunca derruba quem escreveu
            logger.exception("Ouvinte falhou ao tratar a mudanca em %s", app_id)


def limpar() -> None:
    """Esquece todos os ouvintes (usado no encerramento e nos testes)."""
    _ouvintes.clear()
