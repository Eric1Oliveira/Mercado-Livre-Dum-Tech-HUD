// node --test landingpage/tests/pagamento.test.mjs

import test from "node:test";
import assert from "node:assert/strict";

import { enderecoDasFuncoes, guardarPedido, lerVolta, pedidoGuardado } from "../js/pagamento.js";

const PEDIDO = "2f1b7c1e-9a4d-4c3b-8e2f-0a1b2c3d4e5f";
const SEGREDO = "q".repeat(43);

function armazemDeMentira() {
  const dados = new Map();
  return {
    getItem: (k) => (dados.has(k) ? dados.get(k) : null),
    setItem: (k, v) => dados.set(k, String(v)),
    removeItem: (k) => dados.delete(k),
  };
}

test("volta da InfinitePay: com & ou com ? no meio, cada valor sai inteiro", () => {
  const certo = `https://loja/pedido/?p=${PEDIDO}&s=${SEGREDO}&receipt_url=https%3A%2F%2Frecibo.infinitepay.io%2F1&order_nsu=${PEDIDO}&slug=abc123&capture_method=pix&transaction_nsu=b6f8d1c2-0000-4000-8000-000000000001`;
  const torto = certo.replace("&receipt_url", "?receipt_url");
  for (const endereco of [certo, torto]) {
    assert.deepEqual(lerVolta(endereco), {
      pedido: PEDIDO, segredo: SEGREDO, transacao: "b6f8d1c2-0000-4000-8000-000000000001",
      fatura: "abc123", metodo: "pix", recibo: "https://recibo.infinitepay.io/1",
    });
  }
});

test("volta: lixo na URL nunca vira dado", () => {
  const r = lerVolta(`https://loja/pedido/?p=<script>&s=curto&receipt_url=javascript:alert(1)&slug=a"b`);
  assert.deepEqual(r, { pedido: "", segredo: "", transacao: "", fatura: "", metodo: "", recibo: "" });
  // sem ?p=, o order_nsu da InfinitePay serve
  assert.equal(lerVolta(`https://loja/pedido/?order_nsu=${PEDIDO}`).pedido, PEDIDO);
});

test("segredo guardado por pedido, o mais recente primeiro, vence em 30 dias", () => {
  const armazem = armazemDeMentira();
  const outro = "11111111-2222-4333-8444-555555555555";
  assert.ok(guardarPedido(armazem, PEDIDO, SEGREDO, new Date("2026-09-01")));
  assert.ok(guardarPedido(armazem, outro, "w".repeat(43), new Date("2026-09-10")));

  assert.deepEqual(pedidoGuardado(armazem, PEDIDO, new Date("2026-09-13")), { pedido: PEDIDO, segredo: SEGREDO });
  assert.equal(pedidoGuardado(armazem, "", new Date("2026-09-13")).pedido, outro);
  assert.equal(pedidoGuardado(armazem, PEDIDO, new Date("2026-10-15")), null);

  assert.ok(!guardarPedido(armazem, "nao-e-uuid", SEGREDO));
  assert.ok(!guardarPedido(null, PEDIDO, SEGREDO));
});

test("endereco das funcoes sai do endereco do banco", () => {
  assert.equal(enderecoDasFuncoes("https://x.supabase.co/rest/v1"), "https://x.supabase.co/functions/v1");
  assert.equal(enderecoDasFuncoes("http://127.0.0.1:54999/rest/v1/"), "http://127.0.0.1:54999/functions/v1");
});
