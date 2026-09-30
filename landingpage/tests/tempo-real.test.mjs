// Testes do tempo real (sem rede: o WebSocket e de mentira).
//
//     node --test tests/tempo-real.test.mjs

import test from "node:test";
import assert from "node:assert/strict";

import { enderecoDoSocket, interpretar, ouvir, pedidoDeEntrada } from "../js/tempo-real.js";

const esperar = (ms) => new Promise((pronto) => setTimeout(pronto, ms));

/** WebSocket de mentira: o teste decide o que o servidor responde. */
function servidorFalso() {
  const sockets = [];
  const criar = (endereco) => {
    const socket = {
      endereco, readyState: 0, enviados: [],
      send(texto) { this.enviados.push(JSON.parse(texto)); },
      close() { this.readyState = 3; this.onclose?.(); },
      abrir() { this.readyState = 1; this.onopen?.(); },
      receber(mensagem) { this.onmessage?.({ data: JSON.stringify(mensagem) }); },
    };
    sockets.push(socket);
    return socket;
  };
  return { sockets, criar };
}

test("endereco do socket sai do endereco do projeto", () => {
  assert.equal(
    enderecoDoSocket("https://abc.supabase.co/rest/v1", "chave publica"),
    "wss://abc.supabase.co/realtime/v1/websocket?apikey=chave%20publica&vsn=1.0.0"
  );
  assert.equal(
    enderecoDoSocket("http://127.0.0.1:54999", "k"),
    "ws://127.0.0.1:54999/realtime/v1/websocket?apikey=k&vsn=1.0.0",
    "servidor local de teste usa ws://"
  );
});

test("entrar no canal privado leva o token", () => {
  const pedido = pedidoDeEntrada("painel", { privado: true, token: "jwt", ref: "7" });
  assert.equal(pedido.topic, "realtime:painel");
  assert.equal(pedido.event, "phx_join");
  assert.equal(pedido.payload.config.private, true);
  assert.equal(pedido.payload.access_token, "jwt");
});

test("interpreta o que o servidor manda", () => {
  const t = "catalogo";
  assert.deepEqual(
    interpretar({ topic: "realtime:catalogo", event: "broadcast",
                  payload: { event: "mudou", payload: { tabela: "produtos", op: "update" } } }, t),
    { tipo: "mudou", tabela: "produtos", op: "update" });
  assert.deepEqual(interpretar({ topic: "realtime:catalogo", event: "phx_reply",
                                 payload: { status: "ok" } }, t), { tipo: "entrou" });
  assert.equal(interpretar({ topic: "realtime:catalogo", event: "phx_reply",
                             payload: { status: "error", response: { reason: "Unauthorized" } } }, t).tipo,
               "recusado");
  assert.equal(interpretar({ topic: "realtime:catalogo", event: "system",
                             payload: { status: "error", message: "Token has expired" } }, t).tipo, "caiu");
  assert.equal(interpretar({ topic: "phoenix", event: "phx_reply", payload: { status: "ok" } }, t), null,
               "resposta da batida nao e do canal");
  assert.equal(interpretar({ topic: "realtime:outro", event: "broadcast", payload: {} }, t), null,
               "aviso de outro canal e ignorado");
  assert.equal(interpretar(null, t), null);
});

test("ouve, avisa a mudanca e reconecta sozinho", async () => {
  const servidor = servidorFalso();
  const mudancas = [];
  const estados = [];
  const canal = ouvir({
    url: "https://abc.supabase.co/rest/v1", chave: "anon", topico: "catalogo",
    aoMudar: (m) => mudancas.push(m), aoEstado: (e) => estados.push(e),
    criarSocket: servidor.criar, esperas: [5],
  });
  await esperar(0);

  const [primeiro] = servidor.sockets;
  primeiro.abrir();
  assert.equal(primeiro.enviados[0].event, "phx_join", "entra no canal assim que abre");
  primeiro.receber({ topic: "realtime:catalogo", event: "phx_reply", payload: { status: "ok" } });
  assert.equal(estados.at(-1), "ao-vivo");

  primeiro.receber({ topic: "realtime:catalogo", event: "broadcast",
                     payload: { payload: { tabela: "produtos", op: "update" } } });
  assert.deepEqual(mudancas, [{ tabela: "produtos", op: "update" }]);

  // a conexao cai: tenta de novo sozinho
  primeiro.close();
  assert.equal(estados.at(-1), "fora");
  await esperar(30);
  assert.equal(servidor.sockets.length, 2, "deveria ter reconectado");

  const segundo = servidor.sockets[1];
  segundo.abrir();
  segundo.receber({ topic: "realtime:catalogo", event: "phx_reply", payload: { status: "ok" } });
  assert.deepEqual(mudancas.at(-1), { tabela: "", op: "reconectou" },
                   "ao voltar, avisa uma vez: algo pode ter mudado no escuro");

  canal.parar();
  await esperar(30);
  assert.equal(servidor.sockets.length, 2, "depois de parar, nao reconecta");
});

test("canal recusado fecha e tenta de novo mais tarde", async () => {
  const servidor = servidorFalso();
  const canal = ouvir({
    url: "https://abc.supabase.co", chave: "anon", topico: "painel", privado: true,
    token: async () => "jwt-da-sessao", criarSocket: servidor.criar, esperas: [5],
  });
  await esperar(0);
  const socket = servidor.sockets[0];
  socket.abrir();
  assert.equal(socket.enviados[0].payload.access_token, "jwt-da-sessao");
  socket.receber({ topic: "realtime:painel", event: "phx_reply",
                   payload: { status: "error", response: { reason: "Unauthorized" } } });
  assert.equal(socket.readyState, 3, "recusado fecha o socket");
  await esperar(30);
  assert.equal(servidor.sockets.length, 2);
  canal.parar();
});

test("erro na tela nao derruba a conexao", async () => {
  const servidor = servidorFalso();
  const canal = ouvir({
    url: "https://abc.supabase.co", chave: "anon", topico: "catalogo",
    aoMudar: () => { throw new Error("tela quebrada"); },
    criarSocket: servidor.criar, esperas: [5],
  });
  await esperar(0);
  const socket = servidor.sockets[0];
  socket.abrir();
  const erroOriginal = console.error;
  console.error = () => {};
  try {
    socket.receber({ topic: "realtime:catalogo", event: "broadcast", payload: { payload: { tabela: "x" } } });
  } finally {
    console.error = erroOriginal;
  }
  assert.equal(socket.readyState, 1, "a conexao continua de pe");
  canal.parar();
});
