// Catálogo (módulos) e anúncios. Kits têm tela própria: telas/kits.js.
//
// O construtor de anúncios mostra, junto do formulário, o pop-up exatamente
// como ele aparece no Hub do cliente — escrever anúncio às cegas é como vender
// de olhos fechados.

import { apagar, atualizar, inserir, ler } from "../api.js";
import { contagem, data, dinheiro, numero } from "../formato.js";
import { abrirGaveta, fecharGaveta, recarregar } from "../painel.js";
import { modulo } from "../modulos.js";
import { montarAnuncio, situacaoAnuncio } from "../anuncios.js";
import {
  agir, cartao, confirmar, el, icone, limpar, pilula, pilulaModulo, recado, tabela,
} from "../ui.js";

// =============================================================== catálogo ====
export async function catalogo(alvo) {
  const [produtos, modulosPainel] = await Promise.all([
    ler("produtos", { ordem: "codigo.asc" }),
    ler("painel_modulos"),
  ]);
  const porCodigo = new Map(modulosPainel.map((m) => [m.codigo, m]));

  alvo.append(el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Catálogo" }),
      el("p", { texto: "Salvou aqui, o site mostra na hora — sem ninguém atualizar a página." }),
    ]),
    el("div", { classe: "ferramentas" }, [
      el("button", {
        classe: "botao botao-fantasma", texto: "Novo módulo",
        onclick: () => editarProduto(null),
      }),
    ]),
  ]));

  alvo.append(cartao("Módulos", tabela(
    ["Módulo", "Código", { texto: "Preço", numero: true }, { texto: "Clientes", numero: true },
     { texto: "Uso 30d", numero: true }, "À venda"],
    produtos,
    (p) => [
      pilulaModulo(p.codigo),
      el("code", { texto: p.codigo }),
      dinheiro(p.preco),
      numero(porCodigo.get(p.codigo)?.clientes || 0),
      numero(porCodigo.get(p.codigo)?.aberturas_30d || 0),
      p.ativo ? pilula("Sim", "ok") : pilula("Fora de linha", "neutro"),
    ],
    { aoClicar: (p) => editarProduto(p) }
  )));

  alvo.append(el("p", { classe: "rodape-entrada",
    texto: "Kits (pacotes com desconto) ficam na tela Kits, no menu ao lado." }));
}

function editarProduto(produto) {
  const novo = !produto;
  const campos = {
    codigo: campo("Código", produto?.codigo || "", { placeholder: "CRM", disabled: !novo }),
    nome: campo("Nome", produto?.nome || "", { placeholder: "DumTech CRM" }),
    descricao: campo("Descrição", produto?.descricao || ""),
    preco: campo("Preço (R$)", produto?.preco ?? 0, { type: "number", step: "0.01", min: "0" }),
    versao: campo("Versão", produto?.versao || ""),
  };
  const ativo = el("input", { type: "checkbox", checked: produto ? produto.ativo : true });

  const destino = abrirGaveta({
    acima: novo ? "Novo módulo" : "Módulo",
    titulo: novo ? "Cadastrar módulo" : produto.nome,
    conteudo: el("div", {}, [
      cartao("", [
        ...Object.values(campos).map((c) => c.no),
        el("label", { classe: "campo", estilo: "flex-direction:row;align-items:center;gap:8px" },
          [ativo, el("span", { texto: "À venda (aparece no site e pode entrar em licença nova)" })]),
        el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
          el("button", {
            classe: "botao botao-primario", texto: novo ? "Cadastrar" : "Salvar",
            onclick: (e) => {
              const dados = {
                nome: campos.nome.valor().trim(), descricao: campos.descricao.valor().trim(),
                preco: Number(campos.preco.valor()), versao: campos.versao.valor().trim(),
                ativo: ativo.checked,
              };
              const codigo = campos.codigo.valor().trim().toUpperCase();
              const problema = conferirItem(dados, novo ? codigo : produto.codigo);
              if (problema) return recado(problema, "erro");

              agir(e.target, async () => {
                if (novo) await inserir("produtos", { ...dados, codigo });
                else await atualizar("produtos", { id: `eq.${produto.id}` }, dados);
                fecharGaveta();
                await recarregar();
              }, { feito: "Catálogo atualizado. O site já mostra o novo valor." });
            },
          }),
          el("button", { classe: "botao botao-fantasma", texto: "Cancelar", onclick: fecharGaveta }),
        ]),
      ]),
      novo
        ? el("p", { classe: "nota-alerta", estilo: "margin-top:12px;font-size:.84rem",
            texto: "Atenção: cadastrar aqui não cria o módulo. Ele só abre no Hub depois que existir no programa " +
                   "(uma versão nova) e só aparece na loja depois de entrar na página. Deixe “À venda” desmarcado até lá." })
        : el("p", { classe: "rodape-entrada", estilo: "margin-top:12px",
            texto: "Módulo fora de linha continua funcionando para quem já comprou — só não entra em venda nova." }),
    ]),
  });
  return destino;
}

// =============================================================== anúncios ====
//
// COMO O ANÚNCIO CHEGA NO HUB — e por que esta tela insiste nisso.
//
// O anúncio tem UM canal só: um pop-up, na tela de Início do Hub, quatro
// segundos depois de o programa abrir. Ele aparece UMA VEZ por cliente e nunca
// mais: quem fechou não é interrompido de novo (`core/comunicados.py` guarda no
// computador dele os ids já mostrados).
//
// Esta tela já prometeu outra coisa — "aparece no Início, no bloco DumTech para
// você" — e a prévia desenhava esse bloco. O bloco foi tirado do Hub faz tempo
// (`hub/views/home_view.py`): quem publicava procurava no cliente uma coisa que
// não existe mais e concluía que o anúncio não tinha ido. Agora a prévia mostra
// o pop-up de verdade, e as regras estão escritas na tela em vez de no código.

//: a etiqueta do pop-up do Hub (IconBadge("tag") no AnuncioDialog)
const ICONE_TAG = "M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0l-7.2-7.2A2 2 0 0 1 2.8 12V4a1.2 1.2 0 0 1 1.2-1.2h8a2 2 0 0 1 1.4.6l7.2 7.2a2 2 0 0 1 0 2.8z M7.5 7.5h.01";

export async function anuncios(alvo) {
  const [comunicados, produtos] = await Promise.all([
    ler("comunicados", { ordem: "ordem.asc" }),
    ler("produtos", { ordem: "codigo.asc" }),
  ]);

  alvo.append(el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Anúncios" }),
      el("p", { texto: "Um pop-up no Hub do cliente, na tela de Início. Aparece uma vez para " +
                       "cada pessoa e não volta — quem já viu não é interrompido de novo." }),
    ]),
    el("div", { classe: "ferramentas" }, [
      el("button", {
        classe: "botao botao-primario", texto: "Novo anúncio",
        onclick: () => editarAnuncio(null, produtos),
      }),
    ]),
  ]));

  alvo.append(cartao("Como o anúncio chega em quem já é cliente", regrasDoAnuncio()));

  const noAr = comunicados.filter((c) => situacaoAnuncio(c).texto === "No ar").length;
  alvo.append(cartao(`${contagem(comunicados.length, "anúncio")} · ${noAr} no ar`, tabela(
    ["Título", "Alvo", "Período", { texto: "Ordem", numero: true }, "Situação"],
    comunicados,
    (c) => [
      el("div", {}, [
        el("div", { estilo: "font-weight:700", texto: c.titulo }),
        el("div", { estilo: "font-size:.8rem;color:var(--tinta-fraca)", texto: c.texto || "" }),
      ]),
      c.alvo === "sem_produto"
        ? el("div", { classe: "modulos-lista" },
            [el("span", { texto: "quem não tem " }), pilulaModulo(c.produto_codigo)])
        : pilula("Todos", "marca"),
      `${data(c.inicio)} → ${c.fim ? data(c.fim) : "sem fim"}`,
      numero(c.ordem),
      pilulaSituacaoAnuncio(c),
    ],
    { aoClicar: (c) => editarAnuncio(c, produtos), vazioTexto: "Nenhum anúncio ainda." }
  )));
}

const pilulaSituacaoAnuncio = (anuncio) => {
  const { texto, tom } = situacaoAnuncio(anuncio);
  return pilula(texto, tom);
};

/** As quatro regras do pop-up, ditas antes de alguém escrever o primeiro. */
function regrasDoAnuncio() {
  const regras = [
    ["Uma vez por pessoa",
     "Quem viu o pop-up — mesmo quem só fechou em “Agora não” — não vê de novo. " +
     "Editar o texto depois não faz o anúncio voltar para quem já viu."],
    ["Só na tela de Início",
     "Nunca por cima de alguém trabalhando dentro de um módulo, e no máximo um " +
     "por abertura do programa."],
    ["Em até 15 minutos",
     "É de quanto em quanto tempo o Hub pergunta por anúncios novos. Para quem " +
     "abrir o Hub depois de você publicar, é na hora."],
    ["Só para quem interessa",
     "O alvo “quem não tem um módulo” some sozinho para quem já comprou esse " +
     "módulo — ninguém recebe oferta do que já tem."],
  ];
  return el("div", { classe: "regras" }, regras.map(([titulo, texto]) =>
    el("div", {}, [el("strong", { texto: titulo }), el("p", { texto })])
  ));
}

function editarAnuncio(anuncio, produtos) {
  const novo = !anuncio;
  const campos = {
    rotulo: campo("Etiqueta", anuncio?.rotulo || "", { placeholder: "Oferta", maxlength: "24" }),
    titulo: campo("Título", anuncio?.titulo || "", { placeholder: "Leve o DumTech Vendas" }),
    texto: campo("Texto", anuncio?.texto || "", { tag: "textarea",
      placeholder: "Uma frase dizendo o que muda para ele." }),
    link: campo("Link do botão (opcional)", anuncio?.link || "", { placeholder: "https://…" }),
    inicio: campo("Começa em", (anuncio?.inicio || new Date().toISOString().slice(0, 10)), { type: "date" }),
    fim: campo("Termina em", anuncio?.fim || "", { type: "date" }),
    ordem: campo("Ordem", anuncio?.ordem ?? 0, { type: "number", min: "0" }),
  };
  const alvo = el("select", {}, [
    el("option", { value: "todos", texto: "Todos os clientes" }),
    el("option", { value: "sem_produto", texto: "Só quem NÃO tem um módulo" }),
  ]);
  alvo.value = anuncio?.alvo || "todos";
  const qualProduto = el("select", {}, produtos.map((p) =>
    el("option", { value: p.codigo, texto: modulo(p.codigo).nome })));
  if (anuncio?.produto_codigo) qualProduto.value = anuncio.produto_codigo;
  const ativo = el("input", { type: "checkbox", checked: anuncio ? anuncio.ativo : true });

  // ------------------------------------------------------------- prévia ----
  // Isto é o AnuncioDialog do Hub (`hub/views/anuncio_dialog.py`) desenhado em
  // HTML: a mesma etiqueta em cima, o mesmo título grande, os mesmos dois
  // botões. Escrever anúncio às cegas é vender de olhos fechados.
  const previa = el("div", {});
  const desenharPrevia = () => {
    const temLink = Boolean(campos.link.valor().trim());
    // o palco cinza é o que lembra que isto é uma JANELA por cima do trabalho
    // de alguém, não mais um cartão na página
    limpar(previa).append(el("div", { classe: "palco" }, [el("div", { classe: "popup" }, [
      el("div", { classe: "popup-topo" }, [
        el("span", { classe: "popup-selo" }, [icone(ICONE_TAG, 18)]),
        el("div", {}, [
          el("span", { classe: "pilula", "data-tom": "marca",
                       texto: (campos.rotulo.valor().trim() || "Novidade").toUpperCase() }),
          el("div", { classe: "popup-assinatura", texto: "DumTech para você" }),
        ]),
      ]),
      el("div", { classe: "popup-titulo",
                  texto: campos.titulo.valor().trim() || "Título do anúncio" }),
      el("div", { classe: "popup-texto",
                  texto: campos.texto.valor().trim() || "O texto aparece aqui, em uma ou duas linhas." }),
      el("div", { classe: "popup-botoes" }, [
        el("span", { classe: "popup-botao", texto: "Agora não" }),
        el("span", { classe: "popup-botao primario", texto: "Quero ver" }),
      ]),
    ])]));
    previa.append(el("p", { classe: "rodape-entrada",
      texto: temLink
        ? "“Quero ver” abre o endereço que você pôs no link."
        : "Sem link, “Quero ver” abre a nossa loja com o cliente já reconhecido." }));
  };
  for (const c of Object.values(campos)) c.no.addEventListener("input", desenharPrevia);
  desenharPrevia();

  const alvoProduto = el("div", { classe: "campo" }, [
    el("span", { texto: "Qual módulo" }), qualProduto,
  ]);
  const ajustarAlvo = () => { alvoProduto.hidden = alvo.value !== "sem_produto"; };
  alvo.addEventListener("change", ajustarAlvo);
  ajustarAlvo();

  // A recusa acontece ANTES de `agir`, como em todas as outras telas do painel.
  // Dentro dele, o recado de erro era apagado pelo "Anúncio salvo." que `agir`
  // pinta ao ver a ação terminar sem exceção — e o resultado era um botão
  // Publicar que parecia não fazer nada.
  const salvar = (e) => {
    const { erro, campo: campo_ruim, dados } = montarAnuncio({
      titulo: campos.titulo.valor(), texto: campos.texto.valor(),
      rotulo: campos.rotulo.valor(), link: campos.link.valor(),
      alvo: alvo.value, produto: qualProduto.value,
      inicio: campos.inicio.valor(), fim: campos.fim.valor(),
      ordem: campos.ordem.valor(), ativo: ativo.checked,
    });
    for (const c of Object.values(campos)) c.entrada.classList.remove("com-erro");
    if (erro) {
      recado(erro, "erro");
      // acender o campo culpado e levar o olho até ele: a ficha rola, e o
      // recado no rodapé não diz onde está o problema
      const culpado = campos[campo_ruim]?.entrada;
      if (culpado) {
        culpado.classList.add("com-erro");
        culpado.scrollIntoView({ block: "center", behavior: "smooth" });
        culpado.focus({ preventScroll: true });
      }
      return;
    }
    agir(e.target, async () => {
      if (novo) await inserir("comunicados", dados);
      else await atualizar("comunicados", { id: `eq.${anuncio.id}` }, dados);
      fecharGaveta();
      await recarregar();
    }, { feito: "Anúncio salvo." });
  };

  abrirGaveta({
    acima: novo ? "Novo anúncio" : "Anúncio",
    titulo: novo ? "Montar anúncio" : anuncio.titulo,
    conteudo: el("div", {}, [
      cartao("O pop-up, como o cliente vai ver", previa),
      cartao("O anúncio", [
        campos.rotulo.no, campos.titulo.no, campos.texto.no, campos.link.no,
      ]),
      cartao("Para quem", [
        el("div", { classe: "campo" }, [el("span", { texto: "Quem recebe" }), alvo]),
        alvoProduto,
        el("p", { classe: "rodape-entrada",
          texto: "“Só quem NÃO tem um módulo” é a oferta: ela some sozinha para quem já " +
                 "comprou. Em qualquer alvo, quem já viu este anúncio não vê outra vez." }),
      ]),
      cartao("Quando", [
        campos.inicio.no, campos.fim.no, campos.ordem.no,
        el("label", { classe: "campo", estilo: "flex-direction:row;align-items:center;gap:8px" },
          [ativo, el("span", { texto: "No ar" })]),
        el("p", { classe: "rodape-entrada",
          texto: "Sem data para terminar, o anúncio fica valendo. A ordem decide quem aparece " +
                 "primeiro quando há mais de um esperando — o menor vem antes." }),
      ]),
      // as ações fecham a ficha inteira, não o último bloco dela
      el("div", { classe: "acoes-linha", estilo: "margin-top:4px" }, [
        el("button", { classe: "botao botao-primario", texto: novo ? "Publicar" : "Salvar",
                       onclick: salvar }),
        novo ? null : el("button", {
          classe: "botao botao-perigo", texto: "Apagar",
          onclick: (e) => {
            if (!confirmar("Apagar este anúncio?")) return;
            agir(e.target, async () => {
              await apagar("comunicados", { id: `eq.${anuncio.id}` });
              fecharGaveta();
              await recarregar();
            }, { feito: "Anúncio apagado." });
          },
        }),
        el("button", { classe: "botao botao-fantasma", texto: "Cancelar", onclick: fecharGaveta }),
      ]),
    ]),
  });
}

/** O que o banco recusaria, dito antes e em português. Vazio = pode gravar. */
function conferirItem(dados, codigo) {
  if (!/^[A-Z][A-Z0-9_]*$/.test(codigo || "")) {
    return "O código usa só letras maiúsculas, números e _ (começando por letra). Ex.: CRM.";
  }
  if (!dados.nome) return "Dê um nome.";
  if (!Number.isFinite(dados.preco) || dados.preco < 0) return "Confira o preço: número igual ou maior que zero.";
  if (dados.preco > 1_000_000) return "Preço alto demais — confira se não sobrou um zero.";
  return "";
}

// ------------------------------------------------------------------ campo ---
function campo(rotulo, valorInicial, { tag = "input", ...atributos } = {}) {
  const entrada = el(tag, { ...atributos, value: tag === "input" ? valorInicial : undefined });
  if (tag === "textarea") entrada.value = valorInicial ?? "";
  const no = el("label", { classe: "campo" }, [el("span", { texto: rotulo }), entrada]);
  return { no, entrada, valor: () => String(entrada.value ?? "") };
}
