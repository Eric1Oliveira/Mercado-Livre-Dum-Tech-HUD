// Edge Function `acesso`: contas, senhas e computadores de cada chave.
//
//   POST /functions/v1/acesso/criar-primeiro       o primeiro ADM da licenca
//   POST /functions/v1/acesso/entrar               login e senha -> sessao de 30 min
//   POST /functions/v1/acesso/pedir-codigo         esqueci a senha: codigo por e-mail
//   POST /functions/v1/acesso/redefinir            codigo + senha nova
//   POST /functions/v1/acesso/pedir-confirmacao    codigo para confirmar o e-mail
//   POST /functions/v1/acesso/confirmar-email      confirma com o codigo
//   POST /functions/v1/acesso/trocar-senha         a propria senha
//   POST /functions/v1/acesso/usuarios             ADM: lista as contas
//   POST /functions/v1/acesso/salvar-usuario       ADM: cria ou edita
//   POST /functions/v1/acesso/senha-usuario        ADM: redefine a senha de alguem
//   POST /functions/v1/acesso/apagar-usuario       ADM: apaga
//   POST /functions/v1/acesso/computadores         ADM: lista os computadores
//   POST /functions/v1/acesso/renomear-computador  ADM: da nome
//   POST /functions/v1/acesso/liberar-computador   ADM: solta a vaga
//
// O Hub chama com a chave anon (como licenca-assinada). Quem decide tudo e o
// banco (migration 20261102120000_contas_e_acessos.sql), com o service_role.
//
// SEGREDOS (Supabase > Edge Functions > Secrets)
//   DUMTECH_LICENCA_CHAVE_PRIVADA   a MESMA de licenca-assinada
//   DUMTECH_LICENCA_KID             a MESMA de licenca-assinada (ex.: k1)
//   DUMTECH_EMAIL_REMETENTE         ex.: DumTech <dumtechsolutions@gmail.com>
//   e UM provedor de e-mail: BREVO_API_KEY ou RESEND_API_KEY
//   SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY ja vem de fabrica
//
// PUBLICAR: supabase functions deploy acesso --no-verify-jwt --use-api
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

async function rpc(funcao: string, parametros: Record<string, unknown>) {
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
}

const ambiente: Ambiente = {
  kid: KID,
  enviarEmail,
  rpc,
  assinar: async (conteudo) => {
    chavePrivada ??= importarChavePrivada(PRIVADA);
    try {
      return await assinar(conteudo, await chavePrivada, KID);
    } catch (erro) {
      chavePrivada = null;
      throw erro;
    }
  },
};

const responder = (status: number, corpo: unknown) =>
  new Response(JSON.stringify(corpo), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });

Deno.serve(async (pedido) => {
  const rota = rotaDe(new URL(pedido.url).pathname);
  if (pedido.method !== "POST" || !rota) return responder(404, { ok: false, erro: "rota" });
  if (!PRIVADA || !SERVICO || !URL_PROJETO || !REMETENTE || !(BREVO || RESEND)) {
    return responder(503, { ok: false, erro: "nao_configurada", mensagem: "Contas ainda não configuradas." });
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
    // so a rota: o corpo do pedido tem senha, e senha nao vai para log
    console.error("acesso", rota, erro instanceof Error ? erro.name : "erro");
    return responder(500, { ok: false, erro: "interno", mensagem: "Não foi possível concluir agora. Tente de novo em instantes." });
  }
});
