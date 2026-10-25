// node --test painel/tests/saude.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import {
  andamentoDoTeste, compararVersoes, deslocar, diaLocal, diasEntre, estadoDeUso, estadoDoCelular,
  estadoDoTeste, fimEstendido, hubAberto, modulosParados, nivel, ordenarTestes, prazoDoTeste,
  resumoDosTestes, resumoMaisNovo, resumoVelho, saudeDosClientes, serieDaFaixa, serieDiaria, ultimosDias,
  variacao, versaoEmDia, virouPedido,
} from "../js/saude.js";
import { relativo } from "../js/formato.js";
import { mensagemDeAcompanhamento } from "../js/mensagens.js";

// segunda, 19/10/2026, 15h no relogio de quem olha
const AGORA = new Date(2026, 9, 19, 15, 0);
const antes = (horas) => new Date(AGORA.getTime() - horas * 3600000).toISOString();
const depois = (horas) => new Date(AGORA.getTime() + horas * 3600000).toISOString();

test("dias no fuso de quem olha, do mais antigo ate hoje", () => {
  assert.equal(diaLocal(AGORA), "2026-10-19");
  assert.deepEqual(ultimosDias(3, AGORA), ["2026-10-17", "2026-10-18", "2026-10-19"]);
  assert.equal(ultimosDias(30, AGORA)[0], "2026-09-20");
  assert.equal(diasEntre("2026-10-01", "2026-10-19"), 18);
  // virada de mes e horario de verao nao tiram nem poem dia
  assert.equal(diasEntre("2026-02-27", "2026-03-02"), 3);
});

test("serie diaria soma o dia e poe zero onde nao houve uso", () => {
  const serie = serieDiaria([
    { dia: "2026-10-19", aberturas: 3 }, { dia: "2026-10-19", aberturas: 2 },
    { dia: "2026-10-17", aberturas: 1 }, { dia: "2026-09-01", aberturas: 9 },
  ], 3, AGORA);
  assert.deepEqual(serie, [
    { dia: "2026-10-17", valor: 1 }, { dia: "2026-10-18", valor: 0 }, { dia: "2026-10-19", valor: 5 },
  ]);
});

test("a faixa do banco cai nos dias de quem olha", () => {
  const linha = { ate: "2026-10-18", ultimos_30: [...Array(28).fill(0), 7, 3] };
  const serie = serieDaFaixa(linha, 30, AGORA);
  // o banco fechou ontem (virada do dia): ontem = 3, anteontem = 7, hoje = 0
  assert.deepEqual(serie.slice(-3).map((d) => [d.dia, d.valor]),
                   [["2026-10-17", 7], ["2026-10-18", 3], ["2026-10-19", 0]]);
  assert.equal(serieDaFaixa(null, 30, AGORA).every((d) => d.valor === 0), true);
  assert.equal(deslocar("2026-03-01", -1), "2026-02-28");
  assert.equal(deslocar("2026-12-31", 1), "2027-01-01");
});

test("a faixa usa a mesma regua para todo mundo", () => {
  assert.equal(nivel(0, 10), 0);
  assert.equal(nivel(1, 10), 1);
  assert.equal(nivel(5, 10), 2);
  assert.equal(nivel(10, 10), 4);
  assert.equal(nivel(3, 0), 0);
  assert.equal(variacao(12, 10), 20);
  assert.equal(variacao(5, 10), -50);
  assert.equal(variacao(5, 0), null);
});

test("estado de uso: quem precisa de voce aparece primeiro", () => {
  assert.equal(estadoDeUso({ ultimoUso: "2026-10-19", ativadoEm: antes(500) }, AGORA), "usando");
  assert.equal(estadoDeUso({ ultimoUso: "2026-10-12", ativadoEm: antes(500) }, AGORA), "usando");
  assert.equal(estadoDeUso({ ultimoUso: "2026-10-11", ativadoEm: antes(500) }, AGORA), "esfriando");
  assert.equal(estadoDeUso({ ultimoUso: "2026-10-05", ativadoEm: antes(500) }, AGORA), "esfriando");
  assert.equal(estadoDeUso({ ultimoUso: "2026-10-04", ativadoEm: antes(500) }, AGORA), "sumiu");
  // instalou e nunca abriu um modulo; instalou agora ha pouco; nem instalou
  assert.equal(estadoDeUso({ ativadoEm: antes(80) }, AGORA), "nunca");
  assert.equal(estadoDeUso({ ativadoEm: antes(5) }, AGORA), "comecando");
  assert.equal(estadoDeUso({}, AGORA), "sem_ativar");
});

test("Hub aberto: falou com o servidor na ultima hora e pouco", () => {
  assert.equal(hubAberto({ ultima_checagem: antes(5), versao_em: antes(0.5) }, AGORA), true);
  assert.equal(hubAberto({ ultima_checagem: antes(3) }, AGORA), false);
  assert.equal(hubAberto({}, AGORA), false);
  assert.equal(compararVersoes("1.4.10", "1.4.9"), 1);
  assert.equal(compararVersoes("1.4", "1.4.0"), 0);
  assert.equal(versaoEmDia("1.4.1", "1.4.3"), false);
  assert.equal(versaoEmDia("1.4.3", "1.4.3"), true);
  assert.equal(versaoEmDia("", "1.4.3"), null);
});

test("saude dos clientes: so licenca ativa, ordenada por atencao", () => {
  const linhas = saudeDosClientes({
    clientes: [
      { cliente_id: "a", licenca_id: "la", situacao: "ativa", nome: "Ana", ultimo_uso: "2026-10-19" },
      { cliente_id: "b", licenca_id: "lb", situacao: "ativa", nome: "Bia", ultimo_uso: "2026-09-20" },
      { cliente_id: "c", licenca_id: "lc", situacao: "suspensa", nome: "Caio", ultimo_uso: null },
      { cliente_id: "d", licenca_id: null, situacao: null, nome: "Duda (sem licenca)" },
    ],
    faixas: [{ cliente_id: "a", ate: "2026-10-19", ultimos_30: [...Array(28).fill(0), 2, 4] }],
    ativacoes: [
      { licenca_id: "la", apelido: "Caixa", versao: "1.4.3", ativado_em: antes(900), versao_em: antes(0.2) },
      { licenca_id: "lb", apelido: "", versao: "1.4.1", ativado_em: antes(900), ultima_checagem: antes(200) },
    ],
    aparelhos: [{ licenca_id: "la" }, { licenca_id: "la", revogado_em: antes(1) }],
    publicada: "1.4.3",
  }, AGORA);

  assert.deepEqual(linhas.map((l) => l.cliente.nome), ["Bia", "Ana"]);
  const [bia, ana] = linhas;
  assert.equal(bia.estado, "sumiu");
  assert.equal(ana.estado, "usando");
  assert.equal(ana.aberturas, 6);
  assert.equal(ana.diasComUso, 2);
  assert.equal(ana.serie.length, 30);
  assert.equal(ana.celulares, 1, "celular desconectado nao conta");
  assert.deepEqual(ana.computadores.map((c) => [c.apelido, c.emDia, c.aberto]), [["Caixa", true, true]]);
  assert.deepEqual(bia.computadores.map((c) => [c.apelido, c.emDia, c.aberto]), [["Computador", false, false]]);
});

test("modulo pago parado: licenca ativa, comprado ha uma semana, zero em 30 dias", () => {
  const parados = modulosParados([
    { codigo: "VENDAS", situacao: "ativa", aberturas_30d: 9, liberado_em: antes(2000) },
    { codigo: "AGENDA", situacao: "ativa", aberturas_30d: 0, liberado_em: antes(2000), ultimo_uso: "2026-08-01" },
    { codigo: "ESTOQUE", situacao: "ativa", aberturas_30d: 0, liberado_em: antes(2000), ultimo_uso: null },
    { codigo: "FINANCEIRO", situacao: "ativa", aberturas_30d: 0, liberado_em: antes(24) },
    { codigo: "ORDENS", situacao: "cancelada", aberturas_30d: 0, liberado_em: antes(2000) },
  ], AGORA);
  assert.deepEqual(parados.map((m) => m.codigo), ["ESTOQUE", "AGENDA"]);
});

test("teste gratis: estado, prazo, andamento e o fim ao estender", () => {
  const teste = { iniciado_em: antes(24 * 3), termina_em: depois(24 * 4) };
  assert.equal(estadoDoTeste(teste, AGORA), "rodando");
  assert.equal(estadoDoTeste({ termina_em: depois(30) }, AGORA), "acabando");
  assert.equal(estadoDoTeste({ termina_em: antes(1) }, AGORA), "terminou");
  assert.equal(estadoDoTeste({ termina_em: antes(1), comprou: true }, AGORA), "comprou");
  assert.equal(prazoDoTeste(teste, AGORA), "termina em 4 dias");
  assert.equal(prazoDoTeste({ termina_em: depois(2) }, AGORA), "termina hoje");
  assert.equal(prazoDoTeste({ termina_em: depois(24) }, AGORA), "termina amanhã");
  assert.equal(prazoDoTeste({ termina_em: antes(24 * 2) }, AGORA), "terminou há 2 dias");
  assert.equal(Math.round(andamentoDoTeste(teste, AGORA) * 7), 3);
  // estender teste que ja acabou conta de agora; o que ainda corre, do fim
  assert.equal(fimEstendido(antes(48), 7, AGORA), new Date(AGORA.getTime() + 7 * 86400000).toISOString());
  assert.equal(fimEstendido(teste.termina_em, 7, AGORA), depois(24 * 11));
});

test("numeros dos testes e a ordem da tela", () => {
  const testes = [
    { id: 1, termina_em: antes(5), comprou: true, aberturas: 12 },
    { id: 2, termina_em: antes(50), aberturas: 0 },
    { id: 3, termina_em: depois(20), aberturas: 3 },
    { id: 4, termina_em: depois(100), aberturas: 1 },
    { id: 5, termina_em: antes(2), aberturas: 4 },
  ];
  const r = resumoDosTestes(testes, AGORA);
  assert.deepEqual([r.testando, r.acabando, r.terminou, r.comprou, r.usaram, r.conversao], [2, 1, 2, 1, 4, 33]);
  assert.deepEqual(ordenarTestes(testes, AGORA).map((t) => t.id), [3, 4, 5, 2, 1]);
  assert.equal(resumoDosTestes([], AGORA).conversao, null);
});

test("celular: em uso, parado, desconectado e o resumo atrasado", () => {
  assert.equal(estadoDoCelular({ ultimo_acesso: antes(30) }, AGORA), "ativo");
  assert.equal(estadoDoCelular({ ultimo_acesso: antes(24 * 9) }, AGORA), "parado");
  assert.equal(estadoDoCelular({}, AGORA), "nunca");
  assert.equal(estadoDoCelular({ ultimo_acesso: antes(1), revogado_em: antes(1) }, AGORA), "desconectado");
  const novos = resumoMaisNovo([
    { licenca_id: "la", atualizado_em: antes(60) }, { licenca_id: "la", atualizado_em: antes(1) },
  ]);
  assert.equal(novos.get("la"), antes(1));
  assert.equal(resumoVelho(antes(1), AGORA), false);
  assert.equal(resumoVelho(antes(49), AGORA), true);
  assert.equal(resumoVelho(null, AGORA), true);
});

test("clicou em Comprar no Hub: virou pedido so se o pedido veio depois", () => {
  const clique = { cliente_id: "a", email: "ana@x.com", criado_em: antes(10) };
  assert.equal(virouPedido(clique, [{ cliente_id: "a", criado_em: antes(9) }]), true);
  assert.equal(virouPedido(clique, [{ email: "ANA@x.com ", criado_em: antes(2) }]), true);
  assert.equal(virouPedido(clique, [{ cliente_id: "a", criado_em: antes(30) }]), false);
  assert.equal(virouPedido(clique, [{ cliente_id: "b", criado_em: antes(1) }]), false);
});

test("tempo relativo em minutos e horas", () => {
  assert.equal(relativo(antes(0), AGORA), "agora");
  assert.equal(relativo(antes(0.5), AGORA), "há 30 min");
  assert.equal(relativo(antes(5), AGORA), "há 5 h");
  assert.equal(relativo(antes(24 * 3), AGORA), "há 3 dias");
  assert.equal(relativo(null, AGORA), "nunca");
});

test("recado de acompanhamento nao entrega o que o painel sabe", () => {
  const texto = mensagemDeAcompanhamento("teste", { nome: "Ana Souza", modulo: "Agenda" });
  assert.match(texto, /^Olá, Ana!/);
  assert.match(texto, /teste do módulo Agenda/);
  for (const motivo of ["teste", "teste_fim", "parado", "sumiu", "celular", "loja"]) {
    assert.doesNotMatch(mensagemDeAcompanhamento(motivo, { nome: "Ana" }), /vi que|percebi|notei|dias sem/i);
  }
  assert.equal(mensagemDeAcompanhamento("???", {}), mensagemDeAcompanhamento("sumiu", {}));
});

test("o teto do grafico e redondo e a linha do meio e inteira", async () => {
  const { tetoRedondo } = await import("../js/graficos.js");
  assert.deepEqual([0, 1, 3, 7, 10, 11, 23, 100, 140, 260].map(tetoRedondo),
                   [2, 2, 4, 8, 10, 20, 30, 100, 150, 300]);
});
