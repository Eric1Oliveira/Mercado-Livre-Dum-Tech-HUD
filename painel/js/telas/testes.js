// Testes grátis: quem está testando o quê, quanto usou e se virou compra.
//
// O teste começa pelo Hub do cliente ("Testar grátis") ou pela ficha dele aqui.
// Estender e encerrar chegam ao Hub em até 2 minutos: o fim do teste vai
// dentro da licença assinada, e a impressão digital da licença inclui os
// testes (migration 20261019120000).

import { atualizar, inserir, ler } from "../api.js";
import { data, dinheiro, numero, quando } from "../formato.js";
import { mensagemDeAcompanhamento } from "../mensagens.js";
import { modulo } from "../modulos.js";
import { recarregar } from "../painel.js";
import {
  DIAS_DE_TESTE, ESTADOS_DO_TESTE, FALTA_MIGRATION, andamentoDoTeste, estadoDoTeste, fimEstendido,
  ordenarTestes, prazoDoTeste, resumoDosTestes,
} from "../saude.js";
import {
  agir, barra, botaoWhatsApp, cartao, chips, confirmar, el, limpar, pessoa, pilula, pilulaModulo,
  tabela, tile, vazio,
} from "../ui.js";
import { ficha } from "./comercial.js";

const CHEGA_AO_HUB = "O Hub do cliente recebe em até 2 minutos, assim que estiver com internet.";
const COR_DO_PRAZO = { rodando: "var(--violeta)", acabando: "var(--aviso)", terminou: "#b9b5c8", comprou: "var(--ok)" };
const filtroTestes = { estado: "" };
const GRUPOS = {
  testando: (e) => e === "rodando" || e === "acabando",
  terminou: (e) => e === "terminou",
  comprou: (e) => e === "comprou",
};

export async function testes(alvo) {
  const agora = new Date();
  const [lista, clientes] = await Promise.all([
    ler("painel_testes", { ordem: "termina_em.desc" }).catch(() => null),
    ler("painel_clientes", { ordem: "nome.asc" }),
  ]);
  const cabeca = el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Testes grátis" }),
      el("p", { texto: "Quem está testando o quê, quanto usou e se virou compra. " +
                       "Para dar um teste, abra a ficha do cliente." }),
    ]),
  ]);
  if (!lista) {
    alvo.append(cabeca, cartao("", vazio("O banco ainda não mostra os testes ao painel", FALTA_MIGRATION)));
    return;
  }
  const porId = new Map(clientes.map((c) => [c.cliente_id, c]));
  const r = resumoDosTestes(lista, agora);
  const receita = lista.filter((t) => t.comprou).reduce((soma, t) => soma + Number(t.preco || 0), 0);

  alvo.append(
    cabeca,
    el("div", { classe: "tiles" }, [
      tile("Testando agora", numero(r.testando),
        r.acabando ? `${numero(r.acabando)} terminam em até 2 dias` : "nenhum termina nos próximos 2 dias"),
      tile("Viraram compra", numero(r.comprou),
        r.conversao === null ? "nenhum teste terminou ainda" : `${r.conversao}% dos testes que terminaram`,
        r.comprou ? "ok" : ""),
      tile("Usaram o teste", r.total ? `${numero(r.usaram)} de ${numero(r.total)}` : "—",
        "abriram o módulo durante o teste"),
      tile("Receita dos testes", dinheiro(receita), "módulos comprados depois do teste, pelo preço de tabela"),
    ])
  );

  const destino = el("div", {});
  const conta = (grupo) => lista.filter((t) => GRUPOS[grupo](estadoDoTeste(t, agora))).length;
  const opcoes = [
    { valor: "", texto: "Todos", conta: lista.length },
    { valor: "testando", texto: "Testando", conta: conta("testando") },
    { valor: "terminou", texto: "Terminaram sem comprar", conta: conta("terminou") },
    { valor: "comprou", texto: "Compraram", conta: conta("comprou") },
  ];
  const desenhar = () => {
    const visiveis = ordenarTestes(lista, agora).filter((t) =>
      !filtroTestes.estado || GRUPOS[filtroTestes.estado](estadoDoTeste(t, agora)));
    limpar(destino).append(
      lista.length
        ? el("div", { classe: "cartao-filtros" }, [
            chips(opcoes, filtroTestes.estado, (valor) => { filtroTestes.estado = valor; desenhar(); },
                  "Filtrar testes"),
          ])
        : null,
      tabela(
        ["Cliente", "Módulo", "Situação", { texto: "Uso no teste", numero: true }, ""],
        visiveis,
        (t) => {
          const cliente = porId.get(t.cliente_id) || {};
          return [
            pessoa(cliente.nome, cliente.email),
            pilulaModulo(t.codigo),
            periodo(t, agora),
            usoNoTeste(t),
            el("div", { classe: "ferramentas" }, acoesDoTeste(t, cliente, agora)),
          ];
        },
        {
          aoClicar: (t) => porId.get(t.cliente_id) && ficha(porId.get(t.cliente_id)),
          vazioTexto: lista.length ? "Nenhum teste nesta situação."
            : "Nenhum teste grátis ainda. Ele começa no Hub do cliente, no botão Testar grátis de cada módulo.",
        }
      )
    );
  };
  desenhar();
  alvo.append(cartao("Testes", destino));
}

/** A situação do teste e a barrinha do período: quanto dos dias já passou. */
export function periodo(teste, agora = new Date()) {
  const estado = estadoDoTeste(teste, agora);
  const feito = estado === "comprou" || estado === "terminou" ? 1 : andamentoDoTeste(teste, agora);
  const curta = (valor) => data(valor).slice(0, 5);
  return el("div", { classe: "periodo", title: `${data(teste.iniciado_em)} a ${data(teste.termina_em)}` }, [
    pilula(ESTADOS_DO_TESTE[estado].texto, ESTADOS_DO_TESTE[estado].tom),
    barra(Math.round(feito * 100), 100, COR_DO_PRAZO[estado]),
    el("div", { classe: "sub-linha", texto: estado === "comprou"
      ? `comprou ${quando(teste.comprou_em)}`
      : `${prazoDoTeste(teste, agora)} · ${curta(teste.iniciado_em)} a ${curta(teste.termina_em)}` }),
  ]);
}

export function usoNoTeste(teste) {
  const aberturas = Number(teste.aberturas || 0);
  if (!aberturas) return el("span", { classe: "sub-linha", texto: "não abriu" });
  return el("div", {}, [
    `${numero(aberturas)} ${aberturas === 1 ? "abertura" : "aberturas"}`,
    el("div", { classe: "sub-linha", texto: `em ${numero(teste.dias_de_uso)} ${Number(teste.dias_de_uso) === 1 ? "dia" : "dias"}` }),
  ]);
}

const filtroDoTeste = (teste) => ({ licenca_id: `eq.${teste.licenca_id}`, produto_id: `eq.${teste.produto_id}` });

/** Os botões de um teste (a tela de testes e a ficha do cliente usam os mesmos). */
export function acoesDoTeste(teste, cliente = {}, agora = new Date(), { depois = recarregar } = {}) {
  const estado = estadoDoTeste(teste, agora);
  if (estado === "comprou") return [];
  const nomeDoModulo = modulo(teste.codigo).nome;
  const botao = (texto, classe, titulo, fazer) => el("button", {
    type: "button", classe: `botao ${classe} botao-mini`, texto, title: titulo,
    onclick: (evento) => {
      evento.stopPropagation(); // a linha abre a ficha; o botão, não
      fazer(evento.currentTarget);
    },
  });

  const estender = botao("+7 dias", "botao-fantasma",
    estado === "terminou" ? "Reabre o teste por mais 7 dias, a partir de agora" : "Mais 7 dias a partir do fim atual",
    (alvo) => {
      const fim = fimEstendido(teste.termina_em, DIAS_DE_TESTE, new Date());
      agir(alvo, async () => {
        await atualizar("licenca_testes", filtroDoTeste(teste), { termina_em: fim });
        await depois();
      }, { feito: `Teste do módulo ${nomeDoModulo} vai até ${data(fim)}. ${CHEGA_AO_HUB}` });
    });

  const encerrar = estado === "terminou" ? null : botao("Encerrar", "botao-perigo",
    "O módulo deixa de abrir no Hub do cliente",
    (alvo) => {
      if (!confirmar(`Encerrar agora o teste do módulo ${nomeDoModulo}${cliente.nome ? ` de ${cliente.nome}` : ""}? ` +
                     "O módulo deixa de abrir no Hub do cliente em até 2 minutos.")) return;
      agir(alvo, async () => {
        await atualizar("licenca_testes", filtroDoTeste(teste), { termina_em: new Date().toISOString() });
        await depois();
      }, { feito: "Teste encerrado." });
    });

  const conversa = botaoWhatsApp(cliente.telefone, mensagemDeAcompanhamento(
    estado === "terminou" ? "teste_fim" : "teste", { nome: cliente.nome, modulo: nomeDoModulo }));
  return [estender, encerrar, conversa].filter(Boolean);
}

/** "Dar teste": um módulo que o cliente não tem e ainda não testou. */
export async function darTeste(botao, { licencaId, produto, depois = recarregar }) {
  const fim = fimEstendido(null, DIAS_DE_TESTE, new Date());
  await agir(botao, async () => {
    await inserir("licenca_testes", { licenca_id: licencaId, produto_id: produto.id, termina_em: fim });
    await depois();
  }, { feito: `Teste de ${DIAS_DE_TESTE} dias do módulo ${modulo(produto.codigo).nome} liberado. ${CHEGA_AO_HUB}`,
       erro: "Não deu para liberar o teste." });
}
