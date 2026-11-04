// Os botões que mandam atualização: por cliente, em massa e para todos.
//
// ATUALIZAR  o aviso aparece no Hub e o cliente escolhe a hora.
// FORÇAR     o Hub instala sem esperar o clique.
//
// Quem cumpre é o banco (dumtech_atualizar_*): uma conta que não é administradora
// esbarra nas policies, e o botão vira só uma mensagem de erro.

import { rpc } from "./api.js";
import { contagem } from "./formato.js";
import { abrirGaveta, fecharGaveta } from "./painel.js";
import { agir, cartao, confirmar, el, recado } from "./ui.js";

const CHEGA = "O aviso aparece no Hub em até 2 minutos, assim que ele estiver com internet.";

/**
 * O que Forçar faz depende da versão que já está instalada: o código que cumpre
 * a contagem só existe a partir da 1.10.0.
 */
export const COMO_FORCA = [
  "Hub 1.10.0 ou mais novo: baixa, avisa na tela e instala sozinho 5 minutos depois.",
  "Hub 1.5.1 a 1.9.0: baixa sozinho, mostra em até 5 minutos um aviso que não pode ser dispensado e instala quando o programa for fechado.",
  "Hub mais antigo: mostra um aviso que não pode ser dispensado.",
];

/** Atualizar (ou forçar) um cliente, ou os selecionados. */
export function atualizarClientes(botao, { licencas, nome, versao, forcar = false, depois = null }) {
  const quem = nome || contagem(licencas.length, "cliente");
  if (forcar && !confirmar(`Forçar a versão ${versao} em ${quem}?\n\n${COMO_FORCA.join("\n")}`)) return null;
  return agir(botao, async () => {
    await rpc("dumtech_atualizar_clientes", { p_licencas: licencas, p_versao: versao, p_forcar: forcar });
    await depois?.();
  }, {
    feito: forcar ? `Versão ${versao} forçada em ${quem}. O Hub baixa sozinho, e o aviso aparece em até 5 minutos.`
                  : `Versão ${versao} liberada para ${quem}. ${CHEGA}`,
    erro: "Não consegui mandar a atualização.",
  });
}

/** Atualizar todos: a versão vai para todo mundo, e cada cliente escolhe a hora. */
export function atualizarTodos(botao, { versao, computadores, depois = null }) {
  if (!confirmar(`Lançar a versão ${versao} para todos?\n\n` +
                 `${contagem(computadores, "computador", "computadores")} vão ver o botão Atualizar. ` +
                 "Ninguém é obrigado a instalar agora.")) return null;
  return agir(botao, async () => {
    await rpc("dumtech_atualizar_todos", { p_versao: versao, p_forcar: false });
    await depois?.();
  }, { feito: `Versão ${versao} lançada para todos. ${CHEGA}`, erro: "Não consegui lançar." });
}

/** Forçar todos não passa com um clique: mostra o que acontece e pede a versão digitada. */
export function forcarTodos({ versao, computadores, depois = null }) {
  const entrada = el("input", {
    type: "text", inputmode: "decimal", autocomplete: "off", spellcheck: "false", placeholder: versao,
    "aria-label": `Digite ${versao} para confirmar`,
  });
  const executar = el("button", { classe: "botao botao-perigo-cheio", texto: `Forçar ${versao} em todos`, disabled: true });
  entrada.addEventListener("input", () => { executar.disabled = entrada.value.trim() !== versao; });
  executar.addEventListener("click", (e) => {
    if (entrada.value.trim() !== versao) return;
    agir(e.currentTarget, async () => {
      await rpc("dumtech_atualizar_todos", { p_versao: versao, p_forcar: true });
      fecharGaveta();
      await depois?.();
    }, { feito: `Versão ${versao} forçada em todos.`, erro: "Não consegui forçar." });
  });

  abrirGaveta({
    acima: "Forçar para todos", titulo: `Versão ${versao}`,
    conteudo: el("div", { classe: "exclusao" }, [
      cartao("O que acontece", el("ul", { classe: "exclusao-lista" }, [
        el("li", { texto: `Vale para ${contagem(computadores, "computador", "computadores")}, com ou sem o cliente querer.` }),
        ...COMO_FORCA.map((texto) => el("li", { texto })),
      ])),
      el("div", { classe: "exclusao-alternativa" }, [
        el("span", { texto: "Prefere não interromper ninguém? Use Atualizar todos: cada cliente instala quando puder." }),
      ]),
      cartao("", [
        el("label", { classe: "campo" }, [el("span", { texto: `Para confirmar, digite ${versao}` }), entrada]),
        el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
          executar,
          el("button", { classe: "botao botao-fantasma", texto: "Voltar", onclick: fecharGaveta }),
        ]),
      ]),
    ]),
  });
  entrada.focus();
}

/** Tira a versão do ar para quem ainda não instalou; ela volta a ser pendente. */
export function recolher(botao, { versao, depois = null }) {
  if (!confirmar(`Recolher a versão ${versao}?\n\nQuem ainda não instalou volta para a versão anterior. ` +
                 "Quem já instalou continua nela, e ela volta a ser pendente.")) return null;
  return agir(botao, async () => {
    const resposta = await rpc("dumtech_recolher_versao", { p_versao: versao });
    recado(`Versão ${versao} recolhida. O Hub volta a oferecer a ${resposta?.voltou_para}.`, "ok");
    await depois?.();
  }, { feito: "", erro: "Não consegui recolher." });
}

/** A pendente não vai mais sair. O arquivo continua no site, sem ninguém apontar para ele. */
export function descartar(botao, { versao, depois = null }) {
  if (!confirmar(`Descartar a versão ${versao}? Ela sai da lista de pendentes e de quem recebeu para testar.`)) return null;
  return agir(botao, async () => {
    await rpc("dumtech_descartar_versao", { p_versao: versao });
    await depois?.();
  }, { feito: `Versão ${versao} descartada.`, erro: "Não consegui descartar." });
}
