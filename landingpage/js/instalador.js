// O botao de baixar segue a versao lancada no painel.
//
// Lancar pelo painel nao mexe no site: o instalador generico so muda quando o site
// e publicado. Aqui a pagina pergunta qual versao esta no ar e aponta para o
// arquivo dela. Sem resposta, fica o link que ja estava no HTML, que tambem funciona.

import { CONFIG } from "./config.js";

/** So arquivo nosso, da pasta de downloads: o nome, nunca o endereco que veio. */
export function arquivoDaVersao(url) {
  return /^https:\/\/[^/]+\/baixar\/(DumTech-Hub-Setup-[0-9.]+\.exe)$/.exec(String(url ?? ""))?.[1] ?? "";
}

export async function apontarInstalador(links, pasta = "") {
  try {
    const resposta = await fetch(`${CONFIG.SUPABASE_URL}/rpc/dumtech_hub_versao`, {
      method: "POST",
      headers: { apikey: CONFIG.SUPABASE_ANON, Authorization: `Bearer ${CONFIG.SUPABASE_ANON}`,
                 "Content-Type": "application/json" },
      body: "{}",
    });
    const arquivo = arquivoDaVersao((await resposta.json())?.url);
    if (arquivo) for (const link of links) link.href = `${pasta}${arquivo}`;
  } catch {
    /* sem rede ou sem resposta: o link generico continua valendo */
  }
}
