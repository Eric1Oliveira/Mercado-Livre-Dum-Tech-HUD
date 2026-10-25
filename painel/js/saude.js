// A saúde de cada cliente: as regras de Uso, Testes grátis e Celulares que não
// dependem de tela (testadas em tests/saude.test.mjs).
//
// Tudo recebe o "agora" de quem chama: a tela passa o relógio, o teste passa
// uma data fixa. Os dias são "AAAA-MM-DD" no fuso de quem olha - o mesmo dia
// que o Hub anota no computador do cliente.

export const DIA = 86400000;

// O painel publicado antes da migration nao quebra: a ficha abre sem os cartoes
// novos e as telas novas dizem o que falta (como a auditoria ja faz).
export const FALTA_MIGRATION = "Aplique no Supabase a migration 20261019120000_painel_uso_testes_celular.sql " +
  "e recarregue a página.";

const doisDigitos = (n) => String(n).padStart(2, "0");

/** O dia (AAAA-MM-DD) de um momento, no fuso local. */
export function diaLocal(momento = new Date()) {
  const d = new Date(momento);
  return `${d.getFullYear()}-${doisDigitos(d.getMonth() + 1)}-${doisDigitos(d.getDate())}`;
}

/** Os últimos `n` dias, do mais antigo até hoje. */
export function ultimosDias(n, hoje = new Date()) {
  const base = new Date(hoje);
  return Array.from({ length: n }, (_, i) =>
    diaLocal(new Date(base.getFullYear(), base.getMonth(), base.getDate() - (n - 1 - i), 12)));
}

/** Quantos dias de `a` até `b` (dois "AAAA-MM-DD"). */
export function diasEntre(a, b) {
  const meioDia = (dia) => {
    const [ano, mes, d] = String(dia).slice(0, 10).split("-").map(Number);
    return new Date(ano, mes - 1, d, 12).getTime();
  };
  return Math.round((meioDia(b) - meioDia(a)) / DIA);
}

/** [{dia, valor}] dos últimos `n` dias, com zero onde não houve uso. */
export function serieDiaria(linhas, n, hoje = new Date(), campo = "aberturas") {
  const soma = new Map();
  for (const linha of linhas || []) {
    const dia = String(linha.dia).slice(0, 10);
    soma.set(dia, (soma.get(dia) || 0) + Number(linha[campo] || 0));
  }
  return ultimosDias(n, hoje).map((dia) => ({ dia, valor: soma.get(dia) || 0 }));
}

/** O dia `n` dias depois (ou antes, com n negativo) de um "AAAA-MM-DD". */
export function deslocar(dia, n) {
  const [ano, mes, d] = String(dia).slice(0, 10).split("-").map(Number);
  return diaLocal(new Date(ano, mes - 1, d + n, 12));
}

/**
 * A faixa que o banco manda (painel_uso_por_cliente: os valores dos 30 dias até
 * `ate`) nos dias de quem olha: dia que não veio, zero.
 */
export function serieDaFaixa(linha, n = 30, hoje = new Date()) {
  const valores = new Map();
  const lista = linha?.ultimos_30 || [];
  if (linha?.ate) {
    lista.forEach((valor, i) => valores.set(deslocar(linha.ate, i - (lista.length - 1)), Number(valor || 0)));
  }
  return ultimosDias(n, hoje).map((dia) => ({ dia, valor: valores.get(dia) || 0 }));
}

/** Intensidade da faixa: 0 (nada) a 4, na mesma régua para todo mundo. */
export function nivel(valor, teto) {
  if (!(valor > 0) || !(teto > 0)) return 0;
  return Math.min(4, Math.max(1, Math.ceil((valor / teto) * 4)));
}

/** +12 / -30 (por cento) contra o período anterior; sem base, null. */
export function variacao(atual, anterior) {
  if (!anterior) return null;
  return Math.round(((Number(atual) - Number(anterior)) / Number(anterior)) * 100);
}

// ================================================================== uso ====
// A ordem é a de atenção: quem precisa de você primeiro.
export const ESTADOS_DE_USO = {
  sumiu:      { texto: "Sumiu", tom: "ruim", ordem: 0 },
  nunca:      { texto: "Nunca abriu", tom: "ruim", ordem: 1 },
  sem_ativar: { texto: "Não instalou", tom: "aviso", ordem: 2 },
  esfriando:  { texto: "Esfriando", tom: "aviso", ordem: 3 },
  comecando:  { texto: "Começando", tom: "neutro", ordem: 4 },
  usando:     { texto: "Usando", tom: "ok", ordem: 5 },
};
export const ESFRIA = 7;
export const SOME = 14;

/**
 * Como anda o uso de um cliente com licença ativa.
 *   ultimoUso  último dia com módulo aberto (AAAA-MM-DD) ou vazio
 *   ativadoEm  a primeira ativação do Hub (vazio = nunca instalou)
 */
export function estadoDeUso({ ultimoUso = null, ativadoEm = null } = {}, hoje = new Date()) {
  if (!ultimoUso) {
    if (!ativadoEm) return "sem_ativar";
    return new Date(hoje) - new Date(ativadoEm) < 2 * DIA ? "comecando" : "nunca";
  }
  const dias = diasEntre(ultimoUso, diaLocal(hoje));
  if (dias <= ESFRIA) return "usando";
  if (dias <= SOME) return "esfriando";
  return "sumiu";
}

// ================================================================== Hub ====
/** Quando o Hub deste computador falou com o servidor pela última vez. */
export function vistoEm(ativacao) {
  const tempos = [ativacao?.ultima_checagem, ativacao?.versao_em]
    .filter(Boolean)
    .map((t) => new Date(t).getTime())
    .filter(Number.isFinite);
  return tempos.length ? new Date(Math.max(...tempos)) : null;
}

// O Hub pergunta a versão a cada 2 minutos, mas o banco só anota de hora em
// hora (migration 20260917140000): "aberto" é ter falado na última hora e pouco.
export const ABERTO_MS = 75 * 60000;
export function hubAberto(ativacao, agora = new Date()) {
  const visto = vistoEm(ativacao);
  return Boolean(visto && new Date(agora) - visto <= ABERTO_MS);
}

/** 1.4.10 > 1.4.9 (compara número a número, não texto). */
export function compararVersoes(a, b) {
  const partes = (v) => String(v || "").split(".").map((p) => Number.parseInt(p, 10) || 0);
  const [x, y] = [partes(a), partes(b)];
  for (let i = 0; i < Math.max(x.length, y.length); i += 1) {
    const diferenca = (x[i] || 0) - (y[i] || 0);
    if (diferenca) return Math.sign(diferenca);
  }
  return 0;
}

/** true/false: está na versão publicada (ou acima)? null: não dá para saber. */
export function versaoEmDia(instalada, publicada) {
  if (!instalada || !publicada) return null;
  return compararVersoes(instalada, publicada) >= 0;
}

/**
 * Uma linha por cliente com licença ativa: o estado de uso, a faixa de 30
 * dias, os computadores (versão e se o Hub está aberto) e os celulares.
 * Ordenada por atenção; no mesmo estado, quem usa mais vem antes.
 */
export function saudeDosClientes({
  clientes = [], faixas = [], ativacoes = [], aparelhos = [], publicada = "", dias = 30,
} = {}, agora = new Date()) {
  const faixaDe = new Map(faixas.map((f) => [f.cliente_id, f]));
  const maquinasDe = agrupar(ativacoes, "licenca_id");
  const celularesDe = agrupar(aparelhos.filter((a) => !a.revogado_em), "licenca_id");

  return clientes
    .filter((c) => c.licenca_id && c.situacao === "ativa")
    .map((cliente) => {
      const maquinas = maquinasDe.get(cliente.licenca_id) || [];
      const ativadoEm = maquinas.map((m) => m.ativado_em).filter(Boolean).sort()[0] || null;
      const serie = serieDaFaixa(faixaDe.get(cliente.cliente_id), dias, agora);
      const estado = estadoDeUso({ ultimoUso: cliente.ultimo_uso, ativadoEm }, agora);
      return {
        cliente,
        estado,
        serie,
        aberturas: serie.reduce((soma, d) => soma + d.valor, 0),
        diasComUso: serie.filter((d) => d.valor > 0).length,
        computadores: maquinas.map((m) => ({
          apelido: m.apelido || "Computador",
          versao: m.versao || "",
          emDia: versaoEmDia(m.versao, publicada),
          aberto: hubAberto(m, agora),
          visto: vistoEm(m),
        })),
        celulares: (celularesDe.get(cliente.licenca_id) || []).length,
      };
    })
    .sort((a, b) => ESTADOS_DE_USO[a.estado].ordem - ESTADOS_DE_USO[b.estado].ordem
      || b.aberturas - a.aberturas
      || String(a.cliente.nome || "").localeCompare(String(b.cliente.nome || ""), "pt-BR"));
}

/**
 * Módulo pago que não abre: licença ativa, comprado há pelo menos uma semana
 * (quem comprou ontem ainda está instalando) e nenhuma abertura em 30 dias.
 */
export function modulosParados(modulos = [], agora = new Date()) {
  return modulos
    .filter((m) => m.situacao === "ativa" && !Number(m.aberturas_30d)
      && (!m.liberado_em || new Date(agora) - new Date(m.liberado_em) >= 7 * DIA))
    .sort((a, b) => String(a.ultimo_uso || "").localeCompare(String(b.ultimo_uso || ""))
      || String(a.liberado_em || "").localeCompare(String(b.liberado_em || "")));
}

// =============================================================== testes ====
export const ESTADOS_DO_TESTE = {
  acabando: { texto: "Termina logo", tom: "aviso", ordem: 0 },
  rodando:  { texto: "Testando", tom: "marca", ordem: 1 },
  terminou: { texto: "Terminou", tom: "neutro", ordem: 2 },
  comprou:  { texto: "Comprou", tom: "ok", ordem: 3 },
};
export const DIAS_DE_TESTE = 7;

export function estadoDoTeste(teste, agora = new Date()) {
  if (teste?.comprou) return "comprou";
  const restam = new Date(teste?.termina_em) - new Date(agora);
  if (!(restam > 0)) return "terminou";
  return restam <= 2 * DIA ? "acabando" : "rodando";
}

/** Quanto do teste já passou (0 a 1) - a barrinha do período. */
export function andamentoDoTeste(teste, agora = new Date()) {
  const inicio = new Date(teste?.iniciado_em).getTime();
  const fim = new Date(teste?.termina_em).getTime();
  if (!(fim > inicio)) return 1;
  return Math.min(1, Math.max(0, (new Date(agora).getTime() - inicio) / (fim - inicio)));
}

/** "termina hoje", "termina em 3 dias", "terminou há 2 dias". */
export function prazoDoTeste(teste, agora = new Date()) {
  const dias = diasEntre(diaLocal(agora), diaLocal(teste?.termina_em));
  if (new Date(teste?.termina_em) > new Date(agora)) {
    if (dias <= 0) return "termina hoje";
    return dias === 1 ? "termina amanhã" : `termina em ${dias} dias`;
  }
  if (dias === 0) return "terminou hoje";
  return dias === -1 ? "terminou ontem" : `terminou há ${Math.abs(dias)} dias`;
}

/** O fim novo ao estender: a partir do fim atual, ou de agora se já acabou. */
export function fimEstendido(terminaEm, dias = DIAS_DE_TESTE, agora = new Date()) {
  const base = Math.max(new Date(terminaEm).getTime() || 0, new Date(agora).getTime());
  return new Date(base + dias * DIA).toISOString();
}

/** Os números da tela de testes. Conversão = compraram / (compraram + terminaram). */
export function resumoDosTestes(testes = [], agora = new Date()) {
  const conta = { rodando: 0, acabando: 0, terminou: 0, comprou: 0 };
  for (const t of testes) conta[estadoDoTeste(t, agora)] += 1;
  const decididos = conta.comprou + conta.terminou;
  return {
    ...conta,
    testando: conta.rodando + conta.acabando,
    usaram: testes.filter((t) => Number(t.aberturas) > 0).length,
    total: testes.length,
    conversao: decididos ? Math.round((conta.comprou / decididos) * 100) : null,
  };
}

/** Ordem da tela: o que termina primeiro em cima; depois o que acabou há pouco. */
export function ordenarTestes(testes = [], agora = new Date()) {
  const peso = (t) => ESTADOS_DO_TESTE[estadoDoTeste(t, agora)].ordem;
  return [...testes].sort((a, b) => peso(a) - peso(b)
    || (peso(a) <= 1
      ? new Date(a.termina_em) - new Date(b.termina_em)
      : new Date(b.termina_em) - new Date(a.termina_em)));
}

// ============================================================= celulares ===
export const ESTADOS_DO_CELULAR = {
  ativo:        { texto: "Em uso", tom: "ok" },
  parado:       { texto: "Parado", tom: "aviso" },
  nunca:        { texto: "Nunca abriu", tom: "neutro" },
  desconectado: { texto: "Desconectado", tom: "neutro" },
};

export function estadoDoCelular(aparelho, agora = new Date()) {
  if (aparelho?.revogado_em) return "desconectado";
  if (!aparelho?.ultimo_acesso) return "nunca";
  return new Date(agora) - new Date(aparelho.ultimo_acesso) <= 7 * DIA ? "ativo" : "parado";
}

// O Hub publica o resumo enquanto está aberto: loja fechada no domingo deixa o
// resumo de sábado, e isso é normal. Dois dias sem publicar já não é.
export const RESUMO_VELHO_MS = 48 * 3600000;

/** O resumo mais novo de cada licença (o celular mostra todos os computadores). */
export function resumoMaisNovo(espelhos = []) {
  const porLicenca = new Map();
  for (const e of espelhos) {
    const atual = porLicenca.get(e.licenca_id);
    if (!atual || new Date(e.atualizado_em) > new Date(atual)) porLicenca.set(e.licenca_id, e.atualizado_em);
  }
  return porLicenca;
}

export function resumoVelho(atualizadoEm, agora = new Date()) {
  if (!atualizadoEm) return true;
  return new Date(agora) - new Date(atualizadoEm) > RESUMO_VELHO_MS;
}

// ========================================================= loja pelo Hub ===
/** Clicou em "Comprar" no Hub e fez pedido depois (mesmo cliente ou e-mail)? */
export function virouPedido(clique, pedidos = []) {
  const quando = new Date(clique?.criado_em).getTime() - 60000;
  const email = String(clique?.email || "").trim().toLowerCase();
  return pedidos.some((p) => {
    const mesmo = (clique?.cliente_id && p.cliente_id === clique.cliente_id)
      || (email && String(p.email || "").trim().toLowerCase() === email);
    return mesmo && new Date(p.criado_em).getTime() >= quando;
  });
}

function agrupar(linhas, campo) {
  const grupos = new Map();
  for (const linha of linhas || []) {
    const chave = linha?.[campo];
    if (!grupos.has(chave)) grupos.set(chave, []);
    grupos.get(chave).push(linha);
  }
  return grupos;
}
