r"""Onde a plataforma DumTech guarda os arquivos no computador do cliente.

Regra geral: o programa pode ser instalado em "Arquivos de Programas" (pasta
somente leitura), portanto NADA e gravado ao lado do executavel. Todos os dados
ficam na pasta do usuario:

    %APPDATA%\DumTech Hub\
        config\      -> configuracoes do Hub e licenca
        data\        -> banco de dados do Hub
        data\apps\  -> um banco de dados por aplicativo
        logs\        -> registro de erros

Durante o desenvolvimento e possivel apontar tudo para outra pasta definindo a
variavel de ambiente DUMTECH_DATA_DIR (usado tambem pelos testes).

A pasta fica OCULTA no Windows (`ocultar`): cliente curioso que abria a pasta
e apagava ou "arrumava" um banco transformava o programa em erro na abertura.
Oculta nao e trancada - o programa, o backup e o suporte continuam lendo e
gravando normalmente; ela so sai da frente de quem esta navegando.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Nome da pasta criada dentro de %APPDATA%.
APP_FOLDER_NAME = "DumTech Hub"

#: Variavel de ambiente que permite trocar a pasta de dados (dev/testes).
ENV_DATA_DIR = "DUMTECH_DATA_DIR"

#: atributo "oculto" do Windows (FILE_ATTRIBUTE_HIDDEN)
_OCULTO = 0x2
_ATRIBUTO_INVALIDO = 0xFFFFFFFF

logger = logging.getLogger(__name__)


def ocultar(pasta: Path) -> bool:
    """Marca a pasta como oculta no Windows. Nunca levanta.

    So acrescenta o atributo: nada e movido, renomeado ou trancado, entao
    quem le e grava ali (o proprio programa, o backup) segue igual. Fora do
    Windows nao faz nada. Devolve True quando a pasta ficou oculta.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        kernel = ctypes.windll.kernel32
        kernel.GetFileAttributesW.restype = ctypes.c_uint32
        atuais = kernel.GetFileAttributesW(str(pasta))
        if atuais == _ATRIBUTO_INVALIDO:
            return False
        if atuais & _OCULTO:
            return True
        return bool(kernel.SetFileAttributesW(str(pasta), atuais | _OCULTO))
    except Exception:  # noqa: BLE001 - pasta visivel incomoda, programa parado nao
        logger.warning("Nao foi possivel ocultar a pasta %s", pasta, exc_info=True)
        return False


def _default_root() -> Path:
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        return Path(override).expanduser()

    appdata = os.environ.get("APPDATA")
    if appdata:  # Windows
        return Path(appdata) / APP_FOLDER_NAME
    # Fallback para outros sistemas (uso em desenvolvimento).
    return Path.home() / ".dumtech-hub"


@dataclass(frozen=True)
class DataPaths:
    """Pastas e arquivos usados pela plataforma."""

    root: Path

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def apps_data_dir(self) -> Path:
        return self.data_dir / "apps"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def settings_file(self) -> Path:
        """Preferencias do Hub (janela, ultimo app aberto, etc.)."""
        return self.config_dir / "hub.json"

    @property
    def license_file(self) -> Path:
        """Licenca gravada localmente (permite funcionar offline)."""
        return self.config_dir / "license.json"

    @property
    def hub_db(self) -> Path:
        return self.data_dir / "hub.db"

    @property
    def platform_db(self) -> Path:
        """Dados compartilhados pela plataforma (hoje: a agenda de clientes)."""
        return self.data_dir / "plataforma.db"

    @property
    def log_file(self) -> Path:
        return self.logs_dir / "dumtech.log"

    def app_db(self, app_id: str) -> Path:
        """Banco de dados exclusivo de um aplicativo (ex.: estoque.db)."""
        return self.apps_data_dir / f"{app_id}.db"

    def ensure(self) -> "DataPaths":
        """Cria as pastas caso ainda nao existam."""
        for folder in (self.config_dir, self.data_dir, self.apps_data_dir, self.logs_dir):
            folder.mkdir(parents=True, exist_ok=True)
        return self


@lru_cache(maxsize=1)
def get_paths() -> DataPaths:
    """Retorna (e cria) as pastas da plataforma."""
    paths = DataPaths(root=_default_root()).ensure()
    # so a pasta de verdade do cliente: a de teste/desenvolvimento fica a vista
    if not os.environ.get(ENV_DATA_DIR):
        ocultar(paths.root)
    return paths


def reset_paths_cache() -> None:
    """Usado pelos testes quando a pasta de dados muda em tempo de execucao."""
    get_paths.cache_clear()
