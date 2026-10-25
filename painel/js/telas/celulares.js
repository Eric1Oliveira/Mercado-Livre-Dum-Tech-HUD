// Celulares: o "Ver no celular" de cada cliente - quem usa e se os dados estão
// chegando.
//
// O painel vê quando cada celular abriu e quando cada computador atualizou o
// resumo. O que aparece no celular (vendas, clientes e valores da empresa do
// cliente) não chega aqui: o banco não dá ao painel a coluna do conteúdo.

import { atualizar, ler } from "../api.js";
import { numero, quando, relativo } from "../formato.js";
import { mensagemDeAcompanhamento } from "../mensagens.js";
import { recarregar } from "../painel.js";
import { ESTADOS_DO_CELULAR, estadoDoCelular, resumoMaisNovo, resumoVelho } from "../saude.js";
import { agir, botaoWhatsApp, cartao, confirmar, el, pessoa, pilula, pilulaModulo, tabela, tile } from "../ui.js";
import { ficha } from "./comercial.js";

export async function celulares(alvo) {
  const agora = new Date();
  const [aparelhos, clientes, espelhos, ativacoes] = await Promise.all([
    ler("celular_aparelhos", {
      select: "id,licenca_id,nome,maquina,criado_em,ultimo_acesso,revogado_em", ordem: "criado_em.desc",
    }),
    ler("painel_clientes", { ordem: "nome.asc" }),
    // sem a migration 20261019120000 o painel nao ve os resumos: a tela segue sem eles
    ler("celular_espelhos", { select: "licenca_id,maquina,atualizado_em" }).catch(() => null),
    ler("ativacoes", { select: "licenca_id,maquina,apelido" }),
  ]);
  const donoDa = new Map(clientes.filter((c) => c.licenca_id).map((c) => [c.licenca_id, c]));
  const resumos = resumoMaisNovo(espelhos || []);
  const apelidos = new Map(ativacoes.map((a) => [`${a.licenca_id}|${a.maquina}`, a.apelido]));

  const conectados = aparelhos.filter((a) => !a.revogado_em);
  const desconectados = aparelhos.filter((a) => a.revogado_em);
  const emUso = conectados.filter((a) => estadoDoCelular(a, agora) === "ativo");
  const atrasados = espelhos ? conectados.filter((a) => resumoVelho(resumos.get(a.licenca_id), agora)) : [];
  const comCelular = new Set(conectados.map((a) => a.licenca_id));
  const licenciados = clientes.filter((c) => c.licenca_id && c.situacao === "ativa");
  const semCelular = licenciados.filter((c) => !comCelular.has(c.licenca_id))
    .sort((a, b) => Number(b.aberturas_30d) - Number(a.aberturas_30d));

  alvo.append(
    el("div", { classe: "pagina-cabeca" }, [
      el("div", {}, [
        el("h1", { texto: "Celulares" }),
        el("p", { texto: "O Ver no celular de cada cliente: quem usa e se os dados estão chegando. " +
                         "Aqui aparece quando cada celular abriu e quando o resumo foi atualizado, " +
                         "nunca o que aparece nele." }),
      ]),
    ]),
    el("div", { classe: "tiles" }, [
      tile("Conectados", numero(conectados.length), `${numero(emUso.length)} abertos nos últimos 7 dias`),
      tile("Clientes com celular", `${numero(licenciados.filter((c) => comCelular.has(c.licenca_id)).length)} de ${numero(licenciados.length)}`,
        "das licenças ativas"),
      espelhos
        ? tile("Resumo atrasado", numero(atrasados.length), "computador sem atualizar há 2 dias ou mais",
            conectados.length ? (atrasados.length ? "ruim" : "ok") : "")
        : tile("Resumo atrasado", "—", "falta atualizar o banco do painel"),
      tile("Desconectados", numero(desconectados.length), "pelo Hub ou por aqui"),
    ])
  );

  alvo.append(cartao("Conectados", tabela(
    ["Cliente", "Aparelho", "Abriu", "Resumo dos dados", "Situação", ""],
    conectados,
    (a) => {
      const dono = donoDa.get(a.licenca_id) || {};
      const resumo = resumos.get(a.licenca_id);
      const estado = estadoDoCelular(a, agora);
      return [
        pessoa(dono.nome, dono.email),
        aparelho(a, apelidos),
        relativo(a.ultimo_acesso, agora),
        espelhos
          ? el("div", {}, [
              resumo ? `atualizado ${relativo(resumo, agora)}` : "nenhum ainda",
              resumoVelho(resumo, agora)
                ? el("div", { classe: "nota-alerta", texto: "o celular está mostrando dado velho: o Hub não está publicando" })
                : null,
            ])
          : "—",
        pilula(ESTADOS_DO_CELULAR[estado].texto, ESTADOS_DO_CELULAR[estado].tom),
        botaoDesconectar(a, dono),
      ];
    },
    { aoClicar: (a) => donoDa.get(a.licenca_id) && ficha(donoDa.get(a.licenca_id)),
      vazioTexto: "Nenhum celular conectado. O cliente conecta pelo Hub: menu da empresa > Ver no celular." }
  )));

  alvo.append(cartao("Ainda sem celular", tabela(
    ["Cliente", "Módulos", { texto: "Uso 30d", numero: true }, "Último uso", ""],
    semCelular,
    (c) => [
      pessoa(c.nome, c.email),
      el("div", { classe: "modulos-lista" }, (c.produtos_codigos || []).map((codigo) => pilulaModulo(codigo))),
      numero(c.aberturas_30d),
      quando(c.ultimo_uso),
      botaoWhatsApp(c.telefone, mensagemDeAcompanhamento("celular", { nome: c.nome })),
    ],
    { aoClicar: (c) => ficha(c), vazioTexto: "Todo cliente com licença ativa já conectou o celular." }
  ), el("span", { classe: "cartao-nota", texto: "licenças ativas, quem mais usa primeiro" })));

  if (desconectados.length) {
    alvo.append(cartao("Desconectados", tabela(
      ["Cliente", "Aparelho", "Abriu pela última vez", "Desconectado"],
      desconectados,
      (a) => {
        const dono = donoDa.get(a.licenca_id) || {};
        return [pessoa(dono.nome, dono.email), aparelho(a, apelidos), relativo(a.ultimo_acesso, agora),
                quando(a.revogado_em)];
      },
      { aoClicar: (a) => donoDa.get(a.licenca_id) && ficha(donoDa.get(a.licenca_id)) }
    )));
  }
}

/** "Moto G" / conectado há 3 dias, pelo Caixa. */
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
