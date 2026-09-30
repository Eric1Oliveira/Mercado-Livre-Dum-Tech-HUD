"""Gera os criativos dos anúncios do Mercado Livre.

    python tools/criativos/cenas.py           # 1. fotografa as telas do nicho
    python tools/gerar_criativos_ml.py        # 2. monta as 40 peças

    python tools/gerar_criativos_ml.py --nicho 02-salao
    python tools/gerar_criativos_ml.py --so 3      # só a peça de nº 3

Sai em `build/criativos/<nicho>/01..10.png`, 1200x1200, pronto para subir.

AS REGRAS QUE DESENHAM TUDO ISTO
    1. A peça 1 obedece ao Mercado Livre: fundo branco, sem texto, sem logo e
       sem moldura. As outras nove é que conversam.
    2. A ordem importa mais que o número de peças. Quem mede anúncio de
       aplicativo sabe que quase ninguém passa da terceira foto — por isso a 2
       é a dor e a 3 é a tela explicada, com marcadores.
    3. Nenhuma captura é cortada. Cada uma entra inteira, dentro de uma
       moldura de programa (ou de celular), como o comprador vai ver.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from criativos import pecas
from criativos.base import RAIZ, achar_navegador, renderizar
from criativos.nichos import ENTREGA, NICHOS, PROMESSA

#: o teto de fotos de um anúncio do Mercado Livre
POR_ANUNCIO = 10


def jogo(nicho: dict) -> list[tuple[str, str]]:
    """As dez peças de um anúncio, na ordem em que o roteiro pede."""
    def peca(nome: str):
        if nome == "capa":
            return pecas.capa(nicho["capa"])
        if nome == "dor":
            return pecas.dor(nicho["nicho"], *nicho["dor"], nicho["cor"])
        if nome == "explicada":
            return pecas.explicada(*nicho["explicada"])
        if nome == "celular":
            titulo, apoio, itens, captura = nicho["celular"]
            return pecas.no_celular(titulo, apoio, captura, itens)
        if nome == "integracao":
            return pecas.integracao(*nicho["integracao"])
        if nome == "o-que-vem":
            return pecas.o_que_vem(*nicho["o_que_vem"])
        if nome == "promessa":
            return pecas.promessa(*PROMESSA)
        if nome == "entrega":
            return pecas.entrega(*ENTREGA)
        if nome.startswith("modulo:"):
            codigo = nome.split(":", 1)[1]
            return pecas.modulo(codigo, *nicho["modulos"][codigo])
        raise SystemExit(f"{nicho['slug']}: não sei montar a peça '{nome}'.")

    roteiro = nicho["roteiro"]
    if len(roteiro) != POR_ANUNCIO:
        raise SystemExit(
            f"{nicho['slug']}: o roteiro tem {len(roteiro)} peças, e o anúncio "
            f"do Mercado Livre leva exatamente {POR_ANUNCIO}."
        )
    return [(nome.replace(":", "-").lower(), peca(nome)) for nome in roteiro]


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--nicho", default="", help="slug de um nicho só")
    args.add_argument("--so", type=int, default=0, help="só a peça de nº N")
    opcoes = args.parse_args()

    escolhidos = [n for n in NICHOS if not opcoes.nicho or n["slug"] == opcoes.nicho]
    if not escolhidos:
        raise SystemExit(f"Nicho '{opcoes.nicho}' não existe. "
                         f"Há: {', '.join(n['slug'] for n in NICHOS)}")

    telas = RAIZ / "build" / "criativos" / "telas"
    if not telas.exists():
        raise SystemExit("Faltam as capturas: rode tools/criativos/cenas.py antes.")

    navegador = achar_navegador()
    total = 0
    for nicho in escolhidos:
        pasta = RAIZ / "build" / "criativos" / nicho["slug"]
        # a pasta é limpa antes: peça de um roteiro antigo ficava para trás e
        # o jogo ia para o Mercado Livre com dezesseis fotos fora de ordem
        if pasta.exists() and not opcoes.so:
            for velho in pasta.glob("*.png"):
                velho.unlink()
        print(f"\n{nicho['nicho']}  ->  {pasta.relative_to(RAIZ)}")
        for numero, (nome, html_texto) in enumerate(jogo(nicho), 1):
            if opcoes.so and numero != opcoes.so:
                continue
            destino = pasta / f"{numero:02d}-{nome}.png"
            renderizar(html_texto, destino, navegador)
            print(f"  {numero:02d}  {nome}")
            total += 1

    print(f"\n{total} peças em build/criativos/.")
    print("A peça 01 de cada pasta é a foto de capa: fundo branco, sem texto — "
          "é a que o Mercado Livre exige assim.")


if __name__ == "__main__":
    main()
