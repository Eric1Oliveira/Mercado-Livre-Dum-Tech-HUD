"""Ofertas e recados da DumTech que aparecem no Inicio do Hub.

Vem do servidor (``dumtech_comunicados``) e ficam guardados em
``config/comunicados.json``. A regra que desenha este modulo:

* **a tela sempre le o arquivo**, nunca a internet - ela pinta na hora e
  continua igual offline;
* a busca acontece em segundo plano, **no maximo uma vez por hora**;
* falha de rede nao apaga o que ja estava guardado e nao aparece para o
  cliente: uma oferta que nao chegou nao e um problema dele.

O servidor ja devolve a lista filtrada: oferta de um produto que o cliente tem
nao chega aqui.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .paths import get_paths
from .supabase import SupabaseClient, SupabaseError

logger = logging.getLogger(__name__)

#: arquivo guardado na pasta de configuracao do cliente
ARQUIVO = "comunicados.json"

#: funcao do servidor
FUNCAO = "dumtech_comunicados"

#: De quanto em quanto tempo vale a pena perguntar de novo. O relogio de rede
#: do Hub passa a cada 15 min, entao na pratica um anuncio novo aparece nesse
#: prazo - e na hora para quem abre o Hub ou volta para ele. E uma chamada
#: pequena; o painel promete "em ate 15 minutos" com base neste valor.
INTERVALO = timedelta(minutes=10)

#: quantos cabem na tela sem virar mural
MAXIMO = 3

#: secao das preferencias onde ficam os anuncios ja mostrados em pop-up
SECAO = "comunicados"

#: quantos ids guardar (o suficiente para nao repetir; nao e historico)
LEMBRAR = 50


def link_seguro(link) -> str:
    """So endereco https passa; o resto vira "sem link" (abre a loja padrao).

    O link vem do servidor e e aberto no computador do cliente. Um `file:///`,
    um caminho de rede (`\\\\servidor\\x.exe`) ou `javascript:` ali executaria
    coisa na maquina dele - entao o Hub nao confia nem no proprio servidor.
    """
    texto = str(link or "").strip()
    if not re.fullmatch(r"https://[^\s\\]+", texto, flags=re.IGNORECASE):
        return ""
    return texto


@dataclass(frozen=True)
class Comunicado:
    """Uma oferta ou recado."""

    id: str
    titulo: str
    texto: str = ""
    #: etiqueta curta: "Oferta", "Novidade"
    rotulo: str = ""
    #: endereco proprio; vazio = a loja padrao do Hub
    link: str = ""

    @classmethod
    def de_dict(cls, dados: dict) -> "Comunicado":
        return cls(
            id=str(dados.get("id") or ""),
            titulo=str(dados.get("titulo") or "").strip(),
            texto=str(dados.get("texto") or "").strip(),
            rotulo=str(dados.get("rotulo") or "").strip(),
            link=link_seguro(dados.get("link")),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "titulo": self.titulo, "texto": self.texto,
            "rotulo": self.rotulo, "link": self.link,
        }


# =========================================================== o pop-up =======
# O pop-up e o UNICO canal de anuncio no Hub, e aparece uma vez por anuncio.
# Quem ja viu nao e interrompido de novo - anuncio que repete vira estorvo. O
# Inicio nao tem bloco de oferta: aquela tela e do trabalho do cliente.
def vistos(settings) -> list[str]:
    valor = settings.get(SECAO, "vistos", []) or []
    return [str(i) for i in valor] if isinstance(valor, list) else []


def marcar_visto(settings, id_anuncio: str) -> None:
    lista = [i for i in vistos(settings) if i != id_anuncio]
    lista.append(str(id_anuncio))
    settings.set(SECAO, "vistos", lista[-LEMBRAR:])
    settings.save()


def para_anunciar(comunicados, settings) -> "Comunicado | None":
    """O primeiro anuncio que esta pessoa ainda nao viu em pop-up."""
    ja = set(vistos(settings))
    for item in comunicados:
        if item.id and item.id not in ja:
            return item
    return None


class ComunicadosService:
    """Le o arquivo guardado e, de vez em quando, pergunta ao servidor."""

    def __init__(
        self,
        paths=None,
        client: SupabaseClient | None = None,
        arquivo: Path | None = None,
    ) -> None:
        self.arquivo = Path(arquivo) if arquivo else (paths or get_paths()).config_dir / ARQUIVO
        self.client = client or SupabaseClient()

    # ------------------------------------------------------------------ leitura
    def listar(self, maximo: int = MAXIMO) -> list[Comunicado]:
        """O que a tela mostra: sempre do arquivo, nunca da internet."""
        guardados = self._ler().get("comunicados") or []
        comunicados = [Comunicado.de_dict(c) for c in guardados if isinstance(c, dict)]
        return [c for c in comunicados if c.titulo][:maximo]

    @property
    def buscado_em(self) -> datetime | None:
        marca = self._ler().get("buscado_em")
        try:
            return datetime.fromisoformat(str(marca)) if marca else None
        except ValueError:
            return None

    def precisa_atualizar(self) -> bool:
        quando = self.buscado_em
        if quando is None:
            return True
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - quando >= INTERVALO

    # ------------------------------------------------------------------ escrita
    def atualizar(self, chave: str = "") -> list[Comunicado]:
        """Pergunta ao servidor e guarda. Nunca levanta erro de rede.

        Falhou? O arquivo antigo continua valendo e a marca de tempo nao e
        tocada - na proxima abertura tentamos de novo.
        """
        try:
            resposta = self.client.rpc(FUNCAO, {"p_chave": chave or ""})
        except SupabaseError as erro:
            logger.info("Ofertas nao atualizadas: %s", erro)
            return self.listar()
        except Exception:  # noqa: BLE001 - oferta nenhuma derruba o Hub
            logger.exception("Falha inesperada ao buscar as ofertas")
            return self.listar()

        if not isinstance(resposta, dict) or not resposta.get("ok"):
            logger.info("O servidor nao mandou ofertas: %s", resposta)
            return self.listar()

        recebidos = resposta.get("comunicados")
        if not isinstance(recebidos, list):
            recebidos = []

        self._gravar({
            "buscado_em": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "comunicados": [
                Comunicado.de_dict(c).to_dict() for c in recebidos if isinstance(c, dict)
            ],
        })
        return self.listar()

    def limpar(self) -> None:
        """Usado quando a licenca sai do computador: as ofertas eram dela."""
        self.arquivo.unlink(missing_ok=True)

    # ------------------------------------------------------------------ interno
    def _ler(self) -> dict:
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return dados if isinstance(dados, dict) else {}

    def _gravar(self, dados: dict) -> None:
        try:
            self.arquivo.parent.mkdir(parents=True, exist_ok=True)
            self.arquivo.write_text(
                json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            logger.exception("Nao foi possivel guardar as ofertas")
