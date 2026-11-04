// O titulo e a descricao publicados no painel vao para o HTML cru (Google e
// previa do WhatsApp). tools/textos_publicados.mjs, chamado pelo publicar_site.ps1.

import test from "node:test";
import assert from "node:assert/strict";

import { gravar, textosDoHtml } from "../../tools/textos_publicados.mjs";

const HTML = '<title>Velho</title>\n<meta name="description" content="Velha">';

test("sem nada publicado, o HTML fica como esta", () => {
  assert.equal(textosDoHtml({ conteudo: {} }), null);
  assert.equal(textosDoHtml(null), null);
});

test("o publicado vai para o titulo e a descricao, com marcadores e escapado", () => {
  const textos = textosDoHtml({
    preco_base: 89.9, dias_teste: 7, computadores: 1,
    conteudo: { hero: { titulo: "Gestão <fácil> para o seu balcão.", chamada: "Teste {dias_teste} dias \"grátis\"." } },
  });
  assert.equal(textos.titulo, "DumTech Hub · Gestão <fácil> para o seu balcão");
  const html = gravar(HTML, textos);
  assert.match(html, /<title>DumTech Hub · Gestão &lt;fácil&gt; para o seu balcão<\/title>/);
  assert.match(html, /content="Teste 7 dias &quot;grátis&quot;\."/);
});
