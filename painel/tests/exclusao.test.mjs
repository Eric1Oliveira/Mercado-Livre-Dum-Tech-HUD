// node --test painel/tests/exclusao.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { PALAVRA, confere, exclusaoPesada, filtroDeBusca, traduzirExclusao } from "../js/exclusao.js";

test("a palavra so confere inteira, sem ligar para maiuscula e espaco", () => {
  assert.equal(PALAVRA, "EXCLUIR");
  assert.equal(confere("EXCLUIR"), true);
  assert.equal(confere("  excluir "), true);
  assert.equal(confere("exclui"), false);
  assert.equal(confere("excluir agora"), false);
  assert.equal(confere(null), false);
});

test("pedido com dinheiro ou entrega pede a palavra; pedido parado nao", () => {
  assert.equal(exclusaoPesada({ atendido_em: "2026-10-01T10:00:00Z" }), true);
  assert.equal(exclusaoPesada({ pagamento: "pago" }), true);
  assert.equal(exclusaoPesada({ pagamento: "aguardando" }), false);
  assert.equal(exclusaoPesada({}), false);
  assert.equal(exclusaoPesada(null), false);
});

test("o 'nao pode' do banco vira frase que diz onde o modulo ainda esta", () => {
  const banco = (tabela) => new Error(
    `update or delete on table "produtos" violates foreign key constraint "x_fkey" on table "${tabela}"`);
  assert.match(traduzirExclusao(banco("licenca_produtos"), "O módulo CRM").message,
               /^O módulo CRM não pode ser excluído: está na licença de algum cliente/);
  assert.match(traduzirExclusao(banco("combo_produtos")).message, /faz parte de um kit/);
  assert.match(traduzirExclusao(banco("tabela_nova")).message, /ainda é usado em "tabela nova"/);
  // erro que nao e de vinculo passa como veio
  const outro = new Error("Sessão encerrada. Entre de novo.");
  assert.equal(traduzirExclusao(outro), outro);
});

test("busca de pedidos nao deixa o termo quebrar o filtro", () => {
  assert.equal(filtroDeBusca("ana"), "(nome.ilike.*ana*,email.ilike.*ana*,referencia.ilike.*ana*)");
  assert.equal(filtroDeBusca('  João, (Silva) "x"* '),
               "(nome.ilike.*João Silva x*,email.ilike.*João Silva x*,referencia.ilike.*João Silva x*)");
  assert.equal(filtroDeBusca("2000123456", ["referencia"]), "(referencia.ilike.*2000123456*)");
  assert.equal(filtroDeBusca("   "), null);
  assert.equal(filtroDeBusca(null), null);
});
