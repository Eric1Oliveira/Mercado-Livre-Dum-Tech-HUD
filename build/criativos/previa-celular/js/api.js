// Conversa com o servidor da DumTech (as mesmas funcoes que o Hub usa, e a
// funcao de checkout que fala com a InfinitePay).
//
// A pagina NUNCA le tabela: a chave anon so executa funcoes. Se o servidor nao
// responder, o site continua de pe com o catalogo local - ninguem chega numa
// pagina quebrada porque o banco piscou.

import { CONFIG } from "./config.js";
import { catalogoLocal } from "./dados.js";
import { enderecoDasFuncoes } from "./pagamento.js";

async function rpc(funcao, params = {}) {
  const resposta = await fetch(`${CONFIG.SUPABASE_URL}/rpc/${funcao}`, {
    method: "POST",
    headers: {
      apikey: CONFIG.SUPABASE_ANON,
      Authorization: `Bearer ${CONFIG.SUPABASE_ANON}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(params),
  });
  if (!resposta.ok) {
    throw new Error(`${funcao}: HTTP ${resposta.status}`);
  }
  return resposta.json();
}

/** O catalogo a venda. Cai para o local quando o servidor nao responde. */
export async function carregarCatalogo() {
  try {
    const dados = await rpc("dumtech_catalogo");
    if (!dados?.ok || !dados.produtos?.length) throw new Error("catalogo vazio");
    return {
      produtos: dados.produtos.map((p) => ({ ...p, preco: Number(p.preco) })),
      combos: (dados.combos ?? []).map((c) => ({ ...c, preco: Number(c.preco) })),
      local: false,
    };
  } catch (erro) {
    console.warn("Catalogo do servidor indisponivel; usando o local.", erro);
    return catalogoLocal();
  }
}

/**
 * Reconhece quem chegou pelo Hub: o codigo da URL (?t=) vale 15 minutos, e de
 * uso unico, e devolve nome, e-mail e o que a pessoa ja comprou.
 */
export async function reconhecer(token) {
  if (!token) return null;
  try {
    const dados = await rpc("dumtech_abrir_compra", { p_token: token });
    if (!dados?.ok) return null;
    return {
      nome: dados.nome || "",
      email: dados.email || "",
      produtos: (dados.produtos || []).map((c) => String(c).toUpperCase()),
    };
  } catch (erro) {
    console.warn("Nao foi possivel reconhecer o codigo do Hub.", erro);
    return null;
  }
}

/** Grava o kit montado. O total volta calculado pelo banco (com o cupom, se houver). */
export async function registrarPedido({ nome, email, telefone, produtos, combo, origem, observacoes, cupom }) {
  return rpc("dumtech_registrar_pedido", {
    p_nome: nome,
    p_email: email,
    p_telefone: telefone || "",
    p_produtos: produtos ?? [],
    p_combo: combo ?? null,
    p_origem: origem || "site",
    p_observacoes: observacoes || "",
    p_cupom: cupom || null,
  });
}

/** Previa do cupom: {ok, codigo, tipo, valor, descricao, desconto} ou {ok:false, mensagem}. */
export async function conferirCupom(codigo, email, total) {
  try {
    return await rpc("dumtech_conferir_cupom", { p_codigo: codigo, p_email: email || "", p_total: total || 0 });
  } catch (erro) {
    console.warn("Cupom nao conferido.", erro);
    return { ok: false, mensagem: "Não conseguimos conferir o cupom agora. Tente de novo." };
  }
}

/** Cupom que chegou pelo link: ?cupom=PARCEIRO20 (so letras, numeros, - e _). */
export function cupomDaURL() {
  const bruto = new URLSearchParams(location.search).get("cupom") || "";
  return /^[A-Za-z0-9][A-Za-z0-9_-]{1,30}$/.test(bruto) ? bruto.toUpperCase() : "";
}

/**
 * Funcao `checkout` (Edge Function): o link de pagamento de um pedido recem-
 * gravado, e o que a pagina do pedido mostra. Erro vira {ok:false, mensagem}.
 */
async function checkout(rota, corpo) {
  try {
    const resposta = await fetch(`${enderecoDasFuncoes(CONFIG.SUPABASE_URL)}/checkout/${rota}`, {
      method: "POST",
      headers: {
        apikey: CONFIG.SUPABASE_ANON,
        Authorization: `Bearer ${CONFIG.SUPABASE_ANON}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(corpo),
    });
    const dados = await resposta.json().catch(() => null);
    return dados ?? { ok: false, erro: `http_${resposta.status}` };
  } catch (erro) {
    console.warn(`checkout/${rota} indisponivel.`, erro);
    return { ok: false, erro: "rede" };
  }
}

/** {ok, url, segredo}: o endereco da InfinitePay e o segredo que abre o pedido. */
export function abrirPagamento(pedido) {
  return checkout("criar", { pedido });
}

/** {ok, pagamento, entregue, chave?, final_chave, itens, total, ...} */
export function situacaoDoPedido({ pedido, segredo, transacao = "", fatura = "" }) {
  return checkout("status", { pedido, segredo, transacao, fatura });
}

/** Quem chegou pelo Hub traz o codigo na URL. */
export function tokenDaURL() {
  return new URLSearchParams(location.search).get("t") || "";
}

/** Sem token, o Hub ainda diz o que a pessoa ja tem: ?tem=estoque,vendas */
export function jaTemDaURL() {
  return codigosDaURL("tem");
}

/** Um kit ja montado: ?kit=estoque,vendas - da para compartilhar o link. */
export function kitDaURL() {
  return codigosDaURL("kit");
}

function codigosDaURL(nome) {
  const bruto = new URLSearchParams(location.search).get(nome) || "";
  // so o que tem cara de codigo de modulo: qualquer outra coisa vinda da URL
  // e texto de um estranho, e nunca pode chegar ate a tela
  return bruto.split(",").map((c) => c.trim().toUpperCase())
    .filter((c) => /^[A-Z][A-Z0-9_]{0,31}$/.test(c));
}
