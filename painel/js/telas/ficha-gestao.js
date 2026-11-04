// Os cartões novos da ficha: o Hub e a atualização, o acompanhamento comercial e
// a linha do tempo. A ficha (comercial.js) monta a tela e diz quando refazer.

import { apagar, atualizar, inserir, sessao } from "../api.js";
import { atualizarClientes } from "../atualizar.js";
import { data, dataHora, dinheiro, relativo } from "../formato.js";
import { ESTADOS_DA_ATUALIZACAO, estadoDaAtualizacao, lerEtiquetas } from "../gestao.js";
import { mensagemDeAcompanhamento } from "../mensagens.js";
import { compararVersoes, hubAberto } from "../saude.js";
import { agir, botaoWhatsApp, cartao, el, pilula, recado } from "../ui.js";

/** Em que versão o cliente está, o que falta e os dois botões. */
export function cartaoAtualizacao({ cliente, maquinas, liberacao, publicada, forcadaGeral, alvo, depois }, agora) {
  if (!cliente.licenca_id || !maquinas.length) return null;

  const versoes = [...new Set(maquinas.map((m) => m.versao).filter(Boolean))];
  const estado = estadoDaAtualizacao({ versoes, liberacao, publicada, forcadaGeral });
  const { texto, tom } = ESTADOS_DA_ATUALIZACAO[estado];
  const online = maquinas.filter((m) => hubAberto(m, agora)).length;
  const atrasado = versoes.some((v) => alvo && compararVersoes(v, alvo) < 0);
  const opcoes = { licencas: [cliente.licenca_id], nome: cliente.nome, versao: alvo, depois };

  return cartao("Hub e atualização", [
    el("div", { classe: "dados" }, [
      item("Agora", el("span", { classe: "hub-pc" }, [
        el("span", { classe: "hub-ponto", "data-aberto": online ? "sim" : null }),
        online ? `${online} de ${maquinas.length} online` : "Offline",
      ])),
      item("Instalado", el("span", { classe: "hub-versoes" }, versoes.length
        ? versoes.map((v) => el("span", { classe: "hub-versao", texto: v })) : ["—"])),
      item("Atualização", pilula(texto, tom)),
      item("Oferecer", alvo || "—"),
    ]),
    atrasado
      ? el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
          alvo === publicada
            ? null
            : el("button", { classe: "botao botao-primario botao-mini", texto: `Atualizar para ${alvo}`,
                             title: "O botão Atualizar aparece no Hub deste cliente",
                             onclick: (e) => atualizarClientes(e.target, opcoes) }),
          el("button", { classe: "botao botao-perigo botao-mini", texto: "Forçar",
                         title: "O Hub instala sem esperar o clique",
                         onclick: (e) => atualizarClientes(e.target, { ...opcoes, forcar: true }) }),
          liberacao
            ? el("button", {
                classe: "botao botao-fantasma botao-mini", texto: "Cancelar pedido",
                onclick: (e) => agir(e.target, async () => {
                  await apagar("hub_liberacoes", { licenca_id: `eq.${cliente.licenca_id}` }, { conferir: true });
                  await depois();
                }, { feito: "Pedido cancelado.", erro: "Não consegui cancelar." }),
              })
            : null,
          botaoWhatsApp(cliente.telefone, mensagemDeAcompanhamento("atualizar", { nome: cliente.nome }), "Avisar no WhatsApp"),
        ])
      : null,
  ]);
}

/** Etiquetas, próximo contato e o que a DumTech anotou sobre este cliente. */
export function cartaoAcompanhamento({ cliente, gestao, notas, depois }) {
  const etiquetas = el("input", { type: "text", value: (gestao?.etiquetas || []).join(", "),
                                  placeholder: "vip, revenda, indicou alguém" });
  const retorno = el("input", { type: "date", value: gestao?.proximo_contato || "" });
  const salvar = el("button", {
    classe: "botao botao-fantasma botao-mini", texto: "Salvar",
    onclick: (e) => agir(e.target, async () => {
      await atualizar("clientes", { id: `eq.${cliente.cliente_id}` }, {
        etiquetas: lerEtiquetas(etiquetas.value), proximo_contato: retorno.value || null,
      });
      await depois();
    }, { feito: "Acompanhamento salvo.", erro: "Não consegui salvar." }),
  });

  const texto = el("textarea", { rows: "2", maxlength: "2000", placeholder: "O que foi combinado, o que falta fazer…",
                                 "aria-label": "Nova anotação" });
  const anotar = el("button", {
    classe: "botao botao-primario botao-mini", texto: "Anotar",
    onclick: (e) => {
      const conteudo = texto.value.trim();
      if (!conteudo) return recado("Escreva a anotação primeiro.", "erro");
      agir(e.target, async () => {
        await inserir("cliente_notas", {
          cliente_id: cliente.cliente_id, texto: conteudo, autor: sessao()?.email || "",
        });
        await depois();
      }, { feito: "Anotado.", erro: "Não consegui anotar." });
    },
  });

  return cartao("Acompanhamento", [
    el("div", { classe: "linha-campos" }, [
      el("label", { classe: "campo" }, [el("span", { texto: "Etiquetas" }), etiquetas]),
      el("label", { classe: "campo" }, [el("span", { texto: "Próximo contato" }), retorno]),
    ]),
    el("div", { classe: "acoes-linha", estilo: "margin:10px 0 16px" }, [salvar]),
    el("label", { classe: "campo" }, [el("span", { texto: "Nova anotação" }), texto]),
    el("div", { classe: "acoes-linha", estilo: "margin-top:10px" }, [anotar]),
    notas.length
      ? el("ul", { classe: "notas" }, notas.map((nota) => el("li", {}, [
          el("p", { texto: nota.texto }),
          el("div", { classe: "sub-linha nota-rodape" }, [
            `${dataHora(nota.criado_em)}${nota.autor ? ` · ${nota.autor}` : ""}`,
            el("button", {
              type: "button", classe: "nota-apagar", texto: "Apagar",
              onclick: (e) => agir(e.target, async () => {
                await apagar("cliente_notas", { id: `eq.${nota.id}` }, { conferir: true });
                await depois();
              }, { feito: "Anotação apagada.", erro: "Não consegui apagar." }),
            }),
          ]),
        ])))
      : null,
  ]);
}

const ROTULOS = {
  cadastro: "Cadastro", compra: "Compra", modulo: "Módulo", teste: "Teste", computador: "Computador",
  versao: "Versão", nota: "Anotação", assinatura: "Assinatura",
};

/** Tudo o que aconteceu com o cliente, numa coluna só. */
export function cartaoLinhaDoTempo(eventos, agora) {
  if (!eventos.length) return null;
  return cartao("Linha do tempo", el("ol", { classe: "tempo" }, eventos.slice(0, 40).map((evento) => el("li", {
    "data-tipo": evento.tipo,
  }, [
    el("span", { classe: "tempo-tipo", texto: ROTULOS[evento.tipo] }),
    el("div", {}, [
      el("div", { classe: "tempo-texto", texto: evento.texto }),
      evento.detalhe ? el("div", { classe: "tempo-detalhe", texto: evento.detalhe }) : null,
      el("div", { classe: "sub-linha", title: dataHora(evento.quando), texto: [
        relativo(evento.quando, agora) === "hoje" ? "hoje" : data(evento.quando),
        evento.valor ? dinheiro(evento.valor) : "",
        evento.autor || "",
      ].filter(Boolean).join(" · ") }),
    ]),
  ]))));
}

const item = (rotulo, valor) =>
  el("div", { classe: "item" }, [
    el("div", { classe: "rotulo", texto: rotulo }),
    el("div", { classe: "valor" }, [valor]),
  ]);
