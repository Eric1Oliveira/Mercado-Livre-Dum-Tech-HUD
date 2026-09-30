"""Atualizar o Hub pelo proprio Hub: baixar, conferir e instalar.

POR QUE ESTE ARQUIVO E O MAIS DESCONFIADO DO PROJETO
    Aqui um programa baixa um executavel da internet e manda o Windows roda-lo.
    E o sonho de qualquer golpe. Entao nada e aceito por confianca:

    1. **assinatura** - o manifesto (versao + endereco + sha256) vem assinado
       pela DumTech (Ed25519, a mesma chave da licenca). Painel invadido, banco
       adulterado ou resposta trocada no caminho nao passam daqui;
    2. **endereco** - so `https` e so o dominio da loja (`endereco_confiavel`);
    3. **impressao digital** - depois de baixar, o arquivo e conferido byte a
       byte contra o sha256 assinado. Download pela metade, proxy que injeta
       coisa, disco com defeito: nada disso vira instalacao;
    4. **de onde executa** - o instalador roda da pasta do proprio programa
       (`%LOCALAPPDATA%\\DumTech Hub\\atualizacoes`), nunca de Downloads, onde
       qualquer outro programa poderia trocar o arquivo entre baixar e abrir.

COMO A ATUALIZACAO ACONTECE
    O Hub chama o instalador em silencio e fecha. O instalador troca os
    arquivos e abre o Hub de novo, ja atualizado (`/reabrir=1`, ver
    build/instalador.iss). Os dados do cliente ficam em `%APPDATA%` e nao sao
    tocados.

    Instalacao e por usuario, em `%LOCALAPPDATA%\\Programs`: nao pede
    administrador, nao mostra tela de UAC.

O CONTROLE E DA DUMTECH
    O servidor diz se a atualizacao pelo Hub esta liberada (`automatica`). Com
    ela desligada - ou sem sha256 publicado - o Hub apenas avisa e leva o
    cliente para a pagina de download.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import assinatura
from .loja import url_base
from .paths import get_paths
from .supabase import SupabaseClient, SupabaseError
from .versao import SECAO, endereco_confiavel, foi_dispensada, mais_nova

logger = logging.getLogger(__name__)

#: Edge Function que devolve o manifesto assinado
FUNCAO = "versao"

#: marca do documento assinado - separa de licenca e de chave Pix
USO = "atualizacao"

#: o que o Windows recebe: instala sem perguntar nada e abre o Hub de novo
ARGUMENTOS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/reabrir=1")

#: pedaco lido por vez (e o que move a barra de progresso)
PEDACO = 256 * 1024

#: instalador maior que isto e coisa errada - nem comeca a baixar
TAMANHO_MAXIMO = 300 * 1024 * 1024


class AtualizacaoError(Exception):
    """Erro com mensagem pronta para a tela."""

    def __init__(self, mensagem: str, codigo: str = "erro") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


@dataclass(frozen=True)
class Atualizacao:
    """O que a DumTech publicou - ja conferido."""

    versao: str
    url: str
    notas: str = ""
    sha256: str = ""
    obrigatoria: bool = False
    #: o botao "Baixar e instalar" aparece? (decisao da DumTech, no painel)
    automatica: bool = False
    tamanho: int = 0

    @property
    def tamanho_texto(self) -> str:
        if self.tamanho <= 0:
            return ""
        return f"{self.tamanho / (1024 * 1024):.1f} MB".replace(".", ",")


def motivo_da_recusa(pacote: Any) -> str:
    """Por que `abrir_manifesto` devolveu None - em portugues, para o log.

    Existe porque a mensagem generica ("sem assinatura valida") mandava o
    suporte investigar a chave Ed25519 quando o problema costuma ser outro: um
    Hub antigo, compilado com o endereco ANTIGO da loja, recusando em silencio
    a atualizacao que aponta para o endereco novo. A assinatura estava certa o
    tempo todo; o endereco e que nao batia.
    """
    if not isinstance(pacote, dict):
        return "o servidor nao mandou manifesto"
    dados = assinatura.abrir(pacote)
    if not dados:
        return "a assinatura da DumTech nao confere"
    if dados.get("uso") != USO:
        return f"o manifesto e de outro uso ({dados.get('uso')!r})"
    if not str(dados.get("versao") or ""):
        return "o manifesto veio sem numero de versao"
    bruta = str(dados.get("url") or "")
    if not endereco_confiavel(bruta):
        return (
            f"o endereco {bruta!r} nao e o desta instalacao "
            f"({url_base()!r}). Este Hub foi compilado com outro endereco de "
            "loja: instale a versao nova uma vez pelo site e o botao volta a "
            "funcionar sozinho."
        )
    return "motivo desconhecido"


def abrir_manifesto(pacote: Any) -> Atualizacao | None:
    """Confere a assinatura da DumTech e devolve o que ela publicou.

    Qualquer coisa fora do lugar (assinatura, uso, endereco, sha256) devolve
    None: o Hub trata como "nao ha atualizacao", nunca como "vai assim mesmo".
    """
    dados = assinatura.abrir(pacote) if isinstance(pacote, dict) else None
    if not dados or dados.get("uso") != USO:
        return None

    versao = str(dados.get("versao") or "")
    url = endereco_confiavel(str(dados.get("url") or ""))
    sha = str(dados.get("sha256") or "").lower()
    if not versao or not url:
        return None
    # sem impressao digital valida, o download existe mas nao se instala daqui
    automatica = bool(dados.get("automatica")) and len(sha) == 64 and all(
        c in "0123456789abcdef" for c in sha
    )
    return Atualizacao(
        versao=versao,
        url=url,
        notas=str(dados.get("notas") or ""),
        sha256=sha if automatica else "",
        obrigatoria=bool(dados.get("obrigatoria")),
        automatica=automatica,
        tamanho=int(dados.get("tamanho") or 0),
    )


def disponivel(settings, instalada: str) -> Atualizacao | None:
    """A atualizacao que vale para esta maquina - so do arquivo, sem internet."""
    aviso = abrir_manifesto(settings.get(SECAO, "assinado"))
    if aviso is None or not mais_nova(aviso.versao, instalada):
        return None
    return aviso


def para_avisar(settings, instalada: str) -> Atualizacao | None:
    """O que a tela mostra: o mesmo, menos o que o cliente ja dispensou.

    Atualizacao obrigatoria (correcao de seguranca) nao se dispensa.
    """
    aviso = disponivel(settings, instalada)
    if aviso is None:
        return None
    if not aviso.obrigatoria and foi_dispensada(settings, aviso.versao):
        return None
    return aviso


def pasta_de_download(paths=None) -> Path:
    """Dentro da pasta do programa: fora do alcance de outros programas."""
    destino = (paths or get_paths()).root / "atualizacoes"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


class AtualizacaoService:
    """Busca o manifesto assinado, baixa o instalador e o executa."""

    def __init__(
        self,
        settings,
        instalada: str,
        client: SupabaseClient | None = None,
        paths=None,
    ) -> None:
        self.settings = settings
        self.instalada = instalada
        self.client = client or SupabaseClient()
        self.paths = paths

    # ------------------------------------------------------ rede (2o plano) --
    def buscar(self, chave: str = "", maquina: str = "") -> dict | None:
        """Pergunta ao servidor. Qualquer falha e silencio (None)."""
        corpo = {"chave": chave or "", "maquina": maquina or "", "versao": self.instalada}
        try:
            resposta = self.client.funcao(FUNCAO, corpo)
        except SupabaseError as erro:
            logger.info("Versao nao conferida: %s", erro)
            return None
        except Exception:  # noqa: BLE001 - conferir versao nunca derruba o Hub
            logger.exception("Falha inesperada ao conferir a versao")
            return None
        return resposta if isinstance(resposta, dict) and resposta.get("ok") else None

    # --------------------------------------------- gravar (thread da tela) ---
    def guardar(self, resposta: dict | None) -> Atualizacao | None:
        """Grava o manifesto ASSINADO. O que nao confere nao entra no arquivo."""
        if not resposta:
            return None
        pacote = resposta.get("assinado")
        if abrir_manifesto(pacote) is None:
            logger.warning("Atualizacao ignorada: %s", motivo_da_recusa(pacote))
            return None
        self.settings.set(SECAO, "assinado", pacote)
        self.settings.save()
        return disponivel(self.settings, self.instalada)

    # ------------------------------------------------------------ o download --
    def baixar(
        self,
        aviso: Atualizacao,
        progresso: Callable[[int, int], None] | None = None,
        parar: Callable[[], bool] | None = None,
    ) -> Path:
        """Baixa e confere. Devolve o caminho do instalador pronto para rodar."""
        if not aviso.automatica or not aviso.sha256:
            raise AtualizacaoError(
                "Esta atualizacao precisa ser baixada no site.", "sem_assinatura")
        if not endereco_confiavel(aviso.url):
            raise AtualizacaoError("Endereco de atualizacao invalido.", "endereco")

        destino = pasta_de_download(self.paths) / f"DumTech-Hub-Setup-{aviso.versao}.exe"
        if destino.exists() and self._conferir(destino) == aviso.sha256:
            return destino          # ja baixado antes (e intacto)

        conta = hashlib.sha256()
        baixado = 0
        temporario = None
        try:
            pedido = urllib.request.Request(aviso.url, headers={"User-Agent": "DumTechHub/atualizacao"})
            with urllib.request.urlopen(pedido, timeout=30) as resposta:
                total = int(resposta.headers.get("Content-Length") or aviso.tamanho or 0)
                if total and total > TAMANHO_MAXIMO:
                    raise AtualizacaoError("O arquivo da atualizacao e grande demais.", "tamanho")
                with tempfile.NamedTemporaryFile(
                    dir=destino.parent, prefix="baixando-", suffix=".part", delete=False
                ) as arquivo:
                    temporario = Path(arquivo.name)
                    while True:
                        if parar is not None and parar():
                            raise AtualizacaoError("Download cancelado.", "cancelado")
                        pedaco = resposta.read(PEDACO)
                        if not pedaco:
                            break
                        baixado += len(pedaco)
                        if baixado > TAMANHO_MAXIMO:
                            raise AtualizacaoError("O arquivo da atualizacao e grande demais.", "tamanho")
                        arquivo.write(pedaco)
                        conta.update(pedaco)
                        if progresso is not None:
                            progresso(baixado, total)
        except AtualizacaoError:
            if temporario is not None:
                temporario.unlink(missing_ok=True)
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as erro:
            if temporario is not None:
                temporario.unlink(missing_ok=True)
            raise AtualizacaoError(
                "Nao foi possivel baixar a atualizacao. Confira a internet e tente de novo.",
                "download") from erro

        if conta.hexdigest() != aviso.sha256:
            temporario.unlink(missing_ok=True)
            raise AtualizacaoError(
                "O arquivo baixado nao e o oficial - nada foi instalado.",
                "impressao_digital")

        destino.unlink(missing_ok=True)
        temporario.replace(destino)
        return destino

    # ------------------------------------------------------------ instalar ----
    def instalar(self, instalador: Path, aviso: Atualizacao | None = None) -> None:
        """Roda o instalador em silencio. Quem chama fecha o Hub logo depois.

        Confere a impressao digital DE NOVO, imediatamente antes de executar: o
        arquivo pode ter sido trocado entre o download e este momento.
        """
        instalador = Path(instalador)
        if not instalador.is_file():
            raise AtualizacaoError("O instalador baixado sumiu.", "sumiu")
        if instalador.parent != pasta_de_download(self.paths):
            raise AtualizacaoError("Instalador fora da pasta do programa.", "lugar")
        if aviso is not None and aviso.sha256 and self._conferir(instalador) != aviso.sha256:
            instalador.unlink(missing_ok=True)
            raise AtualizacaoError(
                "O instalador foi alterado depois do download - nada foi executado.",
                "impressao_digital")

        try:
            subprocess.Popen(
                [str(instalador), *ARGUMENTOS],
                close_fds=True,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except OSError as erro:
            raise AtualizacaoError(
                f"O Windows nao deixou abrir o instalador: {erro}", "windows") from erro

    def limpar(self, manter: str = "") -> None:
        """Apaga instaladores velhos (e restos de download interrompido)."""
        try:
            pasta = pasta_de_download(self.paths)
        except OSError:
            return
        for arquivo in pasta.glob("*"):
            if arquivo.name == manter:
                continue
            try:
                arquivo.unlink()
            except OSError:
                continue

    @staticmethod
    def _conferir(arquivo: Path) -> str:
        conta = hashlib.sha256()
        with open(arquivo, "rb") as aberto:
            for pedaco in iter(lambda: aberto.read(PEDACO), b""):
                conta.update(pedaco)
        return conta.hexdigest()


def pode_atualizar_aqui() -> bool:
    """So o programa instalado se atualiza sozinho (em desenvolvimento, nao)."""
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"
