// As regras do anúncio, longe da tela — para poderem ser conferidas sozinhas.
//
// O anúncio tem UM canal no Hub: um pop-up na tela de Início, uma vez por
// cliente. Quem publica não vê o Hub de ninguém, então é aqui que mora o que
// a tela promete: quando um anúncio está mesmo no ar e o que o Hub recusaria.

import { data } from "./formato.js";

/**
 * A situação real de um anúncio.
 *
 * "Ativo" no banco não quer dizer "no ar": um anúncio ligado com data já
 * vencida não chega a ninguém, e a tela mostrava "No ar" do mesmo jeito. As
 * quatro situações separam o que está ligado do que está valendo hoje.
 */
export function situacaoAnuncio(anuncio, hoje = new Date().toISOString().slice(0, 10)) {
  if (!anuncio.ativo) return { texto: "Parado", tom: "neutro" };
  if (anuncio.fim && anuncio.fim < hoje) return { texto: "Encerrado", tom: "neutro" };
  if (anuncio.inicio && anuncio.inicio > hoje) {
    return { texto: `Programado · ${data(anuncio.inicio)}`, tom: "aviso" };
  }
  return { texto: "No ar", tom: "ok" };
}

/**
 * O que a tela manda para o banco — ou por que não manda nada.
 *
 * Devolve `{ erro }` OU `{ dados }`, nunca os dois. Existe para que a recusa e
 * a gravação sejam a mesma decisão, tomada uma vez:
 *
 * A tela validava dentro de `agir`. Recusado, ela mostrava o recado vermelho e
 * retornava normalmente — e `agir` (ui.js), que não tem como saber que a ação
 * desistiu, pintava "Anúncio salvo." por cima do erro. Quem clicava em Publicar
 * com um link torto via a mensagem verde, a gaveta aberta e nada no Hub, sem
 * nenhuma pista do que estava errado.
 */
export function montarAnuncio(valores) {
  const problema = conferirAnuncio(valores);
  if (problema) return problema;

  const texto = (v) => String(v ?? "").trim();
  return {
    dados: {
      titulo: texto(valores.titulo),
      texto: texto(valores.texto),
      rotulo: texto(valores.rotulo),
      link: texto(valores.link),
      alvo: valores.alvo,
      // 'todos' não aceita produto e 'sem_produto' exige um: é a mesma regra
      // que o banco cobra em `comunicados_alvo_produto`
      produto_codigo: valores.alvo === "sem_produto" ? valores.produto : null,
      inicio: texto(valores.inicio) || null,
      fim: texto(valores.fim) || null,
      ordem: Number(valores.ordem) || 0,
      ativo: Boolean(valores.ativo),
    },
  };
}

/**
 * O que o Hub ou o banco recusariam, dito antes e em português.
 *
 * Devolve `null` quando pode gravar, ou `{ erro, campo }` — o `campo` diz QUAL
 * entrada está errada, para a tela acender aquela e levar o olho até ela. Um
 * recado no rodapé da página não resolve quando o campo culpado está rolado
 * para fora da ficha.
 */
export function conferirAnuncio({ titulo, link, inicio, fim }) {
  if (!String(titulo || "").trim()) {
    return { erro: "O anúncio precisa de um título.", campo: "titulo" };
  }
  // o Hub abre este link no computador de cada cliente, então ele só aceita
  // página https (`comunicados.link_seguro`): um file:/// ou um caminho de
  // rede ali executaria coisa na máquina do cliente
  const endereco = String(link || "").trim();
  if (endereco && !/^https:\/\/[^\s\\]+$/i.test(endereco)) {
    return {
      erro: "O link precisa começar com https:// — ou deixe em branco para abrir a nossa loja.",
      campo: "link",
    };
  }
  if (fim && inicio && fim < inicio) {
    return { erro: "O anúncio termina antes de começar. Confira as datas.", campo: "fim" };
  }
  return null;
}
