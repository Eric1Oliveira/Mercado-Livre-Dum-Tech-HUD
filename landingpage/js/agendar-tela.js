// A pagina de agendamento: desenha o que o servidor manda e marca o horario.
//
// Tudo que vem do servidor entra como TEXTO (textContent / createElement):
// nome de empresa, servico ou recado nunca viram HTML nesta pagina.

import { CONFIG } from "./config.js";
import * as A from "./agendar.js";

const $ = (id) => document.getElementById(id);
const reduzido = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const estado = {
  slug: "",
  pagina: null,
  servico: null,
  dias: [],
  dia: "",
  hora: "",
  enviando: false,
  formularioVisto: false,
};

// ----------------------------------------------------------------- servidor --
async function rpc(funcao, params = {}) {
  const resposta = await fetch(`${CONFIG.SUPABASE_URL}/rpc/${funcao}`, {
    method: "POST",
    headers: {
      apikey: CONFIG.SUPABASE_ANON,
      Authorization: `Bearer ${CONFIG.SUPABASE_ANON}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(params),
  });
  if (!resposta.ok) throw new Error(`${funcao}: HTTP ${resposta.status}`);
  return resposta.json();
}

// -------------------------------------------------------------------- apoio --
function el(tag, classe, texto) {
  const elemento = document.createElement(tag);
  if (classe) elemento.className = classe;
  if (texto !== undefined && texto !== null) elemento.textContent = texto;
  return elemento;
}

function botao(texto, classe, aoClicar) {
  const b = el("button", classe, texto);
  b.type = "button";
  if (aoClicar) b.addEventListener("click", aoClicar);
  return b;
}

const ICONES = {
  check: "M5 12.5 10 17.5 19.5 7",
  calendario: "M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M4 10h16 M8.5 3v4 M15.5 3v4",
  conversa: "M5 5h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H9.5L5 19.5V6a1 1 0 0 1 1-1z",
};

function icone(nome) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2.2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  const caminho = document.createElementNS("http://www.w3.org/2000/svg", "path");
  caminho.setAttribute("d", ICONES[nome]);
  svg.append(caminho);
  return svg;
}

function linkBotao(texto, href, classe, nomeIcone) {
  const a = el("a", classe);
  if (nomeIcone) a.append(icone(nomeIcone));
  a.append(document.createTextNode(texto));
  a.href = href;
  a.rel = "noopener";
  return a;
}

/** Mistura duas cores #rrggbb: `t` = quanto de `b` entra. */
function misturar(a, b, t) {
  const canal = (cor, i) => parseInt(cor.slice(1 + i * 2, 3 + i * 2), 16);
  const hex = [0, 1, 2].map((i) => Math.round(canal(a, i) * (1 - t) + canal(b, i) * t)
    .toString(16).padStart(2, "0"));
  return `#${hex.join("")}`;
}

/** A cor da empresa, com as variacoes de fundo e de texto para claro e escuro. */
function aplicarCor(chave) {
  const cor = A.CORES[chave] || A.CORES.violeta;
  const escuro = matchMedia("(prefers-color-scheme: dark)").matches;
  const raiz = document.documentElement.style;
  raiz.setProperty("--destaque", cor);
  raiz.setProperty("--destaque-suave", escuro ? misturar(cor, "#1c1b1f", 0.76) : misturar(cor, "#ffffff", 0.9));
  raiz.setProperty("--destaque-texto", escuro ? misturar(cor, "#ffffff", 0.45) : cor);
}

function erro(texto) {
  const caixa = $("erro");
  caixa.textContent = texto || "";
  caixa.hidden = !texto;
}

function lembrarCliente(nome, telefone) {
  try {
    localStorage.setItem("dumtech.agenda.cliente", JSON.stringify({ nome, telefone }));
  } catch {
    // aba anonima: na proxima vez a pessoa digita de novo
  }
}

function clienteLembrado() {
  try {
    return JSON.parse(localStorage.getItem("dumtech.agenda.cliente") || "{}") || {};
  } catch {
    return {};
  }
}

function armazenamento() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function agoraNaLoja() {
  // a hora da loja veio do servidor ao abrir; serve para esconder o que ja passou
  return estado.pagina?.agora || new Date().toISOString().slice(0, 16);
}

// ------------------------------------------------------------------ a empresa --
function pintarEmpresa(empresa = {}) {
  const nome = empresa.nome || "Agenda";
  $("empresa").textContent = nome;
  document.title = `Agendar · ${nome}`;
  const marca = $("marca");
  marca.replaceChildren();
  const logo = A.logoSeguro(empresa.logo);
  if (logo) {
    const imagem = el("img");
    imagem.src = logo;
    imagem.alt = "";
    marca.append(imagem);
    marca.classList.add("com-logo");
  } else {
    marca.textContent = A.iniciais(nome);
  }
  if (empresa.endereco) {
    $("endereco").textContent = empresa.endereco;
    $("endereco").hidden = false;
  }
}

function mostrarAviso(titulo, texto, whatsapp = "", tentar = null) {
  $("carregando").hidden = true;
  $("fluxo").hidden = true;
  $("barra").hidden = true;
  const caixa = $("parado");
  caixa.replaceChildren(el("h2", null, titulo), el("p", null, texto));
  const link = A.linkWhatsApp(whatsapp, "Olá! Quero marcar um horário.");
  if (link) caixa.append(linkBotao("Chamar no WhatsApp", link, "botao botao-cheio", "conversa"));
  if (tentar) caixa.append(botao("Tentar de novo", "botao", tentar));
  caixa.hidden = false;
}

// ---------------------------------------------------------------- as etapas --
function numerarEtapas() {
  let numero = 0;
  for (const etapa of document.querySelectorAll(".etapa")) {
    if (etapa.hidden) continue;
    numero += 1;
    const marcador = etapa.querySelector(".numero");
    if (marcador) marcador.textContent = String(numero);
  }
}

function marcarEscolha(caixa, seletor, escolhido) {
  for (const item of caixa.querySelectorAll(seletor)) {
    item.setAttribute("aria-checked", String(item === escolhido));
  }
}

function pintarServicos() {
  const lista = $("servicos");
  lista.replaceChildren();
  for (const servico of estado.pagina.servicos) {
    const item = botao("", "servico", () => escolherServico(servico, item));
    item.setAttribute("role", "radio");
    item.setAttribute("aria-checked", "false");
    const textos = el("span", "servico-textos");
    textos.append(el("span", "servico-nome", servico.nome), el("span", "servico-tempo", A.duracaoTexto(servico.duracao)));
    item.append(el("span", "marcador"), textos);
    const preco = A.precoTexto(servico.preco);
    if (preco) item.append(el("span", "servico-preco", preco));
    lista.append(item);
  }
}

async function escolherServico(servico, item) {
  estado.servico = servico;
  estado.dia = "";
  estado.hora = "";
  if (item) marcarEscolha($("servicos"), ".servico", item);
  $("etapa-dia").hidden = false;
  $("etapa-hora").hidden = true;
  $("etapa-dados").hidden = true;
  const dias = $("dias");
  dias.replaceChildren(pontos());
  numerarEtapas();
  atualizarResumo();
  erro("");
  await buscarHorarios();
}

function pontos() {
  const caixa = el("div", "carregando");
  caixa.append(el("span", "ponto"), el("span", "ponto"), el("span", "ponto"));
  return caixa;
}

async function buscarHorarios(manterDia = "") {
  let resposta;
  try {
    resposta = await rpc("dumtech_agenda_horarios", { p_slug: estado.slug, p_servico: estado.servico.id });
  } catch {
    $("dias").replaceChildren(semConexao(() => buscarHorarios(manterDia)));
    return;
  }
  if (!resposta?.ok) {
    if (resposta?.erro === "indisponivel") {
      mostrarAviso("Agenda pausada", "A agenda online foi pausada agora há pouco.", resposta.empresa?.whatsapp);
    } else {
      $("dias").replaceChildren(el("p", "vazio", resposta?.mensagem || "Não foi possível carregar os horários."));
    }
    return;
  }
  estado.dias = resposta.dias || [];
  pintarDias();
  const livre = estado.dias.find((d) => d.data === manterDia && d.horarios.length)
    || estado.dias.find((d) => d.horarios.length);
  if (!livre) {
    const vazio = el("p", "vazio", `Nenhum horário livre nos próximos ${estado.dias.length} dias.`);
    const link = A.linkWhatsApp(estado.pagina.empresa?.whatsapp, "Olá! Quero marcar um horário.");
    if (link) vazio.append(linkBotao("Chamar no WhatsApp", link, "botao", "conversa"));
    $("dias").replaceChildren(vazio);
    return;
  }
  escolherDia(livre.data, manterDia === livre.data ? estado.hora : "");
}

function semConexao(tentar) {
  const caixa = el("p", "vazio", "Sem conexão agora. Confira a internet e tente de novo.");
  const b = botao("Tentar de novo", "botao", tentar);
  caixa.append(document.createElement("br"), b);
  return caixa;
}

function pintarDias() {
  const caixa = $("dias");
  caixa.replaceChildren();
  for (const dia of estado.dias) {
    const rotulo = A.rotuloDoDia(dia.data, estado.pagina.hoje);
    const item = botao("", "dia", () => escolherDia(dia.data));
    item.dataset.data = dia.data;
    item.setAttribute("role", "radio");
    item.setAttribute("aria-checked", "false");
    const quantos = dia.horarios.length;
    item.setAttribute("aria-label", `${A.dataPorExtenso(dia.data)}: ${quantos ? `${quantos} horários livres` : "sem horário livre"}`);
    item.append(el("span", "dia-semana", rotulo.semana), el("span", "dia-numero", rotulo.dia), el("span", "dia-mes", rotulo.mes));
    item.disabled = !quantos;
    caixa.append(item);
  }
}

function escolherDia(data, manterHora = "") {
  estado.dia = data;
  estado.hora = "";
  const caixa = $("dias");
  const item = caixa.querySelector(`[data-data="${data}"]`);
  marcarEscolha(caixa, ".dia", item);
  item?.scrollIntoView({ behavior: reduzido() ? "auto" : "smooth", block: "nearest", inline: "nearest" });
  $("dia-escolhido").textContent = A.dataPorExtenso(data);
  $("etapa-hora").hidden = false;
  pintarHorarios();
  numerarEtapas();
  atualizarResumo();
  if (manterHora) {
    const botaoHora = [...$("horarios").querySelectorAll(".hora")].find((b) => b.textContent === manterHora);
    if (botaoHora) escolherHora(manterHora, botaoHora);
  }
}

function pintarHorarios() {
  const dia = estado.dias.find((d) => d.data === estado.dia);
  const caixa = $("horarios");
  caixa.replaceChildren();
  const grupos = A.agruparPorPeriodo(dia?.horarios || []);
  if (!grupos.length) {
    caixa.append(el("p", "vazio", "Nenhum horário livre neste dia."));
    return;
  }
  for (const grupo of grupos) {
    const bloco = el("div", "periodo");
    const grade = el("div", "horas");
    grade.setAttribute("role", "radiogroup");
    grade.setAttribute("aria-label", grupo.nome);
    for (const hora of grupo.horarios) {
      const item = botao(hora, "hora", () => escolherHora(hora, item));
      item.setAttribute("role", "radio");
      item.setAttribute("aria-checked", "false");
      grade.append(item);
    }
    bloco.append(el("p", "periodo-nome", grupo.nome), grade);
    caixa.append(bloco);
  }
}

function escolherHora(hora, item) {
  estado.hora = hora;
  marcarEscolha($("horarios"), ".hora", item);
  const dados = $("etapa-dados");
  const primeiraVez = dados.hidden;
  dados.hidden = false;
  numerarEtapas();
  atualizarResumo();
  erro("");
  if (primeiraVez && !estado.formularioVisto) {
    estado.formularioVisto = true;
    dados.scrollIntoView({ behavior: reduzido() ? "auto" : "smooth", block: "start" });
  }
}

function atualizarResumo() {
  const resumo = $("resumo");
  resumo.replaceChildren();
  if (!estado.servico) {
    resumo.textContent = "Escolha o serviço";
  } else if (!estado.dia || !estado.hora) {
    resumo.append(el("strong", null, estado.servico.nome), document.createTextNode(estado.dia ? "Escolha o horário" : "Escolha o dia"));
  } else {
    resumo.append(
      el("strong", null, `${A.dataCurta(estado.dia)} · ${estado.hora}`),
      document.createTextNode(`${estado.servico.nome} · ${A.duracaoTexto(estado.servico.duracao)}`),
    );
  }
  $("confirmar").disabled = !(estado.servico && estado.dia && estado.hora) || estado.enviando;
}

// ------------------------------------------------------------------- marcar --
async function confirmar(evento) {
  evento.preventDefault();
  if (estado.enviando || !estado.hora) return;
  erro("");
  const nome = $("nome");
  const telefone = $("telefone");
  nome.removeAttribute("aria-invalid");
  telefone.removeAttribute("aria-invalid");
  if (nome.value.trim().length < 2) {
    nome.setAttribute("aria-invalid", "true");
    nome.focus();
    erro("Digite o seu nome.");
    return;
  }
  if (!A.telefoneValido(telefone.value)) {
    telefone.setAttribute("aria-invalid", "true");
    telefone.focus();
    erro("Digite o seu WhatsApp com DDD.");
    return;
  }

  estado.enviando = true;
  const botaoConfirmar = $("confirmar");
  botaoConfirmar.textContent = "Marcando…";
  atualizarResumo();
  try {
    const resposta = await rpc("dumtech_agenda_reservar", {
      p_slug: estado.slug,
      p_servico: estado.servico.id,
      p_inicio: `${estado.dia}T${estado.hora}`,
      p_nome: nome.value.trim(),
      p_telefone: telefone.value,
      p_observacao: $("observacao").value.trim(),
      p_armadilha: $("site").value,
    });
    if (resposta?.ok) {
      lembrarCliente(nome.value.trim(), telefone.value);
      const reserva = {
        codigo: resposta.codigo,
        slug: estado.slug,
        servico: resposta.servico,
        inicio: resposta.inicio,
        fim: resposta.fim,
        cancelar_ate: resposta.cancelar_ate,
        nome: nome.value.trim(),
      };
      A.guardarReserva(armazenamento(), reserva);
      mostrarBilhete(reserva, resposta.empresa || estado.pagina.empresa);
    } else if (resposta?.erro === "ocupado") {
      erro(resposta.mensagem || "Esse horário acabou de ser ocupado. Escolha outro.");
      await buscarHorarios(estado.dia);
    } else if (resposta?.erro === "indisponivel") {
      mostrarAviso("Agenda pausada", "A agenda online foi pausada agora há pouco.", resposta.empresa?.whatsapp);
    } else {
      erro(resposta?.mensagem || "Não foi possível marcar agora. Tente de novo.");
    }
  } catch {
    erro("Sem conexão agora. Confira a internet e tente de novo.");
  } finally {
    estado.enviando = false;
    botaoConfirmar.textContent = "Confirmar";
    atualizarResumo();
  }
}

// ---------------------------------------------- o cartão de horário (assinatura) --
function bilhete(reserva, empresa, cancelado = false) {
  const data = reserva.inicio.slice(0, 10);
  const cartao = el("article", `bilhete${cancelado ? " cancelado" : ""}`);
  const cabeca = el("div", "bilhete-cabeca");
  cabeca.append(icone("check"), document.createTextNode(cancelado ? "Horário cancelado" : "Horário marcado"));

  const corpo = el("div", "bilhete-corpo");
  const legenda = el("div");
  legenda.append(el("div", "bilhete-mes", A.nomeDoMes(data)), el("div", "bilhete-semana", A.nomeDoDia(data)));
  corpo.append(
    el("div", "bilhete-dia", String(A.lerData(data).dia)),
    legenda,
    el("div", "bilhete-hora", `${A.horaDe(reserva.inicio)} – ${A.horaDe(reserva.fim)}`),
    el("div", "bilhete-servico", [reserva.servico, reserva.nome].filter(Boolean).join(" · ")),
  );

  const canhoto = el("div", "bilhete-canhoto");
  canhoto.append(el("strong", null, empresa?.nome || estado.pagina?.empresa?.nome || ""));
  if (empresa?.endereco) canhoto.append(el("span", null, empresa.endereco));
  if (!cancelado && reserva.cancelar_ate && reserva.cancelar_ate > agoraNaLoja()) {
    canhoto.append(el("span", null,
      `Precisa desmarcar? Dá para cancelar por aqui até ${A.dataCurta(reserva.cancelar_ate.slice(0, 10))}, ${A.horaDe(reserva.cancelar_ate)}.`));
  }
  cartao.append(cabeca, corpo, el("div", "bilhete-picote"), canhoto);
  return cartao;
}

function mostrarBilhete(reserva, empresa) {
  $("fluxo").hidden = true;
  $("barra").hidden = true;
  $("marcados").hidden = true;
  const feito = $("feito");
  feito.replaceChildren(bilhete(reserva, empresa));

  const acoes = el("div", "acoes");
  const arquivo = new Blob([A.arquivoIcs({
    uid: reserva.codigo.slice(0, 16),
    titulo: `${reserva.servico} · ${empresa?.nome || ""}`.trim(),
    inicio: reserva.inicio,
    fim: reserva.fim,
    local: empresa?.endereco || "",
  })], { type: "text/calendar;charset=utf-8" });
  const calendario = linkBotao("Adicionar ao calendário", URL.createObjectURL(arquivo), "botao botao-cheio", "calendario");
  calendario.download = "agendamento.ics";
  acoes.append(calendario);
  const whatsapp = A.linkWhatsApp(empresa?.whatsapp,
    `Olá! Marquei ${reserva.servico} para ${A.dataCurta(reserva.inicio.slice(0, 10))} às ${A.horaDe(reserva.inicio)} pelo link.`);
  if (whatsapp) acoes.append(linkBotao("Falar no WhatsApp", whatsapp, "botao", "conversa"));

  const linha = el("div", "acoes-linha");
  linha.append(botao("Marcar outro horário", "botao-texto", recomecar));
  if (reserva.cancelar_ate > agoraNaLoja()) {
    linha.append(botao("Cancelar agendamento", "botao-texto botao-perigo", () => cancelar(reserva, true)));
  }
  acoes.append(linha);
  feito.append(acoes);
  feito.hidden = false;
  window.scrollTo({ top: 0, behavior: reduzido() ? "auto" : "smooth" });
}

function recomecar() {
  $("feito").hidden = true;
  $("fluxo").hidden = false;
  $("barra").hidden = false;
  $("observacao").value = "";
  pintarMarcados();
  if (estado.servico) buscarHorarios(estado.dia);
}

// ---------------------------------------------------- os horarios deste celular --
function pintarMarcados() {
  const caixa = $("marcados");
  caixa.replaceChildren();
  const reservas = A.lerReservas(armazenamento(), estado.slug, agoraNaLoja());
  for (const reserva of reservas) {
    const item = el("div", "marcado");
    const textos = el("div", "marcado-texto");
    textos.append(
      el("strong", null, `${A.dataCurta(reserva.inicio.slice(0, 10))} · ${A.horaDe(reserva.inicio)}`),
      document.createTextNode(`Você marcou ${reserva.servico}`),
    );
    item.append(textos);
    if (reserva.cancelar_ate > agoraNaLoja()) {
      item.append(botao("Cancelar", "botao-texto botao-perigo", () => cancelar(reserva, false)));
    }
    caixa.append(item);
  }
  caixa.hidden = !reservas.length;
}

async function cancelar(reserva, noBilhete) {
  const quando = `${A.dataCurta(reserva.inicio.slice(0, 10))} às ${A.horaDe(reserva.inicio)}`;
  if (!window.confirm(`Cancelar o horário de ${quando}?`)) return;
  let resposta;
  try {
    resposta = await rpc("dumtech_agenda_cancelar", { p_codigo: reserva.codigo });
  } catch {
    window.alert("Sem conexão agora. Confira a internet e tente de novo.");
    return;
  }
  if (resposta?.ok || resposta?.erro === "nao_encontrado") {
    A.esquecerReserva(armazenamento(), reserva.codigo);
    if (noBilhete) {
      const feito = $("feito");
      feito.replaceChildren(bilhete(reserva, estado.pagina?.empresa, true),
        el("p", "recado-curto", "Pronto, o horário ficou livre de novo."));
      const linha = el("div", "acoes");
      linha.append(botao("Marcar outro horário", "botao botao-cheio", recomecar));
      feito.append(linha);
    } else {
      pintarMarcados();
    }
    if (estado.servico && !noBilhete) buscarHorarios(estado.dia);
    return;
  }
  window.alert(resposta?.mensagem || "Não foi possível cancelar agora.");
}

// -------------------------------------------------------------------- inicio --
async function iniciar() {
  $("parado").hidden = true;
  $("carregando").hidden = false;
  estado.slug = A.slugDaUrl(location.href);
  if (!estado.slug) {
    mostrarAviso("Link incompleto", "Este endereço não leva a nenhuma agenda. Confira o link com quem te mandou.");
    return;
  }
  let pagina;
  try {
    pagina = await rpc("dumtech_agenda_pagina", { p_slug: estado.slug });
  } catch {
    mostrarAviso("Sem conexão", "Não foi possível abrir a agenda agora. Confira a internet.", "", iniciar);
    return;
  }
  if (!pagina?.ok) {
    if (pagina?.erro === "indisponivel") {
      pintarEmpresa(pagina.empresa);
      mostrarAviso("Agenda online pausada",
        `Por enquanto, ${pagina.empresa?.nome || "a empresa"} está marcando os horários direto pelo WhatsApp.`,
        pagina.empresa?.whatsapp);
    } else if (pagina?.erro === "nao_encontrado") {
      mostrarAviso("Este link não existe", "Confira o endereço com quem te mandou. Ele pode ter mudado.");
    } else {
      mostrarAviso("Agenda indisponível agora", pagina?.mensagem || "Tente de novo em alguns minutos.", "", iniciar);
    }
    return;
  }

  estado.pagina = pagina;
  aplicarCor(pagina.cor);
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => aplicarCor(pagina.cor));
  pintarEmpresa(pagina.empresa);
  if (pagina.mensagem) {
    $("recado").textContent = pagina.mensagem;
    $("recado").hidden = false;
  }
  $("privacidade").textContent =
    `Seu nome e WhatsApp vão só para ${pagina.empresa?.nome || "a empresa"}, para confirmar o horário.`;
  const lembrado = clienteLembrado();
  if (lembrado.nome) $("nome").value = lembrado.nome;
  if (lembrado.telefone) $("telefone").value = A.mascaraTelefone(lembrado.telefone);

  $("carregando").hidden = true;
  pintarMarcados();
  pintarServicos();
  $("fluxo").hidden = false;
  $("barra").hidden = false;
  atualizarResumo();

  const servicos = pagina.servicos || [];
  if (servicos.length === 1) {
    // um servico so: nao ha o que escolher, o primeiro passo some
    $("etapa-servico").hidden = true;
    escolherServico(servicos[0], $("servicos").querySelector(".servico"));
  }
  numerarEtapas();
}

$("fluxo").addEventListener("submit", confirmar);
$("telefone").addEventListener("input", (evento) => {
  const campo = evento.target;
  const formatado = A.mascaraTelefone(campo.value);
  if (formatado !== campo.value) campo.value = formatado;
});
iniciar();
