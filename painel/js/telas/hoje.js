// Hoje: o que precisa de você, com o botão que resolve ao lado.
//
// A fila vem de fila.js (puro e testado): assinatura para confirmar,
// pagamento pendente, teste acabando, quem não instalou, retorno combinado,
// versão do Hub para lançar... Cada item resolve ali mesmo ou abre a ficha.
// Em cima, os quatro números do mês; embaixo, o que aconteceu por último.

import { ler, um } from "../api.js";
import { data, dinheiro, numero, quando, relativo } from "../formato.js";
import { carregarGestao } from "../gestao-dados.js";
import { montarFila, numerosDoMes, urgentes } from "../fila.js";
import { descreverEvento } from "../mensalidade.js";
import { irPara, marcarHoje } from "../painel.js";
import { botaoWhatsApp, cartao, confirmar, el, tile, vazio } from "../ui.js";
import { ficha } from "./comercial.js";
import { acionar, oQueFoiPedido, primeiro } from "./mensalidades.js";

const DIA_DA_SEMANA = new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "numeric", month: "long" });

export async function hoje(alvo) {
  const agora = new Date();
  const [gestao, pedidos, pedidosLoja, resumo, eventos] = await Promise.all([
    carregarGestao(agora),
    ler("painel_assinatura_pedidos", { filtros: { situacao: "eq.aguardando" }, ordem: "criado_em.desc" }).catch(() => []),
    ler("pedidos_abertos").catch(() => []),
    um("painel_resumo").catch(() => null),
    ler("painel_assinatura_eventos", { limite: 8 }).catch(() => []),
  ]);
  const { linhas, mensalidades } = gestao;
  const fila = montarFila({
    pedidos, mensalidades, pedidosLoja, linhas,
    pendente: gestao.pendente ? gestao.alvo : "", tentativas: resumo?.tentativas_24h,
  }, agora);
  marcarHoje(urgentes(fila));

  const clientePorId = new Map(linhas.map((l) => [l.id, l.cliente]));
  const clientePorLicenca = new Map(linhas.filter((l) => l.cliente.licenca_id).map((l) => [l.cliente.licenca_id, l.cliente]));
  const numeros = numerosDoMes(mensalidades);
  const online = linhas.filter((l) => l.online).length;

  const quantos = fila.length;
  alvo.append(
    el("div", { classe: "pagina-cabeca" }, [
      el("div", {}, [
        el("p", { classe: "sobrenome", texto: DIA_DA_SEMANA.format(agora) }),
        el("h1", { texto: quantos ? (quantos === 1 ? "Uma coisa precisa de você" : `${quantos} coisas precisam de você`)
                                  : "Tudo em dia por aqui" }),
      ]),
    ]),
    el("div", { classe: "tiles tiles-hoje" }, [
      tile("Receita do mês", dinheiro(numeros.receita), "pelo valor combinado de cada assinante", "ok"),
      tile("Assinantes", numero(numeros.assinantes),
        numeros.assinantes === numeros.emDia ? "todos em dia" : `${numero(numeros.emDia)} em dia`),
      tile("Testando", numero(numeros.testando), "teste grátis do plano"),
      tile("Online agora", numero(online), online === 1 ? "cliente com o Hub aberto" : "clientes com o Hub aberto"),
    ]),
    cartao("", fila.length
      ? el("ol", { classe: "fila" }, fila.map((item) => linhaDaFila(item, { clientePorId, clientePorLicenca, agora })))
      : vazio("Nada esperando você",
              "Quando alguém pedir para assinar, um pagamento atrasar ou um teste estiver acabando, aparece aqui com o botão que resolve.")),
  );

  if (eventos.length) {
    const nomes = new Map(mensalidades.map((m) => [m.licenca_id, m.nome]));
    alvo.append(cartao("O que aconteceu por último", el("ol", { classe: "atividade" }, eventos.map((evento) => {
      const { titulo } = descreverEvento(evento);
      const cliente = clientePorLicenca.get(evento.licenca_id);
      return el("li", {
        tabindex: cliente ? "0" : null, "data-clicavel": cliente ? "sim" : null,
        onclick: cliente ? () => ficha(cliente) : null,
        onkeydown: cliente ? (e) => { if (e.key === "Enter") ficha(cliente); } : null,
      }, [
        el("strong", { texto: nomes.get(evento.licenca_id) || cliente?.nome || "Cliente" }),
        el("span", { texto: titulo }),
        el("span", { classe: "sub-linha", texto: `${relativo(evento.criado_em, agora)} · ${evento.quem}` }),
      ]);
    }))));
  }
}

// ================================================================ a fila ===
/** Um item: o que é, o detalhe que decide, e os botões que resolvem. */
function linhaDaFila(item, { clientePorId, clientePorLicenca, agora }) {
  const cliente = (item.clienteId && clientePorId.get(item.clienteId))
    || (item.mensal && clientePorLicenca.get(item.mensal.licenca_id))
    || (item.pedido && clientePorLicenca.get(item.pedido.licenca_id)) || null;
  const { titulo, detalhe, acoes } = DESCRICOES[item.tipo](item, { cliente, agora });
  const abrir = cliente ? () => ficha(cliente) : null;
  return el("li", {
    classe: "fila-item", "data-tipo": item.tipo, "data-urgente": item.urgente ? "sim" : null,
    "data-clicavel": abrir ? "sim" : null, tabindex: abrir ? "0" : null,
    onclick: abrir, onkeydown: abrir ? (e) => { if (e.key === "Enter" && e.target === e.currentTarget) abrir(); } : null,
  }, [
    el("span", { classe: "fila-marca", "aria-hidden": "true" }),
    el("div", { classe: "fila-texto" }, [
      el("strong", { texto: titulo }),
      detalhe ? el("span", { texto: detalhe }) : null,
    ]),
    el("div", { classe: "fila-acoes" }, acoes.filter(Boolean)),
  ]);
}

const botao = (texto, classe, fazer, titulo = "") => el("button", {
  type: "button", classe: `botao ${classe} botao-mini`, texto, title: titulo,
  onclick: (evento) => { evento.stopPropagation(); fazer(evento.currentTarget); },
});
const whats = (telefone, texto, rotulo = "WhatsApp") => botaoWhatsApp(telefone, texto, rotulo);
const ola = (nome) => `Olá, ${primeiro(nome)}! Aqui é da DumTech.`;
const emDias = (dias) => (dias === 0 ? "hoje" : dias === 1 ? "amanhã" : dias < 0 ? `há ${-dias} dias` : `em ${dias} dias`);

// Cada tipo da fila: título, detalhe e ações. Recados do WhatsApp sempre
// gentis: o cliente lê, e ninguém gosta de cobrança seca.
const DESCRICOES = {
  confirmar: ({ pedido: p }) => ({
    titulo: `${p.nome} quer assinar`,
    detalhe: `${oQueFoiPedido(p)} · pediu ${quando(p.criado_em)}. Confira no app da InfinitePay antes de confirmar.` +
             (p.tipo === "assinatura" ? " É mudança de plano: cancele a assinatura antiga lá." : "") +
             (p.link ? "" : " Sem link: combine o pagamento pelo WhatsApp."),
    acoes: [
      botao("Confirmar assinatura", "botao-primario",
        (b) => acionar(b, { acao: "confirmar", pedido: p.id }, `Assinatura de ${p.nome} confirmada.`),
        "A licença vira mensal com este plano e o cliente recebe um e-mail"),
      botao("Descartar", "botao-fantasma", (b) => {
        if (!confirmar(`Descartar o pedido de ${p.nome}? Nada muda na licença dele.`)) return;
        acionar(b, { acao: "descartar", pedido: p.id }, "Pedido descartado.");
      }, "O pedido sai da lista (nada muda para o cliente)"),
      whats(p.telefone, `${ola(p.nome)} Vi o seu pedido de assinatura e queria confirmar se o pagamento na ` +
                        "InfinitePay deu certo. Posso ajudar em algo?"),
    ],
  }),

  cobranca: ({ mensal: m, dias }) => ({
    titulo: m.situacao === "consulta" ? `${m.nome} está só para consulta` : `Pagamento de ${m.nome} a confirmar`,
    detalhe: m.situacao === "consulta"
      ? `O Hub dele ficou só para consulta desde ${data(m.expira_em)}. Pagou? Um clique e volta a lançar.`
      : `${dinheiro(m.valor)} por mês. O Hub funciona até ${data(m.expira_em)} (${emDias(dias)}), com aviso gentil.`,
    acoes: [
      botao("Pagamento em dia", "botao-primario",
        (b) => acionar(b, { acao: "em_dia", licenca: m.licenca_id }, `${m.nome} está em dia.`),
        "Tira o aviso e, se estava só para consulta, volta a lançar"),
      whats(m.telefone, `${ola(m.nome)} Passando porque a mensalidade do DumTech Hub não foi confirmada este mês. ` +
                        "Às vezes é só o cartão que mudou. Quer que eu te mande o link para acertar?"),
    ],
  }),

  pedido_loja: ({ quantos }) => ({
    titulo: quantos === 1 ? "Um pedido antigo da loja em aberto" : `${quantos} pedidos antigos da loja em aberto`,
    detalhe: "Do tempo do módulo avulso. Aprove ou descarte para a lista ficar limpa.",
    acoes: [botao("Ver pedidos", "botao-primario", () => irPara("pedidos"))],
  }),

  teste_acabando: ({ mensal: m, dias }) => ({
    titulo: `Teste de ${m.nome} termina ${emDias(dias)}`,
    detalhe: `Termina em ${data(m.expira_em)}. Boa hora para perguntar como foi e ajudar a assinar.`,
    acoes: [
      botao("+7 dias", "botao-fantasma",
        (b) => acionar(b, { acao: "estender", licenca: m.licenca_id, dias: 7 }, `O teste de ${m.nome} ganhou mais 7 dias.`),
        "Mais 7 dias de teste grátis"),
      whats(m.telefone, `${ola(m.nome)} O seu teste do DumTech Hub termina ${emDias(dias)}. O que está achando? ` +
                        "Se quiser continuar, eu te ajudo a escolher o plano."),
    ],
  }),

  teste_terminou: ({ mensal: m, dias }) => ({
    titulo: `Teste de ${m.nome} terminou sem assinatura`,
    detalhe: `Terminou ${emDias(dias)}. Os dados dele continuam lá, só para consulta.`,
    acoes: [
      botao("+7 dias", "botao-fantasma",
        (b) => acionar(b, { acao: "estender", licenca: m.licenca_id, dias: 7 }, `O teste de ${m.nome} ganhou mais 7 dias.`),
        "Reabre o teste por mais 7 dias"),
      whats(m.telefone, `${ola(m.nome)} O seu teste grátis do DumTech Hub terminou. O que achou? ` +
                        "Os seus dados continuam guardados. Se quiser continuar, eu te ajudo a assinar."),
    ],
  }),

  cancelou: ({ mensal: m, dias }) => ({
    titulo: `${m.nome} cancelou a assinatura`,
    detalhe: `Funciona até ${data(m.expira_em)} (${emDias(dias)}). Se ele mudar de ideia, Reabrir está na ficha.`,
    acoes: [whats(m.telefone, `${ola(m.nome)} Vi que você cancelou o DumTech Hub. Posso perguntar o que faltou? ` +
                              "Sua opinião ajuda muito a melhorar.")],
  }),

  retorno: ({ nome, dias }, { cliente }) => ({
    titulo: `Retornar para ${nome}`,
    detalhe: dias === 0 ? "Combinado para hoje." : `Estava combinado para ${emDias(dias)}.`,
    acoes: [whats(cliente?.telefone, ola(nome))],
  }),

  sem_instalar: ({ mensal: m }) => ({
    titulo: `${m.nome} ainda não instalou o Hub`,
    detalhe: `Começou o teste ${quando(m.criado_em)} e não ativou em nenhum computador. Uma ajuda agora vale ouro.`,
    acoes: [whats(m.telefone, `${ola(m.nome)} Vi que você começou o teste do DumTech Hub. Conseguiu instalar? ` +
                              "Se quiser, te ajudo agora pelo WhatsApp, leva 2 minutinhos.")],
  }),

  parou: ({ mensal: m, ultimoUso }, { agora }) => ({
    titulo: `${m.nome} parou de usar o Hub`,
    detalhe: ultimoUso ? `Último uso ${relativo(ultimoUso, agora)}. Assinante em dia: vale saber se está tudo bem.`
                       : "Assinante em dia sem uso recente: vale saber se está tudo bem.",
    acoes: [whats(m.telefone, `${ola(m.nome)} Passando para saber se está tudo certo com o DumTech Hub. ` +
                              "Precisa de ajuda com alguma coisa?")],
  }),

  teste_novo: ({ mensal: m }) => ({
    titulo: `${m.nome} começou o teste`,
    detalhe: `Começou ${quando(m.criado_em)}. Uma mensagem de boas-vindas ajuda a pessoa a dar o primeiro passo.`,
    acoes: [whats(m.telefone, `${ola(m.nome)} Que bom ter você testando o DumTech Hub! ` +
                              "Se precisar de ajuda para instalar ou cadastrar os primeiros produtos, é só me chamar.")],
  }),

  versao: ({ versao }) => ({
    titulo: `Versão ${versao} do Hub pronta para lançar`,
    detalhe: "Nenhum cliente recebe até você escolher. Dá para testar com um cliente antes.",
    acoes: [botao("Ver em Hub", "botao-primario", () => irPara("hub:atualizacoes"))],
  }),

  tentativas: ({ quantos }) => ({
    titulo: `${numero(quantos)} chaves recusadas nas últimas 24 horas`,
    detalhe: "Pode ser alguém digitando errado ou tentando uma chave que não é dele.",
    acoes: [botao("Ver em Segurança", "botao-fantasma", () => irPara("seguranca"))],
  }),
};
