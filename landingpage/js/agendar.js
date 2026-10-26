// O agendamento online: as contas da pagina, sem tela e sem rede.
//
// Tudo aqui e funcao pura (testada em tests/agendar.test.mjs): o endereco do
// link, o WhatsApp com mascara, os horarios agrupados por periodo, as datas
// por extenso, o arquivo de calendario e a reserva guardada no celular.
//
// Quem decide se um horario esta livre e o SERVIDOR (dumtech_agenda_livres).
// A pagina so desenha o que ele manda - e o servidor confere de novo na hora
// de marcar.

/** As 8 cores que o dono escolhe no Hub (todas com contraste AA para texto branco). */
export const CORES = {
  violeta: "#6A4CE8",
  rosa: "#C2185B",
  vinho: "#8E2443",
  terracota: "#B0432A",
  verde: "#1B7A4B",
  petroleo: "#0E6E78",
  azul: "#2456C2",
  grafite: "#3A4150",
};

const SLUG = /^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$/;

/** O endereco do link: /agendar/beauty-cia, /agendar/?l=beauty-cia ou /agendar/#beauty-cia. */
export function slugDaUrl(endereco) {
  let url;
  try {
    url = new URL(endereco);
  } catch {
    return "";
  }
  const ultimo = url.pathname.replace(/\/+$/, "").split("/").pop() || "";
  const candidatos = [
    url.searchParams.get("l") || "",
    url.hash.replace(/^#/, ""),
    ["agendar", "index.html"].includes(ultimo) ? "" : ultimo,
  ];
  for (const candidato of candidatos) {
    let texto = "";
    try {
      texto = decodeURIComponent(candidato).trim().toLowerCase();
    } catch {
      continue;
    }
    if (SLUG.test(texto)) return texto;
  }
  return "";
}

export function soDigitos(texto) {
  return String(texto ?? "").replace(/\D/g, "");
}

/** Celular ou fixo brasileiro com DDD (o 55 na frente e aceito). Mesma regra do servidor. */
export function telefoneValido(texto) {
  let d = soDigitos(texto);
  if ((d.length === 12 || d.length === 13) && d.startsWith("55")) d = d.slice(2);
  return (d.length === 10 || d.length === 11) && d[0] !== "0" && d[1] !== "0";
}

/** Formata enquanto a pessoa digita: (11) 9, (11) 98765-4321... */
export function mascaraTelefone(texto) {
  const d = soDigitos(texto).slice(0, 11);
  if (d.length <= 2) return d ? `(${d}` : "";
  const ddd = d.slice(0, 2);
  const resto = d.slice(2);
  if (resto.length <= 4) return `(${ddd}) ${resto}`;
  const corte = d.length === 11 ? 5 : 4;
  return `(${ddd}) ${resto.slice(0, corte)}-${resto.slice(corte)}`;
}

/** "09:30" -> "Manhã". */
export function periodo(hora) {
  const h = Number(String(hora).slice(0, 2));
  if (h < 12) return "Manhã";
  if (h < 18) return "Tarde";
  return "Noite";
}

/** Os horarios do dia em Manha / Tarde / Noite, sem periodo vazio. */
export function agruparPorPeriodo(horarios) {
  const grupos = new Map([["Manhã", []], ["Tarde", []], ["Noite", []]]);
  for (const hora of horarios ?? []) grupos.get(periodo(hora)).push(hora);
  return [...grupos].filter(([, lista]) => lista.length).map(([nome, lista]) => ({ nome, horarios: lista }));
}

const SEMANA_CURTA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const SEMANA = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];
const MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
  "outubro", "novembro", "dezembro"];

/** "2026-10-30" -> {ano, mes (0-11), dia, semana (0 = domingo)} sem fuso no meio. */
export function lerData(iso) {
  const [ano, mes, dia] = String(iso).slice(0, 10).split("-").map(Number);
  const semana = new Date(Date.UTC(ano, mes - 1, dia)).getUTCDay();
  return { ano, mes: mes - 1, dia, semana };
}

function somarDias(iso, dias) {
  const { ano, mes, dia } = lerData(iso);
  return new Date(Date.UTC(ano, mes, dia + dias)).toISOString().slice(0, 10);
}

/** A ficha do dia na faixa: {semana: "hoje" | "amanhã" | "qui", dia: "30", mes: "out"}. */
export function rotuloDoDia(iso, hoje) {
  const d = lerData(iso);
  let semana = SEMANA_CURTA[d.semana];
  if (hoje && iso === hoje) semana = "hoje";
  else if (hoje && iso === somarDias(hoje, 1)) semana = "amanhã";
  return { semana, dia: String(d.dia), mes: MESES_CURTOS[d.mes] };
}

/** "quinta-feira, 30 de outubro". */
export function dataPorExtenso(iso) {
  const d = lerData(iso);
  return `${SEMANA[d.semana]}, ${d.dia} de ${MESES[d.mes]}`;
}

/** "qui 30/10". */
export function dataCurta(iso) {
  const d = lerData(iso);
  return `${SEMANA_CURTA[d.semana]} ${String(d.dia).padStart(2, "0")}/${String(d.mes + 1).padStart(2, "0")}`;
}

export function nomeDoMes(iso) {
  return MESES[lerData(iso).mes];
}

export function nomeDoDia(iso) {
  return SEMANA[lerData(iso).semana];
}

/** "2026-10-30T14:00" -> "14:00". */
export function horaDe(momento) {
  return String(momento ?? "").slice(11, 16);
}

/** 30 -> "30 min", 60 -> "1 h", 90 -> "1h30". */
export function duracaoTexto(minutos) {
  const m = Number(minutos) || 0;
  const h = Math.floor(m / 60);
  const resto = m % 60;
  if (!h) return `${resto} min`;
  return resto ? `${h}h${String(resto).padStart(2, "0")}` : `${h} h`;
}

const REAIS = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/** 60 -> "R$ 60,00"; sem preco -> "". */
export function precoTexto(valor) {
  if (valor === null || valor === undefined || valor === "" || Number(valor) <= 0) return "";
  return REAIS.format(Number(valor)).replace(/\u00a0/g, " ");
}

/** Iniciais do nome da empresa para quando nao ha logotipo: "Beauty & Cia" -> "BC". */
export function iniciais(nome) {
  const palavras = String(nome ?? "").split(/\s+/).filter((p) => /^[\p{L}\p{N}]/u.test(p) && !(p === p.toLowerCase() && p.length <= 3));
  if (!palavras.length) return "•";
  if (palavras.length === 1) return palavras[0].slice(0, 2).toUpperCase();
  return (palavras[0][0] + palavras[1][0]).toUpperCase();
}

/** Logotipo so se for imagem embutida de verdade: nada que venha do servidor vira outro tipo de endereco. */
export function logoSeguro(logo) {
  return /^data:image\/(png|jpeg);base64,[A-Za-z0-9+/]+=*$/.test(String(logo ?? "")) ? logo : "";
}

/** Botao de WhatsApp: so com numero de verdade. */
export function linkWhatsApp(numero, texto = "") {
  const d = soDigitos(numero);
  if (d.length < 12 || d.length > 15) return "";
  return `https://wa.me/${d}${texto ? `?text=${encodeURIComponent(texto)}` : ""}`;
}

function textoIcs(texto) {
  return String(texto ?? "").replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/([,;])/g, "\\$1");
}

function momentoIcs(momento) {
  return String(momento).replace(/[-:]/g, "").slice(0, 13) + "00";
}

/**
 * O horario no calendario do celular (iPhone e Android abrem .ics).
 * Hora "flutuante", sem fuso: e a hora da parede da loja, que e a do cliente.
 */
export function arquivoIcs({ uid, titulo, inicio, fim, local = "", descricao = "", agora = new Date() }) {
  const carimbo = agora.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//DumTech//Agendamento online//PT-BR",
    "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT",
    `UID:${uid}@dumtechsolution.com`,
    `DTSTAMP:${carimbo}`,
    `DTSTART:${momentoIcs(inicio)}`,
    `DTEND:${momentoIcs(fim)}`,
    `SUMMARY:${textoIcs(titulo)}`,
    local ? `LOCATION:${textoIcs(local)}` : "",
    descricao ? `DESCRIPTION:${textoIcs(descricao)}` : "",
    "BEGIN:VALARM",
    "TRIGGER:-PT2H",
    "ACTION:DISPLAY",
    `DESCRIPTION:${textoIcs(titulo)}`,
    "END:VALARM",
    "END:VEVENT",
    "END:VCALENDAR",
    "",
  ].filter((linha, i, todas) => linha || i === todas.length - 1).join("\r\n");
}

// --------------------------------------------- a reserva guardada no celular --
const CHAVE = "dumtech.agenda.reservas";
const MAXIMO_GUARDADAS = 10;

function ler(armazenamento) {
  try {
    const lista = JSON.parse(armazenamento?.getItem(CHAVE) || "[]");
    return Array.isArray(lista) ? lista : [];
  } catch {
    return [];
  }
}

function gravar(armazenamento, lista) {
  try {
    armazenamento?.setItem(CHAVE, JSON.stringify(lista.slice(-MAXIMO_GUARDADAS)));
  } catch {
    // aba anonima ou armazenamento cheio: a reserva continua valendo no servidor
  }
}

/** Os horarios que este celular marcou neste link e que ainda nao passaram. */
export function lerReservas(armazenamento, slug, agora) {
  return ler(armazenamento).filter((r) => r && r.slug === slug && String(r.fim) > String(agora));
}

export function guardarReserva(armazenamento, reserva) {
  const lista = ler(armazenamento).filter((r) => r && r.codigo !== reserva.codigo);
  lista.push(reserva);
  gravar(armazenamento, lista);
}

export function esquecerReserva(armazenamento, codigo) {
  gravar(armazenamento, ler(armazenamento).filter((r) => r && r.codigo !== codigo));
}
