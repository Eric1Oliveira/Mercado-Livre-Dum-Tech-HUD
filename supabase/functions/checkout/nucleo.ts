// Checkout direto na InfinitePay: montar o link, ler o aviso, conferir o
// pagamento e o fluxo das tres rotas (sem Deno: rede e banco entram por
// parametro). Testado em supabase/functions/tests/checkout.test.mjs.
//
// API (https://www.infinitepay.io/checkout-documentacao)
//   POST /links          {handle, items[{description, quantity, price(centavos)}],
//                         order_nsu, redirect_url, webhook_url, customer} -> {url}
//   POST /payment_check  {handle, order_nsu, transaction_nsu, slug}
//                        -> {success, paid, amount, paid_amount, installments, capture_method}
//   webhook              {invoice_slug, amount, paid_amount, capture_method,
//                         transaction_nsu, order_nsu, receipt_url, items}

import { emailValido, montarEmail } from "../enviar-chave/nucleo.ts";

export const API_INFINITEPAY = "https://api.checkout.infinitepay.io";

type Buscar = (url: string, init?: RequestInit) => Promise<Response>;
type Rpc = (funcao: string, parametros: Record<string, unknown>) => Promise<any>;

export type Ambiente = {
  handle: string;
  site: string;          // https://dumtechsolution.com (sem barra no fim)
  webhook: string;       // .../functions/v1/checkout/webhook
  buscar: Buscar;        // fetch para a InfinitePay
  rpc: Rpc;              // funcoes do banco, com service_role
  // manda um e-mail (Brevo/Resend); ausente = e-mail nao configurado
  enviarEmail?: (carta: { para: string; assunto: string; texto: string; html: string }) => Promise<boolean>;
};

type Resposta = { status: number; corpo: Record<string, unknown> };

// ---------------------------------------------------------------- formatos --
export function uuidValido(texto: unknown): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(texto ?? ""));
}

export function segredoValido(texto: unknown): boolean {
  return /^[A-Za-z0-9_-]{40,64}$/.test(String(texto ?? ""));
}

/** Codigos que a InfinitePay devolve: letras, numeros, hifen, sublinhado. */
function codigoExterno(texto: unknown, maximo = 100): string {
  const valor = String(texto ?? "").trim();
  return /^[A-Za-z0-9_.:-]+$/.test(valor) ? valor.slice(0, maximo) : "";
}

export function novoSegredo(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function hashSegredo(segredo: string): Promise<string> {
  const resumo = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(segredo));
  return [...new Uint8Array(resumo)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** +55DDDNUMERO, ou vazio (a InfinitePay recusa telefone torto: melhor nao mandar). */
export function telefoneInternacional(texto: unknown): string {
  let digitos = String(texto ?? "").replace(/\D/g, "");
  if (digitos.length === 12 || digitos.length === 13) {
    if (!digitos.startsWith("55")) return "";
    digitos = digitos.slice(2);
  }
  return digitos.length === 10 || digitos.length === 11 ? `+55${digitos}` : "";
}

export function cabecalhosCors(permitida: string, origem: string | null): Record<string, string> {
  const locais = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/;
  const aceita = origem && (origem === permitida || locais.test(origem)) ? origem : permitida;
  return {
    "Access-Control-Allow-Origin": aceita,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

// ------------------------------------------------------------------ link ----
type PedidoPreparado = {
  pedido: string;
  nome: string;
  email: string;
  telefone: string;
  itens: { nome?: string; preco?: number | string }[];
  total_centavos: number;
};

/** O corpo do POST /links. Precos saem do pedido gravado pelo banco. */
export function montarLink(dados: PedidoPreparado, ambiente: Pick<Ambiente, "handle" | "site" | "webhook">, segredo: string) {
  let items = dados.itens.map((item) => ({
    description: String(item.nome ?? "Módulo DumTech").slice(0, 120),
    quantity: 1,
    price: Math.round(Number(item.preco) * 100),
  }));
  const soma = items.reduce((total, item) => total + item.price, 0);
  // qualquer diferenca de arredondamento: um item so, com o total do banco
  if (!items.length || soma !== dados.total_centavos || items.some((i) => !(i.price > 0))) {
    items = [{ description: "Kit DumTech Hub", quantity: 1, price: dados.total_centavos }];
  }

  const customer: Record<string, string> = {};
  if (dados.nome) customer.name = dados.nome.slice(0, 120);
  if (dados.email) customer.email = dados.email;
  const telefone = telefoneInternacional(dados.telefone);
  if (telefone) customer.phone_number = telefone;

  return {
    handle: ambiente.handle,
    items,
    order_nsu: dados.pedido,
    // o segredo vai na volta: so o navegador de quem pagou abre a chave
    redirect_url: `${ambiente.site}/pedido/?p=${dados.pedido}&s=${segredo}`,
    webhook_url: ambiente.webhook,
    ...(Object.keys(customer).length ? { customer } : {}),
  };
}

// ------------------------------------------------------------- conferir -----
export type Pagamento = { pago: boolean; centavos: number; metodo: string };

/** Pergunta a InfinitePay. So `paid: true` com valor conta. */
export async function conferirPagamento(
  ambiente: Pick<Ambiente, "handle" | "buscar">,
  consulta: { pedido: string; transacao: string; fatura: string },
): Promise<Pagamento> {
  const resposta = await ambiente.buscar(`${API_INFINITEPAY}/payment_check`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      handle: ambiente.handle,
      order_nsu: consulta.pedido,
      transaction_nsu: consulta.transacao,
      slug: consulta.fatura,
    }),
  });
  if (!resposta.ok) return { pago: false, centavos: 0, metodo: "" };
  const dados = await resposta.json().catch(() => null);
  // `amount` e o valor do link (o que o pedido custa); `paid_amount` inclui juros
  // do parcelado. Sem `amount`, vale o pago.
  const centavos = Number.isInteger(dados?.amount) ? dados.amount
    : Number.isInteger(dados?.paid_amount) ? dados.paid_amount : 0;
  const pago = dados?.success === true && dados?.paid === true && centavos > 0;
  return { pago, centavos: pago ? centavos : 0, metodo: codigoExterno(dados?.capture_method, 20) };
}

// ---------------------------------------------------------------- rotas -----
export function rotaDe(caminho: string): "criar" | "webhook" | "status" | "" {
  const fim = caminho.replace(/\/+$/, "").split("/").pop() ?? "";
  return fim === "criar" || fim === "webhook" || fim === "status" ? fim : "";
}

const MENSAGENS: Record<string, string> = {
  pedido_nao_existe: "Não encontramos este pedido. Monte o kit de novo.",
  pedido_invalido: "Este pedido não pode ser pago pelo site.",
  pedido_encerrado: "Este pedido já foi pago.",
  checkout_ja_criado: "O pagamento deste pedido já foi aberto. Monte o kit de novo para gerar outro.",
  pedido_expirado: "O pedido expirou. Monte o kit de novo.",
};

/** POST /criar {pedido} -> {ok, url, segredo} */
export async function criar(ambiente: Ambiente, corpo: Record<string, unknown>): Promise<Resposta> {
  if (!uuidValido(corpo.pedido)) return { status: 400, corpo: { ok: false, erro: "pedido_invalido" } };

  const preparado = await ambiente.rpc("dumtech_checkout_preparar", { p_pedido: corpo.pedido });
  if (!preparado?.ok) {
    const erro = String(preparado?.erro ?? "falha");
    return { status: 409, corpo: { ok: false, erro, mensagem: MENSAGENS[erro] ?? "Não foi possível abrir o pagamento." } };
  }

  const segredo = novoSegredo();
  const link = await ambiente.buscar(`${API_INFINITEPAY}/links`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(montarLink(preparado, ambiente, segredo)),
  });
  const dados = link.ok ? await link.json().catch(() => null) : null;
  const url = String(dados?.url ?? "");
  if (!/^https:\/\//.test(url)) {
    console.error("infinitepay /links", link.status, dados ? JSON.stringify(dados).slice(0, 300) : await link.text().catch(() => ""));
    return { status: 502, corpo: { ok: false, erro: "gateway",
      mensagem: "A InfinitePay não respondeu agora. Tente de novo em instantes." } };
  }

  const registro = await ambiente.rpc("dumtech_checkout_registrar", {
    p_pedido: corpo.pedido, p_segredo_hash: await hashSegredo(segredo), p_url: url,
  });
  if (!registro?.ok) {
    const erro = String(registro?.erro ?? "falha");
    return { status: 409, corpo: { ok: false, erro, mensagem: MENSAGENS[erro] ?? "Não foi possível abrir o pagamento." } };
  }
  return { status: 200, corpo: { ok: true, url, segredo } };
}

/** Webhook da InfinitePay. 200 = recebido (nao repete); 400 = repete depois. */
export async function webhook(ambiente: Ambiente, corpo: Record<string, unknown>): Promise<Resposta> {
  const pedido = String(corpo.order_nsu ?? "");
  const transacao = codigoExterno(corpo.transaction_nsu);
  const fatura = codigoExterno(corpo.invoice_slug ?? corpo.slug);
  // aviso que nao e de pedido nosso: nada a fazer, e nao adianta repetir
  if (!uuidValido(pedido) || !transacao) return { status: 200, corpo: { ok: false, ignorado: true } };

  const pagamento = await conferirPagamento(ambiente, { pedido, transacao, fatura });
  if (!pagamento.pago) return { status: 400, corpo: { ok: false, erro: "nao_confirmado" } };

  const recibo = String(corpo.receipt_url ?? "");
  const confirmacao = await ambiente.rpc("dumtech_checkout_confirmar", {
    p_pedido: pedido,
    p_centavos: pagamento.centavos,
    p_transacao: transacao,
    p_fatura: fatura,
    p_metodo: pagamento.metodo,
    p_recibo: /^https:\/\//.test(recibo) ? recibo : "",
  });
  if (confirmacao?.ok) {
    await mandarChave(ambiente, pedido);
    return { status: 200, corpo: { ok: true } };
  }
  // pedido que nao e pago por aqui: registrar no log e nao pedir repeticao
  console.error("checkout confirmar", pedido, JSON.stringify(confirmacao));
  return { status: 200, corpo: { ok: false, erro: confirmacao?.erro ?? "falha" } };
}

/** POST /status {pedido, segredo, transacao?, fatura?} -> o que a pagina mostra. */
export async function status(ambiente: Ambiente, corpo: Record<string, unknown>): Promise<Resposta> {
  if (!uuidValido(corpo.pedido) || !segredoValido(corpo.segredo)) {
    return { status: 404, corpo: { ok: false, erro: "nao_encontrado" } };
  }
  const hash = await hashSegredo(String(corpo.segredo));
  const perguntar = () => ambiente.rpc("dumtech_checkout_situacao", { p_pedido: corpo.pedido, p_segredo_hash: hash });

  let situacao = await perguntar();
  if (!situacao?.ok) return { status: 404, corpo: { ok: false, erro: "nao_encontrado" } };

  // voltou da InfinitePay antes do webhook chegar: confere e confirma daqui
  const transacao = codigoExterno(corpo.transacao);
  const fatura = codigoExterno(corpo.fatura);
  if (situacao.pagamento === "aguardando" && transacao) {
    const pagamento = await conferirPagamento(ambiente, { pedido: String(corpo.pedido), transacao, fatura });
    if (pagamento.pago) {
      await ambiente.rpc("dumtech_checkout_confirmar", {
        p_pedido: corpo.pedido, p_centavos: pagamento.centavos, p_transacao: transacao,
        p_fatura: fatura, p_metodo: pagamento.metodo, p_recibo: "",
      });
      situacao = await perguntar();
    }
  }
  // a pagina do pedido pergunta varias vezes: e aqui que um envio que falhou
  // (ou um pedido pago antes desta versao) ganha outra chance. A reserva no
  // banco garante que ninguem recebe o mesmo e-mail duas vezes.
  if (situacao?.entregue) await mandarChave(ambiente, String(corpo.pedido));
  return { status: 200, corpo: situacao };
}

/**
 * A chave vai por e-mail assim que o pedido esta pago e entregue.
 *
 * Nunca derruba a resposta: o cliente ja ve a chave na tela; o e-mail e a
 * copia que sobrevive a aba fechada. Devolve se mandou agora.
 */
export async function mandarChave(ambiente: Ambiente, pedido: string): Promise<boolean> {
  if (!ambiente.enviarEmail) return false;
  try {
    const dados = await ambiente.rpc("dumtech_checkout_reservar_email", { p_pedido: pedido });
    if (!dados?.ok) return false;            // ja foi, ou outro caminho esta mandando
    let mandou = false;
    if (emailValido(dados.email) && dados.chave) {
      const carta = montarEmail(dados);
      mandou = await ambiente.enviarEmail({ para: String(dados.email), assunto: carta.assunto,
                                            texto: carta.texto, html: carta.html });
    }
    await ambiente.rpc("dumtech_checkout_email_resultado", { p_pedido: pedido, p_enviado: mandou });
    return mandou;
  } catch (erro) {
    console.error("chave por e-mail", pedido, erro);
    return false;
  }
}
