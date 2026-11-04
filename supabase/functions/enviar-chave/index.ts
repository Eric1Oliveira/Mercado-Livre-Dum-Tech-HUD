// Edge Function `enviar-chave`: manda por e-mail a chave de uma licenca.
//
// Quem chama e o PAINEL, com o token do administrador. A funcao nao aceita
// destinatario nem texto de fora: busca os dados com o PROPRIO token de quem
// chamou (dumtech_dados_da_chave obedece as policies - so admin com 2 fatores
// recebe algo). Assim ela nao vira um disparador de e-mail para qualquer um.
//
// SEGREDOS (Supabase > Edge Functions > Secrets)
//   BREVO_API_KEY ou RESEND_API_KEY   quem entrega o e-mail (ver correio.ts)
//   DUMTECH_EMAIL_REMETENTE           ex.: DumTech <dumtechsolutions@gmail.com>
//   DUMTECH_EMAIL_RESPONDER           opcional: para onde vai a resposta do cliente
//   DUMTECH_PAINEL_ORIGEM       opcional: ex. https://painel.seudominio.com.br
//   SUPABASE_URL / SUPABASE_ANON_KEY ja vem de fabrica
//
// PUBLICAR: supabase functions deploy enviar-chave
//   (COM verificacao de JWT: so quem esta logado chega aqui)

import { type Correio, configurado, enviar } from "./correio.ts";
import { cabecalhosCors, emailValido, montarEmail, uuidValido } from "./nucleo.ts";

const URL_PROJETO = Deno.env.get("SUPABASE_URL") ?? "";
const ANON = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
const CORREIO: Correio = {
  brevo: Deno.env.get("BREVO_API_KEY") ?? "",
  resend: Deno.env.get("RESEND_API_KEY") ?? "",
  remetente: Deno.env.get("DUMTECH_EMAIL_REMETENTE") ?? "",
  responder: Deno.env.get("DUMTECH_EMAIL_RESPONDER") ?? "",
};
const ORIGEM = Deno.env.get("DUMTECH_PAINEL_ORIGEM") ?? "*";

Deno.serve(async (pedido) => {
  const cors = cabecalhosCors(ORIGEM, pedido.headers.get("origin"));
  const responder = (status: number, corpo: unknown) =>
    new Response(JSON.stringify(corpo), {
      status,
      headers: { ...cors, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });

  if (pedido.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (pedido.method !== "POST") return responder(405, { ok: false, erro: "metodo" });

  if (!configurado(CORREIO)) {
    return responder(501, { ok: false, erro: "nao_configurado",
                            mensagem: "Falta BREVO_API_KEY (ou RESEND_API_KEY) ou DUMTECH_EMAIL_REMETENTE." });
  }

  const autorizacao = pedido.headers.get("authorization") ?? "";
  if (!autorizacao.startsWith("Bearer ")) return responder(401, { ok: false, erro: "sem_sessao" });

  let corpo: Record<string, unknown>;
  try {
    corpo = await pedido.json();
  } catch {
    return responder(400, { ok: false, erro: "pedido_invalido" });
  }
  if (!uuidValido(corpo.licenca_id)) return responder(400, { ok: false, erro: "pedido_invalido" });

  // com o token de QUEM CHAMOU: a policy decide se ele pode ver esta licenca
  const consulta = await fetch(`${URL_PROJETO}/rest/v1/rpc/dumtech_dados_da_chave`, {
    method: "POST",
    headers: { apikey: ANON, Authorization: autorizacao, "Content-Type": "application/json" },
    body: JSON.stringify({ p_licenca_id: corpo.licenca_id }),
  });
  const dados = consulta.ok ? await consulta.json() : null;
  if (!dados?.ok) {
    return responder(403, { ok: false, erro: "sem_acesso", mensagem: "Sem acesso a esta licenca." });
  }
  if (!emailValido(dados.email)) {
    return responder(422, { ok: false, erro: "sem_email", mensagem: "O cliente nao tem e-mail valido." });
  }

  const email = montarEmail(dados);
  const entregue = await enviar(CORREIO, { para: dados.email, assunto: email.assunto,
                                           texto: email.texto, html: email.html });
  if (!entregue) {
    return responder(502, { ok: false, erro: "falha_no_envio",
                            mensagem: "O servico de e-mail recusou o envio. Tente de novo em instantes." });
  }
  return responder(200, { ok: true, para: dados.email });
});
