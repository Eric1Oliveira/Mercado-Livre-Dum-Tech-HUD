"""O desenho dos criativos do Mercado Livre: tokens, moldura e render.

TEMA CLARO, COMO O PRODUTO
    O Hub abre no claro - é o padrão dele. E é o que funciona no Mercado
    Livre: a vitrine é branca, o comprador rola dezenas de miniaturas, e peça
    clara com letra escura é a que se lê num celular no meio da rua.

A TELA SAI INTEIRA, SEMPRE
    Nenhuma captura é cortada, esticada nem sangrada para fora da arte. Tela
    cortada no meio parece erro de montagem, e num anúncio isso vira dúvida
    sobre o produto. O texto ocupa a parte de cima; a janela inteira entra
    embaixo, com folga dos dois lados.

    A janela aparece COMPLETA, com a barra do Hub e tudo. O anúncio não FALA
    do Hub - fala do trabalho que os módulos resolvem - mas esconder pedaço de
    tela para guardar surpresa só deixava a imagem esquisita.

O QUE ESTE ARQUIVO RECUSA
    O reflexo da categoria no Mercado Livre é gradiente azul, mockup de
    notebook e "SISTEMA COMPLETO" em Impact com estrela amarela. Aqui não há
    gradiente decorativo, não há três cartões iguais lado a lado e não há
    preto puro: o preto é `#14121D`, puxado para o violeta da marca, e o
    cinza de fundo é `#F6F4FB`, pela mesma razão.

A REGRA DO MERCADO LIVRE QUE MANDA NA PRIMEIRA PEÇA
    A foto de capa precisa de fundo branco e NÃO pode ter texto, logo, moldura
    nem marca d'água - anúncio que desrespeita isso perde posição. Por isso a
    peça 1 de todo jogo é só a tela do programa no branco, e toda a conversa
    acontece da peça 2 em diante.
"""

from __future__ import annotations

import html
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FONTES = RAIZ / "landingpage" / "guia" / "fontes"

#: lado da peça. O Mercado Livre pede quadrada e no mínimo 500 px; 1200 é o
#: tamanho em que ele deixa dar zoom sem a imagem embolar.
LADO = 1200
MARGEM = 84

# ----------------------------------------------------------------- as cores --
BRANCO = "#FFFFFF"
FUNDO = "#F6F4FB"        # cinza puxado para o violeta, nunca cinza morto
TINTA = "#14121D"        # preto puxado para o violeta, nunca #000
TINTA_MEDIA = "#56516B"
TINTA_FRACA = "#8A85A0"
FIO = "#E4E1EE"
VIOLETA = "#7353F6"
VIOLETA_FORTE = "#5A3DE0"
VIOLETA_CLARO = "#EFEBFE"

#: as cores dos sete módulos, escurecidas o bastante para ler sobre fundo claro
COR_MODULO = {
    "AGENDA": "#6F5CE8", "CLIENTES": "#1E9184", "ESTOQUE": "#B26C12",
    "FINANCEIRO": "#1F7D52", "ORCAMENTOS": "#C0423A", "VENDAS": "#9C40AE",
    "ORDENS": "#3663CE",
}
#: a mesma cor, bem clara, para o fundo do selo do módulo
FUNDO_MODULO = {
    "AGENDA": "#ECE9FD", "CLIENTES": "#E2F4F1", "ESTOQUE": "#FBF0DF",
    "FINANCEIRO": "#E3F3EB", "ORCAMENTOS": "#FBE9E8", "VENDAS": "#F7E9FA",
    "ORDENS": "#E6EDFB",
}

NOME_MODULO = {
    "AGENDA": "Agenda", "CLIENTES": "Clientes", "ESTOQUE": "Estoque",
    "FINANCEIRO": "Financeiro", "ORCAMENTOS": "Orçamentos",
    "VENDAS": "Vendas", "ORDENS": "Ordem de Serviço",
}

#: a captura sai da janela do Hub neste tamanho (em pontos; o arquivo tem o
#: dobro de pixels, porque o Qt desenha em 2x)
TELA_L, TELA_A = 1240, 800
#: e a do celular, neste
FONE_L, FONE_A = 470, 900


def altura_da_tela(largura: int) -> int:
    """A altura que a captura terá nessa largura, sem distorcer nada."""
    return round(largura * TELA_A / TELA_L)


def _fonte(arquivo: str, peso: int) -> str:
    caminho = (FONTES / arquivo).as_uri()
    return (f"@font-face{{font-family:'Jakarta';src:url('{caminho}') format('truetype');"
            f"font-weight:{peso};font-style:normal;font-display:block}}")


CSS_BASE = (
    _fonte("PlusJakartaSans-Regular.ttf", 400)
    + _fonte("PlusJakartaSans-Medium.ttf", 500)
    + _fonte("PlusJakartaSans-Bold.ttf", 700)
    + _fonte("PlusJakartaSans-ExtraBold.ttf", 800)
    + f"""
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{LADO}px;height:{LADO}px;overflow:hidden}}
body{{font-family:'Jakarta',sans-serif;background:{FUNDO};color:{TINTA};
  -webkit-font-smoothing:antialiased}}
.peca{{position:relative;width:{LADO}px;height:{LADO}px;overflow:hidden;
  background:{FUNDO}}}

/* o selo do módulo: a única peça "mono" do sistema, feita com caixa alta e
   entreletra larga em vez de uma segunda família só para isso */
.selo{{display:inline-flex;align-items:center;gap:12px;padding:10px 20px 10px 16px;
  border-radius:999px;font-size:21px;font-weight:800;letter-spacing:.13em;
  text-transform:uppercase}}
.selo .ponto{{width:12px;height:12px;border-radius:999px;flex:none}}
.rotulo{{font-size:22px;font-weight:800;letter-spacing:.20em;
  text-transform:uppercase;color:{TINTA_FRACA}}}

h1{{font-size:92px;font-weight:800;line-height:1.03;letter-spacing:-.035em;
  text-wrap:balance}}
h2{{font-size:58px;font-weight:800;line-height:1.08;letter-spacing:-.03em}}
.corpo{{font-size:31px;font-weight:500;line-height:1.42;color:{TINTA_MEDIA}}}

/* a janela do programa, INTEIRA. A borda e a sombra existem para separá-la do
   fundo claro - sem elas, tela clara sobre fundo claro vira mancha. */
.janela{{border-radius:16px;overflow:hidden;border:1px solid {FIO};
  box-shadow:0 30px 60px -26px rgba(20,18,31,.30), 0 3px 10px rgba(20,18,31,.05)}}
.janela img{{display:block;width:100%}}

/* a moldura de programa: barra de janela + a captura */
.programa{{border-radius:18px;overflow:hidden;border:1px solid {FIO};
  background:{BRANCO};
  box-shadow:0 34px 64px -28px rgba(20,18,31,.34), 0 3px 10px rgba(20,18,31,.06)}}
.programa-barra{{height:44px;display:flex;align-items:center;gap:10px;
  padding-left:20px;background:#EFECF6;border-bottom:1px solid {FIO}}}
.bolinha{{width:13px;height:13px;border-radius:99px}}
.programa{{position:relative}}
.programa img{{display:block}}
/* O esmaecimento do rodape.
   A janela do programa tem rolagem: a ultima linha da tabela fica pela metade
   na borda de baixo, e na foto isso le como letra cortada - defeito de
   montagem, nao software com mais conteudo. O esmaecimento diz "continua" em
   vez de "acabou errado". E funcao, nao enfeite: e a unica passagem de cor
   deste sistema. */
.desvanece{{position:absolute;left:1px;right:1px;bottom:1px;height:78px;
  border-radius:0 0 17px 17px;
  background:linear-gradient(to bottom, rgba(255,255,255,0), {BRANCO} 86%)}}

/* o aparelho: moldura preta com a tela dentro */
.fone{{border-radius:44px;padding:11px;background:#16141F;position:relative;
  box-shadow:0 40px 70px -30px rgba(20,18,31,.55), 0 0 0 1px rgba(20,18,31,.12)}}
.fone-tela{{overflow:hidden;border-radius:34px}}
.fone img{{display:block}}
.fone::after{{content:"";position:absolute;left:50%;transform:translateX(-50%);
  top:20px;width:84px;height:7px;border-radius:99px;background:#2E2B3C}}
"""
)


def escapar(texto: str) -> str:
    return html.escape(str(texto)).replace("\n", "<br>")


def endereco_da_tela(nome: str) -> str:
    return (RAIZ / "build" / "criativos" / "telas" / f"{nome}.png").as_uri()


def tela(nome: str, largura: int) -> str:
    """A captura INTEIRA, na largura pedida. Nunca cortada, nunca distorcida."""
    return (f'<div class="janela" style="width:{largura}px">'
            f'<img src="{endereco_da_tela(nome)}"></div>')


def janela_de_programa(nome: str, largura: int) -> str:
    """A captura dentro de uma barra de janela, como todo programa tem.

    A referencia de quem vende software faz isso sempre: a moldura diz "isto e
    um programa de computador" antes de qualquer texto. Sem ela, a captura
    parece recorte de print de WhatsApp.
    """
    altura = round(largura * TELA_A / TELA_L)
    return (f'<div class="programa" style="width:{largura}px">'
            f'<div class="programa-barra">'
            f'<span class="bolinha" style="background:#F45B4E"></span>'
            f'<span class="bolinha" style="background:#F5B63F"></span>'
            f'<span class="bolinha" style="background:#3FBF6A"></span>'
            f'</div>'
            f'<img src="{endereco_da_tela(nome)}" '
            f'style="width:{largura}px;height:{altura}px">'
            f'<span class="desvanece"></span></div>')


def telefone(nome: str, largura: int, altura: int = 0) -> str:
    """A captura do celular dentro de um aparelho.

    A medida que manda e a LARGURA: a tela do celular entra inteira na
    horizontal e, se a peca for mais baixa que o aparelho, e o RODAPE que fica
    de fora. Antes isto era dimensionado pela altura, e o telefone estourava a
    coluna - o anuncio saia com "Escova" virando "scova" nas duas bordas.
    """
    tela_l = largura - 22                       # menos a moldura dos dois lados
    tela_a = round(tela_l * FONE_A / FONE_L)
    alto = altura or (tela_a + 22)
    return (f'<div class="fone" style="width:{largura}px;height:{alto}px">'
            f'<div class="fone-tela" style="height:{alto - 22}px">'
            f'<img src="{endereco_da_tela(nome)}" style="width:{tela_l}px">'
            f"</div></div>")


def pagina(corpo: str, css_extra: str = "") -> str:
    return (f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
            f"<style>{CSS_BASE}{css_extra}</style></head><body>{corpo}</body></html>")


def selo(codigo: str) -> str:
    """O nome do módulo na cor dele, num selo claro."""
    return (f'<span class="selo" style="background:{FUNDO_MODULO[codigo]};'
            f'color:{COR_MODULO[codigo]}">'
            f'<span class="ponto" style="background:{COR_MODULO[codigo]}"></span>'
            f"{escapar(NOME_MODULO[codigo])}</span>")


#: Tudo é desenhado no DOBRO de pixels e reduzido no fim.
#:
#: O Mercado Livre deixa ampliar a foto, e é ampliando que o comprador decide
#: se o programa parece sério. Em 1x a letra fina da captura ficava com a
#: borda serrilhada; em 2x, reduzida depois com suavização, ela fica limpa.
ESCALA = 2


def renderizar_em(endereco: str, destino: Path, navegador: str,
                  largura: int, altura: int, escala: int = ESCALA) -> None:
    """Fotografa um endereço já pronto (arquivo ou site)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [navegador, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--default-background-color=00000000",
         f"--screenshot={destino}", f"--window-size={largura},{altura}",
         f"--force-device-scale-factor={escala}",
         # a página do celular desenha depois de ler o cache: sem este prazo o
         # Chrome fotografa o esqueleto cinza em vez dos números
         "--virtual-time-budget=6000", endereco],
        check=True, capture_output=True,
    )


def renderizar(html_texto: str, destino: Path, navegador: str) -> None:
    """HTML -> PNG de 1200x1200, desenhado em 2400 e reduzido com suavização."""
    temporario = destino.with_suffix(".html")
    temporario.parent.mkdir(parents=True, exist_ok=True)
    temporario.write_text(html_texto, encoding="utf-8")
    renderizar_em(temporario.as_uri(), destino, navegador, LADO, LADO)
    reduzir(destino, LADO)
    temporario.unlink(missing_ok=True)


def reduzir(arquivo: Path, lado: int) -> None:
    """Reduz a imagem para `lado` px com suavização (Qt faz isso melhor que o
    navegador, que só sabe redimensionar na hora de desenhar)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication([])
    imagem = QImage(str(arquivo))
    if imagem.width() == lado:
        return
    imagem.scaled(lado, lado, Qt.AspectRatioMode.IgnoreAspectRatio,
                  Qt.TransformationMode.SmoothTransformation).save(str(arquivo), "PNG")


def achar_navegador() -> str:
    """O Chrome vem primeiro de propósito.

    O Edge desta máquina aceita `--screenshot`, responde 0 e NÃO grava arquivo
    nenhum - em qualquer um dos três modos de headless, e sem escrever uma
    linha de erro. O `publicar_site.ps1` usa o Edge só para PDF, que funciona;
    para imagem, quem grava é o Chrome.
    """
    for caminho in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ):
        if Path(caminho).exists():
            return caminho
    raise SystemExit("Nao achei o Chrome nem o Edge para gerar as imagens.")
