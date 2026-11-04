// Testes do nucleo da Edge Function `mensalidade` (Node >= 23.6 roda .ts direto).
//
//     node --test supabase/functions/tests/mensalidade.test.mjs
//
// Sem rede e sem banco: o rpc e o e-mail entram como funcoes de mentira.

import test from "node:test";
import assert from "node:assert/strict";

import { admin, cadastro, cartas, rotaDe } from "../mensalidade/nucleo.ts";

const NOVA = {
  ok: true, caso: "nova", nome: "Padaria Pão de Ouro", email: "dono@padaria.com.br",
  chave: "7K4M-9QX2-BT5H-3DWZ", tipo: "teste", ate: "2026-11-10", dias_teste: 7,
  assinar: false, adicionais: [], valor: null, link: "",
};

function ambiente(respostaDoBanco, { email = true } = {}) {
  const chamadas = [];
  const enviados = [];
  return {
    chamadas, enviados,
    site: "https://dumtechsolution.com",
    whatsapp: "5511978042160",
    rpc: async (funcao, parametros) => { chamadas.push({ funcao, parametros }); return respostaDoBanco; },
    enviarEmail: email ? async (carta) => { enviados.push(carta); return true; } : undefined,
  };
}

const CORPO = { nome: "  Padaria Pão de Ouro ", email: "Dono@Padaria.com.br", whatsapp: "(11) 90000-0001",
                adicionais: ["ORDENS", "agenda"], assinar: false };

test("as rotas", () => {
  assert.equal(rotaDe("/functions/v1/mensalidade/cadastro"), "cadastro");
  assert.equal(rotaDe("/mensalidade/admin"), "admin");
  assert.equal(rotaDe("/mensalidade/qualquer"), "");
});

test("cadastro confere o que chega antes de ir ao banco", async () => {
  for (const [corpo, erro] of [
    [{ ...CORPO, nome: "  " }, "nome"],
    [{ ...CORPO, email: "nao-e-email" }, "email_invalido"],
    [{ ...CORPO, whatsapp: "123" }, "whatsapp"],
  ]) {
    const amb = ambiente(NOVA);
    const r = await cadastro(amb, corpo, "10.0.0.1");
    assert.equal(r.status, 400, JSON.stringify(r));
    assert.equal(r.corpo.erro, erro);
    assert.equal(amb.chamadas.length, 0, "foi ao banco com dado torto");
  }
});

test("cadastro novo: o banco recebe tudo limpo e a chave vai so por e-mail", async () => {
  const amb = ambiente(NOVA);
  const r = await cadastro(amb, CORPO, "10.0.0.1");
  assert.equal(r.status, 200);
  assert.deepEqual(amb.chamadas[0], {
    funcao: "dumtech_cadastrar_mensal",
    parametros: { p_nome: "Padaria Pão de Ouro", p_email: "dono@padaria.com.br", p_telefone: "11900000001",
                  p_adicionais: ["ORDENS", "AGENDA"], p_assinar: false, p_ip: "10.0.0.1",
                  p_plano: null, p_cupom: "" },
  });
  assert.ok(!JSON.stringify(r.corpo).includes(NOVA.chave), "a chave apareceu no navegador");
  assert.equal(amb.enviados.length, 1);
  assert.equal(amb.enviados[0].para, "dono@padaria.com.br");
  assert.ok(amb.enviados[0].texto.includes(NOVA.chave), "o e-mail nao leva a chave");
  assert.ok(amb.enviados[0].texto.includes("https://dumtechsolution.com/baixar/"), "sem o link para baixar");
  assert.ok(amb.enviados[0].texto.includes("10/11/2026"), "sem a data do fim do teste");
});

test("o navegador recebe a MESMA resposta para e-mail novo, repetido e vitalicio", async () => {
  const comAssinar = { ...NOVA, assinar: true, adicionais: ["AGENDA"], valor: 119.8, link: "https://loja.infinitepay.io/x" };
  const respostas = [];
  for (const caso of ["nova", "ja_tem", "vitalicio"]) {
    const amb = ambiente({ ...comAssinar, caso, chave: caso === "vitalicio" ? null : NOVA.chave });
    const r = await cadastro(amb, { ...CORPO, assinar: true }, "10.0.0.1");
    respostas.push(JSON.stringify(r));
  }
  assert.equal(new Set(respostas).size, 1, `respostas diferentes: ${respostas.join(" | ")}`);
  assert.equal(JSON.parse(respostas[0]).corpo.link, "https://loja.infinitepay.io/x");
});

test("cada caso recebe o e-mail certo", async () => {
  const deCada = {};
  for (const caso of ["nova", "ja_tem", "vitalicio"]) {
    const amb = ambiente({ ...NOVA, caso, chave: caso === "vitalicio" ? null : NOVA.chave });
    await cadastro(amb, CORPO, "10.0.0.1");
    deCada[caso] = amb.enviados[0];
  }
  assert.match(deCada.nova.assunto, /teste grátis/i);
  assert.ok(deCada.ja_tem.texto.includes(NOVA.chave), "reenvio sem a chave");
  assert.match(deCada.vitalicio.texto, /para sempre/);
  assert.match(deCada.vitalicio.texto, /não precisa assinar/);
  assert.ok(!/R\$/.test(deCada.vitalicio.texto), "vitalicio recebeu preco de mensalidade");
});

test("quem pediu para assinar recebe o plano, o valor e o link no e-mail", async () => {
  const amb = ambiente({ ...NOVA, assinar: true, adicionais: ["AGENDA", "ORDENS"], valor: 149.7,
                         link: "https://loja.infinitepay.io/dumtech/base-2" });
  await cadastro(amb, { ...CORPO, assinar: true }, "10.0.0.1");
  const texto = amb.enviados[0].texto;
  assert.ok(texto.includes("R$ 149,70"), texto);
  assert.ok(texto.includes("Agenda e Ordem de Serviço"), texto);
  assert.ok(texto.includes("https://loja.infinitepay.io/dumtech/base-2"), texto);

  // sem link para aquela quantidade: a gente chama no WhatsApp
  const semLink = ambiente({ ...NOVA, assinar: true, adicionais: [], valor: 89.9, link: "" });
  await cadastro(semLink, { ...CORPO, assinar: true }, "10.0.0.1");
  assert.match(semLink.enviados[0].texto, /WhatsApp/);
});

test("recusas do banco e falhas de e-mail viram texto de gente", async () => {
  let r = await cadastro(ambiente({ ok: false, erro: "muitas_tentativas", mensagem: "Espere um pouco." }), CORPO, "1.1.1.1");
  assert.equal(r.status, 429);
  assert.equal(r.corpo.mensagem, "Espere um pouco.");

  r = await cadastro(ambiente(null), CORPO, "1.1.1.1");
  assert.equal(r.status, 502);

  r = await cadastro(ambiente(NOVA, { email: false }), CORPO, "1.1.1.1");
  assert.equal(r.status, 501);

  const amb = ambiente(NOVA);
  amb.enviarEmail = async () => false;
  r = await cadastro(amb, CORPO, "1.1.1.1");
  assert.equal(r.status, 502);
  assert.match(r.corpo.mensagem, /e-mail/);
});

// --------------------------------------------------------------- painel --
const UUID = "0b9c6a4e-5f1d-4c3b-9a8e-7d6c5b4a3f2e";

function rpcDoEric(dados, status = 200) {
  const chamadas = [];
  const rpc = async (funcao, parametros) => { chamadas.push({ funcao, parametros }); return { status, dados }; };
  rpc.chamadas = chamadas;
  return rpc;
}

test("admin sem sessao e acao estranha sao recusados antes do banco", async () => {
  let r = await admin(ambiente(null), { acao: "confirmar", pedido: UUID }, null);
  assert.equal(r.status, 401);

  const rpc = rpcDoEric({ ok: true });
  r = await admin(ambiente(null), { acao: "apagar_tudo", pedido: UUID }, rpc);
  assert.equal(r.status, 400);
  r = await admin(ambiente(null), { acao: "confirmar", pedido: "nao-e-uuid" }, rpc);
  assert.equal(r.status, 400);
  assert.equal(rpc.chamadas.length, 0);
});

test("admin chama o banco com o token de quem chamou e manda o e-mail da acao", async () => {
  const casos = [
    ["confirmar", { pedido: UUID }, "dumtech_confirmar_assinatura", { p_pedido: UUID }, /confirmada/i],
    ["falhou", { licenca: UUID }, "dumtech_cobranca", { p_licenca: UUID, p_acao: "falhou", p_ate: null }, /confirmar a sua mensalidade/i],
    ["em_dia", { licenca: UUID }, "dumtech_cobranca", { p_licenca: UUID, p_acao: "em_dia", p_ate: null }, /em dia/i],
    ["cancelou", { licenca: UUID, ate: "2026-12-01" }, "dumtech_cobranca",
     { p_licenca: UUID, p_acao: "cancelou", p_ate: "2026-12-01" }, /encerrada/i],
    ["estender", { licenca: UUID, dias: 3 }, "dumtech_estender_teste_mensal", { p_licenca: UUID, p_dias: 3 }, /mais dias/i],
  ];
  for (const [acao, extra, funcao, parametros, assunto] of casos) {
    const amb = ambiente(null);
    const rpc = rpcDoEric({ ok: true, nome: "Padaria", email: "dono@padaria.com.br", chave: NOVA.chave,
                            ate: "2026-11-10", adicionais: ["AGENDA"], valor: 119.8, mudanca: false });
    const r = await admin(amb, { acao, ...extra }, rpc);
    assert.equal(r.status, 200, `${acao}: ${JSON.stringify(r)}`);
    assert.deepEqual(rpc.chamadas[0], { funcao, parametros }, acao);
    assert.equal(amb.enviados.length, 1, `${acao} sem e-mail`);
    assert.match(amb.enviados[0].assunto, assunto, acao);
    assert.equal(r.corpo.email_enviado, true);
  }
});

test("descartar nao manda e-mail; sem ser admin vira 403", async () => {
  const amb = ambiente(null);
  let r = await admin(amb, { acao: "descartar", pedido: UUID }, rpcDoEric({ ok: true }));
  assert.equal(r.status, 200);
  assert.equal(amb.enviados.length, 0);

  r = await admin(ambiente(null), { acao: "falhou", licenca: UUID },
                  rpcDoEric({ code: "42501", message: "Apenas a DumTech faz isso." }, 403));
  assert.equal(r.status, 403);

  r = await admin(ambiente(null), { acao: "falhou", licenca: UUID },
                  rpcDoEric({ ok: false, erro: "tipo", mensagem: "Só dá para marcar cobrança em licença de mensalidade." }));
  assert.equal(r.status, 400);
  assert.match(r.corpo.mensagem, /mensalidade/);
});

// ---------------------------------------------------------------- textos --
test("todo e-mail e amigavel: sem termo tecnico e com o contato da DumTech", () => {
  const dados = { nome: "Ana Maria", email: "a@b.com", chave: NOVA.chave, ate: "2026-11-10", dias_teste: 7,
                  assinar: true, adicionais: ["CLIENTES"], valor: 119.8, link: "https://loja.infinitepay.io/x",
                  mudanca: false };
  const amb = ambiente(null);
  const PROIBIDO = /licenca_id|token|rpc|erro interno|undefined|\[object/i;
  const QUEBRADO = /\bnull\b|\bNaN\b/; // "Financeiro" tem "nan": aqui a caixa importa
  for (const [nome, montar] of Object.entries(cartas)) {
    const carta = montar(dados, amb);
    assert.ok(carta.assunto && carta.texto && carta.html, nome);
    assert.ok(!PROIBIDO.test(carta.texto) && !QUEBRADO.test(carta.texto), `${nome} tem termo tecnico: ${carta.texto}`);
    assert.ok(carta.texto.startsWith("Olá, Ana!"), `${nome} nao cumprimenta pelo nome`);
    assert.ok(carta.texto.includes("(11) 97804-2160"), `${nome} sem o WhatsApp`);
  }
});

test("o HTML escapa o que vem de fora", () => {
  const carta = cartas.boasVindas({ ...NOVA, nome: "<script>alert(1)</script>" }, ambiente(null));
  assert.ok(!carta.html.includes("<script>alert"), "nome entrou sem escapar");
});


// ------------------------------------------------- planos, cupom e a ficha --
test("cadastro leva o plano pronto e o cupom, e recusa o que vem torto antes do banco", async () => {
  const amb = ambiente(NOVA);
  await cadastro(amb, { ...CORPO, assinar: true, plano: UUID, cupom: " parceiro10 " }, "10.0.0.1");
  assert.equal(amb.chamadas[0].parametros.p_plano, UUID);
  assert.equal(amb.chamadas[0].parametros.p_cupom, "PARCEIRO10");

  for (const [extra, erro] of [[{ plano: "nao-e-uuid" }, "plano"], [{ cupom: "<script>" }, "cupom"]]) {
    const torto = ambiente(NOVA);
    const r = await cadastro(torto, { ...CORPO, assinar: true, ...extra }, "10.0.0.1");
    assert.equal(r.status, 400, JSON.stringify(r));
    assert.equal(r.corpo.erro, erro);
    assert.equal(torto.chamadas.length, 0);
  }
});

test("o e-mail fala do plano pronto pelo nome e pelos modulos", async () => {
  const amb = ambiente({ ...NOVA, assinar: true, plano: "Salão", modulos: ["AGENDA", "CLIENTES", "FINANCEIRO"],
                         valor: 119.9, link: "https://loja.infinitepay.io/x" });
  await cadastro(amb, { ...CORPO, assinar: true, plano: UUID }, "10.0.0.1");
  assert.match(amb.enviados[0].texto, /plano Salão \(Agenda, Clientes e Financeiro\)/);
});

test("a ficha: ajustar, ativar e reabrir chamam o banco certo", async () => {
  const casos = [
    ["ajustar", { licenca: UUID, modulos: ["VENDAS", "AGENDA"], valor: 99.9, computadores: 2, ate: "2026-12-01", observacoes: "ok" },
     "dumtech_ajustar_assinatura",
     { p_licenca: UUID, p_plano: null, p_modulos: ["VENDAS", "AGENDA"], p_valor: 99.9, p_computadores: 2,
       p_ate: "2026-12-01", p_observacoes: "ok" }],
    ["ativar", { licenca: UUID, plano: UUID }, "dumtech_ativar_assinatura",
     { p_licenca: UUID, p_plano: UUID, p_modulos: null, p_valor: null }],
    ["reabrir", { licenca: UUID }, "dumtech_reabrir_assinatura", { p_licenca: UUID }],
  ];
  for (const [acao, extra, funcao, parametros] of casos) {
    const rpc = rpcDoEric({ ok: true, nome: "Padaria", email: "dono@padaria.com.br", valor: 99.9,
                            mudou: { valor: { de: 89.9, para: 99.9 } }, modulos: ["VENDAS"] });
    const r = await admin(ambiente(null), { acao, ...extra }, rpc);
    assert.equal(r.status, 200, `${acao}: ${JSON.stringify(r)}`);
    assert.deepEqual(rpc.chamadas[0], { funcao, parametros }, acao);
  }
});

test("avisar = false nao manda e-mail; ajuste so interno (anotacoes) tambem nao", async () => {
  let amb = ambiente(null);
  await admin(amb, { acao: "falhou", licenca: UUID, avisar: false },
              rpcDoEric({ ok: true, nome: "P", email: "p@x.com", ate: "2026-11-10" }));
  assert.equal(amb.enviados.length, 0);

  amb = ambiente(null);
  const r = await admin(amb, { acao: "ajustar", licenca: UUID, observacoes: "cliente antigo" },
                        rpcDoEric({ ok: true, nome: "P", email: "p@x.com", mudou: { anotacoes: true } }));
  assert.equal(amb.enviados.length, 0);
  assert.equal(r.corpo.email_enviado, false);

  amb = ambiente(null);
  await admin(amb, { acao: "ajustar", licenca: UUID, valor: 99.9 },
              rpcDoEric({ ok: true, nome: "P", email: "p@x.com", valor: 99.9, mudou: { valor: { de: 89.9, para: 99.9 } } }));
  assert.equal(amb.enviados.length, 1);
  assert.match(amb.enviados[0].texto, /R\$ 99,90/);
});

test("a ficha recusa dado torto antes do banco", async () => {
  for (const extra of [{ valor: -1 }, { valor: "muito" }, { computadores: 0 }, { ate: "amanha" },
                       { modulos: "VENDAS" }, { plano: "x" }]) {
    const rpc = rpcDoEric({ ok: true });
    const r = await admin(ambiente(null), { acao: "ajustar", licenca: UUID, ...extra }, rpc);
    assert.equal(r.status, 400, `${JSON.stringify(extra)}: ${JSON.stringify(r)}`);
    assert.equal(rpc.chamadas.length, 0);
  }
});
