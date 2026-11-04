// A fila da tela Hoje: o que precisa de uma decisão sua, na ordem de urgência.
//
// Puro (sem DOM e sem rede): a tela Hoje desenha, o selo do menu conta, e
// tests/fila.test.mjs confere as regras.
//
// REGRA DE OURO: cobrança só existe para quem é mensal. A lista de
// mensalidades (painel_mensalidades) já não traz licença vitalícia, e nenhum
// item de pagamento nasce de outro lugar.

import { diaLocal, diasEntre } from "./saude.js";

export const TIPOS = {
  confirmar:      { ordem: 0, urgente: true },
  cobranca:       { ordem: 1, urgente: true },
  pedido_loja:    { ordem: 2, urgente: true },
  teste_acabando: { ordem: 3, urgente: false },
  teste_terminou: { ordem: 4, urgente: false },
  cancelou:       { ordem: 5, urgente: false },
  retorno:        { ordem: 6, urgente: false },
  sem_instalar:   { ordem: 7, urgente: false },
  parou:          { ordem: 8, urgente: false },
  teste_novo:     { ordem: 9, urgente: false },
  versao:         { ordem: 10, urgente: false },
  tentativas:     { ordem: 11, urgente: false },
};

/** Teste terminando em até tantos dias entra na fila. */
export const AVISO_DO_TESTE = 2;
/** Teste que terminou há até tantos dias ainda vale uma conversa. */
export const JANELA_DO_FIM = 14;
/** Tentativas recusadas em 24h a partir das quais vale olhar. */
export const TENTATIVAS_DEMAIS = 20;

const ehMensal = (m) => m && (m.tipo === "assinatura" || m.tipo === "teste");

/**
 * Monta a fila.
 *   pedidos       painel_assinatura_pedidos aguardando confirmação
 *   mensalidades  painel_mensalidades (só assinatura e teste)
 *   pedidosLoja   pedidos_abertos (o checkout antigo da loja)
 *   linhas        montarClientes (gestao.js): uso, retorno e quem é quem
 *   pendente      versão pronta para lançar ("" quando não há)
 *   tentativas    chaves recusadas nas últimas 24h
 */
export function montarFila({
  pedidos = [], mensalidades = [], pedidosLoja = [], linhas = [], pendente = "", tentativas = 0,
} = {}, agora = new Date()) {
  const hoje = diaLocal(agora);
  const itens = [];
  const linhaDaLicenca = new Map(linhas.filter((l) => l.cliente?.licenca_id).map((l) => [l.cliente.licenca_id, l]));

  for (const p of pedidos) {
    itens.push({ tipo: "confirmar", chave: `confirmar:${p.id}`, nome: p.nome, quando: p.criado_em, pedido: p,
                 clienteId: p.cliente_id || linhaDaLicenca.get(p.licenca_id)?.id || null });
  }

  for (const m of mensalidades.filter(ehMensal)) {
    const base = { nome: m.nome, mensal: m, clienteId: m.cliente_id || null };
    const dias = m.expira_em ? diasEntre(hoje, m.expira_em) : null;

    if (m.tipo === "assinatura") {
      if (m.cobranca_motivo === "cancelou" && m.situacao === "pendente") {
        itens.push({ ...base, tipo: "cancelou", chave: `cancelou:${m.licenca_id}`, dias });
      } else if (m.cobranca_motivo !== "cancelou" && (m.situacao === "pendente" || m.situacao === "consulta")) {
        itens.push({ ...base, tipo: "cobranca", chave: `cobranca:${m.licenca_id}`, dias });
      }
    }

    if (m.tipo === "teste") {
      // um item por teste, o mais importante: acabando > terminou > não instalou > começou
      const idade = m.criado_em ? diasEntre(diaLocal(m.criado_em), hoje) : Infinity;
      const naoInstalou = linhaDaLicenca.get(m.licenca_id)?.uso === "sem_ativar";
      const item = { ...base, chave: `teste:${m.licenca_id}`, dias, quando: m.criado_em };
      if (m.situacao === "teste" && dias !== null && dias <= AVISO_DO_TESTE) {
        itens.push({ ...item, tipo: "teste_acabando" });
      } else if (m.situacao === "consulta" && dias !== null && dias >= -JANELA_DO_FIM) {
        itens.push({ ...item, tipo: "teste_terminou" });
      } else if (m.situacao === "teste" && naoInstalou && idade >= 1) {
        itens.push({ ...item, tipo: "sem_instalar" });
      } else if (m.situacao === "teste" && idade <= 1) {
        itens.push({ ...item, tipo: "teste_novo" });
      }
    }

    if (m.tipo === "assinatura" && m.situacao === "em_dia" && linhaDaLicenca.get(m.licenca_id)?.uso === "sumiu") {
      itens.push({ ...base, tipo: "parou", chave: `parou:${m.licenca_id}`,
                   ultimoUso: linhaDaLicenca.get(m.licenca_id).cliente.ultimo_uso || null });
    }
  }

  if (pedidosLoja.length) {
    itens.push({ tipo: "pedido_loja", chave: "pedido_loja", quantos: pedidosLoja.length, nome: "" });
  }

  for (const l of linhas) {
    if (l.proximoContato && diasEntre(hoje, l.proximoContato) <= 0) {
      itens.push({ tipo: "retorno", chave: `retorno:${l.id}`, nome: l.nome, clienteId: l.id,
                   dias: diasEntre(hoje, l.proximoContato) });
    }
  }

  if (pendente) itens.push({ tipo: "versao", chave: "versao", versao: pendente, nome: "" });
  if (Number(tentativas) > TENTATIVAS_DEMAIS) {
    itens.push({ tipo: "tentativas", chave: "tentativas", quantos: Number(tentativas), nome: "" });
  }

  return itens
    .map((item) => ({ ...item, urgente: TIPOS[item.tipo].urgente }))
    .sort((a, b) => TIPOS[a.tipo].ordem - TIPOS[b.tipo].ordem
      || (a.dias ?? 0) - (b.dias ?? 0)
      || String(b.quando || "").localeCompare(String(a.quando || "")));
}

/** O número do selo: o que não pode esperar (assinatura, pagamento, pedido). */
export const urgentes = (fila) => fila.filter((item) => item.urgente).length;

/** Os números do topo da tela Hoje. Vitalício não entra na receita mensal. */
export function numerosDoMes(mensalidades = []) {
  const assinantes = mensalidades.filter((m) => m.tipo === "assinatura" && m.situacao !== "consulta");
  return {
    receita: assinantes.reduce((soma, m) => soma + Number(m.valor || 0), 0),
    assinantes: assinantes.length,
    emDia: assinantes.filter((m) => m.situacao === "em_dia").length,
    testando: mensalidades.filter((m) => m.tipo === "teste" && m.situacao === "teste").length,
  };
}
