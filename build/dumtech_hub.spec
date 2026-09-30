# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller para gerar o DumTech Hub em .exe (Windows).

Gera uma pasta (build/dist/DumTech Hub) com o DumTech Hub.exe e tudo que ele
precisa. O cliente final NAO precisa ter Python instalado.

    pyinstaller build/dumtech_hub.spec --noconfirm
"""

from pathlib import Path

import PySide6

RAIZ = Path(SPECPATH).parent
SRC = RAIZ / "src"

# O que da landing page NAO deve ir para o computador do cliente. Mandar a
# pasta inteira levava tests/, package.json, servidor.mjs e README.md para
# dentro do produto pago - a mesma lista que tools/publicar_site.ps1 ja tira
# antes de publicar o site.
_FORA_DA_LANDING = {"tests", "node_modules", "package.json", "servidor.mjs",
                    "README.md", "_headers", ".htaccess", "netlify.toml"}


def _landing_do_cliente():
    """(origem, destino) de cada item da landing, menos o que e so de desenvolvimento.

    Atencao a semantica do PyInstaller: para uma PASTA ele copia o CONTEUDO
    dela para o destino. Por isso pasta vai para "landingpage/<nome>" e arquivo
    solto vai para "landingpage" - senao css/ e js/ despejariam os arquivos na
    raiz e a loja abriria sem estilo.
    """
    landing = RAIZ / "landingpage"
    itens = []
    for caminho in sorted(landing.iterdir()):
        if caminho.name in _FORA_DA_LANDING:
            continue
        destino = f"landingpage/{caminho.name}" if caminho.is_dir() else "landingpage"
        itens.append((str(caminho), destino))
    return itens

# O ponto de entrada precisa ser um script de topo (nao um modulo de dentro do
# pacote), senao os imports relativos do pacote nao funcionam no executavel.
a = Analysis(
    [str(RAIZ / "run_hub.py")],
    pathex=[str(SRC)],
    binaries=[],
    # traducao pt_BR do Qt: sem ela a caixa de confirmacao responde "Yes/No"
    datas=[
        (
            str(Path(PySide6.__file__).parent / "translations" / "qtbase_pt_BR.qm"),
            "PySide6/translations",
        ),
        # a fonte da plataforma (Plus Jakarta Sans, licenca OFL) vai junto:
        # sem ela o programa cai no Segoe UI e perde o desenho dos numeros
        (str(SRC / "dumtech" / "ui" / "fonts"), "dumtech/ui/fonts"),
        # a loja (landing page) viaja junto: serve de copia offline, que o
        # proprio Hub abre em 127.0.0.1 quando nao ha internet
        *_landing_do_cliente(),
    ],
    # o Hub carrega os aplicativos por nome (importlib); por isso eles precisam
    # ser declarados aqui para entrar no executavel.
    hiddenimports=[
        "dumtech.apps.estoque.module",
        "dumtech.apps.estoque.ui.window",
        "dumtech.apps.clientes.module",
        "dumtech.apps.clientes.ui.window",
        "dumtech.apps.financeiro.module",
        "dumtech.apps.financeiro.ui.window",
        "dumtech.apps.orcamentos.module",
        "dumtech.apps.orcamentos.ui.window",
        "dumtech.apps.vendas.module",
        "dumtech.apps.vendas.ui.window",
        "dumtech.apps.ordens.module",
        "dumtech.apps.ordens.ui.window",
        "dumtech.apps.agenda.module",
        "dumtech.apps.agenda.ui.window",
        # importados so quando precisam (dentro de funcao): declarar aqui evita
        # que sumam do executavel sem ninguem perceber
        "dumtech.apps.estoque.catalog",
        # as pontes entram por nome de modulo (importlib): sem declarar aqui,
        # elas somem do executavel e o Hub so encontra "ponte indisponivel"
        "dumtech.apps.financeiro.contas",
        "dumtech.apps.vendas.pedidos",
        "dumtech.apps.ordens.pedidos",
        "PySide6.QtPrintSupport",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "test", "pydoc_data"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DumTech Hub",
    icon=str(RAIZ / "assets" / "dumtech_hub.ico"),
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DumTech Hub",
)
