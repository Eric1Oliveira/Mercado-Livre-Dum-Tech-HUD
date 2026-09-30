// O carteiro das Edge Functions: manda um e-mail pelo Brevo ou pelo Resend.
//
// Usado por `enviar-chave` (o botao do painel) e por `checkout` (a chave que
// sai sozinha quando o pagamento e confirmado). Antes, `enviar-chave` so
// conhecia o Resend - e o projeto usa o Brevo, entao o botao do painel nao
// entregava nada.
//
//   BREVO_API_KEY            brevo.com - 300 e-mails/dia gratis (tem prioridade)
//   RESEND_API_KEY           resend.com - exige dominio proprio verificado
//   DUMTECH_EMAIL_REMETENTE  "DumTech <licencas@seudominio.com.br>" ou so o e-mail
//   DUMTECH_EMAIL_RESPONDER  opcional: para onde vai a resposta do cliente

export type Carta = { para: string; assunto: string; texto: string; html: string };

export type Correio = {
  brevo: string;
  resend: string;
  remetente: string;
  responder?: string;
  buscar?: typeof fetch;
};

/** "DumTech <x@y.com>" -> {nome, email}. So o e-mail tambem vale. */
export function remetente(texto: string): { nome: string; email: string } {
  const achado = /^\s*(.*?)\s*<([^>]+)>\s*$/.exec(texto ?? "");
  return achado
    ? { nome: achado[1] || "DumTech", email: achado[2].trim() }
    : { nome: "DumTech", email: String(texto ?? "").trim() };
}

/** Da para mandar e-mail com o que esta configurado? */
export function configurado(correio: Correio): boolean {
  return Boolean(correio.remetente && (correio.brevo || correio.resend));
}

/** Manda. Devolve true so quando o servico aceitou o e-mail. */
export async function enviar(correio: Correio, carta: Carta): Promise<boolean> {
  const buscar = correio.buscar ?? fetch;
  const de = remetente(correio.remetente);
  try {
    if (correio.brevo) {
      const resposta = await buscar("https://api.brevo.com/v3/smtp/email", {
        method: "POST",
        headers: { "api-key": correio.brevo, "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          sender: { name: de.nome, email: de.email },
          to: [{ email: carta.para }],
          subject: carta.assunto, textContent: carta.texto, htmlContent: carta.html,
          ...(correio.responder ? { replyTo: { email: remetente(correio.responder).email } } : {}),
        }),
        signal: AbortSignal.timeout(12_000),
      });
      if (!resposta.ok) console.error("brevo", resposta.status, (await resposta.text()).slice(0, 300));
      return resposta.ok;
    }
    const resposta = await buscar("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${correio.resend}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: correio.remetente, to: [carta.para], subject: carta.assunto,
        text: carta.texto, html: carta.html,
        ...(correio.responder ? { reply_to: correio.responder } : {}),
      }),
      signal: AbortSignal.timeout(12_000),
    });
    if (!resposta.ok) console.error("resend", resposta.status, (await resposta.text()).slice(0, 300));
    return resposta.ok;
  } catch (erro) {
    console.error("e-mail", erro);
    return false;
  }
}
