// O Hub no celular: o que aparece na tela a partir do que o servidor manda.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  aberturaDaTela, alertasDaTela, cartoesVisiveis, codigoDoEndereco, compacto, destaqueDaTela, escala,
  estaAntigo, formatar, haQuanto, hojePorExtenso, linkDaLoja, linkWhatsApp, montarTela, nomeDoAparelho,
  rotulosVisiveis, textoDaVariacao,
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

// ------------------------------------------------------------ formato 2 ---
const sp = (texto) => texto.replace(/\s/g, " "); // o Intl usa espaco que nao quebra

test("dinheiro e numero como o brasileiro le", () => {
  assert.equal(sp(formatar(1234.5)), "R$ 1.234,50");
  assert.equal(formatar(12, "numero"), "12");
  assert.equal(sp(compacto(900)), "R$ 900");
  assert.equal(sp(compacto(1500)), "R$ 1,5 mil");
  assert.equal(compacto(7, "numero"), "7");
});

test("o eixo e redondo, tem o zero e nao inventa fracao de compromisso", () => {
  assert.deepEqual(escala([0, 3565]).marcas, [0, 2000, 4000]);
  assert.deepEqual(escala([0, 3, 5, 2], { inteiros: true }).marcas, [0, 2, 4, 6]);
  const negativo = escala([6000, -2000]);
  assert.ok(negativo.menor <= -2000 && negativo.maior >= 6000);
  assert.ok(negativo.marcas.includes(0), "o zero precisa aparecer quando o saldo fica negativo");
  // dia sem venda: eixo de verdade, e nao "R$ 0, R$ 0, R$ 0"
  assert.deepEqual(escala([0, 0, 0], { topo: 100 }).marcas.at(-1) >= 100, true);
  assert.deepEqual(escala([null, undefined, 4]).marcas.at(-1) >= 4, true);
});

test("o eixo X mostra poucos rotulos e sempre o ultimo (hoje)", () => {
  assert.deepEqual(rotulosVisiveis(7, 7), [0, 1, 2, 3, 4, 5, 6]);
  const trinta = rotulosVisiveis(30, 6);
  assert.ok(trinta.length <= 6);
  assert.equal(trinta.at(-1), 29);
});

const vendas = (extra = {}) => ({
  app: "VENDAS", titulo: "Vendas",
  cartoes: [{ rotulo: "Vendido hoje", valor: "R$ 50,00", papel: "destaque" }, { rotulo: "No mês", valor: "R$ 900,00" }],
  listas: [], ...extra,
});
const periodos = [{ nome: "Hoje", rotulo: "Vendido hoje", valor: "R$ 50,00", numero: 50 }];

test("a tela abre com o destaque da secao de maior peso", () => {
  const tela = montarTela(resposta(["VENDAS"], [vendas({ destaque: { periodos } })]));
  const abertura = aberturaDaTela(tela);
  assert.equal(abertura.destaque.periodos[0].valor, "R$ 50,00");
  assert.equal(abertura.secao.app, "VENDAS");
  // o cartao que o celular antigo usava como destaque nao se repete na grade
  assert.deepEqual(cartoesVisiveis(abertura.secao).map((c) => c.rotulo), ["No mês"]);
});

test("Hub antigo (sem destaque) continua abrindo com o primeiro cartao", () => {
  const antigo = { app: "VENDAS", titulo: "Vendas", listas: [],
                   cartoes: [{ rotulo: "Vendido hoje", valor: "R$ 50,00" }, { rotulo: "Ticket", valor: "R$ 5,00" }] };
  const abertura = aberturaDaTela(montarTela(resposta(["VENDAS"], [antigo])));
  assert.equal(abertura.cartao.rotulo, "Vendido hoje");
  assert.equal(aberturaDaTela(montarTela(resposta([], []))), null);
  // sem destaque, o cartao marcado continua aparecendo
  assert.equal(cartoesVisiveis(vendas()).length, 2);
});

test("precisa de voce: problema antes de lembrete, dinheiro primeiro", () => {
  const tela = montarTela(resposta(["VENDAS", "ESTOQUE", "CLIENTES"], [
    vendas({ alertas: [{ texto: "Fechar o caixa", tom: "aviso" }] }),
    { app: "ESTOQUE", titulo: "Estoque", cartoes: [], listas: [],
      alertas: [{ texto: "Repor 2 produtos zerados", tom: "perigo" }, { texto: "", tom: "perigo" }] },
    { app: "CLIENTES", titulo: "Clientes", cartoes: [], listas: [],
      alertas: [{ texto: "Dar parabéns a Ana", tom: "ok" }] },
    { app: "ORDENS", titulo: "Ordens", cartoes: [], listas: [], alertas: [{ texto: "nao liberado" }] },
  ]));
  const alertas = alertasDaTela(tela);
  assert.deepEqual(alertas.map((a) => a.texto), ["Repor 2 produtos zerados", "Fechar o caixa", "Dar parabéns a Ana"]);
  assert.equal(alertas[0].app, "ESTOQUE");
  assert.deepEqual(alertasDaTela(null), []);
});

test("a variacao tem seta, numero e o nome do que foi comparado", () => {
  assert.deepEqual(textoDaVariacao({ texto: "+18%", direcao: "sobe", tom: "ok", comparado: "sábado passado" }),
                   { seta: "▲", numero: "18%", tom: "ok", comparado: "vs. sábado passado" });
  assert.equal(textoDaVariacao({ texto: "\u22124%", direcao: "desce", tom: "perigo" }).numero, "4%");
  assert.equal(textoDaVariacao(null), null);
});

test("WhatsApp so com numero brasileiro inteiro", () => {
  const link = new URL(linkWhatsApp({ tipo: "whatsapp", numero: "5563988887777", mensagem: "Feliz aniversário!" }));
  assert.equal(link.origin + link.pathname, "https://wa.me/5563988887777");
  assert.equal(link.searchParams.get("text"), "Feliz aniversário!");
  for (const ruim of [{ tipo: "whatsapp", numero: "123" }, { tipo: "whatsapp", numero: "55639888877771234" },
                      { tipo: "link", numero: "5563988887777" }, { tipo: "whatsapp", numero: "javascript:alert(1)" }, null]) {
    assert.equal(linkWhatsApp(ruim), "");
  }
});

test("o dia de hoje por extenso, sem o -feira", () => {
  assert.equal(hojePorExtenso(new Date(2026, 9, 17, 10)), "Sábado, 17 de outubro");
  assert.equal(hojePorExtenso(new Date(2026, 9, 16, 10)), "Sexta, 16 de outubro");
});


test("reserva do link aparece no topo, sem depender do computador ligado", () => {
  const tela = montarTela({ reservas: [{ nome: "Ana", servico: "Corte", inicio: "2026-11-05T14:30" }] });
  const alertas = alertasDaTela(tela);
  assert.equal(alertas.length, 1);
  assert.equal(alertas[0].texto, "Ana marcou Corte");
  assert.equal(alertas[0].detalhe, "05/11 às 14:30");
  assert.equal(alertas[0].app, "AGENDA");
});

test("resposta antiga, sem reservas, continua funcionando", () => {
  assert.deepEqual(alertasDaTela(montarTela({})), []);
});
