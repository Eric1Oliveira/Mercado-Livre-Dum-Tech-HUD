// Edge Function `licenca-assinada`: confere a licenca E devolve ela assinada.
//
// O Hub chama no lugar de `dumtech_verificar_licenca` (e logo depois de ativar).
// A resposta e a mesma da funcao do banco, com um campo a mais: `assinado`.
//
// SEGREDOS (Supabase > Edge Functions > Secrets)
//   DUMTECH_LICENCA_CHAVE_PRIVADA   PKCS8 base64 (tools/gerar_chave_licenca.mjs)
//   DUMTECH_LICENCA_KID             ex.: k1 (o mesmo nome em CHAVES_PUBLICAS do Hub)
//   DUMTECH_LICENCA_DIAS_OFFLINE    opcional, padrao 30
//   SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY ja vem de fabrica
//
// PUBLICAR: supabase functions deploy licenca-assinada --no-verify-jwt
//   (sem verificar JWT: o Hub chama com a chave anon, como chama as RPCs)

import {
  assinar, computadorValido, conteudoAcesso, conteudoDaLicenca, importarChavePrivada, ipDoVisitante, normalizar,
} from "./nucleo.ts";

const URL_PROJETO = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICO = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const PRIVADA = Deno.env.get("DUMTECH_LICENCA_CHAVE_PRIVADA") ?? "";
const KID = Deno.env.get("DUMTECH_LICENCA_KID") ?? "k1";
const DIAS_OFFLINE = Math.min(Math.max(Number(Deno.env.get("DUMTECH_LICENCA_DIAS_OFFLINE") ?? 30), 1), 90);

let chavePrivada: Promise<CryptoKey> | null = null;

const responder = (status: number, corpo: unknown) =>
  new Response(JSON.stringify(corpo), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });

Deno.serve(async (pedido) => {
  if (pedido.method !== "POST") {
    return responder(405, { ok: false, erro: "metodo", mensagem: "Use POST." });
  }
  if (!PRIVADA || !SERVICO || !URL_PROJETO) {
    // sem a chave, nada de licenca "meio assinada": o Hub cai no caminho antigo
    return responder(503, { ok: false, erro: "nao_configurada", mensagem: "Assinatura de licenca nao configurada." });
  }

  let corpo: Record<string, unknown>;
  try {
    corpo = await pedido.json();
  } catch {
    return responder(400, { ok: false, erro: "dados_incompletos", mensagem: "Pedido invalido." });
  }

  const chave = normalizar(corpo.chave, 32);
  const maquina = normalizar(corpo.maquina, 64);
  const computador = String(corpo.computador ?? "");
  if (!chave || !maquina || !computadorValido(computador)) {
    return responder(200, { ok: false, erro: "dados_incompletos", mensagem: "Informe a chave da licenca." });
  }

  // a MESMA regra do banco (existe? ativa? no prazo? computador ativado?), com
  // o limite por hora contado no endereco de quem chamou - nao no da funcao
  const consultar = (corpo: Record<string, unknown>) =>
    fetch(`${URL_PROJETO}/rest/v1/rpc/dumtech_licenca_para_assinar`, {
      method: "POST",
      headers: {
        apikey: SERVICO,
        Authorization: `Bearer ${SERVICO}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(corpo),
    });

  const base = { p_chave: chave, p_maquina: maquina, p_ip: ipDoVisitante(pedido.headers) };
  // o computador vai JUNTO: o banco prende a licenca ao primeiro que chegar,
  // senao bastava copiar o license.json para liberar em qualquer maquina
  let resposta = await consultar({ ...base, p_computador: computador });
  if (resposta.status === 404) {
    // banco ainda sem a migration do computador preso: em vez de deixar todo
    // mundo sem licenca assinada, pergunta do jeito antigo
    console.warn("dumtech_licenca_para_assinar sem p_computador (migration pendente)");
    resposta = await consultar(base);
  }
  if (!resposta.ok) {
    console.error("dumtech_licenca_para_assinar", resposta.status, await resposta.text());
    return responder(502, { ok: false, erro: "servidor", mensagem: "Servidor de licencas indisponivel." });
  }

  const dados = await resposta.json();
  if (!dados?.ok) return responder(200, dados); // recusa do banco vai como veio

  try {
    chavePrivada ??= importarChavePrivada(PRIVADA);
    const privada = await chavePrivada;
    // as contas so saem assinadas: o Hub offline nao pode acreditar em texto solto
    const { acesso, ...publicos } = dados;
    const conteudo = conteudoDaLicenca(publicos, { kid: KID, maquina, computador, diasOffline: DIAS_OFFLINE });
    return responder(200, {
      ...publicos,
      assinado: await assinar(conteudo, privada, KID),
      ...(acesso ? {
        acesso_assinado: await assinar(
          conteudoAcesso({ kid: KID, chave: conteudo.chave, maquina, computador, resumo: acesso }), privada, KID),
      } : {}),
    });
  } catch (erro) {
    chavePrivada = null;
    console.error("assinatura", erro);
    return responder(503, { ok: false, erro: "nao_configurada", mensagem: "Assinatura de licenca indisponivel." });
  }
});
