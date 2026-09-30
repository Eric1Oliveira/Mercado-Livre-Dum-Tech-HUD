// O Hub no celular: o que aparece na tela a partir do que o servidor manda.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  codigoDoEndereco, destaqueDaTela, estaAntigo, haQuanto, linkDaLoja, montarTela, nomeDoAparelho,
} from "../js/celular.js";

const CODIGO = "ab".repeat(32);

const secao = (app) => ({ app, titulo: app, cartoes: [], listas: [] });
const resposta = (modulos, secoes, extra = {}) => ({
  ok: true,
  cliente: "Padaria ZZ",
  modulos,
  espelhos: [{ computador: "Caixa", atualizado_em: "2026-09-21T12:00:00Z", dados: { empresa: "Padaria", secoes } }],
  ...extra,
});

test("o codigo do QR so vale inteiro e depois do #", () => {
  assert.equal(codigoDoEndereco(`#p=${CODIGO}`), CODIGO);
  assert.equal(codigoDoEndereco(`#x=1&p=${CODIGO}`), CODIGO);
  assert.equal(codigoDoEndereco("#p=curto"), "");
  assert.equal(codigoDoEndereco(`#p=${CODIGO}zz`), "");
  assert.equal(codigoDoEndereco(""), "");
});

test("o nome do aparelho que o Hub mostra", () => {
  assert.equal(nomeDoAparelho("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"), "iPhone");
  assert.equal(nomeDoAparelho("Mozilla/5.0 (Linux; Android 14; SM-S918B Build/UP1A) Chrome"), "Android · SM-S918B");
  assert.equal(nomeDoAparelho("Mozilla/5.0 (Linux; Android 10; K) Chrome/120"), "Android");
  assert.equal(nomeDoAparelho(""), "Celular");
});

test("so aparece o que a licenca libera AGORA", () => {
  const t = montarTela(resposta(["VENDAS"], [secao("VENDAS"), secao("ORDENS")]));
  assert.deepEqual(t.secoes.map((s) => s.app), ["VENDAS"]);
  assert.equal(t.empresa, "Padaria");
});

test("modulo comprado agora aparece como a caminho ate o computador mandar", () => {
  const t = montarTela(resposta(["VENDAS", "ORDENS"], [secao("VENDAS")]));
  assert.deepEqual(t.aCaminho.map((m) => m.codigo), ["ORDENS"]);
  assert.ok(!t.faltam.some((m) => m.codigo === "ORDENS"));
  assert.ok(t.faltam.some((m) => m.codigo === "ESTOQUE"));
});

test("teste gratis em minusculas tambem vale", () => {
  const t = montarTela(resposta(["vendas", "agenda"], [secao("VENDAS"), secao("AGENDA")]));
  assert.deepEqual(t.secoes.map((s) => s.app), ["VENDAS", "AGENDA"]);
});

test("mais de um computador: escolhe, e indice fora da faixa nao quebra", () => {
  const dados = resposta(["VENDAS"], [secao("VENDAS")]);
  dados.espelhos.push({ computador: "Escritorio", atualizado_em: "2026-09-21T11:00:00Z",
                        dados: { secoes: [] } });
  assert.equal(montarTela(dados, 1).secoes.length, 0);
  assert.equal(montarTela(dados, 9).indice, 1);
  assert.deepEqual(montarTela(dados).computadores.map((c) => c.nome), ["Caixa", "Escritorio"]);
});

test("sem espelho ainda: tela vazia mas com o nome da empresa", () => {
  const t = montarTela({ ok: true, cliente: "Padaria ZZ", modulos: ["VENDAS"], espelhos: [] });
  assert.equal(t.empresa, "Padaria ZZ");
  assert.equal(t.secoes.length, 0);
  assert.equal(t.atualizadoEm, null);
});

test("ha quanto tempo", () => {
  const agora = new Date("2026-09-21T15:00:00");
  assert.equal(haQuanto(new Date("2026-09-21T14:59:40").toISOString(), agora), "agora mesmo");
  assert.equal(haQuanto(new Date("2026-09-21T14:52:00").toISOString(), agora), "há 8 min");
  assert.equal(haQuanto(new Date("2026-09-21T12:00:00").toISOString(), agora), "há 3 h");
  assert.match(haQuanto(new Date("2026-09-20T18:40:00").toISOString(), agora), /^ontem às 18:40$/);
  assert.equal(haQuanto("", agora), "");
});

test("numero velho avisa que o computador pode estar desligado", () => {
  const agora = new Date("2026-09-21T15:00:00Z");
  assert.equal(estaAntigo("2026-09-21T14:50:00Z", agora), false);
  assert.equal(estaAntigo("2026-09-21T14:00:00Z", agora), true);
});

test("link da loja leva o modulo no carrinho", () => {
  const link = new URL(linkDaLoja("https://dumtechsolution.com/", "ORDENS"));
  assert.equal(link.searchParams.get("kit"), "ORDENS");
  assert.equal(link.hash, "#montador");
});

test("o numero do dia e o primeiro cartao do modulo de maior peso", () => {
  const comCartoes = (app, cartoes) => ({ app, titulo: app, cartoes, listas: [] });
  const caixa = { rotulo: "Vendas de hoje", valor: "R$ 1.482,90", detalhe: "14 vendas" };
  const tela = montarTela(resposta(["VENDAS"], [comCartoes("VENDAS", [caixa, { rotulo: "Ticket", valor: "R$ 105" }])]));
  // e o cartao em si, para quem desenha saber qual tirar da grade
  assert.equal(destaqueDaTela(tela), caixa);

  // sem numero nenhum nao ha destaque, e isso nao pode quebrar a tela
  assert.equal(destaqueDaTela(montarTela(resposta(["VENDAS"], [secao("VENDAS")]))), null);

  // um numero so: ele fica onde esta, senao a secao vira um titulo sozinho
  const unico = montarTela(resposta(["VENDAS"], [comCartoes("VENDAS", [caixa])]));
  assert.equal(destaqueDaTela(unico), null);
  assert.equal(destaqueDaTela(montarTela(resposta([], []))), null);
  assert.equal(destaqueDaTela(null), null);
});
