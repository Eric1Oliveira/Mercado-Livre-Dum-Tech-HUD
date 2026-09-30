// Liga o motor do kit (kit.js) na página.
//
// Só o que é de tela mora aqui: desenhar os módulos, o grafo das integrações,
// o resumo e o envio do pedido. Regra de negócio nenhuma — ela está em kit.js,
// que é testado sem navegador.

import {
  abrirPagamento, carregarCatalogo, conferirCupom, cupomDaURL, jaTemDaURL, kitDaURL, reconhecer,
  registrarPedido, tokenDaURL,
} from "./api.js";
import { guardarPedido } from "./pagamento.js";
import { CONFIG } from "./config.js";
import { INTEGRACOES, MODULOS, SEMPRE, catalogoLocal, moduloDe } from "./dados.js";
import {
  alternar, aplicarCombo, comboRecemFechado, contarLigacoes, criarKit, descontoDoCupom,
  dinheiro, escolherKit, integracoes, pedido, resumo, sugestao,
} from "./kit.js";
import {
  catalogoLembrado, esquecer, lembrado, lembrar, lembrarCatalogo,
} from "./memoria.js";
import { ouvir } from "./tempo-real.js";

const $ = (id) => document.getElementById(id);
const svgNS = "http://www.w3.org/2000/svg";
const suave = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// O icone do ramo: o modulo que mais "diz" o negocio. Kit com os 7 e o grid.
const ICONE_DO_RAMO = ["ORDENS", "AGENDA", "ORCAMENTOS", "VENDAS", "ESTOQUE", "FINANCEIRO", "CLIENTES"];
let kit = null;
// a barra de valor some quando a secao de fechamento aparece: dois totais na
// mesma tela e ruido, nao reforco
let fecharAVista = false;
let cliente = null; // quem chegou pelo Hub, quando chegou
let jaRevelou = false; // os cartoes so entram animados na primeira pintura
let catalogoBuscadoEm = 0;
// o cupom mora aqui em cima: a abertura da pagina ja desenha o total com ele
let cupom = null;                   // {codigo, tipo, valor, descricao} ja conferido
let cupomPendente = cupomDaURL();   // veio no link de um parceiro: ?cupom=X
let pedidoAberto = null; // {assinatura, id, total}: o pedido gravado que ainda nao virou link

// ============================================================== abertura ===
(async function iniciar() {
  if (suave) document.documentElement.classList.add("anima");
  desenharPontes();
  desenharInclui();

  // 1. PINTA NA HORA. O ultimo catalogo do servidor (ou o de seguranca, que vem
  //    junto com a pagina) e quem o navegador lembra estao a um `localStorage`
  //    de distancia: nada aqui pode esperar a rede.
  cliente = lembrado(armazem());
  kit = criarKit(catalogoLembrado(armazem()) ?? catalogoLocal(), quemJaTem(cliente));
  // um kit pode chegar pronto pela URL (?kit=estoque,vendas): serve para o Hub
  // sugerir uma combinacao e para alguem compartilhar o que montou. So entra
  // codigo de modulo que existe - o resto da URL e texto de um estranho.
  for (const codigo of kitDaURL()) {
    if (moduloDe(codigo)) kit = alternar(kit, codigo);
  }
  if (cliente || kit.jaTem.length) saudar(cliente, kit.jaTem);
  desenharModulos();
  desenharKits();
  desenharNegocio();
  atualizar();

  // chegou com modulos marcados (o "Comprar" de dentro do Hub, ou um link de
  // anuncio): leva direto ao montador, com o carrinho a vista
  if (kit.escolhidos.length) {
    requestAnimationFrame(() => document.getElementById("montador")?.scrollIntoView({ block: "start" }));
  }

  // 2. DEPOIS, sem pressa, o servidor corrige preco e identidade. Quem chega
  //    pelo Hub traz o codigo na URL (15 minutos, uso unico); dali em diante o
  //    navegador lembra - ninguem faz login duas vezes, nem uma.
  const [catalogo, doHub] = await Promise.all([
    carregarCatalogo(),
    reconhecer(tokenDaURL()),
  ]);

  if (doHub) {
    cliente = doHub;
    lembrar(armazem(), doHub);
  }
  kit = { ...kit, jaTem: quemJaTem(cliente) };
  if (cliente || kit.jaTem.length) saudar(cliente, kit.jaTem);
  aplicarCatalogo(catalogo, { destacar: false });

  cupomDoLink();

  // 3. E A PARTIR DAI, AO VIVO: mudou preco no painel, o banco avisa e a pagina
  //    busca de novo - sem ninguem apertar F5.
  ligarTempoReal();
})();

/** Troca o catalogo na tela. Preco que mudou pisca uma vez, de leve. */
function aplicarCatalogo(catalogo, { destacar = true } = {}) {
  catalogoBuscadoEm = Date.now();
  if (catalogo.local && !kit.catalogo.local) return; // servidor piscou: fica o que ja veio dele

  const precoAntes = new Map(kit.catalogo.produtos.map((p) => [p.codigo, Number(p.preco)]));
  const mudouAlgo = JSON.stringify([kit.catalogo.produtos, kit.catalogo.combos]) !==
                    JSON.stringify([catalogo.produtos, catalogo.combos]);

  const aVenda = new Set(catalogo.produtos.map((p) => p.codigo));
  kit = {
    ...kit,
    catalogo,
    // modulo que saiu de linha sai do kit tambem: o servidor recusaria o pedido
    escolhidos: catalogo.local ? kit.escolhidos : kit.escolhidos.filter((c) => aVenda.has(c)),
  };
  if (!catalogo.local) lembrarCatalogo(armazem(), catalogo);

  $("rodape-versao").textContent = catalogo.local
    ? "catálogo local"
    : `${catalogo.produtos.length} módulos no catálogo`;

  if (!mudouAlgo) return;
  desenharModulos();
  desenharKits();
  desenharNegocio();
  atualizar();

  if (!destacar) return;
  for (const produto of catalogo.produtos) {
    if (precoAntes.has(produto.codigo) && precoAntes.get(produto.codigo) === Number(produto.preco)) continue;
    const preco = document.querySelector(`.modulo[data-codigo="${produto.codigo}"] .preco`);
    preco?.classList.add("preco-mudou");
  }
}

function ligarTempoReal() {
  // Varios avisos seguidos viram uma busca so - e sem setTimeout: aba em segundo
  // plano tem o relogio segurado pelo navegador (ate 1 s), e o preco demoraria.
  // Chegou aviso com uma busca no meio do caminho? Busca de novo quando ela acabar.
  let buscando = false;
  let deNovo = false;
  const buscarDeNovo = async () => {
    if (buscando) {
      deNovo = true;
      return;
    }
    buscando = true;
    try {
      do {
        deNovo = false;
        aplicarCatalogo(await carregarCatalogo());
      } while (deNovo);
    } finally {
      buscando = false;
    }
  };

  ouvir({
    url: CONFIG.SUPABASE_URL,
    chave: CONFIG.SUPABASE_ANON,
    topico: "catalogo",
    aoMudar: buscarDeNovo,
  });

  // rede de seguranca: aba que volta a ficar visivel confere (se o aviso se
  // perdeu com o computador dormindo, a pessoa nao fica com preco velho)
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && Date.now() - catalogoBuscadoEm > 60_000) buscarDeNovo();
  });
}

/** O que a pessoa ja comprou: do Hub, do navegador, ou do ?tem= da URL. */
function quemJaTem(pessoa) {
  return pessoa?.produtos?.length ? pessoa.produtos : jaTemDaURL();
}

function saudar(pessoa, jaTem) {
  const caixa = $("reconhecido");
  const nomes = jaTem.map((c) => moduloDe(c)?.nome ?? c);
  // sem nome, o selo e o título diriam a mesma frase duas vezes
  const primeiroNome = (pessoa?.nome || "").trim().split(" ")[0];
  $("reconhecido-avatar").textContent = (primeiroNome || "D").charAt(0).toUpperCase();
  // a boas-vindas e o titulo do bloco - e ele abre a pagina
  $("reconhecido-nome").textContent = primeiroNome
    ? `Bem-vindo de volta, ${primeiroNome}!`
    : "Bem-vindo de volta!";

  const oQueTem = nomes.length
    ? "Estes módulos já são seus — deixamos marcados. Escolha só o que falta."
    : "Reconhecemos o seu acesso pelo DumTech Hub.";
  $("reconhecido-nota").textContent = pessoa?.doNavegador
    ? `${oQueTem} (lembramos deste navegador)`
    : oQueTem;

  // o que ele já tem vira pastilha com a cor e o ícone do próprio módulo
  const pastilhas = $("reconhecido-tem");
  pastilhas.innerHTML = "";
  for (const codigo of jaTem) {
    const modulo = moduloDe(codigo);
    if (!modulo) continue;
    const pastilha = document.createElement("span");
    pastilha.className = "pilula-modulo";
    pastilha.style.setProperty("--cor", modulo.cor);
    pastilha.innerHTML = `${svgIcone(modulo.icone, 2, 14)} ${modulo.nome}`;
    pastilhas.appendChild(pastilha);
  }

  // quem foi reconhecido tem de conseguir deixar de ser, na mesma linha
  $("reconhecido-sair").hidden = !pessoa?.email;
  caixa.dataset.visivel = "sim";

  if (pessoa?.nome) $("campo-nome").value = pessoa.nome;
  if (pessoa?.email) $("campo-email").value = pessoa.email;
}

function armazem() {
  try {
    return window.localStorage;
  } catch {
    return null; // navegador anonimo ou armazenamento bloqueado
  }
}

$("reconhecido-sair").addEventListener("click", () => {
  esquecer(armazem());
  location.href = location.pathname; // recomeça limpo, sem token na URL
});

/** Blocos que entram quando a página chega neles (uma vez só). */
function revelar(alvos) {
  if (!suave || !("IntersectionObserver" in window)) return;
  const olho = new IntersectionObserver((entradas, observador) => {
    for (const entrada of entradas) {
      if (!entrada.isIntersecting) continue;
      entrada.target.dataset.visto = "sim";
      observador.unobserve(entrada.target);
    }
  }, { rootMargin: "0px 0px -12% 0px", threshold: .08 });

  const lista = [...(alvos ?? document.querySelectorAll("[data-revelar]"))];
  for (const alvo of lista) {
    if (alvo.dataset.visto !== "sim") olho.observe(alvo);
  }

  // Rede de segurança: animação nenhuma pode esconder conteúdo. Se o
  // observador não disparar (impressão, captura de tela inteira, navegador
  // esquisito), tudo aparece assim mesmo - e rápido: meio segundo é o limite
  // entre "entrou animado" e "sumiu".
  setTimeout(() => {
    for (const alvo of lista) alvo.dataset.visto = "sim";
  }, 500);
}

// =============================================================== módulos ===
function desenharModulos() {
  const area = $("modulos");
  area.innerHTML = "";

  for (const modulo of MODULOS) {
    const preco = precoDe(modulo.codigo);
    const tem = kit.jaTem.includes(modulo.codigo);
    // o catalogo do servidor manda: modulo fora dele saiu de linha
    const aVenda = kit.catalogo.local || kit.catalogo.produtos.some((p) => p.codigo === modulo.codigo);

    const cartao = document.createElement("button");
    cartao.type = "button";
    cartao.className = "modulo";
    cartao.style.setProperty("--cor", modulo.cor);
    // os cartões entram em cascata quando a grade aparece - mas só da primeira
    // vez: redesenhar (quando o servidor manda os preços) não pode piscar
    cartao.setAttribute("data-revelar", "");
    cartao.style.setProperty("--atraso", `${MODULOS.indexOf(modulo) * 55}ms`);
    if (jaRevelou) cartao.dataset.visto = "sim";
    cartao.dataset.codigo = modulo.codigo;
    cartao.dataset.jaTem = tem ? "sim" : "nao";
    cartao.dataset.aVenda = aVenda ? "sim" : "nao";
    cartao.setAttribute("aria-pressed", "false");
    if (tem || !aVenda) cartao.setAttribute("aria-disabled", "true");

    cartao.innerHTML = `
      <div class="cabeca">
        <span class="chip">${svgIcone(modulo.icone)}</span>
        <h3>${modulo.nome}</h3>
        <span class="marca-estado">${svgIcone("M5 12.5 10 17.5 19.5 7", 2.4)}</span>
      </div>
      <p>${modulo.descricao}</p>
      <p class="detalhe">${modulo.detalhe}</p>
      <div class="rodape">
        ${tem
          ? '<span class="selo-tem">Você já tem</span>'
          : !aVenda
            ? '<span class="preco-nota">Indisponível no momento</span>'
            : `<span class="preco">${dinheiro(preco)}</span>
               <span class="preco-nota">uma vez só</span>`}
      </div>`;

    if (!tem && aVenda) cartao.addEventListener("click", () => {
      const antes = kit;
      kit = alternar(kit, modulo.codigo);
      // marcando um a um, o conjunto virou combo: isso merece ser mostrado.
      // Clicar no CARTAO do kit tambem fecha combo, e por isso nao comemora -
      // ninguem se surpreende com o que acabou de pedir.
      const fechou = comboRecemFechado(antes, kit);
      atualizar();
      if (fechou) comemorarCombo();
    });

    area.appendChild(cartao);
  }
  revelar(area.querySelectorAll("[data-revelar]"));
  jaRevelou = true;
}

// ============================================================ kit por ramo ===

/**
 * "Qual e o seu negocio?" no topo da pagina. Cada kit que tem ramo no painel
 * vira um botao; tocar monta o kit no carrinho e leva ao montador - quem
 * chegou de um anuncio decide em um toque, sem entender o que e cada modulo.
 */
function desenharNegocio() {
  const caixa = $("negocio");
  const area = $("negocio-lista");
  area.innerHTML = "";
  const ramos = (kit.catalogo.combos ?? [])
    .filter((c) => String(c.ramo || "").trim())
    .sort((a, b) => a.produtos.length - b.produtos.length || a.preco - b.preco);
  caixa.hidden = ramos.length === 0;

  // dois ramos com o mesmo icone parecem o mesmo botao. O kit maior (mais
  // especifico: a oficina, e nao o prestador) escolhe primeiro.
  const iconeDe = new Map();
  const usados = new Set();
  for (const combo of [...ramos].sort((a, b) => b.produtos.length - a.produtos.length)) {
    if (combo.produtos.length >= MODULOS.length) continue;   // "quero tudo" e o grid
    const candidatos = ICONE_DO_RAMO.filter((c) => combo.produtos.includes(c));
    const escolhido = candidatos.find((c) => !usados.has(c)) ?? candidatos[0];
    usados.add(escolhido);
    iconeDe.set(combo.codigo, escolhido);
  }
  for (const combo of ramos) {
    const principal = iconeDe.get(combo.codigo) ?? null;
    const modulo = principal ? moduloDe(principal) : null;
    const icone = modulo?.icone ?? "M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z";
    const cor = modulo?.cor ?? "var(--violeta)";

    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "ramo";
    botao.style.setProperty("--cor", cor);
    // ramo, nome e preco vem do painel: texto, nunca marcacao
    botao.innerHTML = `
      <span class="chip">${svgIcone(icone)}</span>
      <span class="ramo-texto">
        <strong>${escapar(combo.ramo)}</strong>
        <small>${escapar(combo.nome)} · ${escapar(dinheiro(combo.preco))}</small>
      </span>
      <span class="ramo-seta">${svgIcone("M9.5 5.5 16 12l-6.5 6.5", 2.2)}</span>`;
    botao.addEventListener("click", () => {
      kit = escolherKit(kit, combo.codigo);
      atualizar();
      document.getElementById("montador")?.scrollIntoView({ block: "start", behavior: suave ? "smooth" : "auto" });
    });
    area.appendChild(botao);
  }
}

// ============================================================ kits prontos ===
/**
 * A vitrine de kits. Cada cartao e o mesmo `.modulo` da pagina (mesma borda,
 * raio e sombra), com a economia em destaque. Clicar marca os modulos do kit;
 * quem decide o preco continua sendo `resumo()` - o mesmo caminho de quem
 * marca modulo a modulo, entao os dois nunca discordam.
 */
function desenharKits() {
  const caixa = $("kits-prontos");
  const area = $("kits-lista");
  area.innerHTML = "";

  const precoAvulso = (codigos) => codigos.reduce((soma, c) => soma + precoDe(c), 0);
  const vitrine = (kit.catalogo.combos ?? [])
    .map((combo) => {
      const faltam = combo.produtos.filter((c) => !kit.jaTem.includes(c));
      return { ...combo, faltam, avulso: precoAvulso(faltam) };
    })
    // so kit que ainda vale a pena para ESTA pessoa: dois modulos ou mais que ela
    // nao tem, e mais barato que compra-los separado
    .filter((combo) => combo.faltam.length >= 2 && combo.avulso > Number(combo.preco))
    .sort((a, b) => a.produtos.length - b.produtos.length || a.preco - b.preco);

  caixa.hidden = vitrine.length === 0;
  for (const combo of vitrine) {
    const economia = combo.avulso - Number(combo.preco);
    const porcento = Math.round((economia / combo.avulso) * 100);
    const cartao = document.createElement("button");
    cartao.type = "button";
    cartao.className = "modulo kit-pronto";
    cartao.dataset.combo = combo.codigo;
    cartao.setAttribute("aria-pressed", "false");
    // nome, frase e preco vem do painel: viram texto, nunca marcacao
    cartao.innerHTML = `
      <div class="cabeca">
        <span class="kit-selo">Kit · ${combo.produtos.length} módulos</span>
        <span class="kit-desconto">−${porcento}%</span>
        <span class="marca-estado">${svgIcone("M5 12.5 10 17.5 19.5 7", 2.4)}</span>
      </div>
      <h3>${escapar(combo.nome)}</h3>
      ${combo.descricao ? `<p>${escapar(combo.descricao)}</p>` : ""}
      <div class="kit-modulos">${combo.produtos.map((codigo) => {
        const m = moduloDe(codigo);
        return m ? `<span class="kit-chip" style="--cor:${m.cor}" title="${escapar(m.nome)}">${svgIcone(m.icone, 1.9)}${escapar(m.nome)}</span>` : "";
      }).join("")}</div>
      <div class="rodape">
        <s class="preco-antes">${escapar(dinheiro(combo.avulso))}</s>
        <span class="preco">${escapar(dinheiro(combo.preco))}</span>
        <span class="preco-nota">uma vez só</span>
      </div>`;
    cartao.addEventListener("click", () => {
      kit = escolherKit(kit, combo.codigo);
      atualizar();
    });
    area.appendChild(cartao);
  }
}

// ================================================================= grafo ===
function posicoes() {
  // acompanha o viewBox do <svg id="grafo"> (340 x 300)
  const centro = { x: 170, y: 146 };
  const raio = 98;
  const lugares = {};
  MODULOS.forEach((modulo, i) => {
    const angulo = (i / MODULOS.length) * Math.PI * 2 - Math.PI / 2;
    lugares[modulo.codigo] = {
      x: centro.x + Math.cos(angulo) * raio,
      y: centro.y + Math.sin(angulo) * raio,
      rotulo: {
        x: centro.x + Math.cos(angulo) * (raio + 26),
        y: centro.y + Math.sin(angulo) * (raio + 26) + 3,
      },
      cor: modulo.cor,
      nome: modulo.nome,
    };
  });
  return { centro, lugares };
}

function desenharGrafo() {
  const grafo = $("grafo");
  const { centro, lugares } = posicoes();
  const ativos = new Set([...kit.escolhidos, ...kit.jaTem]);
  const acesas = new Map();

  for (const integracao of integracoes(kit)) {
    if (integracao.estado !== "ativa") continue;
    for (const ligacao of integracao.ligacoes) {
      acesas.set(`${ligacao.de}-${ligacao.para}`, integracao.de);
    }
  }

  grafo.innerHTML = `<title id="grafo-titulo">Ligações entre os módulos escolhidos</title>`;

  // primeiro as linhas, para os nós ficarem por cima
  for (const integracao of INTEGRACOES) {
    for (const destino of integracao.para) {
      const a = lugares[integracao.de];
      const b = lugares[destino];
      if (!a || !b) continue;

      const acesa = acesas.has(`${integracao.de}-${destino}`);
      const curva = document.createElementNS(svgNS, "path");
      curva.setAttribute("d", `M${a.x} ${a.y} Q${centro.x} ${centro.y} ${b.x} ${b.y}`);
      curva.setAttribute("class", acesa ? "fio-ligacao" : "fio-ligacao fio-dormente");
      if (acesa) {
        const cor = moduloDe(integracao.de).cor;
        curva.setAttribute("stroke", cor);
        curva.setAttribute("opacity", ".85");
        if (suave) {
          animarFio(curva);
          grafo.appendChild(correr(curva.getAttribute("d"), cor, acesas.size));
        }
      } else {
        curva.setAttribute("opacity", ativos.size ? ".85" : ".5");
      }
      grafo.appendChild(curva);
    }
  }

  for (const modulo of MODULOS) {
    const lugar = lugares[modulo.codigo];
    const dentro = ativos.has(modulo.codigo);

    const grupo = document.createElementNS(svgNS, "g");
    grupo.setAttribute("class", dentro ? "no" : "no no-fora");

    const circulo = document.createElementNS(svgNS, "circle");
    circulo.setAttribute("cx", lugar.x);
    circulo.setAttribute("cy", lugar.y);
    circulo.setAttribute("r", dentro ? 15 : 12);
    circulo.setAttribute("fill", dentro ? modulo.cor : "#fff");
    circulo.setAttribute("stroke", modulo.cor);
    circulo.setAttribute("stroke-width", "2");
    grupo.appendChild(circulo);

    const icone = document.createElementNS(svgNS, "path");
    icone.setAttribute("d", modulo.icone);
    icone.setAttribute("fill", "none");
    icone.setAttribute("stroke", dentro ? "#fff" : modulo.cor);
    icone.setAttribute("stroke-width", "2");
    icone.setAttribute("stroke-linecap", "round");
    icone.setAttribute("stroke-linejoin", "round");
    icone.setAttribute("transform",
      `translate(${lugar.x - 8} ${lugar.y - 8}) scale(.667)`);
    grupo.appendChild(icone);

    const texto = document.createElementNS(svgNS, "text");
    texto.setAttribute("x", lugar.rotulo.x);
    texto.setAttribute("y", lugar.rotulo.y);
    texto.setAttribute("text-anchor",
      lugar.rotulo.x > 190 ? "start" : lugar.rotulo.x < 150 ? "end" : "middle");
    texto.textContent = modulo.nome;
    grupo.appendChild(texto);

    grafo.appendChild(grupo);
  }
}

/** O ponto que corre pela ligação acesa: é o kit se montando na sua frente. */
function correr(caminho, cor, ordem = 0) {
  const ponto = document.createElementNS(svgNS, "circle");
  ponto.setAttribute("r", "3.1");
  ponto.setAttribute("class", "particula");
  ponto.setAttribute("fill", cor);
  ponto.setAttribute("stroke", "#fff");

  const movimento = document.createElementNS(svgNS, "animateMotion");
  movimento.setAttribute("dur", "2.8s");
  movimento.setAttribute("repeatCount", "indefinite");
  movimento.setAttribute("path", caminho);
  movimento.setAttribute("calcMode", "linear");
  // as ligações não pulsam todas juntas: cada uma entra no seu tempo
  movimento.setAttribute("begin", `${(ordem % 4) * 0.45}s`);
  ponto.appendChild(movimento);
  return ponto;
}

function animarFio(curva) {
  const tamanho = curva.getTotalLength ? curva.getTotalLength() : 200;
  curva.style.strokeDasharray = tamanho;
  curva.style.strokeDashoffset = tamanho;
  curva.animate(
    [{ strokeDashoffset: tamanho }, { strokeDashoffset: 0 }],
    { duration: 520, easing: "cubic-bezier(.2,.7,.3,1)", fill: "forwards" }
  );
}

// ========================================================== integrações ====
function desenharIntegracoes() {
  const lista = $("integracoes-lista");
  const dados = integracoes(kit);
  const ordem = { ativa: 0, dormente: 1, fora: 2 };
  lista.innerHTML = "";

  for (const item of [...dados].sort((a, b) => ordem[a.estado] - ordem[b.estado])) {
    if (item.estado === "fora") continue;
    const bloco = document.createElement("div");
    bloco.className = "integracao";
    bloco.dataset.estado = item.estado;
    const falta = item.faltando.map((c) => moduloDe(c)?.nome ?? c);
    bloco.innerHTML = `
      <div class="titulo"><span class="ponto"></span>${item.titulo}</div>
      <p>${item.estado === "ativa"
            ? item.ativa
            : `Falta ${listar(falta)} para isso acontecer sozinho.`}</p>`;
    lista.appendChild(bloco);
  }

  const total = contarLigacoes(kit);
  $("contador-numero").textContent = total;
  $("contador-texto").textContent = total === 1 ? "ligação ativa" : "ligações ativas";
  $("grafo-legenda").textContent = kit.escolhidos.length
    ? "As linhas coloridas são o que o seu kit já faz sozinho."
    : "Escolha um módulo para começar.";
}

// =============================================================== resumo ====
function desenharResumo() {
  const dados = resumo(kit);
  const alvos = [
    [$("resumo-itens"), "Nenhum módulo escolhido ainda."],
    [$("espelho-itens"), "Volte ao montador e escolha os módulos."],
  ];

  for (const [area, vazio] of alvos) {
    area.innerHTML = "";
    if (dados.vazio) {
      area.innerHTML = `<p class="resumo-vazio">${vazio}</p>`;
      continue;
    }
    for (const item of dados.itens) {
      const linha = document.createElement("div");
      linha.className = item.tipo === "combo" ? "resumo-item combo" : "resumo-item";
      // nome e preco vem do servidor: viram texto, nunca marcacao
      const nomes = item.tipo === "combo"
        ? `<span class="produtos-do-combo">${escapar(item.produtos
              .map((c) => moduloDe(c)?.nome ?? c).join(" · "))}</span>`
        : "";
      linha.innerHTML =
        `<span>${escapar(item.nome)}${nomes}</span><span>${escapar(dinheiro(item.preco))}</span>`;
      area.appendChild(linha);
    }
  }

  // cupom aplicado: uma linha a menos no total - a mesma conta do banco
  const desconto = dados.vazio ? 0 : descontoDoCupom(cupom, dados.total);
  if (desconto > 0) {
    for (const [area] of alvos) {
      const linha = document.createElement("div");
      linha.className = "resumo-item cupom-linha";
      linha.innerHTML = `<span>Cupom ${escapar(cupom.codigo)}</span><span>− ${escapar(dinheiro(desconto))}</span>`;
      area.appendChild(linha);
    }
  }

  const aviso = $("kit-reconhecido");
  const combo = dados.itens.find((i) => i.tipo === "combo");
  aviso.hidden = !combo;
  if (combo) {
    aviso.textContent = "";
    aviso.append("Os módulos que você marcou formam o ");
    const nome = document.createElement("b");
    nome.textContent = combo.nome;
    aviso.append(nome, " — o preço promocional entrou sozinho.");
  }

  const aPagar = Math.round((dados.total - desconto) * 100) / 100;
  mostrarValor($("total-valor"), aPagar);
  mostrarValor($("espelho-total"), aPagar);
  const economia = $("total-economia");
  economia.hidden = dados.economia <= 0;
  economia.textContent = `você economiza ${dinheiro(dados.economia)}`;
  $("ir-para-fechar").disabled = dados.vazio;

  desenharBarraDeValor(dados, combo, aPagar);
}

// ---------------------------------------------------------- comemoracao ----
/**
 * O cliente fechou um combo sem pedir. A sensacao de premio vem do numero
 * subindo e do selo aparecendo - nada voando pela tela.
 *
 * O movimento e so CSS (classe que entra e sai). Quem pediu menos movimento no
 * sistema ja e atendido pelo bloco de prefers-reduced-motion, que zera toda
 * animacao: o selo e a economia continuam aparecendo, so nao se mexem.
 */
function comemorarCombo() {
  // a caixa E a barra: quem esta com a tela rolada ve a comemoracao embaixo,
  // quem esta no topo ve no cartao. Nunca acontece so fora de vista.
  const alvos = [$("kit-reconhecido"),
                 $("barra-kit"), $("barra-total"), $("barra-economia")];
  for (const alvo of alvos) {
    if (!alvo) continue;
    alvo.dataset.comemorar = "nao";
    // forca o navegador a reiniciar a animacao quando dois combos fecham
    // seguidos; sem isto o segundo nao anima
    void alvo.offsetWidth;
    alvo.dataset.comemorar = "sim";
  }
}

// ------------------------------------------------------- barra de valor ----
/** O total acompanha quem esta escolhendo, ancorado no rodape. */
function desenharBarraDeValor(dados, combo, aPagar) {
  const barra = $("barra-valor");
  const temKit = !dados.vazio;
  barra.dataset.visivel = temKit && !fecharAVista ? "sim" : "nao";
  barra.setAttribute("aria-hidden", temKit ? "false" : "true");
  if (!temKit) return;

  $("barra-kit").textContent = combo ? combo.nome : "Seu kit";
  const quantos = dados.escolhidos.length;
  $("barra-itens").textContent = `${quantos} ${quantos === 1 ? "módulo" : "módulos"}`;
  mostrarValor($("barra-total"), aPagar);

  const economia = $("barra-economia");
  economia.hidden = dados.economia <= 0;
  economia.textContent = `economiza ${dinheiro(dados.economia)}`;
}

function desenharOferta() {
  const oferta = sugestao(kit);
  const caixa = $("oferta");
  if (!oferta) {
    caixa.dataset.visivel = "nao";
    return;
  }
  const faltam = oferta.faltando.map((c) => moduloDe(c)?.nome ?? c);
  $("oferta-titulo").textContent = `${oferta.nome}: leve também ${listar(faltam)}`;
  // o que importa para quem esta decidindo: quanto o total muda, e nao o
  // preco do kit solto
  $("oferta-texto").textContent =
    `Seu total vai de ${dinheiro(oferta.totalAtual)} para ${dinheiro(oferta.totalNovo)}: ` +
    `${faltam.length === 1 ? "o módulo sai" : "os módulos saem"} por mais ${dinheiro(oferta.acrescimo)}, ` +
    `em vez de ${dinheiro(oferta.avulso)} separado.`;
  $("oferta-botao").onclick = () => {
    kit = aplicarCombo(kit, oferta.codigo);
    atualizar();
  };
  caixa.dataset.visivel = "sim";
}

function atualizar() {
  const reconhecido = resumo(kit).combo;
  for (const cartao of document.querySelectorAll(".kit-pronto")) {
    cartao.setAttribute("aria-pressed", cartao.dataset.combo === reconhecido ? "true" : "false");
  }
  for (const cartao of document.querySelectorAll(".modulo:not(.kit-pronto)")) {
    cartao.setAttribute(
      "aria-pressed",
      kit.escolhidos.includes(cartao.dataset.codigo) ? "true" : "false"
    );
  }
  desenharGrafo();
  desenharIntegracoes();
  desenharResumo();
  desenharOferta();
  if (cupomPendente && resumo(kit).total > 0 && !cupom) aplicarCupom(cupomPendente);
}

// ======================================================= partes estáticas ==
function desenharPontes() {
  const area = $("pontes");
  for (const integracao of INTEGRACOES) {
    const origem = moduloDe(integracao.de);
    const ponte = document.createElement("article");
    ponte.className = "ponte";
    ponte.innerHTML = `
      <div class="fluxo">
        <span class="pilula" style="--cor:${origem.cor}">${svgIcone(origem.icone, 2, 14)} ${origem.nome}</span>
        <span class="seta">${svgIcone("M4 12h14 M13 7l5 5-5 5", 2)}</span>
        ${integracao.para.map((codigo) => {
          const destino = moduloDe(codigo);
          return `<span class="pilula" style="--cor:${destino.cor}">${destino.nome}</span>`;
        }).join("")}
      </div>
      <h3>${integracao.titulo}</h3>
      <p>${integracao.ativa}</p>`;
    area.appendChild(ponte);
  }
}

function desenharInclui() {
  const area = $("inclui");
  for (const item of SEMPRE) {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="marca-ok">${svgIcone("M5 12.5 10 17.5 19.5 7", 2.4)}</span>
      <div><strong>${item.titulo}</strong><p>${item.texto}</p></div>`;
    area.appendChild(li);
  }
}

// =============================================================== envio =====
// a barra manda para o mesmo lugar que o botao do resumo
$("barra-fechar").addEventListener("click", () => $("ir-para-fechar").click());

// a barra se recolhe quando a secao de fechamento entra na tela
if ("IntersectionObserver" in window) {
  new IntersectionObserver((entradas) => {
    fecharAVista = entradas.some((e) => e.isIntersecting);
    const barra = $("barra-valor");
    if (barra.dataset.visivel === "sim" || fecharAVista) {
      barra.dataset.visivel = fecharAVista ? "nao" : (kit && !resumo(kit).vazio ? "sim" : "nao");
    }
  }, { threshold: 0.12 }).observe($("fechar"));
}

$("ir-para-fechar").addEventListener("click", () => {
  document.getElementById("fechar").scrollIntoView({ behavior: suave ? "smooth" : "auto" });
  $("campo-nome").focus({ preventScroll: true });
});

$("formulario").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const aviso = $("aviso-form");
  const botao = $("enviar");
  const nome = $("campo-nome").value.trim();
  const email = $("campo-email").value.trim();
  const telefone = $("campo-telefone").value.trim();
  const dados = resumo(kit);

  if (dados.vazio) return dizer(aviso, "erro", "Escolha ao menos um módulo no montador.");
  if (!nome) return dizer(aviso, "erro", "Digite o seu nome.");
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email)) {
    return dizer(aviso, "erro", "Confira o e-mail digitado.");
  }

  botao.disabled = true;
  $("ajuda-pagamento").hidden = true;
  dizer(aviso, "", "Abrindo o pagamento…");

  const escolha = pedido(kit);
  // o pedido gravado so e reaproveitado para o MESMO kit e e-mail: se o link
  // falhou, tentar de novo nao cria outro pedido na caixa de entrada
  const assinatura = JSON.stringify([email.toLowerCase(), escolha.produtos, escolha.combo, cupom?.codigo ?? ""]);
  if (pedidoAberto?.assinatura !== assinatura) {
    let resposta = null;
    try {
      resposta = await registrarPedido({
        nome, email, telefone,
        produtos: escolha.produtos,
        combo: escolha.combo,
        origem: cliente ? "hub" : "site",
        cupom: cupom?.codigo,
      });
    } catch (erro) {
      console.warn("Não foi possível registrar o pedido.", erro);
    }
    if (!resposta?.ok) {
      botao.disabled = false;
      if (String(resposta?.erro || "").startsWith("cupom_")) {
        // o banco nao aceitou o cupom (venceu, esgotou...): sai da conta e avisa
        cupom = null;
        atualizar();
        dizer($("cupom-aviso"), "erro", resposta.mensagem || "Este cupom não vale mais.");
      }
      return falhouPagamento(aviso, resposta?.mensagem || "Não conseguimos falar com o servidor agora. Tente de novo em instantes.",
                             { nome, dados, total: dados.total });
    }
    pedidoAberto = { assinatura, id: resposta.pedido, total: Number(resposta.total) };
  }

  const link = await abrirPagamento(pedidoAberto.id);
  if (!link?.ok || !/^https:\/\//.test(link.url || "")) {
    botao.disabled = false;
    // pedido que ja abriu link (ou expirou) nao abre outro: o proximo envio grava um novo
    if (["checkout_ja_criado", "pedido_expirado", "pedido_encerrado"].includes(link?.erro)) pedidoAberto = null;
    return falhouPagamento(aviso, link?.mensagem || "Não conseguimos abrir o pagamento agora. Tente de novo em instantes.",
                           { nome, dados, total: pedidoAberto?.total ?? dados.total });
  }

  guardarPedido(armazem(), pedidoAberto.id, link.segredo);
  dizer(aviso, "ok", `Pedido de ${dinheiro(pedidoAberto.total)} registrado. Levando você ao pagamento seguro…`);
  location.assign(link.url);
});

// ================================================================= cupom ===

$("cupom-abrir").addEventListener("click", () => {
  $("cupom-campo").hidden = false;
  $("cupom-abrir").hidden = true;
  $("campo-cupom").focus();
});
$("cupom-aplicar").addEventListener("click", () => aplicarCupom($("campo-cupom").value));
$("campo-cupom").addEventListener("keydown", (evento) => {
  if (evento.key !== "Enter") return;
  evento.preventDefault();          // Enter aqui aplica o cupom, nao envia o pedido
  aplicarCupom($("campo-cupom").value);
});

async function aplicarCupom(texto) {
  const codigo = String(texto || "").trim().toUpperCase();
  const aviso = $("cupom-aviso");
  if (!codigo) { cupom = null; atualizar(); return dizer(aviso, "", ""); }
  const total = resumo(kit).total;
  if (!(total > 0)) {
    cupomPendente = codigo;
    return dizer(aviso, "", `Monte o seu kit: o cupom ${codigo} entra sozinho no total.`);
  }
  cupomPendente = "";
  dizer(aviso, "", "Conferindo o cupom…");
  const r = await conferirCupom(codigo, $("campo-email").value.trim(), total);
  if (!r?.ok) {
    cupom = null;
    atualizar();
    return dizer(aviso, "erro", r?.mensagem || "Cupom não encontrado.");
  }
  cupom = { codigo: r.codigo, tipo: r.tipo, valor: Number(r.valor), descricao: r.descricao || "" };
  // veio de um link ou de outro caminho: o campo mostra o que esta valendo
  $("cupom-campo").hidden = false;
  $("cupom-abrir").hidden = true;
  $("campo-cupom").value = cupom.codigo;
  atualizar();
  const quanto = cupom.tipo === "percentual" ? `${cupom.valor}% de desconto` : `${dinheiro(cupom.valor)} de desconto`;
  dizer(aviso, "ok", `Cupom ${cupom.codigo} aplicado: ${cupom.descricao || quanto}.`);
}

/** Cupom do link: aparece preenchido e entra assim que houver kit. */
function cupomDoLink() {
  if (!cupomPendente) return;
  $("cupom-campo").hidden = false;
  $("cupom-abrir").hidden = true;
  $("campo-cupom").value = cupomPendente;
  if (resumo(kit).total > 0) aplicarCupom(cupomPendente);
  else dizer($("cupom-aviso"), "", `Cupom ${cupomPendente} guardado: ele entra quando você montar o kit.`);
}

/** O erro na tela e, se ele persistir, o WhatsApp como caminho de reserva. */
function falhouPagamento(aviso, texto, { nome, dados, total }) {
  dizer(aviso, "erro", texto);
  const ajuda = $("ajuda-pagamento");
  if (!CONFIG.WHATSAPP) return;
  const linhas = dados.itens.map((i) => `• ${i.nome} — ${dinheiro(i.preco)}`);
  ajuda.href = `https://wa.me/${CONFIG.WHATSAPP}?text=${encodeURIComponent([
    `Olá! Sou ${nome} e não consegui pagar meu kit DumTech pelo site:`,
    ...linhas,
    `Total: ${dinheiro(total)}`,
  ].join("\n"))}`;
  ajuda.hidden = false;
}

// ================================================================ apoio ====
/** O total conta até o valor novo — saltar de R$ 498 para R$ 699 não se lê. */
function mostrarValor(elemento, alvo) {
  const de = Number(elemento.dataset.valor || 0);
  elemento.dataset.valor = String(alvo);

  if (!suave || de === alvo) {
    elemento.textContent = dinheiro(alvo);
    return;
  }

  elemento.dataset.mudou = "sim";
  const comeco = performance.now();
  const duracao = 420;
  const passo = (agora) => {
    const t = Math.min(1, (agora - comeco) / duracao);
    const suavizado = 1 - Math.pow(1 - t, 3);
    elemento.textContent = dinheiro(de + (alvo - de) * suavizado);
    if (t < 1) requestAnimationFrame(passo);
    else setTimeout(() => { elemento.dataset.mudou = "nao"; }, 240);
  };
  requestAnimationFrame(passo);
}

function precoDe(codigo) {
  const produto = (kit?.catalogo.produtos ?? []).find((p) => p.codigo === codigo);
  return Number(produto?.preco ?? 0);
}

function svgIcone(caminho, espessura = 1.9, tamanho = 0) {
  const medida = tamanho ? ` width="${tamanho}" height="${tamanho}"` : "";
  return `<svg viewBox="0 0 24 24"${medida} fill="none" stroke="currentColor" stroke-width="${espessura}"
    stroke-linecap="round" stroke-linejoin="round"><path d="${caminho}"/></svg>`;
}

function escapar(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function listar(nomes) {
  if (nomes.length <= 1) return nomes[0] ?? "";
  return `${nomes.slice(0, -1).join(", ")} e ${nomes[nomes.length - 1]}`;
}

function dizer(alvo, tom, texto) {
  alvo.dataset.tom = tom;
  alvo.textContent = texto;
}

// a barra do topo ganha um fio quando a página rola
const topo = $("topo");
addEventListener("scroll", () => {
  topo.dataset.rolou = window.scrollY > 8 ? "sim" : "nao";
}, { passive: true });
