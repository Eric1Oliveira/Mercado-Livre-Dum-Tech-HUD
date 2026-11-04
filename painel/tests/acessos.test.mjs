// As regras de Contas e acessos: a senha que nasce no navegador, as vagas e a migracao.
import assert from "node:assert/strict";
import test from "node:test";

import {
  AVISOS, ITERACOES, VERSAO_COM_LOGIN, avisosDos, derivarSenha, filtrarAcessos, gerarProvisoria,
  licencasParaExigir, modulosDaEdicao, montarAcessos, resumoMigracao, temLogin, vagasASoltar,
} from "../js/acessos.js";
import { ITERACOES as ITERACOES_DO_SERVIDOR, conferirSenha, senhaAceitavel } from "../../supabase/functions/acesso/nucleo.ts";

const cliente = (id, extras = {}) => ({ licenca_id: `lic-${id}`, nome: id, situacao: "ativa", ...extras });

test("a senha que nasce aqui e a que o servidor confere", async () => {
  const guardado = await derivarSenha("kmpr-4821-tzq", { iteracoes: 10_000 });
  assert.match(guardado, /^pbkdf2\$10000\$[A-Za-z0-9_-]+\$[A-Za-z0-9_-]+$/);
  assert.ok(await conferirSenha("kmpr-4821-tzq", guardado));
  assert.ok(!(await conferirSenha("kmpr-4821-tzz", guardado)));
  assert.equal(ITERACOES, ITERACOES_DO_SERVIDOR, "painel e servidor no mesmo custo");
});

test("acentos derivam igual dos dois lados", async () => {
  const composta = "coração-azul";
  const decomposta = "coração-azul";
  assert.ok(await conferirSenha(decomposta, await derivarSenha(composta, { iteracoes: 10_000 })));
});

test("sal novo a cada senha", async () => {
  assert.notEqual(await derivarSenha("igual", { iteracoes: 10_000 }), await derivarSenha("igual", { iteracoes: 10_000 }));
});

test("provisoria facil de ditar e que o servidor aceita", () => {
  const vistas = new Set();
  for (let i = 0; i < 50; i += 1) {
    const senha = gerarProvisoria();
    assert.match(senha, /^[a-z]{4}-[2-9]{4}-[a-z]{3}$/);
    assert.doesNotMatch(senha, /[ilo]/, "sem letra que se confunda");
    assert.equal(senhaAceitavel(senha, "maria"), "");
    vistas.add(senha);
  }
  assert.ok(vistas.size > 45, "nao repete");
});

test("quantos computadores precisam sair", () => {
  assert.equal(vagasASoltar(3, 1), 2);
  assert.equal(vagasASoltar(1, 3), 0, "aumentar nao solta ninguem");
  assert.equal(vagasASoltar(2, 2), 0);
});

test("so a partir da 1.11.0 o computador pede login", () => {
  assert.equal(VERSAO_COM_LOGIN, "1.11.0");
  assert.ok(temLogin("1.11.0"));
  assert.ok(temLogin("1.12.3"));
  assert.ok(temLogin("2.0.0"));
  assert.ok(!temLogin("1.10.0"));
  assert.ok(!temLogin("1.9.0"));
  assert.ok(!temLogin(""), "quem nunca disse a versao e tratado como antigo");
});

test("editar nao tira o modulo que nao tem caixa", () => {
  assert.deepEqual(modulosDaEdicao(["vendas"], ["vendas", "agenda"], ["vendas", "estoque"]), ["vendas", "agenda"],
    "agenda em teste gratis continua");
  assert.deepEqual(modulosDaEdicao([], ["vendas"], ["vendas"]), [], "desmarcou de verdade: sai");
});

test("os avisos seguem os modulos marcados", () => {
  assert.deepEqual(avisosDos(["estoque", "vendas"]), [...AVISOS.estoque, ...AVISOS.vendas]);
  assert.deepEqual(avisosDos(["nao_existe"]), []);
});

test("uma linha por loja com chave, com as contas e os computadores antigos", () => {
  const linhas = montarAcessos(
    [cliente("a"), cliente("b"), { nome: "sem chave", licenca_id: null }],
    [{ licenca_id: "lic-a", contas: 3, adms: 1, funcionarios: 2, exigir_conta: true, email_difere: true }],
    [{ licenca_id: "lic-a", versao: "1.9.0" }, { licenca_id: "lic-a", versao: "1.11.0" }, { licenca_id: "lic-b", versao: "" }],
  );
  assert.equal(linhas.length, 2);
  const [a, b] = linhas;
  assert.equal(a.contas, 3);
  assert.equal(a.funcionarios, 2);
  assert.equal(a.semLogin, 1);
  assert.equal(a.exigirConta, true);
  assert.equal(a.emailDifere, true);
  assert.equal(b.contas, 0);
  assert.equal(b.semLogin, 1);
});

test("a contagem da migracao", () => {
  const linhas = montarAcessos(
    [cliente("a"), cliente("b"), cliente("c")],
    [{ licenca_id: "lic-a", contas: 2 }, { licenca_id: "lic-b", exigir_conta: true }],
    [{ licenca_id: "lic-a", versao: "1.9.0" }, { licenca_id: "lic-c", versao: "1.9.0" }],
  );
  assert.deepEqual(resumoMigracao(linhas), {
    total: 3, comConta: 1, semConta: 2, exigindo: 1, computadoresSemLogin: 1,
  });
});

test("os filtros", () => {
  const linhas = montarAcessos(
    [cliente("a"), cliente("b"), cliente("c")],
    [{ licenca_id: "lic-a", contas: 2 }, { licenca_id: "lic-b", exigir_conta: true },
     { licenca_id: "lic-c", contas: 1, email_difere: true }],
    [{ licenca_id: "lic-a", versao: "1.9.0" }],
  );
  const nomes = (filtro) => filtrarAcessos(linhas, filtro).map((l) => l.cliente.nome);
  assert.deepEqual(nomes("todas"), ["a", "b", "c"]);
  assert.deepEqual(nomes("sem_conta"), ["b"]);
  assert.deepEqual(nomes("com_conta"), ["a", "c"]);
  assert.deepEqual(nomes("exigindo"), ["b"]);
  assert.deepEqual(nomes("atencao"), ["a", "c"]);
});

test("exigir de todas pega so chave ativa que ainda nao exige", () => {
  const linhas = montarAcessos(
    [cliente("a"), cliente("b"), cliente("c", { situacao: "suspensa" })],
    [{ licenca_id: "lic-b", exigir_conta: true }],
  );
  assert.deepEqual(licencasParaExigir(linhas), ["lic-a"]);
});
