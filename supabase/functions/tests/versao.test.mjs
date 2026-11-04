// Testes do nucleo do manifesto de atualizacao (Node >= 23.6 roda .ts direto).
//
//     node --test supabase/functions/tests/versao.test.mjs
//
// O que estes testes protegem: o Hub vai BAIXAR E EXECUTAR o que este manifesto
// disser. Entao ele so pode sair assinado, e a instalacao pelo Hub so pode ser
// liberada quando houver uma impressao digital de verdade.

import test from "node:test";
import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, verify } from "node:crypto";

import {
  assinar, conteudoDaAtualizacao, importarChavePrivada, shaValido, tratar, versaoValida,
} from "../versao/nucleo.ts";

const SHA = createHash("sha256").update("instalador").digest("hex");
const URL_OFICIAL = "https://dumtechsolution.com/baixar/DumTech-Hub-Setup.exe";

const { publicKey, privateKey } = generateKeyPairSync("ed25519");
const pkcs8 = privateKey.export({ format: "der", type: "pkcs8" }).toString("base64");
const chave = await importarChavePrivada(pkcs8);

function ambiente(resposta) {
  const chamadas = [];
  return {
    chamadas,
    kid: "k1",
    agora: () => new Date("2026-09-18T12:00:00Z"),
    rpc: async (funcao, parametros) => {
      chamadas.push({ funcao, parametros });
      return resposta;
    },
    assinar: (conteudo) => assinar(conteudo, chave, "k1"),
  };
}

function abrir(pacote) {
  const bytes = Buffer.from(pacote.licenca, "base64url");
  assert.ok(verify(null, bytes, publicKey, Buffer.from(pacote.assinatura, "base64url")),
            "assinatura nao confere");
  return JSON.parse(bytes.toString("utf8"));
}

const PUBLICADA = {
  ok: true, versao: "1.3.0", url: URL_OFICIAL, notas: "Novidades",
  obrigatoria: false, automatica: true, sha256: SHA, tamanho: 29781768,
};

test("formatos", () => {
  assert.ok(versaoValida("1.2.3"));
  assert.ok(versaoValida("2"));
  assert.ok(!versaoValida("1.2.3-beta"));
  assert.ok(!versaoValida(""));
  assert.ok(shaValido(SHA));
  assert.ok(!shaValido(SHA.slice(0, 63)));
  assert.ok(!shaValido("z".repeat(64)));
});

test("o manifesto sai assinado, com endereco e impressao digital", async () => {
  const amb = ambiente(PUBLICADA);
  const r = await tratar(amb, { chave: "7k4m-9qx2-bt5h-3dwz", maquina: "aaaa", versao: "1.2.1" }, "1.2.3.4");

  assert.equal(r.status, 200);
  assert.equal(r.corpo.versao, "1.3.0");
  assert.equal(r.corpo.automatica, true);
  const conteudo = abrir(r.corpo.assinado);
  assert.equal(conteudo.uso, "atualizacao");
  assert.equal(conteudo.url, URL_OFICIAL);
  assert.equal(conteudo.sha256, SHA);
  assert.equal(conteudo.versao, "1.3.0");
});

test("a versao instalada e o endereco do visitante vao para o banco", async () => {
  const amb = ambiente(PUBLICADA);
  await tratar(amb, { chave: "abc", maquina: "def", versao: "1.2.1" }, "9.9.9.9");
  assert.deepEqual(amb.chamadas[0].parametros, {
    p_chave: "ABC", p_maquina: "DEF", p_versao: "1.2.1", p_ip: "9.9.9.9",
  });
});

test("sem impressao digital, o Hub so avisa (nao instala)", async () => {
  const amb = ambiente({ ...PUBLICADA, sha256: "" });
  const r = await tratar(amb, { versao: "1.2.1" }, "");
  assert.equal(r.corpo.automatica, false, "sem sha256 nao se instala pelo Hub");
  assert.equal(r.corpo.sha256, "");
  assert.equal(abrir(r.corpo.assinado).sha256, "", "nem assinado vai hash de mentira");
});

test("sha256 mal formado tambem desliga a instalacao", async () => {
  const amb = ambiente({ ...PUBLICADA, sha256: "nao-e-hash" });
  const r = await tratar(amb, { versao: "1.2.1" }, "");
  assert.equal(r.corpo.automatica, false);
});

test("desligar no painel tira o botao do Hub", async () => {
  const amb = ambiente({ ...PUBLICADA, automatica: false });
  const r = await tratar(amb, { versao: "1.2.1" }, "");
  assert.equal(r.corpo.automatica, false);
  assert.equal(abrir(r.corpo.assinado).automatica, false);
});

test("sem versao publicada nao ha manifesto", async () => {
  for (const versao of ["", "nenhuma", null]) {
    const r = await tratar(ambiente({ ...PUBLICADA, versao }), { versao: "1.2.1" }, "");
    assert.equal(r.corpo.versao, "");
    assert.equal(r.corpo.assinado, undefined);
  }
});

test("banco fora do ar: 502, nunca um manifesto", async () => {
  const r = await tratar(ambiente(null), { versao: "1.2.1" }, "");
  assert.equal(r.status, 502);
  assert.equal(r.corpo.ok, false);
});

test("recusa do banco vai como veio", async () => {
  const recusa = { ok: false, erro: "muitas_tentativas" };
  const r = await tratar(ambiente(recusa), { versao: "1.2.1" }, "");
  assert.deepEqual(r.corpo, recusa);
});

test("o conteudo assinado tem o carimbo de uso", () => {
  const c = conteudoDaAtualizacao(PUBLICADA, { kid: "k1", agora: new Date(0) });
  assert.deepEqual(Object.keys(c), [
    "v", "kid", "uso", "versao", "url", "sha256", "tamanho", "obrigatoria",
    "automatica", "silenciosa", "forcada", "emitido_em",
  ]);
  assert.equal(c.uso, "atualizacao");
});

test("versao forcada vai dentro do pacote assinado", async () => {
  const r = await tratar(ambiente({ ...PUBLICADA, forcada: true }), { versao: "1.2.1" }, "");
  assert.equal(r.corpo.forcada, true);
  assert.equal(abrir(r.corpo.assinado).forcada, true);

  const normal = await tratar(ambiente(PUBLICADA), { versao: "1.2.1" }, "");
  assert.equal(abrir(normal.corpo.assinado).forcada, false);
});

test("sem impressao digital nada e forcado", async () => {
  const r = await tratar(ambiente({ ...PUBLICADA, forcada: true, sha256: "" }), { versao: "1.2.1" }, "");
  assert.equal(r.corpo.forcada, false);
  assert.equal(abrir(r.corpo.assinado).forcada, false);
});

test("o freio do painel tambem segura a forcada", async () => {
  const r = await tratar(ambiente({ ...PUBLICADA, forcada: true, automatica: false }), { versao: "1.2.1" }, "");
  assert.equal(r.corpo.forcada, false);
  assert.equal(abrir(r.corpo.assinado).forcada, false);
});

test("versao silenciosa vai dentro do pacote assinado", async () => {
  const r = await tratar(ambiente({ ...PUBLICADA, silenciosa: true }), { versao: "1.2.1" }, "");
  assert.equal(r.corpo.silenciosa, true);
  assert.equal(abrir(r.corpo.assinado).silenciosa, true);

  const normal = await tratar(ambiente(PUBLICADA), { versao: "1.2.1" }, "");
  assert.equal(abrir(normal.corpo.assinado).silenciosa, false);
});

test("sem instalacao pelo Hub nao existe silencio: o cliente tem de ser avisado", async () => {
  const r = await tratar(ambiente({ ...PUBLICADA, silenciosa: true, sha256: "" }), { versao: "1.2.1" }, "");
  assert.equal(r.corpo.silenciosa, false);
  assert.equal(abrir(r.corpo.assinado).silenciosa, false);
});

test("a impressao da licenca passa para o Hub, fora do pacote assinado", async () => {
  const marca = "0123456789abcdef0123456789abcdef";
  const { corpo } = await tratar(ambiente({ ...PUBLICADA, licenca: marca }), {}, "1.1.1.1");
  assert.equal(corpo.licenca, marca);
  // o que o Hub executa continua sendo so o que esta assinado
  assert.equal(abrir(corpo.assinado).licenca, undefined);
});

test("mesmo sem versao publicada a impressao chega", async () => {
  const marca = "fedcba9876543210fedcba9876543210";
  const { corpo } = await tratar(ambiente({ ok: true, versao: "", licenca: marca }), {}, "");
  assert.equal(corpo.versao, "");
  assert.equal(corpo.licenca, marca);
});

test("impressao estranha vinda do banco nao passa", async () => {
  const { corpo } = await tratar(ambiente({ ...PUBLICADA, licenca: "<script>" }), {}, "");
  assert.equal(corpo.licenca, "");
});
