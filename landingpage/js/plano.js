// O plano mensal da DumTech. Regra de negocio pura (sem tela, sem rede),
// testada em tests/plano.test.mjs.
//
//   planos prontos  nome, modulos (qualquer combinacao), preco e de/por - o
//                   Eric monta no painel
//   monte o seu     a base + cada adicional, com o preco de cada um
//   cupom           libera um plano (normalmente escondido) com preco proprio
//
// Tudo que vale dinheiro vem do banco (dumtech_mensalidade_publica) e e
// recalculado la no cadastro: o que esta aqui e o que a pessoa VE. O padrao
// abaixo e so a rede de seguranca para a pagina pintar na hora.

import { MODULOS } from "./dados.js";

export const CONFIG_PADRAO = Object.freeze({
  precoBase: 89.9,
  diasTeste: 7,
  computadores: 1,
  base: ["VENDAS", "ESTOQUE", "FINANCEIRO"],
  adicionais: [
    { codigo: "CLIENTES", preco: 29.9 },
    { codigo: "ORCAMENTOS", preco: 29.9 },
    { codigo: "ORDENS", preco: 29.9 },
    { codigo: "AGENDA", preco: 29.9 },
  ],
  planos: [],
  combinacoes: null, // null = ainda nao sabemos: o servidor decide no cadastro
  local: true,
});

const CODIGO = /^[A-Z][A-Z0-9_]{1,30}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const numero = (valor) => (Number.isFinite(Number(valor)) && Number(valor) >= 0 ? Number(valor) : null);

export const nomeDoModulo = (codigo) => MODULOS.find((m) => m.codigo === codigo)?.nome ?? codigo;

/** A resposta do servidor, conferida. Qualquer coisa torta vira null (fica o padrao). */
export function configDoServidor(bruto) {
  const base = numero(bruto?.preco_base);
  if (!bruto?.ok || base === null) return null;
  const codigos = (lista) => (Array.isArray(lista) ? lista.map(String).filter((c) => CODIGO.test(c)) : []);
  const inteiro = (valor, padrao) => (Number.isInteger(Number(valor)) && Number(valor) > 0 ? Number(valor) : padrao);
  return {
    precoBase: base,
    diasTeste: inteiro(bruto.dias_teste, CONFIG_PADRAO.diasTeste),
    computadores: inteiro(bruto.computadores, CONFIG_PADRAO.computadores),
    base: codigos(bruto.base),
    adicionais: (Array.isArray(bruto.adicionais) ? bruto.adicionais : [])
      .filter((a) => CODIGO.test(String(a?.codigo)) && numero(a?.preco) !== null)
      .map((a) => ({ codigo: String(a.codigo), preco: numero(a.preco) })),
    planos: (Array.isArray(bruto.planos) ? bruto.planos : [])
      .filter((p) => UUID.test(String(p?.id)) && numero(p?.preco) !== null && String(p?.nome ?? "").trim())
      .map((p) => ({
        id: String(p.id),
        nome: String(p.nome).slice(0, 60),
        descricao: String(p.descricao ?? "").slice(0, 240),
        modulos: codigos(p.modulos),
        preco: numero(p.preco),
        precoCheio: numero(p.preco_cheio),
        promoRotulo: String(p.promo_rotulo ?? "").slice(0, 40),
        promoAte: /^\d{4}-\d{2}-\d{2}$/.test(String(p.promo_ate)) ? String(p.promo_ate) : "",
        destaque: p.destaque === true,
        assinavel: p.assinavel === true,
      })),
    combinacoes: new Set((Array.isArray(bruto.combinacoes) ? bruto.combinacoes : []).map(String)),
    local: false,
  };
}

/** A chave de uma combinacao: igual a do banco (ordem alfabetica, com "+"). */
export function chaveCombinacao(adicionais = []) {
  return [...new Set(adicionais.map((c) => String(c).trim().toUpperCase()).filter(Boolean))].sort().join("+");
}

/** So adicional a venda, sem repetir, na ordem da vitrine. */
export function adicionaisValidos(config, codigos = []) {
  const pedidos = new Set((codigos || []).map((c) => String(c).trim().toUpperCase()));
  return config.adicionais.map((a) => a.codigo).filter((c) => pedidos.has(c));
}

// --------------------------------------------------------------- o estado --
// plano = { config, escolha: { tipo: "montado", adicionais } | { tipo: "pronto", id }, cupom }

export function criarPlano(config = CONFIG_PADRAO, adicionais = []) {
  return { config, escolha: { tipo: "montado", adicionais: adicionaisValidos(config, adicionais) }, cupom: null };
}

export function comConfig(plano, config) {
  const escolha = plano.escolha.tipo === "pronto" && config.planos.some((p) => p.id === plano.escolha.id)
    ? plano.escolha
    : { tipo: "montado", adicionais: adicionaisValidos(config, plano.escolha.adicionais ?? []) };
  return { ...plano, config, escolha };
}

export function alternarAdicional(plano, codigo) {
  const atuais = plano.escolha.tipo === "montado" ? plano.escolha.adicionais : [];
  const novos = atuais.includes(codigo) ? atuais.filter((c) => c !== codigo) : [...atuais, codigo];
  return { ...plano, escolha: { tipo: "montado", adicionais: adicionaisValidos(plano.config, novos) }, cupom: null };
}

export function escolherPronto(plano, id) {
  if (!plano.config.planos.some((p) => p.id === id)) return plano;
  return { ...plano, escolha: { tipo: "pronto", id }, cupom: null };
}

/** O cupom conferido pelo servidor ({ codigo, descricao, plano }). */
export function aplicarCupom(plano, resposta) {
  const [cupomPlano] = configDoServidor({ ok: true, preco_base: 0, planos: [resposta?.plano] })?.planos ?? [];
  if (!resposta?.ok || !cupomPlano) return plano;
  return { ...plano, cupom: { codigo: String(resposta.codigo), descricao: String(resposta.descricao ?? ""), plano: cupomPlano } };
}

export function tirarCupom(plano) {
  return { ...plano, cupom: null };
}

export function codigoDeCupom(texto) {
  const codigo = String(texto ?? "").trim().toUpperCase();
  return /^[A-Z0-9_-]{3,32}$/.test(codigo) ? codigo : "";
}

// --------------------------------------------------------------- o resumo --
/**
 * O que o cupom de balcao mostra e o que vai no cadastro:
 * { tipo, nome, modulos, adicionais, linhas[{texto, valor, detalhe}], total, totalCheio, rotulo, ate,
 *   assinavel, pedido{plano, cupom, adicionais} }
 */
export function resumo(plano) {
  const { config } = plano;
  const pronto = plano.cupom?.plano
    ?? (plano.escolha.tipo === "pronto" ? config.planos.find((p) => p.id === plano.escolha.id) : null);

  if (pronto) {
    const linhas = [{ texto: pronto.nome, valor: pronto.preco, detalhe: pronto.modulos.map(nomeDoModulo).join(" · ") }];
    if (plano.cupom) linhas.push({ texto: `Cupom ${plano.cupom.codigo}`, valor: null, detalhe: plano.cupom.descricao });
    return {
      tipo: plano.cupom ? "cupom" : "pronto",
      nome: pronto.nome,
      modulos: pronto.modulos,
      adicionais: pronto.modulos.filter((c) => config.adicionais.some((a) => a.codigo === c)),
      linhas,
      total: pronto.preco,
      totalCheio: pronto.precoCheio,
      rotulo: pronto.precoCheio ? pronto.promoRotulo : "",
      ate: pronto.precoCheio ? pronto.promoAte : "",
      assinavel: pronto.assinavel,
      pedido: plano.cupom ? { plano: null, cupom: plano.cupom.codigo, adicionais: [] }
                          : { plano: pronto.id, cupom: "", adicionais: [] },
    };
  }

  const adicionais = plano.escolha.adicionais ?? [];
  const precoDe = (codigo) => config.adicionais.find((a) => a.codigo === codigo)?.preco ?? 0;
  const linhas = [
    { texto: "Plano base", valor: config.precoBase, detalhe: config.base.map(nomeDoModulo).join(" · ") },
    ...adicionais.map((codigo) => ({ texto: `+ ${nomeDoModulo(codigo)}`, valor: precoDe(codigo), detalhe: "" })),
  ];
  const total = Math.round(linhas.reduce((soma, l) => soma + (l.valor ?? 0), 0) * 100) / 100;
  return {
    tipo: "montado",
    nome: adicionais.length ? `Plano base + ${adicionais.map(nomeDoModulo).join(", ")}` : "Plano base",
    modulos: [...config.base, ...adicionais],
    adicionais,
    linhas,
    total,
    totalCheio: null,
    rotulo: "",
    ate: "",
    assinavel: config.combinacoes === null || config.combinacoes.has(chaveCombinacao(adicionais)),
    pedido: { plano: null, cupom: "", adicionais },
  };
}

// compatibilidade com quem so quer o numero
export const valorDoMes = (plano) => resumo(plano).total;
export const assinavel = (plano) => resumo(plano).assinavel;

export function dinheiro(valor) {
  return Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** "R$ 89,90" -> partes para desenhar o preco grande: { inteiro: "89", centavos: "90" }. */
export function partesDoPreco(valor) {
  const [inteiro, centavos] = Number(valor || 0).toFixed(2).split(".");
  return { inteiro: Number(inteiro).toLocaleString("pt-BR"), centavos };
}

/**
 * Quem chegou: novo (visitante), mensal (teste ou assinante) ou vitalicio.
 * O vitalicio nunca e empurrado para a mensalidade: a pagina mostra o WhatsApp.
 */
export function perfil(cliente) {
  const tipo = String(cliente?.tipo || "");
  if (tipo === "vitalicia") return "vitalicio";
  if (tipo === "assinatura" || tipo === "teste") return "mensal";
  return "novo";
}

/** O plano que ja vem marcado: o do assinante; teste e visitante escolhem. */
export function adicionaisDoCliente(cliente, config = CONFIG_PADRAO) {
  return cliente?.tipo === "assinatura" ? adicionaisValidos(config, cliente.produtos) : [];
}

/** Confere o formulario antes de ir ao servidor. Devolve a mensagem, ou "". */
export function problemaNoCadastro({ nome = "", email = "", whatsapp = "" } = {}) {
  if (!String(nome).trim()) return "Conte para a gente o seu nome ou o da sua empresa.";
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(String(email).trim())) {
    return "Confira o e-mail: é por ele que a sua chave chega.";
  }
  const digitos = String(whatsapp).replace(/\D/g, "");
  if (digitos && digitos.length < 10) return "Confira o WhatsApp: coloque o DDD e o número.";
  return "";
}
