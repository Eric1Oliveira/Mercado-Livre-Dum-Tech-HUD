// Testes das contas da pagina de agendamento (js/agendar.js).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  agruparPorPeriodo,
  arquivoIcs,
  dataCurta,
  dataPorExtenso,
  duracaoTexto,
  esquecerReserva,
  guardarReserva,
  iniciais,
  lerReservas,
  linkWhatsApp,
  logoSeguro,
  mascaraTelefone,
  precoTexto,
  rotuloDoDia,
  slugDaUrl,
  telefoneValido,
} from "../js/agendar.js";

test("o endereco do link vem do caminho, do ?l= ou do #", () => {
  assert.equal(slugDaUrl("https://dumtechsolution.com/agendar/beauty-cia"), "beauty-cia");
  assert.equal(slugDaUrl("https://dumtechsolution.com/agendar/Beauty-Cia/"), "beauty-cia");
  assert.equal(slugDaUrl("http://127.0.0.1:8080/agendar/?l=salao-da-ana"), "salao-da-ana");
  assert.equal(slugDaUrl("http://127.0.0.1:8080/agendar/index.html#salao-da-ana"), "salao-da-ana");
  assert.equal(slugDaUrl("https://dumtechsolution.com/agendar/"), "");
  assert.equal(slugDaUrl("https://dumtechsolution.com/agendar/<script>"), "");
  assert.equal(slugDaUrl("nao e endereco"), "");
});

test("WhatsApp: mesma regra do servidor e mascara enquanto digita", () => {
  for (const bom of ["(11) 98765-4321", "6332258899", "+55 11 98765-4321"]) assert.ok(telefoneValido(bom), bom);
  for (const ruim of ["", "98765-4321", "(01) 98765-4321", "(10) 3225-8899", "123"]) assert.ok(!telefoneValido(ruim), ruim);
  assert.equal(mascaraTelefone("11"), "(11");
  assert.equal(mascaraTelefone("119876"), "(11) 9876");
  assert.equal(mascaraTelefone("1132258899"), "(11) 3225-8899");
  assert.equal(mascaraTelefone("11987654321"), "(11) 98765-4321");
  assert.equal(mascaraTelefone("119876543210"), "(11) 98765-4321");
});

test("horarios em manha, tarde e noite, sem periodo vazio", () => {
  assert.deepEqual(agruparPorPeriodo(["09:00", "11:30", "14:00", "19:00"]), [
    { nome: "Manhã", horarios: ["09:00", "11:30"] },
    { nome: "Tarde", horarios: ["14:00"] },
    { nome: "Noite", horarios: ["19:00"] },
  ]);
  assert.deepEqual(agruparPorPeriodo(["13:00"]).map((g) => g.nome), ["Tarde"]);
  assert.deepEqual(agruparPorPeriodo([]), []);
});

test("datas por extenso sem o fuso atrapalhar", () => {
  assert.equal(dataPorExtenso("2026-10-30"), "sexta-feira, 30 de outubro");
  assert.equal(dataCurta("2026-11-01"), "dom 01/11");
  assert.deepEqual(rotuloDoDia("2026-10-30", "2026-10-30"), { semana: "hoje", dia: "30", mes: "out" });
  assert.deepEqual(rotuloDoDia("2026-10-31", "2026-10-30"), { semana: "amanhã", dia: "31", mes: "out" });
  assert.deepEqual(rotuloDoDia("2026-11-02", "2026-10-30"), { semana: "seg", dia: "2", mes: "nov" });
});

test("duracao, preco e iniciais", () => {
  assert.equal(duracaoTexto(30), "30 min");
  assert.equal(duracaoTexto(60), "1 h");
  assert.equal(duracaoTexto(90), "1h30");
  assert.equal(precoTexto(60), "R$ 60,00");
  assert.equal(precoTexto(null), "");
  assert.equal(precoTexto(0), "");
  assert.equal(iniciais("Beauty & Cia"), "BC");
  assert.equal(iniciais("Salão da Ana"), "SA");
  assert.equal(iniciais("Barbearia"), "BA");
});

test("nada do servidor vira endereco perigoso", () => {
  assert.equal(logoSeguro("data:image/png;base64,iVBORw0KGgo="), "data:image/png;base64,iVBORw0KGgo=");
  assert.equal(logoSeguro("javascript:alert(1)"), "");
  assert.equal(logoSeguro("data:image/svg+xml;base64,PHN2Zz4="), "", "svg pode carregar script");
  assert.equal(linkWhatsApp("5511987654321", "Oi"), "https://wa.me/5511987654321?text=Oi");
  assert.equal(linkWhatsApp(""), "");
});

test("arquivo de calendario com hora da loja e lembrete", () => {
  const ics = arquivoIcs({
    uid: "abc", titulo: "Corte; Beauty & Cia", inicio: "2026-10-30T14:00", fim: "2026-10-30T14:45",
    local: "Rua das Flores, 120", agora: new Date("2026-10-26T12:00:00Z"),
  });
  assert.match(ics, /DTSTART:20261030T140000\r\n/);
  assert.match(ics, /DTEND:20261030T144500\r\n/);
  assert.match(ics, /SUMMARY:Corte\\; Beauty & Cia\r\n/);
  assert.match(ics, /LOCATION:Rua das Flores\\, 120\r\n/);
  assert.match(ics, /TRIGGER:-PT2H/);
  assert.ok(!ics.includes("DESCRIPTION:\r\n"), "linha vazia nao entra");
});

test("a reserva fica guardada no celular ate o horario passar", () => {
  const memoria = new Map();
  const armazenamento = { getItem: (k) => memoria.get(k) ?? null, setItem: (k, v) => memoria.set(k, v) };
  guardarReserva(armazenamento, { codigo: "a", slug: "beauty-cia", fim: "2026-10-30T14:45" });
  guardarReserva(armazenamento, { codigo: "b", slug: "outra", fim: "2026-10-30T15:00" });
  guardarReserva(armazenamento, { codigo: "c", slug: "beauty-cia", fim: "2026-10-01T10:00" });
  assert.deepEqual(lerReservas(armazenamento, "beauty-cia", "2026-10-26T12:00").map((r) => r.codigo), ["a"]);
  esquecerReserva(armazenamento, "a");
  assert.deepEqual(lerReservas(armazenamento, "beauty-cia", "2026-10-26T12:00"), []);

  const quebrado = { getItem: () => { throw new Error("bloqueado"); }, setItem: () => { throw new Error("cheio"); } };
  assert.deepEqual(lerReservas(quebrado, "x", "2026"), [], "aba anonima nao quebra a pagina");
  guardarReserva(quebrado, { codigo: "z" });
});
