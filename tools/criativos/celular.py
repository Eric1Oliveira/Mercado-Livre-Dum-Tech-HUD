"""Fotografa a tela do celular — a página de verdade, com dados de verdade.

POR QUE NÃO É UM DESENHO
    O "ver no celular" é metade do argumento de venda: o dono sai da loja e
    continua vendo o caixa. Desenhar uma tela parecida seria propaganda
    enganosa e, pior, ficaria diferente do que o comprador recebe.

    Então aqui roda `landingpage/celular/index.html` — o mesmo arquivo que vai
    ao ar — com o resumo que `core.celular.montar()` gerou a partir da loja
    fictícia do nicho. O que o anúncio mostra é o produto rodando.

COMO A PÁGINA É CONVENCIDA A ABRIR SEM PAREAMENTO
    Ela guarda o último resumo em `localStorage` para abrir offline. A prévia
    escreve essa chave antes dos módulos carregarem. Três armadilhas, todas
    pagas em foto errada antes de virarem comentário:

    1. A página tem Content-Security-Policy `script-src 'self'`, então a
       semente NÃO pode ser script inline — é um arquivo `.js` ao lado.
    2. `localStorage` NÃO EXISTE em `file://`: a semente falhava calada (está
       dentro de try/catch) e a foto saía com o esqueleto cinza de "Abrindo o
       resumo da sua empresa...". Por isso a prévia sobe um servidor HTTP
       local só para tirar a foto.
    3. A página abre pelo cache e SÓ DEPOIS vai à rede. Com um acesso
       inventado, o servidor responde "acesso inválido" e a tela vira "Este
       celular foi desconectado" bem na hora do clique. A semente derruba o
       `fetch`: falha de rede é tratada como "sem internet agora", e os
       números do cache continuam na tela.

    Nada disso toca `landingpage/`. A prévia monta uma cópia em
    `build/criativos/previa-celular/`, fora do que é publicado.
"""

from __future__ import annotations

import contextlib
import functools
import json
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .base import RAIZ, renderizar_em

LANDING = RAIZ / "landingpage"
PREVIA = RAIZ / "build" / "criativos" / "previa-celular"

#: o tamanho de um celular comum, em pontos de CSS
FONE_L, FONE_A = 470, 900


def _montar_copia() -> None:
    """Uma cópia da página do celular, fora da pasta que vai para o ar."""
    if PREVIA.exists():
        shutil.rmtree(PREVIA)
    (PREVIA / "css").mkdir(parents=True)
    shutil.copytree(LANDING / "celular", PREVIA / "celular")
    shutil.copytree(LANDING / "js", PREVIA / "js")
    shutil.copy(LANDING / "css" / "celular.css", PREVIA / "css" / "celular.css")


SEMENTE = """// Previa do anuncio: o ultimo resumo, como o celular guardaria.
try {
  localStorage.setItem("dumtech.tema", "claro");
  localStorage.setItem("dumtech.celular.acesso", "previa");
  localStorage.setItem("dumtech.celular.computador", "0");
  localStorage.setItem("dumtech.celular.ultimo", %s);
} catch (e) {}

// Sem rede de proposito: ver o comentario do modulo (armadilha 3).
window.fetch = function () {
  return Promise.reject(new TypeError("previa: sem rede de proposito"));
};

// A falha de rede escreve "Sem conexao - tentando de novo" no topo. E verdade
// nesta previa e mentira no celular de quem comprou, que esta pareado: o
// anuncio nao pode carimbar um defeito que o produto nao tem. Aqui o subtitulo
// volta a dizer o que o cliente ve de verdade.
addEventListener("load", function () {
  setInterval(function () {
    var q = document.getElementById("quando");
    if (q && /conex|tentando|offline/i.test(q.textContent || "")) {
      q.textContent = "atualizado agora mesmo";
    }
  }, 120);
});
"""


def _semear(pacote: dict) -> None:
    """Escreve a semente e a enxerta no index, antes dos módulos."""
    guardado = json.dumps(json.dumps(pacote, ensure_ascii=False))
    (PREVIA / "celular" / "semente.js").write_text(SEMENTE % guardado,
                                                   encoding="utf-8")

    indice = PREVIA / "celular" / "index.html"
    html = indice.read_text(encoding="utf-8")
    marca = '<script src="../js/tema.js"></script>'
    if "semente.js" not in html:
        html = html.replace(marca, '<script src="semente.js"></script>\n' + marca)
    # o service worker serviria a casca antiga por cima da semente
    html = html.replace('if ("serviceWorker" in navigator)', "if (false)")
    indice.write_text(html, encoding="utf-8")


@contextlib.contextmanager
def _servidor(pasta: Path):
    """Um servidor local, calado, só enquanto a foto é tirada."""
    class Quieto(SimpleHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D102 - o log polui a saída
            pass

    handler = functools.partial(Quieto, directory=str(pasta))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def fotografar(cenario: str, navegador: str) -> Path:
    """Gera `build/criativos/telas/<cenario>/celular.png`."""
    origem = RAIZ / "build" / "criativos" / "telas" / cenario / "celular.json"
    if not origem.exists():
        raise SystemExit(f"Falta {origem}: rode tools/criativos/cenas.py antes.")

    _montar_copia()
    _semear(json.loads(origem.read_text(encoding="utf-8")))

    destino = origem.with_name("celular.png")
    with _servidor(PREVIA) as base:
        renderizar_em(f"{base}/celular/index.html", destino,
                      navegador, FONE_L, FONE_A)
    return destino
