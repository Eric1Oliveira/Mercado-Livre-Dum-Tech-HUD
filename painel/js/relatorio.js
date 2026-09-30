// As contas do relatorio de vendas: por kit e por cupom.
//
// Modulo puro (sem DOM, sem rede) - testado em painel/tests/relatorio.test.mjs.
//
// De onde vem: `pedidos_site`. Cada pedido criado e uma INTENCAO (a pessoa
// chegou ate o pagamento); pago e uma VENDA. A conversao e pagos / criados -
// e o numero que responde "que desconto converte": um kit com muita
// intencao e pouca venda esta caro, ou esta atraindo quem nao ia comprar.

const centavos = (v) => Math.round(Number(v || 0) * 100);

/** O kit do pedido, ou "AVULSO" quando ele foi montado modulo a modulo. */
export function grupoDoPedido(pedido) {
  const itens = Array.isArray(pedido?.itens) ? pedido.itens : [];
  const combo = itens.find((i) => i?.tipo === "combo");
  return combo ? String(combo.codigo) : "AVULSO";
}

function somar(mapa, chave, pedido) {
  const linha = mapa.get(chave) ?? { chave, pedidos: 0, pagos: 0, receitaCentavos: 0, descontoCentavos: 0 };
  linha.pedidos += 1;
  if (pedido.pagamento === "pago") {
    linha.pagos += 1;
    linha.receitaCentavos += centavos(pedido.pago_valor ?? pedido.total);
    linha.descontoCentavos += centavos(pedido.desconto);
  }
  mapa.set(chave, linha);
}

function fechar(linha) {
  return {
    chave: linha.chave,
    pedidos: linha.pedidos,
    pagos: linha.pagos,
    conversao: linha.pedidos ? Math.round((linha.pagos / linha.pedidos) * 100) : 0,
    receita: linha.receitaCentavos / 100,
    ticket: linha.pagos ? Math.round(linha.receitaCentavos / linha.pagos) / 100 : 0,
    desconto: linha.descontoCentavos / 100,
  };
}

/** Uma linha por kit (e uma "AVULSO"), da que mais fatura para a que menos. */
export function porKit(pedidos) {
  const mapa = new Map();
  for (const pedido of pedidos ?? []) somar(mapa, grupoDoPedido(pedido), pedido);
  return [...mapa.values()].map(fechar)
    .sort((a, b) => b.receita - a.receita || b.pedidos - a.pedidos);
}

/** Uma linha por cupom usado (pedidos sem cupom ficam de fora). */
export function porCupom(pedidos) {
  const mapa = new Map();
  for (const pedido of pedidos ?? []) {
    const codigo = String(pedido?.cupom || "").trim();
    if (codigo) somar(mapa, codigo, pedido);
  }
  return [...mapa.values()].map(fechar)
    .sort((a, b) => b.pagos - a.pagos || b.receita - a.receita);
}

/** O total do periodo, para os cartoes do topo. */
export function totais(pedidos) {
  const mapa = new Map();
  for (const pedido of pedidos ?? []) somar(mapa, "TOTAL", pedido);
  return fechar(mapa.get("TOTAL") ?? { chave: "TOTAL", pedidos: 0, pagos: 0, receitaCentavos: 0, descontoCentavos: 0 });
}

/** A data de corte (AAAA-MM-DD) para "ultimos N dias"; 0 = tudo. */
export function desde(dias, hoje = new Date()) {
  if (!dias) return "";
  const d = new Date(hoje.getTime() - dias * 86400000);
  return d.toISOString().slice(0, 10);
}
