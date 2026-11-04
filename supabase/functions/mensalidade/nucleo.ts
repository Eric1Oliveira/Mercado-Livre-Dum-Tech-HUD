// O coracao da Edge Function `mensalidade` (sem Deno, sem rede: banco e e-mail
// entram por parametro). Testado em supabase/functions/tests/mensalidade.test.mjs.
//
//   cadastro  o site: teste gratis e pedido de assinatura. A chave vai SO por
//             e-mail, e a resposta ao navegador e a mesma para todo mundo -
//             nao da para descobrir quem ja e cliente digitando um e-mail.
//   admin     o painel: confirmar, descartar, cobranca falhou, em dia,
//             cancelou e estender teste. O banco decide se quem chamou e admin
//             (a funcao chama com o token dele), e cada acao manda o seu e-mail.
//
// Os e-mails falam com o dono de um pequeno negocio: frases completas, o que
// muda para ele, nenhum termo tecnico.

import { emailValido, uuidValido } from "../enviar-chave/nucleo.ts";

export type Carta = { assunto: string; texto: string; html: string };
type Envio = Carta & { para: string };
export type Rpc = (funcao: string, parametros: Record<string, unknown>) => Promise<any>;
/** rpc com o token de quem chamou: o status importa (403 = nao e admin). */
export type RpcDoChamador = (funcao: string, parametros: Record<string, unknown>) =>
  Promise<{ status: number; dados: any }>;

export type Ambiente = {
  site: string;        // https://dumtechsolution.com (sem barra no fim)
  whatsapp: string;    // 5511978042160
  rpc: Rpc;            // service_role
  enviarEmail?: (carta: Envio) => Promise<boolean>;
};

type Resposta = { status: number; corpo: Record<string, unknown> };
type Dados = Record<string, any>;

const NOMES: Record<string, string> = {
  VENDAS: "Vendas", ESTOQUE: "Estoque", FINANCEIRO: "Financeiro",
  AGENDA: "Agenda", CLIENTES: "Clientes", ORCAMENTOS: "Orçamentos", ORDENS: "Ordem de Serviço",
};
const ADICIONAIS = new Set(["AGENDA", "CLIENTES", "ORCAMENTOS", "ORDENS"]);
const CODIGO = /^[A-Z][A-Z0-9_]{1,30}$/;
const DATA = /^\d{4}-\d{2}-\d{2}$/;

export function rotaDe(caminho: string): "cadastro" | "admin" | "" {
  const fim = caminho.replace(/\/+$/, "").split("/").pop() ?? "";
  return fim === "cadastro" || fim === "admin" ? fim : "";
}

// ================================================================ cadastro ==
export async function cadastro(amb: Ambiente, corpo: Dados, ip: string): Promise<Resposta> {
  const nome = String(corpo.nome ?? "").trim().replace(/\s+/g, " ").slice(0, 120);
  const email = String(corpo.email ?? "").trim().toLowerCase();
  const telefone = String(corpo.whatsapp ?? "").replace(/\D/g, "").slice(0, 20);
  const adicionais = Array.isArray(corpo.adicionais)
    ? [...new Set(corpo.adicionais.slice(0, 10).map((c: unknown) => String(c).trim().toUpperCase()))]
        .filter((c) => ADICIONAIS.has(c))
    : [];
  const assinar = corpo.assinar === true;
  const plano = corpo.plano == null || corpo.plano === "" ? null : String(corpo.plano);
  const cupom = String(corpo.cupom ?? "").trim().toUpperCase();

  if (!nome) return recusa(400, "nome", "Conte para a gente o seu nome ou o da sua empresa.");
  if (!emailValido(email) || email.length > 160) {
    return recusa(400, "email_invalido", "Confira o e-mail digitado: é por ele que a sua chave chega.");
  }
  if (telefone && telefone.length < 10) {
    return recusa(400, "whatsapp", "Confira o WhatsApp: coloque o DDD e o número.");
  }
  if (plano !== null && !uuidValido(plano)) {
    return recusa(400, "plano", "Esse plano não está mais disponível. Escolha outro, por favor.");
  }
  if (cupom && !/^[A-Z0-9_-]{3,32}$/.test(cupom)) {
    return recusa(400, "cupom", "Confira o código do cupom: só letras, números e traço.");
  }
  if (!amb.enviarEmail) {
    return recusa(501, "email", "O envio de e-mail ainda não está ligado. Chame a DumTech no WhatsApp.");
  }

  const dados = await amb.rpc("dumtech_cadastrar_mensal", {
    p_nome: nome, p_email: email, p_telefone: telefone, p_adicionais: adicionais,
    p_assinar: assinar, p_ip: ip, p_plano: plano, p_cupom: cupom,
  });
  if (!dados) return recusa(502, "servidor", "Não conseguimos falar com a DumTech agora. Tente de novo em instantes.");
  if (!dados.ok) {
    return recusa(dados.erro === "muitas_tentativas" ? 429 : 400, String(dados.erro ?? "erro"),
                  String(dados.mensagem ?? "Não deu para concluir o cadastro."));
  }

  const montar = dados.caso === "vitalicio" ? cartas.vitalicio
    : dados.caso === "ja_tem" ? cartas.jaTem : cartas.boasVindas;
  const entregue = await amb.enviarEmail({ para: email, ...montar(dados, amb) });
  if (!entregue) {
    return recusa(502, "email", "Não conseguimos enviar o e-mail agora. Tente de novo em alguns minutos.");
  }

  // a MESMA resposta para todos os casos: o que muda vai so no e-mail
  return {
    status: 200,
    corpo: {
      ok: true,
      assinar: dados.assinar === true,
      link: dados.assinar === true ? String(dados.link ?? "") : "",
      valor: dados.assinar === true ? Number(dados.valor ?? 0) : null,
      dias_teste: Number(dados.dias_teste ?? 7),
    },
  };
}

// =================================================================== admin ==
type Acao = { funcao: string; id: "pedido" | "licenca"; parametros: (c: Dados) => Dados;
              carta: ((d: Dados, amb: Ambiente) => Carta) | null };

const ACOES: Record<string, Acao> = {
  confirmar: { funcao: "dumtech_confirmar_assinatura", id: "pedido",
               parametros: (c) => ({ p_pedido: c.pedido }),
               carta: (d, amb) => (d.mudanca ? cartas.planoMudou : cartas.confirmada)(d, amb) },
  descartar: { funcao: "dumtech_descartar_assinatura", id: "pedido",
               parametros: (c) => ({ p_pedido: c.pedido }), carta: null },
  falhou:    { funcao: "dumtech_cobranca", id: "licenca",
               parametros: (c) => ({ p_licenca: c.licenca, p_acao: "falhou", p_ate: null }),
               carta: (d, amb) => cartas.falhou(d, amb) },
  em_dia:    { funcao: "dumtech_cobranca", id: "licenca",
               parametros: (c) => ({ p_licenca: c.licenca, p_acao: "em_dia", p_ate: null }),
               carta: (d, amb) => cartas.emDia(d, amb) },
  cancelou:  { funcao: "dumtech_cobranca", id: "licenca",
               parametros: (c) => ({ p_licenca: c.licenca, p_acao: "cancelou",
                                     p_ate: /^\d{4}-\d{2}-\d{2}$/.test(String(c.ate ?? "")) ? c.ate : null }),
               carta: (d, amb) => cartas.cancelou(d, amb) },
  ajustar:   { funcao: "dumtech_ajustar_assinatura", id: "licenca",
               parametros: (c) => ({ p_licenca: c.licenca, p_plano: c.plano ?? null, p_modulos: c.modulos ?? null,
                                     p_valor: c.valor ?? null, p_computadores: c.computadores ?? null,
                                     p_ate: c.ate ?? null, p_observacoes: c.observacoes ?? null }),
               carta: (d, amb) => cartas.ajustado(d, amb) },
  ativar:    { funcao: "dumtech_ativar_assinatura", id: "licenca",
               parametros: (c) => ({ p_licenca: c.licenca, p_plano: c.plano ?? null, p_modulos: c.modulos ?? null,
                                     p_valor: c.valor ?? null }),
               carta: (d, amb) => cartas.confirmada(d, amb) },
  reabrir:   { funcao: "dumtech_reabrir_assinatura", id: "licenca",
               parametros: (c) => ({ p_licenca: c.licenca }),
               carta: (d, amb) => cartas.reaberta(d, amb) },
  estender:  { funcao: "dumtech_estender_teste_mensal", id: "licenca",
               parametros: (c) => ({ p_licenca: c.licenca,
                                     p_dias: Number.isInteger(c.dias) ? c.dias : 7 }),
               carta: (d, amb) => cartas.estendido(d, amb) },
};

export async function admin(amb: Ambiente, corpo: Dados, rpcDoChamador: RpcDoChamador | null): Promise<Resposta> {
  if (!rpcDoChamador) return recusa(401, "sem_sessao", "Entre no painel de novo.");
  const acao = ACOES[String(corpo.acao ?? "")];
  if (!acao) return recusa(400, "acao", "Ação desconhecida.");
  if (!uuidValido(corpo[acao.id])) return recusa(400, "pedido_invalido", "Pedido inválido.");
  const torto = problemaNaFicha(corpo);
  if (torto) return recusa(400, "dado_invalido", torto);

  const { status, dados } = await rpcDoChamador(acao.funcao, acao.parametros(corpo));
  if (status === 401 || status === 403 || dados?.code === "42501") {
    return recusa(403, "sem_acesso", "Só a DumTech faz isso.");
  }
  if (status >= 400 || !dados) return recusa(502, "servidor", "O banco não respondeu. Tente de novo.");
  if (!dados.ok) return recusa(400, String(dados.erro ?? "erro"), String(dados.mensagem ?? "Não deu certo."));

  let emailEnviado = false;
  if (acao.carta && corpo.avisar !== false && interessaAoCliente(String(corpo.acao), dados)
      && amb.enviarEmail && emailValido(dados.email)) {
    emailEnviado = await amb.enviarEmail({ para: String(dados.email), ...acao.carta(dados, amb) });
  }
  return { status: 200, corpo: { ...dados, ok: true, email_enviado: emailEnviado } };
}

/** O que vem do painel para a ficha, conferido antes do banco. Vazio = tudo certo. */
function problemaNaFicha(c: Dados): string {
  if (c.plano != null && !uuidValido(c.plano)) return "Plano inválido.";
  if (c.modulos != null && (!Array.isArray(c.modulos) || c.modulos.length > 20
                            || !c.modulos.every((m: unknown) => CODIGO.test(String(m).toUpperCase())))) {
    return "Módulos inválidos.";
  }
  if (c.valor != null && (typeof c.valor !== "number" || !Number.isFinite(c.valor) || c.valor < 0)) {
    return "Confira o valor do mês.";
  }
  if (c.computadores != null && (!Number.isInteger(c.computadores) || c.computadores < 1 || c.computadores > 50)) {
    return "Escolha de 1 a 50 computadores.";
  }
  if (c.ate != null && !DATA.test(String(c.ate))) return "Confira a data.";
  if (c.observacoes != null && (typeof c.observacoes !== "string" || c.observacoes.length > 2000)) {
    return "As anotações passaram do tamanho.";
  }
  return "";
}

/** Ajuste so de anotacao e assunto interno: o cliente nao precisa de e-mail. */
function interessaAoCliente(acao: string, dados: Dados): boolean {
  if (acao !== "ajustar") return true;
  return Object.keys(dados.mudou ?? {}).some((k) => ["modulos", "plano", "valor", "computadores", "ate"].includes(k));
}

function recusa(status: number, erro: string, mensagem: string): Resposta {
  return { status, corpo: { ok: false, erro, mensagem } };
}

// ================================================================== textos ==
const escapar = (texto: unknown) =>
  String(texto ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);

function dataCurta(valor: unknown): string {
  const [ano, mes, dia] = String(valor ?? "").slice(0, 10).split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : "";
}

const dinheiro = (valor: unknown) =>
  `R$ ${Number(valor ?? 0).toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, ".")}`;

function primeiroNome(nome: unknown): string {
  return String(nome ?? "").trim().split(/\s+/)[0] ?? "";
}

function telefoneLegivel(whatsapp: string): string {
  const d = whatsapp.replace(/\D/g, "").replace(/^55/, "");
  return d.length === 11 ? `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}` : whatsapp;
}

/** "Agenda e Ordem de Serviço" */
function lista(codigos: unknown): string {
  const nomes = (Array.isArray(codigos) ? codigos : []).map((c) => NOMES[String(c)]).filter(Boolean);
  return nomes.length <= 1 ? (nomes[0] ?? "") : `${nomes.slice(0, -1).join(", ")} e ${nomes.at(-1)}`;
}

/** "Salão (Agenda, Clientes e Financeiro)", ou os modulos montados, ou a base + adicionais. */
function plano(dados: Dados): string {
  const modulos = Array.isArray(dados.modulos) && dados.modulos.length ? lista(dados.modulos) : "";
  if (dados.plano) return modulos ? `${dados.plano} (${modulos})` : String(dados.plano);
  if (modulos) return modulos;
  const extras = lista(dados.adicionais);
  return extras ? `Vendas, Estoque e Financeiro, mais ${extras}` : "Vendas, Estoque e Financeiro";
}

type Bloco = { p?: string; chave?: string; botao?: { texto: string; link: string }; passos?: string[] };

/** Monta o texto puro e o HTML a partir dos mesmos blocos (assim os dois nunca divergem). */
function carta(amb: Ambiente, dados: Dados, assunto: string, titulo: string, blocos: Bloco[]): Carta {
  const nome = primeiroNome(dados.nome);
  const ola = nome ? `Olá, ${nome}!` : "Olá!";
  const contato = `Qualquer dúvida, é só responder este e-mail ou chamar a gente no WhatsApp: ${telefoneLegivel(amb.whatsapp)}.`;

  const texto: string[] = [ola, ""];
  for (const b of blocos) {
    if (b.p) texto.push(b.p, "");
    if (b.chave) texto.push(`Sua chave: ${b.chave}`, "");
    if (b.passos) texto.push(...b.passos.map((passo, i) => `${i + 1}. ${passo}`), "");
    if (b.botao) texto.push(`${b.botao.texto}: ${b.botao.link}`, "");
  }
  texto.push(contato, "", "Equipe DumTech");

  const corpo = blocos.map((b) => {
    if (b.p) return `<p style="margin:0 0 14px">${escapar(b.p)}</p>`;
    if (b.chave) {
      return `<div style="font-size:12px;color:#75758a;margin:4px 0 6px">Sua chave</div>
<div style="font-family:Consolas,monospace;font-size:22px;font-weight:700;letter-spacing:.06em;background:#f1effe;color:#3b2aa8;border-radius:10px;padding:14px 16px;text-align:center;margin:0 0 16px">${escapar(b.chave)}</div>`;
    }
    if (b.passos) {
      return `<ol style="margin:0 0 16px;padding-left:20px">${b.passos.map((passo) => `<li style="margin:0 0 6px">${escapar(passo)}</li>`).join("")}</ol>`;
    }
    if (b.botao) {
      return `<p style="margin:4px 0 18px"><a href="${escapar(b.botao.link)}" style="display:inline-block;background:#7353F6;color:#ffffff;text-decoration:none;font-weight:700;border-radius:10px;padding:12px 20px">${escapar(b.botao.texto)}</a></p>`;
    }
    return "";
  }).join("\n");

  const html = `<!doctype html><html lang="pt-BR"><body style="margin:0;background:#f6f6f9;font-family:Segoe UI,Arial,sans-serif;color:#1d1d29">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:540px;background:#ffffff;border:1px solid #e6e6ee;border-radius:16px">
<tr><td style="padding:28px 28px 6px"><div style="font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#7353F6">DumTech</div>
<h1 style="margin:10px 0 0;font-size:22px;line-height:1.3">${escapar(titulo)}</h1></td></tr>
<tr><td style="padding:18px 28px 26px;font-size:15px;line-height:1.6;color:#3a3a4c">
<p style="margin:0 0 14px">${escapar(ola)}</p>
${corpo}
<p style="margin:8px 0 0;color:#5a5a6e">${escapar(contato)}</p>
<p style="margin:14px 0 0;color:#5a5a6e">Equipe DumTech</p></td></tr>
</table></td></tr></table></body></html>`;

  return { assunto, texto: texto.join("\n"), html };
}

function blocoDaAssinatura(dados: Dados, amb: Ambiente): Bloco[] {
  if (dados.assinar !== true) return [];
  const resumo = `Você também pediu para assinar o plano ${plano(dados)}, por ${dinheiro(dados.valor)} por mês.`;
  if (!dados.link) {
    return [{ p: `${resumo} A gente vai chamar você no WhatsApp para combinar o pagamento, combinado?` }];
  }
  return [
    { p: `${resumo} Se ainda não concluiu o pagamento, é por este link, com Pix ou cartão:` },
    { botao: { texto: "Concluir a assinatura", link: String(dados.link) } },
    { p: "Assim que a InfinitePay confirmar, a gente libera a sua assinatura e avisa você por aqui. Enquanto isso, pode usar o programa normalmente." },
  ];
}

const passosParaComecar = (amb: Ambiente) => [
  `Baixe o DumTech Hub para Windows: ${amb.site}/baixar/`,
  "Abra o programa, informe o seu nome e o seu e-mail e cole a chave quando ele pedir.",
  "Pronto: os módulos aparecem na hora, e tudo funciona mesmo sem internet.",
];

export const cartas = {
  boasVindas(dados: Dados, amb: Ambiente): Carta {
    const dias = Number(dados.dias_teste ?? 7);
    return carta(amb, dados, "Seu teste grátis da DumTech começou", "Seu teste grátis começou!", [
      { p: `Que bom ter você por aqui. O seu teste do DumTech Hub já está liberado: são ${dias} dias com todos os módulos, sem cartão e sem compromisso.` },
      { chave: String(dados.chave ?? "") },
      { p: "Para começar é bem simples:" },
      { passos: passosParaComecar(amb) },
      { p: `O seu teste vai até ${dataCurta(dados.ate)}. Até lá, use à vontade: tudo o que você lançar fica guardado no seu computador.` },
      ...blocoDaAssinatura(dados, amb),
    ]);
  },

  jaTem(dados: Dados, amb: Ambiente): Carta {
    return carta(amb, dados, "A sua chave da DumTech", "Aqui está a sua chave", [
      { p: "Recebemos um pedido no site com este e-mail, e você já tem uma chave da DumTech. Ela continua a mesma:" },
      { chave: String(dados.chave ?? "") },
      { p: "Para usar, abra o DumTech Hub, entre em Licença, cole a chave e clique em Ativar. Se ainda não tem o programa, baixe aqui:" },
      { botao: { texto: "Baixar o DumTech Hub", link: `${amb.site}/baixar/` } },
      ...blocoDaAssinatura(dados, amb),
      { p: "Se não foi você que fez esse pedido, pode ignorar este e-mail tranquilamente." },
    ]);
  },

  vitalicio(dados: Dados, amb: Ambiente): Carta {
    return carta(amb, dados, "A sua licença DumTech continua sendo para sempre", "A sua licença continua sendo para sempre", [
      { p: "Recebemos um pedido no site com este e-mail e queremos tranquilizar você: a sua licença DumTech é vitalícia e continua valendo para sempre, sem mensalidade." },
      { p: "Você não precisa assinar nada nem pagar nada. As atualizações continuam chegando normalmente." },
      { p: "Quer mais um módulo? É só chamar a gente no WhatsApp, que a gente libera na mesma chave que você já usa." },
      { botao: { texto: "Falar com a DumTech", link: `https://wa.me/${amb.whatsapp}` } },
      { p: "Se não foi você que fez esse pedido, pode ignorar este e-mail." },
    ]);
  },

  confirmada(dados: Dados, amb: Ambiente): Carta {
    return carta(amb, dados, "Sua assinatura DumTech está confirmada", "Sua assinatura está confirmada!", [
      { p: "Recebemos o seu pagamento e a sua assinatura está ativa. Muito obrigado pela confiança!" },
      { p: `O seu plano: ${plano(dados)}, por ${dinheiro(dados.valor)} por mês, cobrado pela InfinitePay.` },
      { p: "Você não precisa fazer nada: em alguns minutos o DumTech Hub se atualiza sozinho com o seu plano. Se quiser ver na hora, abra Licença e clique em Verificar licença." },
      { p: `A sua chave continua a mesma: ${String(dados.chave ?? "")}.` },
    ]);
  },

  planoMudou(dados: Dados, amb: Ambiente): Carta {
    return carta(amb, dados, "O seu plano DumTech foi atualizado", "O seu plano foi atualizado", [
      { p: "A mudança que você pediu já está valendo. Obrigado por continuar com a gente!" },
      { p: `O seu plano agora: ${plano(dados)}, por ${dinheiro(dados.valor)} por mês.` },
      { p: "Em alguns minutos o DumTech Hub mostra os módulos novos sozinho. Se quiser ver na hora, abra Licença e clique em Verificar licença." },
    ]);
  },

  falhou(dados: Dados, amb: Ambiente): Carta {
    return carta(amb, dados, "Não conseguimos confirmar a sua mensalidade", "Um aviso sobre a sua mensalidade", [
      { p: "Passando para avisar, com calma: não conseguimos confirmar o pagamento da sua mensalidade da DumTech. Às vezes é só um cartão que venceu ou foi trocado." },
      { p: `Nada muda por enquanto: o DumTech Hub continua funcionando normalmente até ${dataCurta(dados.ate)}.` },
      { p: "Para resolver, confira o pagamento no app ou no link da InfinitePay, ou chame a gente no WhatsApp que a gente resolve junto com você." },
      { p: "Se você já pagou, pode desconsiderar este aviso: assim que a confirmação chegar, está tudo certo." },
    ]);
  },

  emDia(dados: Dados, amb: Ambiente): Carta {
    return carta(amb, dados, "Tudo certo: sua mensalidade está em dia", "Tudo certo com a sua mensalidade", [
      { p: "Boa notícia: o pagamento da sua mensalidade foi confirmado e está tudo em dia. Obrigado!" },
      { p: "O DumTech Hub segue funcionando normalmente. Se ele estava só para consulta, volta a lançar sozinho em alguns minutos." },
    ]);
  },

  cancelou(dados: Dados, amb: Ambiente): Carta {
    return carta(amb, dados, "Sua assinatura DumTech foi encerrada", "Sua assinatura foi encerrada", [
      { p: `Confirmamos o encerramento da sua assinatura. O DumTech Hub funciona normalmente até ${dataCurta(dados.ate)}.` },
      { p: "Depois disso, ele fica só para consulta: você continua vendo e exportando tudo o que lançou, só não dá para lançar coisas novas. Os seus dados não se perdem e continuam no seu computador." },
      { p: "Se quiser voltar, é só assinar de novo: a sua chave continua a mesma. Obrigado por ter usado a DumTech!" },
    ]);
  },

  ajustado(dados: Dados, amb: Ambiente): Carta {
    const mudou = dados.mudou ?? {};
    const linhas: Bloco[] = [];
    if (mudou.modulos || mudou.plano) linhas.push({ p: `O seu plano agora: ${plano(dados)}.` });
    if (mudou.valor) linhas.push({ p: `O valor do mês passa a ser ${dinheiro(dados.valor)}.` });
    if (mudou.computadores) {
      const n = Number(dados.computadores);
      linhas.push({ p: `Você pode usar o DumTech Hub em até ${n} ${n === 1 ? "computador" : "computadores"}.` });
    }
    if (mudou.ate) linhas.push({ p: `O DumTech Hub funciona normalmente até ${dataCurta(dados.ate)}.` });
    return carta(amb, dados, "Atualizamos a sua assinatura DumTech", "Atualizamos a sua assinatura", [
      { p: "Passando para contar que fizemos um ajuste na sua assinatura da DumTech:" },
      ...linhas,
      { p: "Em alguns minutos o DumTech Hub se atualiza sozinho. Se quiser ver na hora, abra Licença e clique em Verificar licença." },
    ]);
  },

  reaberta(dados: Dados, amb: Ambiente): Carta {
    return carta(amb, dados, "Sua assinatura DumTech voltou a valer", "Que bom ter você de volta!", [
      { p: "A sua assinatura da DumTech voltou a valer, e o DumTech Hub segue funcionando normalmente." },
      { p: "Se ele estava só para consulta, volta a lançar sozinho em alguns minutos. A sua chave continua a mesma." },
    ]);
  },

  estendido(dados: Dados, amb: Ambiente): Carta {
    return carta(amb, dados, "Seu teste grátis ganhou mais dias", "Seu teste ganhou mais dias", [
      { p: `Liberamos mais alguns dias de teste para você: agora ele vai até ${dataCurta(dados.ate)}.` },
      { p: "Aproveite para conhecer tudo com calma. O DumTech Hub recebe a data nova sozinho em alguns minutos." },
    ]);
  },
};
