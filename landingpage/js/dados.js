// Os módulos da DumTech e as integrações entre eles.
//
// DIVISÃO DE RESPONSABILIDADE
//   Aqui: a cópia da vitrine (nome, descrição, cor, ícone) — texto de venda,
//         escrito em português correto e revisado por gente.
//   No banco (dumtech_catalogo): preço e disponibilidade — o que muda toda hora
//         e não pode depender de publicar o site de novo.
//
// Tudo aqui é verdade conferida no código do Hub: cor e ícone saem do MANIFEST
// de cada aplicativo (src/dumtech/apps/<id>/module.py) e de ui/icons.py. As
// integrações são as pontes que existem de fato (hub/launcher.py,
// core/catalog.py, core/contas.py, core/pedidos.py, core/contacts.py).

export const MODULOS = [
  {
    codigo: "ESTOQUE",
    nome: "Estoque",
    descricao: "Produtos com código de barras, entrada de nota, contagem e planilha.",
    detalhe: "O custo médio se recalcula sozinho a cada entrada. Quem vende por peso vende 1,5 kg.",
    cor: "#8A7BF8",
    categoria: "Gestão",
    icone: "M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z M3 7.5 12 12l9-4.5 M12 12v9",
  },
  {
    codigo: "VENDAS",
    nome: "Vendas",
    descricao: "PDV de balcão: bipe, receba de várias formas e feche o caixa.",
    detalhe: "Nada é gravado até o pagamento fechar. Troco, sangria, devolução parcial e Pix no balcão.",
    cor: "#D8574F",
    categoria: "Vendas",
    icone: "M3 4h2.2l2.3 11.2a1.5 1.5 0 0 0 1.5 1.2h8.4a1.5 1.5 0 0 0 1.5-1.2L21 8H6 M9.5 20.5h.01 M17.5 20.5h.01",
  },
  {
    codigo: "FINANCEIRO",
    nome: "Financeiro",
    descricao: "Fluxo de caixa: projeção, parcelamento, baixa parcial e contas.",
    detalhe: "Mostra o dia em que o seu saldo cruza o zero — antes de ele cruzar.",
    cor: "#2E9E6B",
    categoria: "Gestão",
    icone: "M3 6h18v12H3z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M6.5 9.5h.01 M17.5 14.5h.01",
  },
  {
    codigo: "ORCAMENTOS",
    nome: "Orçamentos",
    descricao: "Proposta comercial com condições, documento em PDF e taxa de conversão.",
    detalhe: "O funil responde por que você perde: preço, prazo, concorrente ou silêncio.",
    cor: "#E0902F",
    categoria: "Vendas",
    icone: "M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7l-4-4z M14 3v4h4 M9 12.5h6 M9 16.5h6",
  },
  {
    codigo: "ORDENS",
    nome: "Ordem de Serviço",
    descricao: "Serviços por etapa, aprovação, garantia e comprovante — em qualquer ramo.",
    detalhe: "Cada passo fica gravado com hora e nunca é apagado. A garantia conta a partir da entrega.",
    cor: "#4C7EF3",
    categoria: "Serviços",
    icone: "M20.5 6.2a5.5 5.5 0 0 1-7.3 7.3L6 20.7a2 2 0 0 1-2.8-2.8l7.2-7.2a5.5 5.5 0 0 1 7.3-7.3l-3.2 3.2 2.8 2.8 3.2-3.2z",
  },
  {
    codigo: "CLIENTES",
    nome: "Clientes",
    descricao: "Ficha do cliente com documento, endereço, anotações e aniversários.",
    detalhe: "É a agenda que todos os outros módulos consultam para sugerir nomes.",
    cor: "#2FB6A6",
    categoria: "Cadastros",
    icone: "M9 11.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M2.5 20a6.5 6.5 0 0 1 13 0 M17 5.2a3.5 3.5 0 0 1 0 6.6 M18 14.4a6.5 6.5 0 0 1 3.5 5.6",
  },
  {
    codigo: "AGENDA",
    nome: "Agenda",
    descricao: "Grade da semana com conflito de horário, bloqueio e repetição.",
    detalhe: "Conflito avisa e pede um segundo clique — nunca trava o seu atendimento.",
    cor: "#C05FD4",
    categoria: "Serviços",
    icone: "M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M4 10h16 M8.5 3v4 M15.5 3v4 M8 14h.01 M12 14h.01 M16 14h.01",
  },
];

// As pontes que existem no programa. Cada uma vira uma linha acesa no grafo
// quando os dois lados estão no kit — e uma linha apagada, dizendo o que falta,
// quando só um lado está.
export const INTEGRACOES = [
  {
    id: "catalogo",
    de: "ESTOQUE",
    para: ["VENDAS", "ORCAMENTOS", "ORDENS"],
    titulo: "O seu estoque abastece o balcão, a proposta e a ordem de serviço",
    ativa: "Bipou o código de barras: nome e preço vêm do estoque, e a saída dá baixa sozinha — " +
           "na venda, na proposta aprovada e na peça que sai com a ordem de serviço.",
    falta: "Sem o Estoque, esses módulos vendem por item digitado à mão — funciona, mas ninguém dá baixa por você.",
  },
  {
    id: "receber_venda",
    de: "VENDAS",
    para: ["FINANCEIRO"],
    titulo: "Venda a prazo vira conta a receber",
    ativa: "A conta nasce sozinha no dia combinado; quando o cliente paga, ela se quita.",
    falta: "Sem o Financeiro, o fiado do balcão continua vivendo no caderno.",
  },
  {
    id: "receber_ordem",
    de: "ORDENS",
    para: ["FINANCEIRO"],
    titulo: "Serviço entregue cai no caixa",
    ativa: "Na entrega você diz se o cliente pagou na hora ou vai pagar depois — o Financeiro já fica certo.",
    falta: "Sem o Financeiro, o serviço entregue não entra na projeção.",
  },
  {
    id: "pagar_compra",
    de: "ESTOQUE",
    para: ["FINANCEIRO"],
    titulo: "Nota de compra vira conta a pagar",
    ativa: "Lançou a nota do fornecedor no Estoque: o saldo sobe e a conta a pagar nasce com o vencimento.",
    falta: "Sem o Financeiro, a compra entra no estoque mas a dívida fica fora da projeção.",
  },
  {
    id: "proposta",
    de: "ORCAMENTOS",
    para: ["VENDAS", "ORDENS"],
    titulo: "Proposta aprovada vira trabalho",
    ativa: "O sim do cliente vira venda no balcão ou ordem de serviço, com os itens já dentro.",
    falta: "Sem Vendas nem Ordens, a proposta aprovada é digitada de novo do outro lado.",
  },
  {
    id: "cadastro",
    de: "CLIENTES",
    para: ["VENDAS", "ORCAMENTOS", "ORDENS", "AGENDA", "FINANCEIRO"],
    titulo: "Um cadastro só, para todos",
    ativa: "O nome que você digita no balcão é o mesmo da proposta, da ordem e do compromisso.",
    falta: "Sem o Clientes, cada módulo guarda o nome do seu jeito.",
  },
];

// O que vem junto em qualquer kit, com um módulo ou com sete.
export const SEMPRE = [
  {
    titulo: "A tela Início junta o dia",
    texto: "Cada módulo manda o que precisa de você hoje: conta vencendo, estoque no mínimo, compromisso agora.",
  },
  {
    titulo: "Documento com a sua cara",
    texto: "Comprovante de bobina e proposta em PDF saem com o nome, o logotipo e o contato da sua empresa.",
  },
  {
    titulo: "WhatsApp sem digitar",
    texto: "A mensagem é montada a partir do que está na tela — você revisa e envia.",
  },
  {
    titulo: "Cópia de segurança diária",
    texto: "Uma cópia por dia, automática, guardada onde você escolher. As manuais nunca são apagadas.",
  },
  {
    titulo: "Funciona sem internet",
    texto: "A internet é usada só para ativar a licença. Depois disso, o programa é seu e roda offline.",
  },
];

// Rede de segurança: espelha os preços do banco (supabase/migrations). Só é
// usada se o servidor não responder — o preço de verdade vem de lá.
export const PRECO_PADRAO = {
  ESTOQUE: 49.9, VENDAS: 49.9, FINANCEIRO: 49.9, ORDENS: 49.9,
  ORCAMENTOS: 49.9, CLIENTES: 49.9, AGENDA: 49.9,
};

// Os kits de reserva: so aparecem se o servidor nao responder. Quem manda de
// verdade e o painel (tela Kits) - estes precos tem de acompanhar os de la.
export const KITS_PADRAO = [
  { codigo: "COMERCIO", ramo: "Loja ou comércio", nome: "Kit Comércio", preco: 119.9,
    descricao: "Balcão, estoque e cadastro de clientes para quem vende no dia a dia",
    produtos: ["CLIENTES", "ESTOQUE", "VENDAS"] },
  { codigo: "ATENDIMENTO", ramo: "Salão, clínica ou estética", nome: "Kit Atendimento", preco: 119.9,
    descricao: "Agenda, clientes e caixa para salão, clínica e estética",
    produtos: ["AGENDA", "CLIENTES", "VENDAS"] },
  { codigo: "SERVICOS", ramo: "Prestador de serviços", nome: "Kit Serviços", preco: 119.9,
    descricao: "Orçamento que vira ordem de serviço, com a ficha do cliente",
    produtos: ["CLIENTES", "ORCAMENTOS", "ORDENS"] },
  { codigo: "GESTAO", nome: "Kit Gestão", preco: 149.9,
    descricao: "Vendas, estoque, financeiro e clientes numa chave só",
    produtos: ["CLIENTES", "ESTOQUE", "FINANCEIRO", "VENDAS"] },
  { codigo: "OFICINA", ramo: "Oficina ou assistência técnica", nome: "Kit Oficina Completa", preco: 179.9,
    descricao: "Da proposta à entrega: peça sai do estoque e o valor cai no caixa",
    produtos: ["CLIENTES", "ESTOQUE", "FINANCEIRO", "ORCAMENTOS", "ORDENS"] },
  { codigo: "COMPLETO", ramo: "Quero tudo", nome: "Kit Completo", preco: 229.9,
    descricao: "Os 7 módulos, todas as integrações ligadas",
    produtos: ["AGENDA", "CLIENTES", "ESTOQUE", "FINANCEIRO", "ORCAMENTOS", "ORDENS", "VENDAS"] },
];

export const catalogoLocal = () => ({
  produtos: MODULOS.map((m) => ({
    codigo: m.codigo, nome: m.nome, descricao: m.descricao,
    preco: PRECO_PADRAO[m.codigo] ?? 0, versao: "",
  })),
  combos: KITS_PADRAO,
  local: true,
});

/** O módulo da vitrine, pelo código. */
export const moduloDe = (codigo) =>
  MODULOS.find((m) => m.codigo === String(codigo).toUpperCase()) ?? null;
