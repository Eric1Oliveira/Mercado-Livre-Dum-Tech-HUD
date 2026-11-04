// Testes do motor do plano mensal. Rodar da pasta landingpage:
//
//     node --test tests/
//
// Modulo puro: sem navegador e sem internet.

import test from "node:test";
import assert from "node:assert/strict";

import {
  CONFIG_PADRAO, adicionaisDoCliente, alternarAdicional, aplicarCupom, chaveCombinacao, codigoDeCupom,
  comConfig, configDoServidor, criarPlano, escolherPronto, partesDoPreco, perfil, problemaNoCadastro, resumo,
  tirarCupom,
} from "../js/plano.js";

const SALAO = "0b9c6a4e-5f1d-4c3b-9a8e-7d6c5b4a3f2e";
const COMPLETO = "1c9c6a4e-5f1d-4c3b-9a8e-7d6c5b4a3f2e";
const SERVIDOR = {
  ok: true, preco_base: 89.9, dias_teste: 7, computadores: 2,
  base: ["VENDAS", "ESTOQUE", "FINANCEIRO"],
  adicionais: [{ codigo: "CLIENTES", preco: 29.9 }, { codigo: "ORDENS", preco: 29.9 }, { codigo: "AGENDA", preco: 39.9 }],
  planos: [
    { id: SALAO, nome: "Salão", descricao: "Hora marcada", modulos: ["AGENDA", "CLIENTES", "FINANCEIRO"],
      preco: 99.9, preco_cheio: 119.9, promo_rotulo: "Novembro", promo_ate: "2026-11-30", destaque: true, assinavel: true },
    { id: COMPLETO, nome: "Completo", modulos: ["VENDAS"], preco: 199.9, preco_cheio: null, assinavel: false },
    { id: "nao-e-uuid", nome: "Torto", modulos: [], preco: 1 },
  ],
  combinacoes: ["", "AGENDA+ORDENS"],
};
const config = configDoServidor(SERVIDOR);

test("a vitrine do servidor e conferida, e lixo fica de fora", () => {
  assert.equal(config.precoBase, 89.9);
  assert.equal(config.computadores, 2);
  assert.equal(config.planos.length, 2, "plano com id torto entrou");
  assert.equal(config.planos[0].precoCheio, 119.9);
  assert.equal(configDoServidor({ ok: true, preco_base: "abc" }), null);
  assert.equal(configDoServidor(null), null);
});

test("monte o seu: a base mais o preco de cada adicional", () => {
  let plano = criarPlano(config);
  assert.equal(resumo(plano).total, 89.9);
  plano = alternarAdicional(plano, "AGENDA");
  plano = alternarAdicional(plano, "ORDENS");
  const r = resumo(plano);
  assert.equal(r.total, 159.7);
  assert.deepEqual(r.adicionais, ["ORDENS", "AGENDA"], "na ordem da vitrine");
  assert.deepEqual(r.linhas.map((l) => l.texto), ["Plano base", "+ Ordem de Serviço", "+ Agenda"]);
  assert.deepEqual(r.pedido, { plano: null, cupom: "", adicionais: ["ORDENS", "AGENDA"] });
});

test("a combinacao so e assinavel quando tem link (a chave e a mesma do banco)", () => {
  assert.equal(chaveCombinacao(["ordens", "AGENDA", "ORDENS"]), "AGENDA+ORDENS");
  let plano = criarPlano(config);
  assert.ok(resumo(plano).assinavel, "so a base tem link");
  plano = alternarAdicional(plano, "AGENDA");
  assert.ok(!resumo(plano).assinavel, "AGENDA sozinha nao tem link");
  plano = alternarAdicional(plano, "ORDENS");
  assert.ok(resumo(plano).assinavel);
  // sem resposta do servidor ainda: quem decide e o cadastro
  assert.ok(resumo(alternarAdicional(criarPlano(CONFIG_PADRAO), "AGENDA")).assinavel);
});

test("adicional fora da venda ou inventado nao entra", () => {
  const plano = criarPlano(config, ["ORCAMENTOS", "<script>", "agenda"]);
  assert.deepEqual(resumo(plano).adicionais, ["AGENDA"]);
});

test("plano pronto: preco de/por, modulos pelo nome e o pedido leva so o id", () => {
  const r = resumo(escolherPronto(criarPlano(config), SALAO));
  assert.equal(r.tipo, "pronto");
  assert.equal(r.total, 99.9);
  assert.equal(r.totalCheio, 119.9);
  assert.equal(r.rotulo, "Novembro");
  assert.equal(r.linhas[0].detalhe, "Agenda · Clientes · Financeiro");
  assert.deepEqual(r.pedido, { plano: SALAO, cupom: "", adicionais: [] });
  assert.ok(!resumo(escolherPronto(criarPlano(config), COMPLETO)).assinavel);
  // id que nao existe nao troca a escolha
  assert.equal(resumo(escolherPronto(criarPlano(config), "outro")).tipo, "montado");
  // mexer num adicional volta ao monte o seu
  assert.equal(resumo(alternarAdicional(escolherPronto(criarPlano(config), SALAO), "AGENDA")).tipo, "montado");
});

test("cupom: libera o plano dele e sai com tirarCupom", () => {
  const resposta = { ok: true, codigo: "PARCEIRO10", descricao: "Parceiro Joao",
                     plano: { id: COMPLETO, nome: "Parceiro", modulos: ["VENDAS", "ESTOQUE"], preco: 69.9, assinavel: true } };
  const comCupom = aplicarCupom(criarPlano(config), resposta);
  const r = resumo(comCupom);
  assert.equal(r.tipo, "cupom");
  assert.equal(r.total, 69.9);
  assert.deepEqual(r.pedido, { plano: null, cupom: "PARCEIRO10", adicionais: [] });
  assert.equal(resumo(tirarCupom(comCupom)).tipo, "montado");
  assert.equal(resumo(aplicarCupom(criarPlano(config), { ok: false })).tipo, "montado");
  assert.equal(codigoDeCupom(" parceiro10 "), "PARCEIRO10");
  assert.equal(codigoDeCupom("<x>"), "");
});

test("a resposta do servidor chegando depois mantem a escolha que ainda vale", () => {
  const local = escolherPronto(criarPlano(config), SALAO);
  assert.equal(resumo(comConfig(local, config)).tipo, "pronto");
  const semOPlano = { ...config, planos: [] };
  assert.equal(resumo(comConfig(local, semOPlano)).tipo, "montado");
  const montado = criarPlano(CONFIG_PADRAO, ["ORCAMENTOS", "AGENDA"]);
  assert.deepEqual(resumo(comConfig(montado, config)).adicionais, ["AGENDA"], "fora da venda caiu");
});

test("quem chegou pelo Hub: vitalicio nunca vira mensal", () => {
  assert.equal(perfil({ tipo: "vitalicia", produtos: ["VENDAS"] }), "vitalicio");
  assert.equal(perfil({ tipo: "assinatura" }), "mensal");
  assert.equal(perfil({ tipo: "teste" }), "mensal");
  assert.equal(perfil({ tipo: "" }), "novo");
  assert.equal(perfil(null), "novo");
  assert.deepEqual(adicionaisDoCliente({ tipo: "assinatura", produtos: ["VENDAS", "ORDENS"] }, config), ["ORDENS"]);
  assert.deepEqual(adicionaisDoCliente({ tipo: "teste", produtos: ["ORDENS"] }, config), []);
});

test("o formulario e conferido com texto de gente", () => {
  assert.match(problemaNoCadastro({ nome: " ", email: "a@b.com" }), /nome/);
  assert.match(problemaNoCadastro({ nome: "Ana", email: "a@b" }), /e-mail/);
  assert.match(problemaNoCadastro({ nome: "Ana", email: "a@b.com", whatsapp: "1234" }), /WhatsApp/);
  assert.equal(problemaNoCadastro({ nome: "Ana", email: "a@b.com", whatsapp: "(11) 90000-0001" }), "");
});

test("o preco grande separa reais e centavos", () => {
  assert.deepEqual(partesDoPreco(89.9), { inteiro: "89", centavos: "90" });
  assert.deepEqual(partesDoPreco(1209.5), { inteiro: "1.209", centavos: "50" });
});
