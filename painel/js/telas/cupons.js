// Cupons: PRIMEIRA10, parceiros, revendedores.
//
// O que a tela garante:
//   * desconto em % (ate 90%) ou em R$, com validade, limite de usos, valor
//     minimo e "so na primeira compra" - quem confere tudo e o banco, na hora
//     do pedido;
//   * cada cupom tem o LINK pronto (loja?cupom=CODIGO): o parceiro manda no
//     WhatsApp e o cliente chega com o desconto ja aplicado;
//   * o uso so conta quando o pedido e PAGO - pedido abandonado nao gasta;
//   * cupom ja usado nao some (e historico): ele e pausado.

import { apagar, atualizar, inserir, ler } from "../api.js";
import { CONFIG } from "../config.js";
import { data, dinheiro, numero } from "../formato.js";
import { abrirGaveta, fecharGaveta, recarregar } from "../painel.js";
import { codigoDeCupom, linkDoCupom as linkDaLoja, problemaDoCupom } from "../cupons.js";
import { porCupom } from "../relatorio.js";
import { agir, cartao, confirmar, el, pilula, recado, tabela } from "../ui.js";

const LOJA = CONFIG.LOJA_URL || "https://dumtechsolution.com";
const linkDoCupom = (codigo) => linkDaLoja(LOJA, codigo);

export async function cupons(alvo) {
  const [lista, pedidos] = await Promise.all([
    ler("cupons", { ordem: "criado_em.desc" }),
    ler("pedidos_site", { select: "itens,total,desconto,cupom,pagamento,pago_valor",
                          filtros: { cupom: "neq." } }),
  ]);
  const desempenho = new Map(porCupom(pedidos).map((l) => [l.chave, l]));

  alvo.append(el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Cupons" }),
      el("p", { texto: "O cliente digita no fechamento da compra, ou chega pelo link do cupom com o desconto já aplicado." }),
    ]),
    el("div", { classe: "ferramentas" }, [
      el("button", { classe: "botao botao-primario", texto: "Novo cupom", onclick: () => editar(null) }),
    ]),
  ]));

  alvo.append(cartao("Cupons", tabela(
    ["Cupom", "Desconto", "Regras", { texto: "Usos", numero: true }, { texto: "Pedidos", numero: true },
     { texto: "Receita", numero: true }, "Situação"],
    lista,
    (c) => {
      const d = desempenho.get(c.codigo);
      return [
        el("div", {}, [el("strong", { texto: c.codigo }),
                       el("div", { classe: "rodape-entrada", texto: c.parceiro ? `parceiro: ${c.parceiro}` : c.descricao })]),
        c.tipo === "percentual" ? `${Number(c.valor)}%` : dinheiro(c.valor),
        regras(c),
        c.usos_max ? `${numero(c.usos)} de ${numero(c.usos_max)}` : numero(c.usos),
        numero(d?.pedidos || 0),
        dinheiro(d?.receita || 0),
        situacao(c),
      ];
    },
    { aoClicar: (c) => editar(c), vazioTexto: "Nenhum cupom ainda. Crie o primeiro em “Novo cupom”." }
  )));
}

function regras(c) {
  const partes = [];
  if (c.primeira_compra) partes.push("só 1ª compra");
  if (Number(c.minimo) > 0) partes.push(`mínimo ${dinheiro(c.minimo)}`);
  if (c.valido_ate) partes.push(`até ${data(c.valido_ate)}`);
  return partes.join(" · ") || "—";
}

function situacao(c) {
  if (!c.ativo) return pilula("Pausado", "neutro");
  if (c.valido_ate && c.valido_ate < new Date().toISOString().slice(0, 10)) return pilula("Vencido", "aviso");
  if (c.usos_max && c.usos >= c.usos_max) return pilula("Esgotado", "aviso");
  return pilula("Valendo", "ok");
}

// ------------------------------------------------------------------ editor ---
function editar(cupom) {
  const novo = !cupom;
  const campo = (rotulo, valor, atributos = {}) => {
    const entrada = el("input", { ...atributos, value: valor ?? "" });
    return { no: el("label", { classe: "campo" }, [el("span", { texto: rotulo }), entrada]), entrada,
             valor: () => String(entrada.value ?? "").trim() };
  };
  const codigo = campo("Código (o que o cliente digita)", cupom?.codigo, { placeholder: "PRIMEIRA10", disabled: !novo });
  codigo.entrada.addEventListener("input", () => {
    const limpo = codigoDeCupom(codigo.entrada.value);
    if (limpo !== codigo.entrada.value) codigo.entrada.value = limpo;
    link.textContent = linkDoCupom(limpo || "CODIGO");
  });
  const descricao = campo("Descrição (aparece para o cliente)", cupom?.descricao, { placeholder: "10% de desconto na primeira compra" });
  const tipo = el("select", {}, [["percentual", "% sobre o total"], ["valor", "R$ fixos"]].map(([v, t]) =>
    el("option", { value: v, texto: t, selected: (cupom?.tipo || "percentual") === v })));
  const valor = campo("Desconto", cupom?.valor, { type: "number", min: "0", step: "0.01" });
  const validade = campo("Vale até (vazio = sem prazo)", cupom?.valido_ate, { type: "date" });
  const limite = campo("Limite de usos (vazio = sem limite)", cupom?.usos_max, { type: "number", min: "1", step: "1" });
  const minimo = campo("Compra mínima (R$)", cupom?.minimo ?? 0, { type: "number", min: "0", step: "0.01" });
  const parceiro = campo("Parceiro / revendedor (só para o relatório)", cupom?.parceiro, { placeholder: "João Revenda" });
  const primeira = el("input", { type: "checkbox", checked: cupom ? cupom.primeira_compra : false });
  const ativo = el("input", { type: "checkbox", checked: cupom ? cupom.ativo : true });
  const link = el("code", { classe: "link-cupom", texto: linkDoCupom(cupom?.codigo || "CODIGO") });

  const salvar = (e) => {
    const dados = {
      descricao: descricao.valor(), tipo: tipo.value, valor: Number(valor.valor()),
      valido_ate: validade.valor() || null, usos_max: limite.valor() ? Number(limite.valor()) : null,
      minimo: Number(minimo.valor() || 0), parceiro: parceiro.valor(),
      primeira_compra: primeira.checked, ativo: ativo.checked,
    };
    const cod = novo ? codigoDeCupom(codigo.valor()) : cupom.codigo;
    const problema = problemaDoCupom({ ...dados, codigo: cod });
    if (problema) return recado(problema, "erro");
    agir(e.target, async () => {
      if (novo) await inserir("cupons", { ...dados, codigo: cod });
      else await atualizar("cupons", { id: `eq.${cupom.id}` }, dados);
      fecharGaveta();
      await recarregar();
    }, { feito: "Cupom salvo. Já vale na loja.", erro: "Não deu certo (o código já existe?)." });
  };

  const pausar = (e) => agir(e.target, async () => {
    await atualizar("cupons", { id: `eq.${cupom.id}` }, { ativo: false });
    fecharGaveta();
    await recarregar();
  }, { feito: "Cupom pausado." });

  // usado ou nao, os pedidos guardam o codigo do cupom como texto: o historico fica
  const excluir = (e) => {
    const aviso = cupom.usos > 0
      ? `O cupom ${cupom.codigo} já foi usado ${cupom.usos} vez(es). Os pedidos guardam o código e o desconto ` +
        "que deram.\n\nExcluir mesmo assim? Ele para de valer na loja na hora."
      : `Excluir o cupom ${cupom.codigo}? Ele nunca foi usado.`;
    if (!confirmar(aviso)) return;
    agir(e.target, async () => {
      await apagar("cupons", { id: `eq.${cupom.id}` }, { conferir: true });
      fecharGaveta();
      await recarregar();
    }, { feito: "Cupom excluído." });
  };

  const copiar = el("button", {
    classe: "botao botao-fantasma botao-mini", texto: "Copiar link",
    onclick: async () => {
      try { await navigator.clipboard.writeText(link.textContent); recado("Link copiado.", "ok"); }
      catch { recado("Não deu para copiar: selecione o link e copie.", "erro"); }
    },
  });

  abrirGaveta({
    acima: novo ? "Novo cupom" : "Cupom",
    titulo: novo ? "Criar cupom" : cupom.codigo,
    conteudo: el("div", {}, [
      cartao("", [
        codigo.no, descricao.no,
        el("div", { classe: "linha-campos" }, [
          el("label", { classe: "campo" }, [el("span", { texto: "Tipo" }), tipo]), valor.no]),
        el("div", { classe: "linha-campos" }, [validade.no, limite.no]),
        el("div", { classe: "linha-campos" }, [minimo.no, parceiro.no]),
        el("label", { classe: "campo", estilo: "flex-direction:row;align-items:center;gap:8px" },
          [primeira, el("span", { texto: "Só na primeira compra (quem já comprou não usa)" })]),
        el("label", { classe: "campo", estilo: "flex-direction:row;align-items:center;gap:8px" },
          [ativo, el("span", { texto: "Valendo" })]),
        el("div", { classe: "campo" }, [el("span", { texto: "Link com o cupom já aplicado" }),
          el("div", { classe: "acoes-linha" }, [link, copiar])]),
        el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
          el("button", { classe: "botao botao-primario", texto: novo ? "Criar cupom" : "Salvar", onclick: salvar }),
          novo || !cupom.usos || !cupom.ativo ? "" : el("button", { classe: "botao botao-fantasma", texto: "Pausar", onclick: pausar }),
          novo ? "" : el("button", { classe: "botao botao-perigo", texto: "Excluir", onclick: excluir }),
          el("button", { classe: "botao botao-fantasma", texto: "Cancelar", onclick: fecharGaveta }),
        ]),
      ]),
      el("p", { classe: "rodape-entrada", estilo: "margin-top:12px",
        texto: "O uso só conta quando o pedido é pago. O desconto nunca deixa uma compra abaixo de R$ 1." }),
    ]),
  });
}
