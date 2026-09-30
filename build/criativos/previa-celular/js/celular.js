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
