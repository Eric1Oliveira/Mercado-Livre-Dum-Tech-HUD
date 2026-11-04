// Textos do site: todo texto da pagina inicial, com rascunho e publicar.
//
//   Salvar rascunho  guarda no banco; o site nao muda
//   Ver como fica    abre o site com o rascunho (vai pelo armazenamento deste
//                    navegador: o painel e o site moram no mesmo endereco)
//   Publicar         o site passa a mostrar, para todo mundo, na hora
//   Versoes          cada publicacao fica guardada; da para voltar a qualquer uma
//
// Os textos padrao (e a regra de tamanho de cada campo) sao os do proprio
// site: /js/conteudo.js. Tudo vai para a pagina como texto puro.

import { atualizar, ler, rpc } from "../api.js";
import { dataHora } from "../formato.js";
import { recarregar } from "../painel.js";
import { agir, cartao, confirmar, el, vazio } from "../ui.js";

const FALTA_MIGRATION =
  "Rode a migration 20261104120000_controle_mensalidade.sql no Supabase (npx supabase db push) para ver esta tela.";

/** A pagina, na ordem em que o visitante le. [caminho, rotulo, "longo"?] */
const SECOES = [
  { titulo: "Abertura", campos: [
      ["hero.rotulo", "Rótulo acima do título"], ["hero.titulo", "Título"],
      ["hero.chamada", "Frase de abertura", "longo"], ["hero.nota", "Nota abaixo dos botões", "longo"]],
    listas: [["fatos", "Os fatos abaixo da abertura", "texto"]] },
  { titulo: "O programa (plano base)", campos: [
      ["base.rotulo", "Rótulo"], ["base.titulo", "Título"], ["base.texto", "Texto", "longo"],
      ["modulos.VENDAS.frase", "Vendas: frase"], ["modulos.VENDAS.detalhe", "Vendas: detalhe", "longo"],
      ["modulos.ESTOQUE.frase", "Estoque: frase"], ["modulos.ESTOQUE.detalhe", "Estoque: detalhe", "longo"],
      ["modulos.FINANCEIRO.frase", "Financeiro: frase"], ["modulos.FINANCEIRO.detalhe", "Financeiro: detalhe", "longo"]] },
  { titulo: "O plano", campos: [
      ["plano.rotulo", "Rótulo"], ["plano.titulo", "Título"], ["plano.texto", "Texto", "longo"],
      ["modulos.CLIENTES.frase", "Clientes: frase"], ["modulos.ORCAMENTOS.frase", "Orçamentos: frase"],
      ["modulos.ORDENS.frase", "Ordem de Serviço: frase"], ["modulos.AGENDA.frase", "Agenda: frase"]],
    listas: [["inclui", "O que vem em todo plano", "texto"]] },
  { titulo: "Como começar", campos: [["como.rotulo", "Rótulo"], ["como.titulo", "Título"]],
    listas: [["passos", "Os passos", ["titulo", "texto"]]] },
  { titulo: "Comece agora (cadastro)", campos: [["comecar.rotulo", "Rótulo"], ["comecar.titulo", "Título"]] },
  { titulo: "Dúvidas", campos: [["duvidas.rotulo", "Rótulo"], ["duvidas.titulo", "Título"]],
    listas: [["duvidas.itens", "Perguntas e respostas", ["pergunta", "resposta"]]] },
  { titulo: "Contato", campos: [
      ["contato.titulo", "Título"], ["contato.texto", "Texto", "longo"],
      ["whatsapp", "WhatsApp da DumTech (55 + DDD + número)"]] },
];
const ROTULOS_DO_ITEM = { titulo: "Título", texto: "Texto", pergunta: "Pergunta", resposta: "Resposta" };

const pegar = (objeto, caminho) => caminho.split(".").reduce((atual, chave) => atual?.[chave], objeto);
function colocar(objeto, caminho, valor) {
  const chaves = caminho.split(".");
  const ultima = chaves.pop();
  const alvo = chaves.reduce((atual, chave) => (atual[chave] ??= {}), objeto);
  alvo[ultima] = valor;
}

export async function textosSite(alvo) {
  const [site, linhas, versoes] = await Promise.all([
    import("/js/conteudo.js").catch(() => null),
    ler("landing_conteudo", { fresco: true }).catch(() => null),
    ler("landing_publicacoes", { ordem: "publicado_em.desc", limite: 8 }).catch(() => []),
  ]);
  const cabeca = el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Textos do site" }),
      el("p", { texto: "Todo texto da página inicial. Edite à vontade, veja como fica e publique quando gostar: " +
                       "até publicar, o site não muda." }),
    ]),
  ]);
  if (!linhas) {
    alvo.append(cabeca, cartao("", vazio("O banco ainda não tem os textos do site", FALTA_MIGRATION)));
    return;
  }
  if (!site) {
    alvo.append(cabeca, cartao("", vazio("Não encontrei os textos padrão do site",
      "O painel lê /js/conteudo.js do próprio site. Abra o painel pelo endereço publicado (dumtechsolution.com/painel).")));
    return;
  }

  const doBanco = (id) => linhas.find((l) => l.id === id)?.conteudo ?? {};
  const publicado = site.mesclar(doBanco("publicado"));
  const estado = structuredClone(site.mesclar(doBanco("rascunho")));
  const iguais = () => JSON.stringify(site.mesclar(estado)) === JSON.stringify(publicado);
  const situacao = el("p", { classe: "dica" });
  const marcar = () => {
    situacao.textContent = iguais()
      ? "O rascunho está igual ao que está no ar."
      : "Você tem alterações que ainda não foram publicadas.";
  };

  // ---------------------------------------------------------- campos
  const campoDeTexto = (caminho, rotulo, longo) => {
    const entrada = el(longo ? "textarea" : "input", longo ? {} : { type: "text" });
    entrada.value = pegar(estado, caminho) ?? "";
    entrada.addEventListener("input", () => { colocar(estado, caminho, entrada.value); marcar(); });
    return el("label", { classe: "campo" }, [el("span", { texto: rotulo }), entrada]);
  };

  const editorDeLista = (caminho, rotulo, forma) => {
    const caixa = el("div", { classe: "campo" });
    const desenhar = () => {
      const itens = pegar(estado, caminho) ?? [];
      const mover = (de, para) => {
        if (para < 0 || para >= itens.length) return;
        const [item] = itens.splice(de, 1);
        itens.splice(para, 0, item);
        marcar();
        desenhar();
      };
      caixa.replaceChildren(
        el("span", { texto: rotulo }),
        ...itens.map((item, i) => {
          const entradas = forma === "texto"
            ? [(() => {
                const e = el("input", { type: "text", value: item });
                e.addEventListener("input", () => { itens[i] = e.value; marcar(); });
                return e;
              })()]
            : forma.map((chave) => {
                const longo = chave === "resposta" || chave === "texto";
                const e = el(longo ? "textarea" : "input", longo ? { placeholder: ROTULOS_DO_ITEM[chave] }
                                                              : { type: "text", placeholder: ROTULOS_DO_ITEM[chave] });
                e.value = item[chave] ?? "";
                e.addEventListener("input", () => { item[chave] = e.value; marcar(); });
                return e;
              });
          const mini = (texto, titulo, fazer) => el("button", { type: "button", classe: "botao botao-fantasma botao-mini",
                                                                texto, title: titulo, onclick: fazer });
          return el("div", { estilo: "display:grid;grid-template-columns:1fr auto;gap:8px;align-items:start;" +
                                      "padding:10px;border:1px solid var(--fio);border-radius:10px" }, [
            el("div", { estilo: "display:grid;gap:6px" }, entradas),
            el("div", { classe: "acoes-linha", estilo: forma === "texto" ? "flex-wrap:nowrap" : "flex-direction:column" }, [
              mini("↑", "Subir", () => mover(i, i - 1)),
              mini("↓", "Descer", () => mover(i, i + 1)),
              mini("✕", "Tirar", () => { itens.splice(i, 1); marcar(); desenhar(); }),
            ]),
          ]);
        }),
        el("button", { type: "button", classe: "botao botao-fantasma", texto: "+ Acrescentar",
          onclick: () => {
            itens.push(forma === "texto" ? "" : Object.fromEntries(forma.map((c) => [c, ""])));
            colocar(estado, caminho, itens);
            marcar();
            desenhar();
          } }),
      );
    };
    desenhar();
    return caixa;
  };

  // ---------------------------------------------------------- acoes
  const salvarRascunho = () => atualizar("landing_conteudo", { id: "eq.rascunho" }, { conteudo: estado });
  const verComoFica = (e) => agir(e.target, async () => {
    await salvarRascunho();
    try {
      localStorage.setItem(site.CHAVE_PREVIA, JSON.stringify({ conteudo: estado, quando: Date.now() }));
    } catch {
      throw new Error("Este navegador não deixou guardar a pré-visualização.");
    }
    window.open("/?previa=1#topo", "_blank", "noopener");
  }, { feito: "Rascunho salvo. A pré-visualização abriu em outra aba.", erro: "Não deu para abrir a pré-visualização." });
  const publicar = (e) => {
    if (!confirmar("Publicar estes textos? O site passa a mostrar na hora, para todo mundo.")) return;
    agir(e.target, async () => {
      await salvarRascunho();
      await rpc("dumtech_publicar_landing");
      try { localStorage.removeItem(site.CHAVE_PREVIA); } catch { /* nada */ }
      await recarregar();
    }, { feito: "Publicado. O site já mostra os textos novos.", erro: "Não deu para publicar." });
  };
  const descartar = (e) => {
    if (!confirmar("Descartar as alterações e voltar o rascunho para o que está no ar?")) return;
    agir(e.target, async () => {
      await atualizar("landing_conteudo", { id: "eq.rascunho" }, { conteudo: doBanco("publicado") });
      await recarregar();
    }, { feito: "Rascunho igual ao que está no ar.", erro: "Não deu para descartar." });
  };
  const voltar = (versao, botao) => {
    if (!confirmar(`Voltar o site para a versão de ${dataHora(versao.publicado_em)}? Ela vai ao ar na hora.`)) return;
    agir(botao, async () => {
      const r = await rpc("dumtech_voltar_landing", { p_publicacao: versao.id });
      if (r && r.ok === false) throw new Error(r.mensagem);
      await recarregar();
    }, { feito: "Pronto: o site voltou para essa versão.", erro: "Não deu para voltar." });
  };

  marcar();
  const barra = el("div", { classe: "acoes-linha" }, [
    el("button", { classe: "botao botao-fantasma", texto: "Salvar rascunho",
      onclick: (e) => agir(e.target, salvarRascunho, { feito: "Rascunho salvo. O site ainda não mudou." }) }),
    el("button", { classe: "botao botao-fantasma", texto: "Ver como fica", onclick: verComoFica }),
    el("button", { classe: "botao botao-primario", texto: "Publicar", onclick: publicar }),
    el("button", { classe: "botao botao-fantasma", texto: "Descartar alterações", onclick: descartar }),
  ]);

  alvo.append(
    cabeca,
    cartao("", el("div", { estilo: "display:grid;gap:10px" }, [
      barra,
      situacao,
      el("p", { classe: "dica", texto: "Marcadores que se trocam sozinhos: {preco_base} (o preço da base), " +
                                      "{dias_teste} (os dias de teste) e {computadores} (\"1 computador\")." }),
    ])),
    ...SECOES.map((secao) => cartao(secao.titulo, el("div", { estilo: "display:grid;gap:14px" }, [
      ...secao.campos.map(([caminho, rotulo, longo]) => campoDeTexto(caminho, rotulo, longo === "longo")),
      ...(secao.listas ?? []).map(([caminho, rotulo, forma]) => editorDeLista(caminho, rotulo, forma)),
    ]))),
    cartao("Versões publicadas", versoes.length
      ? el("ol", { estilo: "list-style:none;margin:0;padding:0;display:grid;gap:10px" }, versoes.map((v, i) =>
          el("li", { classe: "acoes-linha", estilo: "justify-content:space-between" }, [
            el("span", { texto: `${dataHora(v.publicado_em)}${i === 0 ? " · no ar agora" : ""}` }),
            i === 0 ? null : el("button", { type: "button", classe: "botao botao-fantasma botao-mini",
              texto: "Voltar para esta", onclick: (e) => voltar(v, e.currentTarget) }),
          ])))
      : vazio("Nada publicado ainda", "Enquanto isso, o site mostra os textos padrão.")),
  );
}
