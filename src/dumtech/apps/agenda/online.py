"""Agendamento online: o lado do Hub.

O QUE MORA AQUI (sem tela e sem rede)
    * `AjustesOnline` - o que o dono escolheu: servicos, horario de
      atendimento e regras. Fica na tabela `ajustes` do agenda.db, porque o
      link e DESTE computador e vai no backup junto com os compromissos;
    * `config_do_servidor` - o que a pagina publica precisa saber, com a
      empresa e o logotipo de Minha empresa;
    * `Sincronia` - a conversa periodica com o servidor, no contrato de
      `core/online.py`: `preparar` le o banco, o Hub chama o servidor em
      segundo plano e `aplicar` grava o que chegou.

O QUE SAI DESTE COMPUTADOR
    Os horarios ocupados - inicio, minutos e se e bloqueio. Nunca titulo,
    cliente, telefone ou observacao (ver `AgendaRepository.ocupados`).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable

from ...core.documentos import so_digitos
from ...core.online import Resultado
from .models import DIAS_CURTOS, DIAS_SEMANA, AgendaError, Expediente

logger = logging.getLogger(__name__)

#: funcoes do servidor (supabase/migrations/20261026130000_agendamento_online.sql)
SALVAR = "dumtech_agenda_salvar"
SINCRONIZAR = "dumtech_agenda_sincronizar"

#: o caminho da pagina no site da DumTech
CAMINHO = "/agendar/"

#: id, nome na tela, cor. Todas com contraste AA para texto branco (>= 4,5:1).
CORES = (
    ("violeta", "Violeta", "#6A4CE8"),
    ("rosa", "Rosa", "#C2185B"),
    ("vinho", "Vinho", "#8E2443"),
    ("terracota", "Terracota", "#B0432A"),
    ("verde", "Verde", "#1B7A4B"),
    ("petroleo", "Petróleo", "#0E6E78"),
    ("azul", "Azul", "#2456C2"),
    ("grafite", "Grafite", "#3A4150"),
)
COR_PADRAO = "violeta"

PASSOS = (10, 15, 20, 30, 45, 60)
#: o "Horarios a cada" do link antes da aba Servicos, para quem nunca mexeu
PASSO_PADRAO = 30
MAXIMO_SERVICOS = 20
MAXIMO_VAGAS = 10
MAXIMO_DIAS = 90
#: antecedencia e prazo de cancelar: ate uma semana (em minutos)
MAXIMO_MINUTOS = 7 * 24 * 60
LIMITE_MENSAGEM = 280

#: o logotipo viaja dentro da configuracao: pequeno de proposito
LADO_LOGO = 160
LIMITE_LOGO = 48000

# chaves da tabela `ajustes`
CHAVE_AJUSTES = "online.ajustes"
CHAVE_ATIVO = "online.ativo"
CHAVE_SLUG = "online.slug"
CHAVE_PUBLICADA = "online.publicada"
CHAVE_NOVO_ENDERECO = "online.novo_endereco"
CHAVE_PUBLICADO_EM = "online.publicado_em"
CHAVE_ERRO = "online.erro"


# ------------------------------------------------------------------ ajustes --
def passo_padrao(duracao: int, limite: int = PASSO_PADRAO) -> int:
    """De quanto em quanto tempo o servico aparece, se o dono nao escolheu.

    No tempo dele - a barba de 15 min, de 15 em 15 -, arredondado para baixo
    na lista de passos e sem passar de `limite` (o passo geral do link). E a
    regra do servidor para link de Hub antigo (`dumtech_agenda_passo`).
    """
    cabem = [passo for passo in PASSOS if passo <= int(duracao)]
    return min(max(cabem) if cabem else PASSOS[0], int(limite))


def horarios_no_dia(intervalos, duracao: int, passo: int) -> list[int]:
    """Os inicios (minutos do dia) que o link oferece num dia sem ninguem.

    A conta do servidor (`dumtech_agenda_livres`) sem os ocupados: cabe inteiro
    num pedaco aberto, de `passo` em `passo` a partir do comeco do pedaco.
    """
    return [inicio for de, ate in intervalos
            for inicio in range(int(de), int(ate) - int(duracao) + 1, int(passo))]


@dataclass
class Servico:
    id: str
    nome: str
    duracao: int = 60
    #: None = a pagina nao mostra preco
    preco: float | None = None
    #: de quanto em quanto tempo aparece no link (um de PASSOS). 0 = ninguem
    #: escolheu (gravado antes da aba Servicos): vale o `passo_padrao`
    passo: int = 0


@dataclass
class Dia:
    """Um dia da semana no horario de atendimento (minutos desde a meia-noite)."""

    aberto: bool = True
    abre: int = 9 * 60
    fecha: int = 18 * 60
    almoco: bool = True
    almoco_de: int = 12 * 60
    almoco_ate: int = 13 * 60

    def intervalos(self) -> list[list[int]]:
        """Os pedacos abertos do dia. O almoco e o vao entre dois."""
        if not self.aberto or self.fecha <= self.abre:
            return []
        if self.almoco and self.abre < self.almoco_de < self.almoco_ate < self.fecha:
            return [[self.abre, self.almoco_de], [self.almoco_ate, self.fecha]]
        return [[self.abre, self.fecha]]


@dataclass
class AjustesOnline:
    servicos: list[Servico] = field(default_factory=list)
    #: segunda a domingo
    semana: list[Dia] = field(default_factory=list)
    #: o passo geral de antes da aba Servicos. Saiu da tela: e o teto do
    #: padrao de cada servico, e o servidor ainda o exige
    passo: int = PASSO_PADRAO
    vagas: int = 1
    antecedencia: int = 120
    dias: int = 30
    cancelar_ate: int = 180
    mensagem: str = ""
    cor: str = COR_PADRAO

    @classmethod
    def padrao(cls) -> "AjustesOnline":
        """O link nasce funcionando: seg a sex 9h-18h com almoco, sabado de manha."""
        semana = [Dia() for _ in range(5)]
        semana.append(Dia(abre=9 * 60, fecha=13 * 60, almoco=False))
        semana.append(Dia(aberto=False))
        return cls(servicos=[Servico("s1", "Atendimento", 60)], semana=semana)

    def expediente(self) -> Expediente:
        """O horario de atendimento do jeito que a grade da Agenda usa."""
        semana = self.semana if len(self.semana) == 7 else AjustesOnline.padrao().semana
        return Expediente(
            semana=tuple(tuple((de, ate) for de, ate in dia.intervalos()) for dia in semana),
            vagas=self.vagas,
        )

    def passo_de(self, servico: Servico) -> int:
        """De quanto em quanto tempo o servico aparece no link."""
        return int(servico.passo) or passo_padrao(servico.duracao, self.passo)

    def validar(self) -> None:
        """Erro de preenchimento vira frase para o dono, nao codigo do servidor."""
        if not self.servicos:
            raise AgendaError("Cadastre pelo menos um serviço.")
        if len(self.servicos) > MAXIMO_SERVICOS:
            raise AgendaError(f"No máximo {MAXIMO_SERVICOS} serviços no link.")
        for servico in self.servicos:
            if not servico.nome.strip():
                raise AgendaError("Dê um nome a cada serviço.")
            if not 5 <= int(servico.duracao) <= 720:
                raise AgendaError(f"{servico.nome}: a duração vai de 5 minutos a 12 horas.")
            if servico.preco is not None and servico.preco < 0:
                raise AgendaError(f"{servico.nome}: o preço não pode ser negativo.")
            if servico.passo and servico.passo not in PASSOS:
                raise AgendaError(f"{servico.nome}: escolha de quanto em quanto tempo o horário aparece.")
        if len(self.semana) != 7:
            raise AgendaError("Faltam dias no horário de atendimento.")
        if not any(dia.intervalos() for dia in self.semana):
            raise AgendaError("Abra pelo menos um dia da semana.")
        for nome, dia in zip(DIAS_SEMANA, self.semana):
            if not dia.aberto:
                continue
            if dia.fecha <= dia.abre:
                raise AgendaError(f"{nome}: o horário de fechar precisa ser depois do de abrir.")
            if dia.almoco and not dia.abre < dia.almoco_de < dia.almoco_ate < dia.fecha:
                raise AgendaError(f"{nome}: o almoço precisa ficar dentro do horário de atendimento.")
        if self.passo not in PASSOS:
            raise AgendaError("Escolha de quanto em quanto tempo os horários aparecem.")
        if not 1 <= self.vagas <= MAXIMO_VAGAS:
            raise AgendaError(f"As vagas por horário vão de 1 a {MAXIMO_VAGAS}.")
        if not 1 <= self.dias <= MAXIMO_DIAS:
            raise AgendaError(f"A agenda pode ficar aberta de 1 a {MAXIMO_DIAS} dias.")
        if not 0 <= self.antecedencia <= MAXIMO_MINUTOS or not 0 <= self.cancelar_ate <= MAXIMO_MINUTOS:
            raise AgendaError("Antecedência e prazo de cancelamento vão até 7 dias.")
        if len(self.mensagem) > LIMITE_MENSAGEM:
            raise AgendaError(f"O recado da página tem no máximo {LIMITE_MENSAGEM} letras.")
        if self.cor not in {cor for cor, _, _ in CORES}:
            raise AgendaError("Escolha uma das cores da lista.")

    def novo_id_de_servico(self) -> str:
        usados = {s.id for s in self.servicos}
        numero = len(usados) + 1
        while f"s{numero}" in usados:
            numero += 1
        return f"s{numero}"

    # ---------------------------------------------------------------- arquivo
    def para_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def de_json(cls, texto: str) -> "AjustesOnline":
        try:
            dados = json.loads(texto)
            padrao = cls.padrao()
            semana = [Dia(**d) for d in dados.get("semana") or []]
            return cls(
                servicos=[Servico(**s) for s in dados.get("servicos") or []],
                semana=semana if len(semana) == 7 else padrao.semana,
                **{chave: dados[chave] for chave in
                   ("passo", "vagas", "antecedencia", "dias", "cancelar_ate", "mensagem", "cor")
                   if chave in dados},
            )
        except (TypeError, ValueError):
            logger.warning("Ajustes do agendamento online ilegiveis: voltando ao padrao")
            return cls.padrao()


# --------------------------------------------------------- o que viaja -------
def slug_de(nome: str) -> str:
    """"Beauty & Cia" -> "beauty-cia": a sugestao de endereco do link."""
    sem_acento = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    pedacos = "".join(c if c.isalnum() else " " for c in sem_acento.lower()).split()
    return "-".join(pedacos)[:30].strip("-")


def whatsapp_da_empresa(empresa) -> str:
    """So digitos, com o 55 na frente: o que o botao da pagina precisa."""
    digitos = so_digitos(getattr(empresa, "whatsapp", "") or getattr(empresa, "telefone", ""))
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    return digitos if 12 <= len(digitos) <= 15 else ""


def endereco_curto(empresa) -> str:
    """"Rua das Flores, 120 · Centro · Santo André/SP" - o que a pagina mostra."""
    rua = ", ".join(p for p in (empresa.endereco.strip(), empresa.numero.strip()) if p)
    cidade = "/".join(p for p in (empresa.cidade.strip(), empresa.uf.strip()) if p)
    return " · ".join(p for p in (rua, empresa.bairro.strip(), cidade) if p)[:160]


def logo_em_data_uri(caminho) -> str:
    """O logotipo reduzido (160 px no maior lado) e pronto para viajar."""
    if caminho is None:
        return ""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QImage

    imagem = QImage(str(caminho))
    if imagem.isNull():
        return ""
    if max(imagem.width(), imagem.height()) > LADO_LOGO:
        imagem = imagem.scaled(LADO_LOGO, LADO_LOGO, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
    tentativas = [("PNG", -1, "image/png")] if imagem.hasAlphaChannel() else []
    tentativas += [("JPG", 85, "image/jpeg"), ("JPG", 65, "image/jpeg")]
    for formato, qualidade, tipo in tentativas:
        if formato == "JPG" and imagem.hasAlphaChannel():
            # sem transparencia no JPEG: fundo branco, como o papel do recibo
            fundo = QImage(imagem.size(), QImage.Format.Format_RGB32)
            fundo.fill(Qt.GlobalColor.white)
            from PySide6.QtGui import QPainter
            pintor = QPainter(fundo)
            pintor.drawImage(0, 0, imagem)
            pintor.end()
            imagem = fundo
        dados = QByteArray()
        buffer = QBuffer(dados)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        imagem.save(buffer, formato, qualidade)
        buffer.close()
        texto = f"data:{tipo};base64," + base64.b64encode(bytes(dados)).decode("ascii")
        if len(texto) <= LIMITE_LOGO:
            return texto
    return ""


def config_do_servidor(ajustes: AjustesOnline, empresa, logo: str = "") -> dict:
    """O que a pagina publica sabe: a empresa, os servicos e as regras."""
    return {
        "v": 1,
        "empresa": {
            "nome": (empresa.nome or "").strip()[:80] or "Agenda",
            "endereco": endereco_curto(empresa),
            "whatsapp": whatsapp_da_empresa(empresa),
            "logo": logo,
        },
        "mensagem": ajustes.mensagem.strip()[:LIMITE_MENSAGEM],
        "cor": ajustes.cor,
        "servicos": [
            {"id": s.id, "nome": s.nome.strip()[:80], "duracao": int(s.duracao),
             "preco": None if s.preco is None else round(float(s.preco), 2),
             "passo": ajustes.passo_de(s)}
            for s in ajustes.servicos
        ],
        "semana": [dia.intervalos() for dia in ajustes.semana],
        "passo": ajustes.passo,
        "vagas": ajustes.vagas,
        "antecedencia": ajustes.antecedencia,
        "dias": ajustes.dias,
        "cancelar_ate": ajustes.cancelar_ate,
    }


def link_publico(slug: str) -> str:
    """O endereco que o dono manda para os clientes."""
    from ...core.loja import URL_PADRAO, url_base

    if not slug:
        return ""
    base = url_base()
    if not base.startswith("https://"):  # a copia local da loja nao abre no celular do cliente
        base = URL_PADRAO
    return f"{base.rstrip('/')}{CAMINHO}{slug}"


def fuso_em_minutos() -> int:
    """-180 em Brasilia: o servidor soma isto ao UTC para saber a hora da loja."""
    deslocamento = datetime.now().astimezone().utcoffset()
    return int(deslocamento.total_seconds() // 60) if deslocamento else -180


def quando(compromisso) -> str:
    """"qui 30/10, 14:00" - o horario no aviso."""
    inicio = compromisso.inicio_dt
    if inicio is None:
        return ""
    return f"{DIAS_CURTOS[inicio.weekday()].lower()} {inicio:%d/%m}, {inicio:%H:%M}"


def _marca(valor) -> str:
    return hashlib.sha1(json.dumps(valor, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ estado --
class Online:
    """O estado do link deste computador, guardado no agenda.db."""

    def __init__(self, repository) -> None:
        self.repository = repository

    @property
    def criado(self) -> bool:
        # os servicos podem estar gravados antes do link (aba Servicos): quem
        # diz que o link existe e o ligado/pausado, gravado so ao criar
        return bool(self.repository.ajuste(CHAVE_ATIVO))

    def ajustes(self) -> AjustesOnline:
        texto = self.repository.ajuste(CHAVE_AJUSTES)
        return AjustesOnline.de_json(texto) if texto else AjustesOnline.padrao()

    @property
    def ativo(self) -> bool:
        return self.repository.ajuste(CHAVE_ATIVO, "1") == "1"

    @property
    def slug(self) -> str:
        return self.repository.ajuste(CHAVE_SLUG)

    @property
    def link(self) -> str:
        return link_publico(self.slug)

    @property
    def quer_endereco_novo(self) -> bool:
        return self.repository.ajuste(CHAVE_NOVO_ENDERECO) == "1"

    @property
    def publicado_em(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.repository.ajuste(CHAVE_PUBLICADO_EM))
        except ValueError:
            return None

    @property
    def erro(self) -> str:
        return self.repository.ajuste(CHAVE_ERRO)

    def salvar(self, ajustes: AjustesOnline, ativo: bool) -> None:
        """Grava aqui. Quem publica e a proxima conversa com o servidor."""
        ajustes.validar()
        self.repository.definir_ajuste(CHAVE_AJUSTES, ajustes.para_json())
        self.repository.definir_ajuste(CHAVE_ATIVO, "1" if ativo else "0")

    def salvar_servicos(self, servicos: list[Servico]) -> None:
        """So os servicos (aba Servicos): o resto dos ajustes e o link ficam como estao."""
        ajustes = self.ajustes()
        ajustes.servicos = list(servicos)
        ajustes.validar()
        self.repository.definir_ajuste(CHAVE_AJUSTES, ajustes.para_json())

    def pedir_endereco_novo(self) -> None:
        self.repository.definir_ajuste(CHAVE_NOVO_ENDERECO, "1")

    def anotar_erro(self, texto: str) -> None:
        if texto != self.erro:
            self.repository.definir_ajuste(CHAVE_ERRO, texto)

    def marcar_publicado(self) -> None:
        self.repository.definir_ajuste(CHAVE_PUBLICADO_EM, datetime.now().isoformat(timespec="seconds"))
        self.anotar_erro("")

    # ----------------------------------------------------------- publicar
    def pedido_salvar(self, empresa, logo: str = "") -> tuple[str, dict]:
        config = config_do_servidor(self.ajustes(), empresa, logo)
        return SALVAR, {
            "p_ativo": self.ativo,
            "p_config": config,
            "p_sugestao": slug_de(config["empresa"]["nome"]),
            "p_novo_endereco": self.quer_endereco_novo,
        }

    def precisa_salvar(self, params: dict) -> bool:
        """A configuracao (ou a empresa, ou o ligado) mudou desde a ultima publicacao?"""
        return self.quer_endereco_novo or self._marca_salva(params) != self.repository.ajuste(CHAVE_PUBLICADA)

    def registrar_salvo(self, params: dict, resposta: dict) -> None:
        self.repository.definir_ajuste(CHAVE_SLUG, str(resposta.get("slug") or ""))
        self.repository.definir_ajuste(CHAVE_PUBLICADA, self._marca_salva(params))
        self.repository.definir_ajuste(CHAVE_NOVO_ENDERECO, "")
        self.marcar_publicado()

    @staticmethod
    def _marca_salva(params: dict) -> str:
        return _marca([params.get("p_config"), bool(params.get("p_ativo"))])


# --------------------------------------------------------------- sincronia --
class Sincronia:
    """A conversa periodica com o servidor (contrato de `core/online.py`).

    Publica os ocupados quando a agenda muda, busca a cada 20 segundos o que
    os clientes marcaram, e confirma o recebimento junto com os ocupados novos.
    """

    #: mesmo sem mudanca, pergunta ao servidor de quanto em quanto tempo. Um
    #: minuto era lento demais: o cliente marcava e o dono reabria o Hub achando
    #: que nao tinha chegado. Com o relogio do Hub (10 s), da uma conversa a cada
    #: 20 s - 180 por hora, dentro do limite do servidor (240).
    INTERVALO_S = 18
    #: depois de um erro: sem internet tenta logo; recusa do servidor, bem depois
    ESPERA_REDE_S = 60
    ESPERA_RECUSA_S = 10 * 60

    def __init__(self, paths, empresa: Callable[[], object],
                 relogio: Callable[[], float] = time.monotonic) -> None:
        self.paths = paths
        self._empresa = empresa
        self._relogio = relogio
        self._marca = ""
        self._quando = float("-inf")
        self._espera_ate = 0.0
        self._recebidas: list[str] = []
        self._canceladas: list[str] = []
        self._logo: tuple[str, str] = ("", "")

    def _abrir(self):
        from .database import open_database
        from .repository import AgendaRepository

        banco = open_database(self.paths.app_db("agenda"))
        return banco, AgendaRepository(banco)

    def logo(self, empresa) -> str:
        """O logotipo pronto para viajar - refeito so quando o arquivo muda."""
        caminho = empresa.caminho_logo(self.paths) if hasattr(empresa, "caminho_logo") else None
        if caminho is None:
            return ""
        try:
            marca = f"{caminho}:{caminho.stat().st_mtime_ns}"
        except OSError:
            return ""
        if self._logo[0] != marca:
            self._logo = (marca, logo_em_data_uri(caminho))
        return self._logo[1]

    def preparar(self, agora: float | None = None) -> tuple[str, dict] | None:
        agora = self._relogio() if agora is None else agora
        if agora < self._espera_ate:
            return None
        banco, repo = self._abrir()
        try:
            online = Online(repo)
            if not online.criado:
                return None
            empresa = self._empresa()
            pedido = online.pedido_salvar(empresa, self.logo(empresa))
            if online.precisa_salvar(pedido[1]):
                return pedido

            hoje = date.today()
            ocupados = repo.ocupados(hoje, hoje + timedelta(days=online.ajustes().dias + 1))
            mudou = _marca(ocupados) != self._marca
            confirmar = bool(self._recebidas or self._canceladas)
            if not mudou and not confirmar and agora - self._quando < self.INTERVALO_S:
                return None
            params: dict = {"p_recebidas": list(self._recebidas),
                            "p_canceladas": list(self._canceladas)}
            # confirmar o recebimento so vale junto com o retrato novo
            if mudou or self._recebidas:
                params["p_ocupados"] = ocupados
                params["p_fuso"] = fuso_em_minutos()
            return SINCRONIZAR, params
        finally:
            banco.close()

    def aplicar(self, funcao: str, params: dict, resposta: dict) -> Resultado:
        self._espera_ate = 0.0
        banco, repo = self._abrir()
        try:
            online = Online(repo)
            if funcao == SALVAR:
                online.registrar_salvo(params, resposta)
                self._marca = ""  # os ocupados vao logo em seguida
                return Resultado(de_novo=True)
            return self._sincronizado(repo, online, params, resposta)
        finally:
            banco.close()

    def falhou(self, funcao: str, erro: Exception) -> None:
        codigo = getattr(erro, "codigo", "")
        rede = codigo in ("sem_internet", "servidor", "")
        self._espera_ate = self._relogio() + (self.ESPERA_REDE_S if rede else self.ESPERA_RECUSA_S)
        banco, repo = self._abrir()
        try:
            Online(repo).anotar_erro(str(erro))
        finally:
            banco.close()

    def _sincronizado(self, repo, online: Online, params: dict, resposta: dict) -> Resultado:
        self._quando = self._relogio()
        if not resposta.get("link"):
            # o servidor nao conhece o link desta maquina: publica de novo
            repo.definir_ajuste(CHAVE_PUBLICADA, "")
            return Resultado(de_novo=True)
        if "p_ocupados" in params:
            self._marca = _marca(params["p_ocupados"])
        # o que foi confirmado nesta conversa sai das listas
        enviadas = set(params.get("p_recebidas") or [])
        self._recebidas = [c for c in self._recebidas if c not in enviadas]
        aplicadas = set(params.get("p_canceladas") or [])
        self._canceladas = [c for c in self._canceladas if c not in aplicadas]
        if resposta.get("slug") and resposta["slug"] != online.slug:
            repo.definir_ajuste(CHAVE_SLUG, str(resposta["slug"]))

        resultado = Resultado()
        for reserva in resposta.get("novas") or []:
            codigo = str(reserva.get("id") or "")
            try:
                novo = repo.importar_reserva(reserva)
            except (AgendaError, TypeError, ValueError) as erro:
                # confirmada assim mesmo: senao o servidor mandaria para sempre
                logger.warning("Reserva do link ignorada (%s): %s", codigo, erro)
                novo = None
            if codigo and codigo not in self._recebidas:
                self._recebidas.append(codigo)
            if novo is not None:
                resultado.mudou = True
                resultado.alvo = novo.inicio
                resultado.avisos.append(
                    f"Novo agendamento pelo link · {novo.cliente or novo.titulo} · {quando(novo)}")
        for codigo in resposta.get("canceladas") or []:
            codigo = str(codigo)
            cancelado = repo.cancelar_reserva(codigo)
            if codigo not in self._canceladas:
                self._canceladas.append(codigo)
            if cancelado is not None:
                resultado.mudou = True
                resultado.alvo = cancelado.inicio
                resultado.avisos.append(
                    f"Cancelado pelo cliente · {cancelado.cliente or cancelado.titulo} · {quando(cancelado)}")
        resultado.de_novo = bool(self._recebidas or self._canceladas)
        online.marcar_publicado()
        return resultado
