// Edge Function `versao`: o manifesto de atualizacao do Hub, assinado.
//
//   POST /functions/v1/versao  {chave, maquina, versao}
//     -> {ok, versao, url, notas, sha256, obrigatoria, automatica, tamanho, assinado}
//
// O Hub chama de hora em hora (chave anon, como nas outras). O `assinado` e um
// pacote Ed25519 com a MESMA chave da licenca: o Hub confere antes de baixar
// qualquer coisa, e so entao executa o instalador.
//
// SEGREDOS (Supabase > Edge Functions > Secrets)
//   DUMTECH_LICENCA_CHAVE_PRIVADA   a MESMA de licenca-assinada
//   DUMTECH_LICENCA_KID             a MESMA de licenca-assinada (ex.: k1)
//   SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY ja vem de fabrica
//
// PUBLICAR: supabase functions deploy versao --no-verify-jwt
//   (sem verificar JWT: o Hub chama com a chave anon)

import { type Ambiente, assinar, importarChavePrivada, ipDoVisitante, tratar } from "./nucleo.ts";

const URL_PROJETO = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICO = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const PRIVADA = Deno.env.get("DUMTECH_LICENCA_CHAVE_PRIVADA") ?? "";
const KID = Deno.env.get("DUMTECH_LICENCA_KID") ?? "k1";

let chavePrivada: Promise<CryptoKey> | null = null;

const ambiente: Ambiente = {
  kid: KID,
  assinar: async (conteudo) => {
    chavePrivada ??= importarChavePrivada(PRIVADA);
    try {
      return await assinar(conteudo, await chavePrivada, KID);
    } catch (erro) {
      chavePrivada = null;
      throw erro;
    }
  },
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

const responder = (status: number, corpo: unknown) =>
  new Response(JSON.stringify(corpo), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });

Deno.serve(async (pedido) => {
  if (pedido.method !== "POST") return responder(405, { ok: false, erro: "metodo" });
  if (!PRIVADA || !SERVICO || !URL_PROJETO) {
    return responder(503, { ok: false, erro: "nao_configurada" });
  }

  let corpo: Record<string, unknown>;
  try {
    corpo = await pedido.json();
    if (!corpo || typeof corpo !== "object" || Array.isArray(corpo)) throw new Error("corpo");
  } catch {
    return responder(400, { ok: false, erro: "pedido_invalido" });
  }

  try {
    const resultado = await tratar(ambiente, corpo, ipDoVisitante(pedido.headers));
    return responder(resultado.status, resultado.corpo);
  } catch (erro) {
    console.error("versao", erro);
    return responder(500, { ok: false, erro: "interno" });
  }
});
