// node --test supabase/functions/tests/enviar-chave.test.mjs

import test from "node:test";
import assert from "node:assert/strict";

import { cabecalhosCors, emailValido, montarEmail, uuidValido } from "../enviar-chave/nucleo.ts";

test("valida o que chega", () => {
  assert.ok(uuidValido("2f1b7c1e-9a4d-4c3b-8e2f-0a1b2c3d4e5f"));
  assert.ok(!uuidValido("2f1b7c1e; drop table"));
  assert.ok(emailValido("a@b.com"));
  assert.ok(!emailValido("sem arroba"));
});

test("e-mail traz a chave, os modulos e como ativar", () => {
  const { assunto, texto, html } = montarEmail({
    nome: "Padaria Pão de Ouro", chave: "7K4M-9QX2-BT5H-3DWZ",
    modulos: ["DumTech Estoque", "DumTech Vendas"], max_computadores: 2, expira_em: "2027-03-31",
  });
  assert.equal(assunto, "Sua licença DumTech está pronta");
  assert.match(texto, /Chave: 7K4M-9QX2-BT5H-3DWZ/);
  assert.match(texto, /Válida até: 31\/03\/2027/);
  assert.match(html, /7K4M-9QX2-BT5H-3DWZ/);
  assert.match(html, /Olá, Padaria!/);
});

test("nome do cliente vira texto no HTML, nunca marcacao", () => {
  const { html } = montarEmail({ nome: "<img src=x onerror=alert(1)>", chave: "<b>X</b>", modulos: ["<script>"] });
  assert.doesNotMatch(html, /<img src=x/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;b&gt;X&lt;\/b&gt;/);
});

test("CORS: aberto quando nao configurado, fechado para origem estranha", () => {
  assert.equal(cabecalhosCors("*", "https://qualquer.um")["Access-Control-Allow-Origin"], "*");
  assert.equal(cabecalhosCors("https://painel.dumtech.com.br", "https://painel.dumtech.com.br")["Access-Control-Allow-Origin"],
               "https://painel.dumtech.com.br");
  assert.equal(cabecalhosCors("https://painel.dumtech.com.br", "https://golpe.com")["Access-Control-Allow-Origin"], "null");
});
