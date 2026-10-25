"""Cliente minimo do Supabase, usado SO para licenciamento.

Nenhum aplicativo depende deste modulo para funcionar: ele e chamado apenas na
ativacao e na verificacao da licenca. Usa somente a biblioteca padrao do Python
(urllib), entao nao entra dependencia nova no instalador.

A chave "anon" abaixo e publica por natureza (o proprio Supabase a distribui
para aplicativos cliente). A protecao real esta no banco: as tabelas estao com
RLS ligado e sem policies, a chave anon nao tem privilegio nas tabelas e so
consegue executar as tres funcoes de licenca, que devolvem apenas os dados da
chave consultada. Veja supabase/migrations/.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

URL_PADRAO = "https://kpiyhhmtteojqxhhmcyr.supabase.co/rest/v1"
CHAVE_PADRAO = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtwaXloaG10dGVvanF4aGhtY3lyIiwicm9sZSI6ImFub24i"
    "LCJpYXQiOjE3ODc1NTAxMzUsImV4cCI6MjEwMzEyNjEzNX0."
    "kOvM-Pvau3Es0QD6161LLV3isA4Y7UKWCaKoKnjhQic"
)

#: permitem apontar para outro projeto (testes, homologacao) sem recompilar
ENV_URL = "DUMTECH_SUPABASE_URL"
ENV_CHAVE = "DUMTECH_SUPABASE_KEY"

TIMEOUT_PADRAO = 12.0


class SupabaseError(Exception):
    """Falha ao falar com o servidor de licencas."""


class SemConexao(SupabaseError):
    """Sem internet, DNS falhou ou o servidor demorou demais."""


class ServicoIndisponivel(SupabaseError):
    """O servidor respondeu, mas nao do jeito esperado."""


class FuncaoIndisponivel(ServicoIndisponivel):
    """A Edge Function nao foi publicada (ou ainda nao foi configurada)."""


class SupabaseClient:
    """Chamadas RPC (funcoes do banco) no Supabase."""

    def __init__(
        self,
        url: str | None = None,
        anon_key: str | None = None,
        timeout: float = TIMEOUT_PADRAO,
    ) -> None:
        # no programa instalado as variaveis nao valem: apontar o Hub para um
        # servidor falso seria o primeiro passo de qualquer golpe
        ambiente = {} if getattr(sys, "frozen", False) else os.environ
        self.url = (url or ambiente.get(ENV_URL) or URL_PADRAO).rstrip("/")
        self.anon_key = anon_key or ambiente.get(ENV_CHAVE) or CHAVE_PADRAO
        self.timeout = timeout

    @property
    def configurado(self) -> bool:
        return bool(self.url and self.anon_key)

    def rpc(self, funcao: str, params: dict[str, Any] | None = None) -> Any:
        """Executa uma funcao do banco e devolve a resposta ja convertida."""
        return self._post(f"{self.url}/rpc/{funcao}", params)

    def funcao(self, nome: str, corpo: dict[str, Any] | None = None) -> Any:
        """Chama uma Edge Function do mesmo projeto (``/functions/v1/<nome>``).

        Funcao que nao existe (404) ou que ainda nao tem os segredos (503) vira
        `FuncaoIndisponivel` - quem chama decide cair no caminho antigo.
        """
        base = self.url[: -len("/rest/v1")] if self.url.endswith("/rest/v1") else self.url
        return self._post(f"{base}/functions/v1/{nome}", corpo, edge=True)

    def _post(self, endereco: str, params: dict[str, Any] | None, edge: bool = False) -> Any:
        if not self.configurado:
            raise ServicoIndisponivel("Servidor de licenças não configurado.")

        corpo = json.dumps(params or {}).encode("utf-8")
        pedido = urllib.request.Request(
            endereco,
            data=corpo,
            method="POST",
            headers={
                "apikey": self.anon_key,
                "Authorization": f"Bearer {self.anon_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "DumTechHub/1.0",
            },
        )
        try:
            with urllib.request.urlopen(pedido, timeout=self.timeout) as resposta:
                bruto = resposta.read().decode("utf-8")
        except urllib.error.HTTPError as erro:  # o servidor respondeu com erro
            if edge:
                # respondeu, entao ha internet: qualquer erro da funcao (nao
                # publicada, sem segredo, fora do ar) manda para o caminho antigo
                raise FuncaoIndisponivel(f"Edge Function respondeu {erro.code}.") from erro
            raise self._erro_http(erro) from erro
        except urllib.error.URLError as erro:  # sem internet, DNS, timeout...
            raise SemConexao(
                "Sem conexão com a internet. Verifique sua rede e tente de novo em instantes."
            ) from erro
        except TimeoutError as erro:
            raise SemConexao("A conexão com o servidor demorou. Tente de novo em alguns instantes.") from erro

        if not bruto.strip():
            return None
        try:
            return json.loads(bruto)
        except ValueError as erro:
            raise ServicoIndisponivel(
                "O servidor de licenças retornou uma resposta inesperada. Tente de novo em alguns minutos."
            ) from erro

    # ------------------------------------------------------------------ interno
    def _erro_http(self, erro: urllib.error.HTTPError) -> SupabaseError:
        detalhe = ""
        try:
            corpo = json.loads(erro.read().decode("utf-8"))
            detalhe = str(corpo.get("message") or corpo.get("hint") or "")
        except Exception:  # noqa: BLE001 - corpo pode nao ser JSON
            detalhe = ""

        if erro.code == 404:
            return ServicoIndisponivel(
                "O servidor de licenças ainda não está preparado "
                "(as migrations de supabase/migrations foram aplicadas?)."
            )
        if erro.code in (401, 403):
            return ServicoIndisponivel(
                "Este programa não tem permissão para consultar as licenças."
            )
        if erro.code >= 500:
            return ServicoIndisponivel(
                "O servidor de licenças está fora do ar. Tente de novo em alguns minutos."
            )
        return ServicoIndisponivel(detalhe or f"Erro {erro.code} no servidor de licenças. Tente de novo.")
