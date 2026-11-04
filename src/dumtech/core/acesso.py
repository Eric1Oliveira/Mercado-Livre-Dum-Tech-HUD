"""Contas do Hub: quem esta neste computador e o que essa pessoa pode ver.

Nao confundir com ``core/conta.py``: aquela e a conta DumTech de quem instalou o
programa. Esta e das pessoas da loja, ADM e funcionario, ligadas a chave.

COMO FUNCIONA
    * as contas moram no servidor. Quem deriva e confere senha e a Edge Function
      ``acesso``, e o banco so ve o hash;
    * o Hub guarda, junto da licenca, um pacote ASSINADO com as contas da chave
      (sem senha nem e-mail): e dele que saem papel e permissoes;
    * loja sem conta nao sente nada: tudo liberado, como sempre foi.

SEM INTERNET
    Ao entrar com internet, o Hub grava aqui um verificador PBKDF2 da senha. Sem
    internet, confere com ele. Por isso o primeiro login de cada pessoa em cada
    computador precisa de internet, e a senha trocada em outro computador
    (``senha_versao`` assinada diferente) so entra de novo online.

DUAS SESSOES
    A *do computador* diz quem esta aqui e nao precisa de rede. A *de gestao* vale
    30 minutos, fica so na memoria e e o que abre Usuarios, Computadores e o
    celular. Sem ela, a tela pede a senha de novo.

O QUE NAO RESOLVE (limite honesto)
    A conta controla o que cada pessoa ve dentro do programa. Os bancos ``.db``
    continuam sem criptografia: quem tem conhecimento tecnico e acesso ao Windows
    consegue abri-los. E programa alterado pula qualquer conferencia.

Aqui nao ha Qt. As chamadas de rede (`entrar`, `salvar_usuario`...) rodam em
segundo plano; `aplicar` e `guardar_documento` gravam e rodam na thread da tela.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import assinatura
from .avisos import TIPOS
from .paths import get_paths
from .supabase import FuncaoIndisponivel, SemConexao, SupabaseClient, SupabaseError

logger = logging.getLogger(__name__)

#: Edge Function que responde por tudo isto (supabase/functions/acesso)
FUNCAO = "acesso"

ADM = "adm"
FUNCIONARIO = "funcionario"

#: marcas dos documentos assinados - separam contas e lembranca de uma licenca
USO_ACESSO = "acesso"
USO_LEMBRAR = "lembrar"

#: o servidor da 30 minutos; aqui fecha um pouco antes, para nunca mostrar
#: "liberado" com a sessao ja vencida la
SESSAO_SEGUNDOS = 29 * 60

#: quanto custa cada tentativa de senha offline neste computador (~100 ms)
ITERACOES_LOCAIS = 300_000

#: quantas pessoas aparecem no login em um clique
RECENTES = 6

SEM_INTERNET = "Você está sem internet. Conecte o computador e tente de novo."

_LOGIN = re.compile(r"^[a-z0-9._@+-]{3,60}$")

#: as mesmas de `senhaAceitavel` no servidor, que e quem decide de verdade
_OBVIAS = frozenset({
    "12345678", "123456789", "1234567890", "87654321", "senha123", "senha1234", "password", "password1",
    "qwerty123", "admin123", "administrador", "abcd1234", "dumtech123", "mudar123",
})

#: Modelos do cadastro. So preenchem as caixas: o que vale e o que ficou marcado.
MODELOS: dict[str, tuple[str, ...]] = {
    "Vendedor": ("vendas", "clientes", "agenda"),
    "Estoque": ("estoque",),
    "Técnico": ("ordens", "clientes", "agenda"),
    "Financeiro": ("financeiro", "clientes"),
}


class AcessoError(Exception):
    """Erro com mensagem pronta para a tela."""

    def __init__(self, mensagem: str, codigo: str = "erro") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


# ================================================================ formatos ===
def validar_login(login: str) -> str:
    """O motivo da recusa, ou "" quando serve."""
    if _LOGIN.match((login or "").strip().lower()):
        return ""
    return "Use de 3 a 60 letras e números, sem espaços e sem acentos."


def validar_senha(senha: str, login: str = "") -> str:
    """O motivo da recusa, ou "" quando serve. O servidor confere de novo."""
    texto = senha or ""
    if len(texto) < 8:
        return "A senha precisa ter pelo menos 8 caracteres."
    if len(texto) > 72:
        return "A senha pode ter no máximo 72 caracteres."
    minusculo = texto.lower()
    if login and minusculo == login.strip().lower():
        return "A senha não pode ser igual ao login."
    if minusculo in _OBVIAS or len(set(minusculo)) == 1:
        return "Essa senha é fácil demais de adivinhar. Escolha outra."
    return ""


def forca_da_senha(senha: str) -> int:
    """0 nao serve, 1 fraca, 2 boa, 3 forte. So orienta: quem decide e o tamanho."""
    texto = senha or ""
    if validar_senha(texto):
        return 0
    variedade = sum((any(c.islower() for c in texto), any(c.isupper() for c in texto),
                     any(c.isdigit() for c in texto), any(not c.isalnum() for c in texto)))
    if len(texto) >= 12 and variedade >= 3:
        return 3
    if len(texto) >= 10 and variedade >= 2:
        return 2
    return 1


def sugerir_login(nome: str) -> str:
    """"Maria Conceição" -> "maria.conceicao": um a menos para a pessoa inventar."""
    simples = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode("ascii").lower()
    partes = re.findall(r"[a-z0-9]+", simples)
    if not partes:
        return ""
    return ".".join(partes[:2] if len(partes) == 2 else (partes[0], partes[-1]) if len(partes) > 2 else partes)[:60]


def gerar_senha() -> str:
    """Senha inicial facil de ditar. Quem recebe cria a propria no primeiro acesso."""
    letras = "abcdefghjkmnpqrstuvwxyz"   # sem i, l e o: nada que se confunda ao ler
    pedaco = "".join(secrets.choice(letras) for _ in range(4))
    numero = "".join(secrets.choice("23456789") for _ in range(4))
    fim = "".join(secrets.choice(letras) for _ in range(3))
    return f"{pedaco}-{numero}-{fim}"


def avisos_dos_modulos(modulos) -> tuple[str, ...]:
    """Os tipos de aviso que pertencem a estes modulos."""
    escolhidos = set(modulos or ())
    return tuple(tipo.chave for tipo in TIPOS if tipo.app_id in escolhidos)


def permissoes_do_modelo(nome: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    modulos = MODELOS.get(nome, ())
    return modulos, avisos_dos_modulos(modulos)


# ================================================================== pessoa ===
@dataclass(frozen=True)
class Usuario:
    """Uma conta da chave, como veio no pacote assinado."""

    id: str
    login: str
    nome: str
    papel: str
    modulos: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()
    senha_versao: int = 1
    trocar_senha: bool = False
    ativo: bool = True
    tem_email: bool = False
    email_confirmado: bool = False

    @property
    def e_adm(self) -> bool:
        return self.papel == ADM

    @classmethod
    def de_dict(cls, dados: dict) -> "Usuario":
        return cls(
            id=str(dados.get("id") or ""),
            login=str(dados.get("login") or ""),
            nome=str(dados.get("nome") or ""),
            papel=str(dados.get("papel") or FUNCIONARIO),
            modulos=tuple(str(m) for m in dados.get("modulos") or ()),
            avisos=tuple(str(a) for a in dados.get("avisos") or ()),
            senha_versao=int(dados.get("senha_versao") or 1),
            trocar_senha=bool(dados.get("trocar_senha")),
            ativo=bool(dados.get("ativo", True)),
            tem_email=bool(dados.get("tem_email")),
            email_confirmado=bool(dados.get("email_confirmado")),
        )


def _verificador(senha: str, sal: bytes, iteracoes: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, iteracoes)


def _base64(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


class AcessoService:
    """Login, permissoes e gestao das contas da chave ativada aqui."""

    def __init__(self, licencas, arquivo: Path | None = None, client: SupabaseClient | None = None,
                 relogio=time.monotonic) -> None:
        self.licencas = licencas
        self.arquivo = Path(arquivo) if arquivo else get_paths().acesso_file
        self.client = client or SupabaseClient()
        self._relogio = relogio
        #: quem esta neste computador agora
        self._usuario_id = ""
        #: a senha com que essa pessoa entrou: mudou em outro lugar, ela sai
        self._senha_versao = 0
        #: segredo da sessao de gestao: so na memoria, nunca no disco
        self._sessao = ""
        self._expira = 0.0
        #: abriu quando a loja ainda nao tinha conta (`nova_abertura`)
        self._aberto_sem_conta = False
        #: conferir a assinatura custa: uma vez por pacote
        self._aberto: tuple[Any, dict | None] = (None, None)

    # ----------------------------------------------------------------- pacote
    def documento(self) -> dict | None:
        """As contas da chave, se o pacote for assinado para ESTE computador."""
        licenca = self.licencas.current
        pacote = licenca.acesso
        if not pacote:
            return None
        marca = (pacote.get("assinatura"), licenca.key, licenca.machine)
        if self._aberto[0] == marca:
            return self._aberto[1]
        dados = assinatura.abrir(pacote)
        if not self._do_computador(dados, USO_ACESSO):
            logger.warning("Pacote de contas que nao confere: ignorado")
            dados = None
        self._aberto = (marca, dados)
        return dados

    def _do_computador(self, dados: dict | None, uso: str) -> bool:
        licenca = self.licencas.current
        return bool(dados and dados.get("uso") == uso and dados.get("chave") == licenca.key
                    and str(dados.get("maquina") or "").upper() == (licenca.machine or "").upper()
                    and dados.get("computador") == assinatura.computador_id())

    def falta_documento(self) -> bool:
        """Licenca do servidor ainda sem o pacote: a proxima conferencia traz."""
        licenca = self.licencas.current
        return licenca.ativa and licenca.source == "supabase" and not licenca.acesso

    def usuarios(self) -> list[Usuario]:
        documento = self.documento() or {}
        return [Usuario.de_dict(dados) for dados in documento.get("usuarios") or []]

    def _achar(self, usuario_id: str) -> Usuario | None:
        return next((u for u in self.usuarios() if u.id == usuario_id), None)

    # ----------------------------------------------------------------- estado
    @property
    def ha_contas(self) -> bool:
        # a licenca assinada tambem diz: apagar o pacote nao faz a loja parecer sem conta
        return self.licencas.current.tem_contas or bool(self.usuarios())

    @property
    def exigir_conta(self) -> bool:
        return bool((self.documento() or {}).get("exigir_conta"))

    def nova_abertura(self) -> None:
        """O Hub abriu, ou a chave mudou. Decide se este Hub ja pede conta.

        O ADM cria a conta num computador e os outros so pedem login na proxima
        abertura: Hub aberto no meio de uma venda nao pode perder as abas.
        """
        self._aberto_sem_conta = not self.ha_contas

    @property
    def exige_conta(self) -> bool:
        return self.ha_contas and not self._aberto_sem_conta

    @property
    def usuario(self) -> Usuario | None:
        return self._achar(self._usuario_id) if self._usuario_id else None

    @property
    def _liberado(self) -> Usuario | None:
        """Quem ja pode usar. Senha provisoria nao abre nada: ela so serve para
        criar a senha da pessoa, e quem a escolheu tambem a conhece."""
        usuario = self.usuario
        return None if usuario is None or usuario.trocar_senha else usuario

    def precisa_login(self) -> bool:
        return self.exige_conta and self._liberado is None

    @property
    def computador_fora(self) -> bool:
        """A vaga deste computador foi solta: nenhuma senha resolve, so ativar de novo."""
        return self.licencas.current.bloqueio in ("maquina_nao_ativada", "outro_computador")

    @property
    def e_adm(self) -> bool:
        """Loja sem conta segue como sempre: quem abre manda."""
        if not self.exige_conta:
            return True
        usuario = self._liberado
        return usuario is not None and usuario.e_adm

    def permite_modulo(self, app_id: str) -> bool:
        if self.e_adm:
            return True
        usuario = self._liberado
        return usuario is not None and app_id in usuario.modulos

    def permite_aviso(self, tipo: str) -> bool:
        if self.e_adm:
            return True
        usuario = self._liberado
        return usuario is not None and tipo in usuario.avisos

    @property
    def sessao(self) -> str:
        if self._sessao and self._relogio() >= self._expira:
            self.trancar_gestao()
        return self._sessao

    @property
    def gestao_aberta(self) -> bool:
        return bool(self.sessao)

    def trancar_gestao(self) -> None:
        self._sessao = ""
        self._expira = 0.0

    def esta_lembrado(self) -> bool:
        return bool(self._usuario_id) and self._ler().get("lembrado") == self._usuario_id

    def recentes(self) -> list[Usuario]:
        """Quem ja entrou neste computador, o ultimo primeiro."""
        pessoas = {u.id: u for u in self.usuarios() if u.ativo}
        lista = (pessoas.get(i) for i in self._ler().get("recentes") or [])
        return [pessoa for pessoa in lista if pessoa is not None]

    # ----------------------------------------------------------------- entrar
    def abrir_lembrado(self) -> Usuario | None:
        """Abre direto quem pediu para ser lembrado, sem rede e sem senha.

        Vale so com lembranca assinada para esta pessoa, esta senha e este
        computador: mudar o ``lembrado`` no arquivo nao abre nada.
        """
        guardado = self._ler()
        usuario_id = str(guardado.get("lembrado") or "")
        pacote = (guardado.get("locais") or {}).get(usuario_id, {}).get("lembranca")
        usuario = self._achar(usuario_id) if usuario_id and pacote else None
        if usuario is None or not usuario.ativo or usuario.trocar_senha:
            return None
        dados = assinatura.abrir(pacote)
        if (not self._do_computador(dados, USO_LEMBRAR) or dados.get("usuario") != usuario.id
                or dados.get("senha_versao") != usuario.senha_versao):
            logger.info("Lembranca que nao vale mais: pede a senha")
            return None
        self._usuario_id = usuario.id
        self._senha_versao = usuario.senha_versao
        self._aberto_sem_conta = False
        return usuario

    def entrar(self, login: str, senha: str, lembrar: bool = True) -> dict:
        """Em segundo plano. Sem internet ou com o servidor fora, confere offline."""
        login = (login or "").strip().lower()
        try:
            resposta = self._chamar("entrar", {**self._identidade(), "login": login, "senha": senha,
                                               "lembrar": lembrar})
        except AcessoError as erro:
            if erro.codigo not in ("sem_internet", "indisponivel"):
                raise
            return self._entrar_offline(login, senha, lembrar)
        return self._com_verificador(resposta, senha, lembrar)

    def _entrar_offline(self, login: str, senha: str, lembrar: bool) -> dict:
        usuario = next((u for u in self.usuarios() if u.login == login), None)
        local = (self._ler().get("locais") or {}).get(usuario.id if usuario else "")
        if usuario is None or not local or "verificador" not in local:
            raise AcessoError("Sem internet, só entra quem já usou este computador. "
                              "Conecte à internet para o primeiro acesso.", "primeiro_acesso_online")
        if not usuario.ativo:
            raise AcessoError("Esta conta está bloqueada. Fale com o administrador.", "conta_bloqueada")
        if int(local.get("senha_versao") or 0) != usuario.senha_versao:
            raise AcessoError("A senha desta conta mudou. Conecte à internet para entrar.", "senha_mudou")
        if usuario.trocar_senha:
            raise AcessoError("Você precisa criar uma senha nova. Conecte à internet para continuar.",
                              "trocar_senha_online")
        try:
            calculado = _verificador(senha, base64.b64decode(local["sal"]), int(local["iteracoes"]))
            esperado = base64.b64decode(local["verificador"])
        except (KeyError, TypeError, ValueError):
            raise AcessoError("Conecte à internet para entrar.", "primeiro_acesso_online") from None
        if not hmac.compare_digest(calculado, esperado):
            raise AcessoError("Login ou senha incorretos.", "credenciais")
        return {"ok": True, "usuario": {"id": usuario.id}, "_lembrar": lembrar}

    def _com_verificador(self, resposta: dict, senha: str, lembrar: bool | None) -> dict:
        """Calcula aqui, em segundo plano: derivar a senha nao trava a tela."""
        sal = os.urandom(16)
        iteracoes = ITERACOES_LOCAIS
        return {**resposta, "_lembrar": lembrar, "_local": {
            "sal": _base64(sal), "iteracoes": iteracoes, "verificador": _base64(_verificador(senha, sal, iteracoes)),
        }}

    def aplicar(self, resposta: dict) -> Usuario:
        """Na thread da tela: grava o que a entrada trouxe e poe a pessoa aqui."""
        self.guardar_documento(resposta.get("acesso_assinado"))
        usuario = self._achar(str((resposta.get("usuario") or {}).get("id") or ""))
        if usuario is None:
            raise AcessoError("A resposta do servidor não confere. Tente de novo.", "assinatura")

        guardado = self._ler()
        locais = guardado.setdefault("locais", {})
        local = locais.setdefault(usuario.id, {})
        if resposta.get("_local"):
            local.update(resposta["_local"], senha_versao=usuario.senha_versao)
        lembrar = resposta.get("_lembrar")
        if resposta.get("lembranca"):
            local["lembranca"] = resposta["lembranca"]
        elif lembrar is False:
            local.pop("lembranca", None)
        if lembrar is True and "lembranca" in local:
            guardado["lembrado"] = usuario.id
        elif lembrar is False:
            guardado["lembrado"] = ""
        recentes = [i for i in guardado.get("recentes") or [] if i != usuario.id]
        guardado["recentes"] = [usuario.id, *recentes][:RECENTES]
        self._gravar(guardado)

        self._usuario_id = usuario.id
        self._senha_versao = usuario.senha_versao
        self._aberto_sem_conta = False
        if resposta.get("sessao"):
            self._sessao = str(resposta["sessao"])
            self._expira = self._relogio() + SESSAO_SEGUNDOS
        return usuario

    def guardar_documento(self, pacote: Any) -> None:
        """Grava o pacote novo, se a assinatura confirmar. Sem pacote, nada muda."""
        if not pacote:
            return
        if not self._do_computador(assinatura.abrir(pacote) if isinstance(pacote, dict) else None, USO_ACESSO):
            raise AcessoError("A resposta do servidor não confere. Tente de novo.", "assinatura")
        self.licencas.guardar_acesso(pacote)

    def reconciliar(self) -> bool:
        """Chegou pacote novo: a pessoa logada ainda pode estar aqui?

        Permissao nova nao derruba ninguem, as abas e que mudam. Conta apagada,
        bloqueada ou com a senha redefinida precisa sair.
        """
        if not self._usuario_id:
            return False
        usuario = self.usuario
        return (usuario is None or not usuario.ativo or usuario.senha_versao != self._senha_versao)

    def sair(self, esquecer: bool = True) -> None:
        """Tira a pessoa do computador. `esquecer` apaga a lembranca dela.

        Sair nunca deixa `lembrado` apontando para ela: quem trocou de usuario
        passou o computador, e reabrir o Hub nao pode devolver a conta sem senha.
        """
        usuario_id, self._usuario_id = self._usuario_id, ""
        self._senha_versao = 0
        self.trancar_gestao()
        if not usuario_id:
            return
        guardado = self._ler()
        if esquecer:
            (guardado.get("locais") or {}).get(usuario_id, {}).pop("lembranca", None)
        guardado["lembrado"] = ""
        self._gravar(guardado)

    def esquecer_tudo(self) -> None:
        """A licenca saiu deste computador: nada dela fica para tras."""
        self._usuario_id = ""
        self.trancar_gestao()
        try:
            self.arquivo.unlink(missing_ok=True)
        except OSError:
            logger.exception("Nao foi possivel apagar as contas deste computador")

    # ---------------------------------------------------- rede (2o plano) ---
    def criar_primeiro(self, nome: str, login: str, email: str, senha: str) -> dict:
        resposta = self._chamar("criar-primeiro", {
            **self._identidade(), "nome": nome, "login": login, "email": email, "senha": senha, "lembrar": True,
        })
        return self._com_verificador(resposta, senha, True)

    def reabrir_gestao(self, senha: str) -> dict:
        """Confirma a senha para abrir Usuarios ou o celular. Nao ha gestao offline."""
        usuario = self.usuario
        if usuario is None:
            raise AcessoError("Entre com a sua conta primeiro.", "sessao_vencida")
        resposta = self._chamar("entrar", {**self._identidade(), "login": usuario.login, "senha": senha})
        return self._com_verificador(resposta, senha, None)

    def pedir_codigo(self, login: str) -> dict:
        return self._chamar("pedir-codigo", {**self._identidade(), "login": (login or "").strip().lower()})

    def redefinir(self, login: str, codigo: str, senha: str, lembrar: bool = True) -> dict:
        texto = (codigo or "").strip()
        if not re.fullmatch(r"\d{6}", texto):
            raise AcessoError("Digite os 6 números que chegaram no e-mail.", "formato")
        resposta = self._chamar("redefinir", {
            **self._identidade(), "login": (login or "").strip().lower(), "codigo": texto, "senha": senha,
            "lembrar": lembrar,
        })
        return self._com_verificador(resposta, senha, lembrar)

    def pedir_confirmacao(self) -> str:
        """Manda o codigo de confirmar o e-mail. Devolve o e-mail mascarado."""
        return str(self._gestao("pedir-confirmacao").get("email") or "")

    def confirmar_email(self, codigo: str) -> dict:
        return self._gestao("confirmar-email", codigo=(codigo or "").strip())

    def trocar_senha(self, atual: str, nova: str, lembrar: bool = True) -> dict:
        """A propria senha. A atual abre a sessao, se ela ja tiver vencido."""
        sessao = self.sessao
        aberta: dict = {}
        if not sessao:
            usuario = self.usuario
            if usuario is None:
                raise AcessoError("Entre com a sua conta primeiro.", "sessao_vencida")
            entrada = self._chamar("entrar", {**self._identidade(), "login": usuario.login, "senha": atual})
            sessao = str(entrada.get("sessao") or "")
            aberta = {"sessao": sessao}
        resposta = self._chamar("trocar-senha", {**self._identidade(), "sessao": sessao, "atual": atual,
                                                 "nova": nova, "lembrar": lembrar})
        return self._com_verificador({**resposta, **aberta}, nova, lembrar)

    def listar_usuarios(self) -> list[dict]:
        return list(self._gestao("usuarios").get("usuarios") or [])

    def salvar_usuario(self, dados: dict, senha: str = "") -> dict:
        return self._gestao("salvar-usuario", id=dados.get("id"), usuario=dados, senha=senha)

    def definir_senha(self, usuario_id: str, login: str, senha: str) -> dict:
        return self._gestao("senha-usuario", id=usuario_id, login=login, senha=senha)

    def apagar_usuario(self, usuario_id: str) -> dict:
        return self._gestao("apagar-usuario", id=usuario_id)

    def computadores(self) -> dict:
        return self._gestao("computadores")

    def renomear_computador(self, maquina: str, apelido: str) -> dict:
        return self._gestao("renomear-computador", maquina_alvo=maquina, apelido=apelido)

    def liberar_computador(self, maquina: str) -> dict:
        return self._gestao("liberar-computador", maquina_alvo=maquina)

    # ---------------------------------------------------------------- interno
    def _identidade(self) -> dict:
        licenca = self.licencas.current
        if not licenca.key or licenca.source != "supabase":
            raise AcessoError("Ative a licença deste computador para usar as contas.", "sem_licenca")
        return {"chave": licenca.key, "maquina": licenca.machine, "computador": assinatura.computador_id()}

    def _gestao(self, rota: str, **corpo) -> dict:
        sessao = self.sessao
        if not sessao:
            raise AcessoError("Confirme a sua senha para continuar.", "sessao_vencida")
        return self._chamar(rota, {**self._identidade(), "sessao": sessao, **corpo})

    def _chamar(self, rota: str, corpo: dict) -> dict:
        try:
            resposta = self.client.funcao(f"{FUNCAO}/{rota}", corpo)
        except SemConexao as erro:
            raise AcessoError(SEM_INTERNET, "sem_internet") from erro
        except (FuncaoIndisponivel, SupabaseError) as erro:
            raise AcessoError("As contas estão indisponíveis agora. Tente de novo em instantes.",
                              "indisponivel") from erro
        if not isinstance(resposta, dict):
            raise AcessoError("Resposta inesperada do servidor.", "servidor")
        if not resposta.get("ok"):
            raise AcessoError(str(resposta.get("mensagem") or "Não foi possível concluir agora."),
                              str(resposta.get("erro") or "erro"))
        return resposta

    def _ler(self) -> dict:
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return dados if isinstance(dados, dict) else {}

    def _gravar(self, dados: dict) -> None:
        try:
            self.arquivo.parent.mkdir(parents=True, exist_ok=True)
            self.arquivo.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            # nao gravar so custa pedir a senha de novo: nao derruba quem entrou
            logger.exception("Nao foi possivel guardar as contas deste computador")
