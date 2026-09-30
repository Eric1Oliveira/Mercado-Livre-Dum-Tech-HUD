"""Licenca da plataforma: quais aplicativos este computador pode abrir.

COMO FUNCIONA
-------------
1. o cliente compra um ou mais aplicativos e recebe uma chave XXXX-XXXX-XXXX-XXXX;
2. na tela "Licenca" do Hub ele digita a chave e clica em Ativar
   -> UNICO momento em que a internet e necessaria;
3. o Supabase confere a chave (existe? ativa? no prazo? tem vaga de computador?)
   e devolve a lista de aplicativos comprados;
4. o Hub grava tudo em ``config/license.json`` e, a partir dai, funciona OFFLINE;
5. quando o cliente compra outro aplicativo, o botao "Verificar licenca"
   reconsulta e o novo aplicativo aparece - depois disso, offline de novo;
6. com internet, o Hub tambem confere sozinho a cada ``INTERVALO_CONFERENCIA`` (1 h)
   (`LicenseService.conferir`): modulo comprado aparece, e licenca suspensa,
   cancelada, vencida ou computador desligado no painel param de abrir.
   Sem internet nada muda - a conferencia fica para a proxima vez;
7. a conferencia devolve a licenca ASSINADA pela DumTech (Edge Function
   ``licenca-assinada``, ver `core/assinatura.py`): ao carregar o arquivo, o
   Hub confere a assinatura, o computador e o prazo offline. Editar a lista de
   modulos ou copiar o arquivo para outro computador nao libera nada.

Nenhum aplicativo consulta o Supabase para funcionar no dia a dia: eles so olham
para o arquivo local.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import logging
import os
import re
import socket
import sys
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from . import assinatura
from .paths import get_paths
from .supabase import SemConexao, SupabaseClient, SupabaseError

logger = logging.getLogger(__name__)

#: Formato da chave entregue ao cliente: XXXX-XXXX-XXXX-XXXX
KEY_PATTERN = re.compile(r"^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$")

#: Modo de desenvolvimento: com DUMTECH_LICENCA_LOCAL=1 o Hub cria uma licenca
#: local liberando tudo, sem consultar a internet (usado pelos testes tambem).
ENV_LICENCA_LOCAL = "DUMTECH_LICENCA_LOCAL"

#: Aplicativos liberados na licenca local de desenvolvimento.
DEFAULT_ENTITLEMENTS: tuple[str, ...] = (
    "estoque",
    "clientes",
    "financeiro",
    "orcamentos",
    "vendas",
    "ordens",
    "agenda",
)

LOCAL_KEY = "LOCAL-0000-0000-0001"

ORIGEM_LOCAL = "local"
ORIGEM_SUPABASE = "supabase"
ORIGEM_VAZIA = "nenhuma"

#: De quanto em quanto tempo o Hub confere a licenca sozinho (quando ha internet).
#: E uma chamada pequena; o painel promete "em ate 1 hora" com base neste valor.
INTERVALO_CONFERENCIA = timedelta(hours=1)

#: Respostas do servidor que querem dizer "esta licenca nao vale mais AQUI".
#: Qualquer outra falha (sem internet, servidor fora, limite de tentativas)
#: deixa tudo como estava.
#:
#: `outro_computador`: a licenca esta presa a outra identidade de Windows (o
#: cliente reinstalou o sistema, ou alguem copiou o license.json). A saida esta
#: na propria mensagem do servidor: ativar a chave de novo, aqui - e a tela de
#: Licenca mostra a chave para isso.
RECUSAS_DEFINITIVAS = frozenset({"inativa", "expirada", "nao_encontrada",
                                 "maquina_nao_ativada", "outro_computador"})

#: license.json SEM assinatura nao libera nada (ligado em 13/09/2026, antes das
#: primeiras vendas). A Edge Function `licenca-assinada` esta publicada: a
#: assinatura chega junto com a ativacao e em cada conferencia. Um Hub que tinha
#: licenca antiga precisa abrir com internet uma vez para receber a assinatura.
ASSINATURA_OBRIGATORIA = True

#: bloqueios calculados na hora de carregar (nao vem do servidor): a proxima
#: conferencia com internet resolve, entao ela nao espera o intervalo normal
BLOQUEIOS_DE_CONFERENCIA = frozenset({"sem_assinatura", "conferencia_vencida"})


class LicenseError(Exception):
    """Erro de licenca com mensagem pronta para mostrar ao cliente."""

    def __init__(self, mensagem: str, codigo: str = "erro") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


class SemInternet(LicenseError):
    """A operacao precisava de internet e nao conseguiu."""

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem, "sem_internet")


def _nome_do_computador() -> str:
    """O mesmo valor de `platform.node()`, sem o custo dele.

    No CPython, `platform.node()` devolve `socket.gethostname()` - mas antes
    monta o `uname()` inteiro, e no Windows isso abre um processo `cmd /c ver`
    (~35-55 ms na abertura do programa). O valor precisa ser o MESMO de
    sempre: ele entra no identificador que a licenca ativada reconhece.
    """
    try:
        return socket.gethostname()
    except OSError:
        return ""  # o que `platform.node()` devolveria


def machine_id() -> str:
    """Identificador estavel do computador, calculado sem acessar a internet."""
    raw = f"{_nome_do_computador()}|{getpass.getuser()}|{uuid.getnode()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    return "-".join(digest[i : i + 4] for i in range(0, 16, 4))


def machine_label() -> str:
    """Nome amigavel do computador, so para o cliente se reconhecer na lista."""
    try:
        return f"{_nome_do_computador()} ({getpass.getuser()})"
    except Exception:  # noqa: BLE001
        return _nome_do_computador() or "computador"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_key(key: str) -> str:
    """Aceita a chave digitada de qualquer jeito e devolve XXXX-XXXX-XXXX-XXXX."""
    limpo = re.sub(r"[^A-Za-z0-9]", "", key or "").upper()[:16]
    return "-".join(limpo[i : i + 4] for i in range(0, len(limpo), 4))


def is_valid_key_format(key: str) -> bool:
    return bool(KEY_PATTERN.match((key or "").strip().upper()))


@dataclass(frozen=True)
class License:
    """Licenca conhecida por este computador."""

    key: str
    customer: str
    entitlements: tuple[str, ...]
    machine: str
    activated_at: str
    last_check: str | None = None
    expires_at: str | None = None
    source: str = ORIGEM_LOCAL
    max_machines: int = 1
    used_machines: int = 1
    #: vitalicia, assinatura ou teste (vazio em servidor antigo)
    tipo: str = ""
    extras: dict = field(default_factory=dict)
    #: o pacote assinado pela DumTech ({"v", "kid", "licenca", "assinatura"})
    assinado: dict = field(default_factory=dict)
    #: teste gratis: {"agenda": "2026-09-29T12:00:00+00:00"} - modulo -> fim.
    #: So vale o que veio assinado (ver `_conferir_assinatura`).
    testes: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ estados
    @classmethod
    def vazia(cls, machine: str | None = None) -> "License":
        """Instalacao sem licenca: nenhum aplicativo liberado."""
        return cls(
            key="",
            customer="",
            entitlements=(),
            machine=machine or machine_id(),
            activated_at="",
            source=ORIGEM_VAZIA,
            max_machines=0,
            used_machines=0,
        )

    @property
    def ativa(self) -> bool:
        return bool(self.key) and self.source != ORIGEM_VAZIA and not self.is_expired

    @property
    def is_local(self) -> bool:
        return self.source == ORIGEM_LOCAL

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            prazo = datetime.fromisoformat(str(self.expires_at))
        except ValueError:
            return False
        if prazo.tzinfo is None:
            prazo = prazo.replace(tzinfo=timezone.utc)
        return prazo < datetime.now(timezone.utc)

    def allows(self, app_id: str) -> bool:
        comprado = app_id in self.entitlements or self.teste_ativo(app_id)
        return comprado and not self.is_expired

    # ------------------------------------------------------------- teste gratis
    def fim_do_teste(self, app_id: str) -> datetime | None:
        fim = self.testes.get(app_id)
        if not fim:
            return None
        try:
            momento = datetime.fromisoformat(str(fim).replace("Z", "+00:00"))
        except ValueError:
            return None
        return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)

    def teste_ativo(self, app_id: str) -> bool:
        """Em teste gratis agora? (comprado nao conta como teste)"""
        if app_id in self.entitlements:
            return False
        fim = self.fim_do_teste(app_id)
        return fim is not None and fim > datetime.now(timezone.utc)

    def teste_acabou(self, app_id: str) -> bool:
        fim = self.fim_do_teste(app_id)
        return (fim is not None and fim <= datetime.now(timezone.utc)
                and app_id not in self.entitlements)

    def dias_de_teste(self, app_id: str) -> int:
        """Quantos dias ainda restam (arredondado para cima; 0 = acabou)."""
        fim = self.fim_do_teste(app_id)
        if fim is None:
            return 0
        segundos = (fim - datetime.now(timezone.utc)).total_seconds()
        return max(int(-(-segundos // 86400)), 0)

    @property
    def em_teste(self) -> tuple[str, ...]:
        return tuple(sorted(a for a in self.testes if self.teste_ativo(a)))

    @property
    def bloqueio(self) -> str:
        """Por que o servidor recusou esta licenca (vazio = nao esta bloqueada)."""
        return str(self.extras.get("bloqueio") or "")

    # -------------------------------------------------------------- serializacao
    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "customer": self.customer,
            "entitlements": list(self.entitlements),
            "machine": self.machine,
            "activated_at": self.activated_at,
            "last_check": self.last_check,
            "expires_at": self.expires_at,
            "source": self.source,
            "max_machines": self.max_machines,
            "used_machines": self.used_machines,
            "tipo": self.tipo,
            "extras": dict(self.extras),
            "assinado": dict(self.assinado),
            "testes": dict(self.testes),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "License":
        return cls(
            key=str(data.get("key", "")),
            customer=str(data.get("customer", "")),
            entitlements=tuple(data.get("entitlements") or ()),
            machine=str(data.get("machine", machine_id())),
            activated_at=str(data.get("activated_at") or ""),
            last_check=data.get("last_check"),
            expires_at=data.get("expires_at"),
            source=str(data.get("source", ORIGEM_LOCAL)),
            max_machines=int(data.get("max_machines") or 1),
            used_machines=int(data.get("used_machines") or 1),
            tipo=str(data.get("tipo") or ""),
            extras=dict(data.get("extras") or {}),
            assinado=dict(data.get("assinado") or {}) if isinstance(data.get("assinado"), dict) else {},
            testes=_testes(data.get("testes")),
        )


# ================================================================== gateways ==
class LicenseGateway(Protocol):
    """De onde a licenca vem: Supabase (producao) ou local (desenvolvimento)."""

    def fetch(self, key: str, machine: str) -> License:  # ativar
        ...

    def verify(self, key: str, machine: str) -> License:  # reconsultar
        ...

    def release(self, key: str, machine: str) -> None:  # liberar a vaga
        ...

    def iniciar_teste(self, key: str, machine: str, produto: str) -> dict:  # 7 dias gratis
        ...


class LocalLicenseGateway:
    """Licenca de desenvolvimento: libera tudo sem consultar a internet."""

    def __init__(self, entitlements: tuple[str, ...] = DEFAULT_ENTITLEMENTS) -> None:
        self._entitlements = entitlements

    def fetch(self, key: str, machine: str) -> License:
        return License(
            key=key or LOCAL_KEY,
            customer="Instalacao local",
            entitlements=self._entitlements,
            machine=machine,
            activated_at=_now(),
            last_check=_now(),
            source=ORIGEM_LOCAL,
            max_machines=1,
            used_machines=1,
        )

    def verify(self, key: str, machine: str) -> License:
        return self.fetch(key, machine)

    def release(self, key: str, machine: str) -> None:
        return None

    def iniciar_teste(self, key: str, machine: str, produto: str) -> dict:
        raise LicenseError("A instalacao local ja libera todos os modulos.", "local")


class SupabaseLicenseGateway:
    """Consulta as licencas reais da DumTech no Supabase."""

    FUNCAO_ATIVAR = "dumtech_ativar_licenca"
    FUNCAO_VERIFICAR = "dumtech_verificar_licenca"
    FUNCAO_DESATIVAR = "dumtech_desativar_licenca"
    FUNCAO_TESTE = "dumtech_iniciar_teste"
    #: Edge Function que confere E assina (sem ela, o Hub usa a RPC de sempre)
    FUNCAO_ASSINADA = "licenca-assinada"

    def __init__(self, client: SupabaseClient | None = None) -> None:
        self.client = client or SupabaseClient()

    # ------------------------------------------------------------------ publico
    def fetch(self, key: str, machine: str) -> License:
        dados = self._chamar(
            self.FUNCAO_ATIVAR,
            {"p_chave": key, "p_maquina": machine, "p_apelido": machine_label()},
        )
        # ativou: ja pede a versao assinada. Se nao vier (funcao nao publicada,
        # rede caiu no meio), a ativacao vale igual e a assinatura chega na
        # proxima conferencia.
        try:
            assinada = self._assinada(key, machine)
        except LicenseError:
            assinada = None
        return self._para_licenca(dados, key, machine, (assinada or {}).get("assinado"))

    def verify(self, key: str, machine: str) -> License:
        dados = self._assinada(key, machine)
        if dados is None:
            dados = self._chamar(self.FUNCAO_VERIFICAR, {"p_chave": key, "p_maquina": machine})
        return self._para_licenca(dados, key, machine, dados.get("assinado"))

    def release(self, key: str, machine: str) -> None:
        self._chamar(self.FUNCAO_DESATIVAR, {"p_chave": key, "p_maquina": machine})

    def iniciar_teste(self, key: str, machine: str, produto: str) -> dict:
        """Pede 7 dias gratis de um modulo. Recusa vira LicenseError com a mensagem."""
        return self._chamar(self.FUNCAO_TESTE,
                            {"p_chave": key, "p_maquina": machine, "p_produto": produto.upper()})

    # ------------------------------------------------------------------ interno
    def _assinada(self, key: str, machine: str) -> dict | None:
        """Conferencia pela Edge Function. None = use o caminho antigo (RPC)."""
        funcao = getattr(self.client, "funcao", None)
        if funcao is None:
            return None
        try:
            resposta = funcao(self.FUNCAO_ASSINADA, {
                "chave": key, "maquina": machine, "computador": assinatura.computador_id(),
            })
        except SemConexao as erro:
            raise SemInternet(str(erro)) from erro
        except SupabaseError as erro:
            logger.info("Licenca assinada indisponivel, usando a verificacao antiga: %s", erro)
            return None
        if not isinstance(resposta, dict):
            return None
        if not resposta.get("ok"):
            # a funcao usa a MESMA regra do banco: recusa dela e recusa de verdade
            raise LicenseError(
                str(resposta.get("mensagem") or "Nao foi possivel validar a licenca."),
                str(resposta.get("erro") or "erro"),
            )
        return resposta

    def _chamar(self, funcao: str, params: dict) -> dict:
        try:
            resposta = self.client.rpc(funcao, params)
        except SemConexao as erro:
            raise SemInternet(str(erro)) from erro
        except SupabaseError as erro:
            raise LicenseError(str(erro), "servidor") from erro

        if not isinstance(resposta, dict):
            raise LicenseError("Resposta inesperada do servidor de licencas.", "servidor")
        if not resposta.get("ok"):
            raise LicenseError(
                str(resposta.get("mensagem") or "Nao foi possivel validar a licenca."),
                str(resposta.get("erro") or "erro"),
            )
        return resposta

    def _para_licenca(self, dados: dict, key: str, machine: str, assinado=None) -> License:
        # "produtos" e o campo atual; "aplicativos" e o nome antigo do mesmo
        # campo, ainda enviado para os Hubs instalados antes da migration
        # comercial. Ler os dois deixa o Hub novo funcionar com os dois servidores.
        codigos = dados.get("produtos")
        if codigos is None:
            codigos = dados.get("aplicativos") or []
        entitlements = tuple(
            sorted(str(codigo).strip().lower() for codigo in codigos if str(codigo).strip())
        )
        return License(
            key=str(dados.get("chave") or key).upper(),
            customer=str(dados.get("cliente") or "Cliente DumTech"),
            entitlements=entitlements,
            machine=machine,
            activated_at=_now(),
            last_check=_now(),
            expires_at=dados.get("expira_em"),
            source=ORIGEM_SUPABASE,
            max_machines=int(dados.get("max_computadores") or 1),
            used_machines=int(dados.get("computadores_usados") or 1),
            tipo=str(dados.get("tipo") or ""),
            assinado=dict(assinado) if isinstance(assinado, dict) else {},
            testes=_testes(dados.get("testes")),
        )


def _testes(bruto) -> dict:
    """{"AGENDA": "..."} do servidor -> {"agenda": "..."}. Lixo vira vazio."""
    if not isinstance(bruto, dict):
        return {}
    return {str(codigo).strip().lower(): str(fim) for codigo, fim in bruto.items()
            if str(codigo).strip() and fim}


# =================================================================== servico ==
def modo_local_ligado() -> bool:
    """True quando DUMTECH_LICENCA_LOCAL=1 (desenvolvimento e testes).

    Nunca no programa instalado: no .exe, uma variavel de ambiente que qualquer
    um cria com `setx` liberaria todos os modulos sem licenca.
    """
    if getattr(sys, "frozen", False):
        return False
    return os.environ.get(ENV_LICENCA_LOCAL, "").strip() in ("1", "true", "sim")


class LicenseService:
    """Ponto unico de consulta de licenca usado pelo Hub.

    Le e grava ``config/license.json``. So conversa com a internet quando o
    cliente pede: ativar ou verificar.
    """

    def __init__(
        self,
        file_path: Path | None = None,
        gateway: LicenseGateway | None = None,
    ) -> None:
        self.file_path = Path(file_path) if file_path else get_paths().license_file
        self.gateway: LicenseGateway = gateway or self._gateway_padrao()
        self._license: License | None = None

    @staticmethod
    def _gateway_padrao() -> LicenseGateway:
        return LocalLicenseGateway() if modo_local_ligado() else SupabaseLicenseGateway()

    # ------------------------------------------------------------------ leitura
    @property
    def current(self) -> License:
        if self._license is None:
            self._license = self._carregar()
        return self._license

    @property
    def ativada(self) -> bool:
        """Este computador ja tem uma licenca gravada?"""
        return self.current.ativa

    def allows(self, app_id: str) -> bool:
        return self.current.allows(app_id)

    def reload(self) -> License:
        self._license = None
        return self.current

    # ------------------------------------------------------------------ escrita
    def save(self, license_: License) -> License:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(license_.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._license = license_
        return license_

    def activate(self, key: str) -> License:
        """Ativa a chave (precisa de internet) e grava para uso offline."""
        chave = normalize_key(key)
        if not is_valid_key_format(chave):
            raise LicenseError(
                "Chave incompleta. Ela tem 16 caracteres, no formato XXXX-XXXX-XXXX-XXXX.",
                "formato",
            )
        licenca = self.gateway.fetch(chave, machine_id())
        return self.save(replace(licenca, activated_at=_now(), last_check=_now()))

    def iniciar_teste(self, app_id: str) -> License:
        """Comeca o teste gratis de 7 dias e ja traz a licenca assinada com ele.

        Precisa de internet (e o servidor que conta os dias). Levanta
        LicenseError com a mensagem pronta quando nao da: modulo ja comprado,
        teste ja usado, licenca invalida.
        """
        atual = self.current
        if not atual.key or not atual.ativa:
            raise LicenseError("Ative a sua licenca para testar outros modulos.", "sem_licenca")
        self.gateway.iniciar_teste(atual.key, atual.machine or machine_id(), app_id)
        return self.verify()

    def verify(self) -> License:
        """Reconsulta a licenca - usado quando o cliente compra outro aplicativo."""
        atual = self.current
        if not atual.key:
            raise LicenseError("Nenhuma licenca ativada neste computador.", "sem_licenca")
        licenca = self.gateway.verify(atual.key, atual.machine or machine_id())
        return self.save(
            replace(licenca, activated_at=atual.activated_at or _now(), last_check=_now())
        )

    def precisa_conferir(self, agora: datetime | None = None) -> bool:
        """Licenca do servidor sem conferencia recente?

        Vale tambem para licenca vencida ou bloqueada: e a conferencia que traz
        a renovacao ou a reativacao feita no painel.
        """
        atual = self.current
        if not atual.key or atual.source != ORIGEM_SUPABASE:
            return False
        if atual.bloqueio in BLOQUEIOS_DE_CONFERENCIA:
            return True  # so a conferencia destrava: nao espera o intervalo
        try:
            ultima = datetime.fromisoformat(str(atual.last_check)) if atual.last_check else None
        except ValueError:
            ultima = None
        if ultima is None:
            return True
        if ultima.tzinfo is None:
            ultima = ultima.replace(tzinfo=timezone.utc)
        return (agora or datetime.now(timezone.utc)) - ultima >= INTERVALO_CONFERENCIA

    def conferir(self) -> License:
        """Conferencia silenciosa com o servidor. Nunca levanta erro.

        - servidor confirmou: grava o que ele disse (modulo novo aparece);
        - servidor recusou de vez (RECUSAS_DEFINITIVAS): os aplicativos param,
          mas a chave fica guardada - quando a DumTech reativar, a proxima
          conferencia (ou o botao Verificar) devolve tudo sem digitar nada;
        - sem internet ou qualquer outra falha: nada muda.
        """
        try:
            return self.verify()
        except LicenseError as erro:
            if erro.codigo in RECUSAS_DEFINITIVAS and self.current.key:
                return self._bloquear(str(erro), erro.codigo)
            return self.current
        except Exception:  # noqa: BLE001 - conferir nunca derruba o Hub
            return self.current

    def _bloquear(self, mensagem: str, codigo: str) -> License:
        atual = self.current
        return self.save(
            replace(
                atual,
                entitlements=(),
                testes={},
                last_check=_now(),
                extras={**atual.extras, "bloqueio": codigo, "mensagem": mensagem},
            )
        )

    def deactivate(self, liberar_vaga: bool = True) -> None:
        """Remove a licenca deste computador (e libera a vaga, se der)."""
        atual = self.current
        if liberar_vaga and atual.key and not atual.is_local:
            self.gateway.release(atual.key, atual.machine or machine_id())
        if self.file_path.exists():
            self.file_path.unlink()
        self._license = None

    # ------------------------------------------------------------------ interno
    def _carregar(self) -> License:
        if self.file_path.exists():
            try:
                dados = json.loads(self.file_path.read_text(encoding="utf-8"))
                licenca = License.from_dict(dados)
            except (OSError, ValueError):
                licenca = None  # arquivo ilegivel: trata como se nao houvesse licenca
            if licenca is not None:
                # licenca de desenvolvimento so vale em modo de desenvolvimento:
                # no cliente ela nao pode liberar nada
                if licenca.source == ORIGEM_SUPABASE:
                    return self._conferir_assinatura(licenca)
                if licenca.is_local and modo_local_ligado():
                    return licenca
                # qualquer outra origem escrita no arquivo ("xyz", "nenhuma"...)
                # nao passa pela assinatura - entao nao pode liberar nada
                return License.vazia()
        if modo_local_ligado():
            return self.save(LocalLicenseGateway().fetch(LOCAL_KEY, machine_id()))
        return License.vazia()

    @staticmethod
    def _conferir_assinatura(licenca: License) -> License:
        """O arquivo diz; a assinatura da DumTech confirma (ou desmente).

        - assinatura que nao bate, ou de outra chave/maquina -> arquivo mexido;
        - assinada para outro computador -> arquivo copiado;
        - modulos: vale o que esta nos DOIS (o arquivo so pode tirar, nunca por);
        - prazo, cliente e tipo: valem os assinados;
        - passou do prazo offline -> sem modulos ate conferir com internet.
        """
        def sem_modulos(base: License, codigo: str, mensagem: str) -> License:
            return replace(base, entitlements=(), testes={},
                           extras={**base.extras, "bloqueio": codigo, "mensagem": mensagem})

        if not licenca.assinado:
            if ASSINATURA_OBRIGATORIA and licenca.key:
                return sem_modulos(licenca, "sem_assinatura",
                                   "Conecte este computador a internet para confirmar a licenca com a DumTech.")
            return licenca

        dados = assinatura.abrir(licenca.assinado)
        if (dados is None
                or "uso" in dados  # outro documento assinado (ex.: a chave Pix), nao uma licenca
                or dados.get("chave") != licenca.key
                or str(dados.get("maquina") or "").upper() != (licenca.machine or "").upper()):
            logger.warning("license.json com assinatura que nao confere: ignorado")
            return License.vazia()
        if dados.get("computador") != assinatura.computador_id():
            logger.warning("license.json assinado para outro computador: ignorado")
            return License.vazia()

        teto = {str(c).strip().lower() for c in dados.get("produtos") or []}
        testes_assinados = _testes(dados.get("testes"))
        conferida = replace(
            licenca,
            testes={app: fim for app, fim in testes_assinados.items() if app in licenca.testes},
            customer=str(dados.get("cliente") or licenca.customer),
            entitlements=tuple(sorted(e for e in licenca.entitlements if e in teto)),
            expires_at=dados.get("expira_em"),
            tipo=str(dados.get("tipo") or licenca.tipo),
            max_machines=int(dados.get("max_computadores") or licenca.max_machines),
        )
        if assinatura.vencida(dados):
            return sem_modulos(conferida, "conferencia_vencida",
                               "Faz tempo que este computador nao confere a licenca. "
                               "Conecte-o a internet para continuar usando os modulos.")
        return conferida
