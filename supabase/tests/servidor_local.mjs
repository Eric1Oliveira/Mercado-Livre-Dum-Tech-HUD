// Um "Supabase" de mentira, aqui no computador, para testar o agendamento online
// de ponta a ponta sem tocar no banco de producao.
//
//     cd supabase && node tests/servidor_local.mjs          -> http://127.0.0.1:54999
//
// O que sobe:
//   * o Postgres de teste (PGlite) com TODAS as migrations, em memoria;
//   * as funcoes respondendo em POST /rest/v1/rpc/<funcao>, como o PostgREST;
//   * a landingpage, com /agendar/<endereco> abrindo agendar/index.html (o
//     mesmo que o .htaccess faz na HostGator);
//   * uma loja de teste com a Agenda liberada. A chave e a maquina saem no
//     console: e com elas que o Hub de desenvolvimento conversa.
//
// O Hub aponta para ca com DUMTECH_SUPABASE_URL=http://127.0.0.1:54999/rest/v1
// (so fora do programa instalado). A pagina, com ?api=http://127.0.0.1:54999/rest/v1.
// Ao fechar, tudo some.
import { createServer } from "node:http";
import fs from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const SUPABASE = path.dirname(AQUI);
const LANDING = path.join(SUPABASE, "..", "landingpage");
const PORTA = Number(process.env.PORTA || 54999);
const MAQUINA = "AAAA-BBBB-CCCC-TEST";

const { PGlite } = await import("@electric-sql/pglite");
const db = new PGlite();
await db.exec(`
  create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;
  grant usage on schema public to anon, authenticated, service_role;
  alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
  alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
  alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;`);
for (const arquivo of fs.readdirSync(path.join(SUPABASE, "migrations")).sort()) {
  await db.exec(fs.readFileSync(path.join(SUPABASE, "migrations", arquivo), "utf8"));
}

const cliente = (await db.query(
  "insert into public.clientes (nome, email) values ('Loja de Teste', 'teste@local.dev') returning id")).rows[0].id;
const chave = (await db.query(
  "select chave from public.dumtech_emitir_licenca($1, array['AGENDA'])", [cliente])).rows[0].chave;
await db.query("select public.dumtech_ativar_licenca($1, $2, 'teste')", [chave, MAQUINA]);

const TIPOS = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".json": "application/json",
};
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, accept",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};

/** {p_a: 1, p_b: [..]} -> "p_a => $1, p_b => $2" e os valores, como o PostgREST faz. */
function argumentos(corpo) {
  const nomes = Object.keys(corpo).filter((nome) => /^p_[a-z_]+$/.test(nome));
  const valores = nomes.map((nome) => {
    const valor = corpo[nome];
    if (Array.isArray(valor)) {
      return nome === "p_ocupados" ? JSON.stringify(valor)
        : `{${valor.map((item) => `"${String(item).replace(/"/g, "")}"`).join(",")}}`;
    }
    if (valor !== null && typeof valor === "object") return JSON.stringify(valor);
    return valor;
  });
  return { sql: nomes.map((nome, i) => `${nome} => $${i + 1}`).join(", "), valores };
}

async function rpc(funcao, corpo, res) {
  if (!/^dumtech_[a-z_]+$/.test(funcao)) {
    res.writeHead(404, CORS).end();
    return;
  }
  const { sql, valores } = argumentos(corpo);
  try {
    const { rows } = await db.query(`select public.${funcao}(${sql}) as r`, valores);
    res.writeHead(200, { ...CORS, "Content-Type": "application/json" }).end(JSON.stringify(rows[0].r));
  } catch (erro) {
    console.error(`rpc ${funcao}:`, erro.message);
    res.writeHead(400, { ...CORS, "Content-Type": "application/json" })
      .end(JSON.stringify({ message: erro.message }));
  }
}

async function arquivo(caminho, res) {
  // o mesmo que o .htaccess: /agendar/<endereco> abre a pagina de agendamento
  if (/^\/agendar\/[a-z0-9-]+\/?$/.test(caminho)) caminho = "/agendar/index.html";
  const alvo = path.join(LANDING, path.normalize(caminho.endsWith("/") ? `${caminho}index.html` : caminho));
  if (!alvo.startsWith(LANDING)) {
    res.writeHead(403).end();
    return;
  }
  try {
    const conteudo = await readFile(alvo);
    res.writeHead(200, { "Content-Type": TIPOS[path.extname(alvo)] || "application/octet-stream",
      "Cache-Control": "no-store" }).end(conteudo);
  } catch {
    res.writeHead(404).end("nao achei");
  }
}

createServer((req, res) => {
  const caminho = decodeURIComponent(req.url.split("?")[0]);
  if (req.method === "OPTIONS") {
    res.writeHead(204, CORS).end();
    return;
  }
  const funcao = /^\/rest\/v1\/rpc\/([a-z_]+)$/.exec(caminho);
  if (req.method === "POST" && funcao) {
    let bruto = "";
    req.on("data", (pedaco) => { bruto += pedaco; });
    req.on("end", () => {
      let corpo = {};
      try { corpo = JSON.parse(bruto || "{}"); } catch { /* corpo vazio */ }
      rpc(funcao[1], corpo, res);
    });
    return;
  }
  arquivo(caminho, res);
}).listen(PORTA, "127.0.0.1", () => {
  console.log(JSON.stringify({ porta: PORTA, chave, maquina: MAQUINA }));
});
