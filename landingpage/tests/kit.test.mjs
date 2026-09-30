// Testes do motor do kit. Rodar da pasta landingpage:
//
//     node --test tests/
//
// Nao precisa de navegador nem de internet: o modulo e puro.

import test from "node:test";
import assert from "node:assert/strict";

import { KITS_PADRAO, MODULOS, catalogoLocal } from "../js/dados.js";
import {
  alternar, aplicarCombo, comboRecemFechado, contarLigacoes, criarKit, escolherKit,
  integracoes, limpar,
  pedido, resumo, sugestao,
} from "../js/kit.js";

// Catalogo FIXO destes testes: as regras do motor nao podem depender do preco
// que a loja cobra hoje (que muda pelo painel).
const PRECOS_TESTE = {
  ESTOQUE: 249, VENDAS: 249, FINANCEIRO: 229, ORDENS: 229,
  ORCAMENTOS: 199, CLIENTES: 149, AGENDA: 149,
};
const CATALOGO_TESTE = {
  produtos: MODULOS.map((m) => ({ codigo: m.codigo, nome: m.nome, preco: PRECOS_TESTE[m.codigo] })),
  combos: [{ codigo: "GESTAO", nome: "DumTech Gestão", preco: 699,
             produtos: ["CLIENTES", "ESTOQUE", "FINANCEIRO", "VENDAS"] }],
  local: true,
};
const novo = (jaTem = []) => criarKit(CATALOGO_TESTE, jaTem);

// Os kits de verdade (os mesmos do painel), para os testes de preco novo
const comKits = (jaTem = []) => criarKit(catalogoLocal(), jaTem);
const marcar = (kit, codigos) => codigos.reduce((k, c) => alternar(k, c), kit);

test("o kit comeca vazio", () => {
  const r = resumo(novo());
  assert.equal(r.vazio, true);
  assert.equal(r.total, 0);
  assert.deepEqual(r.itens, []);
});

test("escolher e desescolher um modulo", () => {
  let kit = alternar(novo(), "ESTOQUE");
  assert.equal(resumo(kit).total, 249);

  kit = alternar(kit, "ESTOQUE");
  assert.equal(resumo(kit).vazio, true);
});

test("a ordem do resumo segue o catalogo, nao a ordem dos cliques", () => {
  let kit = alternar(alternar(novo(), "AGENDA"), "ESTOQUE");
  assert.deepEqual(resumo(kit).escolhidos, ["ESTOQUE", "AGENDA"]);
});

test("quatro modulos do combo custam o preco do combo", () => {
  let kit = novo();
  for (const c of ["CLIENTES", "ESTOQUE", "FINANCEIRO", "VENDAS"]) kit = alternar(kit, c);

  const r = resumo(kit);
  assert.equal(r.combo, "GESTAO");
  assert.equal(r.total, 699);
  assert.equal(r.economia, 876 - 699);
  assert.equal(r.itens.length, 1, "o combo entra como um item so");
});

test("combo mais um avulso: soma os dois, sem cobrar o modulo duas vezes", () => {
  let kit = novo();
  for (const c of ["CLIENTES", "ESTOQUE", "FINANCEIRO", "VENDAS", "AGENDA"]) {
    kit = alternar(kit, c);
  }
  const r = resumo(kit);
  assert.equal(r.total, 699 + 149);
  assert.equal(r.itens.filter((i) => i.tipo === "produto").length, 1);
});

test("o botao do combo marca o que falta e, no segundo clique, desmarca", () => {
  let kit = aplicarCombo(novo(), "GESTAO");
  assert.equal(resumo(kit).total, 699);

  kit = aplicarCombo(kit, "GESTAO");
  assert.equal(resumo(kit).vazio, true);
});

test("o que o cliente ja tem nao e vendido de novo", () => {
  let kit = novo(["estoque", "vendas"]);
  kit = alternar(kit, "ESTOQUE"); // clicar no que ele ja tem nao faz nada
  assert.equal(resumo(kit).vazio, true);

  kit = alternar(kit, "FINANCEIRO");
  assert.equal(resumo(kit).total, 229);
});

test("integracao acende quando os dois lados estao no kit", () => {
  let kit = alternar(novo(), "ESTOQUE");
  let catalogo = integracoes(kit).find((i) => i.id === "catalogo");
  assert.equal(catalogo.estado, "dormente");
  assert.deepEqual(catalogo.faltando, ["VENDAS", "ORCAMENTOS", "ORDENS"]);

  kit = alternar(kit, "VENDAS");
  catalogo = integracoes(kit).find((i) => i.id === "catalogo");
  assert.equal(catalogo.estado, "ativa");
  assert.deepEqual(catalogo.ligacoes, [{ de: "ESTOQUE", para: "VENDAS" }]);
  assert.deepEqual(catalogo.faltando, ["ORCAMENTOS", "ORDENS"]);
});

test("sem nenhum dos dois lados, a integracao fica fora", () => {
  const kit = alternar(novo(), "AGENDA");
  assert.equal(integracoes(kit).find((i) => i.id === "receber_venda").estado, "fora");
});

test("o que o cliente ja tem tambem acende as ligacoes", () => {
  const kit = alternar(novo(["vendas"]), "FINANCEIRO");
  assert.equal(integracoes(kit).find((i) => i.id === "receber_venda").estado, "ativa");
});

test("contar ligacoes acesas", () => {
  let kit = novo();
  assert.equal(contarLigacoes(kit), 0);
  for (const c of ["ESTOQUE", "VENDAS", "FINANCEIRO"]) kit = alternar(kit, c);
  // estoque->vendas, vendas->financeiro e estoque->financeiro (compra vira conta a pagar)
  assert.equal(contarLigacoes(kit), 3);
});

test("a sugestao aparece quando falta pouco para um combo valer a pena", () => {
  let kit = novo();
  for (const c of ["ESTOQUE", "VENDAS", "CLIENTES"]) kit = alternar(kit, c);

  const oferta = sugestao(kit);
  assert.equal(oferta.codigo, "GESTAO");
  assert.deepEqual(oferta.faltando, ["FINANCEIRO"]);
  assert.ok(oferta.economia > 0);
});

test("com o combo completo nao ha mais o que sugerir", () => {
  const kit = aplicarCombo(novo(), "GESTAO");
  assert.equal(sugestao(kit), null);
});

test("o pedido separa combo de avulsos", () => {
  let kit = aplicarCombo(novo(), "GESTAO");
  kit = alternar(kit, "AGENDA");

  assert.deepEqual(pedido(kit), { combo: "GESTAO", produtos: ["AGENDA"] });
});

test("limpar zera a escolha e mantem o que o cliente ja tem", () => {
  let kit = alternar(novo(["estoque"]), "VENDAS");
  kit = limpar(kit);
  assert.equal(resumo(kit).vazio, true);
  assert.deepEqual(kit.jaTem, ["ESTOQUE"]);
});


// ------------------------------------------------------------ kits reais ---
test("todo kit de reserva sai mais barato que os seus modulos avulsos", () => {
  const precos = Object.fromEntries(catalogoLocal().produtos.map((p) => [p.codigo, p.preco]));
  for (const kit of KITS_PADRAO) {
    const avulso = kit.produtos.reduce((soma, c) => soma + precos[c], 0);
    assert.ok(kit.preco < avulso, `${kit.codigo}: ${kit.preco} nao e menor que ${avulso}`);
  }
});

test("marcar os modulos de um kit aplica o preco dele sozinho", () => {
  const r = resumo(marcar(comKits(), ["VENDAS", "ESTOQUE", "CLIENTES"]));
  assert.equal(r.combo, "COMERCIO");
  assert.equal(r.total, 119.9);
});

test("os 7 modulos marcados um a um viram o Kit Completo", () => {
  const r = resumo(marcar(comKits(), ["AGENDA", "CLIENTES", "ESTOQUE", "FINANCEIRO",
                                      "ORCAMENTOS", "ORDENS", "VENDAS"]));
  assert.equal(r.combo, "COMPLETO");
  assert.equal(r.total, 229.9);
});

test("com 6 modulos, a sugestao e levar o setimo quase de graca", () => {
  const kit = marcar(comKits(), ["CLIENTES", "ESTOQUE", "FINANCEIRO", "ORCAMENTOS", "ORDENS", "VENDAS"]);
  const oferta = sugestao(kit);
  assert.equal(oferta.codigo, "COMPLETO");
  assert.deepEqual(oferta.faltando, ["AGENDA"]);
  assert.ok(oferta.acrescimo < 1, `acrescimo ${oferta.acrescimo}`);
});

test("nunca sugere kit que nao baixa o total", () => {
  // com o Gestao no carrinho, completar o Atendimento (+Agenda) nao muda nada
  const kit = marcar(comKits(), ["CLIENTES", "ESTOQUE", "FINANCEIRO", "VENDAS"]);
  const oferta = sugestao(kit);
  assert.notEqual(oferta?.codigo, "ATENDIMENTO");
  if (oferta) assert.ok(oferta.acrescimo < oferta.avulso);
});

test("quem ja tem modulo nao paga kit mais caro que o que falta", () => {
  // ja tem Vendas: Estoque + Clientes avulsos (99,80) sao melhores que o Comercio (119,90)
  const r = resumo(marcar(comKits(["VENDAS"]), ["ESTOQUE", "CLIENTES"]));
  assert.equal(r.combo, null);
  assert.equal(r.total, 99.8);
});

// ----------------------------------------------------------------- cupom ---
import { descontoDoCupom } from "../js/kit.js";

test("cupom: mesma conta do banco", () => {
  assert.equal(descontoDoCupom({ tipo: "percentual", valor: 10 }, 199.6), 19.96);
  assert.equal(descontoDoCupom({ tipo: "valor", valor: 20 }, 119.9), 20);
  assert.equal(descontoDoCupom({ tipo: "valor", valor: 500 }, 49.9), 48.9);   // nunca abaixo de R$ 1
  assert.equal(descontoDoCupom(null, 100), 0);
  assert.equal(descontoDoCupom({ tipo: "percentual", valor: 10 }, 0), 0);
});

// ---------------------------------------------------------- escolher kit ---
// O bug que isto tranca: o cartao de kit SOMAVA ao que ja estava escolhido,
// enquanto o botao de ramo limpava antes. Clicar em tres kits seguidos deixava
// 7 modulos marcados, acendia um cartao que ninguem clicou (o melhorCombo do
// conjunto) e, no clique seguinte, tirava tudo e nao acendia nada.
test("escolher um kit SUBSTITUI o anterior, nunca soma", () => {
  let kit = escolherKit(comKits(), "COMERCIO");
  const primeiro = resumo(kit);
  assert.equal(primeiro.combo, "COMERCIO");

  kit = escolherKit(kit, "OFICINA");
  const segundo = resumo(kit);
  assert.equal(segundo.combo, "OFICINA", "trocar de kit deveria acender o novo");
  assert.equal(
    segundo.escolhidos.length,
    KITS_PADRAO.find((k) => k.codigo === "OFICINA").produtos.length,
    "sobrou modulo do kit anterior: o kit somou em vez de substituir");

  // e o preco e o do kit escolhido, nao a soma de dois kits
  assert.equal(segundo.total, KITS_PADRAO.find((k) => k.codigo === "OFICINA").preco);
});

test("escolher o mesmo kit duas vezes nao deixa a tela sem nada aceso", () => {
  let kit = escolherKit(comKits(), "COMERCIO");
  kit = escolherKit(kit, "COMERCIO");
  assert.equal(resumo(kit).combo, "COMERCIO",
    "o kit deve continuar aceso: e escolha, nao liga-desliga");
});

// ------------------------------------------------ combo fechado sem querer ---
// O momento que a animacao celebra: o cliente vinha marcando modulo a modulo e,
// sem pedir, fechou um combo. Quem decide SE anima e a tela (so no caminho do
// modulo avulso; clicar no cartao do kit nao e surpresa) - aqui so respondemos
// "mudou para um combo que nao havia antes?".
test("fechar um combo marcando modulos avulsos e um acontecimento", () => {
  const vazio = comKits();
  const kitComercio = KITS_PADRAO.find((k) => k.codigo === "COMERCIO");

  let antes = vazio;
  let depois = marcar(vazio, kitComercio.produtos.slice(0, -1));   // falta um
  assert.equal(comboRecemFechado(antes, depois), null, "ainda nao fechou combo");

  antes = depois;
  depois = marcar(antes, [kitComercio.produtos.at(-1)]);           // fechou
  assert.equal(comboRecemFechado(antes, depois), "COMERCIO");
});

test("o mesmo combo continuando nao e acontecimento de novo", () => {
  const kitComercio = KITS_PADRAO.find((k) => k.codigo === "COMERCIO");
  const fechado = marcar(comKits(), kitComercio.produtos);
  assert.equal(comboRecemFechado(fechado, fechado), null,
    "sem mudanca nao ha o que comemorar");

  // desfazer tambem nao comemora
  const desfeito = alternar(fechado, kitComercio.produtos[0]);
  assert.equal(comboRecemFechado(fechado, desfeito), null);
});

test("subir de um combo para outro maior comemora o novo", () => {
  const comercio = KITS_PADRAO.find((k) => k.codigo === "COMERCIO");
  const antes = marcar(comKits(), comercio.produtos);
  // `marcar` alterna: so os que ainda NAO estao escolhidos
  const faltando = MODULOS.map((m) => m.codigo)
    .filter((c) => !comercio.produtos.includes(c));
  const depois = marcar(antes, faltando);
  assert.equal(comboRecemFechado(antes, depois), "COMPLETO");
});
