"""Registro do aplicativo DumTech Estoque na plataforma.

Este e o unico arquivo que o Hub conhece deste aplicativo.
"""

from __future__ import annotations

from ...core.app_module import AppContext, AppManifest

MANIFEST = AppManifest(
    app_id="estoque",
    name="DumTech Estoque",
    short_name="Estoque",
    description="Produtos com código de barras, entrada de nota, contagem e CSV.",
    version="2.0.0",
    icon="box",
    accent="#8A7BF8",
    category="Gestão",
    requires_internet=False,
)


def create_window(context: AppContext):
    """Cria a janela do aplicativo (importada aqui para o Hub abrir rapido)."""
    from .ui.window import EstoqueWindow

    return EstoqueWindow(context)


def avisos(paths, config):
    """O que chegou ao minimo - antes de faltar na hora da venda."""
    from ...core.avisos import Aviso
    from ...ui import format as fmt
    from .database import open_database
    from .repository import EstoqueRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        resumo = EstoqueRepository(banco).resumo()
    finally:
        banco.close()

    if not resumo.produtos_baixo:
        return []
    nomes = ", ".join(p.nome for p in resumo.baixos[:3])
    return [Aviso(
        app_id=MANIFEST.app_id, tipo="estoque_baixo",
        titulo=f"{fmt.contagem(resumo.produtos_baixo, 'produto')} no estoque mínimo",
        detalhe=nomes,
        tom="warning", urgencia=50, icone="box",
        quantidade=resumo.produtos_baixo,
    )]


def indicadores(paths):
    """O sinal vital do estoque: quanto dinheiro esta investido na prateleira."""
    from ...core.indicadores import Indicador
    from ...ui import format as fmt
    from .database import open_database
    from .repository import EstoqueRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        resumo = EstoqueRepository(banco).resumo(limite_listas=1)
    finally:
        banco.close()

    return [Indicador(
        app_id=MANIFEST.app_id, rotulo="Valor investido em estoque",
        valor=fmt.moeda(resumo.valor_custo),
        detalhe=(f"{fmt.contagem(resumo.produtos_baixo, 'produto')} no mínimo"
                 if resumo.produtos_baixo else "estoque em dia"),
        tom="warning" if resumo.produtos_baixo else "success",
        icone="box", peso=60,
    )]


def celular(paths):
    """No celular: o que acabou, o que esta acabando e quanto vale o estoque."""
    from ...core import celular as c
    from ...ui import format as fmt
    from .database import open_database
    from .models import quantidade_texto
    from .repository import EstoqueRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        r = EstoqueRepository(banco).resumo(limite_listas=c.LIMITE_LISTA)
    finally:
        banco.close()

    so_baixo = max(r.produtos_baixo - r.sem_estoque, 0)
    alertas = []
    if r.sem_estoque:
        alertas.append(c.alerta(
            f"Repor {fmt.contagem(r.sem_estoque, 'produto zerado', 'produtos zerados')}", tom="perigo"))
    if so_baixo:
        alertas.append(c.alerta(
            f"Comprar {fmt.contagem(so_baixo, 'produto que está acabando', 'produtos que estão acabando')}",
            tom="aviso"))
    return c.secao(MANIFEST.app_id, "Estoque", peso=60, cartoes=[
        c.cartao("Abaixo do mínimo", fmt.numero(r.produtos_baixo), "produtos para repor",
                 "aviso" if r.produtos_baixo else ""),
        c.cartao("Sem estoque", fmt.numero(r.sem_estoque), "não dá para vender",
                 "perigo" if r.sem_estoque else ""),
        c.cartao("Valor em estoque", fmt.moeda(r.valor_custo),
                 f"{fmt.contagem(r.total_produtos, 'produto', 'produtos')} · "
                 f"{fmt.moeda(r.valor_venda)} a preço de venda", largo=True),
    ], listas=[
        c.lista("Acabando", [
            c.linha(p.nome, f"mínimo {quantidade_texto(p.estoque_minimo, p.unidade, True)}",
                    quantidade_texto(p.quantidade, p.unidade, True), "perigo" if p.sem_estoque else "aviso",
                    medidor=c.medidor(max(p.quantidade, 0), p.estoque_minimo))
            for p in r.baixos], "Nada abaixo do mínimo."),
    ], alertas=alertas)
