"""Preferencias do Hub, gravadas em um arquivo JSON simples.

Sao apenas preferencias de uso (tamanho da janela, ultima tela aberta...).
Nada aqui e essencial: se o arquivo sumir, o Hub volta aos valores padrao.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import get_paths

DEFAULTS: dict[str, Any] = {
    "window": {"width": 1180, "height": 760, "maximized": False},
    "hub": {"last_view": "apps", "theme": "dark"},
}


class Settings:
    """Leitura/gravacao das preferencias do Hub."""

    def __init__(self, file_path: Path | None = None) -> None:
        self.file_path = Path(file_path) if file_path else get_paths().settings_file
        self._data: dict[str, Any] = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self) -> None:
        if not self.file_path.exists():
            return
        try:
            saved = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # arquivo corrompido: mantem os padroes
        if isinstance(saved, dict):
            for section, value in saved.items():
                if isinstance(value, dict) and isinstance(self._data.get(section), dict):
                    self._data[section].update(value)
                else:
                    self._data[section] = value

    def save(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        self._data.setdefault(section, {})[key] = value


class AppPreferences:
    """Preferencias de UM aplicativo (ex.: o tema escolhido para ele).

    Ficam no mesmo arquivo do Hub, em uma secao por aplicativo, e sao gravadas
    na hora - o cliente escolhe uma vez e nao precisa repetir.
    """

    def __init__(self, settings: Settings, app_id: str) -> None:
        self._settings = settings
        self._section = f"app:{app_id}"

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(self._section, key, default)

    def set(self, key: str, value: Any) -> None:
        self._settings.set(self._section, key, value)
        self._settings.save()


class MemoryPreferences:
    """Preferencias que nao sao gravadas (usado quando nao ha Hub por perto)."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
