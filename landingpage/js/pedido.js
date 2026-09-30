// A pagina do pedido: para onde a InfinitePay manda o comprador depois de pagar.
//
// So abre com o segredo do pedido (veio na URL de volta, e fica guardado neste
// navegador). A URL e limpa logo em seguida: o segredo nao fica no historico,
// nem numa captura de tela da barra de endereco.

import { situacaoDoPedido } from "./api.js";
import { CONFIG } from "./config.js";
import { METODOS, guardarPedido, lerVolta, pedidoGuardado } from "./pagamento.js";

const $ = (id) => document.getElementById(id);
const dinheiro = (valor) => Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

// quanto tempo a pagina insiste sozinha antes de sugerir o WhatsApp
const INTERVALO_MS = 4000;
const PACIENCIA_MS = 15 * 60 * 1000;
const PACIENCIA_ENTREGA_MS = 90 * 1000;
const CONFERE_MS = 2 * 60 * 1000;

function armazem() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function mostrar(estado) {
  for (const secao of document.querySelectorAll(".estado")) {
    secao.hidden = secao.dataset.estado !== estado;
  }
}

function whatsapp(texto) {
  if (!CONFIG.WHATSAPP) return;
  for (const link of document.querySelectorAll("[data-whatsapp]")) {
    link.href = `https://wa.me/${CONFIG.WHATSAPP}?text=${encodeURIComponent(texto)}`;
  }
}

function resumir(dados, volta) {
  const itens = Array.isArray(dados.itens) ? dados.itens : [];
  const area = $("resumo-itens");
  area.replaceChildren(...itens.map((nome) => {
    const linha = document.createElement("div");
    linha.className = "resumo-linha";
    linha.textContent = String(nome);
    return linha;
  }));
  $("resumo-total").textContent = dinheiro(dados.total);

  const meta = $("resumo-meta");
  meta.replaceChildren();
  const metodo = METODOS[dados.metodo] || METODOS[volta.metodo];
  if (metodo && dados.pagamento === "pago") meta.append(`Pago com ${metodo}. `);
  const recibo = /^https:\/\//.test(dados.recibo || "") ? dados.recibo : volta.recibo;
  if (recibo && dados.pagamento === "pago") {
    const link = document.createElement("a");
    link.href = recibo;
    link.rel = "noopener noreferrer";
    link.target = "_blank";
    link.textContent = "Ver comprovante";
    meta.append(link);
  }
  $("resumo-pedido").hidden = itens.length === 0;
}

function pintar(dados, volta, { desdeInicio, pagoDesde }) {
  resumir(dados, volta);
  const kit = (dados.itens || []).join(", ");

  if (dados.pagamento === "pago" && dados.entregue && dados.licenca_nova && dados.chave) {
    $("chave-valor").textContent = dados.chave;
    $("chave-email").textContent = dados.email || "—";
    const maximo = Number(dados.max_computadores) || 1;
    $("chave-computadores").textContent = maximo > 1 ? `Ativa em até ${maximo} computadores.` : "Ativa em 1 computador.";
    whatsapp(`Olá! Comprei ${kit} pela loja e preciso de ajuda para instalar.`);
    mostrar("chave");
    return "fim";
  }

  if (dados.pagamento === "pago" && dados.entregue) {
    $("modulos-texto").textContent = dados.final_chave
      ? `${kit} entrou na chave que você já usa, terminada em ${dados.final_chave}. Não precisa de chave nova nem reinstalar.`
      : `${kit} entrou na chave que você já usa.`;
    mostrar("modulos");
    return "fim";
  }

  if (dados.pagamento === "pago") {
    const demorou = Date.now() - pagoDesde > PACIENCIA_ENTREGA_MS;
    $("liberando-texto").textContent = demorou
      ? "Recebemos o seu pagamento, e a liberação está levando mais tempo que o normal. Já fomos avisados: chame no WhatsApp e a sua chave sai na hora."
      : "Estamos liberando a sua chave. Esta página se atualiza sozinha.";
    whatsapp(`Olá! Paguei ${dinheiro(dados.total)} pela loja (${kit}) e ainda não recebi a chave.`);
    mostrar("liberando");
    return demorou ? "devagar" : "continua";
  }

  // aguardando
  const voltar = $("voltar-pagamento");
  if (/^https:\/\//.test(dados.checkout_url || "")) {
    voltar.href = dados.checkout_url;
    voltar.hidden = false;
  }
  const demorou = Date.now() - desdeInicio > PACIENCIA_MS;
  $("aguardando-texto").textContent = demorou
    ? "Ainda não recebemos a confirmação. Se o pagamento não foi concluído, você pode voltar e pagar. Se já pagou, chame no WhatsApp com o comprovante."
    : volta.transacao
      ? "Recebemos a sua volta da InfinitePay e estamos confirmando o pagamento. Esta página se atualiza sozinha."
      : "Pagou com Pix? A confirmação costuma chegar em menos de um minuto. Esta página se atualiza sozinha.";
  whatsapp(`Olá! Fiz um pedido de ${dinheiro(dados.total)} na loja (${kit}) e preciso de ajuda com o pagamento.`);
  mostrar("aguardando");
  return demorou ? "devagar" : "continua";
}

(async function iniciar() {
  const volta = lerVolta(location.href);
  const guardado = pedidoGuardado(armazem(), volta.pedido);
  const pedido = volta.pedido || guardado?.pedido || "";
  const segredo = volta.segredo || (guardado?.pedido === pedido ? guardado.segredo : "");

  if (!pedido || !segredo) {
    mostrar("nao-encontrado");
    return;
  }
  guardarPedido(armazem(), pedido, segredo);
  // tira o segredo da barra de endereco e do historico
  try {
    const limpo = new URLSearchParams({ p: pedido });
    const api = new URLSearchParams(location.search).get("api"); // so desenvolvimento (config.js)
    if (api) limpo.set("api", api);
    history.replaceState(null, "", `${location.pathname}?${limpo}`);
  } catch {
    /* navegador que nao deixa: segue igual */
  }

  const desdeInicio = Date.now();
  let pagoDesde = 0;
  let falhas = 0;

  while (true) {
    // nos primeiros minutos a pagina pede a conferencia com o numero da transacao
    // (o webhook pode chegar depois dela); dali em diante so pergunta ao banco
    const confere = Date.now() - desdeInicio < CONFERE_MS;
    const dados = await situacaoDoPedido({
      pedido, segredo,
      transacao: confere ? volta.transacao : "",
      fatura: confere ? volta.fatura : "",
    });
    if (!dados?.ok) {
      if (dados?.erro === "nao_encontrado") {
        mostrar("nao-encontrado");
        return;
      }
      // rede piscou: tenta de novo, sem trocar o que esta na tela
      falhas += 1;
      if (falhas > 20) {
        mostrar("nao-encontrado");
        return;
      }
    } else {
      falhas = 0;
      if (dados.pagamento === "pago" && !pagoDesde) pagoDesde = Date.now();
      const passo = pintar(dados, volta, { desdeInicio, pagoDesde });
      if (passo === "fim") return;
      // depois da paciencia, confere bem menos (a pessoa pode ter so deixado a aba aberta)
      if (passo === "devagar") {
        await esperar(INTERVALO_MS * 8);
        continue;
      }
    }
    await esperar(INTERVALO_MS);
  }
})();

function esperar(ms) {
  return new Promise((pronto) => setTimeout(pronto, ms));
}

$("copiar-chave").addEventListener("click", async () => {
  const rotulo = $("copiar-chave").querySelector("span");
  try {
    await navigator.clipboard.writeText($("chave-valor").textContent.trim());
    rotulo.textContent = "Chave copiada";
  } catch {
    // sem permissao de area de transferencia: seleciona para o Ctrl+C
    const faixa = document.createRange();
    faixa.selectNodeContents($("chave-valor"));
    getSelection().removeAllRanges();
    getSelection().addRange(faixa);
    rotulo.textContent = "Selecionada: Ctrl+C";
  }
  setTimeout(() => { rotulo.textContent = "Copiar chave"; }, 2500);
});
