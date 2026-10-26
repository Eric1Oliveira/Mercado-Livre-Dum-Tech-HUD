"""A conta DumTech deste computador: quem instalou o Hub.

No primeiro acesso o cliente diz o nome e o e-mail. Esses dados vao para dois
lugares:

* ``hub.json``, secao ``empresa`` - a mesma que assina os comprovantes, para
  ninguem ter de digitar duas vezes a mesma coisa (ver ``core/empresa.py``);
* o servidor da DumTech, que passa a saber quem instalou o programa mesmo antes
  da primeira compra.

O que fica aqui, na secao ``conta``, e so o estado do cadastro: ja passou pelo
primeiro acesso? qual e-mail foi registrado? o servidor chegou a saber?

**Falhar aqui nunca pode travar o programa.** Sem internet, o cadastro fica
marcado como pendente e o Hub tenta de novo na proxima abertura - o primeiro
acesso termina do mesmo jeito, e o cliente entra.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .documentos import so_digitos
from .supabase import SupabaseClient, SupabaseError

logger = logging.getLogger(__name__)

SECAO = "conta"

#: funcao do servidor que cadastra (ou reconhece) quem instalou o Hub
FUNCAO_IDENTIFICAR = "dumtech_identificar_cliente"

#: liga o e-mail desta conta a licenca ativada (junta cadastro duplicado)
FUNCAO_VINCULAR = "dumtech_vincular_conta"

#: erros que valem tentar de novo mais tarde; qualquer outra resposta encerra
_VINCULO_DE_NOVO = frozenset({"muitas_tentativas", "maquina_nao_ativada"})

#: a mesma regra do servidor, conferida antes para nao gastar a viagem
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


class ContaError(Exception):
    """Erro de preenchimento, com mensagem pronta para a tela."""


def email_valido(email: str) -> bool:
    return bool(_EMAIL.match((email or "").strip()))


@dataclass
class Conta:
    """O estado do cadastro deste computador."""

    #: o primeiro acesso ja foi concluido (com ou sem internet)
    concluido: bool = False
    #: e-mail informado pelo cliente
    email: str = ""
    #: o cadastro ainda nao chegou ao servidor
    pendente: bool = False

    @property
    def registrada(self) -> bool:
        return bool(self.email) and not self.pendente

    @classmethod
    def carregar(cls, settings) -> "Conta":
        return cls(
            concluido=bool(settings.get(SECAO, "concluido", False)),
            email=str(settings.get(SECAO, "email", "") or ""),
            pendente=bool(settings.get(SECAO, "pendente", False)),
        )

    def salvar(self, settings) -> "Conta":
        settings.set(SECAO, "concluido", self.concluido)
        settings.set(SECAO, "email", self.email)
        settings.set(SECAO, "pendente", self.pendente)
        settings.save()
        return self


class ContaService:
    """Cadastra quem instalou o Hub no servidor da DumTech."""

    def __init__(self, settings, client: SupabaseClient | None = None) -> None:
        self.settings = settings
        self.client = client or SupabaseClient()

    @property
    def atual(self) -> Conta:
        return Conta.carregar(self.settings)

    def registrar(self, nome: str, email: str, telefone: str = "") -> Conta:
        """Grava a conta e avisa o servidor. Sem internet, fica pendente.

        Levanta ``ContaError`` apenas quando o que foi digitado nao serve -
        erro de rede nunca sobe daqui.
        """
        nome = (nome or "").strip()
        email = (email or "").strip().lower()
        if not nome:
            raise ContaError("Informe o seu nome.")
        if not email_valido(email):
            raise ContaError("Confira o e-mail digitado.")

        enviado = self._enviar(nome, email, telefone)
        return Conta(concluido=True, email=email, pendente=not enviado).salvar(self.settings)

    def reenviar(self, nome: str, telefone: str = "") -> Conta:
        """Segunda chance para o cadastro que nao chegou ao servidor.

        Chamado quando o Hub abre. Se nao houver nada pendente, nao fala com a
        internet.
        """
        conta = self.atual
        nome = (nome or "").strip()
        if not conta.pendente or not conta.email or not nome:
            return conta
        if self._enviar(nome, conta.email, telefone):
            conta.pendente = False
            conta.salvar(self.settings)
        return conta

    # ------------------------------------------------------------ um cadastro
    # Quem compra no Mercado Livre vira cliente SEM e-mail (o ML nao mostra), e
    # no primeiro acesso do Hub digita o e-mail - o que criava um segundo
    # cadastro. Depois de ativar, o Hub avisa o servidor: "esta chave, neste
    # computador ativado, e deste e-mail". O servidor liga e junta.
    def precisa_vincular(self, chave: str) -> bool:
        """Ainda nao ligou o e-mail desta conta a esta chave?"""
        conta = self.atual
        return bool(chave and conta.email) and self.settings.get(SECAO, "vinculado_a", "") != chave

    def vincular(self, chave: str, maquina: str, nome: str) -> bool:
        """So rede (pode rodar em segundo plano). True = assunto encerrado.

        Encerrado inclui "o servidor preferiu nao ligar" (o cadastro ja tem outro
        e-mail): perguntar de novo todo dia nao mudaria a resposta.
        """
        conta = self.atual
        if not chave or not maquina or not conta.email:
            return False
        try:
            resposta = self.client.rpc(FUNCAO_VINCULAR, {
                "p_chave": chave, "p_maquina": maquina, "p_nome": (nome or "").strip(),
                "p_email": conta.email,
            })
        except SupabaseError as erro:
            logger.info("Vinculo da conta adiado: %s", erro)
            return False
        except Exception:  # noqa: BLE001 - nada aqui pode derrubar o Hub
            logger.exception("Falha inesperada ao vincular a conta")
            return False
        if not isinstance(resposta, dict):
            return False
        if resposta.get("ok"):
            return True
        return str(resposta.get("erro") or "") not in _VINCULO_DE_NOVO

    def marcar_vinculo(self, chave: str) -> None:
        """Na thread da interface: grava que esta chave ja foi ligada."""
        self.settings.set(SECAO, "vinculado_a", chave)
        self.settings.save()

    # ------------------------------------------------------------------ interno
    def _enviar(self, nome: str, email: str, telefone: str = "") -> bool:
        params = {"p_nome": nome, "p_email": email}
        # so os digitos, e so quando ha: o servidor anterior a 1.5.0 nao
        # conhece o parametro, e o cadastro sem telefone continua igual
        digitos = so_digitos(telefone)
        if digitos:
            params["p_telefone"] = digitos
        try:
            resposta = self.client.rpc(FUNCAO_IDENTIFICAR, params)
        except SupabaseError as erro:
            logger.info("Cadastro da conta adiado: %s", erro)
            return False
        except Exception:  # noqa: BLE001 - nada aqui pode derrubar o Hub
            logger.exception("Falha inesperada ao cadastrar a conta")
            return False

        if isinstance(resposta, dict) and resposta.get("ok"):
            return True
        logger.info("O servidor recusou o cadastro: %s", resposta)
        return False
