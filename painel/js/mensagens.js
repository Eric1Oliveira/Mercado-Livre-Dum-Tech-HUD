// A mensagem "sua licença está pronta" e os links que a levam ao cliente.
//
// Lógica pura (sem DOM, sem rede): testada em tests/mensagens.test.mjs.
// O e-mail automático (supabase/functions/enviar-chave) tem o seu próprio
// modelo em HTML; o texto que o cliente lê é o mesmo nos dois.
//
// DUAS VERSÕES, porque o Mercado Livre proíbe link, telefone e e-mail nas
// mensagens da venda:
//   - "direto"        WhatsApp e e-mail: com o link de download e o suporte
//   - "mercadolivre"  só a chave e os passos; o link vai no guia PDF anexado

/** Texto pronto. `dados` vem de dumtech_dados_da_chave (ou da reserva da tela). */
export function mensagemDaChave(dados = {}, { canal = "direto", download = "", suporte = "" } = {}) {
  const primeiroNome = String(dados.nome || "").trim().split(/\s+/)[0] || "";
  const modulos = (dados.modulos || []).filter(Boolean);
  const mercadoLivre = canal === "mercadolivre";

  const linhas = [
    primeiroNome ? `Olá, ${primeiroNome}!` : "Olá!",
    "",
    mercadoLivre ? "Obrigado pela compra! Sua licença do DumTech Hub está pronta." : "Sua licença DumTech está pronta.",
    "",
    `Chave: ${dados.chave || "—"}`,
  ];
  if (modulos.length) linhas.push(`Módulos: ${modulos.join(", ")}`);
  if (dados.expira_em) linhas.push(`Válida até: ${dataCurta(dados.expira_em)}`);
  if (Number(dados.max_computadores) > 1) linhas.push(`Pode ativar em até ${dados.max_computadores} computadores.`);

  linhas.push("");
  if (mercadoLivre) {
    linhas.push(
      "Como começar:",
      "1. Abra o guia de instalação anexado nesta mensagem, baixe e instale o DumTech Hub.",
      "2. Abra o programa e informe seu nome e e-mail.",
      "3. Cole a chave acima e clique em Ativar. Os módulos aparecem na hora.",
      "",
      "Qualquer dúvida, responda aqui mesmo nesta conversa.",
    );
  } else {
    linhas.push(
      "Como começar:",
      download ? `1. Baixe e instale o DumTech Hub: ${download}` : "1. Instale o DumTech Hub.",
      "2. Abra o programa e informe seu nome e e-mail.",
      "3. Cole a chave acima e clique em Ativar. Os módulos aparecem na hora.",
    );
    if (suporte) linhas.push("", `Dúvidas: ${suporte}`);
  }
  linhas.push("", "Guarde esta chave: ela é sua e vale para reinstalar o programa.");
  return linhas.join("\n");
}

export const ASSUNTO_DA_CHAVE = "Sua licença DumTech está pronta";

/**
 * O Mercado Livre bloqueia mensagem com link, e-mail ou telefone. Devolve o
 * que parece contato - a tela avisa antes de você colar e tomar sanção.
 */
export function contatosNoTexto(texto) {
  const achados = [];
  const t = String(texto || "");
  if (/https?:\/\/|www\.|\b[a-z0-9-]+\.(com|net|app|br|io)\b/i.test(t)) achados.push("link");
  if (/[^\s@]+@[^\s@]+\.[^\s@]{2,}/.test(t)) achados.push("e-mail");
  if (/(\+?55\s*)?\(?\d{2}\)?\s*9?\d{4}[-\s]?\d{4}/.test(t.replace(/[A-Z0-9]{4}(-[A-Z0-9]{4}){3}/g, ""))) achados.push("telefone");
  return achados;
}

/**
 * wa.me com o número no formato internacional. Número brasileiro sem DDI
 * (10 ou 11 dígitos) ganha o 55. Sem número válido, devolve "".
 */
export function linkWhatsApp(telefone, texto) {
  let numero = String(telefone || "").replace(/\D/g, "");
  if (numero.length === 10 || numero.length === 11) numero = `55${numero}`;
  if (numero.length < 12 || numero.length > 15) return "";
  return `https://wa.me/${numero}?text=${encodeURIComponent(texto)}`;
}

export function linkEmail(email, assunto, texto) {
  const destino = String(email || "").trim();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(destino)) return "";
  return `mailto:${encodeURIComponent(destino)}?subject=${encodeURIComponent(assunto)}` +
         `&body=${encodeURIComponent(texto)}`;
}

function dataCurta(valor) {
  const [ano, mes, dia] = String(valor).slice(0, 10).split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : String(valor);
}
