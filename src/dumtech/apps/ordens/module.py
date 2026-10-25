"""Registro do aplicativo DumTech Ordem de Servico na plataforma."""

from __future__ import annotations

from ...core.app_module import AppContext, AppManifest

MANIFEST = AppManifest(
    app_id="ordens",
    name="DumTech Ordem de Serviço",
    short_name="OS",
    description="Serviços por etapa, aprovação, garantia e comprovantes.",
    version="2.0.0",
    icon="wrench",
    accent="#4C7EF3",
    category="Serviços",
)


def create_window(context: AppContext):
    from .ui.window import OrdensWindow

    return OrdensWindow(context)


def _citar(ordem) -> str:
    """Uma ordem em uma linha de aviso. Sem item, sem parenteses vazio."""
    cliente = ordem.cliente or "Sem cliente"
    return f"{ordem.numero} - {cliente}" + (f" ({ordem.assunto})" if ordem.assunto else "")


def avisos(paths, config):
    """O que passou do prazo, e o que ficou pronto e ninguem veio buscar."""
    from datetime import date

    from ...core.avisos import Aviso
    from ...ui import format as fmt
    from .database import open_database
    from .models import ler_data
    from .repository import OrdensRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        resumo = OrdensRepository(banco).resumo(limite_listas=50)
    finally:
        banco.close()

    encontrados = []
    atrasadas = [ordem for ordem in resumo.fila if ordem.atrasada]
    if atrasadas:
        primeira = atrasadas[0]
        encontrados.append(Aviso(
            app_id=MANIFEST.app_id, tipo="os_atrasada",
            titulo=("1 OS passou do prazo" if len(atrasadas) == 1
                    else f"{len(atrasadas)} OS passaram do prazo"),
            detalhe=_citar(primeira),
            tom="danger", urgencia=80, icone="wrench", quantidade=len(atrasadas),
        ))

    espera = config.dias("os_para_retirar")
    hoje = date.today()
    paradas = []
    for ordem in resumo.prontas:
        quando = ler_data(ordem.concluida_em or "")
        if quando is not None and (hoje - quando).days >= espera:
            paradas.append(ordem)
    if paradas:
        primeira = paradas[0]
        encontrados.append(Aviso(
            app_id=MANIFEST.app_id, tipo="os_para_retirar",
            titulo=f"{fmt.contagem(len(paradas), 'serviço')} pronto"
                   f"{'s' if len(paradas) > 1 else ''} esperando retirada",
            detalhe=_citar(primeira),
            tom="accent", urgencia=30, icone="wrench", quantidade=len(paradas),
        ))
    return encontrados


def indicadores(paths):
    """O sinal vital do modulo: quantos servicos estao em andamento."""
    from ...core.indicadores import Indicador
    from ...ui import format as fmt
    from .database import open_database
    from .repository import OrdensRepository

    banco = open_database(paths.app_db(MANIFEST.app_id))
    try:
        resumo = OrdensRepository(banco).resumo(limite_listas=1)
    finally:
        banco.close()

    em_aberto = resumo.abertas + resumo.aguardando + resumo.em_andamento
    return [Indicador(
        app_id=MANIFEST.app_id, rotulo="Em andamento",
        valor=fmt.numero(em_aberto),
        detalhe=(f"{resumo.atrasadas} passaram do prazo" if resumo.atrasadas
                 else "nenhuma atrasada"),
        tom="danger" if resumo.atrasadas else "accent",
        icone="wrench", peso=70,
    )]


def celular(paths):
    """No celular: o quadro, o que atrasou e o que esta pronto para entregar."""
    from .celular import secao

    return secao(paths, MANIFEST)
