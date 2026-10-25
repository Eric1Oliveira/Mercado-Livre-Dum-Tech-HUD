// Os dois gráficos do painel, em HTML (não canvas): nítidos em qualquer
// largura, com dica ao passar o dedo ou o mouse e uma tabela escondida para
// leitor de tela.
//
//   colunasPorDia  quantas aberturas houve em cada dia (uma cor só, a da marca)
//   faixa          os mesmos dias de UM cliente, em quadradinhos: quanto mais
//                  escuro, mais uso. A régua é a mesma para todos os clientes,
//                  então duas faixas se comparam de olho.

import { numero } from "./formato.js";
import { nivel } from "./saude.js";
import { el } from "./ui.js";

const nomeDoDia = (dia) => new Date(`${dia}T12:00:00`)
  .toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
const diaCurto = (dia) => `${dia.slice(8, 10)}/${dia.slice(5, 7)}`;
const plural = (n, um, varios) => `${numero(n)} ${n === 1 ? um : varios}`;

// ------------------------------------------------------------------- dica --
// Uma só para a página inteira, presa à janela: dentro da tabela que rola de
// lado ela seria cortada pela caixa.
let dica = null;

function mostrarDica(alvo, titulo, linhas) {
  if (!dica) {
    dica = el("div", { classe: "dica-grafico", role: "tooltip", hidden: true });
    document.body.append(dica);
    for (const evento of ["scroll", "resize"]) {
      window.addEventListener(evento, esconderDica, { passive: true, capture: true });
    }
  }
  dica.replaceChildren(el("strong", { texto: titulo }), ...linhas.map((l) => el("span", { texto: l })));
  dica.hidden = false;
  const caixa = alvo.getBoundingClientRect();
  const largura = dica.offsetWidth;
  const altura = dica.offsetHeight;
  const esquerda = Math.min(Math.max(8, caixa.left + caixa.width / 2 - largura / 2),
                            window.innerWidth - largura - 8);
  const acima = caixa.top - altura - 8;
  dica.style.left = `${esquerda}px`;
  dica.style.top = `${acima >= 8 ? acima : caixa.bottom + 8}px`;
}

function esconderDica() {
  if (dica) dica.hidden = true;
}

/** Liga a dica a um grupo de marcas (delegação: uma escuta por gráfico). */
function comDica(raiz, seletor, conteudo) {
  const sobre = (evento) => {
    const marca = evento.target.closest?.(seletor);
    if (!marca || !raiz.contains(marca)) return;
    const { titulo, linhas } = conteudo(marca);
    mostrarDica(marca, titulo, linhas);
  };
  raiz.addEventListener("pointerover", sobre);
  raiz.addEventListener("pointerdown", sobre);
  raiz.addEventListener("pointerleave", esconderDica);
}

/**
 * O teto "redondo" da escala, com a metade inteira (é a linha do meio):
 * 3 -> 4, 7 -> 8, 23 -> 30, 140 -> 150.
 */
export function tetoRedondo(maior) {
  if (!(maior > 0)) return 2;
  if (maior <= 10) return Math.max(2, Math.ceil(maior / 2) * 2);
  const ordem = 10 ** Math.floor(Math.log10(maior));
  for (const passo of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) {
    const teto = passo * ordem;
    if (teto >= maior && Number.isInteger(teto / 2)) return teto;
  }
  return 10 * ordem;
}

const tabelaParaLeitor = (titulo, cabecas, linhas) =>
  el("div", { classe: "so-leitor" }, [
    el("table", {}, [
      el("caption", { texto: titulo }),
      el("thead", {}, [el("tr", {}, cabecas.map((c) => el("th", { texto: c })))]),
      el("tbody", {}, linhas.map((linha) => el("tr", {}, linha.map((c) => el("td", { texto: c }))))),
    ]),
  ]);

// ========================================================== colunas/dia ====
/**
 * serie: [{dia, valor, clientes?}] em ordem, do mais antigo até hoje.
 */
export function colunasPorDia(serie, { titulo = "Aberturas por dia" } = {}) {
  const teto = tetoRedondo(Math.max(0, ...serie.map((d) => d.valor)));
  const total = serie.reduce((soma, d) => soma + d.valor, 0);
  const meio = serie[Math.floor((serie.length - 1) / 2)];

  const colunas = el("div", { classe: "colunas", estilo: `--dias:${serie.length}` },
    serie.map((d, indice) => el("div", {
      classe: `coluna${indice === serie.length - 1 ? " hoje" : ""}`,
      "data-indice": String(indice),
    }, [d.valor > 0
      ? el("span", { classe: "coluna-barra", estilo: `height:${Math.max(2, (d.valor / teto) * 100)}%` })
      : null])));

  const grafico = el("figure", { classe: "grafico-colunas" }, [
    el("div", {
      classe: "grafico-area", role: "img",
      "aria-label": `${titulo}: ${plural(total, "abertura", "aberturas")} em ${serie.length} dias.`,
    }, [
      el("div", { classe: "grade", "aria-hidden": "true" }, [[teto, 0], [teto / 2, 50], [0, 100]].map(([valor, topo]) =>
        el("span", { "data-valor": numero(valor), estilo: `top:${topo}%` }))),
      colunas,
    ]),
    el("div", { classe: "eixo-dias", "aria-hidden": "true" }, [
      el("span", { texto: diaCurto(serie[0].dia) }),
      el("span", { texto: diaCurto(meio.dia) }),
      el("span", { texto: "hoje" }),
    ]),
    tabelaParaLeitor(titulo, ["Dia", "Aberturas", "Clientes"],
      serie.map((d) => [diaCurto(d.dia), numero(d.valor), d.clientes === undefined ? "—" : numero(d.clientes)])),
  ]);

  comDica(colunas, ".coluna", (marca) => {
    const d = serie[Number(marca.dataset.indice)];
    const linhas = [plural(d.valor, "abertura", "aberturas")];
    if (d.clientes !== undefined && d.valor > 0) linhas.push(plural(d.clientes, "cliente", "clientes"));
    return { titulo: nomeDoDia(d.dia), linhas };
  });
  return grafico;
}

// ================================================================= faixa ===
/**
 * Os dias de um cliente em quadradinhos. `teto` é o maior dia de TODOS os
 * clientes da tela (a régua comum).
 */
export function faixa(serie, teto, { rotulo = "" } = {}) {
  const usados = serie.filter((d) => d.valor > 0);
  const total = usados.reduce((soma, d) => soma + d.valor, 0);
  const resumo = usados.length
    ? `usou em ${plural(usados.length, "dia", "dias")} dos últimos ${serie.length}, ${plural(total, "abertura", "aberturas")}`
    : `nenhum uso nos últimos ${serie.length} dias`;

  const caixa = el("div", {
    classe: "faixa", role: "img", "aria-label": rotulo ? `${rotulo}: ${resumo}` : resumo,
    estilo: `--dias:${serie.length}`,
  }, serie.map((d, indice) => el("span", {
    classe: "celula", "data-n": String(nivel(d.valor, teto)), "data-indice": String(indice),
  })));
  comDica(caixa, ".celula", (marca) => {
    const d = serie[Number(marca.dataset.indice)];
    return { titulo: nomeDoDia(d.dia), linhas: [d.valor ? plural(d.valor, "abertura", "aberturas") : "não abriu"] };
  });
  return caixa;
}

/** A legenda da faixa: menos ▢▢▢▢▢ mais. */
export const legendaDaFaixa = () =>
  el("div", { classe: "legenda-faixa", "aria-hidden": "true" }, [
    el("span", { texto: "menos" }),
    ...[0, 1, 2, 3, 4].map((n) => el("span", { classe: "celula", "data-n": String(n) })),
    el("span", { texto: "mais" }),
  ]);
