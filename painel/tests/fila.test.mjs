// A fila da tela Hoje (js/fila.js): o que entra, em que ordem, e o que conta no selo.

import test from "node:test";
import assert from "node:assert/strict";

import { montarFila, numerosDoMes, urgentes } from "../js/fila.js";

const AGORA = new Date(2026, 10, 4, 10); // 04/11/2026
const mensal = (extra) => ({ licenca_id: "L1", cliente_id: "C1", nome: "Ana Lima", tipo: "assinatura",
                             situacao: "em_dia", expira_em: null, cobranca_motivo: null, valor: 89.9, ...extra });
const tipos = (fila) => fila.map((i) => i.tipo);

test("fila vazia quando nada precisa de você", () => {
  const fila = montarFila({}, AGORA);
  assert.deepEqual(fila, []);
  assert.equal(urgentes(fila), 0);
});

test("assinatura para confirmar e pagamento pendente vêm primeiro e contam no selo", () => {
  const fila = montarFila({
    pedidos: [{ id: "P1", nome: "Bia", criado_em: "2026-11-04T09:00:00Z" }],
    mensalidades: [mensal({ situacao: "pendente", expira_em: "2026-11-08" }),
                   mensal({ licenca_id: "L2", tipo: "teste", situacao: "teste", expira_em: "2026-11-05" })],
    pendente: "1.13.0",
  }, AGORA);
  assert.deepEqual(tipos(fila), ["confirmar", "cobranca", "teste_acabando", "versao"]);
  assert.equal(urgentes(fila), 2);
  assert.equal(fila[1].dias, 4);
});

test("quem cancelou não vira cobrança: aparece como 'cancelou', fora do selo", () => {
  const fila = montarFila({ mensalidades: [mensal({ situacao: "pendente", cobranca_motivo: "cancelou", expira_em: "2026-11-20" })] }, AGORA);
  assert.deepEqual(tipos(fila), ["cancelou"]);
  assert.equal(urgentes(fila), 0);
});

test("só consulta também é cobrança (o cliente está travado)", () => {
  const fila = montarFila({ mensalidades: [mensal({ situacao: "consulta", expira_em: "2026-10-20" })] }, AGORA);
  assert.deepEqual(tipos(fila), ["cobranca"]);
});

test("licença vitalícia nunca gera item de pagamento, mesmo que chegue na lista por engano", () => {
  const fila = montarFila({ mensalidades: [mensal({ tipo: "vitalicia", situacao: "consulta", expira_em: "2026-10-20" })] }, AGORA);
  assert.deepEqual(fila, []);
  assert.equal(numerosDoMes([mensal({ tipo: "vitalicia" })]).receita, 0);
});

test("teste: um item só, do mais importante", () => {
  const teste = (extra) => mensal({ tipo: "teste", situacao: "teste", expira_em: "2026-11-10", ...extra });
  const linhas = [{ id: "C1", nome: "Ana", cliente: { licenca_id: "L1" }, uso: "sem_ativar" }];
  // começou hoje e ainda não instalou: é novo (dá tempo)
  assert.deepEqual(tipos(montarFila({ mensalidades: [teste({ criado_em: "2026-11-04T08:00:00" })], linhas }, AGORA)), ["teste_novo"]);
  // começou há 2 dias e não instalou: precisa de ajuda
  assert.deepEqual(tipos(montarFila({ mensalidades: [teste({ criado_em: "2026-11-02T08:00:00" })], linhas }, AGORA)), ["sem_instalar"]);
  // acabando ganha de "não instalou"
  assert.deepEqual(tipos(montarFila({ mensalidades: [teste({ criado_em: "2026-10-29T08:00:00", expira_em: "2026-11-05" })], linhas }, AGORA)),
                   ["teste_acabando"]);
  // terminou há 3 dias: ainda vale a conversa; há 20, não
  assert.deepEqual(tipos(montarFila({ mensalidades: [teste({ situacao: "consulta", expira_em: "2026-11-01" })] }, AGORA)), ["teste_terminou"]);
  assert.deepEqual(montarFila({ mensalidades: [teste({ situacao: "consulta", expira_em: "2026-10-15" })] }, AGORA), []);
  // usando bem, no meio do teste: nada
  assert.deepEqual(montarFila({ mensalidades: [teste({ criado_em: "2026-11-01T08:00:00" })],
                                linhas: [{ ...linhas[0], uso: "usando" }] }, AGORA), []);
});

test("assinante em dia que sumiu entra como 'parou'", () => {
  const linhas = [{ id: "C1", nome: "Ana", cliente: { licenca_id: "L1", ultimo_uso: "2026-10-01" }, uso: "sumiu" }];
  const fila = montarFila({ mensalidades: [mensal()], linhas }, AGORA);
  assert.deepEqual(tipos(fila), ["parou"]);
  assert.equal(fila[0].ultimoUso, "2026-10-01");
});

test("retorno agendado para hoje ou atrasado, pedidos antigos e tentativas demais", () => {
  const linhas = [
    { id: "C1", nome: "Ana", cliente: {}, proximoContato: "2026-11-02" },
    { id: "C2", nome: "Bia", cliente: {}, proximoContato: "2026-11-04" },
    { id: "C3", nome: "Caio", cliente: {}, proximoContato: "2026-11-09" },
  ];
  const fila = montarFila({ linhas, pedidosLoja: [{}, {}], tentativas: 35 }, AGORA);
  assert.deepEqual(tipos(fila), ["pedido_loja", "retorno", "retorno", "tentativas"]);
  assert.equal(fila[1].nome, "Ana"); // o mais atrasado primeiro
  assert.equal(fila[0].quantos, 2);
  assert.equal(urgentes(fila), 1);
  assert.deepEqual(montarFila({ tentativas: 20 }, AGORA), []);
});

test("números do mês: só assinatura que não está em consulta entra na receita", () => {
  const n = numerosDoMes([
    mensal({ valor: 100 }),
    mensal({ licenca_id: "L2", situacao: "pendente", valor: 50 }),
    mensal({ licenca_id: "L3", situacao: "consulta", valor: 70 }),
    mensal({ licenca_id: "L4", tipo: "teste", situacao: "teste", valor: 89.9 }),
  ]);
  assert.deepEqual(n, { receita: 150, assinantes: 2, emDia: 1, testando: 1 });
});
