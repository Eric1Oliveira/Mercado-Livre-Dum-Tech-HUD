// Hub > Atualizações: o que está pronto para lançar, onde cada computador está
// e o histórico de versões. É aqui que o lançamento acontece; para um cliente
// só (testar antes de lançar para todos), os botões estão na ficha dele.

import { apagar, atualizar, inserir } from "../api.js";
import {
  COMO_FORCA, atualizarTodos, descartar, forcarTodos, recolher,
} from "../atualizar.js";
import { contagem, data, dataHora, numero, relativo } from "../formato.js";
import { carregarGestao } from "../gestao-dados.js";
import { comPresenca, distribuicaoDeVersoes } from "../gestao.js";
import { recarregar } from "../painel.js";
import { compararVersoes } from "../saude.js";
import { agir, cartao, confirmar, el, pessoa, pilula, recado, tabela, tile, vazio } from "../ui.js";
import { ficha } from "./comercial.js";

const megabytes = (bytes) => (Number(bytes) > 0
  ? `${(Number(bytes) / (1024 * 1024)).toFixed(1).replace(".", ",")} MB` : "");

export async function atualizacoes(alvo) {
  const dados = await carregarGestao();
  const { linhas, lancamentos, liberacoes, publicada, alvo: versao, atual } = dados;

  const maquinas = comPresenca(linhas.flatMap((l) => l.maquinas));
  const conhecidas = maquinas.filter((m) => m.versao);
  const naPublicada = conhecidas.filter((m) => publicada && compararVersoes(m.versao, publicada) >= 0).length;
  const online = linhas.reduce((soma, l) => soma + l.online, 0);
  const aguardando = linhas.filter((l) => ["liberada", "forcada"].includes(l.atualizacao)).length;

  alvo.append(
    el("div", { classe: "pagina-cabeca" }, [
      el("div", {}, [
        el("h1", { texto: "Atualizações" }),
        el("p", { texto: "Você decide quando cada versão chega: para um cliente, para os selecionados ou para todos." }),
      ]),
    ]),
    el("div", { classe: "tiles" }, [
      tile("Publicada", publicada || "—", atual?.atualizado_em ? `desde ${data(atual.atualizado_em)}` : "nenhuma versão"),
      tile("Em dia", conhecidas.length ? `${numero(naPublicada)} de ${numero(conhecidas.length)}` : "—", "computadores na publicada",
           conhecidas.length && naPublicada === conhecidas.length ? "ok" : ""),
      tile("Online agora", numero(online), "computadores com o Hub aberto", online ? "ok" : ""),
      tile("Aguardando", numero(aguardando), "clientes com ordem por instalar"),
    ]),
    ...[
      cartaoPendente(dados, conhecidas.length),
      cartaoDistribuicao(conhecidas, publicada),
      cartaoLiberacoes(liberacoes, linhas),
      cartaoHistorico(lancamentos, publicada, conhecidas, atual),
      cartaoMaoEFreio(atual, versao),
    ].filter(Boolean),
  );
}

// ======================================================== pronta para lançar
function cartaoPendente({ pendente, publicada, alvo, linhas, forcadaGeral }, computadores) {
  if (!pendente) {
    const atrasados = linhas.filter((l) => l.podeAtualizar).length;
    return cartao("Pronta para lançar", [
      vazio("Nenhuma versão esperando", "A próxima que subir com tools\\lancar_versao.ps1 -Pendente aparece aqui."),
      atrasados && publicada && !forcadaGeral
        ? el("div", { classe: "acoes-linha lancamento-acoes" }, [
            el("span", { classe: "dica", texto: `${contagem(atrasados, "cliente ainda não instalou", "clientes ainda não instalaram")} a ${publicada}.` }),
            el("button", { classe: "botao botao-perigo", texto: "Forçar todos",
                           onclick: () => forcarTodos({ versao: alvo, computadores, depois: recarregar }) }),
          ])
        : null,
    ]);
  }

  const testando = linhas.filter((l) => l.liberacao?.versao === pendente.versao).length;
  return el("section", { classe: "lancamento" }, [
    el("div", { classe: "espectro espectro-faixa", "aria-hidden": "true" },
       Array.from({ length: 7 }, () => el("span"))),
    el("div", { classe: "lancamento-corpo" }, [
      el("div", { classe: "lancamento-versao" }, [
        el("span", { classe: "faixa-lancamento-rotulo", texto: "Pronta para lançar" }),
        el("strong", { texto: pendente.versao }),
        el("span", { texto: [`subiu ${relativo(pendente.criado_em)}`, megabytes(pendente.tamanho)].filter(Boolean).join(" · ") }),
      ]),
      el("div", { classe: "lancamento-texto" }, [
        el("p", { texto: pendente.notas || "Sem recado." }),
        el("p", { classe: "lancamento-situacao", texto: testando
          ? `${contagem(testando, "cliente já recebeu", "clientes já receberam")} para testar. Para os outros, a versão no ar segue sendo a ${publicada}.`
          : `Nenhum cliente recebeu. A versão no ar segue sendo a ${publicada}.` }),
      ]),
    ]),
    el("div", { classe: "lancamento-botoes" }, [
      el("button", {
        classe: "botao botao-primario", texto: "Atualizar todos",
        onclick: (e) => atualizarTodos(e.currentTarget, { versao: pendente.versao, computadores, depois: recarregar }),
      }),
      el("button", {
        classe: "botao botao-noite", texto: "Forçar todos",
        onclick: () => forcarTodos({ versao: pendente.versao, computadores, depois: recarregar }),
      }),
      el("button", {
        classe: "botao botao-noite", texto: "Descartar",
        onclick: (e) => descartar(e.currentTarget, { versao: pendente.versao, depois: recarregar }),
      }),
    ]),
  ]);
}

// ========================================================== onde cada um está
function cartaoDistribuicao(conhecidas, publicada) {
  if (!conhecidas.length) return null;
  const partes = distribuicaoDeVersoes(conhecidas);
  const total = conhecidas.length;
  return cartao("Onde cada computador está", [
    el("div", { classe: "versoes-barra", role: "img",
                "aria-label": partes.map((p) => `${p.versao}: ${p.computadores}`).join(", ") },
       partes.map((p) => el("span", {
         estilo: `flex-grow:${p.computadores}`, title: `${p.versao}: ${contagem(p.computadores, "computador", "computadores")}`,
         "data-estado": compararVersoes(p.versao, publicada) >= 0 ? "em-dia" : "atrasada",
       }))),
    el("ul", { classe: "versoes-lista" }, partes.map((p) => el("li", {}, [
      el("span", { classe: "hub-versao", "data-velha": compararVersoes(p.versao, publicada) < 0 ? "sim" : null, texto: p.versao }),
      el("span", { texto: contagem(p.computadores, "computador", "computadores") }),
      el("span", { classe: "sub-linha", texto: `${Math.round((p.computadores / total) * 100)}%` }),
    ]))),
  ]);
}

// ========================================================= pedidos por cliente
function cartaoLiberacoes(liberacoes, linhas) {
  const porLicenca = new Map(linhas.filter((l) => l.cliente.licenca_id).map((l) => [l.cliente.licenca_id, l]));
  const ativas = liberacoes
    .map((liberacao) => ({ liberacao, linha: porLicenca.get(liberacao.licenca_id) }))
    .filter(({ linha }) => linha);
  if (!ativas.length) return null;
  return cartao("Liberadas por cliente", tabela(
    ["Cliente", "Versão", "Como", "Situação", "Pedido em", ""],
    ativas,
    ({ liberacao, linha }) => {
      const instalou = linha.versoes.length && compararVersoes(linha.maisVelha, liberacao.versao) >= 0;
      return [
        pessoa(linha.nome, linha.cliente.email),
        el("span", { classe: "hub-versao", texto: liberacao.versao }),
        liberacao.forcada ? pilula("Forçada", "ruim") : pilula("Opcional", "marca"),
        instalou ? pilula("Instalou", "ok") : pilula(linha.online ? "Online, aguardando" : "Offline, aguardando", "aviso"),
        dataHora(liberacao.criado_em),
        instalou ? null : el("button", {
          classe: "botao botao-fantasma botao-mini", texto: "Cancelar",
          onclick: (e) => {
            e.stopPropagation();
            agir(e.currentTarget, async () => {
              await apagar("hub_liberacoes", { licenca_id: `eq.${liberacao.licenca_id}` }, { conferir: true });
              await recarregar();
            }, { feito: "Liberação cancelada. O Hub deixa de oferecer esta versão em até 2 minutos.",
                 erro: "Não consegui cancelar." });
          },
        }),
      ];
    },
    { aoClicar: ({ linha }) => ficha(linha.cliente) }
  ));
}

// ==================================================================== histórico
function situacaoDaVersao(lancamento, publicada) {
  if (lancamento.descartada_em) return pilula("Descartada", "neutro");
  if (lancamento.versao === publicada) {
    return lancamento.forcada_em ? pilula("No ar, forçada", "ruim") : pilula("No ar", "ok");
  }
  return lancamento.liberada_em ? pilula("Anterior", "neutro") : pilula("Pendente", "marca");
}

function cartaoHistorico(lancamentos, publicada, conhecidas, atual) {
  const ordenados = [...lancamentos].sort((a, b) => compararVersoes(b.versao, a.versao));
  const temAnterior = (versao) => lancamentos.some((l) => l.liberada_em && !l.descartada_em
    && compararVersoes(l.versao, versao) < 0);
  return cartao("Versões", tabela(
    ["Versão", "Situação", "Subiu", "Lançada", { texto: "Computadores", numero: true }, ""],
    ordenados,
    (l) => [
      el("span", { classe: "hub-versao", texto: l.versao, title: l.notas || "" }),
      situacaoDaVersao(l, publicada),
      data(l.criado_em),
      l.liberada_em ? dataHora(l.liberada_em) : "—",
      numero(conhecidas.filter((m) => m.versao === l.versao).length),
      l.versao === publicada && temAnterior(l.versao)
        ? el("button", {
            classe: "botao botao-fantasma botao-mini", texto: "Recolher",
            title: "Volta a oferecer a versão anterior. Quem já instalou continua nesta.",
            onclick: (e) => recolher(e.currentTarget, { versao: l.versao, depois: recarregar }),
          })
        : null,
    ],
    { vazioTexto: atual?.versao ? `A ${atual.versao} entrou antes deste histórico.` : "Nenhuma versão registrada." }
  ));
}

// ====================================================== à mão e freio do Hub
/** Registrar sem o script, e o freio que desliga a instalação pelo Hub. */
function cartaoMaoEFreio(atual, versaoAtual) {
  const campos = {
    versao: campo("Versão", "1.11.0"),
    url: campo("Endereço do instalador", "https://dumtechsolution.com/baixar/DumTech-Hub-Setup-1.11.0.exe"),
    sha256: campo("SHA-256 do instalador", "64 caracteres"),
    tamanho: campo("Tamanho em bytes", "29781768"),
    notas: campo("Recado", "O que mudou nesta versão"),
  };
  const freio = el("input", { type: "checkbox" });
  freio.checked = atual ? Boolean(atual.automatica) : true;
  freio.addEventListener("change", () => {
    if (!freio.checked && !confirmar("Desligar a instalação pelo Hub? O botão passa a levar o cliente ao site, " +
                                     "e nenhuma atualização é forçada enquanto estiver desligada.")) {
      freio.checked = true;
      return;
    }
    agir(null, async () => {
      await atualizar("hub_versoes", { id: "eq.1" }, { automatica: freio.checked });
      await recarregar();
    }, { feito: freio.checked ? "Instalação pelo Hub ligada." : "Instalação pelo Hub desligada.", erro: "Não consegui mudar." });
  });

  const registrar = el("button", {
    classe: "botao botao-fantasma", texto: "Registrar como pendente",
    onclick: (e) => agir(e.currentTarget, async () => {
      const versao = campos.versao.valor();
      const sha256 = campos.sha256.valor().toLowerCase();
      if (!/^[0-9]+(\.[0-9]+){0,3}$/.test(versao)) throw new Error("A versão é só número e ponto: 1.11.0");
      if (!/^https:\/\//.test(campos.url.valor())) throw new Error("O endereço precisa começar com https://");
      if (!/^[0-9a-f]{64}$/.test(sha256)) throw new Error("O SHA-256 tem 64 caracteres (0-9 e a-f).");
      if (compararVersoes(versao, versaoAtual) <= 0) throw new Error(`A versão precisa ser maior que a ${versaoAtual}.`);
      await inserir("hub_lancamentos", {
        versao, sha256, url: campos.url.valor(), notas: campos.notas.valor(),
        tamanho: Number(campos.tamanho.valor()) || 0,
      });
      recado(`Versão ${versao} registrada como pendente.`, "ok");
      await recarregar();
    }, { feito: "", erro: "Não consegui registrar." }),
  });

  return el("details", { classe: "cartao detalhes-cartao" }, [
    el("summary", { texto: "Controles avançados" }),
    el("div", { classe: "corpo" }, [
      el("label", { classe: "campo-linha" }, [freio, el("span", { texto: "Deixar o cliente atualizar pelo próprio Hub" })]),
      el("p", { classe: "dica", texto: `Forçar: ${COMO_FORCA.join(" ")}` }),
      el("div", { classe: "form-versao" }, [
        el("h3", { texto: "Registrar uma versão à mão" }),
        el("p", { classe: "dica", texto: "Use só se o instalador subiu sem o script. O arquivo precisa estar no ar com esse SHA-256." }),
        ...Object.values(campos).map((c) => c.no),
        el("div", { classe: "acoes-cartao" }, [registrar]),
      ]),
    ]),
  ]);
}

function campo(rotulo, dica = "") {
  const entrada = el("input", { placeholder: dica });
  return {
    no: el("label", { classe: "campo" }, [el("span", { texto: rotulo }), entrada]),
    valor: () => String(entrada.value ?? "").trim(),
  };
}
