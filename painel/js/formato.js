// Como o painel escreve numero, data e gente.
//
// Modulo puro (sem DOM, sem rede): e o que os testes exercitam.

export const dinheiro = (valor) =>
  Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export const numero = (valor) => Number(valor || 0).toLocaleString("pt-BR");

/** 2026-09-12 -> 12/09/2026 (e vazio continua vazio, nao "Invalid Date"). */
export function data(valor) {
  if (!valor) return "—";
  const quando = new Date(String(valor).length <= 10 ? `${valor}T12:00:00` : valor);
  if (Number.isNaN(quando.getTime())) return "—";
  return quando.toLocaleDateString("pt-BR");
}

export function dataHora(valor) {
  if (!valor) return "—";
  const quando = new Date(valor);
  if (Number.isNaN(quando.getTime())) return "—";
  return quando.toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

/** "hoje", "ontem", "há 5 dias", "em 12 dias" - o tempo como gente fala. */
export function quando(valor, hoje = new Date()) {
  if (!valor) return "nunca";
  const alvo = new Date(String(valor).length <= 10 ? `${valor}T12:00:00` : valor);
  if (Number.isNaN(alvo.getTime())) return "nunca";

  const dia = 86400000;
  const inicio = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const dias = Math.round((inicio(alvo) - inicio(hoje)) / dia);

  if (dias === 0) return "hoje";
  if (dias === -1) return "ontem";
  if (dias === 1) return "amanhã";
  if (dias < 0) return `há ${Math.abs(dias)} dias`;
  return `em ${dias} dias`;
}

/** "agora", "há 12 min", "há 3 h" - passado de um dia, fala como `quando`. */
export function relativo(valor, agora = new Date()) {
  if (!valor) return "nunca";
  const alvo = new Date(valor);
  if (Number.isNaN(alvo.getTime())) return "nunca";
  const minutos = Math.floor((agora - alvo) / 60000);
  if (minutos < 1) return "agora";
  if (minutos < 60) return `há ${minutos} min`;
  if (minutos < 24 * 60) return `há ${Math.floor(minutos / 60)} h`;
  return quando(valor, agora);
}

/** 1 cliente / 2 clientes - sem "1 cliente(s)". */
export function contagem(quantos, singular, plural = "") {
  const n = Number(quantos || 0);
  return `${numero(n)} ${n === 1 ? singular : plural || `${singular}s`}`;
}

/** As duas primeiras iniciais do nome, para o avatar. */
export function iniciais(nome) {
  const partes = String(nome || "").trim().split(/\s+/).filter(Boolean);
  if (!partes.length) return "?";
  const primeira = partes[0][0] ?? "";
  const ultima = partes.length > 1 ? partes[partes.length - 1][0] ?? "" : "";
  return (primeira + ultima).toUpperCase();
}

/** Como a situacao da licenca aparece na tela. */
export function situacao(valor) {
  const mapa = {
    ativa: { texto: "Ativa", tom: "ok" },
    suspensa: { texto: "Suspensa", tom: "aviso" },
    cancelada: { texto: "Cancelada", tom: "ruim" },
    expirada: { texto: "Vencida", tom: "ruim" },
  };
  return mapa[valor] || { texto: valor ? String(valor) : "Sem licença", tom: "neutro" };
}

/** Telefone brasileiro legivel; o que nao reconhecer volta como veio. */
export function telefone(valor) {
  const digitos = String(valor || "").replace(/\D/g, "");
  if (digitos.length === 11) return `(${digitos.slice(0, 2)}) ${digitos.slice(2, 7)}-${digitos.slice(7)}`;
  if (digitos.length === 10) return `(${digitos.slice(0, 2)}) ${digitos.slice(2, 6)}-${digitos.slice(6)}`;
  return String(valor || "");
}

/** CPF/CNPJ com pontuacao; o que nao reconhecer volta como veio. */
export function documento(valor) {
  const d = String(valor || "").replace(/\D/g, "");
  if (d.length === 11) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
  if (d.length === 14) {
    return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
  }
  return String(valor || "");
}
