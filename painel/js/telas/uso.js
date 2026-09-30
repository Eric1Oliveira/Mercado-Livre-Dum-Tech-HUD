// Uso (quem usa o quê) e Segurança (quem tentou entrar).
//
// O uso chega agregado por dia: "o módulo X foi aberto N vezes naquele dia,
// naquele computador". Não há hora nem sequência — nem aqui, nem no banco.

import { atualizar, ler } from "../api.js";
import { contagem, dataHora, numero, quando } from "../formato.js";
import { ficha } from "./comercial.js";
import { cor, modulo } from "../modulos.js";
import { agir, barra, cartao, el, pessoa, pilula, pilulaModulo, tabela, tile } from "../ui.js";

const JANELA = 30;
const SUMIDO = 14;
const diaLimite = (dias) => new Date(Date.now() - dias * 86400000).toISOString().slice(0, 10);

/**
 * A versao publicada do Hub: o que o cliente ve como "atualize", e quantos
 * computadores ja estao nela. Sem isto, a correcao fica parada no instalador.
 */
function cartaoVersao(atual, ativacoes) {
  const publicada = String(atual?.versao || "");
  const instaladas = ativacoes.map((a) => String(a.versao || "")).filter(Boolean);
  const naVersao = publicada ? instaladas.filter((v) => v === publicada).length : 0;
  const atrasados = instaladas.length - naVersao;

  const versao = campoSimples("Versao publicada", publicada, "1.2.0");
  const url = campoSimples("Endereco para baixar", String(atual?.url || ""),
                           "https://dumtechsolution.com/baixar/");
  const notas = campoSimples("Recado (aparece no Hub)", String(atual?.notas || ""),
                             "O que mudou nesta versao");
  // a impressao digital do instalador: build\build.ps1 imprime no fim.
  // Sem ela, o Hub NAO instala sozinho - so manda para a pagina de download.
  const sha = campoSimples("SHA-256 do instalador", String(atual?.sha256 || ""),
                           "64 caracteres - o build imprime");
  const tamanho = campoSimples("Tamanho em bytes", String(atual?.tamanho || ""), "29781768");
  const obrigatoria = el("input", { type: "checkbox" });
  obrigatoria.checked = Boolean(atual?.obrigatoria);
  const automatica = el("input", { type: "checkbox" });
  automatica.checked = atual ? Boolean(atual.automatica) : true;

  const salvar = el("button", { classe: "botao botao-primario", texto: "Publicar versao" });
  salvar.addEventListener("click", () => agir(salvar, async () => {
    const numero = versao.valor().trim();
    if (numero && !/^[0-9]+(\.[0-9]+){0,3}$/.test(numero)) {
      throw new Error("A versao e so numero e ponto: 1.2.0");
    }
    const impressao = sha.valor().trim().toLowerCase();
    if (impressao && !/^[0-9a-f]{64}$/.test(impressao)) {
      throw new Error("O SHA-256 tem 64 caracteres (0-9 e a-f).");
    }
    if (automatica.checked && !impressao) {
      throw new Error("Para atualizar pelo Hub, informe o SHA-256 do instalador.");
    }
    await atualizar("hub_versoes", { id: "eq.1" }, {
      versao: numero, url: url.valor().trim(), notas: notas.valor().trim(),
      sha256: impressao, tamanho: Number(tamanho.valor().trim() || 0) || 0,
      obrigatoria: obrigatoria.checked, automatica: automatica.checked,
      atualizado_em: new Date().toISOString(),
    });
  }, { feito: "Versao publicada. O botao aparece no Hub do cliente em ate 2 minutos (Hub 1.2.2 ou anterior: quando o programa for aberto de novo).",
       erro: "Nao foi possivel publicar." }));

  return cartao("Versao do DumTech Hub", el("div", { classe: "form-versao" }, [
    el("p", { classe: "explica-versao", texto: publicada
      ? `${naVersao} computador(es) ja estao na ${publicada}` +
        (atrasados > 0 ? ` · ${atrasados} ainda em versao antiga` : "")
      : "Nenhuma versao publicada: os clientes nao recebem aviso de atualizacao." }),
    versao.no, url.no, notas.no, sha.no, tamanho.no,
    el("label", { classe: "campo-linha" }, [
      automatica,
      el("span", { texto: "Deixar o cliente atualizar pelo proprio Hub (um clique)" }),
    ]),
    el("label", { classe: "campo-linha" }, [
      obrigatoria,
      el("span", { texto: "Atualizacao importante (o aviso nao pode ser dispensado)" }),
    ]),
    el("div", { classe: "acoes-cartao" }, [salvar]),
  ]));
}

function campoSimples(rotulo, valor, dica = "") {
  const entrada = el("input", { value: valor, placeholder: dica });
  return {
    no: el("label", { classe: "campo" }, [el("span", { texto: rotulo }), entrada]),
    entrada,
    valor: () => String(entrada.value ?? ""),
  };
}

// ==================================================================== uso ====
export async function uso(alvo) {
  const [modulos, clientes, linhas] = await Promise.all([
    ler("painel_modulos", { ordem: "aberturas_30d.desc" }),
    ler("painel_clientes", { ordem: "aberturas_30d.desc" }),
    ler("uso_diario", { filtros: { dia: `gte.${diaLimite(JANELA)}` } }),
  ]);

  const totalAberturas = linhas.reduce((soma, l) => soma + Number(l.aberturas || 0), 0);
  const comUso = clientes.filter((c) => Number(c.aberturas_30d) > 0);
  const licenciados = clientes.filter((c) => c.chave && c.situacao === "ativa");
  const sumidos = licenciados.filter(
    (c) => !c.ultimo_uso || c.ultimo_uso < diaLimite(SUMIDO)
  );

  alvo.append(
    el("div", { classe: "pagina-cabeca" }, [
      el("div", {}, [
        el("h1", { texto: "Uso" }),
        el("p", { texto: `Aberturas de módulo nos últimos ${JANELA} dias, enviadas pelo Hub.` }),
      ]),
    ]),
    el("div", { classe: "tiles" }, [
      tile("Aberturas", numero(totalAberturas), `últimos ${JANELA} dias`),
      tile("Clientes ativos", numero(comUso.length), `de ${numero(licenciados.length)} com licença`),
      tile("Sem abrir", numero(sumidos.length), `há mais de ${SUMIDO} dias`,
        sumidos.length ? "ruim" : "ok"),
      tile("Módulo mais usado",
        modulos[0] && Number(modulos[0].aberturas_30d) ? modulo(modulos[0].codigo).nome : "—",
        modulos[0] ? `${numero(modulos[0].aberturas_30d)} aberturas` : ""),
    ])
  );

  const teto = Math.max(1, ...modulos.map((m) => Number(m.aberturas_30d)));
  alvo.append(cartao("Por módulo", tabela(
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
  )));

  alvo.append(cartao("Quem mais usa", tabela(
    ["Cliente", "Módulos", { texto: "Aberturas", numero: true }, "Último uso"],
    comUso.slice(0, 20),
    (c) => [
      pessoa(c.nome, c.email),
      el("div", { classe: "modulos-lista" },
        (c.produtos_codigos || []).map((codigo) => pilulaModulo(codigo))),
      numero(c.aberturas_30d),
      quando(c.ultimo_uso),
    ],
    { aoClicar: (c) => ficha(c), vazioTexto: "Nenhum uso recebido ainda." }
  )));

  alvo.append(cartao(`Sumiram (sem abrir há mais de ${SUMIDO} dias)`, tabela(
    ["Cliente", "Módulos", "Último uso", "Última checagem"],
    sumidos.slice(0, 20),
    (c) => [
      pessoa(c.nome, c.email),
      el("div", { classe: "modulos-lista" },
        (c.produtos_codigos || []).map((codigo) => pilulaModulo(codigo))),
      quando(c.ultimo_uso),
      quando(c.ultima_checagem),
    ],
    { aoClicar: (c) => ficha(c), vazioTexto: "Ninguém sumiu. Bom sinal." }
  )));
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

  if (versoes) alvo.append(cartaoVersao(versoes[0], ativacoes));

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

  alvo.append(cartao("Computadores ativados", tabela(
    ["Cliente", "Apelido", "Computador", "Última checagem"],
    ativacoes,
    (a) => {
      const dono = porLicenca.get(a.licenca_id);
      return [
        dono ? pessoa(dono.nome, dono.email) : "—",
        a.apelido || "—",
        el("code", { texto: a.maquina }),
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
  return curto(linha.nome || linha.titulo || linha.codigo || linha.chave || linha.maquina || linha.email || a.registro);
}

const motivo = (erro) => ({
  nao_encontrada: "Chave não existe",
  inativa: "Licença suspensa ou cancelada",
  expirada: "Licença vencida",
  limite_maquinas: "Limite de computadores",
  dados_incompletos: "Dados incompletos",
}[erro] || erro || "—");
