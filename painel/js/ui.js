// As peças de tela do painel: elemento, tabela, pílula, recado, confirmação.
//
// Tudo aqui monta DOM e devolve o nó — nenhuma tela escreve innerHTML com dado
// do banco, senão um nome de cliente com "<" viraria marcação.

import { iniciais, numero, situacao as rotuloSituacao } from "./formato.js";
import { linkWhatsApp } from "./mensagens.js";
import { modulo } from "./modulos.js";

/** el("div", {clase: "x", texto: "oi"}, [filhos]) */
export function el(tag, atributos = {}, filhos = []) {
  const nó = document.createElement(tag);
  for (const [chave, valor] of Object.entries(atributos)) {
    if (valor === undefined || valor === null || valor === false) continue;
    if (chave === "texto") nó.textContent = valor;
    else if (chave === "classe") nó.className = valor;
    else if (chave === "estilo") nó.setAttribute("style", valor);
    else if (chave.startsWith("on") && typeof valor === "function") {
      nó.addEventListener(chave.slice(2), valor);
    } else if (valor === true) nó.setAttribute(chave, "");
    else nó.setAttribute(chave, valor);
  }
  for (const filho of [].concat(filhos)) {
    if (filho === null || filho === undefined || filho === false) continue;
    nó.append(filho?.nodeType ? filho : document.createTextNode(String(filho)));
  }
  return nó;
}

export function limpar(alvo) {
  alvo.replaceChildren();
  return alvo;
}

export const icone = (caminho, tamanho = 16) => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", tamanho);
  svg.setAttribute("height", tamanho);
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  const traço = document.createElementNS("http://www.w3.org/2000/svg", "path");
  traço.setAttribute("d", caminho);
  svg.append(traço);
  return svg;
};

// ------------------------------------------------------------------- peças --
export const pilula = (texto, tom = "neutro") =>
  el("span", { classe: "pilula", "data-tom": tom, texto });

export const pilulaSituacao = (valor) => {
  const { texto, tom } = rotuloSituacao(valor);
  return pilula(texto, tom);
};

export function pilulaModulo(codigo, { apagada = false } = {}) {
  const m = modulo(codigo);
  return el(
    "span",
    { classe: `modulo-pilula${apagada ? " apagada" : ""}`, estilo: `--cor:${m.cor}` },
    [icone(m.icone, 13), m.nome]
  );
}

export const iniciaisDe = iniciais;

export const pessoa = (nome, sub) =>
  el("div", { classe: "pessoa" }, [
    el("span", { classe: "avatar", texto: iniciais(nome) }),
    el("div", {}, [
      el("div", { classe: "nome", texto: nome || "—" }),
      sub ? el("div", { classe: "sub", texto: sub }) : null,
    ]),
  ]);

export const tile = (rotulo, valor, nota = "", tom = "") =>
  el("div", { classe: "tile", "data-tom": tom || null }, [
    el("div", { classe: "rotulo", texto: rotulo }),
    el("div", { classe: "valor", texto: valor }),
    nota ? el("div", { classe: "nota", texto: nota }) : null,
  ]);

export const cartao = (titulo, corpo, acoes = null) =>
  el("section", { classe: "cartao" }, [
    titulo
      ? el("header", {}, [el("h3", { texto: titulo }), acoes])
      : null,
    el("div", { classe: "corpo" }, corpo),
  ]);

export const vazio = (titulo, texto = "") =>
  el("div", { classe: "vazio" }, [el("strong", { texto: titulo }), texto]);

export const carregando = (texto = "Carregando…") => el("div", { classe: "carregando", texto });

/** Barra de proporção (uso por módulo). */
export const barra = (parte, total, corBarra) =>
  el("div", { classe: "barra", title: `${parte} de ${total}` }, [
    el("span", {
      estilo: `width:${total > 0 ? Math.max(2, Math.round((parte / total) * 100)) : 0}%;` +
        (corBarra ? `--cor:${corBarra}` : ""),
    }),
  ]);

/**
 * tabela(["Nome", {texto:"Total", numero:true}], linhas, montar)
 * `montar(linha)` devolve a lista de células (nó ou texto).
 */
export function tabela(colunas, linhas, montar, { aoClicar = null, vazioTexto = "Nada por aqui." } = {}) {
  if (!linhas.length) return vazio(vazioTexto);

  const cabeca = el("tr", {}, colunas.map((coluna) => {
    const { texto, numero, no } = typeof coluna === "string" ? { texto: coluna } : coluna;
    return el("th", { classe: numero ? "numero" : null }, [no ?? texto]);
  }));

  const corpo = el("tbody", {}, linhas.map((linha) => {
    const tr = el("tr", { "data-clicavel": aoClicar ? "sim" : null });
    if (aoClicar) tr.addEventListener("click", () => aoClicar(linha));
    for (const [indice, celula] of montar(linha).entries()) {
      const coluna = colunas[indice];
      const numero = typeof coluna === "object" && coluna.numero;
      tr.append(el("td", { classe: numero ? "numero" : null }, [celula]));
    }
    return tr;
  }));

  return el("div", { classe: "tabela-rolagem" }, [
    el("table", {}, [el("thead", {}, [cabeca]), corpo]),
  ]);
}

/**
 * Filtro em botões, cada um com a sua contagem:
 *   chips([{ valor: "", texto: "Todos", conta: 12 }, ...], atual, (valor) => ...)
 */
export function chips(opcoes, atual, aoEscolher, rotulo = "Filtrar") {
  return el("div", { classe: "chips", role: "group", "aria-label": rotulo },
    opcoes.map((o) => el("button", {
      type: "button", classe: "chip", "aria-pressed": o.valor === atual ? "true" : "false",
      onclick: () => aoEscolher(o.valor),
    }, [o.texto, o.conta === undefined ? null : el("span", { classe: "chip-conta", texto: numero(o.conta) })])));
}

/** Abre o WhatsApp do cliente com o recado pronto (sem número válido, nada). */
export function botaoWhatsApp(telefone, texto, rotulo = "WhatsApp") {
  const url = linkWhatsApp(telefone, texto);
  if (!url) return null;
  return el("button", {
    type: "button", classe: "botao botao-fantasma botao-mini", texto: rotulo,
    title: "Abre o WhatsApp com o recado pronto; você revisa antes de mandar",
    onclick: (evento) => {
      evento.stopPropagation(); // a linha da tabela abre a ficha; o botão, não
      window.open(url, "_blank", "noopener");
    },
  });
}

// ------------------------------------------------------------------ recados --
let apagarRecado = null;

export function recado(texto, tom = "") {
  const caixa = document.getElementById("recado");
  caixa.textContent = texto;
  caixa.dataset.tom = tom;
  caixa.hidden = false;
  clearTimeout(apagarRecado);
  apagarRecado = setTimeout(() => { caixa.hidden = true; }, tom === "erro" ? 6000 : 3500);
}

/** Confirmação honesta: diz o que vai acontecer, não "tem certeza?". */
export const confirmar = (pergunta) => window.confirm(pergunta);

/** Roda uma ação, cuida do botão e do recado de erro. */
export async function agir(botao, acao, { feito = "Pronto.", erro = "Não deu certo." } = {}) {
  const antes = botao?.textContent;
  if (botao) {
    botao.disabled = true;
    botao.textContent = "…";
  }
  try {
    const resultado = await acao();
    if (feito) recado(feito, "ok");
    return resultado;
  } catch (falha) {
    console.error(falha);
    recado(`${erro} ${falha.message || ""}`.trim(), "erro");
    return null;
  } finally {
    if (botao) {
      botao.disabled = false;
      botao.textContent = antes;
    }
  }
}
