"""O resumo de uso que o Hub manda para a DumTech.

Nenhum teste acessa a internet: o servidor e um cliente falso controlado aqui.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from dumtech.core.hub_store import HubStore
from dumtech.core.supabase import SemConexao, ServicoIndisponivel
from dumtech.core.uso import UsoService

HOJE = date.today().isoformat()


def banco() -> HubStore:
    return HubStore(Path(tempfile.mkdtemp(prefix="dumtech_uso_")) / "hub.db")


class ClienteFalso:
    def __init__(self, resposta=None, excecao: Exception | None = None) -> None:
        self.resposta = resposta if resposta is not None else {"ok": True, "gravados": 0}
        self.excecao = excecao
        self.chamadas: list[tuple[str, dict]] = []

    def rpc(self, funcao: str, params: dict | None = None):
        self.chamadas.append((funcao, params or {}))
        if self.excecao is not None:
            raise self.excecao
        return self.resposta


class ContagemPorDiaTestCase(unittest.TestCase):
    """O Hub soma localmente, por dia e por modulo."""

    def setUp(self) -> None:
        self.store = banco()
        self.addCleanup(self.store.close)

    def test_abrir_conta_no_dia_de_hoje(self) -> None:
        self.store.register_open("estoque")
        self.store.register_open("estoque")
        self.store.register_open("vendas")

        pendente = self.store.uso_pendente()
        self.assertEqual(
            sorted((p["produto"], p["aberturas"]) for p in pendente),
            [("ESTOQUE", 2), ("VENDAS", 1)],
        )
        self.assertTrue(all(p["dia"] == HOJE for p in pendente))

    def test_o_codigo_vai_em_maiuscula(self) -> None:
        """No servidor o produto e ESTOQUE; aqui dentro o modulo e estoque."""
        self.store.register_open("estoque")
        self.assertEqual(self.store.uso_pendente()[0]["produto"], "ESTOQUE")

    def test_contador_de_sempre_continua_valendo(self) -> None:
        self.store.register_open("estoque")
        self.store.register_open("estoque")
        self.assertEqual(self.store.usage()["estoque"], 2)
        self.assertIsNotNone(self.store.last_opened("estoque"))

    def test_marcar_enviado_tira_da_fila(self) -> None:
        self.store.register_open("estoque")
        pendente = self.store.uso_pendente()
        self.store.marcar_uso_enviado(pendente)
        self.assertEqual(self.store.uso_pendente(), [])

    def test_abrir_de_novo_depois_de_enviar_volta_para_a_fila(self) -> None:
        self.store.register_open("estoque")
        self.store.marcar_uso_enviado(self.store.uso_pendente())

        self.store.register_open("estoque")
        pendente = self.store.uso_pendente()
        self.assertEqual(len(pendente), 1)
        self.assertEqual(pendente[0]["aberturas"], 2, "o dia continua acumulando")


class EnvioTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.store = banco()
        self.addCleanup(self.store.close)
        self.cliente = ClienteFalso({"ok": True, "gravados": 1})
        self.service = UsoService(self.store, self.cliente)
        self.store.register_open("estoque")

    def test_envia_e_marca(self) -> None:
        enviados = self.service.enviar("ABCD-EFGH-JKLM-NPQR", "MAQ-1")

        self.assertEqual(enviados, 1)
        funcao, params = self.cliente.chamadas[0]
        self.assertEqual(funcao, "dumtech_registrar_uso")
        self.assertEqual(params["p_chave"], "ABCD-EFGH-JKLM-NPQR")
        self.assertEqual(params["p_maquina"], "MAQ-1")
        self.assertEqual(params["p_uso"], [{"dia": HOJE, "produto": "ESTOQUE", "aberturas": 1}])
        self.assertEqual(self.store.uso_pendente(), [], "o que foi aceito sai da fila")

    def test_sem_internet_nada_e_marcado(self) -> None:
        offline = UsoService(self.store, ClienteFalso(excecao=SemConexao("sem rede")))
        self.assertEqual(offline.enviar("CHAVE", "MAQ-1"), 0)
        self.assertEqual(len(self.store.uso_pendente()), 1, "fica para a proxima vez")

    def test_servidor_com_problema_nao_marca(self) -> None:
        ruim = UsoService(self.store, ClienteFalso(excecao=ServicoIndisponivel("sem a funcao")))
        self.assertEqual(ruim.enviar("CHAVE", "MAQ-1"), 0)
        self.assertEqual(len(self.store.uso_pendente()), 1)

    def test_recusa_do_servidor_nao_marca(self) -> None:
        recusa = UsoService(self.store, ClienteFalso({"ok": False, "erro": "maquina_nao_ativada"}))
        self.assertEqual(recusa.enviar("CHAVE", "MAQ-1"), 0)
        self.assertEqual(len(self.store.uso_pendente()), 1)

    def test_sem_licenca_nem_tenta(self) -> None:
        self.assertEqual(self.service.enviar("", "MAQ-1"), 0)
        self.assertEqual(self.service.enviar("CHAVE", ""), 0)
        self.assertEqual(self.cliente.chamadas, [], "sem chave nao ha a quem atribuir o uso")

    def test_o_caminho_do_hub_separa_banco_de_rede(self) -> None:
        """`pendente` e `marcar` mexem no SQLite; `enviar_dados` so na rede.

        E essa divisao que mantem o banco fora da thread de segundo plano - usar
        a conexao la enquanto o Hub fecha derruba o processo inteiro.
        """
        pendentes = self.service.pendente()   # interface
        self.assertEqual(len(pendentes), 1)

        enviou = self.service.enviar_dados("CHAVE", "MAQ-1", pendentes)  # segundo plano
        self.assertTrue(enviou)
        self.assertEqual(len(self.store.uso_pendente()), 1, "ainda nao foi marcado")

        self.service.marcar(pendentes)        # interface de novo
        self.assertEqual(self.store.uso_pendente(), [])

    def test_enviar_dados_sem_nada_nao_chama_o_servidor(self) -> None:
        self.assertFalse(self.service.enviar_dados("CHAVE", "MAQ-1", []))
        self.assertFalse(self.service.enviar_dados("", "MAQ-1", [{"dia": "x"}]))
        self.assertEqual(self.cliente.chamadas, [])

    def test_sem_nada_pendente_nem_tenta(self) -> None:
        self.service.enviar("CHAVE", "MAQ-1")
        self.cliente.chamadas.clear()

        self.assertEqual(self.service.enviar("CHAVE", "MAQ-1"), 0)
        self.assertEqual(self.cliente.chamadas, [], "nao ha nada novo para enviar")


if __name__ == "__main__":
    unittest.main()
