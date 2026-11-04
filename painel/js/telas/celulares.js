// O "Ver no celular" de cada cliente: as peças que a ficha usa (o aparelho e
// o botão Desconectar).
//
// O painel vê quando cada celular abriu e quando cada computador atualizou o
// resumo. O que aparece no celular (vendas, clientes e valores da empresa do
// cliente) não chega aqui: o banco não dá ao painel a coluna do conteúdo.

import { atualizar } from "../api.js";
import { quando } from "../formato.js";
import { recarregar } from "../painel.js";
import { agir, confirmar, el } from "../ui.js";

export function aparelho(a, apelidos = new Map()) {
  const computador = apelidos.get(`${a.licenca_id}|${a.maquina}`);
  return el("div", {}, [
    el("strong", { texto: a.nome || "Celular" }),
    el("div", { classe: "sub-linha", texto: `conectado ${quando(a.criado_em)}${computador ? `, pelo ${computador}` : ""}` }),
  ]);
}

/** O mesmo "Desconectar" do Hub: o celular para de ver os dados na hora. */
export function botaoDesconectar(a, dono = {}, { depois = recarregar } = {}) {
  return el("button", {
    type: "button", classe: "botao botao-perigo botao-mini", texto: "Desconectar",
    onclick: (evento) => {
      evento.stopPropagation(); // a linha abre a ficha; o botão, não
      const alvo = evento.currentTarget;
      if (!confirmar(`Desconectar o celular "${a.nome || "Celular"}"${dono.nome ? ` de ${dono.nome}` : ""}? ` +
                     "Ele para de ver os dados na hora. Para voltar, o cliente lê um QR Code novo no Hub.")) return;
      agir(alvo, async () => {
        await atualizar("celular_aparelhos", { id: `eq.${a.id}` }, { revogado_em: new Date().toISOString() });
        await depois();
      }, { feito: "Celular desconectado." });
    },
  });
}
