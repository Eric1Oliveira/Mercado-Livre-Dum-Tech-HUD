"""Gera as imagens de demonstracao usadas na documentacao.

    python tools/gerar_capturas.py

Cria uma pasta de dados temporaria com exemplos em todos os aplicativos, monta
as telas e salva os PNGs em docs/imagens/. Nao toca nos dados reais do usuario.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
from datetime import datetime

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DEMO = pathlib.Path(tempfile.mkdtemp(prefix="dumtech_demo_"))
os.environ["DUMTECH_DATA_DIR"] = str(DEMO)
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
# licenca local: as imagens mostram a plataforma completa, sem consultar a internet
os.environ["DUMTECH_LICENCA_LOCAL"] = "1"
sys.path.insert(0, str(RAIZ / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from dumtech.hub.main_window import (  # noqa: E402
    PAGINA_CONFIG,
    PAGINA_INICIO,
    PAGINA_LICENCA,
    PAGINA_SOBRE,
    HubWindow,
)
from dumtech.ui.theme import MODO_CLARO, MODO_ESCURO, ThemeManager  # noqa: E402

sys.path.insert(0, str(RAIZ / "tools"))
import dados_demo  # noqa: E402  (a loja ficticia, compartilhada com o semeador)
from dados_demo import abrir  # noqa: E402

SAIDA = RAIZ / "docs" / "imagens"
SAIDA.mkdir(parents=True, exist_ok=True)



def capturar(app: QApplication, widget, nome: str) -> None:
    widget.resize(1280, 820)
    widget.show()
    for _ in range(3):
        app.processEvents()
    widget.grab().save(str(SAIDA / nome))
    print("gerado", nome)


TELAS = {
    # o Estoque tem cinco telas: Painel, Produtos, Entradas, Movimentacoes,
    # Contagem. A lista segue a ordem em que elas sao criadas.
    "estoque": ["04_estoque_painel.png", "05_estoque_produtos.png",
                "25_estoque_entradas.png", "06_estoque_movimentacoes.png",
                "26_estoque_contagem.png"],
    "clientes": ["07_clientes_painel.png", "08_clientes_lista.png"],
    # o Financeiro comeca pelo Fluxo: quem abre quer saber se vai ter dinheiro
    "financeiro": ["09_financeiro_fluxo.png", "29_financeiro_painel.png",
                   "10_financeiro_lancamentos.png", "30_financeiro_contas.png"],
    # o Orcamentos tem duas telas: o Funil ja e o painel dele
    "orcamentos": ["11_orcamentos_funil.png", "12_orcamentos_lista.png"],
    # o Vendas comeca pelo Balcao: quem abre o modulo abre para vender
    "vendas": ["13_vendas_balcao.png", "27_vendas_painel.png",
               "14_vendas_lista.png", "28_vendas_caixa.png"],
    # a Ordem de Servico comeca pela Bancada: o que esta em cima dela agora
    "ordens": ["15_ordens_bancada.png", "32_ordens_painel.png",
               "16_ordens_lista.png"],
    # a Agenda comeca pela grade: e o tempo desenhado
    "agenda": ["17_agenda_grade.png", "18_agenda_lista.png"],
}


def capturar_documentos(hub: HubWindow) -> None:
    """As duas folhas A4, desenhadas como saem no PDF.

    Aqui nao se fotografa uma janela: desenha-se o proprio documento, que e o
    que o cliente do cliente recebe por e-mail.
    """
    from PySide6.QtGui import QColor, QImage, QPainter

    from dumtech.apps.orcamentos.documento import proposta_a4
    from dumtech.apps.ordens.documento import entrega_a4
    from dumtech.apps.ordens.models import ENTREGUE
    from dumtech.core.empresa import Empresa
    from dumtech.ui import documento as doc

    empresa = Empresa.carregar(hub.settings)
    margem = round(doc.MARGEM_MM / 25.4 * doc.RESOLUCAO)

    def desenhar(html: str, nome: str) -> None:
        folha = doc.render(html, empresa)
        altura = int(folha.size().height()) + 2 * margem
        imagem = QImage(doc.LARGURA, altura, QImage.Format.Format_RGB32)
        imagem.fill(QColor("white"))
        pintor = QPainter(imagem)
        pintor.translate(margem, margem)
        folha.drawContents(pintor)
        pintor.end()
        imagem.save(str(SAIDA / nome))
        print("gerado", nome)

    orcamentos = abrir(hub, "orcamentos").repository
    proposta = orcamentos.obter(orcamentos.listar()[0].id)
    desenhar(proposta_a4(proposta, empresa), "35_documento_proposta.png")

    ordens = abrir(hub, "ordens").repository
    entregues = [o for o in ordens.listar() if o.status == ENTREGUE]
    if entregues:
        ordem = ordens.obter(entregues[0].id)
        desenhar(entrega_a4(ordem, empresa), "36_documento_entrega.png")


def capturar_licencas(app: QApplication, tema) -> None:
    """Tela de licenca nos dois estados: sem licenca e com licenca ativada."""
    from datetime import timezone

    from dumtech.core.config import Settings
    from dumtech.core.licensing import ORIGEM_SUPABASE, License, LicenseService, machine_id

    # --- sem licenca: aparece o formulario de ativacao
    os.environ["DUMTECH_LICENCA_LOCAL"] = "0"   # desliga a licenca de desenvolvimento
    try:
        vazio = LicenseService(DEMO / "sem_licenca.json", None)
        hub_vazio = HubWindow(
            settings=Settings(DEMO / "hub_vazio.json"), license_service=vazio, theme=tema
        )
        hub_vazio._go(PAGINA_LICENCA)
        capturar(app, hub_vazio, "21_licenca_ativar.png")
        hub_vazio._go(PAGINA_INICIO)
        capturar(app, hub_vazio, "22_hub_sem_licenca.png")
        hub_vazio.close()
    finally:
        os.environ["DUMTECH_LICENCA_LOCAL"] = "1"

    # --- com licenca de um cliente que comprou tres aplicativos
    agora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    servico = LicenseService(DEMO / "com_licenca.json", None)
    servico.save(License(
        key="DEMO-2026-TEST-0001",
        customer="Joao da Silva - Informatica",
        entitlements=("estoque", "financeiro", "vendas"),
        machine=machine_id(),
        activated_at=agora,
        last_check=agora,
        source=ORIGEM_SUPABASE,
        max_machines=3,
        used_machines=1,
    ))
    hub_licenca = HubWindow(
        settings=Settings(DEMO / "hub_licenca.json"), license_service=servico, theme=tema
    )
    hub_licenca._go(PAGINA_LICENCA)
    capturar(app, hub_licenca, "23_licenca_ativa.png")
    hub_licenca._go(PAGINA_INICIO)
    capturar(app, hub_licenca, "24_hub_licenca_parcial.png")


def main() -> None:
    app = QApplication([])
    tema = ThemeManager(app, MODO_ESCURO)
    hub = HubWindow(theme=tema)
    hub.launcher.notify = lambda *args: None

    dados_demo.semear_tudo(hub)
    dados_demo.semear_balcao_em_uso(hub)

    # tudo acontece na mesma janela: as imagens sao sempre do Hub inteiro
    hub._go(PAGINA_INICIO)
    capturar(app, hub, "01_hub_apps.png")
    hub._go(PAGINA_LICENCA)
    capturar(app, hub, "02_hub_licenca.png")
    hub._go(PAGINA_SOBRE)
    capturar(app, hub, "03_hub_sobre.png")
    # Configuracoes: a empresa ja veio preenchida no semeador
    from dumtech.core import backup as copia_seguranca

    hub.empresa_view.refresh()
    hub.launcher.atualizar_empresa()
    hub._ir_para_config(0)
    capturar(app, hub, "34_hub_empresa.png")

    hub.mensagens_view.refresh()
    hub._ir_para_config(2)
    capturar(app, hub, "37_hub_mensagens.png")

    hub.avisos_view.refresh()
    hub._ir_para_config(1)
    capturar(app, hub, "38_hub_avisos.png")

    pasta = hub.backup_view.pasta
    copia_seguranca.criar(pasta, versao="1.0.0", automatico=True)
    copia_seguranca.criar(pasta, versao="1.0.0")
    hub.backup_view.refresh()
    hub._ir_para_config(3)
    capturar(app, hub, "33_hub_backup.png")

    for app_id, arquivos in TELAS.items():
        casca = abrir(hub, app_id)
        casca.refresh_all()
        for indice, arquivo in enumerate(arquivos):
            casca.show_view(indice)
            capturar(app, hub, arquivo)

    capturar_documentos(hub)
    capturar_licencas(app, tema)

    tema.set_mode(MODO_CLARO)
    hub._go(PAGINA_INICIO)
    app.processEvents()
    capturar(app, hub, "19_hub_claro.png")
    abrir(hub, "vendas").show_view(0)
    capturar(app, hub, "20_vendas_claro.png")
    # o grafico do fluxo e pintado a mao: precisa ser conferido nos dois temas
    casca = abrir(hub, "financeiro")
    casca.refresh_all()
    casca.show_view(0)
    capturar(app, hub, "31_financeiro_claro.png")

    print("dados de demonstracao em", DEMO)


if __name__ == "__main__":
    main()
