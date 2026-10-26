"""Contrato que todo aplicativo DumTech precisa cumprir para rodar no Hub.

Um aplicativo e um pacote Python dentro de ``dumtech/apps/`` contendo um arquivo
``module.py`` que expoe exatamente duas coisas:

    MANIFEST: AppManifest        -> identidade do aplicativo (nome, icone, cor...)
    create_window(context) -> QWidget  -> cria a janela do aplicativo

Nada mais. O Hub nao precisa conhecer o funcionamento interno do aplicativo, e o
aplicativo nao precisa conhecer o Hub. Para adicionar um novo aplicativo no
futuro basta criar a pasta e registrar o caminho em ``dumtech/apps/__init__.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .paths import DataPaths, get_paths


@dataclass(frozen=True)
class AppManifest:
    """Identidade de um aplicativo da plataforma."""

    app_id: str          # identificador tecnico, ex.: "estoque"
    name: str            # nome comercial, ex.: "DumTech Estoque"
    short_name: str      # nome curto usado no card, ex.: "Estoque"
    description: str     # frase curta exibida no Hub
    version: str = "1.0.0"
    icon: str = "box"    # nome do icone (ver dumtech/ui/icons.py)
    accent: str = "#4F8DFD"  # cor de destaque do aplicativo
    category: str = "Gestão"
    requires_internet: bool = False

    @property
    def license_code(self) -> str:
        """Codigo usado na licenca (ex.: ESTOQUE)."""
        return self.app_id.upper()


@dataclass(frozen=True)
class AppContext:
    """Recursos que o Hub entrega ao aplicativo quando ele e aberto.

    Tudo aqui e opcional: um aplicativo continua funcionando (em testes, por
    exemplo) mesmo sem Hub, com valores padrao.
    """

    manifest: AppManifest
    paths: DataPaths = field(default_factory=get_paths)
    hub_version: str = "1.0.0"
    #: preferencias gravadas deste aplicativo (tema, etc.)
    prefs: Any = None
    #: gerenciador de tema da plataforma (para o modo "seguir o Hub")
    theme: Any = None
    #: agenda de clientes compartilhada pela plataforma
    contacts: Any = None
    #: catalogo de produtos da plataforma (`core/catalog.py`), quando o
    #: cliente tem o DumTech Estoque liberado na licenca
    catalog: Any = None
    #: dados da empresa do cliente, para o cabecalho dos documentos
    empresa: Any = None
    #: modelos de mensagem de WhatsApp (`core/mensagens.py`), ja com a empresa
    mensagens: Any = None
    #: contas a receber da plataforma (`core/contas.py`), quando o cliente tem
    #: o DumTech Financeiro liberado na licenca
    contas: Any = None
    #: para onde uma proposta aprovada pode virar trabalho (`core/pedidos.py`)
    destinos: list = field(default_factory=list)
    #: o servidor da DumTech ja com as credenciais da licenca (`core/online.py`)
    #: - so para quem tem parte online, como o link de agendamento
    servidor: Any = None

    @property
    def db_path(self) -> Path:
        """Arquivo de banco de dados exclusivo deste aplicativo."""
        return self.paths.app_db(self.manifest.app_id)


@runtime_checkable
class AppModule(Protocol):
    """Formato esperado do arquivo ``module.py`` de cada aplicativo."""

    MANIFEST: AppManifest

    def create_window(self, context: AppContext):  # pragma: no cover - contrato
        ...
