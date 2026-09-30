// Edge Function `checkout`: pagamento direto da loja pela InfinitePay.
//
//   POST /functions/v1/checkout/criar    o site, com o pedido recem-gravado -> link de pagamento
//   POST /functions/v1/checkout/webhook  a InfinitePay avisando que foi pago
//   POST /functions/v1/checkout/status   a pagina /pedido/ perguntando (com o segredo)
//
// O aviso da InfinitePay nao e assinado: nenhuma licenca sai dele. A funcao
// pergunta de novo a InfinitePay (payment_check) e so entao o banco entrega.
//
// SEGREDOS (Supabase > Edge Functions > Secrets) - todos opcionais
//   INFINITEPAY_HANDLE   InfiniteTag sem o $ (padrao: dumtechsolutions)
//   DUMTECH_SITE_URL     endereco da loja (padrao: https://dumtechsolution.com)
//   BREVO_API_KEY / RESEND_API_KEY + DUMTECH_EMAIL_REMETENTE: a chave vai por
//                        e-mail na confirmacao do pagamento (ver enviar-chave/correio.ts)
//   SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY ja vem de fabrica
//
// PUBLICAR: supabase functions deploy checkout --no-verify-jwt
//   (sem verificacao de JWT: a InfinitePay nao manda token)

import { type Correio, configurado, enviar } from "../enviar-chave/correio.ts";
import { type Ambiente, cabecalhosCors, criar, rotaDe, status, webhook } from "./nucleo.ts";

const URL_PROJETO = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICO = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const SITE = (Deno.env.get("DUMTECH_SITE_URL") ?? "https://dumtechsolution.com").replace(/\/+$/, "");

const CORREIO: Correio = {
  brevo: Deno.env.get("BREVO_API_KEY") ?? "",
  resend: Deno.env.get("RESEND_API_KEY") ?? "",
  remetente: Deno.env.get("DUMTECH_EMAIL_REMETENTE") ?? "",
  responder: Deno.env.get("DUMTECH_EMAIL_RESPONDER") ?? "",
};

const ambiente: Ambiente = {
  // a chave vai por e-mail sozinha quando o pagamento e confirmado
  enviarEmail: configurado(CORREIO) ? (carta) => enviar(CORREIO, carta) : undefined,
  handle: (Deno.env.get("INFINITEPAY_HANDLE") ?? "dumtechsolutions").replace(/^\$/, ""),
  site: SITE,
  webhook: `${URL_PROJETO}/functions/v1/checkout/webhook`,
  buscar: (url, init) => fetch(url, { ...init, signal: AbortSignal.timeout(12_000) }),
  rpc: async (funcao, parametros) => {
    const resposta = await fetch(`${URL_PROJETO}/rest/v1/rpc/${funcao}`, {
      method: "POST",
      headers: { apikey: SERVICO, Authorization: `Bearer ${SERVICO}`, "Content-Type": "application/json" },
      body: JSON.stringify(parametros),
      signal: AbortSignal.timeout(12_000),
    });
    if (!resposta.ok) {
      console.error("rpc", funcao, resposta.status, (await resposta.text()).slice(0, 300));
      return null;
    }
    return resposta.json();
  },
};

Deno.serve(async (pedido) => {
  const rota = rotaDe(new URL(pedido.url).pathname);
  const cors = rota === "webhook" ? {} : cabecalhosCors(SITE, pedido.headers.get("origin"));
  const responder = (codigo: number, corpo: unknown) =>
    new Response(JSON.stringify(corpo), {
      status: codigo,
      headers: { ...cors, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });

  if (pedido.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (pedido.method !== "POST" || !rota) return responder(404, { ok: false, erro: "rota" });

  let corpo: Record<string, unknown>;
  try {
    corpo = await pedido.json();
    if (!corpo || typeof corpo !== "object" || Array.isArray(corpo)) throw new Error("corpo");
  } catch {
    return responder(400, { ok: false, erro: "pedido_invalido" });
  }

  try {
    const acao = rota === "criar" ? criar : rota === "webhook" ? webhook : status;
    const resultado = await acao(ambiente, corpo);
    return responder(resultado.status, resultado.corpo);
  } catch (erro) {
    console.error("checkout", rota, erro);
    // webhook com erro nosso: 400 faz a InfinitePay tentar de novo
    return responder(rota === "webhook" ? 400 : 500, { ok: false, erro: "interno",
      mensagem: "Não foi possível falar com o pagamento agora. Tente de novo em instantes." });
  }
});
