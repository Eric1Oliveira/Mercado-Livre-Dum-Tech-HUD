"""Fotografa TODAS as telas da plataforma, uma pasta por aplicativo.

    python tools/capturar_telas.py

Diferente do `gerar_capturas.py`, que produz as poucas imagens da documentacao,
este varre o programa inteiro: cada tela de cada aplicativo, cada janela de
cadastro e cada documento. Serve para olhar o produto todo de uma vez - o que
existe, o que falta e o que esta feio.

Sai em `docs/imagens/telas/<NN_aplicativo>/`, numerado na ordem em que a pessoa
encontraria cada coisa. Usa uma pasta de dados temporaria: nao toca no que o
cliente tem instalado.

Sai no tema claro, que e o padrao do produto; `--escuro` gera o mesmo conjunto
no tema escuro.

Para material de divulgacao (imagem nitida, barra do topo inteira):

    python tools/capturar_telas.py --saida "docs/imagens/Minha pasta" \\
        --escala 2 --janela 1600x1000 [--escuro]

`--saida` grava numa pasta escolhida SEM apagar nada (so a pasta padrao e
recriada do zero); `--escala 2` desenha tudo no dobro de pixels.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile


def _opcao(nome: str, padrao: str | None = None) -> str | None:
    """O valor que vem depois de `nome` na linha de comando."""
    if nome in sys.argv:
        posicao = sys.argv.index(nome)
        if posicao + 1 < len(sys.argv):
            return sys.argv[posicao + 1]
    return padrao


RAIZ = pathlib.Path(__file__).resolve().parent.parent
DEMO = pathlib.Path(tempfile.mkdtemp(prefix="dumtech_telas_"))
os.environ["DUMTECH_DATA_DIR"] = str(DEMO)
os.environ["DUMTECH_LICENCA_LOCAL"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
# a foto e tirada com a tela parada: animacao pela metade vira imagem desbotada
os.environ["DUMTECH_SEM_ANIMACAO"] = "1"
ESCALA = _opcao("--escala", "1")
if ESCALA != "1":
    os.environ["QT_SCALE_FACTOR"] = ESCALA  # antes da QApplication existir
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tools"))

import dados_demo  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dumtech.hub.main_window import (  # noqa: E402
    PAGINA_CONFIG,
    PAGINA_INICIO,
    PAGINA_LICENCA,
    PAGINA_SOBRE,
    HubWindow,
)
from dumtech.ui.theme import MODO_CLARO, MODO_ESCURO, ThemeManager  # noqa: E402

SAIDA_PADRAO = RAIZ / "docs" / "imagens" / "telas"
_pedida = _opcao("--saida")
if _pedida:
    SAIDA = pathlib.Path(_pedida)
    SAIDA = SAIDA if SAIDA.is_absolute() else RAIZ / SAIDA
else:
    SAIDA = SAIDA_PADRAO
JANELA = tuple(int(n) for n in (_opcao("--janela", "1360x860") or "").lower().split("x"))
#: nada aparece na tela de quem esta capturando - a janela e desenhada fora dela
FORA_DA_TELA = Qt.WidgetAttribute.WA_DontShowOnScreen

app: QApplication
hub: HubWindow
tema: ThemeManager
pasta_atual: pathlib.Path
contador = 0


def pasta(nome: str) -> None:
    """Comeca uma secao: uma pasta, com a numeracao reiniciada."""
    global pasta_atual, contador
    pasta_atual = SAIDA / nome
    pasta_atual.mkdir(parents=True, exist_ok=True)
    contador = 0


def foto(nome: str, alvo=None) -> None:
    """Fotografa a janela do Hub (ou o widget indicado)."""
    global contador
    contador += 1
    widget = alvo if alvo is not None else hub
    if alvo is None:
        hub.resize(*JANELA)
        hub.show()
    for _ in range(3):
        app.processEvents()
    arquivo = pasta_atual / f"{contador:02d}_{nome}.png"
    widget.grab().save(str(arquivo))
    print("  ", arquivo.relative_to(SAIDA))


def dialogo(construir, nome: str, preparar=None) -> None:
    """Abre uma janela de cadastro sem `exec()` e fotografa.

    `exec()` bloqueia esperando o usuario; `show()` desenha a mesma janela e
    devolve o controle - e e a janela de verdade, nao uma imitacao.
    """
    janela = construir()
    janela.setAttribute(FORA_DA_TELA, True)
    janela.show()
    for _ in range(3):
        app.processEvents()
    if preparar is not None:
        preparar(janela)
        for _ in range(3):
            app.processEvents()
    foto(nome, janela)
    janela.close()
    janela.deleteLater()


def folha(html: str, nome: str, empresa) -> None:
    """Desenha um documento A4 como ele sai no PDF."""
    global contador
    from dumtech.ui import documento as doc

    contador += 1
    documento = doc.render(html, empresa)
    margem = round(doc.MARGEM_MM / 25.4 * doc.RESOLUCAO)
    altura = int(documento.size().height()) + 2 * margem
    imagem = QImage(doc.LARGURA, altura, QImage.Format.Format_RGB32)
    imagem.fill(QColor("white"))
    pintor = QPainter(imagem)
    pintor.translate(margem, margem)
    documento.drawContents(pintor)
    pintor.end()
    arquivo = pasta_atual / f"{contador:02d}_{nome}.png"
    imagem.save(str(arquivo))
    print("  ", arquivo.relative_to(SAIDA))


def casca(app_id: str):
    hub.open_app(app_id)
    aberta = hub.launcher.get(app_id)
    aberta.refresh_all()
    return aberta


# ------------------------------------------------------------------------ Hub
def telas_do_hub() -> None:
    pasta("00_hub")
    hub._go(PAGINA_INICIO)
    foto("inicio_com_avisos")

    hub._go(PAGINA_LICENCA)
    foto("licenca")

    for indice, nome in enumerate(("config_minha_empresa", "config_avisos",
                                   "config_mensagens", "config_backup")):
        hub._ir_para_config(indice)
        foto(nome)

    hub._go(PAGINA_SOBRE)
    foto("sobre")

    hub._go(PAGINA_INICIO)
    hub.open_palette()
    foto("paleta_de_comandos")
    hub.palette_dialog.close()

    # o outro tema, como recurso e nao como padrao
    atual = tema.mode
    tema.set_mode(MODO_ESCURO if atual == MODO_CLARO else MODO_CLARO)
    hub._go(PAGINA_INICIO)
    foto("inicio_no_outro_tema")
    tema.set_mode(atual)


# ------------------------------------------------------------------ Aplicativos
def telas_do_estoque() -> None:
    from dumtech.apps.estoque.models import TIPO_ENTRADA
    from dumtech.apps.estoque.ui.movimento_dialog import MovimentoDialog
    from dumtech.apps.estoque.ui.produto_dialog import ProdutoDialog

    pasta("01_estoque")
    aberta = casca("estoque")
    for indice, nome in enumerate(("painel", "produtos", "entradas",
                                   "movimentacoes", "contagem")):
        aberta.show_view(indice)
        foto(nome)

    repositorio = aberta.repository
    produto = repositorio.buscar_por_codigo("MOU-001")
    dialogo(lambda: ProdutoDialog(repositorio, produto, hub), "cadastro_de_produto")
    dialogo(lambda: MovimentoDialog(repositorio, produto, TIPO_ENTRADA, hub),
            "entrada_de_mercadoria")


def telas_dos_clientes() -> None:
    from dumtech.apps.clientes.ui.cliente_dialog import ClienteDialog
    from dumtech.apps.clientes.ui.ficha_dialog import FichaDialog

    pasta("02_clientes")
    aberta = casca("clientes")
    for indice, nome in enumerate(("painel", "lista_de_clientes")):
        aberta.show_view(indice)
        foto(nome)

    loja = hub.contacts
    contato = loja.por_nome("Mercado Central")
    dialogo(lambda: ClienteDialog(loja, contato, hub), "ficha_de_cadastro")
    dialogo(lambda: FichaDialog(loja, contato, hub), "ficha_com_anotacoes")


def telas_do_financeiro() -> None:
    from dumtech.apps.financeiro.models import PARCELAMENTO
    from dumtech.apps.financeiro.ui.dialogos import (
        BaixaDialog,
        SerieDialog,
        TransferenciaDialog,
    )
    from dumtech.apps.financeiro.ui.lancamento_dialog import LancamentoDialog

    pasta("03_financeiro")
    aberta = casca("financeiro")
    for indice, nome in enumerate(("fluxo_de_caixa", "painel", "lancamentos",
                                   "contas")):
        aberta.show_view(indice)
        foto(nome)

    repositorio = aberta.repository
    abertos = [item for item in repositorio.listar() if not item.pago]
    lancamento = abertos[0]
    dialogo(lambda: LancamentoDialog(repositorio, lancamento, hub.contacts.nomes(),
                                     hub), "novo_lancamento")
    dialogo(lambda: BaixaDialog(repositorio, lancamento, hub), "receber_ou_pagar")
    dialogo(lambda: SerieDialog(repositorio, lancamento, PARCELAMENTO, hub),
            "parcelamento")
    dialogo(lambda: TransferenciaDialog(repositorio, hub), "transferencia")


def telas_dos_orcamentos() -> None:
    from dumtech.apps.orcamentos.ui.orcamento_dialog import OrcamentoDialog, RecusaDialog

    pasta("04_orcamentos")
    aberta = casca("orcamentos")
    for indice, nome in enumerate(("funil", "lista_de_propostas")):
        aberta.show_view(indice)
        foto(nome)

    repositorio = aberta.repository
    proposta = repositorio.obter(repositorio.listar()[0].id)
    dialogo(lambda: OrcamentoDialog(repositorio, proposta, hub.contacts.nomes(), hub),
            "montagem_da_proposta")
    dialogo(lambda: RecusaDialog(repositorio, proposta, hub),
            "motivo_da_recusa")


def telas_das_vendas() -> None:
    from dumtech.apps.vendas.models import CONCLUIDA
    from dumtech.apps.vendas.ui.caixa_dialogs import FecharCaixaDialog
    from dumtech.apps.vendas.ui.devolucao_dialog import DevolucaoDialog
    from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

    pasta("05_vendas")
    aberta = casca("vendas")
    dados_demo.semear_balcao_em_uso(hub)
    for indice, nome in enumerate(("balcao_pdv", "painel", "lista_de_vendas",
                                   "caixa_do_dia")):
        aberta.show_view(indice)
        foto(nome)

    repositorio = aberta.repository
    dialogo(lambda: PagamentoDialog(1898.0, "3 itens  ·  Mercado Central",
                                    conferir=repositorio.conferir_pagamento,
                                    parent=hub), "pagamento")
    concluidas = [v for v in repositorio.listar(status=CONCLUIDA) if v.itens]
    venda = repositorio.obter(concluidas[0].id)
    dialogo(lambda: DevolucaoDialog(repositorio, venda, hub), "devolucao")
    dialogo(lambda: FecharCaixaDialog(repositorio, repositorio.conferencia(), hub),
            "fechamento_do_caixa")


def telas_das_ordens() -> None:
    from dumtech.apps.ordens.models import AGUARDANDO, CONCLUIDA
    from dumtech.apps.ordens.ui.dialogos import AprovacaoDialog, EntregaDialog
    from dumtech.apps.ordens.ui.ordem_dialog import OrdemDialog

    pasta("06_ordens")
    aberta = casca("ordens")
    for indice, nome in enumerate(("bancada", "painel", "lista_de_ordens")):
        aberta.show_view(indice)
        foto(nome)

    repositorio = aberta.repository
    todas = repositorio.listar()
    ordem = repositorio.obter(todas[0].id)
    dialogo(lambda: OrdemDialog(repositorio, ordem, hub.contacts.nomes(), hub),
            "ficha_da_ordem")

    esperando = next(o for o in todas if o.status == AGUARDANDO)
    dialogo(lambda: AprovacaoDialog(repositorio, repositorio.obter(esperando.id), hub),
            "aprovacao_do_orcamento")
    pronta = next(o for o in todas if o.status == CONCLUIDA)
    dialogo(lambda: EntregaDialog(repositorio, repositorio.obter(pronta.id), hub),
            "entrega_e_garantia")


def telas_da_agenda() -> None:
    from dumtech.apps.agenda.ui.compromisso_dialog import CompromissoDialog

    pasta("07_agenda")
    aberta = casca("agenda")
    for indice, nome in enumerate(("grade_da_semana", "lista_de_compromissos")):
        aberta.show_view(indice)
        foto(nome)

    repositorio = aberta.repository
    compromisso = repositorio.obter(repositorio.listar()[0].id)
    dialogo(lambda: CompromissoDialog(repositorio, compromisso,
                                      hub.contacts.nomes(), hub),
            "novo_compromisso")


# ------------------------------------------------------------------ Documentos
def telas_dos_documentos() -> None:
    from dumtech.apps.orcamentos.documento import proposta_a4
    from dumtech.apps.ordens.documento import entrega_a4
    from dumtech.apps.ordens.models import ENTREGUE
    from dumtech.apps.ordens.recibo import entrada
    from dumtech.apps.vendas.recibo import comprovante
    from dumtech.core.empresa import Empresa
    from dumtech.ui.widgets.comprovante import ComprovanteDialog
    from dumtech.ui.widgets.documento import DocumentoDialog
    from dumtech.ui.widgets.mensagem import MensagemDialog

    pasta("08_documentos")
    empresa = Empresa.carregar(hub.settings)

    orcamentos = casca("orcamentos").repository
    aprovada = orcamentos.obter(orcamentos.listar()[0].id)
    folha(proposta_a4(aprovada, empresa), "proposta_comercial_a4", empresa)

    ordens = casca("ordens").repository
    entregues = [o for o in ordens.listar() if o.status == ENTREGUE]
    ordem = ordens.obter(entregues[0].id)
    folha(entrega_a4(ordem, empresa), "comprovante_de_entrega_a4", empresa)

    dialogo(lambda: DocumentoDialog(
        proposta_a4(aprovada, empresa), f"Proposta {aprovada.numero}",
        "proposta", "", empresa, None, hub), "janela_do_documento")

    vendas = casca("vendas").repository
    venda = vendas.obter([v for v in vendas.listar() if v.itens][0].id)
    dialogo(lambda: ComprovanteDialog(comprovante(venda, empresa),
                                      f"Venda {venda.numero}", hub),
            "comprovante_de_venda_bobina")
    dialogo(lambda: ComprovanteDialog(entrada(ordem, empresa),
                                      f"Entrada da {ordem.numero}", hub),
            "entrada_de_os_bobina")

    from dumtech.core.mensagens import Mensageiro

    mensageiro = Mensageiro(hub.settings, empresa)
    texto = mensageiro.texto("ordem_pronta", {
        "cliente": ordem.cliente, "numero": ordem.numero,
        "equipamento": ordem.equipamento, "total": "R$ 540,00",
        "garantia": "90 dias",
    })
    dialogo(lambda: MensagemDialog(texto, "(63) 98877-1100",
                                   f"Mandar no WhatsApp - {ordem.cliente}", hub),
            "mensagem_de_whatsapp")


def telas_da_licenca() -> None:
    """O mesmo Inicio com uma licenca pobre e com a licenca cheia.

    E a imagem que explica o modelo de venda melhor que qualquer texto: mesma
    instalacao, mesmo banco, muda so o que a licenca libera.
    """
    from dumtech.core.licensing import LicenseService, LocalLicenseGateway
    from dumtech.core.registry import AppRegistry

    pasta("09_licenca")
    global hub

    cheio = hub
    foto("inicio_7_modulos")

    servico = LicenseService(gateway=LocalLicenseGateway(("vendas",)))
    servico.activate("DUMT-DEMO-0000-0001")
    magro = HubWindow(theme=tema, license_service=servico,
                      registry=AppRegistry(servico))
    magro.launcher.notify = lambda *args: None
    magro.setAttribute(FORA_DA_TELA, True)
    hub = magro
    hub._go(PAGINA_INICIO)
    foto("inicio_1_modulo")
    magro.launcher.close_all()
    magro.hub_store.close()
    magro.contacts.close()
    magro.close()
    hub = cheio


def escrever_leia_me(total: int) -> None:
    """A pasta se explica sozinha - e o texto nunca fica velho."""
    escuro = tema.mode == MODO_ESCURO
    linhas = [
        "# Telas do DumTech Hub", "",
        "Uma pasta por parte do produto, na ordem em que o cliente encontra cada",
        "coisa. Geradas por `tools/capturar_telas.py` com a loja de demonstracao",
        "(`tools/dados_demo.py`) - nenhuma imagem aqui e montagem.", "",
        f"Sao {total} imagens, no **tema {'escuro' if escuro else 'claro'}**; o",
        f"{'claro' if escuro else 'escuro'} aparece uma vez, como opcao.", "",
        "| Pasta | O que tem |", "|---|---|",
    ]
    for caminho in sorted(SAIDA.iterdir()):
        if not caminho.is_dir():
            continue
        nomes = [
            arquivo.stem.split("_", 1)[1].replace("_", " ")
            for arquivo in sorted(caminho.glob("*.png"))
        ]
        linhas.append(f"| `{caminho.name}` | {', '.join(nomes)} |")
    linhas += [
        "", "Para regerar:", "",
        "    .venv\\Scripts\\python.exe tools/capturar_telas.py",
        "    .venv\\Scripts\\python.exe tools/capturar_telas.py --escuro",
        "",
    ]
    (SAIDA / "LEIA-ME.md").write_text("\n".join(linhas), encoding="utf-8")


def main() -> None:
    global app, tema, hub

    # so a pasta padrao e recriada do zero; uma pasta pedida nunca e apagada
    if SAIDA == SAIDA_PADRAO and SAIDA.exists():
        shutil.rmtree(SAIDA)
    SAIDA.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    # o tema claro e o principal do produto; o escuro aparece como opcao
    tema = ThemeManager(app, MODO_ESCURO if "--escuro" in sys.argv else MODO_CLARO)
    hub = HubWindow(theme=tema)
    hub.launcher.notify = lambda *args: None
    hub.setAttribute(FORA_DA_TELA, True)
    hub.palette_dialog.setAttribute(FORA_DA_TELA, True)
    dados_demo.semear_tudo(hub)
    # a loja de demonstracao tem copia de seguranca em dia, como a de verdade
    hub.backup_automatico()
    # a demonstracao grava a empresa direto nas preferencias, sem passar pela
    # tela Minha empresa: sem reler, o canto da barra dizia "Sua empresa" ao
    # lado da faixa com o nome da loja
    hub.refresh_rail()

    for secao in (telas_do_hub, telas_do_estoque, telas_dos_clientes,
                  telas_do_financeiro, telas_dos_orcamentos, telas_das_vendas,
                  telas_das_ordens, telas_da_agenda, telas_dos_documentos,
                  telas_da_licenca):
        print(secao.__name__)
        secao()

    total = len(list(SAIDA.rglob("*.png")))
    escrever_leia_me(total)
    print(f"\n{total} imagens em {SAIDA}")


if __name__ == "__main__":
    main()
