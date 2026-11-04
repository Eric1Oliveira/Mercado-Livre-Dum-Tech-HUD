// A mensalidade dentro do painel: o bloco "Assinatura" da ficha do cliente e
// as ações que a tela Hoje usa (confirmar, pagamento em dia, +7 dias...).
//
// A InfinitePay cobra pelos planos do app dela, mas NAO avisa o sistema. Por
// isso o dia a dia é de poucos cliques:
//   * a assinatura apareceu no app da InfinitePay -> "Confirmar assinatura";
//   * o app mostrou uma cobranca recusada         -> "Cobrança falhou";
//   * o cliente regularizou                        -> "Pagamento em dia".
// Toda mudanca pergunta "Avisar o cliente por e-mail" (marcado) e chega ao Hub
// dele em ate 2 minutos.
//
// Licenca vitalicia nunca passa por aqui: ela nunca entra na mensalidade, e a
// ficha so desenha este bloco para assinatura e teste.

import { funcao, ler, um } from "../api.js";
import { data, dinheiro } from "../formato.js";
import { descreverEvento, mudancasDaFicha } from "../mensalidade.js";
import { recarregar } from "../painel.js";
import { agir, cartao, confirmar, el, pilulaModulo, recado } from "../ui.js";

export const primeiro = (nome) => String(nome || "").trim().split(/\s+/)[0] || "";

/** Chama a Edge Function e conta o resultado. E-mail que nao saiu vira recado. */
export function acionar(alvo, corpo, feito, { depois = recarregar } = {}) {
  return agir(alvo, async () => {
    const { status, dados } = await funcao("mensalidade/admin", corpo);
    if (status === 0 || status === 404) throw new Error("A função mensalidade ainda não foi publicada no Supabase.");
    if (!dados?.ok) throw new Error(dados?.mensagem || `Erro ${status}.`);
    await depois();
    const quisAvisar = corpo.avisar !== false && corpo.acao !== "descartar";
    if (quisAvisar && dados.email_enviado === false && !(corpo.acao === "ajustar" && !temMudancaDoCliente(dados))) {
      recado(`${feito} O e-mail para o cliente não saiu: avise pelo WhatsApp.`, "aviso");
    } else {
      recado(`${feito}${quisAvisar && dados.email_enviado ? " O cliente recebeu um e-mail." : ""}`, "ok");
    }
    return dados;
  }, { feito: "", erro: "Não deu certo." });
}

const temMudancaDoCliente = (dados) =>
  Object.keys(dados.mudou ?? {}).some((k) => ["modulos", "plano", "valor", "computadores", "ate"].includes(k));

/** A data que importa em cada situação ("funciona até 12/11"). */
export function detalheDaSituacao(linha) {
  if (linha.situacao === "teste") return `até ${data(linha.expira_em)}`;
  if (linha.situacao === "pendente") return `${linha.cobranca_motivo === "cancelou" ? "encerra" : "funciona até"} ${data(linha.expira_em)}`;
  if (linha.situacao === "consulta") return `desde ${data(linha.expira_em)}`;
  return "";
}

/** O que o pedido de assinatura pediu, em uma linha (tela Hoje). */
export function oQueFoiPedido(p) {
  const partes = [p.plano_nome ? `Plano ${p.plano_nome}` : "Monte o seu", `${dinheiro(p.valor)} por mês`];
  if (p.cupom) partes.push(`cupom ${p.cupom}`);
  return partes.join(" · ");
}

/** O histórico da assinatura, já em frases, para a linha do tempo da ficha. */
export async function eventosDaAssinatura(licencaId) {
  const eventos = await ler("painel_assinatura_eventos", {
    filtros: { licenca_id: `eq.${licencaId}` }, fresco: true,
  }).catch(() => []);
  return eventos.map((evento) => {
    const { titulo, detalhe } = descreverEvento(evento);
    return { quando: evento.criado_em, texto: titulo, detalhe, autor: evento.quem };
  });
}

// ========================================================= a assinatura ====
/**
 * Os cartões da assinatura na ficha: o que vale hoje, as ações do momento e
 * o formulário de plano, valor e datas. `depois` refaz a ficha.
 */
export async function cartoesDaAssinatura(linha, { depois }) {
  const [planos, modulos, config] = await Promise.all([
    ler("mensalidade_planos", { ordem: "ordem.asc" }).catch(() => []),
    ler("mensalidade_modulos", { ordem: "ordem.asc" }).catch(() => []),
    um("mensalidade_config").catch(() => null),
  ]);
  const carencia = Number(config?.dias_carencia ?? 7);
  const avisar = el("input", { type: "checkbox", checked: true });
  const comAviso = (corpo) => ({ ...corpo, avisar: avisar.checked });
  const teste = linha.tipo === "teste";

  // ------------------------------------------------------------- resumo
  // situação, plano e valor já estão no topo da ficha: aqui só o que falta
  const resumo = el("p", { classe: "zona-texto", texto: teste
    ? `Teste grátis até ${data(linha.expira_em)}. Fechou pelo WhatsApp? Escolha o plano abaixo e ative.`
    : linha.assinatura_desde
      ? `Assina desde ${data(linha.assinatura_desde)}, e a InfinitePay cobra todo dia ${Number(linha.assinatura_desde.slice(8, 10))}.`
      : "Assinatura ativa." });

  // ------------------------------------------------------------- formulário
  const escolhaPlano = el("select", {}, [
    el("option", { value: "", texto: "Módulos à mão (abaixo)" }),
    ...planos.map((p) => el("option", { value: p.id, texto: `${p.nome}${p.ativo ? "" : " (desligado)"} · ${dinheiro(p.preco)}`,
                                        selected: p.id === linha.plano_id })),
  ]);
  const caixas = modulos.filter((m) => m.papel !== "fora").map((m) => {
    const caixa = el("input", { type: "checkbox", value: m.codigo, checked: (linha.modulos ?? []).includes(m.codigo) });
    return { caixa, no: el("label", { classe: "marcador" }, [caixa, pilulaModulo(m.codigo)]) };
  });
  const quadroModulos = el("div", { classe: "acoes-linha", estilo: "gap:6px 14px" }, caixas.map((c) => c.no));
  const mostrarModulos = () => { quadroModulos.style.opacity = escolhaPlano.value ? ".45" : "1"; };
  escolhaPlano.addEventListener("change", mostrarModulos);
  mostrarModulos();

  const campo = (rotulo, entrada, dica = "") => el("label", { classe: "campo" }, [
    el("span", { texto: rotulo }), entrada, dica ? el("small", { classe: "dica", texto: dica }) : null,
  ]);
  const valor = el("input", { type: "number", min: "0", step: "0.01", value: linha.valor_mensal ?? "",
                              placeholder: linha.valor_mensal == null ? `calculado: ${dinheiro(linha.valor)}` : "" });
  const computadores = el("input", { type: "number", min: "1", max: "50", step: "1", value: linha.max_computadores });
  const ate = el("input", { type: "date", value: linha.expira_em ?? "", disabled: !linha.expira_em, min: hoje() });
  const anotacoes = el("textarea", { maxlength: "2000", placeholder: "Só a DumTech vê. Ex.: combinou desconto até março." });
  anotacoes.value = linha.observacoes ?? "";

  const lerFormulario = () => ({
    plano: escolhaPlano.value,
    modulos: caixas.filter((c) => c.caixa.checked).map((c) => c.caixa.value),
    valor: valor.value === "" ? "" : Number(valor.value),
    computadores: Number(computadores.value),
    ate: ate.disabled ? "" : ate.value,
    observacoes: anotacoes.value.trim(),
  });

  const salvar = (e) => {
    const form = lerFormulario();
    if (!form.plano && !form.modulos.length) return recado("Marque ao menos um módulo, ou escolha um plano pronto.", "erro");
    const mudou = mudancasDaFicha(linha, form);
    if (!Object.keys(mudou).length) return recado("Nada mudou.", "");
    acionar(e.currentTarget, comAviso({ acao: "ajustar", licenca: linha.licenca_id, ...mudou }), "Assinatura salva.", { depois });
  };

  // ------------------------------------------------------------- ações
  const botao = (texto, classe, titulo, fazer) =>
    el("button", { type: "button", classe: `botao ${classe}`, texto, title: titulo, onclick: (e) => fazer(e.currentTarget) });
  const acoes = [];

  if (teste) {
    acoes.push(botao("Ativar assinatura", "botao-primario",
      "Fechou pelo WhatsApp: vira assinatura com o plano (ou os módulos) e o valor escolhidos abaixo", (b) => {
        const form = lerFormulario();
        if (!form.plano && !form.modulos.length) return recado("Escolha o plano ou marque os módulos em Plano, valor e datas.", "erro");
        if (!confirmar(`Ativar a assinatura de ${linha.nome} agora, com o plano e o valor de "Plano, valor e datas"?`)) return;
        acionar(b, comAviso({ acao: "ativar", licenca: linha.licenca_id,
          ...(form.plano ? { plano: form.plano } : { modulos: form.modulos }),
          ...(form.valor !== "" ? { valor: form.valor } : {}) }), `Assinatura de ${linha.nome} ativada.`, { depois });
      }));
    acoes.push(botao("+7 dias de teste", "botao-fantasma", "Mais 7 dias de teste grátis",
      (b) => acionar(b, comAviso({ acao: "estender", licenca: linha.licenca_id, dias: 7 }), "O teste ganhou mais 7 dias.", { depois })));
  } else if (linha.cobranca_motivo === "cancelou") {
    acoes.push(botao("Reabrir assinatura", "botao-primario", "O cliente desistiu de sair: volta a valer, sem prazo",
      (b) => acionar(b, comAviso({ acao: "reabrir", licenca: linha.licenca_id }), "Assinatura reaberta.", { depois })));
  } else {
    if (linha.situacao === "em_dia") {
      acoes.push(botao("Cobrança falhou", "botao-fantasma", `O Hub continua funcionando por ${carencia} dias, com aviso gentil`, (b) => {
        if (!confirmar(`Marcar que a cobrança de ${linha.nome} falhou?\n\nO Hub dele continua funcionando por ${carencia} dias ` +
                       "e ele recebe um aviso gentil. O Hub recebe em até 2 minutos.")) return;
        acionar(b, comAviso({ acao: "falhou", licenca: linha.licenca_id }), "Cobrança marcada como falha.", { depois });
      }));
    } else {
      acoes.push(botao("Pagamento em dia", "botao-primario", "Tira o aviso e, se estava só para consulta, volta a lançar",
        (b) => acionar(b, comAviso({ acao: "em_dia", licenca: linha.licenca_id }), `${linha.nome} está em dia.`, { depois })));
    }
    const encerraEm = el("input", { type: "date", min: hoje(), value: diaDaqui(carencia), "aria-label": "Funciona até" });
    acoes.push(el("div", { classe: "encerrar" }, [
      el("span", { texto: "Cancelou? Funciona até" }), encerraEm,
      botao("Encerrar", "botao-perigo", "Até a data o Hub funciona; depois fica só para consulta. Cancele também no app da InfinitePay.", (b) => {
        if (!confirmar(`Encerrar a assinatura de ${linha.nome}? Até ${data(encerraEm.value)} tudo funciona; ` +
                       "depois fica só para consulta, sem perder dados.\n\nLembre de cancelar o plano no app da InfinitePay.")) return;
        acionar(b, comAviso({ acao: "cancelou", licenca: linha.licenca_id, ate: encerraEm.value }), "Assinatura encerrada.", { depois });
      }),
    ]));
  }

  const formulario = montarFormulario({ teste, escolhaPlano, quadroModulos, campo, valor, computadores, ate, anotacoes, avisar, salvar });
  return [
    cartao(teste ? "Teste do plano mensal" : "Assinatura", [
      resumo,
      el("div", { classe: "acoes-linha" }, acoes),
      el("details", { classe: "recolhido", open: teste }, [
        el("summary", { texto: teste ? "Plano, valor e datas" : "Mudar plano, valor, computadores ou datas" }),
        formulario,
      ]),
    ]),
  ];
}

const hoje = () => new Date().toISOString().slice(0, 10);
const diaDaqui = (dias) => new Date(Date.now() + dias * 86_400_000).toISOString().slice(0, 10);

function montarFormulario({ teste, escolhaPlano, quadroModulos, campo, valor, computadores, ate, anotacoes, avisar, salvar }) {
  return el("div", { classe: "pilha" }, [
    campo("Plano", escolhaPlano),
    el("div", { classe: "campo" }, [el("span", { texto: "Módulos (quando não é plano pronto)" }), quadroModulos]),
    el("div", { classe: "linha-campos" }, [
      campo("Valor combinado por mês (R$)", valor, "Vazio: o preço do plano ou dos módulos."),
      campo("Computadores", computadores),
    ]),
    campo(teste ? "Teste até" : "Funciona até", ate,
      ate.disabled ? "Assinatura em dia não tem data. Para dar prazo, use Cobrança falhou ou Encerrar." : ""),
    campo("Anotações (só a DumTech vê)", anotacoes),
    el("label", { classe: "marcador" },
      [avisar, el("span", { texto: "Avisar o cliente por e-mail (mudança de plano, valor, data ou computadores)" })]),
    el("div", { classe: "acoes-linha" }, [
      el("button", { classe: "botao botao-primario", texto: "Salvar", onclick: salvar }),
    ]),
  ]);
}
