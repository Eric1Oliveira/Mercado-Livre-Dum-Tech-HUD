// Planos e precos: tudo que o site cobra, editado aqui e valendo na hora.
//
//   * a base (quais modulos e o preco) e cada adicional (preco e "a venda");
//   * os planos prontos (qualquer combinacao, preco, link, destaque, de/por);
//   * o link da InfinitePay de cada combinacao do "monte o seu";
//   * teste, carencia e computadores.
// O preco cobrado e sempre o que esta aqui: o site so mostra, e o cadastro
// recalcula no banco. Quem ja assina continua no valor combinado.

import { apagar, atualizar, inserir, ler, um } from "../api.js";
import { data, dinheiro, numero } from "../formato.js";
import { chaveCombinacao, problemaDoPlano, todasAsCombinacoes, totalDaCombinacao } from "../mensalidade.js";
import { abrirGaveta, fecharGaveta, recarregar } from "../painel.js";
import { agir, cartao, confirmar, el, pilula, pilulaModulo, recado, tabela, vazio } from "../ui.js";

const FALTA_MIGRATION =
  "Rode a migration 20261104120000_controle_mensalidade.sql no Supabase (npx supabase db push) para ver esta tela.";
const hoje = () => new Date().toISOString().slice(0, 10);

export async function planos(alvo) {
  const [config, modulos, prontos, combinacoes, comLink] = await Promise.all([
    um("mensalidade_config").catch(() => null),
    ler("mensalidade_modulos", { ordem: "ordem.asc" }).catch(() => null),
    ler("mensalidade_planos", { ordem: "ordem.asc" }).catch(() => null),
    ler("painel_combinacoes").catch(() => []),
    ler("mensalidade_combinacoes").catch(() => []),
  ]);
  const cabeca = el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Planos e preços" }),
      el("p", { texto: "O que o site cobra: a base, cada adicional, os planos prontos e os links da InfinitePay. " +
                       "Mudou aqui, o site mostra na hora. Quem já assina continua no valor combinado." }),
    ]),
    el("div", { classe: "ferramentas" }, [
      el("button", { classe: "botao botao-primario", texto: "Novo plano pronto", onclick: () => editarPlano(null, modulos ?? []) }),
    ]),
  ]);
  if (!config || !modulos || !prontos) {
    alvo.append(cabeca, cartao("", vazio("O banco ainda não tem os planos", FALTA_MIGRATION)));
    return;
  }

  alvo.append(
    cabeca,
    cartao("Planos prontos", tabelaDePlanos(prontos, modulos)),
    cartao("Plano base e adicionais", baseEAdicionais(config, modulos)),
    cartao("Monte o seu: link de cada combinação", linksDoMonteOSeu(config, modulos, combinacoes, comLink)),
    cartao("Teste, carência e computadores", prazos(config)),
  );
}

const campo = (rotulo, entrada, dica = "") => el("label", { classe: "campo" }, [
  el("span", { texto: rotulo }), entrada, dica ? el("small", { classe: "dica", texto: dica }) : null,
]);
const caixa = (rotulo, marcado) => {
  const entrada = el("input", { type: "checkbox", checked: Boolean(marcado) });
  return { entrada, no: el("label", { classe: "campo", estilo: "flex-direction:row;align-items:center;gap:8px" },
                           [entrada, el("span", { texto: rotulo })]) };
};
/** Campos empilhados com respiro (o .corpo do cartao nao separa um do outro). */
const pilha = (filhos) => el("div", { estilo: "display:grid;gap:14px" }, filhos);
const promoVigente = (p) => p.promo_preco != null && p.promo_ate && p.promo_ate >= hoje();

// ------------------------------------------------------ planos prontos ---
function tabelaDePlanos(prontos, modulos) {
  return tabela(
    ["Plano", "Módulos", { texto: "Preço por mês", numero: true }, "Link", "No site", ""],
    prontos,
    (p) => [
      el("div", {}, [el("strong", { texto: p.nome }),
                     p.descricao ? el("div", { classe: "sub-linha", texto: p.descricao }) : null]),
      el("div", { classe: "acoes-linha" }, p.modulos.map((c) => pilulaModulo(c))),
      el("div", {}, promoVigente(p)
        ? [el("s", { classe: "sub-linha", texto: dinheiro(p.preco) }), el("div", { texto: dinheiro(p.promo_preco) }),
           el("div", { classe: "sub-linha", texto: `${p.promo_rotulo || "Promoção"} até ${data(p.promo_ate)}` })]
        : [dinheiro(p.preco)]),
      (promoVigente(p) ? p.promo_link : p.link) ? pilula("Tem link", "ok") : pilula("Sem link: WhatsApp", "aviso"),
      el("div", {}, [
        !p.ativo ? pilula("Desligado", "neutro") : p.visivel ? pilula("Aparece", "ok") : pilula("Só por cupom", "marca"),
        p.destaque ? el("div", { classe: "sub-linha", texto: "Recomendado" }) : null,
        el("div", { classe: "sub-linha", texto: `posição ${p.ordem}` }),
      ]),
      el("button", { type: "button", classe: "botao botao-fantasma botao-mini", texto: "Editar",
                     onclick: (e) => { e.stopPropagation(); editarPlano(p, modulos); } }),
    ],
    { aoClicar: (p) => editarPlano(p, modulos),
      vazioTexto: "Nenhum plano pronto ainda. Sem eles, o site mostra só o monte o seu. Crie o primeiro em Novo plano pronto." },
  );
}

function editarPlano(plano, modulos) {
  const novo = !plano;
  const p = plano ?? { nome: "", descricao: "", modulos: [], preco: "", link: "", destaque: false, visivel: true,
                       ordem: 1, ativo: true, promo_preco: null, promo_link: "", promo_rotulo: "", promo_ate: null };
  const entrada = (valor, atributos = {}) => el("input", { ...atributos, value: valor ?? "" });
  const nome = entrada(p.nome, { maxlength: "60", placeholder: "Ex.: Oficina" });
  const descricao = entrada(p.descricao, { maxlength: "240", placeholder: "Uma frase: para quem é este plano" });
  const preco = entrada(p.preco, { type: "number", min: "0", step: "0.01" });
  const link = entrada(p.link, { type: "url", placeholder: "https://… (o plano mensal no app da InfinitePay)" });
  const ordem = entrada(p.ordem, { type: "number", min: "0", step: "1" });
  const destaque = caixa("Recomendado (ganha o selo no site)", p.destaque);
  const visivel = caixa("Aparece no site (desmarcado: só por cupom)", p.visivel);
  const ativo = caixa("Ligado", p.ativo);
  const marcas = modulos.filter((m) => m.papel !== "fora").map((m) => {
    const c = el("input", { type: "checkbox", value: m.codigo, checked: p.modulos.includes(m.codigo) });
    return { c, no: el("label", { classe: "campo", estilo: "flex-direction:row;align-items:center;gap:8px" }, [c, pilulaModulo(m.codigo)]) };
  });
  const promoPreco = entrada(p.promo_preco, { type: "number", min: "0", step: "0.01", placeholder: "vazio = sem promoção" });
  const promoLink = entrada(p.promo_link, { type: "url", placeholder: "https://… (o plano com o valor promocional)" });
  const promoRotulo = entrada(p.promo_rotulo, { maxlength: "40", placeholder: "Ex.: Novembro" });
  const promoAte = entrada(p.promo_ate, { type: "date" });

  const ler_ = () => ({
    nome: nome.value.trim(), descricao: descricao.value.trim(),
    modulos: marcas.filter((m) => m.c.checked).map((m) => m.c.value),
    preco: preco.value === "" ? "" : Number(preco.value), link: link.value.trim(),
    destaque: destaque.entrada.checked, visivel: visivel.entrada.checked, ativo: ativo.entrada.checked,
    ordem: Number(ordem.value || 0),
    promo_preco: promoPreco.value === "" ? null : Number(promoPreco.value),
    promo_link: promoLink.value.trim(), promo_rotulo: promoRotulo.value.trim(), promo_ate: promoAte.value || null,
  });

  const salvar = (e) => {
    const dados = ler_();
    const problema = problemaDoPlano(dados);
    if (problema) return recado(problema, "erro");
    agir(e.target, async () => {
      if (novo) await inserir("mensalidade_planos", dados);
      else await atualizar("mensalidade_planos", { id: `eq.${p.id}` }, dados);
      fecharGaveta();
      await recarregar();
    }, { feito: "Plano salvo. O site já mostra.", erro: "Não deu para salvar." });
  };
  const excluir = (e) => {
    if (!confirmar(`Excluir o plano ${p.nome}? Quem já assina continua com os módulos e o valor dele.\n\n` +
                   "Se ele tem cupom, desligue em vez de excluir.")) return;
    agir(e.target, async () => {
      await apagar("mensalidade_planos", { id: `eq.${p.id}` }, { conferir: true });
      fecharGaveta();
      await recarregar();
    }, { feito: "Plano excluído.", erro: "Não deu para excluir (ele tem cupom? desligue em vez de excluir)." });
  };

  abrirGaveta({
    acima: novo ? "Novo plano pronto" : "Plano pronto",
    titulo: novo ? "Criar plano" : p.nome,
    conteudo: el("div", {}, [
      cartao("O plano", pilha([
        el("div", { classe: "linha-campos" }, [campo("Nome", nome), campo("Posição na página", ordem, "1 aparece primeiro")]),
        campo("Descrição", descricao),
        el("div", { classe: "campo" }, [el("span", { texto: "Módulos (qualquer combinação)" }),
          el("div", { classe: "acoes-linha", estilo: "gap:4px 14px" }, marcas.map((m) => m.no))]),
        el("div", { classe: "linha-campos" }, [campo("Preço por mês (R$)", preco), campo("Link da InfinitePay", link)]),
        destaque.no, visivel.no, ativo.no,
      ])),
      cartao("Promoção (de/por)", pilha([
        el("p", { classe: "dica", estilo: "margin-bottom:10px",
          texto: "O site mostra \"de R$ X por R$ Y\" até a data. Crie no app da InfinitePay um plano com o valor " +
                 "promocional e cole o link aqui: sem ele, quem quiser assinar na promoção vai para o WhatsApp. " +
                 "Quem assinar na promoção continua pagando o valor promocional." }),
        el("div", { classe: "linha-campos" }, [campo("Preço promocional (R$)", promoPreco), campo("Até", promoAte)]),
        el("div", { classe: "linha-campos" }, [campo("Rótulo", promoRotulo), campo("Link da promoção", promoLink)]),
      ])),
      el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
        el("button", { classe: "botao botao-primario", texto: novo ? "Criar plano" : "Salvar", onclick: salvar }),
        novo ? "" : el("button", { classe: "botao botao-perigo", texto: "Excluir", onclick: excluir }),
        el("button", { classe: "botao botao-fantasma", texto: "Cancelar", onclick: fecharGaveta }),
      ]),
    ]),
  });
}

// ------------------------------------------------ base e adicionais ------
function baseEAdicionais(config, modulos) {
  const precoBase = el("input", { type: "number", min: "0", step: "0.01", value: config.preco_base });
  const linhas = modulos.map((m) => {
    const papel = el("select", {}, [["base", "Base"], ["adicional", "Adicional"], ["fora", "Fora da mensalidade"]]
      .map(([v, t]) => el("option", { value: v, texto: t, selected: m.papel === v })));
    const preco = el("input", { type: "number", min: "0", step: "0.01", value: m.preco, estilo: "max-width:120px" });
    const venda = el("input", { type: "checkbox", checked: m.a_venda });
    const ajustar = () => {
      preco.disabled = papel.value !== "adicional";
      venda.disabled = papel.value !== "adicional";
    };
    papel.addEventListener("change", ajustar);
    ajustar();
    return { m, papel, preco, venda };
  });

  const salvar = (e) => {
    if (!linhas.some((l) => l.papel.value === "base")) return recado("A base precisa de ao menos um módulo.", "erro");
    if (!(Number(precoBase.value) >= 0)) return recado("Confira o preço da base.", "erro");
    agir(e.target, async () => {
      for (const l of linhas) {
        const dados = { papel: l.papel.value, preco: Number(l.preco.value || 0), a_venda: l.venda.checked };
        if (dados.papel !== l.m.papel || dados.preco !== Number(l.m.preco) || dados.a_venda !== l.m.a_venda) {
          await atualizar("mensalidade_modulos", { codigo: `eq.${l.m.codigo}` }, dados);
        }
      }
      if (Number(precoBase.value) !== Number(config.preco_base)) {
        await atualizar("mensalidade_config", { id: "eq.true" }, { preco_base: Number(precoBase.value) });
      }
      await recarregar();
    }, { feito: "Salvo. O site já mostra os preços novos.", erro: "Não deu para salvar." });
  };

  return el("div", {}, [
    el("p", { classe: "dica", estilo: "margin-bottom:12px",
      texto: "A base é o que todo plano do monte o seu tem. Cada adicional soma o próprio preço. Adicional fora da " +
             "venda some do site, mas quem já tem continua com ele." }),
    el("div", { classe: "linha-campos" }, [campo("Preço da base por mês (R$)", precoBase), el("div")]),
    tabela(
      ["Módulo", "Papel", { texto: "Preço por mês", numero: true }, "À venda"],
      linhas,
      (l) => [pilulaModulo(l.m.codigo), l.papel, l.preco, l.venda],
    ),
    el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
      el("button", { classe: "botao botao-primario", texto: "Salvar base e adicionais", onclick: salvar }),
    ]),
  ]);
}

// ------------------------------------------------ monte o seu: links -----
function linksDoMonteOSeu(config, modulos, combinacoes, comLink) {
  const adicionais = modulos.filter((m) => m.papel === "adicional" && m.a_venda)
    .map((m) => ({ codigo: m.codigo, preco: Number(m.preco) }));
  const existentes = new Map(comLink.map((k) => [k.chave, k.link]));
  const pedidas = new Map(combinacoes.map((k) => [k.chave, Number(k.pedidos || 0)]));
  const linhas = todasAsCombinacoes(adicionais.map((a) => a.codigo)).map((escolhidos) => {
    const chave = chaveCombinacao(escolhidos);
    const link = el("input", { type: "url", value: existentes.get(chave) ?? "", estilo: "width:100%;min-width:280px",
                               placeholder: "https://… (plano mensal no app da InfinitePay)" });
    return { escolhidos, chave, link, pedidos: pedidas.get(chave) ?? 0,
             total: totalDaCombinacao(config.preco_base, adicionais, escolhidos) };
  });
  // quem alguem pediu e ainda nao tem link vem primeiro
  linhas.sort((a, b) => Number(!existentes.get(b.chave) && b.pedidos > 0) - Number(!existentes.get(a.chave) && a.pedidos > 0));

  const salvar = (e) => {
    const torto = linhas.find((l) => l.link.value.trim() && !/^https:\/\/\S+$/.test(l.link.value.trim()));
    if (torto) return recado("Um dos links não começa com https://", "erro");
    agir(e.target, async () => {
      for (const l of linhas) {
        const novo = l.link.value.trim();
        const antes = existentes.get(l.chave);
        if (antes === undefined && novo) await inserir("mensalidade_combinacoes", { chave: l.chave, link: novo });
        else if (antes !== undefined && antes !== novo) {
          await atualizar("mensalidade_combinacoes", { chave: `eq.${l.chave}` }, { link: novo });
        }
      }
      await recarregar();
    }, { feito: "Links salvos.", erro: "Não deu para salvar os links." });
  };

  return el("div", {}, [
    el("p", { classe: "dica", estilo: "margin-bottom:12px",
      texto: "Para cada combinação que você quer vender sem conversa, crie no app da InfinitePay um plano mensal com o " +
             "total ao lado e cole o link. Sem link, quem escolhe aquela combinação é levado ao WhatsApp." }),
    tabela(
      ["Combinação", { texto: "Total por mês", numero: true }, "Pedidos", "Link"],
      linhas,
      (l) => [
        el("div", { classe: "acoes-linha" }, l.escolhidos.length
          ? [el("span", { classe: "sub-linha", texto: "Base +" }), ...l.escolhidos.map((c) => pilulaModulo(c))]
          : [el("span", { texto: "Só a base" })]),
        dinheiro(l.total),
        l.pedidos
          ? (existentes.get(l.chave) ? numero(l.pedidos) : pilula(`${numero(l.pedidos)}: alguém pediu e falta link`, "aviso"))
          : "—",
        l.link,
      ],
    ),
    el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
      el("button", { classe: "botao botao-primario", texto: "Salvar links", onclick: salvar }),
    ]),
  ]);
}

// ---------------------------------------------- teste, carencia, pcs ------
function prazos(config) {
  const teste = el("input", { type: "number", min: "1", max: "60", step: "1", value: config.dias_teste });
  const carencia = el("input", { type: "number", min: "0", max: "60", step: "1", value: config.dias_carencia });
  const computadores = el("input", { type: "number", min: "1", max: "50", step: "1", value: config.computadores });
  const salvar = (e) => agir(e.target, async () => {
    await atualizar("mensalidade_config", { id: "eq.true" }, {
      dias_teste: Number(teste.value), dias_carencia: Number(carencia.value), computadores: Number(computadores.value),
    });
    await recarregar();
  }, { feito: "Salvo. Vale para os próximos testes e cobranças.", erro: "Não deu para salvar (confira os números)." });
  return pilha([
    el("div", { classe: "linha-campos" }, [
      campo("Dias de teste grátis", teste), campo("Dias de carência quando a cobrança falha", carencia)]),
    el("div", { classe: "linha-campos" }, [
      campo("Computadores por licença", computadores, "Vale para os novos testes, e é o número que o site mostra."),
      el("div"),
    ]),
    el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
      el("button", { classe: "botao botao-primario", texto: "Salvar", onclick: salvar }),
    ]),
  ]);
}
