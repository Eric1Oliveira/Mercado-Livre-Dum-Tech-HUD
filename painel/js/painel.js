// A casca do painel: entrar, sair, navegar e abrir a ficha do cliente.
//
// Cada tela mora no seu arquivo e entra por importação sob demanda. A casca não
// sabe nada de negócio: ela dá um destino e a tela se desenha nele.
//
// POR QUE ELE É RÁPIDO
//   - a tela é desenhada FORA da página e entra de uma vez: trocar de aba não
//     pisca "Carregando" quando os dados já estão na memória (api.js);
//   - logo depois de entrar, as outras abas são preparadas em segundo plano;
//   - o banco avisa quando algo muda (tempo real) e a tela se atualiza sozinha,
//     sem perder a rolagem nem o que está sendo digitado.

import {
  aoMudarDados, aoPerderSessao, confirmarCodigo, conferirTudo, entrar, invalidar, ler, sair, sessao,
  sessaoCompleta, token,
} from "./api.js";
import { CONFIG } from "./config.js";
import { montarFila, urgentes } from "./fila.js";
import { lerPresenca } from "./gestao-dados.js";
import { versaoPendente } from "./gestao.js";
import { ouvir } from "./tempo-real.js";
import { carregando, el, limpar, recado } from "./ui.js";

const $ = (id) => document.getElementById(id);

// Seis lugares, cada um com um trabalho:
//   hoje       o que precisa de você agora, com o botão que resolve
//   clientes   todo mundo, e a ficha de cada um
//   planos     preços, planos prontos, links e cupons
//   site       textos do site e a faixa de aviso
//   hub        versões do programa, uso e anúncios
//   seguranca  tentativas, auditoria e contas de acesso
// Planos, Site, Hub e Segurança têm abas; "tela:aba" abre direto numa delas.
// Pedidos (o checkout antigo da loja) fica fora do menu: Hoje leva até lá.
const tela = (arquivo, funcao) => () => import(arquivo).then((m) => m[funcao]);

const ABAS = {
  planos: [
    { id: "precos", texto: "Planos e preços", tela: tela("./telas/planos.js", "planos") },
    { id: "cupons", texto: "Cupons", tela: tela("./telas/promocoes.js", "cupons") },
  ],
  site: [
    { id: "textos", texto: "Textos do site", tela: tela("./telas/textos-site.js", "textosSite") },
    { id: "faixa", texto: "Faixa de aviso", tela: tela("./telas/promocoes.js", "faixas") },
  ],
  hub: [
    { id: "atualizacoes", texto: "Atualizações", tela: tela("./telas/atualizacoes.js", "atualizacoes") },
    { id: "uso", texto: "Uso", tela: tela("./telas/uso.js", "uso") },
    { id: "anuncios", texto: "Anúncios", tela: tela("./telas/catalogo.js", "anuncios") },
  ],
  seguranca: [
    { id: "tentativas", texto: "Tentativas e auditoria", tela: tela("./telas/uso.js", "seguranca") },
    { id: "acessos", texto: "Contas de acesso", tela: tela("./telas/acessos.js", "acessos") },
  ],
};

const TELAS = {
  hoje: tela("./telas/hoje.js", "hoje"),
  clientes: tela("./telas/clientes.js", "clientes"),
  pedidos: tela("./telas/comercial.js", "pedidos"),
  ...Object.fromEntries(Object.keys(ABAS).map((nome) => [nome, async () => comAbas(nome)])),
};

// --------------------------------------------------------------- abas -----
const CHAVE_ABAS = "dumtech.painel.abas";
const abaEscolhida = (() => {
  try { return JSON.parse(localStorage.getItem(CHAVE_ABAS) || "{}"); } catch { return {}; }
})();

function lembrarAba(nome, aba) {
  if (!ABAS[nome]?.some((a) => a.id === aba)) return;
  abaEscolhida[nome] = aba;
  try { localStorage.setItem(CHAVE_ABAS, JSON.stringify(abaEscolhida)); } catch { /* vale até recarregar */ }
}

/** Desenha a barra de abas e, embaixo, a aba escolhida (cada aba é uma tela de sempre). */
function comAbas(nome) {
  return async (alvo) => {
    const abas = ABAS[nome];
    const atual = abas.find((a) => a.id === abaEscolhida[nome]) || abas[0];
    const corpo = document.createElement("div");
    await (await atual.tela())(corpo);
    alvo.append(
      el("nav", { classe: "abas", "aria-label": "Abas" }, abas.map((aba) => el("button", {
        type: "button", classe: "aba", "aria-current": aba === atual ? "page" : null, texto: aba.texto,
        onclick: () => { if (aba !== atual) irPara(`${nome}:${aba.id}`); },
        onpointerenter: () => aba.tela().catch(() => {}),
      }))),
      corpo,
    );
  };
}

// ================================================================== entrar ===
$("form-entrar").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const botao = $("botao-entrar");
  const aviso = $("aviso-entrada");

  aviso.dataset.tom = "neutro";
  aviso.textContent = "Entrando…";
  botao.disabled = true;
  try {
    const passo = await entrar($("campo-email").value, $("campo-senha").value);
    $("campo-senha").value = "";
    aviso.textContent = "";
    if (passo.etapa === "pronto") abrirPainel();
    else mostrarCodigo(passo);
  } catch (erro) {
    aviso.dataset.tom = "erro";
    aviso.textContent = erro.message || "Não foi possível entrar.";
  } finally {
    botao.disabled = false;
  }
});

// ----------------------------------------------------- segundo fator -------
function mostrarCodigo({ etapa, qr = "", segredo = "", endereco = "" }) {
  const primeiraVez = etapa === "cadastrar";
  $("form-entrar").hidden = true;
  $("form-codigo").hidden = false;
  $("cadastro-2fa").hidden = !primeiraVez;
  $("codigo-titulo").textContent = primeiraVez ? "Proteja o painel com o celular" : "Código de verificação";
  $("codigo-explica").textContent = primeiraVez
    ? "Uma vez só: leia o QR Code com um aplicativo autenticador (Google Authenticator, Microsoft Authenticator, 1Password…) e digite o código que aparecer."
    : "Abra o aplicativo autenticador e digite o código de 6 números da DumTech.";
  if (primeiraVez) desenharQr(qr, segredo, endereco);
  $("aviso-codigo").textContent = "";
  $("campo-codigo").value = "";
  $("campo-codigo").focus();
}

/** O QR quando da, a chave escrita sempre: ninguem fica preso numa imagem que nao veio. */
function desenharQr(qr, segredo, endereco) {
  const imagem = $("qr-2fa");
  const recado = $("qr-sem-desenho");
  const link = $("qr-link");
  $("segredo-2fa").textContent = segredo || "—";
  link.hidden = !endereco;
  if (endereco) link.href = endereco;

  imagem.onerror = () => {   // formato que este navegador nao desenha
    imagem.hidden = true;
    recado.hidden = false;
  };
  imagem.onload = () => {
    imagem.hidden = false;
    recado.hidden = true;
  };
  imagem.removeAttribute("src");
  if (!qr) {                 // o servidor nao mandou desenho nenhum
    imagem.hidden = true;
    recado.hidden = false;
    return;
  }
  imagem.hidden = false;
  recado.hidden = true;
  imagem.src = qr;
}

$("botao-copiar-segredo").addEventListener("click", async () => {
  const chave = $("segredo-2fa").textContent.trim();
  if (!chave || chave === "—") return;
  try {
    await navigator.clipboard.writeText(chave);
    $("aviso-codigo").dataset.tom = "neutro";
    $("aviso-codigo").textContent = "Chave copiada.";
  } catch {
    $("aviso-codigo").dataset.tom = "erro";
    $("aviso-codigo").textContent = "Não consegui copiar. Selecione a chave e copie na mão.";
  }
});

$("campo-codigo").addEventListener("input", (evento) => {
  const campo = evento.target;
  campo.value = campo.value.replace(/\D/g, "").slice(0, 6);
  // 6 números = manda sozinho (quem cola o código não precisa achar o botão)
  if (campo.value.length === 6) $("form-codigo").requestSubmit();
});

$("form-codigo").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const botao = $("botao-codigo");
  const aviso = $("aviso-codigo");
  if (botao.disabled) return;
  aviso.dataset.tom = "neutro";
  aviso.textContent = "Conferindo…";
  botao.disabled = true;
  try {
    await confirmarCodigo($("campo-codigo").value);
    aviso.textContent = "";
    abrirPainel();
  } catch (erro) {
    aviso.dataset.tom = "erro";
    aviso.textContent = erro.message || "Não deu certo.";
    $("campo-codigo").value = "";
    $("campo-codigo").focus();
  } finally {
    botao.disabled = false;
  }
});

$("botao-voltar").addEventListener("click", async () => {
  await sair();
  mostrarEntrada();
});

$("botao-sair").addEventListener("click", async () => {
  desligarTempoReal();
  await sair();
  mostrarEntrada();
});

aoPerderSessao.add(() => {
  desligarTempoReal();
  mostrarEntrada();
  recado("Sua sessão expirou. Entre de novo.", "erro");
});

function mostrarEntrada() {
  fecharGaveta();
  $("painel").hidden = true;
  $("entrada").hidden = false;
  $("form-codigo").hidden = true;
  $("form-entrar").hidden = false;
  limpar($("tela"));
  $("campo-email").focus();
}

function abrirPainel() {
  const atual = sessao();
  $("entrada").hidden = true;
  $("painel").hidden = false;
  $("usuario-email").textContent = atual?.email || "";
  irPara(lembrarTela() || "hoje").then(aquecer);
  ligarTempoReal();
}

function lembrarTela(nome) {
  try {
    if (nome) localStorage.setItem("dumtech.painel.tela", nome);
    return localStorage.getItem("dumtech.painel.tela");
  } catch {
    return nome || ""; /* sem memória do navegador o painel funciona igual */
  }
}

// ================================================================ navegar ====
for (const botao of document.querySelectorAll("#navegacao button")) {
  botao.addEventListener("click", () => irPara(botao.dataset.tela));
  // passou o mouse, já baixa o código da tela (o clique chega com tudo pronto)
  botao.addEventListener("pointerenter", () => TELAS[botao.dataset.tela]?.().catch(() => {}),
                         { once: true });
}

const telaAtual = () => document.querySelector("#navegacao button.ativo")?.dataset.tela || "hoje";

// Telas que mudaram de casa: um favorito ou a memória do navegador não caem no vazio.
const MUDOU = {
  resumo: "hoje", mensalidades: "clientes", testes: "clientes", celulares: "clientes",
  planos: "planos", promocoes: "planos:cupons", cupons: "planos:cupons", textos: "site:textos",
  atualizacoes: "hub:atualizacoes", uso: "hub:uso", anuncios: "hub:anuncios", catalogo: "hub:anuncios",
  kits: "planos", acessos: "seguranca:acessos",
};

// Quem clica em duas abas seguidas — ou clica numa enquanto a primeira ainda
// carrega — não pode acabar com as duas telas desenhadas uma embaixo da outra.
// Só o pedido mais novo tem direito de entrar na página.
let pedidoAtual = 0;

/**
 * Desenha a tela numa folha solta e só então troca. Com os dados na memória
 * isso leva milissegundos; sem eles, o "Carregando" aparece se passar de 150 ms.
 * `silencioso`: redesenho da mesma tela (não sobe a rolagem, não mostra aviso).
 */
export async function irPara(pedido, { silencioso = false } = {}) {
  const meu = ++pedidoAtual;
  const [nome, aba] = String(MUDOU[pedido] || pedido || "").split(":");
  if (aba) lembrarAba(nome, aba);
  const tela = TELAS[nome] ? nome : "hoje";
  const area = $("tela");

  // Pedidos não está no menu: o botão aceso continua o de Hoje, de onde se chega lá
  const doMenu = tela === "pedidos" ? "hoje" : tela;
  for (const botao of document.querySelectorAll("#navegacao button")) {
    botao.classList.toggle("ativo", botao.dataset.tela === doMenu);
    if (botao.dataset.tela === doMenu) botao.setAttribute("aria-current", "page");
    else botao.removeAttribute("aria-current");
  }
  lembrarTela(tela);

  const aviso = silencioso ? null : setTimeout(() => {
    if (meu === pedidoAtual) limpar(area).append(carregando());
  }, 150);

  const folha = document.createElement("div");
  folha.dataset.tela = tela;
  try {
    const desenhar = await TELAS[tela]();
    await desenhar(folha);
    if (meu !== pedidoAtual) return;
    trocar(area, folha, { manterRolagem: silencioso });
  } catch (erro) {
    console.error(erro);
    if (meu !== pedidoAtual) return;
    if (silencioso) return; // a tela que já estava continua valendo
    limpar(area).append(
      Object.assign(document.createElement("div"), {
        className: "vazio",
        textContent: `Não consegui abrir esta tela. ${erro.message || ""}`.trim(),
      })
    );
  } finally {
    clearTimeout(aviso);
  }
}

function trocar(area, folha, { manterRolagem }) {
  // segura a altura durante a troca: a página não "pula" para cima
  area.style.minHeight = `${area.offsetHeight}px`;
  area.replaceChildren(folha);
  requestAnimationFrame(() => { area.style.minHeight = ""; });
  if (!manterRolagem) window.scrollTo(0, 0);
}

/**
 * A tela chama quando mexeu em algo. Redesenha na hora com o que a memória já
 * sabe (inclusive o que acabou de ser salvo) e confere com o banco por trás.
 */
const telaNaPagina = () => $("tela").firstElementChild?.dataset.tela || telaAtual();

export async function recarregar() {
  invalidar();
  await irPara(telaNaPagina(), { silencioso: true });
  conferirTudo().catch(() => {});
}

// Algo mudou numa conferência de segundo plano: redesenha a tela aberta. Se a
// pessoa está digitando nela, espera ela sair do campo — ninguém perde o que
// escreveu porque chegou um pedido novo.
let redesenhoPendente = false;
aoMudarDados.add(() => {
  if ($("painel").hidden) return;
  const foco = document.activeElement;
  if (foco && $("tela").contains(foco) && foco.matches("input, select, textarea")) {
    if (!redesenhoPendente) {
      redesenhoPendente = true;
      foco.addEventListener("blur", () => {
        redesenhoPendente = false;
        irPara(telaNaPagina(), { silencioso: true });
      }, { once: true });
    }
    return;
  }
  irPara(telaNaPagina(), { silencioso: true });
});

/** Prepara as outras abas em segundo plano (código e dados), uma de cada vez. */
async function aquecer() {
  const ocioso = (fn) => (window.requestIdleCallback
    ? new Promise((pronto) => requestIdleCallback(() => pronto(fn()), { timeout: 1500 }))
    : new Promise((pronto) => setTimeout(() => pronto(fn()), 200)));

  for (const nome of ["hoje", "clientes", "planos", "hub", "site", "seguranca"]) {
    if ($("painel").hidden) return; // saiu no meio
    if (nome === telaAtual()) continue;
    await ocioso(async () => {
      try {
        const desenhar = await TELAS[nome]();
        await desenhar(document.createElement("div")); // folha que nunca entra na página
      } catch {
        /* aquecer é bônus: se falhar, a tela carrega quando for aberta */
      }
    });
  }
}

// ============================================================= tempo real ====
let canal = null;
let filaAntes = null;

function ligarTempoReal() {
  desligarTempoReal();
  const selo = $("ao-vivo");

  // Várias gravações seguidas (aprovar pedido mexe em 4 tabelas) viram uma
  // conferência — sem setTimeout, que o navegador segura em aba de fundo.
  let conferindo = false;
  let deNovo = false;
  let filaTambem = false;
  const conferirAgora = async () => {
    if (conferindo) {
      deNovo = true;
      return;
    }
    conferindo = true;
    try {
      do {
        deNovo = false;
        const comFila = filaTambem;
        filaTambem = false;
        invalidar();
        await Promise.all([conferirTudo(), comFila ? conferirHoje() : null]);
      } while (deNovo);
    } catch {
      /* a próxima mudança (ou a volta para a aba) confere de novo */
    } finally {
      conferindo = false;
    }
  };

  canal = ouvir({
    url: CONFIG.SUPABASE_URL,
    chave: CONFIG.SUPABASE_ANON,
    topico: "painel",
    privado: true, // só administrador entra (policy em realtime.messages)
    token: async () => (await token()) || "",
    aoEstado: (estado) => {
      selo.dataset.estado = estado;
      selo.title = estado === "ao-vivo"
        ? "Ao vivo: o que mudar no banco aparece aqui sozinho"
        : "Reconectando… os dados continuam sendo conferidos ao voltar para a aba";
    },
    aoMudar: ({ tabela }) => {
      if (!tabela || ["pedidos_site", "licencas", "clientes", "assinatura_pedidos"].includes(tabela)) filaTambem = true;
      if (tabela === "hub_lancamentos" || tabela === "hub_versoes") conferirPendente();
      conferirAgora();
    },
  });
  conferirHoje();
  conferirPendente();
}

function desligarTempoReal() {
  canal?.parar();
  canal = null;
  filaAntes = null;
}

/**
 * O selo de Hoje fica certo em qualquer aba (assinatura para confirmar,
 * pagamento pendente, pedido antigo) e avisa quando chega algo novo.
 */
async function conferirHoje() {
  try {
    const [pedidos, mensalidades, pedidosLoja] = await Promise.all([
      ler("painel_assinatura_pedidos", { filtros: { situacao: "eq.aguardando" }, ordem: "criado_em.desc", fresco: true })
        .catch(() => []),
      ler("painel_mensalidades", { ordem: "criado_em.desc", fresco: true }).catch(() => []),
      ler("pedidos_abertos", { fresco: true }).catch(() => []),
    ]);
    const quantos = urgentes(montarFila({ pedidos, mensalidades, pedidosLoja }));
    if (filaAntes !== null && pedidos.length > filaAntes) {
      recado(pedidos.length - filaAntes === 1 ? "Chegou um pedido de assinatura para confirmar." : "Chegaram pedidos de assinatura.", "ok");
    }
    filaAntes = pedidos.length;
    marcarHoje(quantos);
  } catch {
    /* o selo espera a próxima */
  }
}

/** O selo de Atualizações: há versão esperando a sua decisão. */
async function conferirPendente() {
  try {
    const [lancamentos, versoes] = await Promise.all([
      ler("hub_lancamentos", { ordem: "criado_em.desc" }), ler("hub_versoes", { limite: 1 }),
    ]);
    $("selo-hub").hidden = !versaoPendente(lancamentos, String(versoes?.[0]?.versao || ""));
  } catch {
    /* o selo espera a próxima */
  }
}

// voltou para a aba (ou o computador acordou): confere o que pode ter mudado
document.addEventListener("visibilitychange", () => {
  if (document.hidden || $("painel").hidden) return;
  conferirTudo().catch(() => {});
  conferirHoje();
  conferirPendente();
});

// Quem está online muda sem passar pelo tempo real: cada Hub bate de 2 em 2
// minutos, e avisar cada batida redesenharia o painel à toa. A leitura confere
// em segundo plano e só redesenha se algo mudou (aoMudarDados).
const TELAS_COM_PRESENCA = new Set(["hoje", "clientes", "hub"]);
setInterval(() => {
  if (document.hidden || $("painel").hidden || !TELAS_COM_PRESENCA.has(telaAtual())) return;
  lerPresenca().catch(() => {});
}, 60_000);

// ================================================================= gaveta ====
const gaveta = $("gaveta");

for (const alvo of gaveta.querySelectorAll("[data-fechar]")) {
  alvo.addEventListener("click", fecharGaveta);
}
document.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape" && !gaveta.hidden) fecharGaveta();
});

/** Abre a ficha (do cliente, do anúncio) por cima da tela. */
export function abrirGaveta({ acima = "", titulo = "", conteudo }) {
  $("gaveta-acima").textContent = acima;
  $("gaveta-titulo").textContent = titulo;
  // Pelo mesmo motivo da tela: a ficha desenha numa folha própria. Abrir outra
  // troca a folha, e a que ainda estava carregando escreve num nó solto.
  const folha = document.createElement("div");
  folha.append(conteudo ?? carregando());
  limpar($("gaveta-conteudo")).append(folha);
  gaveta.hidden = false;
  document.body.style.overflow = "hidden";
  return folha;
}

/**
 * Troca a ficha aberta por uma versão nova, sem piscar — mas só se ninguém
 * abriu outra ficha (ou fechou a gaveta) enquanto a nova era montada.
 */
export function substituirNaGaveta(antiga, nova, titulo) {
  const area = $("gaveta-conteudo");
  if (gaveta.hidden || area.firstElementChild !== antiga) return false;
  if (titulo) $("gaveta-titulo").textContent = titulo;
  area.replaceChildren(nova);
  return true;
}

export const folhaDaGaveta = () => (gaveta.hidden ? null : $("gaveta-conteudo").firstElementChild);

export function fecharGaveta() {
  gaveta.hidden = true;
  document.body.style.overflow = "";
}

/** O selo vermelho de Hoje: o que não pode esperar. */
export function marcarHoje(quantos) {
  const selo = $("selo-hoje");
  selo.textContent = quantos > 9 ? "9+" : String(quantos || "");
  selo.hidden = !quantos;
}

// =================================================================== abrir ===
if (sessaoCompleta()) {
  abrirPainel();
} else {
  // sessao que parou antes do codigo (aba fechada no meio) nao vale: recomeca
  if (sessao()?.token) sair();
  mostrarEntrada();
}
