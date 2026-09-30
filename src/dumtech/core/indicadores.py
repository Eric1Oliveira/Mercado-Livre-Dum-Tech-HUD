"""O numero que cada aplicativo poe na vitrine do Inicio.

O `core/avisos.py` responde "o que precisa de atencao"; este responde outra
coisa: **"como o negocio esta agora"**. Sao os sinais vitais - o que a pessoa
olha de manha antes de qualquer problema existir.

Mesmo desenho do contrato de avisos: cada `module.py` expoe

    def indicadores(paths) -> list[Indicador]

e o Hub junta os aplicativos que a licenca liberou. Um modulo da um numero, e
so um: a linha e uma vitrine, nao um relatorio. Com um modulo ela tem um
numero e continua fazendo sentido; com sete, ela e o retrato da empresa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Indicador:
    """Um sinal vital do negocio."""

    app_id: str
    rotulo: str
    valor: str
    #: a linha de baixo, que explica o numero sem precisar de outro numero
    detalhe: str = ""
    tom: str = "accent"
    icone: str = "chart"
    #: ordena a vitrine; o dinheiro vem antes do resto
    peso: int = 0


def coletar(modulo, paths) -> list[Indicador]:
    """Pede o indicador a um modulo, sem deixar ele derrubar a tela."""
    funcao = getattr(modulo, "indicadores", None)
    if not callable(funcao):
        return []
    try:
        encontrados = funcao(paths) or []
    except Exception:  # noqa: BLE001 - contrato: modulo quebrado nao propaga
        logger.exception("Falha ao calcular os indicadores de %s",
                         getattr(modulo, "__name__", modulo))
        return []
    return [i for i in encontrados if isinstance(i, Indicador)]


def ordenar(indicadores: list[Indicador]) -> list[Indicador]:
    """O de maior peso primeiro; empate, pela ordem em que chegou."""
    return sorted(indicadores, key=lambda i: -i.peso)
