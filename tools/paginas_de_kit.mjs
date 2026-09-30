// Uma pagina propria para cada kit: /kit/comercio/, /kit/oficina/...
//
//     node tools/paginas_de_kit.mjs <pasta-do-site>     (publicar_site.ps1 chama)
//
// POR QUE GERAR NA PUBLICACAO
//   O link vai para anuncio, Instagram e WhatsApp - e quem monta a previa
//   (titulo, preco, imagem) le o HTML CRU, sem rodar JavaScript. Entao nome,
//   preco e imagem precisam estar escritos no arquivo. O kit vem do servidor
//   (tela Kits do painel) na hora de publicar; a propria pagina confere o
//   preco de novo ao abrir, para um kit reajustado nao mostrar valor velho.
//
// A IMAGEM DA PREVIA (og.png, 1200x630) sai de um HTML fotografado pelo Edge
// ou Chrome sem janela - o mesmo truque do PDF do guia.

import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const LOJA = path.join(RAIZ, "landingpage");
const SITE = path.resolve(process.argv[2] || path.join(RAIZ, "build", "site"));
const ENDERECO = "https://dumtechsolution.com";

globalThis.location = { search: "" }; // config.js le a URL da pagina
const { CONFIG } = await import(pathToFileURL(path.join(LOJA, "js", "config.js")));
const { MODULOS, INTEGRACOES, KITS_PADRAO, PRECO_PADRAO } = await import(pathToFileURL(path.join(LOJA, "js", "dados.js")));

// ------------------------------------------------------------- catalogo ---
async function catalogo() {
  try {
    const r = await fetch(`${CONFIG.SUPABASE_URL}/rpc/dumtech_catalogo`, {
      method: "POST",
      headers: { apikey: CONFIG.SUPABASE_ANON, Authorization: `Bearer ${CONFIG.SUPABASE_ANON}`, "Content-Type": "application/json" },
      body: "{}",
    });
    const d = await r.json();
    if (!d?.ok || !d.combos?.length) throw new Error("sem kits");
    return { kits: d.combos, precos: Object.fromEntries(d.produtos.map((p) => [p.codigo, Number(p.preco)])) };
  } catch (erro) {
    console.warn(`  (servidor fora: usando os kits de reserva - ${erro.message})`);
    return { kits: KITS_PADRAO, precos: PRECO_PADRAO };
  }
}

// ------------------------------------------------------------- ajudantes ---
export const slug = (texto) => String(texto).normalize("NFD").replace(/[\u0300-\u036f]/g, "")
  .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const moeda = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const icone = (d, cor, lado = 22) =>
  `<span class="kp-icone" style="--cor:${esc(cor)}"><svg viewBox="0 0 24 24" width="${lado}" height="${lado}" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="${esc(d)}"/></svg></span>`;

function contas(kit, precos) {
  const modulos = kit.produtos.map((c) => MODULOS.find((m) => m.codigo === c)).filter(Boolean);
  const avulso = kit.produtos.reduce((s, c) => s + (Number(precos[c]) || 0), 0);
  const preco = Number(kit.preco);
  // so as pontes que o kit inteiro liga (de E para dentro do kit)
  const pontes = INTEGRACOES.filter((i) => kit.produtos.includes(i.de) && i.para.some((p) => kit.produtos.includes(p)));
  return { modulos, avulso, preco, economia: Math.max(0, Math.round((avulso - preco) * 100) / 100), pontes };
}

// ---------------------------------------------------------------- pagina ---
function pagina(kit, outros, precos) {
  const k = contas(kit, precos);
  const s = slug(kit.codigo);
  const url = `${ENDERECO}/kit/${s}/`;
  const titulo = `${kit.nome} · ${moeda(k.preco)} — DumTech Hub`;
  const resumo = `${kit.descricao || kit.nome}. ${k.modulos.map((m) => m.nome).join(", ")} num programa só, sem mensalidade.`;
  const destino = `../../?kit=${kit.produtos.join(",")}#montador`;
  const para = kit.ramo ? `Para ${kit.ramo.charAt(0).toLowerCase()}${kit.ramo.slice(1)}` : "Kit pronto";

  return `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self' https://kpiyhhmtteojqxhhmcyr.supabase.co; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>${esc(titulo)}</title>
<meta name="description" content="${esc(resumo)}">
<link rel="canonical" href="${url}">
<meta property="og:type" content="product">
<meta property="og:site_name" content="DumTech Hub">
<meta property="og:locale" content="pt_BR">
<meta property="og:url" content="${url}">
<meta property="og:title" content="${esc(`${kit.nome} · ${moeda(k.preco)}`)}">
<meta property="og:description" content="${esc(resumo)}">
<meta property="og:image" content="${url}og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="${esc(`${kit.nome}: ${k.modulos.map((m) => m.nome).join(", ")}`)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><rect width='24' height='24' rx='6' fill='%237353F6'/><path d='M6 6h4v4H6z M14 6h4v4h-4z M6 14h4v4H6z M14 14h4v4h-4z' fill='none' stroke='white' stroke-width='2'/></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../../css/estilo.css">
<link rel="stylesheet" href="../../css/paginas.css">
<link rel="stylesheet" href="../../css/kit-pagina.css">
</head>
<body>

<header class="topo" data-rolou="sim">
  <div class="envolve">
    <a class="marca" href="../../">
      <span class="selo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z"/></svg></span>
      DumTech Hub
    </a>
    <nav>
      <a href="../../#kits-prontos">Todos os kits</a>
      <a href="../../baixar/">Baixar</a>
    </nav>
  </div>
</header>

<main class="pagina kp" data-kit="${esc(kit.codigo)}" data-preco="${k.preco}">
  <div class="envolve">
    <section class="kp-topo">
      <div class="kp-texto">
        <p class="sobrenome">${esc(para)}</p>
        <h1>${esc(kit.nome)}</h1>
        <p class="lede">${esc(kit.descricao)}</p>
        <div class="kp-preco">
          <strong id="kp-preco">${moeda(k.preco)}</strong>
          <span>pagamento único · sem mensalidade</span>
        </div>
        ${k.economia > 0 ? `<p class="kp-economia" id="kp-economia">Separados, os ${k.modulos.length} módulos custam ${moeda(k.avulso)}: você economiza <b>${moeda(k.economia)}</b>.</p>` : ""}
        <div class="kp-acoes">
          <a class="botao botao-primario" id="kp-comprar" href="${esc(destino)}">Quero este kit</a>
          <a class="botao botao-fantasma" href="https://wa.me/${esc(CONFIG.WHATSAPP)}?text=${encodeURIComponent(`Oi! Quero saber mais do ${kit.nome}.`)}" rel="noopener" target="_blank">Tirar dúvida no WhatsApp</a>
        </div>
        <p class="kp-nota">Teste grátis de 7 dias em qualquer módulo, direto no programa.</p>
      </div>
      <ul class="kp-modulos">
        ${k.modulos.map((m) => `<li>${icone(m.icone, m.cor)}<div><strong>${esc(m.nome)}</strong><span>${esc(m.descricao)}</span></div></li>`).join("\n        ")}
      </ul>
    </section>

    ${k.pontes.length ? `<section class="kp-bloco">
      <h2>Juntos, eles conversam</h2>
      <p class="kp-sub">O que um módulo faz já aparece no outro — sem digitar duas vezes.</p>
      <div class="kp-pontes">
        ${k.pontes.map((p) => `<article><h3>${esc(p.titulo)}</h3><p>${esc(p.ativa)}</p></article>`).join("\n        ")}
      </div>
    </section>` : ""}

    <section class="kp-bloco">
      <h2>Vem junto, em qualquer kit</h2>
      <ul class="kp-sempre">
        <li>Funciona sem internet: ela só é usada para ativar a licença.</li>
        <li>Cópia de segurança automática, todo dia.</li>
        <li>O seu negócio no celular: vendas, contas e agenda de onde estiver.</li>
        <li>Recibo e proposta com o nome e o logotipo da sua empresa.</li>
      </ul>
    </section>

    ${outros.length ? `<section class="kp-bloco">
      <h2>Outros kits</h2>
      <div class="kp-outros">
        ${outros.map((o) => `<a href="../${slug(o.codigo)}/"><strong>${esc(o.nome)}</strong><span>${esc(o.ramo || o.descricao || "")}</span><b>${moeda(Number(o.preco))}</b></a>`).join("\n        ")}
      </div>
    </section>` : ""}
  </div>
</main>

<script type="module" src="../../js/kit-pagina.js"></script>
</body>
</html>
`;
}

// ------------------------------------------------------------ a imagem ---
function arteDaPrevia(kit, precos) {
  const k = contas(kit, precos);
  return `<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700;800&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0}
body{width:1200px;height:630px;font-family:"Plus Jakarta Sans",sans-serif;background:#f6f6f9;color:#17171f;
  display:grid;grid-template-columns:1fr 440px;gap:48px;padding:72px 80px;overflow:hidden}
.marca{display:flex;align-items:center;gap:14px;font-weight:700;font-size:26px;color:#4a4a5a}
.selo{width:48px;height:48px;border-radius:14px;background:#7353f6;color:#fff;display:grid;place-items:center}
.para{margin-top:54px;font-size:24px;font-weight:700;color:#7353f6;letter-spacing:.02em}
h1{margin-top:10px;font-size:76px;line-height:1.02;letter-spacing:-.03em;font-weight:800}
.preco{margin-top:34px;font-size:56px;font-weight:800;letter-spacing:-.02em}
.preco span{display:block;font-size:22px;font-weight:600;color:#75758a;letter-spacing:0;margin-top:4px}
ul{list-style:none;padding:0;display:flex;flex-direction:column;gap:14px;align-self:center}
li{display:flex;align-items:center;gap:16px;background:#fff;border:1px solid #e7e7ef;border-radius:18px;padding:18px 20px;font-size:26px;font-weight:700}
.kp-icone{width:48px;height:48px;border-radius:13px;display:grid;place-items:center;color:var(--cor);background:color-mix(in srgb,var(--cor) 15%,transparent);flex:none}
</style></head><body>
<div>
  <div class="marca"><span class="selo"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z"/></svg></span>DumTech Hub</div>
  <p class="para">${esc(kit.ramo ? kit.ramo.toUpperCase() : "KIT PRONTO")}</p>
  <h1>${esc(kit.nome)}</h1>
  <p class="preco">${moeda(k.preco)}<span>${k.economia > 0 ? `economia de ${moeda(k.economia)} · ` : ""}sem mensalidade</span></p>
</div>
<ul>${k.modulos.slice(0, 5).map((m) => `<li>${icone(m.icone, m.cor, 26)}${esc(m.nome)}</li>`).join("")}${k.modulos.length > 5 ? `<li style="color:#75758a">+ ${k.modulos.length - 5} módulos</li>` : ""}</ul>
</body></html>`;
}

const NAVEGADORES = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
];

function fotografar(html, destino) {
  const navegador = NAVEGADORES.find((n) => fs.existsSync(n));
  if (!navegador) return Promise.resolve(false);
  // fora da pasta do site: o navegador ainda segura o arquivo quando termina
  const temp = path.join(os.tmpdir(), `dumtech-arte-${process.pid}.html`);
  fs.writeFileSync(temp, html);
  return new Promise((ok) => {
    const p = spawn(navegador, ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1200,630",
      "--virtual-time-budget=3000", `--screenshot=${destino}`, pathToFileURL(temp).href], { stdio: "ignore" });
    p.on("exit", () => ok(fs.existsSync(destino)));
  });
}

// ------------------------------------------------------------------ roda ---
const { kits, precos } = await catalogo();
const pasta = path.join(SITE, "kit");
fs.rmSync(pasta, { recursive: true, force: true });
for (const kit of kits) {
  const dir = path.join(pasta, slug(kit.codigo));
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "index.html"), pagina(kit, kits.filter((o) => o !== kit), precos));
  const foto = await fotografar(arteDaPrevia(kit, precos), path.join(dir, "og.png"));
  console.log(`  /kit/${slug(kit.codigo)}/${foto ? "" : "  (sem imagem: nenhum Edge/Chrome)"}`);
}
