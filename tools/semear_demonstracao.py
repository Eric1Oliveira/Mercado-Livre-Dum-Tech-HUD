"""Enche a instalacao de verdade com a loja ficticia, para ver o programa em uso.

    .venv\\Scripts\\python.exe tools/semear_demonstracao.py
    .venv\\Scripts\\python.exe tools/semear_demonstracao.py --somar

Diferente do `gerar_capturas.py`, que trabalha numa pasta temporaria, este mexe
nos dados que o DumTech Hub abre - `%APPDATA%\\DumTech Hub`. Por isso ele faz
**backup antes de qualquer coisa** e diz onde guardou: desfazer e restaurar essa
copia pela tela de Configuracoes > Backup.

Por padrao ele comeca do zero (apaga os bancos e semeia); com `--somar`, apenas
acrescenta ao que ja existe - util para ver como fica com mais volume, e
arriscado quando ha cadastro com codigo repetido.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tools"))
# a demonstracao mostra a plataforma inteira, sem consultar a internet
os.environ.setdefault("DUMTECH_LICENCA_LOCAL", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import dados_demo  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dumtech.core import backup  # noqa: E402
from dumtech.core.paths import get_paths  # noqa: E402
from dumtech.hub.main_window import HubWindow  # noqa: E402
from dumtech.ui.theme import MODO_ESCURO, ThemeManager  # noqa: E402


class EmUso(Exception):
    """Alguem esta com os bancos abertos - trocar arquivo agora corrompe."""


TABELAS = {
    "estoque": "produtos",
    "vendas": "vendas",
    "financeiro": "lancamentos",
    "orcamentos": "orcamentos",
    "ordens": "ordens",
    "agenda": "compromissos",
}


def contar(paths) -> dict[str, int]:
    """Quantas linhas ha em cada aplicativo agora."""
    import sqlite3

    totais: dict[str, int] = {}
    for app_id, tabela in TABELAS.items():
        caminho = paths.app_db(app_id)
        if not caminho.exists():
            totais[app_id] = 0
            continue
        conexao = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        try:
            totais[app_id] = int(
                conexao.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
            )
        except sqlite3.Error:
            totais[app_id] = 0
        finally:
            conexao.close()

    plataforma = paths.platform_db
    if plataforma.exists():
        conexao = sqlite3.connect(f"file:{plataforma}?mode=ro", uri=True)
        try:
            totais["clientes"] = int(
                conexao.execute("SELECT COUNT(*) FROM contatos").fetchone()[0]
            )
        except sqlite3.Error:
            totais["clientes"] = 0
        finally:
            conexao.close()
    return totais


def limpar(paths) -> list[str]:
    """Apaga os bancos dos aplicativos e a agenda de clientes.

    O `hub.db` fica: ele guarda o que voce abriu por ultimo, nao dado de
    trabalho. E a licenca tambem, que mora em `config/` e nunca entra aqui.
    """
    apagados = []
    alvos = [paths.app_db(app_id) for app_id in TABELAS] + [paths.platform_db]
    for caminho in alvos:
        for sufixo in ("", "-wal", "-shm"):
            arquivo = pathlib.Path(f"{caminho}{sufixo}")
            if not arquivo.exists():
                continue
            try:
                arquivo.unlink()
            except OSError as erro:
                # o proprio Hub aberto e o suspeito numero um
                raise EmUso(
                    f"O banco '{arquivo.name}' esta em uso. Feche o DumTech Hub "
                    f"(inclusive outras janelas dele) e rode de novo."
                ) from erro
            if not sufixo:
                apagados.append(arquivo.name)
    return apagados


def main() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument(
        "--somar", action="store_true",
        help="acrescenta aos dados atuais em vez de comecar do zero",
    )
    opcoes = argumentos.parse_args()

    paths = get_paths().ensure()
    print(f"Pasta de dados: {paths.root}")

    antes = contar(paths)
    tinha = sum(antes.values())
    print("Antes:", ", ".join(f"{k}={v}" for k, v in sorted(antes.items())))

    if tinha:
        try:
            copia = backup.criar(backup.pasta_padrao(paths), paths)
            print(f"Backup guardado em: {copia.arquivo}")
        except backup.BackupError as erro:
            print(f"Nao consegui fazer backup ({erro}). Nada foi alterado.")
            return 1

    if not opcoes.somar:
        try:
            apagados = limpar(paths)
        except EmUso as erro:
            print("")
            print(str(erro))
            print("Nada foi alterado - o backup acima continua valendo.")
            return 1
        print("Bancos zerados:", ", ".join(apagados) if apagados else "(nenhum)")

    app = QApplication.instance() or QApplication([])
    tema = ThemeManager(app, MODO_ESCURO)
    hub = HubWindow(theme=tema)
    hub.launcher.notify = lambda *args: None
    try:
        dados_demo.semear_tudo(hub)
    finally:
        hub.launcher.close_all()
        hub.hub_store.close()
        hub.contacts.close()

    depois = contar(paths)
    print("Depois:", ", ".join(f"{k}={v}" for k, v in sorted(depois.items())))
    print("\nPronto. Abra o DumTech Hub para ver a loja de demonstracao.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
