// Busca do Passo a passo: acha o video pela pergunta escrita do jeito da pessoa.
//
// Roda inteira no navegador (nada vai ao servidor, nada toca o banco). "como cadastro produtos",
// "cadastrar produto", "Cadastro de produtos" e "cadstro produto" chegam no mesmo video porque:
//   - acento, maiuscula e pontuacao somem;
//   - palavras vazias ("como", "eu", "o", "de"...) nao contam;
//   - cada palavra vira um radical (cadastro/cadastrar/cadastrando -> "cadastr");
//   - radical que comeca igual vale quase tanto quanto igual; uma letra trocada tambem vale.
// Funcoes puras: os testes rodam no Node (tests/passo-a-passo.test.mjs).

const VAZIAS = new Set(("como eu faco fazer faz o a os as um uma uns umas de do da dos das no na nos nas em para pra pro " +
  "com que e meu minha meus minhas se sobre onde qual quais quero queria posso consigo tem ter ao aos vou " +
  "esta estou isso esse essa la aqui ja nao mais muito so pelo pela por sistema programa hub dumtech").split(" "));

// palavras diferentes que querem dizer a mesma coisa (todas viram a primeira)
const SINONIMOS = [
  ["produt", "mercador", "item", "itens", "artig"],
  ["cadastr", "registr", "adicion", "inclu", "cri", "nov", "inser"],
  ["vend", "pdv", "balca", "cobr"],
  ["client", "fregue", "comprador"],
  ["orcament", "propost", "cotaca"],
  ["ordem", "os", "consert", "assistenc", "reparo"],
  ["agend", "compromiss", "horari"],
  ["devoluca", "devolv", "estorn", "reembols"],
  ["contag", "inventari", "balanc"],
  ["backup", "copi", "seguranc"],
  ["celular", "smartphon", "aplicativ", "app"],
  ["despes", "boleto", "conta"],
  ["procur", "pesquis", "busc", "ach", "encontr", "localiz"],
];

const SUFIXOS = ["amentos", "amento", "imentos", "imento", "acoes", "acao", "icoes", "icao", "ando", "endo", "indo",
  "ados", "adas", "idos", "idas", "ado", "ada", "ido", "ida", "aria", "arias", "ar", "er", "ir", "as", "os", "es", "a", "o", "e", "s"];

export function normalizar(texto) {
  return String(texto ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9+ ]+/g, " ").replace(/\s+/g, " ").trim();
}

export function radical(palavra) {
  let p = palavra;
  for (const s of SUFIXOS) {
    if (p.length - s.length >= 4 && p.endsWith(s)) { p = p.slice(0, -s.length); break; }
  }
  for (const grupo of SINONIMOS) if (grupo.some(g => p.startsWith(g))) return grupo[0];
  return p;
}

export function radicais(texto) {
  // "OS" maiusculo e ordem de servico (o "os" minusculo e artigo e nao conta)
  const comOrdem = String(texto ?? "").replace(/(^|[^A-Za-z])O\.?S\.?(?![A-Za-z])/g, "$1 ordem ");
  return normalizar(comOrdem).split(" ").filter(p => p && !VAZIAS.has(p)).map(radical);
}

// distancia de edicao com teto 1 (so interessa "igual ou uma letra de diferenca")
function quaseIgual(a, b) {
  if (Math.abs(a.length - b.length) > 1 || Math.min(a.length, b.length) < 5) return false;
  let i = 0, j = 0, erros = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; continue; }
    if (++erros > 1) return false;
    if (a.length > b.length) i++; else if (b.length > a.length) j++; else { i++; j++; }
  }
  return erros + (a.length - i) + (b.length - j) <= 1;
}

function parecido(q, d) {
  if (q === d) return 1;
  if (q.length >= 4 && d.length >= 4 && (d.startsWith(q) || q.startsWith(d))) return 0.85;
  if (quaseIgual(q, d)) return 0.75;
  return 0;
}

// o indice de cada video: radicais de cada campo, com o peso do campo
export function indexar(video) {
  const campos = [
    [video.titulo, 3], [(video.perguntas || []).join(" "), 2.6], [(video.palavras || []).join(" "), 2],
    [video.grupo, 1.2], [video.resumo, 1], [(video.passos || []).map(p => p.texto).join(" "), 0.6],
  ];
  return {
    video,
    termos: campos.map(([texto, peso]) => ({ radicais: [...new Set(radicais(texto))], peso })),
    frases: (video.perguntas || []).map(p => radicais(p).join(" ")),
  };
}

export function pontuar(indice, consulta) {
  const qs = [...new Set(radicais(consulta))];
  if (!qs.length) return { pontos: 0, cobertura: 0 };
  let pontos = 0, achados = 0;
  for (const q of qs) {
    let melhor = 0;
    for (const campo of indice.termos) for (const d of campo.radicais) melhor = Math.max(melhor, parecido(q, d) * campo.peso);
    if (melhor > 0) achados++;
    pontos += melhor;
  }
  const frase = qs.join(" ");
  if (indice.frases.some(f => f === frase)) pontos += 4;                  // a pergunta exata que alguem faria
  else if (indice.frases.some(f => frase.length > 3 && f.includes(frase))) pontos += 1.5;
  const cobertura = achados / qs.length;
  return { pontos: pontos * (0.4 + 0.6 * cobertura) / Math.sqrt(qs.length), cobertura };
}

// lista ordenada; `exato` diz se o primeiro e a resposta (cobre a pergunta toda e se destaca)
export function buscar(indices, consulta) {
  const resultados = indices.map(i => ({ video: i.video, ...pontuar(i, consulta) }))
    .filter(r => r.pontos > 0.9 && r.cobertura >= 0.5)
    .sort((a, b) => b.pontos - a.pontos);
  const [primeiro, segundo] = resultados;
  const exato = !!primeiro && primeiro.cobertura === 1 && (!segundo || primeiro.pontos >= segundo.pontos * 1.12);
  return { resultados, exato };
}
