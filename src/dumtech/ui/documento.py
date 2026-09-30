"""O documento A4 - o papel que vai por e-mail.

As 40 colunas de `ui/recibo.py` estao certas para a bobina termica do balcao e
erradas para uma proposta comercial: ninguem manda arte ASCII para um cliente
decidir uma compra de mil reais. Aqui e o contrario - tipografia, tabela de
itens alinhada, logotipo, e um PDF no fim.

Mesmo desenho do `recibo.py`: **um motor, varios consumidores**. Este arquivo
sabe montar a *forma* (cabecalho, tabela, totais, rodape); cada aplicativo
escreve o *conteudo*. Nada aqui conhece orcamento nem ordem de servico.

Sobre o HTML: quem desenha e o `QTextDocument`, que entende um subconjunto de
CSS - sem flex, sem grid, sem border-radius. Por isso a estrutura e feita de
tabelas e os estilos vao na propria tag: seletor de classe e uma aposta que
varia entre versoes do Qt, estilo na tag sempre vale.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Iterable, Sequence

from PySide6.QtCore import QMarginsF, QSizeF, QUrl
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPdfWriter, QTextDocument

# ---------------------------------------------------------------------- tinta
#: cinza-azulado escuro: preto puro no papel fica duro, e no PDF fica sujo
TINTA = "#16202b"
SUAVE = "#5d6b7a"
RISCO = "#c9d0d8"
FUNDO = "#f2f4f7"

TITULO = "Georgia, 'Times New Roman', serif"
CORPO = "'Segoe UI', Arial, sans-serif"

#: A4 a 96 dpi, com margem de 15 mm - o mesmo numero da previa e do PDF
LARGURA = 794
MARGEM_MM = 15.0
RESOLUCAO = 96

DIREITA = "right"
CENTRO = "center"
ESQUERDA = "left"

LOGO = "empresa:logo"
ALTURA_LOGO = 54


# --------------------------------------------------------------------- pedacos
def cabecalho(empresa=None, com_logo: bool = False) -> str:
    """Quem esta mandando o papel: logotipo de um lado, endereco do outro."""
    if empresa is None or not empresa.preenchida:
        return ""

    marca = []
    if com_logo:
        marca.append(f'<img src="{LOGO}" height="{ALTURA_LOGO}">')
    marca.append(
        f'<div style="font-family:{TITULO};font-size:16pt;color:{TINTA};">'
        f"{escape(empresa.nome)}</div>"
    )
    if empresa.razao_social.strip() and empresa.razao_social.strip() != empresa.nome.strip():
        marca.append(_pequeno(empresa.razao_social))
    if empresa.documento_formatado:
        marca.append(_pequeno(f"{empresa.tipo_documento}: {empresa.documento_formatado}"))

    contato = [_pequeno(parte, DIREITA) for parte in (
        empresa.endereco_completo, empresa.telefone_formatado, empresa.email.strip()
    ) if parte]

    return (
        f'<table width="100%" cellspacing="0" cellpadding="0">'
        f'<tr><td width="60%" valign="top">{"".join(marca)}</td>'
        f'<td width="40%" valign="top">{"".join(contato)}</td></tr></table>'
        + regua(2)
    )


def titulo(texto: str, numero: str = "", data: str = "") -> str:
    """O nome do documento e a sua identificacao, na mesma linha."""
    lado = " &nbsp;&middot;&nbsp; ".join(escape(p) for p in (numero, data) if p)
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0"><tr>'
        f'<td valign="bottom"><span style="font-family:{TITULO};font-size:15pt;'
        f'color:{TINTA};">{escape(texto)}</span></td>'
        f'<td align="right" valign="bottom"><span style="font-family:{CORPO};'
        f'font-size:10pt;color:{SUAVE};">{lado}</span></td>'
        f"</tr></table>"
    )


def campos(pares: Sequence[tuple[str, str]], colunas: int = 2) -> str:
    """Rotulo em cima, valor embaixo - o bloco de dados do cliente/aparelho."""
    celulas = [
        f'<td width="{100 // colunas}%" valign="top" '
        f'style="padding:0 12px 10px 0;">{_rotulo(rotulo)}{_valor(valor)}</td>'
        for rotulo, valor in pares if str(valor).strip()
    ]
    if not celulas:
        return ""
    linhas = [
        "<tr>" + "".join(celulas[i:i + colunas]) + "</tr>"
        for i in range(0, len(celulas), colunas)
    ]
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="margin-top:14px;">{"".join(linhas)}</table>'
    )


def tabela(
    colunas: Sequence[str],
    linhas: Iterable[Sequence[str]],
    alinhamentos: Sequence[str] = (),
    larguras: Sequence[str] = (),
) -> str:
    """A tabela de itens. Sem zebra: a linha fina separa melhor e imprime igual."""
    linhas = list(linhas)
    if not linhas:
        return ""

    def alinhar(indice: int) -> str:
        return alinhamentos[indice] if indice < len(alinhamentos) else ESQUERDA

    cabeca = "".join(
        f'<td align="{alinhar(i)}" width="{larguras[i] if i < len(larguras) else ""}" '
        f'style="border-bottom:1px solid {TINTA};padding:0 6px 5px 6px;">'
        f'<span style="font-family:{CORPO};font-size:8pt;color:{SUAVE};">'
        f"{escape(str(nome)).upper()}</span></td>"
        for i, nome in enumerate(colunas)
    )
    corpo = "".join(
        "<tr>" + "".join(
            f'<td align="{alinhar(i)}" valign="top" '
            f'style="border-bottom:1px solid {RISCO};padding:7px 6px;">'
            f'<span style="font-family:{CORPO};font-size:10pt;color:{TINTA};">'
            f"{_texto(celula)}</span></td>"
            for i, celula in enumerate(linha)
        ) + "</tr>"
        for linha in linhas
    )
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="margin-top:16px;"><tr>{cabeca}</tr>{corpo}</table>'
    )


def totais(pares: Sequence[tuple[str, str]], total: tuple[str, str] | None = None) -> str:
    """Encostado a direita, como em qualquer nota - o olho procura ali."""
    linhas = [
        f'<tr><td align="right" style="padding:2px 6px;">{_pequeno(rotulo, DIREITA)}</td>'
        f'<td align="right" width="130" style="padding:2px 6px;">'
        f'<span style="font-family:{CORPO};font-size:10pt;color:{TINTA};">'
        f"{escape(valor)}</span></td></tr>"
        for rotulo, valor in pares
    ]
    if total is not None:
        rotulo, valor = total
        linhas.append(
            f'<tr><td align="right" style="border-top:1px solid {TINTA};padding:7px 6px 0 6px;">'
            f'<span style="font-family:{CORPO};font-size:11pt;color:{TINTA};">'
            f"<b>{escape(rotulo)}</b></span></td>"
            f'<td align="right" style="border-top:1px solid {TINTA};padding:7px 6px 0 6px;">'
            f'<span style="font-family:{TITULO};font-size:14pt;color:{TINTA};">'
            f"<b>{escape(valor)}</b></span></td></tr>"
        )
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:10px;">'
        f'<tr><td width="55%"></td><td><table width="100%" cellspacing="0" '
        f'cellpadding="0">{"".join(linhas)}</table></td></tr></table>'
    )


def secao(rotulo: str, texto: str) -> str:
    """Um paragrafo com titulo - condicoes, diagnostico, observacoes."""
    if not str(texto).strip():
        return ""
    return (
        f'<div style="margin-top:16px;">{_rotulo(rotulo)}'
        f'<div style="font-family:{CORPO};font-size:10pt;color:{TINTA};">'
        f"{_texto(texto)}</div></div>"
    )


def destaque(texto: str) -> str:
    """A faixa que muda a leitura do papel inteiro: APROVADA, CANCELADA."""
    return (
        f'<table width="100%" cellspacing="0" cellpadding="8" '
        f'style="margin-top:16px;background-color:{FUNDO};">'
        f'<tr><td align="center"><span style="font-family:{CORPO};font-size:11pt;'
        f'color:{TINTA};"><b>{escape(texto).upper()}</b></span></td></tr></table>'
    )


def assinatura(texto: str) -> str:
    """A linha onde alguem assina - so faz sentido no papel impresso."""
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:42px;">'
        f'<tr><td width="55%" style="border-top:1px solid {TINTA};padding-top:5px;">'
        f"{_pequeno(texto)}</td><td></td></tr></table>"
    )


def rodape(empresa=None, nota: str = "") -> str:
    partes = []
    if empresa is not None and empresa.rodape.strip():
        partes.append(_pequeno(empresa.rodape, CENTRO))
    if nota:
        partes.append(_pequeno(nota, CENTRO))
    if not partes:
        return ""
    return regua(1) + "".join(partes)


def regua(espessura: int = 1) -> str:
    """Uma linha horizontal.

    O ponto e o `&nbsp;` de 1pt: celula vazia colada em outra tabela vira uma
    tabela de altura zero e a borda some. Com um pingo de conteudo, fica.
    """
    return (
        ar(9)
        + f'<table width="100%" cellspacing="0" cellpadding="0"><tr>'
        f'<td style="border-top:{espessura}px solid '
        f'{TINTA if espessura > 1 else RISCO};">'
        f'<div style="font-size:1pt;">&nbsp;</div></td></tr></table>'
        + ar(7)
    )


def ar(pontos: int) -> str:
    """Espaco vertical medido.

    `margin` em tabela o Qt aplica quando quer; um paragrafo com altura
    conhecida ele sempre respeita. Entao o respiro do documento e explicito.
    """
    return f'<div style="font-size:{pontos}pt;">&nbsp;</div>' 


# ---------------------------------------------------------------------- pagina
def pagina(partes: Iterable[str]) -> str:
    """Junta os pedacos numa folha. Pedaco vazio simplesmente nao entra."""
    corpo = "".join(parte for parte in partes if parte)
    return (
        f'<body style="font-family:{CORPO};font-size:10pt;color:{TINTA};">'
        f"{corpo}</body>"
    )


def render(html: str, empresa=None, paths=None, largura: int = LARGURA) -> QTextDocument:
    """Vira um documento pronto para desenhar - na tela ou no PDF.

    O logotipo entra como recurso do documento em vez de caminho no `src`:
    assim o mesmo HTML funciona na previa, na impressora e no PDF, sem depender
    de o Qt resolver `file://` com acento no caminho (e ha acento no caminho).
    """
    documento = QTextDocument()
    documento.setDocumentMargin(0)
    documento.setTextWidth(largura - 2 * _margem_px())
    if empresa is not None:
        caminho = empresa.caminho_logo(paths)
        if caminho is not None:
            imagem = QImage(str(caminho))
            if not imagem.isNull():
                documento.addResource(
                    QTextDocument.ResourceType.ImageResource, QUrl(LOGO), imagem
                )
    documento.setHtml(html)
    return documento


def tem_logo(empresa=None, paths=None) -> bool:
    """Se ha logotipo utilizavel - quem monta o HTML precisa saber antes."""
    if empresa is None:
        return False
    caminho = empresa.caminho_logo(paths)
    return caminho is not None and not QImage(str(caminho)).isNull()


def salvar_pdf(html: str, destino: Path, empresa=None, paths=None) -> Path:
    """Grava a folha em PDF. Devolve o caminho gravado."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    escritor = QPdfWriter(str(destino))
    escritor.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    escritor.setPageMargins(
        QMarginsF(MARGEM_MM, MARGEM_MM, MARGEM_MM, MARGEM_MM), QPageLayout.Unit.Millimeter
    )
    # a mesma resolucao da previa: o PDF sai igual ao que o cliente viu na tela
    escritor.setResolution(RESOLUCAO)

    documento = render(html, empresa, paths)
    documento.setPageSize(QSizeF(escritor.pageLayout().paintRectPixels(RESOLUCAO).size()))
    documento.print_(escritor)
    return destino


def imprimir(html: str, impressora, empresa=None, paths=None) -> None:
    """Manda a folha para a impressora ja escolhida no dialogo do sistema."""
    resolucao = impressora.resolution()
    documento = render(html, empresa, paths)
    documento.setTextWidth(impressora.pageLayout().paintRectPixels(resolucao).width())
    documento.print_(impressora)


def _margem_px() -> int:
    return round(MARGEM_MM / 25.4 * RESOLUCAO)


# --------------------------------------------------------------------- miudezas
def _rotulo(texto: str) -> str:
    return (
        f'<div style="font-family:{CORPO};font-size:8pt;color:{SUAVE};">'
        f"{escape(str(texto)).upper()}</div>"
    )


def _valor(texto: str) -> str:
    return (
        f'<div style="font-family:{CORPO};font-size:11pt;color:{TINTA};">'
        f"{_texto(texto)}</div>"
    )


def _pequeno(texto: str, alinhamento: str = ESQUERDA) -> str:
    return (
        f'<div style="font-family:{CORPO};font-size:9pt;color:{SUAVE};'
        f'text-align:{alinhamento};">{_texto(texto)}</div>'
    )


def _texto(valor) -> str:
    """Escapa e preserva as quebras que o cliente digitou no campo."""
    return escape(str(valor)).replace("\n", "<br>")
