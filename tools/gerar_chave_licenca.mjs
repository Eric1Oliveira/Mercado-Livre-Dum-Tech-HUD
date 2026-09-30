// Gera o par de chaves que ASSINA as licencas (Ed25519).
//
//   node tools/gerar_chave_licenca.mjs [pasta_fora_do_projeto] [kid]
//
// - a chave PRIVADA vai para um arquivo FORA do projeto. Ela so pode existir em
//   dois lugares: nesse arquivo (guarde num cofre) e no segredo
//   DUMTECH_LICENCA_CHAVE_PRIVADA da Edge Function `licenca-assinada`.
//   Quem tem essa chave emite licenca de qualquer modulo para qualquer um.
// - a chave PUBLICA (hex) vai para `CHAVES_PUBLICAS` em
//   src/dumtech/core/assinatura.py. Ela e publica de verdade: so confere.
//
// Trocar de chave: gere com outro `kid` (k2), acrescente a publica nova ao lado
// da antiga no Hub, recompile, e so depois troque o segredo da funcao.

import { generateKeyPairSync } from "node:crypto";
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const pasta = process.argv[2] || join(homedir(), "DumTech-segredos");
const kid = process.argv[3] || "k1";
const arquivo = join(pasta, `licenca-${kid}-privada.txt`);

if (existsSync(arquivo)) {
  console.error(`Ja existe ${arquivo}. Nao sobrescrevo chave privada - use outro kid.`);
  process.exit(1);
}

const { publicKey, privateKey } = generateKeyPairSync("ed25519");
const privadaPkcs8 = privateKey.export({ format: "der", type: "pkcs8" }).toString("base64");
// SPKI de Ed25519 = 12 bytes de cabecalho + 32 bytes da chave
const publicaHex = publicKey.export({ format: "der", type: "spki" }).subarray(12).toString("hex");

mkdirSync(pasta, { recursive: true });
writeFileSync(arquivo, privadaPkcs8 + "\n", { mode: 0o600 });

console.log(`kid ............ ${kid}`);
console.log(`chave publica .. ${publicaHex}`);
console.log(`chave privada .. gravada em ${arquivo}`);
console.log("");
console.log("Proximos passos:");
console.log(`  1. src/dumtech/core/assinatura.py -> CHAVES_PUBLICAS["${kid}"] = "${publicaHex}"`);
console.log("  2. Supabase > Edge Functions > licenca-assinada > Secrets:");
console.log("       DUMTECH_LICENCA_CHAVE_PRIVADA = (conteudo do arquivo acima)");
console.log(`       DUMTECH_LICENCA_KID           = ${kid}`);
