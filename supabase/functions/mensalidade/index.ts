// Edge Function `mensalidade`: o cadastro do site e as acoes do painel.
//
//   POST /functions/v1/mensalidade/cadastro  o site, sem login: teste gratis e
//                                            pedido de assinatura (a chave vai por e-mail)
//   POST /functions/v1/mensalidade/admin     o painel, com o token do administrador:
//                                            confirmar, descartar, falhou, em_dia,
//                                            cancelou, estender
//
// A rota admin nao confia em nada: chama o banco COM O TOKEN de quem chamou, e
// o banco (dumtech_painel_portao) decide se e admin com 2 fatores.
//
// SEGREDOS (Supabase > Edge Functions > Secrets)
//   BREVO_API_KEY ou RESEND_API_KEY + DUMTECH_EMAIL_REMETENTE   (ver enviar-chave/correio.ts)
//   DUMTECH_EMAIL_RESPONDER   opcional: para onde vai a resposta do cliente
//   DUMTECH_SITE_URL          padrao https://dumtechsolution.com
//   DUMTECH_WHATSAPP          padrao 5511978042160
//   DUMTECH_PAINEL_ORIGEM     opcional: restringe quem chama a rota admin (CORS)
//   SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY ja vem de fabrica
//
// PUBLICAR: npx supabase functions deploy mensalidade --no-verify-jwt --use-api
//   (sem verificacao de JWT: o site chama sem login)

import { type Correio, configurado, enviar } from "../enviar-chave/correio.ts";
import { cabecalhosCors } from "../enviar-chave/nucleo.ts";
import { ipDoVisitante } from "../licenca-assinada/nucleo.ts";
import { type Ambiente, type RpcDoChamador, admin, cadastro, rotaDe } from "./nucleo.ts";

const URL_PROJETO = Deno.env.get("SUPABASE_URL") ?? "";
const ANON = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
const SERVICO = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const SITE = (Deno.env.get("DUMTECH_SITE_URL") ?? "https://dumtechsolution.com").replace(/\/+$/, "");
const PAINEL = Deno.env.get("DUMTECH_PAINEL_ORIGEM") ?? "*";

const CORREIO: Correio = {
  brevo: Deno.env.get("BREVO_API_KEY") ?? "",
  resend: Deno.env.get("RESEND_API_KEY") ?? "",
  remetente: Deno.env.get("DUMTECH_EMAIL_REMETENTE") ?? "",
  responder: Deno.env.get("DUMTECH_EMAIL_RESPONDER") ?? "",
};

const ambiente: Ambiente = {
  site: SITE,
  whatsapp: (Deno.env.get("DUMTECH_WHATSAPP") ?? "5511978042160").replace(/\D/g, ""),
  enviarEmail: configurado(CORREIO) ? (carta) => enviar(CORREIO, carta) : undefined,
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

/** O banco com o token de quem chamou: e la que se decide se e admin. */
function rpcComToken(autorizacao: string): RpcDoChamador {
  return async (funcao, parametros) => {
    const resposta = await fetch(`${URL_PROJETO}/rest/v1/rpc/${funcao}`, {
      method: "POST",
      headers: { apikey: ANON, Authorization: autorizacao, "Content-Type": "application/json" },
      body: JSON.stringify(parametros),
      signal: AbortSignal.timeout(12_000),
    });
    const dados = await resposta.json().catch(() => null);
    if (!resposta.ok) console.error("rpc admin", funcao, resposta.status, JSON.stringify(dados).slice(0, 300));
    return { status: resposta.status, dados };
  };
}

/** O site e, em desenvolvimento, a copia servida neste computador. */
function corsDoSite(origem: string | null): Record<string, string> {
  const local = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(origem ?? "");
  return cabecalhosCors(local ? String(origem) : SITE, origem);
}

Deno.serve(async (pedido) => {
  const rota = rotaDe(new URL(pedido.url).pathname);
  const origem = pedido.headers.get("origin");
  const cors = rota === "admin" ? cabecalhosCors(PAINEL, origem) : corsDoSite(origem);
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
    if (rota === "cadastro") {
      const r = await cadastro(ambiente, corpo, ipDoVisitante(pedido.headers));
      return responder(r.status, r.corpo);
    }
    const autorizacao = pedido.headers.get("authorization") ?? "";
    const r = await admin(ambiente, corpo, autorizacao.startsWith("Bearer ") ? rpcComToken(autorizacao) : null);
    return responder(r.status, r.corpo);
  } catch (erro) {
    console.error("mensalidade", rota, erro);
    return responder(500, { ok: false, erro: "interno",
      mensagem: "Não conseguimos concluir agora. Tente de novo em instantes." });
  }
});
