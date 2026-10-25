"""A loja de demonstracao "Mercado & Cia": um mercadinho de bairro.

So tem Estoque, Vendas e Financeiro liberados (MODULOS vira a licenca local do
video). Vende no balcao, compra da distribuidora e controla o fiado e as
contas. Os dados sao de alguns dias de uso, para nenhuma tela abrir vazia.
"""

from __future__ import annotations

from datetime import date, timedelta

EMPRESA = "Mercado & Cia"
CIDADE = "Santo André"
MODULOS = ("estoque", "vendas", "financeiro")


def dia(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


CLIENTES = [
    ("Maria Aparecida", "11987001122", "Santo André"),
    ("José Carlos", "11976002233", "Santo André"),
    ("Fernanda Lima", "11965003344", "São Bernardo"),
    ("Lanchonete do Zé", "1144556677", "Santo André"),
    ("Restaurante Sabor Caseiro", "1143219876", "Mauá"),
    ("Roberto Nunes", "11954004455", "São Caetano"),
]

PRODUTOS = [
    # codigo, nome, categoria, barras, qtd, minimo, custo, venda
    ("ARR-5KG", "Arroz branco tipo 1 5kg", "Mercearia", "7896000100015", 40, 10, 19.90, 27.90),
    ("FEI-1KG", "Feijão carioca 1kg", "Mercearia", "7896000200012", 35, 10, 5.80, 8.49),
    ("CAF-500", "Café torrado e moído 500g", "Mercearia", "7896000300019", 6, 12, 14.50, 21.90),
    ("ACU-1KG", "Açúcar refinado 1kg", "Mercearia", "7896000400016", 28, 10, 3.60, 5.29),
    ("OLE-900", "Óleo de soja 900ml", "Mercearia", "7896000500013", 4, 10, 5.40, 7.99),
    ("LEI-1L", "Leite integral 1L", "Laticínios", "7896000600010", 60, 24, 3.90, 5.79),
    ("REF-2L", "Refrigerante de cola 2L", "Bebidas", "7896000700017", 18, 12, 6.50, 10.99),
    ("DET-500", "Detergente neutro 500ml", "Limpeza", "7896000800014", 50, 15, 1.60, 2.79),
    ("PAP-12", "Papel higiênico 12 rolos", "Higiene", "7896000900011", 15, 6, 13.00, 19.90),
]


def semear(paths) -> None:
    from dumtech.apps.estoque.database import open_database as estoque_db
    from dumtech.apps.estoque.models import Produto
    from dumtech.apps.estoque.repository import EstoqueRepository
    from dumtech.apps.financeiro.database import open_database as fin_db
    from dumtech.apps.financeiro.models import CAIXA, DESPESA, RECEITA, Conta, Lancamento
    from dumtech.apps.financeiro.repository import FinanceiroRepository
    from dumtech.apps.vendas.database import open_database as vendas_db
    from dumtech.apps.vendas.models import ItemVenda, Pagamento, Venda
    from dumtech.apps.vendas.repository import VendasRepository
    from dumtech.core.contacts import ContactsStore, Contato

    # ---- clientes (aparecem como sugestao no balcao e no financeiro)
    loja = ContactsStore(paths.platform_db)
    for nome, fone, cidade in CLIENTES:
        loja.criar(Contato(nome=nome, telefone=fone, whatsapp=fone, cidade=cidade, uf="SP"))
    loja.close()

    # ---- estoque
    banco = estoque_db(paths.app_db("estoque"))
    estoque = EstoqueRepository(banco)
    ids = {}
    for codigo, nome, cat, barras, qtd, minimo, custo, venda in PRODUTOS:
        p = estoque.criar(Produto(codigo=codigo, nome=nome, categoria=cat, codigo_barras=barras,
                                  quantidade=float(qtd), estoque_minimo=float(minimo),
                                  preco_custo=custo, preco_venda=venda, fornecedor="Distribuidora Paulista"))
        ids[codigo] = (p.id, nome, venda)
    banco.close()

    # ---- vendas do dia
    banco = vendas_db(paths.app_db("vendas"))
    vendas = VendasRepository(banco)
    caixa = vendas.abrir_caixa(200.0)
    for cliente, itens, forma in (
        ("Maria Aparecida", [("ARR-5KG", 1), ("FEI-1KG", 2), ("OLE-900", 1)], "Pix"),
        ("", [("LEI-1L", 6), ("CAF-500", 1)], "Dinheiro"),
        ("José Carlos", [("REF-2L", 2), ("PAP-12", 1)], "Cartao de debito"),
        ("", [("DET-500", 3), ("ACU-1KG", 2)], "Dinheiro"),
        ("Roberto Nunes", [("ARR-5KG", 2), ("CAF-500", 2)], "Cartao de credito"),
        ("", [("LEI-1L", 12)], "Pix"),
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
    conta = fin.criar_conta(Conta(nome="Conta corrente", saldo_inicial=12350.0))
    fin.criar_conta(Conta(nome="Gaveta do caixa", tipo=CAIXA, saldo_inicial=200.0))
    for tipo, desc, cat, cliente, valor, venc in (
        (RECEITA, "Fiado do mês - Lanchonete do Zé", "Vendas", "Lanchonete do Zé", 640.0, -3),
        (RECEITA, "Fornecimento semanal - Sabor Caseiro", "Vendas", "Restaurante Sabor Caseiro", 1180.0, 5),
        (RECEITA, "Fiado - Maria Aparecida", "Vendas", "Maria Aparecida", 86.5, 10),
        (DESPESA, "Aluguel do mercado", "Aluguel", "", 3200.0, 4),
        (DESPESA, "Distribuidora Paulista - NF 4471", "Fornecedores", "", 2860.0, 6),
        (DESPESA, "Hortifrúti Vale Verde - entrega", "Fornecedores", "", 540.0, 2),
        (DESPESA, "Energia elétrica (freezers)", "Contas da loja", "", 912.4, 9),
    ):
        fin.criar(Lancamento(tipo=tipo, descricao=desc, categoria=cat, cliente=cliente, valor=valor,
                             vencimento=dia(venc), conta_id=conta.id))
    banco.close()
