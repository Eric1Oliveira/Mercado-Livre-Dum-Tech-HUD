// A conta de um kit: quanto sairia avulso, quanto custa no kit, quanto economiza.
//
// Modulo puro (sem DOM, sem rede) - testado em painel/tests/kits.test.mjs.
//
// A regra que importa: a loja SO aplica um kit quando ele sai mais barato que os
// mesmos modulos avulsos. Kit com preco igual ou maior nunca e usado - foi o que
// aconteceu com o "Gestao" a R$ 699 contra R$ 199,60 avulsos. Por isso o painel
// avisa, em vez de deixar salvar calado.

const centavos = (valor) => Math.round(Number(valor || 0) * 100);
const reais = (c) => c / 100;

/** Soma dos precos avulsos dos modulos escolhidos (ids de produto). */
export function somaAvulsa(produtos, ids) {
  const escolhidos = new Set(ids);
  return reais(produtos
    .filter((p) => escolhidos.has(p.id))
    .reduce((soma, p) => soma + centavos(p.preco), 0));
}

/** Preco a partir de um desconto em %, arredondado para terminar em ,90. */
export function precoComDesconto(soma, porcento) {
  const bruto = centavos(soma) * (1 - Math.min(Math.max(Number(porcento) || 0, 0), 95) / 100);
  if (bruto <= 0) return 0;
  // R$ 179,64 vira R$ 178,90: final ,90 de vitrine, e nunca acima do desconto pedido
  const cheio = Math.floor(bruto / 100) * 100 + 90;
  return reais(cheio <= bruto ? cheio : Math.max(cheio - 100, 90));
}

/** Tudo o que a tela mostra sobre um kit. */
export function avaliar(produtos, ids, preco) {
  const soma = somaAvulsa(produtos, ids);
  const economia = reais(Math.max(centavos(soma) - centavos(preco), 0));
  const porcento = soma > 0 ? Math.round((economia / soma) * 100) : 0;

  let problema = "";
  if (ids.length < 2) problema = "Um kit precisa de pelo menos dois módulos.";
  else if (centavos(preco) <= 0) problema = "Dê um preço ao kit.";
  else if (centavos(preco) >= centavos(soma)) {
    problema = "Este kit custa o mesmo ou mais que os módulos avulsos — a loja nunca vai aplicá-lo.";
  }
  return { soma, preco: Number(preco) || 0, economia, porcento, problema };
}

/** Codigo a partir do nome: "Kit Comércio" -> "KIT_COMERCIO". */
export function codigoDoNome(nome) {
  return String(nome || "")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_+|_+$/g, "")
    .replace(/^(?=[0-9])/, "K_")
    .slice(0, 40);
}
