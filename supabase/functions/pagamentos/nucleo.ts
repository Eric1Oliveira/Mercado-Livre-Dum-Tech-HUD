// Pagamentos protegidos do Hub: codigo por e-mail, sessao curta e chave Pix
// assinada. Sem nada de Deno aqui - banco, e-mail e assinatura entram por
// parametro. Testado em supabase/functions/tests/pagamentos.test.mjs.
//
// Esta pasta e autossuficiente de proposito: o painel do Supabase (Via Editor)
// publica uma funcao sem enxergar as pastas vizinhas. Por isso `assinar` esta
// repetido aqui - e o MESMO formato de licenca-assinada/nucleo.ts, conferido
// pelo mesmo `assinatura.abrir` do Hub.

type Rpc = (funcao: string, parametros: Record<string, unknown>) => Promise<any>;

export type Mensagem = { para: string; assunto: string; texto: string; html: string };
export type Pacote = { v: 1; kid: string; licenca: string; assinatura: string };

export type Ambiente = {
  rpc: Rpc;                                          // funcoes do banco, com service_role
  enviarEmail: (mensagem: Mensagem) => Promise<boolean>;
  assinar: (conteudo: object) => Promise<Pacote>;    // chave privada da licenca
  kid: string;
  agora?: () => Date;
};

export type Resposta = { status: number; corpo: Record<string, unknown> };
export type Rota = "codigo" | "entrar" | "salvar" | "atual";

// ---------------------------------------------------------------- formatos --
/** Texto vindo da internet: sem espacos, maiusculo e com tamanho limitado. */
export function normalizar(texto: unknown, tamanho: number): string {
  return String(texto ?? "").trim().slice(0, tamanho).toUpperCase();
}

/** O identificador do computador que o Hub manda: 32 hex (ja embaralhado la). */
export function computadorValido(texto: unknown): boolean {
  return /^[0-9a-f]{32}$/.test(String(texto ?? ""));
}

export function rotaDe(caminho: string): Rota | "" {
  const fim = caminho.replace(/\/+$/, "").split("/").pop() ?? "";
  return (["codigo", "entrar", "salvar", "atual"] as const).find((r) => r === fim) ?? "";
}

/** Primeiro endereco do visitante (o banco conta o limite por hora nele). */
export function ipDoVisitante(cabecalhos: Headers): string {
  return (cabecalhos.get("cf-connecting-ip")
    || cabecalhos.get("x-real-ip")
    || (cabecalhos.get("x-forwarded-for") ?? "").split(",")[0]
    || "").trim().slice(0, 64);
}

/** e***o@gmail.com - o Hub mostra para onde foi, sem entregar o endereco. */
export function mascararEmail(email: string): string {
  const [usuario, dominio] = String(email ?? "").split("@");
  if (!usuario || !dominio) return "";
  const meio = usuario.length <= 2 ? "*" : "*".repeat(Math.min(usuario.length - 2, 6));
  return `${usuario[0]}${meio}${usuario.length > 1 ? usuario.at(-1) : ""}@${dominio}`;
}

/** So o comeco e o fim da chave Pix, para o e-mail de aviso. */
export function mascararPix(pix: string): string {
  const texto = String(pix ?? "");
  if (!texto) return "(nenhuma)";
  if (texto.length <= 6) return `${texto[0]}***`;
  return `${texto.slice(0, 3)}***${texto.slice(-4)}`;
}

function escapar(texto: string): string {
  return texto.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

function primeiroNome(nome: string): string {
  return String(nome ?? "").trim().split(/\s+/)[0] || "cliente";
}

// ----------------------------------------------------------------- e-mails --
export function emailDoCodigo(dados: { cliente: string; codigo: string; validade: number }):
  Omit<Mensagem, "para"> {
  const nome = primeiroNome(dados.cliente);
  const texto = [
    `Olá, ${nome}!`,
    "",
    "Alguém pediu para abrir a área de Pagamentos do DumTech Hub (chave Pix e formas de pagamento).",
    "",
    `Código: ${dados.codigo}`,
    `Vale por ${dados.validade} minutos e só pode ser usado uma vez.`,
    "",
    "Se não foi você, ignore este e-mail: sem este código ninguém entra. " +
      "Nunca passe este código por telefone ou WhatsApp - a DumTech nunca pede.",
  ].join("\n");
  const html = `<div style="font-family:Arial,sans-serif;max-width:480px;color:#1f2330">
  <p>Olá, ${escapar(nome)}!</p>
  <p>Alguém pediu para abrir a área de <b>Pagamentos</b> do DumTech Hub (chave Pix e formas de pagamento).</p>
  <p style="font-size:32px;letter-spacing:8px;font-weight:bold;margin:24px 0">${escapar(dados.codigo)}</p>
  <p>Vale por ${dados.validade} minutos e só pode ser usado uma vez.</p>
  <p style="color:#6b7080;font-size:13px">Se não foi você, ignore este e-mail: sem este código ninguém entra.
  Nunca passe este código por telefone ou WhatsApp - a DumTech nunca pede.</p>
</div>`;
  return { assunto: `${dados.codigo} é o seu código de acesso aos Pagamentos`, texto, html };
}

export function emailDaTroca(dados: { cliente: string; antes: string; depois: string; quando: Date }):
  Omit<Mensagem, "para"> {
  const nome = primeiroNome(dados.cliente);
  const quando = dados.quando.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const antes = mascararPix(dados.antes);
  const depois = dados.depois ? mascararPix(dados.depois) : "(removida - o QR Code deixa de aparecer)";
  const texto = [
    `Olá, ${nome}!`,
    "",
    "A chave Pix que aparece no QR Code do seu balcão foi alterada.",
    "",
    `Antes: ${antes}`,
    `Agora: ${depois}`,
    `Quando: ${quando}`,
    "",
    "Se foi você, está tudo certo. Se NÃO foi você, pare de receber Pix pelo QR Code agora, " +
      "confira o computador e fale com a DumTech.",
  ].join("\n");
  const html = `<div style="font-family:Arial,sans-serif;max-width:480px;color:#1f2330">
  <p>Olá, ${escapar(nome)}!</p>
  <p>A chave Pix que aparece no QR Code do seu balcão <b>foi alterada</b>.</p>
  <table style="margin:16px 0;font-size:15px">
    <tr><td style="color:#6b7080;padding-right:12px">Antes</td><td>${escapar(antes)}</td></tr>
    <tr><td style="color:#6b7080;padding-right:12px">Agora</td><td><b>${escapar(depois)}</b></td></tr>
    <tr><td style="color:#6b7080;padding-right:12px">Quando</td><td>${escapar(quando)}</td></tr>
  </table>
  <p>Se foi você, está tudo certo. <b>Se não foi você</b>, pare de receber Pix pelo QR Code agora,
  confira o computador e fale com a DumTech.</p>
</div>`;
  return { assunto: "Aviso: a chave Pix do seu balcão foi alterada", texto, html };
}

/** "DumTech <avisos@x.com>" -> {nome, email} (o Brevo quer separado). */
export function remetente(texto: string): { nome: string; email: string } {
  const achado = /^\s*(.*?)\s*<([^>]+)>\s*$/.exec(texto ?? "");
  return achado ? { nome: achado[1] || "DumTech", email: achado[2].trim() } : { nome: "DumTech", email: String(texto ?? "").trim() };
}

// --------------------------------------------------------------- assinatura --
/** O que vai assinado. `uso` separa este documento de uma licenca. */
export function conteudoPix(
  { kid, chave, maquina, computador, pix, agora = new Date() }:
    { kid: string; chave: string; maquina: string; computador: string; pix: string; agora?: Date },
) {
  return { v: 1, kid, uso: "pagamentos", chave, maquina, computador, pix_chave: pix, emitido_em: agora.toISOString() };
}

export function base64url(bytes: Uint8Array): string {
  let binario = "";
  for (const b of bytes) binario += String.fromCharCode(b);
  return btoa(binario).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

/** A chave privada do segredo (PKCS8 em base64, a mesma de licenca-assinada). */
export function importarChavePrivada(pkcs8Base64: string): Promise<CryptoKey> {
  const bytes = Uint8Array.from(atob(pkcs8Base64.trim()), (c) => c.charCodeAt(0));
  return crypto.subtle.importKey("pkcs8", bytes, { name: "Ed25519" }, false, ["sign"]);
}

/** Assina os BYTES do JSON - o Hub confere exatamente esses bytes. */
export async function assinar(conteudo: object, chave: CryptoKey, kid: string): Promise<Pacote> {
  const bytes = new TextEncoder().encode(JSON.stringify(conteudo));
  const assinatura = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, chave, bytes));
  return { v: 1, kid, licenca: base64url(bytes), assinatura: base64url(assinatura) };
}

// ------------------------------------------------------------------- rotas --
const FALHA: Resposta = { status: 502, corpo: { ok: false, erro: "servidor", mensagem: "Servidor indisponível. Tente de novo em instantes." } };

function identidade(corpo: Record<string, unknown>) {
  const chave = normalizar(corpo.chave, 32);
  const maquina = normalizar(corpo.maquina, 64);
  const computador = String(corpo.computador ?? "");
  return chave && maquina && computadorValido(computador) ? { chave, maquina, computador } : null;
}

const INCOMPLETO: Resposta = { status: 200, corpo: { ok: false, erro: "dados_incompletos", mensagem: "Pedido incompleto." } };

async function pixAssinado(ambiente: Ambiente, id: { chave: string; maquina: string; computador: string }, pix: string) {
  return ambiente.assinar(conteudoPix({ kid: ambiente.kid, ...id, pix, agora: ambiente.agora?.() ?? new Date() }));
}

/** Uma rota inteira: o index.ts so cuida de HTTP. */
export async function tratar(ambiente: Ambiente, rota: Rota, corpo: Record<string, unknown>, ip: string): Promise<Resposta> {
  const id = identidade(corpo);
  if (!id) return INCOMPLETO;
  const base = { p_chave: id.chave, p_maquina: id.maquina };

  if (rota === "codigo") {
    const dados = await ambiente.rpc("dumtech_pagamentos_pedir_codigo", { ...base, p_computador: id.computador, p_ip: ip });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    const email = emailDoCodigo({ cliente: dados.cliente, codigo: dados.codigo, validade: Number(dados.validade_minutos ?? 10) });
    if (!(await ambiente.enviarEmail({ para: dados.email, ...email }))) {
      return { status: 200, corpo: { ok: false, erro: "falha_no_envio", mensagem: "Não foi possível enviar o e-mail agora. Tente de novo em instantes." } };
    }
    // o codigo NUNCA volta para o Hub: so por e-mail
    return { status: 200, corpo: { ok: true, email: mascararEmail(dados.email), validade_minutos: dados.validade_minutos } };
  }

  if (rota === "entrar") {
    const dados = await ambiente.rpc("dumtech_pagamentos_entrar", {
      ...base, p_computador: id.computador, p_codigo: String(corpo.codigo ?? "").slice(0, 8), p_ip: ip,
    });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    return { status: 200, corpo: { ...dados, assinado: await pixAssinado(ambiente, id, String(dados.pix_chave ?? "")) } };
  }

  const sessao = String(corpo.sessao ?? "").slice(0, 128);

  if (rota === "salvar") {
    const dados = await ambiente.rpc("dumtech_pagamentos_salvar", {
      ...base, p_computador: id.computador, p_sessao: sessao, p_pix_chave: String(corpo.pix_chave ?? "").slice(0, 100),
    });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    if (dados.mudou && dados.email) {
      // o aviso nao segura a troca: a chave ja mudou no banco
      const aviso = emailDaTroca({ cliente: dados.cliente, antes: dados.antes, depois: dados.pix_chave, quando: ambiente.agora?.() ?? new Date() });
      await ambiente.enviarEmail({ para: dados.email, ...aviso }).catch(() => false);
    }
    return { status: 200, corpo: { ok: true, pix_chave: dados.pix_chave, assinado: await pixAssinado(ambiente, id, dados.pix_chave) } };
  }

  // atual
  const dados = await ambiente.rpc("dumtech_pagamentos_atual",
    { ...base, p_computador: id.computador, p_ip: ip });
  if (!dados) return FALHA;
  if (!dados.ok) return { status: 200, corpo: dados };
  return { status: 200, corpo: { ok: true, pix_chave: dados.pix_chave, assinado: await pixAssinado(ambiente, id, dados.pix_chave) } };
}
