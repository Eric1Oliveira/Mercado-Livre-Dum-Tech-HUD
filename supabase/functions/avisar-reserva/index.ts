// Edge Function `avisar-reserva`: conta ao dono que alguem marcou pelo link.
//
// Quem chama e a pagina de agendamento, logo depois de marcar. A funcao nao
// aceita destinatario nem texto de fora: recebe so o id da reserva, e quem decide
// para quem vai e o banco (`dumtech_agenda_aviso`), que marca a reserva como
// avisada na mesma hora. Por isso chamar de novo nao manda outro e-mail, e um id
// antigo nao manda nada. A resposta e sempre a mesma: quem chama nao descobre
// nada sobre a empresa.
//
// SEGREDOS (Supabase > Edge Functions > Secrets)
//   BREVO_API_KEY ou RESEND_API_KEY   quem entrega o e-mail (ver correio.ts)
//   DUMTECH_EMAIL_REMETENTE           ex.: DumTech <dumtechsolutions@gmail.com>
//   DUMTECH_SITE_URL                  a origem da pagina de agendamento
//   SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY ja vem de fabrica
//
// PUBLICAR: supabase functions deploy avisar-reserva --no-verify-jwt
//   (a pagina e publica: quem protege e a trava de uma vez por reserva)

import { type Correio, configurado, enviar } from "../enviar-chave/correio.ts";
import { cabecalhosCors } from "../enviar-chave/nucleo.ts";
import { montarAviso, uuidValido } from "./nucleo.ts";

const URL_PROJETO = Deno.env.get("SUPABASE_URL") ?? "";
const CHAVE_SERVICO = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const ORIGEM = Deno.env.get("DUMTECH_SITE_URL") ?? "*";
const CORREIO: Correio = {
  brevo: Deno.env.get("BREVO_API_KEY") ?? "",
  resend: Deno.env.get("RESEND_API_KEY") ?? "",
  remetente: Deno.env.get("DUMTECH_EMAIL_REMETENTE") ?? "",
  responder: Deno.env.get("DUMTECH_EMAIL_RESPONDER") ?? "",
};

Deno.serve(async (pedido) => {
  const cors = cabecalhosCors(ORIGEM, pedido.headers.get("origin"));
  const responder = (status: number) =>
    new Response(JSON.stringify({ ok: status < 400 }), {
      status,
      headers: { ...cors, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });

  if (pedido.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (pedido.method !== "POST") return responder(405);
  if (!configurado(CORREIO)) return responder(200);

  let corpo: Record<string, unknown>;
  try {
    corpo = await pedido.json();
  } catch {
    return responder(400);
  }
  if (!uuidValido(corpo?.reserva)) return responder(400);

  const resposta = await fetch(`${URL_PROJETO}/rest/v1/rpc/dumtech_agenda_aviso`, {
    method: "POST",
    headers: {
      apikey: CHAVE_SERVICO,
      Authorization: `Bearer ${CHAVE_SERVICO}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ p_reserva: corpo.reserva }),
  });
  if (!resposta.ok) {
    console.error("avisar-reserva: o banco recusou", resposta.status);
    return responder(200);
  }

  const dados = await resposta.json();
  if (dados?.ok) {
    await enviar(CORREIO, { para: dados.email, ...montarAviso(dados) });
  }
  return responder(200);
});
