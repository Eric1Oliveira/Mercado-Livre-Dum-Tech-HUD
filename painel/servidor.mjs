// Servidor de desenvolvimento do painel: `node servidor.mjs`.
//
// O painel é só HTML, CSS e módulos ES — mas `file://` não carrega módulos, e o
// Supabase Auth precisa de uma origem de verdade. Daí este servidor.
//
// Ele serve apenas esta pasta, e só o que existe nela.

import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = dirname(fileURLToPath(import.meta.url));
const PORTA = Number(process.env.PORTA || 4010);

const TIPOS = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

createServer((pedido, resposta) => {
  const caminho = decodeURIComponent(new URL(pedido.url, "http://localhost").pathname);
  const arquivo = normalize(join(RAIZ, caminho === "/" ? "index.html" : caminho));

  if (!arquivo.startsWith(RAIZ + sep) && arquivo !== join(RAIZ, "index.html")) {
    resposta.writeHead(403).end("fora da pasta");
    return;
  }

  let dados;
  try {
    dados = statSync(arquivo);
  } catch {
    resposta.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" })
            .end("não encontrei esse arquivo");
    return;
  }
  if (dados.isDirectory()) {
    resposta.writeHead(403).end("é uma pasta");
    return;
  }

  const extensao = arquivo.slice(arquivo.lastIndexOf("."));
  resposta.writeHead(200, {
    "Content-Type": TIPOS[extensao] || "application/octet-stream",
    "Cache-Control": "no-store",
  });
  createReadStream(arquivo).pipe(resposta);
}).listen(PORTA, () => {
  console.log(`Painel DumTech em http://localhost:${PORTA}`);
  console.log("Entre com uma conta criada no Supabase (Authentication > Users)");
  console.log("e liberada na tabela administradores. Ctrl+C para parar.");
});
