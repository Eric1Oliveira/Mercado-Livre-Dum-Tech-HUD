"""O que precisa de atencao hoje.

Cada aplicativo ja sabe responder isso por dentro - o Financeiro sabe o que
vence, a oficina sabe o que atrasou, o Estoque sabe o que acabou. O que faltava
era o cliente nao precisar abrir sete telas para descobrir.

Este arquivo e so o contrato, no mesmo desenho de `core/catalog.py`: quem
implementa e cada `module.py`, expondo

    def avisos(paths, config) -> list[Aviso]

e o Hub junta os aplicativos que a licenca liberou. Aplicativo que nao
implementa simplesmente nao aparece, e aplicativo que quebrar ao calcular nao
derruba a tela de ninguem.

Nada disso e obrigatorio para o programa funcionar: sem avisos nenhum, o Inicio
volta a ser a central de aplicativos que sempre foi.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SECAO = "avisos"


@dataclass(frozen=True)
class Aviso:
    """Uma linha da tela de hoje."""

    app_id: str
    #: chave do tipo (ver TIPOS) - e por ela que o cliente liga e desliga
    tipo: str
    titulo: str
    detalhe: str = ""
    #: cor da linha: "danger" para o que ja passou, "warning" para o que vem
    tom: str = "muted"
    #: ordena a lista; o mais urgente em cima
    urgencia: int = 0
    icone: str = "alert"
    quantidade: int = 0


@dataclass(frozen=True)
class Tipo:
    """Um tipo de aviso que o cliente pode ajustar ou desligar."""

    chave: str
    app_id: str
    titulo: str
    #: o que a pessoa esta ligando/desligando, em uma linha
    explicacao: str
    #: prazo em dias, quando o aviso tem um; None quando nao faz sentido
    dias: int | None = None
    rotulo_dias: str = "Avisar com quantos dias de antecedencia"
    minimo: int = 1
    maximo: int = 90


TIPOS: tuple[Tipo, ...] = (
    Tipo("compromisso_hoje", "agenda", "Compromissos de hoje",
         "Os horarios marcados para hoje, com o proximo em destaque.",
         dias=None),
    Tipo("aniversario_hoje", "clientes", "Aniversariantes",
         "Quem faz aniversario hoje - motivo de ligacao que gera venda.",
         dias=None),
    Tipo("estoque_baixo", "estoque", "Estoque baixo",
         "Produtos que chegaram ao minimo que voce definiu.", dias=None),
    Tipo("conta_vencendo", "financeiro", "Contas a vencer",
         "Contas a pagar e a receber chegando ao vencimento.",
         dias=7, rotulo_dias="Avisar com quantos dias de antecedencia"),
    Tipo("conta_vencida", "financeiro", "Contas vencidas",
         "O que passou do vencimento e continua em aberto.", dias=None),
    Tipo("proposta_parada", "orcamentos", "Propostas sem resposta",
         "Propostas enviadas que o cliente ainda nao respondeu.",
         dias=5, rotulo_dias="Cobrar depois de quantos dias sem resposta"),
    Tipo("proposta_vencendo", "orcamentos", "Propostas vencendo",
         "Propostas cuja validade esta acabando.",
         dias=3, rotulo_dias="Avisar com quantos dias de antecedencia"),
    Tipo("os_atrasada", "ordens", "Ordens atrasadas",
         "Ordens de servico que passaram do prazo combinado.", dias=None),
    Tipo("os_para_retirar", "ordens", "Servicos parados na prateleira",
         "Ordens prontas que o cliente ainda nao veio buscar.",
         dias=2, rotulo_dias="Avisar depois de quantos dias prontas"),
    Tipo("venda_a_receber", "vendas", "Vendas a receber",
         "Vendas fechadas que ainda nao foram pagas.", dias=None),
)
POR_CHAVE = {tipo.chave: tipo for tipo in TIPOS}


def tipos_de(app_id: str) -> list[Tipo]:
    return [tipo for tipo in TIPOS if tipo.app_id == app_id]


@dataclass
class Config:
    """O que o cliente ajustou. Sem nada ajustado, valem os padroes.

    Guardado nas preferencias do Hub, e nao no banco de nenhum aplicativo:
    a tela de hoje e da plataforma, nao de um modulo.
    """

    settings: object = None
    _cache: dict = field(default_factory=dict)

    def ligado(self, chave: str) -> bool:
        return bool(self._ler(f"{chave}_ligado", True))

    def dias(self, chave: str) -> int:
        tipo = POR_CHAVE.get(chave)
        padrao = tipo.dias if tipo and tipo.dias is not None else 0
        try:
            valor = int(self._ler(f"{chave}_dias", padrao))
        except (TypeError, ValueError):
            return padrao
        if tipo is None:
            return valor
        return max(tipo.minimo, min(tipo.maximo, valor)) if valor else padrao

    def definir(self, chave: str, ligado: bool | None = None,
                dias: int | None = None) -> None:
        if ligado is not None:
            self._escrever(f"{chave}_ligado", bool(ligado))
        if dias is not None:
            self._escrever(f"{chave}_dias", int(dias))

    # ------------------------------------------------------------------ leitura
    def _ler(self, chave: str, padrao):
        if self.settings is None:
            return self._cache.get(chave, padrao)
        valor = self.settings.get(SECAO, chave, None)
        return padrao if valor is None else valor

    def _escrever(self, chave: str, valor) -> None:
        if self.settings is None:
            self._cache[chave] = valor
            return
        self.settings.set(SECAO, chave, valor)
        self.settings.save()


def coletar(modulo, paths, config: Config | None = None) -> list[Aviso]:
    """Pergunta os avisos a um modulo, sem deixar ele derrubar a tela.

    Um aplicativo com banco corrompido, meio migrado ou aberto por outro
    processo nao pode impedir o cliente de ver o resto do dia dele.
    """
    funcao = getattr(modulo, "avisos", None)
    if not callable(funcao):
        return []
    config = config or Config()
    try:
        encontrados = funcao(paths, config) or []
    except Exception:  # noqa: BLE001 - contrato: modulo quebrado nao propaga
        # o cliente nao ve nada; quem da suporte ve tudo, no log
        logger.exception("Falha ao calcular os avisos de %s",
                         getattr(modulo, "__name__", modulo))
        return []
    return [a for a in encontrados if isinstance(a, Aviso) and config.ligado(a.tipo)]


def ordenar(avisos: list[Aviso]) -> list[Aviso]:
    """O mais urgente em cima; empate, pela ordem dos tipos."""
    ordem = {tipo.chave: posicao for posicao, tipo in enumerate(TIPOS)}
    return sorted(avisos, key=lambda a: (-a.urgencia, ordem.get(a.tipo, 99)))
