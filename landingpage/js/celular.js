// O Hub no celular — a conta, sem tela (testada em tests/celular.test.mjs).
//
// O celular nao sabe nada de venda, conta ou ordem: o Hub manda cada modulo
// pronto em "secoes" (cartoes + listas) e aqui so se decide O QUE aparece.
// Quem manda nisso e a licenca que o servidor le NA HORA em que o celular
// abre: comprou um modulo, ele entra; licenca suspensa, some tudo.

import { MODULOS } from "./dados.js";

/** O codigo do QR vem depois do # (nunca chega a servidor nenhum). */
export function codigoDoEndereco(hash) {
  const achou = /(?:^#|&)p=([0-9a-f]{64})(?:&|$)/.exec(hash || "");
  return achou ? achou[1] : "";
}

/** O nome que aparece no Hub, em "Celulares conectados". */
export function nomeDoAparelho(agente = "") {
  if (/iPhone/.test(agente)) return "iPhone";
  if (/iPad/.test(agente)) return "iPad";
  const android = /Android[^;)]*;\s*([^;)]+?)(?:\s+Build|\))/.exec(agente);
  if (android && !/^(wv|Linux|K)$/i.test(android[1].trim())) return `Android · ${android[1].trim()}`.slice(0, 60);
  if (/Android/.test(agente)) return "Android";
  return "Celular";
}

export const ERROS = {
  codigo_invalido: {
    titulo: "Este QR Code já foi usado ou venceu",
    texto: "Cada código vale por 5 minutos e uma leitura só. No computador, abra o Hub › menu da empresa › Ver no celular e leia o código novo.",
  },
  desconectado: {
    titulo: "Este celular foi desconectado",
    texto: "Alguém tirou este aparelho da lista no Hub. Para ver de novo, leia um QR Code novo em Ver no celular.",
  },
  licenca_bloqueada: {
    titulo: "A licença desta empresa não está ativa",
    texto: "Os dados voltam a aparecer assim que a licença for regularizada. Fale com a DumTech pelo WhatsApp.",
  },
  muitas_tentativas: {
    titulo: "Muitas tentativas seguidas",
    texto: "Espere alguns minutos e tente de novo.",
  },
  sem_internet: {
    titulo: "Sem conexão agora",
    texto: "Confira a internet do celular. Tentamos de novo sozinhos.",
  },
};

export const moduloDoCodigo = (codigo) => MODULOS.find((m) => m.codigo === String(codigo).toUpperCase());

/**
 * O que a tela mostra a partir da resposta de dumtech_celular_dados.
 *   escolhido: o indice do computador (a loja pode ter mais de um).
 */
export function montarTela(dados, escolhido = 0) {
  const liberados = new Set((dados?.modulos ?? []).map((c) => String(c).toUpperCase()));
  const espelhos = dados?.espelhos ?? [];
  const indice = Math.min(Math.max(0, escolhido | 0), Math.max(0, espelhos.length - 1));
  const espelho = espelhos[indice];
  const resumo = espelho?.dados ?? {};

  // so o que a licenca libera AGORA - o espelho pode ser de antes da suspensao
  // de um modulo, e o celular nao mostra o que a empresa nao tem mais
  const secoes = (resumo.secoes ?? []).filter((s) => liberados.has(String(s.app).toUpperCase()));
  const comSecao = new Set(secoes.map((s) => String(s.app).toUpperCase()));

  return {
    empresa: resumo.empresa || dados?.cliente || "",
    // 1 = Hub antigo (cartoes e listas); 2 = destaque, graficos e alertas
    formato: Number(resumo.formato) || 1,
    computadores: espelhos.map((e) => ({ nome: e.computador || "Computador", atualizadoEm: e.atualizado_em })),
    indice,
    atualizadoEm: espelho?.atualizado_em ?? null,
    secoes,
    // comprou agora e o computador ainda nao mandou: aparece "a caminho"
    aCaminho: MODULOS.filter((m) => liberados.has(m.codigo) && !comSecao.has(m.codigo)),
    // o que a empresa ainda nao tem (a vitrine discreta do fim da tela)
    faltam: MODULOS.filter((m) => !liberados.has(m.codigo)),
  };
}

/**
 * O número que abre a tela, grande e sem moldura.
 *
 * E o primeiro cartao do modulo de maior peso - o Hub ja ordena as secoes por
 * peso, e dinheiro vem primeiro. Ele sai da grade da secao para nao aparecer
 * duas vezes (quem desenha compara por identidade, nao por copia).
 */
export function destaqueDaTela(tela) {
  const primeira = tela?.secoes?.[0];
  const cartao = primeira?.cartoes?.[0];
  if (!cartao?.valor) return null;
  // subir o unico numero da secao deixaria para tras um titulo sozinho
  const sobra = primeira.cartoes.length > 1
    || (primeira.listas ?? []).some((l) => l?.linhas?.length || l?.vazio);
  return sobra ? cartao : null;
}

/** "agora mesmo", "há 4 min", "há 2 h", "ontem às 18:40", "12/09 às 09:15". */
export function haQuanto(iso, agora = new Date()) {
  if (!iso) return "";
  const quando = new Date(iso);
  if (Number.isNaN(quando.getTime())) return "";
  const segundos = Math.max(0, Math.round((agora - quando) / 1000));
  if (segundos < 60) return "agora mesmo";
  const minutos = Math.round(segundos / 60);
  if (minutos < 60) return `há ${minutos} min`;
  const hora = quando.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const dia = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const dias = Math.round((dia(agora) - dia(quando)) / 86400000);
  if (dias === 0) return `há ${Math.round(minutos / 60)} h`;
  if (dias === 1) return `ontem às ${hora}`;
  return `${quando.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} às ${hora}`;
}

/** Numeros velhos: o computador pode estar desligado (a tela avisa). */
export const MINUTOS_PARA_ANTIGO = 20;
export function estaAntigo(iso, agora = new Date()) {
  if (!iso) return false;
  return (agora - new Date(iso)) / 60000 > MINUTOS_PARA_ANTIGO;
}

/** Link da loja ja com o modulo no carrinho. */
export function linkDaLoja(base, codigo) {
  const url = new URL(base);
  url.searchParams.set("kit", codigo);
  url.hash = "montador";
  return url.toString();
}

/* ===========================================================================
   FORMATO 2 — o que transforma número em resposta
   O Hub manda, por seção: `destaque` (o número que abre a tela, com períodos e
   gráfico), `graficos`, `alertas` e, em cartões e linhas, `variacao`,
   `medidor` e `acao`. Tudo opcional: resumo de Hub antigo continua valendo.
   ========================================================================= */

const MOEDA = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const MOEDA_CURTA = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL", notation: "compact", maximumFractionDigits: 1,
});
const NUMERO = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

/** O número por extenso, como o Hub escreve: "R$ 1.234,50", "12". */
export function formatar(valor, formato = "moeda") {
  const n = Number(valor) || 0;
  return formato === "moeda" ? MOEDA.format(n) : NUMERO.format(n);
}

/** Para eixo e rótulo de gráfico, onde cabe pouco: "R$ 1,5 mil", "R$ 900". */
export function compacto(valor, formato = "moeda") {
  const n = Number(valor) || 0;
  if (formato !== "moeda") return NUMERO.format(n);
  return Math.abs(n) < 1000 ? MOEDA.format(Math.round(n)).replace(/,00$/, "") : MOEDA_CURTA.format(n);
}

/**
 * O eixo de um gráfico: de onde a onde vai e onde passam as linhas de grade.
 * Números redondos (0, 500, 1.000...), o zero sempre dentro, e só inteiros
 * quando o que se conta não se divide (compromissos, ordens).
 */
export function escala(valores, { divisoes = 3, inteiros = false, topo = 1 } = {}) {
  const numeros = valores.filter((v) => typeof v === "number" && Number.isFinite(v));
  let menor = Math.min(0, ...numeros);
  let maior = Math.max(0, ...numeros);
  // tudo zero (dia sem venda): um eixo de verdade, e nao marcas de centavos
  if (maior === menor) maior = menor + (inteiros ? divisoes : topo);
  const bruto = (maior - menor) / divisoes;
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  let passo = [1, 2, 2.5, 3, 4, 5, 6, 8, 10].map((m) => m * potencia).find((p) => p >= bruto) ?? 10 * potencia;
  if (inteiros) passo = Math.max(1, Math.ceil(passo));
  menor = Math.floor(menor / passo) * passo;
  maior = Math.ceil(maior / passo) * passo;
  const marcas = [];
  for (let v = menor; v <= maior + passo / 2; v += passo) marcas.push(Math.round(v * 100) / 100);
  return { menor, maior, marcas };
}

/** Quais rótulos do eixo X aparecem: no máximo `cabem`, sempre o último. */
export function rotulosVisiveis(total, cabem) {
  if (total <= cabem) return Array.from({ length: total }, (_, i) => i);
  const passo = Math.ceil(total / cabem);
  const escolhidos = [];
  for (let i = total - 1; i >= 0; i -= passo) escolhidos.unshift(i);
  return escolhidos;
}

/**
 * O número que abre a tela.
 *   - o `destaque` da seção de maior peso (com períodos e gráfico), ou
 *   - na falta dele (Hub antigo), o primeiro cartão - como sempre foi.
 */
export function aberturaDaTela(tela) {
  const secao = tela?.secoes?.[0];
  if (!secao) return null;
  const periodos = (secao.destaque?.periodos ?? []).filter((p) => p && p.valor);
  if (periodos.length) return { secao, destaque: { ...secao.destaque, periodos } };
  const cartao = destaqueDaTela(tela);
  return cartao ? { secao, cartao } : null;
}

/** Os cartões que a seção mostra: o que já virou destaque não se repete. */
export function cartoesVisiveis(secao, pular = null) {
  const temDestaque = (secao?.destaque?.periodos ?? []).length > 0;
  return (secao?.cartoes ?? []).filter((c) => c !== pular && !(temDestaque && c?.papel === "destaque"));
}

const PESO_DO_TOM = { perigo: 0, aviso: 1, ok: 2 };

/**
 * "Precisa de você": o que cada módulo pediu, num lugar só. Problema antes de
 * lembrete; dentro do mesmo tom, a ordem dos módulos (dinheiro primeiro).
 */
export function alertasDaTela(tela) {
  const todos = [];
  (tela?.secoes ?? []).forEach((s, ordem) => {
    for (const a of s.alertas ?? []) {
      if (!a?.texto) continue;
      todos.push({ ...a, tom: a.tom in PESO_DO_TOM ? a.tom : "aviso", app: String(s.app).toUpperCase(),
                   modulo: s.titulo, ordem });
    }
  });
  return todos.sort((a, b) => PESO_DO_TOM[a.tom] - PESO_DO_TOM[b.tom] || a.ordem - b.ordem);
}

/** "+18%" + "vs. sábado passado até 15:18" - a comparação sempre tem nome. */
export function textoDaVariacao(v) {
  if (!v?.texto) return null;
  const seta = v.direcao === "sobe" ? "▲" : v.direcao === "desce" ? "▼" : "=";
  return { seta, numero: v.texto.replace(/^[+−-]/, ""), tom: v.tom || "",
           comparado: v.comparado ? `vs. ${v.comparado}` : "" };
}

/**
 * Link do WhatsApp com a mensagem pronta. O número vem do computador da loja:
 * só passa número brasileiro inteiro (55 + DDD + telefone).
 */
export function linkWhatsApp(acao) {
  if (acao?.tipo !== "whatsapp" || !/^55\d{10,11}$/.test(String(acao.numero ?? ""))) return "";
  const texto = String(acao.mensagem ?? "").slice(0, 500);
  return `https://wa.me/${acao.numero}${texto ? `?text=${encodeURIComponent(texto)}` : ""}`;
}

/** "Sábado, 17 de outubro" - o dia de hoje no alto da tela. */
export function hojePorExtenso(agora = new Date()) {
  const texto = agora.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
  return texto.charAt(0).toUpperCase() + texto.slice(1).replace("-feira", "");
}
