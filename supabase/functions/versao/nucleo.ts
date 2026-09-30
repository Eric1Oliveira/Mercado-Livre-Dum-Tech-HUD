// O manifesto de atualizacao do Hub, ASSINADO.
//
// POR QUE ASSINADO
//   O Hub vai baixar um .exe e executar. Se bastasse "o servidor mandou", quem
//   entrasse no painel (ou no banco) apontaria o botao para um instalador
//   falso - e o cliente instalaria confiando no proprio programa. Aqui o
//   manifesto (versao + endereco + sha256) e assinado com a chave privada da
//   DumTech, que so existe no segredo desta funcao. O Hub confere a assinatura
//   ANTES de baixar, e confere o sha256 depois de baixar.
//
// Sem nada de Deno aqui: banco e assinatura entram por parametro (testes em
// supabase/functions/tests/versao.test.mjs).

type Rpc = (funcao: string, parametros: Record<string, unknown>) => Promise<any>;

export type Pacote = { v: 1; kid: string; licenca: string; assinatura: string };

export type Ambiente = {
  rpc: Rpc;
  assinar: (conteudo: object) => Promise<Pacote>;
  kid: string;
  agora?: () => Date;
};

export type Resposta = { status: number; corpo: Record<string, unknown> };

/** Texto vindo da internet: sem espacos, maiusculo e com tamanho limitado. */
export function normalizar(texto: unknown, tamanho: number): string {
  return String(texto ?? "").trim().slice(0, tamanho).toUpperCase();
}

/** So numero e ponto: "1.2.2". Serve para versao instalada e publicada. */
export function versaoValida(texto: unknown): boolean {
  return /^[0-9]+(\.[0-9]+){0,3}$/.test(String(texto ?? ""));
}

export function shaValido(texto: unknown): boolean {
  return /^[0-9a-f]{64}$/.test(String(texto ?? "").toLowerCase());
}

/** Primeiro endereco do visitante (o banco conta o limite por hora nele). */
export function ipDoVisitante(cabecalhos: Headers): string {
  return (cabecalhos.get("cf-connecting-ip")
    || cabecalhos.get("x-real-ip")
    || (cabecalhos.get("x-forwarded-for") ?? "").split(",")[0]
    || "").trim().slice(0, 64);
}

/**
 * O que vai assinado. `uso` separa este documento de uma licenca e da chave
 * Pix - o Hub recusa um pelo outro.
 */
export function conteudoDaAtualizacao(
  dados: Record<string, unknown>,
  { kid, agora = new Date() }: { kid: string; agora?: Date },
) {
  return {
    v: 1,
    kid,
    uso: "atualizacao",
    versao: String(dados.versao ?? ""),
    url: String(dados.url ?? ""),
    sha256: String(dados.sha256 ?? "").toLowerCase(),
    tamanho: Number(dados.tamanho ?? 0),
    obrigatoria: Boolean(dados.obrigatoria),
    automatica: Boolean(dados.automatica),
    emitido_em: agora.toISOString(),
  };
}

export function base64url(bytes: Uint8Array): string {
  let binario = "";
  for (const b of bytes) binario += String.fromCharCode(b);
  return btoa(binario).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

/** A chave privada do segredo (PKCS8 em base64, a mesma da licenca assinada). */
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

/** POST / -> {ok, versao, notas, url, sha256, obrigatoria, automatica, licenca, assinado} */
export async function tratar(
  ambiente: Ambiente,
  corpo: Record<string, unknown>,
  ip: string,
): Promise<Resposta> {
  const dados = await ambiente.rpc("dumtech_hub_versao", {
    p_chave: normalizar(corpo.chave, 32),
    p_maquina: normalizar(corpo.maquina, 64),
    p_versao: String(corpo.versao ?? "").slice(0, 20),
    p_ip: ip,
  });
  if (!dados) {
    return { status: 502, corpo: { ok: false, erro: "servidor" } };
  }
  if (!dados.ok) {
    return { status: 200, corpo: dados };
  }

  // impressao digital da licenca: se mudou, o Hub reconfere a licenca NA HORA
  // (modulo liberado, renovacao, bloqueio, Pix trocado). Nao libera nada
  // sozinha - por isso nao precisa ir dentro do pacote assinado.
  const licenca = /^[0-9a-f]{32}$/.test(String(dados.licenca ?? "")) ? String(dados.licenca) : "";

  // sem versao publicada nao ha o que assinar - e o Hub nao avisa nada
  if (!versaoValida(dados.versao)) {
    return { status: 200, corpo: { ok: true, versao: "", licenca } };
  }

  // sem sha256 valido a atualizacao pelo Hub fica DESLIGADA: melhor mandar o
  // cliente para a pagina de download do que executar arquivo sem conferencia
  const automatica = Boolean(dados.automatica) && shaValido(dados.sha256);
  const manifesto = { ...dados, automatica };
  return {
    status: 200,
    corpo: {
      ok: true,
      versao: manifesto.versao,
      url: manifesto.url,
      notas: manifesto.notas,
      obrigatoria: Boolean(manifesto.obrigatoria),
      automatica,
      sha256: automatica ? String(manifesto.sha256).toLowerCase() : "",
      tamanho: Number(manifesto.tamanho ?? 0),
      licenca,
      assinado: await ambiente.assinar(
        conteudoDaAtualizacao({ ...manifesto, sha256: automatica ? manifesto.sha256 : "" },
                              { kid: ambiente.kid, agora: ambiente.agora?.() }),
      ),
    },
  };
}
