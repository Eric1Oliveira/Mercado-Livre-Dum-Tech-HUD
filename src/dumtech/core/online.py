"""A parte online de um aplicativo: o que conversa com o servidor sozinho.

O CONTRATO (o mesmo desenho de `avisos`, `indicadores` e `celular`)
    Cada `module.py` pode expor

        def online(paths, empresa) -> Sincronia | None

    `empresa` e uma funcao que devolve os dados de Minha empresa (lidos na
    hora). A `Sincronia` tem dois metodos, os dois chamados NA THREAD DA TELA:

        preparar() -> (funcao, params) | None
            le o banco e diz o que perguntar ao servidor; None = nada a fazer
        aplicar(funcao, params, resposta) -> Resultado
            grava o que o servidor respondeu

    e, opcional, `falhou(funcao, erro)` para guardar o recado de erro.

    Entre os dois, o Hub chama o servidor em segundo plano (`ServidorDaLicenca`).
    E a regra que ja vale para o celular: banco so na thread da tela, rede so
    fora dela. O Hub continua sem saber o que existe dentro de um aplicativo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from . import assinatura
from .supabase import SemConexao, SupabaseClient, SupabaseError

logger = logging.getLogger(__name__)


@dataclass
class Resultado:
    """O que mudou depois de uma conversa com o servidor."""

    #: textos curtos para o aviso flutuante ("Novo agendamento pelo link...")
    avisos: list[str] = field(default_factory=list)
    #: algo foi gravado no banco do aplicativo (a tela aberta precisa recarregar)
    mudou: bool = False
    #: a proxima conversa deve ir logo (confirmar o que acabou de chegar)
    de_novo: bool = False
    #: o que o aviso flutuante abre ao clicar em "Ver" (ex.: a data do horario)
    alvo: str = ""


class OnlineError(Exception):
    """Erro com mensagem pronta para a tela."""

    def __init__(self, mensagem: str, codigo: str = "erro") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


#: o que o servidor responde -> o que o dono le
ERROS = {
    "licenca_invalida": "Esta licença não está ativa neste computador. Confira em Licença.",
    "sem_agenda": "A Agenda não está liberada na sua licença.",
    "muitas_tentativas": "Muitas tentativas seguidas. Espere alguns minutos e tente de novo.",
    "config_invalida": "Algum ajuste está fora do permitido. Confira e salve de novo.",
}


class ServidorDaLicenca:
    """Chama uma funcao do servidor ja com chave, maquina e computador.

    Rede pura: chamar de `ui.tasks.executar`, nunca da thread da tela. A
    licenca e conferida a cada chamada - ativou com a tela aberta, ja vale.
    """

    def __init__(self, licenca: Callable[[], Any], client: SupabaseClient | None = None) -> None:
        self._licenca = licenca
        self.client = client or SupabaseClient()

    def disponivel(self) -> bool:
        atual = self._licenca()
        return bool(atual.key) and atual.ativa and not getattr(atual, "is_local", False)

    def chamar(self, funcao: str, params: dict | None = None) -> dict:
        if not self.disponivel():
            raise OnlineError("Ative a sua licença para usar o agendamento online.", "sem_licenca")
        atual = self._licenca()
        credenciais = {"p_chave": atual.key, "p_maquina": atual.machine,
                       "p_computador": assinatura.computador_id()}
        try:
            resposta = self.client.rpc(funcao, {**credenciais, **(params or {})})
        except SemConexao as erro:
            raise OnlineError("Sem internet agora. Publica sozinho quando a conexão voltar.",
                              "sem_internet") from erro
        except SupabaseError as erro:
            # 404: a migration ainda nao esta no servidor
            raise OnlineError("O servidor da DumTech ainda não está pronto para isso.",
                              "servidor") from erro
        if not isinstance(resposta, dict):
            raise OnlineError("O servidor da DumTech respondeu de um jeito inesperado.", "servidor")
        if not resposta.get("ok"):
            codigo = str(resposta.get("erro") or "erro")
            mensagem = ERROS.get(codigo) or str(resposta.get("mensagem") or "") \
                or "Não foi possível falar com o servidor da DumTech."
            raise OnlineError(mensagem, codigo)
        return resposta


def sincronia_de(modulo, paths, empresa) -> Any | None:
    """Pede a parte online a um modulo, sem deixar ele derrubar o Hub."""
    funcao = getattr(modulo, "online", None)
    if not callable(funcao):
        return None
    try:
        return funcao(paths, empresa)
    except Exception:  # noqa: BLE001 - modulo quebrado nao derruba o Hub
        logger.exception("Falha ao montar a parte online de %s", getattr(modulo, "__name__", modulo))
        return None
