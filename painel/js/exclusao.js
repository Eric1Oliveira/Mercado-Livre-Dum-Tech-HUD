// Excluir: as regras que não dependem de tela (testadas em tests/exclusao.test.mjs).
//
// O banco deixa o administrador excluir tudo — e grava cada exclusão na
// auditoria (tela Segurança), com o valor de antes. O cuidado mora aqui:
// exclusão que leva coisa junto (cliente, licença, pedido que já teve dinheiro
// ou entrega) só passa digitando EXCLUIR; o resto, com um "ok" que diz o que vai
// acontecer.

export const PALAVRA = "EXCLUIR";

/** A palavra conferida: sem diferença de maiúscula e de espaço nas pontas. */
export const confere = (digitado) => String(digitado ?? "").trim().toUpperCase() === PALAVRA;

/** Pedido que já teve dinheiro ou entrega pede a palavra; pedido parado, um "ok". */
export const exclusaoPesada = (pedido) => Boolean(pedido?.atendido_em || pedido?.pagamento === "pago");

//: onde um módulo do catálogo ainda está sendo usado (a tabela que segurou a exclusão)
const ONDE = {
  licenca_produtos: "está na licença de algum cliente — tire de linha em vez de excluir",
  licenca_testes: "algum cliente já fez o teste grátis dele — tire de linha em vez de excluir",
  combo_produtos: "faz parte de um kit — tire ele do kit primeiro",
  comunicados: "um anúncio aponta para ele — apague ou mude o anúncio primeiro",
  uso_diario: "já tem uso registrado em algum Hub — tire de linha em vez de excluir",
  integracoes: "faz parte das integrações entre módulos — tire de linha em vez de excluir",
};

/** O "não pode" do banco em português: onde o registro ainda está sendo usado. */
export function traduzirExclusao(erro, oQue = "Este registro") {
  const texto = String(erro?.message || erro || "");
  const tabela = /foreign key constraint "[^"]*" on table "([a-z_]+)"/i.exec(texto)?.[1];
  if (tabela) {
    const onde = ONDE[tabela] || `ainda é usado em "${tabela.replace(/_/g, " ")}"`;
    return new Error(`${oQue} não pode ser excluído: ${onde}.`);
  }
  return erro instanceof Error ? erro : new Error(texto || "Não consegui excluir.");
}

/**
 * Busca de pedidos no idioma do PostgREST: `(nome.ilike.*ana*,email.ilike.*ana*,...)`.
 * Vírgula, parênteses, aspas e asterisco quebrariam o filtro: viram espaço.
 */
export function filtroDeBusca(termo, campos = ["nome", "email", "referencia"]) {
  const limpo = String(termo ?? "").replace(/[,()"*\\]/g, " ").trim().replace(/\s+/g, " ");
  if (!limpo) return null;
  return `(${campos.map((campo) => `${campo}.ilike.*${limpo}*`).join(",")})`;
}
