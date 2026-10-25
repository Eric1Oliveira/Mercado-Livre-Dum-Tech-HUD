// Conversa do painel com o Supabase: login e leitura/escrita das tabelas.
//
// COMO A SEGURANCA FUNCIONA AQUI
//   O painel entra com Supabase Auth e usa o token da sessao em todas as
//   chamadas. Quem manda no que ele enxerga sao as POLICIES do banco: elas so
//   liberam para quem esta em `administradores`. Se alguem abrir este painel e
//   entrar com uma conta comum, ele carrega - e nao mostra uma linha.
//
//   Nao existe cadastro nem convite: a conta de administrador nasce no painel
//   do Supabase (Authentication > Users) e o id entra em `administradores`.
//
// COMO A VELOCIDADE FUNCIONA AQUI
//   Toda leitura fica guardada pelo endereco (memoria). Abrir uma tela que ja
//   foi vista desenha NA HORA com o que se sabe, e a rede confere por tras: se
//   algo mudou, `aoMudarDados` avisa e a tela se redesenha sozinha. Gravar marca
//   tudo como "a conferir" e ja corrige na memoria o que o banco devolveu - o
//   preco salvo aparece antes de a rede terminar de conferir o resto.

import { CONFIG } from "./config.js";
import { imagemDoQr } from "./qr.js";

const AUTH = () => `${CONFIG.SUPABASE_URL}/auth/v1`;
const REST = () => `${CONFIG.SUPABASE_URL}/rest/v1`;
const CHAVE_SESSAO = "dumtech.painel.sessao";

/** Avisa a tela quando a sessao cai (token vencido, senha trocada...). */
export const aoPerderSessao = new Set();

/** Avisa quando uma conferencia em segundo plano trouxe dado diferente. */
export const aoMudarDados = new Set();

// ================================================================= sessao ===
export function sessao() {
  try {
    const bruto = localStorage.getItem(CHAVE_SESSAO);
    return bruto ? JSON.parse(bruto) : null;
  } catch {
    return null;
  }
}

function guardar(dados) {
  // o nivel da sessao vem carimbado no proprio token: aal1 = senha, aal2 = senha + codigo
  const completo = { ...dados, aal: lerToken(dados.token).aal || "" };
  try {
    localStorage.setItem(CHAVE_SESSAO, JSON.stringify(completo));
  } catch {
    /* navegador anonimo: a sessao vale so enquanto a aba estiver aberta */
  }
}

/** O conteudo do JWT (so para LER o nivel; quem confere a assinatura e o servidor). */
function lerToken(jwt) {
  try {
    const meio = String(jwt || "").split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(meio.padEnd(Math.ceil(meio.length / 4) * 4, "=")));
  } catch {
    return {};
  }
}

/**
 * A sessao guardada serve para abrir o painel direto? So se ja passou pelo
 * segundo fator - ou se o banco ainda nao exige (migration antiga, `mfa: false`).
 * Mesmo que alguem force isto no navegador, o banco nao entrega dado sem aal2.
 */
export function sessaoCompleta() {
  const atual = sessao();
  return Boolean(atual?.token && (atual.aal === "aal2" || atual.mfa === false));
}

function esquecerSessao() {
  try {
    localStorage.removeItem(CHAVE_SESSAO);
  } catch {
    /* nada a fazer */
  }
  memoria.clear(); // dado de uma sessao nunca aparece na seguinte
}

/**
 * Primeiro passo: e-mail e senha. Recusa quem nao e administrador e diz o que
 * vem depois:
 *   { etapa: "pronto" }                              banco sem 2 fatores (migration antiga)
 *   { etapa: "codigo" }                              ja tem autenticador: pedir o codigo
 *   { etapa: "cadastrar", qr, segredo, endereco }    primeira vez: mostrar o QR Code
 */
export async function entrar(email, senha) {
  const resposta = await fetch(`${AUTH()}/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: CONFIG.SUPABASE_ANON, "Content-Type": "application/json" },
    body: JSON.stringify({ email: String(email || "").trim(), password: senha || "" }),
  });
  const dados = await resposta.json().catch(() => ({}));

  if (!resposta.ok) {
    throw new Error(
      resposta.status === 429
        ? "Muitas tentativas seguidas. Espere um minuto e tente de novo."
        : dados.error_description || dados.msg || "E-mail ou senha incorretos."
    );
  }

  guardar({
    token: dados.access_token,
    refresh: dados.refresh_token,
    expira_em: Date.now() + (Number(dados.expires_in) || 3600) * 1000,
    email: dados.user?.email || email,
    user_id: dados.user?.id || "",
  });

  // a conta existe - mas e administradora? (pergunta que funciona antes do codigo)
  let situacao;
  try {
    situacao = await rpc("dumtech_sou_admin", {}, { grava: false });
  } catch (erro) {
    if (erro.status !== 404) throw erro;
    // banco sem a migration dos 2 fatores: o jeito antigo, e o painel avisa
    if ((await rpc("dumtech_e_admin", {}, { grava: false })) !== true) return recusarConta();
    guardar({ ...sessao(), mfa: false });
    return { etapa: "pronto" };
  }
  if (situacao?.admin !== true) return recusarConta();
  return prepararSegundoFator();
}

async function recusarConta() {
  await sair();
  throw new Error(
    "Esta conta existe, mas não é administradora. Peça para incluírem o seu " +
    "usuário na tabela administradores."
  );
}

// ========================================================= dois fatores ====
let fatorAtual = null;

async function prepararSegundoFator() {
  const usuario = await auth("/user");
  const totp = (usuario.factors || []).filter((f) => f.factor_type === "totp");
  const pronto = totp.find((f) => f.status === "verified");
  if (pronto) {
    fatorAtual = pronto.id;
    return { etapa: "codigo" };
  }

  // cadastro que ficou pela metade (fechou a aba antes do codigo): recomeca
  for (const velho of totp) {
    await auth(`/factors/${velho.id}`, { method: "DELETE" }).catch(() => {});
  }
  const novo = await auth("/factors", {
    method: "POST",
    body: { factor_type: "totp", friendly_name: `Painel DumTech ${new Date().toISOString().slice(0, 10)}`, issuer: "DumTech" },
  });
  fatorAtual = novo.id;
  return {
    etapa: "cadastrar",
    qr: imagemDoQr(novo.totp?.qr_code),
    segredo: novo.totp?.secret || "",
    // otpauth://... - vale como plano B: no celular, abre o autenticador direto
    endereco: novo.totp?.uri || "",
  };
}

/** Segundo passo: o codigo de 6 digitos. Troca a sessao por uma aal2. */
export async function confirmarCodigo(codigo) {
  const limpo = String(codigo || "").replace(/\D/g, "");
  if (limpo.length !== 6) throw new Error("O código tem 6 números.");
  if (!fatorAtual) throw new Error("Entre com e-mail e senha de novo.");

  const desafio = await auth(`/factors/${fatorAtual}/challenge`, { method: "POST", body: {} });
  const nova = await auth(`/factors/${fatorAtual}/verify`, {
    method: "POST", body: { challenge_id: desafio.id, code: limpo },
  });
  const atual = sessao();
  guardar({
    token: nova.access_token,
    refresh: nova.refresh_token,
    expira_em: Date.now() + (Number(nova.expires_in) || 3600) * 1000,
    email: nova.user?.email || atual?.email || "",
    user_id: nova.user?.id || atual?.user_id || "",
  });
  fatorAtual = null;

  if ((await rpc("dumtech_e_admin", {}, { grava: false })) !== true) return recusarConta();
  return sessao();
}

/** Supabase Auth com o token da sessao (fatores do 2FA). */
async function auth(caminho, { method = "GET", body } = {}) {
  const atual = await token();
  if (!atual) throw new Error("Sessão encerrada. Entre de novo.");
  const resposta = await fetch(`${AUTH()}${caminho}`, {
    method,
    headers: {
      apikey: CONFIG.SUPABASE_ANON,
      Authorization: `Bearer ${atual}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) {
    throw Object.assign(new Error(erroDeAuth(resposta.status, dados)), { status: resposta.status });
  }
  return dados;
}

function erroDeAuth(status, dados) {
  const codigo = String(dados?.error_code || dados?.code || "");
  if (status === 429) return "Muitas tentativas seguidas. Espere um minuto e tente de novo.";
  if (codigo.includes("verification_failed") || /invalid totp/i.test(dados?.msg || "")) {
    return "Código incorreto ou vencido. Use o código que está na tela do aplicativo agora.";
  }
  if (codigo.includes("enroll_not_enabled") || (codigo.includes("mfa") && status === 422)) {
    return "O login em 2 fatores está desligado no Supabase (Authentication › Multi-Factor › TOTP).";
  }
  return dados?.msg || dados?.error_description || dados?.message || `Erro ${status} ao falar com o login.`;
}

export async function sair() {
  const atual = sessao();
  esquecerSessao();
  if (!atual?.token) return;
  try {
    await fetch(`${AUTH()}/logout`, {
      method: "POST",
      headers: { apikey: CONFIG.SUPABASE_ANON, Authorization: `Bearer ${atual.token}` },
    });
  } catch {
    /* sair e local: se a rede falhar, a sessao ja foi embora daqui */
  }
}

// O refresh token do Supabase e de USO UNICO. Dez leituras em paralelo com o
// token vencendo pediam dez renovacoes com o mesmo refresh - a segunda em diante
// era recusada e o painel "caia" sozinho. Agora ha uma renovacao so, e todos
// esperam por ela.
let renovando = null;

/** O token valido da sessao (renova quando falta pouco). null = sem sessao. */
export async function token() {
  const atual = sessao();
  if (!atual?.token) return null;
  if (Date.now() < atual.expira_em - 60_000) return atual.token;

  renovando ??= renovar(atual).finally(() => { renovando = null; });
  return renovando;
}

async function renovar(atual) {
  try {
    const resposta = await fetch(`${AUTH()}/token?grant_type=refresh_token`, {
      method: "POST",
      headers: { apikey: CONFIG.SUPABASE_ANON, "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: atual.refresh }),
    });
    if (!resposta.ok) throw new Error("sessao vencida");
    const dados = await resposta.json();
    guardar({
      ...atual,
      token: dados.access_token,
      refresh: dados.refresh_token || atual.refresh,
      expira_em: Date.now() + (Number(dados.expires_in) || 3600) * 1000,
    });
    return dados.access_token;
  } catch {
    perdemosASessao();
    return null;
  }
}

function perdemosASessao() {
  esquecerSessao();
  for (const avisar of aoPerderSessao) {
    try {
      avisar();
    } catch {
      /* uma tela quebrada nao pode impedir as outras de saber */
    }
  }
}

// ================================================================ rede =====
async function chamar(caminho, opcoes = {}) {
  const atual = await token();
  if (!atual) throw new Error("Sessão encerrada. Entre de novo.");

  const resposta = await fetch(`${REST()}${caminho}`, {
    ...opcoes,
    headers: {
      apikey: CONFIG.SUPABASE_ANON,
      Authorization: `Bearer ${atual}`,
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(opcoes.headers || {}),
    },
  });

  if (resposta.status === 401) {
    perdemosASessao();
    throw new Error("Sessão encerrada. Entre de novo.");
  }

  const texto = await resposta.text();
  let dados = null;
  try {
    dados = texto ? JSON.parse(texto) : null;
  } catch {
    // proxy, pagina de erro, gateway fora: nao e JSON e nao pode virar "SyntaxError"
    dados = resposta.ok ? null : { message: `Erro ${resposta.status} no servidor.` };
  }
  if (!resposta.ok) {
    throw Object.assign(new Error(dados?.message || dados?.hint || `Erro ${resposta.status}.`),
                        { status: resposta.status });
  }
  return { dados, texto };
}

/**
 * Edge Function do projeto, com o token do administrador. Devolve
 * { status, dados } sem lancar: quem chama decide o que "404" significa
 * (quase sempre: a funcao ainda nao foi publicada).
 */
export async function funcao(nome, corpo = {}) {
  const atual = await token();
  if (!atual) throw new Error("Sessão encerrada. Entre de novo.");
  try {
    const resposta = await fetch(`${CONFIG.SUPABASE_URL}/functions/v1/${nome}`, {
      method: "POST",
      headers: { apikey: CONFIG.SUPABASE_ANON, Authorization: `Bearer ${atual}`, "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
    return { status: resposta.status, dados: await resposta.json().catch(() => ({})) };
  } catch {
    return { status: 0, dados: {} }; // sem rede, ou a funcao nao responde a CORS (nao publicada)
  }
}

// ============================================================= memoria =====
//   caminho -> { dados, texto, quando, usado, buscando }
const memoria = new Map();

/** Dado com menos que isto nao e conferido de novo ao ser lido. */
const FRESCO_MS = 20_000;
/** Leitura que ninguem usa ha tanto tempo sai da memoria na proxima conferencia. */
const ESQUECER_MS = 10 * 60_000;

function montarCaminho(alvo, { select = "*", ordem = "", limite = 0, filtros = {} } = {}) {
  const parametros = new URLSearchParams({ select });
  for (const [campo, valor] of Object.entries(filtros)) {
    if (valor !== undefined && valor !== null && valor !== "") parametros.append(campo, valor);
  }
  if (ordem) parametros.set("order", ordem);
  if (limite) parametros.set("limit", String(limite));
  return `/${alvo}?${parametros}`;
}

/** Vai a rede (uma vez por caminho, mesmo com varios pedindo juntos). */
function buscar(caminho, { avisar = false } = {}) {
  const entrada = memoria.get(caminho) ?? { usado: Date.now() };
  if (entrada.buscando) return entrada.buscando;

  entrada.buscando = chamar(caminho)
    .then(({ dados, texto }) => {
      const mudou = entrada.texto !== undefined && entrada.texto !== texto;
      Object.assign(entrada, { dados, texto, quando: Date.now() });
      if (mudou && avisar) avisarMudanca(caminho);
      return dados;
    })
    .finally(() => { entrada.buscando = null; });

  memoria.set(caminho, entrada);
  return entrada.buscando;
}

let mudancaAgendada = null;
function avisarMudanca() {
  // varias conferencias terminando juntas viram UM redesenho
  clearTimeout(mudancaAgendada);
  mudancaAgendada = setTimeout(() => {
    for (const avisar of aoMudarDados) {
      try {
        avisar();
      } catch (erro) {
        console.error(erro);
      }
    }
  }, 60);
}

/**
 * Le uma tabela ou visao.
 *   ler("painel_clientes", { select: "*", ordem: "nome.asc", limite: 50,
 *                            filtros: { situacao: "eq.ativa" }, fresco: false })
 * `fresco: true` ignora a memoria e espera a rede (depois de gravar algo que a
 * tela precisa mostrar certo, como a ficha do cliente).
 */
export function ler(alvo, { fresco = false, ...opcoes } = {}) {
  const caminho = montarCaminho(alvo, opcoes);
  const entrada = memoria.get(caminho);

  if (entrada && entrada.texto !== undefined && !fresco) {
    entrada.usado = Date.now();
    if (Date.now() - entrada.quando > FRESCO_MS) {
      buscar(caminho, { avisar: true }).catch(() => { /* fica o que ja estava */ });
    }
    return Promise.resolve(entrada.dados);
  }
  return buscar(caminho);
}

export async function um(alvo, opcoes) {
  const linhas = await ler(alvo, { ...opcoes, limite: 1 });
  return Array.isArray(linhas) ? linhas[0] ?? null : linhas;
}

/** Tudo o que esta na memoria passa a ser "a conferir" (sem apagar nada). */
export function invalidar() {
  for (const entrada of memoria.values()) entrada.quando = 0;
}

/**
 * Confere com a rede tudo o que foi lido recentemente. Se algo mudou,
 * `aoMudarDados` avisa. Usado quando o banco avisa que mudou (tempo real) e
 * quando a aba volta a ficar visivel.
 */
export async function conferirTudo() {
  const agora = Date.now();
  const pendentes = [];
  for (const [caminho, entrada] of memoria) {
    if (agora - (entrada.usado || 0) > ESQUECER_MS) {
      memoria.delete(caminho);
      continue;
    }
    pendentes.push(buscar(caminho, { avisar: true }).catch(() => null));
  }
  await Promise.all(pendentes);
}

/** O que o banco devolveu de uma gravacao ja entra na memoria, linha por linha. */
function corrigirMemoria(tabela, linhas) {
  if (!Array.isArray(linhas) || !linhas.length) return;
  const porId = new Map(linhas.filter((l) => l?.id).map((l) => [l.id, l]));
  if (!porId.size) return;

  for (const [caminho, entrada] of memoria) {
    if (!caminho.startsWith(`/${tabela}?`) || !Array.isArray(entrada.dados)) continue;
    let trocou = false;
    const dados = entrada.dados.map((linha) => {
      const nova = porId.get(linha?.id);
      if (!nova) return linha;
      trocou = true;
      return { ...linha, ...nova };
    });
    if (trocou) Object.assign(entrada, { dados, texto: JSON.stringify(dados) });
  }
}

// ============================================================== escrita ====
export async function inserir(tabela, dados) {
  const { dados: linhas } = await chamar(`/${tabela}`, {
    method: "POST",
    headers: { Prefer: "return=representation" },
    body: JSON.stringify(dados),
  });
  invalidar();
  return linhas;
}

export async function atualizar(tabela, filtros, dados) {
  const parametros = new URLSearchParams(filtros);
  const { dados: linhas } = await chamar(`/${tabela}?${parametros}`, {
    method: "PATCH",
    headers: { Prefer: "return=representation" },
    body: JSON.stringify(dados),
  });
  invalidar();
  corrigirMemoria(tabela, linhas);
  return linhas;
}

/**
 * Apaga as linhas que batem com os filtros.
 *
 * `conferir`: pede ao banco as linhas que ele de fato apagou e reclama se
 * nenhuma saiu. Sem isso, uma policy que barra (ou um registro que outra
 * pessoa ja apagou) devolve "204 sem conteudo" igual a uma exclusao que deu
 * certo - e a tela diria "excluido" sem ter excluido nada.
 */
export async function apagar(tabela, filtros, { conferir = false } = {}) {
  const parametros = new URLSearchParams(filtros);
  // o banco devolve o que apagou: e o que sai da memoria na hora
  const { dados } = await chamar(`/${tabela}?${parametros}`, {
    method: "DELETE",
    headers: { Prefer: "return=representation" },
  });
  invalidar();
  tirarDaMemoria(tabela, dados);
  if (conferir && !(Array.isArray(dados) && dados.length)) {
    throw new Error("O banco não excluiu nada: o registro já tinha saído ou esta conta não pode excluí-lo.");
  }
  return Array.isArray(dados) ? dados : [];
}

//: as visoes que mostram uma tabela com o id dela em outro nome
const VISOES_DA_TABELA = {
  clientes: { painel_clientes: "cliente_id" },
  pedidos_site: { pedidos_abertos: "pedido_id" },
};

/**
 * O que acabou de ser apagado sai da memoria (da tabela e das visoes que a
 * mostram). Sem isso, a tela redesenhada logo depois mostraria o registro
 * apagado ate a conferencia com o banco voltar - ele "sumia e voltava".
 */
function tirarDaMemoria(tabela, linhas) {
  const ids = new Set((Array.isArray(linhas) ? linhas : []).map((linha) => linha?.id).filter(Boolean));
  if (!ids.size) return;
  const visoes = VISOES_DA_TABELA[tabela] || {};
  for (const [caminho, entrada] of memoria) {
    if (!Array.isArray(entrada.dados)) continue;
    const alvo = caminho.slice(1, caminho.indexOf("?"));
    const chave = alvo === tabela ? "id" : visoes[alvo];
    if (!chave) continue;
    const ficam = entrada.dados.filter((linha) => !ids.has(linha?.[chave]));
    if (ficam.length !== entrada.dados.length) {
      Object.assign(entrada, { dados: ficam, texto: JSON.stringify(ficam) });
    }
  }
}

/** Funcao do banco. `grava: false` para as que so leem (nao invalida a memoria). */
export async function rpc(nome, params = {}, { grava = true } = {}) {
  const { dados } = await chamar(`/rpc/${nome}`, { method: "POST", body: JSON.stringify(params) });
  if (grava) invalidar();
  return dados;
}
