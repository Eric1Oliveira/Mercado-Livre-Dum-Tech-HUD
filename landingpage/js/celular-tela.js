// O Hub no celular — a tela. A conta mora em celular.js.
//
// CAMINHO
//   1. Chegou do QR (#p=codigo): troca o codigo por um acesso proprio, guarda
//      neste aparelho e limpa o endereco (o codigo nao fica no historico).
//   2. Com acesso: ABRE JA COM OS ULTIMOS NUMEROS guardados no aparelho e vai
//      buscar os novos no mesmo instante. Depois le a cada 12 s com a tela
//      aberta, e na hora em que o dono volta para o aplicativo (voltar da
//      bandeja, trocar de aba, a internet voltar). A licenca vem junto.
//   3. Sem acesso: explica como conectar.
//
// Tudo que vem do servidor entra na pagina como TEXTO (textContent), nunca
// como HTML: o resumo e escrito pelo computador da loja.

import { CONFIG } from "./config.js";
import {
  ERROS, codigoDoEndereco, destaqueDaTela, estaAntigo, haQuanto, linkDaLoja, moduloDoCodigo,
  montarTela, nomeDoAparelho,
} from "./celular.js";

const CHAVE = "dumtech.celular.acesso";
const CHAVE_PC = "dumtech.celular.computador";
//: o ultimo resumo que chegou, para a tela abrir cheia em vez de vazia
const CHAVE_CACHE = "dumtech.celular.ultimo";
//: resumo guardado maior que isto nao cabe no aparelho - abre sem cache
const CACHE_MAXIMO = 400000;
//: de quanto em quanto tempo le, com a tela na frente do dono
const INTERVALO_MS = 12000;
//: duas leituras coladas (voltar da bandeja logo depois de abrir) viram uma
const DESCANSO_MS = 1500;
//: o "atualizado ha" anda sozinho entre uma leitura e outra
const RELOGIO_TEXTO_MS = 10000;
//: rede movel nao avisa quando desiste - o fetch pendura calado por minutos
const TEMPO_LIMITE_MS = 10000;

const $ = (id) => document.getElementById(id);
const tela = $("tela");
const barra = $("barra");
const navModulos = $("modulos");
const trilha = $("modulos-trilha");
const marca = $("modulos-marca");
let dados = null;
let relogio = 0;
let lendo = false;
let ultimaLeitura = 0;
//: a impressao digital do ultimo resumo desenhado - igual, nao redesenha
let assinatura = "";
//: a animacao de entrada e da primeira vez; releitura nao pode piscar
let jaEntrou = false;

// ------------------------------------------------------------- guardar ---
function guardado(chave) {
  try { return localStorage.getItem(chave) || ""; } catch { return ""; }
}
function guardar(chave, valor) {
  try {
    if (valor === null) localStorage.removeItem(chave);
    else localStorage.setItem(chave, valor);
  } catch { /* aba anonima ou memoria cheia: vale ate fechar */ }
}
let acessoEmMemoria = "";
const acesso = () => guardado(CHAVE) || acessoEmMemoria;

/** A impressao digital do resumo: muda quando ha algo novo para desenhar. */
function assinar(resposta) {
  try {
    return JSON.stringify({ m: resposta?.modulos, e: resposta?.espelhos });
  } catch {
    return String(Math.random()); // nao deu para comparar: desenha
  }
}

/** O ultimo resumo que chegou, para a proxima abertura nao comecar do zero. */
function lerCache() {
  const bruto = guardado(CHAVE_CACHE);
  if (!bruto) return null;
  try {
    const salvo = JSON.parse(bruto);
    return salvo && salvo.ok ? salvo : null;
  } catch { return null; }
}
function salvarCache(resposta) {
  const bruto = JSON.stringify(resposta);
  guardar(CHAVE_CACHE, bruto.length > CACHE_MAXIMO ? null : bruto);
}

// ---------------------------------------------------------------- rede ---
/** Um prazo para a chamada. Sem isto o `fetch` espera para sempre. */
function prazoDe(ms) {
  if (typeof AbortSignal !== "undefined" && AbortSignal.timeout) {
    return { signal: AbortSignal.timeout(ms), limpar() {} };
  }
  if (typeof AbortController !== "function") return { signal: undefined, limpar() {} };
  const controle = new AbortController();
  const id = setTimeout(() => controle.abort(), ms);
  return { signal: controle.signal, limpar: () => clearTimeout(id) };
}

/**
 * Uma chamada ao servidor que SEMPRE devolve um objeto - nunca levanta.
 *
 * Quem chama trata o erro pelo campo `erro`; uma excecao solta aqui escaparia
 * de `ler()` e deixaria a trava `lendo` ligada para sempre, e a partir dai o
 * celular nunca mais buscaria nada sem recarregar a pagina.
 */
async function rpc(funcao, params) {
  const prazo = prazoDe(TEMPO_LIMITE_MS);
  try {
    const resposta = await fetch(`${CONFIG.SUPABASE_URL}/rpc/${funcao}`, {
      method: "POST",
      headers: {
        apikey: CONFIG.SUPABASE_ANON,
        Authorization: `Bearer ${CONFIG.SUPABASE_ANON}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(params),
      cache: "no-store",
      signal: prazo.signal,
    });
    if (!resposta.ok) return { ok: false, erro: "sem_internet" };
    // um 200 que nao e JSON (portal de wi-fi, pagina de erro de proxy) faz
    // json() rejeitar - aqui isso vira "sem internet", como qualquer outra
    // conversa que nao deu certo
    return await resposta.json();
  } catch {
    return { ok: false, erro: "sem_internet" };
  } finally {
    prazo.limpar();
  }
}

// ------------------------------------------------------------- desenho ---
function el(tag, classe, texto) {
  const no = document.createElement(tag);
  if (classe) no.className = classe;
  if (texto !== undefined && texto !== null && texto !== "") no.textContent = texto;
  return no;
}

function icone(caminho, cor) {
  const selo = el("span", "sec-icone");
  if (cor) selo.style.setProperty("--cor", cor);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", caminho);
  svg.append(path);
  selo.append(svg);
  return selo;
}

function estado({ titulo, texto, passos = false, botao = "", acao = null, tom = "" }) {
  pararRelogio();
  montarModulos([]);
  const copia = $("modelo-estado").content.cloneNode(true);
  const secao = copia.querySelector(".estado");
  if (tom) secao.dataset.tom = tom;
  copia.querySelector("h1").textContent = titulo;
  copia.querySelector("p").textContent = texto;
  copia.querySelector(".passos").hidden = !passos;
  const b = copia.querySelector("button");
  if (botao && acao) {
    b.hidden = false;
    b.textContent = botao;
    b.addEventListener("click", acao);
  }
  tela.replaceChildren(copia);
  tela.setAttribute("aria-busy", "false");
  $("recarregar").hidden = true;
  marcarQuando("", "mudo");
}

/** O numero do dia: grande, sem moldura, o assunto da tela. */
function destaque(c) {
  const no = el("section", "destaque");
  if (c.tom) no.dataset.tom = c.tom;
  no.append(el("span", "destaque-rotulo", c.rotulo), el("strong", "destaque-valor", c.valor));
  if (c.detalhe) no.append(el("span", "destaque-detalhe", c.detalhe));
  return no;
}

function cartao(c) {
  const no = el("div", "cartao");
  if (c.tom) no.dataset.tom = c.tom;
  no.append(el("span", "cartao-rotulo", c.rotulo), el("strong", "cartao-valor", c.valor));
  if (c.detalhe) no.append(el("span", "cartao-detalhe", c.detalhe));
  return no;
}

function lista(l) {
  const bloco = el("div", "lista");
  bloco.append(el("h3", "lista-titulo", l.titulo));
  if (!l.linhas?.length) {
    if (!l.vazio) return null;
    bloco.append(el("p", "lista-vazia", l.vazio));
    return bloco;
  }
  const ul = el("ul");
  for (const linha of l.linhas) {
    const li = el("li");
    if (linha.tom) li.dataset.tom = linha.tom;
    const textos = el("div", "linha-textos");
    textos.append(el("span", "linha-texto", linha.texto));
    if (linha.detalhe) textos.append(el("span", "linha-detalhe", linha.detalhe));
    li.append(textos);
    if (linha.valor) li.append(el("span", "linha-valor", linha.valor));
    ul.append(li);
  }
  bloco.append(ul);
  return bloco;
}

function secao(s, modulo, pular) {
  const no = el("section", "secao");
  no.id = `sec-${String(s.app).toLowerCase()}`;
  const topo = el("header", "secao-topo");
  if (modulo) topo.append(icone(modulo.icone, modulo.cor));
  topo.append(el("h2", "", s.titulo));
  no.append(topo);
  // o cartao que virou destaque la em cima nao se repete aqui
  const cartoes = (s.cartoes ?? []).filter((c) => c !== pular);
  if (cartoes.length) {
    const grade = el("div", "cartoes");
    cartoes.forEach((c) => grade.append(cartao(c)));
    no.append(grade);
  }
  for (const l of s.listas ?? []) {
    const bloco = lista(l);
    if (bloco) no.append(bloco);
  }
  return no;
}

function desenhar() {
  const escolhido = Number(guardado(CHAVE_PC)) || 0;
  const t = montarTela(dados, escolhido);
  $("empresa").textContent = t.empresa || "Sua empresa";
  $("recarregar").hidden = false;
  document.title = t.empresa ? `${t.empresa} · DumTech` : "DumTech no celular";
  atualizarQuando(t.atualizadoEm);

  const partes = [];
  const emDestaque = t.computadores.length ? destaqueDaTela(t) : null;
  if (emDestaque) partes.push(destaque(emDestaque));

  if (t.computadores.length > 1) {
    const chips = el("div", "chips");
    chips.setAttribute("role", "tablist");
    chips.setAttribute("aria-label", "Computador");
    t.computadores.forEach((pc, i) => {
      const b = el("button", "chip", pc.nome);
      b.type = "button";
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(i === t.indice));
      b.addEventListener("click", () => { guardar(CHAVE_PC, String(i)); desenhar(); });
      chips.append(b);
    });
    partes.push(chips);
  }

  if (!t.computadores.length) {
    partes.push(aviso("O computador ainda não mandou os números",
      "Deixe o DumTech Hub aberto no computador: em até 1 minuto eles aparecem aqui."));
  } else if (estaAntigo(t.atualizadoEm)) {
    partes.push(aviso("O computador pode estar desligado",
      `Estes números são de ${haQuanto(t.atualizadoEm)}. Abra o Hub no computador para atualizar.`));
  }

  for (const s of t.secoes) {
    partes.push(secao(s, moduloDoCodigo(s.app), s === t.secoes[0] ? emDestaque : null));
  }

  // comprou agora: o celular ja sabe (a licenca vem na hora), o numero vem
  // assim que o computador mandar
  for (const m of t.aCaminho) {
    if (!t.computadores.length) break;
    const no = el("section", "secao a-caminho");
    const topo = el("header", "secao-topo");
    topo.append(icone(m.icone, m.cor), el("h2", "", m.nome));
    no.append(topo, el("p", "a-caminho-texto",
      "Liberado! Os números chegam na próxima vez que o Hub do computador enviar (em até 1 minuto com ele aberto)."));
    partes.push(no);
  }

  if (t.faltam.length) partes.push(vitrine(t.faltam));
  partes.push(rodape());

  // a entrada e da primeira vez: um numero que muda nao pode fazer a tela
  // inteira piscar de novo
  if (!jaEntrou) {
    jaEntrou = true;
    partes.forEach((no, i) => {
      no.style.setProperty("--atraso", `${Math.min(i, 7) * 45}ms`);
      no.classList.add("entra");
    });
  }

  tela.replaceChildren(...partes);
  tela.setAttribute("aria-busy", "false");
  montarModulos(t.secoes);
}

/* ===========================================================================
   OS MODULOS NA BARRA
   Acompanham a rolagem: marcam onde voce esta, deslizam o risco da cor do
   modulo e se arrastam sozinhos para a aba atual nunca ficar escondida.

   Durante a rolagem nada de layout e lido - as alturas sao medidas UMA vez,
   ao desenhar e ao girar o aparelho. Ler `getBoundingClientRect` a cada
   quadro e o que faz uma lista travar no celular.
   ========================================================================= */
let abas = [];
let abaAtiva = -1;
let alturaBarra = 60;
let quadroPedido = 0;

function medirBarra() {
  alturaBarra = Math.round(barra.getBoundingClientRect().height) || 60;
  document.documentElement.style.setProperty("--altura-barra", `${alturaBarra}px`);
}

function medirSecoes() {
  const rolagem = window.scrollY;
  for (const aba of abas) {
    const alvo = document.getElementById(aba.id);
    aba.topo = alvo ? alvo.getBoundingClientRect().top + rolagem : 0;
  }
}

function montarModulos(secoes) {
  for (const velho of [...trilha.querySelectorAll("a")]) velho.remove();
  abas = [];
  abaAtiva = -1;
  marca.dataset.ligada = "nao";
  // um modulo so nao tem para onde ir: a barra fica limpa
  navModulos.hidden = secoes.length < 2;
  if (!navModulos.hidden) {
    for (const secaoAtual of secoes) {
      const id = `sec-${String(secaoAtual.app).toLowerCase()}`;
      const modulo = moduloDoCodigo(secaoAtual.app);
      const link = el("a", "", secaoAtual.titulo);
      link.href = `#${id}`;
      if (modulo?.cor) link.style.setProperty("--cor", modulo.cor);
      trilha.insertBefore(link, marca);
      abas.push({ id, link, cor: modulo?.cor || "" });
    }
  }
  medirBarra();
  requestAnimationFrame(() => { medirSecoes(); acompanhar(); bordasDoMenu(); });
  // a animacao de entrada ainda desloca as secoes alguns pixels no primeiro
  // quadro: quando ela acaba, mede de novo e acerta a conta
  setTimeout(() => { medirSecoes(); acompanhar(); }, 700);
}

function moverMarca(aba) {
  // translate + scaleX: a GPU resolve sozinha, sem refazer conta de layout
  const largura = aba.link.offsetWidth;
  marca.style.setProperty("--cor", aba.cor);
  marca.style.transform = `translate3d(${aba.link.offsetLeft}px, 0, 0) scaleX(${largura / 100})`;
  marca.dataset.ligada = "sim";
}

function trazerAVista(link) {
  const margem = 16;
  const esquerda = link.offsetLeft - margem;
  const direita = link.offsetLeft + link.offsetWidth + margem;
  if (esquerda < navModulos.scrollLeft) {
    navModulos.scrollTo({ left: esquerda, behavior: "smooth" });
  } else if (direita > navModulos.scrollLeft + navModulos.clientWidth) {
    navModulos.scrollTo({ left: direita - navModulos.clientWidth, behavior: "smooth" });
  }
}

function trocarAba(indice) {
  abas[abaAtiva]?.link.removeAttribute("aria-current");
  abaAtiva = indice;
  const aba = abas[indice];
  if (!aba) { marca.dataset.ligada = "nao"; return; }
  aba.link.setAttribute("aria-current", "true");
  moverMarca(aba);
  trazerAVista(aba.link);
}

/** Qual modulo esta na tela agora (so contas, nenhuma leitura do layout). */
function acompanhar() {
  if (!abas.length) return;
  const linha = window.scrollY + alturaBarra + 16;
  let atual = 0;
  for (let i = 0; i < abas.length; i += 1) if (abas[i].topo <= linha) atual = i;
  // no fim da pagina o ultimo modulo pode nunca alcancar a linha
  if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) {
    atual = abas.length - 1;
  }
  if (atual !== abaAtiva) trocarAba(atual);
}

/* Um quadro, um calculo: a rolagem pode disparar 120 vezes por segundo e o
   navegador so precisa da resposta uma vez por quadro que ele vai pintar. */
function aoRolar() {
  if (quadroPedido) return;
  quadroPedido = requestAnimationFrame(() => { quadroPedido = 0; acompanhar(); });
}

/** A fita apaga na ponta enquanto houver modulo escondido para aquele lado. */
function bordasDoMenu() {
  const sobra = navModulos.scrollWidth - navModulos.clientWidth;
  if (sobra <= 2) { delete navModulos.dataset.borda; return; }
  const temEsquerda = navModulos.scrollLeft > 2;
  const temDireita = navModulos.scrollLeft < sobra - 2;
  navModulos.dataset.borda = temEsquerda && temDireita ? "ambas"
    : temEsquerda ? "esquerda" : "direita";
}

let quadroDaFita = 0;
navModulos.addEventListener("scroll", () => {
  if (quadroDaFita) return;
  quadroDaFita = requestAnimationFrame(() => { quadroDaFita = 0; bordasDoMenu(); });
}, { passive: true });

addEventListener("scroll", aoRolar, { passive: true });
addEventListener("resize", () => { medirBarra(); medirSecoes(); acompanhar(); bordasDoMenu(); });
if (typeof ResizeObserver === "function") new ResizeObserver(medirBarra).observe(barra);
medirBarra();

function aviso(titulo, texto) {
  const no = el("div", "aviso");
  const textos = el("div");
  textos.append(el("strong", "", titulo), el("span", "", texto));
  no.append(textos);
  return no;
}

function vitrine(faltam) {
  const no = el("section", "secao vitrine");
  no.append(el("h2", "vitrine-titulo", "Mais para o seu negócio"));
  const ul = el("ul");
  const base = new URL("../", location.href).toString();
  for (const m of faltam) {
    const li = el("li");
    const a = el("a");
    a.href = linkDaLoja(base, m.codigo);
    a.target = "_blank";
    a.rel = "noopener";
    const textos = el("div", "linha-textos");
    textos.append(el("span", "linha-texto", m.nome), el("span", "linha-detalhe", m.descricao));
    a.append(icone(m.icone, m.cor), textos, el("span", "vitrine-ver", "Ver"));
    li.append(a);
    ul.append(li);
  }
  no.append(ul);
  return no;
}

function rodape() {
  const no = el("footer", "rodape");
  if (!instalado()) {
    const dica = el("div", "dica");
    const ios = /iPhone|iPad/.test(navigator.userAgent);
    dica.append(
      el("strong", "", "Deixe um atalho na tela inicial"),
      el("span", "", ios
        ? "No Safari, toque em Compartilhar (o quadrado com a seta) e depois em “Adicionar à Tela de Início”."
        : "No menu do navegador (⋮), toque em “Instalar aplicativo” ou “Adicionar à tela inicial”."),
    );
    if (pedidoDeInstalar) {
      const b = el("button", "botao", "Adicionar agora");
      b.type = "button";
      b.addEventListener("click", async () => {
        pedidoDeInstalar.prompt();
        await pedidoDeInstalar.userChoice.catch(() => null);
        pedidoDeInstalar = null;
        desenhar();
      });
      dica.append(b);
    }
    no.append(dica);
  }
  const sair = el("button", "link-discreto", "Desconectar este celular");
  sair.type = "button";
  sair.addEventListener("click", () => {
    if (!confirm("Desconectar este celular? Para ver de novo, será preciso ler um QR Code novo no Hub.")) return;
    guardar(CHAVE, null);
    guardar(CHAVE_PC, null);
    guardar(CHAVE_CACHE, null);
    acessoEmMemoria = "";
    dados = null;
    semAcesso();
  });
  no.append(sair, el("p", "rodape-nota", "Só leitura: nada muda no computador pelo celular."));
  return no;
}

function marcarQuando(texto, sinal) {
  const alvo = $("quando");
  alvo.textContent = texto;
  if (sinal) alvo.dataset.sinal = sinal;
  else delete alvo.dataset.sinal;
}

function atualizarQuando(iso) {
  if (!iso) return marcarQuando("", "mudo");
  marcarQuando(`Atualizado ${haQuanto(iso)}`, estaAntigo(iso) ? "velho" : "");
}

// -------------------------------------------------------------- instalar ---
let pedidoDeInstalar = null;
addEventListener("beforeinstallprompt", (evento) => {
  evento.preventDefault();
  pedidoDeInstalar = evento;
  if (dados) desenhar();
});
addEventListener("appinstalled", () => { pedidoDeInstalar = null; if (dados) desenhar(); });
const instalado = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

// ----------------------------------------------------------------- tema ---
const ROTULO_TEMA = {
  auto: "Tema: automático (o do celular). Tocar para claro.",
  claro: "Tema: claro. Tocar para escuro.",
  escuro: "Tema: escuro. Tocar para automático.",
};
const botaoTema = $("tema");
botaoTema.addEventListener("click", (evento) => window.DumTema?.proximo(evento.currentTarget));
window.DumTema?.aoMudar((tema) => botaoTema.setAttribute("aria-label", ROTULO_TEMA[tema] ?? ""));

// ---------------------------------------------------------------- fluxo ---
function semAcesso() {
  estado({
    titulo: "Conecte ao seu DumTech Hub",
    texto: "Veja vendas, contas, ordens e agenda da sua empresa de onde estiver. Leva 10 segundos:",
    passos: true,
  });
}

function mostrarErro(codigo, tentar) {
  const e = ERROS[codigo] ?? ERROS.sem_internet;
  const volta = ["sem_internet", "muitas_tentativas"].includes(codigo);
  estado({
    titulo: e.titulo, texto: e.texto, tom: "erro",
    passos: codigo === "codigo_invalido" || codigo === "desconectado",
    botao: volta ? "Tentar de novo" : "", acao: volta ? tentar : null,
  });
}

async function parear(codigo) {
  // o codigo sai do endereco ANTES da rede: recarregar a pagina nao tenta de novo
  history.replaceState(null, "", location.pathname + location.search);
  const r = await rpc("dumtech_celular_parear", { p_codigo: codigo, p_nome: nomeDoAparelho(navigator.userAgent) });
  if (!r?.ok) {
    if (acesso()) return ler(true); // ja estava conectado: segue com o acesso de antes
    return mostrarErro(r?.erro ?? "sem_internet", () => location.reload());
  }
  guardar(CHAVE, r.token);
  acessoEmMemoria = r.token;
  guardar(CHAVE_PC, null);
  guardar(CHAVE_CACHE, null); // acesso novo, empresa possivelmente outra
  return ler(true);
}

async function ler(agora = false) {
  if (lendo) return;
  const token = acesso();
  if (!token) return semAcesso();
  // duas voltas coladas (trocar de aba e voltar) nao viram duas chamadas
  if (!agora && performance.now() - ultimaLeitura < DESCANSO_MS) return;
  lendo = true;
  ultimaLeitura = performance.now();
  $("recarregar").classList.add("girando-icone");
  let r;
  try {
    r = await rpc("dumtech_celular_dados", { p_token: token });
  } finally {
    // aconteca o que acontecer, a proxima leitura tem de poder comecar
    lendo = false;
    ultimaLeitura = performance.now();
    $("recarregar").classList.remove("girando-icone");
  }

  if (r?.ok) {
    dados = r;
    salvarCache(r);
    // mesma resposta de antes: refazer a tela custaria caro e ainda jogaria
    // a rolagem do dono para fora do lugar
    const nova = assinar(r);
    if (nova === assinatura) atualizarQuando(montarTela(r, Number(guardado(CHAVE_PC)) || 0).atualizadoEm);
    else { assinatura = nova; desenhar(); }
    ligarRelogio();
    return;
  }
  const erro = r?.erro ?? "sem_internet";
  if (erro === "desconectado") {
    guardar(CHAVE, null);
    guardar(CHAVE_CACHE, null);
    acessoEmMemoria = "";
  }
  // sem internet com dados na tela: mantem o que tinha e so avisa no topo
  if (dados && (erro === "sem_internet" || erro === "muitas_tentativas")) {
    marcarQuando("Sem conexão · tentando de novo", "mudo");
    ligarRelogio();
    return;
  }
  mostrarErro(erro, () => ler(true));
  if (erro === "sem_internet") ligarRelogio();
}

function ligarRelogio() {
  pararRelogio();
  relogio = setInterval(() => {
    if (document.visibilityState === "visible") ler();
  }, INTERVALO_MS);
}
function pararRelogio() {
  if (relogio) clearInterval(relogio);
  relogio = 0;
}

// Voltar para o aplicativo tem de trazer numero novo, venha de onde vier:
// trocar de aba, voltar da bandeja, o "voltar" do Android, a internet voltar.
// sem `agora`: o descanso junta o visibilitychange e o focus que chegam
// colados na mesma volta numa leitura so
const aoVoltar = () => { if (document.visibilityState === "visible" && acesso()) ler(); };
document.addEventListener("visibilitychange", aoVoltar);
addEventListener("pageshow", (evento) => { if (evento.persisted) aoVoltar(); });
addEventListener("focus", aoVoltar);
addEventListener("online", aoVoltar);
$("recarregar").addEventListener("click", () => ler(true));

// o "atualizado ha" anda sozinho entre uma leitura e outra
setInterval(() => {
  if (dados && !lendo) atualizarQuando(montarTela(dados, Number(guardado(CHAVE_PC)) || 0).atualizadoEm);
}, RELOGIO_TEXTO_MS);

// a casca sai do proprio aparelho na proxima vez - e e ela que faz o Android
// instalar isto como aplicativo de verdade
if ("serviceWorker" in navigator) {
  addEventListener("load", () => {
    navigator.serviceWorker.register(new URL("sw.js", location.href), { scope: "./" }).catch(() => null);
  });
}

// ----------------------------------------------------------- abrir a tela ---
const codigo = codigoDoEndereco(location.hash);
if (codigo) {
  parear(codigo);
} else {
  // abre JA com o que chegou da ultima vez, e busca o novo no mesmo instante
  if (acesso()) {
    const salvo = lerCache();
    if (salvo) {
      dados = salvo;
      assinatura = assinar(salvo);
      desenhar();
      marcarQuando("Atualizando...", "mudo");
    }
  }
  ler(true);
}
