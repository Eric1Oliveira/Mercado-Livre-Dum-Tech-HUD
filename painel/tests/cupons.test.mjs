// node --test painel/tests/cupons.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { codigoDeCupom, linkDoCupom, problemaDoCupom } from "../js/cupons.js";

test("codigo: maiusculo, sem acento, sem espaco", () => {
  assert.equal(codigoDeCupom("primeira 10"), "PRIMEIRA10");
  assert.equal(codigoDeCupom("João-Revenda!"), "JOAO-REVENDA");
});

test("regras", () => {
  const base = { codigo: "PRIMEIRA10", tipo: "percentual", valor: 10, usos_max: null, minimo: 0 };
  assert.equal(problemaDoCupom(base), "");
  assert.match(problemaDoCupom({ ...base, valor: 95 }), /90%/);
  assert.match(problemaDoCupom({ ...base, valor: 0 }), /maior que zero/);
  assert.match(problemaDoCupom({ ...base, codigo: "X" }), /código/);
  assert.match(problemaDoCupom({ ...base, usos_max: 0 }), /Limite/);
  assert.equal(problemaDoCupom({ ...base, tipo: "valor", valor: 150 }), "");
});

test("link com o cupom", () => {
  assert.equal(linkDoCupom("https://loja.com/", "PARCEIRO20"), "https://loja.com/?cupom=PARCEIRO20");
});
