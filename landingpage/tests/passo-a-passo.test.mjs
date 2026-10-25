// A busca do Passo a passo: a pergunta escrita do jeito da pessoa precisa achar o video certo.
import { test } from "node:test";
import assert from "node:assert/strict";

import { buscar, indexar, radicais } from "../passo-a-passo/busca.js";
import { VIDEOS } from "../passo-a-passo/catalogo.js";

const indices = VIDEOS.map(indexar);
const primeiro = consulta => buscar(indices, consulta).resultados[0]?.video.id;

test("o pedido do dono: 'como cadastro produtos' abre o video exato", () => {
  const { resultados, exato } = buscar(indices, "como cadastro produtos");
  assert.equal(resultados[0].video.id, "cadastrar-produto");
  assert.ok(exato, "o primeiro precisa ser a resposta, nao um palpite");
});

test("variacoes da mesma pergunta chegam no mesmo video", () => {
  for (const consulta of ["cadastrar produto", "Cadastro de Produtos", "COMO CADASTRAR UM PRODUTO?",
    "cadstro de produto", "como adicionar mercadoria", "novo produto"]) {
    assert.equal(primeiro(consulta), "cadastrar-produto", consulta);
  }
});

test("cada tarefa responde as perguntas comuns", () => {
  const casos = {
    "como fechar o caixa": "caixa", "fazer sangria": "caixa",
    "como faço uma venda": "vender-balcao", "como cobrar o cliente": "vender-balcao",
    "abrir uma OS": "abrir-ordem", "chegou um aparelho para conserto": "abrir-ordem",
    "como fazer backup": "backup", "cadastrar cliente": "cadastrar-cliente",
    "dar baixa numa conta": "receber-conta", "lançar nota do fornecedor": "entrada-mercadoria",
    "inventário": "contagem-estoque", "devolução de venda": "devolucao",
    "fazer orçamento": "criar-orcamento", "marcar horário": "marcar-compromisso",
    "ver no celular": "celular", "fluxo de caixa": "fluxo-caixa",
  };
  for (const [consulta, id] of Object.entries(casos)) assert.equal(primeiro(consulta), id, consulta);
});

test("palavra vazia nao conta e 'os' minusculo e artigo; 'OS' e ordem de servico", () => {
  assert.deepEqual(radicais("como eu faço para os produtos"), ["produt"]);
  assert.deepEqual(radicais("abrir uma OS"), ["abrir", "ordem"]);
});

test("o que nao existe nao inventa resultado", () => {
  assert.equal(buscar(indices, "xyzabc qwerty").resultados.length, 0);
  assert.equal(buscar(indices, "como").resultados.length, 0);
});

test("todo video do catalogo tem passos com tempo e arquivo leve", () => {
  for (const v of VIDEOS) {
    assert.ok(v.passos.length >= 2, v.id);
    assert.ok(v.passos.every((p, i) => i === 0 || p.t >= v.passos[i - 1].t), `${v.id}: passos fora de ordem`);
    assert.ok(v.kb < 2500, `${v.id}: ${v.kb} KB e pesado demais para a hospedagem`);
  }
});
