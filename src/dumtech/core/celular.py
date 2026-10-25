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

    No formato 2 a secao ganha o que transforma numero em resposta: o
    `destaque` (o numero que abre a tela, com periodos e grafico), `graficos`,
    `alertas` (o que precisa do dono hoje) e, nos cartoes e linhas, a
    `variacao` contra um periodo com nome, o `medidor` e a acao de WhatsApp.
    Tudo opcional: o celular antigo le `cartoes` e `listas` e ignora o resto.

QUANDO VAI
    Enquanto houver celular pareado (o servidor diz). Sem celular, o Hub nao
    manda nada.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from . import assinatura
from .loja import URL_PADRAO, url_base
from .supabase import SemConexao, SupabaseClient, SupabaseError

logger = logging.getLogger(__name__)

#: itens por lista: o celular mostra o que precisa de atencao, nao o arquivo
LIMITE_LISTA = 8
#: versao do formato do resumo (o celular entende esta e as anteriores)
FORMATO = 2

#: "Cartao de credito" e como o Hub grava; no celular a forma aparece escrita direito
NOMES_DE_FORMA = {
    "cartao de credito": "Cartão de crédito",
    "cartao de debito": "Cartão de débito",
    "nao informado": "Não informado",
}


def nome_da_forma(forma: str) -> str:
    return NOMES_DE_FORMA.get((forma or "").strip().lower(), forma or "Não informado")


#: o dia da semana no eixo do grafico (date.weekday(): segunda = 0)
DIAS_CURTOS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


def dia_passado(quando) -> str:
    """"sábado passado", "segunda passada" - o português concorda com o dia."""
    nome = DIAS[quando.weekday()]
    return f"{nome} {'passado' if quando.weekday() >= 5 else 'passada'}"


def data_curta(quando) -> str:
    """dd/mm - no celular o ano so atrapalha."""
    return f"{quando.day:02d}/{quando.month:02d}"


def _com(base: dict, **extras) -> dict:
    """A base de sempre + o que veio preenchido (o vazio nem viaja)."""
    base.update({chave: valor for chave, valor in extras.items() if valor not in (None, "", [], {})})
    return base


def _numero(valor) -> float | None:
    return None if valor is None else round(float(valor), 2)


# ------------------------------------------------------------ montar secoes --
def cartao(rotulo: str, valor: str, detalhe: str = "", tom: str = "", *,
           variacao: dict | None = None, medidor: dict | None = None,
           largo: bool = False, papel: str = "") -> dict:
    """Um numero. `tom`: "" | ok | aviso | perigo.

    `largo` ocupa a linha inteira; `papel="destaque"` marca o cartao que o
    celular novo ja mostra como destaque (o antigo continua mostrando).
    """
    return _com({"rotulo": rotulo, "valor": valor, "detalhe": detalhe, "tom": tom},
                variacao=variacao, medidor=medidor, largo=largo or None, papel=papel)


def linha(texto: str, detalhe: str = "", valor: str = "", tom: str = "", *,
          hora: str = "", estado: str = "", medidor: dict | None = None,
          acao: dict | None = None) -> dict:
    """Uma linha de lista. `hora` vira coluna a esquerda (linha do tempo) e
    `estado` ("passou" | "agora") diz onde ela esta no dia."""
    return _com({"texto": texto, "detalhe": detalhe, "valor": valor, "tom": tom},
                hora=hora, estado=estado, medidor=medidor, acao=acao)


def lista(titulo: str, linhas: list[dict], vazio: str = "") -> dict:
    return {"titulo": titulo, "linhas": linhas[:LIMITE_LISTA], "vazio": vazio}


def variacao(atual: float, base: float | None, comparado: str, bom: str = "sobe") -> dict | None:
    """Quanto mudou contra um periodo com nome ("+18%" vs. "sabado passado").

    `bom` diz para que lado e boa noticia: venda subir e bom, conta a pagar
    subir nao. Sem base (o periodo comparado nao teve nada) nao existe
    porcentagem honesta - devolve None e o celular mostra so o numero.
    """
    if base is None or float(base) <= 0:
        return None
    mudou = (float(atual) - float(base)) / float(base) * 100
    if abs(mudou) < 0.5:
        return {"texto": "0%", "direcao": "igual", "tom": "", "comparado": comparado}
    direcao = "sobe" if mudou > 0 else "desce"
    sinal = "+" if mudou > 0 else "−"
    return {"texto": f"{sinal}{min(abs(mudou), 999):.0f}%", "direcao": direcao,
            "tom": "ok" if direcao == bom else "perigo", "comparado": comparado}


def medidor(parte: float, todo: float, texto: str = "") -> dict | None:
    """Uma barra de progresso: quanto de `todo` ja e `parte` (0 a 1)."""
    if not todo or float(todo) <= 0:
        return None
    return _com({"fracao": round(max(0.0, min(float(parte) / float(todo), 1.0)), 4)}, texto=texto)


def whatsapp(telefone: str, mensagem: str, rotulo: str) -> dict | None:
    """Botao que abre a conversa no WhatsApp ja com a mensagem escrita.

    So numero brasileiro com DDD (10 ou 11 digitos, com ou sem o 55): o resto
    nao vira link - melhor sem botao do que um botao que abre conversa errada.
    """
    texto = (telefone or "").strip()
    digitos = re.sub(r"\D", "", texto)
    # "+1 415..." tem 11 digitos e passaria por celular de Bauru (DDD 14):
    # numero com + que nao e +55 e de fora, e o 55 na frente ligaria para outra pessoa
    if texto.startswith("+") and not digitos.startswith("55"):
        return None
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    if not (len(digitos) in (12, 13) and digitos.startswith("55")):
        return None
    return {"tipo": "whatsapp", "numero": digitos, "mensagem": mensagem, "rotulo": rotulo}


def alerta(texto: str, valor: str = "", tom: str = "aviso", detalhe: str = "") -> dict:
    """O que precisa do dono hoje. Escreva como tarefa: "Cobrar 2 contas atrasadas".

    `valor` e numero (vai na coluna da direita); `detalhe` e frase curta que
    vai embaixo, ao lado do nome do modulo."""
    return _com({"texto": texto, "valor": valor, "tom": tom}, detalhe=detalhe)


# ----------------------------------------------------------------- graficos --
def serie(nome: str, valores: list, destaque: bool = False) -> dict:
    """Uma linha do grafico. `None` no meio = ainda nao aconteceu (a linha para)."""
    return _com({"nome": nome, "valores": [_numero(v) for v in valores]}, destaque=destaque or None)


def colunas(titulo: str, rotulos: list[str], valores: list[float], formato: str = "moeda", *,
            destaque: int | None = None, dicas: list[str] | None = None) -> dict:
    """Uma coluna por periodo (o dia, a semana). `destaque`: a coluna de agora."""
    return _com({"tipo": "colunas", "titulo": titulo, "formato": formato, "rotulos": rotulos,
                 "valores": [_numero(v) or 0.0 for v in valores]},
                destaque=destaque, dicas=dicas)


def linhas(titulo: str, rotulos: list[str], series: list[dict], formato: str = "moeda", *,
           dicas: list[str] | None = None, zero: bool = False, agora: dict | None = None) -> dict:
    """Linhas no mesmo eixo (nunca dois eixos). `zero`: risca o zero quando o
    numero pode ficar negativo (o saldo previsto). `agora`: onde fica o
    presente entre duas marcas ({"posicao": 7.5, "valores": [...], "rotulo"})
    - a linha de hoje termina ali, e nao na hora cheia seguinte."""
    return _com({"tipo": "linhas", "titulo": titulo, "formato": formato, "rotulos": rotulos,
                 "series": series}, dicas=dicas, zero=zero or None, agora=agora)


def item(rotulo: str, valor: float, texto: str = "", detalhe: str = "") -> dict:
    return _com({"rotulo": rotulo, "valor": _numero(valor) or 0.0}, texto=texto, detalhe=detalhe)


def ranking(titulo: str, itens: list[dict], formato: str = "moeda", *,
            parte_do_todo: bool = False, vazio: str = "") -> dict:
    """Barras deitadas, da maior para a menor. `parte_do_todo`: cada barra e a
    fatia do total (e o celular mostra a porcentagem)."""
    return _com({"tipo": "ranking", "titulo": titulo, "formato": formato,
                 "itens": itens[:LIMITE_LISTA]}, parte_do_todo=parte_do_todo or None, vazio=vazio)


def etapas(titulo: str, itens: list[dict], vazio: str = "") -> dict:
    """Uma barra so, dividida em etapas que tem ordem (aguardando -> pronta)."""
    return _com({"tipo": "etapas", "titulo": titulo, "itens": itens}, vazio=vazio)


# ----------------------------------------------------------------- destaque --
def periodo(nome: str, rotulo: str, valor: str, numero: float | None = None, *,
            detalhe: str = "", variacao: dict | None = None, grafico: dict | None = None) -> dict:
    """Uma aba do destaque ("Hoje", "7 dias"...). `numero` deixa o celular
    animar quando o valor muda; `valor` e o texto pronto."""
    return _com({"nome": nome, "rotulo": rotulo, "valor": valor},
                numero=_numero(numero), detalhe=detalhe, variacao=variacao, grafico=grafico)


def destaque(periodos: list[dict], formato: str = "moeda", tom: str = "") -> dict:
    """O numero que abre a tela - ou a secao, quando outro modulo abre a tela."""
    return _com({"formato": formato, "periodos": periodos}, tom=tom)


def secao(app_id: str, titulo: str, cartoes: list[dict] | None = None,
          listas: list[dict] | None = None, peso: int = 0, *,
          destaque: dict | None = None, graficos: list[dict] | None = None,
          alertas: list[dict] | None = None) -> dict:
    """A parte de um aplicativo na tela do celular."""
    return _com({"app": app_id.upper(), "titulo": titulo, "cartoes": cartoes or [],
                 "listas": [item for item in (listas or []) if item], "peso": peso},
                destaque=destaque, graficos=[g for g in (graficos or []) if g],
                alertas=alertas)


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
