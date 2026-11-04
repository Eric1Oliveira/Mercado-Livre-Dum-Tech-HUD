// As regras da gestão de clientes: o que aparece, o que filtra e o que exporta.
import assert from "node:assert/strict";
import test from "node:test";

import {
  ATALHOS, atalhoAtivo, buscaCombina, comPresenca, contarOpcoes, csvDosClientes, distribuicaoDeVersoes,
  estadoDaAtualizacao, filtrar, GRUPOS, lerEtiquetas, linhaDoTempo, montarClientes, opcoesDoGrupo,
  ordenarLinhas, quantosFiltros, versaoAlvo, versaoPendente,
} from "../js/gestao.js";

const AGORA = new Date("2026-11-01T15:00:00-03:00");
const minutos = (n) => new Date(AGORA.getTime() - n * 60000).toISOString();

const clienteBase = (id, extras = {}) => ({
  cliente_id: id, nome: id, email: `${id}@teste.local`, telefone: "", documento: "",
  licenca_id: `lic-${id}`, chave: `CH-${id}`, tipo: "vitalicia", situacao: "ativa", status: "ativa",
  expira_em: null, produtos_codigos: ["VENDAS"], ultimo_uso: "2026-11-01", total_comprado: 100,
  cliente_desde: "2026-01-01", pedidos_abertos: 0, ...extras,
});

const pc = (id, maquina, extras = {}) => ({
  licenca_id: `lic-${id}`, maquina, apelido: maquina, versao: "1.9.0", versao_em: minutos(600),
  ativado_em: "2026-02-01T10:00:00Z", ultima_checagem: minutos(600), ...extras,
});

const batida = (id, maquina, minutosAtras, extras = {}) => ({
  licenca_id: `lic-${id}`, maquina, visto_em: minutos(minutosAtras), online_desde: minutos(120),
  versao: "1.9.0", versao_desde: minutos(9000), ...extras,
});

const BASE = {
  clientes: [
    clienteBase("ana", { produtos_codigos: ["VENDAS", "ESTOQUE"], total_comprado: 900 }),
    clienteBase("bia", { tipo: "assinatura", expira_em: "2026-11-20" }),
    clienteBase("caio", { situacao: "suspensa", produtos_codigos: ["ESTOQUE"] }),
    clienteBase("dora", { licenca_id: null, chave: null, situacao: null, tipo: null, produtos_codigos: [], total_comprado: 0 }),
  ],
  ativacoes: [pc("ana", "PC1"), pc("ana", "PC2", { versao: "1.8.0" }), pc("bia", "PC3"), pc("caio", "PC4", { versao: "1.7.0" })],
  presencas: [batida("ana", "PC1", 1), batida("ana", "PC2", 30, { versao: "1.8.0" }), batida("bia", "PC3", 60)],
  liberacoes: [{ licenca_id: "lic-bia", versao: "1.10.0", forcada: true }],
  gestao: [
    { cliente_id: "ana", etiquetas: ["vip", "Revenda"], proximo_contato: "2026-11-01", compras: 3, canal: "mercadolivre" },
    { cliente_id: "bia", etiquetas: [], proximo_contato: "2026-12-01", compras: 1, canal: "site" },
  ],
  catalogo: ["VENDAS", "ESTOQUE", "AGENDA"],
  publicada: "1.9.0",
  alvo: "1.10.0",
};

const linhas = () => montarClientes(BASE, AGORA);
const nomes = (lista) => lista.map((l) => l.id);

// ---------------------------------------------------------------- presença --
test("a batida traz a hora e a versão mais novas que a ativação", () => {
  const [a] = comPresenca([pc("ana", "PC1", { versao: "1.8.0" })], [batida("ana", "PC1", 1, { versao: "1.9.0" })]);
  assert.equal(a.versao, "1.9.0");
  assert.equal(a.visto_em, minutos(1));
});

test("computador sem batida fica como veio", () => {
  const ativacao = pc("ana", "PC9");
  assert.deepEqual(comPresenca([ativacao], []), [ativacao]);
});

test("online é quem bateu nos últimos 5 minutos, não na última hora", () => {
  const [ana, bia, caio, dora] = linhas();
  assert.equal(ana.conexao, "online");
  assert.equal(ana.online, 1, "só o PC1 bateu agora");
  assert.equal(bia.conexao, "offline", "bateu há 1 hora: já não está");
  assert.equal(caio.conexao, "offline", "viu pela ativação antiga");
  assert.equal(dora.conexao, "nunca");
});

// ------------------------------------------------------------- lançamentos --
test("a pendente é a mais nova, ainda sem lançar, acima da publicada", () => {
  const lancamentos = [
    { versao: "1.9.0", liberada_em: "2026-10-30" },
    { versao: "1.10.0", liberada_em: null },
    { versao: "1.11.0", liberada_em: null, descartada_em: "2026-11-01" },
    { versao: "1.8.0", liberada_em: null },
  ];
  assert.equal(versaoPendente(lancamentos, "1.9.0").versao, "1.10.0");
  assert.equal(versaoPendente(lancamentos, "1.10.0"), null);
  assert.equal(versaoPendente([], "1.9.0"), null);
});

test("sem pendente, Atualizar e Forçar entregam a publicada", () => {
  assert.equal(versaoAlvo([], "1.9.0"), "1.9.0");
  assert.equal(versaoAlvo([{ versao: "1.10.0" }], "1.9.0"), "1.10.0");
});

// ------------------------------------------------- o estado da atualização --
test("o estado segue o computador mais atrasado", () => {
  const estado = (extras) => estadoDaAtualizacao({ publicada: "1.9.0", ...extras });
  assert.equal(estado({ versoes: [] }), "sem_hub");
  assert.equal(estado({ versoes: ["1.9.0"] }), "em_dia");
  assert.equal(estado({ versoes: ["1.10.0"] }), "em_dia");
  assert.equal(estado({ versoes: ["1.9.0", "1.8.0"] }), "atrasado");
  assert.equal(estado({ versoes: ["1.8.0"], forcadaGeral: true }), "forcada");
  assert.equal(estado({ versoes: ["1.9.0"], liberacao: { versao: "1.10.0", forcada: false } }), "liberada");
  assert.equal(estado({ versoes: ["1.9.0"], liberacao: { versao: "1.10.0", forcada: true } }), "forcada");
  assert.equal(estado({ versoes: ["1.10.0"], liberacao: { versao: "1.10.0", forcada: true } }), "em_dia",
               "instalou: a ordem foi cumprida");
});

test("os botões só aparecem para quem está abaixo da versão alvo", () => {
  const [ana, bia, , dora] = linhas();
  assert.ok(ana.podeAtualizar);
  assert.ok(bia.podeAtualizar);
  assert.ok(!dora.podeAtualizar, "sem computador não há o que atualizar");
  const tudoEmDia = montarClientes({ ...BASE, alvo: "1.7.0" }, AGORA);
  assert.ok(!tudoEmDia.some((l) => l.podeAtualizar));
});

// ----------------------------------------------------------------- filtros --
test("os filtros combinam: E entre grupos, OU dentro do grupo", () => {
  const base = linhas();
  assert.deepEqual(nomes(filtrar(base, { filtros: { modulo: ["ESTOQUE"] } }, AGORA)), ["ana", "caio"]);
  assert.deepEqual(nomes(filtrar(base, { filtros: { versao: ["1.7.0", "1.8.0"] } }, AGORA)), ["ana", "caio"]);
  assert.deepEqual(nomes(filtrar(base, { filtros: { modulo: ["ESTOQUE"], versao: ["1.7.0"] } }, AGORA)), ["caio"]);
  assert.deepEqual(nomes(filtrar(base, { filtros: { modulo: ["ESTOQUE"], conexao: ["online"], licenca: ["ativa"] } }, AGORA)), ["ana"]);
  assert.deepEqual(nomes(filtrar(base, { filtros: { modulo: [], versao: [] } }, AGORA)), nomes(base));
});

test("dá para achar quem NÃO tem um módulo", () => {
  assert.deepEqual(nomes(filtrar(linhas(), { filtros: { falta: ["AGENDA"] } }, AGORA)), ["ana", "bia", "caio"],
                   "interessado sem licença não entra: não há o que vender a mais");
});

test("cada grupo conhece os seus valores", () => {
  const f = (filtros) => nomes(filtrar(linhas(), { filtros }, AGORA));
  assert.deepEqual(f({ licenca: ["sem"] }), ["dora"]);
  assert.deepEqual(f({ licenca: ["suspensa"] }), ["caio"]);
  assert.deepEqual(f({ tipo: ["assinatura"] }), ["bia"]);
  assert.deepEqual(f({ validade: ["vence_30"] }), ["bia"]);
  assert.deepEqual(f({ atualizacao: ["forcada"] }), ["bia"]);
  assert.deepEqual(f({ canal: ["mercadolivre"] }), ["ana"]);
  assert.deepEqual(f({ etiqueta: ["vip"] }), ["ana"]);
  assert.deepEqual(f({ contato: ["hoje"] }), ["ana"]);
  assert.deepEqual(f({ versao: ["sem"] }), ["dora"]);
  assert.deepEqual(f({ uso: ["usando"] }), ["ana", "bia"]);
});

test("a busca ignora acento e acha por chave, etiqueta, computador e telefone", () => {
  const [ana] = montarClientes({
    ...BASE,
    clientes: [clienteBase("ana", { nome: "Ana Lúcia", telefone: "(11) 98765-4321", documento: "123.456.789-00" })],
  }, AGORA);
  for (const termo of ["ana lucia", "ANA", "ch-ana", "vip", "pc1", "98765", "123456"]) {
    assert.ok(buscaCombina(ana, termo), termo);
  }
  assert.ok(!buscaCombina(ana, "bruno"));
  assert.ok(!buscaCombina(ana, "12"), "dígito solto não casa com telefone");
});

test("a contagem de um grupo ignora o próprio grupo, mas respeita os outros", () => {
  const contas = contarOpcoes(linhas(), { filtros: { versao: ["1.7.0"], modulo: ["ESTOQUE"] } }, AGORA);
  assert.equal(contas.versao.get("1.8.0"), 1, "marcar uma versão não pode zerar as outras do menu");
  assert.equal(contas.versao.get("1.9.0"), 1);
  assert.equal(contas.licenca.get("suspensa"), 1);
  assert.equal(contas.licenca.get("ativa") ?? 0, 0, "o outro grupo continua valendo");
});

test("o menu de versões vem da mais nova para a mais antiga", () => {
  const grupo = GRUPOS.find((g) => g.id === "versao");
  const conta = new Map([["1.9.0", 3], ["1.10.0", 1], ["sem", 2]]);
  assert.deepEqual(opcoesDoGrupo(grupo, conta).map((o) => o.valor), ["1.10.0", "1.9.0", "sem"]);
});

test("opção marcada não some do menu quando a contagem zera", () => {
  const grupo = GRUPOS.find((g) => g.id === "etiqueta");
  assert.deepEqual(opcoesDoGrupo(grupo, new Map(), ["vip"]), [{ valor: "vip", texto: "vip", conta: 0 }]);
});

test("os atalhos são filtros comuns e se reconhecem", () => {
  for (const atalho of ATALHOS) assert.equal(atalhoAtivo(atalho.filtros), atalho.id);
  assert.equal(atalhoAtivo({ conexao: ["online"], modulo: ["VENDAS"] }), "");
  assert.equal(atalhoAtivo({}), "");
  assert.equal(quantosFiltros({ conexao: ["online"], modulo: ["VENDAS", "ESTOQUE"] }), 3);
});

// ------------------------------------------------------------------- ordem --
test("a ordem padrão traz quem está online para cima", () => {
  assert.equal(ordenarLinhas(linhas())[0].id, "ana");
  assert.deepEqual(nomes(ordenarLinhas(linhas(), "nome", true)), ["ana", "bia", "caio", "dora"]);
  assert.equal(ordenarLinhas(linhas(), "comprado")[0].id, "ana");
});

test("versão ordena como número: 1.10 depois de 1.9", () => {
  const versoes = (versao) => ({ nome: versao, maisVelha: versao, cliente: {} });
  const ordem = ordenarLinhas([versoes("1.9.0"), versoes("1.10.0"), versoes("1.2.0")], "versao", true);
  assert.deepEqual(ordem.map((l) => l.maisVelha), ["1.2.0", "1.9.0", "1.10.0"]);
});

test("quem não vence nunca fica por último na ordem de validade", () => {
  assert.equal(ordenarLinhas(linhas(), "validade", true)[0].id, "bia");
});

test("a distribuição conta computadores por versão", () => {
  assert.deepEqual(distribuicaoDeVersoes([{ versao: "1.9.0" }, { versao: "1.10.0" }, { versao: "1.9.0" }, { versao: "" }]), [
    { versao: "1.10.0", computadores: 1 }, { versao: "1.9.0", computadores: 2 }, { versao: "", computadores: 1 },
  ]);
});

// ---------------------------------------------------------------- exportar --
test("o CSV abre certo no Excel brasileiro", () => {
  const csv = csvDosClientes(linhas());
  assert.ok(csv.startsWith("﻿Cliente;E-mail;"), "BOM e ponto e vírgula");
  assert.equal(csv.trim().split("\r\n").length, 5, "cabeçalho + 4 clientes");
  assert.ok(csv.includes("900,00"), "centavos com vírgula");
});

test("nome vira texto, nunca fórmula", () => {
  const perigosos = ['=HYPERLINK("http://golpe")', "+5511", "-1", "@soma"];
  for (const nome of perigosos) {
    const [linha] = montarClientes({ ...BASE, clientes: [clienteBase("x", { nome })] }, AGORA);
    const celula = csvDosClientes([linha]).split("\r\n")[1].split(";")[0].replace(/^"/, "");
    assert.ok(celula.startsWith("'"), `${nome} saiu como ${celula}`);
  }
});

test("aspas e ponto e vírgula não quebram as colunas", () => {
  const [linha] = montarClientes({ ...BASE, clientes: [clienteBase("x", { nome: 'Loja "A"; filial' })] }, AGORA);
  assert.ok(csvDosClientes([linha]).includes('"Loja ""A""; filial"'));
});

// --------------------------------------------------------------- etiquetas --
test("as etiquetas não repetem, nem por acento ou maiúscula", () => {
  assert.deepEqual(lerEtiquetas(" vip, Revenda ,,VIP, revendá"), ["vip", "Revenda"]);
  assert.deepEqual(lerEtiquetas(""), []);
});

// --------------------------------------------------------- linha do tempo ---
test("a linha do tempo junta tudo, do mais recente para o mais antigo", () => {
  const eventos = linhaDoTempo({
    cliente: { cliente_desde: "2026-01-01T10:00:00Z" },
    pedidos: [{ atendido_em: "2026-03-01T10:00:00Z", itens: [{ nome: "Vendas" }], total: 300 }],
    testes: [{ iniciado_em: "2026-02-01T10:00:00Z", codigo: "AGENDA" }],
    modulos: [{ liberado_em: "2026-03-02T10:00:00Z", codigo: "VENDAS" }, { liberado_em: null, codigo: "X" }],
    maquinas: [{ ativado_em: "2026-01-02T10:00:00Z", apelido: "Caixa", versao: "1.9.0", versao_desde: "2026-10-30T10:00:00Z" }],
    notas: [{ criado_em: "2026-10-31T10:00:00Z", texto: "Ligar na terça", autor: "eric" }],
    nomeDoModulo: (c) => c.toLowerCase(),
  });
  assert.deepEqual(eventos.map((e) => e.tipo),
                   ["nota", "versao", "modulo", "compra", "teste", "computador", "cadastro"]);
  assert.equal(eventos[2].texto, "Módulo liberado: vendas");
  assert.equal(eventos[3].texto, "Comprou: Vendas");
});

test("a mensalidade entra na linha do cliente mensal, nunca na do vitalício", () => {
  const mensalidades = [
    { licenca_id: "lic-bia", tipo: "assinatura", situacao: "pendente", valor: 89.9, plano_nome: "Completo" },
    // linha vitalicia que chegasse por engano e ignorada
    { licenca_id: "lic-ana", tipo: "vitalicia", situacao: "consulta", valor: 10 },
  ];
  const [ana, bia, , dora] = montarClientes({ ...BASE, mensalidades }, AGORA);
  assert.equal(ana.mensal, null);
  assert.equal(bia.mensal.situacao, "pendente");
  assert.equal(dora.mensal, null);
  const todas = montarClientes({ ...BASE, mensalidades }, AGORA);
  assert.deepEqual(filtrar(todas, { filtros: { cobranca: ["pendente"] } }, AGORA).map((l) => l.id), ["bia"]);
  assert.deepEqual(filtrar(todas, { filtros: { tipo: ["vitalicia"] } }, AGORA).map((l) => l.id), ["ana", "caio"]);
  assert.deepEqual(ordenarLinhas(todas, "mensal").map((l) => l.id)[0], "bia");
  assert.match(csvDosClientes([bia]), /;pendente;Completo;89,90;/);
});

test("a linha do tempo junta o histórico da assinatura", () => {
  const tempo = linhaDoTempo({
    cliente: { cliente_desde: "2026-11-01T10:00:00Z" },
    assinatura: [{ quando: "2026-11-03T10:00:00Z", texto: "Assinatura confirmada", detalhe: "Plano Completo", autor: "Eric" }],
  });
  assert.deepEqual(tempo.map((e) => e.tipo), ["assinatura", "cadastro"]);
  assert.equal(tempo[0].detalhe, "Plano Completo");
});
