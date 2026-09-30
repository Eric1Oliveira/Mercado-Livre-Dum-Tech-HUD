"""Grava os videos de demonstracao do DumTech Hub (o programa de verdade, rodando).

    .venv\\Scripts\\python tools\\videos\\gravar.py              -> todos
    .venv\\Scripts\\python tools\\videos\\gravar.py hub vendas   -> so estes

Saida: build\videos\<nome>.mp4 (Hub gravado em 1280x720, entregue em 1920x1080, H.264).

Precisa do ffmpeg: o do PATH, o da variavel FFMPEG, ou o do pacote
`imageio-ffmpeg` (pip install imageio-ffmpeg - nao e dependencia do Hub).
Cada video roda num Hub novo, com a empresa de demonstracao de semente.py.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "build" / "videos"
LARGURA, ALTURA = 1280, 720


def achar_ffmpeg() -> str:
    if os.environ.get("FFMPEG"):
        return os.environ["FFMPEG"]
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("Falta o ffmpeg: instale (winget install ffmpeg) ou `pip install imageio-ffmpeg`.")


def gravar_um(nome: str, ffmpeg: str) -> Path:
    """Um video = um processo novo (Hub limpo, dados de demonstracao frescos)."""
    SAIDA.mkdir(parents=True, exist_ok=True)
    destino = SAIDA / f"{nome}.mp4"
    env = {**os.environ, "DUMTECH_DATA_DIR": tempfile.mkdtemp(prefix="dumtech-video-"),
           "QT_QPA_PLATFORM": "offscreen", "DUMTECH_LICENCA_LOCAL": "1", "FFMPEG": ffmpeg,
           "PYTHONPATH": os.pathsep.join([str(RAIZ / "src"), str(Path(__file__).parent)])}
    subprocess.run([sys.executable, str(Path(__file__)), "--dentro", nome, str(destino)], env=env, check=True)
    return destino


def dentro(nome: str, destino: str) -> None:
    """Roda DENTRO do processo filho: monta o Hub e toca o roteiro."""
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    from dumtech.core.config import Settings
    from dumtech.core.paths import get_paths
    from dumtech.hub.main_window import HubWindow
    from dumtech.ui.theme import MODO_CLARO, ThemeManager, carregar_fontes

    import roteiros
    import semente
    from gravador import Diretor, Gravador, rodar

    carregar_fontes()
    ajustes = Settings()
    ajustes.set("conta", "concluido", True)
    ajustes.set("empresa", "nome", semente.EMPRESA)
    ajustes.set("empresa", "cidade", "Santo André")
    ajustes.save()
    semente.semear(get_paths())

    tema = ThemeManager(app, MODO_CLARO)
    hub = HubWindow(settings=ajustes, theme=tema)
    hub.celular_service = roteiros.CelularDeMentira()
    hub._tarefas_de_rede = lambda *a, **k: None  # video nao fala com servidor
    hub.conferir_versao = lambda *a, **k: None
    hub.resize(LARGURA, ALTURA)
    hub.show()
    app.processEvents()

    gravador = Gravador(hub, destino, os.environ["FFMPEG"])
    diretor = Diretor(gravador)
    rodar(roteiros.ROTEIROS[nome](diretor, hub), gravador, app)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--dentro":
        dentro(sys.argv[2], sys.argv[3])
        sys.exit(0)
    sys.path.insert(0, str(Path(__file__).parent))
    import roteiros

    pedidos = sys.argv[1:] or list(roteiros.ROTEIROS)
    ffmpeg = achar_ffmpeg()
    falharam = []
    for nome in pedidos:
        print(f"gravando {nome}...", flush=True)
        try:
            print("  ->", gravar_um(nome, ffmpeg), flush=True)
        except subprocess.CalledProcessError:
            falharam.append(nome)
    if falharam:
        sys.exit(f"falharam: {', '.join(falharam)}")
