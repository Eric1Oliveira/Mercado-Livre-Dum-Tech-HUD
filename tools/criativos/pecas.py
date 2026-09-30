"""Os sete moldes de peça. Um molde = uma coisa dita.

Miniatura de Mercado Livre é pequena: peça que diz duas coisas não diz
nenhuma. Cada molde aqui tem UM assunto, um título grande e no máximo uma
linha de apoio.

A CONTA QUE MANDA NO MOLDE DE MÓDULO
    A captura tem 1360x860 (proporção 1,58). Numa peça de 1200x1200 com 84 de
    margem, ela cabe INTEIRA em 1032 de largura por 653 de altura. Sobram 379
    px em cima, que é exatamente o espaço do selo, do título de duas linhas e
    da linha de apoio. Nada é cortado porque a conta fecha, não porque alguém
    empurrou a imagem para fora da arte.
"""

from __future__ import annotations

from .base import (
    BRANCO, COR_MODULO, FIO, FUNDO, FUNDO_MODULO, LADO, MARGEM, NOME_MODULO,
    TINTA, TINTA_FRACA, TINTA_MEDIA, VIOLETA, VIOLETA_CLARO, VIOLETA_FORTE,
    altura_da_tela, escapar, janela_de_programa, pagina, selo, tela, telefone,
)

#: A captura ocupa a LARGURA INTEIRA da peça. Com margem dos dois lados ela
#: encolhia, e o que encolhe numa captura de sistema é justamente a letra —
#: que é o que o comprador quer ler. Inteira quer dizer inteira: nada é
#: cortado, ela só encosta nas bordas.
TELA_NA_PECA = LADO


# ============================================================ 1. a capa =====
def capa(captura: str) -> str:
    """Fundo branco, a tela do programa inteira, e mais nada.

    O Mercado Livre não aceita texto, logo nem moldura na primeira foto. A
    restrição joga a favor: o produto aparece sozinho, sem promessa em volta.
    """
    largura = 1060
    css = f"""
    body,.capa{{background:{BRANCO}}}
    .capa{{width:{LADO}px;height:{LADO}px;display:grid;place-items:center}}
    .capa .janela{{border-color:#E8E5F0;
      box-shadow:0 34px 70px -30px rgba(20,18,31,.26), 0 2px 8px rgba(20,18,31,.05)}}
    """
    return pagina(f'<div class="peca capa">{tela(captura, largura)}</div>', css)


# =========================================================== 2. a dor =======
def dor(nicho: str, titulo: str, apoio: str, cor: str) -> str:
    """A pergunta que o dono do negócio já se fez sozinho, escrita grande."""
    css = f"""
    .dor{{padding:{MARGEM}px;display:flex;flex-direction:column;
      justify-content:center;height:{LADO}px;background:{BRANCO}}}
    .dor .faixa{{position:absolute;left:0;top:0;width:14px;height:{LADO}px;
      background:{cor}}}
    .dor .rotulo{{color:{cor};margin-bottom:46px}}
    .dor h1{{font-size:96px;max-width:990px}}
    .dor .risco{{width:112px;height:8px;border-radius:99px;background:{cor};
      margin:50px 0 38px}}
    .dor .corpo{{max-width:900px;font-size:35px}}
    """
    corpo = f"""<div class="peca dor"><div class="faixa"></div>
      <div class="rotulo">{escapar(nicho)}</div>
      <h1>{escapar(titulo)}</h1>
      <div class="risco"></div>
      <div class="corpo">{escapar(apoio)}</div>
    </div>"""
    return pagina(corpo, css)


# ======================================================== 3. um módulo ======
def modulo(codigo: str, titulo: str, apoio: str, captura: str) -> str:
    """O módulo pelo trabalho que faz, não pelo nome que tem.

    Texto em cima, tela INTEIRA embaixo, com a mesma margem dos dois lados.
    """
    cor = COR_MODULO[codigo]
    altura = altura_da_tela(TELA_NA_PECA)
    css = f"""
    .mod{{padding:{MARGEM}px;height:{LADO}px;position:relative;background:{BRANCO}}}
    .mod .selo{{margin-bottom:30px}}
    .mod h2{{max-width:1010px;font-size:55px}}
    .mod .corpo{{margin-top:20px;max-width:1000px;font-size:29px}}
    /* 26 px de folga embaixo: a borda inferior da janela fica visível, e
       ninguém precisa se perguntar se a tela foi cortada ali */
    .mod .palco{{position:absolute;left:0;bottom:26px;width:{LADO}px;height:{altura}px}}
    .mod .palco .janela{{border-radius:16px}}
    /* o chão colorido: uma faixa clara atrás da janela, para a tela do
       programa (que é clara) não sumir no fundo branco da peça */
    .mod .chao{{position:absolute;left:0;right:0;bottom:0;
      height:{altura + 60}px;background:{FUNDO_MODULO[codigo]}}}
    """
    corpo = f"""<div class="peca mod"><div class="chao"></div>
      {selo(codigo)}
      <h2>{escapar(titulo)}</h2>
      <div class="corpo">{escapar(apoio)}</div>
      <div class="palco">{tela(captura, TELA_NA_PECA)}</div>
    </div>"""
    return pagina(corpo, css)


# ====================================================== 4. a integração =====
def integracao(titulo: str, passos: list[tuple[str, str]], rodape: str) -> str:
    """O que um módulo faz acontecer no outro.

    É uma escada ligada por um fio, não três cartões iguais lado a lado: o
    ponto da peça é que um passo PUXA o outro.
    """
    linhas = []
    for i, (codigo, texto) in enumerate(passos):
        cor = COR_MODULO[codigo]
        ultimo = i == len(passos) - 1
        linhas.append(f"""
        <div class="passo">
          <div class="marca">
            <span class="bola" style="background:{cor}"></span>
            {'' if ultimo else f'<span class="fio-v" style="background:{cor}"></span>'}
          </div>
          <div class="texto">
            <div class="quem" style="color:{cor}">{escapar(NOME_MODULO[codigo])}</div>
            <div class="oque">{escapar(texto)}</div>
          </div>
        </div>""")

    css = f"""
    .int{{padding:{MARGEM}px;height:{LADO}px;display:flex;flex-direction:column;
      background:{BRANCO}}}
    .int h2{{font-size:60px;max-width:960px;margin-bottom:46px}}
    /* a escada ocupa o que sobrar entre o título e o rodapé: com três passos
       curtos, o espaço morto no meio fazia a peça parecer inacabada */
    .escada{{flex:1;display:flex;flex-direction:column;justify-content:space-evenly}}
    .passo{{display:flex;gap:30px;align-items:stretch}}
    .marca{{display:flex;flex-direction:column;align-items:center;width:28px;flex:none}}
    .bola{{width:28px;height:28px;border-radius:99px;flex:none;margin-top:10px}}
    .fio-v{{width:4px;flex:1;border-radius:99px;margin-top:10px;min-height:34px;
      opacity:.35}}
    .texto{{padding-bottom:24px}}
    .quem{{font-size:23px;font-weight:800;letter-spacing:.17em;text-transform:uppercase}}
    .oque{{font-size:39px;font-weight:700;line-height:1.3;margin-top:10px;
      max-width:940px;letter-spacing:-.02em}}
    .rodape{{margin-top:8px;font-size:30px;font-weight:700;color:{VIOLETA_FORTE};
      background:{VIOLETA_CLARO};padding:24px 30px;border-radius:14px}}
    """
    corpo = f"""<div class="peca int">
      <h2>{escapar(titulo)}</h2>
      <div class="escada">{''.join(linhas)}</div>
      <div class="rodape">{escapar(rodape)}</div>
    </div>"""
    return pagina(corpo, css)


# ==================================================== 5. antes × depois =====
def antes_depois(antes: list[str], depois: list[str], cor: str) -> str:
    """Os dois lados da mesma semana.

    Sem foto de caderno: a comparação é tipográfica, porque o que muda não é o
    objeto, é o que a pessoa consegue responder.
    """
    def itens(lista, classe):
        return "".join(f'<li class="{classe}">{escapar(t)}</li>' for t in lista)

    css = f"""
    .ad{{height:{LADO}px;display:grid;grid-template-rows:1fr 1fr}}
    .lado{{padding:64px {MARGEM}px;display:flex;flex-direction:column;
      justify-content:center}}
    .velho{{background:{FUNDO}}}
    .novo{{background:{BRANCO};border-top:5px solid {cor}}}
    .cabeca{{font-size:22px;font-weight:800;letter-spacing:.20em;
      text-transform:uppercase;margin-bottom:26px}}
    .velho .cabeca{{color:{TINTA_FRACA}}}
    .novo .cabeca{{color:{cor}}}
    ul{{list-style:none}}
    li{{font-size:37px;font-weight:700;line-height:1.34;letter-spacing:-.02em;
      padding-left:50px;position:relative;margin-bottom:12px}}
    .ruim{{color:{TINTA_FRACA}}}
    .ruim::before{{content:"";position:absolute;left:0;top:22px;width:28px;height:4px;
      border-radius:99px;background:{TINTA_FRACA}}}
    .bom{{color:{TINTA}}}
    .bom::before{{content:"";position:absolute;left:2px;top:13px;width:12px;height:24px;
      border:solid {cor};border-width:0 5px 5px 0;transform:rotate(42deg)}}
    """
    corpo = f"""<div class="peca ad">
      <div class="lado velho"><div class="cabeca">Como é hoje</div>
        <ul>{itens(antes, 'ruim')}</ul></div>
      <div class="lado novo"><div class="cabeca">Como fica</div>
        <ul>{itens(depois, 'bom')}</ul></div>
    </div>"""
    return pagina(corpo, css)


# ======================================================= 6. o que vem =======
def o_que_vem(titulo: str, modulos: list[tuple[str, str]], rodape: str) -> str:
    """Os módulos do jogo, cada um com o trabalho que faz.

    Lista em coluna, não grade de cartões: o olho desce uma vez e lê tudo.
    """
    linhas = "".join(f"""
      <div class="linha">
        <span class="bola" style="background:{COR_MODULO[c]}"></span>
        <div><div class="nome">{escapar(NOME_MODULO[c])}</div>
        <div class="faz">{escapar(t)}</div></div>
      </div>""" for c, t in modulos)

    css = f"""
    .vem{{padding:{MARGEM}px;height:{LADO}px;display:flex;flex-direction:column;
      background:{BRANCO}}}
    .vem h2{{font-size:56px;max-width:930px;margin-bottom:40px}}
    .lista{{flex:1;display:flex;flex-direction:column;justify-content:center}}
    .linha{{display:flex;gap:26px;align-items:flex-start;padding:22px 0;
      border-top:1px solid {FIO}}}
    .linha:last-of-type{{border-bottom:1px solid {FIO}}}
    .bola{{width:22px;height:22px;border-radius:99px;flex:none;margin-top:11px}}
    .nome{{font-size:37px;font-weight:800;letter-spacing:-.02em}}
    .faz{{font-size:28px;font-weight:500;color:{TINTA_MEDIA};margin-top:3px}}
    .rodape{{margin-top:34px;font-size:30px;font-weight:700;color:{VIOLETA_FORTE};
      background:{VIOLETA_CLARO};padding:24px 30px;border-radius:14px}}
    """
    corpo = f"""<div class="peca vem"><h2>{escapar(titulo)}</h2>
      <div class="lista">{linhas}</div>
      <div class="rodape">{escapar(rodape)}</div></div>"""
    return pagina(corpo, css)


# ======================================================== 7. a objeção ======
def promessa(titulo: str, itens: list[tuple[str, str]]) -> str:
    """O que trava a compra, respondido de frente: mensalidade e internet."""
    blocos = "".join(f"""
      <div class="bloco"><div class="forte">{escapar(a)}</div>
      <div class="leve">{escapar(b)}</div></div>""" for a, b in itens)

    css = f"""
    .pr{{padding:{MARGEM}px;height:{LADO}px;display:flex;flex-direction:column;
      justify-content:center;background:{BRANCO}}}
    .pr .faixa{{position:absolute;left:0;top:0;width:14px;height:{LADO}px;
      background:{VIOLETA}}}
    .pr h1{{font-size:98px;max-width:980px}}
    .pr .risco{{width:112px;height:8px;border-radius:99px;background:{VIOLETA};
      margin:46px 0 14px}}
    .bloco{{padding:24px 0;border-bottom:1px solid {FIO}}}
    .forte{{font-size:38px;font-weight:800;letter-spacing:-.02em}}
    .leve{{font-size:28px;font-weight:500;color:{TINTA_MEDIA};margin-top:5px}}
    """
    corpo = f"""<div class="peca pr"><div class="faixa"></div>
      <h1>{escapar(titulo)}</h1><div class="risco"></div>{blocos}</div>"""
    return pagina(corpo, css)


# ======================================================== 8. a entrega ======
def entrega(titulo: str, passos: list[str], rodape: str) -> str:
    """Como a coisa chega. Produto digital que não explica isso não vende."""
    linhas = "".join(f"""
      <div class="passo"><span class="num">{i}</span>
      <div class="txt">{escapar(t)}</div></div>"""
      for i, t in enumerate(passos, 1))

    css = f"""
    .en{{padding:{MARGEM}px;height:{LADO}px;display:flex;flex-direction:column;
      justify-content:center;background:{BRANCO}}}
    .en h2{{font-size:60px;max-width:930px;margin-bottom:56px}}
    .passo{{display:flex;gap:30px;align-items:center;margin-bottom:34px}}
    .num{{width:72px;height:72px;border-radius:99px;flex:none;display:grid;
      place-items:center;font-size:32px;font-weight:800;color:{BRANCO};
      background:{VIOLETA}}}
    .txt{{font-size:38px;font-weight:700;line-height:1.3;letter-spacing:-.02em;
      max-width:930px}}
    .rodape{{margin-top:26px;font-size:29px;font-weight:600;color:{TINTA_MEDIA};
      border-top:1px solid {FIO};padding-top:32px}}
    """
    corpo = f"""<div class="peca en"><h2>{escapar(titulo)}</h2>{linhas}
      <div class="rodape">{escapar(rodape)}</div></div>"""
    return pagina(corpo, css)


# ================================================== 9. a tela explicada =====
def explicada(titulo: str, captura: str, pinos: list[tuple[int, str]]) -> str:
    """A tela com marcadores na borda e a legenda embaixo.

    É o padrão que quem vende software usa há anos, e que faltava aqui: a
    captura sozinha mostra QUE existe uma tela; os marcadores mostram O QUE
    olhar nela. Sem eles, o comprador vê "um monte de coisa" e passa.

    OS MARCADORES FICAM NA BORDA, NUNCA EM CIMA DO CONTEÚDO.
        Espalhados sobre a tela, eles tapavam justamente o número que estavam
        apontando — o pino de "quanto entrou" cobria o "R$ 3.770,00". Na borda
        esquerda, com uma linha até a altura certa, eles apontam sem esconder.

    `pinos` são (y% da altura da captura, texto).
    """
    largura = LADO - MARGEM * 2
    altura = altura_da_tela(largura) + 44          # + a barra da janela
    marcas = "".join(
        f'<span class="risca" style="top:{y}%"></span>'
        f'<span class="pino" style="top:{y}%">{i}</span>'
        for i, (y, _) in enumerate(pinos, 1))
    legenda = "".join(
        f'<div class="verbete"><span class="num">{i}</span>'
        f"<span>{escapar(t)}</span></div>"
        for i, (_, t) in enumerate(pinos, 1))

    css = f"""
    .ex{{padding:{MARGEM}px;height:{LADO}px;display:flex;flex-direction:column;
      background:{BRANCO}}}
    .ex h2{{font-size:52px;max-width:1000px;margin-bottom:30px}}
    .quadro{{position:relative;width:{largura}px;height:{altura}px;flex:none}}
    /* a risca sai do pino e entra na tela, dizendo a altura exata */
    .risca{{position:absolute;left:26px;width:96px;height:4px;border-radius:99px;
      background:{VIOLETA};opacity:.42;transform:translateY(-50%)}}
    .pino{{position:absolute;left:0;transform:translate(-50%,-50%);width:56px;
      height:56px;border-radius:99px;background:{VIOLETA};color:{BRANCO};
      display:grid;place-items:center;font-size:28px;font-weight:800;
      box-shadow:0 0 0 8px {BRANCO}, 0 10px 20px rgba(20,18,31,.24)}}
    .legenda{{margin-top:auto;display:flex;flex-direction:column;gap:14px}}
    .verbete{{display:flex;gap:16px;align-items:baseline;font-size:29px;
      font-weight:600;color:{TINTA}}}
    .verbete .num{{flex:none;width:38px;height:38px;border-radius:99px;
      background:{VIOLETA_CLARO};color:{VIOLETA_FORTE};display:inline-grid;
      place-items:center;font-size:21px;font-weight:800;transform:translateY(4px)}}
    """
    corpo = f"""<div class="peca ex">
      <h2>{escapar(titulo)}</h2>
      <div class="quadro">{janela_de_programa(captura, largura)}{marcas}</div>
      <div class="legenda">{legenda}</div>
    </div>"""
    return pagina(corpo, css)


# ===================================================== 10. o celular ========
def no_celular(titulo: str, apoio: str, captura: str,
               destaques: list[str]) -> str:
    """O aparelho de verdade, com o resumo da loja dentro.

    Não é o app do Hub: é a página que o dono abre no celular depois de ler um
    QR Code. Por isso a peça diz o que ela mostra — senão o comprador acha que
    está levando um aplicativo de loja e reclama depois.
    """
    itens = "".join(f'<li>{escapar(t)}</li>' for t in destaques)
    css = f"""
    .cel{{height:{LADO}px;display:grid;grid-template-columns:1fr 452px;
      background:{BRANCO}}}
    .cel .texto{{padding:{MARGEM}px 0 {MARGEM}px {MARGEM}px;display:flex;
      flex-direction:column;justify-content:center}}
    .cel h2{{font-size:56px;max-width:560px}}
    .cel .corpo{{margin-top:22px;max-width:560px;font-size:29px}}
    .cel ul{{list-style:none;margin-top:36px;display:flex;flex-direction:column;
      gap:16px}}
    .cel li{{font-size:29px;font-weight:700;padding-left:44px;position:relative;
      max-width:540px;line-height:1.3}}
    .cel li::before{{content:"";position:absolute;left:2px;top:6px;width:11px;
      height:21px;border:solid {VIOLETA};border-width:0 5px 5px 0;
      transform:rotate(42deg)}}
    .cel .palco{{position:relative;background:{VIOLETA_CLARO};
      display:flex;align-items:center;justify-content:center;overflow:hidden}}
    """
    corpo = f"""<div class="peca cel">
      <div class="texto">
        <h2>{escapar(titulo)}</h2>
        <div class="corpo">{escapar(apoio)}</div>
        <ul>{itens}</ul>
      </div>
      <div class="palco">{telefone(captura, 416)}</div>
    </div>"""
    return pagina(corpo, css)
