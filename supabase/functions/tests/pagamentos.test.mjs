// Testes do nucleo dos pagamentos protegidos (Node >= 23.6 roda .ts direto).
//
//     node --test supabase/functions/tests/pagamentos.test.mjs
//
// Com PACOTE_PIX_SAIDA definido, grava {publica, pacote} de uma chave Pix
// assinada aqui: o Hub (Python) confere o mesmo pacote - as duas pontas provadas
// uma contra a outra, como na licenca assinada.

import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, verify } from "node:crypto";
import { writeFileSync } from "node:fs";

import {
  assinar, conteudoPix, emailDaTroca, emailDoCodigo, importarChavePrivada, mascararEmail, mascararPix,
  remetente, rotaDe, tratar,
} from "../pagamentos/nucleo.ts";

const PC = "0123456789abcdef0123456789abcdef";
const ID = { chave: "7k4m-9qx2-bt5h-3dwz", maquina: "aaaa-bbbb", computador: PC };

const { publicKey, privateKey } = generateKeyPairSync("ed25519");
const pkcs8 = privateKey.export({ format: "der", type: "pkcs8" }).toString("base64");
const chave = await importarChavePrivada(pkcs8);

function ambiente(respostas = {}, { emailFunciona = true } = {}) {
  const chamadas = [];
  const emails = [];
  return {
    chamadas, emails,
    kid: "k1",
    agora: () => new Date("2026-09-16T15:00:00Z"),
    rpc: async (funcao, parametros) => {
      chamadas.push({ funcao, parametros });
      return funcao in respostas ? respostas[funcao] : null;
    },
    enviarEmail: async (m) => { emails.push(m); return emailFunciona; },
    assinar: (conteudo) => assinar(conteudo, chave, "k1"),
  };
}

function abrir(pacote) {
  const bytes = Buffer.from(pacote.licenca, "base64url");
  assert.ok(verify(null, bytes, publicKey, Buffer.from(pacote.assinatura, "base64url")), "assinatura nao confere");
  return JSON.parse(bytes.toString("utf8"));
}

test("rotas conhecidas e so elas", () => {
  assert.equal(rotaDe("/functions/v1/pagamentos/codigo"), "codigo");
  assert.equal(rotaDe("/pagamentos/atual/"), "atual");
  assert.equal(rotaDe("/pagamentos/apagar"), "");
  assert.equal(rotaDe("/pagamentos/reservas"), "", "a rota das reservas deixou de existir");
});

test("mascaras nao entregam o dado inteiro", () => {
  assert.equal(mascararEmail("eric.dudu@gmail.com"), "e******u@gmail.com");
  assert.equal(mascararEmail("ab@x.com"), "a*b@x.com");
  assert.equal(mascararEmail("sem-arroba"), "");
  assert.equal(mascararPix("12345678901"), "123***8901");
  assert.equal(mascararPix(""), "(nenhuma)");
  assert.deepEqual(remetente("DumTech <avisos@x.com>"), { nome: "DumTech", email: "avisos@x.com" });
  assert.deepEqual(remetente("avisos@x.com"), { nome: "DumTech", email: "avisos@x.com" });
});

test("pedido sem identidade valida nem chega no banco", async () => {
  const amb = ambiente();
  for (const corpo of [{}, { ...ID, computador: "ABC" }, { ...ID, chave: "" }]) {
    const r = await tratar(amb, "codigo", corpo, "1.2.3.4");
    assert.equal(r.corpo.erro, "dados_incompletos");
  }
  assert.equal(amb.chamadas.length, 0);
});

test("codigo vai so por e-mail: a resposta ao Hub nunca traz o codigo", async () => {
  const amb = ambiente({ dumtech_pagamentos_pedir_codigo: {
    ok: true, codigo: "482913", email: "dono@loja.com", cliente: "Maria Souza", validade_minutos: 10 } });
  const r = await tratar(amb, "codigo", ID, "1.2.3.4");
  assert.equal(r.status, 200);
  assert.deepEqual(r.corpo, { ok: true, email: "d**o@loja.com", validade_minutos: 10 });
  assert.doesNotMatch(JSON.stringify(r.corpo), /482913/);
  assert.equal(amb.emails[0].para, "dono@loja.com");
  assert.match(amb.emails[0].texto, /Código: 482913/);
  assert.match(amb.emails[0].assunto, /^482913/);
  assert.deepEqual(amb.chamadas[0].parametros, {
    p_chave: "7K4M-9QX2-BT5H-3DWZ", p_maquina: "AAAA-BBBB", p_computador: PC, p_ip: "1.2.3.4" });
});

test("e-mail que nao sai vira erro claro", async () => {
  const amb = ambiente({ dumtech_pagamentos_pedir_codigo: { ok: true, codigo: "1", email: "a@b.com", cliente: "X" } },
                       { emailFunciona: false });
  assert.equal((await tratar(amb, "codigo", ID, "")).corpo.erro, "falha_no_envio");
});

test("recusa do banco vai como veio", async () => {
  const recusa = { ok: false, erro: "sem_email", mensagem: "Esta licenca ainda nao tem e-mail." };
  const amb = ambiente({ dumtech_pagamentos_pedir_codigo: recusa });
  assert.deepEqual((await tratar(amb, "codigo", ID, "")).corpo, recusa);
  assert.equal(amb.emails.length, 0);
});

test("banco fora do ar: 502, nunca um ok", async () => {
  const r = await tratar(ambiente(), "entrar", { ...ID, codigo: "123456" }, "");
  assert.equal(r.status, 502);
  assert.equal(r.corpo.ok, false);
});

test("entrar devolve a sessao e a chave Pix assinada para ESTE computador", async () => {
  const amb = ambiente({ dumtech_pagamentos_entrar: {
    ok: true, sessao: "s".repeat(64), expira_em: "2026-09-16T15:15:00Z", pix_chave: "loja@banco.com" } });
  const r = await tratar(amb, "entrar", { ...ID, codigo: "123456" }, "");
  assert.equal(r.corpo.sessao, "s".repeat(64));
  assert.equal("p_queimadas" in amb.chamadas[0].parametros, false, "nao existe mais reserva");
  const conteudo = abrir(r.corpo.assinado);
  assert.equal(conteudo.uso, "pagamentos");
  assert.equal(conteudo.pix_chave, "loja@banco.com");
  assert.equal(conteudo.computador, PC);
  assert.equal(conteudo.chave, "7K4M-9QX2-BT5H-3DWZ");
});

test("salvar assina a chave nova e avisa o dono quando mudou", async () => {
  const amb = ambiente({ dumtech_pagamentos_salvar: {
    ok: true, pix_chave: "novo@banco.com", antes: "velho@banco.com", mudou: true, email: "dono@loja.com", cliente: "Maria" } });
  const r = await tratar(amb, "salvar", { ...ID, sessao: "abc", pix_chave: "novo@banco.com" }, "");
  assert.equal(abrir(r.corpo.assinado).pix_chave, "novo@banco.com");
  assert.equal(amb.emails.length, 1);
  assert.match(amb.emails[0].assunto, /foi alterada/);
  assert.match(amb.emails[0].texto, /Antes: vel\*\*\*.com/);
  assert.match(amb.emails[0].texto, /Agora: nov\*\*\*.com/);
});

test("salvar a mesma chave nao manda aviso", async () => {
  const amb = ambiente({ dumtech_pagamentos_salvar: {
    ok: true, pix_chave: "x@banco.com", antes: "x@banco.com", mudou: false, email: "dono@loja.com", cliente: "M" } });
  await tratar(amb, "salvar", { ...ID, sessao: "abc", pix_chave: "x@banco.com" }, "");
  assert.equal(amb.emails.length, 0);
});

test("sessao recusada nao assina nada", async () => {
  const amb = ambiente({ dumtech_pagamentos_salvar: { ok: false, erro: "sessao_vencida", mensagem: "venceu" } });
  const r = await tratar(amb, "salvar", { ...ID, sessao: "velha", pix_chave: "golpe@x.com" }, "");
  assert.equal(r.corpo.erro, "sessao_vencida");
  assert.equal(r.corpo.assinado, undefined);
});

test("atual assina a chave de agora (inclusive vazia)", async () => {
  const amb = ambiente({ dumtech_pagamentos_atual: { ok: true, pix_chave: "" } });
  const r = await tratar(amb, "atual", ID, "9.9.9.9");
  assert.equal(abrir(r.corpo.assinado).pix_chave, "");
  assert.equal(amb.chamadas[0].parametros.p_ip, "9.9.9.9");
});

test("e-mails: nome vira texto, nunca marcacao", () => {
  const codigo = emailDoCodigo({ cliente: "<img src=x onerror=alert(1)>", codigo: "123456", validade: 10 });
  assert.doesNotMatch(codigo.html, /<img src=x/);
  const troca = emailDaTroca({ cliente: "<b>X</b>", antes: "<script>", depois: "a@b.com", quando: new Date() });
  assert.doesNotMatch(troca.html, /<script>|<b>X/);
  assert.match(emailDaTroca({ cliente: "Ana", antes: "a@b.com", depois: "", quando: new Date() }).texto, /removida/);
});

test("o conteudo assinado tem o carimbo de uso", () => {
  const c = conteudoPix({ kid: "k1", chave: "K", maquina: "M", computador: PC, pix: "p", agora: new Date(0) });
  assert.deepEqual(Object.keys(c), ["v", "kid", "uso", "chave", "maquina", "computador", "pix_chave", "emitido_em"]);
});

if (process.env.PACOTE_PIX_SAIDA) {
  const pacote = await assinar(
    conteudoPix({ kid: "k1", chave: "7K4M-9QX2-BT5H-3DWZ", maquina: "AAAA-BBBB", computador: PC, pix: "loja@banco.com" }),
    chave, "k1");
  const publica = publicKey.export({ format: "der", type: "spki" }).subarray(-32).toString("hex");
  writeFileSync(process.env.PACOTE_PIX_SAIDA, JSON.stringify({ publica, pacote }));
}
