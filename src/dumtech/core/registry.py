"""Catalogo de aplicativos do Hub.

O registro carrega os modulos listados em ``dumtech.apps.INSTALLED_APPS``, le o
MANIFEST de cada um e cruza com a licenca para saber o que o cliente pode abrir.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from types import ModuleType

from ..apps import INSTALLED_APPS
from .app_module import AppContext, AppManifest
from .licensing import LicenseService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppEntry:
    """Um aplicativo instalado e pronto para ser aberto."""

    manifest: AppManifest
    module: ModuleType

    @property
    def app_id(self) -> str:
        return self.manifest.app_id

    def create_window(self, context: AppContext):
        """Cria a janela do aplicativo (delegado ao proprio aplicativo)."""
        return self.module.create_window(context)


class AppRegistry:
    """Descobre os aplicativos instalados e aplica as regras de licenca."""

    def __init__(self, license_service: LicenseService | None = None) -> None:
        self.license_service = license_service or LicenseService()
        self._entries: list[AppEntry] = []
        self._failures: list[tuple[str, str]] = []

    # ------------------------------------------------------------------ leitura
    def load(self, module_paths: tuple[str, ...] = INSTALLED_APPS) -> list[AppEntry]:
        entries: list[AppEntry] = []
        self._failures = []
        for path in module_paths:
            try:
                module = importlib.import_module(path)
                manifest = getattr(module, "MANIFEST")
                if not hasattr(module, "create_window"):
                    raise AttributeError("módulo sem create_window()")
                entries.append(AppEntry(manifest=manifest, module=module))
            except Exception as exc:  # aplicativo com defeito nao derruba o Hub
                logger.exception("Falha ao carregar aplicativo %s", path)
                self._failures.append((path, str(exc)))
        entries.sort(key=lambda e: e.manifest.name.lower())
        self._entries = entries
        return entries

    @property
    def entries(self) -> list[AppEntry]:
        if not self._entries:
            self.load()
        return self._entries

    @property
    def failures(self) -> list[tuple[str, str]]:
        return list(self._failures)

    def get(self, app_id: str) -> AppEntry | None:
        return next((e for e in self.entries if e.app_id == app_id), None)

    # ------------------------------------------------------------------ licenca
    def available(self) -> list[AppEntry]:
        """Aplicativos instalados E liberados pela licenca."""
        return [e for e in self.entries if self.license_service.allows(e.app_id)]

    def locked(self) -> list[AppEntry]:
        """Aplicativos instalados que a licenca ainda nao libera."""
        return [e for e in self.entries if not self.license_service.allows(e.app_id)]
