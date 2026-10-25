// O Hub no celular — os gráficos.
//
// SVG desenhado aqui mesmo, sem biblioteca: a página proíbe script de fora
// (Content-Security-Policy) e cada gráfico tem poucas dezenas de marcas.
//
// AS REGRAS (iguais em todo gráfico)
//   - uma cor de dado só, o violeta da marca; o contexto (a semana passada,
//     os outros dias) é cinza. Verde, âmbar e vermelho só onde o número É um
//     estado (o saldo abaixo de zero, o estoque acabando);
//   - um eixo só, grade em fio fino, rótulo só onde ajuda (agora, o maior);
//   - tocar e arrastar mostra o valor - e nada fica só no toque: cada gráfico
//     leva a tabela para leitor de tela;
//   - o que vem do Hub entra como TEXTO (textContent), nunca como HTML.
//
// COMO DESENHA
//   `criar(g)` monta a moldura (título, legenda, tabela) e devolve o elemento.
//   Linhas e colunas precisam da largura de verdade para o texto sair nítido:
//   `pintar(figura)` desenha depois que a figura está na página - e de novo
//   quando a tela gira.

import { compacto, escala, formatar, rotulosVisiveis } from "./celular.js?v=7";

const NS = "http://www.w3.org/2000/svg";
const especificacoes = new WeakMap();
//: o toque de cada desenho: redesenhar (girar a tela) desliga o do desenho velho
const toques = new WeakMap();

function el(tag, classe, texto) {
  const no = document.createElement(tag);
  if (classe) no.className = classe;
  if (texto !== undefined && texto !== null && texto !== "") no.textContent = texto;
  return no;
}

function svg(tag, atributos = {}, pai = null) {
  const no = document.createElementNS(NS, tag);
  for (const [nome, valor] of Object.entries(atributos)) {
    if (valor !== undefined && valor !== null) no.setAttribute(nome, String(valor));
  }
  if (pai) pai.append(no);
  return no;
}

const numeros = (lista) => (Array.isArray(lista) ? lista : []).map((v) => (typeof v === "number" ? v : null));

// --------------------------------------------------------------- moldura ---
/**
 * A figura de um gráfico do Hub, ou null se o tipo é desconhecido (Hub mais
 * novo que a página: o resto da tela continua de pé).
 *   semTitulo: o destaque já tem o rótulo grande em cima.
 */
export function criar(g, { semTitulo = false } = {}) {
  if (!g || typeof g !== "object") return null;
  const tipo = g.tipo;
  if (tipo === "ranking") return ranking(g);
  if (tipo === "etapas") return etapas(g);
  if (tipo !== "linhas" && tipo !== "colunas") return null;

  const figura = el("figure", `grafico grafico-${tipo}`);
  if (!semTitulo && g.titulo) figura.append(el("figcaption", "grafico-titulo", g.titulo));
  const area = el("div", "grafico-area");
  area.tabIndex = 0;
  area.setAttribute("aria-label", `${g.titulo || "Gráfico"}. Toque e arraste para ver os valores.`);
  figura.append(area);

  const series = tipo === "linhas" ? (g.series ?? []).filter((s) => s && Array.isArray(s.valores)) : [];
  // com "agora", a legenda leva o valor de cada linha neste minuto - e o
  // rotulo direto que nao colide com linha nenhuma
  const doAgora = g.agora ? numeros(g.agora.valores) : [];
  if (series.length > 1) figura.append(legenda(series, doAgora, g.formato));
  figura.append(tabela(g, series));
  especificacoes.set(figura, { ...g, series });
  return figura;
}

function legenda(series, valores = [], formato = "moeda") {
  const lista = el("ul", "grafico-legenda");
  series.forEach((s, i) => {
    const item = el("li");
    const chave = el("span", "legenda-chave");
    chave.dataset.serie = s.destaque ? "destaque" : `contexto-${i}`;
    item.append(chave, el("span", "", s.nome));
    if (typeof valores[i] === "number") item.append(el("strong", "legenda-valor", formatar(valores[i], formato)));
    lista.append(item);
  });
  return lista;
}

/**
 * O gêmeo acessível: os mesmos números, em tabela, para quem não vê o desenho.
 *
 * A tabela mora numa caixa de 1 px que corta: tabela não aceita largura menor
 * que o conteúdo, e solta ela alargava a página no celular (476 px numa tela
 * de 390) - o navegador afastava o zoom e o menu do topo "fugia".
 */
function tabela(g, series) {
  const caixa = el("div", "so-leitor");
  const t = el("table");
  caixa.append(t);
  t.append(el("caption", "", g.titulo || "Gráfico"));
  const cabeca = el("tr");
  cabeca.append(el("th", "", "Quando"));
  if (g.tipo === "linhas") series.forEach((s) => cabeca.append(el("th", "", s.nome)));
  else cabeca.append(el("th", "", "Valor"));
  const corpo = el("tbody");
  (g.rotulos ?? []).forEach((rotulo, i) => {
    const linha = el("tr");
    linha.append(el("th", "", g.dicas?.[i] || rotulo));
    const valores = g.tipo === "linhas" ? series.map((s) => s.valores[i]) : [g.valores?.[i]];
    valores.forEach((v) => linha.append(el("td", "", typeof v === "number" ? formatar(v, g.formato) : "—")));
    corpo.append(linha);
  });
  const thead = el("thead");
  thead.append(cabeca);
  t.append(thead, corpo);
  return caixa;
}

// ------------------------------------------------------------- desenhar ---
/** Desenha (ou redesenha) uma figura que já está na página. */
export function pintar(figura, { animar = false } = {}) {
  const g = especificacoes.get(figura);
  const area = figura.querySelector(".grafico-area");
  if (!g || !area) return;
  const largura = Math.round(area.clientWidth);
  if (largura < 120) return; // escondida (aba fechada): desenha quando aparecer
  if (area.dataset.largura === String(largura) && !animar) return;
  area.dataset.largura = String(largura);
  area.replaceChildren();
  toques.get(area)?.abort();
  toques.set(area, new AbortController());
  if (g.tipo === "linhas") linhas(area, g, largura, animar);
  else colunas(area, g, largura, animar);
}

/** Todas as figuras de um pedaço da tela - depois de entrar e ao girar. */
export function pintarTudo(raiz, opcoes) {
  raiz.querySelectorAll(".grafico-linhas, .grafico-colunas").forEach((f) => pintar(f, opcoes));
}

const ALTURA = { linhas: 176, colunas: 148 };
const EIXO_X = 22;
const TOPO = 16;

/** Os fios da grade e o zero - embaixo de tudo. */
function grade(desenho, e, y, largura) {
  const grupo = svg("g", { class: "grade" }, desenho);
  for (const marca of e.marcas) {
    const altura = y(marca);
    svg("line", { x1: 0, x2: largura, y1: altura, y2: altura, class: marca === 0 ? "eixo-zero" : "fio" }, grupo);
  }
}

/** Os numeros do eixo Y, no alto de cada fio - por cima das marcas, com contorno. */
function marcasY(desenho, e, y, formato) {
  const grupo = svg("g", { class: "eixo-y" }, desenho);
  for (const marca of e.marcas) {
    // o zero no chao do grafico e obvio; so ganha rotulo quando ha numero abaixo dele
    if (marca === 0 && e.menor >= 0) continue;
    const texto = svg("text", { x: 0, y: y(marca) - 4, class: "marca" }, grupo);
    texto.textContent = compacto(marca, formato);
  }
}

function rotulosX(desenho, rotulos, x, largura, altura, pontas = false) {
  const grupo = svg("g", { class: "eixo-x" }, desenho);
  // quantos cabem depende do tamanho do texto: "sex" cabe mais que "17/10"
  const maior = Math.max(...rotulos.map((r) => String(r).length), 1);
  const visiveis = rotulosVisiveis(rotulos.length, Math.max(2, Math.floor(largura / Math.max(36, maior * 7.5 + 18))));
  for (const i of visiveis) {
    // na linha o primeiro e o ultimo ponto encostam na borda; na coluna ha folga
    const ancora = !pontas ? "middle" : i === 0 ? "start" : i === rotulos.length - 1 ? "end" : "middle";
    const texto = svg("text", { x: x(i), y: altura - 5, "text-anchor": ancora }, grupo);
    texto.textContent = rotulos[i];
  }
}

// ---------------------------------------------------------------- linhas ---
function linhas(area, g, largura, animar) {
  const altura = ALTURA.linhas;
  const rotulos = g.rotulos ?? [];
  const n = rotulos.length;
  const series = g.series.map((s) => ({ ...s, valores: numeros(s.valores).slice(0, n) }));
  const agora = g.agora && typeof g.agora.posicao === "number" ? g.agora : null;
  const todos = series.flatMap((s) => s.valores).concat(numeros(agora?.valores));
  const e = escala(todos, { topo: g.formato === "moeda" ? 100 : 3, inteiros: g.formato !== "moeda" });

  const margem = 6;
  const baseY = altura - EIXO_X;
  const x = (i) => (n <= 1 ? largura / 2 : margem + (i / (n - 1)) * (largura - 2 * margem));
  const y = (v) => TOPO + (1 - (v - e.menor) / (e.maior - e.menor)) * (baseY - TOPO);
  // o presente cai entre duas marcas (10:40 fica entre "10h" e "11h")
  const xAgora = agora ? x(Math.min(agora.posicao, Math.max(n - 1, 0))) : null;

  const desenho = svg("svg", { viewBox: `0 0 ${largura} ${altura}`, width: largura, height: altura,
                               "aria-hidden": "true", class: animar ? "entrando" : "" });
  grade(desenho, e, y, largura);
  rotulosX(desenho, rotulos, x, largura, altura, true);

  const pontosDe = (s, indice) => {
    const pontos = [];
    s.valores.forEach((v, i) => pontos.push(v === null ? null : [x(i), y(v)]));
    // a linha de hoje termina no minuto de agora, e nao na hora cheia seguinte
    const doAgora = agora ? numeros(agora.valores)[indice] : null;
    if (s.destaque && agora && doAgora !== null) {
      while (pontos.length && pontos.at(-1) === null) pontos.pop();
      pontos.push([xAgora, y(doAgora)]);
    }
    return pontos;
  };
  const caminho = (pontos) => {
    let d = "";
    let novo = true;
    for (const p of pontos) {
      if (!p) { novo = true; continue; }
      d += `${novo ? "M" : "L"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`;
      novo = false;
    }
    return d;
  };

  // contexto primeiro (embaixo), destaque por cima
  const ordem = series.map((s, i) => ({ s, i })).sort((a, b) => Number(!!a.s.destaque) - Number(!!b.s.destaque));
  const finais = [];
  for (const { s, i } of ordem) {
    const pontos = pontosDe(s, i);
    const validos = pontos.filter(Boolean);
    if (!validos.length) continue;
    if (s.destaque) {
      // a lavagem embaixo da linha, ate o zero; abaixo do zero ela vira alerta
      const zeroY = y(Math.max(0, e.menor)).toFixed(1);
      const d = `${caminho(validos)}L${validos.at(-1)[0].toFixed(1)} ${zeroY}L${validos[0][0].toFixed(1)} ${zeroY}Z`;
      if (e.menor < 0) {
        const defs = svg("defs", {}, desenho);
        const id = Math.random().toString(36).slice(2, 8);
        svg("rect", { x: 0, y: 0, width: largura, height: y(0) }, svg("clipPath", { id: `acima-${id}` }, defs));
        svg("rect", { x: 0, y: y(0), width: largura, height: Math.max(0, baseY - y(0)) },
            svg("clipPath", { id: `abaixo-${id}` }, defs));
        svg("path", { d, class: "area", "clip-path": `url(#acima-${id})` }, desenho);
        svg("path", { d, class: "area-negativa", "clip-path": `url(#abaixo-${id})` }, desenho);
      } else {
        svg("path", { d, class: "area" }, desenho);
      }
    }
    const linha = svg("path", { d: caminho(pontos), class: s.destaque ? "linha destaque" : "linha contexto" }, desenho);
    if (s.destaque && animar) linha.classList.add("desenha");
    finais.push({ s, i, ultimo: validos.at(-1) });
  }

  // os pontos de agora: hoje (violeta) e o comparado (cinza); os valores
  // deles moram na legenda, onde nao colidem com linha nenhuma
  if (agora) {
    svg("line", { x1: xAgora, x2: xAgora, y1: TOPO - 6, y2: baseY, class: "agora" }, desenho);
    const valores = numeros(agora.valores);
    const marcas = series.map((s, i) => ({ s, v: valores[i] })).filter((m) => m.v !== null);
    for (const { s, v } of marcas) {
      svg("circle", { cx: xAgora, cy: y(v), r: 4.5, class: s.destaque ? "ponto destaque" : "ponto contexto" }, desenho);
    }
  } else {
    // sem "agora" (o saldo previsto): o valor no fim e, se ficar negativo, o fundo do poço
    const destaque = finais.find((f) => f.s.destaque);
    if (destaque) {
      const [px, py] = destaque.ultimo;
      svg("circle", { cx: px, cy: py, r: 4.5, class: "ponto destaque" }, desenho);
      const ultimoValor = destaque.s.valores.filter((v) => v !== null).at(-1);
      rotulo(desenho, px, py - 10, compacto(ultimoValor, g.formato), largura);
      const valores = destaque.s.valores;
      const menor = Math.min(...valores.filter((v) => v !== null));
      if (menor < 0) {
        const i = valores.indexOf(menor);
        svg("circle", { cx: x(i), cy: y(menor), r: 4.5, class: "ponto perigo" }, desenho);
        // o fundo do poco so ganha numero se for outro que o do fim (que ja tem)
        const outro = Math.abs(menor - ultimoValor) > Math.abs(menor) * 0.01;
        if (outro && Math.abs(x(i) - px) > 60) rotulo(desenho, x(i), y(menor) + 18, compacto(menor, g.formato), largura);
      }
    }
  }

  marcasY(desenho, e, y, g.formato);
  area.append(desenho);
  if (animar) {
    desenho.querySelectorAll(".desenha").forEach((linha) => {
      const comprimento = Math.ceil(linha.getTotalLength?.() || 600);
      linha.style.setProperty("--comprimento", comprimento);
    });
  }

  // o dedo (ou o mouse) passeia pelas marcas; o "agora" e uma marca a mais
  const posicoes = rotulos.map((_, i) => ({ x: x(i), i }));
  if (agora) posicoes.push({ x: xAgora, agora: true });
  interagir(area, desenho, posicoes, (p) => {
    const linhasDaDica = series.map((s, i) => {
      const v = p.agora ? numeros(agora.valores)[i] : s.valores[p.i];
      return { nome: s.nome, serie: s.destaque ? "destaque" : `contexto-${i}`,
               valor: v === null || v === undefined ? "—" : formatar(v, g.formato), y: v === null ? null : y(v) };
    });
    return {
      titulo: p.agora ? agora.rotulo || "agora" : g.dicas?.[p.i] || rotulos[p.i],
      linhas: linhasDaDica,
    };
  }, { baseY, topo: TOPO });
}

/** Onde o rotulo vai cair (de, ate): o mesmo alinhamento que `rotulo` usa. */
function ancoraDe(px, largura) {
  return px < 40 ? "start" : px > largura - 40 ? "end" : "middle";
}

function extensao(px, texto, largura) {
  const w = texto.length * 6.6 + 4;
  const ancora = ancoraDe(px, largura);
  return ancora === "start" ? [px, px + w] : ancora === "end" ? [px - w, px] : [px - w / 2, px + w / 2];
}

function rotulo(desenho, px, py, texto, largura) {
  const ancora = ancoraDe(px, largura);
  const no = svg("text", { x: px, y: py, "text-anchor": ancora, class: "rotulo-valor" }, desenho);
  no.textContent = texto;
}

// --------------------------------------------------------------- colunas ---
function colunas(area, g, largura, animar) {
  const altura = ALTURA.colunas;
  const rotulos = g.rotulos ?? [];
  const valores = numeros(g.valores).slice(0, rotulos.length).map((v) => v ?? 0);
  const n = valores.length;
  const inteiros = g.formato !== "moeda";
  const e = escala(valores, { topo: inteiros ? 3 : 100, inteiros });
  const baseY = altura - EIXO_X;
  const faixa = largura / Math.max(n, 1);
  const grossura = Math.min(24, Math.max(3, faixa * 0.62));
  const x = (i) => i * faixa + faixa / 2;
  const y = (v) => TOPO + (1 - (v - e.menor) / (e.maior - e.menor)) * (baseY - TOPO);

  const desenho = svg("svg", { viewBox: `0 0 ${largura} ${altura}`, width: largura, height: altura,
                               "aria-hidden": "true", class: animar ? "entrando" : "" });
  grade(desenho, e, y, largura);
  rotulosX(desenho, rotulos, x, largura, altura);

  const barras = svg("g", { class: "barras" }, desenho);
  const maior = Math.max(...valores);
  valores.forEach((v, i) => {
    const esquerda = x(i) - grossura / 2;
    const classe = i === g.destaque ? "barra destaque" : "barra";
    if (v <= 0) {
      // dia zerado tambem e informacao (loja fechada): um toco no chao
      svg("rect", { x: esquerda, y: baseY - 2, width: grossura, height: 2, rx: 1, class: "barra vazia" }, barras);
      return;
    }
    const topo = y(v);
    const raio = Math.min(4, grossura / 2, baseY - topo);
    const d = `M${esquerda} ${baseY}V${topo + raio}Q${esquerda} ${topo} ${esquerda + raio} ${topo}`
      + `H${esquerda + grossura - raio}Q${esquerda + grossura} ${topo} ${esquerda + grossura} ${topo + raio}V${baseY}Z`;
    const barra = svg("path", { d, class: classe }, barras);
    if (animar) barra.style.setProperty("--atraso", `${Math.min(i, 30) * 14}ms`);
  });

  // valor so onde ajuda: a coluna de agora e a maior (se nao colidirem)
  const marcar = [];
  if (typeof g.destaque === "number" && valores[g.destaque] > 0) marcar.push(g.destaque);
  const iMaior = valores.indexOf(maior);
  // em grafico denso (30 dias) so a coluna de agora fala; o maior fica para a dica
  const cabeMaior = n <= 14 && (!marcar.length || Math.abs(x(iMaior) - x(marcar[0])) > 64);
  if (maior > 0 && iMaior !== g.destaque && cabeMaior) marcar.push(iMaior);
  marcasY(desenho, e, y, g.formato);
  for (const i of marcar) {
    const texto = compacto(valores[i], g.formato);
    // o rotulo e mais largo que a coluna: sobe acima das vizinhas que ele cobre
    const [de, ate] = extensao(x(i), texto, largura);
    const cobertas = valores.filter((v, j) => x(j) + grossura / 2 > de && x(j) - grossura / 2 < ate);
    rotulo(desenho, x(i), y(Math.max(...cobertas)) - 7, texto, largura);
  }

  area.append(desenho);
  interagir(area, desenho, valores.map((_, i) => ({ x: x(i), i })), (p) => ({
    titulo: g.dicas?.[p.i] || rotulos[p.i],
    linhas: [{ valor: formatar(valores[p.i], g.formato), serie: p.i === g.destaque ? "destaque" : "contexto-1" }],
    barra: p.i,
  }), { baseY, topo: TOPO, faixa });
}

// ------------------------------------------------------------- interacao ---
/**
 * Tocar, arrastar, passar o mouse ou usar as setas: uma linha vertical acha a
 * marca mais perto e a dica mostra os valores dela. No toque, a dica fica
 * um pouco depois de soltar o dedo - senão some antes de ser lida.
 */
function interagir(area, desenho, posicoes, ler, { baseY, topo, faixa = 0 }) {
  if (!posicoes.length) return;
  const { signal } = toques.get(area) ?? new AbortController();
  const ouvir = (nome, fn) => area.addEventListener(nome, fn, { signal });
  const mira = svg("line", { y1: topo - 6, y2: baseY, class: "mira", visibility: "hidden" }, desenho);
  const pontos = svg("g", { class: "mira-pontos" }, desenho);
  const dica = el("div", "grafico-dica");
  dica.setAttribute("role", "status");
  dica.hidden = true;
  area.append(dica);
  let atual = -1;
  let some = 0;

  const mostrar = (indice) => {
    clearTimeout(some);
    const p = posicoes[indice];
    if (!p) return;
    atual = indice;
    const leitura = ler(p);
    mira.setAttribute("x1", p.x);
    mira.setAttribute("x2", p.x);
    mira.setAttribute("visibility", "visible");
    pontos.replaceChildren();
    for (const l of leitura.linhas) {
      if (typeof l.y === "number") svg("circle", { cx: p.x, cy: l.y, r: 5, "data-serie": l.serie, class: "mira-ponto" }, pontos);
    }
    desenho.querySelectorAll(".barra.ativa").forEach((b) => b.classList.remove("ativa"));
    if (typeof leitura.barra === "number") desenho.querySelectorAll(".barra")[leitura.barra]?.classList.add("ativa");

    dica.replaceChildren(el("span", "grafico-dica-titulo", leitura.titulo));
    for (const l of leitura.linhas) {
      const linha = el("span", "grafico-dica-linha");
      const chave = el("span", "legenda-chave");
      chave.dataset.serie = l.serie;
      linha.append(chave, el("strong", "", l.valor));
      if (l.nome) linha.append(el("span", "grafico-dica-nome", l.nome));
      dica.append(linha);
    }
    dica.hidden = false;
    const largura = area.clientWidth;
    const meia = dica.offsetWidth / 2;
    dica.style.left = `${Math.max(0, Math.min(largura - dica.offsetWidth, p.x - meia))}px`;
  };
  const esconder = (depois = 0) => {
    clearTimeout(some);
    some = setTimeout(() => {
      atual = -1;
      dica.hidden = true;
      mira.setAttribute("visibility", "hidden");
      pontos.replaceChildren();
      desenho.querySelectorAll(".barra.ativa").forEach((b) => b.classList.remove("ativa"));
    }, depois);
  };
  const maisPerto = (evento) => {
    const caixa = area.getBoundingClientRect();
    const px = evento.clientX - caixa.left;
    let melhor = 0;
    posicoes.forEach((p, i) => { if (Math.abs(p.x - px) < Math.abs(posicoes[melhor].x - px)) melhor = i; });
    // coluna: so conta se o dedo esta perto da faixa dela
    if (faixa && Math.abs(posicoes[melhor].x - px) > faixa) return -1;
    return melhor;
  };

  ouvir("pointerdown", (ev) => { const i = maisPerto(ev); if (i >= 0) mostrar(i); });
  ouvir("pointermove", (ev) => {
    if (ev.pointerType === "mouse" || ev.buttons || ev.pressure > 0) {
      const i = maisPerto(ev);
      if (i >= 0 && i !== atual) mostrar(i);
    }
  });
  ouvir("pointerleave", (ev) => esconder(ev.pointerType === "mouse" ? 0 : 2200));
  ouvir("pointerup", (ev) => { if (ev.pointerType !== "mouse") esconder(2200); });
  ouvir("pointercancel", () => esconder(0));
  ouvir("keydown", (ev) => {
    if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
      ev.preventDefault();
      const passo = ev.key === "ArrowRight" ? 1 : -1;
      mostrar(Math.max(0, Math.min(posicoes.length - 1, (atual < 0 ? posicoes.length - 1 : atual + passo))));
    } else if (ev.key === "Escape") esconder(0);
  });
  ouvir("focus", () => { if (atual < 0) mostrar(posicoes.length - 1); });
  ouvir("blur", () => esconder(0));
}

// --------------------------------------------------------------- ranking ---
/** Barras deitadas: o nome em cima, o tamanho embaixo. Cabe nome comprido. */
function ranking(g) {
  const itens = (g.itens ?? []).filter((i) => i && i.rotulo && typeof i.valor === "number");
  const figura = el("figure", "grafico grafico-ranking");
  if (g.titulo) figura.append(el("figcaption", "grafico-titulo", g.titulo));
  if (!itens.length) {
    if (!g.vazio) return null;
    figura.append(el("p", "lista-vazia", g.vazio));
    return figura;
  }
  const total = itens.reduce((soma, i) => soma + Math.max(0, i.valor), 0) || 1;
  const maior = Math.max(...itens.map((i) => i.valor)) || 1;
  const lista = el("ol", "ranking-itens");
  for (const item of itens) {
    const li = el("li");
    const fracao = Math.max(0, item.valor) / (g.parte_do_todo ? total : maior);
    const parte = g.parte_do_todo ? `${Math.round((Math.max(0, item.valor) / total) * 100)}%` : item.detalhe;
    const barra = el("span", "ranking-barra");
    const preenchido = el("span");
    preenchido.style.setProperty("--fracao", Math.max(0.015, Math.min(1, fracao)).toFixed(4));
    barra.append(preenchido);
    const nome = el("span", "ranking-rotulo", item.rotulo);
    if (parte) nome.append(el("span", "ranking-detalhe", parte));
    li.append(nome, el("strong", "ranking-valor", item.texto || formatar(item.valor, g.formato)), barra);
    lista.append(li);
  }
  figura.append(lista);
  return figura;
}

// ---------------------------------------------------------------- etapas ---
/** Uma barra só, dividida pelas etapas - que têm ordem, então o tom escurece. */
function etapas(g) {
  const itens = (g.itens ?? []).filter((i) => i && i.rotulo && typeof i.valor === "number");
  const figura = el("figure", "grafico grafico-etapas");
  if (g.titulo) figura.append(el("figcaption", "grafico-titulo", g.titulo));
  const total = itens.reduce((soma, i) => soma + Math.max(0, i.valor), 0);
  if (!total) {
    if (!g.vazio) return null;
    figura.append(el("p", "lista-vazia", g.vazio));
    return figura;
  }
  const barra = el("div", "etapas-barra");
  barra.setAttribute("aria-hidden", "true");
  const legenda = el("ul", "etapas-legenda");
  itens.forEach((item, i) => {
    const passo = String(Math.min(i + 1, 4));
    if (item.valor > 0) {
      const pedaco = el("span");
      pedaco.dataset.etapa = passo;
      pedaco.style.flexGrow = String(item.valor);
      barra.append(pedaco);
    }
    const li = el("li");
    const chave = el("span", "etapa-chave");
    chave.dataset.etapa = passo;
    li.append(chave, el("span", "etapa-nome", item.rotulo), el("strong", "etapa-valor", item.texto || formatar(item.valor, "numero")));
    legenda.append(li);
  });
  figura.append(barra, legenda);
  return figura;
}

// ---------------------------------------------------------------- medidor ---
/** Uma barra de progresso. O tom (aviso, perigo) pinta o que já foi. */
export function medidor(m, tom = "") {
  if (!m || typeof m.fracao !== "number") return null;
  const no = el("span", "medidor");
  if (tom) no.dataset.tom = tom;
  const preenchido = el("span");
  preenchido.style.setProperty("--fracao", Math.max(0, Math.min(1, m.fracao)).toFixed(4));
  no.append(preenchido);
  no.setAttribute("role", "img");
  no.setAttribute("aria-label", m.texto || `${Math.round(m.fracao * 100)}%`);
  return no;
}
