// Pagina propria de um kit (/kit/<nome>/, gerada por tools/paginas_de_kit.mjs).
//
// O HTML ja chega com nome e preco escritos (a previa do WhatsApp nao roda
// JavaScript). Aqui so duas coisas:
//   1. o cupom do link (?cupom=PRIMEIRA10) segue para a loja no "Quero este kit";
//   2. o preco e conferido com o servidor - kit reajustado no painel depois da
//      publicacao nao mostra valor velho.

import { CONFIG } from "./config.js";

const pagina = document.querySelector("main[data-kit]");
const comprar = document.getElementById("kp-comprar");

const cupom = new URLSearchParams(location.search).get("cupom");
if (cupom && /^[A-Za-z0-9_-]{2,30}$/.test(cupom) && comprar) {
  const destino = new URL(comprar.getAttribute("href"), location.href);
  destino.searchParams.set("cupom", cupom.toUpperCase());
  comprar.href = destino.toString();
}

const moeda = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

try {
  const r = await fetch(`${CONFIG.SUPABASE_URL}/rpc/dumtech_catalogo`, {
    method: "POST",
    headers: { apikey: CONFIG.SUPABASE_ANON, Authorization: `Bearer ${CONFIG.SUPABASE_ANON}`, "Content-Type": "application/json" },
    body: "{}",
  });
  const dados = await r.json();
  const kit = dados?.combos?.find((c) => c.codigo === pagina.dataset.kit);
  if (!kit) {
    // saiu de linha no painel: a pagina fica, mas leva para a loja
    comprar.textContent = "Ver os kits disponíveis";
    comprar.href = "../../#kits-prontos";
  } else if (Number(kit.preco) !== Number(pagina.dataset.preco)) {
    document.getElementById("kp-preco").textContent = moeda(Number(kit.preco));
    const precos = Object.fromEntries(dados.produtos.map((p) => [p.codigo, Number(p.preco)]));
    const avulso = kit.produtos.reduce((s, c) => s + (precos[c] || 0), 0);
    const economia = Math.round((avulso - Number(kit.preco)) * 100) / 100;
    const caixa = document.getElementById("kp-economia");
    if (caixa) caixa.hidden = economia <= 0;
    if (caixa && economia > 0) caixa.querySelector("b").textContent = moeda(economia);
  }
} catch {
  // sem servidor: vale o preco escrito na pagina (o da publicacao)
}
