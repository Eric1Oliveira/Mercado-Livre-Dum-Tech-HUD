"""Onde a plataforma DumTech guarda os arquivos no computador do cliente.

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
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Nome da pasta criada dentro de %APPDATA%.
APP_FOLDER_NAME = "DumTech Hub"

#: Variavel de ambiente que permite trocar a pasta de dados (dev/testes).
ENV_DATA_DIR = "DUMTECH_DATA_DIR"


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
    return DataPaths(root=_default_root()).ensure()


def reset_paths_cache() -> None:
    """Usado pelos testes quando a pasta de dados muda em tempo de execucao."""
    get_paths.cache_clear()
