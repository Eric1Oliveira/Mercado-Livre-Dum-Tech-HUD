"""O caminho do Hub para a loja DumTech (a pagina de vendas).

O botao "Adquirir novo produto" abre o navegador. Para a pagina ja saber quem
chegou, o Hub pede ao servidor um **codigo de 15 minutos** e o leva na URL:

    https://.../comprar?t=8f14e45fceea167a5a36dedd4bea2543

A pagina troca esse codigo por nome, e-mail e os produtos que o cliente ja tem -
assim ela nao pede dados de novo nem oferece o que ele ja comprou. O codigo e de
uso unico e nao serve para mais nada: nenhum dado do cliente viaja na URL.

Sem internet (ou quando o servidor recusa), o link sai sem codigo, apenas
marcando de onde veio. A loja abre do mesmo jeito - so pede os dados.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .supabase import SupabaseClient, SupabaseError

logger = logging.getLogger(__name__)

#: Endereco da loja na internet (dominio proprio, hospedado na HostGator).
#: Vazio = o proprio Hub serve a copia da landing page que acompanha o
#: programa. Trocou de endereco? E so aqui (e recompilar).
#:
#: SEMPRE sem "www": e este host que `core/versao.py` exige no endereco de
#: atualizacao, e que a Edge Function `checkout` usa no CORS. O .htaccess da
#: loja redireciona www -> raiz justamente para os tres combinarem.
URL_PADRAO = "https://dumtechsolution.com"

#: onde o cliente pede ajuda e le o passo a passo (tela Sobre do Hub)
WHATSAPP_SUPORTE = "5511978042160"
URL_GUIA = "https://dumtechsolution.com/guia/"

#: permite apontar para outro endereco sem recompilar (homologacao, testes)
ENV_URL = "DUMTECH_URL_LOJA"

#: funcao do servidor que gera o codigo curto
FUNCAO_TOKEN = "dumtech_token_compra"


def pasta_da_landing() -> Path | None:
    """A landing page que acompanha o programa, em desenvolvimento ou no .exe."""
    candidatos = [
        Path(getattr(sys, "_MEIPASS", "")) / "landingpage",      # dentro do .exe
        Path(sys.argv[0]).resolve().parent / "landingpage",      # ao lado do .exe
        Path(__file__).resolve().parents[3] / "landingpage",     # repositorio
    ]
    for caminho in candidatos:
        try:
            if (caminho / "index.html").is_file():
                return caminho
        except OSError:  # caminho invalido (ex.: _MEIPASS vazio)
            continue
    return None


@lru_cache(maxsize=1)
def endereco_local() -> str:
    """Serve a landing page em 127.0.0.1 enquanto o Hub estiver aberto.

    Abrir o `index.html` direto (`file://`) NAO funciona: o navegador recusa
    modulos ES vindos de arquivo e a pagina abre em branco. Um servidor de
    tres linhas resolve - sem dominio, sem instalar nada, e funcionando offline.

    Devolve vazio quando a pasta nao veio junto: ai o botao simplesmente nao
    abre nada, em vez de abrir uma pagina quebrada.
    """
    pasta = pasta_da_landing()
    if pasta is None:
        logger.info("A landing page nao acompanha esta instalacao.")
        return ""

    class Entregador(SimpleHTTPRequestHandler):
        # O tipo do arquivo vem do REGISTRO do Windows, e ha computadores com o
        # `.js` registrado como text/plain: o navegador recusa modulo ES com esse
        # tipo e a loja abre em branco. Aqui o tipo e fixo, nao do registro.
        extensions_map = {
            **SimpleHTTPRequestHandler.extensions_map,
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".mjs": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".pdf": "application/pdf",
        }

        def guess_type(self, path) -> str:  # noqa: D401 - assinatura do http.server
            extensao = os.path.splitext(str(path))[1].lower()
            return self.extensions_map.get(extensao) or super().guess_type(path)

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, directory=str(pasta), **kwargs)

        def log_message(self, *args) -> None:  # o Hub nao e um servidor de verdade
            pass

    try:
        servidor = ThreadingHTTPServer(("127.0.0.1", 0), Entregador)
    except OSError:
        logger.exception("Nao foi possivel abrir a loja local")
        return ""

    threading.Thread(
        target=servidor.serve_forever, daemon=True, name="loja-dumtech"
    ).start()
    endereco = f"http://127.0.0.1:{servidor.server_port}"
    logger.info("Loja local em %s (%s)", endereco, pasta)
    return endereco


def url_base() -> str:
    """O endereco da loja: o configurado, ou a copia local que vem no programa."""
    endereco = (os.environ.get(ENV_URL) or URL_PADRAO).strip().rstrip("/")
    return endereco or endereco_local()


def url_compra(token: str = "", produtos: tuple[str, ...] = (), marcar: tuple[str, ...] = ()) -> str:
    """A URL que o navegador vai abrir.

    Com codigo, ele basta. Sem codigo, a loja pelo menos sabe que a visita veio
    do Hub e o que a pessoa ja tem, para nao oferecer o mesmo de novo.
    `marcar` abre a loja com esses modulos ja no carrinho (o "Comprar" de
    dentro de um modulo em teste gratis).
    """
    base = url_base()
    if not base:
        return ""  # sem loja configurada e sem copia local: nada a abrir
    if base.count("/") < 3:
        base += "/"  # "http://127.0.0.1:5173" nao pode virar "...:5173?t=..."

    # `kit` e o parametro que a loja ja entende (?kit=estoque,vendas)
    marcados = ",".join(sorted({str(m).strip().lower() for m in marcar if str(m).strip()}))
    if token:
        return f"{base}?{urlencode({'t': token, **({'kit': marcados} if marcados else {})})}"

    parametros = {"origem": "hub"}
    if marcados:
        parametros["kit"] = marcados
    comprados = ",".join(sorted(p for p in produtos if p))
    if comprados:
        parametros["tem"] = comprados
    return f"{base}?{urlencode(parametros)}"


def e_da_loja(link: str) -> bool:
    """Este endereco e a NOSSA loja?

    So a nossa: o codigo que identifica o cliente nunca pode sair para o site
    de outra pessoa - nem por um anuncio cadastrado errado no painel.
    """
    base = url_base()
    if not link or not base:
        return False
    try:
        alvo, casa = urlparse(link), urlparse(base)
    except ValueError:
        return False
    if alvo.scheme.lower() not in ("http", "https"):
        return False
    return (alvo.hostname or "").lower() == (casa.hostname or "").lower() and alvo.port == casa.port


def com_token(link: str, token: str) -> str:
    """Poe o codigo de 15 minutos no link do anuncio, mantendo o resto.

    Endereco de fora (ou sem codigo) volta do jeito que veio.
    """
    if not link or not token or not e_da_loja(link):
        return link
    partes = urlparse(link)
    consulta = [(c, v) for c, v in parse_qsl(partes.query, keep_blank_values=True) if c != "t"]
    consulta.append(("t", token))
    return urlunparse(partes._replace(query=urlencode(consulta)))


class LojaService:
    """Monta o link da loja, com codigo quando for possivel."""

    def __init__(self, client: SupabaseClient | None = None) -> None:
        self.client = client or SupabaseClient()

    def token(
        self,
        chave: str = "",
        maquina: str = "",
        nome: str = "",
        email: str = "",
    ) -> str:
        """O codigo de 15 minutos. Devolve vazio quando nao for possivel."""
        try:
            resposta = self.client.rpc(
                FUNCAO_TOKEN,
                {
                    "p_chave": chave or "",
                    "p_maquina": maquina or "",
                    "p_nome": nome or "",
                    "p_email": email or "",
                },
            )
        except SupabaseError as erro:
            logger.info("Loja aberta sem codigo: %s", erro)
            return ""
        except Exception:  # noqa: BLE001 - abrir a loja nao pode derrubar o Hub
            logger.exception("Falha inesperada ao pedir o codigo da loja")
            return ""

        if isinstance(resposta, dict) and resposta.get("ok"):
            return str(resposta.get("token") or "")
        logger.info("O servidor nao deu codigo para a loja: %s", resposta)
        return ""

    def link_do_anuncio(self, link: str, licenca=None, nome: str = "", email: str = "") -> str:
        """O link do anuncio, com o codigo quando ele aponta para a nossa loja.

        Sem codigo (sem internet, servidor fora) o anuncio abre do mesmo jeito -
        so nao reconhece quem chegou.
        """
        if not link:
            return self.link(licenca, nome, email)
        if not e_da_loja(link):
            return link
        return com_token(link, self._token_de(licenca, nome, email))

    def link(self, licenca=None, nome: str = "", email: str = "", marcar: tuple[str, ...] = ()) -> str:
        """A URL pronta para abrir no navegador.

        Quem tem licenca ativa se identifica pela chave e pelo computador ja
        ativado - a prova que o servidor reconhece. Quem ainda nao comprou se
        identifica pelo nome e pelo e-mail que ele mesmo informou no primeiro
        acesso.
        """
        produtos: tuple[str, ...] = ()
        if licenca is not None and getattr(licenca, "ativa", False) and licenca.key:
            produtos = tuple(licenca.entitlements)
        return url_compra(self._token_de(licenca, nome, email), produtos, marcar)

    def _token_de(self, licenca=None, nome: str = "", email: str = "") -> str:
        """Quem tem licenca se identifica por ela; quem nao tem, pelo e-mail."""
        token = ""
        if licenca is not None and getattr(licenca, "ativa", False) and licenca.key:
            token = self.token(chave=licenca.key, maquina=licenca.machine)
        if not token and email:
            token = self.token(nome=nome, email=email)
        return token
