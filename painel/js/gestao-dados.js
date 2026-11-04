// O que Hoje, Clientes e Atualizações leem do banco, junto e já cruzado.
//
// As leituras são as de sempre (api.js guarda e confere por trás). Nada aqui é
// grande: o PostgREST corta acima de 1000 linhas, e cada uma destas tem uma
// linha por cliente ou por computador.

import { ler } from "./api.js";
import { montarClientes, versaoAlvo, versaoPendente } from "./gestao.js";

/** A batida de cada Hub. É ela que painel.js confere a cada minuto. */
export const lerPresenca = () =>
  ler("hub_presenca", { select: "licenca_id,maquina,visto_em,online_desde,versao,versao_desde" });

export async function carregarGestao(agora = new Date()) {
  const [clientes, ativacoes, presencas, liberacoes, lancamentos, versoes, gestao, faixas, aparelhos, testes,
         produtos, mensalidades] = await Promise.all([
    ler("painel_clientes", { ordem: "nome.asc" }),
    ler("ativacoes", { select: "id,licenca_id,maquina,apelido,versao,versao_em,ultima_checagem,ativado_em" }),
    lerPresenca(),
    ler("hub_liberacoes"),
    ler("hub_lancamentos", { ordem: "criado_em.desc" }),
    ler("hub_versoes", { limite: 1 }),
    ler("painel_gestao"),
    ler("painel_uso_por_cliente").catch(() => []),
    ler("celular_aparelhos", { select: "licenca_id,revogado_em" }),
    ler("painel_testes", { select: "licenca_id,codigo,comprou,iniciado_em,termina_em" }).catch(() => []),
    ler("produtos", { ordem: "codigo.asc" }),
    // sem a migration da mensalidade a lista abre igual, sem a coluna do plano
    ler("painel_mensalidades", { ordem: "criado_em.desc" }).catch(() => []),
  ]);

  const atual = versoes?.[0] || null;
  const publicada = String(atual?.versao || "");
  const forcadaGeral = Boolean(atual?.forcada);
  const alvo = versaoAlvo(lancamentos, publicada);
  const linhas = montarClientes({
    clientes, ativacoes, presencas, liberacoes, gestao, faixas, aparelhos, testes, publicada, forcadaGeral, alvo,
    mensalidades,
    catalogo: produtos.filter((p) => p.ativo).map((p) => p.codigo),
  }, agora);

  return {
    linhas, lancamentos, liberacoes, atual, publicada, forcadaGeral, alvo, mensalidades,
    pendente: versaoPendente(lancamentos, publicada),
  };
}
