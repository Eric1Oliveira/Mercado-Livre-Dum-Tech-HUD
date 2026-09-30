// node --test supabase/functions/tests/checkout.test.mjs

import test from "node:test";
import assert from "node:assert/strict";

import {
  API_INFINITEPAY, cabecalhosCors, conferirPagamento, criar, hashSegredo, montarLink,
  novoSegredo, rotaDe, segredoValido, status, telefoneInternacional, webhook,
} from "../checkout/nucleo.ts";

const PEDIDO = "2f1b7c1e-9a4d-4c3b-8e2f-0a1b2c3d4e5f";
const json = (corpo, codigo = 200) => new Response(JSON.stringify(corpo), { status: codigo });

/** Uma InfinitePay e um banco de mentira, que anotam tudo o que receberam. */
function ambienteFalso({ pago = true, amount = 34800, link = { url: "https://checkout.infinitepay.io/eric/abc" }, banco = {} } = {}) {
  const chamadas = { infinite: [], rpc: [] };
  return {
    chamadas,
    handle: "dumtechsolutions",
    site: "https://dumtechsolution.com",
    webhook: "https://x.supabase.co/functions/v1/checkout/webhook",
    buscar: async (url, init) => {
      const corpo = JSON.parse(init.body);
      chamadas.infinite.push({ url, corpo });
      if (url.endsWith("/links")) return link ? json(link) : json({ erro: "x" }, 422);
      return json({ success: true, paid: pago, amount, paid_amount: amount + 120, installments: 1, capture_method: "pix" });
    },
    rpc: async (funcao, parametros) => {
      chamadas.rpc.push({ funcao, parametros });
      const resposta = banco[funcao];
      return typeof resposta === "function" ? resposta(parametros) : resposta ?? { ok: true };
    },
  };
}

const PREPARADO = {
  ok: true, pedido: PEDIDO, nome: "Padaria Pão de Ouro", email: "a@b.com", telefone: "(11) 97804-2160",
  itens: [{ nome: "DumTech Estoque", preco: 249 }, { nome: "DumTech Vendas", preco: "99.00" }],
  total: 348, total_centavos: 34800,
};

test("segredo: forte, formato de URL, hash hex de 64", async () => {
  const s = novoSegredo();
  assert.ok(segredoValido(s));
  assert.notEqual(s, novoSegredo());
  assert.match(await hashSegredo(s), /^[0-9a-f]{64}$/);
  assert.ok(!segredoValido("curto"));
  assert.ok(!segredoValido("x".repeat(43) + "&"));
});

test("telefone vai no formato da InfinitePay ou nao vai", () => {
  assert.equal(telefoneInternacional("(11) 97804-2160"), "+5511978042160");
  assert.equal(telefoneInternacional("5511978042160"), "+5511978042160");
  assert.equal(telefoneInternacional("1133334444"), "+551133334444");
  assert.equal(telefoneInternacional("123"), "");
  assert.equal(telefoneInternacional("441234567890"), "");
});

test("link: itens em centavos do banco, pedido, volta com segredo e webhook", () => {
  const corpo = montarLink(PREPARADO, ambienteFalso(), "SEGREDO");
  assert.equal(corpo.handle, "dumtechsolutions");
  assert.deepEqual(corpo.items, [
    { description: "DumTech Estoque", quantity: 1, price: 24900 },
    { description: "DumTech Vendas", quantity: 1, price: 9900 },
  ]);
  assert.equal(corpo.order_nsu, PEDIDO);
  assert.equal(corpo.redirect_url, `https://dumtechsolution.com/pedido/?p=${PEDIDO}&s=SEGREDO`);
  assert.equal(corpo.webhook_url, "https://x.supabase.co/functions/v1/checkout/webhook");
  assert.deepEqual(corpo.customer, { name: "Padaria Pão de Ouro", email: "a@b.com", phone_number: "+5511978042160" });
});

test("link: soma dos itens diferente do total vira um item so com o total", () => {
  const corpo = montarLink({ ...PREPARADO, total_centavos: 69900 }, ambienteFalso(), "S");
  assert.deepEqual(corpo.items, [{ description: "Kit DumTech Hub", quantity: 1, price: 69900 }]);
});

test("conferir: so paid true com valor conta; amount (sem juros) manda", async () => {
  assert.deepEqual(await conferirPagamento(ambienteFalso(), { pedido: PEDIDO, transacao: "t", fatura: "f" }),
                   { pago: true, centavos: 34800, metodo: "pix" });
  assert.equal((await conferirPagamento(ambienteFalso({ pago: false }), { pedido: PEDIDO, transacao: "t", fatura: "f" })).pago, false);
  const erro = { ...ambienteFalso(), buscar: async () => json({}, 500) };
  assert.equal((await conferirPagamento(erro, { pedido: PEDIDO, transacao: "t", fatura: "f" })).pago, false);
});

test("criar: prepara, cria o link, grava so o hash do segredo", async () => {
  const amb = ambienteFalso({ banco: { dumtech_checkout_preparar: PREPARADO } });
  const r = await criar(amb, { pedido: PEDIDO });
  assert.equal(r.status, 200);
  assert.equal(r.corpo.url, "https://checkout.infinitepay.io/eric/abc");
  assert.ok(segredoValido(r.corpo.segredo));
  const registro = amb.chamadas.rpc.find((c) => c.funcao === "dumtech_checkout_registrar");
  assert.equal(registro.parametros.p_segredo_hash, await hashSegredo(r.corpo.segredo));
  assert.ok(!JSON.stringify(registro).includes(r.corpo.segredo), "o segredo em si nao pode ir para o banco");
  assert.equal(amb.chamadas.infinite[0].url, `${API_INFINITEPAY}/links`);
});

test("criar: pedido recusado pelo banco ou InfinitePay fora do ar nao abre nada", async () => {
  const recusado = ambienteFalso({ banco: { dumtech_checkout_preparar: { ok: false, erro: "checkout_ja_criado" } } });
  const r1 = await criar(recusado, { pedido: PEDIDO });
  assert.equal(r1.status, 409);
  assert.equal(recusado.chamadas.infinite.length, 0);

  const fora = ambienteFalso({ link: null, banco: { dumtech_checkout_preparar: PREPARADO } });
  const r2 = await criar(fora, { pedido: PEDIDO });
  assert.equal(r2.status, 502);
  assert.ok(!fora.chamadas.rpc.some((c) => c.funcao === "dumtech_checkout_registrar"));

  assert.equal((await criar(ambienteFalso(), { pedido: "1; drop table" })).status, 400);
});

test("webhook: confere na InfinitePay antes de confirmar, com o valor dela", async () => {
  const amb = ambienteFalso({ amount: 34800 });
  const r = await webhook(amb, {
    order_nsu: PEDIDO, transaction_nsu: "b6f8d1c2-0000-4000-8000-000000000001", invoice_slug: "abc123",
    amount: 1, paid_amount: 1, capture_method: "pix", receipt_url: "https://recibo/1",
  });
  assert.equal(r.status, 200);
  assert.equal(amb.chamadas.infinite[0].url, `${API_INFINITEPAY}/payment_check`);
  assert.deepEqual(amb.chamadas.infinite[0].corpo, {
    handle: "dumtechsolutions", order_nsu: PEDIDO, transaction_nsu: "b6f8d1c2-0000-4000-8000-000000000001", slug: "abc123",
  });
  const confirmar = amb.chamadas.rpc.find((c) => c.funcao === "dumtech_checkout_confirmar");
  // o valor do corpo do webhook (1 centavo) e ignorado: vale o da consulta
  assert.equal(confirmar.parametros.p_centavos, 34800);
});

test("webhook falso: nao confirma nada e pede repeticao; lixo e ignorado", async () => {
  const amb = ambienteFalso({ pago: false });
  const r = await webhook(amb, { order_nsu: PEDIDO, transaction_nsu: "tx", invoice_slug: "s", paid_amount: 999999 });
  assert.equal(r.status, 400);
  assert.ok(!amb.chamadas.rpc.length, "aviso nao confirmado chegou ao banco");

  const lixo = ambienteFalso();
  assert.equal((await webhook(lixo, { order_nsu: "qualquer", transaction_nsu: "x" })).status, 200);
  assert.equal(lixo.chamadas.infinite.length, 0);
});

test("status: segredo errado nao ve; voltou antes do webhook confirma daqui", async () => {
  const segredo = novoSegredo();
  const hash = await hashSegredo(segredo);
  let pago = false;
  const amb = ambienteFalso({
    banco: {
      dumtech_checkout_situacao: (p) => p.p_segredo_hash !== hash ? { ok: false }
        : { ok: true, pagamento: pago ? "pago" : "aguardando", entregue: pago, chave: pago ? "AAAA-BBBB-CCCC-DDDD" : null },
      dumtech_checkout_confirmar: () => { pago = true; return { ok: true, entregue: true }; },
    },
  });

  assert.equal((await status(amb, { pedido: PEDIDO, segredo: novoSegredo() })).status, 404);

  const semVolta = await status(amb, { pedido: PEDIDO, segredo });
  assert.equal(semVolta.corpo.pagamento, "aguardando");
  assert.equal(amb.chamadas.infinite.length, 0, "sem transacao nao pergunta a InfinitePay");

  const voltou = await status(amb, { pedido: PEDIDO, segredo, transacao: "tx-1", fatura: "abc" });
  assert.equal(voltou.corpo.pagamento, "pago");
  assert.equal(voltou.corpo.chave, "AAAA-BBBB-CCCC-DDDD");
});

test("rotas e CORS", () => {
  assert.equal(rotaDe("/functions/v1/checkout/criar"), "criar");
  assert.equal(rotaDe("/checkout/webhook/"), "webhook");
  assert.equal(rotaDe("/checkout/status"), "status");
  assert.equal(rotaDe("/checkout"), "");
  const site = "https://dumtechsolution.com";
  assert.equal(cabecalhosCors(site, site)["Access-Control-Allow-Origin"], site);
  assert.equal(cabecalhosCors(site, "http://127.0.0.1:5192")["Access-Control-Allow-Origin"], "http://127.0.0.1:5192");
  assert.equal(cabecalhosCors(site, "https://golpe.com")["Access-Control-Allow-Origin"], site);
});

// ------------------------------------------------------- chave por e-mail ---
import { mandarChave } from "../checkout/nucleo.ts";

const DADOS_DA_CHAVE = { ok: true, nome: "Maria Souza", email: "maria@loja.com.br",
                         chave: "ABCD-EFGH-IJKL-MNOP", modulos: ["DumTech Vendas"] };

function comCorreio(ambiente, { aceita = true } = {}) {
  const cartas = [];
  ambiente.enviarEmail = async (carta) => { cartas.push(carta); return aceita; };
  return cartas;
}

test("pagamento confirmado pelo aviso: a chave vai por e-mail", async () => {
  const amb = ambienteFalso({ banco: { dumtech_checkout_reservar_email: DADOS_DA_CHAVE } });
  const cartas = comCorreio(amb);
  const r = await webhook(amb, { order_nsu: PEDIDO, transaction_nsu: "T1", invoice_slug: "F1" });
  assert.equal(r.corpo.ok, true);
  assert.equal(cartas.length, 1);
  assert.equal(cartas[0].para, "maria@loja.com.br");
  assert.match(cartas[0].texto, /ABCD-EFGH-IJKL-MNOP/);
  const fim = amb.chamadas.rpc.find((c) => c.funcao === "dumtech_checkout_email_resultado");
  assert.deepEqual(fim.parametros, { p_pedido: PEDIDO, p_enviado: true });
});

test("ja enviado (ou outro caminho mandando): nao manda de novo", async () => {
  const amb = ambienteFalso({ banco: { dumtech_checkout_reservar_email: { ok: false } } });
  const cartas = comCorreio(amb);
  assert.equal(await mandarChave(amb, PEDIDO), false);
  assert.equal(cartas.length, 0);
  assert.ok(!amb.chamadas.rpc.some((c) => c.funcao === "dumtech_checkout_email_resultado"));
});

test("o servico de e-mail recusou: a reserva e solta para tentar de novo", async () => {
  const amb = ambienteFalso({ banco: { dumtech_checkout_reservar_email: DADOS_DA_CHAVE } });
  comCorreio(amb, { aceita: false });
  assert.equal(await mandarChave(amb, PEDIDO), false);
  const fim = amb.chamadas.rpc.find((c) => c.funcao === "dumtech_checkout_email_resultado");
  assert.deepEqual(fim.parametros, { p_pedido: PEDIDO, p_enviado: false });
});

test("sem e-mail configurado, a confirmacao do pagamento segue normal", async () => {
  const amb = ambienteFalso({ banco: { dumtech_checkout_reservar_email: DADOS_DA_CHAVE } });
  const r = await webhook(amb, { order_nsu: PEDIDO, transaction_nsu: "T2", invoice_slug: "F2" });
  assert.equal(r.corpo.ok, true);
  assert.ok(!amb.chamadas.rpc.some((c) => c.funcao === "dumtech_checkout_reservar_email"));
});

test("a pagina do pedido tambem dispara o envio (pedido pago antes desta versao)", async () => {
  const segredo = "s".repeat(43);
  const amb = ambienteFalso({ banco: {
    dumtech_checkout_situacao: { ok: true, pagamento: "pago", entregue: true, chave: "ABCD-EFGH-IJKL-MNOP" },
    dumtech_checkout_reservar_email: DADOS_DA_CHAVE,
  } });
  const cartas = comCorreio(amb);
  const r = await status(amb, { pedido: PEDIDO, segredo });
  assert.equal(r.corpo.entregue, true);
  assert.equal(cartas.length, 1);
});
