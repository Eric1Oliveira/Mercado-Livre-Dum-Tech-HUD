// O e-mail "chegou um agendamento": validacao e montagem (sem Deno, sem rede).
// Testado em supabase/functions/tests/avisar-reserva.test.mjs.

export type AvisoDeReserva = {
  email?: string;
  empresa?: string;
  servico?: string;
  /** Hora da loja: AAAA-MM-DDTHH:MM */
  inicio?: string;
  nome?: string;
  telefone?: string;
};

export function uuidValido(texto: unknown): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(texto ?? ""));
}

const escapar = (texto: unknown) =>
  String(texto ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);

/** 2026-11-05T14:30 -> 05/11 às 14:30 */
export function quando(inicio: string): string {
  const achado = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(inicio ?? "");
  return achado ? `${achado[3]}/${achado[2]} às ${achado[4]}` : String(inicio ?? "");
}

function telefoneDeLer(numero: string): string {
  const digitos = String(numero ?? "").replace(/\D/g, "");
  const achado = /^(\d{2})(\d{4,5})(\d{4})$/.exec(digitos);
  return achado ? `(${achado[1]}) ${achado[2]}-${achado[3]}` : digitos;
}

/** Texto e HTML do e-mail. Tudo que veio do formulario entra escapado no HTML. */
export function montarAviso(dados: AvisoDeReserva): { assunto: string; texto: string; html: string } {
  const data = quando(String(dados.inicio ?? ""));
  const nome = String(dados.nome ?? "").trim();
  const servico = String(dados.servico ?? "").trim();
  const telefone = telefoneDeLer(String(dados.telefone ?? ""));
  const texto = [
    `${nome} marcou ${servico} para ${data}.`,
    telefone ? `WhatsApp: ${telefone}` : "",
    "",
    "Quando você abrir o DumTech Hub, este horário entra sozinho na Agenda.",
  ].filter((linha, i) => linha || i === 2).join("\n");
  const html = `<p><strong>${escapar(nome)}</strong> marcou <strong>${escapar(servico)}</strong> ` +
    `para <strong>${escapar(data)}</strong>.</p>` +
    (telefone ? `<p>WhatsApp: ${escapar(telefone)}</p>` : "") +
    "<p>Quando você abrir o DumTech Hub, este horário entra sozinho na Agenda.</p>";
  return { assunto: `Novo agendamento: ${servico} em ${data}`, texto, html };
}
