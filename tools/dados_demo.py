"""Os dados de demonstracao da plataforma.

Uma loja ficticia com um mes de historia: clientes, produtos, contas, propostas,
vendas, ordens de servico e a agenda da semana. Nasceu dentro do gerador de
imagens e mora aqui porque tem dois usos - as capturas da documentacao e o
`semear_demonstracao.py`, que enche a instalacao de verdade para alguem ver o
programa funcionando.

Um so lugar: se os dois tivessem a propria copia, a demonstracao que o cliente
ve deixaria de ser a que esta na documentacao.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from dumtech.core.contacts import Contato

HOJE = date.today()


def dia(offset: int) -> str:
    return (HOJE + timedelta(days=offset)).isoformat()


def abrir(hub, app_id: str):
    """Monta o aplicativo dentro do Hub e devolve a casca dele."""
    hub.open_app(app_id)
    return hub.launcher.get(app_id)


def semear_clientes(hub) -> None:
    """A carteira da loja - com um aniversariante hoje, de proposito.

    O aniversario de hoje faz o Inicio mostrar o aviso e o botao de WhatsApp
    abrir ja com o numero certo: e a funcionalidade inteira em uma linha.
    """
    aniversario_hoje = HOJE.replace(year=HOJE.year - 38).isoformat()
    for nome, cidade, telefone, whatsapp, nascimento, segmento in [
        ("Joao da Silva", "Palmas", "(63) 3225-1010", "(63) 99911-2233",
         "1988-04-12", "Pessoa fisica"),
        ("Maria Souza", "Araguaina", "", "(63) 98877-1100",
         "1995-11-30", "Pessoa fisica"),
        ("Mercado Central", "Palmas", "(63) 3225-8899", "(63) 99640-2211",
         "", "Comercio"),
        ("Ana Paula Lima", "Gurupi", "", "(63) 99123-4567",
         "1979-07-08", "Escritorio"),
        ("Carlos Menezes", "Palmas", "", "(63) 99555-8080",
         aniversario_hoje, "Pessoa fisica"),
        ("Padaria Bom Pao", "Palmas", "(63) 3215-4400", "(63) 99333-1212",
         "", "Alimentacao"),
        ("Auto Pecas Silva", "Paraiso do Tocantins", "", "(63) 99777-4545",
         "", "Comercio"),
        ("Escritorio Lima", "Gurupi", "(63) 3312-7788", "",
         "", "Escritorio"),
    ]:
        hub.contacts.criar(Contato(
            nome=nome, cidade=cidade, uf="TO", telefone=telefone,
            whatsapp=whatsapp, nascimento=nascimento, segmento=segmento,
            email=nome.split()[0].lower() + "@exemplo.com",
            observacoes="Cliente de demonstracao",
        ))


def semear_estoque(hub) -> None:
    from dumtech.apps.estoque.models import Produto

    repo = abrir(hub, "estoque").repository
    for codigo, nome, cat, un, qtd, minimo, maximo, custo, venda, local, ean in [
        ("MOU-001", "Mouse USB sem fio", "Perifericos", "UN", 24, 5, 40, 25.90, 59.90,
         "A1", "7891234567895"),
        ("TEC-002", "Teclado mecanico ABNT2", "Perifericos", "UN", 3, 4, 20, 149.00,
         289.00, "A2", "7891234567901"),
        ("CAB-010", "Cabo HDMI 2.0", "Cabos", "M", 48.5, 10, 100, 12.50, 34.90,
         "B1", ""),
        ("MON-021", "Monitor 24 polegadas", "Monitores", "UN", 6, 2, 12, 620.00,
         949.00, "C3", ""),
        ("SSD-512", "SSD 512GB NVMe", "Armazenamento", "UN", 0, 3, 15, 210.00, 379.00,
         "A4", ""),
        ("FIO-25", "Fio flexivel 2,5mm", "Cabos", "M", 132.75, 50, 300, 2.35, 4.90,
         "B2", ""),
    ]:
        repo.criar(Produto(codigo=codigo, nome=nome, categoria=cat, unidade=un,
                           quantidade=qtd, estoque_minimo=minimo, estoque_maximo=maximo,
                           preco_custo=custo, preco_venda=venda, localizacao=local,
                           codigo_barras=ean, fornecedor="Tech Distribuidora",
                           descricao="Produto de demonstracao"))
    mouse = repo.buscar_por_codigo("MOU-001")
    repo.registrar_entrada(mouse.id, 10, "Compra fornecedor Tech",
                           custo_unitario=24.50, fornecedor="Tech Distribuidora",
                           documento="NF 8821")
    repo.registrar_saida(mouse.id, 2, "Venda balcao")
    repo.registrar_saida(repo.buscar_por_codigo("CAB-010").id, 5, "Venda balcao")
    # uma contagem em andamento, para a tela ter o que mostrar
    repo.contar(mouse.id, 30)
    repo.contar(repo.buscar_por_codigo("MON-021").id, 6)
    repo.contar(repo.buscar_por_codigo("TEC-002").id, 2)


def semear_financeiro(hub) -> None:
    """Um mes real: contas, parcelamento, recorrencia, atraso e um aperto."""
    from dumtech.apps.financeiro.models import DESPESA, RECEITA, CAIXA, Conta, Lancamento

    repo = abrir(hub, "financeiro").repository
    banco = repo.criar_conta(Conta(nome="Banco do Brasil", saldo_inicial=4200.0))
    caixa = repo.criar_conta(Conta(nome="Caixa da loja", tipo=CAIXA, saldo_inicial=380.0))
    repo.transferir(banco.id, caixa.id, 500.0, dia(-2), "Troco da semana")

    def lancar(tipo, descricao, categoria, cliente, valor, venc, conta=None):
        return repo.criar(Lancamento(
            tipo=tipo, descricao=descricao, categoria=categoria, cliente=cliente,
            valor=valor, vencimento=venc, forma_pagamento="Pix",
            conta_id=(conta or banco).id,
        ))

    # a receber
    grande = lancar(RECEITA, "Instalacao de rede - Mercado Central", "Servicos",
                    "Mercado Central", 4800.0, dia(6))
    repo.baixar(grande.id, 1800.0, dia(0), banco.id, "Pix")    # entrada parcial
    lancar(RECEITA, "Manutencao mensal", "Servicos", "Joao da Silva", 450.0, dia(-3))
    lancar(RECEITA, "Venda balcao 998", "Vendas", "Maria Souza", 320.0, dia(12))

    # a pagar: o aluguel se repete, o equipamento foi parcelado
    repo.repetir(Lancamento(tipo=DESPESA, descricao="Aluguel da loja",
                            categoria="Fixas", valor=2200.0, vencimento=dia(8),
                            conta_id=banco.id), 6)
    repo.parcelar(Lancamento(tipo=DESPESA, descricao="Compra de equipamento",
                             categoria="Compras", valor=3600.0, vencimento=dia(4),
                             conta_id=banco.id), 3)
    lancar(DESPESA, "Fornecedor de perifericos", "Compras", "", 1340.0, dia(-5))
    energia = lancar(DESPESA, "Energia eletrica", "Fixas", "", 380.0, dia(-2))
    repo.baixar(energia.id, data=dia(0), conta_id=banco.id, forma="Boleto")
    lancar(DESPESA, "Contador", "Fixas", "", 620.0, dia(9), caixa)
    # o aperto do mes: e ele que faz a tela avisar a data em que o dinheiro acaba
    lancar(DESPESA, "Lote de mercadoria - Tech Distribuidora", "Compras", "",
           6800.0, dia(14))


def semear_orcamentos(hub) -> None:
    """Um funil de verdade: aprovadas, perdidas com motivo e uma parada ha dias."""
    from dumtech.apps.orcamentos.models import (
        MOTIVO_CONCORRENTE,
        MOTIVO_PRECO,
        MOTIVO_SEM_RESPOSTA,
        ItemOrcamento,
        Orcamento,
    )

    repo = abrir(hub, "orcamentos").repository

    def propor(cliente, itens, quando, **campos):
        return repo.salvar(Orcamento(
            numero=repo.proximo_numero(), cliente=cliente, data=quando,
            itens=[ItemOrcamento(descricao=d, quantidade=q, valor_unitario=v,
                                 desconto=desc, unidade=un)
                   for d, q, v, desc, un in itens],
            **campos,
        ))

    # rascunho: ainda sendo montado
    propor("Ana Paula Lima", [("Suporte mensal", 12, 250.0, 0.0, "mes")], dia(-1),
           condicao_pagamento="30 dias", prazo_entrega="A combinar")

    # enviada ha dias, esperando resposta
    parada = propor("Mercado Central",
                    [("Instalacao de rede", 1, 1800.0, 180.0, ""),
                     ("Cabo cat6", 60, 4.5, 20.0, "m")],
                    dia(-9), condicao_pagamento="50% na entrada, 50% na entrega",
                    prazo_entrega="10 dias uteis", validade_dias=15, desconto=100.0)
    repo.enviar(parada.id, quando=dia(-9))

    # enviada ontem, ainda no prazo
    recente = propor("Carlos Menezes", [("Montagem de PC", 1, 620.0, 0.0, "")],
                     dia(-1), condicao_pagamento="A vista", prazo_entrega="5 dias uteis")
    repo.enviar(recente.id, quando=dia(-1))

    # aprovadas neste mes
    for cliente, itens, desconto in (
        ("Joao da Silva", [("Formatacao completa", 1, 180.0, 0.0, ""),
                           ("SSD 512GB", 1, 379.0, 30.0, "")], 0.0),
        ("Maria Souza", [("Manutencao preventiva", 3, 220.0, 0.0, "h")], 60.0),
    ):
        aprovada = propor(cliente, itens, dia(-4), desconto=desconto,
                          condicao_pagamento="3x sem juros", prazo_entrega="Imediato")
        repo.aprovar(aprovada.id)

    # perdidas, cada uma com o seu motivo
    for cliente, valor, motivo in (
        ("Loja do Centro", 4200.0, MOTIVO_PRECO),
        ("Padaria Bom Pao", 1850.0, MOTIVO_PRECO),
        ("Escritorio Lima", 2600.0, MOTIVO_CONCORRENTE),
        ("Auto Pecas Silva", 980.0, MOTIVO_SEM_RESPOSTA),
    ):
        perdida = propor(cliente, [("Projeto e instalacao", 1, valor, 0.0, "")], dia(-15))
        repo.enviar(perdida.id, quando=dia(-15))
        repo.recusar(perdida.id, motivo, quando=dia(-6))


def semear_vendas(hub) -> None:
    """Um dia de balcao: caixa aberto, formas variadas, prazo e devolucao."""
    from dumtech.apps.vendas.models import ItemVenda, Pagamento, Venda
    from dumtech.apps.vendas.repository import pagamento_unico

    repo = abrir(hub, "vendas").repository
    repo.abrir_caixa(200.0)

    def vender(cliente, itens, pagamentos, desconto=0.0, quando=None):
        venda = Venda(
            cliente=cliente, data=quando or dia(0), desconto=desconto,
            itens=[ItemVenda(descricao=d, quantidade=q, valor_unitario=v,
                             produto_id=pid, codigo=cod)
                   for d, q, v, pid, cod in itens],
        )
        return repo.finalizar(venda, pagamentos)

    # os produtos do Estoque, para a venda aparecer ligada ao catalogo
    catalogo = repo.catalogo
    monitor = catalogo.buscar("MON-021") if catalogo else None
    mouse = catalogo.buscar("MOU-001") if catalogo else None

    def linha(item, quantidade, descricao, valor):
        if item is None:
            return (descricao, quantidade, valor, 0, "")
        return (item.nome, quantidade, item.preco, item.produto_id, item.codigo)

    vender("Mercado Central",
           [linha(monitor, 2, "Monitor 24 polegadas", 949.0)],
           [Pagamento(forma="Pix", valor=1000.0),
            Pagamento(forma="Dinheiro", valor=848.0, recebido=900.0)],
           desconto=50.0)
    vender("Maria Souza",
           [linha(mouse, 1, "Mouse USB sem fio", 59.9)],
           [pagamento_unico("Cartao de credito", 59.9)])
    vender("", [("Cabo HDMI 2.0 - 2m", 3, 34.9, 0, "")],
           [Pagamento(forma="Dinheiro", valor=104.7, recebido=150.0)])
    prazo = vender("Ana Paula Lima", [("Fonte ATX 500W", 2, 299.0, 0, "")],
                   [pagamento_unico("Prazo", 598.0)])
    devolvida = vender("Joao da Silva", [("Teclado mecanico ABNT2", 1, 289.0, 0, "")],
                       [pagamento_unico("Dinheiro", 289.0)], quando=dia(-1))
    repo.devolver(devolvida.id, [(devolvida.itens[0].id, 1)], "Cliente trocou de modelo")

    cancelada = vender("", [("Adaptador USB-C", 1, 89.0, 0, "")],
                       [pagamento_unico("Pix", 89.0)])
    repo.cancelar(cancelada.id, "Erro de operacao no balcao")
    repo.sangria(300.0, "Deposito no banco")
    assert prazo.status  # a venda a prazo fica no painel "A receber"


def juntar(*acessorios: str) -> str:
    """Acessorios sao uma linha por item."""
    return chr(10).join(acessorios)


def semear_ordens(hub) -> None:
    """Uma oficina de verdade: bancada cheia, um orcamento parado e uma entrega."""
    from dumtech.apps.ordens.models import ItemOS, Ordem, PECA, SERVICO

    repo = abrir(hub, "ordens").repository

    def abrir_os(cliente, equipamento, defeito, tecnico, dias, **campos):
        return repo.salvar(Ordem(
            numero=repo.proximo_numero(), cliente=cliente, equipamento=equipamento,
            defeito=defeito, tecnico=tecnico, aberta_em=dia(-dias),
            prazo=campos.pop("prazo", dia(5 - dias)), **campos,
        ))

    # 1) na entrada, esperando diagnostico
    abrir_os("Maria Souza", "Impressora Epson L3150", "Nao puxa papel",
             "Equipe DumTech", 1, telefone="(63) 98877-1100",
             acessorios=juntar("Cabo USB", "Fonte"),
             condicao="Tampa arranhada")

    # 2) orcamento pronto, esperando o cliente responder
    orcada = abrir_os("Ana Paula Lima", "Desktop montado", "Nao da video",
                      "Equipe DumTech", 4, telefone="(63) 99123-4567",
                      acessorios="Cabo de forca",
                      diagnostico="Fonte queimada e memoria com defeito",
                      itens=[ItemOS(tipo=PECA, descricao="Fonte 500W", valor_unitario=289.0),
                             ItemOS(tipo=PECA, descricao="Memoria 8GB", valor_unitario=210.0),
                             ItemOS(tipo=SERVICO, descricao="Mao de obra",
                                    valor_unitario=180.0)])
    repo.avancar(orcada.id)

    # 3) em servico, ja aprovada
    andamento = abrir_os("Joao da Silva", "Notebook Dell G15", "Nao liga",
                         "Equipe DumTech", 6, telefone="(63) 99911-2233",
                         acessorios=juntar("Carregador", "Capa"), senha="1234",
                         condicao="Risco na tampa e tecla F5 solta",
                         diagnostico="Curto no circuito de carga da placa mae",
                         itens=[ItemOS(tipo=PECA, descricao="Placa mae",
                                       valor_unitario=680.0),
                                ItemOS(tipo=SERVICO, descricao="Mao de obra",
                                       quantidade=2, valor_unitario=90.0)])
    repo.avancar(andamento.id)
    repo.aprovar(andamento.id, "Joao da Silva", "Autorizou por telefone")

    # 4) atrasada: passou do prazo e ainda esta na bancada
    atrasada = abrir_os("Mercado Central", "PDV Balcao 2", "Travando ao imprimir",
                        "Equipe DumTech", 9, prazo=dia(-2),
                        telefone="(63) 3225-8899",
                        acessorios=juntar("Fonte", "Cabo USB"))
    repo.avancar(atrasada.id)
    repo.aprovar(atrasada.id, "Mercado Central")

    # 5) pronta, esperando o cliente vir buscar
    pronta = abrir_os("Carlos Menezes", "Notebook Acer A515", "Superaquecendo",
                      "Equipe DumTech", 5, acessorios="Carregador",
                      diagnostico="Cooler entupido e pasta termica ressecada",
                      itens=[ItemOS(tipo=PECA, descricao="Pasta termica",
                                    valor_unitario=25.0),
                             ItemOS(tipo=SERVICO, descricao="Limpeza completa",
                                    valor_unitario=140.0)])
    repo.avancar(pronta.id)
    repo.aprovar(pronta.id, "Carlos Menezes")
    repo.avancar(pronta.id)

    # 6) entregue neste mes, dentro da garantia
    entregue = abrir_os("Maria Souza", "Celular Motorola G54", "Tela trincada",
                        "Equipe DumTech", 12, garantia_dias=90,
                        acessorios=juntar("Carregador", "Pelicula"),
                        diagnostico="Troca do modulo de tela",
                        itens=[ItemOS(tipo=PECA, descricao="Modulo de tela",
                                      valor_unitario=420.0),
                               ItemOS(tipo=SERVICO, descricao="Troca da tela",
                                      valor_unitario=120.0)])
    repo.avancar(entregue.id)
    repo.aprovar(entregue.id, "Maria Souza")
    repo.avancar(entregue.id)
    repo.entregar(entregue.id, "Maria Souza")


def semear_agenda(hub) -> None:
    """Uma semana de trabalho: atendimentos, visitas, almoco e um choque."""
    from dumtech.apps.agenda.models import (
        ATENDIMENTO,
        BLOQUEIO,
        CONFIRMADO,
        ENTREGA,
        VISITA,
        Compromisso,
        inicio_da_semana,
    )

    repo = abrir(hub, "agenda").repository
    segunda = inicio_da_semana(HOJE)

    def marcar(titulo, cliente, dia_util, hora, minutos, duracao, tipo, **campos):
        quando = datetime.combine(
            segunda + timedelta(days=dia_util), datetime.min.time()
        ).replace(hour=hora, minute=minutos)
        return repo.salvar(Compromisso(
            titulo=titulo, cliente=cliente, inicio=quando.isoformat(timespec="minutes"),
            duracao_min=duracao, tipo=tipo, **campos,
        ))

    # o almoco se repete a semana inteira: bloqueio ocupa a grade
    almoco = Compromisso(
        titulo="Almoco", tipo=BLOQUEIO, duracao_min=60,
        inicio=datetime.combine(segunda, datetime.min.time())
        .replace(hour=12).isoformat(timespec="minutes"),
    )
    repo.repetir(almoco, 5, "diaria")

    marcar("Visita tecnica", "Mercado Central", 0, 9, 0, 90, VISITA,
           local="Loja do cliente", status=CONFIRMADO)
    marcar("Manutencao preventiva", "Maria Souza", 0, 14, 0, 120, ATENDIMENTO,
           local="Escritorio")
    marcar("Entrega de equipamento", "Joao da Silva", 1, 10, 30, 30, ENTREGA,
           local="Balcao", status=CONFIRMADO)
    marcar("Instalacao de rede", "Mercado Central", 2, 8, 0, 240, VISITA,
           local="Loja do cliente", status=CONFIRMADO)
    # dois no mesmo horario: a grade divide a coluna em vez de esconder um
    marcar("Orcamento no local", "Ana Paula Lima", 2, 9, 0, 60, VISITA,
           local="Escritorio Lima")
    marcar("Suporte remoto", "Carlos Menezes", 3, 15, 0, 45, ATENDIMENTO,
           local="Online")
    marcar("Reuniao de fechamento", "Equipe", 4, 17, 0, 60, ATENDIMENTO,
           local="Loja")
    marcar("Retirada de peca", "Padaria Bom Pao", 4, 11, 0, 30, ENTREGA,
           local="Balcao")


def semear_empresa(settings) -> None:
    """A loja que assina os documentos e as mensagens."""
    from dumtech.core.empresa import Empresa

    Empresa(
        nome="Casa do Parafuso", razao_social="Casa do Parafuso Comercio Ltda",
        documento="11.222.333/0001-81", telefone="6332258899",
        whatsapp="63988887777", email="contato@casadoparafuso.com.br",
        endereco="Avenida JK", numero="1200", bairro="Plano Diretor Sul",
        cidade="Palmas", uf="TO", cep="77020000",
        rodape="Obrigado pela preferencia! Garantia de 90 dias.",
    ).salvar(settings)


def semear_balcao_em_uso(hub) -> None:
    """Deixa uma venda pela metade no balcao.

    Nao grava nada - serve para a tela do PDV aparecer em uso, e nao vazia.
    """
    balcao = hub.launcher.get("vendas").balcao_view
    for codigo, quantidade in (("MOU-001", 2), ("CAB-010", 3), ("SSD-512", 1)):
        balcao.bipe.setText(codigo)
        balcao._localizar()
        balcao.quantidade.setValue(quantidade)
        balcao._adicionar()
    balcao.cliente.setText("Mercado Central")
    balcao.desconto.setValue(15.0)


def semear_tudo(hub) -> None:
    """A loja inteira, na ordem em que um modulo depende do outro.

    Clientes primeiro (os outros sugerem o nome), Estoque antes do Vendas (o
    balcao precisa do catalogo) e a empresa por ultimo, que so depende das
    preferencias.
    """
    semear_clientes(hub)
    semear_estoque(hub)
    semear_financeiro(hub)
    semear_orcamentos(hub)
    semear_vendas(hub)
    semear_ordens(hub)
    semear_agenda(hub)
    semear_empresa(hub.settings)
