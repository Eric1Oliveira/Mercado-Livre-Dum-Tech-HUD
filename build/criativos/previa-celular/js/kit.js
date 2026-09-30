// O motor do "monte seu kit": escolha, preco e integracoes.
//
// Modulo puro, sem DOM e sem rede - por isso ele e testado sozinho
// (landingpage/tests/kit.test.mjs). O navegador so pinta o que sai daqui.
//
// Regra de ouro: o preco mostrado aqui e uma PREVIA. Quem soma de verdade e o
// banco, na hora de registrar o pedido - o navegador nunca decide quanto custa.

import { INTEGRACOES } from "./dados.js";

export function criarKit(catalogo, jaTem = []) {
  return {
    catalogo,
    // modulos que o cliente ja comprou (vem do token do Hub): aparecem
    // marcados, mas nao sao cobrados de novo
    jaTem: [...jaTem].map((c) => c.toUpperCase()),
    escolhidos: [],
  };
}

export function alternar(kit, codigo) {
  codigo = codigo.toUpperCase();
  if (kit.jaTem.includes(codigo)) return kit; // ja e dele; nao entra no kit
  const escolhidos = kit.escolhidos.includes(codigo)
    ? kit.escolhidos.filter((c) => c !== codigo)
    : [...kit.escolhidos, codigo];
  return { ...kit, escolhidos };
}

export function aplicarCombo(kit, comboCodigo) {
  const combo = acharCombo(kit, comboCodigo);
  if (!combo) return kit;
  const faltando = combo.produtos.filter(
    (c) => !kit.escolhidos.includes(c) && !kit.jaTem.includes(c)
  );
  // clicar de novo no combo ja aplicado desmarca o que ele trouxe
  const escolhidos = faltando.length
    ? [...kit.escolhidos, ...faltando]
    : kit.escolhidos.filter((c) => !combo.produtos.includes(c));
  return { ...kit, escolhidos };
}

export function limpar(kit) {
  return { ...kit, escolhidos: [] };
}

/**
 * Escolher um kit: ele SUBSTITUI o que estava escolhido.
 *
 * Kit e escolha unica, como um radio - modulo avulso e que soma e tira. A tela
 * tinha os dois caminhos (o botao do ramo e o cartao do kit) escritos a mao, e
 * cada um fazia diferente: o do ramo limpava antes, o do cartao somava. Clicar
 * em tres kits seguidos deixava 7 modulos marcados e acendia um cartao que
 * ninguem tinha clicado - o `melhorCombo` do conjunto que se formou sozinho.
 *
 * Existe para que os dois chamem A MESMA coisa e nao voltem a divergir.
 */
export function escolherKit(kit, comboCodigo) {
  return aplicarCombo(limpar(kit), comboCodigo);
}

/**
 * Acabou de fechar um combo? Devolve o codigo dele, ou null.
 *
 * E a pergunta que a animacao de "voce ganhou desconto" responde: o cliente
 * vinha marcando modulo a modulo e, sem pedir, o conjunto virou um combo.
 *
 * Aqui so comparamos DOIS estados. Quem decide se aquilo merece animacao e a
 * tela: clicar no cartao do kit tambem fecha combo, mas ninguem se surpreende
 * com o que acabou de pedir. So o caminho do modulo avulso comemora.
 */
export function comboRecemFechado(antes, depois) {
  const deAntes = resumo(antes).combo;
  const deAgora = resumo(depois).combo;
  return deAgora && deAgora !== deAntes ? deAgora : null;
}

/** Tudo o que a tela precisa mostrar sobre o kit atual. */
export function resumo(kit) {
  const escolhidos = ordenar(kit, kit.escolhidos);
  const combo = melhorCombo(kit, escolhidos);
  const doCombo = combo ? combo.produtos.filter((c) => escolhidos.includes(c)) : [];
  const avulsos = escolhidos.filter((c) => !doCombo.includes(c));

  const itens = [
    ...(combo ? [{ tipo: "combo", codigo: combo.codigo, nome: combo.nome,
                   preco: combo.preco, produtos: doCombo }] : []),
    ...avulsos.map((codigo) => ({
      tipo: "produto", codigo, nome: nomeDe(kit, codigo), preco: precoDe(kit, codigo),
    })),
  ];

  const total = itens.reduce((soma, item) => soma + item.preco, 0);
  const cheio = escolhidos.reduce((soma, c) => soma + precoDe(kit, c), 0);

  return {
    escolhidos,
    itens,
    combo: combo ? combo.codigo : null,
    total,
    economia: Math.max(0, cheio - total),
    vazio: escolhidos.length === 0,
  };
}

/**
 * As integracoes, do jeito que a tela mostra:
 *   ativa    -> os dois lados estao no kit (ou o cliente ja tem)
 *   dormente -> um lado esta; diz o que falta para acender
 *   fora     -> nenhum lado escolhido ainda
 */
export function integracoes(kit) {
  const tem = new Set([...kit.escolhidos, ...kit.jaTem]);
  return INTEGRACOES.map((integracao) => {
    const temOrigem = tem.has(integracao.de);
    const destinos = integracao.para.filter((c) => tem.has(c));
    const faltando = temOrigem
      ? integracao.para.filter((c) => !tem.has(c))
      : [integracao.de];

    let estado = "fora";
    if (temOrigem && destinos.length) estado = "ativa";
    else if (temOrigem || destinos.length) estado = "dormente";

    return {
      ...integracao,
      estado,
      ligacoes: temOrigem ? destinos.map((para) => ({ de: integracao.de, para })) : [],
      faltando,
    };
  });
}

/** Quantas ligacoes estao acesas - o numero que a tela anima. */
export function contarLigacoes(kit) {
  return integracoes(kit)
    .filter((i) => i.estado === "ativa")
    .reduce((soma, i) => soma + i.ligacoes.length, 0);
}

/**
 * O kit que vale a pena oferecer agora, ou null.
 *
 * Nao basta "faltam poucos modulos para um kit": so um kit vale por compra, e
 * completar um kit pode nao mudar nada no total (com o Gestao no carrinho,
 * "leve a Agenda e forme o Atendimento" nao baixa um centavo). Entao cada
 * candidato e SIMULADO no carrinho de verdade, e so entra se o kit for mesmo
 * aplicado e o que falta sair mais barato do que avulso. Ganha o que mais
 * economiza - com 6 modulos, isso e "o setimo sai por mais R$ 0,10".
 */
export function sugestao(kit) {
  if (!kit.escolhidos.length) return null;
  const atual = resumo(kit).total;
  const tem = new Set([...kit.escolhidos, ...kit.jaTem]);
  let melhor = null;
  for (const combo of kit.catalogo.combos ?? []) {
    const faltando = combo.produtos.filter((c) => !tem.has(c));
    if (!faltando.length || faltando.length > 2) continue;
    const depois = resumo({ ...kit, escolhidos: [...kit.escolhidos, ...faltando] });
    if (depois.combo !== combo.codigo) continue;
    const avulso = centavos(faltando.reduce((soma, c) => soma + precoDe(kit, c), 0));
    const acrescimo = centavos(depois.total) - centavos(atual);
    const ganho = avulso - acrescimo;
    if (ganho <= 0 || (melhor && ganho <= melhor.ganhoCentavos)) continue;
    melhor = {
      ...combo, faltando,
      totalAtual: atual, totalNovo: depois.total,
      acrescimo: acrescimo / 100, avulso: avulso / 100,
      economia: ganho / 100, ganhoCentavos: ganho,
    };
  }
  return melhor;
}

const centavos = (valor) => Math.round(Number(valor || 0) * 100);

/** O que vai para o servidor: produtos avulsos + o combo, se houver. */
export function pedido(kit) {
  const { itens } = resumo(kit);
  return {
    combo: itens.find((i) => i.tipo === "combo")?.codigo ?? null,
    produtos: itens.filter((i) => i.tipo === "produto").map((i) => i.codigo),
  };
}

// ------------------------------------------------------------------ interno
function acharCombo(kit, codigo) {
  return (kit.catalogo.combos ?? []).find((c) => c.codigo === codigo) ?? null;
}

/** O combo mais vantajoso que cabe inteiro dentro do que foi escolhido. */
function melhorCombo(kit, escolhidos) {
  let melhor = null;
  let melhorEconomia = 0;
  for (const combo of kit.catalogo.combos ?? []) {
    const dentro = combo.produtos.every(
      (c) => escolhidos.includes(c) || kit.jaTem.includes(c)
    );
    const usados = combo.produtos.filter((c) => escolhidos.includes(c));
    // combo so vale se o cliente esta comprando a maior parte dele agora
    if (!dentro || usados.length < 2) continue;
    const cheio = usados.reduce((soma, c) => soma + precoDe(kit, c), 0);
    const economia = cheio - combo.preco;
    if (economia > melhorEconomia) {
      melhor = combo;
      melhorEconomia = economia;
    }
  }
  return melhor;
}

function produtoDe(kit, codigo) {
  return (kit.catalogo.produtos ?? []).find((p) => p.codigo === codigo) ?? null;
}

function precoDe(kit, codigo) {
  return Number(produtoDe(kit, codigo)?.preco ?? 0);
}

function nomeDe(kit, codigo) {
  return produtoDe(kit, codigo)?.nome ?? codigo;
}

function ordenar(kit, codigos) {
  const ordem = (kit.catalogo.produtos ?? []).map((p) => p.codigo);
  return [...codigos].sort((a, b) => ordem.indexOf(a) - ordem.indexOf(b));
}

/**
 * Quanto o cupom desconta deste total - a MESMA conta do banco
 * (dumtech_aplicar_cupom): % arredondado no centavo, R$ fixo, e nunca deixa
 * o total abaixo de R$ 1 (a InfinitePay nao cobra zero). E so previa: o
 * pedido e recalculado no servidor.
 */
export function descontoDoCupom(cupom, total) {
  if (!cupom || !(total > 0)) return 0;
  const bruto = cupom.tipo === "percentual"
    ? Math.round(total * Number(cupom.valor) + Number.EPSILON) / 100
    : Number(cupom.valor);
  return Math.round(Math.min(bruto, Math.max(total - 1, 0)) * 100) / 100;
}

export const dinheiro = (valor) =>
  Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
