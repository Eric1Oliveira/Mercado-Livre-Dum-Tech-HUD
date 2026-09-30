// O coracao da licenca assinada: montar o conteudo e assinar.
//
// Sem nada de Deno aqui - so WebCrypto, que existe igual no Deno (Edge
// Function) e no Node (testes: supabase/functions/tests/licenca-assinada.test.mjs).

export type RespostaLicenca = {
  ok: boolean;
  chave?: string;
  cliente?: string;
  tipo?: string;
  produtos?: string[];
  expira_em?: string | null;
  max_computadores?: number;
  [campo: string]: unknown;
};

export type Pacote = { v: 1; kid: string; licenca: string; assinatura: string };

const MS_DIA = 86_400_000;

/** Texto vindo da internet: sem espacos, maiusculo e com tamanho limitado. */
export function normalizar(texto: unknown, tamanho: number): string {
  return String(texto ?? "").trim().slice(0, tamanho).toUpperCase();
}

/** O identificador do computador que o Hub manda: 32 hex (ja embaralhado la). */
export function computadorValido(texto: unknown): boolean {
  return /^[0-9a-f]{32}$/.test(String(texto ?? ""));
}

/**
 * O que vai assinado. `valida_ate` e o prazo offline: passado dele, o Hub pede
 * uma conferencia nova antes de abrir os modulos.
 */
export function conteudoDaLicenca(
  dados: RespostaLicenca,
  { kid, maquina, computador, agora = new Date(), diasOffline = 30 }:
    { kid: string; maquina: string; computador: string; agora?: Date; diasOffline?: number },
) {
  return {
    v: 1,
    kid,
    chave: String(dados.chave ?? ""),
    maquina,
    computador,
    cliente: String(dados.cliente ?? ""),
    tipo: String(dados.tipo ?? ""),
    produtos: (dados.produtos ?? []).map((c) => String(c).toUpperCase()),
    // teste gratis: modulo -> quando acaba. Vai ASSINADO: o Hub bloqueia no dia
    // certo mesmo offline, e ninguem estica o prazo editando o arquivo
    testes: testesValidos(dados.testes),
    expira_em: dados.expira_em ?? null,
    max_computadores: Number(dados.max_computadores ?? 1),
    emitida_em: agora.toISOString(),
    valida_ate: new Date(agora.getTime() + diasOffline * MS_DIA).toISOString(),
  };
}

/** So {CODIGO: data ISO} de verdade entra no pacote assinado. */
export function testesValidos(testes: unknown): Record<string, string> {
  const saida: Record<string, string> = {};
  if (!testes || typeof testes !== "object" || Array.isArray(testes)) return saida;
  for (const [codigo, fim] of Object.entries(testes as Record<string, unknown>)) {
    if (/^[A-Z][A-Z0-9_]{1,30}$/.test(codigo) && !Number.isNaN(Date.parse(String(fim)))) {
      saida[codigo] = new Date(String(fim)).toISOString();
    }
  }
  return saida;
}

export function base64url(bytes: Uint8Array): string {
  let binario = "";
  for (const b of bytes) binario += String.fromCharCode(b);
  return btoa(binario).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function deBase64(texto: string): Uint8Array {
  const binario = atob(texto.trim());
  return Uint8Array.from(binario, (c) => c.charCodeAt(0));
}

/** A chave privada do segredo (PKCS8 em base64, como sai de tools/gerar_chave_licenca.mjs). */
export function importarChavePrivada(pkcs8Base64: string): Promise<CryptoKey> {
  return crypto.subtle.importKey("pkcs8", deBase64(pkcs8Base64), { name: "Ed25519" }, false, ["sign"]);
}

/** Assina os BYTES do JSON - o Hub confere exatamente esses bytes. */
export async function assinar(conteudo: object, chave: CryptoKey, kid: string): Promise<Pacote> {
  const bytes = new TextEncoder().encode(JSON.stringify(conteudo));
  const assinatura = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, chave, bytes));
  return { v: 1, kid, licenca: base64url(bytes), assinatura: base64url(assinatura) };
}

/** Primeiro endereco do visitante (a funcao repassa ao banco para o limite por hora). */
export function ipDoVisitante(cabecalhos: Headers): string {
  return (cabecalhos.get("cf-connecting-ip")
    || cabecalhos.get("x-real-ip")
    || (cabecalhos.get("x-forwarded-for") ?? "").split(",")[0]
    || "").trim().slice(0, 64);
}
