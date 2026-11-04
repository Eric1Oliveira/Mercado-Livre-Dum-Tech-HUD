// Uso (quem usa o quê) e Segurança (quem tentou entrar).
//
// O uso chega agregado por dia: "o módulo X foi aberto N vezes naquele dia,
// naquele computador". Não há hora nem sequência — nem aqui, nem no banco.
// As regras (quem esfriou, quem sumiu, Hub aberto, versão) moram em saude.js.

import { ler } from "../api.js";
import { contagem, dataHora, numero, quando, relativo } from "../formato.js";
import { lerPresenca } from "../gestao-dados.js";
import { comPresenca } from "../gestao.js";
import { colunasPorDia, faixa, legendaDaFaixa } from "../graficos.js";
import { mensagemDeAcompanhamento } from "../mensagens.js";
import { cor, modulo } from "../modulos.js";
import {
  DIA, ESTADOS_DE_USO, FALTA_MIGRATION, diaLocal, modulosParados, saudeDosClientes, serieDiaria, variacao,
  versaoEmDia, virouPedido,
} from "../saude.js";
import {
  barra, botaoWhatsApp, cartao, chips, el, icone, limpar, pessoa, pilula, pilulaModulo, tabela, tile, vazio,
} from "../ui.js";
import { ficha } from "./comercial.js";

const JANELA = 30;

// ==================================================================== uso ====
// A pergunta da tela: meus clientes estão usando? Quem esfriou, quem pagou e
// não abre, quem está com o Hub velho - e o que fazer (a ficha, o WhatsApp).
const filtroUso = { estado: "" };
const ATENCAO = new Set(["sumiu", "nunca", "sem_ativar", "esfriando"]);
const diaDoPainel = (dias) => diaLocal(new Date(Date.now() - dias * DIA));

export async function uso(alvo) {
  const agora = new Date();
  // tudo chega somado pelo banco (uma linha por dia, uma por cliente): o
  // PostgREST corta leitura acima de 1000 linhas, e conta cortada mente calada
  const [modulos, clientes, dias, faixas, registros, aparelhos, modulosParadosDoBanco, versoes, cliques, pedidos,
         presencas] =
    await Promise.all([
      ler("painel_modulos", { ordem: "aberturas_30d.desc" }),
      ler("painel_clientes", { ordem: "nome.asc" }),
      ler("painel_uso_dias", { filtros: { dia: `gte.${diaDoPainel(2 * JANELA)}` } }).catch(() => null),
      ler("painel_uso_por_cliente").catch(() => null),
      ler("ativacoes", { select: "licenca_id,maquina,apelido,versao,versao_em,ultima_checagem,ativado_em" }),
      ler("celular_aparelhos", { select: "licenca_id,revogado_em" }),
      ler("painel_modulos_da_licenca", { filtros: { situacao: "eq.ativa", aberturas_30d: "eq.0" } }).catch(() => null),
      ler("hub_versoes", { limite: 1 }).catch(() => null),
      // quem clicou em "Comprar" no Hub (o banco guarda uns 7 dias)
      ler("compra_tokens", {
        select: "cliente_id,nome,email,produtos,criado_em,usado_em", ordem: "criado_em.desc",
        filtros: { criado_em: `gte.${diaDoPainel(7)}` },
      }).catch(() => null),
      ler("pedidos_site", { select: "cliente_id,email,criado_em", filtros: { criado_em: `gte.${diaDoPainel(7)}` } }),
      lerPresenca().catch(() => []),
    ]);
  const ativacoes = comPresenca(registros, presencas);
  const publicada = String(versoes?.[0]?.versao || "");
  const porId = new Map(clientes.map((c) => [c.cliente_id, c]));

  const cabeca = el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Uso" }),
      el("p", { texto: `Quem usa o quê nos últimos ${JANELA} dias, em que computador e em que versão do Hub.` }),
    ]),
  ]);
  if (!dias || !faixas || !modulosParadosDoBanco) {
    alvo.append(cabeca, cartao("", vazio("O banco ainda não tem as visões novas do uso", FALTA_MIGRATION)),
                cartaoPorModulo(modulos));
    return;
  }

  // os 30 dias de agora e os 30 de antes (a comparação do primeiro número)
  const serie60 = serieDiaria(dias, 2 * JANELA, agora);
  const clientesNoDia = new Map(dias.map((d) => [String(d.dia).slice(0, 10), Number(d.clientes || 0)]));
  const serie = serie60.slice(JANELA).map((d) => ({ ...d, clientes: clientesNoDia.get(d.dia) || 0 }));
  const total = serie.reduce((soma, d) => soma + d.valor, 0);
  const delta = variacao(total, serie60.slice(0, JANELA).reduce((soma, d) => soma + d.valor, 0));

  const saude = saudeDosClientes({ clientes, faixas, ativacoes, aparelhos, publicada }, agora);
  const conta = (estado) => saude.filter((s) => s.estado === estado).length;
  const atencao = saude.filter((s) => ATENCAO.has(s.estado)).length;
  const comVersao = ativacoes.filter((a) => a.versao);
  const emDia = comVersao.filter((a) => versaoEmDia(a.versao, publicada)).length;
  const comCelular = saude.filter((s) => s.celulares > 0).length;

  alvo.append(
    cabeca,
    el("div", { classe: "tiles" }, [
      tile("Aberturas", numero(total),
        delta === null ? `últimos ${JANELA} dias` : `${delta > 0 ? "+" : ""}${delta}% contra os ${JANELA} dias antes`),
      tile("Usando", numero(conta("usando")), `abriram nos últimos 7 dias, de ${numero(saude.length)}`),
      tile("Pedem atenção", numero(atencao), "esfriando, sumidos ou sem instalar", atencao ? "ruim" : "ok"),
      tile("Hub em dia", comVersao.length ? `${numero(emDia)} de ${numero(comVersao.length)}` : "—",
        publicada ? `computadores na ${publicada}` : "nenhuma versão publicada",
        comVersao.length && emDia === comVersao.length ? "ok" : ""),
      tile("No celular", numero(comCelular), `de ${numero(saude.length)} clientes com licença`),
    ])
  );

  alvo.append(cartao("Aberturas por dia",
    total ? colunasPorDia(serie)
      : vazio("Nenhuma abertura nos últimos 30 dias", "O Hub envia o uso quando fala com o servidor."),
    el("span", { classe: "cartao-nota", texto: `últimos ${JANELA} dias` })));

  alvo.append(cartaoSaude(saude, { conta, atencao }));
  alvo.append(cartaoParados(modulosParados(modulosParadosDoBanco, agora), porId));
  alvo.append(cartaoPorModulo(modulos));
  if (cliques) alvo.append(cartaoLoja(cliques, pedidos, porId, agora));
}

function cartaoPorModulo(modulos) {
  const teto = Math.max(1, ...modulos.map((m) => Number(m.aberturas_30d)));
  return cartao("Por módulo", tabela(
    ["Módulo", { texto: "Clientes com", numero: true }, { texto: "Usando", numero: true },
     { texto: "Aberturas", numero: true }, "Proporção"],
    modulos,
    (m) => [
      pilulaModulo(m.codigo),
      numero(m.clientes),
      numero(m.licencas_ativas_30d),
      numero(m.aberturas_30d),
      barra(Number(m.aberturas_30d), teto, cor(m.codigo)),
    ]
  ));
}

/** Cada cliente com licença: estado, faixa de 30 dias, Hub e celular. */
function cartaoSaude(saude, { conta, atencao }) {
  const destino = el("div", {});
  const tetoDaFaixa = Math.max(1, ...saude.flatMap((s) => s.serie.map((d) => d.valor)));
  const opcoes = [
    { valor: "", texto: "Todos", conta: saude.length },
    { valor: "atencao", texto: "Pedem atenção", conta: atencao },
    ...Object.entries(ESTADOS_DE_USO).map(([valor, { texto }]) => ({ valor, texto, conta: conta(valor) })),
  ].filter((o) => o.valor === "" || o.conta > 0);
  if (!opcoes.some((o) => o.valor === filtroUso.estado)) filtroUso.estado = "";

  const desenhar = () => {
    const visiveis = saude.filter((s) => !filtroUso.estado
      || (filtroUso.estado === "atencao" ? ATENCAO.has(s.estado) : s.estado === filtroUso.estado));
    limpar(destino).append(
      el("div", { classe: "cartao-filtros" }, [
        chips(opcoes, filtroUso.estado, (valor) => { filtroUso.estado = valor; desenhar(); }, "Filtrar clientes"),
        legendaDaFaixa(),
      ]),
      tabela(
        ["Cliente", "Situação", `Últimos ${JANELA} dias`, "Hub e celular", ""],
        visiveis,
        (s) => [
          pessoa(s.cliente.nome, s.cliente.email),
          el("div", {}, [
            pilula(ESTADOS_DE_USO[s.estado].texto, ESTADOS_DE_USO[s.estado].tom),
            el("div", { classe: "sub-linha", texto: s.cliente.ultimo_uso ? `abriu ${quando(s.cliente.ultimo_uso)}`
              : s.estado === "sem_ativar" ? "nunca ativou o Hub" : "nenhum módulo aberto" }),
          ]),
          el("div", {}, [
            faixa(s.serie, tetoDaFaixa, { rotulo: s.cliente.nome }),
            el("div", { classe: "sub-linha", texto: s.aberturas
              ? `${numero(s.aberturas)} ${s.aberturas === 1 ? "abertura" : "aberturas"} em ${numero(s.diasComUso)} ${s.diasComUso === 1 ? "dia" : "dias"}`
              : "nenhuma abertura" }),
          ]),
          hubs(s.computadores, s.celulares),
          ATENCAO.has(s.estado)
            ? botaoWhatsApp(s.cliente.telefone, mensagemDeAcompanhamento("sumiu", { nome: s.cliente.nome }))
            : null,
        ],
        { aoClicar: (s) => ficha(s.cliente), vazioTexto: "Ninguém nesta situação." }
      )
    );
  };
  desenhar();
  return cartao("Clientes com licença", destino);
}

const CELULAR = "M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z M11 18h2";

/** Os computadores do cliente (apelido, versão, Hub aberto agora) e os celulares. */
export function hubs(computadores, celulares = 0) {
  if (!computadores.length && !celulares) return el("span", { classe: "sub-linha", texto: "nenhum computador" });
  const linhaDoCelular = celulares
    ? el("div", { classe: "hub-pc hub-celular" }, [icone(CELULAR, 13), contagem(celulares, "celular", "celulares")])
    : null;
  return el("div", { classe: "hub-lista" }, [...computadores.map((pc) => el("div", {
    classe: "hub-pc", title: pc.visto ? `Falou com o servidor ${relativo(pc.visto)}` : "Nunca falou com o servidor",
  }, [
    el("span", { classe: "hub-ponto", "data-aberto": pc.aberto ? "sim" : null }),
    el("span", { classe: "hub-nome", texto: pc.apelido }),
    pc.versao
      ? el("span", { classe: "hub-versao", "data-velha": pc.emDia === false ? "sim" : null, texto: pc.versao,
                     "aria-label": pc.emDia === false ? `versão ${pc.versao}, desatualizada` : `versão ${pc.versao}` })
      : null,
    el("span", { classe: "sub-linha", texto: pc.aberto ? "aberto agora" : relativo(pc.visto) }),
  ])), linhaDoCelular]);
}

/** Pagou e não abre: chance de ajudar antes de o cliente achar que não serve. */
function cartaoParados(parados, porId) {
  return cartao(`Pagaram e não abriram em ${JANELA} dias`, tabela(
    ["Cliente", "Módulo", "Comprado", "Último uso", ""],
    parados,
    (m) => {
      const c = porId.get(m.cliente_id) || {};
      return [
        pessoa(c.nome, c.email),
        pilulaModulo(m.codigo),
        quando(m.liberado_em),
        m.ultimo_uso ? quando(m.ultimo_uso) : "nunca abriu",
        botaoWhatsApp(c.telefone, mensagemDeAcompanhamento("parado", { nome: c.nome, modulo: modulo(m.codigo).nome })),
      ];
    },
    { aoClicar: (m) => porId.get(m.cliente_id) && ficha(porId.get(m.cliente_id)),
      vazioTexto: `Todo módulo pago foi aberto nos últimos ${JANELA} dias.` }
  ));
}

/** Quem clicou em "Comprar" no Hub nos últimos 7 dias, e se fechou pedido. */
function cartaoLoja(cliques, pedidos, porId, agora) {
  const porPessoa = new Map();
  for (const clique of cliques) { // vem do mais novo para o mais velho
    const chave = clique.cliente_id || String(clique.email || "").toLowerCase() || clique.criado_em;
    const atual = porPessoa.get(chave);
    if (atual) {
      atual.vezes += 1;
      atual.abriu ||= Boolean(clique.usado_em);
    } else {
      porPessoa.set(chave, { ...clique, vezes: 1, abriu: Boolean(clique.usado_em) });
    }
  }
  return cartao("Clicaram em Comprar no Hub", tabela(
    ["Quem", "Quando", "Já tinha", "Resultado", ""],
    [...porPessoa.values()],
    (l) => {
      const cliente = porId.get(l.cliente_id);
      const pediu = virouPedido(l, pedidos);
      return [
        pessoa(cliente?.nome || l.nome || "Visitante", cliente?.email || l.email),
        el("div", {}, [relativo(l.criado_em, agora),
          l.vezes > 1 ? el("div", { classe: "sub-linha", texto: `${l.vezes} cliques na semana` }) : null]),
        el("div", { classe: "modulos-lista" }, (l.produtos || []).length
          ? l.produtos.map((codigo) => pilulaModulo(codigo))
          : [pilula("nenhum", "neutro")]),
        pediu ? pilula("Fez pedido", "ok")
          : l.abriu ? pilula("Viu a loja, não pediu", "aviso") : pilula("Não chegou à loja", "neutro"),
        pediu ? null
          : botaoWhatsApp(cliente?.telefone, mensagemDeAcompanhamento("loja", { nome: cliente?.nome || l.nome })),
      ];
    },
    { aoClicar: (l) => porId.get(l.cliente_id) && ficha(porId.get(l.cliente_id)),
      vazioTexto: "Ninguém clicou em Comprar no Hub nos últimos 7 dias." }
  ), el("span", { classe: "cartao-nota", texto: "últimos 7 dias" }));
}

// ============================================================== segurança ====
export async function seguranca(alvo) {
  const [tentativas, ativacoes, clientes, alteracoes, versoes] = await Promise.all([
    ler("licenca_tentativas", { ordem: "quando.desc", limite: 200 }),
    ler("ativacoes", { ordem: "ultima_checagem.desc", limite: 50 }),
    ler("painel_clientes"),
    // sem a migration da auditoria a tabela nao existe: a tela segue sem o cartao
    ler("auditoria", { ordem: "quando.desc", limite: 40 }).catch(() => null),
    // idem para a versao publicada do Hub
    ler("hub_versoes", { limite: 1 }).catch(() => null),
  ]);

  const ontem = Date.now() - 86400000;
  const recentes = tentativas.filter((t) => new Date(t.quando).getTime() > ontem);
  const porMaquina = new Map();
  for (const t of recentes) {
    porMaquina.set(t.maquina, (porMaquina.get(t.maquina) || 0) + 1);
  }
  const insistentes = [...porMaquina.entries()]
    .filter(([, quantas]) => quantas >= 10)
    .sort((a, b) => b[1] - a[1]);

  const porLicenca = new Map(clientes.filter((c) => c.licenca_id)
    .map((c) => [c.licenca_id, c]));

  alvo.append(
    el("div", { classe: "pagina-cabeca" }, [
      el("div", {}, [
        el("h1", { texto: "Segurança" }),
        el("p", { texto: "Chaves recusadas e computadores ativados." }),
      ]),
    ]),
    el("div", { classe: "tiles" }, [
      tile("Recusas 24h", numero(recentes.length), "tentativas que não entraram",
        recentes.length > 50 ? "ruim" : ""),
      tile("Computadores insistindo", numero(insistentes.length), "10+ tentativas em 24h",
        insistentes.length ? "ruim" : "ok"),
      tile("Ativações", numero(ativacoes.length), "computadores com licença"),
    ])
  );

  if (insistentes.length) {
    alvo.append(cartao("Insistindo demais", tabela(
      ["Computador", { texto: "Tentativas 24h", numero: true }],
      insistentes,
      ([maquina, quantas]) => [el("code", { texto: maquina || "—" }), numero(quantas)]
    )));
  }

  alvo.append(cartao(`${contagem(tentativas.length, "tentativa")} recusada(s)`, tabela(
    ["Quando", "Chave tentada", "Computador", "Motivo"],
    tentativas.slice(0, 60),
    (t) => [
      dataHora(t.quando),
      el("code", { texto: t.chave || "—" }),
      el("code", { texto: t.maquina || "—" }),
      pilula(motivo(t.erro), t.erro === "nao_encontrada" ? "ruim" : "aviso"),
    ],
    { vazioTexto: "Nenhuma tentativa recusada. " }
  )));

  const publicada = String(versoes?.[0]?.versao || "");
  alvo.append(cartao("Computadores ativados", tabela(
    ["Cliente", "Apelido", "Computador", "Versão", "Última checagem"],
    ativacoes,
    (a) => {
      const dono = porLicenca.get(a.licenca_id);
      return [
        dono ? pessoa(dono.nome, dono.email) : "—",
        a.apelido || "—",
        el("code", { texto: a.maquina }),
        a.versao
          ? el("span", { classe: "hub-versao", "data-velha": versaoEmDia(a.versao, publicada) === false ? "sim" : null,
                         texto: a.versao })
          : "—",
        quando(a.ultima_checagem),
      ];
    },
    { vazioTexto: "Nenhum computador ativado ainda." }
  )));

  if (alteracoes) {
    alvo.append(cartao("Quem mexeu em quê", tabela(
      ["Quando", "Quem", "O quê", "Detalhe"],
      alteracoes,
      (a) => [
        dataHora(a.quando),
        a.quem_email || { painel: "Painel", servico: "Servidor", sql: "SQL Editor" }[a.origem] || a.origem,
        `${TABELAS[a.tabela] || a.tabela} · ${OPERACOES[a.operacao] || a.operacao}`,
        el("span", { classe: "detalhe-auditoria", texto: detalhe(a) }),
      ],
      { vazioTexto: "Nenhuma alteração registrada ainda." }
    )));
  }
}

const TABELAS = {
  clientes: "Cliente", licencas: "Licença", licenca_produtos: "Módulo da licença",
  ativacoes: "Computador", produtos: "Módulo", combos: "Combo", combo_produtos: "Módulo do combo",
  comunicados: "Anúncio", pedidos_site: "Pedido", administradores: "Administrador",
  licenca_testes: "Teste grátis", celular_aparelhos: "Celular",
  hub_versoes: "Versão publicada", hub_lancamentos: "Versão", hub_liberacoes: "Atualização do cliente",
  cliente_notas: "Anotação",
};
const OPERACOES = { insert: "criou", update: "mudou", delete: "apagou" };

/** "preco: 249 → 311.9" para mudança; o nome/título para criar e apagar. */
function detalhe(a) {
  const curto = (valor) => {
    const texto = valor === null || valor === undefined ? "vazio" : typeof valor === "object" ? JSON.stringify(valor) : String(valor);
    return texto.length > 40 ? `${texto.slice(0, 39)}…` : texto;
  };
  if (a.operacao === "update" && a.depois) {
    return Object.keys(a.depois)
      .map((campo) => `${campo}: ${curto(a.antes?.[campo])} → ${curto(a.depois[campo])}`)
      .join(" · ");
  }
  const linha = a.depois || a.antes || {};
  return curto(linha.nome || linha.titulo || linha.versao || linha.texto || linha.codigo || linha.chave
               || linha.maquina || linha.email || a.registro);
}

const motivo = (erro) => ({
  nao_encontrada: "Chave não existe",
  inativa: "Licença suspensa ou cancelada",
  expirada: "Licença vencida",
  limite_maquinas: "Limite de computadores",
  dados_incompletos: "Dados incompletos",
}[erro] || erro || "—");
