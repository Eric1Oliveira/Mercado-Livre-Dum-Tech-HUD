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
  ".mp4": "video/mp4",
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
    const cabecalhos = {
      "Content-Type": TIPOS[extname(arquivo).toLowerCase()] || "application/octet-stream",
      "Cache-Control": "no-store",
      "Accept-Ranges": "bytes",
    };
    // pedido de um trecho, como o Apache responde: sem isso o navegador nao pula
    // para um ponto do video (clicar num passo do Passo a passo volta ao zero)
    const trecho = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || "");
    if (trecho && (trecho[1] || trecho[2])) {
      const total = conteudo.length;
      const inicio = trecho[1] ? Number(trecho[1]) : Math.max(0, total - Number(trecho[2]));
      const fim = trecho[1] && trecho[2] ? Math.min(Number(trecho[2]), total - 1) : total - 1;
      if (inicio >= total || inicio > fim) {
        res.writeHead(416, { "Content-Range": `bytes */${total}` }).end();
        return;
      }
      res.writeHead(206, { ...cabecalhos, "Content-Range": `bytes ${inicio}-${fim}/${total}`, "Content-Length": fim - inicio + 1 });
      res.end(conteudo.subarray(inicio, fim + 1));
      return;
    }
    res.writeHead(200, cabecalhos);
    res.end(conteudo);
  } catch {
    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("nao encontrado");
  }
}).listen(PORTA, "127.0.0.1", () => {
  console.log(`landing page em http://127.0.0.1:${PORTA}`);
});
