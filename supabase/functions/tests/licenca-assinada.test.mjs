// Testes do nucleo da licenca assinada (Node >= 23.6 roda .ts direto).
//
//     node --test supabase/functions/tests/licenca-assinada.test.mjs
//
// Gera um pacote aqui e grava em PACOTE_SAIDA (se definido): o teste do Hub
// (tests/test_assinatura.py) confere o mesmo pacote em Python - assim a ponta
// que assina e a ponta que confere sao provadas uma contra a outra.

import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, verify } from "node:crypto";
import { writeFileSync } from "node:fs";

import {
  assinar, base64url, computadorValido, conteudoAcesso, conteudoDaLicenca, importarChavePrivada, ipDoVisitante, normalizar,
} from "../licenca-assinada/nucleo.ts";

const RESPOSTA = {
  ok: true, chave: "7K4M-9QX2-BT5H-3DWZ", cliente: "Padaria Pão de Ouro", tipo: "vitalicia",
  produtos: ["estoque", "VENDAS"], expira_em: null, max_computadores: 3, computadores_usados: 1,
};

test("normaliza e valida o que chega da internet", () => {
  assert.equal(normalizar("  abcd-efgh ", 32), "ABCD-EFGH");
  assert.equal(normalizar("x".repeat(80), 64).length, 64);
  assert.ok(computadorValido("0123456789abcdef0123456789abcdef"));
  assert.ok(!computadorValido("0123456789ABCDEF0123456789ABCDEF"), "so hex minusculo");
  assert.ok(!computadorValido("curto"));
  assert.ok(!computadorValido(undefined));
});

test("conteudo tem prazo offline e produtos em maiusculas", () => {
  const agora = new Date("2026-09-12T12:00:00Z");
  const c = conteudoDaLicenca(RESPOSTA, { kid: "k1", maquina: "AB12-CD34", computador: "f".repeat(32), agora, diasOffline: 30 });
  assert.equal(c.v, 1);
  assert.deepEqual(c.produtos, ["ESTOQUE", "VENDAS"]);
  assert.equal(c.valida_ate, "2026-10-12T12:00:00.000Z");
  assert.equal(c.maquina, "AB12-CD34");
});

test("a licenca assinada diz se ha contas, e so a verdade conta", () => {
  const base = { kid: "k1", maquina: "AB12-CD34", computador: "f".repeat(32) };
  assert.equal(conteudoDaLicenca({ ...RESPOSTA, contas: true }, base).contas, true);
  assert.equal(conteudoDaLicenca(RESPOSTA, base).contas, false, "servidor antigo nao diz: sem contas");
  assert.equal(conteudoDaLicenca({ ...RESPOSTA, contas: "sim" }, base).contas, false);
});

test("o pacote de acesso e outro documento, preso ao computador", () => {
  const c = conteudoAcesso({
    kid: "k1", chave: "7K4M", maquina: "AB12", computador: "f".repeat(32),
    resumo: { exigir_conta: true, usuarios: [{ id: "u1", login: "dona" }] },
    agora: new Date("2026-11-02T12:00:00Z"),
  });
  assert.equal(c.uso, "acesso");
  assert.equal(c.exigir_conta, true);
  assert.equal(c.computador, "f".repeat(32));
  assert.deepEqual(c.usuarios, [{ id: "u1", login: "dona" }]);
  assert.equal(c.emitido_em, "2026-11-02T12:00:00.000Z");
});

test("assina os bytes do JSON e a assinatura confere", async () => {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const pkcs8 = privateKey.export({ format: "der", type: "pkcs8" }).toString("base64");
  const conteudo = conteudoDaLicenca(RESPOSTA, { kid: "t1", maquina: "AB12-CD34", computador: "a".repeat(32) });
  const pacote = await assinar(conteudo, await importarChavePrivada(pkcs8), "t1");

  const bytes = Buffer.from(pacote.licenca, "base64url");
  assert.deepEqual(JSON.parse(bytes.toString("utf8")), conteudo, "acentos sobrevivem (UTF-8)");
  assert.ok(verify(null, bytes, publicKey, Buffer.from(pacote.assinatura, "base64url")));

  const adulterado = Buffer.from(bytes.toString("utf8").replace("ESTOQUE", "AGENDA"), "utf8");
  assert.ok(!verify(null, adulterado, publicKey, Buffer.from(pacote.assinatura, "base64url")),
            "trocar um modulo no conteudo derruba a assinatura");

  if (process.env.PACOTE_SAIDA) {
    const publica = publicKey.export({ format: "der", type: "spki" }).subarray(12).toString("hex");
    writeFileSync(process.env.PACOTE_SAIDA, JSON.stringify({ publica, pacote, conteudo }));
  }
});

test("base64url sem preenchimento", () => {
  assert.equal(base64url(new Uint8Array([251, 255])), "-_8");
});

test("endereco do visitante, na ordem de confianca", () => {
  assert.equal(ipDoVisitante(new Headers({ "cf-connecting-ip": "1.1.1.1", "x-forwarded-for": "2.2.2.2" })), "1.1.1.1");
  assert.equal(ipDoVisitante(new Headers({ "x-forwarded-for": "2.2.2.2, 10.0.0.1" })), "2.2.2.2");
  assert.equal(ipDoVisitante(new Headers()), "");
});

// ------------------------------------------------------------ teste gratis ---
import { testesValidos } from "../licenca-assinada/nucleo.ts";

test("o teste gratis vai dentro do pacote assinado", () => {
  const conteudo = conteudoDaLicenca(
    { ok: true, chave: "AAAA-BBBB-CCCC-DDDD", produtos: ["VENDAS"],
      testes: { AGENDA: "2026-09-29T12:00:00Z" } },
    { kid: "k1", maquina: "M", computador: "C" });
  assert.deepEqual(conteudo.testes, { AGENDA: "2026-09-29T12:00:00.000Z" });
  assert.deepEqual(conteudo.produtos, ["VENDAS"]);   // teste nao vira compra
});

test("teste com lixo nao entra no pacote", () => {
  assert.deepEqual(testesValidos({ AGENDA: "nao e data", "<x>": "2026-09-29", ORDENS: "2026-10-01" }),
                   { ORDENS: "2026-10-01T00:00:00.000Z" });
  assert.deepEqual(testesValidos(null), {});
  assert.deepEqual(testesValidos(["AGENDA"]), {});
});

test("a cobranca da mensalidade vai assinada, e vitalicia nao ganha o campo", () => {
  const base = { kid: "k1", maquina: "AB12-CD34", computador: "f".repeat(32) };
  assert.ok(!("cobranca" in conteudoDaLicenca(RESPOSTA, base)), "vitalicia ganhou cobranca");
  assert.ok(!("cobranca" in conteudoDaLicenca({ ...RESPOSTA, cobranca: null }, base)));

  const teste = conteudoDaLicenca({
    ...RESPOSTA, tipo: "teste",
    cobranca: { situacao: "teste", ate: "2026-11-10", motivo: null, desde: null, extra: "<script>" },
  }, base);
  assert.deepEqual(teste.cobranca, { situacao: "teste", ate: "2026-11-10", motivo: null, desde: null });

  const pendente = conteudoDaLicenca({
    ...RESPOSTA, tipo: "assinatura",
    cobranca: { situacao: "pendente", ate: "2026-11-10", motivo: "falhou", desde: "2026-10-01" },
  }, base);
  assert.equal(pendente.cobranca.motivo, "falhou");

  // lixo nao entra: situacao inventada, data torta, motivo estranho
  assert.ok(!("cobranca" in conteudoDaLicenca({ ...RESPOSTA, cobranca: { situacao: "gratis_para_sempre" } }, base)));
  const torta = conteudoDaLicenca({
    ...RESPOSTA, tipo: "assinatura",
    cobranca: { situacao: "em_dia", ate: "amanha", motivo: "porque sim", desde: 5 },
  }, base);
  assert.deepEqual(torta.cobranca, { situacao: "em_dia", ate: null, motivo: null, desde: null });
});
