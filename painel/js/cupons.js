// As regras do cupom que o painel confere antes de gravar (o banco confere de novo).
// Modulo puro - testado em painel/tests/cupons.test.mjs.

/** Codigo de cupom: maiusculo, sem acento nem espaco. */
export function codigoDeCupom(texto) {
  return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toUpperCase().replace(/\s+/g, "").replace(/[^A-Z0-9_-]/g, "").slice(0, 31);
}

/** O que esta errado no cupom (vazio = tudo certo). */
export function problemaDoCupom(d) {
  if (!/^[A-Z0-9][A-Z0-9_-]{1,30}$/.test(d.codigo || "")) return "O código usa letras, números, - e _ (de 2 a 31).";
  if (!(d.valor > 0)) return "Dê um valor de desconto maior que zero.";
  if (d.tipo === "percentual" && d.valor > 90) return "Desconto em % vai até 90%.";
  if (d.usos_max !== null && d.usos_max !== undefined && !(d.usos_max >= 1)) {
    return "Limite de usos: 1 ou mais (ou vazio para sem limite).";
  }
  if (d.minimo < 0) return "O valor mínimo não pode ser negativo.";
  return "";
}

/** O link que o parceiro manda: a loja abre com o cupom ja aplicado. */
export function linkDoCupom(loja, codigo) {
  return `${String(loja).replace(/\/+$/, "")}/?cupom=${encodeURIComponent(codigo)}`;
}
