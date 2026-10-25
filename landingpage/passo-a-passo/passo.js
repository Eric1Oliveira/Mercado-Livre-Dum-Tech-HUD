// Passo a passo: catalogo de videos com busca pela duvida.
//
// Peso: a pagina carrega so o texto e as capas que aparecem na tela (cada uma ~25 KB, sob demanda).
// O video so baixa quando alguem da play (preload="none"). Nada vai ao banco nem ao Supabase.
// Enderecos que se pode mandar para alguem: ?q=como cadastro produtos  ou  #cadastrar-produto

import { VIDEOS } from "./catalogo.js";
import { buscar, indexar } from "./busca.js";

const ONLINE = "https://dumtechsolution.com/videos/";   // a copia que vem no programa nao leva os videos
const GRUPOS = ["Primeiros passos", "Estoque", "Vendas", "Financeiro", "Ordem de Serviço", "Orçamentos", "Clientes",
  "Agenda", "Configurações", "Este catálogo"];
const SUGESTOES = ["como cadastro produtos", "como fazer uma venda", "como fechar o caixa", "como dar baixa numa conta",
  "como abrir uma ordem de serviço", "como fazer backup"];
const PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z"/></svg>';

const $ = s => document.querySelector(s);
const indices = VIDEOS.map(indexar);
const porId = new Map(VIDEOS.map(v => [v.id, v]));
let grupo = "";
let atual = null;

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat()) if (f != null && f !== false) e.append(f instanceof Node ? f : document.createTextNode(String(f)));
  return e;
}
const tempo = s => { const t = Math.max(0, Math.round(s)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; };
const arquivo = (v, ext) => `../videos/${v.id}.${ext}`;

function comReserva(midia, v, ext) {                     // sem o arquivo aqui? busca no site publicado
  midia.addEventListener("error", () => {
    if (midia.dataset.online) return;
    midia.dataset.online = "1";
    midia.src = ONLINE + v.id + "." + ext;
    if (midia.tagName === "VIDEO") midia.play().catch(() => {});
  });
}

/* ------------------------------------------------------------------ cartoes */
function cartao(v) {
  const img = el("img", { src: arquivo(v, "jpg"), alt: "", loading: "lazy", decoding: "async", width: 640, height: 360 });
  comReserva(img, v, "jpg");
  return el("a", { class: "cartao-video", href: `#${v.id}`, "data-id": v.id,
    onclick: e => { e.preventDefault(); abrir(v, { tocar: true }); } },
    el("span", { class: "capa" }, img, el("span", { class: "tempo" }, tempo(v.duracao)), el("span", { class: "play", html: PLAY })),
    el("span", { class: "grupo" }, v.grupo),
    el("strong", {}, v.titulo),
    el("span", { class: "resumo" }, v.resumo));
}

/* ------------------------------------------------------------------ o video aberto */
function abrir(v, { tocar = false, nota = "", rolar = true } = {}) {
  atual = v;
  const video = $("#video");
  delete video.dataset.online;
  video.poster = arquivo(v, "jpg");
  video.src = arquivo(v, "mp4");
  $("#destaque").hidden = false;
  $("#destaque-nota").textContent = nota;
  $("#destaque-nota").hidden = !nota;
  $("#video-grupo").textContent = v.grupo;
  $("#video-titulo").textContent = v.titulo;
  $("#video-resumo").textContent = v.resumo;
  $("#video-duracao").textContent = `${tempo(v.duracao)} · ${v.passos.length} passos`;
  const lista = $("#lista-passos");
  lista.replaceChildren(...v.passos.map((p, i) => el("li", {},
    el("button", { type: "button", "data-i": i, onclick: () => { video.currentTime = p.t; video.play().catch(() => {}); } },
      el("span", { class: "t" }, tempo(p.t)), el("span", { class: "x" }, p.texto)))));
  history.replaceState(null, "", `${location.pathname}${location.search}#${v.id}`);
  document.title = `${v.titulo} — Passo a passo do DumTech Hub`;
  for (const c of document.querySelectorAll(".cartao-video")) c.classList.toggle("aberto", c.dataset.id === v.id);
  if (rolar) $("#destaque").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  if (tocar) video.play().catch(() => {});
}

function passoAtual() {                                   // o passo que esta passando fica marcado
  if (!atual) return;
  const t = $("#video").currentTime;
  let i = 0;
  while (i + 1 < atual.passos.length && atual.passos[i + 1].t <= t + 0.05) i++;
  for (const b of document.querySelectorAll("#lista-passos button")) b.classList.toggle("agora", Number(b.dataset.i) === i && t >= atual.passos[0]?.t - 0.05);
}

/* ------------------------------------------------------------------ catalogo e busca */
function filtros() {
  const presentes = new Set(VIDEOS.map(v => v.grupo));
  const nav = $("#filtros");
  nav.replaceChildren(...["", ...GRUPOS.filter(g => presentes.has(g))].map(g =>
    el("button", { type: "button", class: g === grupo ? "on" : "", "aria-pressed": String(g === grupo),
      onclick: () => { grupo = g; filtros(); renderizar(false); } }, g || "Todos")));
}

function renderizar(abrirMelhor = true) {
  const consulta = $("#busca").value.trim();
  const url = new URL(location.href);
  if (consulta) url.searchParams.set("q", consulta); else url.searchParams.delete("q");
  history.replaceState(null, "", url.pathname + url.search + url.hash);

  let lista, titulo;
  if (consulta) {
    const { resultados, exato } = buscar(indices, consulta);
    lista = resultados.map(r => r.video).filter(v => !grupo || v.grupo === grupo);
    titulo = lista.length ? `Vídeos para “${consulta}”` : "";
    if (abrirMelhor && lista[0]) {
      abrir(lista[0], { nota: exato ? `Este é o vídeo para “${consulta}”:` : `O que mais se parece com “${consulta}”:`, rolar: false });
    }
  } else {
    lista = VIDEOS.filter(v => !grupo || v.grupo === grupo);
    titulo = grupo || "Todos os vídeos";
  }
  $("#catalogo-titulo").textContent = titulo;
  $("#grade").replaceChildren(...lista.map(cartao));
  $("#vazio").hidden = lista.length > 0;
  for (const c of document.querySelectorAll(".cartao-video")) c.classList.toggle("aberto", c.dataset.id === atual?.id);
}

function iniciar() {
  $("#sugestoes").replaceChildren(...SUGESTOES.map(s => el("button", { type: "button", class: "sugestao",
    onclick: () => { $("#busca").value = s; renderizar(); $("#busca").focus(); } }, s)));
  filtros();
  const busca = $("#busca");
  let espera;
  busca.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(renderizar, 140); });
  $("#busca-form").addEventListener("submit", e => {          // Enter: toca o melhor resultado
    e.preventDefault(); clearTimeout(espera); renderizar();
    if (atual && busca.value.trim()) abrir(atual, { tocar: true, nota: $("#destaque-nota").textContent });
  });
  document.addEventListener("keydown", e => {
    if (e.key === "/" && !e.target.closest("input, textarea")) { e.preventDefault(); busca.focus(); }
  });
  const video = $("#video");
  video.addEventListener("error", () => {
    if (!atual || video.dataset.online) return;
    video.dataset.online = "1";
    video.src = ONLINE + atual.id + ".mp4";
    video.play().catch(() => {});
  });
  video.addEventListener("timeupdate", passoAtual);
  video.addEventListener("seeked", passoAtual);
  $("#copiar-link").addEventListener("click", async e => {
    const link = `${location.origin}${location.pathname}#${atual?.id || ""}`;
    try { await navigator.clipboard.writeText(link); e.target.textContent = "Link copiado"; }
    catch { e.target.textContent = link; }
    setTimeout(() => { e.target.textContent = "Copiar link deste vídeo"; }, 2200);
  });

  const params = new URLSearchParams(location.search);
  if (params.get("q")) busca.value = params.get("q");
  const pedido = porId.get(location.hash.slice(1));      // lido antes: abrir() troca o # do endereco
  renderizar(!pedido);
  if (pedido) abrir(pedido, { rolar: true });
  else if (!busca.value) abrir(porId.get("primeiros-passos") || VIDEOS[0], { nota: "Comece por aqui:", rolar: false });
}

iniciar();
