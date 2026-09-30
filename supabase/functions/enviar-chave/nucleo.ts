// O e-mail "sua licenca esta pronta": validacao e montagem (sem Deno, sem rede).
// Testado em supabase/functions/tests/enviar-chave.test.mjs.

export type DadosDaChave = {
  nome?: string;
  email?: string;
  chave?: string;
  tipo?: string;
  expira_em?: string | null;
  max_computadores?: number;
  modulos?: string[];
};

export const ASSUNTO = "Sua licença DumTech está pronta";

export function uuidValido(texto: unknown): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(texto ?? ""));
}

export function emailValido(texto: unknown): boolean {
  return /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(String(texto ?? ""));
}

const escapar = (texto: unknown) =>
  String(texto ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);

function dataCurta(valor: string): string {
  const [ano, mes, dia] = valor.slice(0, 10).split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : valor;
}

/** Texto e HTML do e-mail. Tudo que vem do banco entra escapado no HTML. */
export function montarEmail(dados: DadosDaChave): { assunto: string; texto: string; html: string } {
  const primeiroNome = String(dados.nome ?? "").trim().split(/\s+/)[0] ?? "";
  const modulos = (dados.modulos ?? []).filter(Boolean);
  const extras: string[] = [];
  if (modulos.length) extras.push(`Módulos: ${modulos.join(", ")}`);
  if (dados.expira_em) extras.push(`Válida até: ${dataCurta(String(dados.expira_em))}`);
  if (Number(dados.max_computadores) > 1) extras.push(`Pode ativar em até ${dados.max_computadores} computadores.`);

  const texto = [
    primeiroNome ? `Olá, ${primeiroNome}!` : "Olá!",
    "",
    "Sua licença DumTech está pronta.",
    "",
    `Chave: ${dados.chave ?? ""}`,
    ...extras,
    "",
    "Como ativar: abra o DumTech Hub, entre em Licença, cole a chave e clique em Ativar. Os módulos aparecem na hora.",
    "",
    "Guarde esta chave: ela é sua e vale para reinstalar o programa.",
  ].join("\n");

  const html = `<!doctype html><html lang="pt-BR"><body style="margin:0;background:#f6f6f9;font-family:Segoe UI,Arial,sans-serif;color:#1d1d29">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border:1px solid #e6e6ee;border-radius:16px">
<tr><td style="padding:28px 28px 8px"><div style="font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#7353F6">DumTech</div>
<h1 style="margin:10px 0 0;font-size:22px">${primeiroNome ? `Olá, ${escapar(primeiroNome)}!` : "Olá!"} Sua licença está pronta.</h1></td></tr>
<tr><td style="padding:16px 28px"><div style="font-size:12px;color:#75758a;margin-bottom:6px">Sua chave</div>
<div style="font-family:Consolas,monospace;font-size:22px;font-weight:700;letter-spacing:.06em;background:#f1effe;color:#3b2aa8;border-radius:10px;padding:14px 16px;text-align:center">${escapar(dados.chave)}</div>
${extras.map((linha) => `<p style="margin:12px 0 0;font-size:14px;color:#4a4a5c">${escapar(linha)}</p>`).join("")}</td></tr>
<tr><td style="padding:8px 28px 28px;font-size:14px;line-height:1.55;color:#4a4a5c">
<p style="margin:12px 0"><strong>Como ativar:</strong> abra o DumTech Hub, entre em <em>Licença</em>, cole a chave e clique em <em>Ativar</em>. Os módulos aparecem na hora.</p>
<p style="margin:12px 0 0;color:#75758a">Guarde esta chave: ela é sua e vale para reinstalar o programa.</p></td></tr>
</table></td></tr></table></body></html>`;

  return { assunto: ASSUNTO, texto, html };
}

/** Quem pode chamar do navegador (o painel). Vazio = qualquer origem (o token decide). */
export function cabecalhosCors(origemPermitida: string, origemPedido: string | null): Record<string, string> {
  const origem = !origemPermitida || origemPermitida === "*" ? "*"
    : origemPedido === origemPermitida ? origemPermitida : "null";
  return {
    "Access-Control-Allow-Origin": origem,
    "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    Vary: "Origin",
  };
}
