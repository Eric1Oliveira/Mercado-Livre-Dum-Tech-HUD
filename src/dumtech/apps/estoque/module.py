"""Registro do aplicativo DumTech Estoque na plataforma.

Este e o unico arquivo que o Hub conhece deste aplicativo.
"""

from __future__ import annotations

from ...core.app_module import AppContext, AppManifest

MANIFEST = AppManifest(
    app_id="estoque",
    name="DumTech Estoque",
    short_name="Estoque",
    description="Produtos com codigo de barras, entrada de nota, contagem e CSV.",
    version="2.0.0",
    icon="box",
    accent="#8A7BF8",
    category="Gestao",
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
        titulo=f"{fmt.contagem(resumo.produtos_baixo, 'produto')} no estoque minimo",
        detalhe=nomes,
        tom="warning", urgencia=50, icone="box",
        quantidade=resumo.produtos_baixo,
    )]


def indicadores(paths):
    """O sinal vital do estoque: quanto dinheiro esta parado na prateleira."""
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
        app_id=MANIFEST.app_id, rotulo="Parado em estoque",
        valor=fmt.moeda(resumo.valor_custo),
        detalhe=(f"{fmt.contagem(resumo.produtos_baixo, 'produto')} no minimo"
                 if resumo.produtos_baixo else "estoque em dia"),
        tom="warning" if resumo.produtos_baixo else "success",
        icone="box", peso=60,
    )]


def celular(paths):
    """No celular: o que esta acabando."""
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
    return c.secao(MANIFEST.app_id, "Estoque", peso=60, cartoes=[
        c.cartao("Abaixo do mínimo", fmt.numero(r.produtos_baixo), "produtos para repor",
                 "aviso" if r.produtos_baixo else ""),
        c.cartao("Valor em estoque", fmt.moeda(r.valor_custo),
                 fmt.contagem(r.total_produtos, "produto", "produtos")),
    ], listas=[
        c.lista("Acabando", [
            c.linha(p.nome, f"mínimo {quantidade_texto(p.estoque_minimo, p.unidade, True)}",
                    quantidade_texto(p.quantidade, p.unidade, True), "perigo" if p.sem_estoque else "aviso")
            for p in r.baixos], "Nada abaixo do mínimo."),
    ])
