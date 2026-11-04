// As regras de Contas e acessos: o que o painel decide, sem tocar em tela.
//
// A senha provisoria nasce aqui, no navegador: ao banco so vai a string derivada,
// no MESMO formato de supabase/functions/acesso/nucleo.ts. Assim a senha em claro
// nao passa por parametro SQL, e o Hub confere do mesmo jeito.

import { versaoEmDia } from "./saude.js";

/** Os mesmos 600 mil de `derivarSenha` no servidor. O numero fica guardado no hash. */
export const ITERACOES = 600_000;

/** A partir daqui o Hub pede login. Computador mais velho abre sem pedir. */
export const VERSAO_COM_LOGIN = "1.11.0";

/** Os avisos de cada modulo: o mesmo `TIPOS` de src/dumtech/core/avisos.py. */
export const AVISOS = {
  agenda: ["compromisso_hoje", "link_para_confirmar"],
  clientes: ["aniversario_hoje"],
  estoque: ["estoque_baixo", "lote_vencendo"],
  financeiro: ["conta_vencendo", "conta_vencida"],
  orcamentos: ["proposta_parada", "proposta_vencendo"],
  ordens: ["os_atrasada", "os_para_retirar"],
  vendas: ["venda_a_receber"],
};

export const avisosDos = (modulos = []) => modulos.flatMap((m) => AVISOS[m] || []);

const base64url = (bytes) =>
  btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");

export async function derivarSenha(senha, { iteracoes = ITERACOES } = {}) {
  const sal = crypto.getRandomValues(new Uint8Array(16));
  const bruta = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(String(senha).normalize("NFKC")), "PBKDF2", false, ["deriveBits"]);
  const derivado = new Uint8Array(await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: sal, iterations: iteracoes }, bruta, 256));
  return `pbkdf2$${iteracoes}$${base64url(sal)}$${base64url(derivado)}`;
}

/** Facil de ditar: sem i, l, o, 0 e 1. Quem recebe cria a propria no primeiro acesso. */
export function gerarProvisoria() {
  const sorteia = (letras, quantas) => {
    const numeros = crypto.getRandomValues(new Uint32Array(quantas));
    return Array.from(numeros, (n) => letras[n % letras.length]).join("");
  };
  const letras = "abcdefghjkmnpqrstuvwxyz";
  return `${sorteia(letras, 4)}-${sorteia("23456789", 4)}-${sorteia(letras, 3)}`;
}

/**
 * Os modulos depois de editar pelo painel. Modulo em teste gratis nao tem caixa
 * aqui (a lista e do que foi comprado), e salvar nao pode tirar o que ninguem
 * desmarcou.
 */
export function modulosDaEdicao(marcados, antigos = [], listados = []) {
  return [...new Set([...marcados, ...antigos.filter((m) => !listados.includes(m))])];
}

/** Quantos computadores ainda precisam sair para caber no limite novo. */
export const vagasASoltar = (ativos, maximo) => Math.max(Number(ativos) - Number(maximo), 0);

export const temLogin = (versao) => versaoEmDia(versao, VERSAO_COM_LOGIN) === true;

/** Uma linha por loja com chave: as contas dela e o que ainda abre sem login. */
export function montarAcessos(clientes = [], acessos = [], ativacoes = []) {
  const porLicenca = new Map(acessos.map((a) => [a.licenca_id, a]));
  const antigos = new Map();
  for (const { licenca_id: licenca, versao } of ativacoes) {
    if (!temLogin(versao)) antigos.set(licenca, (antigos.get(licenca) || 0) + 1);
  }
  return clientes.filter((c) => c.licenca_id).map((cliente) => {
    const dados = porLicenca.get(cliente.licenca_id) || {};
    return {
      cliente,
      contas: Number(dados.contas || 0),
      adms: Number(dados.adms || 0),
      funcionarios: Number(dados.funcionarios || 0),
      ultimoAcesso: dados.ultimo_acesso || null,
      exigirConta: Boolean(dados.exigir_conta),
      emailDifere: Boolean(dados.email_difere),
      emailConfirmado: Boolean(dados.email_confirmado),
      semLogin: antigos.get(cliente.licenca_id) || 0,
    };
  });
}

export const FILTROS = [
  { valor: "todas", texto: "Todas" },
  { valor: "sem_conta", texto: "Sem conta" },
  { valor: "com_conta", texto: "Com conta" },
  { valor: "exigindo", texto: "Exigindo" },
  { valor: "atencao", texto: "Atenção" },
];

export function filtrarAcessos(linhas, filtro) {
  const regras = {
    sem_conta: (l) => !l.contas,
    com_conta: (l) => l.contas > 0,
    exigindo: (l) => l.exigirConta,
    atencao: (l) => l.emailDifere || (l.contas > 0 && l.semLogin > 0),
  };
  return linhas.filter(regras[filtro] || (() => true));
}

export function resumoMigracao(linhas = []) {
  const comConta = linhas.filter((l) => l.contas > 0);
  return {
    total: linhas.length,
    comConta: comConta.length,
    semConta: linhas.length - comConta.length,
    exigindo: linhas.filter((l) => l.exigirConta).length,
    // so preocupa onde ha conta: la e que o computador antigo fura o login
    computadoresSemLogin: comConta.reduce((soma, l) => soma + l.semLogin, 0),
  };
}

/** Chaves ativas que ainda nao exigem conta: o alvo de "Exigir de todas". */
export const licencasParaExigir = (linhas = []) =>
  linhas.filter((l) => !l.exigirConta && l.cliente.situacao === "ativa").map((l) => l.cliente.licenca_id);
