// A regra das telas da mensalidade (Assinantes, Planos e precos, Textos do
// site, Promocoes). Puro: sem DOM e sem rede - e o que tests/mensalidade.test.mjs
// exercita. As telas so desenham.

import { data, dinheiro } from "./formato.js";
import { modulo } from "./modulos.js";

export const SITUACAO = {
  teste:    { texto: "Testando", tom: "marca" },
  em_dia:   { texto: "Em dia", tom: "ok" },
  pendente: { texto: "Pagamento a confirmar", tom: "aviso" },
  consulta: { texto: "Só consulta", tom: "neutro" },
};

const nomes = (codigos = []) => {
  const lista = codigos.map((c) => modulo(c).nome);
  return lista.length <= 1 ? (lista[0] ?? "") : `${lista.slice(0, -1).join(", ")} e ${lista.at(-1)}`;
};

/** Igual a dumtech_chave_combinacao: ordem alfabetica, com "+"; "" = so a base. */
export function chaveCombinacao(adicionais = []) {
  return [...new Set(adicionais.map((c) => String(c).trim().toUpperCase()).filter(Boolean))].sort().join("+");
}

/** Todas as combinacoes dos adicionais, da menor para a maior (a vazia e "so a base"). */
export function todasAsCombinacoes(codigos = []) {
  const todas = [];
  for (let mascara = 0; mascara < 2 ** codigos.length; mascara++) {
    todas.push(codigos.filter((_, i) => mascara & (1 << i)));
  }
  return todas.sort((a, b) => a.length - b.length);
}

export function totalDaCombinacao(precoBase, adicionais, escolhidos) {
  const soma = escolhidos.reduce((total, codigo) =>
    total + Number(adicionais.find((a) => a.codigo === codigo)?.preco ?? 0), Number(precoBase || 0));
  return Math.round(soma * 100) / 100;
}

// ------------------------------------------------------------ o historico --
const TITULOS = {
  teste: (d) => `Começou o teste grátis${d.ate ? ` (até ${data(d.ate)})` : ""}`,
  pediu: (d) => `Pediu para assinar ${d.plano ? `o plano ${d.plano}` : "pelo monte o seu"}`
              + `${d.valor != null ? ` por ${dinheiro(d.valor)}` : ""}${d.cupom ? ` com o cupom ${d.cupom}` : ""}`,
  confirmou: (d) => `Assinatura confirmada${d.plano ? `: plano ${d.plano}` : ""}${d.valor != null ? ` por ${dinheiro(d.valor)}` : ""}`,
  ativou: (d) => `Assinatura ativada pelo painel${d.plano ? `: plano ${d.plano}` : ""}${d.valor != null ? ` por ${dinheiro(d.valor)}` : ""}`,
  descartou: () => "Pedido de assinatura descartado",
  falhou: (d) => `Cobrança falhou${d.ate ? ` (funciona até ${data(d.ate)})` : ""}`,
  em_dia: () => "Pagamento em dia",
  cancelou: (d) => `Assinatura cancelada${d.ate ? ` (funciona até ${data(d.ate)})` : ""}`,
  reabriu: () => "Assinatura reaberta",
  estendeu: (d) => `Teste estendido${d.dias ? ` em ${d.dias} dias` : ""}${d.ate ? ` (até ${data(d.ate)})` : ""}`,
  ajustou: () => "Assinatura ajustada",
};

/** { titulo, detalhe } de um evento de assinatura_eventos. */
export function descreverEvento(evento) {
  const d = evento?.detalhe ?? {};
  const titulo = TITULOS[evento?.tipo]?.(d) ?? String(evento?.tipo ?? "");
  if (evento?.tipo !== "ajustou") return { titulo, detalhe: "" };
  const partes = [];
  if (d.modulos) {
    const de = d.modulos.de ?? [];
    const para = d.modulos.para ?? [];
    const entrou = para.filter((c) => !de.includes(c));
    const saiu = de.filter((c) => !para.includes(c));
    if (d.plano) partes.push(`plano ${d.plano}`);
    if (entrou.length) partes.push(`entrou ${nomes(entrou)}`);
    if (saiu.length) partes.push(`saiu ${nomes(saiu)}`);
  }
  if (d.valor) partes.push(`valor de ${d.valor.de != null ? dinheiro(d.valor.de) : "—"} para ${dinheiro(d.valor.para)}`);
  if (d.computadores) partes.push(`computadores de ${d.computadores.de} para ${d.computadores.para}`);
  if (d.ate) partes.push(`funciona até ${data(d.ate.para)}`);
  if (d.anotacoes) partes.push("anotações atualizadas");
  return { titulo, detalhe: partes.join(" · ") };
}

// ---------------------------------------------------------------- a ficha --
/**
 * O que mudou entre a linha do banco e o formulario - so isso vai para a
 * Edge Function. Plano pronto escolhido manda o plano (os modulos vem dele).
 */
export function mudancasDaFicha(antes, form) {
  const saida = {};
  if (form.plano && form.plano !== antes.plano_id) {
    saida.plano = form.plano;
  } else if (!form.plano) {
    const mesmos = [...form.modulos].sort().join() === [...(antes.modulos ?? [])].sort().join();
    if (!mesmos || antes.plano_id) saida.modulos = form.modulos;
  }
  if (form.valor !== "" && form.valor != null && Number(form.valor) !== Number(antes.valor_mensal)) {
    saida.valor = Number(form.valor);
  }
  if (Number(form.computadores) !== Number(antes.max_computadores)) saida.computadores = Number(form.computadores);
  if (form.ate && form.ate !== antes.expira_em) saida.ate = form.ate;
  if ((form.observacoes ?? "") !== (antes.observacoes ?? "")) saida.observacoes = form.observacoes;
  // modulos iguais ao que ja estava, sem plano antes: nao e mudanca
  if (saida.modulos && !antes.plano_id
      && [...saida.modulos].sort().join() === [...(antes.modulos ?? [])].sort().join()) delete saida.modulos;
  return saida;
}

// ------------------------------------------------------------- os planos --
const linkValido = (link) => !link || /^https:\/\/\S+$/.test(link);

export function problemaDoPlano(p) {
  if (!String(p.nome ?? "").trim()) return "Dê um nome ao plano.";
  if (!p.modulos?.length) return "Marque ao menos um módulo.";
  if (!(Number(p.preco) >= 0) || p.preco === "" || p.preco == null) return "Confira o preço do mês.";
  if (!linkValido(p.link)) return "O link da InfinitePay precisa começar com https://";
  if (p.promo_preco != null && p.promo_preco !== "") {
    if (!p.promo_ate) return "Diga até quando vale a promoção.";
    if (!(Number(p.promo_preco) < Number(p.preco))) return "O preço promocional precisa ser menor que o normal.";
    if (!linkValido(p.promo_link)) return "O link da promoção precisa começar com https://";
  }
  return "";
}

// ------------------------------------------------------------- promocoes --
export function situacaoDoAviso(aviso, hoje = new Date().toISOString().slice(0, 10)) {
  if (!aviso.ativo) return "desligado";
  if (aviso.inicio > hoje) return "programado";
  if (aviso.fim && aviso.fim < hoje) return "encerrado";
  return "no_ar";
}

export function problemaDoAviso(a) {
  if (!String(a.texto ?? "").trim()) return "Escreva o texto da faixa.";
  if (String(a.texto).length > 160) return "O texto da faixa passou de 160 letras.";
  if (a.link && !/^(https:\/\/\S+|#[a-z0-9-]+)$/.test(a.link)) {
    return "O link precisa começar com https:// (ou ser #plano, para levar ao plano na própria página).";
  }
  if (a.fim && a.inicio && a.fim < a.inicio) return "O fim não pode vir antes do início.";
  return "";
}

export function problemaDoCupom(c) {
  if (!/^[A-Z0-9_-]{3,32}$/.test(String(c.codigo ?? "").trim().toUpperCase())) {
    return "O código do cupom precisa ter de 3 a 32 letras, números ou traço.";
  }
  if (!c.plano_id) return "Escolha o plano que o cupom libera.";
  return "";
}

export function linkDoCupom(loja, codigo) {
  return `${String(loja).replace(/\/+$/, "")}/?cupom=${String(codigo).trim().toUpperCase()}#plano`;
}
