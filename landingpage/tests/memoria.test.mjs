// Testes da identidade lembrada no navegador.
//
//     node --test tests/memoria.test.mjs

import test from "node:test";
import assert from "node:assert/strict";

import {
  CHAVE, CHAVE_CATALOGO, VALIDADE_CATALOGO_DIAS, VALIDADE_DIAS,
  catalogoLembrado, esquecer, lembrado, lembrar, lembrarCatalogo,
} from "../js/memoria.js";

/** Um localStorage de mentira. */
function armazemFalso(inicial = {}) {
  const dados = new Map(Object.entries(inicial));
  return {
    getItem: (k) => (dados.has(k) ? dados.get(k) : null),
    setItem: (k, v) => dados.set(k, String(v)),
    removeItem: (k) => dados.delete(k),
    tamanho: () => dados.size,
  };
}

const JOAO = { nome: "Joao da Silva", email: "Joao@Exemplo.com", produtos: ["estoque", "vendas"] };

test("sem nada guardado, ninguem e reconhecido", () => {
  assert.equal(lembrado(armazemFalso()), null);
});

test("lembrar e depois reconhecer", () => {
  const armazem = armazemFalso();
  lembrar(armazem, JOAO);

  const pessoa = lembrado(armazem);
  assert.equal(pessoa.nome, "Joao da Silva");
  assert.equal(pessoa.email, "joao@exemplo.com", "o e-mail e guardado em minusculas");
  assert.deepEqual(pessoa.produtos, ["ESTOQUE", "VENDAS"]);
  assert.equal(pessoa.doNavegador, true, "a tela precisa saber que isso veio do navegador");
});

test("produto repetido nao duplica", () => {
  const armazem = armazemFalso();
  lembrar(armazem, { ...JOAO, produtos: ["ESTOQUE", "estoque", "VENDAS"] });
  assert.deepEqual(lembrado(armazem).produtos, ["ESTOQUE", "VENDAS"]);
});

test("sem e-mail nao ha o que lembrar", () => {
  const armazem = armazemFalso();
  assert.equal(lembrar(armazem, { nome: "Sem E-mail" }), null);
  assert.equal(armazem.tamanho(), 0);
});

test("depois da validade, melhor perguntar de novo", () => {
  const armazem = armazemFalso();
  lembrar(armazem, JOAO);

  const amanha = new Date(Date.now() + (VALIDADE_DIAS + 1) * 86400000);
  assert.equal(lembrado(armazem, amanha), null);
  assert.equal(armazem.tamanho(), 0, "o que venceu tambem sai do navegador");
});

test("dentro da validade continua valendo", () => {
  const armazem = armazemFalso();
  lembrar(armazem, JOAO);
  const daquiUmMes = new Date(Date.now() + 30 * 86400000);
  assert.equal(lembrado(armazem, daquiUmMes).email, "joao@exemplo.com");
});

test("lixo no armazenamento e tratado como ninguem", () => {
  const armazem = armazemFalso({ [CHAVE]: "{isso nao e json" });
  assert.equal(lembrado(armazem), null);
  assert.equal(armazem.tamanho(), 0);
});

test("registro sem e-mail e descartado", () => {
  const armazem = armazemFalso({ [CHAVE]: JSON.stringify({ nome: "X" }) });
  assert.equal(lembrado(armazem), null);
});

test("esquecer apaga", () => {
  const armazem = armazemFalso();
  lembrar(armazem, JOAO);
  esquecer(armazem);
  assert.equal(lembrado(armazem), null);
});

test("navegador que proibe armazenamento nao derruba a pagina", () => {
  const proibido = {
    getItem() { throw new Error("negado"); },
    setItem() { throw new Error("negado"); },
    removeItem() { throw new Error("negado"); },
  };
  assert.equal(lembrado(proibido), null);
  assert.equal(lembrar(proibido, JOAO).email, "joao@exemplo.com", "segue em frente sem gravar");
  esquecer(proibido); // nao pode lancar
});

test("sem armazem nenhum (modo estranho de navegador)", () => {
  assert.equal(lembrado(null), null);
  assert.equal(lembrar(null, JOAO), null);
  assert.equal(catalogoLembrado(null), null);
  lembrarCatalogo(null, { produtos: [] }); // nao pode lancar
});

// ---------------------------------------------------------------- catalogo --
const CATALOGO = {
  produtos: [{ codigo: "ESTOQUE", nome: "Estoque", preco: "249.00" }],
  combos: [{ codigo: "GESTAO", produtos: ["ESTOQUE"], preco: 699 }],
  local: false,
};

test("o catalogo do servidor volta na proxima visita, com preco numerico", () => {
  const armazem = armazemFalso();
  lembrarCatalogo(armazem, CATALOGO);
  const guardado = catalogoLembrado(armazem);
  assert.equal(guardado.produtos[0].preco, 249);
  assert.equal(guardado.combos[0].codigo, "GESTAO");
  assert.equal(guardado.local, false);
});

test("o catalogo local (de exemplo) nunca e guardado", () => {
  const armazem = armazemFalso();
  lembrarCatalogo(armazem, { ...CATALOGO, local: true });
  assert.equal(armazem.tamanho(), 0);
});

test("catalogo vencido ou estragado e ignorado", () => {
  const armazem = armazemFalso();
  lembrarCatalogo(armazem, CATALOGO);
  const depois = new Date(Date.now() + (VALIDADE_CATALOGO_DIAS + 1) * 86400000);
  assert.equal(catalogoLembrado(armazem, depois), null);

  for (const lixo of ["{nao e json", JSON.stringify({ produtos: [] }),
                      JSON.stringify({ produtos: [{ codigo: 1, preco: "x" }], quando: new Date() })]) {
    assert.equal(catalogoLembrado(armazemFalso({ [CHAVE_CATALOGO]: lixo })), null, lixo);
  }
});
