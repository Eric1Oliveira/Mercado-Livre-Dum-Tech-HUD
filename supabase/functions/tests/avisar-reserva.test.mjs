// node --test supabase/functions/tests/avisar-reserva.test.mjs

import test from "node:test";
import assert from "node:assert/strict";

import { montarAviso, quando, uuidValido } from "../avisar-reserva/nucleo.ts";

const RESERVA = {
  email: "dono@loja.com", empresa: "Studio", servico: "Corte", inicio: "2026-11-05T14:30",
  nome: "Ana Souza", telefone: "11987654321",
};

test("so aceita id de reserva", () => {
  assert.ok(uuidValido("2f1b7c1e-9a4d-4c3b-8e2f-0a1b2c3d4e5f"));
  assert.ok(!uuidValido("2f1b7c1e; drop table"));
  assert.ok(!uuidValido(undefined));
});

test("data na forma que se le", () => {
  assert.equal(quando("2026-11-05T14:30"), "05/11 às 14:30");
});

test("e-mail diz quem, o que, quando e como falar", () => {
  const { assunto, texto, html } = montarAviso(RESERVA);
  assert.equal(assunto, "Novo agendamento: Corte em 05/11 às 14:30");
  assert.match(texto, /Ana Souza marcou Corte para 05\/11 às 14:30/);
  assert.match(texto, /\(11\) 98765-4321/);
  assert.match(html, /<strong>Ana Souza<\/strong>/);
});

test("o que veio do formulario vira texto, nunca marcacao", () => {
  const { html } = montarAviso({ ...RESERVA, nome: "<img src=x onerror=alert(1)>", servico: "<script>" });
  assert.doesNotMatch(html, /<img src=x/);
  assert.doesNotMatch(html, /<script>/);
});
