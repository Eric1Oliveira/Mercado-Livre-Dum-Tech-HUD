// As promocoes, em duas abas de telas diferentes:
//
//   faixa   (Site > Faixa de aviso) um recado no topo do site, com datas; liga
//           e desliga sozinha. Vale a mais nova que estiver no ar. Vitalicio nao ve.
//   cupom   (Planos > Cupons) um codigo que libera um plano (normalmente "so por
//           cupom") com preco e link proprios. Vem no link do parceiro: ?cupom=CODIGO
//
// O de/por e editado no proprio plano (Planos > Planos e precos).

import { apagar, atualizar, inserir, ler } from "../api.js";
import { CONFIG } from "../config.js";
import { data, dinheiro, numero } from "../formato.js";
import { linkDoCupom, problemaDoAviso, problemaDoCupom, situacaoDoAviso } from "../mensalidade.js";
import { abrirGaveta, fecharGaveta, recarregar } from "../painel.js";
import { agir, cartao, confirmar, el, pilula, recado, tabela, vazio } from "../ui.js";

const FALTA_MIGRATION =
  "Rode a migration 20261104120000_controle_mensalidade.sql no Supabase (npx supabase db push) para ver esta tela.";
const LOJA = CONFIG.LOJA_URL || "https://dumtechsolution.com";
const hoje = () => new Date().toISOString().slice(0, 10);
const SITUACAO_DO_AVISO = {
  no_ar: ["No ar", "ok"], programado: ["Programado", "marca"], encerrado: ["Encerrado", "neutro"], desligado: ["Desligado", "neutro"],
};
const TONS = [["violeta", "Violeta (o da marca)"], ["verde", "Verde"], ["ambar", "Âmbar (atenção)"]];

const semBanco = (alvo, cabeca, titulo) =>
  alvo.append(cabeca, cartao("", vazio(titulo, FALTA_MIGRATION)));

/** Site > Faixa de aviso: o recado no topo do site, com datas. */
export async function faixas(alvo) {
  const avisos = await ler("landing_avisos", { ordem: "criado_em.desc" }).catch(() => null);
  const cabeca = el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Faixa de aviso" }),
      el("p", { texto: "Um recado no topo do site, nas datas que você escolher: liga e desliga sozinho. " +
                       "Vale a mais nova que estiver no ar. Cliente vitalício não vê." }),
    ]),
    el("div", { classe: "ferramentas" }, [
      el("button", { classe: "botao botao-primario", texto: "Nova faixa", onclick: () => editarAviso(null) }),
    ]),
  ]);
  if (!avisos) return semBanco(alvo, cabeca, "O banco ainda não tem a faixa de aviso");

  alvo.append(cabeca, cartao("", tabela(
    ["Texto", "Período", "Situação", ""],
    avisos,
    (a) => {
      const [texto, tom] = SITUACAO_DO_AVISO[situacaoDoAviso(a, hoje())];
      return [
        el("div", {}, [el("strong", { texto: a.texto }),
                       a.link ? el("div", { classe: "sub-linha", texto: `leva a ${a.link}` }) : null]),
        `${data(a.inicio)} a ${a.fim ? data(a.fim) : "sem fim"}`,
        pilula(texto, tom),
        el("button", { type: "button", classe: "botao botao-fantasma botao-mini", texto: "Editar",
                       onclick: (e) => { e.stopPropagation(); editarAviso(a); } }),
      ];
    },
    { aoClicar: (a) => editarAviso(a),
      vazioTexto: "Nenhuma faixa ainda. Ela aparece no topo do site, para quem não é vitalício, nas datas que você escolher." },
  )));
}

/** Planos > Cupons: o código do parceiro que libera um plano com preço próprio. */
export async function cupons(alvo) {
  const [lista, planos] = await Promise.all([
    ler("painel_cupons", { ordem: "criado_em.desc" }).catch(() => null),
    ler("mensalidade_planos", { ordem: "ordem.asc" }).catch(() => []),
  ]);
  const cabeca = el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Cupons" }),
      el("p", { texto: "Um código que libera um plano com preço e link próprios, normalmente um plano \"só por cupom\". " +
                       "Vai no link do parceiro (?cupom=CODIGO) e se aplica sozinho. Lembrete: a InfinitePay cobra o valor " +
                       "do link, então o desconto precisa de um link com o valor promocional." }),
    ]),
    el("div", { classe: "ferramentas" }, [
      el("button", { classe: "botao botao-primario", texto: "Novo cupom", onclick: () => editarCupom(null, planos) }),
    ]),
  ]);
  if (!lista) return semBanco(alvo, cabeca, "O banco ainda não tem os cupons");

  alvo.append(cabeca, cartao("", tabela(
    ["Cupom", "Libera o plano", "Usos", { texto: "Assinaturas", numero: true }, "Situação", ""],
    lista,
    (c) => [
      el("div", {}, [el("strong", { texto: c.codigo }),
                     el("div", { classe: "sub-linha", texto: [c.parceiro && `parceiro: ${c.parceiro}`, c.descricao].filter(Boolean).join(" · ") })]),
      el("div", {}, [c.plano_nome, el("div", { classe: "sub-linha", texto: `${dinheiro(c.plano_preco)} por mês${c.plano_visivel ? "" : " · só por cupom"}` })]),
      c.usos_max ? `${numero(c.pedidos)} de ${numero(c.usos_max)}` : numero(c.pedidos),
      numero(c.assinaturas),
      situacaoDoCupom(c),
      el("button", { type: "button", classe: "botao botao-fantasma botao-mini", texto: "Editar",
                     onclick: (e) => { e.stopPropagation(); editarCupom(c, planos); } }),
    ],
    { aoClicar: (c) => editarCupom(c, planos),
      vazioTexto: "Nenhum cupom ainda. Crie um plano \"só por cupom\" na aba Planos e preços e depois o cupom que o libera." },
  )));
}

function situacaoDoCupom(c) {
  if (!c.ativo) return pilula("Desligado", "neutro");
  if (c.valido_ate && c.valido_ate < hoje()) return pilula("Vencido", "aviso");
  if (c.usos_max && c.pedidos >= c.usos_max) return pilula("Esgotado", "aviso");
  return pilula("Valendo", "ok");
}

const campo = (rotulo, entrada, dica = "") => el("label", { classe: "campo" }, [
  el("span", { texto: rotulo }), entrada, dica ? el("small", { classe: "dica", texto: dica }) : null,
]);
/** Campos empilhados com respiro (o .corpo do cartao nao separa um do outro). */
const pilha = (filhos) => el("div", { estilo: "display:grid;gap:14px" }, filhos);
const marcador = (rotulo, marcado) => {
  const entrada = el("input", { type: "checkbox", checked: Boolean(marcado) });
  return { entrada, no: el("label", { classe: "campo", estilo: "flex-direction:row;align-items:center;gap:8px" },
                           [entrada, el("span", { texto: rotulo })]) };
};

// ---------------------------------------------------------------- a faixa --
function editarAviso(aviso) {
  const novo = !aviso;
  const a = aviso ?? { texto: "", link: "#plano", tom: "violeta", inicio: hoje(), fim: null, ativo: true };
  const texto = el("input", { type: "text", maxlength: "160", value: a.texto, placeholder: "Ex.: Novembro: plano Oficina com R$ 30 de desconto" });
  const link = el("input", { type: "text", value: a.link, placeholder: "#plano ou https://…" });
  const tom = el("select", {}, TONS.map(([v, t]) => el("option", { value: v, texto: t, selected: a.tom === v })));
  const inicio = el("input", { type: "date", value: a.inicio });
  const fim = el("input", { type: "date", value: a.fim ?? "" });
  const ativo = marcador("Ligada", a.ativo);
  const salvar = (e) => {
    const dados = { texto: texto.value.trim(), link: link.value.trim(), tom: tom.value,
                    inicio: inicio.value || hoje(), fim: fim.value || null, ativo: ativo.entrada.checked };
    const problema = problemaDoAviso(dados);
    if (problema) return recado(problema, "erro");
    agir(e.target, async () => {
      if (novo) await inserir("landing_avisos", dados);
      else await atualizar("landing_avisos", { id: `eq.${a.id}` }, dados);
      fecharGaveta();
      await recarregar();
    }, { feito: "Faixa salva. O site mostra nas datas escolhidas.", erro: "Não deu para salvar." });
  };
  const excluir = (e) => {
    if (!confirmar("Excluir esta faixa?")) return;
    agir(e.target, async () => {
      await apagar("landing_avisos", { id: `eq.${a.id}` }, { conferir: true });
      fecharGaveta();
      await recarregar();
    }, { feito: "Faixa excluída." });
  };
  abrirGaveta({
    acima: novo ? "Nova faixa de aviso" : "Faixa de aviso",
    titulo: novo ? "Criar faixa" : a.texto,
    conteudo: cartao("", pilha([
      campo("Texto (até 160 letras)", texto),
      el("div", { classe: "linha-campos" }, [
        campo("Ao clicar, leva para", link, "#plano leva ao plano na própria página. Vazio: a faixa não é clicável."),
        campo("Cor", tom),
      ]),
      el("div", { classe: "linha-campos" }, [campo("Começa em", inicio), campo("Termina em (vazio = sem fim)", fim)]),
      ativo.no,
      el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
        el("button", { classe: "botao botao-primario", texto: novo ? "Criar faixa" : "Salvar", onclick: salvar }),
        novo ? "" : el("button", { classe: "botao botao-perigo", texto: "Excluir", onclick: excluir }),
        el("button", { classe: "botao botao-fantasma", texto: "Cancelar", onclick: fecharGaveta }),
      ]),
    ])),
  });
}

// ---------------------------------------------------------------- cupons --
function editarCupom(cupom, planos) {
  const novo = !cupom;
  const c = cupom ?? { codigo: "", plano_id: "", descricao: "", parceiro: "", valido_ate: null, usos_max: null, ativo: true };
  const codigo = el("input", { type: "text", maxlength: "32", value: c.codigo, disabled: !novo, placeholder: "PARCEIRO10" });
  // os "so por cupom" primeiro: e para eles que o cupom existe
  const ordenados = [...planos].sort((a, b) => Number(a.visivel) - Number(b.visivel));
  const plano = el("select", {}, [
    el("option", { value: "", texto: "Escolha o plano" }),
    ...ordenados.map((p) => el("option", { value: p.id, selected: p.id === c.plano_id,
      texto: `${p.nome} · ${dinheiro(p.preco)}${p.visivel ? "" : " (só por cupom)"}${p.ativo ? "" : " (desligado)"}` })),
  ]);
  const descricao = el("input", { type: "text", maxlength: "120", value: c.descricao, placeholder: "Aparece no cupom de balcão do site" });
  const parceiro = el("input", { type: "text", maxlength: "80", value: c.parceiro, placeholder: "Quem indica (só para você)" });
  const validade = el("input", { type: "date", value: c.valido_ate ?? "" });
  const limite = el("input", { type: "number", min: "1", step: "1", value: c.usos_max ?? "" });
  const ativo = marcador("Valendo", c.ativo);
  const link = el("code", { classe: "link-cupom", texto: linkDoCupom(LOJA, c.codigo || "CODIGO") });
  codigo.addEventListener("input", () => { link.textContent = linkDoCupom(LOJA, codigo.value || "CODIGO"); });

  const salvar = (e) => {
    const dados = { plano_id: plano.value, descricao: descricao.value.trim(), parceiro: parceiro.value.trim(),
                    valido_ate: validade.value || null, usos_max: limite.value ? Number(limite.value) : null,
                    ativo: ativo.entrada.checked };
    const cod = novo ? codigo.value.trim().toUpperCase() : c.codigo;
    const problema = problemaDoCupom({ ...dados, codigo: cod });
    if (problema) return recado(problema, "erro");
    agir(e.target, async () => {
      if (novo) await inserir("mensalidade_cupons", { ...dados, codigo: cod });
      else await atualizar("mensalidade_cupons", { codigo: `eq.${c.codigo}` }, dados);
      fecharGaveta();
      await recarregar();
    }, { feito: "Cupom salvo. Já vale no site.", erro: "Não deu certo (o código já existe?)." });
  };
  const excluir = (e) => {
    if (!confirmar(`Excluir o cupom ${c.codigo}? Os pedidos que já usaram guardam o código.`)) return;
    agir(e.target, async () => {
      await apagar("mensalidade_cupons", { codigo: `eq.${c.codigo}` }, { conferir: true });
      fecharGaveta();
      await recarregar();
    }, { feito: "Cupom excluído." });
  };
  const copiar = el("button", { classe: "botao botao-fantasma botao-mini", texto: "Copiar link",
    onclick: async () => {
      try { await navigator.clipboard.writeText(link.textContent); recado("Link copiado.", "ok"); }
      catch { recado("Não deu para copiar: selecione o link e copie.", "erro"); }
    } });

  abrirGaveta({
    acima: novo ? "Novo cupom" : "Cupom",
    titulo: novo ? "Criar cupom" : c.codigo,
    conteudo: cartao("", pilha([
      el("div", { classe: "linha-campos" }, [campo("Código (o que o cliente digita)", codigo), campo("Libera o plano", plano)]),
      campo("Descrição", descricao),
      el("div", { classe: "linha-campos" }, [campo("Parceiro", parceiro), campo("Vale até (vazio = sem prazo)", validade)]),
      el("div", { classe: "linha-campos" }, [campo("Limite de usos (vazio = sem limite)", limite), el("div")]),
      ativo.no,
      el("div", { classe: "campo" }, [el("span", { texto: "Link com o cupom já aplicado (para o parceiro mandar)" }),
                                      el("div", { classe: "acoes-linha" }, [link, copiar])]),
      el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
        el("button", { classe: "botao botao-primario", texto: novo ? "Criar cupom" : "Salvar", onclick: salvar }),
        novo ? "" : el("button", { classe: "botao botao-perigo", texto: "Excluir", onclick: excluir }),
        el("button", { classe: "botao botao-fantasma", texto: "Cancelar", onclick: fecharGaveta }),
      ]),
    ])),
  });
}
