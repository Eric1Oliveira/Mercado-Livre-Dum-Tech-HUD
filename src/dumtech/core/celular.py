"""O Hub no celular: o resumo que vai para o telefone do dono.

O CONTRATO (o mesmo desenho de `indicadores` e `avisos`)
    Cada `module.py` pode expor

        def celular(paths) -> dict   # uma secao, montada com `secao(...)`

    e o Hub junta os aplicativos que a licenca liberou. O celular desenha
    qualquer secao com o mesmo codigo - cartoes (os numeros) e listas (o que
    precisa de atencao) - entao um modulo novo aparece no telefone sem mexer
    na pagina do celular.

O QUE VAI
    So o resumo do dia e listas curtas (as ultimas vendas, as ordens
    atrasadas...). Nunca o banco inteiro: o celular e para olhar, e quanto
    menos dado viaja, menos dado fica exposto.

QUANDO VAI
    Enquanto houver celular pareado (o servidor diz). Sem celular, o Hub nao
    manda nada.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from . import assinatura
from .loja import URL_PADRAO, url_base
from .supabase import SemConexao, SupabaseClient, SupabaseError

logger = logging.getLogger(__name__)

#: itens por lista: o celular mostra o que precisa de atencao, nao o arquivo
LIMITE_LISTA = 8
#: versao do formato do resumo (o celular entende esta e as anteriores)
FORMATO = 1


# ------------------------------------------------------------ montar secoes --
def cartao(rotulo: str, valor: str, detalhe: str = "", tom: str = "") -> dict:
    """Um numero grande. `tom`: "" | ok | aviso | perigo."""
    return {"rotulo": rotulo, "valor": valor, "detalhe": detalhe, "tom": tom}


def linha(texto: str, detalhe: str = "", valor: str = "", tom: str = "") -> dict:
    return {"texto": texto, "detalhe": detalhe, "valor": valor, "tom": tom}


def lista(titulo: str, linhas: list[dict], vazio: str = "") -> dict:
    return {"titulo": titulo, "linhas": linhas[:LIMITE_LISTA], "vazio": vazio}


def secao(app_id: str, titulo: str, cartoes: list[dict] | None = None,
          listas: list[dict] | None = None, peso: int = 0) -> dict:
    """A parte de um aplicativo na tela do celular."""
    return {"app": app_id.upper(), "titulo": titulo, "cartoes": cartoes or [],
            "listas": [item for item in (listas or []) if item], "peso": peso}


def coletar(modulo, paths) -> dict | None:
    """Pede a secao a um modulo, sem deixar ele derrubar o resto."""
    funcao = getattr(modulo, "celular", None)
    if not callable(funcao):
        return None
    try:
        resultado = funcao(paths)
    except Exception:  # noqa: BLE001 - modulo quebrado nao derruba o resumo
        logger.exception("Falha ao montar o resumo do celular de %s", getattr(modulo, "__name__", modulo))
        return None
    return resultado if isinstance(resultado, dict) else None


def montar(entradas, paths, empresa: str = "", versao: str = "") -> dict:
    """O resumo inteiro: uma secao por aplicativo liberado, dinheiro primeiro."""
    secoes = [s for s in (coletar(e.module, paths) for e in entradas) if s]
    secoes.sort(key=lambda s: -int(s.get("peso") or 0))
    return {
        "formato": FORMATO,
        "empresa": empresa,
        "versao_hub": versao,
        "gerado_em": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "secoes": secoes,
    }


def link_de_pareamento(codigo: str) -> str:
    """O que vai no QR. O codigo vai depois do # - nunca chega a servidor de site."""
    base = url_base()
    if not base.startswith("https://"):  # a copia local da loja nao abre no celular
        base = URL_PADRAO
    return f"{base.rstrip('/')}/celular/#p={codigo}"


# ----------------------------------------------------------------- servidor --
class CelularError(Exception):
    """Erro com mensagem pronta para a tela."""


#: o que o servidor responde -> o que o dono le
ERROS = {
    "licenca_invalida": "Esta licença não está ativa neste computador. Confira em Licença.",
    "muitas_tentativas": "Muitas tentativas seguidas. Espere alguns minutos e tente de novo.",
    "resumo_invalido": "O resumo ficou grande demais para o celular.",
}


class CelularService:
    """Conversa com o servidor: QR, aparelhos pareados e o resumo.

    Rede pura - chamar de `ui.tasks.executar`, nunca da thread da tela.
    """

    def __init__(self, licenca, client: SupabaseClient | None = None) -> None:
        #: funcao que devolve a licenca atual (muda quando o cliente ativa)
        self._licenca = licenca
        self.client = client or SupabaseClient()

    def _credenciais(self) -> dict:
        atual = self._licenca()
        if not atual.key or not atual.ativa:
            raise CelularError("Ative a sua licença para usar o Hub no celular.")
        return {"p_chave": atual.key, "p_maquina": atual.machine,
                "p_computador": assinatura.computador_id()}

    def _chamar(self, funcao: str, extras: dict | None = None) -> dict:
        try:
            resposta = self.client.rpc(funcao, {**self._credenciais(), **(extras or {})})
        except SemConexao as erro:
            raise CelularError("Sem internet agora. Conecte o computador e tente de novo.") from erro
        except SupabaseError as erro:
            raise CelularError(f"O servidor não respondeu ({erro}).") from erro
        if not isinstance(resposta, dict) or not resposta.get("ok"):
            erro = resposta.get("erro") if isinstance(resposta, dict) else ""
            raise CelularError(ERROS.get(erro, "Não foi possível falar com o servidor da DumTech."))
        return resposta

    def iniciar(self) -> dict:
        """Codigo novo para o QR: {"codigo", "expira_em", "link"}."""
        resposta = self._chamar("dumtech_celular_iniciar")
        return {**resposta, "link": link_de_pareamento(str(resposta["codigo"]))}

    def aparelhos(self) -> list[dict]:
        return list(self._chamar("dumtech_celular_aparelhos").get("aparelhos") or [])

    def revogar(self, aparelho_id: str) -> None:
        self._chamar("dumtech_celular_revogar", {"p_aparelho": aparelho_id})

    def publicar(self, resumo: dict[str, Any]) -> int:
        """Manda o resumo. Devolve quantos celulares estao pareados (0 = pare de mandar)."""
        return int(self._chamar("dumtech_celular_publicar", {"p_dados": resumo}).get("pareados") or 0)
