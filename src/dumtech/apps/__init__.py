"""Aplicativos instalados na plataforma DumTech.

PARA ADICIONAR UM NOVO APLICATIVO NO FUTURO:

1. crie a pasta ``dumtech/apps/<nome>/`` com um arquivo ``module.py``
   contendo ``MANIFEST`` e ``create_window(context)``;
2. acrescente o caminho do modulo na lista abaixo;
3. libere o codigo do aplicativo na licenca (ex.: FINANCEIRO).

Nada mais precisa ser alterado no Hub.
"""

from __future__ import annotations

#: Modulos de aplicativos que acompanham esta instalacao.
INSTALLED_APPS: tuple[str, ...] = (
    "dumtech.apps.estoque.module",
    "dumtech.apps.clientes.module",
    "dumtech.apps.financeiro.module",
    "dumtech.apps.orcamentos.module",
    "dumtech.apps.vendas.module",
    "dumtech.apps.ordens.module",
    "dumtech.apps.agenda.module",
)
