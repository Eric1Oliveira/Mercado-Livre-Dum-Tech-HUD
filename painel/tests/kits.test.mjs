// node --test painel/tests/kits.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { avaliar, codigoDoNome, precoComDesconto, somaAvulsa } from "../js/kits.js";

const PRODUTOS = [
  { id: 1, codigo: "VENDAS", preco: 49.9 },
  { id: 2, codigo: "ESTOQUE", preco: 49.9 },
  { id: 3, codigo: "FINANCEIRO", preco: 49.9 },
  { id: 4, codigo: "CLIENTES", preco: 49.9 },
];

test("soma sem erro de centavo", () => {
  assert.equal(somaAvulsa(PRODUTOS, [1, 2, 3, 4]), 199.6);
  assert.equal(somaAvulsa(PRODUTOS, [1]), 49.9);
  assert.equal(somaAvulsa(PRODUTOS, []), 0);
});

test("desconto vira preco terminado em ,90 e nunca acima do pedido", () => {
  assert.equal(precoComDesconto(199.6, 10), 178.9);   // 179,64 -> 178,90
  assert.equal(precoComDesconto(199.6, 20), 158.9);   // 159,68 -> 158,90
  assert.equal(precoComDesconto(149.7, 0), 149.7 >= 149.9 ? 149.9 : 148.9);
  assert.ok(precoComDesconto(349.3, 30) <= 349.3 * 0.7);
});

test("o kit Gestao antigo e reprovado: mais caro que os avulsos", () => {
  const r = avaliar(PRODUTOS, [1, 2, 3, 4], 699);
  assert.match(r.problema, /nunca vai aplic/);
  assert.equal(r.economia, 0);
});

test("kit com desconto de verdade passa e mostra a economia", () => {
  const r = avaliar(PRODUTOS, [1, 2, 3, 4], 159.9);
  assert.equal(r.problema, "");
  assert.equal(r.soma, 199.6);
  assert.equal(r.economia, 39.7);
  assert.equal(r.porcento, 20);
});

test("kit de um modulo so nao existe", () => {
  assert.match(avaliar(PRODUTOS, [1], 40).problema, /dois m/);
});

test("codigo nasce do nome", () => {
  assert.equal(codigoDoNome("Kit Comércio"), "KIT_COMERCIO");
  assert.equal(codigoDoNome("  Oficina & Serviços! "), "OFICINA_SERVICOS");
  assert.equal(codigoDoNome("7 módulos"), "K_7_MODULOS");
});
