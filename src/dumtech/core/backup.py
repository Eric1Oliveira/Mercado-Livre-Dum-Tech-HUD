"""Copia de seguranca dos dados do cliente.

Tudo que o cliente digitou vive em `%APPDATA%\\DumTech Hub\\data`. HD que morre,
Windows reinstalado, ransomware, alguem que formata a maquina: sem copia, acabou
- e a culpa vai ser do programa, com razao.

**Copiar o arquivo .db com o programa aberto nao serve.** Os bancos ficam em
modo WAL: parte do que foi gravado esta no arquivo `-wal`, nao no `.db`, e uma
copia crua pode sair pela metade. Por isso aqui se usa a API de backup do
proprio SQLite (`Connection.backup`), que le um retrato consistente mesmo com o
programa em uso.

O resultado e um `.zip` unico: da para mandar por e-mail, jogar no pendrive ou
deixar numa pasta do Google Drive.

**Copia fora do computador** (`copiar_para_fora`): a copia local nao salva
ninguem de HD queimado, maquina formatada nem ransomware - ela morre junto. Por
isso o cliente pode apontar uma pasta que o OneDrive/Google Drive/Dropbox
sincroniza (ou um pendrive), e cada backup e duplicado para la. Falhar nisso
**nunca** estraga o backup local: o pendrive pode estar fora, a nuvem pode estar
pausada, e o que importa ja esta gravado.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
import pathlib
from pathlib import Path

from .paths import DataPaths, get_paths

#: nome do arquivo que descreve o backup por dentro
MANIFESTO = "backup.json"
#: versao do formato: se um dia mudar, da para recusar restaurar o errado
FORMATO = 1
#: quantas copias automaticas guardar antes de apagar a mais velha
MANTER = 10

PREFIXO = "dumtech-backup-"

#: quantas copias manter na pasta de fora (la o espaco costuma ser da nuvem)
MANTER_FORA = 30

#: pastas de nuvem mais comuns no Windows, na ordem em que sugerimos
_NUVENS = (
    ("OneDrive", "OneDrive"),
    ("Google Drive", "Meu Drive"),
    ("Google Drive", "My Drive"),
    ("Dropbox", "Dropbox"),
)


class BackupError(Exception):
    """Erro ao copiar ou restaurar (mensagem pronta para o usuario)."""


@dataclass(frozen=True)
class Backup:
    """Um arquivo de backup ja gravado."""

    arquivo: Path
    criado_em: str
    bancos: tuple[str, ...] = ()
    versao: str = ""
    automatico: bool = False

    @property
    def tamanho(self) -> int:
        try:
            return self.arquivo.stat().st_size
        except OSError:
            return 0

    @property
    def momento(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.criado_em)
        except (TypeError, ValueError):
            return None


def _copia_consistente(origem: Path, destino: Path) -> None:
    """Retrato do banco pela API do SQLite - seguro com o programa aberto."""
    fonte = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
    try:
        alvo = sqlite3.connect(destino)
        try:
            fonte.backup(alvo)
        finally:
            alvo.close()
    finally:
        fonte.close()


def _bancos(paths: DataPaths) -> list[Path]:
    """Todo arquivo .db da plataforma, do Hub e dos aplicativos."""
    encontrados: list[Path] = []
    for pasta in (paths.data_dir, paths.apps_data_dir):
        if pasta.exists():
            encontrados += sorted(p for p in pasta.glob("*.db") if p.is_file())
    return encontrados


def nome_do_arquivo(momento: datetime | None = None, automatico: bool = False) -> str:
    quando = (momento or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    return f"{PREFIXO}{quando}{'-auto' if automatico else ''}.zip"


def _sem_colisao(arquivo: Path) -> Path:
    """Dois backups no mesmo segundo nao podem se sobrescrever em silencio.

    O nome so tem resolucao de segundo. Clicar duas vezes em "Fazer backup"
    apagaria a primeira copia sem avisar - justamente o contrario do que este
    modulo existe para fazer.
    """
    if not arquivo.exists():
        return arquivo
    for contador in range(2, 100):
        candidato = arquivo.with_name(f"{arquivo.stem}-{contador}{arquivo.suffix}")
        if not candidato.exists():
            return candidato
    raise BackupError("Backups demais no mesmo segundo. Tente de novo.")


def criar(
    destino: Path,
    paths: DataPaths | None = None,
    automatico: bool = False,
    versao: str = "",
) -> Backup:
    """Grava um `.zip` com todos os bancos e a configuracao.

    A licenca fica de fora de proposito: ela e amarrada a maquina, e restaurar
    a licenca de um computador em outro so criaria confusao.
    """
    paths = paths or get_paths()
    bancos = _bancos(paths)
    if not bancos:
        raise BackupError("Nao ha nenhum dado para copiar ainda.")

    destino = Path(destino)
    try:
        destino.mkdir(parents=True, exist_ok=True)
    except OSError as erro:
        raise BackupError(f"Nao foi possivel usar a pasta {destino}: {erro}") from erro

    momento = datetime.now()
    arquivo = _sem_colisao(destino / nome_do_arquivo(momento, automatico))
    manifesto = {
        "formato": FORMATO,
        "criado_em": momento.isoformat(timespec="seconds"),
        "versao": versao,
        "automatico": automatico,
        "bancos": [b.name for b in bancos],
    }

    with tempfile.TemporaryDirectory(prefix="dumtech_backup_") as temporario:
        pasta = Path(temporario)
        for banco in bancos:
            try:
                _copia_consistente(banco, pasta / banco.name)
            except sqlite3.Error as erro:
                raise BackupError(f"Nao foi possivel copiar {banco.name}: {erro}") from erro

        try:
            with zipfile.ZipFile(arquivo, "w", zipfile.ZIP_DEFLATED) as pacote:
                pacote.writestr(MANIFESTO, json.dumps(manifesto, indent=2))
                for banco in bancos:
                    pacote.write(pasta / banco.name, f"data/{banco.name}")
                config = paths.settings_file
                if config.exists():
                    pacote.write(config, f"config/{config.name}")
        except OSError as erro:
            arquivo.unlink(missing_ok=True)
            raise BackupError(f"Nao foi possivel gravar o backup: {erro}") from erro

    return Backup(
        arquivo=arquivo,
        criado_em=manifesto["criado_em"],
        bancos=tuple(manifesto["bancos"]),
        versao=versao,
        automatico=automatico,
    )


# ---------------------------------------------------------- fora daqui -----
def nuvens_encontradas() -> list[Path]:
    """Pastas de nuvem que existem neste computador (para sugerir ao cliente)."""
    achadas: list[Path] = []
    casa = Path.home()
    candidatos = [Path(os.environ[c]) for c in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")
                  if os.environ.get(c)]
    for marca, pasta in _NUVENS:
        candidatos.append(casa / pasta)
        candidatos.append(casa / marca / pasta)
    for caminho in candidatos:
        try:
            if caminho.is_dir() and caminho not in achadas:
                achadas.append(caminho)
        except OSError:
            continue
    return achadas


def copiar_para_fora(copia: Backup, pasta: Path, manter: int = MANTER_FORA) -> Path:
    """Duplica o backup numa pasta de nuvem/pendrive. Levanta `BackupError` se nao der.

    Quem chama trata o erro como recado na tela, nunca como falha do backup: o
    arquivo local ja esta gravado quando esta funcao roda.
    """
    pasta = Path(pasta)
    if not pasta:
        raise BackupError("Nenhuma pasta escolhida para a copia de fora.")
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        destino = _sem_colisao(pasta / copia.arquivo.name)
        shutil.copy2(copia.arquivo, destino)
    except OSError as erro:
        raise BackupError(
            f"Nao foi possivel copiar para {pasta}: {erro}. "
            "O backup no computador foi feito normalmente."
        ) from erro

    # a pasta de fora tambem nao pode crescer para sempre
    try:
        antigos = sorted(pasta.glob(f"{PREFIXO}*.zip"), key=lambda a: a.name, reverse=True)
        for velho in antigos[max(int(manter), 1):]:
            velho.unlink(missing_ok=True)
    except OSError:
        pass   # limpar e conforto, nao obrigacao
    return destino


def ler_manifesto(arquivo: Path) -> Backup:
    """Le o backup sem restaurar nada."""
    arquivo = Path(arquivo)
    try:
        with zipfile.ZipFile(arquivo) as pacote:
            dados = json.loads(pacote.read(MANIFESTO))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as erro:
        raise BackupError(
            f"'{arquivo.name}' nao e um backup do DumTech Hub."
        ) from erro

    if int(dados.get("formato", 0)) > FORMATO:
        raise BackupError(
            f"'{arquivo.name}' foi feito por uma versao mais nova do programa."
        )
    return Backup(
        arquivo=arquivo,
        criado_em=str(dados.get("criado_em", "")),
        bancos=tuple(dados.get("bancos", ())),
        versao=str(dados.get("versao", "")),
        automatico=bool(dados.get("automatico", False)),
    )


def listar(pasta: Path) -> list[Backup]:
    """Os backups de uma pasta, do mais novo para o mais velho."""
    pasta = Path(pasta)
    if not pasta.exists():
        return []
    achados = []
    for arquivo in pasta.glob(f"{PREFIXO}*.zip"):
        try:
            achados.append(ler_manifesto(arquivo))
        except BackupError:
            continue  # arquivo estranho na pasta: ignora em vez de quebrar
    return sorted(achados, key=lambda b: b.criado_em, reverse=True)


def limpar_antigos(pasta: Path, manter: int = MANTER) -> int:
    """Apaga as copias **automaticas** mais velhas. As manuais nunca somem."""
    automaticos = [b for b in listar(pasta) if b.automatico]
    sobrando = automaticos[max(int(manter), 1):]
    for backup in sobrando:
        backup.arquivo.unlink(missing_ok=True)
    return len(sobrando)


def restaurar(arquivo: Path, paths: DataPaths | None = None) -> list[str]:
    """Devolve os bancos do backup para a pasta de dados.

    Quem chama **precisa** ter fechado todas as conexoes antes: substituir um
    arquivo que o SQLite tem aberto deixa o programa lendo dados velhos, ou pior.
    Devolve os nomes dos bancos restaurados.
    """
    paths = (paths or get_paths()).ensure()
    ler_manifesto(arquivo)  # valida antes de mexer em qualquer coisa

    restaurados: list[str] = []
    with zipfile.ZipFile(arquivo) as pacote:
        for nome in pacote.namelist():
            if not nome.startswith("data/") or not nome.endswith(".db"):
                continue
            banco = Path(nome).name
            # o banco de um aplicativo mora em data/apps; o resto em data
            destino = (
                paths.apps_data_dir / banco
                if _e_de_aplicativo(banco, paths)
                else paths.data_dir / banco
            )
            destino.parent.mkdir(parents=True, exist_ok=True)
            with pacote.open(nome) as origem, open(destino, "wb") as saida:
                shutil.copyfileobj(origem, saida)
            # WAL velho ao lado de banco novo e receita de corrupcao: se nao
            # der para apagar, alguem ainda esta com o banco aberto e restaurar
            # seria pior do que nao restaurar
            for sobra in ("-wal", "-shm"):
                try:
                    pathlib.Path(f"{destino}{sobra}").unlink(missing_ok=True)
                except OSError as erro:
                    raise BackupError(
                        f"O banco '{banco}' ainda esta em uso. Feche o DumTech "
                        "Hub e abra de novo antes de restaurar."
                    ) from erro
            restaurados.append(banco)

    if not restaurados:
        raise BackupError("O backup nao tem nenhum banco de dados dentro.")
    return sorted(restaurados)


def _e_de_aplicativo(banco: str, paths: DataPaths) -> bool:
    """hub.db e plataforma.db moram em data/; o resto e de aplicativo."""
    return banco not in {paths.hub_db.name, paths.platform_db.name}


def pasta_padrao(paths: DataPaths | None = None) -> Path:
    """Onde as copias automaticas ficam se o cliente nao escolher outra."""
    return (paths or get_paths()).root / "backups"
