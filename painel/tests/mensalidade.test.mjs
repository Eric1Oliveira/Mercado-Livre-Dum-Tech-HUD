// A regra das telas da mensalidade no painel (sem DOM, sem rede).
//
//     cd painel && npm test

import test from "node:test";
import assert from "node:assert/strict";

import {
  chaveCombinacao, descreverEvento, linkDoCupom, mudancasDaFicha, problemaDoAviso, problemaDoCupom,
  problemaDoPlano, situacaoDoAviso, todasAsCombinacoes, totalDaCombinacao,
} from "../js/mensalidade.js";

const sem = (texto) => String(texto).replace(/ /g, " ");

test("a chave da combinacao e a mesma do banco", () => {
  assert.equal(chaveCombinacao(["ORDENS", "agenda", "ORDENS"]), "AGENDA+ORDENS");
  assert.equal(chaveCombinacao([]), "");
});

test("todas as combinacoes do monte o seu, da menor para a maior", () => {
  const todas = todasAsCombinacoes(["CLIENTES", "AGENDA", "ORDENS"]);
  assert.equal(todas.length, 8);
  assert.deepEqual(todas[0], []);
  assert.deepEqual(todas.at(-1), ["CLIENTES", "AGENDA", "ORDENS"]);
  assert.ok(todas.findIndex((c) => c.length === 2) > todas.findIndex((c) => c.length === 1));
});

test("o total de uma combinacao: base + o preco de cada adicional", () => {
  const adicionais = [{ codigo: "AGENDA", preco: 39.9 }, { codigo: "ORDENS", preco: 29.9 }];
  assert.equal(totalDaCombinacao(89.9, adicionais, ["AGENDA", "ORDENS"]), 159.7);
  assert.equal(totalDaCombinacao(89.9, adicionais, []), 89.9);
});

test("o historico em portugues de gente", () => {
  const ajuste = descreverEvento({ tipo: "ajustou", detalhe: {
    modulos: { de: ["VENDAS"], para: ["AGENDA", "VENDAS"] }, valor: { de: 89.9, para: 99.9 },
    computadores: { de: 1, para: 2 }, anotacoes: true } });
  assert.match(ajuste.titulo, /Assinatura ajustada/);
  assert.match(sem(ajuste.detalhe), /entrou Agenda/);
  assert.match(sem(ajuste.detalhe), /valor de R\$ 89,90 para R\$ 99,90/);
  assert.match(ajuste.detalhe, /computadores de 1 para 2/);
  assert.match(ajuste.detalhe, /anotações/);
  assert.match(sem(descreverEvento({ tipo: "pediu", detalhe: { plano: "Salão", valor: 99.9, cupom: "PARCEIRO10" } }).titulo),
               /Pediu para assinar o plano Salão por R\$ 99,90 com o cupom PARCEIRO10/);
  assert.match(descreverEvento({ tipo: "falhou", detalhe: { ate: "2026-11-10" } }).titulo, /10\/11\/2026/);
  assert.equal(descreverEvento({ tipo: "qualquer" }).titulo, "qualquer");
});

test("a ficha manda so o que mudou", () => {
  const antes = { plano_id: null, modulos: ["VENDAS", "ESTOQUE"], valor_mensal: 89.9, max_computadores: 1,
                  expira_em: null, observacoes: "" };
  assert.deepEqual(mudancasDaFicha(antes, { plano: "", modulos: ["ESTOQUE", "VENDAS"], valor: 89.9,
                                            computadores: 1, ate: "", observacoes: "" }), {});
  assert.deepEqual(mudancasDaFicha(antes, { plano: "", modulos: ["VENDAS"], valor: 99.9, computadores: 2,
                                            ate: "", observacoes: "Ligar dia 5" }),
                   { modulos: ["VENDAS"], valor: 99.9, computadores: 2, observacoes: "Ligar dia 5" });
  const PLANO = "0b9c6a4e-5f1d-4c3b-9a8e-7d6c5b4a3f2e";
  assert.deepEqual(mudancasDaFicha(antes, { plano: PLANO, modulos: ["VENDAS"], valor: 89.9, computadores: 1,
                                            ate: "", observacoes: "" }), { plano: PLANO });
  assert.deepEqual(mudancasDaFicha({ ...antes, expira_em: "2026-11-10" },
                                   { plano: "", modulos: ["VENDAS", "ESTOQUE"], valor: 89.9, computadores: 1,
                                     ate: "2026-11-20", observacoes: "" }), { ate: "2026-11-20" });
});

test("o plano pronto e conferido antes de salvar", () => {
  const bom = { nome: "Salão", modulos: ["AGENDA"], preco: 79.9, link: "", promo_preco: null, promo_ate: "", promo_link: "" };
  assert.equal(problemaDoPlano(bom), "");
  assert.match(problemaDoPlano({ ...bom, nome: " " }), /nome/);
  assert.match(problemaDoPlano({ ...bom, modulos: [] }), /módulo/);
  assert.match(problemaDoPlano({ ...bom, preco: -1 }), /preço/);
  assert.match(problemaDoPlano({ ...bom, link: "http://x" }), /https/);
  assert.match(problemaDoPlano({ ...bom, promo_preco: 59.9 }), /até quando/);
  assert.match(problemaDoPlano({ ...bom, promo_preco: 99.9, promo_ate: "2026-12-01" }), /menor/);
});

test("faixa de aviso: situacao pelas datas", () => {
  const hoje = "2026-11-04";
  assert.equal(situacaoDoAviso({ ativo: true, inicio: "2026-11-01", fim: "2026-11-30" }, hoje), "no_ar");
  assert.equal(situacaoDoAviso({ ativo: true, inicio: "2026-11-10", fim: null }, hoje), "programado");
  assert.equal(situacaoDoAviso({ ativo: true, inicio: "2026-10-01", fim: "2026-10-31" }, hoje), "encerrado");
  assert.equal(situacaoDoAviso({ ativo: false, inicio: "2026-11-01" }, hoje), "desligado");
  assert.match(problemaDoAviso({ texto: "", link: "" }), /texto/);
  assert.match(problemaDoAviso({ texto: "Oi", link: "javascript:x" }), /link/);
  assert.equal(problemaDoAviso({ texto: "Oi", link: "#plano", inicio: "2026-11-01", fim: "" }), "");
  assert.match(problemaDoAviso({ texto: "Oi", link: "", inicio: "2026-11-10", fim: "2026-11-01" }), /fim/);
});

test("cupom: codigo, plano e o link pronto do parceiro", () => {
  assert.equal(problemaDoCupom({ codigo: "PARCEIRO10", plano_id: "x" }), "");
  assert.match(problemaDoCupom({ codigo: "a", plano_id: "x" }), /código/);
  assert.match(problemaDoCupom({ codigo: "PARCEIRO10", plano_id: "" }), /plano/);
  assert.equal(linkDoCupom("https://dumtechsolution.com/", "parceiro10"), "https://dumtechsolution.com/?cupom=PARCEIRO10#plano");
});
