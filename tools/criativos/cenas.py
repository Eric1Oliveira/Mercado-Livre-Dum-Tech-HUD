"""Fotografa os módulos com os dados DO NICHO do anúncio.

    python tools/criativos/cenas.py

POR QUE ISTO EXISTE
    A demonstração da documentação é uma loja de informática: "Mouse USB sem
    fio", "Instalação de rede", "Suporte remoto". Num anúncio de salão de
    beleza, a cliente lê "Visita técnica" na agenda e não se reconhece — e
    anúncio em que o comprador não se reconhece não vende.

    Cada nicho ganha aqui a própria loja fictícia. Não é enfeite: é a
    diferença entre "um sistema qualquer" e "o sistema do meu salão".

O QUE NÃO MEXEMOS
    `tools/dados_demo.py` fica intacto. Ele alimenta a documentação E a
    demonstração que o cliente de verdade recebe — parametrizar aquilo por
    ramo era risco sem necessidade. A loja de ferragens que ele descreve já
    serve aos dois anúncios de "empresa", então só faltavam estes dois.

SAI EM
    build/criativos/telas/<cenario>/<modulo>.png, já sem a barra do Hub.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
from datetime import date, datetime, timedelta

RAIZ = pathlib.Path(__file__).resolve().parents[2]
DEMO = pathlib.Path(tempfile.mkdtemp(prefix="dumtech_criativos_"))
os.environ["DUMTECH_DATA_DIR"] = str(DEMO)
os.environ["DUMTECH_LICENCA_LOCAL"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
os.environ["DUMTECH_SEM_ANIMACAO"] = "1"
# O Qt desenha tudo no DOBRO de pixels. O Mercado Livre deixa ampliar a foto, e
# e ampliando que o comprador decide se o programa parece serio: em 1x a letra
# fina da tabela saia serrilhada. Tem de vir ANTES de existir QApplication.
os.environ["QT_SCALE_FACTOR"] = "2"
sys.path.insert(0, str(RAIZ / "src"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dumtech.core.contacts import Contato  # noqa: E402
from dumtech.hub.main_window import HubWindow  # noqa: E402
from dumtech.ui.theme import MODO_CLARO, ThemeManager  # noqa: E402

HOJE = date.today()
#: a janela é desenhada fora da tela de quem está gerando
FORA_DA_TELA = Qt.WidgetAttribute.WA_DontShowOnScreen
# A janela é capturada quase do tamanho em que sai na arte (1200 px de
# largura). Fotografar grande e encolher depois deixava a letra do programa a
# 76% - ilegível na miniatura do Mercado Livre, que é onde a venda começa.
JANELA = (1240, 800)
SAIDA = RAIZ / "build" / "criativos" / "telas"
#: A janela sai INTEIRA, com a barra do Hub e tudo. Cortar pedaco de tela em
#: anuncio parece defeito de montagem, e o comprador merece ver o programa como
#: ele e. O que o anuncio nao faz e FALAR do Hub: ele fala do trabalho que os
#: modulos resolvem, e a janela aparece como prova, nao como assunto.
CORTE_TOPO = 0


def dia(offset: int) -> str:
    return (HOJE + timedelta(days=offset)).isoformat()


def _abrir(hub, app_id: str):
    hub.open_app(app_id)
    aberta = hub.launcher.get(app_id)
    aberta.refresh_all()
    return aberta


# ======================================================== mercado de bairro ==
def cenario_mercearia(hub) -> None:
    """Um minimercado de bairro: mercearia, hortifrúti, frios e bebida."""
    from dumtech.apps.estoque.models import Produto
    from dumtech.apps.financeiro.models import CAIXA, DESPESA, RECEITA, Conta, Lancamento

    for nome, segmento, whats in [
        ("Dona Cleide", "Pessoa fisica", "(63) 99911-2233"),
        ("Seu Antonio", "Pessoa fisica", "(63) 98877-1100"),
        ("Padaria Bom Pao", "Alimentacao", "(63) 99333-1212"),
        ("Escola Pequeno Passo", "Escola", "(63) 99640-2211"),
        ("Lanchonete da Praca", "Alimentacao", "(63) 99123-4567"),
    ]:
        hub.contacts.criar(Contato(nome=nome, cidade="Palmas", uf="TO",
                                   whatsapp=whats, segmento=segmento))

    estoque = _abrir(hub, "estoque").repository
    for codigo, nome, cat, un, qtd, minimo, maximo, custo, venda, ean in [
        ("ARR-5", "Arroz tipo 1 - 5kg", "Mercearia", "UN", 42, 12, 80, 21.90, 28.90,
         "7891234500017"),
        ("FEI-1", "Feijao carioca - 1kg", "Mercearia", "UN", 8, 10, 60, 6.40, 9.49,
         "7891234500024"),
        ("OLE-900", "Oleo de soja 900ml", "Mercearia", "UN", 36, 12, 72, 5.80, 8.29,
         "7891234500031"),
        ("LEI-1", "Leite integral 1L", "Frios e laticinios", "UN", 54, 24, 120, 3.90,
         5.79, "7891234500048"),
        ("REF-2", "Refrigerante 2L", "Bebidas", "UN", 0, 12, 60, 6.20, 9.90,
         "7891234500055"),
        ("BAN-KG", "Banana prata", "Hortifruti", "KG", 18.4, 8, 40, 3.20, 6.90, ""),
        ("PAO-KG", "Pao frances", "Padaria", "KG", 6.2, 4, 20, 8.50, 16.90, ""),
        ("SAB-5", "Sabao em po 1kg", "Limpeza", "UN", 15, 6, 40, 9.80, 15.90,
         "7891234500062"),
    ]:
        estoque.criar(Produto(
            codigo=codigo, nome=nome, categoria=cat, unidade=un, quantidade=qtd,
            estoque_minimo=minimo, estoque_maximo=maximo, preco_custo=custo,
            preco_venda=venda, codigo_barras=ean, fornecedor="Distribuidora Bom Preco",
        ))
    arroz = estoque.buscar_por_codigo("ARR-5")
    estoque.registrar_entrada(arroz.id, 30, "Compra do mes",
                              custo_unitario=21.40, fornecedor="Distribuidora Bom Preco",
                              documento="NF 4412")
    estoque.registrar_saida(estoque.buscar_por_codigo("LEI-1").id, 12, "Venda balcao")
    estoque.contar(arroz.id, 40)

    fin = _abrir(hub, "financeiro").repository
    banco = fin.criar_conta(Conta(nome="Banco", saldo_inicial=3100.0))
    caixa = fin.criar_conta(Conta(nome="Caixa do mercado", tipo=CAIXA, saldo_inicial=420.0))
    fin.transferir(banco.id, caixa.id, 300.0, dia(-1), "Troco do dia")
    fin.criar(Lancamento(tipo=RECEITA, descricao="Fiado - Dona Cleide", categoria="Vendas",
                         cliente="Dona Cleide", valor=186.40, vencimento=dia(5),
                         conta_id=caixa.id, forma_pagamento="Dinheiro"))
    fin.criar(Lancamento(tipo=RECEITA, descricao="Conta do mes - Lanchonete da Praca",
                         categoria="Vendas", cliente="Lanchonete da Praca", valor=940.00,
                         vencimento=dia(9), conta_id=banco.id, forma_pagamento="Pix"))
    fin.repetir(Lancamento(tipo=DESPESA, descricao="Aluguel do ponto", categoria="Fixas",
                           valor=1800.0, vencimento=dia(7), conta_id=banco.id), 6)
    energia = fin.criar(Lancamento(tipo=DESPESA, descricao="Energia eletrica",
                                   categoria="Fixas", valor=540.0, vencimento=dia(-2),
                                   conta_id=banco.id))
    fin.baixar(energia.id, data=dia(0), conta_id=banco.id, forma="Boleto")
    fin.criar(Lancamento(tipo=DESPESA, descricao="Distribuidora Bom Preco",
                         categoria="Compras", valor=3240.0, vencimento=dia(11),
                         conta_id=banco.id))

    _empresa(hub, "Mercado do Bairro")
    _venda_em_curso(hub, [("ARR-5", 2), ("LEI-1", 6), ("BAN-KG", 1.35),
                          ("OLE-900", 3), ("SAB-5", 1)], "Dona Cleide", 2.50)


# ========================================================= salão de beleza ==
def cenario_salao(hub) -> None:
    """Um salão com agenda cheia, ficha de cliente e pacote orçado."""
    from dumtech.apps.agenda.models import (
        ATENDIMENTO, BLOQUEIO, CONFIRMADO, Compromisso, inicio_da_semana,
    )
    from dumtech.apps.orcamentos.models import ItemOrcamento, Orcamento

    for nome, whats, nasc, obs in [
        ("JulianaPrado", "(63) 99911-2233", "1991-03-18",
         "Loira 9.1 - fundo 7. Alergia a amonia."),
        ("Fernanda Rocha", "(63) 98877-1100", "1986-09-02",
         "Progressiva a cada 4 meses. Cabelo fino."),
        ("Camila Duarte", "(63) 99333-1212", "1998-12-21",
         "Sempre com a Bruna. Gosta de corte repicado."),
        ("Patricia Nunes", "(63) 99640-2211", "1975-05-30",
         "Coloracao 6.0 - cobrir branco."),
        ("Aline Barros", "(63) 99123-4567", "2000-01-14", "Noiva - casamento em marco."),
        ("Renata Alves", "(63) 99555-8080", "1989-07-08", "Unhas em gel, 15 em 15 dias."),
    ]:
        hub.contacts.criar(Contato(nome=nome, cidade="Palmas", uf="TO", whatsapp=whats,
                                   nascimento=nasc, segmento="Pessoa fisica",
                                   observacoes=obs))

    _empresa(hub, "Studio Bella")
    agenda = _abrir(hub, "agenda").repository
    segunda = inicio_da_semana(HOJE)

    def marcar(titulo, cliente, dia_util, hora, minutos, duracao, **campos):
        quando = datetime.combine(segunda + timedelta(days=dia_util),
                                  datetime.min.time()).replace(hour=hora, minute=minutos)
        agenda.salvar(Compromisso(titulo=titulo, cliente=cliente,
                                  inicio=quando.isoformat(timespec="minutes"),
                                  duracao_min=duracao, tipo=ATENDIMENTO, **campos))

    agenda.repetir(Compromisso(
        titulo="Almoco", tipo=BLOQUEIO, duracao_min=60,
        inicio=datetime.combine(segunda, datetime.min.time())
        .replace(hour=12).isoformat(timespec="minutes")), 5, "diaria")

    # HOJE recebe os quatro melhores horarios. O celular abre pelo "hoje": com
    # a semana comecando na segunda, a foto tirada numa quinta mostrava
    # "Nada marcado para hoje" - o pior cartaz possivel para uma agenda.
    hoje = HOJE.weekday()
    marcar("Escova + hidratacao", "Juliana Prado", hoje, 9, 0, 90, status=CONFIRMADO)
    marcar("Mechas + matizacao", "Fernanda Rocha", hoje, 11, 0, 180,
           status=CONFIRMADO)
    marcar("Corte feminino", "Camila Duarte", hoje, 15, 0, 60)
    marcar("Unhas em gel", "Renata Alves", hoje, 16, 30, 90, status=CONFIRMADO)
    marcar("Progressiva", "Patricia Nunes", (hoje + 1) % 5, 9, 0, 180,
           status=CONFIRMADO)
    marcar("Coloracao - retoque", "Patricia Nunes", (hoje + 1) % 5, 14, 0, 120)
    # titulo curto de proposito: bloco de 30 min corta o que nao couber, e
    # "Design de sobrancelha" saia como "Desian de sobrance" na foto
    marcar("Sobrancelha", "Camila Duarte", (hoje + 2) % 5, 17, 0, 60)
    marcar("Teste de penteado", "Aline Barros", 3, 10, 0, 120,
           status=CONFIRMADO)
    marcar("Escova", "Renata Alves", 3, 15, 30, 45)
    marcar("Corte + barba", "Fernanda Rocha", 4, 9, 30, 60)
    marcar("Dia da noiva", "Aline Barros", 4, 13, 0, 300, status=CONFIRMADO)

    orc = _abrir(hub, "orcamentos").repository
    from dumtech.apps.orcamentos.models import MOTIVO_PRECO

    def propor(cliente, itens, quando, **campos):
        return orc.salvar(Orcamento(
            numero=orc.proximo_numero(), cliente=cliente, data=quando,
            itens=[ItemOrcamento(descricao=d, quantidade=q, valor_unitario=v,
                                 unidade=un)
                   for d, q, v, un in itens],
            **campos,
        ))

    # o pacote da noiva, esperando o sim ha tres dias
    noiva = propor("Aline Barros",
                   [("Teste de penteado", 1, 180.0, ""),
                    ("Dia da noiva - cabelo e maquiagem", 1, 890.0, ""),
                    ("Penteado para madrinha", 2, 160.0, "")],
                   dia(-3), condicao_pagamento="50% na reserva",
                   prazo_entrega="Data do casamento", validade_dias=20)
    orc.enviar(noiva.id, quando=dia(-3))

    # aprovado nesta semana
    formatura = propor("Camila Duarte",
                       [("Maquiagem", 1, 220.0, ""), ("Penteado", 1, 190.0, "")],
                       dia(-5), condicao_pagamento="A vista")
    orc.enviar(formatura.id, quando=dia(-5))
    orc.aprovar(formatura.id)

    # ainda sendo montado no balcao
    propor("Patricia Nunes",
           [("Coloracao completa", 1, 280.0, ""),
            ("Tratamento de reconstrucao", 3, 120.0, "sessao")],
           dia(-1), condicao_pagamento="2x sem juros")

    # perdido por preco: o funil mostra o motivo, nao so o numero
    perdido = propor("Renata Alves", [("Alongamento de unhas", 1, 320.0, "")], dia(-12))
    orc.enviar(perdido.id, quando=dia(-12))
    orc.recusar(perdido.id, MOTIVO_PRECO, quando=dia(-5))


def _venda_em_curso(hub, itens, cliente, desconto=0.0) -> None:
    """Deixa o balcão com uma venda pela metade.

    Não grava venda nenhuma: mexe na tela como o operador mexeria. PDV vazio
    dizendo "bipe o primeiro item" é a pior foto possível de um programa de
    vendas — o anúncio tem de mostrar o balcão com movimento.
    """
    _abrir(hub, "vendas")
    balcao = hub.launcher.get("vendas").balcao_view
    for codigo, quantidade in itens:
        balcao.bipe.setText(codigo)
        balcao._localizar()
        balcao.quantidade.setValue(quantidade)
        balcao._adicionar()
    balcao.cliente.setText(cliente)
    if desconto:
        balcao.desconto.setValue(desconto)


# ============================================== loja e empresa (a de sempre) ==
def cenario_empresa(hub) -> None:
    """A loja de ferragens da documentação, e ela basta.

    "Casa do Parafuso" já É uma pequena empresa: parafuso, cabo e monitor são
    mercadoria de balcão como qualquer outra. O que ela não servia era salão e
    mercearia — por isso só esses dois ganharam cenário próprio.
    """
    sys.path.insert(0, str(RAIZ / "tools"))
    import dados_demo

    dados_demo.semear_tudo(hub)
    dados_demo.semear_balcao_em_uso(hub)


# ==================================================================== fotos ==
CENAS = {
    "mercearia": (cenario_mercearia, [
        ("vendas", 0, "vendas-balcao"),
        ("vendas", 3, "vendas-caixa"),
        ("estoque", 1, "estoque-produtos"),
        ("estoque", 0, "estoque-painel"),
        ("financeiro", 0, "financeiro-painel"),
        ("financeiro", 2, "financeiro-contas"),
    ]),
    "empresa": (cenario_empresa, [
        ("vendas", 0, "vendas-balcao"),
        ("vendas", 1, "vendas-painel"),
        ("vendas", 3, "vendas-caixa"),
        ("estoque", 0, "estoque-painel"),
        ("estoque", 1, "estoque-produtos"),
        ("estoque", 2, "estoque-movimentacoes"),
        ("financeiro", 0, "financeiro-painel"),
        ("financeiro", 1, "financeiro-fluxo"),
        ("financeiro", 2, "financeiro-contas"),
        ("clientes", 0, "clientes-painel"),
        ("clientes", 1, "clientes-lista"),
        ("orcamentos", 0, "orcamentos-funil"),
        ("agenda", 0, "agenda-grade"),
    ]),
    "salao": (cenario_salao, [
        ("agenda", 0, "agenda-grade"),
        ("agenda", 1, "agenda-lista"),
        ("clientes", 0, "clientes-painel"),
        ("clientes", 1, "clientes-lista"),
        ("orcamentos", 0, "orcamentos-funil"),
        ("orcamentos", 1, "orcamentos-lista"),
    ]),
}


def _empresa(hub, nome: str, cidade: str = "Palmas") -> None:
    """A loja que assina a tela do celular e os documentos.

    Sem isto o celular abria com "Sua empresa" no topo - o texto de quem ainda
    nao configurou nada, bem no anuncio que promete um sistema pronto.
    """
    from dumtech.core.empresa import Empresa

    Empresa(nome=nome, cidade=cidade, uf="TO", telefone="6332258899",
            whatsapp="63988887777").salvar(hub.settings)


def _ajustar(aberta, app_id: str, indice: int) -> None:
    """Deixa a tela do jeito que rende foto, antes do clique do obturador.

    A grade da agenda abre no dia inteiro, e metade da imagem vira hora vazia
    de madrugada. No anúncio isso não é neutro: é metade da peça dizendo que o
    salão está vazio. "Comercial (7h às 20h)" mostra o dia de trabalho cheio.
    """
    if app_id == "agenda" and indice == 0:
        grade = aberta.views[0].widget
        posicao = grade.faixa.findData("comercial")
        if posicao >= 0:
            grade.faixa.setCurrentIndex(posicao)


#: o celular de cada cenário mostra SÓ o que aquele anúncio vende
MODULOS_DA_CENA = {
    "mercearia": ["VENDAS", "ESTOQUE", "FINANCEIRO"],
    "salao": ["AGENDA", "CLIENTES", "ORCAMENTOS"],
    "empresa": ["VENDAS", "FINANCEIRO", "ESTOQUE", "ORCAMENTOS", "AGENDA", "CLIENTES"],
}


def _resumo_do_celular(hub, pasta, cenario: str) -> None:
    """Grava o resumo que o celular receberia desta loja.

    É o MESMO `core.celular.montar` que o Hub manda para o servidor — não é
    uma tela inventada para o anúncio. Vira `celular.json`, e a prévia do
    telefone desenha a página de verdade a partir dele.
    """
    import json

    from dumtech import __version__
    from dumtech.core import celular as nucleo
    from dumtech.core.paths import get_paths

    empresa = hub.launcher.empresa()
    resumo = nucleo.montar(hub.registry.available(), get_paths(),
                           empresa=empresa.nome if empresa is not None else "",
                           versao=__version__)
    # o anúncio do salão não pode mostrar Estoque no celular: o comprador
    # entenderia que leva sete módulos e ficaria bravo depois da compra
    liberados = MODULOS_DA_CENA[cenario]
    resumo["secoes"] = [s for s in resumo["secoes"] if s["app"] in liberados]
    # o formato que o celular guarda em cache: a resposta do servidor inteira
    pacote = {
        "ok": True,
        "cliente": resumo.get("empresa") or "",
        "modulos": liberados,
        "espelhos": [{
            "computador": "Computador da loja",
            "atualizado_em": resumo.get("gerado_em"),
            "dados": resumo,
        }],
    }
    (pasta / "celular.json").write_text(
        json.dumps(pacote, ensure_ascii=False), encoding="utf-8")
    print("   celular.json")


def _um_cenario(cenario: str) -> None:
    """Fotografa UM cenário. Roda sozinho no processo, e é por isso que presta.

    `core.paths.get_paths` guarda a pasta de dados em cache, então trocar
    DUMTECH_DATA_DIR no meio do caminho não separa nada: os três cenários
    caíam no mesmo banco e a agenda do salão acabava com "Instalação de rede"
    da loja de informática no meio das progressivas.
    """
    semear, fotos = CENAS[cenario]
    pasta = SAIDA / cenario
    pasta.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    tema = ThemeManager(app, MODO_CLARO)
    hub = HubWindow(theme=tema)
    hub.launcher.notify = lambda *args: None
    hub.setAttribute(FORA_DA_TELA, True)
    hub.palette_dialog.setAttribute(FORA_DA_TELA, True)
    semear(hub)
    hub.refresh_rail()

    for app_id, indice, nome in fotos:
        aberta = _abrir(hub, app_id)
        aberta.show_view(indice)
        _ajustar(aberta, app_id, indice)
        hub.resize(*JANELA)
        hub.show()
        for _ in range(3):
            app.processEvents()
        imagem = hub.grab().toImage()
        if CORTE_TOPO:
            imagem = imagem.copy(0, CORTE_TOPO,
                                 imagem.width(), imagem.height() - CORTE_TOPO)
        imagem.save(str(pasta / f"{nome}.png"), "PNG")
        print("  ", nome)

    _resumo_do_celular(hub, pasta, cenario)
    hub.close()

    # a tela do celular sai da pagina de verdade, com este mesmo resumo.
    # Import por caminho, nao relativo: no subprocesso este arquivo roda como
    # __main__ e nao tem pacote pai.
    sys.path.insert(0, str(RAIZ / "tools"))
    from criativos.base import achar_navegador
    from criativos.celular import fotografar

    fotografar(cenario, achar_navegador())
    print("   celular.png")


def main() -> None:
    import subprocess

    if "--cena" in sys.argv:
        _um_cenario(sys.argv[sys.argv.index("--cena") + 1])
        return

    for cenario in CENAS:
        print(f"\n{cenario}")
        ambiente = dict(os.environ)
        # cada cenário nasce numa pasta de dados só dele
        ambiente["DUMTECH_DATA_DIR"] = tempfile.mkdtemp(prefix=f"dumtech_{cenario}_")
        resultado = subprocess.run(
            [sys.executable, __file__, "--cena", cenario],
            env=ambiente, capture_output=True, text=True,
        )
        print(resultado.stdout.rstrip())
        if resultado.returncode:
            print(resultado.stderr[-2000:])
            raise SystemExit(f"O cenário {cenario} falhou.")

    print(f"\nTelas em {SAIDA}")


if __name__ == "__main__":
    main()
