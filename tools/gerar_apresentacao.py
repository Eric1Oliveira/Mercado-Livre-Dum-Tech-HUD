"""Monta a apresentacao comercial em PDF.

    python tools/gerar_apresentacao.py

Le `docs/apresentacao/apresentacao.html`, embute as fontes e as imagens no
proprio arquivo e manda o Chrome imprimir em A4.

Por que embutir: a fonte baixada da internet perde a corrida com a impressao -
o Chrome renderiza com a fonte de reserva e o PDF sai em Times New Roman. Com
tudo dentro do arquivo, o PDF sai igual em qualquer maquina, inclusive sem
internet.
"""

from __future__ import annotations

import base64
import pathlib
import re
import subprocess
import sys
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PASTA = RAIZ / "docs" / "apresentacao"
ORIGEM = PASTA / "apresentacao.html"
SAIDA = PASTA / "DumTech-Hub-um-modulo-ou-sete.pdf"
MONTADO = PASTA / ".apresentacao-completa.html"

FONTES = (
    "https://fonts.googleapis.com/css2"
    "?family=Archivo:wght@500;600;700"
    "&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600"
    "&family=IBM+Plex+Mono:wght@400;500;600"
    # `block` e nao `swap`: com `swap` o Chrome imprime com a fonte de reserva
    # se o arquivo ainda nao estiver decodificado, e o PDF sai em Times New Roman
    "&display=block"
)
#: um navegador de verdade recebe woff2; um cliente anonimo recebe ttf
NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CHROMES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def baixar(url: str) -> bytes:
    pedido = urllib.request.Request(url, headers={"User-Agent": NAVEGADOR})
    with urllib.request.urlopen(pedido, timeout=30) as resposta:
        return resposta.read()


def fontes_embutidas() -> str:
    """As tres familias como `@font-face` com o arquivo dentro do CSS.

    So os recortes latinos entram: o resto do mundo nao aparece neste documento
    e cada recorte extra sao dezenas de KB no PDF.

    O comentario com o nome do recorte vem **antes** do bloco, e nao dentro
    dele - ler por dentro embute o alfabeto errado, o texto latino nao acha
    glifo nenhum e o PDF sai inteiro na fonte de reserva.
    """
    css = baixar(FONTES).decode("utf-8")
    blocos, guardadas = [], 0
    for recorte, corpo in re.findall(
        r"/\*\s*([\w-]+)\s*\*/\s*@font-face\s*\{([^}]*)\}", css
    ):
        if recorte not in ("latin", "latin-ext"):
            continue
        url = re.search(r"url\((https://[^)]+)\)", corpo)
        if not url:
            continue
        dados = base64.b64encode(baixar(url.group(1))).decode("ascii")
        corpo = corpo.replace(url.group(1), f"data:font/woff2;base64,{dados}")
        blocos.append("@font-face {" + corpo + "}")
        guardadas += 1
    if not guardadas:
        raise SystemExit("Nenhuma fonte latina encontrada - o CSS do Google mudou?")
    print(f"  {guardadas} recortes de fonte embutidos")
    return "\n".join(blocos)


def imagens_embutidas(html: str) -> str:
    """Troca cada `src` por um `data:` - o PDF nao depende da pasta de imagens."""
    def trocar(achado: re.Match) -> str:
        caminho = (PASTA / achado.group(1)).resolve()
        dados = base64.b64encode(caminho.read_bytes()).decode("ascii")
        return f'src="data:image/png;base64,{dados}"'

    html, quantas = re.subn(r'src="(\.\./[^"]+)"', trocar, html)
    print(f"  {quantas} imagens embutidas")
    return html


def chrome() -> str:
    for caminho in CHROMES:
        if pathlib.Path(caminho).exists():
            return caminho
    raise SystemExit("Nao encontrei o Chrome nem o Edge para gerar o PDF.")


def paginas(pdf: pathlib.Path) -> int:
    """Conta as paginas do PDF sem depender de biblioteca."""
    dados = pdf.read_bytes()
    return len(re.findall(rb"/Type\s*/Page[^s]", dados))


def main() -> int:
    html = ORIGEM.read_text(encoding="utf-8")
    print("Montando a apresentacao...")
    html = re.sub(
        r'<link rel="preconnect".*?<link rel="stylesheet" href="https://fonts\.googleapis[^>]*>',
        "<style>" + fontes_embutidas() + "</style>",
        html, flags=re.S,
    )
    html = imagens_embutidas(html)
    MONTADO.write_text(html, encoding="utf-8")
    print(f"  arquivo montado: {len(html.encode()) // 1024} KB")

    subprocess.run(
        [chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         "--virtual-time-budget=20000",
         f"--print-to-pdf={SAIDA}", MONTADO.as_uri()],
        check=True, capture_output=True,
    )
    if "--manter" not in sys.argv:
        MONTADO.unlink(missing_ok=True)

    print(f"\n{SAIDA.relative_to(RAIZ)}")
    print(f"  {SAIDA.stat().st_size // 1024} KB, {paginas(SAIDA)} paginas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
