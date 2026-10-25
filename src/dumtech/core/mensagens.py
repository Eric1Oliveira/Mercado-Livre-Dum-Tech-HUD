"""As mensagens de WhatsApp - o caminho mais curto entre o sistema e o cliente.

Nao ha API, nem cadastro, nem custo: o link `wa.me` abre a conversa com o texto
ja escrito, e quem aperta enviar e a pessoa. Isso tambem e uma decisao de
produto - nada sai sozinho em nome do cliente.

A regra da plataforma vale inteira aqui: **configuravel pelo cliente, e util
sem configurar**. Os seis modelos nascem escritos e funcionam no primeiro dia;
quem quiser muda o texto na tela de Configuracoes. Campo desconhecido no modelo
nao derruba nada - sai vazio, e a tela avisa antes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

from .documentos import so_digitos

SECAO = "mensagens"
#: Brasil. O `wa.me` exige o pais junto do numero.
DDI = "55"

CAMPO = re.compile(r"\{([a-z_]+)\}")


class MensagemError(Exception):
    """Erro com mensagem pronta para o usuario."""


@dataclass(frozen=True)
class Modelo:
    """Um modelo de mensagem, com o texto que ja vem pronto."""

    chave: str
    titulo: str
    #: quando essa mensagem e usada - aparece na tela, nao numa documentacao
    quando: str
    campos: tuple[str, ...]
    padrao: str
    exemplo: dict[str, str]


PROPOSTA = Modelo(
    chave="proposta",
    titulo="Proposta enviada",
    quando="No Orçamentos, ao mandar a proposta para o cliente decidir.",
    campos=("cliente", "empresa", "numero", "total", "validade", "pagamento",
            "prazo"),
    padrao=(
        "Olá, {cliente}! Aqui é da {empresa}.\n\n"
        "Sua proposta {numero} está pronta, no valor de {total}. "
        "Ela vale até {validade}.\n\n"
        "Qualquer dúvida é só chamar por aqui."
    ),
    exemplo={
        "cliente": "Mercado Bom Preço", "empresa": "Casa do Parafuso",
        "numero": "ORC-2026-0042", "total": "R$ 4.509,40",
        "validade": "16/09/2026", "pagamento": "50% na entrada",
        "prazo": "10 dias úteis",
    },
)

ORDEM_PRONTA = Modelo(
    chave="ordem_pronta",
    titulo="Serviço pronto para retirada",
    quando="Nas Ordens de Serviço, quando o serviço fica pronto.",
    campos=("cliente", "empresa", "numero", "equipamento", "total", "garantia"),
    # `{equipamento}` fica numa linha so dele porque o item e OPCIONAL: quem
    # instala, lava ou faz chave nao tem o que digitar ali. No meio da frase
    # ("Seu {equipamento} esta pronto") o campo vazio mandava "Seu esta pronto"
    # para o cliente; sozinho, ele so nao aparece.
    padrao=(
        "Olá, {cliente}! Aqui é da {empresa}.\n\n"
        "O seu serviço está pronto para retirada.\n"
        "{equipamento}\n"
        "Ordem {numero}, valor {total}.\n\n"
        "Estamos te esperando!"
    ),
    exemplo={
        "cliente": "Joana Ribeiro", "empresa": "Casa do Parafuso",
        "numero": "OS-2026-0117", "equipamento": "Notebook Dell",
        "total": "R$ 535,00", "garantia": "90 dias",
    },
)

COBRANCA = Modelo(
    chave="cobranca",
    titulo="Lembrete de vencimento",
    quando="No Financeiro, para uma conta a receber que está vencendo.",
    campos=("cliente", "empresa", "descricao", "valor", "vencimento", "dias"),
    padrao=(
        "Olá, {cliente}! Aqui é da {empresa}.\n\n"
        "Passando para lembrar de {descricao}, no valor de {valor}, "
        "com vencimento em {vencimento}.\n\n"
        "Se já tiver pago, é só desconsiderar esta mensagem."
    ),
    exemplo={
        "cliente": "Ana Paula Lima", "empresa": "Casa do Parafuso",
        "descricao": "parcela 2 de 3", "valor": "R$ 380,00",
        "vencimento": "05/09/2026", "dias": "4 dias",
    },
)

VENDA = Modelo(
    chave="venda",
    titulo="Agradecimento de venda",
    quando="No Vendas, depois de fechar a venda no balcão.",
    campos=("cliente", "empresa", "numero", "total", "data"),
    padrao=(
        "Olá, {cliente}! Aqui é da {empresa}.\n\n"
        "Obrigado pela preferência! Sua compra {numero} foi registrada "
        "aqui, no valor de {total}.\n\n"
        "Qualquer coisa é só chamar. Até a próxima!"
    ),
    exemplo={
        "cliente": "Maria Souza", "empresa": "Casa do Parafuso",
        "numero": "VEN-2026-0311", "total": "R$ 189,90", "data": "01/09/2026",
    },
)

COMPROMISSO = Modelo(
    chave="compromisso",
    titulo="Lembrete de compromisso",
    quando="Na Agenda, para confirmar um horário marcado.",
    campos=("cliente", "empresa", "titulo", "data", "hora"),
    padrao=(
        "Olá, {cliente}! Aqui é da {empresa}.\n\n"
        "Passando para confirmar o nosso compromisso: {titulo}, "
        "dia {data} às {hora}.\n\n"
        "Pode confirmar para mim?"
    ),
    exemplo={
        "cliente": "João da Silva", "empresa": "Casa do Parafuso",
        "titulo": "Visita técnica", "data": "03/09/2026", "hora": "14:30",
    },
)

ANIVERSARIO = Modelo(
    chave="aniversario",
    titulo="Aniversário do cliente",
    quando="No Clientes, na lista de aniversariantes do mês.",
    campos=("cliente", "empresa", "idade"),
    padrao=(
        "Olá, {cliente}! Feliz aniversário!\n\n"
        "Toda a equipe da {empresa} deseja um ótimo dia para você."
    ),
    exemplo={
        "cliente": "Carlos Menezes", "empresa": "Casa do Parafuso",
        "idade": "42 anos",
    },
)

MODELOS: tuple[Modelo, ...] = (
    PROPOSTA, ORDEM_PRONTA, COBRANCA, VENDA, COMPROMISSO, ANIVERSARIO,
)
POR_CHAVE = {modelo.chave: modelo for modelo in MODELOS}


# ------------------------------------------------------------------ preencher
def preencher(texto: str, dados: dict) -> str:
    """Troca os `{campos}` pelos valores.

    Campo que nao existe sai vazio, de proposito: um erro de digitacao no
    modelo nao pode derrubar o programa na frente do cliente. A tela de
    Configuracoes avisa antes, que e onde o aviso resolve alguma coisa.
    """

    def trocar(achado: re.Match) -> str:
        return str(dados.get(achado.group(1), "") or "")

    preenchido = CAMPO.sub(trocar, texto or "")
    return _limpar(preenchido)


def desconhecidos(texto: str, modelo: Modelo) -> list[str]:
    """Campos escritos no modelo que ninguem vai preencher."""
    usados = dict.fromkeys(CAMPO.findall(texto or ""))
    return [campo for campo in usados if campo not in modelo.campos]


def _limpar(texto: str) -> str:
    """Some com a sujeira que um campo vazio deixa para tras."""
    linhas = [re.sub(r"[ \t]{2,}", " ", linha).strip() for linha in texto.splitlines()]
    enxuto = "\n".join(linhas)
    enxuto = re.sub(r"\n{3,}", "\n\n", enxuto)
    # pontuacao orfa de campo vazio: "valor de , com" -> "valor de, com"
    enxuto = re.sub(r"\s+([,.!?])", r"\1", enxuto)
    return enxuto.strip()


# ----------------------------------------------------------------- guardadas
def carregar(settings, chave: str) -> str:
    """O texto que o cliente escreveu - ou o padrao, se nunca mexeu."""
    modelo = obter(chave)
    if settings is None:
        return modelo.padrao
    guardado = settings.get(SECAO, chave, "") or ""
    return guardado.strip() or modelo.padrao


def salvar(settings, chave: str, texto: str) -> str:
    """Guarda o texto. Texto vazio volta ao padrao, em vez de virar silencio."""
    modelo = obter(chave)
    texto = (texto or "").strip()
    settings.set(SECAO, chave, texto)
    settings.save()
    return texto or modelo.padrao


def restaurar(settings, chave: str) -> str:
    return salvar(settings, chave, "")


def obter(chave: str) -> Modelo:
    modelo = POR_CHAVE.get(chave)
    if modelo is None:
        raise MensagemError(f"Modelo de mensagem desconhecido: {chave}")
    return modelo


# --------------------------------------------------------------------- envio
def numero_internacional(telefone: str) -> str:
    """O numero como o `wa.me` quer: 55 + DDD + numero. Vazio se nao servir."""
    digitos = so_digitos(telefone or "")
    if digitos.startswith(DDI) and len(digitos) in (12, 13):
        return digitos
    if len(digitos) in (10, 11):
        return DDI + digitos
    return ""


def link(telefone: str, texto: str) -> str:
    numero = numero_internacional(telefone)
    if not numero:
        raise MensagemError(
            "Número de WhatsApp inválido. Use DDD e número, como (63) 98888-7777."
        )
    return f"https://wa.me/{numero}?text={quote(texto or '')}"


class Mensageiro:
    """Junta modelo guardado, dados do momento e o nome da empresa.

    Existe para que os aplicativos nao precisem conhecer nem as preferencias
    nem a empresa: eles pedem o texto de uma mensagem e recebem o texto.
    """

    def __init__(self, settings=None, empresa=None) -> None:
        self.settings = settings
        self.empresa = empresa

    def modelo(self, chave: str) -> str:
        return carregar(self.settings, chave)

    def texto(self, chave: str, dados: dict | None = None) -> str:
        dados = dict(dados or {})
        dados.setdefault("empresa", self._nome_da_empresa())
        return preencher(self.modelo(chave), dados)

    def previa(self, chave: str, texto: str | None = None) -> str:
        """Como fica com dados de exemplo - a tela nao manda ninguem 'testar'."""
        modelo = obter(chave)
        dados = dict(modelo.exemplo)
        if self._nome_da_empresa():
            dados["empresa"] = self._nome_da_empresa()
        return preencher(modelo.padrao if texto is None else texto, dados)

    def link(self, chave: str, telefone: str, dados: dict | None = None) -> str:
        return link(telefone, self.texto(chave, dados))

    def _nome_da_empresa(self) -> str:
        return getattr(self.empresa, "nome", "") or ""
