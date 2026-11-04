// Edge Function `pagamentos`: a area de Pagamentos do Hub, protegida por codigo.
//
//   POST /functions/v1/pagamentos/codigo    manda o codigo para o e-mail DA LICENCA
//   POST /functions/v1/pagamentos/entrar    codigo de 6 digitos -> sessao de 15 min + chave Pix assinada
//   POST /functions/v1/pagamentos/salvar    sessao + chave Pix nova -> assinada, e avisa o dono por e-mail
//   POST /functions/v1/pagamentos/atual     conferencia de fundo: a chave Pix de agora, assinada
//
// O Hub chama com a chave anon (como licenca-assinada). Quem decide tudo e o
// banco (migration 20260916120000_pagamentos_protegidos.sql), com o service_role.
//
// SEGREDOS (Supabase > Edge Functions > Secrets)
//   DUMTECH_LICENCA_CHAVE_PRIVADA   a MESMA de licenca-assinada
//   DUMTECH_LICENCA_KID             a MESMA de licenca-assinada (ex.: k1)
//   DUMTECH_EMAIL_REMETENTE         ex.: DumTech <dumtechsolutions@gmail.com>
//   e UM provedor de e-mail (os dois tem plano gratis):
//     BREVO_API_KEY    brevo.com - 300 e-mails/dia gratis; basta confirmar o e-mail remetente
//     RESEND_API_KEY   resend.com - 3.000/mes gratis; exige dominio proprio verificado
//   SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY ja vem de fabrica
//
// PUBLICAR: supabase functions deploy pagamentos --no-verify-jwt
//   (sem verificar JWT: o Hub chama com a chave anon)

import {
  type Ambiente, type Mensagem, assinar, importarChavePrivada, ipDoVisitante, remetente, rotaDe, tratar,
} from "./nucleo.ts";

const URL_PROJETO = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICO = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const PRIVADA = Deno.env.get("DUMTECH_LICENCA_CHAVE_PRIVADA") ?? "";
const KID = Deno.env.get("DUMTECH_LICENCA_KID") ?? "k1";
const REMETENTE = Deno.env.get("DUMTECH_EMAIL_REMETENTE") ?? "";
const BREVO = Deno.env.get("BREVO_API_KEY") ?? "";
const RESEND = Deno.env.get("RESEND_API_KEY") ?? "";

let chavePrivada: Promise<CryptoKey> | null = null;

async function enviarEmail(mensagem: Mensagem): Promise<boolean> {
  const tempo = AbortSignal.timeout(12_000);
  try {
    if (BREVO) {
      const de = remetente(REMETENTE);
      const envio = await fetch("https://api.brevo.com/v3/smtp/email", {
        method: "POST",
        headers: { "api-key": BREVO, "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          sender: { name: de.nome, email: de.email }, to: [{ email: mensagem.para }],
          subject: mensagem.assunto, textContent: mensagem.texto, htmlContent: mensagem.html,
        }),
        signal: tempo,
      });
      if (!envio.ok) console.error("brevo", envio.status, (await envio.text()).slice(0, 300));
      return envio.ok;
    }
    const envio = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${RESEND}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: REMETENTE, to: [mensagem.para], subject: mensagem.assunto, text: mensagem.texto, html: mensagem.html }),
      signal: tempo,
    });
    if (!envio.ok) console.error("resend", envio.status, (await envio.text()).slice(0, 300));
    return envio.ok;
  } catch (erro) {
    console.error("e-mail", erro);
    return false;
  }
}

const ambiente: Ambiente = {
  kid: KID,
  enviarEmail,
  assinar: async (conteudo) => {
    chavePrivada ??= importarChavePrivada(PRIVADA);
    try {
      return await assinar(conteudo, await chavePrivada, KID);
    } catch (erro) {
      chavePrivada = null;
      throw erro;
    }
  },
  rpc: (funcao, parametros) => rpcDireto(funcao, parametros),
};

async function rpcDireto(funcao: string, parametros: Record<string, unknown>) {
  {
    const resposta = await fetch(`${URL_PROJETO}/rest/v1/rpc/${funcao}`, {
      method: "POST",
      headers: { apikey: SERVICO, Authorization: `Bearer ${SERVICO}`, "Content-Type": "application/json" },
      body: JSON.stringify(parametros),
      signal: AbortSignal.timeout(12_000),
    });
    if (resposta.status === 404 && "p_computador" in parametros) {
      // banco ainda sem a migration do computador preso: pergunta do jeito antigo
      const { p_computador: _, ...antigos } = parametros;
      console.warn("rpc", funcao, "sem p_computador (migration pendente)");
      return rpcDireto(funcao, antigos);
    }
    if (!resposta.ok) {
      console.error("rpc", funcao, resposta.status, (await resposta.text()).slice(0, 300));
      return null;
    }
    return resposta.json();
  }
}

const responder = (status: number, corpo: unknown) =>
  new Response(JSON.stringify(corpo), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });

Deno.serve(async (pedido) => {
  const rota = rotaDe(new URL(pedido.url).pathname);
  if (pedido.method !== "POST" || !rota) return responder(404, { ok: false, erro: "rota" });
  if (!PRIVADA || !SERVICO || !URL_PROJETO || !REMETENTE || !(BREVO || RESEND)) {
    return responder(503, { ok: false, erro: "nao_configurada", mensagem: "Pagamentos protegidos ainda nao configurados." });
  }

  let corpo: Record<string, unknown>;
  try {
    corpo = await pedido.json();
    if (!corpo || typeof corpo !== "object" || Array.isArray(corpo)) throw new Error("corpo");
  } catch {
    return responder(400, { ok: false, erro: "pedido_invalido" });
  }

  try {
    const resultado = await tratar(ambiente, rota, corpo, ipDoVisitante(pedido.headers));
    return responder(resultado.status, resultado.corpo);
  } catch (erro) {
    console.error("pagamentos", rota, erro);
    return responder(500, { ok: false, erro: "interno", mensagem: "Nao foi possivel concluir agora. Tente de novo em instantes." });
  }
});
