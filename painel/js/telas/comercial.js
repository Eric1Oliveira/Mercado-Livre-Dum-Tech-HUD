// Resumo, clientes (com a ficha) e pedidos.
//
// A ficha do cliente é o coração do painel: tudo o que a DumTech sabe daquela
// pessoa numa tela só — e as ações que resolvem o caso sem sair dali.

import { apagar, atualizar, funcao, inserir, ler, rpc, um } from "../api.js";
import { CONFIG } from "../config.js";
import { PALAVRA, confere, exclusaoPesada, filtroDeBusca } from "../exclusao.js";
import {
  ASSUNTO_DA_CHAVE, contatosNoTexto, linkEmail, linkWhatsApp, mensagemDaChave, mensagemDeAcompanhamento,
} from "../mensagens.js";
import {
  contagem, data, dataHora, dinheiro, documento as fmtDocumento, numero, quando, relativo, telefone,
} from "../formato.js";
import { faixa } from "../graficos.js";
import {
  abrirGaveta, fecharGaveta, folhaDaGaveta, irPara, marcarPedidos, recarregar, substituirNaGaveta,
} from "../painel.js";
import { cor, modulo } from "../modulos.js";
import {
  ESTADOS_DO_CELULAR, estadoDoCelular, estadoDoTeste, hubAberto, resumoMaisNovo,
  serieDiaria, versaoEmDia, vistoEm,
} from "../saude.js";
import {
  agir, barra, botaoWhatsApp, cartao, confirmar, el, limpar, pessoa, pilula, pilulaModulo,
  pilulaSituacao, recado, tabela, tile, vazio,
} from "../ui.js";
import { aparelho, botaoDesconectar } from "./celulares.js";
import { acoesDoTeste, darTeste, periodo, usoNoTeste } from "./testes.js";

const JANELA = 30;
// Desde o Hub 1.2.4 a consulta leve de 2 em 2 minutos traz uma impressao
// digital da licenca (migration 20260921120000): mudou, o Hub reconfere na hora.
// Hubs mais antigos ainda conferem de hora em hora - por isso os dois prazos.
const AVISO_HUB = "O Hub do cliente recebe em até 2 minutos, assim que estiver com internet " +
                  "(versões anteriores à 1.2.4: em até 1 hora).";
const diaLimite = (dias) =>
  new Date(Date.now() - dias * 86400000).toISOString().slice(0, 10);

// ================================================================= resumo ====
export async function resumo(alvo) {
  const [resumoLinha, pedidosAbertos, modulos, recentes] = await Promise.all([
    um("painel_resumo"),
    ler("pedidos_abertos", { limite: 6 }),
    ler("painel_modulos", { ordem: "aberturas_30d.desc" }),
    ler("painel_clientes", { ordem: "cliente_desde.desc", limite: 6 }),
  ]);
  const r = resumoLinha || {};
  marcarPedidos(Number(r.pedidos_abertos || 0));

  alvo.append(
    el("div", { classe: "pagina-cabeca" }, [
      el("div", {}, [
        el("h1", { texto: "Resumo" }),
        el("p", { texto: "O retrato do negócio agora." }),
      ]),
    ]),
    el("div", { classe: "tiles" }, [
      tile("Clientes", numero(r.clientes), `${numero(r.interessados)} sem compra`),
      tile("Licenças ativas", numero(r.licencas_ativas),
        Number(r.licencas_vencidas) ? `${numero(r.licencas_vencidas)} vencidas` : "todas no prazo",
        Number(r.licencas_vencidas) ? "ruim" : ""),
      tile("Módulos vendidos", numero(r.modulos_vendidos), `${numero(r.computadores)} computadores`),
      tile("Vendido", dinheiro(r.vendido), "loja, Mercado Livre e venda direta", "ok"),
      tile("Pedidos abertos", numero(r.pedidos_abertos), "esperando você",
        Number(r.pedidos_abertos) ? "ruim" : ""),
      tile("Aberturas (30d)", numero(r.aberturas_30d), "uso dos módulos"),
      tile("Tentativas 24h", numero(r.tentativas_24h), "chaves recusadas",
        Number(r.tentativas_24h) > 20 ? "ruim" : ""),
    ])
  );

  if (pedidosAbertos.length) {
    alvo.append(cartao(
      "Precisa de você",
      tabela(
        ["Quem", "Kit", { texto: "Total", numero: true }, "Quando"],
        pedidosAbertos,
        (p) => [
          pessoa(p.nome, p.email),
          p.kit || "—",
          dinheiro(p.total),
          quando(p.criado_em),
        ],
        { aoClicar: () => irPara("pedidos") }
      ),
      el("button", {
        classe: "botao botao-primario botao-mini", texto: "Ver pedidos",
        onclick: () => irPara("pedidos"),
      })
    ));
  }

  const maisUsado = modulos.filter((m) => Number(m.aberturas_30d) > 0);
  const teto = Math.max(1, ...maisUsado.map((m) => Number(m.aberturas_30d)));
  alvo.append(cartao(
    "Módulos, por uso nos últimos 30 dias",
    maisUsado.length
      ? tabela(
          ["Módulo", { texto: "Clientes", numero: true }, { texto: "Aberturas", numero: true }, "Proporção"],
          maisUsado,
          (m) => [
            pilulaModulo(m.codigo),
            numero(m.clientes),
            numero(m.aberturas_30d),
            barra(Number(m.aberturas_30d), teto, cor(m.codigo)),
          ]
        )
      : vazio("Ninguém mandou uso ainda",
              "O Hub envia o resumo quando fala com o servidor; espere o primeiro dia de uso.")
  ));

  alvo.append(cartao(
    "Últimos cadastros",
    tabela(
      ["Cliente", "Situação", "Módulos", "Entrou"],
      recentes,
      (c) => [
        pessoa(c.nome, c.email),
        pilulaSituacao(c.situacao),
        listaDeModulos(c.produtos_codigos),
        quando(c.cliente_desde),
      ],
      { aoClicar: (c) => ficha(c) }
    )
  ));
}

const listaDeModulos = (codigos) =>
  el("div", { classe: "modulos-lista" },
    (codigos || []).length
      ? (codigos || []).map((c) => pilulaModulo(c))
      : [el("span", { classe: "pilula", "data-tom": "neutro", texto: "nenhum" })]);

// =============================================================== clientes ====
// A busca sobrevive ao redesenho: quando a tela se atualiza sozinha (tempo
// real), o que foi digitado e o filtro escolhido continuam ali.
const filtroClientes = { busca: "", situacao: "" };

export async function clientes(alvo) {
  const busca = el("input", { type: "search", placeholder: "Nome, e-mail ou chave…" });
  const filtro = el("select", {}, [
    el("option", { value: "", texto: "Todas as situações" }),
    el("option", { value: "ativa", texto: "Ativas" }),
    el("option", { value: "suspensa", texto: "Suspensas" }),
    el("option", { value: "expirada", texto: "Vencidas" }),
    el("option", { value: "cancelada", texto: "Canceladas" }),
    el("option", { value: "sem", texto: "Sem licença (interessados)" }),
  ]);
  const destino = el("div", {});

  alvo.append(
    el("div", { classe: "pagina-cabeca" }, [
      el("div", {}, [
        el("h1", { texto: "Clientes" }),
        el("p", { texto: "Clique em alguém para abrir a ficha completa." }),
      ]),
      el("div", { classe: "ferramentas" }, [
        busca, filtro,
        el("button", { classe: "botao botao-fantasma", texto: "Novo cliente", onclick: () => novoCliente() }),
        el("button", { classe: "botao botao-primario", texto: "Nova venda", onclick: () => novaVenda() }),
      ]),
    ]),
    destino
  );

  const linhas = await ler("painel_clientes", { ordem: "nome.asc" });

  const desenhar = () => {
    const termo = busca.value.trim().toLowerCase();
    const situacaoEscolhida = filtro.value;
    const visiveis = linhas.filter((c) => {
      const combina = !termo
        || `${c.nome} ${c.email} ${c.chave || ""}`.toLowerCase().includes(termo);
      const situacaoOk = !situacaoEscolhida
        || (situacaoEscolhida === "sem" ? !c.chave : c.situacao === situacaoEscolhida);
      return combina && situacaoOk;
    });

    limpar(destino).append(cartao(
      `${contagem(visiveis.length, "cliente")}`,
      tabela(
        ["Cliente", "Licença", "Situação", "Módulos",
         { texto: "PCs", numero: true }, { texto: "Uso 30d", numero: true }, "Último uso"],
        visiveis,
        (c) => [
          pessoa(c.nome, c.email),
          c.chave ? el("code", { texto: c.chave }) : "—",
          pilulaSituacao(c.chave ? c.situacao : null),
          listaDeModulos(c.produtos_codigos),
          c.chave ? `${c.computadores}/${c.max_computadores}` : "—",
          numero(c.aberturas_30d),
          quando(c.ultimo_uso),
        ],
        { aoClicar: (c) => ficha(c), vazioTexto: "Nenhum cliente com esse filtro." }
      )
    ));
  };

  busca.value = filtroClientes.busca;
  filtro.value = filtroClientes.situacao;
  busca.addEventListener("input", () => { filtroClientes.busca = busca.value; desenhar(); });
  filtro.addEventListener("change", () => { filtroClientes.situacao = filtro.value; desenhar(); });
  desenhar();
}

// ================================================================== ficha ====
export async function ficha(cliente, { silencioso = false } = {}) {
  // `silencioso`: a ficha ja esta aberta e so precisa refletir o que mudou -
  // monta a nova por tras e troca de uma vez, sem voltar ao "Carregando".
  const antiga = silencioso ? folhaDaGaveta() : null;
  if (silencioso && !antiga) return;
  const destino = silencioso
    ? document.createElement("div")
    : abrirGaveta({ acima: "Cliente", titulo: cliente.nome || cliente.email });

  // Depois de mexer em algo, a ficha volta do banco (uma ficha que continua
  // mostrando o estado antigo mente) e a tela de baixo se corrige por tras.
  const refazer = async () => {
    recarregar();
    const novo = await um("painel_clientes", {
      filtros: { cliente_id: `eq.${cliente.cliente_id}` }, fresco: true,
    });
    if (novo) await ficha(novo, { silencioso: true });
    else fecharGaveta();
  };

  // o que e deste cliente vem sempre do banco quando a ficha e refeita
  const fresco = silencioso;
  const daLicenca = (tabela, opcoes = {}) => (cliente.licenca_id
    ? ler(tabela, { ...opcoes, filtros: { licenca_id: `eq.${cliente.licenca_id}`, ...opcoes.filtros } })
    : Promise.resolve([]));
  const [produtos, combos, liberados, maquinas, uso, recomendacoes, pedidosDoCliente,
         testesDoCliente, aparelhos, espelhos, modulosPagos, versoes] =
    await Promise.all([
      ler("produtos", { ordem: "codigo.asc" }),
      ler("combos", { ordem: "codigo.asc" }),
      daLicenca("licenca_produtos", { fresco }),
      daLicenca("ativacoes", { ordem: "ativado_em.asc", fresco }),
      daLicenca("uso_diario", { filtros: { dia: `gte.${diaLimite(JANELA)}` } }),
      ler("painel_recomendacoes", { filtros: { cliente_id: `eq.${cliente.cliente_id}` },
                                    ordem: "aberturas_origem.desc", fresco }),
      ler("pedidos_site", { filtros: { cliente_id: `eq.${cliente.cliente_id}` },
                            ordem: "criado_em.desc", limite: 10, fresco }),
      // sem a migration 20261019120000 estas tres nao existem: a ficha abre sem elas
      daLicenca("painel_testes", { ordem: "iniciado_em.desc", fresco }).catch(() => null),
      daLicenca("celular_aparelhos", {
        select: "id,licenca_id,nome,maquina,criado_em,ultimo_acesso,revogado_em", ordem: "criado_em.desc", fresco,
      }),
      daLicenca("celular_espelhos", { select: "licenca_id,maquina,atualizado_em" }).catch(() => null),
      daLicenca("painel_modulos_da_licenca").catch(() => []),
      ler("hub_versoes", { limite: 1 }).catch(() => null),
    ]);
  const agora = new Date();
  const publicada = String(versoes?.[0]?.versao || "");

  const porId = new Map(produtos.map((p) => [p.id, p]));
  const tem = liberados.map((l) => porId.get(l.produto_id)?.codigo).filter(Boolean);
  const naoTem = produtos.filter((p) => p.ativo && !tem.includes(p.codigo));

  limpar(destino);

  // ---------------------------------------------------------------- dados --
  destino.append(cartao("Dados", el("div", { classe: "dados" }, [
    dado("E-mail", cliente.email || "— (liga sozinho quando ele ativar o Hub)"),
    dado("Telefone", telefone(cliente.telefone) || "—"),
    dado("Documento", fmtDocumento(cliente.documento) || "—"),
    dado("Origem", cliente.origem === "hub" ? "Hub ou loja" : "Cadastrado no painel"),
    dado("Cliente desde", data(cliente.cliente_desde)),
    dado("Comprou", dinheiro(cliente.total_comprado)),
  ]), el("button", {
    classe: "botao botao-fantasma botao-mini", texto: "Editar", onclick: () => editarCliente(cliente),
  })));

  // -------------------------------------------------------------- licença --
  if (cliente.licenca_id) {
    const acoes = el("div", { classe: "acoes-linha" });
    const mudarStatus = (novo, texto) =>
      el("button", {
        classe: "botao botao-fantasma botao-mini", texto,
        onclick: (e) => agir(e.target, async () => {
          await atualizar("licencas", { id: `eq.${cliente.licenca_id}` }, { status: novo });
          await refazer();
        }, { feito: `Licença ${texto.toLowerCase()}. ${AVISO_HUB}` }),
      });

    acoes.append(
      el("button", {
        classe: "botao botao-primario botao-mini", texto: "Enviar chave",
        onclick: () => enviarChave(cliente.licenca_id, { reserva: reservaDoCliente(cliente) }),
      }),
      el("button", {
        classe: "botao botao-fantasma botao-mini", texto: "Registrar venda",
        title: "Vendeu mais um módulo por fora da loja (Mercado Livre, WhatsApp, telefone)",
        onclick: () => novaVenda({ cliente }),
      }),
      el("button", {
        classe: "botao botao-fantasma botao-mini", texto: "Editar licença",
        title: "Tipo, vencimento e número de computadores",
        onclick: () => editarLicenca(cliente),
      }),
    );
    if (cliente.status !== "ativa") acoes.append(mudarStatus("ativa", "Reativar"));
    if (cliente.status === "ativa") acoes.append(mudarStatus("suspensa", "Suspender"));
    if (cliente.status !== "cancelada") {
      acoes.append(el("button", {
        classe: "botao botao-perigo botao-mini", texto: "Cancelar",
        onclick: (e) => {
          if (!confirmar("Cancelar esta licença? Os módulos param de abrir no computador do cliente " +
                         "em até 2 minutos, assim que o Hub dele estiver com internet.")) return;
          agir(e.target, async () => {
            await atualizar("licencas", { id: `eq.${cliente.licenca_id}` }, { status: "cancelada" });
            await refazer();
          }, { feito: `Licença cancelada. ${AVISO_HUB}` });
        },
      }));
    }
    acoes.append(el("button", {
      classe: "botao botao-perigo botao-mini", texto: "Excluir licença",
      title: "Apaga a licença e tudo dela; o cadastro do cliente fica",
      onclick: () => excluirLicenca(cliente, { modulos: tem, maquinas }),
    }));

    destino.append(cartao("Licença", [
      el("div", { classe: "dados" }, [
        dado("Chave", el("code", { texto: cliente.chave })),
        dado("Situação", pilulaSituacao(cliente.situacao)),
        dado("Tipo", cliente.tipo || "—"),
        dado("Validade", cliente.expira_em ? data(cliente.expira_em) : "sem prazo"),
        dado("Computadores", `${cliente.computadores} de ${cliente.max_computadores}`),
        dado("Última checagem", dataHora(cliente.ultima_checagem)),
      ]),
      el("div", { estilo: "margin-top:14px" }, [acoes]),
    ]));
  } else {
    destino.append(cartao("Licença", [
      el("p", { estilo: "color:var(--tinta-media);margin-bottom:12px",
                texto: "Ainda não comprou. Fechou por WhatsApp, telefone ou Mercado Livre? Registre a venda: a chave sai na hora." }),
      el("button", {
        classe: "botao botao-primario botao-mini", texto: "Registrar venda e gerar a chave",
        onclick: () => novaVenda({ cliente }),
      }),
    ]));
  }

  // -------------------------------------------------------------- módulos --
  const escolha = el("select", {}, [
    el("option", { value: "", texto: "Liberar módulo…" }),
    ...naoTem.map((p) => el("option", { value: `p:${p.codigo}`, texto: `${p.nome} — ${dinheiro(p.preco)}` })),
    ...combos.filter((c) => c.ativo).map((c) =>
      el("option", { value: `c:${c.codigo}`, texto: `Combo ${c.nome} — ${dinheiro(c.preco)}` })),
  ]);
  const liberar = el("button", {
    classe: "botao botao-primario botao-mini", texto: "Liberar",
    onclick: (e) => {
      if (!escolha.value) {
        recado("Escolha um módulo primeiro.", "erro");
        return;
      }
      const [tipo, codigo] = escolha.value.split(":");
      agir(e.target, async () => {
        await rpc("dumtech_liberar_produtos", {
          p_licenca_id: cliente.licenca_id,
          p_produtos: tipo === "p" ? [codigo] : [],
          p_combo: tipo === "c" ? codigo : null,
        });
        await refazer();
      }, { feito: `Módulo liberado. ${AVISO_HUB}` });
    },
  });

  destino.append(cartao("Módulos", [
    el("div", { classe: "modulos-lista" }, [
      ...tem.map((codigo) => {
        const pilulaDoModulo = pilulaModulo(codigo);
        pilulaDoModulo.append(el("button", {
          classe: "botao botao-mini", estilo: "background:transparent;border:0;padding:0 0 0 4px;color:inherit",
          title: "Tirar este módulo da licença", texto: "×",
          onclick: (evento) => {
            evento.stopPropagation();
            if (!confirmar(`Tirar ${modulo(codigo).nome} desta licença?`)) return;
            const produto = produtos.find((p) => p.codigo === codigo);
            agir(evento.target, async () => {
              await apagar("licenca_produtos", {
                licenca_id: `eq.${cliente.licenca_id}`, produto_id: `eq.${produto.id}`,
              });
              await refazer();
            }, { feito: "Módulo removido." });
          },
        }));
        return pilulaDoModulo;
      }),
      // módulo em teste grátis aparece aceso, com o selo: ele abre no Hub até o fim do teste
      ...naoTem.map((p) => {
        const teste = (testesDoCliente || []).find((t) => t.produto_id === p.id && estadoDoTeste(t, agora) !== "terminou");
        if (!teste) return pilulaModulo(p.codigo, { apagada: true });
        const emTeste = pilulaModulo(p.codigo);
        emTeste.title = `Em teste grátis até ${data(teste.termina_em)}`;
        emTeste.append(el("span", { classe: "selo-teste", texto: "teste" }));
        return emTeste;
      }),
    ]),
    cliente.licenca_id
      ? el("div", { classe: "ferramentas", estilo: "margin-top:14px" }, [escolha, liberar])
      : null,
  ]));

  // ---------------------------------------------------------------- uso ----
  // os módulos pagos (com o último uso de sempre) e os abertos em teste
  const porModulo = new Map(modulosPagos.map((m) => [m.codigo, { aberturas: 0, ultimo: m.ultimo_uso }]));
  for (const linha of uso) {
    const atual = porModulo.get(linha.produto_codigo) || { aberturas: 0, ultimo: null };
    atual.aberturas += Number(linha.aberturas || 0);
    if (!atual.ultimo || linha.dia > atual.ultimo) atual.ultimo = linha.dia;
    porModulo.set(linha.produto_codigo, atual);
  }
  const usoOrdenado = [...porModulo.entries()].sort((a, b) => b[1].aberturas - a[1].aberturas);
  const tetoUso = Math.max(1, ...usoOrdenado.map(([, m]) => m.aberturas));
  const serieDoCliente = serieDiaria(uso, JANELA, agora);

  destino.append(cartao(`Uso nos últimos ${JANELA} dias`,
    usoOrdenado.length
      ? [
          el("div", { classe: "faixa-da-ficha" }, [
            faixa(serieDoCliente, Math.max(1, ...serieDoCliente.map((d) => d.valor)), { rotulo: cliente.nome }),
            el("div", { classe: "eixo-dias", "aria-hidden": "true" }, [
              el("span", { texto: data(serieDoCliente[0].dia).slice(0, 5) }), el("span", { texto: "hoje" }),
            ]),
          ]),
          tabela(
            ["Módulo", { texto: "Aberturas", numero: true }, "Último uso", "Proporção"],
            usoOrdenado,
            ([codigo, m]) => [pilulaModulo(codigo), numero(m.aberturas),
                              m.ultimo ? quando(m.ultimo) : "nunca abriu", barra(m.aberturas, tetoUso, cor(codigo))]
          ),
        ]
      : vazio("Sem uso registrado", "Ou o cliente não abriu nada, ou o Hub ainda não enviou.")
  ));

  // -------------------------------------------------------- teste grátis ----
  if (cliente.licenca_id && testesDoCliente) {
    const testados = new Set(testesDoCliente.map((t) => t.produto_id));
    const paraTestar = naoTem.filter((p) => !testados.has(p.id));
    const escolhaTeste = el("select", { "aria-label": "Módulo para testar" }, [
      el("option", { value: "", texto: "Dar 7 dias de teste…" }),
      ...paraTestar.map((p) => el("option", { value: p.id, texto: modulo(p.codigo).nome })),
    ]);
    destino.append(cartao("Teste grátis", [
      testesDoCliente.length
        ? tabela(
            ["Módulo", "Situação", { texto: "Uso no teste", numero: true }, ""],
            testesDoCliente,
            (t) => [pilulaModulo(t.codigo), periodo(t, agora), usoNoTeste(t),
                    el("div", { classe: "ferramentas" }, acoesDoTeste(t, cliente, agora, { depois: refazer }))]
          )
        : el("p", { classe: "zona-texto", texto: "Nenhum teste grátis ainda. O cliente começa pelo Hub, " +
                                                 "ou você libera aqui." }),
      paraTestar.length
        ? el("div", { classe: "ferramentas", estilo: "margin-top:14px" }, [
            escolhaTeste,
            el("button", {
              classe: "botao botao-fantasma botao-mini", texto: "Dar teste",
              onclick: (e) => {
                const produto = paraTestar.find((p) => p.id === escolhaTeste.value);
                if (!produto) return recado("Escolha o módulo do teste.", "erro");
                darTeste(e.target, { licencaId: cliente.licenca_id, produto, depois: refazer });
              },
            }),
          ])
        : null,
    ]));
  }

  // ------------------------------------------------------------- celular ----
  if (cliente.licenca_id) {
    const ligados = aparelhos.filter((a) => !a.revogado_em);
    const resumo = espelhos ? resumoMaisNovo(espelhos).get(cliente.licenca_id) : null;
    const apelidos = new Map(maquinas.map((m) => [`${m.licenca_id}|${m.maquina}`, m.apelido]));
    destino.append(cartao("Celular", ligados.length
      ? [
          espelhos
            ? el("p", { classe: "zona-texto", texto: resumo
                ? `Resumo dos dados atualizado ${relativo(resumo, agora)}.`
                : "Nenhum resumo publicado ainda: o celular abre vazio até o Hub publicar." })
            : null,
          tabela(
            ["Aparelho", "Abriu", "Situação", ""],
            ligados,
            (a) => {
              const estado = ESTADOS_DO_CELULAR[estadoDoCelular(a, agora)];
              return [aparelho(a, apelidos), relativo(a.ultimo_acesso, agora), pilula(estado.texto, estado.tom),
                      botaoDesconectar(a, cliente, { depois: refazer })];
            }
          ),
        ]
      : [
          el("p", { classe: "zona-texto", texto: "Nenhum celular conectado. O cliente conecta pelo Hub: " +
                                                 "menu da empresa > Ver no celular." }),
          botaoWhatsApp(cliente.telefone, mensagemDeAcompanhamento("celular", { nome: cliente.nome }),
                        "Contar pelo WhatsApp"),
        ]));
  }

  // ----------------------------------------------------- o que oferecer ----
  if (recomendacoes.length) {
    destino.append(cartao("O que faz sentido oferecer", tabela(
      ["Módulo", { texto: "Preço", numero: true }, "Por quê"],
      recomendacoes,
      (r) => [
        pilulaModulo(r.recomendado),
        dinheiro(r.preco),
        el("div", {}, [
          el("div", { texto: r.porque }),
          el("div", { estilo: "font-size:.8rem;color:var(--tinta-fraca)",
                      texto: `usa ${modulo(r.porque_tem).nome}: ${numero(r.aberturas_origem)} aberturas em 30 dias` }),
        ]),
      ]
    )));
  }

  // -------------------------------------------------------- computadores --
  if (maquinas.length) {
    destino.append(cartao("Computadores", tabela(
      ["Apelido", "Identificador", "Versão", "Ativado", "Hub", ""],
      maquinas,
      (m) => [
        m.apelido || "—",
        el("code", { texto: m.maquina }),
        m.versao
          ? el("span", { classe: "hub-versao", "data-velha": versaoEmDia(m.versao, publicada) === false ? "sim" : null,
                         texto: m.versao, title: publicada ? `Publicada: ${publicada}` : "" })
          : "—",
        data(m.ativado_em),
        hubAberto(m, agora)
          ? el("span", { classe: "hub-pc" }, [el("span", { classe: "hub-ponto", "data-aberto": "sim" }), "aberto agora"])
          : vistoEm(m) ? `visto ${relativo(vistoEm(m), agora)}` : "nunca falou com o servidor",
        el("button", {
          classe: "botao botao-fantasma botao-mini", texto: "Liberar vaga",
          onclick: (e) => {
            if (!confirmar("Liberar esta vaga? O cliente precisará ativar de novo neste computador.")) return;
            agir(e.target, async () => {
              await apagar("ativacoes", { id: `eq.${m.id}` });
              await refazer();
            }, { feito: "Vaga liberada." });
          },
        }),
      ]
    )));
  }

  // ------------------------------------------------------------- pedidos --
  if (pedidosDoCliente.length) {
    destino.append(cartao("Compras e pedidos", tabela(
      ["Quando", "Canal", "Kit", { texto: "Total", numero: true }, "Situação"],
      pedidosDoCliente,
      (p) => [
        data(p.criado_em),
        el("div", {}, [CANAIS[p.origem] || p.origem,
                       p.referencia ? el("div", { classe: "sub-linha", texto: `nº ${p.referencia}` }) : null]),
        kitDoPedido(p),
        dinheiro(p.total),
        p.atendido_em ? pilula("Atendido", "ok") : pilula("Em aberto", "aviso"),
      ],
      { aoClicar: (p) => abrirPedido(p.id, { voltar: () => ficha(cliente) }) }
    )));
  }

  // ------------------------------------------------------ excluir cliente --
  const zona = cartao("Excluir cliente", [
    el("p", { classe: "zona-texto",
              texto: cliente.licenca_id
                ? "Apaga o cadastro e, junto, a licença e tudo dela. Os pedidos continuam no histórico."
                : "Apaga o cadastro. Os pedidos continuam no histórico." }),
    el("button", {
      classe: "botao botao-perigo", texto: "Excluir cliente…",
      onclick: () => excluirCliente(cliente, { modulos: tem, maquinas }),
    }),
  ]);
  zona.classList.add("zona-perigo");
  destino.append(zona);

  if (silencioso) substituirNaGaveta(antiga, destino, cliente.nome || cliente.email);
}

// ================================================================ excluir ====
// Exclusao que leva coisa junto nao passa com um clique: a gaveta mostra o que
// some, o que fica e o caminho mais leve, e o botao so acende depois de
// digitar EXCLUIR. O banco grava cada exclusao na auditoria (tela Seguranca).
function confirmarExclusao({ acima, titulo, some = [], fica = [], alternativa = null,
                             botao = "Excluir para sempre", acao, voltar = null }) {
  const lista = (itens) => el("ul", { classe: "exclusao-lista" }, itens.map((t) => el("li", { texto: t })));
  const entrada = el("input", {
    id: "confirmar-exclusao", type: "text", autocomplete: "off", spellcheck: "false",
    autocapitalize: "characters", placeholder: PALAVRA,
  });
  const excluir = el("button", { classe: "botao botao-perigo-cheio", texto: botao, disabled: true });
  entrada.addEventListener("input", () => { excluir.disabled = !confere(entrada.value); });
  entrada.addEventListener("keydown", (e) => { if (e.key === "Enter" && !excluir.disabled) excluir.click(); });
  excluir.addEventListener("click", (e) => {
    if (!confere(entrada.value)) return;
    agir(e.currentTarget, acao, { feito: "", erro: "Não consegui excluir." });
  });

  abrirGaveta({
    acima, titulo,
    conteudo: el("div", { classe: "exclusao" }, [
      cartao("Vai sumir", lista(some)),
      fica.length ? cartao("Continua", lista(fica)) : null,
      alternativa
        ? el("div", { classe: "exclusao-alternativa" }, [
            el("span", { texto: alternativa.texto }),
            el("button", { classe: "botao botao-fantasma botao-mini", texto: alternativa.rotulo,
                           onclick: (e) => agir(e.currentTarget, alternativa.acao, { feito: "" }) }),
          ])
        : null,
      cartao("", [
        campo(`Para confirmar, digite ${PALAVRA}`, entrada, "Não dá para desfazer. A exclusão fica registrada em Segurança."),
        el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
          excluir,
          voltar ? el("button", { classe: "botao botao-fantasma", texto: "Voltar", onclick: voltar }) : null,
        ]),
      ]),
    ]),
  });
  entrada.focus();
}

/** A ficha de novo, fresca do banco (o cliente pode ter perdido a licenca). */
async function reabrirFicha(clienteId) {
  recarregar();
  const novo = await um("painel_clientes", { filtros: { cliente_id: `eq.${clienteId}` }, fresco: true });
  if (novo) ficha(novo);
  else fecharGaveta();
}

/** O que a licenca leva junto, em frases (para cliente e para licenca). */
function oQueALicencaLeva(cliente, { modulos = [], maquinas = [] }) {
  const itens = [`A licença ${cliente.chave}: o Hub do cliente para de abrir os módulos em até 2 minutos.`];
  if (modulos.length) {
    itens.push(`${contagem(modulos.length, "módulo liberado", "módulos liberados")}: ` +
               `${modulos.map((codigo) => modulo(codigo).nome).join(", ")}.`);
  }
  itens.push(maquinas.length
    ? `${contagem(maquinas.length, "computador ativado", "computadores ativados")}, os celulares conectados e o uso registrado.`
    : "Os celulares conectados e o uso registrado.");
  return itens;
}

function excluirCliente(cliente, contexto) {
  const nome = cliente.nome || cliente.email || "Cliente";
  const some = [`O cadastro de ${nome}: nome, e-mail, telefone e documento.`];
  if (cliente.licenca_id) some.push(...oQueALicencaLeva(cliente, contexto));
  confirmarExclusao({
    acima: "Excluir cliente", titulo: nome, some,
    fica: [
      "Os pedidos e as vendas dele continuam em Pedidos, sem ligação com o cadastro " +
        "(os que estão em aberto não poderão mais ser aprovados).",
    ],
    alternativa: cliente.licenca_id && cliente.status !== "cancelada"
      ? {
          texto: "Só quer que pare de funcionar? Cancele a licença: o cadastro e o histórico ficam.",
          rotulo: "Cancelar a licença",
          acao: async () => {
            await atualizar("licencas", { id: `eq.${cliente.licenca_id}` }, { status: "cancelada" });
            recado(`Licença cancelada. ${AVISO_HUB}`, "ok");
            await reabrirFicha(cliente.cliente_id);
          },
        }
      : null,
    acao: async () => {
      await apagar("clientes", { id: `eq.${cliente.cliente_id}` }, { conferir: true });
      fecharGaveta();
      await recarregar();
      recado(`${nome} foi excluído.`, "ok");
    },
    voltar: () => ficha(cliente),
  });
}

function excluirLicenca(cliente, contexto) {
  confirmarExclusao({
    acima: "Excluir licença", titulo: cliente.chave,
    some: oQueALicencaLeva(cliente, contexto),
    fica: [
      `O cadastro de ${cliente.nome || cliente.email}: ele volta a ser um interessado, sem licença.`,
      "Os pedidos e as vendas dele continuam em Pedidos.",
    ],
    alternativa: cliente.status !== "cancelada"
      ? {
          texto: "Prefere guardar o histórico? Cancele em vez de excluir: os módulos param do mesmo jeito.",
          rotulo: "Cancelar a licença",
          acao: async () => {
            await atualizar("licencas", { id: `eq.${cliente.licenca_id}` }, { status: "cancelada" });
            recado(`Licença cancelada. ${AVISO_HUB}`, "ok");
            await reabrirFicha(cliente.cliente_id);
          },
        }
      : null,
    acao: async () => {
      await apagar("licencas", { id: `eq.${cliente.licenca_id}` }, { conferir: true });
      recado(`Licença ${cliente.chave} excluída. ${AVISO_HUB}`, "ok");
      await reabrirFicha(cliente.cliente_id);
    },
    voltar: () => ficha(cliente),
  });
}

// ======================================================== enviar a chave ====
// O que a tela ja sabe do cliente - usado se o banco nao devolver os dados.
const reservaDoCliente = (cliente) => ({
  nome: cliente.nome, email: cliente.email, telefone: cliente.telefone, chave: cliente.chave,
  tipo: cliente.tipo, expira_em: cliente.expira_em, max_computadores: cliente.max_computadores,
  modulos: (cliente.produtos_codigos || []).map((codigo) => modulo(codigo).nome),
});

const CANAIS = { hub: "Pelo Hub", site: "Pela loja", mercadolivre: "Mercado Livre", manual: "Venda direta" };

async function copiar(texto, caixa) {
  try {
    await navigator.clipboard.writeText(texto);
    recado("Mensagem copiada.", "ok");
  } catch {
    caixa?.select();
    recado("Mensagem selecionada: Ctrl+C para copiar.");
  }
}

/**
 * A gaveta "Enviar a chave". Dois jeitos de mandar:
 *   - WhatsApp ou e-mail: com o link de download (e o e-mail automatico, se publicado)
 *   - Mercado Livre: sem link, e-mail nem telefone (o ML bloqueia); o link vai
 *     no guia PDF, que voce ANEXA na mensagem da venda
 */
export async function enviarChave(licencaId, { reserva = {}, tentarEmail = false, canal = "direto" } = {}) {
  const destino = abrirGaveta({ acima: "Enviar a chave", titulo: reserva.nome || "Cliente" });

  let doBanco = null;
  try {
    doBanco = await rpc("dumtech_dados_da_chave", { p_licenca_id: licencaId }, { grava: false });
  } catch (erro) {
    if (erro.status !== 404) console.warn("dados da chave", erro);
  }
  const dados = { ...reserva, ...(doBanco || {}) };

  const onde = el("select", { id: "enviar-onde" }, [
    el("option", { value: "direto", texto: "WhatsApp ou e-mail" }),
    el("option", { value: "mercadolivre", texto: "Mensagem da venda no Mercado Livre" }),
  ]);
  onde.value = canal === "mercadolivre" ? "mercadolivre" : "direto";

  const previa = el("textarea", { readonly: true, rows: "13", "aria-label": "Mensagem para o cliente" });
  const telefone = el("input", { type: "tel", value: dados.telefone || "", placeholder: "(00) 00000-0000" });
  const situacaoEmail = el("p", { classe: "aviso", "data-tom": "neutro", role: "status" });
  let texto = "";

  const mandarEmail = async (botao) => {
    if (!dados.email) {
      situacaoEmail.dataset.tom = "neutro";
      situacaoEmail.textContent = "Este cliente não tem e-mail cadastrado.";
      return;
    }
    if (botao) botao.disabled = true;
    situacaoEmail.dataset.tom = "neutro";
    situacaoEmail.textContent = "Enviando o e-mail…";
    const { status, dados: resposta } = await funcao("enviar-chave", { licenca_id: licencaId });
    if (botao) botao.disabled = false;
    if (status === 200 && resposta.ok) {
      situacaoEmail.dataset.tom = "ok";
      situacaoEmail.textContent = `E-mail enviado para ${resposta.para || dados.email}.`;
      return;
    }
    situacaoEmail.dataset.tom = status === 0 || status === 404 || status === 501 ? "neutro" : "erro";
    situacaoEmail.textContent =
      status === 0 || status === 404 ? "E-mail automático ainda não publicado. Use WhatsApp ou e-mail acima."
      : status === 501 ? "E-mail automático sem configuração (falta a chave do Resend). Use WhatsApp ou e-mail acima."
      : `O e-mail automático falhou: ${resposta.mensagem || `erro ${status}`}. Use WhatsApp ou e-mail acima.`;
  };

  const areaDireta = el("div", {}, [
    el("label", { classe: "campo" }, [el("span", { texto: "WhatsApp do cliente" }), telefone]),
    el("div", { classe: "acoes-linha", estilo: "margin-top:12px" }, [
      el("button", {
        classe: "botao botao-primario", texto: "Abrir no WhatsApp",
        onclick: () => {
          const url = linkWhatsApp(telefone.value, texto);
          if (!url) return recado("Confira o número do WhatsApp (com DDD).", "erro");
          window.open(url, "_blank", "noopener");
        },
      }),
      el("button", {
        classe: "botao botao-fantasma", texto: "Abrir e-mail",
        onclick: () => {
          const url = linkEmail(dados.email, ASSUNTO_DA_CHAVE, texto);
          if (!url) return recado("Este cliente não tem e-mail válido.", "erro");
          window.location.href = url;
        },
      }),
      el("button", { classe: "botao botao-fantasma", texto: "Copiar mensagem", onclick: () => copiar(texto, previa) }),
    ]),
    el("div", { classe: "acoes-linha", estilo: "margin-top:14px;padding-top:12px;border-top:1px dashed var(--fio)" }, [
      el("button", {
        classe: "botao botao-fantasma botao-mini", texto: "Enviar e-mail automático",
        onclick: (e) => mandarEmail(e.target),
      }),
    ]),
    situacaoEmail,
  ]);

  const areaMercadoLivre = el("div", {}, [
    el("ol", { classe: "passos-ml" }, [
      el("li", { texto: "Copie a mensagem e cole em “Mensagens” da venda, no Mercado Livre." }),
      el("li", {}, [
        "Anexe o guia de instalação em PDF na mesma mensagem (ele tem o link de download). ",
        el("a", { href: CONFIG.GUIA_PDF_URL, target: "_blank", rel: "noopener", texto: "Abrir o guia PDF" }),
      ]),
      el("li", { texto: "Envie. O cliente instala, cola a chave e o cadastro dele se liga sozinho à venda." }),
    ]),
    el("div", { classe: "acoes-linha", estilo: "margin-top:12px" }, [
      el("button", {
        classe: "botao botao-primario", texto: "Copiar mensagem para o Mercado Livre",
        onclick: () => {
          const proibido = contatosNoTexto(texto);
          if (proibido.length) {
            return recado(`A mensagem tem ${proibido.join(", ")} — o Mercado Livre bloquearia. Tire antes de colar.`, "erro");
          }
          copiar(texto, previa);
        },
      }),
    ]),
    el("p", { classe: "nota-alerta", estilo: "margin-top:10px",
              texto: "Não escreva link, e-mail nem telefone na mensagem do Mercado Livre: a mensagem é bloqueada e a conta pode sofrer sanção." }),
  ]);

  const desenhar = () => {
    const ml = onde.value === "mercadolivre";
    texto = mensagemDaChave(dados, {
      canal: ml ? "mercadolivre" : "direto", download: CONFIG.DOWNLOAD_URL, suporte: CONFIG.SUPORTE,
    });
    previa.value = texto;
    areaDireta.hidden = ml;
    areaMercadoLivre.hidden = !ml;
  };
  onde.addEventListener("change", desenhar);
  desenhar();

  limpar(destino).append(
    cartao("Onde vai mandar", [el("label", { classe: "campo" }, [onde])]),
    cartao("A mensagem", [el("label", { classe: "campo" }, [previa])]),
    cartao("Enviar", [areaDireta, areaMercadoLivre])
  );

  if (tentarEmail && onde.value === "direto") mandarEmail(null);
}

const dado = (rotulo, valor) =>
  el("div", { classe: "item" }, [
    el("div", { classe: "rotulo", texto: rotulo }),
    el("div", { classe: "valor" }, [valor]),
  ]);

const kitDoPedido = (pedido) =>
  (pedido.itens || []).map((i) => i.nome || i.codigo).join(" + ") || "—";

const campo = (rotulo, entrada, dica = "") =>
  el("label", { classe: "campo" }, [
    el("span", { texto: rotulo }), entrada,
    dica ? el("small", { classe: "dica", texto: dica }) : null,
  ]);

/** Erro do banco em portugues de gente. */
function traduzirErro(erro) {
  const texto = String(erro?.message || "");
  if (texto.includes("idx_clientes_email")) return new Error("Esse e-mail já é de outro cliente.");
  if (texto.includes("idx_clientes_documento")) return new Error("Esse CPF/CNPJ já é de outro cliente.");
  if (texto.includes("licencas_prazo_check")) return new Error("Vitalícia não tem vencimento; assinatura e teste precisam de data.");
  if (/permission denied for function|Could not find the function/i.test(texto)) {
    return new Error("O banco ainda não tem a atualização das vendas: cole a migration 20260913090000_vendas_e_identidade.sql no SQL Editor do Supabase.");
  }
  return erro;
}

// ============================================= nova venda (ML / direta) ====
// Venda que nao passou pela loja: Mercado Livre, WhatsApp, telefone, balcao.
// Cadastra quem precisar, entrega na licenca que o cliente ja tem (ou cria),
// registra o valor recebido e abre "Enviar a chave".
export async function novaVenda({ cliente = null } = {}) {
  const destino = abrirGaveta({
    acima: cliente ? "Registrar venda" : "Nova venda",
    titulo: cliente ? (cliente.nome || cliente.email) : "Mercado Livre ou venda direta",
  });
  const [produtos, combos, itensDeCombo] = await Promise.all([
    ler("produtos", { ordem: "codigo.asc" }),
    ler("combos", { ordem: "codigo.asc" }),
    ler("combo_produtos"),
  ]);
  const aVenda = produtos.filter((p) => p.ativo);
  const combosAVenda = combos.filter((c) => c.ativo);
  const tem = new Set(cliente?.produtos_codigos || []);

  const canal = el("select", { id: "venda-canal" }, [
    el("option", { value: "mercadolivre", texto: "Mercado Livre" }),
    el("option", { value: "manual", texto: "Venda direta (WhatsApp, telefone, balcão)" }),
  ]);
  const referencia = el("input", { id: "venda-referencia", type: "text", placeholder: "Ex.: 2000012345678" });
  const nome = el("input", { id: "venda-nome", type: "text", placeholder: "Nome que aparece na venda" });
  const email = el("input", { id: "venda-email", type: "email", placeholder: "opcional" });
  const whatsapp = el("input", { id: "venda-whatsapp", type: "tel", placeholder: "opcional" });
  const combo = el("select", { id: "venda-combo" }, [
    el("option", { value: "", texto: "Sem combo" }),
    ...combosAVenda.map((c) => el("option", { value: c.codigo, texto: `${c.nome} — ${dinheiro(c.preco)}` })),
  ]);
  const escolhidos = new Set();
  const valor = el("input", { id: "venda-valor", type: "number", min: "0", step: "0.01", placeholder: "0,00" });
  let valorDigitado = false;
  valor.addEventListener("input", () => { valorDigitado = true; });

  const precoDeTabela = () => {
    let total = 0;
    const dentroDoCombo = new Set();
    if (combo.value) {
      const c = combos.find((x) => x.codigo === combo.value);
      total += Number(c?.preco || 0);
      for (const item of itensDeCombo.filter((i) => i.combo_id === c?.id)) {
        dentroDoCombo.add(produtos.find((p) => p.id === item.produto_id)?.codigo);
      }
    }
    for (const codigo of escolhidos) {
      if (!dentroDoCombo.has(codigo)) total += Number(produtos.find((p) => p.codigo === codigo)?.preco || 0);
    }
    return total;
  };
  const tabelaTexto = el("small", { classe: "dica" });
  const sugerirValor = () => {
    const total = precoDeTabela();
    tabelaTexto.textContent = `Preço de tabela: ${dinheiro(total)}. No Mercado Livre, informe o que você recebeu.`;
    if (!valorDigitado) valor.value = total ? total.toFixed(2) : "";
  };
  combo.addEventListener("change", sugerirValor);

  const listaModulos = el("div", { classe: "modulos-lista" }, aVenda.map((p) => {
    const marca = el("input", {
      type: "checkbox", disabled: tem.has(p.codigo),
      onchange: (e) => { e.target.checked ? escolhidos.add(p.codigo) : escolhidos.delete(p.codigo); sugerirValor(); },
    });
    return el("label", { classe: "pilula", "data-tom": tem.has(p.codigo) ? "ok" : "neutro",
                         estilo: "gap:7px;cursor:pointer", title: tem.has(p.codigo) ? "O cliente já tem" : "" },
              [marca, `${modulo(p.codigo).nome} · ${dinheiro(p.preco)}`]);
  }));
  const tipo = el("select", { id: "venda-tipo" }, [
    el("option", { value: "vitalicia", texto: "Vitalícia" }),
    el("option", { value: "assinatura", texto: "Assinatura" }),
    el("option", { value: "teste", texto: "Teste" }),
  ]);
  if (cliente?.tipo) tipo.value = cliente.tipo === "teste" ? "vitalicia" : cliente.tipo;
  const validade = el("input", { id: "venda-validade", type: "date", value: cliente?.expira_em || "" });
  const computadores = el("input", { id: "venda-computadores", type: "number", min: "1", max: "50",
                                     value: String(cliente?.max_computadores || 1) });

  const campoReferencia = campo("Número do pedido no Mercado Livre", referencia, "Aparece no histórico do cliente.");
  const campoValidade = campo("Vence em", validade);
  const ajustar = () => {
    campoReferencia.hidden = canal.value !== "mercadolivre";
    campoValidade.hidden = tipo.value === "vitalicia";
  };
  canal.addEventListener("change", ajustar);
  tipo.addEventListener("change", ajustar);
  ajustar();
  sugerirValor();

  const quem = cliente
    ? [dado("Cliente", pessoa(cliente.nome, cliente.email || "sem e-mail"))]
    : [
        campo("Nome do comprador", nome),
        campo("E-mail", email, "O Mercado Livre não mostra: deixe em branco. Quando ele ativar o Hub, o e-mail se liga sozinho."),
        campo("WhatsApp", whatsapp),
      ];

  limpar(destino).append(cartao("", [
    campo("Onde vendeu", canal),
    campoReferencia,
    ...quem,
    campo("Combo", combo),
    el("div", { classe: "campo" }, [el("span", { texto: "Módulos avulsos" }), listaModulos]),
    el("div", { classe: "dados" }, [campo("Tipo de licença", tipo), campoValidade, campo("Computadores", computadores)]),
    campo("Valor recebido (R$)", valor),
    tabelaTexto,
    el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
      el("button", {
        classe: "botao botao-primario", texto: "Registrar venda e gerar a chave",
        onclick: (e) => {
          if (!cliente && !nome.value.trim()) return recado("Informe o nome do comprador.", "erro");
          if (!combo.value && !escolhidos.size) return recado("Escolha um combo ou pelo menos um módulo.", "erro");
          if (tipo.value !== "vitalicia" && !validade.value) return recado("Assinatura e teste precisam de data de vencimento.", "erro");
          const recebido = valor.value === "" ? null : Number(valor.value);
          if (recebido !== null && (!Number.isFinite(recebido) || recebido < 0)) return recado("Confira o valor recebido.", "erro");

          agir(e.target, async () => {
            let resposta;
            try {
              resposta = await rpc("dumtech_venda_manual", {
                p_nome: cliente ? (cliente.nome || "") : nome.value.trim(),
                p_email: cliente ? "" : email.value.trim(),
                p_telefone: cliente ? "" : whatsapp.value.trim(),
                p_produtos: [...escolhidos],
                p_combo: combo.value || null,
                p_canal: canal.value,
                p_referencia: canal.value === "mercadolivre" ? referencia.value.trim() : "",
                p_total: recebido,
                p_tipo: tipo.value,
                p_expira_em: tipo.value === "vitalicia" ? null : validade.value,
                p_max_computadores: Number(computadores.value) || 1,
                p_cliente_id: cliente?.cliente_id || null,
              });
            } catch (erro) {
              throw traduzirErro(erro);
            }
            recado(
              resposta.licenca_nova ? `Venda registrada. Chave nova: ${resposta.chave}`
              : resposta.reativada ? `Venda registrada. A licença ${resposta.chave} voltou a valer.`
              : `Venda registrada na chave que o cliente já tem: ${resposta.chave}`, "ok");
            recarregar();
            const nomesVendidos = [
              ...(combo.value ? [combos.find((c) => c.codigo === combo.value)?.nome] : []),
              ...[...escolhidos].map((c) => modulo(c).nome),
            ].filter(Boolean);
            enviarChave(resposta.licenca_id, {
              reserva: { nome: resposta.nome, email: resposta.email, telefone: resposta.telefone,
                         chave: resposta.chave, modulos: nomesVendidos },
              canal: canal.value === "mercadolivre" ? "mercadolivre" : "direto",
              tentarEmail: canal.value !== "mercadolivre" && Boolean(resposta.email),
            });
          }, { feito: "", erro: "Não consegui registrar a venda." });
        },
      }),
      el("button", { classe: "botao botao-fantasma", texto: "Cancelar", onclick: fecharGaveta }),
    ]),
  ]));
}

// ============================================== editar cliente e licenca ====
/** Cadastro sem venda: o interessado que ligou, o contato do Mercado Livre. */
function novoCliente() {
  const nome = el("input", { id: "novo-cliente-nome", type: "text" });
  const email = el("input", { id: "novo-cliente-email", type: "email" });
  const telefoneCampo = el("input", { id: "novo-cliente-telefone", type: "tel" });
  const documento = el("input", { id: "novo-cliente-documento", type: "text" });

  abrirGaveta({
    acima: "Novo cliente", titulo: "Cadastrar cliente",
    conteudo: cartao("", [
      campo("Nome", nome), campo("E-mail", email, "Pode ficar vazio: liga sozinho quando ele ativar o Hub."),
      campo("WhatsApp / telefone", telefoneCampo), campo("CPF ou CNPJ", documento),
      el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
        el("button", {
          classe: "botao botao-primario", texto: "Cadastrar",
          onclick: (e) => {
            if (!nome.value.trim()) return recado("O cliente precisa de um nome.", "erro");
            const emailLimpo = email.value.trim().toLowerCase();
            if (emailLimpo && !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(emailLimpo)) return recado("Confira o e-mail.", "erro");
            agir(e.target, async () => {
              let criado;
              try {
                criado = await inserir("clientes", {
                  nome: nome.value.trim(), email: emailLimpo, origem: "venda",
                  telefone: telefoneCampo.value.trim(), documento: documento.value.replace(/\D/g, ""),
                });
              } catch (erro) {
                throw traduzirErro(erro);
              }
              const id = (Array.isArray(criado) ? criado[0] : criado)?.id;
              if (id) await reabrirFicha(id);
              else { fecharGaveta(); await recarregar(); }
            }, { feito: "Cliente cadastrado." });
          },
        }),
        el("button", { classe: "botao botao-fantasma", texto: "Cancelar", onclick: fecharGaveta }),
      ]),
    ]),
  });
  nome.focus();
}

function editarCliente(cliente) {
  const nome = el("input", { id: "cliente-nome", type: "text", value: cliente.nome || "" });
  const email = el("input", { id: "cliente-email", type: "email", value: cliente.email || "" });
  const telefoneCampo = el("input", { id: "cliente-telefone", type: "tel", value: cliente.telefone || "" });
  const documento = el("input", { id: "cliente-documento", type: "text", value: cliente.documento || "" });

  abrirGaveta({
    acima: "Editar cliente", titulo: cliente.nome || cliente.email,
    conteudo: cartao("", [
      campo("Nome", nome), campo("E-mail", email), campo("WhatsApp / telefone", telefoneCampo),
      campo("CPF ou CNPJ", documento),
      el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
        el("button", {
          classe: "botao botao-primario", texto: "Salvar",
          onclick: (e) => {
            if (!nome.value.trim()) return recado("O cliente precisa de um nome.", "erro");
            const emailLimpo = email.value.trim().toLowerCase();
            if (emailLimpo && !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(emailLimpo)) return recado("Confira o e-mail.", "erro");
            agir(e.target, async () => {
              try {
                await atualizar("clientes", { id: `eq.${cliente.cliente_id}` }, {
                  nome: nome.value.trim(), email: emailLimpo,
                  telefone: telefoneCampo.value.trim(), documento: documento.value.replace(/\D/g, ""),
                });
              } catch (erro) {
                throw traduzirErro(erro);
              }
              recarregar();
              const novo = await um("painel_clientes", { filtros: { cliente_id: `eq.${cliente.cliente_id}` }, fresco: true });
              if (novo) ficha(novo);
            }, { feito: "Cliente atualizado." });
          },
        }),
        el("button", { classe: "botao botao-fantasma", texto: "Voltar", onclick: () => ficha(cliente) }),
      ]),
    ]),
  });
}

function editarLicenca(cliente) {
  const tipo = el("select", { id: "licenca-tipo" }, [
    el("option", { value: "vitalicia", texto: "Vitalícia" }),
    el("option", { value: "assinatura", texto: "Assinatura" }),
    el("option", { value: "teste", texto: "Teste" }),
  ]);
  tipo.value = cliente.tipo || "vitalicia";
  const validade = el("input", { id: "licenca-validade", type: "date", value: cliente.expira_em || "" });
  const computadores = el("input", { id: "licenca-computadores", type: "number", min: "1", max: "50",
                                     value: String(cliente.max_computadores || 1) });
  const campoValidade = campo("Vence em", validade, "Renovar é mudar esta data. O Hub do cliente recebe em até 2 minutos.");
  const ajustar = () => { campoValidade.hidden = tipo.value === "vitalicia"; };
  tipo.addEventListener("change", ajustar);
  ajustar();

  abrirGaveta({
    acima: "Editar licença", titulo: cliente.chave,
    conteudo: cartao("", [
      campo("Tipo", tipo), campoValidade,
      campo("Computadores", computadores, `Hoje ativada em ${cliente.computadores}. Diminuir não desliga ninguém: só impede ativar outro.`),
      el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
        el("button", {
          classe: "botao botao-primario", texto: "Salvar",
          onclick: (e) => {
            if (tipo.value !== "vitalicia" && !validade.value) return recado("Assinatura e teste precisam de data de vencimento.", "erro");
            agir(e.target, async () => {
              try {
                await atualizar("licencas", { id: `eq.${cliente.licenca_id}` }, {
                  tipo: tipo.value,
                  expira_em: tipo.value === "vitalicia" ? null : validade.value,
                  max_computadores: Math.max(1, Number(computadores.value) || 1),
                });
              } catch (erro) {
                throw traduzirErro(erro);
              }
              recarregar();
              const novo = await um("painel_clientes", { filtros: { cliente_id: `eq.${cliente.cliente_id}` }, fresco: true });
              if (novo) ficha(novo);
            }, { feito: `Licença atualizada. ${AVISO_HUB}` });
          },
        }),
        el("button", { classe: "botao botao-fantasma", texto: "Voltar", onclick: () => ficha(cliente) }),
      ]),
    ]),
  });
}

// ================================================================ pedidos ====
const SITUACAO_QUE_VOLTA = { suspensa: "suspensa", cancelada: "cancelada", expirada: "vencida" };
const METODOS_PAGAMENTO = { pix: "Pix", credit_card: "cartão" };

/** Checkout da loja: desistiu no pagamento, ou pagou e a entrega automatica falhou. */
function situacaoDoPagamento(p) {
  if (p.pagamento === "aguardando") {
    return el("div", {}, [
      pilula("não pagou", "aviso"),
      el("div", { classe: "sub-linha", texto: "abriu o pagamento e não concluiu — vale chamar" }),
    ]);
  }
  if (p.pagamento === "pago") {
    return el("div", {}, [
      pilula(`pago · ${METODOS_PAGAMENTO[p.pagamento_metodo] || "InfinitePay"}`, "ok"),
      p.entrega_erro
        ? el("div", { classe: "nota-alerta", texto: `a entrega automática falhou (${p.entrega_erro}) — aprove para liberar` })
        : null,
    ]);
  }
  return null;
}

// A busca e o "carregar mais" das vendas feitas sobrevivem ao redesenho (tempo real).
const filtroVendas = { busca: "", limite: 50 };

export async function pedidos(alvo) {
  const abertos = await ler("pedidos_abertos");
  marcarPedidos(abertos.length);

  alvo.append(el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Pedidos" }),
      el("p", { texto: "Aprovar entrega os módulos na licença que o cliente já tem (ou cria uma) e abre o envio da chave. " +
                       "Clique num pedido para ver, editar ou excluir." }),
    ]),
    el("div", { classe: "ferramentas" }, [
      el("button", { classe: "botao botao-primario", texto: "Nova venda", onclick: () => novaVenda() }),
    ]),
  ]));

  alvo.append(cartao(`${contagem(abertos.length, "pedido")} em aberto`, tabela(
    ["Quem", "Kit", { texto: "Total", numero: true }, "Chegou", "Licença", ""],
    abertos,
    (p) => {
      const jaTem = (p.ja_tem || []).map((codigo) => modulo(codigo).nome);
      const volta = SITUACAO_QUE_VOLTA[p.licenca_situacao];
      const computadores = el("input", {
        type: "number", min: "1", max: "50", value: "1",
        estilo: "width:64px", title: "Em quantos computadores",
      });
      const tipo = el("select", { title: "Tipo da licença" }, [
        el("option", { value: "", texto: p.licenca_situacao ? "Manter tipo" : "Vitalícia" }),
        el("option", { value: "vitalicia", texto: "Vitalícia" }),
        el("option", { value: "assinatura", texto: "Assinatura até…" }),
      ]);
      const validade = el("input", { type: "date", hidden: true, title: "Vence em" });
      tipo.addEventListener("change", () => { validade.hidden = tipo.value !== "assinatura"; });

      return [
        pessoa(p.nome, p.email),
        el("div", {}, [
          p.kit || "—",
          jaTem.length ? el("div", { classe: "nota-alerta", texto: `já tem: ${jaTem.join(", ")} — confira se não cobrou de novo` }) : null,
        ]),
        el("div", {}, [
          dinheiro(p.total),
          situacaoDoPagamento(p),
        ]),
        quando(p.criado_em),
        !p.licenca_situacao
          ? pilula("primeira compra", "marca")
          : el("div", {}, [
              p.chave_atual ? el("code", { texto: p.chave_atual }) : pilulaSituacao(p.licenca_situacao),
              el("div", { classe: "nota-alerta",
                          texto: volta ? `licença ${volta}: volta a valer ao aprovar` : "já é cliente — confirme com ele" }),
            ]),
        // os campos de aprovar nao abrem o pedido: clicar neles e preencher
        el("div", { classe: "ferramentas", onclick: (e) => e.stopPropagation() }, [
          computadores, tipo, validade,
          el("button", {
            classe: "botao botao-primario botao-mini", texto: "Aprovar",
            onclick: (e) => {
              if (tipo.value === "assinatura" && !validade.value) return recado("Assinatura precisa de data de vencimento.", "erro");
              // Qualquer pessoa digita qualquer e-mail no site. Pedido com o
              // e-mail de quem ja e cliente entra NA LICENCA DELE: so aprove
              // depois de confirmar o pagamento com o proprio cliente.
              const avisos = [];
              if (p.pagamento === "aguardando") avisos.push("O cliente abriu o pagamento na loja e NÃO concluiu.");
              if (p.licenca_situacao) avisos.push(`${p.email} já é cliente: os módulos entram na licença dele${volta ? `, que está ${volta} e volta a valer` : ""}.`);
              if (jaTem.length) avisos.push(`Ele já tem ${jaTem.join(", ")}.`);
              // pago pela InfinitePay: o dinheiro ja entrou, nao ha o que confirmar
              if (p.pagamento !== "pago" && avisos.length && !confirmar(`${avisos.join("\n")}\n\nQualquer pessoa pode digitar um e-mail no site: aprove só se já confirmou o pagamento com o cliente.`)) return;
              agir(e.target, async () => {
                let dados;
                try {
                  // tipo so vai quando foi escolhido: mandar null por cima do
                  // padrao do banco apagaria o "vitalicia" de quem nao escolheu
                  const parametros = {
                    p_pedido_id: p.pedido_id,
                    p_max_computadores: Number(computadores.value) || 1,
                  };
                  if (tipo.value) parametros.p_tipo = tipo.value;
                  if (tipo.value === "assinatura") parametros.p_expira_em = validade.value;
                  dados = await rpc("dumtech_aprovar_pedido", parametros);
                } catch (erro) {
                  throw traduzirErro(erro);
                }
                recado(dados?.reativada ? `Aprovado. A licença ${dados.chave} voltou a valer.`
                       : `Aprovado. Chave: ${dados?.chave || "—"}`, "ok");
                await recarregar();
                if (dados?.licenca_id) {
                  enviarChave(dados.licenca_id, {
                    reserva: {
                      nome: p.nome, email: p.email, telefone: p.telefone, chave: dados.chave,
                      modulos: String(p.kit || "").split(" + ").filter(Boolean),
                    },
                    tentarEmail: true,
                  });
                }
                return dados;
              }, { feito: "", erro: "Não consegui aprovar." });
            },
          }),
        ]),
      ];
    },
    { vazioTexto: "Nenhum pedido esperando. ", aoClicar: (p) => abrirPedido(p.pedido_id) }
  )));

  // ------------------------------------------------------- vendas feitas --
  // todas, e nao so as ultimas 30: busca no banco e "carregar mais" de 50 em 50
  const busca = el("input", { type: "search", placeholder: "Nome, e-mail ou nº do pedido…", value: filtroVendas.busca });
  const corpoVendas = el("div", {});
  alvo.append(cartao("Vendas feitas", corpoVendas, el("div", { classe: "ferramentas" }, [busca])));

  const desenharVendas = async () => {
    const pedido = { ...filtroVendas };
    const linhas = await ler("pedidos_site", {
      filtros: { atendido_em: "not.is.null", or: filtroDeBusca(pedido.busca) },
      ordem: "atendido_em.desc", limite: pedido.limite + 1,
    });
    // a busca mudou enquanto esta leitura viajava: a mais nova desenha
    if (pedido.busca !== filtroVendas.busca || pedido.limite !== filtroVendas.limite) return;
    const temMais = linhas.length > pedido.limite;
    // el() e nao append direto: append(null) escreveria "null" na tela
    limpar(corpoVendas).append(el("div", {}, [
      tabela(
        ["Quando", "Quem", "Canal", "Kit", { texto: "Total", numero: true }],
        linhas.slice(0, pedido.limite),
        (p) => [
          data(p.atendido_em),
          pessoa(p.nome, p.email),
          el("div", {}, [CANAIS[p.origem] || p.origem, p.referencia ? el("div", { classe: "sub-linha", texto: `nº ${p.referencia}` }) : null]),
          kitDoPedido(p),
          el("div", {}, [
            dinheiro(p.total),
            p.pagamento === "pago"
              ? el("div", { classe: "sub-linha", texto: `InfinitePay · ${METODOS_PAGAMENTO[p.pagamento_metodo] || "pago"}` })
              : null,
          ]),
        ],
        { vazioTexto: pedido.busca ? "Nenhuma venda com essa busca." : "Nenhuma venda atendida ainda.",
          aoClicar: (p) => abrirPedido(p.id) }
      ),
      temMais
        ? el("button", {
            classe: "botao botao-fantasma botao-carregar", texto: "Carregar mais 50",
            onclick: () => { filtroVendas.limite += 50; desenharVendas(); },
          })
        : null,
    ]));
  };

  // o que foi digitado vale NA HORA (a tela redesenhada no meio da digitação
  // volta com ele); só a ida ao banco espera a pessoa parar de digitar
  let espera = 0;
  busca.addEventListener("input", () => {
    filtroVendas.busca = busca.value;
    filtroVendas.limite = 50;
    clearTimeout(espera);
    espera = setTimeout(() => {
      if (busca.isConnected) desenharVendas(); // tela trocada: a nova já buscou
    }, 300);
  });
  await desenharVendas();
}

// ================================================ ver, editar e excluir ====
/** O pedido inteiro numa ficha: o que veio, como pagou e o que fazer com ele. */
async function abrirPedido(pedidoId, { voltar = null } = {}) {
  const destino = abrirGaveta({ acima: "Pedido", titulo: "Pedido" });
  const p = await um("pedidos_site", { filtros: { id: `eq.${pedidoId}` }, fresco: true });
  limpar(destino);
  if (!p) {
    destino.append(vazio("Este pedido não existe mais", "Ele já foi excluído."));
    return;
  }
  const titulo = document.getElementById("gaveta-titulo");
  if (titulo) titulo.textContent = p.nome || p.email || "Pedido";
  const reabrir = () => abrirPedido(pedidoId, { voltar });

  destino.append(cartao("Pedido", [
    el("div", { classe: "dados" }, [
      dado("Quem", pessoa(p.nome, p.email)),
      dado("Telefone", telefone(p.telefone) || "—"),
      dado("Canal", el("div", {}, [CANAIS[p.origem] || p.origem || "—",
                                   p.referencia ? el("div", { classe: "sub-linha", texto: `nº ${p.referencia}` }) : null])),
      dado("Situação", p.atendido_em ? pilula(`Atendido em ${data(p.atendido_em)}`, "ok") : pilula("Em aberto", "aviso")),
      dado("Kit", kitDoPedido(p)),
      dado("Total", el("div", {}, [
        dinheiro(p.total),
        Number(p.desconto) > 0
          ? el("div", { classe: "sub-linha", texto: `de ${dinheiro(p.subtotal)}, com ${dinheiro(p.desconto)} de desconto` +
                                                  (p.cupom ? ` (cupom ${p.cupom})` : "") })
          : null,
      ])),
      dado("Pagamento", situacaoDoPagamento(p) || "—"),
      dado("Chegou", dataHora(p.criado_em)),
      p.observacoes ? dado("Observações", p.observacoes) : null,
    ]),
    el("div", { classe: "acoes-linha", estilo: "margin-top:16px" }, [
      el("button", { classe: "botao botao-fantasma botao-mini", texto: "Editar",
                     onclick: () => editarPedido(p, { voltar: reabrir }) }),
      p.cliente_id
        ? el("button", {
            classe: "botao botao-fantasma botao-mini", texto: "Abrir cliente",
            onclick: async () => {
              const cliente = await um("painel_clientes", { filtros: { cliente_id: `eq.${p.cliente_id}` }, fresco: true });
              if (cliente) ficha(cliente);
              else recado("O cliente deste pedido foi excluído.", "erro");
            },
          })
        : null,
      el("button", { classe: "botao botao-perigo botao-mini", texto: "Excluir pedido",
                     onclick: () => excluirPedido(p, { voltar: reabrir, depois: voltar }) }),
      voltar ? el("button", { classe: "botao botao-fantasma botao-mini", texto: "Voltar", onclick: voltar }) : null,
    ]),
  ]));
}

function editarPedido(p, { voltar }) {
  const nome = el("input", { id: "pedido-nome", type: "text", value: p.nome || "" });
  const email = el("input", { id: "pedido-email", type: "email", value: p.email || "" });
  const telefoneCampo = el("input", { id: "pedido-telefone", type: "tel", value: p.telefone || "" });
  const referencia = el("input", { id: "pedido-referencia", type: "text", value: p.referencia || "" });
  // o valor pago pela loja veio da InfinitePay: ali o total e o do pagamento
  const pagoNaLoja = p.pagamento === "pago";
  const total = el("input", { id: "pedido-total", type: "number", step: "0.01", min: "0",
                              value: String(p.total ?? 0), disabled: pagoNaLoja });
  const observacoes = el("textarea", { id: "pedido-observacoes", rows: "3" });
  observacoes.value = p.observacoes || "";

  abrirGaveta({
    acima: "Editar pedido", titulo: p.nome || p.email || "Pedido",
    conteudo: cartao("", [
      campo("Nome", nome),
      campo("E-mail", email, p.cliente_id
        ? "Corrige o registro do pedido. A conta do cliente se corrige na ficha dele."
        : ""),
      campo("WhatsApp / telefone", telefoneCampo),
      campo("Nº do pedido (Mercado Livre, nota…)", referencia),
      campo("Total (R$)", total, pagoNaLoja
        ? "Pago pela loja: o total é o que a InfinitePay recebeu e não muda aqui."
        : "Corrige o que entra em “Vendido” e no “Comprou” do cliente."),
      campo("Observações", observacoes),
      el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
        el("button", {
          classe: "botao botao-primario", texto: "Salvar",
          onclick: (e) => {
            if (!nome.value.trim() && !email.value.trim()) return recado("O pedido precisa de um nome ou e-mail.", "erro");
            const emailLimpo = email.value.trim().toLowerCase();
            if (emailLimpo && !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(emailLimpo)) return recado("Confira o e-mail.", "erro");
            const valor = Number(total.value);
            if (!pagoNaLoja && (!Number.isFinite(valor) || valor < 0)) return recado("Confira o total.", "erro");
            const dados = {
              nome: nome.value.trim(), email: emailLimpo, telefone: telefoneCampo.value.trim(),
              referencia: referencia.value.trim(), observacoes: observacoes.value.trim(),
            };
            if (!pagoNaLoja) dados.total = Math.round(valor * 100) / 100;
            agir(e.target, async () => {
              await atualizar("pedidos_site", { id: `eq.${p.id}` }, dados);
              await recarregar();
              await voltar();
            }, { feito: "Pedido atualizado." });
          },
        }),
        el("button", { classe: "botao botao-fantasma", texto: "Voltar", onclick: voltar }),
      ]),
    ]),
  });
}

/**
 * Pedido parado (nem pago, nem atendido) sai com um "ok". O que ja teve
 * dinheiro ou entrega pede EXCLUIR digitado - e diz que os modulos entregues
 * continuam na licenca (excluir o pedido nao desfaz a entrega).
 */
function excluirPedido(p, { voltar, depois = null }) {
  const quem = p.nome || p.email || "sem nome";
  const terminar = async () => {
    await apagar("pedidos_site", { id: `eq.${p.id}` }, { conferir: true });
    await recarregar();
    recado(`Pedido de ${quem} excluído.`, "ok");
    if (depois) await depois();
    else fecharGaveta();
  };

  if (!exclusaoPesada(p)) {
    if (!confirmar(`Excluir o pedido de ${quem} (${kitDoPedido(p)}, ${dinheiro(p.total)})?\n\n` +
                   "Ele não foi pago nem aprovado: nenhuma licença muda.")) return;
    agir(null, terminar, { feito: "", erro: "Não consegui excluir." });
    return;
  }

  const some = [`O registro deste pedido: ${kitDoPedido(p)}, ${dinheiro(p.total)}.`];
  if (p.pagamento === "pago") {
    some.push("O registro do pagamento pela InfinitePay neste painel (o dinheiro já entrou; o extrato continua lá).");
  }
  if (p.atendido_em) some.push(`Os ${dinheiro(p.total)} saem de “Vendido” e do “Comprou” do cliente.`);
  confirmarExclusao({
    acima: "Excluir pedido", titulo: `${quem} · ${dinheiro(p.total)}`, some,
    fica: p.atendido_em
      ? ["Os módulos que este pedido entregou continuam na licença do cliente. Para tirar, use a ficha dele."]
      : [],
    acao: terminar,
    voltar,
  });
}
