// node --test painel/tests/anuncios.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { conferirAnuncio, montarAnuncio, situacaoAnuncio } from "../js/anuncios.js";

const HOJE = "2026-09-25";
const anuncio = (campos = {}) => ({ ativo: true, inicio: "2026-09-01", fim: null, ...campos });

test("ligado e dentro do periodo: no ar", () => {
  assert.equal(situacaoAnuncio(anuncio(), HOJE).texto, "No ar");
  assert.equal(situacaoAnuncio(anuncio({ fim: HOJE }), HOJE).texto, "No ar");
});

test("desligado nao esta no ar, tenha a data que tiver", () => {
  assert.equal(situacaoAnuncio(anuncio({ ativo: false }), HOJE).texto, "Parado");
});

test("ligado com data vencida nao chega a ninguem - e a tela diz isso", () => {
  // era aqui que a lista mentia: "ativo" no banco virava "No ar" na tela
  assert.equal(situacaoAnuncio(anuncio({ fim: "2026-09-24" }), HOJE).texto, "Encerrado");
});

test("ligado com inicio no futuro: programado, com a data", () => {
  const situacao = situacaoAnuncio(anuncio({ inicio: "2026-10-03" }), HOJE);
  assert.match(situacao.texto, /^Programado/);
  assert.match(situacao.texto, /03\/10\/2026/);
});

test("titulo e obrigatorio, e o erro aponta o campo", () => {
  assert.equal(conferirAnuncio({ titulo: "Leve o Vendas" }), null);
  const problema = conferirAnuncio({ titulo: "  " });
  assert.match(problema.erro, /título/);
  assert.equal(problema.campo, "titulo");
});

test("o link so pode ser pagina https - o Hub abre isso na maquina do cliente", () => {
  const base = { titulo: "Oferta" };
  assert.equal(conferirAnuncio({ ...base, link: "https://dumtech.com.br/loja" }), null);
  assert.equal(conferirAnuncio({ ...base, link: "" }), null);
  for (const torto of ["teste", "http://dumtech.com.br", "file:///C:/x.exe",
                       "\\\\servidor\\x.exe", "https://com espaco"]) {
    const problema = conferirAnuncio({ ...base, link: torto });
    assert.match(problema.erro, /https:\/\//, torto);
    assert.equal(problema.campo, "link", torto);
  }
});

test("nao deixa terminar antes de comecar", () => {
  const base = { titulo: "Oferta", inicio: "2026-10-10" };
  const problema = conferirAnuncio({ ...base, fim: "2026-10-01" });
  assert.match(problema.erro, /termina antes/);
  assert.equal(problema.campo, "fim");
  assert.equal(conferirAnuncio({ ...base, fim: "2026-10-20" }), null);
  assert.equal(conferirAnuncio({ ...base, fim: "" }), null);
});

// ------------------------------------------------------------------ montar ---
// O bug que isto tranca: a tela validava DENTRO de `agir`. Recusado, o recado
// vermelho aparecia e a função retornava normal — então `agir` dava por feito e
// pintava "Anúncio salvo." por cima do erro. Quem publicava via o verde, a
// gaveta aberta e nada no Hub.
test("link invalido: devolve erro e NAO devolve dados para gravar", () => {
  // exatamente o que foi digitado quando o botao Publicar "nao fazia nada"
  const { erro, campo, dados } = montarAnuncio({
    titulo: "teste", texto: "teste", rotulo: "teste", link: "teste",
    alvo: "todos", inicio: "2026-09-25", fim: "", ordem: "0", ativo: true,
  });
  assert.match(erro, /https:\/\//);
  assert.equal(campo, "link");
  assert.equal(dados, undefined);
});

test("anuncio bom: devolve os dados prontos para o banco, sem erro", () => {
  const { erro, dados } = montarAnuncio({
    titulo: "  Leve o Vendas  ", texto: " Uma frase. ", rotulo: " Oferta ",
    link: "https://dumtech.com.br/loja",
    alvo: "todos", produto: "VENDAS", inicio: "2026-09-25", fim: "", ordem: "2", ativo: true,
  });
  assert.equal(erro, undefined);
  assert.deepEqual(dados, {
    titulo: "Leve o Vendas", texto: "Uma frase.", rotulo: "Oferta",
    link: "https://dumtech.com.br/loja",
    alvo: "todos", produto_codigo: null,
    inicio: "2026-09-25", fim: null, ordem: 2, ativo: true,
  });
});

test("alvo por modulo leva o codigo; sem fim e sem data viram null", () => {
  const { dados } = montarAnuncio({
    titulo: "Oferta", alvo: "sem_produto", produto: "VENDAS",
    inicio: "", fim: "", ordem: "", ativo: false,
  });
  assert.equal(dados.produto_codigo, "VENDAS");
  assert.equal(dados.inicio, null);
  assert.equal(dados.fim, null);
  assert.equal(dados.ordem, 0);
  assert.equal(dados.ativo, false);
});
