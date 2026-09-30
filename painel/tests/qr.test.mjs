// O QR do segundo fator, em todos os formatos que o Supabase ja mandou.
//
//     node --test tests/qr.test.mjs

import test from "node:test";
import assert from "node:assert/strict";

import { imagemDoQr } from "../js/qr.js";

const SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="29" height="29"><rect fill="#FFFFFF" width="29" height="29"/><path fill="#000000" d="M0 0h7v7H0z"/></svg>';

/** O que o navegador realmente carregaria. */
function conteudo(endereco) {
  const virgula = endereco.indexOf(",");
  return decodeURIComponent(endereco.slice(virgula + 1));
}

test("SVG cru vira endereco que o <img> entende", () => {
  const endereco = imagemDoQr(SVG);
  assert.ok(endereco.startsWith("data:image/svg+xml;charset=utf-8,"), endereco.slice(0, 40));
  assert.equal(conteudo(endereco), SVG);
});

test("o # das cores nao corta o desenho", () => {
  // era isto que quebrava: um `#` solto faz o navegador jogar fora o resto
  const endereco = imagemDoQr(SVG);
  assert.doesNotMatch(endereco.slice(endereco.indexOf(",")), /#/);
  assert.match(conteudo(endereco), /#000000/);
});

test("data: com o SVG dentro continua funcionando", () => {
  assert.equal(conteudo(imagemDoQr(`data:image/svg+xml;utf-8,${SVG}`)), SVG);
  assert.equal(conteudo(imagemDoQr(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(SVG)}`)), SVG);
});

test("PNG em base64 passa direto", () => {
  const png = "data:image/png;base64,iVBORw0KGgo=";
  assert.equal(imagemDoQr(png), png);
});

test("sem desenho devolve vazio (a tela mostra a chave escrita)", () => {
  for (const valor of ["", null, undefined, "   ", "otpauth://totp/DumTech:eu?secret=ABC", "data:image/svg+xml"]) {
    assert.equal(imagemDoQr(valor), "", String(valor));
  }
});

test("porcentagem solta nao derruba o cadastro", () => {
  const endereco = imagemDoQr("data:image/svg+xml;utf-8,%<svg/>");
  assert.ok(endereco.startsWith("data:image/svg+xml;charset=utf-8,"));
});
