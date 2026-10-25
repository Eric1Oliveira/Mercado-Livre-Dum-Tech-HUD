// Grava o video "Como usar o Passo a passo" a partir do SITE de verdade, no Microsoft Edge sem janela.
//
//     .venv\Scripts\python tools\videos\publicar_passo.py    (antes: a pagina precisa do catalogo e dos videos)
//     node tools/videos/gravar_site.mjs
//     .venv\Scripts\python tools\videos\publicar_passo.py    (depois: leva este video para o site)
//
// Por que Edge e nao o Qt: o navegador embutido do Qt nao toca H.264, e aqui o video precisa aparecer tocando.
// O Edge e controlado pelo protocolo de depuracao (CDP). Cliques e digitacao sao eventos de verdade
// (hover, foco e o play do <video> reagem como com uma pessoa); o cursor, a legenda e os cartoes sao
// desenhados por cima da pagina com as mesmas medidas de gravador.py, entao o video sai igual aos do programa.
// Saida: build/videos/passo-a-passo/usar-passo-a-passo.mp4 + .passos.json (cada legenda com o seu segundo).
// Se o roteiro quebrar no meio, nada fica salvo (o publicador nao leva video pela metade).

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SAIDA = join(RAIZ, "build", "videos", "passo-a-passo");
const ID = "usar-passo-a-passo";
const LARGURA = 1280, ALTURA = 720, FPS = 25, PORTA = 5191, DEPURACAO = 9333;
const SITE = `http://127.0.0.1:${PORTA}`;
const EDGE = ["C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe"].find(existsSync);
const FFMPEG = process.env.FFMPEG || join(RAIZ, ".venv/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe");
const GRADE = "M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z";
const PLAY = "M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0z M10 8.5v7l5.5-3.5z";
const espera = ms => new Promise(r => setTimeout(r, ms));

// ---------------------------------------------------------------- o que aparece por cima da pagina
// Roda dentro do navegador (vai como texto). Medidas copiadas de gravador.py, num quadro de 1280x720.
// O estado (cursor e legenda) fica no sessionStorage para sobreviver a troca de pagina sem pulo.
function sobreposicao() {
  if (window.__gv || window.top !== window) return;
  const GRADE = "M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z";
  const SUAVE = "cubic-bezier(.45,0,.55,1)";          // a curva _ease de gravador.py: t*t*(3-2t)
  const svg = (d, lado, traco) => `<svg viewBox="0 0 24 24" width="${lado}" height="${lado}" fill="none" stroke="#fff"
    stroke-width="${traco}" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
  const CSS = `
    #gv-cursor { position: fixed; left: 0; top: 0; z-index: 2147483646; pointer-events: none; }
    #gv-onda { position: fixed; left: 0; top: 0; z-index: 2147483645; pointer-events: none; width: 16px; height: 16px;
      margin: -8px 0 0 -8px; border-radius: 50%; background: #7353F6; opacity: 0; }
    #gv-onda.vai { animation: gv-onda .45s ${SUAVE}; }
    @keyframes gv-onda { from { opacity: .55; transform: scale(1); } to { opacity: 0; transform: scale(4.25); } }
    #gv-legenda { position: fixed; left: 50%; bottom: 34px; z-index: 2147483644; pointer-events: none; box-sizing: border-box;
      display: flex; align-items: center; height: 58px; max-width: 1120px; padding: 0 22px 0 42px; border-radius: 18px;
      background: rgba(23, 23, 31, .91); color: #fff; font: 600 22.6px/1 "Plus Jakarta Sans", "Segoe UI", sans-serif;
      white-space: nowrap; opacity: 0; transform: translate(-50%, 14px); transition: opacity .3s ${SUAVE}, transform .3s ${SUAVE}; }
    #gv-legenda::before { content: ""; position: absolute; left: 22px; top: 24px; width: 10px; height: 10px; background: #7353F6; }
    #gv-legenda.on { opacity: 1; transform: translate(-50%, 0); }
    .gv-ja, .gv-ja::before { transition: none !important; }
    #gv-cartao { position: fixed; inset: 0; z-index: 2147483647; display: none; overflow: hidden; pointer-events: none; color: #fff;
      background: linear-gradient(119.36deg, #6a48f2 0%, #7c5cf7 60%, #9d86fb 100%);
      font-family: "Plus Jakarta Sans", "Segoe UI", sans-serif; }
    #gv-cartao.on { display: block; }
    #gv-cartao .fundo { position: absolute; left: 742px; top: 36px; opacity: .1; animation: gv-deriva 20s linear both; }
    @keyframes gv-deriva { to { transform: translateY(-120px); } }
    #gv-cartao .marca { position: absolute; left: 96px; top: 80px; height: 52px; display: flex; align-items: center; gap: 16px;
      font-size: 26.7px; font-weight: 800; animation: gv-aparece .6s ${SUAVE} both; }
    #gv-cartao .selo { width: 52px; height: 52px; border-radius: 15px; background: rgba(255, 255, 255, .18); display: grid; place-items: center; }
    #gv-cartao .corpo { position: absolute; inset: 0; animation: gv-sobe .6s ${SUAVE} both; }
    @keyframes gv-aparece { from { opacity: 0; } }
    @keyframes gv-sobe { from { opacity: 0; transform: translateY(24px); } }
    #gv-cartao .ico { position: absolute; left: 96px; top: 259.2px; width: 116px; height: 116px; box-sizing: border-box;
      border-radius: 32px; border: 2px solid rgba(255, 255, 255, .35); display: grid; place-items: center; }
    #gv-cartao small { position: absolute; left: 244px; top: 259.2px; line-height: 36px; font-size: 20px; font-weight: 800;
      letter-spacing: 3.3px; text-transform: uppercase; color: rgba(255, 255, 255, .84); }
    #gv-cartao b { position: absolute; left: 240px; top: 289.2px; height: 100px; display: flex; align-items: center;
      white-space: nowrap; font-size: 72px; font-weight: 800; letter-spacing: -.03em; }
    #gv-cartao p { position: absolute; left: 96px; top: 419.2px; width: 794px; margin: 0; font-size: 25.3px; line-height: 1.35;
      color: rgba(255, 255, 255, .88); }
    #gv-cartao .branco { position: absolute; inset: 0; background: #F6F6F9; opacity: 0; transition: opacity .35s ${SUAVE}; }
    #gv-cartao .branco.on { opacity: 1; }`;

  let estado = {};
  try { estado = JSON.parse(sessionStorage.getItem("gv") || "{}"); } catch { /* sem sessionStorage: comeca do zero */ }
  const guardar = () => { try { sessionStorage.setItem("gv", JSON.stringify(estado)); } catch { /* idem */ } };
  const $ = id => document.getElementById(id);
  const semAnimar = e => { e.classList.add("gv-ja"); requestAnimationFrame(() => requestAnimationFrame(() => e.classList.remove("gv-ja"))); };

  const montar = () => {
    if ($("gv-cursor")) return;
    const estilo = document.createElement("style");
    estilo.textContent = CSS;
    document.head.append(estilo);
    const cursor = document.createElement("div");
    cursor.id = "gv-cursor";
    cursor.innerHTML = '<svg width="22" height="31" viewBox="-2 -2 22 31"><path d="M0 0L0 22L6 17L10.5 26L14 24.5L9.8 15.8L17 15.5Z" '
      + 'fill="#14141c" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/></svg>';
    const onda = document.createElement("div");
    onda.id = "gv-onda";
    const legenda = document.createElement("div");
    legenda.id = "gv-legenda";
    const cartao = document.createElement("div");
    cartao.id = "gv-cartao";
    cartao.innerHTML = `<div class="fundo">${svg(GRADE, 648, 0.9)}</div>
      <div class="marca"><span class="selo">${svg(GRADE, 30, 2)}</span>DumTech Hub</div>
      <div class="corpo"><span class="ico"></span><small></small><b></b><p></p></div><div class="branco"></div>`;
    document.body.append(cursor, onda, legenda, cartao);
    // continua de onde a pagina anterior parou
    cursor.style.transform = `translate(${(estado.x ?? 820) - 2}px, ${(estado.y ?? 400) - 2}px)`;
    if (estado.legenda) { legenda.textContent = estado.legenda; semAnimar(legenda); legenda.classList.add("on"); }
  };

  window.__gv = {
    mover(x, y, ms) {
      montar();
      const c = $("gv-cursor");
      c.style.transition = ms ? `transform ${ms}ms ${SUAVE}` : "none";
      c.style.transform = `translate(${x - 2}px, ${y - 2}px)`;    // a ponta da seta fica exatamente em (x, y)
      Object.assign(estado, { x, y }); guardar();
    },
    clique(x, y) {
      montar();
      const o = $("gv-onda");
      o.style.left = `${x}px`; o.style.top = `${y}px`;
      o.classList.remove("vai"); void o.offsetWidth; o.classList.add("vai");
    },
    legenda(texto) {
      montar();
      const l = $("gv-legenda");
      estado.legenda = texto; guardar();
      if (!texto) { l.classList.remove("on"); return; }
      l.textContent = texto;
      l.classList.remove("on"); semAnimar(l); void l.offsetWidth; l.classList.add("on");
    },
    cartao({ sobre, titulo, texto, icone, cor }) {
      montar();
      const c = $("gv-cartao");
      c.querySelector(".ico").innerHTML = svg(icone, 72, 1.7);
      c.querySelector(".ico").style.background = cor;
      c.querySelector("small").textContent = sobre;
      c.querySelector("b").textContent = titulo;
      c.querySelector("p").textContent = texto;
      c.querySelector(".branco").classList.remove("on");
      c.classList.remove("on"); void c.offsetWidth; c.classList.add("on");   // entra de corte; o conteudo sobe em 0,6 s
    },
    cartaoSai() {                                                             // some num branco, como o da abertura do programa
      const c = $("gv-cartao"), branco = c.querySelector(".branco");
      branco.classList.add("on");
      setTimeout(() => { c.classList.remove("on"); semAnimar(branco); branco.classList.remove("on"); }, 360);
    },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", montar);
  else montar();
}

// ---------------------------------------------------------------- protocolo do navegador (CDP)
async function conectar(url) {
  const ws = new WebSocket(url);
  await new Promise((ok, falha) => { ws.onopen = ok; ws.onerror = () => falha(new Error("sem conexao com o Edge")); });
  let n = 0;
  const pendentes = new Map(), ouvintes = new Set();
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) {
      const p = pendentes.get(m.id);
      if (!p) return;
      pendentes.delete(m.id);
      if (m.error) p.falha(new Error(`${p.metodo}: ${m.error.message}`)); else p.ok(m.result);
    } else if (m.method) for (const o of [...ouvintes]) o(m);
  };
  const cdp = (metodo, params = {}) => new Promise((ok, falha) => {
    const id = ++n;
    pendentes.set(id, { ok, falha, metodo });
    ws.send(JSON.stringify({ id, method: metodo, params }));
  });
  const ouvir = (nome, fn) => {
    const o = m => { if (m.method === nome) fn(m.params); };
    ouvintes.add(o);
    return () => ouvintes.delete(o);
  };
  const evento = (nome, ms = 20000) => new Promise((ok, falha) => {
    const t = setTimeout(() => { parar(); falha(new Error(`esperei demais por ${nome}`)); }, ms);
    const parar = ouvir(nome, p => { clearTimeout(t); parar(); ok(p); });
  });
  return { cdp, ouvir, evento, fechar: () => ws.close() };
}

// ---------------------------------------------------------------- gravacao
async function main() {
  if (!EDGE) throw new Error("Microsoft Edge nao encontrado");
  if (!existsSync(FFMPEG)) throw new Error(`ffmpeg nao encontrado em ${FFMPEG} (defina FFMPEG)`);
  if (!existsSync(join(RAIZ, "landingpage", "passo-a-passo", "catalogo.js"))) {
    throw new Error("rode antes tools/videos/publicar_passo.py: a pagina precisa do catalogo e dos videos");
  }
  mkdirSync(SAIDA, { recursive: true });
  const destino = join(SAIDA, `${ID}.mp4`);

  const servidor = spawn(process.execPath, [join(RAIZ, "landingpage", "servidor.mjs"), String(PORTA)], { stdio: "ignore" });
  const perfil = mkdtempSync(join(tmpdir(), "dumtech-site-"));
  const edge = spawn(EDGE, ["--headless=new", `--remote-debugging-port=${DEPURACAO}`, "--remote-allow-origins=*",
    `--window-size=${LARGURA},${ALTURA}`, "--force-device-scale-factor=1", "--hide-scrollbars", "--mute-audio",
    "--autoplay-policy=no-user-gesture-required", "--no-first-run", "--no-default-browser-check",
    `--user-data-dir=${perfil}`, "about:blank"], { stdio: "ignore" });
  let ff, relogio, fechar = () => {}, ok = false;
  try {
    let alvo;
    for (const limite = Date.now() + 20000; !alvo && Date.now() < limite; await espera(250)) {
      try {
        await fetch(SITE + "/");
        alvo = (await (await fetch(`http://127.0.0.1:${DEPURACAO}/json/list`)).json()).find(t => t.type === "page");
      } catch { /* servidor ou Edge ainda subindo */ }
    }
    if (!alvo) throw new Error("o Edge ou o servidor local nao responderam");
    const conexao = await conectar(alvo.webSocketDebuggerUrl);
    const { cdp, ouvir, evento } = conexao;
    fechar = conexao.fechar;
    await cdp("Page.enable");
    await cdp("Page.setBypassCSP", { enabled: true });
    await cdp("Emulation.setDeviceMetricsOverride", { width: LARGURA, height: ALTURA, deviceScaleFactor: 1, mobile: false });
    await cdp("Emulation.setFocusEmulationEnabled", { enabled: true }).catch(() => {});      // a aba conta como em foco
    await cdp("Browser.grantPermissions", { origin: SITE, permissions: ["clipboardReadWrite", "clipboardSanitizedWrite"] })
      .catch(() => {});                                                                       // "Copiar link" sem pedir licenca
    await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(${sobreposicao})();` });

    const js = async expr => {
      const r = await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(`no site: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
      return r.result.value;
    };
    const carregar = async acao => {
      const carregou = evento("Page.loadEventFired");
      await acao();
      await carregou;
      await js("document.fonts.ready.then(() => true)");
      await espera(400);
    };

    // ---- quadros: o Edge manda um quadro quando a tela muda; o relogio grava o ultimo a cada 1/FPS s
    ff = spawn(FFMPEG, ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
      "-vf", `scale=${LARGURA}:${ALTURA}`, "-c:v", "libx264", "-preset", "slow", "-crf", "30", "-tune", "stillimage",
      "-g", "250", "-pix_fmt", "yuv420p", "-movflags", "+faststart", destino], { stdio: ["pipe", "ignore", "inherit"] });
    let ultimo = null, quadros = 0, inicio = 0;
    const agora = () => (performance.now() - inicio) / 1000;
    ouvir("Page.screencastFrame", ({ data, sessionId }) => {
      ultimo = Buffer.from(data, "base64");
      cdp("Page.screencastFrameAck", { sessionId }).catch(() => {});
    });
    const escrever = () => {
      if (!inicio || !ultimo) return;
      for (const devidos = Math.floor(agora() * FPS) + 1; quadros < devidos; quadros++) ff.stdin.write(ultimo);
    };
    const filmar = () => cdp("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: LARGURA, maxHeight: ALTURA, everyNthFrame: 1 });

    // ---- gestos (os mesmos do Diretor de gravador.py)
    const passos = [];
    let pos = { x: 820, y: 400 };
    const dizer = async texto => {
      if (texto) passos.push({ t: Math.round(agora() * 10) / 10, texto });
      await js(`__gv.legenda(${JSON.stringify(texto)})`);
    };
    const centro = async alvo => {                 // "seletor" ou ["seletor", "texto exato do elemento"]
      const [seletor, texto = null] = Array.isArray(alvo) ? alvo : [alvo];
      const c = await js(`(() => {
        const todos = [...document.querySelectorAll(${JSON.stringify(seletor)})];
        const texto = ${JSON.stringify(texto)};
        const e = texto === null ? todos[0] : todos.find(x => x.textContent.trim() === texto);
        if (!e) return null;
        const r = e.getBoundingClientRect();
        return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
      })()`);
      if (!c) throw new Error(`nao achei na pagina: ${[seletor, texto].filter(Boolean).join(" / ")}`);
      return c;
    };
    const apontar = async alvo => {
      const c = await centro(alvo);
      const ms = Math.round(Math.min(800, 250 + Math.hypot(c.x - pos.x, c.y - pos.y) / 1.4));
      await js(`__gv.mover(${c.x}, ${c.y}, ${ms})`);
      await espera(ms + 40);
      pos = c;
      await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: c.x, y: c.y });
      await espera(140);
      return c;
    };
    const clicar = async (alvo, depois = 700) => {
      const c = await apontar(alvo);
      await js(`__gv.clique(${c.x}, ${c.y})`);
      await cdp("Input.dispatchMouseEvent", { type: "mousePressed", x: c.x, y: c.y, button: "left", clickCount: 1 });
      await cdp("Input.dispatchMouseEvent", { type: "mouseReleased", x: c.x, y: c.y, button: "left", clickCount: 1 });
      await espera(depois);
    };
    const digitar = async (alvo, texto, porSegundo = 12) => {
      await clicar(alvo, 250);
      for (const letra of texto) {
        await cdp("Input.insertText", { text: letra });
        await espera(1000 / porSegundo);
      }
    };
    const rolar = async seletor => {                // deixa o topo do bloco logo abaixo da barra do site
      await js(`(() => { const e = document.querySelector(${JSON.stringify(seletor)});
        scrollTo({ top: e.getBoundingClientRect().top + scrollY - 84, behavior: "smooth" }); return true; })()`);
      await espera(1100);
    };
    const cartao = (sobre, titulo, texto, icone, cor) => js(`__gv.cartao(${JSON.stringify({ sobre, titulo, texto, icone, cor })})`);

    // ---- o roteiro
    await carregar(() => cdp("Page.navigate", { url: SITE + "/" }));
    await js(`Promise.all(["800 72px", "400 25px", "600 22px"].map(f => document.fonts.load(f + ' "Plus Jakarta Sans"'))).then(() => true)`);
    await js(`__gv.mover(${pos.x}, ${pos.y}, 0)`);
    await filmar();
    for (const limite = Date.now() + 5000; !ultimo && Date.now() < limite;) await espera(20);
    if (!ultimo) throw new Error("o Edge nao mandou nenhum quadro");

    // abertura: como abrir() dos roteiros do programa (2,8 s, sai num branco)
    await cartao("Passo a passo", "Como usar o Passo a passo",
      "Escreva a sua dúvida do seu jeito e o vídeo certo aparece na hora.", PLAY, "#7353F6");
    await espera(90);
    inicio = performance.now();
    relogio = setInterval(escrever, 8);
    await espera(2440);
    await js("__gv.cartaoSai()");
    await espera(420);

    await dizer("No site da DumTech, clique em Passo a passo, no topo");
    await espera(600);
    await carregar(() => clicar(".topo nav .nav-passo", 0));   // o screencast segue sozinho na pagina nova

    await dizer("Escreva a sua dúvida do seu jeito");
    await digitar("#busca", "como cadastro produtos");
    await espera(800);
    await dizer("O vídeo exato aparece na hora, com o passo a passo ao lado");
    await rolar("#destaque");
    await apontar("#video-titulo");
    await espera(1500);

    await dizer("Dê o play: é o programa de verdade fazendo a tarefa");
    await clicar("#video", 300);
    await js(`(() => { const v = document.querySelector("#video"); if (v.paused) v.play(); return true; })()`);
    await espera(4600);

    await dizer("Clique num passo para pular direto para ele");
    await clicar("#lista-passos li:nth-child(6) button", 4000);
    await js(`(() => { document.querySelector("#video").pause(); return true; })()`);

    await dizer("Ou escolha pelo assunto, nos filtros");
    await js(`(() => { const b = document.querySelector("#busca"); b.value = "";
      b.dispatchEvent(new Event("input", { bubbles: true })); return true; })()`);    // o filtro vale para o catalogo todo
    await rolar("#catalogo");
    await clicar(["#filtros button", "Estoque"], 2300);

    await dizer("Copiar link manda o vídeo certo para quem precisa");
    await rolar("#destaque");
    await clicar("#copiar-link", 1900);

    // encerramento: como fim() (2,6 s, fica ate o video acabar)
    await dizer("");
    await cartao("Pronto", "Feito!", "Não achou o que procurava? Fale com a gente: a dúvida que aparece vira vídeo aqui.",
      GRADE, "#5b3fe0");
    await espera(2600);

    escrever();
    await cdp("Page.stopScreencast").catch(() => {});
    writeFileSync(join(SAIDA, `${ID}.passos.json`),
      JSON.stringify({ duracao: Math.round((quadros / FPS) * 10) / 10, passos }, null, 1), "utf8");
    ok = true;
  } finally {
    clearInterval(relogio);
    if (ff) {
      ff.stdin.end();
      await new Promise(r => ff.on("close", r));
      if (!ok) rmSync(destino, { force: true });
    }
    fechar();
    edge.kill();
    servidor.kill();
    await espera(800);
    try { rmSync(perfil, { recursive: true, force: true }); } catch { /* o Edge ainda segura um arquivo: fica no %TEMP% */ }
  }
  console.log("gravado:", destino);
}

main().catch(erro => { console.error(erro); process.exit(1); });
