"""O resumo de uso que o Hub manda para a DumTech.

O QUE VAI
    uma linha por dia e por modulo: "ESTOQUE, 2026-09-12, 7 aberturas".

O QUE NAO VAI
    hora, sequencia, nome de cliente, nada do que foi digitado dentro do
    modulo, nenhum dado dos bancos dos aplicativos. O resumo e agregado antes
    de sair do computador.

QUANDO VAI
    de carona nas tarefas de rede do Hub (abertura do programa, e depois de uma
    compra), e so quando ja existe licenca ativa - e a chave que diz de quem e
    aquele uso. Sem internet, os dias ficam guardados e vao na proxima vez;
    enviar de novo o mesmo dia nao soma duas vezes (o servidor fica com o maior
    numero).

Falhar aqui e silencio no log: ninguem abre o programa para mandar estatistica.
"""

from __future__ import annotations

import logging

from .supabase import SupabaseClient, SupabaseError

logger = logging.getLogger(__name__)

#: funcao do servidor que recebe o resumo
FUNCAO = "dumtech_registrar_uso"


class UsoService:
    """Envia o uso agregado guardado no `hub.db`."""

    def __init__(self, store, client: SupabaseClient | None = None) -> None:
        self.store = store
        self.client = client or SupabaseClient()

    # ---------------------------------------------------------------- banco --
    # REGRA: `pendente` e `marcar` tocam no SQLite do Hub e por isso rodam
    # SEMPRE na thread da interface. A conexao do banco e uma so (compartilhada
    # entre as telas) e usa-la no segundo plano enquanto o Hub fecha derruba o
    # processo inteiro - violacao de acesso, sem excecao, sem log. Em segundo
    # plano vai apenas `enviar_dados`, que so fala com a internet.
    def pendente(self) -> list[dict]:
        return self.store.uso_pendente()

    def marcar(self, pendentes: list[dict]) -> None:
        """Tira da fila o que o servidor aceitou."""
        if pendentes:
            self.store.marcar_uso_enviado(pendentes)

    # ------------------------------------------------------------- so rede --
    def enviar_dados(self, chave: str, maquina: str, pendentes: list[dict]) -> bool:
        """Manda o resumo ja lido. Pode rodar em segundo plano."""
        chave = (chave or "").strip()
        maquina = (maquina or "").strip()
        if not chave or not maquina or not pendentes:
            return False  # sem licenca ativa nao ha a quem atribuir o uso

        try:
            resposta = self.client.rpc(
                FUNCAO, {"p_chave": chave, "p_maquina": maquina, "p_uso": pendentes}
            )
        except SupabaseError as erro:
            logger.info("Uso nao enviado (fica para a proxima): %s", erro)
            return False
        except Exception:  # noqa: BLE001 - estatistica nao derruba o Hub
            logger.exception("Falha inesperada ao enviar o uso")
            return False

        if not (isinstance(resposta, dict) and resposta.get("ok")):
            logger.info("O servidor nao aceitou o uso: %s", resposta)
            return False
        return True

    # ------------------------------------------------------------ caminho unico
    def enviar(self, chave: str, maquina: str) -> int:
        """Le, manda e marca - para quem chama de uma thread so (testes, tools).

        No Hub o caminho e outro: `pendente()` antes de ir para o segundo plano,
        `enviar_dados()` la dentro, `marcar()` de volta na interface.
        """
        pendentes = self.pendente()
        if not pendentes:
            return 0
        if not self.enviar_dados(chave, maquina, pendentes):
            return 0
        self.marcar(pendentes)
        return len(pendentes)
