// Testes dos textos da pagina inicial (o que o Eric publica no painel).
//
//     node --test tests/

import test from "node:test";
import assert from "node:assert/strict";

import { CHAVE_PREVIA, PADRAO, mesclar, pedacos, preencher, previaGuardada, valoresDosMarcadores } from "../js/conteudo.js";

test("sem nada publicado, fica o texto de sempre", () => {
  assert.deepEqual(mesclar({}), PADRAO);
  assert.deepEqual(mesclar(null), PADRAO);
});

test("o publicado entra campo a campo; o que falta fica com o padrao", () => {
  const c = mesclar({ hero: { titulo: "  Novo título  " }, modulos: { AGENDA: { frase: "Agenda nova" } } });
  assert.equal(c.hero.titulo, "Novo título");
  assert.equal(c.hero.chamada, PADRAO.hero.chamada);
  assert.equal(c.modulos.AGENDA.frase, "Agenda nova");
  assert.equal(c.modulos.VENDAS.frase, PADRAO.modulos.VENDAS.frase);
});

test("lixo nao entra: numero, objeto onde e texto, texto vazio", () => {
  const c = mesclar({ hero: { titulo: 42, chamada: { x: 1 }, nota: "   " }, fatos: "nao e lista", whatsapp: "abc" });
  assert.equal(c.hero.titulo, PADRAO.hero.titulo);
  assert.equal(c.hero.chamada, PADRAO.hero.chamada);
  assert.equal(c.hero.nota, PADRAO.hero.nota);
  assert.deepEqual(c.fatos, PADRAO.fatos);
  assert.equal(c.whatsapp, PADRAO.whatsapp);
});

test("listas: acrescentar, tirar e reordenar, com limite", () => {
  const c = mesclar({
    fatos: ["Um", "", 3, "Dois"],
    duvidas: { itens: [{ pergunta: "P1", resposta: "R1" }, { pergunta: "Sem resposta" }, { pergunta: "P2", resposta: "R2" }] },
    passos: Array.from({ length: 30 }, (_, i) => ({ titulo: `T${i}`, texto: "x" })),
  });
  assert.deepEqual(c.fatos, ["Um", "Dois"]);
  assert.deepEqual(c.duvidas.itens.map((d) => d.pergunta), ["P1", "P2"], "pergunta sem resposta entrou");
  assert.equal(c.duvidas.titulo, PADRAO.duvidas.titulo);
  assert.equal(c.passos.length, 16, "lista sem limite");
  // lista que ficou vazia de verdade volta ao padrao (a pagina nunca fica sem perguntas)
  assert.deepEqual(mesclar({ fatos: [] }).fatos, PADRAO.fatos);
});

test("texto muito longo e cortado, nao recusado", () => {
  assert.equal(mesclar({ hero: { titulo: "x".repeat(500) } }).hero.titulo.length, 140);
});

test("os marcadores trocam pelo valor de agora", () => {
  // o "R$" e o numero ficam presos por um espaco que nao quebra a linha
  const semQuebra = (texto) => texto.replace(/ /g, " ");
  const valores = valoresDosMarcadores({ precoBase: 89.9, diasTeste: 7, computadores: 1 });
  assert.equal(semQuebra(preencher("Base por {preco_base}, {dias_teste} dias, {computadores}.", valores)),
               "Base por R$ 89,90, 7 dias, 1 computador.");
  assert.equal(valoresDosMarcadores({ precoBase: 1, diasTeste: 7, computadores: 2 }).computadores, "2 computadores");
  assert.deepEqual(pedacos("Por {preco_base} ao mês", valores).map((p) => ({ ...p, ...(p.valor ? { valor: semQuebra(p.valor) } : {}) })),
                   [{ texto: "Por " }, { valor: "R$ 89,90" }, { texto: " ao mês" }]);
  assert.equal(preencher("{desconhecido} fica", valores), "{desconhecido} fica");
});

test("a pre-visualizacao do painel vale por 2 horas", () => {
  const armazem = new Map();
  const guardar = (dados) => armazem.set(CHAVE_PREVIA, JSON.stringify(dados));
  const api = { getItem: (k) => armazem.get(k) ?? null };
  guardar({ conteudo: { hero: { titulo: "Rascunho" } }, quando: 1000 });
  assert.equal(previaGuardada(api, 1000 + 60_000).hero.titulo, "Rascunho");
  assert.equal(previaGuardada(api, 1000 + 3 * 3600_000), null, "previa velha valeu");
  armazem.set(CHAVE_PREVIA, "{torto");
  assert.equal(previaGuardada(api, 2000), null);
});
