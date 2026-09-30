// node --test painel/tests/relatorio.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { desde, grupoDoPedido, porCupom, porKit, totais } from "../js/relatorio.js";

const kit = (codigo) => [{ tipo: "combo", codigo }];
const avulso = [{ tipo: "produto", codigo: "VENDAS" }];

const PEDIDOS = [
  { itens: kit("COMERCIO"), total: 119.9, pagamento: "pago", pago_valor: 119.9 },
  { itens: kit("COMERCIO"), total: 119.9, pagamento: "aguardando" },
  { itens: kit("COMPLETO"), total: 206.91, subtotal: 229.9, desconto: 22.99, cupom: "PRIMEIRA10",
    pagamento: "pago", pago_valor: 206.91 },
  { itens: avulso, total: 49.9, pagamento: "pago" },
  { itens: avulso, total: 49.9, cupom: "PRIMEIRA10", pagamento: "aguardando" },
];

test("o grupo do pedido: kit ou avulso", () => {
  assert.equal(grupoDoPedido({ itens: kit("GESTAO") }), "GESTAO");
  assert.equal(grupoDoPedido({ itens: avulso }), "AVULSO");
  assert.equal(grupoDoPedido({}), "AVULSO");
});

test("por kit: pedidos, vendas, conversao e receita", () => {
  const linhas = porKit(PEDIDOS);
  const comercio = linhas.find((l) => l.chave === "COMERCIO");
  assert.deepEqual([comercio.pedidos, comercio.pagos, comercio.conversao, comercio.receita], [2, 1, 50, 119.9]);
  assert.equal(linhas[0].chave, "COMPLETO");          // quem mais fatura vem primeiro
});

test("por cupom: so pedidos com cupom, desconto concedido", () => {
  const [primeira] = porCupom(PEDIDOS);
  assert.equal(primeira.chave, "PRIMEIRA10");
  assert.deepEqual([primeira.pedidos, primeira.pagos, primeira.desconto], [2, 1, 22.99]);
});

test("totais do periodo sem erro de centavo", () => {
  const t = totais(PEDIDOS);
  assert.equal(t.pedidos, 5);
  assert.equal(t.pagos, 3);
  assert.equal(t.receita, 376.71);
  assert.equal(t.ticket, 125.57);
});

test("data de corte", () => {
  assert.equal(desde(30, new Date("2026-09-30T12:00:00Z")), "2026-08-31");
  assert.equal(desde(0), "");
});
