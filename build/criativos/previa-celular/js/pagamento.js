// O que a loja precisa saber do pagamento, sem rede e sem tela.
//
//   - guardar o segredo do pedido neste navegador antes de ir para a InfinitePay
//     (a pagina /pedido/ so mostra a chave com ele)
//   - ler a volta da InfinitePay, que acrescenta receipt_url, order_nsu, slug,
//     capture_method e transaction_nsu ao endereco de retorno
//
// Modulo puro: testado em tests/pagamento.test.mjs.

export const CHAVE_PEDIDOS = "dumtech.pedidos";
export const VALIDADE_PEDIDO_DIAS = 30;
const MAXIMO_GUARDADOS = 8;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SEGREDO = /^[A-Za-z0-9_-]{40,64}$/;
const CODIGO = /^[A-Za-z0-9_.:-]{1,100}$/;

/**
 * Le a volta sem confiar no formato: se a InfinitePay juntar os parametros com
 * "?" em vez de "&", cada valor ainda sai inteiro (nenhum dos nossos tem ? ou &).
 */
export function lerVolta(endereco) {
  const valor = (nome) => {
    const achado = String(endereco ?? "").match(new RegExp(`[?&]${nome}=([^&?#]*)`));
    if (!achado) return "";
    try {
      return decodeURIComponent(achado[1].replace(/\+/g, " "));
    } catch {
      return "";
    }
  };
  const pedido = UUID.test(valor("p")) ? valor("p") : UUID.test(valor("order_nsu")) ? valor("order_nsu") : "";
  const recibo = valor("receipt_url");
  return {
    pedido: pedido.toLowerCase(),
    segredo: SEGREDO.test(valor("s")) ? valor("s") : "",
    transacao: CODIGO.test(valor("transaction_nsu")) ? valor("transaction_nsu") : "",
    fatura: CODIGO.test(valor("slug")) ? valor("slug") : "",
    metodo: CODIGO.test(valor("capture_method")) ? valor("capture_method") : "",
    // so https vira link na tela
    recibo: /^https:\/\/[^\s"'<>]+$/.test(recibo) ? recibo : "",
  };
}

function lerGuardados(armazem) {
  try {
    const dados = JSON.parse(armazem?.getItem(CHAVE_PEDIDOS) ?? "[]");
    return Array.isArray(dados) ? dados : [];
  } catch {
    return [];
  }
}

export function guardarPedido(armazem, pedido, segredo, agora = new Date()) {
  if (!armazem || !UUID.test(pedido) || !SEGREDO.test(segredo)) return false;
  const lista = [
    { pedido: pedido.toLowerCase(), segredo, quando: agora.toISOString() },
    ...lerGuardados(armazem).filter((item) => item?.pedido !== pedido.toLowerCase()),
  ].slice(0, MAXIMO_GUARDADOS);
  try {
    armazem.setItem(CHAVE_PEDIDOS, JSON.stringify(lista));
    return true;
  } catch {
    return false;
  }
}

/** O segredo guardado deste pedido (ou do mais recente, sem pedido), ou null. */
export function pedidoGuardado(armazem, pedido = "", agora = new Date()) {
  const valido = (item) => UUID.test(item?.pedido ?? "") && SEGREDO.test(item?.segredo ?? "") &&
    (agora - new Date(item.quando ?? 0)) / 86400000 <= VALIDADE_PEDIDO_DIAS;
  const lista = lerGuardados(armazem).filter(valido);
  const item = pedido ? lista.find((i) => i.pedido === String(pedido).toLowerCase()) : lista[0];
  return item ? { pedido: item.pedido, segredo: item.segredo } : null;
}

/** https://x.supabase.co/rest/v1 -> https://x.supabase.co/functions/v1 */
export function enderecoDasFuncoes(rest) {
  return String(rest ?? "").replace(/\/rest\/v1\/?$/, "/functions/v1");
}

export const METODOS = { pix: "Pix", credit_card: "cartão de crédito" };
