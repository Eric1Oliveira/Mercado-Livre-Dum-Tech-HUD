// Testes da formatacao do painel.
//
//     node --test tests/formato.test.mjs

import test from "node:test";
import assert from "node:assert/strict";

import {
  contagem, data, dataHora, dinheiro, documento, iniciais, numero, quando,
  situacao, telefone,
} from "../js/formato.js";

test("dinheiro em real", () => {
  assert.match(dinheiro(699), /699,00/);
  assert.match(dinheiro(0), /0,00/);
  assert.match(dinheiro(null), /0,00/);
});

test("data do jeito daqui", () => {
  assert.equal(data("2026-09-12"), "12/09/2026");
  assert.equal(data(""), "—");
  assert.equal(data("nao e data"), "—", "data invalida nao vira Invalid Date na tela");
});

test("data com hora", () => {
  assert.match(dataHora("2026-09-12T15:30:00Z"), /12\/09\/2026/);
  assert.equal(dataHora(null), "—");
});

test("quando: o tempo como gente fala", () => {
  const hoje = new Date("2026-09-12T10:00:00");
  assert.equal(quando("2026-09-12", hoje), "hoje");
  assert.equal(quando("2026-09-11", hoje), "ontem");
  assert.equal(quando("2026-09-07", hoje), "há 5 dias");
  assert.equal(quando("2026-09-13", hoje), "amanhã");
  assert.equal(quando("2026-09-24", hoje), "em 12 dias");
  assert.equal(quando(null, hoje), "nunca");
});

test("contagem nao escreve cliente(s)", () => {
  assert.equal(contagem(1, "cliente"), "1 cliente");
  assert.equal(contagem(2, "cliente"), "2 clientes");
  assert.equal(contagem(0, "cliente"), "0 clientes");
  assert.equal(contagem(3, "licença", "licenças"), "3 licenças");
});

test("iniciais para o avatar", () => {
  assert.equal(iniciais("Joao da Silva"), "JS");
  assert.equal(iniciais("Joao"), "J");
  assert.equal(iniciais("  "), "?");
  assert.equal(iniciais(null), "?");
});

test("situacao vira rotulo e tom", () => {
  assert.deepEqual(situacao("ativa"), { texto: "Ativa", tom: "ok" });
  assert.deepEqual(situacao("expirada"), { texto: "Vencida", tom: "ruim" });
  assert.equal(situacao(null).texto, "Sem licença");
});

test("telefone e documento legiveis", () => {
  assert.equal(telefone("63999990000"), "(63) 99999-0000");
  assert.equal(telefone("6333330000"), "(63) 3333-0000");
  assert.equal(telefone("123"), "123", "o que nao reconhece volta como veio");
  assert.equal(documento("00000000000"), "000.000.000-00");
  assert.equal(documento("00000000000191"), "00.000.000/0001-91");
  assert.equal(documento(""), "");
});

test("numero com separador", () => {
  assert.equal(numero(1234), "1.234");
  assert.equal(numero(null), "0");
});
