/* O Hub no celular — o atendente da página.
 *
 * POR QUE EXISTE
 *   1. Abrir tem de ser instantâneo: a tela (HTML, CSS, ícones) sai daqui, do
 *      próprio aparelho, e os números começam a ser buscados no mesmo instante.
 *   2. Sem ele o Android não instala o atalho como aplicativo de verdade — vira
 *      um atalho de segunda classe, e é daí que sai o aviso de "app bloqueado".
 *
 * O QUE ELE NUNCA GUARDA
 *   Os números da empresa. Só passam por aqui pedidos POST ao servidor, que
 *   seguem direto para a rede, sem cópia. O que fica guardado é a casca.
 */

// MUDOU CSS OU JS DO CELULAR? SOBE O NUMERO AQUI.
// E o que faz o aparelho jogar fora a copia antiga: sem isto, quem ja abriu a
// pagina continua vendo a tela velha na primeira vez que abre de novo.
const VERSAO = "celular-v7";
// O ?v= tambem esta no index.html e nos import: o HTML novo pede os arquivos
// novos pelo nome, e uma copia velha guardada nunca se mistura com ele.
const CASCA = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icone-192.png",
  "./icone-512.png",
  "./icone-180.png",
  "../css/celular.css?v=7",
  "../js/tema.js",
  "../js/sem-zoom.js",
  "../js/celular-tela.js?v=7",
  "../js/celular-graficos.js?v=7",
  "../js/celular.js?v=7",
  "../js/config.js",
  "../js/dados.js",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches.open(VERSAO)
      // um arquivo que falhe não pode impedir a instalação inteira
      .then((cache) => Promise.all(CASCA.map((url) => cache.add(url).catch(() => null))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((nomes) => Promise.all(nomes.filter((n) => n !== VERSAO).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

/** Guarda a resposta boa e devolve ela. */
async function guardar(pedido, resposta) {
  if (resposta && resposta.ok && resposta.type === "basic") {
    const cache = await caches.open(VERSAO);
    cache.put(pedido, resposta.clone()).catch(() => null);
  }
  return resposta;
}

/** A tela: rede primeiro (para pegar versão nova), cópia local se falhar. */
async function tela(pedido) {
  try {
    return await guardar(pedido, await fetch(pedido));
  } catch (erro) {
    return (await caches.match(pedido)) || (await caches.match("./index.html")) || Response.error();
  }
}

/** Casca: entrega a cópia na hora e busca a nova por baixo, para a próxima vez. */
async function arquivo(pedido) {
  const guardado = await caches.match(pedido);
  const rede = fetch(pedido).then((r) => guardar(pedido, r)).catch(() => null);
  return guardado || (await rede) || Response.error();
}

self.addEventListener("fetch", (evento) => {
  const pedido = evento.request;
  if (pedido.method !== "GET") return; // os números vão e voltam pela rede, sempre
  const url = new URL(pedido.url);
  if (url.origin !== location.origin) return;

  if (pedido.mode === "navigate") {
    evento.respondWith(tela(pedido));
    return;
  }
  if (/\.(?:css|js|mjs|png|svg|webmanifest|woff2)$/.test(url.pathname)) {
    evento.respondWith(arquivo(pedido));
  }
});
