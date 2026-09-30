// Servidor estatico minimo, so para ver a pagina no navegador durante o
// desenvolvimento (modulos ES nao carregam por file://).
//
//     npm run servir      -> http://127.0.0.1:5173
//
// Em producao nao existe servidor nenhum: a pasta inteira e estatica.

import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

// fileURLToPath e obrigatorio aqui: `url.pathname` vem percent-encoded, e o
// caminho deste projeto tem espaco e acento ("Projetos%20Pr%C3%B3prios") -
// usar o pathname cru faz o servidor nao achar arquivo nenhum.
const RAIZ = fileURLToPath(new URL(".", import.meta.url));
const PORTA = Number(process.argv[2] || 5173);

const TIPOS = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".woff2": "font/woff2",
};

createServer(async (req, res) => {
  const caminho = decodeURIComponent(req.url.split("?")[0]);
  // pasta (/baixar/, /pedido/) abre o index.html dela, como no Apache
  const arquivo = join(RAIZ, normalize(caminho.endsWith("/") ? `${caminho}index.html` : caminho));

  if (!arquivo.startsWith(RAIZ)) {
    res.writeHead(403).end("fora da pasta");
    return;
  }
  try {
    const conteudo = await readFile(arquivo);
    res.writeHead(200, {
      "Content-Type": TIPOS[extname(arquivo).toLowerCase()] || "application/octet-stream",
      "Cache-Control": "no-store",
    });
    res.end(conteudo);
  } catch {
    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("nao encontrado");
  }
}).listen(PORTA, "127.0.0.1", () => {
  console.log(`landing page em http://127.0.0.1:${PORTA}`);
});
