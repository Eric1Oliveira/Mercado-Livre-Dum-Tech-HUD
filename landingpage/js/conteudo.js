// Os textos da pagina inicial. Puro (sem tela), testado em tests/conteudo.test.mjs.
//
// O Eric edita no painel (Textos do site) e publica; a vitrine entrega o
// publicado. O que nao foi publicado (ou veio torto) fica com o texto daqui,
// que e o de sempre. Tudo entra na pagina como TEXTO (textContent): nada que
// venha do banco vira codigo.
//
// Marcadores trocados na hora: {preco_base} {dias_teste} {computadores}

export const PADRAO = Object.freeze({
  hero: {
    rotulo: "Programa de gestão para Windows",
    titulo: "O balcão, o estoque e o caixa da sua empresa num programa só.",
    chamada: "O DumTech Hub roda no computador que você já tem e funciona mesmo sem internet. "
           + "Comece pelo plano base e ligue só o que o seu negócio usa.",
    nota: "Sem cartão. A chave chega no seu e-mail na hora. Plano base por {preco_base} por mês depois do teste.",
  },
  fatos: ["Funciona sem internet", "Cópia de segurança todo dia", "Comprovante com a sua marca", "Atendimento pelo WhatsApp"],
  base: {
    rotulo: "Plano base",
    titulo: "Tudo o que o balcão pede, desde o primeiro dia",
    texto: "Vendas, Estoque e Financeiro já vêm juntos, e conversam entre si: a venda baixa o estoque e já entra no caixa, "
         + "sem ninguém digitar duas vezes.",
  },
  modulos: {
    VENDAS: { frase: "Bipe, receba e feche o caixa.",
              detalhe: "Pix, cartão e dinheiro na mesma venda, troco calculado, sangria, devolução e o fechamento do caixa no fim do dia." },
    ESTOQUE: { frase: "Cada venda baixa o estoque sozinha.",
               detalhe: "Código de barras, entrada de nota, contagem e planilha. O custo médio se ajusta a cada entrada, e quem vende por peso vende 1,5 kg." },
    FINANCEIRO: { frase: "Saiba hoje se vai faltar dinheiro.",
                  detalhe: "Contas a pagar e a receber, parcelas e baixa parcial. O fluxo de caixa mostra o dia em que o saldo fica negativo, antes de acontecer." },
    CLIENTES: { frase: "Ficha de cada cliente, aniversários e o histórico do que ele comprou." },
    ORCAMENTOS: { frase: "Proposta com a sua marca em PDF, e o motivo de cada orçamento perdido." },
    ORDENS: { frase: "Serviço por etapa, com aprovação, garantia e comprovante de entrega." },
    AGENDA: { frase: "A semana sem horário encavalado, e um link para o cliente marcar sozinho." },
  },
  plano: {
    rotulo: "Quanto custa",
    titulo: "Um valor por mês, do tamanho do seu negócio",
    texto: "Escolha um plano pronto ou monte o seu: você paga o plano base e liga só os adicionais que fazem sentido. "
         + "Precisou de mais um depois? É só mudar o plano.",
  },
  inclui: ["Atualizações sem custo extra", "Cópia de segurança todo dia", "Atendimento pelo WhatsApp", "Uso em {computadores}"],
  como: { rotulo: "Como começar", titulo: "Do cadastro ao balcão em poucos minutos" },
  passos: [
    { titulo: "Peça o seu teste", texto: "Só nome e e-mail. Não pedimos cartão." },
    { titulo: "A chave chega no e-mail", texto: "Junto com o link para baixar o programa para Windows 10 e 11." },
    { titulo: "Use tudo por {dias_teste} dias", texto: "Todos os módulos liberados. O que você lançar fica guardado no seu computador." },
    { titulo: "Gostou? Assine", texto: "O pagamento é pela InfinitePay, todo mês. A chave continua a mesma." },
  ],
  comecar: { rotulo: "Comece agora", titulo: "Testar é grátis. Assinar leva um minuto." },
  duvidas: {
    rotulo: "Dúvidas",
    titulo: "O que as pessoas perguntam antes de começar",
    itens: [
      { pergunta: "Preciso de cartão para testar?",
        resposta: "Não. Para testar você só informa o nome e o e-mail. A forma de pagamento aparece apenas se você decidir assinar." },
      { pergunta: "E se a mensalidade atrasar?",
        resposta: "Nada se perde. Você recebe um aviso e o programa continua funcionando normalmente por alguns dias. Se o pagamento não for confirmado, ele fica só para consulta: dá para ver e exportar tudo o que você lançou, mas não lançar coisas novas. Assim que o pagamento é confirmado, volta ao normal sozinho." },
      { pergunta: "Posso cancelar quando quiser?",
        resposta: "Pode. É só avisar a gente pelo WhatsApp. Os seus dados continuam no seu computador, e se quiser voltar depois, a mesma chave volta a valer." },
      { pergunta: "Precisa de internet para usar?",
        resposta: "Não. O programa funciona offline no dia a dia. A internet só é usada para ativar a chave e para conferir a assinatura de vez em quando." },
      { pergunta: "Em quantos computadores posso usar?",
        resposta: "O plano vale para {computadores}. Precisa de mais? Fale com a gente pelo WhatsApp que a gente monta o plano certo para a sua loja." },
      { pergunta: "Onde ficam os meus dados?",
        resposta: "No seu computador. O programa faz uma cópia de segurança todo dia, para você não perder nada se o computador der problema." },
      { pergunta: "Como é o pagamento?",
        resposta: "Pela InfinitePay, todo mês, na página de pagamento dela. Você escolhe a forma de pagar por lá." },
      { pergunta: "Já comprei a licença vitalícia. Muda alguma coisa para mim?",
        resposta: "Não muda nada. A sua licença continua valendo para sempre, sem mensalidade, e as atualizações continuam chegando normalmente. Quer mais um módulo? Chame a gente no WhatsApp." },
    ],
  },
  contato: {
    titulo: "Prefere conversar antes?",
    texto: "Chame a DumTech no WhatsApp. A gente tira as suas dúvidas e ajuda você a escolher o plano certo para o seu negócio.",
  },
  whatsapp: "5511978042160",
});

/** Limite de cada texto, pelo caminho. O que passar e cortado (nao recusado). */
const LIMITES = { titulo: 140, rotulo: 60, chamada: 400, nota: 240, texto: 600, frase: 140, detalhe: 300,
                  pergunta: 160, resposta: 900, item: 120 };
const MAX_ITENS = 16;

function textoLimpo(valor, limite) {
  if (typeof valor !== "string") return null;
  const limpo = valor.replace(/\r\n?/g, "\n").trim();
  return limpo ? limpo.slice(0, limite) : null;
}

/**
 * O publicado por cima do padrao, campo a campo. So entra texto onde o padrao
 * tem texto e lista onde o padrao tem lista: o resto (e o que vier torto) fica
 * com o padrao.
 */
export function mesclar(publicado, padrao = PADRAO, chave = "") {
  if (Array.isArray(padrao)) {
    if (!Array.isArray(publicado)) return padrao;
    const modelo = padrao[0];
    const itens = publicado.slice(0, MAX_ITENS)
      .map((item) => (typeof modelo === "string"
        ? textoLimpo(item, LIMITES.item)
        : mesclarObjeto(item, modelo, true)))
      .filter(Boolean);
    return itens.length ? itens : padrao;
  }
  if (typeof padrao === "string") {
    if (chave === "whatsapp") {
      const numero = String(publicado ?? "").replace(/\D/g, "");
      return numero.length >= 12 && numero.length <= 15 ? numero : padrao;
    }
    return textoLimpo(publicado, LIMITES[chave] ?? 600) ?? padrao;
  }
  return mesclarObjeto(publicado, padrao, false);
}

function mesclarObjeto(publicado, padrao, exigeTudo) {
  const dado = publicado && typeof publicado === "object" && !Array.isArray(publicado) ? publicado : {};
  const saida = {};
  for (const [chave, valor] of Object.entries(padrao)) {
    if (exigeTudo && typeof valor === "string") {
      // item de lista (pergunta, passo): ou vem completo, ou nao entra
      const texto = textoLimpo(dado[chave], LIMITES[chave] ?? 600);
      if (!texto) return null;
      saida[chave] = texto;
    } else {
      saida[chave] = mesclar(dado[chave], valor, chave);
    }
  }
  return saida;
}

/** Os marcadores: o valor de cada um, ja formatado. */
export function valoresDosMarcadores({ precoBase, diasTeste, computadores }) {
  return {
    preco_base: Number(precoBase || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }),
    dias_teste: String(diasTeste),
    computadores: `${computadores} ${Number(computadores) === 1 ? "computador" : "computadores"}`,
  };
}

/**
 * "Plano base por {preco_base}" -> [{texto: "Plano base por "}, {valor: "R$ 89,90"}].
 * A tela poe o valor em destaque; marcador desconhecido fica como estava.
 */
export function pedacos(texto, valores) {
  const saida = [];
  let resto = String(texto ?? "");
  const marcador = /\{(preco_base|dias_teste|computadores)\}/;
  let achado;
  while ((achado = marcador.exec(resto))) {
    if (achado.index) saida.push({ texto: resto.slice(0, achado.index) });
    saida.push({ valor: valores[achado[1]] });
    resto = resto.slice(achado.index + achado[0].length);
  }
  if (resto) saida.push({ texto: resto });
  return saida;
}

export const preencher = (texto, valores) =>
  pedacos(texto, valores).map((p) => p.texto ?? p.valor).join("");

// ------------------------------------------------------- a pre-visualizacao --
// O painel mora no mesmo endereco do site: ele grava o rascunho aqui e abre
// a pagina com ?previa=1. Nao passa pela internet e nao fica no ar.
export const CHAVE_PREVIA = "dumtech.previa";
const VALIDADE_PREVIA_MS = 2 * 60 * 60 * 1000;

export function previaGuardada(armazem, agora = Date.now()) {
  try {
    const dados = JSON.parse(armazem?.getItem(CHAVE_PREVIA) ?? "null");
    if (!dados?.conteudo || typeof dados.conteudo !== "object") return null;
    if (!(agora - Number(dados.quando) < VALIDADE_PREVIA_MS)) return null;
    return dados.conteudo;
  } catch {
    return null;
  }
}
