// A ficha do cliente e os pedidos antigos da loja.
//
// A ficha é o coração do painel: tudo o que a DumTech sabe daquela pessoa numa
// tela só, e as ações que resolvem o caso sem sair dali. Abre de Hoje, de
// Clientes, de Hub e de Segurança.
//
// Pedidos: o checkout antigo da loja (módulo avulso). A loja agora vende por
// mensalidade, mas um pedido antigo em aberto ainda precisa de alguém para
// aprovar: a tela fica fora do menu e Hoje avisa quando há um.

import { apagar, atualizar, ler, rpc, um } from "../api.js";
import { CONFIG } from "../config.js";
import { PALAVRA, confere, exclusaoPesada, filtroDeBusca } from "../exclusao.js";
import {
  ASSUNTO_DA_CHAVE, contatosNoTexto, linkEmail, linkWhatsApp, mensagemDaChave, mensagemDeAcompanhamento,
} from "../mensagens.js";
import {
  contagem, data, dataHora, dinheiro, documento as fmtDocumento, numero, quando, relativo, telefone,
} from "../formato.js";
import { CANAIS, comPresenca, linhaDoTempo, versaoAlvo } from "../gestao.js";
import { faixa } from "../graficos.js";
import { SITUACAO } from "../mensalidade.js";
import {
  abrirGaveta, fecharGaveta, folhaDaGaveta, irPara, recarregar, substituirNaGaveta,
} from "../painel.js";
import { cor, modulo } from "../modulos.js";
import {
  ESTADOS_DO_CELULAR, estadoDoCelular, estadoDoTeste, hubAberto, resumoMaisNovo,
  serieDiaria, versaoEmDia, vistoEm,
} from "../saude.js";
import {
  agir, barra, botaoWhatsApp, cartao, confirmar, el, limpar, pessoa, pilula, pilulaModulo,
  pilulaSituacao, recado, tabela, vazio,
} from "../ui.js";
import { temLogin, vagasASoltar } from "../acessos.js";
import { cartaoContas } from "./acessos.js";
import { aparelho, botaoDesconectar } from "./celulares.js";
import { cartaoAcompanhamento, cartaoAtualizacao, cartaoLinhaDoTempo } from "./ficha-gestao.js";
import { cartoesDaAssinatura, detalheDaSituacao, eventosDaAssinatura, primeiro } from "./mensalidades.js";
import { acoesDoTeste, darTeste, periodo, usoNoTeste } from "./testes.js";

const JANELA = 30;
// Desde o Hub 1.2.4 a consulta leve de 2 em 2 minutos traz uma impressao
// digital da licenca (migration 20260921120000): mudou, o Hub reconfere na hora.
// Hubs mais antigos ainda conferem de hora em hora - por isso os dois prazos.
const AVISO_HUB = "O Hub do cliente recebe em até 2 minutos, assim que estiver com internet " +
                  "(versões anteriores à 1.2.4: em até 1 hora).";
const diaLimite = (dias) =>
  new Date(Date.now() - dias * 86400000).toISOString().slice(0, 10);

// ================================================================== ficha ====
const ROTULO_DA_FICHA = { assinatura: "Assinante", teste: "Testando o plano mensal", vitalicia: "Cliente vitalício" };

/**
 * A ficha do cliente: uma só para assinante, teste, vitalício e quem ainda
 * não tem licença. O topo diz quem é e como está; o bloco do meio muda com o
 * tipo (assinatura, ou módulos do vitalício); o resto é igual para todos.
 */
export async function ficha(cliente, { silencioso = false } = {}) {
  // `silencioso`: a ficha ja esta aberta e so precisa refletir o que mudou -
  // monta a nova por tras e troca de uma vez, sem voltar ao "Carregando".
  const antiga = silencioso ? folhaDaGaveta() : null;
  if (silencioso && !antiga) return;
  const destino = silencioso
    ? document.createElement("div")
    : abrirGaveta({ acima: ROTULO_DA_FICHA[cliente.tipo] || "Cliente", titulo: cliente.nome || cliente.email });

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
  const mensalPossivel = cliente.licenca_id && (cliente.tipo === "assinatura" || cliente.tipo === "teste");
  const [produtos, combos, liberados, ativacoes, uso, recomendacoes, pedidosDoCliente,
         testesDoCliente, aparelhos, espelhos, modulosPagos, versoes, presencas, liberacoes,
         lancamentos, gestaoDoCliente, notas, mensal, assinatura] =
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
      daLicenca("hub_presenca", { fresco }),
      daLicenca("hub_liberacoes", { fresco }),
      ler("hub_lancamentos", { ordem: "criado_em.desc" }),
      um("painel_gestao", { filtros: { cliente_id: `eq.${cliente.cliente_id}` }, fresco }),
      ler("cliente_notas", { filtros: { cliente_id: `eq.${cliente.cliente_id}` }, ordem: "criado_em.desc", fresco }),
      // a mensalidade so existe para assinatura e teste: vitalicio nunca a ve
      mensalPossivel
        ? um("painel_mensalidades", { filtros: { licenca_id: `eq.${cliente.licenca_id}` }, fresco }).catch(() => null)
        : null,
      mensalPossivel ? eventosDaAssinatura(cliente.licenca_id) : [],
    ]);
  const agora = new Date();
  const publicada = String(versoes?.[0]?.versao || "");
  const maquinas = comPresenca(ativacoes, presencas);
  const vitalicia = Boolean(cliente.licenca_id) && !mensal;

  const porId = new Map(produtos.map((p) => [p.id, p]));
  const tem = liberados.map((l) => porId.get(l.produto_id)?.codigo).filter(Boolean);
  const naoTem = produtos.filter((p) => p.ativo && !tem.includes(p.codigo));

  limpar(destino);

  // ----------------------------------------------------------------- topo --
  destino.append(topoDaFicha({ cliente, mensal, maquinas, gestao: gestaoDoCliente, agora, vitalicia }));

  // ------------------------------------------------- o bloco do meio ------
  if (mensal) {
    destino.append(...await cartoesDaAssinatura(mensal, { depois: refazer }));
  } else if (cliente.licenca_id) {
    destino.append(cartaoModulos({ cliente, produtos, combos, tem, naoTem, testes: testesDoCliente, agora, depois: refazer }));
  } else {
    destino.append(cartao("Ainda sem licença", [
      el("p", { classe: "zona-texto", texto: "Esta pessoa está cadastrada, mas ainda não começou o teste grátis. " +
                                             "Mande o link do site: o teste de 7 dias começa lá, sem cartão." }),
      botaoWhatsApp(cliente.telefone, `Olá, ${primeiro(cliente.nome)}! Aqui é da DumTech. Para testar o DumTech Hub ` +
        `por 7 dias, grátis e sem cartão, é só entrar em ${CONFIG.LOJA_URL || "dumtechsolution.com"} e clicar em ` +
        "Testar grátis. Qualquer dúvida, estou por aqui.", "Mandar o link do teste"),
    ]));
  }

  destino.append(cartaoAcompanhamento({ cliente, gestao: gestaoDoCliente, notas, depois: refazer }));

  // ---------------------------------------------------------------- uso ----
  // os módulos pagos (com o último uso de sempre) e os abertos em teste
  if (cliente.licenca_id) {
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
  }

  // -------------------------------------------------------- computadores --
  if (maquinas.length) {
    destino.append(cartao(`Computadores: ${maquinas.length} de ${cliente.max_computadores} vagas`, tabela(
      ["Apelido", "Identificador", "Versão", "Ativado", "Hub", ""],
      maquinas,
      (m) => [
        m.apelido || "—",
        el("code", { texto: m.maquina }),
        m.versao
          ? el("span", { classe: "hub-versao", "data-velha": versaoEmDia(m.versao, publicada) === false ? "sim" : null,
                         texto: temLogin(m.versao) ? m.versao : `${m.versao} · sem login`,
                         title: publicada ? `Publicada: ${publicada}` : "" })
          : "—",
        data(m.ativado_em),
        hubAberto(m, agora)
          ? el("span", { classe: "hub-pc" }, [el("span", { classe: "hub-ponto", "data-aberto": "sim" }),
                                               m.online_desde ? `online, aberto ${relativo(m.online_desde, agora)}` : "aberto agora"])
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

  // ------------------------------------------------------------------ hub --
  const atualizacao = cartaoAtualizacao({
    cliente, maquinas, publicada, liberacao: liberacoes[0] || null, forcadaGeral: Boolean(versoes?.[0]?.forcada),
    alvo: versaoAlvo(lancamentos, publicada), depois: refazer,
  }, agora);
  if (atualizacao) destino.append(atualizacao);

  // --------------------------------------------------------------- contas --
  const contas = cliente.licenca_id ? await cartaoContas(cliente, { depois: refazer }) : null;
  if (contas) destino.append(contas);

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
  // O cruzamento de uso ("usa Vendas e não tem Orçamentos") vale para os dois:
  // para o vitalício é um módulo a mais, para o mensal um adicional no plano.
  if (recomendacoes.length) {
    destino.append(cartao(mensal ? "Adicional que faz sentido oferecer" : "O que faz sentido oferecer", tabela(
      vitalicia ? ["Módulo", { texto: "Preço", numero: true }, "Por quê"] : ["Módulo", "Por quê"],
      recomendacoes,
      (r) => [
        pilulaModulo(r.recomendado),
        ...(vitalicia ? [dinheiro(r.preco)] : []),
        el("div", {}, [
          el("div", { texto: r.porque }),
          el("div", { classe: "sub-linha",
                      texto: `usa ${modulo(r.porque_tem).nome}: ${numero(r.aberturas_origem)} aberturas em 30 dias` }),
        ]),
      ]
    )));
  }

  // ------------------------------------------------------- linha do tempo --
  const tempo = cartaoLinhaDoTempo(linhaDoTempo({
    cliente, pedidos: pedidosDoCliente, testes: testesDoCliente || [], modulos: modulosPagos, maquinas, notas,
    assinatura, nomeDoModulo: (codigo) => modulo(codigo).nome,
  }), agora);
  if (tempo) destino.append(tempo);

  // --------------------------------------------- compras do modelo antigo --
  if (pedidosDoCliente.length) {
    destino.append(cartao("Compras e pedidos da loja", tabela(
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

  // ------------------------------------------------ bloquear ou excluir --
  destino.append(zonaDePerigo(cliente, { modulos: tem, maquinas, depois: refazer }));

  if (silencioso) substituirNaGaveta(antiga, destino, cliente.nome || cliente.email);
}

/** Quem é, como está e os atalhos de sempre: o que se lê em 2 segundos. */
function topoDaFicha({ cliente, mensal, maquinas, gestao, agora, vitalicia }) {
  const online = maquinas.filter((m) => hubAberto(m, agora));
  const s = mensal ? SITUACAO[mensal.situacao] : null;
  const selos = [
    mensal ? pilula(s?.texto || mensal.situacao, s?.tom || "neutro")
      : vitalicia ? pilula("Vitalícia", "marca") : pilula("Sem licença", "neutro"),
    cliente.licenca_id && cliente.situacao !== "ativa" && !mensal ? pilulaSituacao(cliente.situacao) : null,
    cliente.licenca_id && cliente.status && cliente.status !== "ativa" && mensal ? pilulaSituacao(cliente.status) : null,
    online.length ? pilula(online.length > 1 ? `${online.length} computadores online` : "Online agora", "ok") : null,
    ...(gestao?.etiquetas || []).map((t) => el("span", { classe: "etiqueta", texto: t })),
  ];
  const destaque = mensal
    ? `${dinheiro(mensal.valor)} por mês · ${mensal.plano_nome ? `Plano ${mensal.plano_nome}` : "Montado à mão"}`
    : vitalicia
      ? `${(cliente.produtos_codigos || []).length ? contagem(cliente.produtos_codigos.length, "módulo") : "Nenhum módulo"}` +
        (Number(cliente.total_comprado) ? ` · comprou ${dinheiro(cliente.total_comprado)}` : "")
      : "Ainda não testou nem assinou";
  const detalhe = mensal ? detalheDaSituacao(mensal) : "";

  const acoes = [
    botaoWhatsApp(cliente.telefone, `Olá, ${primeiro(cliente.nome)}! Aqui é da DumTech.`),
    cliente.licenca_id
      ? el("button", { classe: "botao botao-fantasma botao-mini", texto: "Enviar chave",
                       title: "WhatsApp, e-mail ou Mercado Livre, com o link de download",
                       onclick: () => enviarChave(cliente.licenca_id, { reserva: reservaDoCliente(cliente) }) })
      : null,
    el("button", { classe: "botao botao-fantasma botao-mini", texto: "Editar dados", onclick: () => editarCliente(cliente) }),
    vitalicia
      ? el("button", { classe: "botao botao-fantasma botao-mini", texto: "Computadores",
                       title: "Em quantos computadores a licença vale", onclick: () => editarLicenca(cliente) })
      : null,
  ].filter(Boolean);

  return el("section", { classe: "ficha-topo" }, [
    el("div", { classe: "ficha-selos" }, selos.filter(Boolean)),
    el("p", { classe: "ficha-destaque", texto: destaque }),
    detalhe ? el("p", { classe: "sub-linha", texto: detalhe[0].toUpperCase() + detalhe.slice(1) }) : null,
    el("div", { classe: "acoes-linha ficha-atalhos" }, acoes),
    el("div", { classe: "dados" }, [
      dado("E-mail", cliente.email || "—"),
      dado("WhatsApp", telefone(cliente.telefone) || "—"),
      dado("CPF ou CNPJ", fmtDocumento(cliente.documento) || "—"),
      dado("Cliente desde", data(cliente.cliente_desde)),
      dado("Chave", cliente.chave ? el("code", { texto: cliente.chave }) : "—"),
      dado("Computadores", cliente.licenca_id ? `${cliente.computadores} de ${cliente.max_computadores}` : "—"),
      dado("Hub falou com o servidor", cliente.ultima_checagem ? relativo(cliente.ultima_checagem, agora) : "nunca"),
      dado("Canal", CANAIS[gestao?.canal] || (cliente.origem === "hub" ? "Pelo site ou Hub" : "Cadastrado no painel")),
    ]),
  ]);
}

/** Vitalício: os módulos que tem, os que está testando e o "liberar". */
function cartaoModulos({ cliente, produtos, combos, tem, naoTem, testes, agora, depois }) {
  const escolha = el("select", { "aria-label": "Módulo para liberar" }, [
    el("option", { value: "", texto: "Liberar módulo…" }),
    ...naoTem.map((p) => el("option", { value: `p:${p.codigo}`, texto: p.nome })),
    ...combos.filter((c) => c.ativo).map((c) => el("option", { value: `c:${c.codigo}`, texto: `Combo ${c.nome}` })),
  ]);
  const liberar = el("button", {
    classe: "botao botao-primario botao-mini", texto: "Liberar",
    onclick: (e) => {
      if (!escolha.value) return recado("Escolha um módulo primeiro.", "erro");
      const [tipo, codigo] = escolha.value.split(":");
      agir(e.target, async () => {
        await rpc("dumtech_liberar_produtos", {
          p_licenca_id: cliente.licenca_id,
          p_produtos: tipo === "p" ? [codigo] : [],
          p_combo: tipo === "c" ? codigo : null,
        });
        await depois();
      }, { feito: `Módulo liberado. ${AVISO_HUB}` });
    },
  });

  const pilulas = [
    ...tem.map((codigo) => {
      const pilulaDoModulo = pilulaModulo(codigo);
      pilulaDoModulo.append(el("button", {
        classe: "tirar-modulo", title: `Tirar ${modulo(codigo).nome} desta licença`, texto: "×",
        "aria-label": `Tirar ${modulo(codigo).nome}`,
        onclick: (evento) => {
          evento.stopPropagation();
          if (!confirmar(`Tirar ${modulo(codigo).nome} desta licença? Ele para de abrir no Hub do cliente em até 2 minutos.`)) return;
          const produto = produtos.find((p) => p.codigo === codigo);
          agir(evento.target, async () => {
            await apagar("licenca_produtos", { licenca_id: `eq.${cliente.licenca_id}`, produto_id: `eq.${produto.id}` });
            await depois();
          }, { feito: "Módulo removido." });
        },
      }));
      return pilulaDoModulo;
    }),
    // módulo em teste grátis aparece aceso, com o selo: ele abre no Hub até o fim do teste
    ...naoTem.map((p) => {
      const teste = (testes || []).find((t) => t.produto_id === p.id && estadoDoTeste(t, agora) !== "terminou");
      if (!teste) return pilulaModulo(p.codigo, { apagada: true });
      const emTeste = pilulaModulo(p.codigo);
      emTeste.title = `Em teste grátis até ${data(teste.termina_em)}`;
      emTeste.append(el("span", { classe: "selo-teste", texto: "teste" }));
      return emTeste;
    }),
  ];

  // teste grátis de um módulo (o modelo vitalício): dar, estender, encerrar
  const blocoDoTeste = [];
  if (testes) {
    const testados = new Set(testes.map((t) => t.produto_id));
    const paraTestar = naoTem.filter((p) => !testados.has(p.id));
    if (testes.length) {
      blocoDoTeste.push(tabela(
        ["Teste grátis", "Situação", { texto: "Uso no teste", numero: true }, ""],
        testes,
        (t) => [pilulaModulo(t.codigo), periodo(t, agora), usoNoTeste(t),
                el("div", { classe: "ferramentas" }, acoesDoTeste(t, cliente, agora, { depois }))]
      ));
    }
    if (paraTestar.length) {
      const escolhaTeste = el("select", { "aria-label": "Módulo para testar" }, [
        el("option", { value: "", texto: "Dar 7 dias de teste…" }),
        ...paraTestar.map((p) => el("option", { value: p.id, texto: modulo(p.codigo).nome })),
      ]);
      blocoDoTeste.push(el("div", { classe: "ferramentas" }, [
        escolhaTeste,
        el("button", {
          classe: "botao botao-fantasma botao-mini", texto: "Dar teste",
          onclick: (e) => {
            const produto = paraTestar.find((p) => p.id === escolhaTeste.value);
            if (!produto) return recado("Escolha o módulo do teste.", "erro");
            darTeste(e.target, { licencaId: cliente.licenca_id, produto, depois });
          },
        }),
      ]));
    }
  }

  return cartao("Módulos", [
    el("div", { classe: "modulos-lista" }, pilulas),
    el("div", { classe: "ferramentas", estilo: "margin-top:14px" }, [escolha, liberar]),
    ...blocoDoTeste.map((no) => el("div", { estilo: "margin-top:14px" }, [no])),
  ]);
}

/** O fim da ficha: suspender, cancelar e excluir, com o que cada um faz. */
function zonaDePerigo(cliente, { modulos, maquinas, depois }) {
  const mudarStatus = (novo, texto, classe = "botao-fantasma") => el("button", {
    classe: `botao ${classe} botao-mini`, texto,
    onclick: (e) => {
      if (novo === "cancelada" && !confirmar("Cancelar esta licença agora? Os módulos param de abrir no computador do " +
                                             "cliente em até 2 minutos. Para assinante que quer sair, prefira Encerrar, em Assinatura.")) return;
      agir(e.target, async () => {
        await atualizar("licencas", { id: `eq.${cliente.licenca_id}` }, { status: novo });
        await depois();
      }, { feito: `Licença ${novo === "ativa" ? "reativada" : novo}. ${AVISO_HUB}` });
    },
  });
  const botoes = [];
  if (cliente.licenca_id) {
    if (cliente.status !== "ativa") botoes.push(mudarStatus("ativa", "Reativar licença", "botao-primario"));
    if (cliente.status === "ativa") botoes.push(mudarStatus("suspensa", "Suspender licença"));
    if (cliente.status !== "cancelada") botoes.push(mudarStatus("cancelada", "Cancelar licença", "botao-perigo"));
    botoes.push(el("button", { classe: "botao botao-perigo botao-mini", texto: "Excluir licença…",
                               title: "Apaga a licença e tudo dela; o cadastro do cliente fica",
                               onclick: () => excluirLicenca(cliente, { modulos, maquinas }) }));
  }
  botoes.push(el("button", { classe: "botao botao-perigo botao-mini", texto: "Excluir cliente…",
                             onclick: () => excluirCliente(cliente, { modulos, maquinas }) }));
  const zona = cartao("Bloquear ou excluir", [
    el("p", { classe: "zona-texto", texto: cliente.licenca_id
      ? "Suspender trava o Hub até você reativar. Cancelar e excluir param os módulos em até 2 minutos."
      : "Apaga o cadastro. Os pedidos antigos continuam no histórico." }),
    el("div", { classe: "acoes-linha" }, botoes),
  ]);
  zona.classList.add("zona-perigo");
  return zona;
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

export const campo = (rotulo, entrada, dica = "") =>
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

// ============================================== editar cliente e licenca ====
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

async function editarLicenca(cliente) {
  const ativos = await ler("ativacoes", {
    select: "maquina,apelido,versao", filtros: { licenca_id: `eq.${cliente.licenca_id}` },
    ordem: "ativado_em.asc", fresco: true,
  });
  const computadores = el("input", { id: "licenca-computadores", type: "number", min: "1", max: "50",
                                     value: String(cliente.max_computadores || 1) });

  // reduzir vale de verdade: quem passa do limite novo precisa sair, e quem sai
  // e escolha sua. O limite e as vagas mudam juntos no banco, ou nada muda.
  const marcas = ativos.map((m) => ({ maquina: m.maquina, caixa: el("input", { type: "checkbox" }) }));
  const aviso = el("small", { classe: "dica" });
  const blocoVagas = el("div", { classe: "campo", hidden: true }, [
    el("span", { texto: "Quais computadores desconectar?" }),
    el("div", { classe: "acoes-linha" }, ativos.map((m, i) =>
      el("label", { classe: "pilula" }, [marcas[i].caixa, m.apelido || m.maquina]))),
    aviso,
  ]);
  const marcadas = () => marcas.filter((m) => m.caixa.checked).map((m) => m.maquina);
  const faltam = () => vagasASoltar(ativos.length - marcadas().length, Math.max(1, Number(computadores.value) || 1));
  const conferirVagas = () => {
    const maximo = Math.max(1, Number(computadores.value) || 1);
    blocoVagas.hidden = !vagasASoltar(ativos.length, maximo);
    aviso.textContent = faltam() ? `Marque mais ${faltam()}.` : "O computador marcado perde a licença em até 2 minutos.";
  };
  computadores.addEventListener("input", conferirVagas);
  marcas.forEach((m) => m.caixa.addEventListener("change", conferirVagas));
  conferirVagas();

  abrirGaveta({
    acima: "Computadores da licença", titulo: cliente.chave,
    conteudo: cartao("", [
      campo("Computadores", computadores, `Hoje ativada em ${ativos.length}. Passou desse limite, o próximo computador é recusado.`),
      blocoVagas,
      el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
        el("button", {
          classe: "botao botao-primario", texto: "Salvar",
          onclick: (e) => {
            if (faltam()) return recado(`Marque mais ${faltam()} computador(es) para desconectar.`, "erro");
            const nomesSaindo = ativos.filter((m) => marcadas().includes(m.maquina)).map((m) => m.apelido || m.maquina);
            if (nomesSaindo.length && !confirmar(`Desconectar ${nomesSaindo.join(", ")}? O Hub para de abrir ` +
                                                 "nesses computadores, e a vaga fica livre.")) return;
            agir(e.target, async () => {
              try {
                const resposta = await rpc("dumtech_ajustar_computadores", {
                  p_licenca: cliente.licenca_id, p_maximo: Math.max(1, Number(computadores.value) || 1),
                  p_soltar: marcadas(),
                });
                if (!resposta?.ok) throw new Error(resposta?.mensagem || "");
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

  alvo.append(el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Pedidos antigos da loja" }),
      el("p", { texto: "Do tempo em que a loja vendia módulo avulso. Aprovar entrega os módulos na licença que o cliente " +
                       "já tem (ou cria uma) e abre o envio da chave. Clique num pedido para ver, editar ou excluir." }),
    ]),
    el("div", { classe: "ferramentas" }, [
      el("button", { classe: "botao botao-fantasma", texto: "Voltar para Hoje", onclick: () => irPara("hoje") }),
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
