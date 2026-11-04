// Contas do Hub: login, senha e gestao das pessoas de cada chave. Sem nada de
// Deno aqui - banco, e-mail e assinatura entram por parametro. Testado em
// supabase/functions/tests/acesso.test.mjs.
//
// A SENHA NUNCA CHEGA AO BANCO. Esta funcao deriva com PBKDF2 e o Postgres so ve
// a string derivada: a senha em claro nao passa por parametro SQL nem por log.
// Para conferir, o banco devolve o hash a esta funcao, e ele nao sai daqui.
//
// Esta pasta e autossuficiente de proposito, como `pagamentos`: `assinar` e
// `conteudoAcesso` sao o MESMO formato de licenca-assinada/nucleo.ts, conferido
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
  iteracoes?: number;                                // so os testes mudam
};

export type Resposta = { status: number; corpo: Record<string, unknown> };

const ROTAS = [
  "criar-primeiro", "entrar", "pedir-codigo", "redefinir", "pedir-confirmacao", "confirmar-email", "trocar-senha",
  "usuarios", "salvar-usuario", "senha-usuario", "apagar-usuario",
  "computadores", "renomear-computador", "liberar-computador",
] as const;
export type Rota = (typeof ROTAS)[number];

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
  return ROTAS.find((r) => r === fim) ?? "";
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

function escapar(texto: string): string {
  return texto.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

function primeiroNome(nome: string): string {
  return String(nome ?? "").trim().split(/\s+/)[0] || "cliente";
}

/** "DumTech <avisos@x.com>" -> {nome, email} (o Brevo quer separado). */
export function remetente(texto: string): { nome: string; email: string } {
  const achado = /^\s*(.*?)\s*<([^>]+)>\s*$/.exec(texto ?? "");
  return achado ? { nome: achado[1] || "DumTech", email: achado[2].trim() } : { nome: "DumTech", email: String(texto ?? "").trim() };
}

// ------------------------------------------------------------------- senha --
/** 600 mil iteracoes (OWASP para PBKDF2-SHA256). O numero fica guardado no hash. */
export const ITERACOES = 600_000;

const TAMANHO_MAXIMO = 72;

/** As que qualquer um tenta primeiro. Comparadas sem maiusculas. */
const OBVIAS = new Set([
  "12345678", "123456789", "1234567890", "87654321", "senha123", "senha1234", "password", "password1",
  "qwerty123", "admin123", "administrador", "abcd1234", "dumtech123", "mudar123",
]);

/** Devolve o motivo da recusa, ou "" quando a senha serve. */
export function senhaAceitavel(senha: string, login = ""): string {
  const texto = String(senha ?? "");
  if (texto.length < 8) return "A senha precisa ter pelo menos 8 caracteres.";
  if (texto.length > TAMANHO_MAXIMO) return `A senha pode ter no máximo ${TAMANHO_MAXIMO} caracteres.`;
  const minusculo = texto.toLowerCase();
  if (login && minusculo === String(login).trim().toLowerCase()) return "A senha não pode ser igual ao login.";
  if (OBVIAS.has(minusculo) || new Set(minusculo).size === 1) return "Essa senha é fácil demais de adivinhar. Escolha outra.";
  return "";
}

async function pbkdf2(senha: string, sal: Uint8Array, iteracoes: number): Promise<Uint8Array> {
  const bruta = await crypto.subtle.importKey("raw", new TextEncoder().encode(senha.normalize("NFKC")),
    "PBKDF2", false, ["deriveBits"]);
  return new Uint8Array(await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: sal, iterations: iteracoes }, bruta, 256));
}

/** "pbkdf2$<iteracoes>$<sal>$<derivado>": a mesma forma que o painel gera no navegador. */
export async function derivarSenha(senha: string, { iteracoes = ITERACOES }: { iteracoes?: number } = {}): Promise<string> {
  const sal = crypto.getRandomValues(new Uint8Array(16));
  return `pbkdf2$${iteracoes}$${base64url(sal)}$${base64url(await pbkdf2(senha, sal, iteracoes))}`;
}

export async function conferirSenha(senha: string, guardado: string): Promise<boolean> {
  const partes = /^pbkdf2\$(\d{5,8})\$([A-Za-z0-9_-]+)\$([A-Za-z0-9_-]+)$/.exec(String(guardado ?? ""));
  if (!partes || !senha) return false;
  const esperado = deBase64url(partes[3]);
  const calculado = await pbkdf2(senha, deBase64url(partes[2]), Number(partes[1]));
  if (calculado.length !== esperado.length) return false;
  let diferenca = 0;   // sem sair no primeiro byte diferente
  for (let i = 0; i < calculado.length; i++) diferenca |= calculado[i] ^ esperado[i];
  return diferenca === 0;
}

// ----------------------------------------------------------------- e-mails --
export function emailDoCodigo(dados: { nome: string; codigo: string; validade: number; finalidade: "recuperar_senha" | "confirmar_email" }):
  Omit<Mensagem, "para"> {
  const nome = primeiroNome(dados.nome);
  const recuperar = dados.finalidade === "recuperar_senha";
  const pedido = recuperar
    ? "Alguém pediu para redefinir a senha da sua conta no DumTech Hub."
    : "Use este código para confirmar o seu e-mail no DumTech Hub. É ele que recupera a sua senha se você esquecer.";
  const fim = recuperar
    ? "Se não foi você, ignore este e-mail: sem este código ninguém troca a senha."
    : "Se não foi você, ignore este e-mail.";
  const texto = [
    `Olá, ${nome}!`,
    "",
    pedido,
    "",
    `Código: ${dados.codigo}`,
    `Vale por ${dados.validade} minutos e só pode ser usado uma vez.`,
    "",
    `${fim} Nunca passe este código por telefone ou WhatsApp - a DumTech nunca pede.`,
  ].join("\n");
  const html = `<div style="font-family:Arial,sans-serif;max-width:480px;color:#1f2330">
  <p>Olá, ${escapar(nome)}!</p>
  <p>${escapar(pedido)}</p>
  <p style="font-size:32px;letter-spacing:8px;font-weight:bold;margin:24px 0">${escapar(dados.codigo)}</p>
  <p>Vale por ${dados.validade} minutos e só pode ser usado uma vez.</p>
  <p style="color:#6b7080;font-size:13px">${escapar(fim)}
  Nunca passe este código por telefone ou WhatsApp - a DumTech nunca pede.</p>
</div>`;
  const assunto = recuperar ? "é o código para redefinir a sua senha" : "é o código para confirmar o seu e-mail";
  return { assunto: `${dados.codigo} ${assunto}`, texto, html };
}

// --------------------------------------------------------------- assinatura --
type Identidade = { chave: string; maquina: string; computador: string };

/** O que vai assinado: quem pode entrar neste computador e o que cada um ve. */
export function conteudoAcesso(
  { kid, chave, maquina, computador, resumo, agora = new Date() }:
    Identidade & { kid: string; resumo: { exigir_conta?: boolean; usuarios?: unknown[] }; agora?: Date },
) {
  return {
    v: 1, kid, uso: "acesso", chave, maquina, computador,
    exigir_conta: Boolean(resumo?.exigir_conta), usuarios: resumo?.usuarios ?? [],
    emitido_em: agora.toISOString(),
  };
}

/** A lembranca que abre o Hub direto: presa a pessoa, a senha e a este computador. */
export function conteudoLembranca(
  { kid, chave, maquina, computador, usuario, agora = new Date() }:
    Identidade & { kid: string; usuario: { id: string; senha_versao: number }; agora?: Date },
) {
  return {
    v: 1, kid, uso: "lembrar", chave, maquina, computador,
    usuario: usuario.id, senha_versao: usuario.senha_versao, emitido_em: agora.toISOString(),
  };
}

export function base64url(bytes: Uint8Array): string {
  let binario = "";
  for (const b of bytes) binario += String.fromCharCode(b);
  return btoa(binario).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function deBase64url(texto: string): Uint8Array {
  const binario = atob(texto.replaceAll("-", "+").replaceAll("_", "/").padEnd(Math.ceil(texto.length / 4) * 4, "="));
  return Uint8Array.from(binario, (c) => c.charCodeAt(0));
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
const INCOMPLETO: Resposta = { status: 200, corpo: { ok: false, erro: "dados_incompletos", mensagem: "Pedido incompleto." } };

const recusa = (erro: string, mensagem: string): Resposta => ({ status: 200, corpo: { ok: false, erro, mensagem } });

function identidade(corpo: Record<string, unknown>): Identidade | null {
  const chave = normalizar(corpo.chave, 32);
  const maquina = normalizar(corpo.maquina, 64);
  const computador = String(corpo.computador ?? "");
  return chave && maquina && computadorValido(computador) ? { chave, maquina, computador } : null;
}

/** Tira o resumo em claro e devolve o pacote assinado, com a lembranca se pediram. */
async function assinada(ambiente: Ambiente, id: Identidade, dados: Record<string, any>, lembrar = false): Promise<Resposta> {
  const { resumo, ...resto } = dados;
  const agora = ambiente.agora?.() ?? new Date();
  const corpo: Record<string, unknown> = {
    ...resto,
    acesso_assinado: await ambiente.assinar(conteudoAcesso({ kid: ambiente.kid, ...id, resumo, agora })),
  };
  if (lembrar && dados.usuario) {
    corpo.lembranca = await ambiente.assinar(conteudoLembranca({ kid: ambiente.kid, ...id, usuario: dados.usuario, agora }));
  }
  return { status: 200, corpo };
}

async function mandarCodigo(ambiente: Ambiente, dados: Record<string, any>, finalidade: "recuperar_senha" | "confirmar_email"): Promise<Resposta> {
  const email = emailDoCodigo({ nome: dados.nome, codigo: dados.codigo, validade: Number(dados.validade_minutos ?? 10), finalidade });
  if (!(await ambiente.enviarEmail({ para: dados.email, ...email }))) {
    return recusa("falha_no_envio", "Não foi possível enviar o e-mail agora. Tente de novo em instantes.");
  }
  // o codigo NUNCA volta para o Hub: so por e-mail
  return { status: 200, corpo: { ok: true, email: mascararEmail(dados.email), validade_minutos: dados.validade_minutos } };
}

/** So o que uma conta tem: campo a mais no pedido nao chega ao banco. */
function dadosDaConta(usuario: unknown) {
  const u = (usuario && typeof usuario === "object" ? usuario : {}) as Record<string, unknown>;
  return {
    nome: String(u.nome ?? "").slice(0, 120), login: String(u.login ?? "").slice(0, 80),
    email: String(u.email ?? "").slice(0, 160), papel: String(u.papel ?? "funcionario").slice(0, 20),
    modulos: Array.isArray(u.modulos) ? u.modulos.map(String).slice(0, 64) : [],
    avisos: Array.isArray(u.avisos) ? u.avisos.map(String).slice(0, 64) : [],
    ativo: u.ativo !== false,
  };
}

/** Uma rota inteira: o index.ts so cuida de HTTP. */
export async function tratar(ambiente: Ambiente, rota: Rota, corpo: Record<string, unknown>, ip: string): Promise<Resposta> {
  const id = identidade(corpo);
  if (!id) return INCOMPLETO;
  const base = { p_chave: id.chave, p_maquina: id.maquina, p_computador: id.computador };
  const sessao = { ...base, p_sessao: String(corpo.sessao ?? "").slice(0, 128) };
  const senha = String(corpo.senha ?? "").slice(0, 200);
  const login = String(corpo.login ?? "").slice(0, 80);
  const lembrar = corpo.lembrar === true;
  const derivar = (texto: string) => derivarSenha(texto, { iteracoes: ambiente.iteracoes ?? ITERACOES });
  // derivar e caro de proposito, e esta funcao nao exige JWT: nada de gastar CPU
  // antes de saber que o pedido vem de um computador ativado (ou de um ADM)
  const conferirIdentidade = async (): Promise<Resposta | null> => {
    const dados = await ambiente.rpc("dumtech_acesso_antes_de_derivar", { ...base, p_ip: ip });
    if (!dados) return FALHA;
    return dados.ok ? null : { status: 200, corpo: dados };
  };
  const conferirAdm = async (): Promise<Resposta | null> => {
    const dados = await ambiente.rpc("dumtech_acesso_portao", { ...sessao, p_so_adm: true });
    if (!dados) return FALHA;
    return dados.ok ? null : { status: 200, corpo: dados };
  };

  if (rota === "criar-primeiro") {
    const problema = senhaAceitavel(senha, login);
    if (problema) return recusa("senha_fraca", problema);
    const barrado = await conferirIdentidade();
    if (barrado) return barrado;
    const dados = await ambiente.rpc("dumtech_acesso_criar_primeiro", {
      ...base, p_nome: String(corpo.nome ?? "").slice(0, 120), p_login: login,
      p_email: String(corpo.email ?? "").slice(0, 160), p_senha_hash: await derivar(senha), p_ip: ip,
    });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    return assinada(ambiente, id, dados, lembrar);
  }

  if (rota === "entrar") {
    if (!senha) return recusa("credenciais", "Login ou senha incorretos.");
    const busca = await ambiente.rpc("dumtech_acesso_buscar", { ...base, p_login: login, p_ip: ip });
    if (!busca) return FALHA;
    if (!busca.ok) return { status: 200, corpo: busca };
    const certo = await conferirSenha(senha, busca.senha_hash);
    const dados = await ambiente.rpc("dumtech_acesso_resultado", { ...base, p_usuario: busca.usuario_id, p_certo: certo, p_ip: ip });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    return assinada(ambiente, id, dados, lembrar);
  }

  if (rota === "pedir-codigo") {
    const dados = await ambiente.rpc("dumtech_acesso_pedir_codigo", { ...base, p_login: login, p_ip: ip });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    if (dados.sem_email) return { status: 200, corpo: { ok: true, sem_email: true } };
    if (!dados.codigo) return { status: 200, corpo: { ok: true, email: "" } };   // login errado responde igual
    return mandarCodigo(ambiente, dados, "recuperar_senha");
  }

  if (rota === "redefinir") {
    const problema = senhaAceitavel(senha, login);
    if (problema) return recusa("senha_fraca", problema);
    const barrado = await conferirIdentidade();
    if (barrado) return barrado;
    const dados = await ambiente.rpc("dumtech_acesso_redefinir", {
      ...base, p_login: login, p_codigo: String(corpo.codigo ?? "").slice(0, 8), p_senha_hash: await derivar(senha), p_ip: ip,
    });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    return assinada(ambiente, id, dados, lembrar);
  }

  if (rota === "pedir-confirmacao") {
    const dados = await ambiente.rpc("dumtech_acesso_codigo_email", sessao);
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    return mandarCodigo(ambiente, dados, "confirmar_email");
  }

  if (rota === "confirmar-email") {
    const dados = await ambiente.rpc("dumtech_acesso_confirmar_email", { ...sessao, p_codigo: String(corpo.codigo ?? "").slice(0, 8) });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    return assinada(ambiente, id, dados);
  }

  if (rota === "trocar-senha") {
    const atual = String(corpo.atual ?? "").slice(0, 200);
    const nova = String(corpo.nova ?? "").slice(0, 200);
    const busca = await ambiente.rpc("dumtech_acesso_buscar_sessao", sessao);
    if (!busca) return FALHA;
    if (!busca.ok) return { status: 200, corpo: busca };
    if (!(await conferirSenha(atual, busca.senha_hash))) {
      // errar aqui tambem conta: senao esta rota viraria um jeito de testar senhas
      await ambiente.rpc("dumtech_acesso_resultado", { ...base, p_usuario: busca.usuario_id, p_certo: false, p_ip: ip });
      return recusa("senha_atual_errada", "A senha atual não confere.");
    }
    if (nova === atual) return recusa("senha_fraca", "A senha nova precisa ser diferente da atual.");
    const problema = senhaAceitavel(nova, busca.login);
    if (problema) return recusa("senha_fraca", problema);
    const dados = await ambiente.rpc("dumtech_acesso_gravar_senha", { ...sessao, p_senha_hash: await derivar(nova) });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    return assinada(ambiente, id, dados, lembrar);
  }

  if (rota === "salvar-usuario") {
    const usuario = dadosDaConta(corpo.usuario);
    if (senha) {
      const problema = senhaAceitavel(senha, usuario.login);
      if (problema) return recusa("senha_fraca", problema);
      const barrado = await conferirAdm();
      if (barrado) return barrado;
    }
    const dados = await ambiente.rpc("dumtech_acesso_salvar_usuario", {
      ...sessao, p_id: corpo.id ? String(corpo.id) : null, p_dados: usuario, p_senha_hash: senha ? await derivar(senha) : "",
    });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    return assinada(ambiente, id, dados);
  }

  if (rota === "senha-usuario") {
    const problema = senhaAceitavel(senha, login);
    if (problema) return recusa("senha_fraca", problema);
    const barrado = await conferirAdm();
    if (barrado) return barrado;
    const dados = await ambiente.rpc("dumtech_acesso_senha_usuario", { ...sessao, p_id: String(corpo.id ?? ""), p_senha_hash: await derivar(senha) });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    return assinada(ambiente, id, dados);
  }

  if (rota === "apagar-usuario") {
    const dados = await ambiente.rpc("dumtech_acesso_apagar_usuario", { ...sessao, p_id: String(corpo.id ?? "") });
    if (!dados) return FALHA;
    if (!dados.ok) return { status: 200, corpo: dados };
    return assinada(ambiente, id, dados);
  }

  const alvo = String(corpo.maquina_alvo ?? "").slice(0, 64);
  const dados = rota === "usuarios" ? await ambiente.rpc("dumtech_acesso_usuarios", sessao)
    : rota === "computadores" ? await ambiente.rpc("dumtech_acesso_computadores", sessao)
    : rota === "renomear-computador" ? await ambiente.rpc("dumtech_acesso_renomear_computador", {
        ...sessao, p_alvo: alvo, p_apelido: String(corpo.apelido ?? "").slice(0, 120) })
    : await ambiente.rpc("dumtech_acesso_liberar_computador", { ...sessao, p_alvo: alvo });
  if (!dados) return FALHA;
  return { status: 200, corpo: dados };
}
