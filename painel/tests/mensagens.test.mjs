// node --test tests/mensagens.test.mjs

import test from "node:test";
import assert from "node:assert/strict";

import { contatosNoTexto, linkEmail, linkWhatsApp, mensagemDaChave } from "../js/mensagens.js";

const DADOS = {
  nome: "Padaria Pão de Ouro", email: "contato@paodeouro.com.br", telefone: "(11) 98888-7777",
  chave: "7K4M-9QX2-BT5H-3DWZ", modulos: ["DumTech Estoque", "DumTech Vendas"],
  expira_em: null, max_computadores: 3,
};

test("mensagem traz nome, chave, modulos e como ativar", () => {
  const texto = mensagemDaChave(DADOS);
  assert.match(texto, /^Olá, Padaria!/);
  assert.match(texto, /Chave: 7K4M-9QX2-BT5H-3DWZ/);
  assert.match(texto, /Módulos: DumTech Estoque, DumTech Vendas/);
  assert.match(texto, /até 3 computadores/);
  assert.match(texto, /Como começar/);
  assert.doesNotMatch(texto, /Válida até/, "vitalícia não tem validade");
});

test("assinatura mostra a validade; um computador so nao fala em limite", () => {
  const texto = mensagemDaChave({ ...DADOS, expira_em: "2027-03-31", max_computadores: 1 });
  assert.match(texto, /Válida até: 31\/03\/2027/);
  assert.doesNotMatch(texto, /computadores\./);
});

test("mensagem direta leva o link de download e o suporte", () => {
  const texto = mensagemDaChave(DADOS, {
    download: "https://dumtechsolution.com/baixar/", suporte: "WhatsApp (11) 97804-2160",
  });
  assert.match(texto, /Baixe e instale o DumTech Hub: https:\/\/dumtechsolution\.com\/baixar\//);
  assert.match(texto, /Dúvidas: WhatsApp/);
});

test("mensagem do Mercado Livre nao tem link, e-mail nem telefone", () => {
  const texto = mensagemDaChave(DADOS, {
    canal: "mercadolivre", download: "https://dumtechsolution.com/baixar/", suporte: "(11) 97804-2160",
  });
  assert.match(texto, /Chave: 7K4M-9QX2-BT5H-3DWZ/);
  assert.match(texto, /guia de instalação anexado/);
  assert.deepEqual(contatosNoTexto(texto), [], `o ML bloquearia: ${contatosNoTexto(texto)}`);
});

test("detecta o que o Mercado Livre bloqueia (sem confundir a chave com telefone)", () => {
  assert.deepEqual(contatosNoTexto("baixe em dumtechsolution.com"), ["link"]);
  assert.deepEqual(contatosNoTexto("me chama no (11) 97804-2160"), ["telefone"]);
  assert.deepEqual(contatosNoTexto("escreva para eric@dumtech.com"), ["link", "e-mail"]);
  assert.deepEqual(contatosNoTexto("Chave: 7K4M-9QX2-BT5H-3DWZ"), []);
});

test("sem nome nao sai 'Olá, !'", () => {
  assert.match(mensagemDaChave({ chave: "X" }), /^Olá!/);
});

test("whatsapp: poe o 55 no numero brasileiro e recusa numero quebrado", () => {
  assert.equal(linkWhatsApp("(11) 98888-7777", "oi").startsWith("https://wa.me/5511988887777?text=oi"), true);
  assert.equal(linkWhatsApp("+55 11 3322-4455", "oi"), "https://wa.me/551133224455?text=oi");
  assert.equal(linkWhatsApp("123", "oi"), "");
  assert.equal(linkWhatsApp("", "oi"), "");
});

test("e-mail: mailto com assunto e corpo codificados", () => {
  const link = linkEmail("contato@paodeouro.com.br", "Sua licença", "linha 1\nlinha 2");
  assert.equal(link, "mailto:contato%40paodeouro.com.br?subject=Sua%20licen%C3%A7a&body=linha%201%0Alinha%202");
  assert.equal(linkEmail("nao e email", "a", "b"), "");
});
