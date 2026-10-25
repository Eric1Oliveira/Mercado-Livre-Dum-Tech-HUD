"""Leva os videos do Passo a passo para o site e monta o catalogo da busca.

    .venv\\Scripts\\python tools\\videos\\gravar.py --loja passo       (grava os videos do programa)
    node tools\\videos\\gravar_site.mjs                             (grava o video de como usar o catalogo, no Edge)
    .venv\\Scripts\\python tools\\videos\\publicar_passo.py            (este: copia, faz as capas e o catalogo)

O que sai em landingpage/:
    videos/<id>.mp4          o video (720p, leve: ~0,5 MB por minuto de tela)
    videos/<id>.jpg          a capa (640x360, ~25 KB) - so ela carrega antes do clique
    passo-a-passo/catalogo.js   titulos, perguntas, palavras e os passos com o segundo de cada um

Nada disso passa pelo banco: o site e estatico e a busca roda no navegador.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ORIGEM = RAIZ / "build" / "videos" / "passo-a-passo"
SITE = RAIZ / "landingpage"
VIDEOS = SITE / "videos"
SAIDA_JS = SITE / "passo-a-passo" / "catalogo.js"

sys.path.insert(0, str(Path(__file__).parent))

#: o video que mostra o proprio catalogo (gravado do site por gravar_site.mjs)
SITE_VIDEO = {
    "usar-passo-a-passo": dict(
        titulo="Como usar o Passo a passo", modulo="site", grupo="Este catálogo",
        resumo="Escreva a sua dúvida com as suas palavras e o vídeo certo aparece na hora.",
        perguntas=["como achar um vídeo", "como usar o passo a passo", "como pesquisar uma dúvida", "onde tem tutorial"],
        palavras=["tutorial", "video", "vídeo", "ajuda", "duvida", "dúvida", "passo a passo", "catalogo", "pesquisar"]),
}


def ffmpeg() -> str:
    from gravar import achar_ffmpeg
    return achar_ffmpeg()


def capa(video: Path, destino: Path, segundo: float) -> None:
    """Um quadro do meio do video, pequeno: e o que carrega antes de alguem clicar."""
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{segundo:.1f}", "-i", str(video),
                    "-frames:v", "1", "-vf", "scale=640:-2:flags=lanczos", "-q:v", "6", str(destino)], check=True)


def main() -> None:
    from roteiros_passo import CATALOGO

    VIDEOS.mkdir(exist_ok=True)
    itens, faltando = [], []
    for id_, info in {**CATALOGO, **SITE_VIDEO}.items():
        video = ORIGEM / f"{id_}.mp4"
        passos_json = ORIGEM / f"{id_}.passos.json"
        if not video.exists() or not passos_json.exists():
            faltando.append(id_)
            continue
        dados = json.loads(passos_json.read_text(encoding="utf-8"))
        shutil.copyfile(video, VIDEOS / f"{id_}.mp4")
        passos = dados["passos"]
        # a capa mostra a tela do meio da tarefa (nao o cartao de titulo do comeco)
        meio = passos[len(passos) // 2]["t"] + 1.2 if passos else dados["duracao"] / 2
        capa(video, VIDEOS / f"{id_}.jpg", min(meio, dados["duracao"] - 1))
        itens.append({"id": id_, **info, "duracao": dados["duracao"], "passos": passos,
                      "kb": round(video.stat().st_size / 1024)})
    corpo = json.dumps(itens, ensure_ascii=False, indent=1)
    SAIDA_JS.write_text(
        "// Gerado por tools/videos/publicar_passo.py a partir dos roteiros - nao edite a mao.\n"
        "// Cada video: titulo, perguntas que as pessoas fazem, palavras parecidas e os passos com o segundo de cada um.\n"
        f"export const VIDEOS = {corpo};\n", encoding="utf-8")
    total = sum(i["kb"] for i in itens)
    print(f"{len(itens)} videos no catalogo ({total / 1024:.1f} MB no total, so baixam quando alguem da play)")
    if faltando:
        print("sem gravacao ainda:", ", ".join(faltando))


if __name__ == "__main__":
    main()
