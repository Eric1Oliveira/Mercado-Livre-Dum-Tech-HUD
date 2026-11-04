// Clientes: todo mundo numa lista só (assinantes, testes, vitalícios e quem
// ainda não tem licença), com busca, atalhos, filtros que se combinam,
// etiquetas em massa e exportação. Clicar em alguém abre a ficha.
//
// O que filtra e ordena mora em gestao.js, testado. Aqui só se desenha. A
// atualização do Hub (versões, Atualizar e Forçar) mora na tela Hub.
//
// Busca, filtros e ordem sobrevivem ao redesenho e voltam na próxima visita:
// a tela se atualiza sozinha (tempo real, presença) e ninguém perde o recorte.

import { atualizar } from "../api.js";
import { contagem, dinheiro, numero, relativo } from "../formato.js";
import { carregarGestao } from "../gestao-dados.js";
import {
  ATALHOS, GRUPOS, atalhoAtivo, contarOpcoes, csvDosClientes, filtrar, lerEtiquetas, opcoesDoGrupo,
  ordenarLinhas, quantosFiltros,
} from "../gestao.js";
import { SITUACAO } from "../mensalidade.js";
import { MODULOS, modulo } from "../modulos.js";
import { recarregar } from "../painel.js";
import { ESTADOS_DE_USO, diaLocal } from "../saude.js";
import { agir, chips, el, iniciaisDe, limpar, pilula, pilulaSituacao, recado, tabela } from "../ui.js";
import { ficha } from "./comercial.js";

const CHAVE = "dumtech.painel.clientes";

const estado = {
  busca: "", filtros: {}, ordem: { campo: "nome", crescente: true }, selecionados: new Set(), aberta: "",
  ...lembrado(),
};

function lembrado() {
  try {
    const { busca = "", filtros = {}, ordem } = JSON.parse(localStorage.getItem(CHAVE) || "{}");
    return { busca, filtros, ...(ordem ? { ordem } : {}) };
  } catch {
    return {};
  }
}

function guardar() {
  try {
    const { busca, filtros, ordem } = estado;
    localStorage.setItem(CHAVE, JSON.stringify({ busca, filtros, ordem }));
  } catch {
    /* sem memória do navegador o filtro vale só até recarregar a página */
  }
}

// Um menu aberto fecha ao clicar fora, em qualquer tela
document.addEventListener("click", (evento) => {
  if (!estado.aberta || evento.target.closest?.(".faceta")) return;
  estado.aberta = "";
  for (const menu of document.querySelectorAll(".faceta[open]")) menu.open = false;
});

export async function clientes(alvo) {
  const agora = new Date();
  const dados = await carregarGestao(agora);
  const { linhas } = dados;
  const ids = new Set(linhas.map((l) => l.id));
  estado.selecionados = new Set([...estado.selecionados].filter((id) => ids.has(id)));

  const busca = el("input", { type: "search", placeholder: "Nome, e-mail, chave, telefone, etiqueta…",
                              "aria-label": "Buscar cliente" });
  busca.value = estado.busca;
  const areaFiltros = el("div", { classe: "gestao-filtros" });
  const areaLista = el("div", {});
  const areaSelecao = el("div", { classe: "gestao-selecao-area" });
  const subtitulo = el("p", {});

  const desenhar = () => {
    const visiveis = ordenarLinhas(filtrar(linhas, estado, agora), estado.ordem.campo, estado.ordem.crescente);
    const online = linhas.filter((l) => l.online).length;
    const assinantes = linhas.filter((l) => l.mensal?.tipo === "assinatura").length;
    subtitulo.textContent = `${contagem(linhas.length, "cliente")} · ${contagem(assinantes, "assinante")} · ` +
      `${contagem(online, "online agora", "online agora")}`;
    limpar(areaFiltros).append(...barraDeFiltros(linhas, agora, desenhar).filter(Boolean));
    limpar(areaLista).append(lista(visiveis, linhas, desenhar, selecionar));
    desenharSelecao();
    focarOpcaoMarcada(areaFiltros);
  };

  // marcar um cliente nao redesenha a tabela: quem usa o teclado nao perde o lugar
  const desenharSelecao = () => {
    const barra = barraDeSelecao(linhas, desenhar);
    limpar(areaSelecao).append(...(barra ? [barra] : []));
  };
  const selecionar = (caixaDeTodas, visiveis) => {
    const marcadas = visiveis.filter((l) => estado.selecionados.has(l.id)).length;
    caixaDeTodas.checked = Boolean(visiveis.length) && marcadas === visiveis.length;
    caixaDeTodas.indeterminate = marcadas > 0 && marcadas < visiveis.length;
    desenharSelecao();
  };

  busca.addEventListener("input", () => {
    estado.busca = busca.value;
    guardar();
    desenhar();
  });

  alvo.append(
    el("div", { classe: "pagina-cabeca" }, [
      el("div", {}, [el("h1", { texto: "Clientes" }), subtitulo]),
      el("div", { classe: "ferramentas" }, [
        el("button", { classe: "botao botao-fantasma", texto: "Exportar", title: "Baixa os clientes filtrados (ou selecionados) em CSV",
                       onclick: () => exportar(linhas, agora) }),
      ]),
    ]),
    el("section", { classe: "cartao gestao-lista" }, [
      el("div", { classe: "gestao-busca" }, [busca]),
      areaFiltros,
      areaLista,
    ]),
    areaSelecao,
  );
  desenhar();
}

// ================================================================ filtros ===
function barraDeFiltros(linhas, agora, desenhar) {
  estado.maisFiltros ??= false;
  const marcados = quantosFiltros(estado.filtros);
  const atual = atalhoAtivo(estado.filtros);
  const mudar = (filtros) => {
    estado.filtros = filtros;
    guardar();
    desenhar();
  };

  const contas = contarOpcoes(linhas, estado, agora);
  const contaDoAtalho = (atalho) => filtrar(linhas, { busca: estado.busca, filtros: atalho.filtros }, agora).length;

  const finos = marcados && !atual; // filtro montado a mao, fora dos atalhos
  return [
    el("div", { classe: "gestao-atalhos" }, [
      chips(
        [{ valor: "", texto: "Todos", conta: filtrar(linhas, { busca: estado.busca }, agora).length },
         ...ATALHOS.map((a) => ({ valor: a.id, texto: a.texto, conta: contaDoAtalho(a) }))],
        finos ? "—" : atual,
        (valor) => mudar(valor ? { ...ATALHOS.find((a) => a.id === valor).filtros } : {}),
        "Atalhos de filtro"
      ),
      el("button", {
        type: "button", classe: "mais-filtros", "aria-expanded": estado.maisFiltros ? "true" : "false",
        "data-ativa": finos ? "sim" : null,
        texto: finos ? `Filtros · ${marcados}` : "Filtros",
        title: "Versão, módulo, licença, uso, validade, canal, etiqueta e mais",
        onclick: () => { estado.maisFiltros = !estado.maisFiltros; desenhar(); },
      }),
    ]),
    !estado.maisFiltros ? null : el("div", { classe: "facetas" }, [
      ...GRUPOS.map((grupo) => faceta(grupo, contas[grupo.id], mudar)),
      marcados
        ? el("button", { type: "button", classe: "faceta-limpar", texto: `Limpar ${marcados === 1 ? "filtro" : `${marcados} filtros`}`,
                         onclick: () => mudar({}) })
        : null,
    ]),
  ];
}

function faceta(grupo, conta, mudar) {
  const marcados = estado.filtros[grupo.id] || [];
  const opcoes = opcoesDoGrupo(grupo, conta, marcados, { rotuloModulo: (c) => modulo(c).nome });
  if (!opcoes.some((o) => o.conta || marcados.includes(o.valor))) return null;

  const menu = el("details", { classe: "faceta", open: estado.aberta === grupo.id, "data-grupo": grupo.id }, [
    el("summary", { "data-ativa": marcados.length ? "sim" : null }, [
      grupo.rotulo,
      marcados.length ? el("span", { classe: "faceta-conta", texto: String(marcados.length) }) : null,
    ]),
    el("div", { classe: "faceta-menu" }, opcoes
      .filter((o) => o.conta || marcados.includes(o.valor))
      .map((opcao) => {
        const caixa = el("input", {
          type: "checkbox", "data-valor": opcao.valor,
          onchange: (e) => {
            const valores = new Set(estado.filtros[grupo.id] || []);
            if (e.target.checked) valores.add(opcao.valor);
            else valores.delete(opcao.valor);
            estado.ultimaOpcao = opcao.valor;
            mudar({ ...estado.filtros, [grupo.id]: [...valores] });
          },
        });
        caixa.checked = marcados.includes(opcao.valor);
        return el("label", {}, [caixa, el("span", { texto: opcao.texto }),
                                el("span", { classe: "chip-conta", texto: numero(opcao.conta) })]);
      })),
  ]);
  menu.addEventListener("toggle", () => {
    if (menu.open) {
      estado.aberta = grupo.id;
      for (const outro of document.querySelectorAll(".faceta[open]")) if (outro !== menu) outro.open = false;
    } else if (estado.aberta === grupo.id) {
      estado.aberta = "";
    }
  });
  return menu;
}

/** Quem marca pelo teclado continua na mesma caixa depois do redesenho. */
function focarOpcaoMarcada(area) {
  if (!estado.ultimaOpcao) return;
  const seletor = `.faceta[open] input[data-valor="${CSS.escape(estado.ultimaOpcao)}"]`;
  estado.ultimaOpcao = "";
  area.querySelector(seletor)?.focus({ preventScroll: true });
}

// ================================================================== lista ===
function cabecalhoOrdem(texto, campo, desenhar) {
  const { ordem } = estado;
  const ativa = ordem.campo === campo;
  return el("button", {
    type: "button", classe: "ordem", "data-ativa": ativa ? "sim" : null,
    title: `Ordenar por ${texto.toLowerCase()}`,
    onclick: () => {
      estado.ordem = { campo, crescente: ativa ? !ordem.crescente : campo === "nome" };
      guardar();
      desenhar();
    },
  }, [texto, ativa ? el("span", { "aria-hidden": "true", texto: ordem.crescente ? " ↑" : " ↓" }) : null]);
}

function lista(visiveis, linhas, desenhar, selecionar) {
  const todas = el("input", { type: "checkbox", "aria-label": "Selecionar todos os clientes da lista" });
  const aoMarcar = () => selecionar(todas, visiveis);
  aoMarcar();
  todas.addEventListener("change", () => {
    for (const linha of visiveis) {
      if (todas.checked) estado.selecionados.add(linha.id);
      else estado.selecionados.delete(linha.id);
    }
    desenhar();
  });

  const ordem = (texto, campo) => ({ texto, no: cabecalhoOrdem(texto, campo, desenhar) });

  return tabela(
    [{ texto: "", no: todas }, ordem("Cliente", "nome"), ordem("Plano", "mensal"), "Módulos",
     ordem("Uso em 30 dias", "uso"), ordem("Conexão", "conexao")],
    visiveis,
    (linha) => [
      caixaDaLinha(linha, aoMarcar),
      celulaCliente(linha),
      celulaPlano(linha),
      espectroDoCliente(linha),
      celulaUso(linha),
      celulaConexao(linha),
    ],
    {
      aoClicar: (linha) => ficha(linha.cliente),
      vazioTexto: linhas.length ? "Nenhum cliente com esses filtros." : "Nenhum cliente ainda.",
    }
  );
}

function caixaDaLinha(linha, aoMarcar) {
  const caixa = el("input", {
    type: "checkbox", "aria-label": `Selecionar ${linha.nome}`,
    onclick: (e) => e.stopPropagation(),
    onchange: (e) => {
      if (e.target.checked) estado.selecionados.add(linha.id);
      else estado.selecionados.delete(linha.id);
      aoMarcar();
    },
  });
  caixa.checked = estado.selecionados.has(linha.id);
  return caixa;
}

function celulaCliente(linha) {
  return el("div", { classe: "pessoa" }, [
    el("span", { classe: "avatar", "data-online": linha.online ? "sim" : null, texto: iniciaisDe(linha.nome) }),
    el("div", {}, [
      el("div", { classe: "nome", texto: linha.nome || "—" }),
      linha.cliente.email ? el("div", { classe: "sub", texto: linha.cliente.email }) : null,
      linha.etiquetas.length
        ? el("div", { classe: "etiquetas" }, linha.etiquetas.map((t) => el("span", { classe: "etiqueta", texto: t })))
        : null,
    ]),
  ]);
}

function celulaConexao(linha) {
  const total = linha.maquinas.length;
  if (linha.online) {
    return el("div", {}, [
      el("div", { classe: "hub-pc hub-online" }, [
        el("span", { classe: "hub-ponto", "data-aberto": "sim" }),
        total > 1 ? `${linha.online} de ${total} online` : "Online agora",
      ]),
      el("div", { classe: "sub-linha", texto: [linha.onlineDesde ? `aberto ${relativo(linha.onlineDesde)}` : "", linha.versoes[0] || ""]
        .filter(Boolean).join(" · ") }),
    ]);
  }
  return el("div", {}, [
    el("div", { classe: "hub-pc" }, [el("span", { classe: "hub-ponto" }), linha.conexao === "nunca" ? "Nunca conectou" : "Offline"]),
    linha.visto || linha.versoes[0]
      ? el("div", { classe: "sub-linha", texto: [linha.visto ? `visto ${relativo(linha.visto)}` : "", linha.versoes[0] || ""]
          .filter(Boolean).join(" · ") })
      : null,
  ]);
}

/** Mensal: a situação e o plano. Vitalício: só "Vitalícia" (nada de cobrança). */
function celulaPlano(linha) {
  const { cliente, mensal } = linha;
  if (mensal) {
    const s = SITUACAO[mensal.situacao] || { texto: mensal.situacao, tom: "neutro" };
    return el("div", {}, [
      pilula(s.texto, s.tom),
      el("div", { classe: "sub-linha", texto: `${mensal.plano_nome || "Montado"} · ${dinheiro(mensal.valor)}/mês` }),
    ]);
  }
  if (!cliente.licenca_id) return pilula("Sem licença", "neutro");
  if (cliente.situacao !== "ativa") return pilulaSituacao(cliente.situacao);
  return el("div", {}, [
    pilula("Vitalícia", "marca"),
    Number(cliente.total_comprado)
      ? el("div", { classe: "sub-linha", texto: `comprou ${dinheiro(cliente.total_comprado)}` })
      : null,
  ]);
}

/** Os sete módulos, na ordem do Hub: aceso tem, listrado está testando, apagado não tem. */
function espectroDoCliente(linha) {
  const nomes = linha.modulos.map((c) => modulo(c).nome);
  const emTeste = linha.testando.map((c) => modulo(c).nome);
  const descricao = [nomes.join(", ") || "nenhum módulo", emTeste.length ? `em teste: ${emTeste.join(", ")}` : ""]
    .filter(Boolean).join(" · ");
  return el("div", { classe: "espectro-modulos", title: descricao, role: "img", "aria-label": descricao },
    Object.keys(MODULOS).map((codigo) => el("i", {
      estilo: `--cor:${MODULOS[codigo].cor}`,
      "data-tem": linha.modulos.includes(codigo) ? "sim" : null,
      "data-teste": linha.testando.includes(codigo) ? "sim" : null,
    })));
}

function celulaUso(linha) {
  if (!linha.uso) return el("span", { classe: "sub-linha", texto: "—" });
  const { texto, tom } = ESTADOS_DE_USO[linha.uso];
  return el("div", {}, [
    pilula(texto, tom),
    el("div", { classe: "sub-linha", texto: linha.aberturas
      ? `${numero(linha.aberturas)} ${linha.aberturas === 1 ? "abertura" : "aberturas"}` : "nenhuma abertura" }),
  ]);
}

// =============================================================== seleção ===
function barraDeSelecao(linhas, desenhar) {
  const escolhidos = linhas.filter((l) => estado.selecionados.has(l.id));
  if (!escolhidos.length) return null;

  const etiqueta = el("input", { type: "text", placeholder: "Nova etiqueta", maxlength: "30", "aria-label": "Etiqueta para os selecionados" });
  const limparSelecao = () => {
    estado.selecionados.clear();
    desenhar();
  };

  return el("div", { classe: "gestao-selecao", role: "region", "aria-label": "Clientes selecionados" }, [
    el("strong", { texto: `${contagem(escolhidos.length, "selecionado")}` }),
    el("span", { classe: "gestao-selecao-etiqueta" }, [
      etiqueta,
      el("button", {
        classe: "botao botao-noite botao-mini", texto: "Etiquetar",
        onclick: (e) => {
          const novas = lerEtiquetas(etiqueta.value);
          if (!novas.length) return recado("Escreva a etiqueta primeiro.", "erro");
          agir(e.currentTarget, async () => {
            await Promise.all(escolhidos.map((l) => atualizar("clientes", { id: `eq.${l.id}` }, {
              etiquetas: lerEtiquetas([...l.etiquetas, ...novas].join(",")),
            })));
            await recarregar();
          }, { feito: `Etiqueta aplicada em ${contagem(escolhidos.length, "cliente")}.`, erro: "Não consegui etiquetar." });
        },
      }),
    ]),
    el("button", { classe: "botao botao-noite botao-mini", texto: "Limpar seleção", onclick: limparSelecao }),
  ]);
}

// ============================================================== exportar ===
function exportar(linhas, agora) {
  const selecionados = linhas.filter((l) => estado.selecionados.has(l.id));
  const escolhidos = selecionados.length ? selecionados : filtrar(linhas, estado, agora);
  const ligacao = el("a", {
    href: URL.createObjectURL(new Blob([csvDosClientes(escolhidos)], { type: "text/csv;charset=utf-8" })),
    download: `clientes-dumtech-${diaLocal(agora)}.csv`,
  });
  ligacao.click();
  setTimeout(() => URL.revokeObjectURL(ligacao.href), 1000);
  recado(`${contagem(escolhidos.length, "cliente exportado", "clientes exportados")}.`, "ok");
}
