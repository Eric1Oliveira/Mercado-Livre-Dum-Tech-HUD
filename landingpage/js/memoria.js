// Quem chegou aqui uma vez pelo Hub nao precisa se apresentar de novo.
//
// O token da URL vale 15 minutos e e de uso unico - ele serve para a PRIMEIRA
// visita. Depois disso, guardamos no navegador o basico (nome, e-mail e o que a
// pessoa ja tem) para que abrir o site direto no dia seguinte continue sendo
// "Olá, Joao" em vez de um formulario em branco.
//
// Limite honesto: isto vale por navegador. Em outro computador, ou apagando os
// dados do site, a pessoa volta a ser visitante - e por isso existe o botao
// "Não é você?".
//
// Modulo puro: o armazem entra por parametro, entao da para testar sem
// navegador (tests/memoria.test.mjs).

export const CHAVE = "dumtech.cliente";

/** Depois disso, e melhor perguntar de novo do que chutar quem e a pessoa. */
export const VALIDADE_DIAS = 90;

/** O tipo da licenca so vale se for um dos tres: o resto e texto de estranho. */
const TIPOS = new Set(["vitalicia", "assinatura", "teste"]);
const tipoValido = (tipo) => (TIPOS.has(String(tipo || "")) ? String(tipo) : "");

export function lembrar(armazem, cliente) {
  if (!armazem || !cliente?.email) return null;
  const guardado = {
    nome: String(cliente.nome || "").slice(0, 120),
    email: String(cliente.email || "").slice(0, 160).toLowerCase(),
    produtos: [...new Set((cliente.produtos || []).map((c) => String(c).toUpperCase()))],
    // vitalicio, assinante ou teste: decide o que a pagina oferece
    tipo: tipoValido(cliente.tipo),
    quando: new Date().toISOString(),
  };
  try {
    armazem.setItem(CHAVE, JSON.stringify(guardado));
  } catch {
    return guardado; // navegador anonimo ou armazenamento cheio: segue sem gravar
  }
  return guardado;
}

/** O que foi lembrado, ou null (sem nada, vencido, ou ilegivel). */
export function lembrado(armazem, agora = new Date()) {
  let bruto = null;
  try {
    bruto = armazem?.getItem(CHAVE) ?? null;
  } catch {
    return null;
  }
  if (!bruto) return null;

  let dados;
  try {
    dados = JSON.parse(bruto);
  } catch {
    esquecer(armazem);
    return null;
  }
  if (!dados?.email) {
    esquecer(armazem);
    return null;
  }

  const quando = new Date(dados.quando ?? 0);
  const dias = (agora - quando) / 86400000;
  if (!Number.isFinite(dias) || dias > VALIDADE_DIAS) {
    esquecer(armazem);
    return null;
  }

  return {
    nome: String(dados.nome || ""),
    email: String(dados.email || ""),
    produtos: Array.isArray(dados.produtos)
      ? dados.produtos.map((c) => String(c).toUpperCase())
      : [],
    tipo: tipoValido(dados.tipo),
    quando: dados.quando,
    doNavegador: true,
  };
}

export function esquecer(armazem) {
  try {
    armazem?.removeItem(CHAVE);
  } catch {
    /* nada a fazer: o navegador nao deixa gravar nem apagar */
  }
}

// ------------------------------------------------------ o ultimo catalogo --
// A pagina pinta antes da rede responder. Com o catalogo do servidor guardado
// da visita anterior, ela ja nasce com o preco de verdade (e nao com o preco
// de exemplo do arquivo, que depois "pula" quando o servidor responde).

export const CHAVE_CATALOGO = "dumtech.catalogo";
export const VALIDADE_CATALOGO_DIAS = 7;

export function lembrarCatalogo(armazem, catalogo, agora = new Date()) {
  if (!armazem || !catalogo || catalogo.local || !Array.isArray(catalogo.produtos)) return;
  try {
    armazem.setItem(CHAVE_CATALOGO, JSON.stringify({
      produtos: catalogo.produtos,
      combos: catalogo.combos ?? [],
      quando: agora.toISOString(),
    }));
  } catch {
    /* sem espaco ou sem permissao: na proxima visita pinta com o local */
  }
}

/** O catalogo guardado, ou null (nada, vencido, ou com cara de lixo). */
export function catalogoLembrado(armazem, agora = new Date()) {
  let dados;
  try {
    dados = JSON.parse(armazem?.getItem(CHAVE_CATALOGO) ?? "null");
  } catch {
    return null;
  }
  const dias = (agora - new Date(dados?.quando ?? 0)) / 86400000;
  const produtosOk = Array.isArray(dados?.produtos) && dados.produtos.length > 0 &&
    dados.produtos.every((p) => typeof p?.codigo === "string" && Number.isFinite(Number(p.preco)));
  if (!produtosOk || !Number.isFinite(dias) || dias > VALIDADE_CATALOGO_DIAS) return null;

  return {
    produtos: dados.produtos.map((p) => ({ ...p, preco: Number(p.preco) })),
    combos: (Array.isArray(dados.combos) ? dados.combos : [])
      .filter((c) => typeof c?.codigo === "string" && Array.isArray(c.produtos))
      .map((c) => ({ ...c, preco: Number(c.preco) })),
    local: false,
    guardado: true,
  };
}
