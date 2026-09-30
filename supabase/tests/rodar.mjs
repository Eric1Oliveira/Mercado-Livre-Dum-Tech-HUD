// Roda os testes SQL num Postgres de mentira, aqui no computador.
//
//     cd supabase && npm install   (uma vez: baixa o PGlite)
//     node tests/rodar.mjs         (todos)
//     node tests/rodar.mjs versao_test.sql
//
// O PGlite e um Postgres de verdade compilado para rodar dentro do Node: as
// migrations sao aplicadas na ordem e cada teste roda como no SQL Editor -
// dentro de uma transacao que se desfaz no fim. Nada toca o banco de producao.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const SUPABASE = path.dirname(AQUI);

let PGlite;
try {
  ({ PGlite } = await import("@electric-sql/pglite"));
} catch {
  console.error("Falta o PGlite. Rode:  cd supabase && npm install");
  process.exit(2);
}

const db = new PGlite();
// os mesmos papeis do Supabase: e por eles que os testes conferem permissao
await db.exec(`
  create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;
  grant usage on schema public to anon, authenticated, service_role;
  alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
  alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
  alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;`);

const migrations = path.join(SUPABASE, "migrations");
for (const arquivo of fs.readdirSync(migrations).sort()) {
  try {
    await db.exec(fs.readFileSync(path.join(migrations, arquivo), "utf8"));
  } catch (erro) {
    console.error(`MIGRATION ${arquivo}: ${erro.message}`);
    process.exit(1);
  }
}

const pedidos = process.argv.slice(2);
const testes = pedidos.length
  ? pedidos
  : fs.readdirSync(AQUI).filter((a) => a.endsWith("_test.sql")).sort();

let falhas = 0;
for (const teste of testes) {
  try {
    await db.exec(fs.readFileSync(path.join(AQUI, teste), "utf8"));
    console.log("ok  ", teste);
  } catch (erro) {
    falhas += 1;
    console.error("FALHOU", teste, "-", erro.message);
    await db.exec("rollback").catch(() => {});
  }
}

console.log(`\n${testes.length - falhas}/${testes.length} baterias SQL passaram.`);
process.exit(falhas ? 1 : 0);
