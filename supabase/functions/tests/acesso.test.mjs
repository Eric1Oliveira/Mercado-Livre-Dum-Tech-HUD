// Testes do nucleo das contas (Node >= 23.6 roda .ts direto).
//
//     node --test supabase/functions/tests/acesso.test.mjs
//
// Com PACOTE_ACESSO_SAIDA definido, grava {publica, acesso, lembranca} assinados
// aqui: o Hub (Python) confere os mesmos pacotes.

import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, verify } from "node:crypto";
import { writeFileSync } from "node:fs";

import {
  assinar, conferirSenha, conteudoAcesso, conteudoLembranca, derivarSenha, emailDoCodigo, importarChavePrivada,
  ITERACOES, mascararEmail, rotaDe, senhaAceitavel, tratar,
} from "../acesso/nucleo.ts";

const PC = "0123456789abcdef0123456789abcdef";
const ID = { chave: "7k4m-9qx2-bt5h-3dwz", maquina: "aaaa-bbbb", computador: PC };
const RAPIDO = { iteracoes: 10_000 };   // o minimo que o banco aceita: teste nao precisa de 600 mil

const { publicKey, privateKey } = generateKeyPairSync("ed25519");
const pkcs8 = privateKey.export({ format: "der", type: "pkcs8" }).toString("base64");
const chave = await importarChavePrivada(pkcs8);

const USUARIO = {
  id: "11111111-1111-1111-1111-111111111111", login: "dona", nome: "Dona", papel: "adm", modulos: [], avisos: [],
  senha_versao: 2, trocar_senha: false, ativo: true, tem_email: true, email_confirmado: false,
};
const RESUMO = { exigir_conta: false, usuarios: [USUARIO] };
const SESSAO = { ok: true, sessao: "segredo", expira_em: "2026-11-02T15:30:00Z", usuario: USUARIO, resumo: RESUMO };

// as conferencias de antes de derivar: abertas, salvo no teste que as fecha
const PORTAS = { dumtech_acesso_antes_de_derivar: { ok: true }, dumtech_acesso_portao: { ok: true } };

function ambiente(respostas = {}, { emailFunciona = true } = {}) {
  const chamadas = [];
  const emails = [];
  return {
    chamadas, emails,
    kid: "k1",
    agora: () => new Date("2026-11-02T15:00:00Z"),
    iteracoes: RAPIDO.iteracoes,
    rpc: async (funcao, parametros) => {
      chamadas.push({ funcao, parametros });
      const resposta = { ...PORTAS, ...respostas }[funcao];
      return typeof resposta === "function" ? resposta(parametros) : resposta ?? null;
    },
    enviarEmail: async (m) => { emails.push(m); return emailFunciona; },
    assinar: (conteudo) => assinar(conteudo, chave, "k1"),
  };
}

function abrir(pacote) {
  const bytes = Buffer.from(pacote.licenca, "base64url");
  assert.ok(verify(null, bytes, publicKey, Buffer.from(pacote.assinatura, "base64url")), "assinatura nao confere");
  return JSON.parse(bytes.toString("utf8"));
}

const texto = (valor) => JSON.stringify(valor);

test("rotas conhecidas e so elas", () => {
  assert.equal(rotaDe("/functions/v1/acesso/entrar"), "entrar");
  assert.equal(rotaDe("/acesso/liberar-computador/"), "liberar-computador");
  assert.equal(rotaDe("/functions/v1/acesso/senha"), "");
  assert.equal(rotaDe("/functions/v1/acesso"), "");
});

test("derivar: formato do banco, sal novo a cada vez, e confere so a senha certa", async () => {
  const guardado = await derivarSenha("Minha senha 1", RAPIDO);
  assert.match(guardado, /^pbkdf2\$10000\$[A-Za-z0-9_-]+\$[A-Za-z0-9_-]+$/);
  assert.notEqual(guardado, await derivarSenha("Minha senha 1", RAPIDO), "sal repetido");
  assert.ok(await conferirSenha("Minha senha 1", guardado));
  assert.ok(!(await conferirSenha("Minha senha 2", guardado)));
  assert.ok(!(await conferirSenha("Minha senha 1", "bcrypt$lixo")));
  assert.ok(!(await conferirSenha("", guardado)));
  assert.equal(ITERACOES, 600_000, "a spec promete 600 mil");
});

test("senha aceitavel: tamanho, igual ao login e as obvias", () => {
  assert.equal(senhaAceitavel("cavalo-azul", "dona"), "");
  assert.match(senhaAceitavel("curta", "dona"), /8 caracteres/);
  assert.match(senhaAceitavel("x".repeat(73), "dona"), /72/);
  assert.match(senhaAceitavel("dona.loja", "dona.loja"), /login/);
  assert.match(senhaAceitavel("12345678", "dona"), /fácil/);
  assert.match(senhaAceitavel("Senha123", "dona"), /fácil/);
  assert.match(senhaAceitavel("aaaaaaaa", "dona"), /fácil/);
});

test("e-mail mascarado nao entrega o endereco", () => {
  assert.equal(mascararEmail("eduardo@gmail.com"), "e*****o@gmail.com");
  assert.equal(mascararEmail("ab@x.com"), "a*b@x.com");
  assert.equal(mascararEmail("lixo"), "");
});

test("e-mail do codigo diz para que serve", () => {
  const recuperar = emailDoCodigo({ nome: "Maria Silva", codigo: "123456", validade: 10, finalidade: "recuperar_senha" });
  assert.match(recuperar.assunto, /123456/);
  assert.match(recuperar.texto, /Olá, Maria!/);
  assert.match(recuperar.texto, /redefinir a senha/);
  const confirmar = emailDoCodigo({ nome: "<b>", codigo: "123456", validade: 10, finalidade: "confirmar_email" });
  assert.match(confirmar.texto, /confirmar/);
  assert.ok(!confirmar.html.includes("<b>Olá"), "nome sem escapar no html");
  assert.ok(confirmar.html.includes("&lt;b&gt;"));
});

test("pedido incompleto nem chega ao banco", async () => {
  const a = ambiente();
  const r = await tratar(a, "entrar", { chave: "x", maquina: "y", computador: "curto" }, "1.1.1.1");
  assert.equal(r.corpo.erro, "dados_incompletos");
  assert.equal(a.chamadas.length, 0);
});

test("criar o primeiro ADM: a senha vira hash antes do banco e a sessao vem assinada", async () => {
  const a = ambiente({ dumtech_acesso_criar_primeiro: SESSAO });
  const r = await tratar(a, "criar-primeiro",
    { ...ID, nome: "Dona", login: "dona", email: "d@x.com", senha: "cavalo-azul", lembrar: true }, "1.1.1.1");
  assert.equal(r.corpo.ok, true);
  const { parametros } = a.chamadas.at(-1);
  assert.ok(!texto(parametros).includes("cavalo-azul"), "senha em claro no parametro SQL");
  assert.match(parametros.p_senha_hash, /^pbkdf2\$10000\$/);
  assert.equal(parametros.p_chave, "7K4M-9QX2-BT5H-3DWZ");
  assert.equal(parametros.p_ip, "1.1.1.1");

  assert.equal(r.corpo.sessao, "segredo");
  assert.ok(!("resumo" in r.corpo), "resumo em claro");
  const acesso = abrir(r.corpo.acesso_assinado);
  assert.equal(acesso.uso, "acesso");
  assert.equal(acesso.computador, PC);
  assert.equal(acesso.maquina, "AAAA-BBBB");
  assert.equal(acesso.usuarios[0].login, "dona");

  const lembranca = abrir(r.corpo.lembranca);
  assert.equal(lembranca.uso, "lembrar");
  assert.equal(lembranca.usuario, USUARIO.id);
  assert.equal(lembranca.senha_versao, 2);
  assert.equal(lembranca.computador, PC);
});

test("derivar e caro: chave inventada e recusada antes", async () => {
  const chamouDerivacao = (a) => a.chamadas.some((c) => "p_senha_hash" in c.parametros);
  const recusa = { ok: false, erro: "nao_autorizado", mensagem: "x" };
  const pedidos = [
    ["criar-primeiro", { nome: "D", login: "dona", email: "d@x.com", senha: "cavalo-azul" }, "dumtech_acesso_antes_de_derivar"],
    ["redefinir", { login: "dona", codigo: "123456", senha: "cavalo-azul" }, "dumtech_acesso_antes_de_derivar"],
    ["salvar-usuario", { sessao: "s", usuario: { nome: "M", login: "maria" }, senha: "cavalo-azul" }, "dumtech_acesso_portao"],
    ["senha-usuario", { sessao: "s", id: USUARIO.id, login: "maria", senha: "cavalo-azul" }, "dumtech_acesso_portao"],
  ];
  for (const [rota, corpo, porta] of pedidos) {
    const a = ambiente({ [porta]: recusa });
    const r = await tratar(a, rota, { ...ID, ...corpo }, "1.1.1.1");
    assert.equal(r.corpo.erro, "nao_autorizado", rota);
    assert.ok(!chamouDerivacao(a), `${rota} derivou antes de conferir`);
  }
});

test("senha fraca e recusada antes de gastar o banco", async () => {
  const a = ambiente();
  const r = await tratar(a, "criar-primeiro", { ...ID, nome: "D", login: "dona", email: "d@x.com", senha: "12345678" }, "");
  assert.equal(r.corpo.erro, "senha_fraca");
  assert.equal(a.chamadas.length, 0);
});

test("entrar: senha certa abre sessao; o hash nunca sai", async () => {
  const hash = await derivarSenha("cavalo-azul", RAPIDO);
  const a = ambiente({
    dumtech_acesso_buscar: { ok: true, usuario_id: USUARIO.id, senha_hash: hash },
    dumtech_acesso_resultado: (p) => (p.p_certo ? SESSAO : { ok: false, erro: "credenciais", mensagem: "x" }),
  });
  const r = await tratar(a, "entrar", { ...ID, login: "dona", senha: "cavalo-azul" }, "1.1.1.1");
  assert.equal(r.corpo.ok, true);
  assert.ok(!texto(r.corpo).includes("pbkdf2"), "hash saiu na resposta");
  assert.ok(!("lembranca" in r.corpo), "lembranca sem pedir");
  assert.equal(a.chamadas.at(-1).parametros.p_certo, true);

  const errada = await tratar(a, "entrar", { ...ID, login: "dona", senha: "outra-senha" }, "1.1.1.1");
  assert.equal(errada.corpo.erro, "credenciais");
  assert.equal(a.chamadas.at(-1).parametros.p_certo, false);
  assert.ok(!texto(errada.corpo).includes("pbkdf2"));
});

test("entrar: conta travada para no banco, sem comparar", async () => {
  const a = ambiente({ dumtech_acesso_buscar: { ok: false, erro: "conta_travada", mensagem: "Espere" } });
  const r = await tratar(a, "entrar", { ...ID, login: "dona", senha: "cavalo-azul" }, "");
  assert.equal(r.corpo.erro, "conta_travada");
  assert.equal(a.chamadas.length, 1);
});

test("entrar: banco fora do ar vira falha, nao excecao", async () => {
  const a = ambiente();
  const r = await tratar(a, "entrar", { ...ID, login: "dona", senha: "cavalo-azul" }, "");
  assert.equal(r.status, 502);
});

test("esqueci: o codigo so vai por e-mail e nunca volta para o Hub", async () => {
  const a = ambiente({ dumtech_acesso_pedir_codigo: {
    ok: true, email: "dona@gmail.com", nome: "Dona", codigo: "654321", validade_minutos: 10,
  } });
  const r = await tratar(a, "pedir-codigo", { ...ID, login: "dona" }, "1.1.1.1");
  assert.equal(r.corpo.ok, true);
  assert.equal(r.corpo.email, "d**a@gmail.com");
  assert.ok(!texto(r.corpo).includes("654321"), "codigo voltou");
  assert.equal(a.emails[0].para, "dona@gmail.com");
  assert.match(a.emails[0].texto, /654321/);
});

test("esqueci: login inexistente responde sem dizer que nao existe", async () => {
  const a = ambiente({ dumtech_acesso_pedir_codigo: { ok: true } });
  const r = await tratar(a, "pedir-codigo", { ...ID, login: "ninguem" }, "");
  assert.deepEqual(r.corpo, { ok: true, email: "" });
  assert.equal(a.emails.length, 0);
});

test("esqueci: conta sem e-mail manda procurar o administrador", async () => {
  const a = ambiente({ dumtech_acesso_pedir_codigo: { ok: true, sem_email: true } });
  const r = await tratar(a, "pedir-codigo", { ...ID, login: "maria" }, "");
  assert.equal(r.corpo.sem_email, true);
});

test("esqueci: e-mail que nao saiu avisa", async () => {
  const a = ambiente({ dumtech_acesso_pedir_codigo: { ok: true, email: "d@x.com", nome: "D", codigo: "1", validade_minutos: 10 } },
                     { emailFunciona: false });
  const r = await tratar(a, "pedir-codigo", { ...ID, login: "dona" }, "");
  assert.equal(r.corpo.erro, "falha_no_envio");
});

test("redefinir: senha nova vira hash e devolve sessao", async () => {
  const a = ambiente({ dumtech_acesso_redefinir: SESSAO });
  const r = await tratar(a, "redefinir", { ...ID, login: "dona", codigo: "654321", senha: "nova-senha-boa", lembrar: true }, "");
  assert.equal(r.corpo.ok, true);
  assert.ok(!texto(a.chamadas).includes("nova-senha-boa"));
  assert.ok(r.corpo.acesso_assinado && r.corpo.lembranca);
});

test("trocar a propria senha confere a atual e conta o erro", async () => {
  const hash = await derivarSenha("senha-atual-1", RAPIDO);
  const a = ambiente({
    dumtech_acesso_buscar_sessao: { ok: true, usuario_id: USUARIO.id, login: "dona", senha_hash: hash },
    dumtech_acesso_gravar_senha: { ok: true, usuario: USUARIO, resumo: RESUMO },
    dumtech_acesso_resultado: { ok: false, erro: "credenciais", mensagem: "x" },
  });
  const errada = await tratar(a, "trocar-senha", { ...ID, sessao: "s", atual: "nao-e-essa", nova: "senha-nova-boa" }, "");
  assert.equal(errada.corpo.erro, "senha_atual_errada");
  assert.ok(a.chamadas.some((c) => c.funcao === "dumtech_acesso_resultado"), "erro nao contou para a trava");
  assert.ok(!a.chamadas.some((c) => c.funcao === "dumtech_acesso_gravar_senha"));

  const igual = await tratar(a, "trocar-senha", { ...ID, sessao: "s", atual: "senha-atual-1", nova: "senha-atual-1" }, "");
  assert.equal(igual.corpo.erro, "senha_fraca");

  const certa = await tratar(a, "trocar-senha", { ...ID, sessao: "s", atual: "senha-atual-1", nova: "senha-nova-boa", lembrar: true }, "");
  assert.equal(certa.corpo.ok, true);
  assert.ok(certa.corpo.acesso_assinado && certa.corpo.lembranca);
  assert.ok(!texto(a.chamadas).includes("senha-nova-boa"));
});

test("confirmar e-mail: pede o codigo e confirma pela sessao", async () => {
  const a = ambiente({
    dumtech_acesso_codigo_email: { ok: true, email: "dona@gmail.com", nome: "Dona", codigo: "111222", validade_minutos: 10 },
    dumtech_acesso_confirmar_email: { ok: true, usuario: USUARIO, resumo: RESUMO },
  });
  const pedido = await tratar(a, "pedir-confirmacao", { ...ID, sessao: "s" }, "");
  assert.equal(pedido.corpo.email, "d**a@gmail.com");
  assert.ok(!texto(pedido.corpo).includes("111222"));
  assert.match(a.emails[0].texto, /confirmar/);
  const confirmado = await tratar(a, "confirmar-email", { ...ID, sessao: "s", codigo: "111222" }, "");
  assert.ok(confirmado.corpo.acesso_assinado);
});

test("salvar usuario: so os campos conhecidos, senha vira hash e o pacote volta novo", async () => {
  const a = ambiente({ dumtech_acesso_salvar_usuario: { ok: true, usuario: USUARIO, resumo: RESUMO } });
  const r = await tratar(a, "salvar-usuario", {
    ...ID, sessao: "s", usuario: { nome: "Maria", login: "maria", papel: "funcionario", modulos: ["vendas"], avisos: [],
                                   ativo: true, senha_hash: "pbkdf2$1$a$b", xpto: 1 },
    senha: "senha-inicial-1",
  }, "");
  assert.equal(r.corpo.ok, true);
  const { parametros } = a.chamadas.at(-1);
  assert.equal(parametros.p_id, null);
  assert.deepEqual(Object.keys(parametros.p_dados).sort(), ["ativo", "avisos", "email", "login", "modulos", "nome", "papel"]);
  assert.match(parametros.p_senha_hash, /^pbkdf2\$10000\$/);
  assert.ok(!texto(parametros).includes("senha-inicial-1"));
  assert.ok(r.corpo.acesso_assinado);
  assert.ok(!("resumo" in r.corpo));
});

test("salvar usuario sem senha nao inventa hash", async () => {
  const a = ambiente({ dumtech_acesso_salvar_usuario: { ok: true, usuario: USUARIO, resumo: RESUMO } });
  await tratar(a, "salvar-usuario", { ...ID, sessao: "s", id: USUARIO.id, usuario: { nome: "Maria", login: "maria", papel: "funcionario" } }, "");
  assert.equal(a.chamadas[0].parametros.p_senha_hash, "");
  assert.equal(a.chamadas[0].parametros.p_id, USUARIO.id);
});

test("gestao simples passa adiante a recusa do banco", async () => {
  const recusa = { ok: false, erro: "so_adm", mensagem: "Só um administrador" };
  const a = ambiente({
    dumtech_acesso_usuarios: recusa, dumtech_acesso_computadores: recusa, dumtech_acesso_apagar_usuario: recusa,
    dumtech_acesso_liberar_computador: recusa, dumtech_acesso_renomear_computador: recusa,
  });
  for (const rota of ["usuarios", "computadores", "apagar-usuario", "liberar-computador", "renomear-computador"]) {
    const r = await tratar(a, rota, { ...ID, sessao: "s", id: USUARIO.id, maquina_alvo: "X", apelido: "Y" }, "");
    assert.equal(r.corpo.erro, "so_adm", rota);
  }
});

test("senha de outra pessoa pelo ADM passa pela mesma regra", async () => {
  const a = ambiente({ dumtech_acesso_senha_usuario: { ok: true, usuario: USUARIO, resumo: RESUMO } });
  const fraca = await tratar(a, "senha-usuario", { ...ID, sessao: "s", id: USUARIO.id, login: "maria", senha: "123" }, "");
  assert.equal(fraca.corpo.erro, "senha_fraca");
  const boa = await tratar(a, "senha-usuario", { ...ID, sessao: "s", id: USUARIO.id, login: "maria", senha: "senha-boa-99" }, "");
  assert.equal(boa.corpo.ok, true);
  assert.ok(boa.corpo.acesso_assinado);
});

test("pacotes para o Hub conferir", async () => {
  const agora = new Date("2026-11-02T15:00:00Z");
  const id = { chave: "7K4M-9QX2-BT5H-3DWZ", maquina: "AAAA-BBBB", computador: PC };
  const acesso = await assinar(conteudoAcesso({ kid: "k1", ...id, resumo: RESUMO, agora }), chave, "k1");
  const lembranca = await assinar(conteudoLembranca({ kid: "k1", ...id, usuario: USUARIO, agora }), chave, "k1");
  assert.equal(abrir(acesso).exigir_conta, false);
  assert.equal(abrir(lembranca).senha_versao, 2);
  if (process.env.PACOTE_ACESSO_SAIDA) {
    const publica = publicKey.export({ format: "der", type: "spki" }).subarray(12).toString("hex");
    writeFileSync(process.env.PACOTE_ACESSO_SAIDA, JSON.stringify({ publica, acesso, lembranca }));
  }
});
