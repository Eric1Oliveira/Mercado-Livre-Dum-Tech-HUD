"""Pagamentos protegidos: a chave Pix e as formas de pagamento do balcao.

POR QUE EXISTE
    A chave Pix morava no ``hub.json``, um arquivo comum. Quem trocasse a chave
    ali - um funcionario na tela de configuracoes ou um virus no arquivo -
    desviava o dinheiro do balcao, e o QR Code continuava aparecendo normal.

COMO FUNCIONA
    * a area de Pagamentos so abre com um codigo que chega no e-mail DA LICENCA
      (o do servidor, nunca um e-mail gravado neste computador);
    * o codigo abre uma sessao de 15 minutos. Trocar a chave Pix precisa dela;
    * o servidor ASSINA a chave Pix para este computador (Ed25519, a mesma
      chave da licenca). O balcao so mostra QR Code de chave com assinatura
      valida: editar o arquivo nao muda para onde o dinheiro vai;
    * toda troca de chave manda um aviso para o e-mail do dono.

SEM INTERNET
    A area nao abre - e a tela diz isso com todas as letras. Nao ha codigo de
    reserva guardado neste computador: um codigo que abre a porta sem falar com
    o servidor e mais uma chave para alguem achar. Quem perdeu o acesso ao
    e-mail resolve com a DumTech, que troca o e-mail da licenca no painel.
    **O balcao continua vendendo normalmente offline**: a chave Pix ja
    confirmada fica valendo, com QR Code e tudo.

O QUE NAO RESOLVE (limite honesto)
    Programa alterado (o .exe modificado para pular a conferencia). Isso ja nao
    e editar um arquivo - e outro nivel de ataque.

Aqui nao ha Qt: a tela e ``hub/views/pagamentos_view.py``. As chamadas de rede
(`pedir_codigo`, `entrar`, `salvar_pix`...) podem rodar em segundo plano; as que
gravam no ``hub.json`` (`aplicar_*`, `guardar_assinado`) rodam na thread da
interface.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from . import assinatura
from .pix import normalizar as normalizar_pix
from .supabase import FuncaoIndisponivel, SemConexao, SupabaseClient, SupabaseError

logger = logging.getLogger(__name__)

SECAO = "pagamentos"

#: Edge Function que responde por tudo isto (supabase/functions/pagamentos)
FUNCAO = "pagamentos"

#: marca do documento assinado - separa a chave Pix de uma licenca
USO = "pagamentos"

#: o servidor da 15 minutos; a tela tranca um pouco antes para nunca mostrar
#: "liberado" com a sessao ja vencida la
SESSAO_SEGUNDOS = 14 * 60

#: A unica forma que mexe na gaveta - e a unica que da troco.
DINHEIRO = "Dinheiro"

#: A unica que o balcao sabe cobrar sozinho, mostrando o QR Code na tela.
PIX = "Pix"

FORMAS = (DINHEIRO, PIX, "Cartao de debito", "Cartao de credito", "Boleto", "Prazo")

SEM_INTERNET = (
    "Você está sem internet. Conecte o computador para mexer em Pagamentos - "
    "o balcão continua vendendo normalmente."
)


class PagamentosError(Exception):
    """Erro com mensagem pronta para a tela."""

    def __init__(self, mensagem: str, codigo: str = "erro") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


# ====================================================== leitura (sem rede) ===
def pix_confirmada(settings) -> str:
    """A chave Pix que o balcao pode usar: so a assinada para ESTE computador."""
    dados = _abrir(settings.get(SECAO, "assinado"))
    return str(dados.get("pix_chave") or "") if dados else ""


def formas_ocultas(settings) -> tuple[str, ...]:
    valor = settings.get(SECAO, "formas_ocultas", []) or []
    if not isinstance(valor, list):
        return ()
    return tuple(str(forma) for forma in valor if str(forma) in FORMAS)


def formas_do_balcao(ocultas=()) -> list[str]:
    """As formas que aparecem no Receber. Esconder todas devolve o Dinheiro."""
    visiveis = [forma for forma in FORMAS if forma not in set(ocultas or ())]
    return visiveis or [DINHEIRO]


def _abrir(pacote: Any) -> dict | None:
    dados = assinatura.abrir(pacote) if isinstance(pacote, dict) else None
    if not dados or dados.get("uso") != USO:
        return None
    if dados.get("computador") != assinatura.computador_id():
        logger.warning("Chave Pix assinada para outro computador: ignorada")
        return None
    return dados


# ================================================================ o acesso ===
@dataclass
class Acesso:
    """A area de Pagamentos esta aberta - ate `expira` (relogio monotonic)."""

    expira: float

    def segundos_restantes(self, agora: float) -> int:
        return max(int(self.expira - agora), 0)


class PagamentosService:
    """Codigo por e-mail, sessao curta e a chave Pix assinada."""

    def __init__(
        self,
        settings,
        licenca: Callable[[], Any],
        client: SupabaseClient | None = None,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self._licenca = licenca
        self.client = client or SupabaseClient()
        self._relogio = relogio
        self._acesso: Acesso | None = None
        #: segredo da sessao do servidor: so na memoria, nunca no disco
        self._sessao = ""

    # ------------------------------------------------------------------ estado
    @property
    def acesso(self) -> Acesso | None:
        if self._acesso is not None and self._acesso.segundos_restantes(self._relogio()) <= 0:
            self.trancar()
        return self._acesso

    def segundos_restantes(self) -> int:
        acesso = self.acesso
        return acesso.segundos_restantes(self._relogio()) if acesso else 0

    @property
    def liberado(self) -> bool:
        return self.acesso is not None

    def trancar(self) -> None:
        self._acesso = None
        self._sessao = ""

    @property
    def pode_usar(self) -> bool:
        """Licenca do servidor ativa neste computador (sem ela, nao ha a quem pedir codigo)."""
        licenca = self._licenca()
        return bool(licenca and licenca.ativa and licenca.source == "supabase")

    # ------------------------------------------------------ rede (2o plano) ---
    def pedir_codigo(self) -> str:
        """Pede o codigo. Devolve o e-mail mascarado para onde ele foi."""
        resposta = self._chamar("codigo", self._identidade())
        return str(resposta.get("email") or "")

    def entrar(self, codigo: str) -> dict:
        texto = (codigo or "").strip()
        if not re.fullmatch(r"\d{6}", texto):
            raise PagamentosError("Digite os 6 números que chegaram no e-mail.", "formato")
        return self._chamar("entrar", {**self._identidade(), "codigo": texto})

    def salvar_pix(self, nova: str) -> dict:
        if self.acesso is None:
            raise PagamentosError("O acesso a Pagamentos venceu. Entre de novo com um código.",
                                  "sessao_vencida")
        texto = (nova or "").strip()
        chave = normalizar_pix(texto) if texto else ""  # levanta PixError se nao for chave
        return self._chamar("salvar", {**self._identidade(), "sessao": self._sessao, "pix_chave": chave})

    def buscar_atual(self) -> dict | None:
        """Conferencia de fundo. Qualquer falha e silencio (None)."""
        if not self.pode_usar:
            return None
        try:
            return self._chamar("atual", self._identidade())
        except PagamentosError as erro:
            logger.info("Conferencia da chave Pix adiada: %s", erro)
            return None
        except Exception:  # noqa: BLE001 - conferencia de fundo nunca derruba o Hub
            logger.exception("Falha inesperada na conferencia da chave Pix")
            return None

    # --------------------------------------------- gravar (thread da tela) ---
    def aplicar_entrada(self, resposta: dict) -> Acesso:
        sessao = str(resposta.get("sessao") or "")
        if not sessao:
            raise PagamentosError("Resposta inesperada do servidor.", "servidor")
        self.guardar_assinado(resposta.get("assinado"))
        self._sessao = sessao
        self._acesso = Acesso(expira=self._relogio() + SESSAO_SEGUNDOS)
        return self._acesso

    def aplicar_pix(self, resposta: dict) -> str:
        self.guardar_assinado(resposta.get("assinado"), obrigatorio=True)
        return pix_confirmada(self.settings)

    def guardar_assinado(self, pacote: Any, obrigatorio: bool = False) -> bool:
        """Grava a chave Pix assinada. True se ela mudou.

        So entra no arquivo o que a assinatura confirma: resposta adulterada no
        caminho (ou servidor falso) nao chega ao balcao.
        """
        if _abrir(pacote) is None:
            if obrigatorio:
                raise PagamentosError("A resposta do servidor não confere. Nada foi alterado.",
                                      "assinatura")
            logger.warning("Chave Pix com assinatura invalida recebida: ignorada")
            return False
        antes = pix_confirmada(self.settings)
        self.settings.set(SECAO, "assinado", pacote)
        self.settings.save()
        return pix_confirmada(self.settings) != antes

    def salvar_formas(self, ocultas) -> tuple[str, ...]:
        if self.acesso is None:
            raise PagamentosError("O acesso a Pagamentos venceu. Entre de novo com um código.",
                                  "sessao_vencida")
        lista = [forma for forma in FORMAS if forma in set(ocultas or ())]
        if len(lista) == len(FORMAS):
            raise PagamentosError("Deixe pelo menos uma forma de pagamento aparecendo no balcão.",
                                  "formas")
        self.settings.set(SECAO, "formas_ocultas", lista)
        self.settings.save()
        return tuple(lista)

    # ------------------------------------------------------------------ interno
    def _identidade(self) -> dict:
        licenca = self._licenca()
        if not self.pode_usar:
            raise PagamentosError(
                "Ative a licença deste computador para usar a área de Pagamentos.", "sem_licenca")
        return {"chave": licenca.key, "maquina": licenca.machine,
                "computador": assinatura.computador_id()}

    def _chamar(self, rota: str, corpo: dict) -> dict:
        try:
            resposta = self.client.funcao(f"{FUNCAO}/{rota}", corpo)
        except SemConexao as erro:
            raise PagamentosError(SEM_INTERNET, "sem_internet") from erro
        except (FuncaoIndisponivel, SupabaseError) as erro:
            raise PagamentosError(
                "A proteção de pagamentos está indisponível agora. Tente de novo em instantes.",
                "indisponivel") from erro
        if not isinstance(resposta, dict):
            raise PagamentosError("Resposta inesperada do servidor.", "servidor")
        if not resposta.get("ok"):
            raise PagamentosError(
                str(resposta.get("mensagem") or "Não foi possível concluir agora."),
                str(resposta.get("erro") or "erro"))
        return resposta
