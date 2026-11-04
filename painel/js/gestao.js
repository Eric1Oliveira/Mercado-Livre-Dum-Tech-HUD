// As regras da gestão de clientes: quem está online, em que pé está a
// atualização de cada um, os filtros que se combinam, a ordem da lista, a
// exportação e a linha do tempo. Sem DOM e sem rede (testado em
// tests/gestao.test.mjs): quem desenha são telas/clientes.js, telas/hoje.js e telas/atualizacoes.js.
//
// Tudo recebe o "agora" de quem chama, como em saude.js.

import {
  ESTADOS_DE_USO, compararVersoes, diaLocal, diasEntre, estadoDeUso, estadoDoTeste, hubAberto,
  serieDaFaixa, vistoEm,
} from "./saude.js";

// ============================================================== presença ===
const chaveDaMaquina = (linha) => `${linha.licenca_id}|${linha.maquina}`;

/**
 * Cada computador com a última batida. A versão da batida é a mais nova que se
 * sabe: `ativacoes` só é regravada de hora em hora.
 */
export function comPresenca(ativacoes = [], presencas = []) {
  const porMaquina = new Map((presencas || []).map((p) => [chaveDaMaquina(p), p]));
  return ativacoes.map((ativacao) => {
    const presenca = porMaquina.get(chaveDaMaquina(ativacao));
    if (!presenca) return ativacao;
    return {
      ...ativacao,
      visto_em: presenca.visto_em,
      online_desde: presenca.online_desde,
      versao_desde: presenca.versao_desde,
      versao: presenca.versao || ativacao.versao,
    };
  });
}

export const ESTADOS_DE_CONEXAO = {
  online:  { texto: "Online agora", tom: "ok" },
  offline: { texto: "Offline", tom: "neutro" },
  nunca:   { texto: "Nunca conectou", tom: "neutro" },
};

// ============================================================ lançamentos ===
/** A versão pronta para lançar: a mais nova que ainda não foi para todos. */
export function versaoPendente(lancamentos = [], publicada = "") {
  return [...(lancamentos || [])]
    .filter((l) => !l.liberada_em && !l.descartada_em && compararVersoes(l.versao, publicada) > 0)
    .sort((a, b) => compararVersoes(b.versao, a.versao))[0] || null;
}

/** A versão que Atualizar e Forçar entregam: a pendente, ou a que já está no ar. */
export const versaoAlvo = (lancamentos, publicada) =>
  versaoPendente(lancamentos, publicada)?.versao || publicada || "";

const maisVelha = (versoes) => [...versoes].sort(compararVersoes)[0] || "";

export const ESTADOS_DA_ATUALIZACAO = {
  forcada:  { texto: "Forçada, aguardando", tom: "ruim" },
  liberada: { texto: "Liberada, aguardando", tom: "marca" },
  atrasado: { texto: "Atrasado", tom: "aviso" },
  em_dia:   { texto: "Em dia", tom: "ok" },
  sem_hub:  { texto: "Sem Hub", tom: "neutro" },
};

/**
 * Em que pé está a atualização deste cliente. Conta sempre o computador mais
 * atrasado: é ele que ainda precisa de atenção.
 */
export function estadoDaAtualizacao({ versoes = [], liberacao = null, publicada = "", forcadaGeral = false } = {}) {
  const atrasada = maisVelha(versoes);
  if (!atrasada) return "sem_hub";
  if (liberacao && compararVersoes(atrasada, liberacao.versao) < 0) {
    return liberacao.forcada ? "forcada" : "liberada";
  }
  if (publicada && compararVersoes(atrasada, publicada) < 0) return forcadaGeral ? "forcada" : "atrasado";
  return "em_dia";
}

// ===================================================== a linha de cada um ===
function agrupar(linhas, campo) {
  const grupos = new Map();
  for (const linha of linhas || []) {
    const chave = linha?.[campo];
    if (!grupos.has(chave)) grupos.set(chave, []);
    grupos.get(chave).push(linha);
  }
  return grupos;
}

const unicos = (lista) => [...new Set(lista)];

/**
 * Uma linha por cliente, com tudo o que a lista mostra e filtra. O que vem do
 * banco continua em `cliente`, que é o que a ficha recebe.
 */
export function montarClientes({
  clientes = [], ativacoes = [], presencas = [], liberacoes = [], gestao = [], faixas = [], aparelhos = [],
  testes = [], catalogo = [], publicada = "", forcadaGeral = false, alvo = "", mensalidades = [],
} = {}, agora = new Date()) {
  const maquinasDe = agrupar(comPresenca(ativacoes, presencas), "licenca_id");
  const liberacaoDe = new Map((liberacoes || []).map((l) => [l.licenca_id, l]));
  const gestaoDe = new Map((gestao || []).map((g) => [g.cliente_id, g]));
  const faixaDe = new Map((faixas || []).map((f) => [f.cliente_id, f]));
  const celularesDe = agrupar((aparelhos || []).filter((a) => !a.revogado_em), "licenca_id");
  const testesDe = agrupar(testes || [], "licenca_id");
  // so assinatura e teste: licenca vitalicia nunca tem mensalidade
  const mensalDe = new Map((mensalidades || []).filter((m) => m.tipo === "assinatura" || m.tipo === "teste")
    .map((m) => [m.licenca_id, m]));

  return clientes.map((cliente) => {
    const maquinas = cliente.licenca_id ? maquinasDe.get(cliente.licenca_id) || [] : [];
    const versoes = unicos(maquinas.map((m) => m.versao).filter(Boolean));
    const ligados = maquinas.filter((m) => hubAberto(m, agora));
    const vistos = maquinas.map(vistoEm).filter(Boolean).map((d) => d.getTime());
    const liberacao = cliente.licenca_id ? liberacaoDe.get(cliente.licenca_id) || null : null;
    const extra = gestaoDe.get(cliente.cliente_id) || {};
    const serie = serieDaFaixa(faixaDe.get(cliente.cliente_id), 30, agora);
    const modulos = cliente.produtos_codigos || [];
    const testando = (testesDe.get(cliente.licenca_id) || [])
      .filter((t) => ["rodando", "acabando"].includes(estadoDoTeste(t, agora)))
      .map((t) => t.codigo);

    return {
      id: cliente.cliente_id,
      cliente,
      nome: cliente.nome || cliente.email || "",
      maquinas,
      online: ligados.length,
      onlineDesde: ligados.map((m) => m.online_desde).filter(Boolean).sort()[0] || null,
      visto: vistos.length ? new Date(Math.max(...vistos)) : null,
      conexao: ligados.length ? "online" : vistos.length ? "offline" : "nunca",
      versoes: versoes.sort((a, b) => compararVersoes(b, a)),
      maisVelha: maisVelha(versoes),
      liberacao,
      atualizacao: estadoDaAtualizacao({ versoes, liberacao, publicada, forcadaGeral }),
      podeAtualizar: Boolean(alvo && versoes.length && compararVersoes(maisVelha(versoes), alvo) < 0),
      modulos,
      faltam: cliente.licenca_id ? catalogo.filter((codigo) => !modulos.includes(codigo)) : [],
      testando,
      uso: cliente.licenca_id && cliente.situacao === "ativa"
        ? estadoDeUso({
            ultimoUso: cliente.ultimo_uso,
            ativadoEm: maquinas.map((m) => m.ativado_em).filter(Boolean).sort()[0] || null,
          }, agora)
        : null,
      serie,
      aberturas: serie.reduce((soma, d) => soma + d.valor, 0),
      celulares: (celularesDe.get(cliente.licenca_id) || []).length,
      etiquetas: extra.etiquetas || [],
      proximoContato: extra.proximo_contato || null,
      compras: Number(extra.compras || 0),
      primeiraCompra: extra.primeira_compra || null,
      ultimaCompra: extra.ultima_compra || null,
      canal: extra.canal || "",
      anotacoes: Number(extra.anotacoes || 0),
      ultimaAnotacao: extra.ultima_anotacao || null,
      diasParaVencer: cliente.expira_em ? diasEntre(diaLocal(agora), cliente.expira_em) : null,
      mensal: cliente.licenca_id ? mensalDe.get(cliente.licenca_id) || null : null,
    };
  });
}

// ================================================================ filtros ===
// E entre os grupos, OU dentro do grupo: "Vendas ou Estoque, na 1.8.0, online".
const normal = (texto) =>
  String(texto ?? "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

export const CANAIS = { hub: "Pelo Hub", site: "Pela loja", mercadolivre: "Mercado Livre", manual: "Venda direta" };

function validade(linha) {
  if (!linha.cliente.licenca_id) return [];
  if (linha.diasParaVencer === null) return ["sem_prazo"];
  if (linha.diasParaVencer < 0) return ["vencida"];
  return [linha.diasParaVencer <= 30 ? "vence_30" : "depois"];
}

function contato(linha, agora) {
  if (!linha.proximoContato) return ["sem"];
  return [diasEntre(diaLocal(agora), linha.proximoContato) <= 0 ? "hoje" : "futuro"];
}

function mais(linha) {
  return [
    linha.celulares ? "celular" : "sem_celular",
    ...(linha.testando.length ? ["testando"] : []),
    ...(Number(linha.cliente.pedidos_abertos) ? ["pedido"] : []),
  ];
}

const paraRotulos = (mapa) => Object.fromEntries(Object.entries(mapa).map(([v, { texto }]) => [v, texto]));

/**
 * Cada grupo diz que valores uma linha tem. `opcoes` são as de sempre; o que
 * nasce dos dados (versão, módulo, etiqueta) aparece sozinho.
 */
export const GRUPOS = [
  { id: "conexao", rotulo: "Conexão", opcoes: paraRotulos(ESTADOS_DE_CONEXAO), valores: (l) => [l.conexao] },
  { id: "versao", rotulo: "Versão", opcoes: { sem: "Sem versão" }, versoes: true,
    valores: (l) => (l.versoes.length ? l.versoes : ["sem"]) },
  { id: "atualizacao", rotulo: "Atualização", opcoes: paraRotulos(ESTADOS_DA_ATUALIZACAO), valores: (l) => [l.atualizacao] },
  { id: "modulo", rotulo: "Tem módulo", modulos: true, valores: (l) => l.modulos },
  { id: "falta", rotulo: "Não tem", modulos: true, valores: (l) => l.faltam },
  { id: "licenca", rotulo: "Licença",
    opcoes: { ativa: "Ativa", suspensa: "Suspensa", expirada: "Vencida", cancelada: "Cancelada", sem: "Sem licença" },
    valores: (l) => [l.cliente.licenca_id ? l.cliente.situacao : "sem"] },
  { id: "tipo", rotulo: "Tipo", opcoes: { vitalicia: "Vitalícia", assinatura: "Assinatura", teste: "Teste" },
    valores: (l) => (l.cliente.tipo ? [l.cliente.tipo] : []) },
  { id: "cobranca", rotulo: "Mensalidade",
    opcoes: { teste: "Testando", em_dia: "Em dia", pendente: "Pagamento a confirmar", consulta: "Só consulta" },
    valores: (l) => (l.mensal ? [l.mensal.situacao] : []) },
  { id: "uso", rotulo: "Uso", opcoes: paraRotulos(ESTADOS_DE_USO), valores: (l) => (l.uso ? [l.uso] : []) },
  { id: "validade", rotulo: "Validade",
    opcoes: { vencida: "Já venceu", vence_30: "Vence em 30 dias", depois: "Vence depois", sem_prazo: "Sem prazo" },
    valores: validade },
  { id: "canal", rotulo: "Canal", opcoes: CANAIS, valores: (l) => (l.canal ? [l.canal] : []) },
  { id: "etiqueta", rotulo: "Etiqueta", opcoes: {}, valores: (l) => l.etiquetas },
  { id: "contato", rotulo: "Retorno",
    opcoes: { hoje: "Para hoje ou atrasado", futuro: "Agendado", sem: "Sem retorno" }, valores: contato },
  { id: "mais", rotulo: "Mais",
    opcoes: { celular: "Com celular", sem_celular: "Sem celular", testando: "Em teste grátis", pedido: "Com pedido aberto" },
    valores: mais },
];

const grupoPorId = new Map(GRUPOS.map((g) => [g.id, g]));

/** Atalhos de um clique para as combinações que se usa todo dia. */
export const ATALHOS = [
  { id: "assinantes", texto: "Assinantes", filtros: { tipo: ["assinatura"] } },
  { id: "testando", texto: "Testando", filtros: { tipo: ["teste"] } },
  { id: "vitalicios", texto: "Vitalícios", filtros: { tipo: ["vitalicia"] } },
  { id: "interessados", texto: "Sem licença", filtros: { licenca: ["sem"] } },
  { id: "atencao", texto: "Pedem atenção", filtros: { uso: ["sumiu", "nunca", "sem_ativar", "esfriando"] } },
  { id: "online", texto: "Online agora", filtros: { conexao: ["online"] } },
];

export function buscaCombina(linha, termo) {
  const alvo = normal(termo).trim();
  if (!alvo) return true;
  const { cliente } = linha;
  const digitos = alvo.replace(/\D/g, "");
  const texto = normal([
    cliente.nome, cliente.email, cliente.chave, ...linha.etiquetas,
    ...linha.maquinas.map((m) => m.apelido),
  ].join(" "));
  return texto.includes(alvo)
    || (digitos.length >= 4 && `${cliente.telefone || ""} ${cliente.documento || ""}`.replace(/\D/g, "").includes(digitos));
}

function passaNoGrupo(linha, grupo, escolhidos, agora) {
  if (!escolhidos?.length) return true;
  const valores = grupo.valores(linha, agora);
  return escolhidos.some((valor) => valores.includes(valor));
}

/** `filtros`: { conexao: ["online"], modulo: ["VENDAS", "ESTOQUE"] } */
export function filtrar(linhas, { busca = "", filtros = {} } = {}, agora = new Date()) {
  return linhas.filter((linha) => buscaCombina(linha, busca)
    && Object.entries(filtros).every(([id, escolhidos]) =>
      !grupoPorId.has(id) || passaNoGrupo(linha, grupoPorId.get(id), escolhidos, agora)));
}

/**
 * Quantos clientes cada opção mostraria. Cada grupo conta com os OUTROS
 * filtros aplicados: marcar uma versão não zera as outras versões do menu.
 */
export function contarOpcoes(linhas, { busca = "", filtros = {} } = {}, agora = new Date()) {
  const contas = {};
  for (const grupo of GRUPOS) {
    const semEste = filtrar(linhas, { busca, filtros: { ...filtros, [grupo.id]: [] } }, agora);
    const conta = new Map();
    for (const linha of semEste) {
      for (const valor of unicos(grupo.valores(linha, agora))) conta.set(valor, (conta.get(valor) || 0) + 1);
    }
    contas[grupo.id] = conta;
  }
  return contas;
}

/** As opções de um grupo: as fixas e as que nasceram dos dados, sem perder a marcada. */
export function opcoesDoGrupo(grupo, conta = new Map(), marcados = [], { rotuloModulo = (c) => c } = {}) {
  const fixas = Object.entries(grupo.opcoes || {}).map(([valor, texto]) => ({ valor, texto }));
  const conhecidas = new Set(fixas.map((o) => o.valor));
  const novas = unicos([...conta.keys(), ...marcados]).filter((v) => !conhecidas.has(v));
  const ordenadas = grupo.versoes
    ? novas.sort((a, b) => compararVersoes(b, a))
    : novas.sort((a, b) => String(a).localeCompare(String(b), "pt-BR"));
  const dinamicas = ordenadas.map((valor) => ({ valor, texto: grupo.modulos ? rotuloModulo(valor) : valor }));
  return [...(grupo.versoes ? [...dinamicas, ...fixas] : [...fixas, ...dinamicas])]
    .map((o) => ({ ...o, conta: conta.get(o.valor) || 0 }));
}

/** Quantos valores estão marcados, somando os grupos. */
export const quantosFiltros = (filtros = {}) =>
  Object.values(filtros).reduce((soma, valores) => soma + (valores?.length || 0), 0);

/** O atalho que corresponde exatamente aos filtros marcados, se houver. */
export function atalhoAtivo(filtros = {}) {
  const limpos = Object.entries(filtros).filter(([, v]) => v?.length);
  return ATALHOS.find((atalho) => {
    const grupos = Object.entries(atalho.filtros);
    return grupos.length === limpos.length && grupos.every(([id, valores]) => {
      const marcados = filtros[id] || [];
      return marcados.length === valores.length && valores.every((v) => marcados.includes(v));
    });
  })?.id || "";
}

// ================================================================== ordem ===
const CRITERIOS = {
  nome: (a, b) => a.nome.localeCompare(b.nome, "pt-BR"),
  conexao: (a, b) => a.online - b.online || (a.visto?.getTime() || 0) - (b.visto?.getTime() || 0),
  versao: (a, b) => compararVersoes(a.maisVelha, b.maisVelha),
  validade: (a, b) => (a.diasParaVencer ?? 1e6) - (b.diasParaVencer ?? 1e6),
  uso: (a, b) => a.aberturas - b.aberturas,
  comprado: (a, b) => Number(a.cliente.total_comprado || 0) - Number(b.cliente.total_comprado || 0),
  mensal: (a, b) => Number(a.mensal?.valor || 0) - Number(b.mensal?.valor || 0),
};

export function ordenarLinhas(linhas, campo = "conexao", crescente = false) {
  const criterio = CRITERIOS[campo] || CRITERIOS.nome;
  return [...linhas].sort((a, b) => (crescente ? 1 : -1) * criterio(a, b) || CRITERIOS.nome(a, b));
}

/** Quantos computadores em cada versão, da mais nova para a mais antiga. */
export function distribuicaoDeVersoes(ativacoes = []) {
  const conta = new Map();
  for (const { versao } of ativacoes) {
    const chave = versao || "";
    conta.set(chave, (conta.get(chave) || 0) + 1);
  }
  return [...conta.entries()]
    .map(([versao, computadores]) => ({ versao, computadores }))
    .sort((a, b) => compararVersoes(b.versao, a.versao));
}

// ============================================================== exportar ===
// Nome e e-mail chegam da loja, escritos por qualquer um. Uma célula que começa
// com = + - @ vira fórmula no Excel: o apóstrofo a mantém como texto.
const celulaCsv = (valor) => {
  let texto = String(valor ?? "");
  if (/^[=+\-@\t\r]/.test(texto)) texto = `'${texto}`;
  return /[;"\n\r]/.test(texto) ? `"${texto.replaceAll('"', '""')}"` : texto;
};

const COLUNAS_CSV = [
  ["Cliente", (l) => l.cliente.nome],
  ["E-mail", (l) => l.cliente.email],
  ["Telefone", (l) => l.cliente.telefone],
  ["Documento", (l) => l.cliente.documento],
  ["Chave", (l) => l.cliente.chave],
  ["Licença", (l) => (l.cliente.licenca_id ? l.cliente.situacao : "sem licença")],
  ["Tipo", (l) => l.cliente.tipo],
  ["Vence em", (l) => l.cliente.expira_em],
  ["Mensalidade", (l) => l.mensal?.situacao || ""],
  ["Plano", (l) => (l.mensal ? l.mensal.plano_nome || "montado" : "")],
  ["Valor por mês", (l) => (l.mensal ? String(Number(l.mensal.valor || 0).toFixed(2)).replace(".", ",") : "")],
  ["Conexão", (l) => ESTADOS_DE_CONEXAO[l.conexao].texto],
  ["Visto em", (l) => l.visto?.toISOString()],
  ["Computadores", (l) => l.maquinas.length],
  ["Versões", (l) => l.versoes.join(" ")],
  ["Atualização", (l) => ESTADOS_DA_ATUALIZACAO[l.atualizacao].texto],
  ["Módulos", (l) => l.modulos.join(" ")],
  ["Em teste", (l) => l.testando.join(" ")],
  ["Aberturas em 30 dias", (l) => l.aberturas],
  ["Último uso", (l) => l.cliente.ultimo_uso],
  ["Uso", (l) => (l.uso ? ESTADOS_DE_USO[l.uso].texto : "")],
  ["Celulares", (l) => l.celulares],
  ["Compras", (l) => l.compras],
  ["Total comprado", (l) => String(Number(l.cliente.total_comprado || 0).toFixed(2)).replace(".", ",")],
  ["Canal", (l) => CANAIS[l.canal] || l.canal],
  ["Etiquetas", (l) => l.etiquetas.join(" ")],
  ["Próximo contato", (l) => l.proximoContato],
];

/** O Excel brasileiro abre `;` em colunas e só lê acento com o BOM. */
export function csvDosClientes(linhas) {
  const corpo = [
    COLUNAS_CSV.map(([titulo]) => titulo),
    ...linhas.map((linha) => COLUNAS_CSV.map(([, valor]) => valor(linha))),
  ].map((colunas) => colunas.map(celulaCsv).join(";"));
  return `﻿${corpo.join("\r\n")}\r\n`;
}

// ======================================================== etiquetas ========
/** "vip, Revenda ,vip" -> ["vip", "Revenda"]. */
export function lerEtiquetas(texto) {
  const vistas = new Set();
  return String(texto ?? "").split(",").map((t) => t.trim().slice(0, 30)).filter((t) => {
    const chave = normal(t);
    if (!t || vistas.has(chave)) return false;
    vistas.add(chave);
    return true;
  });
}

// ===================================================== a linha do tempo ====
/** Tudo o que aconteceu com o cliente, do mais recente para o mais antigo. */
export function linhaDoTempo({
  cliente = {}, pedidos = [], testes = [], modulos = [], maquinas = [], notas = [], assinatura = [],
  nomeDoModulo = (c) => c,
} = {}) {
  const eventos = [
    { quando: cliente.cliente_desde, tipo: "cadastro", texto: "Virou cliente" },
    ...pedidos.map((p) => ({
      quando: p.atendido_em || p.criado_em,
      tipo: "compra",
      texto: `${p.atendido_em ? "Comprou" : "Fez pedido"}: ${(p.itens || []).map((i) => i.nome || i.codigo).join(" + ") || "pedido"}`,
      valor: p.total,
    })),
    ...modulos.filter((m) => m.liberado_em).map((m) => ({
      quando: m.liberado_em, tipo: "modulo", texto: `Módulo liberado: ${nomeDoModulo(m.codigo)}`,
    })),
    ...testes.map((t) => ({
      quando: t.iniciado_em, tipo: "teste", texto: `Começou a testar ${nomeDoModulo(t.codigo)}`,
    })),
    ...maquinas.flatMap((m) => [
      { quando: m.ativado_em, tipo: "computador", texto: `Ativou o Hub em ${m.apelido || "um computador"}` },
      ...(m.versao && m.versao_desde
        ? [{ quando: m.versao_desde, tipo: "versao", texto: `${m.apelido || "Computador"} está na versão ${m.versao}` }]
        : []),
    ]),
    ...notas.map((n) => ({ quando: n.criado_em, tipo: "nota", texto: n.texto, autor: n.autor })),
    // ja descritos por quem chama (mensalidade.js > descreverEvento)
    ...assinatura.map((e) => ({ quando: e.quando, tipo: "assinatura", texto: e.texto, detalhe: e.detalhe, autor: e.autor })),
  ];
  return eventos
    .filter((e) => e.quando)
    .sort((a, b) => new Date(b.quando) - new Date(a.quando));
}
