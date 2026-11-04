// Grava no index.html do pacote do site o titulo e a descricao que o Eric
// publicou no painel (Textos do site).
//
//     node tools/textos_publicados.mjs <pasta-do-site>     (publicar_site.ps1 chama)
//
// POR QUE: a pagina troca os textos sozinha pelo JavaScript, mas o Google e a
// previa do link no WhatsApp leem o HTML CRU. Sem isto, eles mostrariam o
// texto antigo para sempre.
//
// Sem internet, ou sem nada publicado, o arquivo fica como esta: publicar o
// site nunca falha por causa disto.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = path.resolve(process.argv[2] || path.join(RAIZ, "build", "site"));
const ARQUIVO = path.join(SITE, "index.html");

globalThis.location = { search: "" }; // config.js le a URL da pagina
const { CONFIG } = await import(pathToFileURL(path.join(RAIZ, "landingpage", "js", "config.js")));
const { mesclar, preencher, valoresDosMarcadores } = await import(pathToFileURL(path.join(RAIZ, "landingpage", "js", "conteudo.js")));

const escapar = (texto) => String(texto).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

/** O que vai no HTML: titulo e descricao, ja com os marcadores trocados. */
export function textosDoHtml(vitrine) {
  const publicado = vitrine?.conteudo && typeof vitrine.conteudo === "object" ? vitrine.conteudo : {};
  if (!Object.keys(publicado).length) return null;
  const c = mesclar(publicado);
  const valores = valoresDosMarcadores({ precoBase: vitrine.preco_base, diasTeste: vitrine.dias_teste,
                                         computadores: vitrine.computadores });
  const titulo = preencher(c.hero.titulo, valores).replace(/\.$/, "");
  return {
    titulo: `DumTech Hub · ${titulo}`.slice(0, 90),
    descricao: preencher(c.hero.chamada, valores).replace(/\s+/g, " ").slice(0, 200),
  };
}

export function gravar(html, { titulo, descricao }) {
  return html
    .replace(/<title>[^<]*<\/title>/, `<title>${escapar(titulo)}</title>`)
    .replace(/<meta name="description" content="[^"]*">/, `<meta name="description" content="${escapar(descricao)}">`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  try {
    const resposta = await fetch(`${CONFIG.SUPABASE_URL}/rpc/dumtech_mensalidade_publica`, {
      method: "POST",
      headers: { apikey: CONFIG.SUPABASE_ANON, Authorization: `Bearer ${CONFIG.SUPABASE_ANON}`,
                 "Content-Type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(15_000),
    });
    const textos = resposta.ok ? textosDoHtml(await resposta.json()) : null;
    if (!textos) {
      console.log("     Textos do site: nada publicado no painel, o HTML fica com o texto padrao.");
    } else {
      fs.writeFileSync(ARQUIVO, gravar(fs.readFileSync(ARQUIVO, "utf8"), textos));
      console.log(`     Textos do site: titulo e descricao publicados gravados no HTML.`);
    }
  } catch (erro) {
    console.log(`     Textos do site: nao deu para buscar (${erro.message}); o HTML fica com o texto padrao.`);
  }
}
