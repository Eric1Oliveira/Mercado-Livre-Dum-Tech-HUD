"""A empresa de demonstracao dos videos: uma assistencia tecnica com loja.

Usa todos os modulos de um jeito natural - vende acessorios no balcao,
conserta celular (ordem de servico), manda proposta, agenda visita e controla
as contas. Os dados sao de alguns dias de uso, para nenhuma tela abrir vazia.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

EMPRESA = "Conecta Assistência & Acessórios"


def dia(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def hora(dias: int, h: int, m: int = 0) -> str:
    base = datetime.combine(date.today() + timedelta(days=dias), datetime.min.time())
    return base.replace(hour=h, minute=m).isoformat(timespec="seconds")


CLIENTES = [
    ("Ana Souza", "11987654321", "Santo André", 0),
    ("Carlos Lima", "11976543210", "São Bernardo", 120),
    ("Juliana Alves", "11965432109", "Santo André", 40),
    ("Mercado Bom Preço", "1144332211", "Mauá", 300),
    ("Pedro Henrique", "11954321098", "São Caetano", 200),
    ("Beatriz Rocha", "11943210987", "Santo André", 15),
]

PRODUTOS = [
    # codigo, nome, categoria, barras, qtd, minimo, custo, venda
    ("CAP-IP13", "Capinha iPhone 13 transparente", "Capinhas", "7891000100013", 24, 5, 9.0, 39.90),
    ("PEL-3D", "Película 3D vidro temperado", "Películas", "7891000200020", 3, 10, 4.5, 29.90),
    ("CAR-20W", "Carregador USB-C 20W", "Carregadores", "7891000300037", 12, 4, 38.0, 89.90),
    ("CAB-USBC", "Cabo USB-C 1 metro", "Cabos", "7891000400044", 30, 8, 7.0, 24.90),
    ("FON-BT", "Fone Bluetooth com estojo", "Áudio", "7891000500051", 8, 3, 55.0, 129.90),
    ("SUP-VEI", "Suporte veicular magnético", "Acessórios", "7891000600068", 2, 4, 14.0, 49.90),
    ("TEL-A12", "Tela Samsung A12 (peça)", "Peças", "7891000700075", 6, 2, 95.0, 180.00),
    ("BAT-IP11", "Bateria iPhone 11 (peça)", "Peças", "7891000800082", 5, 2, 70.0, 150.00),
]


def semear(paths) -> None:
    from dumtech.apps.agenda.database import open_database as agenda_db
    from dumtech.apps.agenda.models import CONFIRMADO, ENTREGA, VISITA, Compromisso
    from dumtech.apps.agenda.repository import AgendaRepository
    from dumtech.apps.estoque.database import open_database as estoque_db
    from dumtech.apps.estoque.models import Produto
    from dumtech.apps.estoque.repository import EstoqueRepository
    from dumtech.apps.financeiro.database import open_database as fin_db
    from dumtech.apps.financeiro.models import CAIXA, DESPESA, RECEITA, Conta, Lancamento
    from dumtech.apps.financeiro.repository import FinanceiroRepository
    from dumtech.apps.orcamentos.database import open_database as orc_db
    from dumtech.apps.orcamentos.models import ItemOrcamento, Orcamento
    from dumtech.apps.orcamentos.repository import OrcamentosRepository
    from dumtech.apps.ordens.database import open_database as os_db
    from dumtech.apps.ordens.models import AGUARDANDO, ANDAMENTO, CONCLUIDA, ItemOS, Ordem, PECA, SERVICO
    from dumtech.apps.ordens.repository import OrdensRepository
    from dumtech.apps.vendas.database import open_database as vendas_db
    from dumtech.apps.vendas.models import ItemVenda, Pagamento, Venda
    from dumtech.apps.vendas.repository import VendasRepository
    from dumtech.core.contacts import ContactsStore, Contato

    # ---- clientes (a agenda que todos os modulos consultam)
    loja = ContactsStore(paths.platform_db)
    hoje = date.today()
    for nome, fone, cidade, dias_aniv in CLIENTES:
        nasc = (hoje + timedelta(days=dias_aniv)).replace(year=1988) if dias_aniv < 330 else None
        loja.criar(Contato(nome=nome, telefone=fone, whatsapp=fone, cidade=cidade, uf="SP",
                           nascimento=nasc.isoformat() if nasc else ""))
    loja.close()

    # ---- estoque
    banco = estoque_db(paths.app_db("estoque"))
    estoque = EstoqueRepository(banco)
    ids = {}
    for codigo, nome, cat, barras, qtd, minimo, custo, venda in PRODUTOS:
        p = estoque.criar(Produto(codigo=codigo, nome=nome, categoria=cat, codigo_barras=barras,
                                  quantidade=float(qtd), estoque_minimo=float(minimo),
                                  preco_custo=custo, preco_venda=venda, fornecedor="Distribuidora Sul"))
        ids[codigo] = (p.id, nome, venda)
    banco.close()

    # ---- vendas do dia e do mes
    banco = vendas_db(paths.app_db("vendas"))
    vendas = VendasRepository(banco)
    caixa = vendas.abrir_caixa(150.0)
    for cliente, itens, forma in (
        ("Ana Souza", [("CAP-IP13", 1), ("PEL-3D", 1)], "Pix"),
        ("", [("CAB-USBC", 2)], "Dinheiro"),
        ("Carlos Lima", [("CAR-20W", 1)], "Cartao de credito"),
        ("Juliana Alves", [("FON-BT", 1)], "Pix"),
        ("", [("PEL-3D", 2)], "Cartao de debito"),
    ):
        linhas = [ItemVenda(descricao=ids[c][1], quantidade=q, valor_unitario=ids[c][2], produto_id=ids[c][0],
                            codigo=c) for c, q in itens]
        total = sum(i.quantidade * i.valor_unitario for i in linhas)
        vendas.salvar(Venda(numero=vendas.proximo_numero(), cliente=cliente, forma_pagamento=forma,
                            caixa_id=caixa.id, itens=linhas,
                            pagamentos=[Pagamento(forma=forma, valor=total, recebido=total)]))
    banco.close()

    # ---- financeiro
    banco = fin_db(paths.app_db("financeiro"))
    fin = FinanceiroRepository(banco)
    conta = fin.criar_conta(Conta(nome="Banco Itaú", saldo_inicial=8420.0))
    fin.criar_conta(Conta(nome="Gaveta do balcão", tipo=CAIXA, saldo_inicial=150.0))
    for tipo, desc, cat, cliente, valor, venc in (
        (RECEITA, "Conserto notebook Dell", "Serviços", "Mercado Bom Preço", 480.0, -4),
        (RECEITA, "Venda a prazo - fones", "Vendas", "Pedro Henrique", 259.8, 6),
        (DESPESA, "Aluguel da loja", "Aluguel", "", 2200.0, 3),
        (DESPESA, "Distribuidora Sul - NF 1182", "Fornecedores", "", 1340.0, 5),
        (DESPESA, "Energia elétrica", "Contas da loja", "", 318.7, 9),
        (RECEITA, "Troca de tela - OS antiga", "Serviços", "Beatriz Rocha", 180.0, 12),
    ):
        fin.criar(Lancamento(tipo=tipo, descricao=desc, categoria=cat, cliente=cliente, valor=valor,
                             vencimento=dia(venc), conta_id=conta.id))
    banco.close()

    # ---- ordens de servico
    banco = os_db(paths.app_db("ordens"))
    ordens = OrdensRepository(banco)
    for cliente, equip, defeito, status, aberta, prazo, itens in (
        ("Beatriz Rocha", "iPhone 11", "Bateria descarregando rápido", CONCLUIDA, -3, 1,
         [(PECA, "Bateria iPhone 11 (peça)", 150.0), (SERVICO, "Mão de obra - troca de bateria", 60.0)]),
        ("Carlos Lima", "Samsung A12", "Tela trincada, touch falhando", ANDAMENTO, -2, 2,
         [(PECA, "Tela Samsung A12 (peça)", 180.0), (SERVICO, "Mão de obra - troca de tela", 70.0)]),
        ("Mercado Bom Preço", "Notebook Dell Inspiron", "Não liga", AGUARDANDO, -5, -1,
         [(SERVICO, "Diagnóstico e reparo da placa", 380.0)]),
        ("Juliana Alves", "Motorola G32", "Não carrega", "aberta", 0, 3, []),
    ):
        ordens.salvar(Ordem(numero=ordens.proximo_numero(), cliente=cliente, equipamento=equip, defeito=defeito,
                            status=status, aberta_em=dia(aberta), prazo=dia(prazo),
                            concluida_em=dia(-1) if status == CONCLUIDA else None,
                            itens=[ItemOS(tipo=t, descricao=d, valor_unitario=v) for t, d, v in itens]))
    banco.close()

    # ---- orcamentos
    banco = orc_db(paths.app_db("orcamentos"))
    orc = OrcamentosRepository(banco)
    for cliente, itens, data, enviar in (
        ("Mercado Bom Preço", [("Película 3D para 12 aparelhos", 12, 25.0), ("Instalação no local", 1, 90.0)], -6, True),
        ("Pedro Henrique", [("Fone Bluetooth com estojo", 2, 129.9)], -2, True),
        ("Ana Souza", [("Troca de tela iPhone 13", 1, 690.0)], 0, False),
    ):
        p = orc.salvar(Orcamento(numero=orc.proximo_numero(), cliente=cliente, data=dia(data), validade_dias=10,
                                 itens=[ItemOrcamento(descricao=d, quantidade=q, valor_unitario=v) for d, q, v in itens]))
        if enviar:
            orc.enviar(p.id, dia(data))
    banco.close()

    # ---- agenda
    banco = agenda_db(paths.app_db("agenda"))
    agenda = AgendaRepository(banco)
    for titulo, cliente, inicio, dur, tipo, status in (
        ("Retirada do iPhone 11", "Beatriz Rocha", hora(0, 10, 0), 30, ENTREGA, CONFIRMADO),
        ("Visita técnica - rede do mercado", "Mercado Bom Preço", hora(0, 14, 0), 90, VISITA, CONFIRMADO),
        ("Orçamento troca de tela", "Ana Souza", hora(0, 16, 30), 30, "atendimento", "agendado"),
        ("Entrega do Samsung A12", "Carlos Lima", hora(1, 11, 0), 30, ENTREGA, "agendado"),
        ("Instalação das películas", "Mercado Bom Preço", hora(2, 9, 0), 120, VISITA, "agendado"),
    ):
        agenda.salvar(Compromisso(titulo=titulo, cliente=cliente, inicio=inicio, duracao_min=dur,
                                  tipo=tipo, status=status))
    banco.close()
